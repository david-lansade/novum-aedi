"""Scène 3D du site : données d'un scénario simulé pour la vue 3D (dossier avelis_3d/).

scene_3d(usine) traduit une Usine exécutée en un dictionnaire sérialisable en JSON : site et zones
en mètres, gabarits des objets, et la timeline de chaque objet (segments [t0, t1, points], temps en
minutes d'ouverture), avec ses événements de traçabilité et ses liens ; puis les alertes, les
instants du tableau de pilotage et les résultats de la simulation. positions_scene(scene, t) et
pilotage_scene(scene, t) refont les calculs de la vue 3D : ils servent de référence et doivent
redonner Usine.positions(t) et le tableau de pilotage de la vue 2.

Ce module n'importe aucun module graphique.

Exécution directe (« py -3 avelis_flux/scene_3d.py ») : tests intégrés. Avec --reference : écrit le
jeu de référence des tests JavaScript (avelis_3d/tests/reference.json). Avec --scene : écrit la
scène d'un scénario, pour développer la vue 3D sans l'application (avelis_3d/scene.json).
"""

import argparse
import bisect
import datetime
import http.server
import json
import math
import pathlib
import re
import socketserver
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jumeau as jm
from modele import (
    EXTENSION, HYPOTHESES, IMPLANTATION_ACTUELLE, IMPLANTATION_OPTIMISEE, IMPLANTATION_PROPOSEE,
    IMPLANTATIONS, ROUTE_PUBLIQUE, SCHEMAS, SITE_ACTUEL, TORCY, H, executer_tests,
    formater_nombre,
)
from simulation import (
    PAPIER, POINTS_MODULE, POINTS_POD, RFID, TECHNOLOGIES, TYPES_OBJETS, Usine,
    horloge, horloge_courte, minutes_jour, point_sur_chemin,
)

DOSSIER_3D = pathlib.Path(__file__).resolve().parent.parent / "avelis_3d"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. Scène d'un scénario simulé
# ═════════════════════════════════════════════════════════════════════════════════════════════

VERSION_SCENE = 4  # à augmenter si le format change (lu par avelis_3d/src/donnees.js)
DECIMALES_POSITION = 2  # points arrondis au centimètre : la scène pèse deux fois moins
ZONES_A_CIEL_OUVERT = ("Parking PL", "Expédition")  # sans bâtiment, comme toute la catégorie :
CATEGORIES_A_CIEL_OUVERT = ("Réserve foncière",)  # « Réserve 2030+ », « Réserve lignes 2030+ »
GABARITS = {"camion": "dim_camion", "pod": "dim_pod", "kit 2D": "dim_kit_2d", "lot": "dim_lot"}
# Ce qui sort de l'assemblage : un module 3D (unique) ou un kit module (satellites)
GABARIT_MODULE = {"unique": "dim_module", "satellites": "dim_kit_module"}
# Liens de traçabilité d'un objet : nom dans la scène → clé dans Usine.objets
LIENS = {"module": "module", "pod": "pod", "kit 2D": "k2d", "lot": "lot", "camion": "camion",
         "modules": "modules"}


def _point(p) -> list[float]:
    """Point [x, y] arrondi au centimètre."""
    return [round(p[0], DECIMALES_POSITION), round(p[1], DECIMALES_POSITION)]


def _points(chemin) -> list[list[float]]:
    """Points d'un chemin ou d'un contour, arrondis au centimètre."""
    return [_point(p) for p in chemin]


def a_ciel_ouvert(nom: str, categorie: str) -> bool:
    """Vrai pour une zone sans bâtiment (parking, aire d'expédition, réserve foncière)."""
    return nom in ZONES_A_CIEL_OUVERT or categorie in CATEGORIES_A_CIEL_OUVERT


def _zones(plan: dict) -> list[dict]:
    """Zones de l'implantation ; une zone partagée est dessinée avec sa zone hôte, sous un
    libellé commun (comme la vue 2)."""
    partagees = plan["zones_partagees"]
    zones = []
    for nom, (x, y, largeur, profondeur, couleur, categorie) in plan["zones"].items():
        if nom in partagees:
            continue
        invitees = [zone for zone, hote in partagees.items() if hote == nom]
        zones.append({"nom": nom, "libelle": " / ".join([nom, *invitees]), "x": x, "y": y,
                      "largeur": largeur, "profondeur": profondeur, "couleur": couleur,
                      "categorie": categorie,
                      "hauteur": 0 if a_ciel_ouvert(nom, categorie)
                      else H("hauteur_batiments")})
    return zones


def _quais(usine: Usine) -> dict:
    """Premier quai de chaque fonction, nombre de quais et pas [dx, dy] d'un quai au suivant
    (comme Usine._venir_a_quai)."""
    plan, dimension = usine.plan, usine.dimension
    partages = plan["zones_partagees"].get("Expédition") == "Réception"
    nombre_expedition = dimension["quais_reception" if partages else "quais_expedition"]
    return {"reception": {"position": _point(plan["quai_reception"]),
                          "nombre": dimension["quais_reception"],
                          "pas": _point(plan["pas_quai_reception"])},
            "expedition": {"position": _point(plan["quai_expedition"]),
                           "nombre": nombre_expedition,
                           "pas": _point(plan["pas_quai_expedition"])},
            "partages": partages}


def _parking_vl(plan: dict) -> dict | None:
    """Parking des véhicules légers {x, y, largeur, profondeur, voie}, ou None."""
    parking = plan.get("parking_vl")
    if not parking:
        return None
    x, y, largeur, profondeur = parking["zone"]
    return {"x": x, "y": y, "largeur": largeur, "profondeur": profondeur,
            "voie": _points(parking["voie"])}


def _site(usine: Usine) -> dict:
    """Contours, voiries (bretelles comprises), portail et son accès, aire de retournement,
    parking VL, quais et zones, en mètres."""
    plan = usine.plan
    centre, rayon = plan["retournement"], H("rayon_retournement")
    return {"contours": [{"nom": "Site actuel", "points": _points(SITE_ACTUEL), "utilise": True},
                         {"nom": "Extension", "points": _points(EXTENSION),
                          "utilise": plan["extension_utilisee"]}],
            "route_publique": _points(ROUTE_PUBLIQUE), "portail": _point(plan["portail"]),
            "acces": _points(plan["acces"]), "voirie": _points(plan["voirie"]),
            "bretelles": [_points(b) for b in plan["bretelles"]],
            "largeur_voirie": H("largeur_voirie"), "parking_vl": _parking_vl(plan),
            "retournement": {"centre": _point(centre), "rayon": rayon},
            "quais": _quais(usine), "zones": _zones(plan)}


def _gabarits(schema: str) -> dict[str, list[float]]:
    """Gabarit [largeur, longueur, hauteur] (m) de chaque type d'objet."""
    cles = {**GABARITS, "module": GABARIT_MODULE[schema]}
    return {type_objet: list(H(cle)) for type_objet, cle in cles.items()}


