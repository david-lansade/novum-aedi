"""Tests de l'application de scan : règles de la base, puis serveur HTTP de bout en bout.

    py -3 avelis_scan/tests_scan.py

Chaque test utilise une base en mémoire et une horloge simulée (aucun fichier n'est modifié).
"""

import json
import sys
import threading
import urllib.error
import urllib.request

import config as C
from base import Base, Refus, normaliser_code, nombre_cartes_kanban


class Horloge:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def avancer(self, s):
        self.t += s


def nouvelle_base():
    h = Horloge()
    return Base(horloge=h), h


def passer(b, h, code, postes, op="OP-01", **params):
    """Valide les étapes aux postes donnés (avance de 2 min entre deux scans)."""
    for poste in postes:
        h.avancer(120)
        r = b.scanner(code, poste, op, "etape", params)
        assert r["niveau"] in ("ok", "attention"), (code, poste, r["message"])
    return r


def test_base_vide_au_depart():
    b, _ = nouvelle_base()
    e = b.etat()
    assert e["pieces"] == 0 and e["evenements"] == 0 and b.cartes() == []


def test_normalisation_des_codes():
    assert normaliser_code(" mod-29-00001 ") == "MOD-29-00001"
    assert normaliser_code("http://192.168.43.5:8000/s/POD-29-00002") == "POD-29-00002"
    assert normaliser_code("AVELIS|MOD-29-00016|type=module|pod=POD-29-00016|lot=LOT-0012") == "MOD-29-00016"


def test_module_complet_et_attributs():
    b, _ = nouvelle_base()
    lot = b.creer_lot("FOUR-C", "Kits sanitaires", 10)
    codes = b.creer_module_complet("Lyon", lots={"pod": lot})
    assert codes[:4] == ["MOD-29-00001", "POD-29-00001", "K2D-29-00001", "OSS-29-00001"], codes
    assert len(codes) == 4 + len(C.COMPOSANTS_SERIE)
    pod = b.piece("POD-29-00001")
    assert pod["parent"] == "MOD-29-00001" and pod["lot"] == lot
    assert pod["destination"] == "Module MOD-29-00001" and "sur site" in pod["origine"]
    assert b.piece("MOD-29-00001")["destination"] == "Lyon"
    assert "FOUR-A" in b.piece("OSS-29-00001")["origine"]
    assert b.creer_module_complet()[0] == "MOD-29-00002"


def test_suivi_complet_d_un_pod_et_temps_par_poste():
    b, h = nouvelle_base()
    b.creer_module_complet("Lyon", avec_composants=False)
    passer(b, h, "POD-29-00001", ["kitting", "pod_1", "pod_2", "pod_3", "pod_4", "controle_pod"])
    o = b.objet("POD-29-00001", "assemblage")
    assert o["prochaine"]["etape"] == C.INTEGRATION and o["actions"][0]["principal"]
    h.avancer(300)
    r = b.scanner("POD-29-00001", "assemblage", "OP-02", "etape", {})
    assert r["niveau"] == "ok" and b.piece("POD-29-00001")["statut"] == "integree", r
    temps = b.temps_par_poste("POD-29-00001")
    assert len(temps) == 6 and temps["Contrôle pod"] == 300, temps   # séjour clos à l'intégration
    assert all(s["t_sortie"] for s in b.sejours("POD-29-00001"))


def test_hors_sequence_refuse_puis_force_avec_motif():
    b, h = nouvelle_base()
    b.creer_module_complet(avec_composants=False)
    r = b.scanner("POD-29-00001", "pod_2", "OP", "etape")
    assert r["niveau"] == "refus" and "attendue" in r["message"], r
    r = b.scanner("POD-29-00001", "pod_2", "OP", "etape", {"force": True})
    assert r["niveau"] == "refus" and "motif" in r["message"]
    r = b.scanner("POD-29-00001", "pod_2", "OP", "etape", {"force": True, "motif": "étiquette abîmée"})
    assert r["niveau"] == "attention" and b.piece("POD-29-00001")["etape"] == "Kitting"
    refus = [e for e in b.evenements() if e["resultat"] == "refuse"]
    assert len(refus) == 2  # chaque refus est tracé avec sa raison


