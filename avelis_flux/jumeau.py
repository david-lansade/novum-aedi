"""Jumeau numérique de l'atelier de Torcy à partir des scans d'avelis_scan.

Configuration retenue : usine unique, implantation avec extension. Chaque scan accepté place la
pièce dans la zone du plan de son poste (les noms de zones d'avelis_scan/config.py sont ceux de
modele.py) ; on rejoue ainsi l'atelier à n'importe quel instant, comme la simulation.

Sources des scans (même format d'événement, celui de la table « evenements ») :
  - le serveur de scan, par son API JSON (GET /api/evenements?depuis=<id>, GET /api/pieces) ;
  - à défaut, la base SQLite d'avelis_scan ouverte en lecture seule (même PC, serveur arrêté).

Le temps du jumeau est en minutes depuis le premier scan (comme le temps de la simulation) ;
l'horloge affiche l'heure réelle. La comparaison avec la simulation porte sur les durées entre
étapes des gammes, communes aux deux (simulation.POINTS_MODULE et POINTS_POD).

Ce module n'importe aucun module graphique. Exécution directe : tests intégrés.
"""

import bisect
import datetime
import json
import math
import pathlib
import random
import sqlite3
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request

import modele as m
import simulation as sim
from modele import H

DOSSIER_PROJET = pathlib.Path(__file__).resolve().parent.parent
ADRESSE_SCAN_DEFAUT = "http://localhost:8000"  # serveur d'avelis_scan lancé sur ce PC
BASE_SCAN_DEFAUT = DOSSIER_PROJET / "avelis_scan" / "donnees" / "atelier.db"
DELAI_RESEAU_S = 1.5  # attente maximale d'une réponse du serveur de scan
EVENEMENTS_PAR_PAGE = 500  # limite d'une réponse de /api/evenements
IMPLANTATION_JUMEAU, SCHEMA_JUMEAU = m.IMPLANTATION_PROPOSEE, "unique"
SECONDES_PAR_MINUTE = 60
CONFIRMATION_VIDER = "VIDER"  # mot exigé par POST /api/vider du serveur de scan
TABLES_SCAN = ("pieces", "evenements", "sejours", "defauts", "cartes", "demandes", "consignes")

# Types de pièces d'avelis_scan → type affiché sur le plan
TYPES_AFFICHES = {"module": "module", "pod": "pod", "kit2d": "kit 2D", "ossature": "ossature",
                  "composant": "composant", "lot": "lot"}
INTEGRATION, EXPEDITION, REBUT, DEFAUT = ("Intégré au module", "Expédié", "Mise au rebut",
                                          "Défaut déclaré")
LOT_BLOQUE, LOT_DEBLOQUE = "Lot bloqué", "Lot débloqué"
FINS_DE_PARCOURS = (INTEGRATION, EXPEDITION, REBUT)  # la pièce quitte le plan
RESULTATS_ALERTE = ("alerte", "refuse")
GAMMES_COMPAREES = {"module": sim.POINTS_MODULE, "pod": sim.POINTS_POD}
LIBELLES_INDICATEURS = ("Terminés aujourd'hui / objectif à cette heure",
                        "Expédiés aujourd'hui (total)", "En-cours : modules / pods",
                        "Défauts ouverts / lots bloqués", "Stock matières (lots)",
                        "Stock produits finis")


class SourceIndisponible(Exception):
    """Ni le serveur de scan ni la base ne peuvent être lus."""


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. Sources des scans : evenements(depuis, limite), pieces() et vider(), comme
#    avelis_scan/base.py
# ═════════════════════════════════════════════════════════════════════════════════════════════

