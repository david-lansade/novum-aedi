"""Serveur de l'application de scan : à lancer sur le PC, le téléphone s'y connecte par le wifi.

    py -3 avelis_scan/serveur.py                 # port 8000, base avelis_scan/donnees/atelier.db
    py -3 avelis_scan/serveur.py --port 8080
    py -3 avelis_scan/serveur.py --adresse 192.168.43.20   # si l'adresse détectée est mauvaise

Pages :
  /            page de scan (téléphone)            /s/<code>    même page, code déjà scanné
  /pc          gestion de la base (PC)             /etiquettes?codes=A,B   étiquettes QR à imprimer
API JSON (aussi pour le futur jumeau numérique) :
  GET  /api/config, /api/objet/<code>?poste=, /api/pieces, /api/cartes, /api/consignes?poste=,
       /api/evenements?depuis=<id>, /api/etat
  POST /api/scan, /api/pieces, /api/modules, /api/lots, /api/cartes, /api/consignes,
       /api/consignes/<id>/acquitter, /api/lots/<code>/bloquer, /api/lots/<code>/debloquer,
       /api/demo, /api/vider
Exports CSV (Excel, « ; », UTF-8 avec BOM) : /export/<table>.csv

Uniquement la bibliothèque standard ; le module qrcode est facultatif (étiquettes).
"""

import argparse
import csv
import html
import io
import json
import pathlib
import socket
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as C
from base import Base, Refus, normaliser_code, nom_poste, nombre_cartes_kanban

try:
    import qrcode
    import qrcode.image.svg
except ImportError:  # étiquettes sans QR code : le code est écrit en clair
    qrcode = None

DOSSIER = pathlib.Path(__file__).resolve().parent
DOSSIER_WEB = DOSSIER / "web"
BASE_PAR_DEFAUT = DOSSIER / "donnees" / "atelier.db"
TABLES_EXPORT = ("pieces", "evenements", "sejours", "defauts", "cartes", "demandes", "consignes")