def _libelle(objet: dict) -> str:
    """Description courte de l'objet, affichée au survol dans la vue 3D."""
    if objet["type"] == "camion":
        if objet["role"] == "Expédition":
            return f"Expédition vers {objet['destination']}"
        return f"Fournisseur {objet['fournisseur']} · {objet['lot']}"
    if objet["type"] == "lot":
        etat = "non conforme" if objet["non_conforme"] else "conforme"
        return f"{objet['fournisseur']} · {etat}"
    if objet["type"] == "module":  # sa destination n'est tirée qu'au chargement du camion
        return "avec pod" if objet["besoin_pod"] else "sans pod"
    return f"pour {objet['module']}"  # pod et kit 2D


def _segment(segment: dict) -> list:
    """Segment [t0, t1, points] ; t1 vaut None pour une présence qui dure jusqu'à la fin."""
    t1 = None if math.isinf(segment["t1"]) else segment["t1"]
    return [segment["t0"], t1, _points(segment["chemin"])]


def _liens(objet: dict) -> dict:
    """Objets liés, quand ils sont connus : composants et lot d'un module, module et lot d'un
    pod ou d'un kit 2D, camion d'un lot ou d'un module, modules d'un camion d'expédition."""
    return {nom: objet[cle] for nom, cle in LIENS.items() if objet.get(cle)}


def _evenement(enregistrement: dict) -> list:
    """Événement de traçabilité [t, evenement, zone, t_affichage, message] ; t_affichage vaut
    None pour un événement non lu, que l'outil de pilotage n'affiche jamais."""
    return [enregistrement[cle] for cle in ("t", "evenement", "zone", "t_affichage", "message")]


def _objets(usine: Usine) -> list[dict]:
    """Objets animés, dans l'ordre de leur première apparition dans les timelines, avec leurs
    liens et leurs événements de traçabilité (hors alertes), dans l'ordre du journal."""
    par_objet = usine.tracabilite.par_objet
    return [{"id": id_objet, "type": type_objet, "libelle": _libelle(usine.objets[id_objet]),
             "liens": _liens(usine.objets[id_objet]),
             "evenements": [_evenement(e) for e in par_objet.get(id_objet, ())
                            if not e["alerte"]],
             "segments": [_segment(segment) for segment in segments]}
            for id_objet, (type_objet, segments) in usine.timelines().items()]


def _tracabilite(usine: Usine) -> dict:
    """Points de contrôle obligatoires et alertes [t, t_affichage, nature, id, type, zone,
    message], dans l'ordre de leur affichage (comme le tableau de pilotage de la vue 2)."""
    alertes = sorted((e for e in usine.tracabilite.journal if e["alerte"]),
                     key=lambda e: e["t_affichage"])
    cles = ("t", "t_affichage", "evenement", "id", "type", "zone", "message")
    return {"points_module": list(POINTS_MODULE), "points_pod": list(POINTS_POD),
            "alertes": [[e[cle] for cle in cles] for e in alertes]}


def _instants(valeurs) -> list[float]:
    """Instants connus (hors None), triés."""
    return sorted(t for t in valeurs if t is not None)


def _pilotage(usine: Usine) -> dict:
    """Instants qui donnent le tableau de pilotage à tout instant : OF, entrées en stock PF,
    expéditions, début et fin des pods, présence des camions sur site, stocks échantillonnés."""
    modules, pods = usine.objets_de_type("module"), usine.objets_de_type("pod")
    par_objet = usine.tracabilite.par_objet
    camions = [[c["t_arrivee"], c["t_sortie"]] for c in usine.objets_de_type("camion")
               if c["t_arrivee"] is not None]
    return {"objectif_jour": usine.calcul["modules_jour"],
            "of": _instants(m["t_of"] for m in modules),
            "entrees_pf": _instants(m["t_stock_pf"] for m in modules),
            "expeditions": _instants(m["t_expedie"] for m in modules),
            "debuts_pods": _instants(par_objet[p["id"]][0]["t"] for p in pods),
            "fins_pods": _instants(p["t_integre"] for p in pods),
            "camions": camions,
            "echantillons": {"pas": H("pas_echantillonnage"),
                             "stock_matieres": [e["stock_matieres"] for e in usine.echantillons],
                             "stock_pf": [e["stock_pf"] for e in usine.echantillons]}}


def _resultats(usine: Usine) -> dict:
    """Indicateurs de fin de simulation (Usine.resultats), le Pareto en listes pour JSON."""
    resultats = usine.resultats()
    return {**resultats, "pareto_causes": [list(cause) for cause in resultats["pareto_causes"]]}


def changements_equipe() -> list[float]:
    """Heures de l'horloge des changements d'équipe : ouverture, puis fin de chaque équipe
    (06:00, 14:00, 22:00) ; la vue 3D y fait marcher les opérateurs à pied."""
    return [H("heure_ouverture") + k * H("heures_par_equipe")
            for k in range(H("equipes_par_jour") + 1)]


def scene_3d(usine: Usine) -> dict:
    """Scène 3D de l'usine (simulée au besoin) : scénario, temps, site, gabarits, objets,
    traçabilité, pilotage et résultats."""
    usine.executer()
    return {"version": VERSION_SCENE,
            "scenario": {"cadence": usine.cadence, "implantation": usine.implantation,
                         "schema": usine.schema, "techno": usine.techno, "jours": usine.jours,
                         "graine": usine.graine},
            "temps": {"duree": usine.duree, "minutes_jour": minutes_jour(),
                      "heure_ouverture": H("heure_ouverture"),
                      "changements_equipe": changements_equipe()},
            "site": _site(usine), "gabarits": _gabarits(usine.schema), "objets": _objets(usine),
            "tracabilite": _tracabilite(usine), "pilotage": _pilotage(usine),
            "resultats": _resultats(usine)}


