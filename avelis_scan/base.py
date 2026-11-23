"""Base de données de l'atelier (SQLite) et règles de traçabilité et de kanban.

Ce module ne fait aucun affichage et aucun réseau : serveur.py l'appelle, les tests aussi, et le
futur jumeau numérique pourra lire la même base.

Tables :
  pieces      une ligne par pièce suivie (module, pod, kit 2D, ossature, composant, lot)
  evenements  journal de tous les scans (acceptés, refusés, alertes) : la source de vérité
  sejours     temps passé par chaque pièce à chaque poste (entrée, sortie)
  defauts     défauts déclarés, avec cause présumée et statut
  cartes      cartes kanban (état pleine / vide / en préparation)
  demandes    demandes de réapprovisionnement kanban (une par cycle « vide → livrée »)
  consignes   messages renvoyés vers les postes (lot bloqué, bac à préparer, retard…)

Les instants sont des secondes depuis 1970 (time.time()) : le téléphone les affiche en heure locale.
"""

import math
import re
import sqlite3
import threading
import time

import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS pieces (
    code TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    designation TEXT DEFAULT '',
    reference TEXT DEFAULT '',
    numero_serie TEXT DEFAULT '',
    quantite REAL,
    lot TEXT DEFAULT '',
    fournisseur TEXT DEFAULT '',
    origine TEXT DEFAULT '',
    destination TEXT DEFAULT '',
    parent TEXT DEFAULT '',
    etape_index INTEGER DEFAULT -1,
    etape TEXT DEFAULT '',
    poste TEXT DEFAULT '',
    statut TEXT DEFAULT 'creee',
    bloque INTEGER DEFAULT 0,
    motif_blocage TEXT DEFAULT '',
    t_creation REAL,
    t_derniere REAL,
    t_fin REAL,
    commentaire TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evenements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    t REAL NOT NULL,
    t_client REAL,
    code TEXT NOT NULL,
    type TEXT,
    evenement TEXT,
    poste TEXT,
    zone TEXT,
    operateur TEXT,
    resultat TEXT,
    message TEXT,
    lot TEXT,
    force INTEGER DEFAULT 0,
    motif TEXT DEFAULT '',
    moyen TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sejours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    poste TEXT,
    zone TEXT,
    t_entree REAL,
    t_sortie REAL
);
CREATE TABLE IF NOT EXISTS defauts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    t REAL,
    poste TEXT,
    categorie TEXT,
    cause TEXT,
    gravite TEXT,
    description TEXT,
    operateur TEXT,
    lot TEXT,
    statut TEXT DEFAULT 'ouvert',
    t_cloture REAL,
    action TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cartes (
    code TEXT PRIMARY KEY,
    reference TEXT,
    designation TEXT,
    quantite REAL,
    poste_conso TEXT,
    source TEXT,
    delai_min REAL,
    etat TEXT DEFAULT 'pleine',
    t_etat REAL,
    cycles INTEGER DEFAULT 0,
    demande_id INTEGER
);
CREATE TABLE IF NOT EXISTS demandes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carte TEXT,
    t_vide REAL,
    t_prepa REAL,
    t_livre REAL,
    op_vide TEXT,
    op_prepa TEXT,
    op_livre TEXT,
    en_retard INTEGER DEFAULT 0,
    alerte INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS consignes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    t REAL,
    poste TEXT,
    type TEXT,
    message TEXT,
    code TEXT DEFAULT '',
    cle TEXT DEFAULT '',
    statut TEXT DEFAULT 'active',
    t_acquit REAL,
    op_acquit TEXT
);
CREATE INDEX IF NOT EXISTS i_evt_code ON evenements(code);
CREATE INDEX IF NOT EXISTS i_sej_code ON sejours(code);
CREATE INDEX IF NOT EXISTS i_pieces_lot ON pieces(lot);
CREATE INDEX IF NOT EXISTS i_pieces_parent ON pieces(parent);
CREATE INDEX IF NOT EXISTS i_consignes ON consignes(statut, poste);
"""

POSTES = {p["id"]: p for p in C.POSTES}
STATUTS_FINIS = ("integree", "expediee", "terminee", "rebut")
LIBELLES_STATUT = {"creee": "Créée (pas encore scannée)", "en_cours": "En cours",
                   "defaut": "En défaut", "integree": "Intégrée au module",
                   "expediee": "Expédiée", "terminee": "Gamme terminée", "en_stock": "En stock",
                   "rebut": "Mise au rebut"}


class Refus(Exception):
    """Scan refusé : le message est affiché en rouge sur le téléphone et noté au journal."""


def nom_poste(poste_id: str) -> str:
    return POSTES.get(poste_id, {}).get("nom", poste_id or "—")


def zone_poste(poste_id: str) -> str:
    return POSTES.get(poste_id, {}).get("zone", "")


def normaliser_code(texte: str) -> str:
    """Code lu dans un QR : accepte le code seul, une adresse …/s/<code> ou le format
    AVELIS|<code>|… de avelis_flux."""
    texte = (texte or "").strip()
    m = re.search(r"/s/([^/?#\s]+)", texte)
    if m:
        texte = m.group(1)
    if texte.upper().startswith("AVELIS|"):
        texte = texte.split("|")[1]
    return texte.strip().upper()


def type_depuis_code(code: str) -> str | None:
    """Type deviné à partir du préfixe ; 'kanban' pour une carte."""
    if code.startswith(C.PREFIXE_KANBAN):
        return "kanban"
    for type_piece, definition in C.TYPES.items():
        if code.startswith(definition["prefixe"]):
            return type_piece
    return None


def nombre_cartes_kanban(conso_par_heure: float, delai_h: float, marge: float,
                         quantite_bac: float) -> int:
    """Formule classique : (consommation × délai × (1 + marge)) / quantité par bac, arrondi au-dessus,
    au moins 2 cartes (une en service, une en réapprovisionnement)."""
    if quantite_bac <= 0:
        raise ValueError("quantité par bac nulle")
    return max(2, math.ceil(conso_par_heure * delai_h * (1 + marge) / quantite_bac))


class Base:
    """Accès à la base ; toutes les écritures passent par un verrou (plusieurs téléphones)."""

    def __init__(self, chemin: str = ":memory:", horloge=time.time):
        self.horloge = horloge
        self.verrou = threading.RLock()
        self.cx = sqlite3.connect(chemin, check_same_thread=False, isolation_level=None)
        self.cx.row_factory = sqlite3.Row
        if chemin != ":memory:":
            self.cx.execute("PRAGMA journal_mode=WAL")
        self.cx.executescript(SCHEMA)
        self._migrer()
        self._moyen = ""  # moyen d'identification du scan en cours (QR, NFC, saisie)

    def _migrer(self) -> None:
        """Base créée avant l'ajout du NFC : colonne « moyen » ajoutée, données conservées."""
        colonnes = {r["name"] for r in self.cx.execute("PRAGMA table_info(evenements)")}
        if "moyen" not in colonnes:
            self.cx.execute("ALTER TABLE evenements ADD COLUMN moyen TEXT DEFAULT ''")

    # ───────────────────────────────────────────────────────────────── outils
    def _un(self, sql, *args):
        r = self.cx.execute(sql, args).fetchone()
        return dict(r) if r else None

    def _tous(self, sql, *args):
        return [dict(r) for r in self.cx.execute(sql, args).fetchall()]

    def _transaction(self):
        return _Transaction(self)

    def _evenement(self, code, type_objet, evenement, poste, operateur, resultat, message="",
                   lot="", t_client=None, force=0, motif=""):
        self.cx.execute(
            "INSERT INTO evenements (t, t_client, code, type, evenement, poste, zone, operateur, "
            "resultat, message, lot, force, motif, moyen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.horloge(), t_client, code, type_objet, evenement, poste, zone_poste(poste),
             operateur or "", resultat, message, lot or "", int(force), motif or "",
             self._moyen))

    def _consigne(self, poste, type_consigne, message, code="", cle=""):
        """Nouvelle consigne active ; une consigne de même clé encore active n'est pas doublée."""
        if cle and self._un("SELECT id FROM consignes WHERE cle=? AND statut='active'", cle):
            return
        self.cx.execute("INSERT INTO consignes (t, poste, type, message, code, cle) VALUES "
                        "(?,?,?,?,?,?)", (self.horloge(), poste, type_consigne, message, code, cle))

    def _acquitter_cle(self, motif_cle: str, operateur="auto"):
        self.cx.execute("UPDATE consignes SET statut='acquittee', t_acquit=?, op_acquit=? "
                        "WHERE statut='active' AND cle LIKE ?", (self.horloge(), operateur, motif_cle))

    def _prochain_numero(self, prefixe: str) -> int:
        maxi = 0
        for (code,) in self.cx.execute("SELECT code FROM pieces WHERE code LIKE ? UNION "
                                       "SELECT code FROM cartes WHERE code LIKE ?",
                                       (prefixe + "%", prefixe + "%")):
            m = re.match(r"(\d+)", code[len(prefixe):])
            if m:
                maxi = max(maxi, int(m.group(1)))
        return maxi + 1

    # ───────────────────────────────────────────────────────────────── création
    def creer_piece(self, type_piece: str, code: str = "", designation: str = "", reference="",
                    numero_serie="", quantite=None, lot="", fournisseur="", origine="",
                    destination="", parent="", commentaire="", operateur="PC") -> str:
        if type_piece not in C.TYPES:
            raise Refus(f"Type inconnu : {type_piece}")
        definition = C.TYPES[type_piece]
        with self.verrou, self._transaction():
            code = normaliser_code(code)
            if not code:
                chiffres = C.CHIFFRES_NUMERO.get(type_piece, 5)
                code = f"{definition['prefixe']}{self._prochain_numero(definition['prefixe']):0{chiffres}d}"
            if self._un("SELECT code FROM pieces WHERE code=?", code) or \
                    self._un("SELECT code FROM cartes WHERE code=?", code):
                raise Refus(f"Le code {code} existe déjà")
            lot = normaliser_code(lot)
            parent = normaliser_code(parent)
            if lot and type_piece != "lot" and not self._un("SELECT code FROM pieces WHERE code=?", lot):
                raise Refus(f"Lot {lot} inconnu : créez d'abord le lot")
            if parent and not self._un("SELECT code FROM pieces WHERE code=? AND type='module'", parent):
                raise Refus(f"Module parent {parent} inconnu")
            if not origine:
                if type_piece in ("ossature", "composant", "lot"):
                    origine = f"Fournisseur {fournisseur} ({C.FOURNISSEURS.get(fournisseur, '?')})" \
                        if fournisseur else "Fournisseur"
                else:
                    origine = "Fabriqué sur site (Torcy)"
            if not destination and parent:
                destination = f"Module {parent}"
            t = self.horloge()
            self.cx.execute(
                "INSERT INTO pieces (code, type, designation, reference, numero_serie, quantite, lot, "
                "fournisseur, origine, destination, parent, statut, t_creation, t_derniere, "
                "commentaire) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code, type_piece, designation or definition["libelle"], reference, numero_serie,
                 quantite, lot, fournisseur, origine, destination, parent, "creee", t, t, commentaire))
            self._evenement(code, type_piece, "Pièce créée", "", operateur, "info",
                            f"{definition['libelle']} – {designation}".strip(" –"), lot)
        return code

    def creer_lot(self, fournisseur: str, reference: str = "", quantite=None, code="",
                  designation="") -> str:
        return self.creer_piece("lot", code=code, fournisseur=fournisseur, reference=reference,
                                quantite=quantite,
                                designation=designation or f"Lot {C.FOURNISSEURS.get(fournisseur, fournisseur)}")

    def creer_module_complet(self, destination: str = "", avec_composants: bool = True,
                             lots: dict | None = None) -> list[str]:
        """Module + pod + kit 2D + ossature (+ composants série), même numéro, reliés au module."""
        lots = lots or {}
        with self.verrou:
            n = self._prochain_numero(C.TYPES["module"]["prefixe"])
            num = f"{n:05d}"
            module = self.creer_piece("module", f"MOD-29-{num}", "Module 3D T1 (1 logement)",
                                      destination=destination)
            codes = [module]
            for type_piece, designation, fournisseur in C.COMPOSITION_MODULE:
                codes.append(self.creer_piece(type_piece, C.TYPES[type_piece]["prefixe"] + num,
                                              designation, fournisseur=fournisseur,
                                              lot=lots.get(type_piece, ""), parent=module))
            if avec_composants:
                for suffixe, designation, fournisseur in C.COMPOSANTS_SERIE:
                    codes.append(self.creer_piece(
                        "composant", f"CMP-29-{num}-{suffixe}", designation, fournisseur=fournisseur,
                        numero_serie=f"SN-{suffixe}-{num}", lot=lots.get("composant", ""),
                        parent=module))
        return codes

    def creer_carte(self, reference: str, designation: str, quantite: float, poste_conso: str,
                    source: str = "Magasin", delai_min: float | None = None, code: str = "") -> str:
        if poste_conso not in POSTES:
            raise Refus(f"Poste inconnu : {poste_conso}")
        with self.verrou, self._transaction():
            code = normaliser_code(code) or f"{C.PREFIXE_KANBAN}{self._prochain_numero(C.PREFIXE_KANBAN):03d}"
            if self._un("SELECT code FROM cartes WHERE code=?", code) or \
                    self._un("SELECT code FROM pieces WHERE code=?", code):
                raise Refus(f"Le code {code} existe déjà")
            self.cx.execute(
                "INSERT INTO cartes (code, reference, designation, quantite, poste_conso, source, "
                "delai_min, etat, t_etat) VALUES (?,?,?,?,?,?,?,?,?)",
                (code, reference, designation, quantite, poste_conso, source,
                 delai_min if delai_min else C.DELAI_KANBAN_MIN, "pleine", self.horloge()))
            self._evenement(code, "kanban", "Carte créée", "", "PC", "info",
                            f"{quantite:g} × {designation} → {nom_poste(poste_conso)}")
        return code

    # ───────────────────────────────────────────────────────────────── lecture
    def piece(self, code):
        return self._un("SELECT * FROM pieces WHERE code=?", code)

    def carte(self, code):
        return self._un("SELECT * FROM cartes WHERE code=?", code)

    def enfants(self, code):
        return self._tous("SELECT * FROM pieces WHERE parent=? ORDER BY code", code)

    def _gamme(self, piece):
        return C.TYPES[piece["type"]]["gamme"]

    def prochaine_etape(self, piece):
        gamme = self._gamme(piece)
        i = piece["etape_index"] + 1
        return (i, *gamme[i]) if i < len(gamme) else None

    def lot_bloque(self, piece) -> str:
        """Lot bloqué de la pièce (le sien, ou celui d'une pièce qu'elle contient), sinon ''."""
        if piece["type"] == "lot":
            return piece["code"] if piece["bloque"] else ""
        lots = {piece["lot"]} | {e["lot"] for e in self.enfants(piece["code"])}
        for lot in sorted(l for l in lots if l):
            r = self._un("SELECT bloque FROM pieces WHERE code=?", lot)
            if r and r["bloque"]:
                return lot
        return ""

    def sejours(self, code):
        maintenant = self.horloge()
        lignes = self._tous("SELECT * FROM sejours WHERE code=? ORDER BY t_entree", code)
        for s in lignes:
            s["poste_nom"] = nom_poste(s["poste"])
            s["duree_s"] = (s["t_sortie"] or maintenant) - s["t_entree"]
            s["en_cours"] = s["t_sortie"] is None
        return lignes

    def temps_par_poste(self, code) -> dict:
        total = {}
        for s in self.sejours(code):
            total[s["poste_nom"]] = total.get(s["poste_nom"], 0) + s["duree_s"]
        return total

    def defauts(self, code=None, ouverts=False):
        sql, args = "SELECT * FROM defauts WHERE 1=1", []
        if code:
            sql += " AND code=?"
            args.append(code)
        if ouverts:
            sql += " AND statut='ouvert'"
        return self._tous(sql + " ORDER BY t DESC", *args)

    def _actions_piece(self, p, poste) -> tuple[list, str]:
        """Boutons proposés sur le téléphone pour cette pièce à ce poste, et message d'état."""
        if p["statut"] in STATUTS_FINIS:
            return [], f"{LIBELLES_STATUT[p['statut']]} : plus aucune étape à valider."
        actions, message = [], ""
        lot = self.lot_bloque(p)
        if lot:
            return ([{"id": "rebut", "libelle": "Mettre au rebut", "danger": True}],
                    f"PIÈCE À ISOLER : lot {lot} bloqué.")
        if p["statut"] == "defaut":
            return ([{"id": "retouche", "libelle": "Retouche terminée (défaut corrigé)", "principal": True},
                     {"id": "rebut", "libelle": "Mettre au rebut", "danger": True}],
                    "Défaut ouvert : retouche à faire avant de continuer.")
        suivante = self.prochaine_etape(p)
        if suivante:
            _, etape, poste_attendu = suivante
            champs = []
            if etape == C.INTEGRATION:
                champs = [{"nom": "parent", "libelle": "Module (scanner ou saisir)", "valeur": p["parent"]}]
            elif etape == C.EXPEDITION:
                champs = [{"nom": "destination", "libelle": "Chantier de destination",
                           "valeur": p["destination"], "choix": C.CHANTIERS}]
            if poste_attendu == poste:
                actions.append({"id": "etape", "libelle": f"Valider : {etape}", "principal": True,
                                "champs": champs})
            else:
                message = f"Étape attendue : « {etape} » au poste {nom_poste(poste_attendu)}."
                actions.append({"id": "etape", "libelle": f"Forcer « {etape} » ici (hors séquence)",
                                "force": True, "champs": champs + [
                                    {"nom": "motif", "libelle": "Motif obligatoire", "valeur": ""}]})
        actions.append({"id": "defaut", "libelle": "Déclarer un défaut", "danger": True})
        actions.append({"id": "rebut", "libelle": "Mettre au rebut", "danger": True})
        return actions, message

    def _actions_carte(self, c, poste) -> tuple[list, str]:
        etat = c["etat"]
        if etat == "pleine":
            if poste == c["poste_conso"]:
                return [{"id": "vide", "libelle": "Bac vide → demander le réappro", "principal": True}], ""
            return [], f"Carte du poste {nom_poste(c['poste_conso'])} : le bac y est plein."
        demande = self._un("SELECT * FROM demandes WHERE id=?", c["demande_id"]) or {}
        if etat == "vide":
            if poste == C.POSTE_MAGASIN:
                return [{"id": "prepare", "libelle": "Bac préparé (en route)", "principal": True}], ""
            return [], "Déjà signalé vide : en attente de préparation au magasin."
        if poste == c["poste_conso"]:
            return [{"id": "livre", "libelle": "Bac livré au poste", "principal": True}], ""
        return [], f"Bac en route vers {nom_poste(c['poste_conso'])}."

    def objet(self, code: str, poste: str = "") -> dict:
        """Tout ce que le téléphone ou le PC affiche pour un code scanné."""
        code = normaliser_code(code)
        with self.verrou:
            p = self.piece(code)
            if p:
                actions, message = self._actions_piece(p, poste)
                gamme = [{"etape": e, "poste": po, "poste_nom": nom_poste(po),
                          "faite": i <= p["etape_index"]} for i, (e, po) in enumerate(self._gamme(p))]
                suivante = self.prochaine_etape(p)
                return {"genre": "piece", "code": code, "piece": p,
                        "type_libelle": C.TYPES[p["type"]]["libelle"],
                        "statut_libelle": LIBELLES_STATUT.get(p["statut"], p["statut"]),
                        "poste_nom": nom_poste(p["poste"]),
                        "prochaine": {"etape": suivante[1], "poste": suivante[2],
                                      "poste_nom": nom_poste(suivante[2])} if suivante else None,
                        "gamme": gamme, "lot_bloque": self.lot_bloque(p),
                        "lot_info": self.piece(p["lot"]) if p["lot"] else None,
                        "parent_info": self.piece(p["parent"]) if p["parent"] else None,
                        "enfants": self.enfants(code), "sejours": self.sejours(code),
                        "temps_par_poste": self.temps_par_poste(code),
                        "defauts": self.defauts(code),
                        "evenements": self._tous("SELECT * FROM evenements WHERE code=? ORDER BY id DESC "
                                                 "LIMIT 60", code),
                        "actions": actions, "message": message}
            c = self.carte(code)
            if c:
                actions, message = self._actions_carte(c, poste)
                return {"genre": "carte", "code": code, "carte": c,
                        "poste_nom": nom_poste(c["poste_conso"]),
                        "demande": self._un("SELECT * FROM demandes WHERE id=?", c["demande_id"]),
                        "historique": self._tous("SELECT * FROM demandes WHERE carte=? ORDER BY id DESC "
                                                 "LIMIT 20", code),
                        "actions": actions, "message": message}
        return {"genre": "inconnu", "code": code, "type_devine": type_depuis_code(code)}

    # ───────────────────────────────────────────────────────────────── scan
    def scanner(self, code: str, poste: str, operateur: str, action: str, params: dict | None = None,
                t_client: float | None = None, moyen: str = "") -> dict:
        """Applique une action scannée. Renvoie {niveau: ok | attention | info | refus, message,
        objet}. Un refus est noté au journal avec sa raison ; chaque événement garde le moyen
        d'identification (qr, nfc, saisie ; vide s'il n'est pas connu)."""
        params = params or {}
        code = normaliser_code(code)
        if poste not in POSTES:
            return {"niveau": "refus", "message": "Choisissez d'abord votre poste."}
        with self.verrou:
            self._moyen = moyen if moyen in C.MOYENS_IDENTIFICATION else ""
            try:
                return self._scanner(code, poste, operateur, action, params, t_client)
            finally:
                self._moyen = ""

    def noter_ecriture_nfc(self, code: str, poste: str, operateur: str) -> str:
        """Trace l'écriture d'une puce NFC pour une pièce ou une carte kanban existante."""
        code = normaliser_code(code)
        with self.verrou:
            p, c = self.piece(code), self.carte(code)
            if not p and not c:
                raise Refus(f"Code {code} inconnu : impossible de lui associer une puce NFC.")
            self._moyen = "nfc"
            try:
                with self._transaction():
                    self._evenement(code, p["type"] if p else "kanban", C.EVENEMENT_ECRITURE_NFC,
                                    poste, operateur, "info", "puce associée à ce code",
                                    (p or {}).get("lot", ""))
            finally:
                self._moyen = ""
        return f"Puce NFC écrite pour {code}."

    def _scanner(self, code, poste, operateur, action, params, t_client) -> dict:
        """Corps de scanner(), verrou pris."""
        p, c = self.piece(code), self.carte(code)
        try:
            if not p and not c:
                raise Refus(f"Code {code} inconnu : il faut d'abord créer la pièce.")
            with self._transaction():
                if c:
                    niveau, message = self._action_carte(c, poste, operateur, action, t_client)
                else:
                    niveau, message = self._action_piece(p, poste, operateur, action, params, t_client)
        except Refus as refus:
            self._evenement(code, (p or {}).get("type", "kanban" if c else "?"),
                            f"Refus : {action}", poste, operateur, "refuse", str(refus),
                            (p or {}).get("lot", ""), t_client)
            return {"niveau": "refus", "message": str(refus), "objet": self.objet(code, poste)}
        return {"niveau": niveau, "message": message, "objet": self.objet(code, poste)}

    def _doublon(self, code, poste) -> float | None:
        r = self._un("SELECT t FROM evenements WHERE code=? AND poste=? AND resultat='accepte' "
                     "ORDER BY id DESC LIMIT 1", code, poste)
        if r and self.horloge() - r["t"] < C.ANTI_DOUBLE_SCAN_S:
            return self.horloge() - r["t"]
        return None

    def _action_piece(self, p, poste, operateur, action, params, t_client):
        code, lot = p["code"], p["lot"]
        if p["statut"] in STATUTS_FINIS:
            raise Refus(f"{code} : {LIBELLES_STATUT[p['statut']]}, aucune action possible.")
        if action == "etape":
            return self._valider_etape(p, poste, operateur, params, t_client)
        if action == "defaut":
            return self._declarer_defaut(p, poste, operateur, params, t_client)
        if action == "retouche":
            if p["statut"] != "defaut":
                raise Refus("Aucun défaut ouvert sur cette pièce.")
            t = self.horloge()
            self.cx.execute("UPDATE defauts SET statut='clos', t_cloture=?, action='Retouche' "
                            "WHERE code=? AND statut='ouvert'", (t, code))
            statut = "en_cours" if p["etape_index"] >= 0 else "creee"
            self.cx.execute("UPDATE pieces SET statut=?, t_derniere=? WHERE code=?", (statut, t, code))
            self._acquitter_cle(f"defaut:{code}", operateur)
            self._evenement(code, p["type"], "Retouche OK", poste, operateur, "accepte", "", lot, t_client)
            return "ok", f"{code} : retouche enregistrée, la pièce reprend sa gamme."
        if action == "rebut":
            t = self.horloge()
            self.cx.execute("UPDATE pieces SET statut='rebut', t_fin=?, t_derniere=? WHERE code=?",
                            (t, t, code))
            self.cx.execute("UPDATE defauts SET statut='rebut', t_cloture=?, action='Rebut' "
                            "WHERE code=? AND statut='ouvert'", (t, code))
            self._fermer_sejour(code, t)
            self._acquitter_cle(f"defaut:{code}", operateur)
            self._evenement(code, p["type"], "Mise au rebut", poste, operateur, "alerte",
                            params.get("motif", ""), lot, t_client)
            return "attention", f"{code} mis au rebut."
        raise Refus(f"Action inconnue : {action}")

    def _valider_etape(self, p, poste, operateur, params, t_client):
        code = p["code"]
        lot = self.lot_bloque(p)
        if lot:
            raise Refus(f"PIÈCE À ISOLER : le lot {lot} est bloqué.")
        if p["statut"] == "defaut":
            raise Refus("Défaut ouvert : faites la retouche (ou le rebut) avant de continuer.")
        suivante = self.prochaine_etape(p)
        if not suivante:
            raise Refus("Gamme déjà terminée.")
        index, etape, poste_attendu = suivante
        force = bool(params.get("force"))
        motif = (params.get("motif") or "").strip()
        if poste_attendu != poste:
            if not force:
                raise Refus(f"Hors séquence : l'étape attendue est « {etape} » au poste "
                            f"{nom_poste(poste_attendu)}.")
            if not motif:
                raise Refus("Un motif est obligatoire pour forcer une étape.")
        ecart = self._doublon(code, poste)
        if ecart is not None and not force:
            raise Refus(f"Déjà scanné à ce poste il y a {ecart:.0f} s (double scan ignoré).")
        t = self.horloge()
        niveau, messages = "ok", [f"{code} : « {etape} » enregistré."]
        maj = {"etape_index": index, "etape": etape, "poste": poste, "statut": "en_cours",
               "t_derniere": t}
        if etape == C.INTEGRATION:
            parent = normaliser_code(params.get("parent") or p["parent"])
            module = self.piece(parent) if parent else None
            if not module or module["type"] != "module":
                raise Refus("Indiquez le module dans lequel la pièce est intégrée.")
            if module["statut"] in STATUTS_FINIS:
                raise Refus(f"Le module {parent} est déjà {LIBELLES_STATUT[module['statut']].lower()}.")
            maj.update(parent=parent, statut="integree", t_fin=t, destination=f"Module {parent}")
            messages = [f"{code} intégré au module {parent}."]
        elif etape == C.EXPEDITION:
            destination = (params.get("destination") or p["destination"] or "").strip()
            if not destination:
                raise Refus("Indiquez le chantier de destination.")
            manquants = [e["code"] for e in self.enfants(code) if e["statut"] not in ("integree", "rebut")]
            if manquants:
                niveau = "attention"
                messages.append("Attention : pièces non intégrées : " + ", ".join(manquants))
            maj.update(statut="expediee", t_fin=t, destination=destination)
            messages = [f"{code} expédié vers {destination}."] + messages[1:]
        elif index == len(self._gamme(p)) - 1:
            maj.update(statut="en_stock" if p["type"] == "lot" else "terminee", t_fin=t)
        if p["type"] == "module" and etape in ("Début assemblage", "Fin assemblage"):
            # au début : chaque composant doit être prêt (sa prochaine étape est l'intégration) ;
            # à la fin : chaque composant doit être intégré
            en_retard = [e for e in self.enfants(code) if e["statut"] not in ("integree", "rebut") and (
                etape == "Fin assemblage" or (self.prochaine_etape(e) or (0, ""))[1] != C.INTEGRATION)]
            if en_retard:
                niveau = "attention"
                detail = ", ".join(f"{e['code']} ({nom_poste(e['poste']) if e['poste'] else 'pas encore scanné'})"
                                   for e in en_retard)
                messages.append("Attente composant : " + detail)
                self._consigne("assemblage", "attente", f"{code} : composants pas encore intégrés : {detail}",
                               code, f"attente:{code}")
            else:
                self._acquitter_cle(f"attente:{code}")
        self.cx.execute("UPDATE pieces SET " + ", ".join(f"{k}=?" for k in maj) + " WHERE code=?",
                        (*maj.values(), code))
        # temps passé à chaque poste
        if maj["statut"] in ("integree", "expediee"):
            self._fermer_sejour(code, t)
        else:
            self._entrer_poste(code, poste, t)
        if p["type"] == "module" and etape in ("Début assemblage", "Fin assemblage") and niveau == "ok":
            self._acquitter_cle(f"attente:{code}")
        if etape == C.INTEGRATION:
            self._evenement(maj["parent"], "module", f"Intégration {C.TYPES[p['type']]['libelle']}",
                            poste, operateur, "info", code, p["lot"], t_client)
        self._evenement(code, p["type"], etape, poste, operateur, "accepte", " · ".join(messages[1:]),
                        p["lot"], t_client, int(force), motif)
        if p["type"] == "kit2d" and etape in C.ETAPES_RECOPIEES_SUR_MODULE and p["parent"]:
            self._evenement(p["parent"], "module", etape, poste, operateur, "accepte", f"via {code}",
                            p["lot"], t_client)
        if force:
            niveau = "attention"
            messages.append(f"Étape forcée (motif : {motif}).")
        return niveau, " ".join(messages)

    def _entrer_poste(self, code, poste, t):
        ouvert = self._un("SELECT * FROM sejours WHERE code=? AND t_sortie IS NULL", code)
        if ouvert and ouvert["poste"] == poste:
            return
        if ouvert:
            self.cx.execute("UPDATE sejours SET t_sortie=? WHERE id=?", (t, ouvert["id"]))
        self.cx.execute("INSERT INTO sejours (code, poste, zone, t_entree) VALUES (?,?,?,?)",
                        (code, poste, zone_poste(poste), t))

    def _fermer_sejour(self, code, t):
        self.cx.execute("UPDATE sejours SET t_sortie=? WHERE code=? AND t_sortie IS NULL", (t, code))

    def _declarer_defaut(self, p, poste, operateur, params, t_client):
        code = p["code"]
        categorie = params.get("categorie") or "Autre"
        cause = params.get("cause") or "Inconnue"
        if cause not in C.CAUSES_DEFAUT:
            raise Refus(f"Cause inconnue : {cause}")
        gravite = params.get("gravite") or "Mineure"
        description = (params.get("description") or "").strip()
        lot = p["code"] if p["type"] == "lot" else p["lot"]
        t = self.horloge()
        self.cx.execute("INSERT INTO defauts (code, t, poste, categorie, cause, gravite, description, "
                        "operateur, lot) VALUES (?,?,?,?,?,?,?,?,?)",
                        (code, t, poste, categorie, cause, gravite, description, operateur, lot))
        self.cx.execute("UPDATE pieces SET statut='defaut', poste=?, t_derniere=? WHERE code=?", (poste, t, code))
        self._entrer_poste(code, poste, t)
        message = f"{categorie} ({gravite}) – cause présumée : {cause}" + (f" – {description}" if description else "")
        self._evenement(code, p["type"], "Défaut déclaré", poste, operateur, "alerte", message, lot, t_client)
        self._consigne(poste, "defaut", f"Défaut sur {code} : {message}. Isoler et retoucher.", code,
                       f"defaut:{code}")
        textes = [f"Défaut enregistré sur {code}."]
        if lot:
            nb = self._un("SELECT COUNT(*) AS n FROM defauts WHERE lot=?", lot)["n"]
            if C.CAUSES_DEFAUT[cause] or nb >= C.SEUIL_DEFAUTS_LOT:
                raison = (f"cause « {cause} »" if C.CAUSES_DEFAUT[cause]
                          else f"{nb} défauts sur ce lot (seuil {C.SEUIL_DEFAUTS_LOT})")
                isolees = self.bloquer_lot(lot, raison, operateur, _dans_transaction=True)
                textes.append(f"Lot {lot} BLOQUÉ ({raison}) : {isolees} pièce(s) à isoler.")
        return "attention", " ".join(textes)

    # ───────────────────────────────────────────────────────────────── lots
    def bloquer_lot(self, lot: str, motif: str, operateur="PC", _dans_transaction=False) -> int:
        """Bloque un lot et envoie une consigne aux postes où se trouvent ses pièces."""
        lot = normaliser_code(lot)
        with self.verrou:
            if _dans_transaction:
                return self._bloquer_lot(lot, motif, operateur)
            with self._transaction():
                return self._bloquer_lot(lot, motif, operateur)

    def _bloquer_lot(self, lot, motif, operateur):
        if not self.piece(lot):
            raise Refus(f"Lot {lot} inconnu.")
        t = self.horloge()
        self.cx.execute("UPDATE pieces SET bloque=1, motif_blocage=? WHERE code=?", (motif, lot))
        concernees = self._tous("SELECT * FROM pieces WHERE lot=? AND statut NOT IN ('expediee','rebut')", lot)
        modules = {e["parent"] for e in concernees if e["parent"]}
        par_poste = {}
        for e in concernees:
            par_poste.setdefault(e["poste"] or C.POSTE_MAGASIN, []).append(e["code"])
        for m in sorted(modules):
            mod = self.piece(m)
            if mod and mod["statut"] not in ("expediee", "rebut"):
                par_poste.setdefault(mod["poste"] or "bureau", []).append(m)
        for poste, codes in par_poste.items():
            self._consigne(poste, "blocage", f"LOT {lot} BLOQUÉ ({motif}) : isoler {', '.join(codes)}",
                           lot, f"lot:{lot}:{poste}")
        self._consigne("*", "blocage", f"Lot {lot} bloqué : {motif}", lot, f"lot:{lot}:*")
        self._evenement(lot, "lot", "Lot bloqué", "", operateur, "alerte", motif, lot)
        return len(concernees) + len(modules)

    def debloquer_lot(self, lot: str, motif: str = "", operateur="PC"):
        lot = normaliser_code(lot)
        with self.verrou, self._transaction():
            if not self.piece(lot):
                raise Refus(f"Lot {lot} inconnu.")
            self.cx.execute("UPDATE pieces SET bloque=0, motif_blocage='' WHERE code=?", (lot,))
            self._acquitter_cle(f"lot:{lot}:%", operateur)
            self._evenement(lot, "lot", "Lot débloqué", "", operateur, "info", motif, lot)

    # ───────────────────────────────────────────────────────────────── kanban
    def _action_carte(self, c, poste, operateur, action, t_client):
        code, t = c["code"], self.horloge()
        conso = nom_poste(c["poste_conso"])
        if action == "vide":
            if c["etat"] != "pleine":
                d = self._un("SELECT t_vide FROM demandes WHERE id=?", c["demande_id"])
                quand = time.strftime("%H:%M", time.localtime(d["t_vide"])) if d else "?"
                raise Refus(f"Carte {code} déjà signalée vide à {quand}.")
            if poste != c["poste_conso"]:
                raise Refus(f"Le bac vide se signale au poste consommateur ({conso}).")
            cur = self.cx.execute("INSERT INTO demandes (carte, t_vide, op_vide) VALUES (?,?,?)",
                                  (code, t, operateur))
            self.cx.execute("UPDATE cartes SET etat='vide', t_etat=?, demande_id=? WHERE code=?",
                            (t, cur.lastrowid, code))
            self._consigne(C.POSTE_MAGASIN, "kanban",
                           f"Préparer {c['quantite']:g} × {c['designation']} ({c['reference']}) → {conso} "
                           f"[carte {code}, délai {c['delai_min']:g} min]", code, f"kanban:{code}")
            self._evenement(code, "kanban", "Bac vide", poste, operateur, "accepte",
                            f"Demande de réapprovisionnement envoyée au magasin", "", t_client)
            return "ok", f"Demande envoyée au magasin : {c['quantite']:g} × {c['designation']}."
        if action == "prepare":
            if c["etat"] != "vide":
                raise Refus(f"Carte {code} : rien à préparer (état « {c['etat']} »).")
            if poste != C.POSTE_MAGASIN:
                raise Refus(f"La préparation se valide au poste {nom_poste(C.POSTE_MAGASIN)}.")
            self.cx.execute("UPDATE demandes SET t_prepa=?, op_prepa=? WHERE id=?",
                            (t, operateur, c["demande_id"]))
            self.cx.execute("UPDATE cartes SET etat='en_preparation', t_etat=? WHERE code=?", (t, code))
            self._acquitter_cle(f"kanban:{code}", operateur)
            self._consigne(c["poste_conso"], "kanban", f"Bac {c['designation']} en route [carte {code}]",
                           code, f"kanban_livraison:{code}")
            self._evenement(code, "kanban", "Bac préparé", poste, operateur, "accepte", "", "", t_client)
            return "ok", f"Bac préparé : à livrer au poste {conso}."
        if action == "livre":
            if c["etat"] != "en_preparation":
                raise Refus(f"Carte {code} : aucun bac en route (état « {c['etat']} »).")
            if poste != c["poste_conso"]:
                raise Refus(f"La livraison se valide au poste consommateur ({conso}).")
            d = self._un("SELECT * FROM demandes WHERE id=?", c["demande_id"])
            duree_min = (t - d["t_vide"]) / 60
            retard = int(duree_min > c["delai_min"])
            self.cx.execute("UPDATE demandes SET t_livre=?, op_livre=?, en_retard=? WHERE id=?",
                            (t, operateur, retard, d["id"]))
            self.cx.execute("UPDATE cartes SET etat='pleine', t_etat=?, demande_id=NULL, cycles=cycles+1 "
                            "WHERE code=?", (t, code))
            self._acquitter_cle(f"kanban%:{code}", operateur)
            self._acquitter_cle(f"kanban_retard:{code}:%", operateur)
            self._evenement(code, "kanban", "Bac livré", poste, operateur, "accepte",
                            f"Réapprovisionné en {duree_min:.1f} min (cible {c['delai_min']:g})", "", t_client)
            return ("attention" if retard else "ok",
                    f"Bac livré en {duree_min:.1f} min" + (" : EN RETARD." if retard else "."))
        raise Refus(f"Action inconnue pour une carte kanban : {action}")

    def surveiller_kanban(self) -> int:
        """Demandes ouvertes au-delà du délai cible : consigne « risque de rupture » (une fois)."""
        n = 0
        with self.verrou, self._transaction():
            t = self.horloge()
            for d in self._tous("SELECT d.*, c.delai_min, c.poste_conso, c.designation FROM demandes d "
                                "JOIN cartes c ON c.code=d.carte WHERE d.t_livre IS NULL AND d.alerte=0"):
                attente = (t - d["t_vide"]) / 60
                if attente > d["delai_min"]:
                    self.cx.execute("UPDATE demandes SET alerte=1, en_retard=1 WHERE id=?", (d["id"],))
                    texte = (f"RISQUE DE RUPTURE : {d['designation']} (carte {d['carte']}) vide depuis "
                             f"{attente:.0f} min, cible {d['delai_min']:g} min")
                    for poste in (d["poste_conso"], C.POSTE_MAGASIN):
                        self._consigne(poste, "retard", texte, d["carte"], f"kanban_retard:{d['carte']}:{poste}")
                    self._evenement(d["carte"], "kanban", "Retard réapprovisionnement", "", "auto",
                                    "alerte", texte)
                    n += 1
        return n

    def cartes(self):
        lignes = self._tous("SELECT * FROM cartes ORDER BY code")
        t = self.horloge()
        for c in lignes:
            c["poste_nom"] = nom_poste(c["poste_conso"])
            d = self._un("SELECT * FROM demandes WHERE id=?", c["demande_id"]) if c["demande_id"] else None
            c["attente_min"] = (t - d["t_vide"]) / 60 if d else None
            c["en_retard"] = bool(d and c["attente_min"] > c["delai_min"])
            stats = self._un("SELECT COUNT(*) AS n, AVG((t_livre-t_vide)/60.0) AS moy, SUM(en_retard) AS r "
                             "FROM demandes WHERE carte=? AND t_livre IS NOT NULL", c["code"])
            c["delai_moyen_min"], c["retards"] = stats["moy"], stats["r"] or 0
        return lignes

    # ───────────────────────────────────────────────────────────────── consignes
    def consignes(self, poste: str = "", actives: bool = True):
        sql, args = "SELECT * FROM consignes WHERE 1=1", []
        if actives:
            sql += " AND statut='active'"
        if poste:
            sql += " AND (poste=? OR poste='*')"
            args.append(poste)
        lignes = self._tous(sql + " ORDER BY id DESC LIMIT 200", *args)
        for c in lignes:
            c["poste_nom"] = "Tous les postes" if c["poste"] == "*" else nom_poste(c["poste"])
        return lignes

    def envoyer_consigne(self, poste: str, message: str, operateur="PC"):
        if poste != "*" and poste not in POSTES:
            raise Refus(f"Poste inconnu : {poste}")
        with self.verrou, self._transaction():
            self._consigne(poste, "manuel", message.strip())
            self._evenement("CONSIGNE", "consigne", "Consigne envoyée", poste, operateur, "info", message)

    def acquitter_consigne(self, identifiant: int, operateur=""):
        with self.verrou:
            self.cx.execute("UPDATE consignes SET statut='acquittee', t_acquit=?, op_acquit=? WHERE id=?",
                            (self.horloge(), operateur, identifiant))

    # ───────────────────────────────────────────────────────────────── vues d'ensemble
    def pieces(self, type_piece="", statut="", recherche=""):
        sql, args = "SELECT * FROM pieces WHERE 1=1", []
        if type_piece:
            sql += " AND type=?"
            args.append(type_piece)
        if statut:
            sql += " AND statut=?"
            args.append(statut)
        if recherche:
            sql += " AND (code LIKE ? OR designation LIKE ? OR lot LIKE ? OR parent LIKE ?)"
            args += [f"%{recherche}%"] * 4
        lignes = self._tous(sql + " ORDER BY t_creation DESC, code", *args)
        t = self.horloge()
        for p in lignes:
            s = self.prochaine_etape(p)
            p["prochaine"] = f"{s[1]} ({nom_poste(s[2])})" if s and p["statut"] not in STATUTS_FINIS else ""
            p["poste_nom"] = nom_poste(p["poste"]) if p["poste"] else ""
            p["statut_libelle"] = LIBELLES_STATUT.get(p["statut"], p["statut"])
            p["lot_bloque"] = self.lot_bloque(p)
            ouvert = self._un("SELECT t_entree FROM sejours WHERE code=? AND t_sortie IS NULL", p["code"])
            p["temps_poste_s"] = t - ouvert["t_entree"] if ouvert else None
            p["defauts_ouverts"] = self._un("SELECT COUNT(*) n FROM defauts WHERE code=? AND statut='ouvert'",
                                            p["code"])["n"]
        return lignes

    def evenements(self, depuis: int = 0, limite: int = 500):
        return self._tous("SELECT * FROM evenements WHERE id>? ORDER BY id LIMIT ?", depuis, limite)

    def etat(self):
        """Résumé pour le tableau de bord du PC (et plus tard le jumeau numérique)."""
        with self.verrou:
            par_statut = {r["statut"]: r["n"] for r in
                          self._tous("SELECT statut, COUNT(*) n FROM pieces WHERE type!='lot' GROUP BY statut")}
            par_poste = {nom_poste(r["poste"]): r["n"] for r in self._tous(
                "SELECT poste, COUNT(*) n FROM pieces WHERE type!='lot' AND statut IN "
                "('en_cours','defaut') AND poste!='' GROUP BY poste")}
            return {
                "t": self.horloge(),
                "pieces": self._un("SELECT COUNT(*) n FROM pieces WHERE type!='lot'")["n"],
                "lots": self._un("SELECT COUNT(*) n FROM pieces WHERE type='lot'")["n"],
                "par_statut": par_statut, "par_poste": par_poste,
                "defauts_ouverts": self._un("SELECT COUNT(*) n FROM defauts WHERE statut='ouvert'")["n"],
                "lots_bloques": [r["code"] for r in self._tous("SELECT code FROM pieces WHERE bloque=1")],
                "cartes": {r["etat"]: r["n"] for r in self._tous("SELECT etat, COUNT(*) n FROM cartes GROUP BY etat")},
                "consignes_actives": self._un("SELECT COUNT(*) n FROM consignes WHERE statut='active'")["n"],
                "evenements": self._un("SELECT COUNT(*) n FROM evenements")["n"],
                "derniers": self._tous("SELECT * FROM evenements ORDER BY id DESC LIMIT 15"),
            }

    def vider(self):
        with self.verrou, self._transaction():
            for table in ("pieces", "evenements", "sejours", "defauts", "cartes", "demandes", "consignes"):
                self.cx.execute(f"DELETE FROM {table}")
            self.cx.execute("DELETE FROM sqlite_sequence")

    def donnees_demo(self) -> list[str]:
        """Petit jeu d'essai : 2 lots, 1 module complet, 3 cartes kanban."""
        lot_a = self.creer_lot("FOUR-A", "Profilés acier S355", 40)
        lot_c = self.creer_lot("FOUR-C", "Kits sanitaires pods", 10)
        codes = self.creer_module_complet("Lyon", lots={"ossature": lot_a, "pod": lot_c, "composant": lot_c})
        cartes = [self.creer_carte("VIS-M8", "Vis M8 × 40", 200, "kitting", delai_min=3),
                  self.creer_carte("JNT-SDB", "Joints d'étanchéité", 20, "pod_2", delai_min=3),
                  self.creer_carte("ISO-100", "Isolant 100 mm (paquets)", 12, "ligne_2d", delai_min=3)]
        return [lot_a, lot_c, *codes, *cartes]


class _Transaction:
    def __init__(self, base):
        self.base = base

    def __enter__(self):
        self.base.cx.execute("SAVEPOINT t")

    def __exit__(self, type_exception, *_):
        if type_exception:
            self.base.cx.execute("ROLLBACK TO t")
        self.base.cx.execute("RELEASE t")
        return False
