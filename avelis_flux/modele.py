"""Modèle de dimensionnement des flux du site Avelis de Torcy (Imagine & Make 2026, Bloc 3).

Contenu : hypothèses (HYPOTHESES, lues avec H), cadence et ressources, dimensionnement du site,
évolutivité, réseau national (usine unique ou usine mère + satellites), géométrie du site et
implantations, contrôle géométrique, distances et croisements de flux.

Toute valeur numérique métier est dans HYPOTHESES : "A" = donnée Avelis, "H" = hypothèse.
Ce module n'importe aucun module graphique : il sert à simulation.py et à app.py.

Exécution directe (« py -3 avelis_flux/modele.py ») : tests intégrés, puis chiffres clés à
1 500 logements/an comparés aux ordres de grandeur attendus (§6 du cahier des charges).
"""

import copy
import math
import numbers
import sys
import textwrap
from typing import Any


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. Hypothèses : {clé: (valeur, unité, "A" | "H", commentaire)} — "A" = Avelis, "H" = hypothèse
# ═════════════════════════════════════════════════════════════════════════════════════════════

HYPOTHESES: dict[str, tuple[Any, str, str, str]] = {
    # — Données Avelis (A) —
    "logements_par_an": (1500, "logements/an", "A", "haut de la fourchette Avelis 1 000–1 500"),
    "surface_site_actuel": (42786, "m²", "A", "emprise actuelle de Torcy"),
    "perimetre_site_actuel": (983, "m", "A", "périmètre de l'emprise actuelle"),
    "surface_extension": (27443, "m²", "A", "foncier disponible à proximité"),
    "perimetre_extension": (750, "m", "A", "périmètre du foncier disponible"),
    "surface_totale": (70229, "m²", "A", "site + extension"),
    "annee_objectif": (2029, "—", "A", "outil industriel opérationnel"),
    # — Cadence et temps d'ouverture (H) —
    "jours_ouvres": (220, "j/an", "H", "jours ouvrés par an, valeur de la fiche Bloc 2 commune "
                                       "aux trois blocs"),
    "equipes_par_jour": (2, "—", "H", "équipe 1 de 06:00 à 14:00, équipe 2 de 14:00 à 22:00"),
    "heures_par_equipe": (8, "h", "H", "postes de 8 h de la fiche Bloc 2, donc 960 min "
                                       "d'ouverture par jour"),
    "trs": (0.80, "—", "H", "taux de rendement synthétique, sert au dimensionnement"),
    # — Nomenclature d'un logement (H) —
    "modules_par_logement": (1.2, "modules", "H", "modules 3D par logement"),
    "pods_par_logement": (1.0, "pods", "H", "pods salle de bain par logement"),
    "panneaux_par_module": (12, "panneaux 2D", "H", "panneaux 2D par module"),
    # — Temps de cycle et charge (H) —
    "cycle_ligne_2d_module": (70, "min/module", "H", "ligne 2D robotisée"),
    "cycle_pod_postes": ((60, 75, 70, 65), "min", "H",
                         "Châssis, Parois + étanchéité, Plomberie-élec, Finitions"),
    "travail_assemblage_3d": (960, "min/module", "H", "travail d'assemblage d'un module 3D"),
    "temps_kitting": (25, "min/kit", "H", "préparation d'un kit"),
    "charge_max_poste": (0.90, "—", "H", "charge maximale admise pour une ressource"),
    # — Flux entrants (H) —
    "tonnes_par_logement": (12, "t", "H", "matières reçues par logement"),
    "charge_utile_camion": (14, "t", "H", "charge utile d'un camion fournisseur"),
    "temps_quai_reception": (45, "min", "H", "occupation d'un quai de réception par camion"),
    "jours_stock_matieres": (10, "j", "H", "couverture du stock matières"),
    "densite_stockage": (0.6, "t/m²", "H", "densité du stock matières"),
    # — Flux sortants (H) —
    "dim_module": ((3.5, 10, 3.2), "m (l × L × h)", "H", "gabarit d'un module 3D"),
    "temps_chargement_module": (40, "min", "H", "occupation d'un quai d'expédition par camion"),
    "jours_stock_modules": (5, "j", "H", "couverture du stock de produits finis"),
    "kits_par_camion_std": (3, "kits/semi", "H", "kits modules par semi-remorque standard"),
    "taux_occupation_quais": (0.60, "—", "H", "occupation maximale visée des quais"),
    # — Surfaces (H) —
    "m2_baie_assemblage": (350, "m²", "H", "une baie d'assemblage 3D"),
    "m2_poste_pod": (150, "m²", "H", "un poste de la ligne pods"),
    "m2_ligne_2d": (4000, "m²", "H", "une ligne 2D, circulations comprises"),
    "coef_circulation": (1.5, "—", "H", "majoration des surfaces pour les circulations"),
    "ratio_foncier_utilisable": (0.60, "—", "H", "part du foncier réellement utilisable"),
    "m2_poste_kitting": (200, "m²", "H", "ajoutée, à valider"),
    "m2_kit": (12, "m²", "H", "par kit expédié — ajoutée, à valider"),
    "m2_bureaux": (1500, "m²", "H", "bureaux et pilotage"),
    "largeur_voirie": (7, "m", "H", "voirie poids lourds"),
    "longueur_voirie": (520, "m", "H", "voirie poids lourds"),
    "rayon_retournement": (13, "m", "H", "aire de retournement des poids lourds"),
    "m2_parking_pl": (1500, "m²", "H", "parking poids lourds"),
    # — Transport et réseau (H) —
    "cout_km_convoi": (3.4, "€/km", "H", "convoi d'un module 3D"),
    "cout_km_semi": (1.9, "€/km", "H", "semi-remorque standard"),
    "co2_km_pl": (1.0, "kg/km", "H", "émissions d'un poids lourd"),
    "coef_retour_vide_convoi": (2.0, "—", "H", "aller chargé et retour à vide"),
    "coef_retour_semi": (1.6, "—", "H", "retour partiellement chargé"),
    "coef_detour_route": (1.30, "—", "H", "distance routière / distance à vol d'oiseau"),
    "vitesse_convoi": (60, "km/h", "H", "vitesse moyenne d'un convoi"),
    "vitesse_semi": (75, "km/h", "H", "vitesse moyenne d'un semi-remorque"),
    "capex_satellite": (9, "M€", "H", "investissement par usine satellite"),
    "amortissement_ans": (15, "ans", "H", "durée d'amortissement d'un satellite"),
    "frais_fixes_satellite": (1.4, "M€/an", "H", "frais fixes annuels par satellite"),
    "jours_stock_satellite": (2, "j", "H", "j de kits par satellite — ajoutée, à valider"),
    # — Ajoutées par l'IA : valeurs chiffrées de la spec sans clé au §2.1 (H) —
    "quais_secours": (1, "quai", "H", "quai de secours (SPEC §2.3) — ajoutée — à valider"),
    "postes_consolidation": (2, "postes", "H",
                             "consolidation en satellites (SPEC §2.3) — ajoutée — à valider"),
    "modules_par_convoi": (1, "module", "H",
                           "un module 3D par convoi (SPEC §2.3) — ajoutée — à valider"),
    # — Simulation à événements discrets : valeurs chiffrées de SPEC §3 (H) —
    "heure_ouverture": (6, "h", "H", "SPEC §3.1 — début de l'équipe 1 (06:00)"),
    "taux_retard_fournisseur": (0.12, "—", "H", "SPEC §3.2 — camions fournisseurs en retard"),
    "retard_fournisseur_min": ((30, 180), "min", "H", "SPEC §3.2 — loi uniforme"),
    "nombre_fournisseurs": (4, "fournisseurs", "H", "SPEC §3.2 — FOUR-A à FOUR-D"),
    "taux_lots_non_conformes": (0.06, "—", "H", "SPEC §3.2 — lots fournisseurs non conformes"),
    "seuil_attente_quai": (30, "min", "H", "SPEC §3.2 — alerte « Attente quai » au-delà"),
    "dechargement_min": ((30, 60), "min", "H", "SPEC §3.2 — loi triangulaire"),
    "stock_initial_jours": (1.5, "j", "H", "SPEC §3.2 — stock matières initial (consommation)"),
    "kitting_min": ((18, 35), "min", "H", "SPEC §3.2 — préparation d'un kit, loi triangulaire"),
    "marge_synchro_kit_2d": (20, "min", "H", "SPEC §3.2 — marge du lancement décalé du kit 2D"),
    "nombre_agv": (3, "AGV", "H", "SPEC §3.2 — transport des lots, kits et pods"),
    "vitesse_agv": (60, "m/min", "H", "SPEC §3.2"),
    "manutention_agv_min": (2, "min", "H", "SPEC §3.2 — prise et dépose : 2 + d/v + 2"),
    "facteur_cycle_2d": ((0.85, 1.25), "× cycle", "H", "SPEC §3.2 — ligne 2D, loi triangulaire"),
    "mtbf_ligne_2d": (2400, "min", "H", "SPEC §3.2 — moyenne entre pannes, en temps de marche"),
    "mttr_ligne_2d": (45, "min", "H", "SPEC §3.2 — durée moyenne de réparation"),
    "facteur_cycle_pod": ((0.85, 1.2), "× cycle", "H", "SPEC §3.2 — postes pod, triangulaire"),
    "defaut_postes_pod": ((0.01, 0.015, 0.02, 0.01), "—", "H",
                          "SPEC §3.2 — probabilité de défaut par poste pod"),
    "surcroit_defaut_lot": (0.35, "—", "H", "SPEC §3.2 — poste Parois, lot non conforme"),
    "mtbf_poste_parois": (4000, "min", "H", "SPEC §3.2 — entre pannes, en temps de marche"),
    "mttr_poste_parois": (30, "min", "H", "SPEC §3.2 — durée moyenne de réparation"),
    "controle_pod_min": ((10, 20), "min", "H", "SPEC §3.2 — contrôle d'un pod, loi uniforme"),
    "retouche_pod_min": ((60, 150), "min", "H", "SPEC §3.2 — retouche d'un pod, loi uniforme"),
    "evenements_lus_cause": (5, "événements", "H", "SPEC §3.2 — lus pour retrouver une cause"),
    "seuil_attente_composant": (60, "min", "H", "SPEC §3.2 — « Attente composant » au-delà"),
    "facteur_assemblage": ((0.9, 1.25), "× travail", "H", "SPEC §3.2 — loi triangulaire"),
    "consolidation_min": ((20, 40), "min", "H", "SPEC §3.2 — schéma satellites, loi uniforme"),
    "controle_final_min": ((25, 35), "min", "H", "SPEC §3.2 — loi uniforme"),
    "taux_defaut_assemblage": (0.02, "—", "H", "SPEC §3.2 — défauts vus au contrôle final"),
    "retouche_assemblage_min": ((60, 180), "min", "H", "SPEC §3.2 — loi uniforme"),
    "essai_stock_pf_min": (15, "min", "H", "SPEC §3.2 — nouvel essai si le stock PF est plein"),
    "nombre_porteurs": (2, "porteurs", "H", "SPEC §3.2 — transport des modules"),
    "vitesse_porteur": (40, "m/min", "H", "SPEC §3.2"),
    "premier_convoi_j": (1.6, "j", "H", "SPEC §3.2 — premier départ, schéma unique"),
    "premier_semi_j": (0.7, "j", "H", "SPEC §3.2 — premier départ, schéma satellites"),
    "taux_retard_transporteur": (0.08, "—", "H", "SPEC §3.2 — camions d'expédition en retard"),
    "chargement_min": ((30, 55), "min", "H", "SPEC §3.2 — loi triangulaire"),
    "pas_echantillonnage": (15, "min", "H", "SPEC §3.2 — en-cours et stocks"),
    "jour_regime_etabli": (3, "jour", "H", "SPEC §3.4 — débit mesuré à partir de ce jour"),
    "taux_lecture_rfid": (0.998, "—", "H", "SPEC §3.3 — RFID + IoT (automatique)"),
    "delai_rfid_s": ((2, 10), "s", "H", "SPEC §3.3 — délai d'affichage, loi uniforme"),
    "taux_lecture_qr": (0.975, "—", "H", "SPEC §3.3 — QR code (scan manuel)"),
    "delai_qr_min": ((0.5, 6), "min", "H", "SPEC §3.3 — délai d'affichage, loi uniforme"),
    "taux_lecture_papier": (0.92, "—", "H", "SPEC §3.3 — papier, saisie en fin de poste"),
    "delai_papier_min": ((5, 30), "min", "H", "SPEC §3.3 — après la fin de l'équipe, uniforme"),
    # — Interface : seuil d'affichage chiffré par SPEC §4 (H) —
    "seuil_utilisation_critique": (0.85, "—", "H",
                                   "SPEC §4.2 — utilisation affichée en rouge au-delà"),
    # — Simulation : valeurs que la spec ne chiffre pas, ajoutées par l'IA (H) —
    "retard_transporteur_min": ((30, 180), "min", "H",
                                "durée non donnée, comme les fournisseurs — ajoutée — à valider"),
    "manutention_porteur_min": (2, "min", "H",
                                "prise et dépose, comme les AGV — ajoutée — à valider"),
    "postes_controle_final": (1, "poste", "H", "ajoutée — à valider"),
    "vitesse_camion_site": (250, "m/min", "H", "15 km/h sur le site — ajoutée — à valider"),
    "seuil_attente_produit_fini": (30, "min", "H",
                                   "camion d'expédition sans module — ajoutée — à valider"),
    # — Vue 3D : gabarits des objets et hauteur des bâtiments, ajoutés par l'IA (H) —
    "dim_camion": ((2.55, 16.5, 4.0), "m (l × L × h)", "H",
                   "semi-remorque au gabarit routier maximal — ajoutée — à valider"),
    "dim_pod": ((2.0, 2.6, 2.6), "m (l × L × h)", "H", "pod salle de bain — ajoutée — à valider"),
    "dim_kit_2d": ((3.2, 10.0, 1.5), "m (l × L × h)", "H",
                   "pile des panneaux 2D d'un module — ajoutée — à valider"),
    "dim_lot": ((2.4, 6.0, 1.6), "m (l × L × h)", "H",
                "palettes d'un lot fournisseur — ajoutée — à valider"),
    "dim_kit_module": ((2.4, 5.0, 2.5), "m (l × L × h)", "H",
                       "kit module expédié, empreinte = m2_kit — ajoutée — à valider"),
    "hauteur_batiments": (12, "m", "H",
                          "ateliers, stocks couverts et bureaux — ajoutée — à valider"),
    # — Jumeau numérique : comparaison des scans à la simulation, ajoutée par l'IA (H) —
    "echelle_temps_maquette": (1, "min d'usine par min scannée", "H",
                               "1 = atelier réel ; plus grand sur une maquette jouée en accéléré "
                               "— ajoutée — à valider"),
    "seuil_ecart_jumeau": (0.5, "—", "H",
                           "écart relatif réel / simulé signalé dans la comparaison ; un poste "
                           "est anormalement lent au-delà — ajoutée — à valider"),
    # — Jumeau numérique : détection, prévision et décisions proposées, ajoutées par l'IA (H) —
    "passages_recents_derive": (3, "passages", "H",
                                "derniers passages comparés à la référence d'une étape "
                                "— ajoutée — à valider"),
    "passages_reference_min": (3, "passages", "H",
                               "passages antérieurs nécessaires pour servir de référence "
                               "— ajoutée — à valider"),
    "seuil_anomalie_mad": (3.0, "écarts robustes", "H",
                           "passage anormal au-delà de la médiane + 3 écarts robustes "
                           "— ajoutée — à valider"),
    "poids_prevision": (5, "passages", "H",
                        "poids de la durée simulée face aux mesures dans la prévision "
                        "— ajoutée — à valider"),
    "seuil_piece_bloquee": (2.0, "× durée estimée", "H",
                            "pièce sans nouveau scan au-delà : décision proposée "
                            "— ajoutée — à valider"),
    "seuil_defauts_repetes": (2, "défauts", "H",
                              "défauts de même catégorie au même poste dans la fenêtre "
                              "— ajoutée — à valider"),
    "fenetre_defauts_min": (60, "min", "H",
                            "fenêtre de comptage des défauts répétés — ajoutée — à valider"),
    "seuil_retard_objectif": (0.8, "—", "H",
                              "terminés du jour sous cette part de l'objectif à cette heure "
                              "— ajoutée — à valider"),
    "delai_repetition_decision_min": (60, "min", "H",
                                      "une décision envoyée ou ignorée n'est pas reproposée "
                                      "avant ce délai — ajoutée — à valider"),
}