def scene_json(scene: dict) -> str:
    """Scène en JSON compact, accents conservés ; refuse inf et NaN, que JSON ne connaît pas."""
    return json.dumps(scene, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. Positions à un instant donné : le calcul que refait la vue 3D (avelis_3d/src/donnees.js)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def segment_actif(segments: list, t: float) -> list | None:
    """Dernier segment commencé à l'instant t, s'il n'est pas fini ; None si l'objet est
    masqué (comme Usine.segment)."""
    i = bisect.bisect_right([segment[0] for segment in segments], t) - 1
    if i < 0:
        return None
    t1 = segments[i][1]
    return segments[i] if t1 is None or t < t1 else None


def point_du_segment(segment: list, t: float) -> tuple[float, float]:
    """Position sur le segment : point fixe, ou interpolation le long du chemin."""
    t0, t1, points = segment
    if len(points) == 1:
        return tuple(points[0])
    return tuple(point_sur_chemin(points, (t - t0) / (t1 - t0)))


def positions_scene(scene: dict, t: float) -> dict[str, tuple[float, float, str]]:
    """{id: (x, y, type)} des objets visibles à l'instant t, calculés depuis la scène seule."""
    visibles = {}
    for objet in scene["objets"]:
        segment = segment_actif(objet["segments"], t)
        if segment is not None:
            visibles[objet["id"]] = (*point_du_segment(segment, t), objet["type"])
    return visibles


NB_ALERTES_AFFICHEES = 9  # SPEC §4.3 : les 9 dernières alertes affichées (comme la vue 2)


def _nombre(instants: list[float], t: float) -> int:
    """Nombre d'instants triés ≤ t."""
    return bisect.bisect_right(instants, t)


def _du_jour(instants: list[float], t: float, debut_jour: float) -> int:
    """Nombre d'instants triés du jour en cours (debut_jour ≤ instant ≤ t)."""
    return _nombre(instants, t) - bisect.bisect_left(instants, debut_jour)


def _echantillon(echantillons: dict, cle: str, t: float) -> int | None:
    """Dernière valeur échantillonnée (tous les `pas`, depuis t = 0) à l'instant t."""
    valeurs = echantillons[cle]
    if not valeurs:
        return None
    return valeurs[max(0, min(math.floor(t / echantillons["pas"]), len(valeurs) - 1))]


def pilotage_scene(scene: dict, t: float) -> dict:
    """Tableau de pilotage à l'instant t, depuis la scène seule : mêmes valeurs, en nombres, que
    IndicateursTemps.valeurs de la vue 2 (app.py), plus le nombre d'alertes déjà affichées."""
    p, minutes = scene["pilotage"], scene["temps"]["minutes_jour"]
    debut_jour = math.floor(t / minutes) * minutes
    return {
        "termines_jour": _du_jour(p["entrees_pf"], t, debut_jour),
        "objectif_heure": p["objectif_jour"] * (t - debut_jour) / minutes,
        "expedies_jour": _du_jour(p["expeditions"], t, debut_jour),
        "expedies": _nombre(p["expeditions"], t),
        "en_cours": _nombre(p["of"], t) - _nombre(p["entrees_pf"], t),
        "stock_matieres": _echantillon(p["echantillons"], "stock_matieres", t),
        "stock_pf": _echantillon(p["echantillons"], "stock_pf", t),
        "pods_en_cours": _nombre(p["debuts_pods"], t) - _nombre(p["fins_pods"], t),
        "camions_sur_site": sum(1 for arrivee, sortie in p["camions"]
                                if arrivee <= t and (sortie is None or t < sortie)),
        "alertes": _nombre([a[1] for a in scene["tracabilite"]["alertes"]], t),
    }


def alertes_affichees_scene(scene: dict, t: float,
                            nombre: int = NB_ALERTES_AFFICHEES) -> list[list]:
    """Les `nombre` dernières alertes déjà affichées (t_affichage ≤ t), la plus récente
    d'abord (comme IndicateursTemps.alertes_affichees)."""
    alertes = scene["tracabilite"]["alertes"]
    fin = _nombre([a[1] for a in alertes], t)
    return list(reversed(alertes[max(0, fin - nombre):fin]))


def evenements_affiches(objet: dict, t: float) -> list[list]:
    """Événements de l'objet que l'outil de pilotage affiche déjà à l'instant t (lus, et
    t_affichage ≤ t), dans l'ordre du journal."""
    return [e for e in objet["evenements"] if e[3] is not None and e[3] <= t]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. Fichiers pour la vue 3D : jeu de référence des tests JavaScript, scène de développement
# ═════════════════════════════════════════════════════════════════════════════════════════════

FICHIER_REFERENCE = DOSSIER_3D / "tests" / "reference.json"
SCENE_DEVELOPPEMENT = DOSSIER_3D / "scene.json"
SCENARIO_REFERENCE = (1500, IMPLANTATION_PROPOSEE, "unique", RFID, 2, 42)  # jours = 2
PAS_REFERENCE_MIN = 11.3  # instants réguliers du jeu de référence : k × 11,3 + 0,37 min
OBJETS_AUX_LIMITES = 15  # objets dont chaque début et fin de segment devient un instant testé
INSTANTS_HORLOGE = (0, 0.5, 59.99, 60, 449.5, 450, 899.999, 900, 1349.5, 1799.99)
# Implantation de --scene : choix de la ligne de commande → nom dans IMPLANTATIONS
CHOIX_IMPLANTATIONS = {"proposee": IMPLANTATION_PROPOSEE, "actuelle": IMPLANTATION_ACTUELLE,
                       "optimisee": IMPLANTATION_OPTIMISEE}


def _instants_reference(scene: dict) -> list[float]:
    """Instants réguliers, plus les débuts et fins exacts des segments de quelques objets (là
    où un objet apparaît, disparaît ou change de segment)."""
    duree = scene["temps"]["duree"]
    instants = {k * PAS_REFERENCE_MIN + 0.37 for k in range(int(duree / PAS_REFERENCE_MIN))}
    for objet in scene["objets"][:OBJETS_AUX_LIMITES]:
        for t0, t1, _ in objet["segments"]:
            instants.update(t for t in (t0, t1) if t is not None and t < duree)
    return sorted(instants)


def _instants_pilotage(scene: dict) -> list[float]:
    """Instants réguliers, changements de jour, et instants exacts d'affichage des premières
    alertes et des premiers événements (là où un compte change)."""
    duree = scene["temps"]["duree"]
    instants = {k * PAS_REFERENCE_MIN + 0.37 for k in range(int(duree / PAS_REFERENCE_MIN))}
    instants.update(INSTANTS_HORLOGE)
    instants.update(a[1] for a in scene["tracabilite"]["alertes"][:OBJETS_AUX_LIMITES])
    for objet in scene["objets"][:OBJETS_AUX_LIMITES]:
        instants.update(e[3] for e in objet["evenements"] if e[3] is not None)
    return sorted(instants)


def _pilotage_reference(scene: dict) -> list[dict]:
    """Tableau de pilotage, alertes affichées (indices dans tracabilite.alertes) et nombre
    d'événements affichés de quelques objets, à chaque instant de _instants_pilotage."""
    indices = {id(alerte): i for i, alerte in enumerate(scene["tracabilite"]["alertes"])}
    objets = scene["objets"][:OBJETS_AUX_LIMITES]
    return [{"t": t, "valeurs": pilotage_scene(scene, t),
             "alertes": [indices[id(a)] for a in alertes_affichees_scene(scene, t)],
             "evenements": {o["id"]: len(evenements_affiches(o, t)) for o in objets}}
            for t in _instants_pilotage(scene)]


def reference_js() -> dict:
    """Scène d'un scénario de 2 jours, positions, horloges et tableau de pilotage attendus
    (calculés par positions_scene et pilotage_scene) : ce que les tests de avelis_3d/ doivent
    retrouver ; plus le site de chaque implantation (cadrage, repères et décor)."""
    cadence, implantation, schema, techno, jours, graine = SCENARIO_REFERENCE
    scene = scene_3d(Usine(cadence, implantation, schema, techno, jours, graine))
    positions = [{"t": t, "visibles": {id_objet: [x, y] for id_objet, (x, y, _)
                                       in positions_scene(scene, t).items()}}
                 for t in _instants_reference(scene)]
    sites = {nom: _site(Usine(cadence, nom, schema, techno, jours, graine))
             for nom in IMPLANTATIONS}
    return {"scene": scene, "positions": positions, "sites": sites,
            "horloges": [[t, horloge(t), horloge_courte(t)] for t in INSTANTS_HORLOGE],
            "pilotage": _pilotage_reference(scene)}


def ecrire_json(donnees: dict, chemin: pathlib.Path) -> int:
    """Écrit le JSON compact (UTF-8) et renvoie sa taille en octets."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    texte = scene_json(donnees)
    chemin.write_text(texte, encoding="utf-8")
    return len(texte.encode("utf-8"))


def _arguments() -> argparse.Namespace:
    """Options de la ligne de commande."""
    parseur = argparse.ArgumentParser(description="Tests intégrés, ou écriture d'une scène 3D.")
    parseur.add_argument("--reference", action="store_true",
                         help="écrit le jeu de référence des tests JavaScript "
                              f"({FICHIER_REFERENCE})")
    parseur.add_argument("--scene", metavar="CHEMIN", nargs="?", const=str(SCENE_DEVELOPPEMENT),
                         help=f"écrit la scène d'un scénario (par défaut {SCENE_DEVELOPPEMENT})")
    parseur.add_argument("--implantation", choices=CHOIX_IMPLANTATIONS, default="proposee",
                         help="implantation simulée (par défaut : proposée)")
    parseur.add_argument("--actuelle", action="store_true",
                         help="raccourci de --implantation actuelle")
    parseur.add_argument("--schema", choices=SCHEMAS, default="unique")
    parseur.add_argument("--techno", choices=range(len(TECHNOLOGIES)), type=int, default=0,
                         help="0 : RFID, 1 : QR code, 2 : papier")
    parseur.add_argument("--cadence", type=int, default=1500)
    parseur.add_argument("--jours", type=int, default=10)
    parseur.add_argument("--graine", type=int, default=42)
    return parseur.parse_args()


def _ecrire_scene_demandee(options: argparse.Namespace) -> None:
    """Simule le scénario des options et écrit sa scène."""
    choix = "actuelle" if options.actuelle else options.implantation
    implantation = CHOIX_IMPLANTATIONS[choix]
    usine = Usine(options.cadence, implantation, options.schema,
                  list(TECHNOLOGIES)[options.techno], options.jours, options.graine)
    chemin = pathlib.Path(options.scene)
    octets = ecrire_json(scene_3d(usine), chemin)
    print(f"Scène écrite : {chemin} ({formater_nombre(octets / 1e3)} ko)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. Serveur local de la vue 3D : avelis_3d/dist/ et la scène du scénario courant
# ═════════════════════════════════════════════════════════════════════════════════════════════

DOSSIER_DIST = DOSSIER_3D / "dist"
HOTE_LOCAL = "127.0.0.1"  # jamais accessible depuis une autre machine
CHEMIN_SCENE = "/scene.json"  # lu par avelis_3d/src/App.jsx, à côté de la page
PAGE_PAR_DEFAUT = "index.html"
NOM_FIL_SERVEUR = "serveur de la vue 3D"
# Types fixés ici : sous Windows, le registre associe parfois .js à text/plain, et le navigateur
# refuse alors de charger le script de la page
TYPES_CONTENU = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2"}
TYPE_PAR_DEFAUT = "application/octet-stream"


def message_sans_dist(dossier: pathlib.Path) -> str:
    """Explication affichée quand la vue 3D n'est pas construite."""
    return (f"La vue 3D n'est pas construite : {dossier / PAGE_PAR_DEFAUT} est absent.\n"
            f"Pour la construire (Node.js nécessaire), dans {dossier.parent} :\n"
            "npm install, puis npm run build")


class _ServeurHttp(http.server.ThreadingHTTPServer):
    """Serveur HTTP à fils d'exécution, sans la résolution de nom de HTTPServer au démarrage
    (elle peut prendre plusieurs secondes sous Windows)."""

    daemon_threads = True

    def server_bind(self) -> None:
        """Ouvre la socket ; le nom du serveur est son adresse."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class _Requetes(http.server.BaseHTTPRequestHandler):
    """Réponse à chaque requête GET : la scène publiée, un fichier de dist/, ou 404."""

    def do_GET(self) -> None:  # noqa: N802 — nom imposé par http.server
        """Envoie la ressource demandée, jamais mise en cache (la scène change à chaque
        publication, les fichiers à chaque construction)."""
        reponse = self.server.serveur_scene.reponse(urllib.parse.urlsplit(self.path).path)
        if reponse is None:
            self.send_error(404)
            return
        corps, type_contenu = reponse
        self.send_response(200)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *_arguments) -> None:
        """Aucune trace par requête : elle encombrerait la console de l'application."""


class ServeurScene:
    """Serveur HTTP local de la vue 3D : fichiers de `dossier` (avelis_3d/dist/) et scène
    publiée. N'écoute que sur 127.0.0.1, sur un port libre choisi par le système, dans un fil
    d'exécution à part : l'interface n'est jamais bloquée."""

    def __init__(self, dossier: pathlib.Path = DOSSIER_DIST):
        self.dossier = pathlib.Path(dossier).resolve()
        self._scene: bytes | None = None
        self._serveur: _ServeurHttp | None = None
        self._fil: threading.Thread | None = None

    @property
    def ecoute(self) -> tuple[str, int] | None:
        """(adresse, port) d'écoute ; None si le serveur est arrêté."""
        return None if self._serveur is None else self._serveur.server_address[:2]

    @property
    def port(self) -> int | None:
        """Port d'écoute ; None si le serveur est arrêté."""
        return None if self.ecoute is None else self.ecoute[1]

    def demarrer(self) -> None:
        """Démarre le serveur s'il ne tourne pas ; FileNotFoundError si dist/ n'est pas
        construit."""
        if not (self.dossier / PAGE_PAR_DEFAUT).is_file():
            raise FileNotFoundError(message_sans_dist(self.dossier))
        if self._serveur is not None:
            return
        self._serveur = _ServeurHttp((HOTE_LOCAL, 0), _Requetes)  # port 0 : choisi par le système
        self._serveur.serveur_scene = self
        self._fil = threading.Thread(target=self._serveur.serve_forever, name=NOM_FIL_SERVEUR,
                                     daemon=True)
        self._fil.start()

    def publier(self, scene: dict) -> int:
        """Remplace la scène servie ; renvoie sa taille en octets."""
        self._scene = scene_json(scene).encode("utf-8")
        return len(self._scene)

    def adresse(self, t: float = 0.0) -> str:
        """Adresse de la page, ouverte à l'instant t (minutes d'ouverture)."""
        return f"http://{HOTE_LOCAL}:{self.port}/{PAGE_PAR_DEFAUT}?t={t:.2f}"

    def reponse(self, chemin_url: str) -> tuple[bytes, str] | None:
        """Corps et type de contenu de la ressource ; None si elle n'existe pas ou si le chemin
        sort du dossier servi."""
        if chemin_url == CHEMIN_SCENE:
            return None if self._scene is None else (self._scene, TYPES_CONTENU[".json"])
        relatif = urllib.parse.unquote(chemin_url).lstrip("/") or PAGE_PAR_DEFAUT
        fichier = (self.dossier / relatif).resolve()
        if not fichier.is_relative_to(self.dossier) or not fichier.is_file():
            return None
        return fichier.read_bytes(), TYPES_CONTENU.get(fichier.suffix, TYPE_PAR_DEFAUT)

    def arreter(self) -> None:
        """Arrête le serveur et attend la fin de son fil ; sans effet s'il est arrêté."""
        if self._serveur is None:
            return
        self._serveur.shutdown()
        self._serveur.server_close()
        self._fil.join()
        self._serveur, self._fil = None, None


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 5. Scène du jumeau numérique : les scans d'avelis_scan, relus en direct par la vue 3D
# ═════════════════════════════════════════════════════════════════════════════════════════════

INTERVALLE_DIRECT_S = 2  # la page relit la scène du jumeau toutes les 2 s
MINUTES_JOUR_REEL = 24 * 60  # horloge réelle : le temps de la scène part de minuit
SECONDES_PAR_MINUTE = 60
ECHANTILLONS_JUMEAU_MAX = 2000  # stocks échantillonnés : pas d'au moins 1 min
TECHNO_JUMEAU = "Scans (avelis_scan)"
TYPES_JUMEAU_3D = ("module", "pod", "kit 2D", "lot")  # ossatures et composants : pas de forme 3D


def _minuit(secondes: float) -> float:
    """Minuit local (s depuis 1970) du jour de l'instant donné."""
    date = datetime.datetime.fromtimestamp(secondes)
    return date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _segments_jumeau(jumeau: jm.Jumeau, code: str, decalage: float) -> list:
    """Segments [t0, t1, [point]] : la pièce reste posée dans la zone de chaque scan jusqu'au
    suivant (position de Jumeau.repos) ; aucun segment hors du plan."""
    etats = jumeau.parcours[code][1]
    segments = []
    for i, (t, zone, _statut) in enumerate(etats):
        if zone in jumeau.zones:
            t1 = etats[i + 1][0] + decalage if i + 1 < len(etats) else None
            segments.append([t + decalage, t1, [_point(jumeau.repos(code, zone))]])
    return segments


def _liens_jumeau(jumeau: jm.Jumeau, code: str, codes: set[str]) -> dict:
    """Module parent et lot de la pièce, s'ils sont dans la scène."""
    piece = jumeau.pieces.get(code, {})
    liens = {"module": piece.get("parent"), "lot": piece.get("lot")}
    return {nom: valeur for nom, valeur in liens.items() if valeur in codes and valeur != code}


def _objets_jumeau(jumeau: jm.Jumeau, decalage: float) -> list[dict]:
    """Pièces scannées qui ont une forme 3D, dans l'ordre de leur premier scan, avec leurs
    scans acceptés comme événements de traçabilité (affichés dès leur enregistrement)."""
    codes = {code for code, (type_affiche, _) in jumeau.parcours.items()
             if type_affiche in TYPES_JUMEAU_3D}
    scans: dict[str, list] = {}
    for e in jumeau.evenements:
        if e["code"] in codes and e["resultat"] == "accepte":
            t = jumeau.instant(e["t"]) + decalage
            scans.setdefault(e["code"], []).append([t, e["evenement"], e["zone"], t,
                                                    e["message"] or ""])
    return [{"id": code, "type": type_affiche,
             "libelle": jumeau.pieces.get(code, {}).get("lot") or "pièce scannée",
             "liens": _liens_jumeau(jumeau, code, codes), "evenements": scans.get(code, []),
             "segments": _segments_jumeau(jumeau, code, decalage)}
            for code, (type_affiche, _) in jumeau.parcours.items() if code in codes]


def _alertes_jumeau(jumeau: jm.Jumeau, decalage: float) -> list[list]:
    """Alertes du serveur de scan [t, t_affichage, nature, id, type, zone, message]."""
    alertes = []
    for e in jumeau.alertes:
        t = jumeau.instant(e["t"]) + decalage
        alertes.append([t, t, e["evenement"], e["code"], jm.TYPES_AFFICHES.get(e["type"], ""),
                        e["zone"] or "", e["message"] or e["resultat"]])
    return alertes


def _comptes_en_zone(jumeau: jm.Jumeau, type_affiche: str, zone: str, decalage: float,
                     pas: float, nombre: int) -> list[int]:
    """Pièces du type présentes dans la zone aux instants k × pas (k < nombre), par les
    intervalles de présence de chaque pièce (sans rejouer le jumeau à chaque instant)."""
    variations = [0] * (nombre + 1)
    for type_piece, etats in jumeau.parcours.values():
        if type_piece != type_affiche:
            continue
        for i, (t, zone_etat, _) in enumerate(etats):
            if zone_etat != zone:
                continue
            fin = etats[i + 1][0] + decalage if i + 1 < len(etats) else math.inf
            debut_k = max(0, math.ceil((t + decalage) / pas))
            fin_k = nombre if math.isinf(fin) else min(nombre, math.ceil(fin / pas))
            if debut_k < fin_k:
                variations[debut_k] += 1
                variations[fin_k] -= 1
    comptes, total = [], 0
    for variation in variations[:nombre]:
        total += variation
        comptes.append(total)
    return comptes


def _pilotage_jumeau(jumeau: jm.Jumeau, modules_jour: float, decalage: float,
                     duree: float) -> dict:
    """Instants du tableau de pilotage tirés des scans (pas de camions dans l'atelier)."""
    premiers = {type_piece: sorted(etats[0][0] + decalage
                                   for type_objet, etats in jumeau.parcours.values()
                                   if type_objet == type_piece and etats)
                for type_piece in ("module", "pod")}
    decale = lambda instants: [t + decalage for t in instants]  # noqa: E731
    pas = max(1.0, duree / ECHANTILLONS_JUMEAU_MAX)
    nombre = int(duree / pas) + 1
    return {"objectif_jour": modules_jour, "of": premiers["module"],
            "entrees_pf": decale(jumeau.instants("module", "Entrée stock PF")),
            "expeditions": decale(jumeau.instants("module", jm.EXPEDITION)),
            "debuts_pods": premiers["pod"],
            "fins_pods": decale(jumeau.instants("pod", jm.INTEGRATION)), "camions": [],
            "echantillons": {"pas": pas, "stock_matieres": _comptes_en_zone(
                jumeau, "lot", "Stock matières", decalage, pas, nombre),
                "stock_pf": _comptes_en_zone(jumeau, "module", "Stock produits finis",
                                             decalage, pas, nombre)}}


def scene_jumeau(jumeau: jm.Jumeau, cadence: float, maintenant: float, revision: int) -> dict:
    """Scène 3D (même format que scene_3d) de l'atelier reconstitué par les scans, à l'instant
    réel `maintenant` (s). Le temps de la scène part du minuit du premier scan (horloge réelle,
    jours de 24 h) ; `direct` dit à la page de relire la scène, et `revision` change à chaque
    publication de nouveaux scans."""
    origine = jumeau.t0 if jumeau.t0 is not None else maintenant
    decalage = (origine - _minuit(origine)) / SECONDES_PAR_MINUTE
    duree = decalage + (jumeau.duree(maintenant) if jumeau.evenements else 0.0)
    usine = Usine(cadence, jumeau.implantation, jm.SCHEMA_JUMEAU, list(TECHNOLOGIES)[0])
    tracabilite = {"points_module": list(POINTS_MODULE), "points_pod": list(POINTS_POD),
                   "alertes": _alertes_jumeau(jumeau, decalage)}
    return {"version": VERSION_SCENE,
            "scenario": {"cadence": cadence, "implantation": jumeau.implantation,
                         "schema": jm.SCHEMA_JUMEAU, "techno": TECHNO_JUMEAU,
                         "jours": max(1, math.ceil(duree / MINUTES_JOUR_REEL)), "graine": "—"},
            "temps": {"duree": duree, "minutes_jour": MINUTES_JOUR_REEL, "heure_ouverture": 0,
                      "changements_equipe": changements_equipe()},
            "site": _site(usine), "gabarits": _gabarits(jm.SCHEMA_JUMEAU),
            "objets": _objets_jumeau(jumeau, decalage), "tracabilite": tracabilite,
            "pilotage": _pilotage_jumeau(jumeau, usine.calcul["modules_jour"], decalage, duree),
            "resultats": {},
            "direct": {"revision": revision, "intervalle_s": INTERVALLE_DIRECT_S,
                       "lieu": list(TORCY)}}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 6. Tests intégrés
# ═════════════════════════════════════════════════════════════════════════════════════════════

CLES_GABARITS = ("dim_camion", "dim_pod", "dim_kit_2d", "dim_lot", "dim_kit_module")
TOLERANCE_POSITION_M = 0.02  # écart admis : les points de la scène sont arrondis au centimètre
PAS_ECHANTILLON_MIN = 7.3  # instants comparés : k × 7,3 + 0,37 min (évite les instants ronds)
BORNES_VOLUME = (60, 2500, 5_000_000, 10.0)  # jours, cadence, octets et secondes au plus
DELAI_REQUETE_S = 5
# Demandes qui sortent du dossier servi (remontée, chemin absolu, barre oblique inverse)
CHEMINS_INTERDITS = ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt",
                     "/..%5csecret.txt", "/C:/Windows/win.ini")