def test_double_scan_ignore():
    b, h = nouvelle_base()
    b.creer_module_complet(avec_composants=False)
    passer(b, h, "MOD-29-00001", ["bureau", "kitting"])
    passer(b, h, "POD-29-00001", ["kitting"])
    passer(b, h, "K2D-29-00001", ["kitting"])
    passer(b, h, "OSS-29-00001", ["reception", "magasin", "kitting"])
    h.avancer(60)
    passer(b, h, "MOD-29-00001", ["assemblage"])
    h.avancer(5)
    r = b.scanner("MOD-29-00001", "assemblage", "OP", "etape")
    assert r["niveau"] == "refus" and "Déjà scanné" in r["message"], r
    h.avancer(C.ANTI_DOUBLE_SCAN_S)
    assert b.scanner("MOD-29-00001", "assemblage", "OP", "etape")["niveau"] in ("ok", "attention")


def test_code_inconnu():
    b, _ = nouvelle_base()
    assert b.objet("POD-29-00099")["genre"] == "inconnu"
    assert b.objet("POD-29-00099")["type_devine"] == "pod"
    r = b.scanner("POD-29-00099", "kitting", "OP", "etape")
    assert r["niveau"] == "refus" and "inconnu" in r["message"]


def test_defaut_puis_retouche():
    b, h = nouvelle_base()
    b.creer_module_complet(avec_composants=False)
    passer(b, h, "POD-29-00001", ["kitting", "pod_1", "pod_2"])
    r = b.scanner("POD-29-00001", "pod_2", "OP", "defaut", {"categorie": "Étanchéité",
                                                            "cause": "Poste (méthode, main-d'œuvre)"})
    assert r["niveau"] == "attention" and b.piece("POD-29-00001")["statut"] == "defaut"
    assert any(c["type"] == "defaut" for c in b.consignes("pod_2"))
    assert b.scanner("POD-29-00001", "pod_3", "OP", "etape")["niveau"] == "refus"
    b.scanner("POD-29-00001", "pod_2", "OP", "retouche")
    assert b.piece("POD-29-00001")["statut"] == "en_cours"
    assert not any(c["type"] == "defaut" for c in b.consignes("pod_2"))  # consigne acquittée
    assert b.defauts("POD-29-00001")[0]["statut"] == "clos"
    passer(b, h, "POD-29-00001", ["pod_3"])


def test_defaut_matiere_bloque_le_lot_et_previent_les_postes():
    b, h = nouvelle_base()
    lot = b.creer_lot("FOUR-C", "Kits sanitaires", 10)
    b.creer_module_complet(lots={"pod": lot, "composant": lot})
    b.creer_module_complet(lots={"pod": lot})
    passer(b, h, "POD-29-00001", ["kitting", "pod_1"])
    passer(b, h, "POD-29-00002", ["kitting"])
    r = b.scanner("POD-29-00001", "pod_1", "OP", "defaut", {"cause": "Matière / lot fournisseur"})
    assert "BLOQUÉ" in r["message"], r
    assert b.piece(lot)["bloque"] == 1
    assert any(lot in c["message"] for c in b.consignes("kitting"))      # POD-29-00002 y est
    r = b.scanner("POD-29-00002", "pod_1", "OP", "etape")
    assert r["niveau"] == "refus" and "ISOLER" in r["message"]
    assert b.objet("MOD-29-00001")["lot_bloque"] == lot                 # contient une pièce du lot
    b.debloquer_lot(lot, "contrôlé")
    assert not any(lot in c["message"] for c in b.consignes("kitting"))
    passer(b, h, "POD-29-00002", ["pod_1"])


def test_seuil_de_defauts_sur_un_lot():
    b, h = nouvelle_base()
    lot = b.creer_lot("FOUR-C")
    for _ in range(2):
        b.creer_module_complet(avec_composants=False, lots={"pod": lot})
    b.scanner("POD-29-00001", "kitting", "OP", "defaut", {"cause": "Inconnue"})
    assert b.piece(lot)["bloque"] == 0
    b.scanner("POD-29-00002", "kitting", "OP", "defaut", {"cause": "Inconnue"})
    assert b.piece(lot)["bloque"] == 1  # 2 défauts = seuil