def H(cle: str) -> Any:
    """Renvoie la valeur de l'hypothèse « cle » ; KeyError explicite si elle n'existe pas."""
    try:
        return HYPOTHESES[cle][0]
    except KeyError:
        raise KeyError(f"hypothèse inconnue : « {cle} »") from None


# Constantes de définition (conversions, constante physique, plages de balayage) : ce ne sont pas
# des hypothèses métier, elles restent donc hors de HYPOTHESES.
MINUTES_PAR_HEURE = 60
EUROS_PAR_MILLION = 1_000_000
KG_PAR_TONNE = 1000
RAYON_TERRE_KM = 6371.0
LOGEMENTS_REFERENCE = 1000  # base de l'indicateur « m² de stockage pour 1 000 logements/an »
PLAGE_EVOLUTIVITE = (400, 3000, 100)  # (première cadence, dernière incluse, pas)
PLAGE_SENSIBILITE = (400, 8000, 50)  # balayage de sensibilite_reseau et de point_bascule
TOLERANCE_ARRONDI = 1e-9  # absorbe l'erreur flottante avant un arrondi par excès

SCHEMAS = ("unique", "satellites")
VARIANTES = ("proche", "hybride")


def arrondi_superieur(x: float) -> int:
    """Arrondi par excès insensible aux erreurs flottantes (16,000000000000004 → 16)."""
    return math.ceil(x - TOLERANCE_ARRONDI)


def formater_nombre(x: float | None, decimales: int = 0) -> str:
    """Nombre à la française : espace insécable des milliers, virgule décimale ; None → « — »."""
    if x is None:
        return "—"
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def formater_pourcentage(x: float | None, decimales: int = 0) -> str:
    """Fraction affichée en pourcentage à la française (0,16 → « 16 % ») ; None → « — »."""
    if x is None:
        return "—"
    return f"{formater_nombre(x * 100, decimales)} %"


def _verifier_cadence(L: float) -> None:
    """Refuse une cadence nulle, négative, infinie ou non numérique."""
    if not (isinstance(L, numbers.Real) and math.isfinite(L) and L > 0):
        raise ValueError(f"cadence invalide : {L!r} (logements/an, strictement positive)")


def verifier_choix(valeur: str, possibles: tuple, nature: str) -> None:
    """Refuse une valeur hors de la liste autorisée, avec un message en français."""
    if valeur not in possibles:
        raise ValueError(f"{nature} inconnu(e) : « {valeur} » (attendu : {', '.join(possibles)})")


def _plage(debut: int, fin: int, pas: int) -> list[int]:
    """Cadences de début à fin incluse, par pas constant."""
    return list(range(debut, fin + 1, pas))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. Cadence, ressources et dimensionnement du site (SPEC §2.3)
# ═════════════════════════════════════════════════════════════════════════════════════════════

NOMS_POSTES_POD = ("Châssis", "Parois + étanchéité", "Plomberie-élec", "Finitions")


def minutes_ouverture_jour() -> float:
    """Temps d'ouverture quotidien (min) : équipes × heures × 60, soit 960 min."""
    return H("equipes_par_jour") * H("heures_par_equipe") * MINUTES_PAR_HEURE


def _ressource(libelle: str, cycle: float, takt: float) -> dict:
    """Nombre de ressources = ceil(cycle / (takt × charge max)) et charge qui en résulte."""
    nombre = arrondi_superieur(cycle / (takt * H("charge_max_poste")))
    return {"libelle": libelle, "cycle_min": cycle, "takt_min": takt, "nombre": nombre,
            "charge": cycle / (takt * nombre)}


def calcul_cadence(L: float) -> dict:
    """Traduit une cadence (logements/an) en flux journaliers, takts, ressources et charges."""
    _verifier_cadence(L)
    modules_jour = L * H("modules_par_logement") / H("jours_ouvres")
    pods_jour = L * H("pods_par_logement") / H("jours_ouvres")
    ouverture = minutes_ouverture_jour()
    temps_net = ouverture * H("trs")
    takt_module, takt_pod = temps_net / modules_jour, temps_net / pods_jour
    ressources = {
        "baies_assemblage": _ressource("Baies d'assemblage 3D",
                                       H("travail_assemblage_3d"), takt_module),
        "lignes_2d": _ressource("Lignes 2D robotisées", H("cycle_ligne_2d_module"), takt_module),
        "lignes_pods": _ressource("Lignes pods", max(H("cycle_pod_postes")), takt_pod),
        "postes_kitting": _ressource("Postes de kitting", H("temps_kitting"), takt_module),
    }
    return {
        "logements_an": L, "logements_jour": L / H("jours_ouvres"),
        "modules_jour": modules_jour, "pods_jour": pods_jour,
        "panneaux_jour": modules_jour * H("panneaux_par_module"),
        "temps_ouverture_min": ouverture, "temps_net_min": temps_net,
        "takt_module_min": takt_module, "takt_pod_min": takt_pod,
        "ressources": ressources,
        "postes_pods": ressources["lignes_pods"]["nombre"] * len(H("cycle_pod_postes")),
        "goulot": max(ressources, key=lambda cle: ressources[cle]["charge"]),
    }


def surfaces_utilisables() -> tuple[float, float]:
    """Surfaces utilisables (m²) du site seul puis du site + extension (× ratio utilisable)."""
    ratio = H("ratio_foncier_utilisable")
    return H("surface_site_actuel") * ratio, H("surface_totale") * ratio


def _quais(camions_jour: float, minutes_par_camion: float) -> int:
    """Quais = ceil(camions × temps par camion / (ouverture × occupation visée)) + secours."""
    capacite = minutes_ouverture_jour() * H("taux_occupation_quais")
    return arrondi_superieur(camions_jour * minutes_par_camion / capacite) + H("quais_secours")


def surfaces_ateliers(cadence: dict, schema: str) -> dict[str, float]:
    """Surfaces de production par zone (m²) : ligne 2D, ligne pods, assemblage ou consolidation.
    Schéma « satellites » : comme dans la présentation Avelis, l'usine mère fabrique les
    sous-ensembles (murs 2D et pods) ; elle les consolide en kits modules que les usines
    satellites assemblent en volumes."""
    ressources, coef = cadence["ressources"], H("coef_circulation")
    if schema == "unique":
        assemblage = ressources["baies_assemblage"]["nombre"] * H("m2_baie_assemblage") * coef
    else:  # satellites : consolidation des kits, comptée comme des postes pod
        assemblage = H("postes_consolidation") * H("m2_poste_pod") * coef
    return {
        "Ligne 2D robotisée": ressources["lignes_2d"]["nombre"] * H("m2_ligne_2d"),
        "Ligne pods": cadence["postes_pods"] * H("m2_poste_pod") * coef,
        "Assemblage 3D": assemblage,
    }


def _surface_stock_pf(unites_jour: float, schema: str) -> float:
    """Stock de produits finis (m²) : modules au sol (unique) ou kits modules (satellites)."""
    if schema == "unique":
        largeur, longueur, _ = H("dim_module")
        emprise = largeur * longueur
    else:
        emprise = H("m2_kit")
    return unites_jour * H("jours_stock_modules") * emprise * H("coef_circulation")


def _surfaces_site(L: float, schema: str, cadence: dict) -> dict[str, float]:
    """Surfaces nécessaires par poste (m²) selon SPEC §2.3."""
    coef = H("coef_circulation")
    tonnes_jour = L * H("tonnes_par_logement") / H("jours_ouvres")
    postes_kitting = cadence["ressources"]["postes_kitting"]["nombre"]
    return {
        "stock_matieres": tonnes_jour * H("jours_stock_matieres") / H("densite_stockage") * coef,
        "stock_pf": _surface_stock_pf(cadence["modules_jour"], schema),
        "production": sum(surfaces_ateliers(cadence, schema).values()),
        "kitting": postes_kitting * H("m2_poste_kitting") * coef,
        "voiries": (H("largeur_voirie") * H("longueur_voirie")
                    + math.pi * H("rayon_retournement") ** 2 + H("m2_parking_pl")),
        "bureaux": H("m2_bureaux"),
    }


def dimensionnement_site(L: float, schema: str) -> dict:
    """Camions, quais et surfaces (m²) nécessaires pour une cadence et un schéma industriel."""
    verifier_choix(schema, SCHEMAS, "schéma")
    cadence = calcul_cadence(L)
    tonnes_jour = L * H("tonnes_par_logement") / H("jours_ouvres")
    camions_entrants = tonnes_jour / H("charge_utile_camion")
    unites_jour = cadence["modules_jour"]  # un module, ou un kit module, par module produit
    par_camion = H("modules_par_convoi") if schema == "unique" else H("kits_par_camion_std")
    camions_sortants = unites_jour / par_camion
    surfaces = _surfaces_site(L, schema, cadence)
    site_seul, avec_extension = surfaces_utilisables()
    stockage = surfaces["stock_matieres"] + surfaces["stock_pf"]
    return {
        "logements_an": L, "schema": schema, "tonnes_jour": tonnes_jour,
        "camions_entrants_jour": camions_entrants,
        "quais_reception": _quais(camions_entrants, H("temps_quai_reception")),
        "unites_expediees_jour": unites_jour, "camions_sortants_jour": camions_sortants,
        "quais_expedition": _quais(camions_sortants, H("temps_chargement_module")),
        "surfaces": surfaces, "besoin_total": sum(surfaces.values()),
        "utilisable_site_seul": site_seul, "utilisable_avec_extension": avec_extension,
        "m2_stockage_pour_1000": stockage / L * LOGEMENTS_REFERENCE,
    }


LIBELLES_SURFACES = {
    "stock_matieres": "Stock matières",
    "stock_pf": "Stock produits finis",
    "production": "Production (ateliers)",
    "kitting": "Kitting",
    "voiries": "Voiries, retournement, parking PL",
    "bureaux": "Bureaux et pilotage",
}