RESSOURCES_DIST = re.compile(r'(?:src|href)="\./([^"]+)"')  # fichiers appelés par index.html


def _scene_de_test(implantation=IMPLANTATION_PROPOSEE, schema="unique", jours=3, graine=42,
                   techno=RFID):
    """Scène d'un scénario court, avec son usine."""
    usine = Usine(1500, implantation, schema, techno, jours=jours, graine=graine).executer()
    return usine, scene_3d(usine)


def test_gabarits_hypotheses():
    for cle in (*CLES_GABARITS, "hauteur_batiments"):
        _, _, marquage, commentaire = HYPOTHESES[cle]
        assert marquage == "H" and "ajoutée — à valider" in commentaire, cle
    for cle in CLES_GABARITS:
        assert len(H(cle)) == 3 and all(d > 0 for d in H(cle)), cle
    largeur, longueur, _ = H("dim_kit_module")
    assert math.isclose(largeur * longueur, H("m2_kit")), (largeur * longueur, H("m2_kit"))
    assert H("hauteur_batiments") > H("dim_module")[2]


def test_scene_site():
    for nom, plan in IMPLANTATIONS.items():
        usine, scene = _scene_de_test(nom)
        site = scene["site"]
        assert [c["points"] for c in site["contours"]] == [list(map(list, SITE_ACTUEL)),
                                                          list(map(list, EXTENSION))], nom
        assert [c["utilise"] for c in site["contours"]] == [True, plan["extension_utilisee"]]
        zones = {zone["nom"]: zone for zone in site["zones"]}
        assert set(zones) == set(plan["zones"]) - set(plan["zones_partagees"]), nom
        for zone in zones.values():
            ouverte = a_ciel_ouvert(zone["nom"], zone["categorie"])
            assert zone["hauteur"] == (0 if ouverte else H("hauteur_batiments")), zone
            if zone["categorie"] == "Réserve foncière":
                assert zone["hauteur"] == 0, zone  # « Réserve lignes 2030+ » (Optimisée)
            assert list(plan["zones"][zone["nom"]][:4]) == [zone["x"], zone["y"],
                                                            zone["largeur"], zone["profondeur"]]
        quais = site["quais"]
        assert quais["reception"]["nombre"] == usine.dimension["quais_reception"], nom
        assert quais["partages"] == (nom == IMPLANTATION_ACTUELLE), nom
        assert site["voirie"] == list(map(list, plan["voirie"])), nom
        assert site["portail"] == list(plan["portail"]) == site["acces"][-1], nom
        assert site["bretelles"] == [list(map(list, b)) for b in plan["bretelles"]], nom
        assert site["parking_vl"]["voie"] == list(map(list, plan["parking_vl"]["voie"])), nom
        for fonction in ("reception", "expedition"):
            assert quais[fonction]["pas"] == list(plan[f"pas_quai_{fonction}"]), nom
    _, scene = _scene_de_test(IMPLANTATION_ACTUELLE)
    libelles = {zone["nom"]: zone["libelle"] for zone in scene["site"]["zones"]}
    assert libelles["Réception"] == "Réception / Expédition", libelles