def test_assemblage_attend_ses_composants_puis_expedition():
    b, h = nouvelle_base()
    b.creer_module_complet("Nantes", avec_composants=False)
    passer(b, h, "MOD-29-00001", ["bureau", "kitting"])
    r = passer(b, h, "MOD-29-00001", ["assemblage"])
    assert r["niveau"] == "attention" and "Attente composant" in r["message"]
    assert any(c["type"] == "attente" for c in b.consignes("assemblage"))
    passer(b, h, "POD-29-00001", ["kitting", "pod_1", "pod_2", "pod_3", "pod_4", "controle_pod", "assemblage"])
    passer(b, h, "K2D-29-00001", ["kitting", "ligne_2d", "assemblage"])
    passer(b, h, "OSS-29-00001", ["reception", "magasin", "kitting", "assemblage"])
    r = passer(b, h, "MOD-29-00001", ["assemblage"])  # fin d'assemblage : tout est intégré
    assert r["niveau"] == "ok", r
    assert not any(c["type"] == "attente" for c in b.consignes("assemblage"))
    passer(b, h, "MOD-29-00001", ["controle_final", "stock_pf"])
    h.avancer(120)
    r = b.scanner("MOD-29-00001", "expedition", "OP", "etape", {"destination": "Nantes"})
    m = b.piece("MOD-29-00001")
    assert r["niveau"] == "ok" and m["statut"] == "expediee" and m["destination"] == "Nantes", r
    evts = [e["evenement"] for e in b.evenements() if e["code"] == "MOD-29-00001" and e["resultat"] == "accepte"]
    for point in ("OF lancé", "Kitting", "Panneaux 2D terminés", "Début assemblage", "Fin assemblage",
                  "Contrôle final OK", "Entrée stock PF", "Expédié"):  # = POINTS_MODULE de la simulation
        assert point in evts, (point, evts)
    assert b.objet("MOD-29-00001", "expedition")["actions"] == []


def test_integration_exige_un_module():
    b, h = nouvelle_base()
    pod = b.creer_piece("pod")
    passer(b, h, pod, ["kitting", "pod_1", "pod_2", "pod_3", "pod_4", "controle_pod"])
    r = b.scanner(pod, "assemblage", "OP", "etape", {})
    assert r["niveau"] == "refus" and "module" in r["message"]
    mod = b.creer_piece("module")
    r = b.scanner(pod, "assemblage", "OP", "etape", {"parent": mod})
    assert r["niveau"] == "ok" and b.piece(pod)["parent"] == mod


def test_cycle_kanban_et_refus():
    b, h = nouvelle_base()
    carte = b.creer_carte("VIS-M8", "Vis M8", 200, "kitting", delai_min=5)
    assert b.scanner(carte, "magasin", "OP", "vide")["niveau"] == "refus"   # pas au bon poste
    assert b.scanner(carte, "kitting", "OP", "vide")["niveau"] == "ok"
    assert any(carte in c["message"] for c in b.consignes("magasin"))
    r = b.scanner(carte, "kitting", "OP", "vide")
    assert r["niveau"] == "refus" and "déjà signalée vide" in r["message"]
    h.avancer(60)
    assert b.scanner(carte, "magasin", "MAG", "prepare")["niveau"] == "ok"
    assert not any("Préparer" in c["message"] for c in b.consignes("magasin"))
    h.avancer(60)
    r = b.scanner(carte, "kitting", "OP", "livre")
    assert r["niveau"] == "ok" and b.carte(carte)["etat"] == "pleine" and b.carte(carte)["cycles"] == 1
    assert b.cartes()[0]["delai_moyen_min"] == 2.0


def test_kanban_en_retard():
    b, h = nouvelle_base()
    carte = b.creer_carte("JNT", "Joints", 20, "pod_2", delai_min=3)
    b.scanner(carte, "pod_2", "OP", "vide")
    h.avancer(120)
    assert b.surveiller_kanban() == 0
    h.avancer(120)
    assert b.surveiller_kanban() == 1 and b.surveiller_kanban() == 0  # alerte envoyée une seule fois
    assert any("RUPTURE" in c["message"] for c in b.consignes("pod_2"))
    b.scanner(carte, "magasin", "OP", "prepare")
    r = b.scanner(carte, "pod_2", "OP", "livre")
    assert r["niveau"] == "attention" and "RETARD" in r["message"]
    assert not any("RUPTURE" in c["message"] for c in b.consignes("pod_2"))