def _cadence_max_admissible(cadences: list[int], besoins: list[float],
                            surface: float) -> int | None:
    """Plus grande cadence dont le besoin tient dans la surface, ou None."""
    admissibles = [L for L, besoin in zip(cadences, besoins) if besoin <= surface]
    return max(admissibles) if admissibles else None


def evolutivite(schema: str = "unique") -> dict:
    """Besoin total de 400 à 3 000 logements/an face aux surfaces utilisables (SPEC §2.3)."""
    verifier_choix(schema, SCHEMAS, "schéma")
    cadences = _plage(*PLAGE_EVOLUTIVITE)
    besoins = [dimensionnement_site(L, schema)["besoin_total"] for L in cadences]
    site_seul, avec_extension = surfaces_utilisables()
    return {
        "schema": schema, "cadences": cadences, "besoins": besoins,
        "utilisable_site_seul": site_seul, "utilisable_avec_extension": avec_extension,
        "cadence_max_site_seul": _cadence_max_admissible(cadences, besoins, site_seul),
        "cadence_max_avec_extension": _cadence_max_admissible(cadences, besoins, avec_extension),
    }


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. Géographie (H) et réseau national (SPEC §2.2, §2.3)
# ═════════════════════════════════════════════════════════════════════════════════════════════

TORCY = (46.767, 4.450)  # (lat, lon)

# Chantiers : (lat, lon, part de la demande). Les parts sont des HYPOTHÈSES, de somme 1.
CHANTIERS = {
    "Île-de-France": (48.86, 2.35, 0.30),
    "Lyon": (45.76, 4.84, 0.18),
    "Marseille": (43.30, 5.37, 0.09),
    "Lille": (50.63, 3.06, 0.09),
    "Strasbourg": (48.58, 7.75, 0.07),
    "Dijon": (47.32, 5.04, 0.09),
    "Bordeaux": (44.84, -0.58, 0.08),
    "Nantes": (47.22, -1.55, 0.10),
}

# Usines satellites d'assemblage (lat, lon) : HYPOTHÈSES
SATELLITES = {
    "Île-de-France": (48.85, 2.75),
    "Lyon-Sud": (45.65, 4.90),
    "Ouest-Tours": (47.39, 0.69),
}

# Contour simplifié de la France métropolitaine (lon, lat), de Dunkerque dans le sens antihoraire :
# Manche, Bretagne, Atlantique, Pyrénées, Méditerranée, Alpes, Jura, Rhin, frontière du Nord-Est.
CONTOUR_FRANCE = [
    (2.55, 51.09), (1.60, 50.88), (1.55, 50.15), (0.20, 49.70), (-0.20, 49.30), (-1.25, 49.68),
    (-1.94, 49.72), (-1.55, 48.65), (-2.75, 48.55), (-3.55, 48.80), (-4.77, 48.36), (-4.35, 47.80),
    (-3.35, 47.70), (-2.50, 47.28), (-1.45, 46.25), (-1.15, 45.60), (-1.25, 44.60), (-1.75, 43.38),
    (-0.70, 42.90), (0.70, 42.75), (1.75, 42.50), (3.17, 42.43), (3.05, 43.00), (3.70, 43.40),
    (4.60, 43.38), (5.30, 43.20), (6.10, 43.05), (7.50, 43.78), (7.00, 44.30), (6.95, 45.20),
    (6.95, 45.90), (6.15, 46.25), (7.00, 47.45), (7.59, 47.59), (7.80, 48.57), (8.23, 48.97),
    (6.40, 49.47), (4.85, 50.15), (4.05, 50.33), (3.30, 50.50), (3.13, 50.78),
]


def _aretes(polygone: list) -> list:
    """Arêtes (a, b) d'un polygone, le dernier sommet étant relié au premier."""
    return list(zip(polygone, polygone[1:] + polygone[:1]))


def point_dans_polygone(point: tuple, polygone: list) -> bool:
    """Test du rayon horizontal (règle pair-impair). Un point posé sur un bord gauche ou bas est
    intérieur, sur un bord droit ou haut extérieur : un point de la frontière commune de deux
    polygones adjacents appartient à un seul des deux."""
    x, y = point
    dedans = False
    for (x1, y1), (x2, y2) in _aretes(polygone):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dedans = not dedans
    return dedans


def haversine_km(a: tuple, b: tuple) -> float:
    """Distance à vol d'oiseau (km) entre deux points (lat, lon, …) exprimés en degrés."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * RAYON_TERRE_KM * math.asin(math.sqrt(h))


def distance_route_km(a: tuple, b: tuple) -> float:
    """Distance routière estimée (km) : haversine × coefficient de détour (SPEC §7)."""
    return haversine_km(a, b) * H("coef_detour_route")


def part_demande(chantier: str) -> float:
    """Part de la demande nationale du chantier (hypothèse)."""
    return CHANTIERS[chantier][2]


def satellite_le_plus_proche(position: tuple) -> str:
    """Nom du satellite le plus proche d'une position (lat, lon, …)."""
    return min(SATELLITES, key=lambda nom: haversine_km(position, SATELLITES[nom]))


def cout_fixe_satellite_an() -> float:
    """Coût fixe annuel d'un satellite (€/an) : amortissement de l'investissement + frais fixes."""
    capex_annuel = H("capex_satellite") / H("amortissement_ans")
    return (capex_annuel + H("frais_fixes_satellite")) * EUROS_PAR_MILLION


def _troncon(de: str, vers: str, depart: tuple, arrivee: tuple, mode: str) -> dict:
    """Tronçon routier : mode « convoi » (modules 3D) ou « semi » (kits modules)."""
    return {"de": de, "vers": vers, "depart": depart[:2], "arrivee": arrivee[:2], "mode": mode,
            "distance_km": distance_route_km(depart, arrivee)}


def _km_factures(troncon: dict) -> float:
    """Kilomètres facturés par module transporté sur un tronçon, retours compris."""
    if troncon["mode"] == "convoi":
        return troncon["distance_km"] * H("coef_retour_vide_convoi") / H("modules_par_convoi")
    return troncon["distance_km"] * H("coef_retour_semi") / H("kits_par_camion_std")


def _cout_troncon(troncon: dict) -> float:
    """Coût de transport (€) d'un module sur un tronçon."""
    cout_km = H("cout_km_convoi") if troncon["mode"] == "convoi" else H("cout_km_semi")
    return _km_factures(troncon) * cout_km


def _duree_troncon(troncon: dict) -> float:
    """Durée de trajet (h) d'un tronçon."""
    vitesse = H("vitesse_convoi") if troncon["mode"] == "convoi" else H("vitesse_semi")
    return troncon["distance_km"] / vitesse


def _cout_itineraire(itineraire: dict) -> float:
    """Coût variable de transport (€) d'un module sur tout son itinéraire."""
    return sum(_cout_troncon(troncon) for troncon in itineraire["troncons"])


def _itineraire(chantier: str, option: str, variante: str) -> dict:
    """Itinéraire d'un module : direct depuis Torcy (A) ou via le satellite le plus proche du
    chantier (B). En variante hybride, B garde la livraison directe si elle coûte moins cher."""
    position = CHANTIERS[chantier]
    direct = {"satellite": None,
              "troncons": [_troncon("Torcy", chantier, TORCY, position, "convoi")]}
    if option == "A":
        return direct
    nom = satellite_le_plus_proche(position)
    etape = f"Satellite {nom}"
    via = {"satellite": nom,
           "troncons": [_troncon("Torcy", etape, TORCY, SATELLITES[nom], "semi"),
                        _troncon(etape, chantier, SATELLITES[nom], position, "convoi")]}
    if variante == "hybride" and _cout_itineraire(direct) < _cout_itineraire(via):
        return direct
    return via


def itineraires(option: str, variante: str = "proche") -> dict[str, dict]:
    """Itinéraire de chaque chantier pour l'option « A » (usine unique) ou « B » (satellites)."""
    verifier_choix(option, ("A", "B"), "option")
    verifier_choix(variante, VARIANTES, "variante")
    return {chantier: _itineraire(chantier, option, variante) for chantier in CHANTIERS}


def _moyenne_ponderee(routes: dict, mesure_troncon) -> float:
    """Σ des chantiers de (part × Σ des tronçons de mesure_troncon), par module."""
    return sum(part_demande(chantier) * sum(mesure_troncon(t) for t in route["troncons"])
               for chantier, route in routes.items())


def _stocks_tampons(L: float, routes: dict) -> dict[str, float]:
    """Kits en stock tampon par satellite : jours_stock_satellite × kits reçus par jour."""
    kits_jour = L * H("modules_par_logement") / H("jours_ouvres")
    stocks: dict[str, float] = {}
    for chantier, route in routes.items():
        if route["satellite"]:
            kits = H("jours_stock_satellite") * kits_jour * part_demande(chantier)
            stocks[route["satellite"]] = stocks.get(route["satellite"], 0.0) + kits
    return stocks


def _flux(routes: dict) -> list[dict]:
    """Tronçons agrégés et part de la demande qu'ils portent (épaisseur sur les cartes)."""
    flux: dict[tuple, dict] = {}
    for chantier, route in routes.items():
        for troncon in route["troncons"]:
            entree = flux.setdefault((troncon["de"], troncon["vers"]), {**troncon, "part": 0.0})
            entree["part"] += part_demande(chantier)
    return list(flux.values())


def _bilan_option(L: float, routes: dict, libelle: str) -> dict:
    """Indicateurs annuels d'une option de réseau (SPEC §2.3)."""
    modules_an = L * H("modules_par_logement")
    satellites = sorted({route["satellite"] for route in routes.values() if route["satellite"]})
    couts_fixes = len(satellites) * cout_fixe_satellite_an()
    km_an = _moyenne_ponderee(routes, _km_factures) * modules_an
    cout_module = _moyenne_ponderee(routes, _cout_troncon)
    cout_total = cout_module * modules_an + couts_fixes
    return {
        "libelle": libelle, "itineraires": routes, "satellites_utilises": satellites,
        "km_an": km_an, "cout_transport_an": cout_module * modules_an,
        "co2_t_an": km_an * H("co2_km_pl") / KG_PAR_TONNE,
        "distance_moyenne_km": _moyenne_ponderee(routes, lambda t: t["distance_km"]),
        "delai_moyen_h": _moyenne_ponderee(routes, _duree_troncon),
        "couts_fixes_an": couts_fixes, "cout_total_an": cout_total,
        "cout_par_logement": cout_total / L, "cout_variable_par_module": cout_module,
        "stocks_tampons": _stocks_tampons(L, routes),
        "part_directe": sum(part_demande(c) for c, r in routes.items() if r["satellite"] is None),
        "flux": _flux(routes),
    }


def _recommandation(L: float, a: dict, b: dict, variante: str) -> str:
    """Recommandation textuelle : option la moins chère par logement, puis point de bascule."""
    (code, meilleure), (code_autre, autre) = sorted(
        (("A", a), ("B", b)), key=lambda option: option[1]["cout_par_logement"])
    texte = (f"À {formater_nombre(L)} logements/an, l'option {code} "
             f"({meilleure['libelle'].lower()}) est la moins chère : "
             f"{formater_nombre(meilleure['cout_par_logement'])} €/logement contre "
             f"{formater_nombre(autre['cout_par_logement'])} € pour l'option {code_autre}.")
    bascule = point_bascule(variante)
    if bascule is None:
        texte += (" Le réseau avec satellites reste plus cher jusqu'à "
                  f"{formater_nombre(PLAGE_SENSIBILITE[1])} logements/an.")
    else:
        texte += (" Le réseau avec satellites devient moins cher que l'usine unique à partir de "
                  f"{formater_nombre(bascule)} logements/an (variante « {variante} »).")
    if variante == "hybride":
        texte += (f" {formater_pourcentage(b['part_directe'])} de la demande est livrée en direct "
                  "depuis Torcy, qui doit donc garder une capacité d'assemblage 3D.")
    return texte


def comparaison_reseau(L: float, variante: str = "proche") -> dict:
    """Compare l'usine unique (A) et l'usine mère + satellites (B) à une cadence donnée."""
    _verifier_cadence(L)
    verifier_choix(variante, VARIANTES, "variante")
    a = _bilan_option(L, itineraires("A"), "Usine unique")
    b = _bilan_option(L, itineraires("B", variante), "Usine mère + satellites")
    return {"logements_an": L, "variante": variante, "A": a, "B": b,
            "part_directe": b["part_directe"],
            "recommandation": _recommandation(L, a, b, variante)}


def sensibilite_reseau(variante: str) -> dict:
    """Coût par logement (€) de A et de B pour des cadences de 400 à 8 000 logements/an."""
    routes_a, routes_b = itineraires("A"), itineraires("B", variante)
    cadences = _plage(*PLAGE_SENSIBILITE)
    return {"variante": variante, "cadences": cadences,
            "A": [_bilan_option(L, routes_a, "A")["cout_par_logement"] for L in cadences],
            "B": [_bilan_option(L, routes_b, "B")["cout_par_logement"] for L in cadences]}


def point_bascule(variante: str) -> int | None:
    """Plus petite cadence (pas de 50) dès laquelle B coûte moins cher que A, sinon None."""
    s = sensibilite_reseau(variante)
    return next((L for L, a, b in zip(s["cadences"], s["A"], s["B"]) if b < a), None)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3 bis. Paramétrage par l'utilisateur (onglet « Paramètres » de l'application)