def test_scene_gabarits():
    for schema, cle_module in (("unique", "dim_module"), ("satellites", "dim_kit_module")):
        _, scene = _scene_de_test(schema=schema)
        gabarits = scene["gabarits"]
        assert set(gabarits) == set(TYPES_OBJETS), gabarits
        assert gabarits["module"] == list(H(cle_module)), schema
        assert gabarits["camion"] == list(H("dim_camion")), schema


def test_scene_serialisable():
    for schema in ("unique", "satellites"):
        usine, scene = _scene_de_test(schema=schema)
        texte = json.dumps(scene, allow_nan=False)  # inf ou NaN lèveraient ValueError
        assert json.loads(texte) == scene, schema
        assert scene["temps"]["duree"] == usine.duree
        assert {objet["type"] for objet in scene["objets"]} == set(TYPES_OBJETS), schema
        for objet in scene["objets"]:
            assert objet["id"] in usine.objets and isinstance(objet["libelle"], str), objet["id"]
            debuts = [segment[0] for segment in objet["segments"]]
            assert debuts == sorted(debuts), objet["id"]
            for t0, t1, points in objet["segments"]:
                assert points and (t1 is None or t1 >= t0), objet["id"]


def _ecart_positions(usine, scene, t: float) -> float:
    """Plus grand écart (m) entre les positions de la scène et celles de l'usine à l'instant t ;
    échoue si les objets visibles diffèrent."""
    attendues, obtenues = usine.positions(t), positions_scene(scene, t)
    assert set(obtenues) == set(attendues), (t, set(obtenues) ^ set(attendues))
    ecart = 0.0
    for id_objet, (x, y, type_objet) in attendues.items():
        assert obtenues[id_objet][2] == type_objet, id_objet
        ecart = max(ecart, math.dist((x, y), obtenues[id_objet][:2]))
    return ecart