def test_formule_nombre_de_cartes():
    assert nombre_cartes_kanban(60, 0.5, 0.2, 20) == 2
    assert nombre_cartes_kanban(120, 1, 0.25, 20) == 8


def test_poste_obligatoire_et_rebut():
    b, h = nouvelle_base()
    mod = b.creer_piece("module")
    assert b.scanner(mod, "", "OP", "etape")["niveau"] == "refus"
    b.scanner(mod, "bureau", "OP", "rebut", {"motif": "test"})
    assert b.piece(mod)["statut"] == "rebut"
    assert b.scanner(mod, "kitting", "OP", "etape")["niveau"] == "refus"


def test_moyen_d_identification_et_ecriture_nfc():
    b, h = nouvelle_base()
    b.creer_module_complet(avec_composants=False)
    h.avancer(120)
    assert b.scanner("MOD-29-00001", "bureau", "OP", "etape", moyen="nfc")["niveau"] == "ok"
    h.avancer(120)
    b.scanner("MOD-29-00001", "kitting", "OP", "etape", moyen="qr")
    h.avancer(120)
    b.scanner("POD-29-00001", "pod_3", "OP", "etape", moyen="nfc")  # hors séquence : refus
    h.avancer(120)
    b.scanner("POD-29-00001", "kitting", "OP", "etape", moyen="inconnu")
    moyens = [(e["code"], e["evenement"], e["moyen"]) for e in b.evenements()
              if e["evenement"] != "Pièce créée"]
    assert moyens[0] == ("MOD-29-00001", "OF lancé", "nfc"), moyens
    assert ("MOD-29-00001", "Kitting", "qr") in moyens
    assert any(ev.startswith("Refus") and m == "nfc" for _, ev, m in moyens)  # refus tracé
    assert ("POD-29-00001", "Kitting", "") in moyens  # moyen inconnu : non renseigné
    assert "Puce NFC" in b.noter_ecriture_nfc("pod-29-00001", "kitting", "OP")
    ecrite = b.evenements()[-1]
    assert (ecrite["evenement"], ecrite["moyen"], ecrite["resultat"], ecrite["zone"]) == (
        C.EVENEMENT_ECRITURE_NFC, "nfc", "info", "Kitting"), ecrite
    assert b.piece("POD-29-00001")["etape"] == "Kitting"  # écrire une puce ne valide rien
    try:
        b.noter_ecriture_nfc("POD-29-00099", "kitting", "OP")
        raise AssertionError("code inconnu accepté")
    except Refus as refus:
        assert "inconnu" in str(refus)
    carte = b.creer_carte("V", "Vis", 10, "kitting")
    b.noter_ecriture_nfc(carte, "magasin", "OP")
    assert b.evenements()[-1]["type"] == "kanban"


def test_base_existante_mise_a_niveau_pour_le_nfc():
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as dossier:
        chemin = f"{dossier}/ancienne.db"
        ancienne = sqlite3.connect(chemin)
        ancienne.executescript(
            "CREATE TABLE evenements (id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL NOT NULL, "
            "t_client REAL, code TEXT NOT NULL, type TEXT, evenement TEXT, poste TEXT, zone TEXT, "
            "operateur TEXT, resultat TEXT, message TEXT, lot TEXT, force INTEGER DEFAULT 0, "
            "motif TEXT DEFAULT '');"
            "INSERT INTO evenements (t, code, evenement) VALUES (1, 'LOT-0001', 'Réception lot');")
        ancienne.commit()
        ancienne.close()
        b = Base(chemin, horloge=Horloge())
        evenements = b.evenements()
        assert len(evenements) == 1 and evenements[0]["moyen"] == "", evenements
        b.creer_lot("FOUR-A")
        assert b.evenements()[-1]["moyen"] == ""
        b.cx.close()