class SourceServeur:
    """API JSON du serveur de scan."""

    def __init__(self, adresse: str = ADRESSE_SCAN_DEFAUT, delai_s: float = DELAI_RESEAU_S):
        self.adresse, self.delai_s = adresse.rstrip("/"), delai_s
        self.nom = f"serveur de scan {self.adresse}"

    def _lire(self, chemin: str, **parametres):
        """Réponse JSON d'une requête GET ; SourceIndisponible si le serveur ne répond pas."""
        url = f"{self.adresse}{chemin}?{urllib.parse.urlencode(parametres)}"
        try:
            with urllib.request.urlopen(url, timeout=self.delai_s) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as erreur:
            raise SourceIndisponible(f"{self.nom} injoignable ({erreur})") from None

    def evenements(self, depuis: int = 0, limite: int = EVENEMENTS_PAR_PAGE) -> list[dict]:
        """Événements d'identifiant > depuis, dans l'ordre."""
        return self._lire("/api/evenements", depuis=depuis, limite=limite)

    def pieces(self) -> list[dict]:
        """Toutes les pièces (code, type, lot, parent…)."""
        return self._lire("/api/pieces")

    def envoyer_consigne(self, poste: str, message: str) -> None:
        """Envoie une consigne au téléphone d'un poste (POST /api/consignes), comme le PC."""
        self._poster("/api/consignes", {"poste": poste, "message": message,
                                        "operateur": "Jumeau numérique"}, "consigne non envoyée")

    def _poster(self, chemin: str, donnees: dict, echec: str) -> None:
        """Requête POST en JSON ; SourceIndisponible (avec `echec`) si elle n'aboutit pas."""
        requete = urllib.request.Request(f"{self.adresse}{chemin}",
                                         data=json.dumps(donnees).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(requete, timeout=self.delai_s) as reponse:
                reponse.read()
        except (urllib.error.URLError, OSError) as erreur:
            raise SourceIndisponible(f"{self.nom} : {echec} ({erreur})") from None

    def vider(self) -> None:
        """Efface toute la base du serveur de scan (POST /api/vider, confirmation comprise)."""
        self._poster("/api/vider", {"confirmation": CONFIRMATION_VIDER}, "base non vidée")


class SourceFichier:
    """Base SQLite d'avelis_scan, ouverte en lecture seule à chaque lecture."""

    def __init__(self, chemin: pathlib.Path | str = BASE_SCAN_DEFAUT):
        self.chemin = pathlib.Path(chemin)
        self.nom = f"base {self.chemin.name} (lecture du fichier)"

    def _tous(self, requete: str, *arguments) -> list[dict]:
        """Lignes d'une requête, en dictionnaires."""
        if not self.chemin.is_file():
            raise SourceIndisponible(f"base introuvable : {self.chemin}")
        try:
            connexion = sqlite3.connect(f"{self.chemin.as_uri()}?mode=ro", uri=True)
            try:
                connexion.row_factory = sqlite3.Row
                return [dict(ligne) for ligne in connexion.execute(requete, arguments)]
            finally:
                connexion.close()
        except sqlite3.Error as erreur:
            raise SourceIndisponible(f"{self.nom} illisible ({erreur})") from None

    def evenements(self, depuis: int = 0, limite: int = EVENEMENTS_PAR_PAGE) -> list[dict]:
        """Événements d'identifiant > depuis, dans l'ordre."""
        return self._tous("SELECT * FROM evenements WHERE id>? ORDER BY id LIMIT ?", depuis,
                          limite)

    def pieces(self) -> list[dict]:
        """Toutes les pièces."""
        return self._tous("SELECT * FROM pieces")

    def vider(self) -> None:
        """Efface toutes les tables de la base (comme Base.vider d'avelis_scan) ; seule écriture
        du jumeau, quand le serveur de scan n'est pas lancé."""
        if not self.chemin.is_file():
            raise SourceIndisponible(f"base introuvable : {self.chemin}")
        try:
            connexion = sqlite3.connect(self.chemin, timeout=DELAI_RESEAU_S)
            try:
                with connexion:
                    for table in TABLES_SCAN:
                        connexion.execute(f"DELETE FROM {table}")
                    connexion.execute("DELETE FROM sqlite_sequence")
            finally:
                connexion.close()
        except sqlite3.Error as erreur:
            raise SourceIndisponible(f"{self.nom} : base non vidée ({erreur})") from None


def ouvrir_source(adresse: str = ADRESSE_SCAN_DEFAUT,
                  chemin: pathlib.Path | str = BASE_SCAN_DEFAUT):
    """Le serveur de scan s'il répond, sinon la base en lecture seule ; SourceIndisponible si
    aucun des deux n'est lisible."""
    erreurs = []
    for source in (SourceServeur(adresse), SourceFichier(chemin)):
        try:
            source.evenements(0, 1)
            return source
        except SourceIndisponible as erreur:
            erreurs.append(str(erreur))
    raise SourceIndisponible(" ; ".join(erreurs))


def lire_source(source, depuis: int, premier_connu: dict | None) -> dict:
    """Lecture complète (appelée hors de l'interface, dans un fil d'exécution) : nouveaux
    événements depuis l'identifiant `depuis` et pièces. Si le premier événement de la base n'est
    plus celui déjà connu (base vidée), tout est relu : « reinitialiser » vaut alors True."""
    premier = source.evenements(0, 1)
    reinitialiser = premier_connu is not None and (
        not premier or (premier[0]["id"], premier[0]["t"]) != (premier_connu["id"],
                                                                premier_connu["t"]))
    depuis = 0 if reinitialiser else depuis
    evenements = []
    while True:
        page = source.evenements(depuis, EVENEMENTS_PAR_PAGE)
        evenements += page
        if len(page) < EVENEMENTS_PAR_PAGE:
            break
        depuis = page[-1]["id"]
    return {"reinitialiser": reinitialiser, "evenements": evenements, "pieces": source.pieces()}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. État du jumeau : parcours de chaque pièce, positions et indicateurs à l'instant t
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _etat_apres(evenement: dict) -> tuple[str | None, str] | None:
    """(zone, statut) d'une pièce après l'événement, None s'il ne la déplace pas ; zone None :
    la pièce quitte le plan (intégrée, expédiée, mise au rebut)."""
    if evenement["evenement"] in FINS_DE_PARCOURS and evenement["resultat"] in ("accepte",
                                                                                "alerte"):
        return None, "termine"
    if not evenement["zone"]:
        return None
    if evenement["evenement"] == DEFAUT:
        return evenement["zone"], "defaut"
    if evenement["resultat"] == "accepte":
        return evenement["zone"], "en_cours"
    return None


class Jumeau:
    """Atelier reconstitué à partir des événements de scan, rejouable à tout instant."""

    def __init__(self, implantation: str = IMPLANTATION_JUMEAU):
        self.choisir_plan(implantation)
        self.vider()

    def choisir_plan(self, implantation: str) -> None:
        """Plan sur lequel les pièces sont dessinées. Les scans ne changent pas : chaque pièce
        est replacée dans la zone de même nom du nouveau plan."""
        self.implantation = implantation
        self.plan = m.IMPLANTATIONS[implantation]
        self.zones = self.plan["zones"]
        self._repos_cache = {}

    def vider(self) -> None:
        """Oublie tous les événements (base de scan vidée)."""
        self.evenements: list[dict] = []
        self.pieces: dict[str, dict] = {}
        self.t0: float | None = None  # instant (s depuis 1970) du premier événement
        # code → (type, [(t, zone, statut)])
        self.parcours: dict[str, tuple[str, list[tuple]]] = {}
        self.blocages: dict[str, list[tuple[float, bool]]] = {}  # lot → [(t, bloqué ?)]
        self.alertes: list[dict] = []
        self._repos_cache: dict[tuple, tuple] = {}

    @property
    def dernier_id(self) -> int:
        """Identifiant du dernier événement intégré (0 si aucun)."""
        return self.evenements[-1]["id"] if self.evenements else 0

    @property
    def premier(self) -> dict | None:
        """Premier événement intégré : sert à détecter une base vidée."""
        return self.evenements[0] if self.evenements else None

    def appliquer(self, lecture: dict) -> int:
        """Intègre le résultat de lire_source ; renvoie le nombre de nouveaux événements."""
        if lecture["reinitialiser"]:
            self.vider()
        self.pieces = {piece["code"]: piece for piece in lecture["pieces"]}
        nouveaux = [e for e in lecture["evenements"] if e["id"] > self.dernier_id]
        for evenement in nouveaux:
            self._integrer(evenement)
        return len(nouveaux)

    def actualiser(self, source) -> int:
        """Lecture et intégration en une fois (tests, lecture ponctuelle)."""
        return self.appliquer(lire_source(source, self.dernier_id, self.premier))

    def _integrer(self, evenement: dict) -> None:
        """Ajoute un événement : parcours de la pièce, blocage de lot, alerte."""
        self.evenements.append(evenement)
        if self.t0 is None:
            self.t0 = evenement["t"]
        t = self.instant(evenement["t"])
        if evenement["evenement"] in (LOT_BLOQUE, LOT_DEBLOQUE):
            self.blocages.setdefault(evenement["code"], []).append(
                (t, evenement["evenement"] == LOT_BLOQUE))
        if evenement["resultat"] in RESULTATS_ALERTE:
            self.alertes.append(evenement)
        type_affiche = TYPES_AFFICHES.get(evenement["type"])
        etat = _etat_apres(evenement) if type_affiche else None
        if etat is not None:
            self.parcours.setdefault(evenement["code"], (type_affiche, []))[1].append((t, *etat))

    # ── Temps ───────────────────────────────────────────────────────────────────────────────

    def instant(self, t_secondes: float) -> float:
        """Minutes du jumeau d'un instant réel (secondes depuis 1970)."""
        return (t_secondes - (self.t0 or t_secondes)) / SECONDES_PAR_MINUTE

    def date(self, t: float) -> datetime.datetime:
        """Date et heure locales de l'instant t du jumeau."""
        return datetime.datetime.fromtimestamp((self.t0 or 0) + t * SECONDES_PAR_MINUTE)

    def duree(self, maintenant: float | None = None) -> float:
        """Durée rejouable (min) : jusqu'au dernier scan, ou jusqu'à `maintenant` (s)."""
        if not self.evenements:
            return 0.0
        fin = self.evenements[-1]["t"] if maintenant is None else max(maintenant,
                                                                      self.evenements[-1]["t"])
        return self.instant(fin)

    def horloge(self, t: float) -> str:
        """Horloge du tableau de pilotage : « JJ/MM · HH:MM:SS »."""
        return f"{self.date(t):%d/%m · %H:%M:%S}"

    def horloge_courte(self, t: float) -> str:
        """Horodatage compact : « HH:MM:SS »."""
        return f"{self.date(t):%H:%M:%S}"

    # ── Positions ───────────────────────────────────────────────────────────────────────────

    def etat(self, code: str, t: float) -> tuple | None:
        """(t, zone, statut) de la pièce à l'instant t, None avant son premier scan."""
        etats = self.parcours[code][1]
        i = bisect.bisect_right([e[0] for e in etats], t) - 1
        return etats[i] if i >= 0 else None

    def repos(self, code: str, zone: str) -> tuple[float, float]:
        """Position stable de la pièce dans la zone (même règle que la simulation)."""
        cle = (code, zone)
        if cle not in self._repos_cache:
            x, y, largeur, hauteur = self.zones[zone][:4]
            tirage = random.Random(f"{code}|{zone}")
            marge = (1 - sim.DISPERSION_REPOS) / 2
            dispersion = sim.DISPERSION_REPOS
            self._repos_cache[cle] = (x + largeur * (marge + dispersion * tirage.random()),
                                      y + hauteur * (marge + dispersion * tirage.random()))
        return self._repos_cache[cle]

    def positions(self, t: float) -> dict[str, tuple[float, float, str]]:
        """{code: (x, y, type affiché)} des pièces présentes sur le plan à l'instant t."""
        visibles = {}
        for code, (type_affiche, _) in self.parcours.items():
            etat = self.etat(code, t)
            if etat is not None and etat[1] in self.zones:
                visibles[code] = (*self.repos(code, etat[1]), type_affiche)
        return visibles

    def lot_bloque(self, lot: str, t: float) -> bool:
        """Le lot est-il bloqué à l'instant t ?"""
        historique = self.blocages.get(lot, [])
        i = bisect.bisect_right([b[0] for b in historique], t) - 1
        return i >= 0 and historique[i][1]

    def lots_de(self, code: str) -> set[str]:
        """Lot de la pièce et, pour un module, lots de ses composants."""
        lots = {self.pieces.get(code, {}).get("lot", "")}
        lots |= {p.get("lot", "") for p in self.pieces.values() if p.get("parent") == code}
        return {lot for lot in lots if lot}

    def signalees(self, t: float) -> set[str]:
        """Pièces présentes en défaut ouvert ou à isoler (lot bloqué) à l'instant t."""
        resultat = set()
        for code in self.positions(t):
            if self.etat(code, t)[2] == "defaut" or any(self.lot_bloque(lot, t)
                                                        for lot in self.lots_de(code)):
                resultat.add(code)
        return resultat

    def trace_parcourue(self, code: str, t: float) -> list[tuple[float, float]]:
        """Points des zones déjà visitées jusqu'à t, reliés en L (mode suivi)."""
        points: list = []
        for t_etat, zone, _ in self.parcours.get(code, ("", []))[1]:
            if t_etat > t or zone is None:
                break
            point = self.repos(code, zone)
            if points and point == points[-1]:
                continue
            if points:
                points.append((point[0], points[-1][1]))
            points.append(point)
        return points

    def evenements_de(self, code: str) -> list[dict]:
        """Événements de la pièce et de ses composants, dans l'ordre."""
        codes = {code} | {p["code"] for p in self.pieces.values() if p.get("parent") == code}
        return [e for e in self.evenements if e["code"] in codes]

    # ── Indicateurs du tableau de pilotage ──────────────────────────────────────────────────

    def instants(self, type_piece: str, etape: str, t: float = math.inf) -> list[float]:
        """Instants (min) du premier scan accepté de l'étape pour chaque pièce, jusqu'à t."""
        vus: dict[str, float] = {}
        for e in self.evenements:
            if (e["type"] == type_piece and e["evenement"] == etape
                    and e["resultat"] == "accepte" and e["code"] not in vus):
                vus[e["code"]] = self.instant(e["t"])
        return sorted(x for x in vus.values() if x <= t)

    def _nombre_en_zone(self, type_affiche: str, zone: str, t: float) -> int:
        """Pièces d'un type présentes dans une zone à l'instant t."""
        return sum(1 for code, (x, y, type_objet) in self.positions(t).items()
                   if type_objet == type_affiche and self.etat(code, t)[1] == zone)

    def _en_cours(self, type_piece: str, t: float) -> int:
        """Pièces d'un type déjà scannées, encore sur le plan, hors stocks."""
        return sum(1 for code, (type_affiche, _) in self.parcours.items()
                   if type_affiche == TYPES_AFFICHES[type_piece]
                   and (etat := self.etat(code, t)) is not None
                   and etat[1] not in (None, "Stock produits finis"))

    def objectif_a(self, t: float, modules_jour: float) -> float:
        """Modules attendus depuis l'ouverture du jour de l'instant t."""
        date = self.date(t)
        ouverture = date.replace(hour=H("heure_ouverture"), minute=0, second=0, microsecond=0)
        ecoule = (date - ouverture).total_seconds() / SECONDES_PAR_MINUTE
        return modules_jour * min(max(ecoule, 0.0), sim.minutes_jour()) / sim.minutes_jour()

    def valeurs(self, t: float, modules_jour: float) -> dict[str, str]:
        """Textes du tableau de pilotage à l'instant t (rubriques de la simulation, sans les
        camions, plus les défauts ouverts et les lots bloqués)."""
        minuit = self.date(t).replace(hour=0, minute=0, second=0, microsecond=0)
        debut_jour = self.instant(minuit.timestamp())
        termines = self.instants("module", "Entrée stock PF", t)
        expedies = self.instants("module", EXPEDITION, t)
        du_jour = lambda instants: sum(1 for x in instants if x >= debut_jour)  # noqa: E731
        objectif = m.formater_nombre(self.objectif_a(t, modules_jour), 1)
        defauts = sum(1 for code in self.parcours
                      if (e := self.etat(code, t)) and e[2] == "defaut")
        bloques = sum(1 for lot in self.blocages if self.lot_bloque(lot, t))
        return {
            LIBELLES_INDICATEURS[0]: f"{du_jour(termines)} / {objectif}",
            LIBELLES_INDICATEURS[1]: f"{du_jour(expedies)} ({len(expedies)})",
            LIBELLES_INDICATEURS[2]: f"{self._en_cours('module', t)} / "
                                     f"{self._en_cours('pod', t)}",
            LIBELLES_INDICATEURS[3]: f"{defauts} / {bloques}",
            LIBELLES_INDICATEURS[4]: str(self._nombre_en_zone("lot", "Stock matières", t)),
            LIBELLES_INDICATEURS[5]: str(self._nombre_en_zone("module", "Stock produits finis",
                                                               t)),
        }

    def alertes_affichees(self, t: float, nombre: int) -> list[dict]:
        """Les `nombre` dernières alertes (défauts, blocages, refus, retards kanban) enregistrées
        par le serveur jusqu'à t, la plus récente d'abord, avec leur délai d'affichage."""
        passees = [e for e in self.alertes if self.instant(e["t"]) <= t][-nombre:]
        return [{**e, "t_jumeau": self.instant(e["t"]), "delai_s": delai_affichage(e)}
                for e in reversed(passees)]


def delai_affichage(evenement: dict) -> float | None:
    """Secondes entre le scan sur le téléphone et son enregistrement par le serveur (None si le
    téléphone n'a pas donné son heure ; 0 si son horloge avance)."""
    if evenement.get("t_client") is None:
        return None
    return max(0.0, evenement["t"] - evenement["t_client"])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. Comparaison avec la simulation (usine unique, implantation avec extension)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _premiers_passages(enregistrements, cle_id: str, cle_t: str, convertir) -> dict:
    """{(type, id): {étape: instant (min) du premier passage}} pour les gammes comparées."""
    passages: dict = {}
    for e in enregistrements:
        if e["type"] in GAMMES_COMPAREES and e["evenement"] in GAMMES_COMPAREES[e["type"]]:
            etapes = passages.setdefault((e["type"], e[cle_id]), {})
            etapes.setdefault(e["evenement"], convertir(e[cle_t]))
    return passages


def _durees_par_transition(passages: dict) -> dict[tuple[str, str, str], list[float]]:
    """{(gamme, de, vers): [durées en min]} entre étapes consécutives présentes."""
    durees: dict = {}
    for (type_piece, _), etapes in passages.items():
        gamme = GAMMES_COMPAREES[type_piece]
        for de, vers in zip(gamme, gamme[1:]):
            if de in etapes and vers in etapes:
                durees.setdefault((type_piece, de, vers), []).append(etapes[vers] - etapes[de])
    return durees


def durees_reelles(jumeau: Jumeau) -> dict[tuple[str, str, str], list[float]]:
    """Durées entre étapes mesurées par les scans acceptés, en minutes d'usine (× l'échelle de
    temps de la maquette)."""
    acceptes = [e for e in jumeau.evenements if e["resultat"] == "accepte"]
    echelle = H("echelle_temps_maquette")
    return _durees_par_transition(_premiers_passages(
        acceptes, "code", "t", lambda t: jumeau.instant(t) * echelle))


def durees_simulees(usine) -> dict[tuple[str, str, str], list[float]]:
    """Durées entre étapes dans la simulation (instants réels des événements, hors alertes)."""
    normaux = [e for e in usine.tracabilite.journal if not e["alerte"]]
    return _durees_par_transition(_premiers_passages(normaux, "id", "t", lambda t: t))


def qualifier_ecart(reel: float | None, simule: float | None) -> str:
    """« plus lent », « plus rapide » ou « conforme » selon le seuil d'écart relatif ;
    « — » sans les deux valeurs."""
    if reel is None or not simule:
        return "—"
    ecart = reel / simule - 1
    if ecart > H("seuil_ecart_jumeau"):
        return "plus lent"
    if ecart < -H("seuil_ecart_jumeau") / (1 + H("seuil_ecart_jumeau")):
        return "plus rapide"
    return "conforme"


def comparaison_etapes(jumeau: Jumeau, usine) -> list[dict]:
    """Une ligne par transition des gammes module et pod : durées moyennes réelle et simulée,
    nombre de mesures, rapport et écart qualifié."""
    reelles, simulees = durees_reelles(jumeau), durees_simulees(usine)
    lignes = []
    for type_piece, gamme in GAMMES_COMPAREES.items():
        for de, vers in zip(gamme, gamme[1:]):
            transition = (type_piece, de, vers)
            r, s = reelles.get(transition, []), simulees.get(transition, [])
            moy_r = statistics.mean(r) if r else None
            moy_s = statistics.mean(s) if s else None
            lignes.append({"gamme": type_piece, "de": de, "vers": vers, "n_reel": len(r),
                           "reel_min": moy_r, "n_sim": len(s), "sim_min": moy_s,
                           "rapport": moy_r / moy_s if r and moy_s else None,
                           "ecart": qualifier_ecart(moy_r, moy_s)})
    return lignes


def _moyenne(valeurs) -> float | None:
    """Moyenne, ou None sans valeur."""
    valeurs = [v for v in valeurs if v is not None]
    return statistics.mean(valeurs) if valeurs else None


def _trace_complete_reelle(jumeau: Jumeau, code: str) -> bool:
    """Tous les points de contrôle du module et de son pod ont-ils été scannés ?"""
    etapes = {(e["code"], e["evenement"]) for e in jumeau.evenements_de(code)
              if e["resultat"] == "accepte"}
    pods = [p["code"] for p in jumeau.pieces.values()
            if p.get("parent") == code and p.get("type") == "pod"]
    return (all((code, point) in etapes for point in sim.POINTS_MODULE)
            and all((pod, point) in etapes for pod in pods for point in sim.POINTS_POD))


def debit_reel(jumeau: Jumeau) -> float | None:
    """Modules entrés en stock PF par jour d'ouverture, sur la période observée (en temps
    d'usine) ; None avant le premier module terminé."""
    termines = jumeau.instants("module", "Entrée stock PF")
    duree = jumeau.duree() * H("echelle_temps_maquette")
    if not termines or duree <= 0:
        return None
    return len(termines) / (duree / sim.minutes_jour())


def indicateurs_reels(jumeau: Jumeau) -> dict:
    """Indicateurs globaux mesurés par les scans."""
    echelle = H("echelle_temps_maquette")
    of, pf = (dict(zip(*_codes_instants(jumeau, etape))) for etape in ("OF lancé",
                                                                         "Entrée stock PF"))
    expedies = list(_codes_instants(jumeau, EXPEDITION)[0])
    scans = [e for e in jumeau.evenements if e["resultat"] in ("accepte", "refuse")]
    defauts = sum(1 for e in jumeau.evenements if e["evenement"] == DEFAUT)
    return {
        "delai_fabrication_min": _moyenne((pf[c] - of[c]) * echelle for c in pf if c in of),
        "debit_jour": debit_reel(jumeau),
        "defauts_par_module": defauts / len(of) if of else None,
        "delai_affichage_s": _moyenne(delai_affichage(e) for e in scans),
        "pct_traces": (sum(_trace_complete_reelle(jumeau, c) for c in expedies) / len(expedies)
                       if expedies else None),
        "pct_refus": (sum(1 for e in scans if e["resultat"] == "refuse") / len(scans)
                      if scans else None),
        "modules_lances": len(of), "scans": len(scans),
    }


def _codes_instants(jumeau: Jumeau, etape: str) -> tuple[list[str], list[float]]:
    """(codes, instants) du premier scan accepté de l'étape pour chaque module."""
    vus: dict[str, float] = {}
    for e in jumeau.evenements:
        if e["type"] == "module" and e["evenement"] == etape and e["resultat"] == "accepte":
            vus.setdefault(e["code"], jumeau.instant(e["t"]))
    return list(vus), list(vus.values())


def indicateurs_simules(resultats: dict) -> dict:
    """Mêmes indicateurs, pour la simulation (délai d'affichage : hypothèse du QR code)."""
    defauts = sum(resultats["defauts"].values())
    bas, haut = H("delai_qr_min")
    return {
        "delai_fabrication_min": resultats["delai_fabrication_moyen_min"],
        "debit_jour": resultats["debit_regime_etabli"],
        "defauts_par_module": defauts / resultats["lances"] if resultats["lances"] else None,
        "delai_affichage_s": (bas + haut) / 2 * SECONDES_PAR_MINUTE,
        "pct_traces": resultats["pct_traces"], "pct_refus": None,
        "modules_lances": resultats["lances"], "scans": None,
    }


# Indicateurs comparés : (clé, libellé, unité)
INDICATEURS_COMPARES = (
    ("delai_fabrication_min", "Délai OF → stock PF (moyen)", "min"),
    ("debit_jour", "Modules terminés par jour", "modules/j"),
    ("defauts_par_module", "Défauts par module lancé", "—"),
    ("delai_affichage_s", "Délai d'affichage d'un scan", "s"),
    ("pct_traces", "Expédiés tracés de bout en bout", "%"),
    ("pct_refus", "Scans refusés", "%"),
)


def comparaison_indicateurs(jumeau: Jumeau, resultats: dict) -> list[dict]:
    """Une ligne par indicateur : valeur réelle, valeur simulée, unité, écart qualifié (le
    débit et la traçabilité sont meilleurs quand ils sont plus grands)."""
    reel, simule = indicateurs_reels(jumeau), indicateurs_simules(resultats)
    lignes = []
    for cle, libelle, unite in INDICATEURS_COMPARES:
        ecart = qualifier_ecart(reel[cle], simule[cle])
        if cle in ("debit_jour", "pct_traces", "defauts_par_module", "delai_affichage_s",
                   "pct_refus"):
            ecart = {"plus lent": "plus élevé", "plus rapide": "plus faible"}.get(ecart, ecart)
        lignes.append({"cle": cle, "libelle": libelle, "unite": unite, "reel": reel[cle],
                       "simule": simule[cle], "ecart": ecart})
    return lignes


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. Tests intégrés (py -3 avelis_flux/jumeau.py) : atelier de scan réel, en mémoire
# ═════════════════════════════════════════════════════════════════════════════════════════════

T_DEPART = 1_793_700_000.0  # instant fixe des tests (s depuis 1970)


def _base_de_test():
    """Base d'avelis_scan en mémoire, avec une horloge réglable : (base, horloge)."""
    sys.path.insert(0, str(DOSSIER_PROJET / "avelis_scan"))
    import base as base_scan  # noqa: E402 — module de l'application de scan, tests seulement
    horloge = [T_DEPART]
    return base_scan.Base(":memory:", horloge=lambda: horloge[0]), horloge


def _scanner(base, horloge, code: str, poste: str, pas_s: float = 120, **params) -> dict:
    """Avance l'horloge de `pas_s` puis valide l'étape suivante de la pièce au poste."""
    horloge[0] += pas_s
    return base.scanner(code, poste, "OP1", "etape", params, t_client=horloge[0] - 2)


GAMME_POD_TEST = ("kitting", "pod_1", "pod_2", "pod_3", "pod_4", "controle_pod")


def _atelier_de_test():
    """Un module complet expédié (MOD-…01), un second arrêté au poste 2 du pod sur un défaut
    (MOD-…02), un lot réceptionné et stocké : (base, horloge, codes du module 1, du module 2)."""
    base, horloge = _base_de_test()
    lot = base.creer_lot("FOUR-A", "Profilés", 40)
    _scanner(base, horloge, lot, "reception")
    _scanner(base, horloge, lot, "magasin")
    m1, m2 = (base.creer_module_complet("Lyon", avec_composants=False) for _ in range(2))
    _faire_module(base, horloge, m1)
    _scanner(base, horloge, m2[0], "bureau")
    for poste in GAMME_POD_TEST[:3]:
        _scanner(base, horloge, m2[1], poste)
    horloge[0] += 60
    base.scanner(m2[1], "pod_2", "OP1", "defaut", {"categorie": "Étanchéité",
                                                   "cause": "Machine"}, t_client=horloge[0])
    return base, horloge, m1, m2


def _faire_module(base, horloge, codes: list[str]) -> None:
    """Toute la gamme d'un module (module, pod, kit 2D, ossature), jusqu'à l'expédition."""
    module, pod, kit, ossature = codes
    _scanner(base, horloge, module, "bureau")
    _scanner(base, horloge, module, "kitting")
    for poste in GAMME_POD_TEST:
        _scanner(base, horloge, pod, poste)
    _scanner(base, horloge, kit, "kitting", 5)
    _scanner(base, horloge, kit, "ligne_2d")
    for poste in ("reception", "magasin", "kitting"):
        _scanner(base, horloge, ossature, poste)
    for composant in (pod, kit, ossature):
        _scanner(base, horloge, composant, "assemblage", 61)
    _scanner(base, horloge, module, "assemblage", 61)
    _scanner(base, horloge, module, "assemblage", 600)
    _scanner(base, horloge, module, "controle_final")
    _scanner(base, horloge, module, "stock_pf")
    _scanner(base, horloge, module, "expedition", destination="Lyon")


def test_parcours_et_positions():
    base, horloge, m1, m2 = _atelier_de_test()
    jumeau = Jumeau()
    assert jumeau.actualiser(base) == len(base.evenements(0, 10_000)) > 20
    fin = jumeau.duree()
    positions = jumeau.positions(fin)
    assert m1[0] not in positions and m1[1] not in positions  # expédié, pod intégré
    assert positions[m2[1]][2] == "pod" and jumeau.etat(m2[1], fin)[1:] == ("Ligne pods",
                                                                           "defaut")
    x, y, largeur, hauteur = jumeau.zones["Ligne pods"][:4]
    assert x <= positions[m2[1]][0] <= x + largeur and y <= positions[m2[1]][1] <= y + hauteur
    assert jumeau.signalees(fin) == {m2[1]}
    assert positions == jumeau.positions(fin)  # positions stables
    assert jumeau.positions(-1) == {}  # rien avant le premier scan
    t_pf = jumeau.instants("module", "Entrée stock PF")[0]
    assert jumeau.positions(t_pf)[m1[0]][2] == "module"  # le module était en stock PF


def test_changement_de_plan():
    base, horloge, m1, m2 = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    fin = jumeau.duree()
    avant, nombre = jumeau.positions(fin), len(jumeau.evenements)
    jumeau.choisir_plan(m.IMPLANTATION_OPTIMISEE)
    apres = jumeau.positions(fin)
    assert set(apres) == set(avant) and apres != avant  # mêmes pièces, autres positions
    x, y, largeur, hauteur = m.IMPLANTATIONS[m.IMPLANTATION_OPTIMISEE]["zones"]["Ligne pods"][:4]
    assert x <= apres[m2[1]][0] <= x + largeur and y <= apres[m2[1]][1] <= y + hauteur
    assert len(jumeau.evenements) == nombre and jumeau.signalees(fin) == {m2[1]}


def test_actualisation_incrementale_et_base_videe():
    base, horloge, m1, _ = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    total = len(jumeau.evenements)
    assert jumeau.actualiser(base) == 0  # rien de neuf
    _scanner(base, horloge, base.creer_module_complet(avec_composants=False)[0], "bureau")
    nouveaux = 5  # module, pod, kit 2D et ossature créés, puis OF lancé
    assert jumeau.actualiser(base) == nouveaux and len(jumeau.evenements) == total + nouveaux
    base.vider()
    horloge[0] += 10
    base.creer_lot("FOUR-B")
    assert jumeau.actualiser(base) == 1 and len(jumeau.evenements) == 1  # tout relu


def test_indicateurs_et_alertes():
    base, horloge, m1, m2 = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    valeurs = jumeau.valeurs(jumeau.duree(), modules_jour=8)
    assert set(valeurs) == set(LIBELLES_INDICATEURS)
    assert valeurs["Expédiés aujourd'hui (total)"].endswith("(1)")
    assert valeurs["En-cours : modules / pods"] == "1 / 1"
    assert valeurs["Défauts ouverts / lots bloqués"] == "1 / 0"
    assert valeurs["Stock matières (lots)"] == "1"
    alertes = jumeau.alertes_affichees(jumeau.duree(), 9)
    assert alertes[0]["evenement"] == DEFAUT and alertes[0]["code"] == m2[1]
    assert alertes[0]["delai_s"] == 0
    assert jumeau.alertes_affichees(-1, 9) == []


def test_objectif_a_l_heure():
    jumeau = Jumeau()
    jumeau.t0 = datetime.datetime(2026, 11, 4, H("heure_ouverture")).timestamp()
    assert jumeau.objectif_a(0, 10) == 0
    assert math.isclose(jumeau.objectif_a(sim.minutes_jour() / 2, 10), 5)
    assert jumeau.objectif_a(sim.minutes_jour() + 60, 10) == 10  # après la fermeture


def test_trace_parcourue():
    base, horloge, m1, m2 = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    trace = jumeau.trace_parcourue(m2[1], jumeau.duree())
    zones = [jumeau.repos(m2[1], z) for z in ("Kitting", "Ligne pods")]
    assert trace[0] == zones[0] and trace[-1] == zones[1] and len(trace) == 3
    assert jumeau.trace_parcourue(m2[1], -1) == []


def test_source_fichier_et_serveur():
    import tempfile
    import threading
    sys.path.insert(0, str(DOSSIER_PROJET / "avelis_scan"))
    import serveur as serveur_scan  # noqa: E402 — tests seulement
    with tempfile.TemporaryDirectory() as dossier:
        chemin = pathlib.Path(dossier) / "atelier.db"
        serveur, application = serveur_scan.demarrer(chemin, "127.0.0.1", 0, "127.0.0.1")
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()
        try:
            application.base.donnees_demo()
            adresse = f"http://127.0.0.1:{application.port}"
            par_api, par_fichier = Jumeau(), Jumeau()
            assert isinstance(ouvrir_source(adresse, chemin), SourceServeur)
            par_api.actualiser(SourceServeur(adresse))
            par_fichier.actualiser(SourceFichier(chemin))
            assert par_api.evenements == par_fichier.evenements and par_api.evenements
            assert set(par_api.pieces) == set(par_fichier.pieces)
            SourceServeur(adresse).envoyer_consigne("pod_2", "Consigne du jumeau")
            assert any(c["poste"] == "pod_2" and c["message"] == "Consigne du jumeau"
                       for c in application.base.consignes())
            SourceServeur(adresse).vider()
            assert par_api.actualiser(SourceServeur(adresse)) == 0 and not par_api.evenements
            application.base.creer_lot("FOUR-A")
            SourceFichier(chemin).vider()
            assert not SourceFichier(chemin).evenements() and not SourceFichier(chemin).pieces()
        finally:
            serveur.shutdown()
            serveur.server_close()
            application.base.cx.close()
        assert isinstance(ouvrir_source("http://127.0.0.1:9", chemin), SourceFichier)
    try:
        ouvrir_source("http://127.0.0.1:9", pathlib.Path(dossier) / "absente.db")
        raise AssertionError("source absente acceptée")
    except SourceIndisponible as erreur:
        assert "injoignable" in str(erreur) and "introuvable" in str(erreur)


def test_comparaison_avec_la_simulation():
    base, horloge, m1, m2 = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    usine = sim.Usine(1500, IMPLANTATION_JUMEAU, SCHEMA_JUMEAU, sim.QR, 2, 42).executer()
    lignes = comparaison_etapes(jumeau, usine)
    assert len(lignes) == len(sim.POINTS_MODULE) + len(sim.POINTS_POD) - 2
    assemblage = next(l for l in lignes if (l["de"], l["vers"]) == ("Début assemblage",
                                                                     "Fin assemblage"))
    assert assemblage["n_reel"] == 1 and math.isclose(assemblage["reel_min"], 10)
    assert assemblage["n_sim"] > 0 and assemblage["sim_min"] > 0
    assert assemblage["ecart"] == "plus rapide"
    indicateurs = {l["cle"]: l for l in comparaison_indicateurs(jumeau, usine.resultats())}
    assert indicateurs["pct_traces"]["reel"] == 1  # le module expédié est tracé de bout en bout
    assert math.isclose(indicateurs["defauts_par_module"]["reel"], 0.5)
    assert indicateurs["delai_affichage_s"]["reel"] > 0


def test_echelle_de_temps_et_ecarts():
    assert qualifier_ecart(None, 3) == qualifier_ecart(3, None) == "—"
    assert qualifier_ecart(10, 10) == "conforme" and qualifier_ecart(20, 10) == "plus lent"
    assert qualifier_ecart(5, 10) == "plus rapide"
    base, horloge, m1, _ = _atelier_de_test()
    jumeau = Jumeau()
    jumeau.actualiser(base)
    precedente = m.HYPOTHESES["echelle_temps_maquette"]
    try:
        m.HYPOTHESES["echelle_temps_maquette"] = (30, *precedente[1:])
        transition = ("module", "Début assemblage", "Fin assemblage")
        assert math.isclose(durees_reelles(jumeau)[transition][0], 300)
    finally:
        m.HYPOTHESES["echelle_temps_maquette"] = precedente


def executer_tests() -> int:
    """Exécute les tests intégrés ; renvoie le nombre d'échecs."""
    tests = [(nom, f) for nom, f in globals().items() if nom.startswith("test_") and callable(f)]
    echecs = 0
    for nom, test in tests:
        try:
            test()
            print(f"  ✓ {nom}")
        except Exception as erreur:  # noqa: BLE001 — on rapporte tous les échecs
            echecs += 1
            print(f"  ✗ {nom} : {type(erreur).__name__} {erreur}")
    print(f"{len(tests) - echecs}/{len(tests)} tests réussis")
    return echecs


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(1 if executer_tests() else 0)