def test_scene_positions():
    for nom in IMPLANTATIONS:
        for schema in ("unique", "satellites"):
            usine, scene = _scene_de_test(nom, schema)
            instants = [k * PAS_ECHANTILLON_MIN + 0.37
                        for k in range(int(usine.duree / PAS_ECHANTILLON_MIN))]
            ecart = max(_ecart_positions(usine, scene, t) for t in instants)
            assert ecart <= TOLERANCE_POSITION_M, (nom, schema, ecart)


def test_scene_reproductible():
    _, a = _scene_de_test(graine=7)
    _, b = _scene_de_test(graine=7)
    _, c = _scene_de_test(graine=8)
    assert scene_json(a) == scene_json(b)
    assert scene_json(a) != scene_json(c)


def test_scene_volume():
    jours, cadence, octets_max, secondes_max = BORNES_VOLUME
    debut = time.perf_counter()
    usine = Usine(cadence, IMPLANTATION_PROPOSEE, "unique", RFID, jours=jours).executer()
    simulation = time.perf_counter() - debut
    octets = len(scene_json(scene_3d(usine)).encode("utf-8"))
    export = time.perf_counter() - debut - simulation
    print(f"    {jours} j à {formater_nombre(cadence)} logements/an : "
          f"{formater_nombre(len(usine.objets))} objets, {formater_nombre(octets / 1e6, 1)} Mo, "
          f"simulation {formater_nombre(simulation, 1)} s, export {formater_nombre(export, 1)} s")
    assert octets <= octets_max, octets
    assert export <= secondes_max, export