# ═════════════════════════════════════════════════════════════════════════════════════════════

# Valeurs d'origine, rétablies par les boutons « Valeur par défaut »
HYPOTHESES_DEFAUT = {cle: entree[0] for cle, entree in HYPOTHESES.items()}
CHANTIERS_DEFAUT = dict(CHANTIERS)
SATELLITES_DEFAUT = dict(SATELLITES)

BORNES_CARTE = {"lon": (-5.4, 8.8), "lat": (42.1, 51.4)}  # cadre des cartes du réseau (degrés)
TOLERANCE_PARTS = 1e-6  # écart toléré entre la somme des parts des chantiers et 1
UNITE_SANS_DIMENSION = "—"  # unité des taux : une valeur par défaut ≤ 1 y reste bornée à 1

# Villes proposées pour placer un chantier ou une usine satellite : (lat, lon) en degrés
VILLES_FRANCE = {
    "Aix-en-Provence": (43.529, 5.447), "Amiens": (49.894, 2.296), "Angers": (47.478, -0.563),
    "Annecy": (45.899, 6.129), "Avignon": (43.949, 4.806), "Bayonne": (43.493, -1.475),
    "Besançon": (47.238, 6.024), "Bordeaux": (44.838, -0.579), "Bourges": (47.081, 2.399),
    "Brest": (48.390, -4.486), "Caen": (49.183, -0.371), "Chalon-sur-Saône": (46.781, 4.854),
    "Chambéry": (45.564, 5.918), "Clermont-Ferrand": (45.778, 3.087), "Dijon": (47.322, 5.041),
    "Grenoble": (45.188, 5.724), "La Rochelle": (46.160, -1.151), "Le Creusot": (46.801, 4.425),
    "Le Havre": (49.494, 0.108), "Le Mans": (48.006, 0.199), "Lille": (50.629, 3.057),
    "Limoges": (45.834, 1.262), "Lyon": (45.764, 4.836), "Mâcon": (46.307, 4.828),
    "Marseille": (43.296, 5.370), "Metz": (49.119, 6.176), "Montpellier": (43.611, 3.877),
    "Mulhouse": (47.750, 7.336), "Nancy": (48.692, 6.184), "Nantes": (47.218, -1.554),
    "Nice": (43.710, 7.262), "Nîmes": (43.837, 4.360), "Orléans": (47.903, 1.909),
    "Paris": (48.857, 2.352), "Pau": (43.295, -0.371), "Perpignan": (42.699, 2.895),
    "Poitiers": (46.580, 0.340), "Reims": (49.258, 4.032), "Rennes": (48.117, -1.678),
    "Rouen": (49.443, 1.099), "Saint-Étienne": (45.440, 4.387), "Strasbourg": (48.573, 7.752),
    "Toulon": (43.124, 5.928), "Toulouse": (43.605, 1.444), "Tours": (47.394, 0.685),
    "Troyes": (48.297, 4.074), "Valence": (44.933, 4.892),
}


def _anomalie_nombre(valeur: Any, defaut: Any, borne_a_un: bool) -> str | None:
    """Motif de refus d'un nombre : type de la valeur par défaut (entier ou réel), fini,
    strictement positif, au plus 1 pour un taux ; None s'il est acceptable."""
    if isinstance(valeur, bool) or not isinstance(valeur, numbers.Real):
        return "nombre attendu"
    if isinstance(defaut, int) and not isinstance(valeur, int):
        return "nombre entier attendu"
    if not math.isfinite(valeur) or valeur <= 0:
        return "nombre strictement positif attendu"
    if borne_a_un and valeur > 1:
        return "taux compris entre 0 et 1 attendu"
    return None


def anomalies_hypothese(cle: str, valeur: Any) -> list[str]:
    """Motifs de refus d'une nouvelle valeur d'hypothèse (liste vide si elle est acceptable).
    Une séquence garde le nombre d'éléments de sa valeur par défaut ; un couple (min, max) reste
    ordonné."""
    if cle not in HYPOTHESES_DEFAUT:
        return [f"hypothèse inconnue : « {cle} »"]
    defaut, unite = HYPOTHESES_DEFAUT[cle], HYPOTHESES[cle][1]
    if isinstance(defaut, tuple):
        if not isinstance(valeur, tuple) or len(valeur) != len(defaut):
            return [f"« {cle} » : {len(defaut)} valeurs attendues"]
        paires = list(zip(valeur, defaut))
    else:
        paires = [(valeur, defaut)]
    motifs = {_anomalie_nombre(v, d, unite == UNITE_SANS_DIMENSION and d <= 1) for v, d in paires}
    anomalies = [f"« {cle} » : {motif}" for motif in sorted(motifs - {None})]
    if not anomalies and isinstance(defaut, tuple) and len(defaut) == 2 and valeur[0] > valeur[1]:
        anomalies.append(f"« {cle} » : le minimum dépasse le maximum")
    return anomalies


def anomalies_lieu(genre: str, nom: str, lat: float, lon: float) -> list[str]:
    """Nom non vide et position dans le cadre des cartes de France."""
    anomalies = [] if nom.strip() else [f"{genre} sans nom"]
    (lon_min, lon_max), (lat_min, lat_max) = BORNES_CARTE["lon"], BORNES_CARTE["lat"]
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        bornes = [formater_nombre(b, 1) for b in (lat_min, lat_max, lon_min, lon_max)]
        anomalies.append(f"{genre} « {nom} » : position hors de la France métropolitaine "
                         f"(latitude {bornes[0]} à {bornes[1]}, longitude {bornes[2]} à "
                         f"{bornes[3]})")
    return anomalies


def anomalies_reseau(chantiers: dict, satellites: dict) -> list[str]:
    """Motifs de refus d'un réseau : au moins un chantier et une usine satellite, positions en
    France, parts des chantiers positives et de somme 100 %."""
    anomalies = [] if chantiers else ["au moins un chantier est nécessaire"]
    anomalies += [] if satellites else ["au moins une usine satellite est nécessaire"]
    for nom, (lat, lon, part) in chantiers.items():
        anomalies += anomalies_lieu("Chantier", nom, lat, lon)
        if not 0 < part <= 1:
            anomalies.append(f"Chantier « {nom} » : part comprise entre 0 et 100 % attendue")
    total = sum(part for _, _, part in chantiers.values())
    if chantiers and abs(total - 1) > TOLERANCE_PARTS:
        anomalies.append(f"Parts des chantiers : total de {formater_pourcentage(total, 2)} "
                         f"au lieu de {formater_pourcentage(1)}")
    for nom, (lat, lon) in satellites.items():
        anomalies += anomalies_lieu("Usine satellite", nom, lat, lon)
    return anomalies


def etat_parametres() -> dict:
    """Valeurs en vigueur : hypothèses, chantiers et usines satellites (copies)."""
    return {"hypotheses": {cle: entree[0] for cle, entree in HYPOTHESES.items()},
            "chantiers": dict(CHANTIERS), "satellites": dict(SATELLITES)}


def parametres_par_defaut() -> dict:
    """Valeurs d'origine, au même format qu'etat_parametres()."""
    return {"hypotheses": dict(HYPOTHESES_DEFAUT), "chantiers": dict(CHANTIERS_DEFAUT),
            "satellites": dict(SATELLITES_DEFAUT)}


def appliquer_parametres(hypotheses: dict, chantiers: dict, satellites: dict) -> None:
    """Remplace les valeurs en vigueur après les avoir toutes contrôlées ; ValueError (un motif
    par ligne) sans rien changer si l'une est refusée. Les calculs suivants les utilisent."""
    anomalies = [motif for cle, valeur in hypotheses.items()
                 for motif in anomalies_hypothese(cle, valeur)]
    anomalies += anomalies_reseau(chantiers, satellites)
    if anomalies:
        raise ValueError("\n".join(anomalies))
    for cle, valeur in hypotheses.items():
        HYPOTHESES[cle] = (_convertir(valeur, HYPOTHESES_DEFAUT[cle]), *HYPOTHESES[cle][1:])
    CHANTIERS.clear()
    CHANTIERS.update({nom: tuple(map(float, lieu)) for nom, lieu in chantiers.items()})
    SATELLITES.clear()
    SATELLITES.update({nom: tuple(map(float, lieu)) for nom, lieu in satellites.items()})


def _convertir(valeur: Any, defaut: Any) -> Any:
    """Valeur au type de sa valeur par défaut (un entier saisi pour un réel devient réel)."""
    if isinstance(defaut, tuple):
        return tuple(_convertir(v, d) for v, d in zip(valeur, defaut))
    return float(valeur) if isinstance(defaut, float) else valeur


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. Géométrie du site en mètres, reconstituée d'après les plans Avelis (SPEC §2.4)
# ═════════════════════════════════════════════════════════════════════════════════════════════

# Contours relevés sur le schéma d'emprise fourni par l'équipe (2026-11-03), qui remplace le
# §2.4 : pointe au nord-est, longue limite en diagonale au nord-ouest le long de la D601, bande
# au sud. L'échelle est calée sur la surface du site actuel ; l'extension, plus large sur le
# schéma (+ 8 %), est resserrée d'est en ouest pour retrouver sa surface.
# Le cul-de-sac de la Rue Alain Bombard (encoche, côté est du site) appartient à l'extension.
SITE_ACTUEL = [(236, 312), (237, 180), (214, 177), (208, 171), (195, 165), (195, 151),
               (243, 150), (244, 89), (235, 0), (169, 5), (171, 85), (0, 91), (22, 153),
               (48, 202), (83, 236), (150, 283)]  # ≈ 42 786 m²
EXTENSION = [(195, 151), (195, 165), (208, 171), (214, 177), (237, 180), (305, 172), (319, 187),
             (342, 199), (365, 221), (387, 237), (408, 240), (429, 254), (441, 233), (457, 231),
             (455, 148), (447, 105), (441, 76), (244, 89), (243, 150)]  # ≈ 27 443 m²
# Route qui longe l'extension à l'est (du sud, index 0, au nord, index -1). Le portail est posé
# sur la limite est, en face du carrefour avec la Rue Alain Bombard : un camion au portail est
# sur le site, un pas plus loin il est sur la route publique.
ROUTE_PUBLIQUE = [(516, -6), (518, 51), (519, 79), (512, 115), (504, 129), (487, 143),
                  (474, 150), (464, 157), (466, 186), (464, 214), (462, 240), (457, 262)]
PORTAIL = (455, 157)
# Rue Alain Bombard, du carrefour au cul-de-sac : voie publique de l'implantation actuelle (la
# route traverse le foncier disponible) ; l'implantation proposée la recouvre de bâtiments.
RUE_ALAIN_BOMBARD = [PORTAIL, (440, 157), (342, 164), (245, 169), (222, 170)]
# Implantation actuelle (site seul) : portail à l'entrée du site, sur sa limite au bout du
# cul-de-sac, et non à l'entrée de l'extension non utilisée (demande de l'équipe, 2026-11-04).
# Les camions y viennent par la route publique puis la Rue Alain Bombard (`acces`).
PORTAIL_SITE_ACTUEL = (222, 179)  # juste au nord de la limite (y ≈ 178)

# Quais de réception sur la façade est de la Réception (demande de l'équipe, 2026-11-04), les
# uns au-dessus des autres vers le nord ; une bretelle les dessert depuis la voirie interne, en
# biais pour que les camions y entrent et en sortent en marche avant.
QUAI_RECEPTION = (142, 207)  # premier quai, à 2 m du mur est (x = 140)
PAS_QUAIS_RECEPTION = (0, 5)  # d'un quai au suivant (m)
# La bretelle passe à l'est des camions à quai (16,5 m de long), sans les toucher (2026-11-04).
BRETELLE_RECEPTION = [(162, 196), (162, 233)]  # de la voirie au nord des quais
# Quais d'expédition des implantations avec extension : camions garés en long dans la case
# d'expédition, hors de la voirie (demande de l'équipe, 2026-11-04) ; venus du portail, ils font
# d'abord demi-tour à l'aire de retournement, pour repartir en marche avant vers le portail.
PAS_QUAIS_EXPEDITION_EN_LONG = (22, 0)
# Places du parking PL (largeur × longueur, m), en rangées nord-sud dans la zone
PLACE_PARKING_PL = (4.5, 17)
# Parking des véhicules légers (personnel, visiteurs) à l'est du stock matières, rectangle
# (x, y, largeur, profondeur) ; voie d'accès depuis la voirie interne, qui longe son côté est.
PARKING_VL = {"zone": (206, 246, 20, 48), "voie": [(222, 196), (229, 196), (229, 291)]}

DECALAGE_TEST_M = 0.01  # décalage (m) de part et d'autre d'une arête : est-elle intérieure ?
TOLERANCE_GEOMETRIE = 1e-9  # tolérance relative de colinéarité

# Couleur de remplissage de chaque catégorie de zone
CATEGORIES_ZONES = {
    "Accueil et pilotage": "#dfe4ec",
    "Logistique amont": "#cfe3f3",
    "Production": "#fbe3c4",
    "Logistique aval": "#e6dbf0",
    "Réserve foncière": "#e3f0da",
}