def adresse_locale() -> str:
    """Adresse IP du PC sur le réseau (partage de connexion du téléphone)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # aucun paquet n'est envoyé : sert à choisir l'interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def qr_svg(texte: str) -> str | None:
    if qrcode is None:
        return None
    image = qrcode.make(texte, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    svg = image.to_string(encoding="unicode")
    return svg[svg.find("<svg"):]


def heure(t) -> str:
    return time.strftime("%d/%m %H:%M:%S", time.localtime(t)) if t else ""


class Application:
    """État partagé par toutes les requêtes."""

    def __init__(self, chemin_base, adresse, port):
        pathlib.Path(chemin_base).parent.mkdir(parents=True, exist_ok=True) if chemin_base != ":memory:" else None
        self.base = Base(str(chemin_base))
        self.adresse, self.port = adresse, port

    @property
    def url(self) -> str:
        return f"http://{self.adresse}:{self.port}"

    def url_scan(self, code: str) -> str:
        return f"{self.url}/s/{urllib.parse.quote(code)}"

    def config(self) -> dict:
        return {"postes": C.POSTES, "types": {k: {"libelle": v["libelle"], "prefixe": v["prefixe"],
                                                  "gamme": v["gamme"]} for k, v in C.TYPES.items()},
                "categories_defaut": C.CATEGORIES_DEFAUT, "causes_defaut": list(C.CAUSES_DEFAUT),
                "gravites": C.GRAVITES, "fournisseurs": C.FOURNISSEURS, "chantiers": C.CHANTIERS,
                "delai_kanban_min": C.DELAI_KANBAN_MIN, "poste_magasin": C.POSTE_MAGASIN,
                "url": self.url, "qr_disponible": qrcode is not None,
                "moyens": C.MOYENS_IDENTIFICATION}

    def etiquettes(self, codes: list[str]) -> str:
        """Page HTML imprimable : une étiquette par code (QR = adresse de scan)."""
        cartes = []
        for code in codes:
            o = self.base.objet(code)
            if o["genre"] == "piece":
                p = o["piece"]
                lignes = [p["designation"] or o["type_libelle"]]
                if p["lot"]:
                    lignes.append(f"Lot {p['lot']}")
                if p["parent"]:
                    lignes.append(f"Module {p['parent']}")
                if p["numero_serie"]:
                    lignes.append(f"N° série {p['numero_serie']}")
            elif o["genre"] == "carte":
                c = o["carte"]
                lignes = ["CARTE KANBAN", f"{c['quantite']:g} × {c['designation']}", f"Réf. {c['reference']}",
                          f"Poste : {o['poste_nom']}", f"Source : {c['source']}"]
            else:
                continue
            svg = qr_svg(self.url_scan(code)) or "<div class='sansqr'>QR indisponible<br>(pip install qrcode)</div>"
            classe = "kanban" if o["genre"] == "carte" else ""
            cartes.append(f"<div class='etiq {classe}'>{svg}<div><b>{html.escape(code)}</b>"
                          + "".join(f"<br>{html.escape(str(l))}" for l in lignes if l) + "</div></div>")
        return ("<!doctype html><meta charset='utf-8'><title>Étiquettes</title><style>"
                "body{font-family:Segoe UI,Arial,sans-serif;margin:10mm}"
                ".grille{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}"
                ".etiq{border:1px dashed #999;padding:3mm;display:flex;gap:3mm;align-items:center;"
                "font-size:10pt;break-inside:avoid}.etiq svg{width:32mm;height:32mm;flex:none}"
                ".kanban{border:2px solid #e07b00;background:#fff7ec}"
                ".sansqr{width:32mm;height:32mm;border:1px solid #ccc;font-size:8pt;display:flex;"
                "align-items:center;justify-content:center;text-align:center}"
                ".info{color:#555;font-size:9pt;margin-bottom:4mm}@media print{.info{display:none}}</style>"
                f"<div class='info'>Adresse encodée dans les QR : {html.escape(self.url)}/s/… · "
                "Si l'adresse du PC change, réimprimez les étiquettes. · Ctrl+P pour imprimer.</div>"
                f"<div class='grille'>{''.join(cartes)}</div>")

    def export_csv(self, table: str) -> bytes:
        lignes = self.base._tous(f"SELECT * FROM {table}")
        sortie = io.StringIO()
        if lignes:
            colonnes = list(lignes[0])
            colonnes_t = [c for c in colonnes if c.startswith("t") and c[1:2] in ("", "_")]
            ecrivain = csv.writer(sortie, delimiter=";")
            ecrivain.writerow(colonnes + [f"{c}_lisible" for c in colonnes_t])
            for l in lignes:
                ecrivain.writerow([str(l[c]).replace(".", ",") if isinstance(l[c], float) else
                                   ("" if l[c] is None else l[c]) for c in colonnes]
                                  + [heure(l[c]) for c in colonnes_t])
        return ("﻿" + sortie.getvalue()).encode("utf-8")


class Gestionnaire(BaseHTTPRequestHandler):
    app: Application = None  # renseigné au démarrage
    server_version = "AvelisScan/1.0"

    # ───────────────────────────────────────────────────────────── réponses
    def _envoyer(self, code_http, contenu: bytes, type_contenu, entetes=None):
        self.send_response(code_http)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(contenu)

    def _json(self, donnees, code_http=200):
        self._envoyer(code_http, json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8"),
                      "application/json; charset=utf-8")

    def _fichier(self, nom):
        self._envoyer(200, (DOSSIER_WEB / nom).read_bytes(), "text/html; charset=utf-8")

    def _corps(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}

    def log_message(self, *args):  # pas de ligne par requête dans la console
        pass

    # ───────────────────────────────────────────────────────────── routage
    def do_GET(self):
        self._traiter("GET")

    def do_POST(self):
        self._traiter("POST")

    def _traiter(self, methode):
        url = urllib.parse.urlsplit(self.path)
        chemin = urllib.parse.unquote(url.path).rstrip("/") or "/"
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            self.app.base.surveiller_kanban()
            if methode == "GET":
                self._get(chemin, q)
            else:
                self._post(chemin, self._corps())
        except Refus as refus:
            self._json({"erreur": str(refus)}, 400)
        except (ValueError, KeyError, json.JSONDecodeError) as erreur:
            self._json({"erreur": f"Requête invalide : {erreur}"}, 400)
        except Exception as erreur:  # noqa: BLE001 — le serveur ne doit jamais s'arrêter
            traceback.print_exc()
            self._json({"erreur": f"Erreur interne : {erreur}"}, 500)

    def _get(self, chemin, q):
        a, b = self.app, self.app.base
        if chemin == "/" or chemin.startswith("/s/"):
            return self._fichier("scan.html")
        if chemin in ("/pc", "/admin"):
            return self._fichier("pc.html")
        if chemin == "/etiquettes":
            codes = [normaliser_code(c) for c in q.get("codes", "").split(",") if c.strip()]
            return self._envoyer(200, a.etiquettes(codes).encode("utf-8"), "text/html; charset=utf-8")
        if chemin.startswith("/qr/") and chemin.endswith(".svg"):
            svg = qr_svg(a.url_scan(normaliser_code(chemin[4:-4])))
            if svg is None:
                return self._json({"erreur": "module qrcode absent"}, 404)
            return self._envoyer(200, svg.encode("utf-8"), "image/svg+xml")
        if chemin == "/qr_accueil.svg":
            svg = qr_svg(a.url + "/")
            return self._envoyer(200, (svg or "").encode("utf-8"), "image/svg+xml")
        if chemin.startswith("/export/") and chemin.endswith(".csv"):
            table = chemin[8:-4]
            if table not in TABLES_EXPORT:
                return self._json({"erreur": "table inconnue"}, 404)
            return self._envoyer(200, a.export_csv(table), "text/csv; charset=utf-8",
                                 {"Content-Disposition": f'attachment; filename="{table}.csv"'})
        if chemin == "/api/config":
            return self._json(a.config())
        if chemin.startswith("/api/objet/"):
            return self._json(b.objet(chemin[11:], q.get("poste", "")))
        if chemin == "/api/pieces":
            return self._json(b.pieces(q.get("type", ""), q.get("statut", ""), q.get("q", "")))
        if chemin == "/api/cartes":
            return self._json(b.cartes())
        if chemin == "/api/consignes":
            return self._json(b.consignes(q.get("poste", ""), q.get("toutes") != "1"))
        if chemin == "/api/evenements":
            return self._json(b.evenements(int(q.get("depuis", 0)), int(q.get("limite", 500))))
        if chemin == "/api/etat":
            return self._json(b.etat())
        if chemin == "/api/defauts":
            return self._json(b.defauts(ouverts=q.get("ouverts") == "1"))
        if chemin == "/api/kanban/calcul":
            return self._json({"cartes": nombre_cartes_kanban(float(q["conso_h"]), float(q["delai_h"]),
                                                              float(q.get("marge", 0.2)), float(q["qte"]))})
        self._json({"erreur": "page introuvable"}, 404)

    def _post(self, chemin, d):
        b = self.app.base
        if chemin == "/api/scan":
            r = b.scanner(d["code"], d.get("poste", ""), d.get("operateur", ""), d.get("action", "etape"),
                          d.get("params") or {}, d.get("t_client"), d.get("moyen", ""))
            print(f"[{time.strftime('%H:%M:%S')}] {nom_poste(d.get('poste', '')):34} "
                  f"{d.get('operateur', ''):6} {normaliser_code(d['code']):18} {d.get('action', ''):9} "
                  f"→ {r['niveau']:9} {r['message'][:90]}")
            return self._json(r)
        if chemin == "/api/pieces":
            return self._json({"code": b.creer_piece(**{k: v for k, v in d.items() if v not in (None, "")})})
        if chemin == "/api/modules":
            codes = []
            for _ in range(max(1, min(50, int(d.get("nombre", 1))))):
                codes += b.creer_module_complet(d.get("destination", ""), bool(d.get("avec_composants", True)),
                                                d.get("lots") or {})
            return self._json({"codes": codes})
        if chemin == "/api/lots":
            return self._json({"code": b.creer_lot(d["fournisseur"], d.get("reference", ""),
                                                   float(d["quantite"]) if d.get("quantite") else None,
                                                   d.get("code", ""), d.get("designation", ""))})
        if chemin == "/api/cartes":
            return self._json({"code": b.creer_carte(d["reference"], d["designation"], float(d["quantite"]),
                                                     d["poste_conso"], d.get("source") or "Magasin",
                                                     float(d["delai_min"]) if d.get("delai_min") else None,
                                                     d.get("code", ""))})
        if chemin == "/api/consignes":
            b.envoyer_consigne(d["poste"], d["message"], d.get("operateur", "PC"))
            return self._json({"ok": True})
        if chemin == "/api/nfc/ecriture":
            message = b.noter_ecriture_nfc(d["code"], d.get("poste", ""), d.get("operateur", ""))
            return self._json({"ok": True, "message": message})
        if chemin.startswith("/api/consignes/") and chemin.endswith("/acquitter"):
            b.acquitter_consigne(int(chemin.split("/")[3]), d.get("operateur", ""))
            return self._json({"ok": True})
        if chemin.startswith("/api/lots/") and chemin.endswith("/bloquer"):
            return self._json({"isolees": b.bloquer_lot(chemin.split("/")[3], d.get("motif") or "Blocage manuel")})
        if chemin.startswith("/api/lots/") and chemin.endswith("/debloquer"):
            b.debloquer_lot(chemin.split("/")[3], d.get("motif", ""))
            return self._json({"ok": True})
        if chemin == "/api/demo":
            return self._json({"codes": b.donnees_demo()})
        if chemin == "/api/vider":
            if d.get("confirmation") != "VIDER":
                raise Refus("Tapez VIDER pour confirmer.")
            b.vider()
            return self._json({"ok": True})
        self._json({"erreur": "action introuvable"}, 404)


def surveillance(app: Application, arret: threading.Event):
    while not arret.wait(C.INTERVALLE_SURVEILLANCE_S):
        try:
            n = app.base.surveiller_kanban()
            if n:
                print(f"[{time.strftime('%H:%M:%S')}] {n} demande(s) kanban en retard : consigne envoyée")
        except Exception:  # noqa: BLE001
            traceback.print_exc()


def demarrer(chemin_base=BASE_PAR_DEFAUT, adresse=None, port=C.PORT, ecoute="0.0.0.0"):
    """Crée le serveur (sans le lancer) ; renvoie (serveur, application)."""
    app = Application(chemin_base, adresse or adresse_locale(), port)
    Gestionnaire.app = app
    serveur = ThreadingHTTPServer((ecoute, port), Gestionnaire)
    serveur.daemon_threads = True
    if port == 0:
        app.port = serveur.server_address[1]
    return serveur, app


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(description="Serveur de scan de l'atelier Avelis")
    p.add_argument("--port", type=int, default=C.PORT)
    p.add_argument("--adresse", help="adresse IP du PC à mettre dans les QR codes (détectée sinon)")
    p.add_argument("--base", default=str(BASE_PAR_DEFAUT), help="fichier de la base SQLite")
    o = p.parse_args()
    serveur, app = demarrer(o.base, o.adresse, o.port)
    arret = threading.Event()
    threading.Thread(target=surveillance, args=(app, arret), daemon=True).start()
    print("═" * 72)
    print("  AVELIS · Scan de l'atelier (traçabilité + kanban)")
    print(f"  Base de données : {o.base}")
    print(f"  Sur le PC        : http://localhost:{app.port}/pc")
    print(f"  Sur le téléphone : {app.url}/")
    print("  (téléphone et PC sur le même réseau ; autoriser Python dans le pare-feu)")
    print("═" * 72)
    if qrcode is not None:
        print("  Scannez ce QR code avec le téléphone pour ouvrir la page de scan :")
        qr = qrcode.QRCode(border=1)
        qr.add_data(app.url + "/")
        try:
            qr.print_ascii(invert=True)
        except Exception:  # noqa: BLE001 — console sans caractères blocs
            pass
    else:
        print("  (pip install qrcode pour les étiquettes QR)")
    print("  Ctrl+C pour arrêter.\n")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        arret.set()
        serveur.server_close()


if __name__ == "__main__":
    main()