def test_scene_tracabilite():
    usine, scene = _scene_de_test(techno=PAPIER)  # le papier laisse des événements non lus
    objets = {objet["id"]: objet for objet in scene["objets"]}
    for id_objet, enregistrements in usine.tracabilite.par_objet.items():
        normaux = [e for e in enregistrements if not e["alerte"]]
        attendus = [[e["t"], e["evenement"], e["zone"], e["t_affichage"], e["message"]]
                    for e in normaux]
        if id_objet in objets:
            assert objets[id_objet]["evenements"] == attendus, id_objet
        else:  # jamais dessiné (module pas encore assemblé à la fin, machine) : hors scène
            assert id_objet not in usine.timelines(), id_objet
    non_lus = [e for o in objets.values() for e in o["evenements"] if e[3] is None]
    assert non_lus and all(e[3] is None or e[3] >= e[0] for o in objets.values()
                           for e in o["evenements"])
    alertes = scene["tracabilite"]["alertes"]
    assert len(alertes) == sum(1 for e in usine.tracabilite.journal if e["alerte"]) > 0
    assert [a[1] for a in alertes] == sorted(a[1] for a in alertes)
    assert all(a[1] >= a[0] for a in alertes)
    assert scene["tracabilite"]["points_module"][-1] == "Expédié"
    assert scene["tracabilite"]["points_pod"][-1] == "Intégré au module"


def test_scene_liens():
    usine, scene = _scene_de_test()
    objets = {objet["id"]: objet for objet in scene["objets"]}
    for objet in objets.values():
        liens = objet["liens"]
        for lie in [v for k, v in liens.items() if k != "modules"] + liens.get("modules", []):
            assert lie in usine.objets, (objet["id"], lie)
        if objet["type"] == "module":
            for type_lie in ("pod", "kit 2D"):
                if type_lie in liens and liens[type_lie] in objets:
                    assert objets[liens[type_lie]]["liens"]["module"] == objet["id"]
            if "camion" in liens:
                assert objet["id"] in objets[liens["camion"]]["liens"]["modules"]
    modules = [o for o in objets.values() if o["type"] == "module"]
    assert modules and all("lot" in m["liens"] and "kit 2D" in m["liens"] for m in modules)


def _pilotage_usine(usine, t: float) -> dict:
    """Tableau de pilotage calculé directement depuis l'usine (algorithme de la vue 2)."""
    modules, pods = usine.objets_de_type("module"), usine.objets_de_type("pod")
    debut = math.floor(t / minutes_jour()) * minutes_jour()
    compter = lambda instants, depuis=-math.inf: sum(  # noqa: E731
        1 for x in instants if x is not None and depuis <= x <= t)
    passes = [e for e in usine.echantillons if e["t"] <= t]
    return {
        "termines_jour": compter((m["t_stock_pf"] for m in modules), debut),
        "objectif_heure": usine.calcul["modules_jour"] * (t - debut) / minutes_jour(),
        "expedies_jour": compter((m["t_expedie"] for m in modules), debut),
        "expedies": compter(m["t_expedie"] for m in modules),
        "en_cours": compter(m["t_of"] for m in modules)
        - compter(m["t_stock_pf"] for m in modules),
        "stock_matieres": passes[-1]["stock_matieres"], "stock_pf": passes[-1]["stock_pf"],
        "pods_en_cours": compter(usine.tracabilite.par_objet[p["id"]][0]["t"] for p in pods)
        - compter(p["t_integre"] for p in pods),
        "camions_sur_site": usine.camions_sur_site(t),
        "alertes": compter(e["t_affichage"] for e in usine.tracabilite.journal if e["alerte"]),
    }


def test_scene_pilotage():
    for schema in ("unique", "satellites"):
        usine, scene = _scene_de_test(schema=schema)
        pas = scene["pilotage"]["echantillons"]["pas"]
        assert [e["t"] for e in usine.echantillons] == [k * pas for k in
                                                        range(len(usine.echantillons))]
        instants = [k * PAS_ECHANTILLON_MIN + 0.37
                    for k in range(int(usine.duree / PAS_ECHANTILLON_MIN))]
        for t in [*instants, minutes_jour(), 2 * minutes_jour() - 1e-3, usine.duree]:
            obtenu, attendu = pilotage_scene(scene, t), _pilotage_usine(usine, t)
            assert math.isclose(obtenu.pop("objectif_heure"), attendu.pop("objectif_heure"))
            assert obtenu == attendu, (schema, t)
    usine, scene = _scene_de_test(jours=10)  # assez d'alertes pour en écarter les plus vieilles
    alertes = sorted((e for e in usine.tracabilite.journal if e["alerte"]),
                     key=lambda e: e["t_affichage"])
    t = alertes[NB_ALERTES_AFFICHEES + 3]["t_affichage"]
    attendues = [e["id"] for e in alertes if e["t_affichage"] <= t][::-1]
    assert [a[3] for a in alertes_affichees_scene(scene, t)] == attendues[:NB_ALERTES_AFFICHEES]
    assert alertes_affichees_scene(scene, alertes[0]["t_affichage"] - 1e-9) == []


def test_scene_resultats():
    usine, scene = _scene_de_test()
    resultats = usine.resultats()
    assert scene["resultats"]["pareto_causes"] == [list(c) for c in resultats["pareto_causes"]]
    assert {**scene["resultats"], "pareto_causes": resultats["pareto_causes"]} == resultats
    objet = next(o for o in scene["objets"] if o["type"] == "module")
    tous = evenements_affiches(objet, usine.duree)
    assert tous and evenements_affiches(objet, tous[0][3] - 1e-9) == []
    assert evenements_affiches(objet, tous[0][3]) == tous[:1]


def _dist_de_test(racine: pathlib.Path) -> pathlib.Path:
    """Faux dist/ (une page, un script, une feuille de style) et, à côté, un fichier que le
    serveur ne doit jamais rendre."""
    dossier = racine / "dist"
    (dossier / "assets").mkdir(parents=True)
    (dossier / "index.html").write_text("<!doctype html><title>Vue 3D</title>", encoding="utf-8")
    (dossier / "assets" / "index.js").write_text("console.log('vue 3D');", encoding="utf-8")
    (dossier / "assets" / "index.css").write_text("body { margin: 0; }", encoding="utf-8")
    (racine / "secret.txt").write_text("hors du dossier servi", encoding="utf-8")
    return dossier