def _zone(x: float, y: float, largeur: float, hauteur: float, categorie: str) -> tuple:
    """Zone (x, y, largeur, hauteur, couleur, catégorie), le coin bas-gauche étant en (x, y)."""
    return (x, y, largeur, hauteur, CATEGORIES_ZONES[categorie], categorie)


# Zones replacées dans le contour du schéma (dimensions du §2.4 conservées, sauf la Réserve) :
# accès par l'encoche de la Rue Alain Bombard, voirie interne d'est en ouest à y = 196.
_ZONES_COMMUNES = {
    "Parking PL": _zone(186, 200, 40, 34, "Accueil et pilotage"),
    "Bureaux / pilotage": _zone(194, 108, 40, 38, "Accueil et pilotage"),
    "Réception": _zone(80, 202, 60, 30, "Logistique amont"),
    "Stock matières": _zone(130, 238, 74, 30, "Logistique amont"),
}
VOIRIE_INTERNE = [(60, 196), (222, 196), (222, 170)]  # jusqu'au cul-de-sac de la rue
RETOURNEMENT = (220, 163)  # aire de retournement : le cul-de-sac de la Rue Alain Bombard

IMPLANTATION_PROPOSEE = "Proposée : Torcy + extension (flux en U)"
IMPLANTATION_ACTUELLE = "Actuelle : site seul (sans extension)"

IMPLANTATIONS = {
    IMPLANTATION_PROPOSEE: {
        "zones": {
            **_ZONES_COMMUNES,
            "Kitting": _zone(116, 146, 70, 44, "Logistique amont"),
            "Ligne 2D robotisée": _zone(46, 146, 64, 44, "Production"),
            "Ligne pods": _zone(50, 94, 140, 46, "Production"),
            "Assemblage 3D": _zone(246, 92, 124, 72, "Production"),
            "Contrôle final": _zone(372, 92, 36, 72, "Production"),
            "Stock produits finis": _zone(410, 96, 34, 70, "Logistique aval"),
            "Expédition": _zone(335, 168, 100, 10, "Logistique aval"),
            # Bande sud du site : 62 × 80 m (104 m de haut au §2.4, la bande est plus courte)
            "Réserve 2030+": _zone(172, 6, 62, 80, "Réserve foncière"),
        },
        "polygones_site": (SITE_ACTUEL, EXTENSION),
        "extension_utilisee": True,
        # La Rue Alain Bombard est recouverte : la voirie longe le nord de l'extension.
        "voirie": [*VOIRIE_INTERNE, (300, 170), (330, 183), (448, 186), PORTAIL],
        "portail": PORTAIL,
        "acces": [PORTAIL],  # de la route publique au portail (voies publiques)
        "bretelles": [BRETELLE_RECEPTION],
        "parking_vl": PARKING_VL,
        "retournement": RETOURNEMENT,  # centre ; rayon lu à l'usage (paramétrable)
        "quai_reception": QUAI_RECEPTION,
        "pas_quai_reception": PAS_QUAIS_RECEPTION,
        "quai_expedition": (352, 173),  # au milieu de la case (y de 168 à 178)
        "pas_quai_expedition": PAS_QUAIS_EXPEDITION_EN_LONG,
        "expedition_en_long": True,
        "zones_partagees": {},
    },
    IMPLANTATION_ACTUELLE: {
        "zones": {
            **_ZONES_COMMUNES,
            "Kitting": _zone(146, 150, 40, 44, "Logistique amont"),
            "Ligne 2D robotisée": _zone(46, 150, 50, 44, "Production"),
            "Ligne pods": _zone(172, 58, 62, 48, "Production"),
            "Assemblage 3D": _zone(30, 94, 140, 50, "Production"),
            "Contrôle final": _zone(100, 150, 42, 44, "Production"),
            "Stock produits finis": _zone(172, 6, 62, 50, "Logistique aval"),
            # même rectangle que la Réception : quais partagés
            "Expédition": _zone(*_ZONES_COMMUNES["Réception"][:4], "Logistique aval"),
        },
        "polygones_site": (SITE_ACTUEL,),
        "extension_utilisee": False,
        # Les camions suivent la Rue Alain Bombard, à travers le foncier disponible, jusqu'au
        # portail du site ; la voirie interne part du portail.
        "voirie": [*VOIRIE_INTERNE[:-1], PORTAIL_SITE_ACTUEL],
        "portail": PORTAIL_SITE_ACTUEL,
        "acces": [*RUE_ALAIN_BOMBARD, PORTAIL_SITE_ACTUEL],
        "bretelles": [BRETELLE_RECEPTION],
        "parking_vl": PARKING_VL,
        "retournement": RETOURNEMENT,  # centre ; rayon lu à l'usage (paramétrable)
        "quai_reception": QUAI_RECEPTION,
        "pas_quai_reception": PAS_QUAIS_RECEPTION,
        "quai_expedition": QUAI_RECEPTION,
        "pas_quai_expedition": PAS_QUAIS_RECEPTION,
        "zones_partagees": {"Expédition": "Réception"},
    },
}

# Implantation optimisée (demande de l'équipe du 2026-11-04), sur le même foncier que la proposée
# et avec la même voirie : zones à la taille du besoin à 1 500 logements/an, lignes 2D et pods
# accolées à l'ouest de la halle d'assemblage (le goulot), bureaux à l'accueil près du portail,
# expédition au-dessus du stock de produits finis, place réservée pour les lignes de 2030.
# Les lignes sont l'une au-dessus de l'autre, le centre de la ligne pods à l'ouest de celui de la
# ligne 2D : leurs chemins en L depuis le kitting et vers l'assemblage ne se croisent pas.
IMPLANTATION_OPTIMISEE = "Optimisée : Torcy + extension"
IMPLANTATIONS[IMPLANTATION_OPTIMISEE] = {
    "zones": {
        **_ZONES_COMMUNES,
        "Bureaux / pilotage": _zone(380, 192, 40, 38, "Accueil et pilotage"),
        "Kitting": _zone(150, 154, 48, 34, "Logistique amont"),
        "Ligne 2D robotisée": _zone(132, 114, 112, 36, "Production"),
        "Ligne pods": _zone(132, 92, 90, 20, "Production"),
        "Assemblage 3D": _zone(246, 92, 124, 72, "Production"),
        "Contrôle final": _zone(372, 92, 36, 72, "Production"),
        "Stock produits finis": _zone(410, 96, 34, 70, "Logistique aval"),
        "Expédition": _zone(400, 168, 45, 10, "Logistique aval"),
        "Réserve 2030+": _zone(172, 6, 62, 80, "Réserve foncière"),
        "Réserve lignes 2030+": _zone(45, 96, 82, 88, "Réserve foncière"),
    },
    "polygones_site": (SITE_ACTUEL, EXTENSION),
    "extension_utilisee": True,
    "voirie": IMPLANTATIONS[IMPLANTATION_PROPOSEE]["voirie"],
    "portail": PORTAIL,
    "acces": [PORTAIL],
    "bretelles": [BRETELLE_RECEPTION],
    "parking_vl": PARKING_VL,
    "retournement": RETOURNEMENT,  # centre ; rayon lu à l'usage (paramétrable)
    "quai_reception": QUAI_RECEPTION,
    "pas_quai_reception": PAS_QUAIS_RECEPTION,
    "quai_expedition": (412, 173),
    "pas_quai_expedition": (21, 0),  # case plus courte (45 m)
    "expedition_en_long": True,
    "zones_partagees": {},
}

# Gammes logistiques : zones traversées, dans l'ordre
GAMMES = {
    "pod": ("Réception", "Stock matières", "Kitting", "Ligne pods", "Assemblage 3D"),
    "2D": ("Kitting", "Ligne 2D robotisée", "Assemblage 3D"),
    "module": ("Assemblage 3D", "Contrôle final", "Stock produits finis", "Expédition"),
}


def _implantation(implantation: str | dict) -> dict:
    """Implantation donnée par son nom (clé d'IMPLANTATIONS) ou déjà sous forme de dict."""
    if isinstance(implantation, dict):
        return implantation
    verifier_choix(implantation, tuple(IMPLANTATIONS), "implantation")
    return IMPLANTATIONS[implantation]


def aire_polygone(points: list) -> float:
    """Aire (m²) d'un polygone simple par la formule du lacet."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in _aretes(points))) / 2


def centre_zone(zone: tuple) -> tuple[float, float]:
    """Centre (x, y) d'une zone rectangulaire."""
    x, y, largeur, hauteur = zone[:4]
    return (x + largeur / 2, y + hauteur / 2)


def aire_zone(zone: tuple) -> float:
    """Surface dessinée (m²) d'une zone rectangulaire."""
    _, _, largeur, hauteur = zone[:4]
    return largeur * hauteur


def zones_se_chevauchent(a: tuple, b: tuple) -> bool:
    """Vrai si les intérieurs de deux rectangles se recouvrent (des zones contiguës ne se
    chevauchent pas)."""
    ax, ay, al, ah = a[:4]
    bx, by, bl, bh = b[:4]
    return ax < bx + bl and bx < ax + al and ay < by + bh and by < ay + ah


def _segment_traverse_rectangle(a: tuple, b: tuple, rectangle: tuple) -> bool:
    """Vrai si le segment [a, b] passe par l'intérieur ouvert du rectangle : découpage de
    Liang-Barsky, puis test strict du milieu de la partie conservée."""
    x0, y0, largeur, hauteur = rectangle[:4]
    dx, dy = b[0] - a[0], b[1] - a[1]
    t_entree, t_sortie = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x0 + largeur - a[0]),
                 (-dy, a[1] - y0), (dy, y0 + hauteur - a[1])):
        if p == 0:
            if q < 0:
                return False
        elif p < 0:
            t_entree = max(t_entree, q / p)
        else:
            t_sortie = min(t_sortie, q / p)
    if t_entree > t_sortie:
        return False
    t = (t_entree + t_sortie) / 2
    xm, ym = a[0] + t * dx, a[1] + t * dy
    return x0 < xm < x0 + largeur and y0 < ym < y0 + hauteur


def _parametre(p: tuple, a: tuple, b: tuple) -> float:
    """Position de la projection de p sur la droite (a, b) : 0 en a, 1 en b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)


def _sur_segment(p: tuple, a: tuple, b: tuple) -> bool:
    """Vrai si p est sur le segment [a, b], strictement entre ses extrémités."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    vectoriel = dx * (p[1] - a[1]) - dy * (p[0] - a[0])
    return (abs(vectoriel) <= TOLERANCE_GEOMETRIE * (dx * dx + dy * dy)
            and 0 < _parametre(p, a, b) < 1)


def _morceaux_arete(a: tuple, b: tuple, sommets: list) -> list:
    """Découpe l'arête [a, b] aux sommets (d'autres polygones) qui sont posés dessus."""
    if a == b:
        return []
    poses = sorted({p for p in sommets if _sur_segment(p, a, b)},
                   key=lambda p: _parametre(p, a, b))
    points = [a, *poses, b]
    return list(zip(points, points[1:]))


def _point_dans_site(point: tuple, polygones: tuple) -> bool:
    """Vrai si le point est dans l'un des polygones du site."""
    return any(point_dans_polygone(point, polygone) for polygone in polygones)


def _arete_interieure(p: tuple, q: tuple, polygones: tuple) -> bool:
    """Vrai si les deux côtés du milieu de [p, q] sont dans le site (arête commune à deux
    polygones adjacents, donc intérieure à leur union)."""
    milieu = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    longueur = math.dist(p, q)
    nx = (p[1] - q[1]) / longueur * DECALAGE_TEST_M
    ny = (q[0] - p[0]) / longueur * DECALAGE_TEST_M
    return (_point_dans_site((milieu[0] + nx, milieu[1] + ny), polygones)
            and _point_dans_site((milieu[0] - nx, milieu[1] - ny), polygones))


def aretes_frontiere(polygones: tuple) -> list:
    """Arêtes de la frontière extérieure de l'union de polygones adjacents ; les arêtes, ou
    morceaux d'arêtes, communs à deux polygones sont retirés."""
    sommets = [sommet for polygone in polygones for sommet in polygone]
    return [(p, q) for polygone in polygones for a, b in _aretes(polygone)
            for p, q in _morceaux_arete(a, b, sommets)
            if not _arete_interieure(p, q, polygones)]


def rectangle_dans_site(zone: tuple, polygones: tuple) -> bool:
    """Vrai si la zone (x, y, largeur, hauteur, …) est entièrement incluse dans l'union des
    polygones : son centre est dans le site et aucune arête de frontière ne traverse son
    intérieur. Une zone posée contre la limite reste incluse."""
    if not _point_dans_site(centre_zone(zone), polygones):
        return False
    return not any(_segment_traverse_rectangle(a, b, zone)
                   for a, b in aretes_frontiere(polygones))


def _zones_des_gammes() -> list[str]:
    """Zones citées par au moins une gamme, dans l'ordre de première apparition."""
    return list(dict.fromkeys(zone for gamme in GAMMES.values() for zone in gamme))


def _paire_partagee(implantation: dict, a: str, b: str) -> bool:
    """Vrai si l'une des deux zones est déclarée partagée avec l'autre (quais communs)."""
    partagees = implantation["zones_partagees"]
    return partagees.get(a) == b or partagees.get(b) == a