# ───────────────────────────────────────────────────────────── serveur HTTP
def _requete(url, corps=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(url, donnees, {"Content-Type": "application/json"} if donnees else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def test_serveur_de_bout_en_bout():
    import serveur
    srv, app = serveur.demarrer(":memory:", "127.0.0.1", 0, "127.0.0.1")
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    url = app.url
    try:
        for page in ("/", "/s/POD-29-00001", "/pc"):
            code, corps, typ = _requete(url + page)
            assert code == 200 and b"<html" in corps and "text/html" in typ, page
        code, corps, _ = _requete(url + "/api/config")
        k = json.loads(corps)
        assert code == 200 and len(k["postes"]) == len(C.POSTES) and "module" in k["types"]
        code, corps, _ = _requete(url + "/api/modules", {"nombre": 2, "destination": "Lille"})
        codes = json.loads(corps)["codes"]
        assert code == 200 and "MOD-29-00002" in codes
        assert k["moyens"]["nfc"] == "Puce NFC"
        code, corps, _ = _requete(url + "/api/scan", {"code": "http://x/s/MOD-29-00001?m=nfc", "poste": "bureau",
                                                      "operateur": "OP-01", "action": "etape", "t_client": 1,
                                                      "moyen": "nfc"})
        r = json.loads(corps)
        assert r["niveau"] == "ok" and r["objet"]["piece"]["etape"] == "OF lancé", r
        assert r["objet"]["evenements"][0]["moyen"] == "nfc"
        code, corps, _ = _requete(url + "/api/nfc/ecriture", {"code": "MOD-29-00002", "poste": "bureau",
                                                              "operateur": "OP-01"})
        assert code == 200 and "MOD-29-00002" in json.loads(corps)["message"]
        code, corps, _ = _requete(url + "/api/nfc/ecriture", {"code": "MOD-29-00099", "poste": "bureau"})
        assert code == 400 and "inconnu" in json.loads(corps)["erreur"]
        code, corps, _ = _requete(url + "/api/objet/MOD-29-00001?poste=kitting")
        assert json.loads(corps)["actions"][0]["principal"]
        code, corps, _ = _requete(url + "/api/pieces", {"type_piece": "pod", "code": "MOD-29-00001"})
        assert code == 400 and "existe déjà" in json.loads(corps)["erreur"]
        code, corps, _ = _requete(url + "/api/cartes", {"reference": "V", "designation": "Vis", "quantite": 10,
                                                        "poste_conso": "kitting"})
        carte = json.loads(corps)["code"]
        _requete(url + "/api/scan", {"code": carte, "poste": "kitting", "operateur": "OP", "action": "vide"})
        code, corps, _ = _requete(url + "/api/consignes?poste=magasin")
        assert any(carte in c["message"] for c in json.loads(corps))
        code, corps, typ = _requete(url + "/export/evenements.csv")
        texte = corps.decode("utf-8-sig")
        assert code == 200 and "csv" in typ and "OF lancé" in texte and ";" in texte
        code, corps, _ = _requete(url + "/api/evenements?depuis=0")
        assert len(json.loads(corps)) >= 3
        code, corps, _ = _requete(url + "/etiquettes?codes=MOD-29-00001," + carte)
        assert code == 200 and "MOD-29-00001" in corps.decode() and "CARTE KANBAN" in corps.decode()
        if serveur.qrcode is not None:
            code, corps, typ = _requete(url + "/qr/MOD-29-00001.svg")
            assert code == 200 and corps.lstrip().startswith(b"<svg"), corps[:80]
        code, corps, _ = _requete(url + "/api/vider", {"confirmation": "non"})
        assert code == 400
        code, corps, _ = _requete(url + "/api/vider", {"confirmation": "VIDER"})
        assert json.loads(_requete(url + "/api/etat")[1])["pieces"] == 0
        assert _requete(url + "/api/inexistant")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()


def executer_tests() -> bool:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    echecs = 0
    print(f"Tests de avelis_scan ({len(tests)} tests)")
    for nom, f in tests:
        try:
            f()
        except Exception as e:  # noqa: BLE001
            echecs += 1
            import traceback
            print(f"  ✗ {nom} : {type(e).__name__} : {e}")
            traceback.print_exc()
        else:
            print(f"  ✓ {nom}")
    print(f"{len(tests) - echecs}/{len(tests)} tests réussis")
    return echecs == 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(0 if executer_tests() else 1)
