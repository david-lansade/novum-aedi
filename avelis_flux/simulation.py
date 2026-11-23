"""Simulation à événements discrets du site Avelis de Torcy et traçabilité (SPEC §3).

Contenu : moteur fait main (Env, Event, Process, Resource, Machine, Store), traçabilité selon la
technologie d'identification, classe Usine (flux physiques, journal des événements, résultats),
timelines d'animation et positions des objets à un instant donné.

Temps en minutes d'ouverture : 1 jour = 960 min (2 postes de 8 h), sans nuit. L'horloge affichée
commence à 06:00.
Tout l'aléa passe par des instances random.Random dérivées de la graine. Ce module n'importe
aucun module graphique.

Exécution directe (« py -3 avelis_flux/simulation.py ») : tests intégrés, puis résultats clés à
1 500 logements/an pour les trois technologies et les deux schémas, comparés aux ordres de grandeur attendus (§6).
"""

import bisect
import collections
import heapq
import itertools
import math
import random
import statistics
import sys
from collections import Counter

from modele import (
    CHANTIERS, H, IMPLANTATION_ACTUELLE, IMPLANTATION_PROPOSEE, IMPLANTATIONS,
    MINUTES_PAR_HEURE, NOMS_POSTES_POD, PLACE_PARKING_PL, ROUTE_PUBLIQUE, SCHEMAS, SITE_ACTUEL,
    TOLERANCE_ARRONDI, afficher_ligne, afficher_titre, aire_zone, bornes_environ, calcul_cadence,
    dimensionnement_site, distance_zones, distances_sous_ensemble, executer_tests,
    formater_nombre, formater_pourcentage, leve, minutes_ouverture_jour, part_demande,
    point_dans_polygone, satellite_le_plus_proche, verifier_choix,
)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. Moteur à événements discrets, fait main (SPEC §3.1)
# ═════════════════════════════════════════════════════════════════════════════════════════════

PRIORITE_URGENTE = 0  # démarrage des processus : avant les autres événements du même instant
PRIORITE_NORMALE = 1


class Event:
    """Événement déclenchable une seule fois ; à son traitement, ses callbacks sont appelés."""

    def __init__(self, env: "Env"):
        self.env = env
        self.callbacks: list = []
        self.declenche = False  # succeed() a été appelé : l'événement est planifié
        self.traite = False  # ses callbacks ont été exécutés
        self.valeur = None

    def succeed(self, valeur=None, delai: float = 0,
                priorite: int = PRIORITE_NORMALE) -> "Event":
        """Déclenche l'événement, qui sera traité dans `delai` minutes ; une seule fois."""
        if self.declenche:
            raise RuntimeError("événement déjà déclenché")
        self.declenche, self.valeur = True, valeur
        self.env.planifier(self, delai, priorite)
        return self


class Env:
    """Horloge et file d'événements : tas de (temps, priorité, compteur, événement)."""

    def __init__(self):
        self.maintenant = 0.0
        self._file: list = []
        self._compteur = itertools.count()

    def planifier(self, evenement: Event, delai: float, priorite: int) -> None:
        """Insère l'événement dans la file, à traiter dans `delai` minutes."""
        heapq.heappush(self._file,
                       (self.maintenant + delai, priorite, next(self._compteur), evenement))

    def evenement(self) -> Event:
        """Nouvel événement, à déclencher plus tard par succeed()."""
        return Event(self)

    def timeout(self, delai: float, valeur=None) -> Event:
        """Événement traité dans `delai` minutes."""
        if delai < 0:
            raise ValueError(f"délai négatif : {delai}")
        return Event(self).succeed(valeur, delai)

    def process(self, generateur) -> "Process":
        """Démarre un processus à partir d'un générateur d'événements."""
        return Process(self, generateur)

    def run(self, jusqua: float | None = None) -> None:
        """Traite les événements dans l'ordre jusqu'à épuisement de la file ou jusqu'à `jusqua`."""
        while self._file and (jusqua is None or self._file[0][0] <= jusqua):
            self.maintenant, _, _, evenement = heapq.heappop(self._file)
            evenement.traite = True
            callbacks, evenement.callbacks = evenement.callbacks, []
            for callback in callbacks:
                callback(evenement)
        if jusqua is not None:
            self.maintenant = max(self.maintenant, jusqua)


class Process(Event):
    """Processus : enveloppe un générateur qui produit (yield) des événements et reprend quand ils
    sont traités. C'est aussi un événement, déclenché à la fin du générateur avec sa valeur de
    retour."""

    def __init__(self, env: Env, generateur):
        super().__init__(env)
        self._generateur = generateur
        demarrage = Event(env)
        demarrage.callbacks.append(self._reprendre)
        demarrage.succeed(priorite=PRIORITE_URGENTE)

    def _reprendre(self, evenement: Event) -> None:
        """Relance le générateur jusqu'au prochain événement non encore traité."""
        valeur = evenement.valeur
        while True:
            try:
                attendu = self._generateur.send(valeur)
            except StopIteration as fin:
                self.succeed(fin.value)
                return
            if not isinstance(attendu, Event):
                raise TypeError(f"un processus doit produire des événements, pas {attendu!r}")
            if not attendu.traite:
                attendu.callbacks.append(self._reprendre)
                return
            valeur = attendu.valeur


class Resource:
    """Ressource de capacité finie, file d'attente FIFO. request() renvoie un événement dont la
    valeur est le numéro du poste attribué, à rendre par release(poste). Le temps occupé est
    cumulé pour calculer le taux d'utilisation."""

    def __init__(self, env: Env, capacite: int, nom: str = ""):
        if capacite < 1:
            raise ValueError(f"capacité invalide pour « {nom} » : {capacite}")
        self.env, self.capacite, self.nom = env, capacite, nom
        self._libres = list(range(capacite))
        self._file: collections.deque = collections.deque()
        self._debut_occupation: dict[int, float] = {}
        self.temps_occupe = 0.0

    def request(self) -> Event:
        """Demande un poste ; l'événement est déclenché quand un poste est attribué."""
        demande = Event(self.env)
        self._file.append(demande)
        self._servir()
        return demande

    def release(self, poste: int) -> None:
        """Rend le poste et sert la demande suivante de la file."""
        self.temps_occupe += self.env.maintenant - self._debut_occupation.pop(poste)
        self._libres.append(poste)
        self._libres.sort()
        self._servir()

    def _servir(self) -> None:
        """Attribue les postes libres aux demandes, dans l'ordre d'arrivée."""
        while self._libres and self._file:
            poste = self._libres.pop(0)
            self._debut_occupation[poste] = self.env.maintenant
            self._file.popleft().succeed(poste)

    @property
    def occupes(self) -> int:
        """Nombre de postes occupés."""
        return len(self._debut_occupation)

    @property
    def en_attente(self) -> int:
        """Nombre de demandes en file d'attente."""
        return len(self._file)

    def taux_utilisation(self, duree: float) -> float:
        """Temps occupé (occupations en cours comprises) / (capacité × durée)."""
        en_cours = sum(self.env.maintenant - debut for debut in self._debut_occupation.values())
        return (self.temps_occupe + en_cours) / (self.capacite * duree)


class Machine(Resource):
    """Ressource sujette à pannes, poste par poste : temps de marche avant panne exponentiel de
    moyenne MTBF, réparation exponentielle de moyenne MTTR (SPEC §7). Sans MTBF : jamais de
    panne."""

    def __init__(self, env: Env, capacite: int, nom: str, rng: random.Random,
                 mtbf: float | None = None, mttr: float | None = None):
        super().__init__(env, capacite, nom)
        self.rng, self.mtbf, self.mttr = rng, mtbf, mttr
        self.avant_panne = [self.tirer_avant_panne() for _ in range(capacite)]
        self.pannes = 0
        self.temps_panne = 0.0

    def tirer_avant_panne(self) -> float:
        """Temps de marche (min) avant la prochaine panne d'un poste."""
        return self.rng.expovariate(1 / self.mtbf) if self.mtbf else math.inf

    def tirer_reparation(self) -> float:
        """Durée (min) d'une réparation."""
        return self.rng.expovariate(1 / self.mttr)


def usiner(env: Env, machine: Machine, poste: int, duree: float, signaler_panne):
    """Occupe le poste pendant `duree` minutes de marche ; chaque panne suspend le travail le temps
    de la réparation. signaler_panne(reparation) est appelé au début de chaque panne."""
    restant = duree
    while restant > machine.avant_panne[poste]:
        marche = machine.avant_panne[poste]
        yield env.timeout(marche)
        restant -= marche
        reparation = machine.tirer_reparation()
        machine.pannes += 1
        machine.temps_panne += reparation
        signaler_panne(reparation)
        yield env.timeout(reparation)
        machine.avant_panne[poste] = machine.tirer_avant_panne()
    machine.avant_panne[poste] -= restant
    yield env.timeout(restant)


class Store:
    """Stock FIFO : get() attend qu'un objet soit disponible ; put() attend une place quand une
    capacité est fixée."""

    def __init__(self, env: Env, capacite: float = math.inf, nom: str = ""):
        self.env, self.capacite, self.nom = env, capacite, nom
        self.items: collections.deque = collections.deque()
        self._depots: collections.deque = collections.deque()  # (événement, objet)
        self._retraits: collections.deque = collections.deque()

    def put(self, objet) -> Event:
        """Dépose un objet ; l'événement est déclenché quand il est entré en stock."""
        depot = Event(self.env)
        self._depots.append((depot, objet))
        self._servir()
        return depot

    def get(self) -> Event:
        """Retire le plus ancien objet ; la valeur de l'événement est l'objet retiré."""
        retrait = Event(self.env)
        self._retraits.append(retrait)
        self._servir()
        return retrait

    def _servir(self) -> None:
        """Exécute les dépôts et retraits possibles, dans l'ordre d'arrivée."""
        progres = True
        while progres:
            progres = False
            if self._depots and len(self.items) < self.capacite:
                depot, objet = self._depots.popleft()
                self.items.append(objet)
                depot.succeed()
                progres = True
            if self._retraits and self.items:
                self._retraits.popleft().succeed(self.items.popleft())
                progres = True


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. Temps : 1 jour = 960 min d'ouverture sans nuit, horloge affichée à partir de 06:00
# ═════════════════════════════════════════════════════════════════════════════════════════════

def minutes_jour() -> float:
    """Minutes d'ouverture par jour (960)."""
    return minutes_ouverture_jour()


def minutes_equipe() -> float:
    """Durée d'une équipe (480 min)."""
    return H("heures_par_equipe") * MINUTES_PAR_HEURE