def verifier_implantation(implantation: str | dict) -> list[str]:
    """Contrôle géométrique (SPEC §2.4) : zones des gammes présentes, chaque zone incluse dans le
    site retenu, aucun chevauchement (zones partagées exemptées). Renvoie la liste des anomalies,
    vide si l'implantation est conforme."""
    impl = _implantation(implantation)
    zones, polygones = impl["zones"], impl["polygones_site"]
    anomalies = [f"Zone manquante : « {nom} » (citée par les gammes)"
                 for nom in _zones_des_gammes() if nom not in zones]
    anomalies += [f"Débordement : « {nom} » {tuple(zone[:4])} sort du site retenu"
                  for nom, zone in zones.items() if not rectangle_dans_site(zone, polygones)]
    noms = list(zones)
    for i, a in enumerate(noms):
        for b in noms[i + 1:]:
            if zones_se_chevauchent(zones[a], zones[b]) and not _paire_partagee(impl, a, b):
                anomalies.append(f"Chevauchement : « {a} » et « {b} »")
    return anomalies + _anomalies_parking_vl(impl)


def _anomalies_parking_vl(impl: dict) -> list[str]:
    """Le parking VL, s'il y en a un, est dans le site retenu et ne recouvre aucune zone."""
    parking = impl.get("parking_vl")
    if not parking:
        return []
    rectangle = parking["zone"]
    anomalies = [] if rectangle_dans_site(rectangle, impl["polygones_site"]) else [
        f"Débordement : « Parking VL » {tuple(rectangle)} sort du site retenu"]
    return anomalies + [f"Chevauchement : « Parking VL » et « {nom} »"
                        for nom, zone in impl["zones"].items()
                        if zones_se_chevauchent(rectangle, zone)]


def distance_zones(a: tuple, b: tuple) -> float:
    """Distance rectilinéaire (Manhattan, m) entre les centres de deux zones (SPEC §7)."""
    (xa, ya), (xb, yb) = centre_zone(a), centre_zone(b)
    return abs(xb - xa) + abs(yb - ya)


def chemin_zones(a: tuple, b: tuple) -> list[tuple[float, float]]:
    """Chemin en L entre les centres de deux zones : horizontal, puis vertical."""
    (xa, ya), (xb, yb) = centre_zone(a), centre_zone(b)
    return [(xa, ya), (xb, ya), (xb, yb)]


def etapes_gamme(gamme: str) -> list[tuple[str, str]]:
    """Déplacements successifs (zone de départ, zone d'arrivée) d'une gamme."""
    zones = GAMMES[gamme]
    return list(zip(zones, zones[1:]))


def distances_sous_ensemble(implantation: str | dict) -> dict:
    """Distance (m) de chaque gamme ; distance d'un sous-ensemble = gamme pod + gamme module."""
    zones = _implantation(implantation)["zones"]
    detail = {gamme: [(de, vers, distance_zones(zones[de], zones[vers]))
                      for de, vers in etapes_gamme(gamme)] for gamme in GAMMES}
    totaux = {gamme: sum(d for _, _, d in etapes) for gamme, etapes in detail.items()}
    return {**totaux, "sous_ensemble": totaux["pod"] + totaux["module"], "detail": detail}


def segments_gamme(implantation: str | dict, gamme: str) -> list[tuple]:
    """Segments non dégénérés des chemins en L d'une gamme."""
    zones = _implantation(implantation)["zones"]
    segments = []
    for de, vers in etapes_gamme(gamme):
        chemin = chemin_zones(zones[de], zones[vers])
        segments += [(p, q) for p, q in zip(chemin, chemin[1:]) if p != q]
    return segments


def _orientation(a: tuple, b: tuple, c: tuple) -> float:
    """Produit vectoriel (b − a) × (c − a) : positif si c est à gauche de (a, b)."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersection_propre(s1: tuple, s2: tuple) -> bool:
    """Vrai si deux segments se croisent en un point intérieur à chacun : extrémités communes,
    jonctions en T et recouvrements colinéaires ne comptent pas."""
    (a, b), (c, d) = s1, s2
    return (_orientation(c, d, a) * _orientation(c, d, b) < 0
            and _orientation(a, b, c) * _orientation(a, b, d) < 0)


def croisements_flux(implantation: str | dict) -> int:
    """Nombre d'intersections entre segments de gammes différentes, comptées par paire."""
    segments = {gamme: segments_gamme(implantation, gamme) for gamme in GAMMES}
    noms = list(GAMMES)
    return sum(_intersection_propre(s1, s2)
               for i, g1 in enumerate(noms) for g2 in noms[i + 1:]
               for s1 in segments[g1] for s2 in segments[g2])


def _besoins_par_zone(L: float, schema: str) -> dict[str, float]:
    """Besoin calculé (m², SPEC §2.3) des zones qui en ont un."""
    surfaces = dimensionnement_site(L, schema)["surfaces"]
    return {
        "Stock matières": surfaces["stock_matieres"],
        "Kitting": surfaces["kitting"],
        **surfaces_ateliers(calcul_cadence(L), schema),
        "Stock produits finis": surfaces["stock_pf"],
        "Bureaux / pilotage": surfaces["bureaux"],
        "Parking PL": H("m2_parking_pl"),
    }


def capacite_implantation(implantation: str | dict, L: float, schema: str) -> list[dict]:
    """Pour chaque zone dessinée : besoin calculé, surface dessinée (m²) et taux de couverture."""
    zones = _implantation(implantation)["zones"]
    besoins = _besoins_par_zone(L, schema)
    lignes = []
    for nom, zone in zones.items():
        besoin, dessinee = besoins.get(nom), aire_zone(zone)
        lignes.append({"zone": nom, "besoin_m2": besoin, "dessinee_m2": dessinee,
                       "couverture": dessinee / besoin if besoin else None})
    return lignes


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Tests intégrés (SPEC §2.5) — valeurs attendues recalculées à la main ou par un script séparé
# ═════════════════════════════════════════════════════════════════════════════════════════════

CLES_AVELIS = {
    "logements_par_an", "surface_site_actuel", "perimetre_site_actuel", "surface_extension",
    "perimetre_extension", "surface_totale", "annee_objectif",
}
CLES_SPEC = CLES_AVELIS | {
    "jours_ouvres", "equipes_par_jour", "heures_par_equipe", "trs",
    "modules_par_logement", "pods_par_logement", "panneaux_par_module",
    "cycle_ligne_2d_module", "cycle_pod_postes", "travail_assemblage_3d", "temps_kitting",
    "charge_max_poste",
    "tonnes_par_logement", "charge_utile_camion", "temps_quai_reception", "jours_stock_matieres",
    "densite_stockage",
    "dim_module", "temps_chargement_module", "jours_stock_modules", "kits_par_camion_std",
    "taux_occupation_quais",
    "m2_baie_assemblage", "m2_poste_pod", "m2_ligne_2d", "coef_circulation",
    "ratio_foncier_utilisable", "m2_poste_kitting", "m2_kit", "m2_bureaux", "largeur_voirie",
    "longueur_voirie", "rayon_retournement", "m2_parking_pl",
    "cout_km_convoi", "cout_km_semi", "co2_km_pl", "coef_retour_vide_convoi", "coef_retour_semi",
    "coef_detour_route", "vitesse_convoi", "vitesse_semi", "capex_satellite", "amortissement_ans",
    "frais_fixes_satellite", "jours_stock_satellite",
}
CLES_BILAN = (
    "km_an", "cout_transport_an", "co2_t_an", "distance_moyenne_km", "delai_moyen_h",
    "couts_fixes_an", "cout_total_an", "cout_par_logement", "stocks_tampons", "flux",
)


def leve(exception: type, fonction, *args) -> bool:
    """Vrai si fonction(*args) lève l'exception attendue."""
    try:
        fonction(*args)
    except exception:
        return True
    return False


# ── Tâche 1.1 : hypothèses, H(), formatage ──────────────────────────────────────────────────

def test_hypotheses_bien_formees():
    for cle, entree in HYPOTHESES.items():
        assert isinstance(entree, tuple) and len(entree) == 4, cle
        _, unite, marquage, commentaire = entree
        assert isinstance(unite, str) and isinstance(commentaire, str), cle
        assert marquage in ("A", "H"), cle
    assert {cle for cle, entree in HYPOTHESES.items() if entree[2] == "A"} == CLES_AVELIS
    assert CLES_SPEC <= set(HYPOTHESES), CLES_SPEC - set(HYPOTHESES)
    assert H("trs") == 0.80
    assert H("cycle_pod_postes") == (60, 75, 70, 65)


def test_hypotheses_ajoutees_marquees():
    assert {"quais_secours", "postes_consolidation"} <= set(HYPOTHESES)
    for cle in set(HYPOTHESES) - CLES_SPEC:
        _, _, marquage, commentaire = HYPOTHESES[cle]
        chiffree_par_la_spec = commentaire.startswith("SPEC §")  # simulation (§3), interface (§4)
        assert marquage == "H", cle
        assert chiffree_par_la_spec or "ajoutée — à valider" in commentaire, cle


def test_cle_inconnue():
    try:
        H("inexistante")
    except KeyError as erreur:
        assert "inexistante" in str(erreur)
    else:
        raise AssertionError("H() aurait dû lever KeyError")


def test_formater_nombre():
    assert formater_nombre(42786) == "42 786"
    assert formater_nombre(5.714, 1) == "5,7"
    assert formater_nombre(-1234.5, 1) == "-1 234,5"
    assert formater_nombre(None) == "—"
    assert formater_pourcentage(0.16) == "16 %"
    assert formater_pourcentage(0.9734, 1) == "97,3 %"
    assert formater_pourcentage(None) == "—"


# ── Tâche 1.2 : cadence ─────────────────────────────────────────────────────────────────────

# Calculs à la main pour 1 500 logements/an, 220 jours, 2 postes de 8 h (960 min) et TRS 0,8
MODULES_JOUR_1500 = 1500 * 1.2 / 220  # ≈ 8,18 modules/jour
FACTEUR_JOURS = 225 / 220  # stocks journaliers : valeurs du §2 (225 jours) × 225 / 220


def test_cadence_1500():
    c = calcul_cadence(1500)
    r = c["ressources"]
    assert math.isclose(c["modules_jour"], MODULES_JOUR_1500)
    assert math.isclose(c["takt_module_min"], 768 / MODULES_JOUR_1500)  # ≈ 93,9 min
    assert r["baies_assemblage"]["nombre"] == 12
    assert math.isclose(c["pods_jour"], 1500 / 220)
    assert math.isclose(c["panneaux_jour"], 12 * MODULES_JOUR_1500)
    assert c["temps_ouverture_min"] == 960 and math.isclose(c["temps_net_min"], 768)
    assert math.isclose(c["takt_pod_min"], 768 / (1500 / 220))  # ≈ 112,6 min
    assert r["lignes_2d"]["nombre"] == r["lignes_pods"]["nombre"] == 1
    assert r["postes_kitting"]["nombre"] == 1
    assert c["postes_pods"] == 4
    assert math.isclose(r["baies_assemblage"]["charge"], 960 / (768 / MODULES_JOUR_1500 * 12))
    assert c["goulot"] == "baies_assemblage"


def test_arrondi_frontiere_entiere():
    # 960 / (66,67 × 0,9) vaut 16,000000000000004 en flottant : un ceil naïf donnerait 17 baies
    assert calcul_cadence(2025)["ressources"]["baies_assemblage"]["nombre"] == 16
    assert arrondi_superieur(16.000000000000004) == 16
    assert arrondi_superieur(16.01) == 17


def test_entrees_invalides():
    assert leve(ValueError, calcul_cadence, 0)
    assert leve(ValueError, calcul_cadence, -100)
    assert leve(ValueError, dimensionnement_site, 1500, "mixte")
    assert leve(ValueError, evolutivite, "Unique")
    assert leve(ValueError, comparaison_reseau, 1500, "lointaine")
    assert leve(ValueError, distances_sous_ensemble, "inconnue")


# ── Tâche 1.3 : dimensionnement, évolutivité ────────────────────────────────────────────────

def test_dimensionnement_unique():
    d = dimensionnement_site(1500, "unique")
    s = d["surfaces"]
    assert math.isclose(d["camions_entrants_jour"], 1500 * 12 / 220 / 14)  # ≈ 5,84
    assert d["quais_reception"] == 2 and d["quais_expedition"] == 2
    assert math.isclose(d["camions_sortants_jour"], MODULES_JOUR_1500)
    assert math.isclose(s["stock_matieres"], 2000 * FACTEUR_JOURS)
    assert math.isclose(s["stock_pf"], 2100 * FACTEUR_JOURS)
    assert math.isclose(s["production"], 11200) and math.isclose(s["kitting"], 300)
    assert math.isclose(s["voiries"], 7 * 520 + math.pi * 13 ** 2 + 1500)
    assert s["bureaux"] == 1500
    assert math.isclose(d["besoin_total"], sum(s.values()))
    assert math.isclose(d["utilisable_site_seul"], 42786 * 0.6)
    assert math.isclose(d["utilisable_avec_extension"], 70229 * 0.6)
    assert math.isclose(d["m2_stockage_pour_1000"], (2000 + 2100) * FACTEUR_JOURS / 1500 * 1000)