def _lire(adresse: str) -> tuple[int, str, bytes]:
    """(code, type de contenu, corps) de la réponse, sans passer par un proxy."""
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with ouvreur.open(adresse, timeout=DELAI_REQUETE_S) as reponse:
            return reponse.status, reponse.headers.get("Content-Type", ""), reponse.read()
    except urllib.error.HTTPError as erreur:
        return erreur.code, "", b""


def test_serveur_fichiers():
    with tempfile.TemporaryDirectory() as racine:
        serveur = ServeurScene(_dist_de_test(pathlib.Path(racine)))
        serveur.demarrer()
        try:
            base = f"http://{HOTE_LOCAL}:{serveur.port}"
            assert _lire(f"{base}/scene.json")[0] == 404  # aucune scène publiée
            _, scene = _scene_de_test(jours=1)
            serveur.publier(scene)
            code, type_contenu, corps = _lire(f"{base}/scene.json?v=2")
            assert (code, type_contenu) == (200, TYPES_CONTENU[".json"]), (code, type_contenu)
            assert json.loads(corps.decode("utf-8")) == scene
            for chemin, extension in (("/", ".html"), ("/index.html?t=12.5", ".html"),
                                      ("/assets/index.js", ".js"),
                                      ("/assets/index.css", ".css")):
                code, type_contenu, _ = _lire(base + chemin)
                assert (code, type_contenu) == (200, TYPES_CONTENU[extension]), chemin
            for chemin in ("/absente.js", "/assets/", *CHEMINS_INTERDITS):
                assert _lire(base + chemin)[0] == 404, chemin
        finally:
            serveur.arreter()


def test_serveur_local():
    with tempfile.TemporaryDirectory() as racine:
        dossier = _dist_de_test(pathlib.Path(racine))
        a, b = ServeurScene(dossier), ServeurScene(dossier)
        a.demarrer()
        b.demarrer()
        try:
            port = a.port
            a.demarrer()  # déjà démarré : même port
            assert a.port == port and a.ecoute == (HOTE_LOCAL, port), a.ecoute
            assert b.ecoute[0] == HOTE_LOCAL and b.port not in (port, 0), (port, b.port)
            assert a.adresse(1460.123) == f"http://{HOTE_LOCAL}:{port}/index.html?t=1460.12"
            assert a.adresse() == f"http://{HOTE_LOCAL}:{port}/index.html?t=0.00"
        finally:
            a.arreter()
            b.arreter()


def test_serveur_arret():
    with tempfile.TemporaryDirectory() as racine:
        serveur = ServeurScene(_dist_de_test(pathlib.Path(racine)))
        serveur.demarrer()
        port = serveur.port
        assert _lire(f"http://{HOTE_LOCAL}:{port}/")[0] == 200
        serveur.arreter()
        assert serveur.port is None and serveur.ecoute is None
        assert not any(fil.name == NOM_FIL_SERVEUR for fil in threading.enumerate())
        try:
            _lire(f"http://{HOTE_LOCAL}:{port}/")
            refusee = False
        except urllib.error.URLError:
            refusee = True
        assert refusee, port
        serveur.arreter()  # un second arrêt ne fait rien


def test_serveur_sans_dist():
    with tempfile.TemporaryDirectory() as racine:
        serveur = ServeurScene(pathlib.Path(racine) / "dist")
        message = ""
        try:
            serveur.demarrer()
        except FileNotFoundError as erreur:
            message = str(erreur)
        assert "npm run build" in message and "dist" in message, message
        assert serveur.port is None


def test_serveur_dist_construit():
    assert (DOSSIER_DIST / "index.html").is_file(), DOSSIER_DIST
    page = (DOSSIER_DIST / "index.html").read_text(encoding="utf-8")
    ressources = RESSOURCES_DIST.findall(page)
    assert {pathlib.PurePosixPath(r).suffix for r in ressources} >= {".js", ".css"}, ressources
    # tout fichier construit (police comprise, appelée par la feuille de style) a un type connu
    ressources += [f.relative_to(DOSSIER_DIST).as_posix() for f in DOSSIER_DIST.rglob("*")
                   if f.is_file() and f.name != PAGE_PAR_DEFAUT]
    serveur = ServeurScene()
    serveur.demarrer()
    try:
        base = f"http://{HOTE_LOCAL}:{serveur.port}"
        assert _lire(f"{base}/")[2].decode("utf-8") == page
        for ressource in ressources:
            code, type_contenu, corps = _lire(f"{base}/{ressource}")
            attendu = TYPES_CONTENU[pathlib.PurePosixPath(ressource).suffix]
            assert (code, type_contenu) == (200, attendu) and corps, ressource
    finally:
        serveur.arreter()


def test_scene_trois_implantations():
    for choix, implantation in CHOIX_IMPLANTATIONS.items():
        usine, scene = _scene_de_test(implantation, jours=1)
        assert scene["scenario"]["implantation"] == implantation, choix
        json.loads(scene_json(scene))
        assert _ecart_positions(usine, scene, 400.37) <= TOLERANCE_POSITION_M, choix


def test_scene_jumeau():
    base, _horloge, m1, m2 = jm._atelier_de_test()
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    fin = jumeau.duree()
    maintenant = jumeau.t0 + fin * SECONDES_PAR_MINUTE + 30
    scene = json.loads(scene_json(scene_jumeau(jumeau, 1500, maintenant, 7)))
    decalage = (jumeau.t0 - _minuit(jumeau.t0)) / SECONDES_PAR_MINUTE
    assert scene["direct"]["revision"] == 7 and abs(scene["temps"]["duree"] - decalage
                                                     - fin - 0.5) < 1e-6
    for t in (fin / 3, fin / 2, fin):
        attendu = {code: p for code, p in jumeau.positions(t).items() if p[2] in TYPES_JUMEAU_3D}
        obtenu = positions_scene(scene, t + decalage)
        assert set(obtenu) == set(attendu)
        assert all(math.dist(obtenu[c][:2], attendu[c][:2]) <= TOLERANCE_POSITION_M
                   for c in attendu)
    assert pilotage_scene(scene, decalage + fin)["expedies"] == 1
    assert scene["tracabilite"]["alertes"] and m2[1] in {a[3] for a in
                                                        scene["tracabilite"]["alertes"]}
    vide = scene_jumeau(jm.Jumeau(), 1500, maintenant, 0)
    assert vide["objets"] == [] and vide["temps"]["duree"] >= 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    OPTIONS = _arguments()
    if OPTIONS.reference:
        OCTETS = ecrire_json(reference_js(), FICHIER_REFERENCE)
        print(f"Jeu de référence écrit : {FICHIER_REFERENCE} ({formater_nombre(OCTETS / 1e3)} ko)")
    elif OPTIONS.scene:
        _ecrire_scene_demandee(OPTIONS)
    else:
        sys.exit(0 if executer_tests(globals(), "scene_3d.py") else 1)