def jour_de(t: float) -> int:
    """Numéro du jour (1, 2, …) de l'instant t."""
    return int(t // minutes_jour()) + 1


def fin_equipe(t: float) -> float:
    """Instant de fin de l'équipe en cours à l'instant t."""
    duree = minutes_equipe()
    return (math.floor(t / duree) + 1) * duree


def _jour_heure_minute(t: float) -> tuple[int, int, int]:
    """(jour, heure, minute) affichés pour l'instant t."""
    jour, minute = divmod(math.floor(t), minutes_jour())
    heure, minute = divmod(H("heure_ouverture") * MINUTES_PAR_HEURE + minute, MINUTES_PAR_HEURE)
    return int(jour) + 1, int(heure), int(minute)


def horloge(t: float) -> str:
    """Horloge du tableau de pilotage : « Jour N · HH:MM »."""
    jour, heure, minute = _jour_heure_minute(t)
    return f"Jour {jour} · {heure:02d}:{minute:02d}"


def horloge_courte(t: float) -> str:
    """Horodatage compact : « Jn HH:MM »."""
    jour, heure, minute = _jour_heure_minute(t)
    return f"J{jour} {heure:02d}:{minute:02d}"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. Traçabilité (SPEC §3.3)
# ═════════════════════════════════════════════════════════════════════════════════════════════

# Technologie : (clé du taux de lecture, clé du délai d'affichage) dans HYPOTHESES
TECHNOLOGIES = {
    "RFID + IoT (automatique)": ("taux_lecture_rfid", "delai_rfid_s"),
    "QR code (scan manuel)": ("taux_lecture_qr", "delai_qr_min"),
    "Papier / saisie en fin de poste": ("taux_lecture_papier", "delai_papier_min"),
}
RFID, QR, PAPIER = TECHNOLOGIES
SECONDES_PAR_MINUTE = 60

POINTS_MODULE = ("OF lancé", "Kitting", "Panneaux 2D terminés", "Début assemblage",
                 "Fin assemblage", "Contrôle final OK", "Entrée stock PF", "Expédié")
POINTS_POD = ("Kitting",
              *(f"Poste {numero} {nom}" for numero, nom in enumerate(NOMS_POSTES_POD, 1)),
              "Contrôle pod OK", "Intégré au module")
TYPES_OBJETS = ("pod", "kit 2D", "lot", "module", "camion")


def cause_retrouvee(enregistrements: list[dict]) -> bool:
    """Vrai si assez d'événements de l'objet ont été lus pour remonter à la cause d'un défaut
    (SPEC §3.2 : au moins 5) ; les alertes ne comptent pas."""
    lus = sum(1 for e in enregistrements if e["lu"] and not e["alerte"])
    return lus >= H("evenements_lus_cause")


class Tracabilite:
    """Journal des événements. Chaque enregistrement est lu ou non selon le taux de lecture de la
    technologie, puis affiché après son délai ; un événement non lu n'est jamais affiché. Les
    alertes sont toujours lues, avec le délai de la technologie."""

    def __init__(self, techno: str, rng: random.Random):
        verifier_choix(techno, tuple(TECHNOLOGIES), "technologie")
        self.techno, self.rng = techno, rng
        self.journal: list[dict] = []
        self.par_objet: dict[str, list[dict]] = {}

    def instant_affichage(self, t: float) -> float:
        """Instant où un événement survenu en t apparaît dans l'outil de pilotage."""
        bas, haut = H(TECHNOLOGIES[self.techno][1])
        if self.techno == RFID:
            return t + self.rng.uniform(bas, haut) / SECONDES_PAR_MINUTE
        if self.techno == QR:
            return t + self.rng.uniform(bas, haut)
        return fin_equipe(t) + self.rng.uniform(bas, haut)

    def enregistrer(self, t: float, id_objet: str, type_objet: str, evenement: str, zone: str,
                    lot: str | None = None, alerte: bool = False, message: str = "") -> dict:
        """Ajoute un enregistrement (t, id, type, evenement, zone, lot, lu, t_affichage, alerte,
        message) au journal et le renvoie."""
        lu = self.rng.random() < H(TECHNOLOGIES[self.techno][0]) or alerte
        enregistrement = {
            "t": t, "id": id_objet, "type": type_objet, "evenement": evenement, "zone": zone,
            "lot": lot, "lu": lu, "t_affichage": self.instant_affichage(t) if lu else None,
            "alerte": alerte, "message": message,
        }
        self.journal.append(enregistrement)
        self.par_objet.setdefault(id_objet, []).append(enregistrement)
        return enregistrement


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. Chemins dessinés (animation)
# ═════════════════════════════════════════════════════════════════════════════════════════════

EPSILON_DISTANCE_M = 1e-9


def longueur_chemin(chemin: list) -> float:
    """Longueur (m) d'un chemin polygonal."""
    return sum(math.dist(a, b) for a, b in zip(chemin, chemin[1:]))


def portion_de_chemin(chemin: list, fraction: float) -> list:
    """Début du chemin jusqu'à `fraction` (0 à 1) de sa longueur, point final interpolé compris."""
    reste = max(0.0, min(1.0, fraction)) * longueur_chemin(chemin)
    points = [chemin[0]]
    for a, b in zip(chemin, chemin[1:]):
        troncon = math.dist(a, b)
        if reste <= troncon:
            k = reste / troncon if troncon > 0 else 0.0
            points.append((a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1])))
            return points
        points.append(b)
        reste -= troncon
    return points


def point_sur_chemin(chemin: list, fraction: float) -> tuple[float, float]:
    """Point situé à `fraction` (0 à 1) de la longueur du chemin."""
    return portion_de_chemin(chemin, fraction)[-1]