def test_dimensionnement_satellites():
    d = dimensionnement_site(1500, "satellites")
    assert math.isclose(d["camions_sortants_jour"], MODULES_JOUR_1500 / 3)
    assert d["quais_expedition"] == 2
    assert math.isclose(d["surfaces"]["stock_pf"], 720 * FACTEUR_JOURS)
    assert math.isclose(d["surfaces"]["production"], 5350)  # ligne 2D + pods + consolidation
    assert math.isclose(d["m2_stockage_pour_1000"], (2000 + 720) * FACTEUR_JOURS / 1500 * 1000)


def test_evolutivite():
    e = evolutivite()
    assert e["cadences"] == list(range(400, 3001, 100))
    assert all(b2 >= b1 for b1, b2 in zip(e["besoins"], e["besoins"][1:]))
    assert e["cadence_max_site_seul"] == 1800
    assert e["cadence_max_avec_extension"] == 3000


# ── Tâche 1.4 : géographie et réseau ────────────────────────────────────────────────────────

def test_haversine():
    d = haversine_km(CHANTIERS["Île-de-France"], CHANTIERS["Lyon"])
    assert abs(d - 392.5) < 1, d
    route = distance_route_km(TORCY, CHANTIERS["Lyon"])
    assert math.isclose(route, haversine_km(TORCY, CHANTIERS["Lyon"]) * 1.30)


def test_contour_france():
    assert 30 <= len(CONTOUR_FRANCE) <= 45
    for lat, lon, *_ in (TORCY, *CHANTIERS.values(), *SATELLITES.values()):
        assert point_dans_polygone((lon, lat), CONTOUR_FRANCE), (lat, lon)


def test_parts_chantiers():
    assert math.isclose(sum(part for _, _, part in CHANTIERS.values()), 1)


def test_reseau_proche():
    r = comparaison_reseau(1500, "proche")
    attendu = {
        "Île-de-France": "Île-de-France", "Lille": "Île-de-France", "Strasbourg": "Île-de-France",
        "Lyon": "Lyon-Sud", "Marseille": "Lyon-Sud", "Dijon": "Lyon-Sud",
        "Bordeaux": "Ouest-Tours", "Nantes": "Ouest-Tours",
    }
    assert {nom: it["satellite"] for nom, it in r["B"]["itineraires"].items()} == attendu
    assert abs(r["A"]["cout_variable_par_module"] / 2568.9 - 1) < 0.005
    assert math.isclose(r["B"]["couts_fixes_an"], 6.0e6)
    assert math.isclose(sum(r["B"]["stocks_tampons"].values()), 2 * MODULES_JOUR_1500)
    assert r["part_directe"] == 0
    for option in ("A", "B"):
        assert set(CLES_BILAN) <= set(r[option]), option
    assert r["recommandation"]


def test_reseau_hybride():
    r = comparaison_reseau(1500, "hybride")
    directs = {nom for nom, it in r["B"]["itineraires"].items() if it["satellite"] is None}
    assert directs == {"Strasbourg", "Dijon"}
    assert math.isclose(r["part_directe"], 0.16)
    assert abs(r["B"]["cout_variable_par_module"] / 1338.1 - 1) < 0.005


def test_point_bascule():
    assert point_bascule("proche") == 4700
    assert point_bascule("hybride") == 4100
    for variante in VARIANTES:
        r = comparaison_reseau(1500, variante)
        ecart_module = r["A"]["cout_variable_par_module"] - r["B"]["cout_variable_par_module"]
        seuil = r["B"]["couts_fixes_an"] / (ecart_module * H("modules_par_logement"))
        assert point_bascule(variante) == 50 * (math.floor(seuil / 50) + 1), variante


# ── Tâche 1.5 : géométrie du site ───────────────────────────────────────────────────────────

def test_aires_polygones():
    assert aire_polygone(SITE_ACTUEL) == 42668
    assert aire_polygone(EXTENSION) == 27421
    assert abs(aire_polygone(SITE_ACTUEL) / H("surface_site_actuel") - 1) < 0.01
    assert abs(aire_polygone(EXTENSION) / H("surface_extension") - 1) < 0.01


def test_implantations_conformes():
    for nom in IMPLANTATIONS:
        anomalies = verifier_implantation(nom)
        assert anomalies == [], (nom, anomalies)


def test_verification_detecte_defauts():
    implantation = copy.deepcopy(IMPLANTATIONS[IMPLANTATION_PROPOSEE])
    zones = implantation["zones"]
    zones["Stock produits finis"] = (430, 96, 34, 70, "#000000", "test")  # déborde à l'est
    zones["Zone hors site"] = (300, 20, 20, 20, "#000000", "test")
    zones["Doublon kitting"] = (160, 170, 20, 20, "#000000", "test")
    anomalies = " | ".join(verifier_implantation(implantation))
    assert "Débordement : « Stock produits finis »" in anomalies, anomalies
    assert "Débordement : « Zone hors site »" in anomalies, anomalies
    assert "Chevauchement : « Kitting » et « Doublon kitting »" in anomalies, anomalies


def test_verification_cas_limites():
    a_cheval = (230, 100, 30, 20)  # de part et d'autre de la limite site / extension
    assert rectangle_dans_site(a_cheval, (SITE_ACTUEL, EXTENSION))
    assert not rectangle_dans_site(a_cheval, (SITE_ACTUEL,))
    assert rectangle_dans_site((175, 152, 20, 10), (SITE_ACTUEL,))  # bord droit sur x = 195
    assert not zones_se_chevauchent((0, 0, 10, 10), (10, 0, 10, 10))  # zones contiguës
    assert zones_se_chevauchent((0, 0, 10, 10), (9, 9, 10, 10))
    actuelle = IMPLANTATIONS[IMPLANTATION_ACTUELLE]["zones"]
    assert actuelle["Expédition"][:4] == actuelle["Réception"][:4]  # quais partagés, exemptés


def test_chemin_zones():
    a = (5, 5, 10, 10, "#ffffff", "test")
    b = (45, 25, 10, 10, "#ffffff", "test")
    assert chemin_zones(a, b) == [(10, 10), (50, 10), (50, 30)]
    assert distance_zones(a, b) == 60


def test_distances_sous_ensemble():
    # Calcul manuel entre centres de zones, sur les implantations du schéma d'emprise
    p = distances_sous_ensemble(IMPLANTATION_PROPOSEE)
    assert (p["pod"], p["module"], p["sous_ensemble"], p["2D"]) == (475, 206, 681, 343), p
    a = distances_sous_ensemble(IMPLANTATION_ACTUELLE)
    assert (a["pod"], a["module"], a["sous_ensemble"], a["2D"]) == (442, 576, 1018, 177), a


def test_croisements_flux():
    assert croisements_flux(IMPLANTATION_PROPOSEE) == 0
    assert croisements_flux(IMPLANTATION_ACTUELLE) == 2


def test_implantation_optimisee():
    optimisee, proposee = (distances_sous_ensemble(nom) for nom in (IMPLANTATION_OPTIMISEE,
                                                                     IMPLANTATION_PROPOSEE))
    assert verifier_implantation(IMPLANTATION_OPTIMISEE) == []
    assert croisements_flux(IMPLANTATION_OPTIMISEE) == 0
    # calculs à la main (centres des zones, distances de Manhattan)
    assert math.isclose(optimisee["2D"], (14 + 39) + (120 + 4))  # 177 m, contre 343
    assert math.isclose(optimisee["sous_ensemble"], 579.5)  # contre 681
    assert optimisee["sous_ensemble"] < proposee["sous_ensemble"]
    couverture = {ligne["zone"]: ligne["couverture"] for ligne in
                  capacite_implantation(IMPLANTATION_OPTIMISEE, 1500, "unique")}
    assert all(couverture[zone] >= 1 for zone in (
        "Ligne 2D robotisée", "Ligne pods", "Assemblage 3D", "Stock matières",
        "Stock produits finis", "Kitting", "Bureaux / pilotage"))


def test_capacite_implantation():
    lignes = {ligne["zone"]: ligne for ligne in
              capacite_implantation(IMPLANTATION_PROPOSEE, 1500, "unique")}
    assert math.isclose(lignes["Stock matières"]["couverture"], 2220 / (2000 * FACTEUR_JOURS))
    assert math.isclose(lignes["Ligne 2D robotisée"]["couverture"], 2816 / 4000)
    assert lignes["Réception"]["besoin_m2"] is None and lignes["Réception"]["couverture"] is None
    satellites = {ligne["zone"]: ligne for ligne in
                  capacite_implantation(IMPLANTATION_PROPOSEE, 1500, "satellites")}
    assert math.isclose(satellites["Assemblage 3D"]["besoin_m2"], 2 * 150 * 1.5)


def test_pas_de_mutation():
    hypotheses_avant = copy.deepcopy(HYPOTHESES)
    implantations_avant = copy.deepcopy(IMPLANTATIONS)
    calcul_cadence(1500)
    dimensionnement_site(1500, "satellites")
    evolutivite()
    comparaison_reseau(1500, "hybride")
    point_bascule("proche")
    for nom in IMPLANTATIONS:
        verifier_implantation(nom)
        distances_sous_ensemble(nom)
        croisements_flux(nom)
        capacite_implantation(nom, 1500, "unique")
    assert HYPOTHESES == hypotheses_avant
    assert IMPLANTATIONS == implantations_avant


def test_controle_des_parametres():
    assert anomalies_hypothese("trs", 0.75) == []
    assert anomalies_hypothese("trs", 1.2) == ["« trs » : taux compris entre 0 et 1 attendu"]
    assert anomalies_hypothese("jours_ouvres", 220.5) == ["« jours_ouvres » : nombre entier attendu"]
    assert anomalies_hypothese("jours_ouvres", 0) == [
        "« jours_ouvres » : nombre strictement positif attendu"]
    assert anomalies_hypothese("dim_module", (3.5, 10)) == ["« dim_module » : 3 valeurs attendues"]
    assert anomalies_hypothese("kitting_min", (35, 18)) == [
        "« kitting_min » : le minimum dépasse le maximum"]
    assert anomalies_hypothese("inconnue", 1) == ["hypothèse inconnue : « inconnue »"]
    defaut = parametres_par_defaut()
    assert anomalies_reseau(defaut["chantiers"], defaut["satellites"]) == []
    chantiers = {**defaut["chantiers"], "Brest": (48.39, -4.49, 0.05)}
    assert anomalies_reseau(chantiers, {}) == [
        "au moins une usine satellite est nécessaire",
        f"Parts des chantiers : total de {formater_pourcentage(1.05, 2)} au lieu de "
        f"{formater_pourcentage(1)}"]
    assert "position hors de la France" in anomalies_reseau({"Rome": (41.9, 12.5, 1.0)},
                                                            defaut["satellites"])[0]
    assert all(anomalies_lieu("Ville", nom, *lieu) == [] for nom, lieu in VILLES_FRANCE.items())


def test_appliquer_puis_retablir():
    defaut = parametres_par_defaut()
    try:
        hypotheses = {**defaut["hypotheses"], "jours_ouvres": 200}
        chantiers = {"Lille": (50.63, 3.06, 0.4), "Nice": (43.71, 7.26, 0.6)}
        appliquer_parametres(hypotheses, chantiers, {"Nord": (50.0, 3.0)})
        assert H("jours_ouvres") == 200 and isinstance(H("trs"), float)
        assert set(CHANTIERS) == {"Lille", "Nice"} and set(SATELLITES) == {"Nord"}
        bilan = comparaison_reseau(1500)["B"]
        assert bilan["satellites_utilises"] == ["Nord"]
        try:
            appliquer_parametres({"trs": 2.0}, chantiers, {"Nord": (50.0, 3.0)})
        except ValueError as erreur:
            assert "trs" in str(erreur)
        else:
            raise AssertionError("valeur refusée attendue")
        assert H("trs") == defaut["hypotheses"]["trs"]  # rien n'a changé
    finally:
        appliquer_parametres(**defaut)
    assert etat_parametres() == defaut


def executer_tests(espace: dict | None = None, module: str = "modele.py") -> bool:
    """Exécute les fonctions test_* d'un espace de noms (ce module par défaut) ; affiche ✓ ou ✗
    pour chacune et renvoie True si tout passe."""
    espace = globals() if espace is None else espace
    tests = [(nom, f) for nom, f in espace.items() if nom.startswith("test_") and callable(f)]
    echecs = 0
    print(f"Tests intégrés de {module} ({len(tests)} tests)")
    for nom, fonction in tests:
        try:
            fonction()
        except Exception as erreur:  # on veut voir tous les échecs, pas seulement le premier
            echecs += 1
            print(f"  ✗ {nom} : {type(erreur).__name__} : {erreur}")
        else:
            print(f"  ✓ {nom}")
    print(f"{len(tests) - echecs}/{len(tests)} tests réussis\n")
    return echecs == 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Affichage des chiffres clés (exécution directe, SPEC §2.5 et §5.1)
# ═════════════════════════════════════════════════════════════════════════════════════════════

LARGEUR_LIBELLE = 46
LARGEUR_VALEUR = 16
LARGEUR_TEXTE = 100
CADENCE_SPEC_6 = 1500  # cadence à laquelle SPEC §6 donne ses ordres de grandeur
TOLERANCE_ORDRE_DE_GRANDEUR = 0.10  # écart relatif admis pour un « ≈ » avant d'afficher ⚠


def bornes_environ(reference: float) -> tuple[float, float]:
    """Bornes d'un « ≈ » : référence ± TOLERANCE_ORDRE_DE_GRANDEUR."""
    return (reference * (1 - TOLERANCE_ORDRE_DE_GRANDEUR),
            reference * (1 + TOLERANCE_ORDRE_DE_GRANDEUR))


# Ordres de grandeur de SPEC §6 : (libellé, attendu affiché, borne basse, borne haute).
# Contrôles de cohérence : un écart est signalé et expliqué, jamais corrigé par une hypothèse.
CONTROLES_SPEC_6 = {
    "modules_jour": ("Modules par jour", "8 (exact)", 8, 8),
    "takt_module_min": ("Takt module (min)", "90 (exact)", 90, 90),
    "baies_assemblage": ("Baies d'assemblage", "12 (exact)", 12, 12),
    "camions_entrants_jour": ("Camions entrants par jour", "≈ 5,7", *bornes_environ(5.7)),
    "sous_ensemble_proposee": ("Distance d'un sous-ensemble, proposée (m)", "≈ 640",
                               *bornes_environ(640)),
    "sous_ensemble_actuelle": ("Distance d'un sous-ensemble, actuelle (m)", "≈ 950",
                               *bornes_environ(950)),
    "bascule_proche": ("Point de bascule « proche » (logements/an)", "4 500 à 4 800", 4500, 4800),
    "bascule_hybride": ("Point de bascule « hybride » (logements/an)", "4 000 à 4 300",
                        4000, 4300),
}

# Lignes du tableau de réseau : (libellé, clé du bilan, diviseur, décimales)
LIGNES_RESEAU = (
    ("Coût par logement (€)", "cout_par_logement", 1, 0),
    ("Coût total (M€/an)", "cout_total_an", EUROS_PAR_MILLION, 2),
    ("  dont transport (M€/an)", "cout_transport_an", EUROS_PAR_MILLION, 2),
    ("  dont coûts fixes des satellites (M€/an)", "couts_fixes_an", EUROS_PAR_MILLION, 2),
    ("Kilomètres facturés (km/an)", "km_an", 1, 0),
    ("CO2 (t/an)", "co2_t_an", 1, 0),
    ("Distance moyenne pondérée (km)", "distance_moyenne_km", 1, 0),
    ("Délai moyen de livraison (h)", "delai_moyen_h", 1, 1),
)


def afficher_titre(texte: str) -> None:
    """Titre de rubrique souligné."""
    print(f"\n{texte}\n{'─' * len(texte)}")


def afficher_ligne(libelle: str, *valeurs: str, note: str = "") -> None:
    """Ligne alignée : libellé, valeurs en colonnes, note facultative."""
    colonnes = "".join(f"{valeur:>{LARGEUR_VALEUR}}" for valeur in valeurs)
    print(f"  {libelle:<{LARGEUR_LIBELLE}}{colonnes}  {note}".rstrip())


def _signe(texte: str, x: float) -> str:
    """Préfixe « + » devant un écart positif déjà formaté."""
    return f"+{texte}" if x > 0 else texte


def _afficher_cadence(L: float) -> None:
    """Flux journaliers, takts et ressources."""
    c = calcul_cadence(L)
    afficher_titre(f"Cadence : {formater_nombre(L)} logements/an")
    afficher_ligne("Logements par jour", formater_nombre(c["logements_jour"], 2))
    afficher_ligne("Modules par jour", formater_nombre(c["modules_jour"], 2))
    afficher_ligne("Pods par jour", formater_nombre(c["pods_jour"], 2))
    afficher_ligne("Panneaux 2D par jour", formater_nombre(c["panneaux_jour"]))
    afficher_ligne("Temps d'ouverture (min/jour)", formater_nombre(c["temps_ouverture_min"]))
    afficher_ligne("Temps net après TRS (min/jour)", formater_nombre(c["temps_net_min"]))
    afficher_ligne("Takt module (min)", formater_nombre(c["takt_module_min"], 1))
    afficher_ligne("Takt pod (min)", formater_nombre(c["takt_pod_min"], 1))
    afficher_titre("Ressources : nombre = ceil(cycle / (takt × charge max))")
    for cle, ressource in c["ressources"].items():
        libelle = f"{ressource['libelle']} (cycle {formater_nombre(ressource['cycle_min'])} min)"
        afficher_ligne(libelle, str(ressource["nombre"]),
                       f"charge {formater_pourcentage(ressource['charge'])}",
                       note="← goulot" if cle == c["goulot"] else "")


def _afficher_logistique(L: float) -> None:
    """Camions et quais pour les deux schémas industriels."""
    duo = [dimensionnement_site(L, schema) for schema in SCHEMAS]
    afficher_titre("Logistique : camions et quais")
    afficher_ligne("", *SCHEMAS)
    for libelle, cle, decimales in (
            ("Matières reçues (t/jour)", "tonnes_jour", 0),
            ("Camions entrants par jour", "camions_entrants_jour", 2),
            ("Quais de réception (secours compris)", "quais_reception", 0),
            ("Unités expédiées par jour (modules ou kits)", "unites_expediees_jour", 1),
            ("Camions sortants par jour (convois ou semis)", "camions_sortants_jour", 2),
            ("Quais d'expédition (secours compris)", "quais_expedition", 0)):
        afficher_ligne(libelle, *(formater_nombre(d[cle], decimales) for d in duo))


def _texte_cadence_max(cadence: int | None) -> str:
    """Cadence maximale admissible ; « ≥ » si elle atteint la borne de la plage étudiée."""
    if cadence is None:
        return f"< {formater_nombre(PLAGE_EVOLUTIVITE[0])}"
    return ("≥ " if cadence == PLAGE_EVOLUTIVITE[1] else "") + formater_nombre(cadence)


def _afficher_surfaces(L: float) -> None:
    """Surfaces nécessaires et utilisables, puis évolutivité."""
    duo = [dimensionnement_site(L, schema) for schema in SCHEMAS]
    afficher_titre("Surfaces nécessaires (m²)")
    afficher_ligne("", *SCHEMAS)
    for cle, libelle in LIBELLES_SURFACES.items():
        afficher_ligne(libelle, *(formater_nombre(d["surfaces"][cle]) for d in duo))
    afficher_ligne("Besoin total", *(formater_nombre(d["besoin_total"]) for d in duo))
    afficher_ligne("Stockage pour 1 000 logements/an",
                   *(formater_nombre(d["m2_stockage_pour_1000"]) for d in duo))
    afficher_ligne("Surface utilisable, site seul",
                   formater_nombre(duo[0]["utilisable_site_seul"]))
    afficher_ligne("Surface utilisable, site + extension",
                   formater_nombre(duo[0]["utilisable_avec_extension"]))
    afficher_titre("Évolutivité : cadence maximale admissible (logements/an, plage 400 à 3 000)")
    afficher_ligne("", "site seul", "avec extension")
    for schema in SCHEMAS:
        e = evolutivite(schema)
        afficher_ligne(f"Schéma « {schema} »", _texte_cadence_max(e["cadence_max_site_seul"]),
                       _texte_cadence_max(e["cadence_max_avec_extension"]))


def _afficher_implantations(L: float) -> None:
    """Distances, croisements, contrôle géométrique et zones sous-dimensionnées."""
    afficher_titre("Implantations : distances (m), croisements de flux, contrôle géométrique")
    for nom in IMPLANTATIONS:
        d = distances_sous_ensemble(nom)
        anomalies = verifier_implantation(nom)
        sous_dimensionnees = [f"{ligne['zone']} {formater_pourcentage(ligne['couverture'])}"
                              for ligne in capacite_implantation(nom, L, "unique")
                              if ligne["couverture"] is not None and ligne["couverture"] < 1]
        print(f"  {nom}")
        afficher_ligne("  gammes pod / module / 2D",
                       " / ".join(formater_nombre(d[gamme]) for gamme in ("pod", "module", "2D")))
        afficher_ligne("  distance d'un sous-ensemble (pod + module)",
                       formater_nombre(d["sous_ensemble"]))
        afficher_ligne("  croisements de flux", str(croisements_flux(nom)))
        afficher_ligne("  contrôle géométrique",
                       "conforme" if not anomalies else f"{len(anomalies)} anomalie(s)")
        for anomalie in anomalies:
            print(f"      ⚠ {anomalie}")
        print(f"    zones sous-dimensionnées (schéma unique) : "
              f"{', '.join(sous_dimensionnees) or 'aucune'}")


def _afficher_aires() -> None:
    """Aires des polygones du site (formule du lacet) face aux surfaces Avelis."""
    afficher_titre("Contrôle géométrique : aires par la formule du lacet (m²)")
    for libelle, polygone, cle in (("Site actuel", SITE_ACTUEL, "surface_site_actuel"),
                                   ("Extension", EXTENSION, "surface_extension")):
        aire, avelis = aire_polygone(polygone), H(cle)
        ecart = aire - avelis
        ecart_m2 = _signe(formater_nombre(ecart), ecart)
        ecart_relatif = _signe(formater_pourcentage(ecart / avelis, 2), ecart)
        afficher_ligne(libelle, formater_nombre(aire),
                       note=f"Avelis {formater_nombre(avelis)}, écart {ecart_m2} m² "
                            f"({ecart_relatif})")


def _afficher_reseau(L: float) -> None:
    """Comparaison des deux réseaux dans chaque variante, avec la recommandation."""
    for variante in VARIANTES:
        r = comparaison_reseau(L, variante)
        afficher_titre(f"Réseau, variante « {variante} » : "
                       "A = usine unique, B = usine mère + satellites")
        afficher_ligne("", "A", "B")
        for libelle, cle, diviseur, decimales in LIGNES_RESEAU:
            afficher_ligne(libelle,
                           *(formater_nombre(r[o][cle] / diviseur, decimales) for o in "AB"))
        stocks = r["B"]["stocks_tampons"]
        afficher_ligne("Stocks tampons (kits)",
                       *(formater_nombre(sum(r[o]["stocks_tampons"].values()), 1) for o in "AB"),
                       note=", ".join(f"{nom} {formater_nombre(kits, 1)}"
                                      for nom, kits in stocks.items()))
        afficher_ligne("Part de la demande livrée en direct",
                       *(formater_pourcentage(r[o]["part_directe"]) for o in "AB"))
        print(textwrap.fill(r["recommandation"], width=LARGEUR_TEXTE,
                            initial_indent="  → ", subsequent_indent="    "))


def _valeurs_spec_6() -> dict[str, float | None]:
    """Valeurs calculées des grandeurs que SPEC §6 encadre (cadence de 1 500 logements/an)."""
    c = calcul_cadence(CADENCE_SPEC_6)
    return {
        "modules_jour": c["modules_jour"],
        "takt_module_min": c["takt_module_min"],
        "baies_assemblage": c["ressources"]["baies_assemblage"]["nombre"],
        "camions_entrants_jour": dimensionnement_site(CADENCE_SPEC_6, "unique")
        ["camions_entrants_jour"],
        "sous_ensemble_proposee": distances_sous_ensemble(IMPLANTATION_PROPOSEE)["sous_ensemble"],
        "sous_ensemble_actuelle": distances_sous_ensemble(IMPLANTATION_ACTUELLE)["sous_ensemble"],
        "bascule_proche": point_bascule("proche"),
        "bascule_hybride": point_bascule("hybride"),
    }


def _afficher_comparaison_spec_6() -> int:
    """Chaque grandeur du §6 avec ✓ (cohérent) ou ⚠ (écart à expliquer) ; renvoie le nombre
    d'écarts. Aucune hypothèse n'est modifiée pour s'en rapprocher."""
    afficher_titre("Comparaison aux ordres de grandeur de SPEC §6 (contrôles de cohérence)")
    ecarts = 0
    for cle, valeur in _valeurs_spec_6().items():
        libelle, attendu, bas, haut = CONTROLES_SPEC_6[cle]
        conforme = (valeur is not None
                    and bas - TOLERANCE_ARRONDI <= valeur <= haut + TOLERANCE_ARRONDI)
        ecarts += not conforme
        decimales = 0 if valeur is None or float(valeur).is_integer() else 2
        afficher_ligne(f"{'✓' if conforme else '⚠'} {libelle}",
                       formater_nombre(valeur, decimales), note=f"attendu {attendu}")
    print("  Débit simulé et part des modules tracés : contrôlés par simulation.py.")
    return ecarts


def afficher_chiffres_cles(L: float | None = None) -> None:
    """Chiffres clés (SPEC §2.5) à la cadence de référence, puis comparaison à SPEC §6."""
    L = H("logements_par_an") if L is None else L
    print(f"Chiffres clés à {formater_nombre(L)} logements/an "
          "(toutes les valeurs estimées sont des HYPOTHÈSES)")
    _afficher_cadence(L)
    _afficher_logistique(L)
    _afficher_surfaces(L)
    _afficher_implantations(L)
    _afficher_aires()
    _afficher_reseau(L)
    ecarts = _afficher_comparaison_spec_6()
    print(f"\n{ecarts} écart(s) aux ordres de grandeur du §6, à expliquer."
          if ecarts else "\nAucun écart aux ordres de grandeur du §6.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    reussite = executer_tests()
    if reussite:
        afficher_chiffres_cles()
    sys.exit(0 if reussite else 1)