def _projeter(polyligne: list, point: tuple) -> tuple[float, tuple[float, float]]:
    """Abscisse curviligne et position du point de la polyligne le plus proche de `point`."""
    meilleur, abscisse = None, 0.0
    for a, b in zip(polyligne, polyligne[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        longueur = math.hypot(dx, dy)
        k = 0.0
        if longueur > 0:
            produit = (point[0] - a[0]) * dx + (point[1] - a[1]) * dy
            k = max(0.0, min(1.0, produit / longueur ** 2))
        proche = (a[0] + k * dx, a[1] + k * dy)
        ecart = math.dist(point, proche)
        if meilleur is None or ecart < meilleur[0]:
            meilleur = (ecart, abscisse + k * longueur, proche)
        abscisse += longueur
    return meilleur[1], meilleur[2]


def chemin_le_long(polyligne: list, depart: tuple, arrivee: tuple) -> list:
    """Chemin de `depart` à `arrivee` qui rejoint la polyligne et la suit entre leurs
    projections (camions sur la route publique et la voirie)."""
    s_depart, p_depart = _projeter(polyligne, depart)
    s_arrivee, p_arrivee = _projeter(polyligne, arrivee)
    abscisses = list(itertools.accumulate(
        (math.dist(a, b) for a, b in zip(polyligne, polyligne[1:])), initial=0.0))
    bas, haut = sorted((s_depart, s_arrivee))
    sommets = [tuple(p) for p, s in zip(polyligne, abscisses) if bas < s < haut]
    if s_depart > s_arrivee:
        sommets.reverse()
    chemin = [tuple(depart), p_depart, *sommets, p_arrivee, tuple(arrivee)]
    return [p for i, p in enumerate(chemin)
            if i == 0 or math.dist(p, chemin[i - 1]) > EPSILON_DISTANCE_M]


def place_parking_pl(zone: tuple, tirage: random.Random) -> tuple[float, float]:
    """Centre d'une place du parking PL tirée au hasard (rangées nord-sud de PLACE_PARKING_PL,
    centrées dans la zone)."""
    x, y, largeur, hauteur = zone[:4]
    l, p = PLACE_PARKING_PL
    colonnes, rangees = int(largeur // l), max(1, int(hauteur // p))
    x0, y0 = x + (largeur - colonnes * l) / 2, y + (hauteur - rangees * p) / 2
    return (x0 + (tirage.randrange(colonnes) + 0.5) * l,
            y0 + (tirage.randrange(rangees) + 0.5) * p)


def _quai_de_reception(plan: dict, point: tuple) -> bool:
    """Vrai si le point est l'un des quais de réception (sur leur rangée, depuis le premier)."""
    (x0, y0), (dx, dy) = plan["quai_reception"], plan["pas_quai_reception"]
    u, v = point[0] - x0, point[1] - y0
    return abs(u * dy - v * dx) < EPSILON_DISTANCE_M and u * dx + v * dy >= 0


def _bretelle_du_point(plan: dict, point: tuple) -> list | None:
    """Bretelle du point : la première pour un quai de réception (elle les dessert), sinon la
    plus proche, si elle l'est plus que la voirie ; None : le point se rattache à la voirie."""
    if plan.get("bretelles") and _quai_de_reception(plan, point):
        return plan["bretelles"][0]

    def ecart(ligne: list) -> float:
        return math.dist(point, _projeter(ligne, point)[1])
    proche = min(plan.get("bretelles", []), key=ecart, default=None)
    return proche if proche is not None and ecart(proche) < ecart(plan["voirie"]) else None


def chemin_sur_site(plan: dict, depart: tuple, arrivee: tuple) -> list:
    """Chemin d'un camion sur le site : le long de la voirie, et d'une bretelle (raccordée à la
    voirie par son premier point) pour un point plus proche d'elle que de la voirie."""
    b_depart, b_arrivee = _bretelle_du_point(plan, depart), _bretelle_du_point(plan, arrivee)
    if b_depart is not None and b_depart is b_arrivee:
        return chemin_le_long(b_depart, depart, arrivee)
    debut = tuple(depart) if b_depart is None else tuple(b_depart[0])
    fin = tuple(arrivee) if b_arrivee is None else tuple(b_arrivee[0])
    chemin = chemin_le_long(plan["voirie"], debut, fin)
    if b_depart is not None:
        chemin = chemin_le_long(b_depart, depart, debut) + chemin[1:]
    if b_arrivee is not None:
        chemin += chemin_le_long(b_arrivee, fin, arrivee)[1:]
    return chemin


def boucle_de_retournement(plan: dict) -> list:
    """Demi-tour sur l'aire de retournement : trois quarts de cercle dans le sens trigonométrique,
    tangent à la voirie au pied de l'aire (point de la voirie le plus proche de son centre), où
    il commence ; on en repart vers la voirie, qu'on rejoint en tournant à droite."""
    pied = _projeter(plan["voirie"], plan["retournement"])[1]
    rayon = H("rayon_retournement") - H("largeur_voirie") / 2
    ecart = math.dist(pied, plan["retournement"]) or 1.0
    nx, ny = ((plan["retournement"][0] - pied[0]) / ecart,
              (plan["retournement"][1] - pied[1]) / ecart)
    cx, cy, depart = pied[0] + nx * rayon, pied[1] + ny * rayon, math.atan2(-ny, -nx)
    angles = [depart + k * math.pi / 8 for k in range(13)]
    return [tuple(pied)] + [(cx + rayon * math.cos(a), cy + rayon * math.sin(a))
                            for a in angles[1:]]


def chemin_vers_quai(plan: dict, depart: tuple, quai: tuple, en_long: bool = False) -> list:
    """Chemin d'un camion jusqu'à son quai ; un quai en long venu du côté du portail passe par
    l'aire de retournement, pour s'y garer dans le sens du départ."""
    voirie = plan["voirie"]
    if not en_long or _projeter(voirie, depart)[0] <= _projeter(voirie, quai)[0]:
        return chemin_sur_site(plan, depart, quai)
    boucle = boucle_de_retournement(plan)
    return (chemin_sur_site(plan, depart, boucle[0]) + boucle[1:-1]
            + chemin_sur_site(plan, boucle[-1], quai))


def route_d_arrivee(plan: dict) -> list:
    """Route publique depuis le sud jusqu'au début de l'accès, puis l'accès jusqu'au portail."""
    acces = [tuple(p) for p in plan["acces"]]
    return chemin_le_long(ROUTE_PUBLIQUE, ROUTE_PUBLIQUE[0], acces[0]) + acces[1:]


def route_de_depart(plan: dict) -> list:
    """Du portail, l'accès en sens inverse, puis la route publique vers le nord."""
    acces = [tuple(p) for p in reversed(plan["acces"])]
    return acces[:-1] + chemin_le_long(ROUTE_PUBLIQUE, acces[-1], ROUTE_PUBLIQUE[-1])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 5. Usine simulée : flux physiques (SPEC §3.2), résultats (§3.4), animation (§3.5)
# ═════════════════════════════════════════════════════════════════════════════════════════════

POSTE_SENSIBLE_AU_LOT = "Parois + étanchéité"  # un lot non conforme y provoque des défauts
DISPERSION_REPOS = 0.7  # part de la largeur et de la hauteur d'une zone où se posent les objets
ECART_MODULE_CAMION = 1.0  # m entre le flanc d'un camion garé en long et les modules posés à côté

# Alertes comptées dans « ruptures, attentes et blocages » (SPEC §3.4), avec leur famille
NATURES_FLUX = {
    "Rupture matière": "rupture",
    "Attente quai": "attente",
    "Attente composant": "attente",
    "Attente produit fini": "attente",
    "Blocage stock PF": "blocage",
}
NATURES_RETARD = ("Retard fournisseur", "Retard transporteur")


def _centile(valeurs_triees: list[float], q: float) -> float | None:
    """Centile par la méthode du rang le plus proche ; None si la liste est vide."""
    if not valeurs_triees:
        return None
    return valeurs_triees[max(1, math.ceil(q * len(valeurs_triees))) - 1]


def _moyenne(valeurs) -> float | None:
    """Moyenne, ou None s'il n'y a aucune valeur."""
    valeurs = list(valeurs)
    return statistics.fmean(valeurs) if valeurs else None


def _ratio(numerateur: float, denominateur: float) -> float | None:
    """Rapport protégé : None si le dénominateur est nul."""
    return numerateur / denominateur if denominateur else None


class Usine:
    """Usine simulée : Usine(cadence, implantation, schema, techno, jours, graine).executer().

    Le flux physique tire son aléa de self.rng = random.Random(graine) ; les lectures de
    traçabilité ont leur propre générateur dérivé de la même graine. À graine égale, les trois
    technologies voient donc exactement le même flux physique."""

    def __init__(self, cadence: float, implantation: str, schema: str, techno: str,
                 jours: int = 10, graine: int = 42):
        verifier_choix(implantation, tuple(IMPLANTATIONS), "implantation")
        verifier_choix(schema, SCHEMAS, "schéma")
        verifier_choix(techno, tuple(TECHNOLOGIES), "technologie")
        if not (isinstance(jours, int) and jours >= 1):
            raise ValueError(f"nombre de jours simulés invalide : {jours!r} (entier ≥ 1)")
        self.cadence, self.implantation, self.schema = cadence, implantation, schema
        self.techno, self.jours, self.graine = techno, jours, graine
        self.calcul = calcul_cadence(cadence)
        self.dimension = dimensionnement_site(cadence, schema)
        self.plan = IMPLANTATIONS[implantation]
        self.zones = self.plan["zones"]
        self.duree = jours * minutes_jour()
        self.rng = random.Random(graine)
        self.tracabilite = Tracabilite(techno, random.Random(f"{graine}/lecture"))
        self.env = Env()
        self.objets: dict[str, dict] = {}
        self.trajets: list[dict] = []
        self.echantillons: list[dict] = []
        self._initialiser_etat()
        self._creer_ressources()

    # ── Mise en place ───────────────────────────────────────────────────────────────────────

    def _initialiser_etat(self) -> None:
        """Compteurs et structures internes."""
        self._numeros: Counter = Counter()
        self._fraction_kits = 0.0
        self._termines = 0
        self._reservations_pf = 0
        self._en_expedition = 0
        self._arrivees: dict[str, dict] = {}
        self._timelines: dict[str, tuple[str, list[dict]]] = {}
        self._index_t0: dict[str, list[float]] = {}
        self._repos_cache: dict[tuple, tuple[float, float]] = {}
        self._executee = False

    def _creer_ressources(self) -> None:
        """Ressources dimensionnées par calcul_cadence et dimensionnement_site (SPEC §3.2)."""
        env, ressources = self.env, self.calcul["ressources"]
        self.agv = Resource(env, H("nombre_agv"), "AGV")
        self.porteurs = Resource(env, H("nombre_porteurs"), "Porteurs")
        self.kitting = Resource(env, ressources["postes_kitting"]["nombre"], "Postes de kitting")
        self.ligne_2d = Machine(env, ressources["lignes_2d"]["nombre"], "Ligne 2D", self.rng,
                                H("mtbf_ligne_2d"), H("mttr_ligne_2d"))
        lignes_pods = ressources["lignes_pods"]["nombre"]
        self.postes_pod = [self._poste_pod(numero, nom, lignes_pods)
                           for numero, nom in enumerate(NOMS_POSTES_POD, 1)]
        if self.schema == "unique":
            self.assemblage = Resource(env, ressources["baies_assemblage"]["nombre"],
                                       "Baies d'assemblage 3D")
        else:
            self.assemblage = Resource(env, H("postes_consolidation"), "Postes de consolidation")
        self.controle = Resource(env, H("postes_controle_final"), "Contrôle final")
        self._creer_quais()
        self.stock_matieres = Store(env, nom="Stock matières")
        self.stock_pf = Store(env, nom="Stock produits finis")
        self.capacite_pf = self._capacite_stock_pf()

    def _poste_pod(self, numero: int, nom: str, lignes: int) -> Machine:
        """Poste de la ligne pods ; seul le poste Parois tombe en panne (SPEC §3.2)."""
        pannes = ((H("mtbf_poste_parois"), H("mttr_poste_parois"))
                  if nom == POSTE_SENSIBLE_AU_LOT else (None, None))
        return Machine(self.env, lignes, f"Poste {numero} {nom}", self.rng, *pannes)

    def _creer_quais(self) -> None:
        """Quais de réception et d'expédition ; un seul jeu de quais si l'Expédition partage la
        zone de la Réception (implantation actuelle)."""
        if self.plan["zones_partagees"].get("Expédition") == "Réception":
            self.quais_reception = Resource(self.env, self.dimension["quais_reception"],
                                            "Quais partagés (réception + expédition)")
            self.quais_expedition = self.quais_reception
        else:
            self.quais_reception = Resource(self.env, self.dimension["quais_reception"],
                                            "Quais de réception")
            self.quais_expedition = Resource(self.env, self.dimension["quais_expedition"],
                                             "Quais d'expédition")

    def _capacite_stock_pf(self) -> int:
        """Places du stock PF : surface de la zone / (emprise d'un module ou d'un kit × coef de
        circulation), SPEC §3.2."""
        if self.schema == "unique":
            largeur, longueur, _ = H("dim_module")
            emprise = largeur * longueur
        else:
            emprise = H("m2_kit")
        surface = aire_zone(self.zones["Stock produits finis"])
        return math.floor(surface / (emprise * H("coef_circulation")) + TOLERANCE_ARRONDI)

    def executer(self) -> "Usine":
        """Simule les `jours` jours (une seule fois) et renvoie l'usine."""
        if not self._executee:
            self._constituer_stock_initial()
            for processus in (self._lancer_ordres(), self._arrivees_fournisseurs(),
                              self._departs_expedition(), self._echantillonner()):
                self.env.process(processus)
            self.env.run(jusqua=self.duree)
            self._animer_camions_en_attente()
            self._finaliser_timelines()
            self._executee = True
        return self

    # ── Outils : tirages, numérotation, journal ─────────────────────────────────────────────

    def _triangulaire(self, cle: str) -> float:
        """Tirage triangulaire sur l'intervalle de l'hypothèse, mode au milieu (SPEC §7)."""
        bas, haut = H(cle)
        return self.rng.triangular(bas, haut)

    def _uniforme(self, cle: str) -> float:
        """Tirage uniforme sur l'intervalle de l'hypothèse."""
        bas, haut = H(cle)
        return self.rng.uniform(bas, haut)

    def _retard(self, cle_taux: str, cle_duree: str) -> float:
        """Retard (min) avec la probabilité donnée, sinon 0."""
        return self._uniforme(cle_duree) if self.rng.random() < H(cle_taux) else 0.0

    def _numero(self, famille: str) -> int:
        """Numéro suivant dans une famille d'identifiants."""
        self._numeros[famille] += 1
        return self._numeros[famille]

    def _noter(self, id_objet: str, type_objet: str, evenement: str, zone: str,
               lot: str | None = None, message: str = "") -> dict:
        """Enregistre un événement de traçabilité à l'instant courant."""
        return self.tracabilite.enregistrer(self.env.maintenant, id_objet, type_objet,
                                            evenement, zone, lot, False, message)

    def _alerter(self, nature: str, id_objet: str, type_objet: str, zone: str, message: str,
                 lot: str | None = None) -> dict:
        """Enregistre une alerte (toujours lue) à l'instant courant."""
        return self.tracabilite.enregistrer(self.env.maintenant, id_objet, type_objet,
                                            nature, zone, lot, True, message)

    def _surveiller(self, attendu: Event, seuil: float, nature: str, id_objet: str,
                    type_objet: str, zone: str, message: str):
        """Veille : lève l'alerte `nature` si `attendu` n'est pas déclenché au bout de `seuil`."""
        yield self.env.timeout(seuil)
        if not attendu.declenche:
            self._alerter(nature, id_objet, type_objet, zone, message)

    # ── Transports internes ─────────────────────────────────────────────────────────────────

    def _transporter(self, id_objet: str, type_objet: str, de: str, vers: str,
                     flotte: Resource, vitesse: float, manutention: float, animer: bool = True):
        """Durée = manutention + d/v + manutention (SPEC §3.2), trajet journalisé, puis retour à
        vide du véhicule. Renvoie la distance rectilinéaire parcourue (m)."""
        vehicule = yield flotte.request()
        distance = distance_zones(self.zones[de], self.zones[vers])
        trajet, t0 = distance / vitesse, self.env.maintenant
        yield self.env.timeout(manutention + trajet + manutention)
        self.trajets.append({"id": id_objet, "type": type_objet, "de": de, "vers": vers,
                             "t0": t0, "t1": self.env.maintenant, "distance": distance,
                             "vehicule": flotte.nom})
        if animer:
            debut, fin = t0 + manutention, t0 + manutention + trajet
            self._deplacer(id_objet, type_objet, debut, fin,
                           self._chemin_objet(id_objet, de, vers))
            self._placer(id_objet, type_objet, vers, fin)
        self.env.process(self._retour_a_vide(flotte, vehicule, trajet))
        return distance

    def _retour_a_vide(self, flotte: Resource, vehicule: int, duree: float):
        """Le véhicule revient à vide avant d'être de nouveau disponible."""
        yield self.env.timeout(duree)
        flotte.release(vehicule)

    def _par_agv(self, objet: dict, de: str, vers: str):
        """Transport d'un kit 2D ou d'un pod en AGV ; distance cumulée sur l'objet."""
        distance = yield from self._transporter(objet["id"], objet["type"], de, vers, self.agv,
                                                H("vitesse_agv"), H("manutention_agv_min"))
        objet["distance"] += distance

    def _par_porteur(self, module: dict, de: str, vers: str):
        """Transport d'un module par porteur ; distance cumulée sur le module."""
        distance = yield from self._transporter(module["id"], "module", de, vers, self.porteurs,
                                                H("vitesse_porteur"),
                                                H("manutention_porteur_min"))
        module["distance"] += distance

    # ── Flux entrant : lots, camions fournisseurs, stock matières ──────────────────────────

    def _kits_par_camion(self) -> int:
        """Kits apportés par un camion : charge utile / (t par logement / modules par logement),
        soit 1,4, les fractions étant reportées d'un camion au suivant."""
        self._fraction_kits += H("charge_utile_camion") / (
            H("tonnes_par_logement") / H("modules_par_logement"))
        kits = math.floor(self._fraction_kits + TOLERANCE_ARRONDI)
        self._fraction_kits -= kits
        return kits

    def _nouveau_lot(self) -> dict:
        """Lot LOT-xxxx de son camion CAM-xxxx : fournisseur tiré, conformité tirée."""
        numero = self._numero("lot")
        indice = self.rng.randrange(H("nombre_fournisseurs"))
        lot = {"id": f"LOT-{numero:04d}", "type": "lot", "camion": f"CAM-{numero:04d}",
               "fournisseur": f"FOUR-{chr(ord('A') + indice)}",
               "non_conforme": self.rng.random() < H("taux_lots_non_conformes"),
               "kits": 0, "kits_restants": 0, "t_arrivee": None, "distance_reception": 0.0}
        self.objets[lot["id"]] = lot
        return lot

    def _nouveau_camion(self, id_camion: str, role: str, **attributs) -> dict:
        """Camion fournisseur ou d'expédition ; sur site de t_arrivee (portail franchi en entrant)
        à t_sortie (portail franchi en sortant)."""
        camion = {"id": id_camion, "type": "camion", "role": role, "t_arrivee": None,
                  "t_sortie": None, **attributs}
        self.objets[id_camion] = camion
        return camion

    def _stocker_kits(self, lot: dict, kits: int) -> None:
        """Ajoute au stock matières les kits du lot."""
        lot["kits"] = lot["kits_restants"] = kits
        for _ in range(kits):
            self.stock_matieres.put(lot["id"])

    def _constituer_stock_initial(self) -> None:
        """Stock matières initial de 1,5 jour de consommation, en lots reçus avant le jour 1."""
        besoin = round(H("stock_initial_jours") * self.calcul["modules_jour"])
        while len(self.stock_matieres.items) < besoin:
            lot = self._nouveau_lot()
            self._nouveau_camion(lot["camion"], "Fournisseur", lot=lot["id"],
                                 fournisseur=lot["fournisseur"], stock_initial=True)
            lot["distance_reception"] = distance_zones(self.zones["Réception"],
                                                       self.zones["Stock matières"])
            self._stocker_kits(lot, self._kits_par_camion())
            self._placer(lot["id"], "lot", "Stock matières", 0.0)

    def _arrivees_fournisseurs(self):
        """Arrivées régulières : intervalle = 900 / camions entrants par jour."""
        intervalle = minutes_jour() / self.dimension["camions_entrants_jour"]
        while True:
            self.env.process(self._camion_fournisseur())
            yield self.env.timeout(intervalle)

    def _camion_fournisseur(self):
        """Retard éventuel, attente de quai, déchargement, puis rangement du lot."""
        lot = self._nouveau_lot()
        camion = self._nouveau_camion(lot["camion"], "Fournisseur", lot=lot["id"],
                                      fournisseur=lot["fournisseur"], stock_initial=False)
        retard = self._retard("taux_retard_fournisseur", "retard_fournisseur_min")
        if retard:
            self._alerter("Retard fournisseur", camion["id"], "camion", "Réception",
                          f"{camion['id']} ({lot['fournisseur']}, {lot['id']}) en retard de "
                          f"{retard:.0f} min", lot=lot["id"])
            yield self.env.timeout(retard)
        camion["t_arrivee"] = lot["t_arrivee"] = self.env.maintenant
        self._noter(camion["id"], "camion", "Arrivée sur site", "Parking PL", lot=lot["id"])
        poste, position = yield from self._venir_a_quai(camion, self.quais_reception,
                                                        "Réception", self.plan["quai_reception"])
        yield self.env.timeout(self._triangulaire("dechargement_min"))
        self.quais_reception.release(poste)
        self._repartir(camion["id"], position)
        etat = "non conforme" if lot["non_conforme"] else "conforme"
        self._noter(lot["id"], "lot", "Réception", "Réception", lot=lot["id"],
                    message=f"{camion['id']}, {lot['fournisseur']}, lot {etat}")
        self._placer(lot["id"], "lot", "Réception")
        self.env.process(self._ranger_lot(lot))

    def _ranger_lot(self, lot: dict):
        """Transfert du lot en AGV vers le stock matières, puis ajout de ses kits."""
        lot["distance_reception"] = yield from self._transporter(
            lot["id"], "lot", "Réception", "Stock matières", self.agv, H("vitesse_agv"),
            H("manutention_agv_min"))
        self._stocker_kits(lot, self._kits_par_camion())
        self._noter(lot["id"], "lot", "Entrée stock matières", "Stock matières", lot=lot["id"],
                    message=f"{lot['kits']} kit(s)")

    # ── Fabrication d'un module ─────────────────────────────────────────────────────────────

    def _lancer_ordres(self):
        """Un ordre de fabrication MOD-29-xxxxx toutes les 900 / modules par jour minutes."""
        intervalle = minutes_jour() / self.calcul["modules_jour"]
        while True:
            self.env.process(self._fabriquer_module())
            yield self.env.timeout(intervalle)

    def _fabriquer_module(self):
        """Parcours complet d'un module, de l'OF à l'entrée en stock de produits finis."""
        module = self._nouveau_module()
        yield from self._kitter(module)
        yield from self._assembler(module)
        yield from self._controler(module)
        yield from self._entrer_stock_pf(module)

    def _nouveau_module(self) -> dict:
        """Ordre de fabrication : le module a besoin d'un pod avec la probabilité pods/modules
        (dans les deux schémas, les pods sont fabriqués à Torcy)."""
        numero = self._numero("module")
        besoin_pod = self.rng.random() < H("pods_par_logement") / H("modules_par_logement")
        module = {"id": f"MOD-29-{numero:05d}", "type": "module", "numero": numero,
                  "besoin_pod": besoin_pod, "pod": None, "k2d": None, "lot": None,
                  "t_of": self.env.maintenant, "t_debut_assemblage": None, "t_stock_pf": None,
                  "t_expedie": None, "cause": None, "cause_retrouvee": None, "camion": None,
                  "destination": None, "distance": 0.0, "distance_matiere": 0.0}
        self.objets[module["id"]] = module
        self._noter(module["id"], "module", "OF lancé", "Bureaux / pilotage",
                    message="avec pod" if besoin_pod else "sans pod")
        return module

    def _kitter(self, module: dict):
        """Kitting : rupture signalée si le stock matières est vide, apport du kit en AGV,
        préparation, puis lancement du kit 2D et du pod (SPEC §3.2)."""
        poste = yield self.kitting.request()
        if not self.stock_matieres.items:
            self._alerter("Rupture matière", module["id"], "module", "Stock matières",
                          f"{module['id']} : stock matières vide, kitting en attente")
        lot = self.objets[(yield self.stock_matieres.get())]
        module["lot"] = lot["id"]
        lot["kits_restants"] -= 1
        dernier_kit = lot["kits_restants"] == 0
        module["distance_matiere"] = yield from self._transporter(
            lot["id"], "lot", "Stock matières", "Kitting", self.agv, H("vitesse_agv"),
            H("manutention_agv_min"), animer=dernier_kit)
        yield self.env.timeout(self._triangulaire("kitting_min"))
        self.kitting.release(poste)
        if dernier_kit:
            self._masquer(lot["id"])
        self._noter(module["id"], "module", "Kitting", "Kitting", lot=lot["id"])
        self._lancer_composants(module, lot)

    def _lancer_composants(self, module: dict, lot: dict) -> None:
        """Crée le kit 2D K2D-… et, si besoin, le pod POD-… (qui hérite du lot) et lance leurs
        parcours."""
        suffixe = f"29-{module['numero']:05d}"
        k2d = {"id": f"K2D-{suffixe}", "type": "kit 2D", "module": module["id"],
               "lot": lot["id"], "distance": 0.0}
        self.objets[k2d["id"]] = k2d
        module["k2d"] = k2d["id"]
        self._placer(k2d["id"], "kit 2D", "Kitting")
        arrivees = {"2d": self.env.evenement(), "pod": None}
        if module["besoin_pod"]:
            pod = {"id": f"POD-{suffixe}", "type": "pod", "module": module["id"], "lot": lot["id"],
                   "cause": None, "cause_retrouvee": None, "t_integre": None, "distance": 0.0}
            self.objets[pod["id"]] = pod
            module["pod"] = pod["id"]
            arrivees["pod"] = self.env.evenement()
            self._noter(pod["id"], "pod", "Kitting", "Kitting", lot=lot["id"])
            self._placer(pod["id"], "pod", "Kitting")
            self.env.process(self._parcours_pod(module, pod))
        self._arrivees[module["id"]] = arrivees
        self.env.process(self._parcours_2d(module, k2d))

    def _usiner(self, machine: Machine, poste: int, duree: float, zone: str):
        """Usinage avec pannes ; chaque panne lève une alerte « Panne machine »."""
        def signaler(reparation: float) -> None:
            self._alerter("Panne machine", machine.nom, "machine", zone,
                          f"{machine.nom} en panne, réparation de {reparation:.0f} min")

        yield from usiner(self.env, machine, poste, duree, signaler)

    def _parcours_2d(self, module: dict, k2d: dict):
        """Kit 2D : départ décalé de (Σ cycles pod + marge − cycle 2D) pour arriver avec le pod,
        ligne 2D (pannes), puis transport vers l'assemblage."""
        if module["besoin_pod"]:
            yield self.env.timeout(sum(H("cycle_pod_postes")) + H("marge_synchro_kit_2d")
                                   - H("cycle_ligne_2d_module"))
        yield from self._par_agv(k2d, "Kitting", "Ligne 2D robotisée")
        poste = yield self.ligne_2d.request()
        duree = self._triangulaire("facteur_cycle_2d") * H("cycle_ligne_2d_module")
        yield from self._usiner(self.ligne_2d, poste, duree, "Ligne 2D robotisée")
        self.ligne_2d.release(poste)
        self._noter(module["id"], "module", "Panneaux 2D terminés", "Ligne 2D robotisée",
                    lot=module["lot"])
        yield from self._par_agv(k2d, "Ligne 2D robotisée", "Assemblage 3D")
        self._composant_arrive(module, "2d")

    def _parcours_pod(self, module: dict, pod: dict):
        """Pod : 4 postes en série (défauts, pannes du poste Parois), contrôle, retouche
        éventuelle, puis transport vers l'assemblage."""
        yield from self._par_agv(pod, "Kitting", "Ligne pods")
        etapes = zip(NOMS_POSTES_POD, H("cycle_pod_postes"), self.postes_pod)
        for numero, (nom, cycle, machine) in enumerate(etapes, 1):
            poste = yield machine.request()
            duree = self._triangulaire("facteur_cycle_pod") * cycle
            yield from self._usiner(machine, poste, duree, "Ligne pods")
            machine.release(poste)
            self._tirer_defaut_pod(pod, numero, nom)
            self._noter(pod["id"], "pod", f"Poste {numero} {nom}", "Ligne pods", lot=pod["lot"])
        yield from self._controler_pod(pod)
        yield from self._par_agv(pod, "Ligne pods", "Assemblage 3D")
        self._composant_arrive(module, "pod")

    def _tirer_defaut_pod(self, pod: dict, numero: int, nom: str) -> None:
        """Défaut éventuel au poste : probabilité propre au poste, plus un surcroît au poste
        Parois si le lot est non conforme (cause « Lot fournisseur »). On garde le premier."""
        defaut_poste = self.rng.random() < H("defaut_postes_pod")[numero - 1]
        defaut_lot = (nom == POSTE_SENSIBLE_AU_LOT and self.objets[pod["lot"]]["non_conforme"]
                      and self.rng.random() < H("surcroit_defaut_lot"))
        if pod["cause"] is None and (defaut_lot or defaut_poste):
            pod["cause"] = "Lot fournisseur" if defaut_lot else f"Poste {numero} {nom}"

    def _message_defaut(self, objet: dict) -> str:
        """Texte d'une alerte de défaut : cause retrouvée ou non."""
        if objet["cause_retrouvee"]:
            return f"{objet['id']} : défaut, cause retrouvée : {objet['cause']}"
        return f"{objet['id']} : défaut, cause non retrouvée (trop peu d'événements lus)"

    def _controler_pod(self, pod: dict):
        """Contrôle du pod ; en cas de défaut : alerte, cause retrouvée si au moins 5 événements
        du pod ont été lus, retouche."""
        yield self.env.timeout(self._uniforme("controle_pod_min"))
        if pod["cause"]:
            pod["cause_retrouvee"] = cause_retrouvee(self.tracabilite.par_objet.get(pod["id"], []))
            self._alerter("Défaut pod", pod["id"], "pod", "Ligne pods", self._message_defaut(pod),
                          lot=pod["lot"])
            yield self.env.timeout(self._uniforme("retouche_pod_min"))
        self._noter(pod["id"], "pod", "Contrôle pod OK", "Ligne pods", lot=pod["lot"])

    def _composant_arrive(self, module: dict, cle: str) -> None:
        """Signale l'arrivée d'un composant à l'assemblage ; si l'autre manque encore, une veille
        lève « Attente composant » au-delà du seuil (SPEC §3.2)."""
        arrivees = self._arrivees[module["id"]]
        arrivees[cle].succeed(self.env.maintenant)
        autre = arrivees["pod" if cle == "2d" else "2d"]
        if autre is not None and not autre.declenche:
            manque = "son pod" if cle == "2d" else "ses panneaux 2D"
            self.env.process(self._surveiller(
                autre, H("seuil_attente_composant"), "Attente composant", module["id"], "module",
                "Assemblage 3D", f"{module['id']} attend {manque}"))

    def _assembler(self, module: dict):
        """Assemblage 3D (unique) ou consolidation des murs et du pod en kit module, expédié
        vers une usine satellite qui assemble le volume (satellites), dès que le kit 2D et le
        pod éventuel sont arrivés."""
        arrivees = self._arrivees[module["id"]]
        yield arrivees["2d"]
        if arrivees["pod"] is not None:
            yield arrivees["pod"]
        poste = yield self.assemblage.request()
        self._debuter_assemblage(module)
        if self.schema == "unique":
            duree = self._triangulaire("facteur_assemblage") * H("travail_assemblage_3d")
        else:
            duree = self._uniforme("consolidation_min")
        yield self.env.timeout(duree)
        self.assemblage.release(poste)
        self._noter(module["id"], "module", "Fin assemblage", "Assemblage 3D", lot=module["lot"])

    def _debuter_assemblage(self, module: dict) -> None:
        """Le kit 2D et le pod disparaissent dans le module, qui apparaît dans la zone."""
        module["t_debut_assemblage"] = self.env.maintenant
        self._noter(module["id"], "module", "Début assemblage", "Assemblage 3D", lot=module["lot"])
        self._masquer(module["k2d"])
        if module["pod"]:
            self.objets[module["pod"]]["t_integre"] = self.env.maintenant
            self._noter(module["pod"], "pod", "Intégré au module", "Assemblage 3D",
                        lot=module["lot"], message=module["id"])
            self._masquer(module["pod"])
        self._placer(module["id"], "module", "Assemblage 3D")

    def _controler(self, module: dict):
        """Contrôle final ; 2 % de défauts d'assemblage (alerte, retouche)."""
        yield from self._par_porteur(module, "Assemblage 3D", "Contrôle final")
        poste = yield self.controle.request()
        yield self.env.timeout(self._uniforme("controle_final_min"))
        self.controle.release(poste)
        if self.rng.random() < H("taux_defaut_assemblage"):
            module["cause"] = "Assemblage 3D"
            module["cause_retrouvee"] = cause_retrouvee(
                self.tracabilite.par_objet.get(module["id"], []))
            self._alerter("Défaut assemblage", module["id"], "module", "Contrôle final",
                          self._message_defaut(module), lot=module["lot"])
            yield self.env.timeout(self._uniforme("retouche_assemblage_min"))
        self._noter(module["id"], "module", "Contrôle final OK", "Contrôle final",
                    lot=module["lot"])

    def _entrer_stock_pf(self, module: dict):
        """Stock PF : s'il est plein, alerte « Blocage stock PF » et nouvel essai toutes les
        15 min ; sinon transport par porteur et entrée en stock."""
        bloque = False
        while len(self.stock_pf.items) + self._reservations_pf >= self.capacite_pf:
            if not bloque:
                self._alerter("Blocage stock PF", module["id"], "module", "Contrôle final",
                              f"stock PF plein ({self.capacite_pf} places) : {module['id']} "
                              "attend au contrôle final")
                bloque = True
            yield self.env.timeout(H("essai_stock_pf_min"))
        self._reservations_pf += 1
        yield from self._par_porteur(module, "Contrôle final", "Stock produits finis")
        self._reservations_pf -= 1
        module["t_stock_pf"] = self.env.maintenant
        self._termines += 1
        self._noter(module["id"], "module", "Entrée stock PF", "Stock produits finis",
                    lot=module["lot"])
        self.stock_pf.put(module["id"])

    # ── Expédition ──────────────────────────────────────────────────────────────────────────

    def _departs_expedition(self):
        """Unique : un convoi (1 module) dès 1,6 j puis à chaque takt d'OF. Satellites : un semi
        (3 kits) dès 0,7 j puis tous les 3 takts."""
        unique = self.schema == "unique"
        par_camion = H("modules_par_convoi") if unique else H("kits_par_camion_std")
        intervalle = par_camion * minutes_jour() / self.calcul["modules_jour"]
        yield self.env.timeout(H("premier_convoi_j" if unique else "premier_semi_j")
                               * minutes_jour())
        while True:
            self.env.process(self._camion_expedition(par_camion))
            yield self.env.timeout(intervalle)

    def _tirer_destination(self) -> tuple[str, str]:
        """(destination, chantier) : chantier tiré selon les parts de la demande ; en schéma
        satellites, le camion va au satellite le plus proche de ce chantier."""
        chantiers = list(CHANTIERS)
        chantier = self.rng.choices(chantiers, weights=[part_demande(c) for c in chantiers])[0]
        if self.schema == "satellites":
            return f"Satellite {satellite_le_plus_proche(CHANTIERS[chantier])}", chantier
        return chantier, chantier

    def _camion_expedition(self, par_camion: int):
        """Retard éventuel, attente des produits au parking, quai, chargement, départ."""
        destination, chantier = self._tirer_destination()
        camion = self._nouveau_camion(f"EXP-{self._numero('expedition'):04d}", "Expédition",
                                      destination=destination, chantier=chantier, modules=[])
        retard = self._retard("taux_retard_transporteur", "retard_transporteur_min")
        if retard:
            self._alerter("Retard transporteur", camion["id"], "camion", "Expédition",
                          f"{camion['id']} vers {destination} en retard de {retard:.0f} min")
            yield self.env.timeout(retard)
        camion["t_arrivee"] = self.env.maintenant
        self._noter(camion["id"], "camion", "Arrivée sur site", "Parking PL",
                    message=f"vers {destination}")
        modules = yield from self._attendre_produits(camion, par_camion)
        poste, position = yield from self._venir_a_quai(camion, self.quais_expedition,
                                                        "Expédition", self.plan["quai_expedition"])
        if self.plan.get("expedition_en_long", False):
            self._poser_a_cote(modules, position)
        for id_module in modules:
            yield from self._par_porteur(self.objets[id_module], "Stock produits finis",
                                         "Expédition")
        yield self.env.timeout(self._triangulaire("chargement_min"))
        self._expedier(camion, modules)
        self.quais_expedition.release(poste)
        self._repartir(camion["id"], position)

    def _poser_a_cote(self, modules: list[str], position: tuple) -> None:
        """Quai en long : les modules sont posés le long du camion, côté stock PF, en file dans
        le sens de la rangée des quais, et non sur sa place."""
        sens = self.plan["pas_quai_expedition"]
        n = math.hypot(*sens) or 1.0
        ux, uy = sens[0] / n, sens[1] / n
        stock = self.zones["Stock produits finis"]
        centre = (stock[0] + stock[2] / 2, stock[1] + stock[3] / 2)
        cote = 1 if (centre[0] - position[0]) * -uy + (centre[1] - position[1]) * ux > 0 else -1
        gabarit = "dim_module" if self.schema == "unique" else "dim_kit_module"
        ecart = (H("dim_camion")[0] + H(gabarit)[0]) / 2 + ECART_MODULE_CAMION
        pas = H("dim_camion")[1] / len(modules)
        for k, id_module in enumerate(modules):
            le_long = (k - (len(modules) - 1) / 2) * pas
            self._repos_cache[(id_module, "Expédition")] = (
                position[0] + le_long * ux - cote * ecart * uy,
                position[1] + le_long * uy + cote * ecart * ux)

    def _attendre_produits(self, camion: dict, nombre: int):
        """Le camion attend au parking ses modules ou kits ; « Attente produit fini » au-delà du
        seuil. Renvoie les identifiants retirés du stock PF."""
        pret = self.env.evenement()
        quoi = "un module" if nombre == 1 else f"{nombre} kits modules"
        self.env.process(self._surveiller(pret, H("seuil_attente_produit_fini"),
                                          "Attente produit fini", camion["id"], "camion",
                                          "Stock produits finis", f"{camion['id']} attend {quoi}"))
        modules = []
        for _ in range(nombre):
            modules.append((yield self.stock_pf.get()))
            self._en_expedition += 1
        pret.succeed()
        return modules

    def _expedier(self, camion: dict, modules: list[str]) -> None:
        """Fin du chargement : chaque module est expédié vers la destination du camion."""
        for id_module in modules:
            module = self.objets[id_module]
            module.update(t_expedie=self.env.maintenant, camion=camion["id"],
                          destination=camion["destination"])
            self._noter(id_module, "module", "Expédié", "Expédition", lot=module["lot"],
                        message=f"{camion['id']} → {camion['destination']}")
            self._masquer(id_module)
        camion["modules"] = list(modules)
        self._en_expedition -= len(modules)

    def _venir_a_quai(self, camion: dict, quais: Resource, zone: str, point_quai: tuple):
        """Demande un quai (« Attente quai » au-delà du seuil), puis conduit le camion jusqu'à
        lui ; renvoie (numéro du quai, position du camion à quai)."""
        demande = quais.request()
        seuil = H("seuil_attente_quai")
        self.env.process(self._surveiller(demande, seuil, "Attente quai", camion["id"], "camion",
                                          zone, f"{camion['id']} attend un quai ({zone})"))
        poste = yield demande
        pas = self.plan["pas_quai_reception" if zone == "Réception" else "pas_quai_expedition"]
        position = (point_quai[0] + poste * pas[0], point_quai[1] + poste * pas[1])
        en_long = zone != "Réception" and self.plan.get("expedition_en_long", False)
        yield self.env.timeout(self._animer_arrivee(camion["id"], camion["t_arrivee"], position,
                                                    en_long))
        return poste, position

    def _echantillonner(self):
        """En-cours, stock matières et stock PF toutes les 15 min."""
        while True:
            self.echantillons.append({"t": self.env.maintenant, "en_cours": self.en_cours(),
                                      "stock_matieres": len(self.stock_matieres.items),
                                      "stock_pf": len(self.stock_pf.items)})
            yield self.env.timeout(H("pas_echantillonnage"))

    # ── Timelines d'animation ───────────────────────────────────────────────────────────────

    def _segments(self, id_objet: str, type_objet: str) -> list[dict]:
        """Segments de la timeline d'un objet (créée au besoin)."""
        return self._timelines.setdefault(id_objet, (type_objet, []))[1]

    def _clore(self, id_objet: str, t: float) -> None:
        """Termine à l'instant t le segment encore ouvert de l'objet, s'il y en a un."""
        if id_objet in self._timelines:
            segments = self._timelines[id_objet][1]
            if segments and segments[-1]["t1"] is None:
                segments[-1]["t1"] = t

    def _placer(self, id_objet: str, type_objet: str, zone: str, t: float | None = None) -> None:
        """L'objet est posé dans la zone à partir de t (maintenant par défaut)."""
        t = self.env.maintenant if t is None else t
        self._clore(id_objet, t)
        self._segments(id_objet, type_objet).append({"t0": t, "t1": None, "zone": zone})

    def _fixer(self, id_objet: str, type_objet: str, point: tuple, t: float) -> None:
        """L'objet stationne en un point précis (camion à quai) à partir de t."""
        self._clore(id_objet, t)
        self._segments(id_objet, type_objet).append({"t0": t, "t1": None, "chemin": [point]})

    def _deplacer(self, id_objet: str, type_objet: str, t0: float, t1: float,
                  chemin: list) -> None:
        """L'objet parcourt le chemin entre t0 et t1."""
        self._clore(id_objet, t0)
        self._segments(id_objet, type_objet).append({"t0": t0, "t1": t1, "chemin": chemin})

    def _masquer(self, id_objet: str) -> None:
        """L'objet disparaît du dessin (intégré, consommé ou expédié)."""
        self._clore(id_objet, self.env.maintenant)

    def _repos(self, id_objet: str, zone: str) -> tuple[float, float]:
        """Position de repos stable dans la zone : décalage pseudo-aléatoire dont la graine est
        dérivée de l'identifiant (SPEC §3.5)."""
        cle = (id_objet, zone)
        if cle not in self._repos_cache:
            x, y, largeur, hauteur = self.zones[zone][:4]
            tirage = random.Random(f"{id_objet}|{zone}")
            marge = (1 - DISPERSION_REPOS) / 2
            self._repos_cache[cle] = (x + largeur * (marge + DISPERSION_REPOS * tirage.random()),
                                      y + hauteur * (marge + DISPERSION_REPOS * tirage.random()))
            if zone == "Parking PL":  # au milieu d'une place marquée au sol
                self._repos_cache[cle] = place_parking_pl(self.zones[zone], tirage)
        return self._repos_cache[cle]

    def _chemin_objet(self, id_objet: str, de: str, vers: str) -> list:
        """Chemin en L (horizontal puis vertical) entre les positions de repos de l'objet ;
        vertical puis horizontal vers un quai en long, pour finir dans le sens du camion."""
        a, b = self._repos(id_objet, de), self._repos(id_objet, vers)
        if vers == "Expédition" and self.plan.get("expedition_en_long", False):
            return [a, (a[0], b[1]), b]
        return [a, (b[0], a[1]), b]

    def _animer_approche(self, id_camion: str, t_arrivee: float, jusqua: float) -> tuple:
        """Route publique et accès jusqu'au portail, puis attente au portail ou au parking PL
        jusqu'à `jusqua` ; renvoie le point d'où le camion repart vers son quai."""
        vitesse, portail = H("vitesse_camion_site"), self.plan["portail"]
        route = route_d_arrivee(self.plan)
        self._deplacer(id_camion, "camion", t_arrivee - longueur_chemin(route) / vitesse,
                       t_arrivee, route)
        parking = self._repos(id_camion, "Parking PL")
        vers_parking = chemin_sur_site(self.plan, portail, parking)
        duree_parking = longueur_chemin(vers_parking) / vitesse
        if jusqua - t_arrivee > duree_parking:
            self._deplacer(id_camion, "camion", t_arrivee, t_arrivee + duree_parking, vers_parking)
            self._placer(id_camion, "camion", "Parking PL", t_arrivee + duree_parking)
            return parking
        if jusqua > t_arrivee:
            self._fixer(id_camion, "camion", portail, t_arrivee)
        return portail

    def _animer_arrivee(self, id_camion: str, t_arrivee: float, position_quai: tuple,
                        en_long: bool = False) -> float:
        """Approche et attente éventuelle, puis voirie (et bretelle, ou demi-tour pour un quai en
        long) jusqu'au quai. Renvoie la durée (min) du trajet final vers le quai."""
        maintenant = self.env.maintenant
        depart = self._animer_approche(id_camion, t_arrivee, maintenant)
        chemin = chemin_vers_quai(self.plan, depart, position_quai, en_long)
        duree = longueur_chemin(chemin) / H("vitesse_camion_site")
        self._deplacer(id_camion, "camion", maintenant, maintenant + duree, chemin)
        self._fixer(id_camion, "camion", position_quai, maintenant + duree)
        return duree

    def _animer_camions_en_attente(self) -> None:
        """Fin de simulation : un camion arrivé qui attend encore un quai ou ses produits reste
        visible au portail ou au parking PL (son trajet n'est tracé qu'à l'obtention du quai)."""
        for camion in self.objets_de_type("camion"):
            if camion["t_arrivee"] is not None and camion["id"] not in self._timelines:
                self._animer_approche(camion["id"], camion["t_arrivee"], self.duree)

    def _repartir(self, id_camion: str, position_quai: tuple) -> None:
        """Voirie jusqu'au portail (instant de sortie du site), puis accès et route publique vers
        le nord."""
        voirie = chemin_sur_site(self.plan, position_quai, self.plan["portail"])
        chemin = voirie + route_de_depart(self.plan)[1:]
        t0, vitesse = self.env.maintenant, H("vitesse_camion_site")
        self.objets[id_camion]["t_sortie"] = t0 + longueur_chemin(voirie) / vitesse
        self._deplacer(id_camion, "camion", t0, t0 + longueur_chemin(chemin) / vitesse, chemin)

    def _finaliser_timelines(self) -> None:
        """Les présences encore ouvertes durent jusqu'à la fin ; index des débuts de segment."""
        for _, segments in self._timelines.values():
            for segment in segments:
                if segment["t1"] is None:
                    segment["t1"] = math.inf
        self._index_t0 = {id_objet: [segment["t0"] for segment in segments]
                          for id_objet, (_, segments) in self._timelines.items()}

    def segment(self, id_objet: str, t: float) -> dict | None:
        """Segment de timeline actif à l'instant t, ou None si l'objet est masqué."""
        if id_objet not in self._index_t0:
            return None
        segments = self._timelines[id_objet][1]
        i = bisect.bisect_right(self._index_t0[id_objet], t) - 1
        return segments[i] if i >= 0 and t < segments[i]["t1"] else None

    def _point(self, id_objet: str, segment: dict, t: float) -> tuple[float, float]:
        """Position sur un segment : repos dans une zone, point fixe, ou interpolation."""
        if "zone" in segment:
            return self._repos(id_objet, segment["zone"])
        chemin = segment["chemin"]
        if len(chemin) == 1:
            return chemin[0]
        return point_sur_chemin(chemin, (t - segment["t0"]) / (segment["t1"] - segment["t0"]))

    def positions(self, t: float) -> dict[str, tuple[float, float, str]]:
        """{id: (x, y, type)} des objets visibles à l'instant t (SPEC §3.5)."""
        visibles = {}
        for id_objet, (type_objet, _) in self._timelines.items():
            segment = self.segment(id_objet, t)
            if segment is not None:
                visibles[id_objet] = (*self._point(id_objet, segment, t), type_objet)
        return visibles

    def timelines(self) -> dict[str, tuple[str, list[dict]]]:
        """{id: (type, segments)} de tous les objets animés ; chaque segment {t0, t1, chemin},
        la présence dans une zone étant résolue en sa position de repos (export de la vue 3D)."""
        return {id_objet: (type_objet, [{"t0": s["t0"], "t1": s["t1"],
                                         "chemin": ([self._repos(id_objet, s["zone"])]
                                                    if "zone" in s else list(s["chemin"]))}
                                        for s in segments])
                for id_objet, (type_objet, segments) in self._timelines.items()}

    def trace_parcourue(self, id_objet: str, t: float) -> list[tuple[float, float]]:
        """Points déjà parcourus par l'objet jusqu'à t (trajet du mode suivi)."""
        points: list = []
        for segment in self._timelines.get(id_objet, ("", []))[1]:
            if segment["t0"] > t:
                break
            if "zone" in segment:
                points.append(self._repos(id_objet, segment["zone"]))
            elif len(segment["chemin"]) == 1:
                points.append(segment["chemin"][0])
            else:
                fraction = (t - segment["t0"]) / (segment["t1"] - segment["t0"])
                points.extend(portion_de_chemin(segment["chemin"], fraction))
        return points

    # ── Consultation et résultats ───────────────────────────────────────────────────────────

    def objets_de_type(self, type_objet: str) -> list[dict]:
        """Objets d'un type, dans l'ordre de création."""
        return [objet for objet in self.objets.values() if objet["type"] == type_objet]

    def modules_expedies(self) -> list[str]:
        """Identifiants des modules expédiés, dans l'ordre d'expédition."""
        expedies = [m for m in self.objets_de_type("module") if m["t_expedie"] is not None]
        return [m["id"] for m in sorted(expedies, key=lambda m: m["t_expedie"])]

    def en_cours(self) -> int:
        """Modules lancés et pas encore entrés en stock PF."""
        return self._numeros["module"] - self._termines

    def modules_en_expedition(self) -> int:
        """Modules retirés du stock PF par un camion mais pas encore expédiés."""
        return self._en_expedition

    def camions_sur_site(self, t: float) -> int:
        """Camions entre leur entrée et leur sortie par le portail à l'instant t ; ceux qui
        roulent encore sur la route publique ne comptent pas."""
        return sum(1 for camion in self.objets_de_type("camion")
                   if camion["t_arrivee"] is not None and camion["t_arrivee"] <= t
                   and (camion["t_sortie"] is None or t < camion["t_sortie"]))

    def _points_manquants(self, id_objet: str, points: tuple) -> list[str]:
        """Points de contrôle obligatoires non lus (ou pas encore atteints) d'un objet."""
        lus = {e["evenement"] for e in self.tracabilite.par_objet.get(id_objet, [])
               if e["lu"] and not e["alerte"]}
        return [point for point in points if point not in lus]

    def trace_complete(self, id_module: str) -> tuple[bool, list[str]]:
        """(trace complète ?, points manquants) : tous les points obligatoires du module et de
        son pod éventuel doivent être lus (SPEC §3.3)."""
        manquants = self._points_manquants(id_module, POINTS_MODULE)
        pod = self.objets[id_module]["pod"]
        if pod:
            manquants += [f"{pod} · {point}" for point in self._points_manquants(pod, POINTS_POD)]
        return not manquants, manquants

    def ressources(self) -> list[Resource]:
        """Ressources suivies pour le taux d'utilisation, dans l'ordre du flux."""
        quais = [self.quais_reception]
        if self.quais_expedition is not self.quais_reception:
            quais.append(self.quais_expedition)
        return [self.kitting, self.ligne_2d, *self.postes_pod, self.assemblage, self.controle,
                self.agv, self.porteurs, *quais]

    def _par_jour(self, instants) -> list[int]:
        """Nombre d'instants (hors None) dans chaque jour simulé."""
        compte = [0] * self.jours
        for t in instants:
            if t is not None:
                compte[min(int(t // minutes_jour()), self.jours - 1)] += 1
        return compte

    def resultats(self) -> dict:
        """Indicateurs de la simulation (SPEC §3.4) ; un ratio sans dénominateur vaut None."""
        modules = self.objets_de_type("module")
        return {**self._resultats_flux(modules), **self._resultats_alertes(),
                **self._resultats_qualite(modules), **self._resultats_tracabilite(),
                **self._resultats_distances(modules)}

    def _resultats_flux(self, modules: list[dict]) -> dict:
        """Production, délais, en-cours, stocks et utilisation des ressources."""
        objectif = self.calcul["modules_jour"]
        termines = self._par_jour(m["t_stock_pf"] for m in modules)
        expedies = self._par_jour(m["t_expedie"] for m in modules)
        regime = termines[H("jour_regime_etabli") - 1:]
        debit = _moyenne(regime)
        delais = sorted(m["t_stock_pf"] - m["t_of"] for m in modules
                        if m["t_stock_pf"] is not None)
        return {
            "objectif_jour": objectif, "termines_par_jour": termines,
            "expedies_par_jour": expedies, "debit_regime_etabli": debit,
            "taux_atteinte": None if debit is None else debit / objectif,
            "delai_fabrication_moyen_min": _moyenne(delais),
            "delai_fabrication_p90_min": _centile(delais, 0.9),
            "en_cours_moyen": _moyenne(e["en_cours"] for e in self.echantillons),
            "stock_matieres_max": max((e["stock_matieres"] for e in self.echantillons), default=0),
            "stock_pf_max": max((e["stock_pf"] for e in self.echantillons), default=0),
            "utilisation": {r.nom: r.taux_utilisation(self.duree) for r in self.ressources()},
            "lances": len(modules), "termines": sum(termines),
            "en_cours": len(modules) - sum(termines), "expedies": sum(expedies),
        }

    def _resultats_alertes(self) -> dict:
        """Ruptures, attentes et blocages (détail et total), retards, pannes."""
        alertes = Counter(e["evenement"] for e in self.tracabilite.journal if e["alerte"])
        flux = {nature: alertes[nature] for nature in NATURES_FLUX}
        return {"ruptures_attentes": flux, "total_ruptures_attentes": sum(flux.values()),
                "retards": {nature: alertes[nature] for nature in NATURES_RETARD},
                "pannes": alertes["Panne machine"]}

    def _resultats_qualite(self, modules: list[dict]) -> dict:
        """Défauts détectés, Pareto des causes et taux de causes retrouvées."""
        detectes = [o for o in self.objets_de_type("pod") + modules
                    if o["cause_retrouvee"] is not None]
        retrouvees = sum(1 for o in detectes if o["cause_retrouvee"])
        return {"defauts": {"pod": sum(1 for o in detectes if o["type"] == "pod"),
                            "assemblage": sum(1 for o in detectes if o["type"] == "module")},
                "pareto_causes": Counter(o["cause"] for o in detectes).most_common(),
                "taux_causes_retrouvees": _ratio(retrouvees, len(detectes))}

    def _resultats_tracabilite(self) -> dict:
        """Part des modules expédiés tracés de bout en bout, taux de lecture, délai des alertes."""
        expedies = self.modules_expedies()
        traces = sum(1 for id_module in expedies if self.trace_complete(id_module)[0])
        normaux = [e for e in self.tracabilite.journal if not e["alerte"]]
        delais = [e["t_affichage"] - e["t"] for e in self.tracabilite.journal if e["alerte"]]
        return {"pct_traces": _ratio(traces, len(expedies)),
                "taux_lecture": _ratio(sum(1 for e in normaux if e["lu"]), len(normaux)),
                "delai_alertes_moyen_min": _moyenne(delais),
                "delai_alertes_max_min": max(delais, default=None)}

    def _resultats_distances(self, modules: list[dict]) -> dict:
        """Distances moyennes d'un pod, d'un module et d'un sous-ensemble (lot amont + pod +
        module, comme la gamme de modele.py), et distance totale parcourue en charge."""
        expedies = [m for m in modules if m["t_expedie"] is not None]
        pods = [self.objets[m["pod"]] for m in modules
                if m["pod"] and m["t_debut_assemblage"] is not None]
        sous_ensembles = [self.objets[m["lot"]]["distance_reception"] + m["distance_matiere"]
                          + self.objets[m["pod"]]["distance"] + m["distance"]
                          for m in expedies if m["pod"]]
        return {"distance_moyenne_pod": _moyenne(p["distance"] for p in pods),
                "distance_moyenne_module": _moyenne(m["distance"] for m in expedies),
                "distance_moyenne_sous_ensemble": _moyenne(sous_ensembles),
                "distance_totale": sum(trajet["distance"] for trajet in self.trajets)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 6. Affichage des résultats clés (exécution directe, SPEC §3.6 et §5.1)
# ═════════════════════════════════════════════════════════════════════════════════════════════

METRES_PAR_KM = 1000
GRAINES_CONTROLE = tuple(range(1, 21))  # graines du contrôle statistique des parts tracées
CADENCE_SPEC_6 = 1500  # cadence à laquelle SPEC §6 donne ses ordres de grandeur
# Ordres de grandeur de SPEC §6 vérifiés par la simulation : (libellé, attendu, bas, haut).
# Contrôles de cohérence : un écart est signalé et expliqué, jamais corrigé par une hypothèse.
CONTROLES_SPEC_6 = {
    "debit": ("Débit établi / objectif", "95 à 100 %", 0.95, 1.00),
    RFID: ("Modules tracés de bout en bout, RFID", "≈ 97 %", *bornes_environ(0.97)),
    QR: ("Modules tracés de bout en bout, QR code", "70 à 72 %", 0.70, 0.72),
    PAPIER: ("Modules tracés de bout en bout, papier", "≈ 35 %", *bornes_environ(0.35)),
}
SIGLES = {IMPLANTATION_PROPOSEE: "P", IMPLANTATION_ACTUELLE: "A"}


def part_tracee_theorique(techno: str) -> float:
    """Part attendue des modules tracés de bout en bout : taux^(8 + 7) avec pod, taux^8 sans."""
    taux = H(TECHNOLOGIES[techno][0])
    p_pod = H("pods_par_logement") / H("modules_par_logement")
    points_module = len(POINTS_MODULE)
    return (p_pod * taux ** (points_module + len(POINTS_POD))
            + (1 - p_pod) * taux ** points_module)


def _heures(minutes: float | None) -> str:
    """Durée en heures à une décimale (« — » si absente)."""
    return formater_nombre(None if minutes is None else minutes / MINUTES_PAR_HEURE, 1)


def _lignes_flux(usine: Usine) -> list[tuple[str, str]]:
    """(libellé, valeur) des résultats physiques d'une simulation."""
    r = usine.resultats()
    distances = " / ".join(formater_nombre(r[cle]) for cle in
                           ("distance_moyenne_pod", "distance_moyenne_module"))
    lignes = [
        ("Débit en régime établi (modules/jour)", formater_nombre(r["debit_regime_etabli"], 2)),
        ("Taux d'atteinte de l'objectif", formater_pourcentage(r["taux_atteinte"], 1)),
        ("Lancés / terminés / expédiés", f"{r['lances']} / {r['termines']} / {r['expedies']}"),
        ("Délai OF → stock PF moyen (h)", _heures(r["delai_fabrication_moyen_min"])),
        ("Délai OF → stock PF, 90e centile (h)", _heures(r["delai_fabrication_p90_min"])),
        ("En-cours moyen (modules)", formater_nombre(r["en_cours_moyen"], 1)),
        ("Stocks max : matières (kits) / PF", f"{r['stock_matieres_max']} / {r['stock_pf_max']}"),
        ("Ruptures, attentes et blocages", str(r["total_ruptures_attentes"])),
        *((f"  dont {nature}", str(nombre)) for nature, nombre in r["ruptures_attentes"].items()),
        ("Retards fournisseurs / transporteurs", " / ".join(map(str, r["retards"].values()))),
        ("Pannes machine", str(r["pannes"])),
        ("Défauts pod / assemblage", " / ".join(map(str, r["defauts"].values()))),
        ("Distance d'un pod / d'un module (m)", distances),
        ("Distance d'un sous-ensemble (m)", formater_nombre(r["distance_moyenne_sous_ensemble"])),
        ("Distance totale en charge (km)",
         formater_nombre(r["distance_totale"] / METRES_PAR_KM, 1)),
    ]
    postes = ((f"poste pod {numero}", poste) for numero, poste in enumerate(usine.postes_pod, 1))
    suivies = (("kitting", usine.kitting), ("ligne 2D", usine.ligne_2d), *postes,
               ("assemblage ou consolidation", usine.assemblage),
               ("contrôle final", usine.controle), ("AGV", usine.agv),
               ("porteurs", usine.porteurs), ("quais de réception", usine.quais_reception),
               ("quais d'expédition", usine.quais_expedition))
    return lignes + [(f"Utilisation : {nom}",
                      formater_pourcentage(ressource.taux_utilisation(usine.duree)))
                     for nom, ressource in suivies]


def _afficher_flux(physiques: dict) -> None:
    """Résultats physiques des quatre configurations implantation × schéma."""
    afficher_titre("Flux physiques (P = implantation proposée, A = actuelle ; identiques pour les "
                   "trois technologies)")
    afficher_ligne("", *(f"{SIGLES[implantation]} · {schema}"
                         for implantation, schema in physiques))
    colonnes = [_lignes_flux(usine) for usine in physiques.values()]
    for rang, (libelle, _) in enumerate(colonnes[0]):
        afficher_ligne(libelle, *(colonne[rang][1] for colonne in colonnes))
    pareto = next(iter(physiques.values())).resultats()["pareto_causes"]
    print("  Pareto des défauts (P · unique) : "
          + (" · ".join(f"{cause} {nombre}" for cause, nombre in pareto) or "aucun défaut"))


def _afficher_tracabilite(simulations: dict) -> None:
    """Indicateurs de traçabilité par technologie (implantation proposée)."""
    afficher_titre("Traçabilité (implantation proposée, graine 42)")
    afficher_ligne("", "RFID", "QR code", "papier")
    for schema in SCHEMAS:
        parts = (simulations[(schema, t)].resultats()["pct_traces"] for t in TECHNOLOGIES)
        afficher_ligne(f"Modules tracés de bout en bout, {schema}",
                       *(formater_pourcentage(part, 1) for part in parts))
    afficher_ligne("Valeur théorique (taux de lecture ^ points)",
                   *(formater_pourcentage(part_tracee_theorique(t), 1) for t in TECHNOLOGIES))
    resultats = [simulations[("unique", t)].resultats() for t in TECHNOLOGIES]
    for libelle, cle, decimales, en_pourcentage in (
            ("Taux de lecture global", "taux_lecture", 2, True),
            ("Délai moyen événement → écran (min)", "delai_alertes_moyen_min", 1, False),
            ("Délai maximal événement → écran (min)", "delai_alertes_max_min", 1, False),
            ("Causes de défaut retrouvées", "taux_causes_retrouvees", 0, True)):
        formater = formater_pourcentage if en_pourcentage else formater_nombre
        afficher_ligne(libelle, *(formater(r[cle], decimales) for r in resultats))


def _parts_tracees_multi_graines() -> dict[str, tuple[float, float, float]]:
    """Part tracée sur GRAINES_CONTROLE : (moyenne, 2 erreurs types, écart type d'un tirage)."""
    resultats = {}
    for techno in TECHNOLOGIES:
        parts = [Usine(CADENCE_SPEC_6, IMPLANTATION_PROPOSEE, "unique", techno, graine=graine)
                 .executer().resultats()["pct_traces"] for graine in GRAINES_CONTROLE]
        ecart_type = statistics.stdev(parts)
        resultats[techno] = (statistics.fmean(parts), 2 * ecart_type / math.sqrt(len(parts)),
                             ecart_type)
    return resultats


def _afficher_comparaison_spec_6(physiques: dict) -> int:
    """Débit (graine 42) et parts tracées (moyenne de 20 graines ± 2 erreurs types) face à
    SPEC §6 : ✓ si l'intervalle rencontre la plage attendue. Renvoie le nombre d'écarts."""
    afficher_titre("Comparaison aux ordres de grandeur de SPEC §6 (contrôles de cohérence)")
    ecarts = 0
    libelle, attendu, bas, haut = CONTROLES_SPEC_6["debit"]
    for (implantation, schema), usine in physiques.items():
        taux = usine.resultats()["taux_atteinte"]
        conforme = taux is not None and bas - TOLERANCE_ARRONDI <= taux <= haut + TOLERANCE_ARRONDI
        ecarts += not conforme
        afficher_ligne(f"{'✓' if conforme else '⚠'} {libelle} ({SIGLES[implantation]} · {schema})",
                       formater_pourcentage(taux, 1), note=f"attendu {attendu}")
    for techno, (moyenne, demi, ecart_type) in _parts_tracees_multi_graines().items():
        libelle, attendu, bas, haut = CONTROLES_SPEC_6[techno]
        conforme = moyenne - demi <= haut and moyenne + demi >= bas
        ecarts += not conforme
        afficher_ligne(f"{'✓' if conforme else '⚠'} {libelle}", formater_pourcentage(moyenne, 1),
                       note=f"± {formater_nombre(demi * 100, 1)} pt ; théorie "
                            f"{formater_pourcentage(part_tracee_theorique(techno), 1)} ; "
                            f"attendu {attendu} ; un tirage seul : σ ≈ "
                            f"{formater_nombre(ecart_type * 100, 1)} pt")
    print(f"  Parts tracées : moyenne sur {len(GRAINES_CONTROLE)} graines (± 2 erreurs types).")
    return ecarts


def afficher_resultats_cles() -> None:
    """Résultats à 1 500 logements/an : 3 technologies × 2 schémas (SPEC §3.6), l'implantation
    actuelle pour comparaison, puis contrôle des ordres de grandeur de SPEC §6."""
    cadence = H("logements_par_an")
    print(f"Résultats clés à {formater_nombre(cadence)} logements/an, 10 jours simulés, graine 42 "
          "(toutes les valeurs estimées sont des HYPOTHÈSES)")
    simulations = {(schema, techno): Usine(cadence, IMPLANTATION_PROPOSEE, schema, techno)
                   .executer() for schema in SCHEMAS for techno in TECHNOLOGIES}
    physiques = {(IMPLANTATION_PROPOSEE, schema): simulations[(schema, RFID)]
                 for schema in SCHEMAS}
    physiques.update({(IMPLANTATION_ACTUELLE, schema): Usine(
        cadence, IMPLANTATION_ACTUELLE, schema, RFID).executer() for schema in SCHEMAS})
    _afficher_flux(physiques)
    _afficher_tracabilite(simulations)
    ecarts = _afficher_comparaison_spec_6(physiques)
    print(f"\n{ecarts} écart(s) aux ordres de grandeur du §6, à expliquer."
          if ecarts else "\nAucun écart aux ordres de grandeur du §6.")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Tests intégrés (SPEC §3.6)
# ═════════════════════════════════════════════════════════════════════════════════════════════

CLES_RESULTATS = (
    "objectif_jour", "termines_par_jour", "expedies_par_jour", "debit_regime_etabli",
    "taux_atteinte", "delai_fabrication_moyen_min", "delai_fabrication_p90_min", "en_cours_moyen",
    "stock_matieres_max", "stock_pf_max", "utilisation", "ruptures_attentes",
    "total_ruptures_attentes", "retards", "pannes", "defauts", "pareto_causes",
    "taux_causes_retrouvees", "pct_traces", "taux_lecture", "delai_alertes_moyen_min",
    "delai_alertes_max_min", "distance_moyenne_pod", "distance_moyenne_module",
    "distance_moyenne_sous_ensemble", "distance_totale", "lances", "termines", "en_cours",
    "expedies",
)


# ── Moteur ──────────────────────────────────────────────────────────────────────────────────

def test_moteur_ordre_des_evenements():
    env = Env()
    trace = []

    def attendre(nom, delai):
        yield env.timeout(delai)
        trace.append((env.maintenant, nom))

    for nom, delai in (("b", 5), ("a", 2), ("c", 5)):
        env.process(attendre(nom, delai))
    env.run()
    assert trace == [(2, "a"), (5, "b"), (5, "c")], trace  # à temps égal : ordre de planification


def test_moteur_run_jusqua():
    env = Env()
    tops = []

    def horloge_de_test():
        while True:
            tops.append(env.maintenant)
            yield env.timeout(10)

    env.process(horloge_de_test())
    env.run(jusqua=35)
    assert tops == [0, 10, 20, 30] and env.maintenant == 35, tops


def test_moteur_process_et_evenements():
    env = Env()
    vus = []
    signal = env.evenement()

    def enfant():
        yield env.timeout(3)
        return "fini"

    def parent():
        valeur = yield env.process(enfant())
        vus.append((valeur, env.maintenant))
        valeur = yield signal  # déjà traité à t = 0 : reprise immédiate
        vus.append((valeur, env.maintenant))

    signal.succeed("signal")
    env.process(parent())
    env.run()
    assert vus == [("fini", 3), ("signal", 3)], vus
    assert leve(RuntimeError, signal.succeed, "encore")


def test_moteur_resource_fifo_et_utilisation():
    env = Env()
    machine = Resource(env, 1, "machine")
    debuts = []

    def travail(nom):
        poste = yield machine.request()
        debuts.append((env.maintenant, nom, poste))
        yield env.timeout(10)
        machine.release(poste)

    for nom in "xyz":
        env.process(travail(nom))
    env.run()
    assert debuts == [(0, "x", 0), (10, "y", 0), (20, "z", 0)], debuts
    assert math.isclose(machine.taux_utilisation(30), 1.0)
    env_duo = Env()
    duo = Resource(env_duo, 2, "duo")

    def court():
        poste = yield duo.request()
        yield env_duo.timeout(10)
        duo.release(poste)

    env_duo.process(court())
    env_duo.run(jusqua=20)
    assert math.isclose(duo.taux_utilisation(20), 10 / (2 * 20))


def test_moteur_store_bloquant():
    env = Env()
    stock = Store(env, capacite=1)
    journal = []

    def consommateur(depart):
        yield env.timeout(depart)
        objet = yield stock.get()
        journal.append((env.maintenant, "get", objet))

    def producteur():
        yield env.timeout(5)
        for objet in "ABC":
            yield stock.put(objet)
            journal.append((env.maintenant, "put", objet))

    env.process(consommateur(0))
    env.process(consommateur(20))
    env.process(producteur())
    env.run()
    assert journal == [(5, "put", "A"), (5, "get", "A"), (5, "put", "B"),
                       (20, "get", "B"), (20, "put", "C")], journal


def test_moteur_machine_pannes():
    env = Env()
    presse = Machine(env, 1, "presse", random.Random(5), mtbf=100, mttr=10)
    presse.avant_panne[0] = 30.0  # première panne après 30 min de marche
    pannes, fins = [], []

    def travail():
        poste = yield presse.request()
        yield from usiner(env, presse, poste, 50, lambda reparation: pannes.append(
            (env.maintenant, reparation)))
        presse.release(poste)
        fins.append(env.maintenant)

    env.process(travail())
    env.run()
    assert pannes and pannes[0][0] == 30, pannes
    assert math.isclose(fins[0], 50 + sum(reparation for _, reparation in pannes))
    sans_panne = Machine(Env(), 2, "sans panne", random.Random(5))
    assert sans_panne.avant_panne == [math.inf, math.inf]


# ── Temps et traçabilité ────────────────────────────────────────────────────────────────────

def test_horloge_et_equipes():
    assert horloge(0) == "Jour 1 · 06:00"
    assert horloge(480) == "Jour 1 · 14:00"
    assert horloge(959.9) == "Jour 1 · 21:59"
    assert horloge(960) == "Jour 2 · 06:00"
    assert horloge_courte(1455) == "J2 14:15"
    assert fin_equipe(100) == 480 and fin_equipe(480) == 960 and fin_equipe(1000) == 1440


def test_tracabilite_delais_d_affichage():
    rfid, qr, papier = (Tracabilite(techno, random.Random(1)) for techno in TECHNOLOGIES)
    for t in (0.0, 100.0, 500.0):
        assert 2 / 60 <= rfid.instant_affichage(t) - t <= 10 / 60
        assert 0.5 <= qr.instant_affichage(t) - t <= 6
    assert 485 <= papier.instant_affichage(100) <= 510  # équipe 1 : fin à 480 (14:00)
    assert 965 <= papier.instant_affichage(500) <= 990  # équipe 2 : fin à 960 (22:00)


def test_alertes_toujours_lues():
    for techno in TECHNOLOGIES:
        trace = Tracabilite(techno, random.Random(3))
        for i in range(300):
            trace.enregistrer(float(i), "MOD-29-00001", "module", "Défaut pod", "Ligne pods",
                              alerte=True)
        assert all(e["lu"] and e["t_affichage"] is not None for e in trace.journal), techno
    papier = Tracabilite(PAPIER, random.Random(3))
    for i in range(3000):
        papier.enregistrer(float(i), "MOD-29-00001", "module", "Kitting", "Kitting")
    non_lus = [e for e in papier.journal if not e["lu"]]
    assert non_lus and all(e["t_affichage"] is None for e in non_lus)
    assert abs(1 - len(non_lus) / 3000 - H("taux_lecture_papier")) < 0.02


def test_cause_retrouvee():
    lus = [{"lu": True, "alerte": False}] * 5
    assert cause_retrouvee(lus)
    assert not cause_retrouvee(lus[:4] + [{"lu": False, "alerte": False}] * 3)
    # une alerte, même lue, ne compte pas parmi les événements lus
    assert not cause_retrouvee(lus[:4] + [{"lu": True, "alerte": True}])


# ── Usine ───────────────────────────────────────────────────────────────────────────────────

def test_usine_entrees_invalides():
    assert leve(ValueError, Usine, 0, IMPLANTATION_PROPOSEE, "unique", RFID)
    assert leve(ValueError, Usine, 1500, "inconnue", "unique", RFID)
    assert leve(ValueError, Usine, 1500, IMPLANTATION_PROPOSEE, "mixte", RFID)
    assert leve(ValueError, Usine, 1500, IMPLANTATION_PROPOSEE, "unique", "Laser")
    assert leve(ValueError, Usine, 1500, IMPLANTATION_PROPOSEE, "unique", RFID, 0)


def test_usine_capacites_au_dimensionnement():
    haute = Usine(2400, IMPLANTATION_PROPOSEE, "unique", RFID, jours=1)
    ressources = calcul_cadence(2400)["ressources"]
    assert haute.ligne_2d.capacite == ressources["lignes_2d"]["nombre"] == 2
    assert haute.assemblage.capacite == ressources["baies_assemblage"]["nombre"]
    assert all(p.capacite == ressources["lignes_pods"]["nombre"] for p in haute.postes_pod)
    satellites = Usine(1500, IMPLANTATION_PROPOSEE, "satellites", RFID, jours=1)
    assert satellites.assemblage.capacite == H("postes_consolidation")
    actuelle = Usine(1500, IMPLANTATION_ACTUELLE, "unique", RFID, jours=1)
    assert actuelle.quais_expedition is actuelle.quais_reception  # quais partagés
    proposee = Usine(1500, IMPLANTATION_PROPOSEE, "unique", RFID, jours=1)
    assert proposee.quais_expedition is not proposee.quais_reception
    assert proposee.capacite_pf == 45 and satellites.capacite_pf == 132  # 2 380 m² / 52,5 et / 18


def test_usine_conservation():
    for schema in SCHEMAS:
        usine = Usine(1500, IMPLANTATION_ACTUELLE, schema, QR, jours=5).executer()
        r = usine.resultats()
        modules = usine.objets_de_type("module")
        compte = Counter(e["evenement"] for e in usine.tracabilite.journal
                         if e["type"] == "module" and not e["alerte"])
        assert r["lances"] == len(modules) == compte["OF lancé"], schema
        assert r["termines"] == compte["Entrée stock PF"], schema
        assert r["lances"] == r["termines"] + r["en_cours"], schema
        assert r["expedies"] == compte["Expédié"], schema
        assert r["termines"] == (r["expedies"] + len(usine.stock_pf.items)
                                 + usine.modules_en_expedition()), schema
        kits_livres = sum(lot["kits"] for lot in usine.objets_de_type("lot"))
        consommes = sum(1 for m in modules if m["lot"] is not None)
        assert kits_livres == consommes + len(usine.stock_matieres.items), schema
        assert len(usine.objets_de_type("pod")) == sum(1 for m in modules if m["pod"]), schema


def test_usine_reproductible():
    def simuler(graine):
        return Usine(1500, IMPLANTATION_PROPOSEE, "unique", QR, jours=4, graine=graine).executer()

    a, b, c = simuler(7), simuler(7), simuler(8)
    assert a.resultats() == b.resultats()
    assert a.tracabilite.journal == b.tracabilite.journal and a.trajets == b.trajets
    assert c.tracabilite.journal != a.tracabilite.journal


def test_usine_physique_independante_de_la_technologie():
    def physique(techno):
        usine = Usine(1500, IMPLANTATION_ACTUELLE, "unique", techno, jours=4, graine=11)
        usine.executer()
        evenements = [(e["t"], e["id"], e["evenement"]) for e in usine.tracabilite.journal]
        return usine.trajets, evenements

    assert physique(RFID) == physique(QR) == physique(PAPIER)


def test_usine_simulation_courte():
    usine = Usine(1500, IMPLANTATION_PROPOSEE, "unique", PAPIER, jours=1).executer()
    r = usine.resultats()
    assert r["expedies"] == 0 and r["pct_traces"] is None
    assert r["debit_regime_etabli"] is None and r["taux_atteinte"] is None
    assert usine.modules_expedies() == []


def test_usine_trace_complete():
    usine = Usine(1500, IMPLANTATION_PROPOSEE, "unique", QR, jours=6).executer()
    etats = []
    for module in usine.modules_expedies():
        a_verifier = [(module, POINTS_MODULE)]
        if usine.objets[module]["pod"]:
            a_verifier.append((usine.objets[module]["pod"], POINTS_POD))
        attendu = all(any(e["evenement"] == point and e["lu"]
                          for e in usine.tracabilite.par_objet[objet])
                      for objet, points in a_verifier for point in points)
        complete, manquants = usine.trace_complete(module)
        assert complete == attendu and complete == (not manquants), module
        etats.append(complete)
    assert any(etats) and not all(etats), etats


def test_usine_positions():
    usine = Usine(1500, IMPLANTATION_PROPOSEE, "unique", RFID, jours=3).executer()
    t = 2 * 900 + 300
    positions = usine.positions(t)
    assert positions and positions == usine.positions(t)
    assert {type_objet for _, _, type_objet in positions.values()} <= set(TYPES_OBJETS)
    assert {"module", "pod", "kit 2D"} <= {type_objet for _, _, type_objet in positions.values()}
    for id_objet, (x, y, _) in positions.items():
        segment = usine.segment(id_objet, t)
        if "zone" in segment:
            zx, zy, largeur, hauteur = usine.zones[segment["zone"]][:4]
            assert zx <= x <= zx + largeur and zy <= y <= zy + hauteur, (id_objet, segment)


def test_usine_camions_sur_site():
    """Seuls comptent les camions passés par le portail : pas ceux de la route publique."""
    for nom in IMPLANTATIONS:
        usine = Usine(1500, nom, "unique", RFID, jours=3).executer()
        camions = usine.objets_de_type("camion")
        assert any(camion["t_sortie"] is not None for camion in camions), nom
        assert all(camion["t_arrivee"] <= camion["t_sortie"] for camion in camions
                   if camion["t_sortie"] is not None), nom
        sur_route = 0
        for t in (k * 7.3 + 0.37 for k in range(int(usine.duree / 7.3))):
            dans_site = 0
            for x, y, type_objet in usine.positions(t).values():
                if type_objet == "camion":
                    dedans = any(point_dans_polygone((x, y), contour)
                                 for contour in IMPLANTATIONS[nom]["polygones_site"])
                    dans_site, sur_route = dans_site + dedans, sur_route + (not dedans)
            assert usine.camions_sur_site(t) == dans_site, (nom, t)
        assert sur_route > 0, nom  # le cas corrigé se présente bien


def test_chemins_des_camions():
    """Portail et accès de chaque implantation ; quais de réception par la bretelle."""
    for nom, plan in IMPLANTATIONS.items():
        portail = tuple(plan["portail"])
        arrivee, depart = route_d_arrivee(plan), route_de_depart(plan)
        assert arrivee[0] == ROUTE_PUBLIQUE[0] and arrivee[-1] == portail, nom
        assert depart[0] == portail and depart[-1] == ROUTE_PUBLIQUE[-1], nom
        assert any(point_dans_polygone(portail, c) for c in plan["polygones_site"]), nom
        vers_quai = chemin_sur_site(plan, portail, plan["quai_reception"])
        bretelle = plan["bretelles"][0]
        assert vers_quai[0] == portail and vers_quai[-1] == tuple(plan["quai_reception"]), nom
        assert tuple(bretelle[0]) in vers_quai, nom
        assert chemin_sur_site(plan, plan["quai_reception"], portail) == vers_quai[::-1], nom
        vers_parking = chemin_sur_site(plan, portail, (200, 215))
        assert tuple(bretelle[0]) not in vers_parking, nom
    actuelle = IMPLANTATIONS[IMPLANTATION_ACTUELLE]
    assert (222, 170) in route_d_arrivee(actuelle)  # par la Rue Alain Bombard
    assert not point_dans_polygone(route_d_arrivee(actuelle)[-2], SITE_ACTUEL)


def test_usine_camions_aux_quais():
    """Les camions s'arrêtent aux quais de la façade est de la Réception (et d'expédition)."""
    for nom, plan in IMPLANTATIONS.items():
        usine = Usine(1500, nom, "unique", RFID, jours=3).executer()
        arrets = {segment["chemin"][0] for type_objet, segments in usine._timelines.values()
                  if type_objet == "camion" for segment in segments
                  if len(segment.get("chemin", ())) == 1}
        (x0, y0), (dx, dy) = plan["quai_reception"], plan["pas_quai_reception"]
        quais = {(x0 + k * dx, y0 + k * dy) for k in range(usine.dimension["quais_reception"])}
        assert (x0, y0) in arrets and (110, 200) not in arrets, nom  # ancien quai sud
        assert all(x == plan["zones"]["Réception"][0] + plan["zones"]["Réception"][2] + 2
                   for x, _ in quais), nom


def test_usine_resultats_complets():
    usine = Usine(1500, IMPLANTATION_PROPOSEE, "unique", RFID, jours=5).executer()
    r = usine.resultats()
    assert set(CLES_RESULTATS) <= set(r), set(CLES_RESULTATS) - set(r)
    assert 0 < r["taux_atteinte"] <= 1.2
    assert all(0 <= taux <= 1 for taux in r["utilisation"].values()), r["utilisation"]
    sous_ensemble = distances_sous_ensemble(IMPLANTATION_PROPOSEE)["sous_ensemble"]
    assert math.isclose(r["distance_moyenne_sous_ensemble"], sous_ensemble)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    reussite = executer_tests(globals(), "simulation.py")
    if reussite:
        afficher_resultats_cles()
    sys.exit(0 if reussite else 1)
