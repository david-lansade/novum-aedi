"""Analyse du jumeau numérique : la brique d'IA du pilotage (fiche Bloc 3, « pilotage en temps
réel et IA »).

  - Option B, détection des postes anormalement lents : pour chaque étape des gammes module et
    pod, la durée des derniers passages est comparée à une référence (les passages antérieurs,
    sinon la simulation) ; un passage isolé est anormal au-delà de la médiane + 3 écarts robustes.
  - Option A, prévision de la fin de fabrication (entrée en stock de produits finis) de chaque
    module en cours : somme des durées des étapes qui restent, chacune apprise des scans et
    rapprochée de la durée simulée tant qu'il y a peu de mesures ; fourchette p10–p90.
  - Validation de la prévision sur la simulation : apprise sur la première moitié des modules,
    mesurée sur la seconde, comparée à une prévision naïve (OF + délai moyen).

Méthodes statistiques volontairement explicables, qui fonctionnent avec peu de données (quelques
passages par poste) : bibliothèque standard seulement. Les durées sont en minutes du jumeau
(minutes réelles) ; les durées simulées sont converties par l'échelle de temps de la maquette.

Ce module n'importe aucun module graphique. Exécution directe : tests intégrés.
"""

import math
import statistics
import sys

import jumeau as jm
import modele as m
import simulation as sim
from modele import H

Z_FOURCHETTE = 1.2816  # quantile 90 % de la loi normale : fourchette p10–p90
MAD_VERS_ECART_TYPE = 1.4826  # écart absolu médian → écart-type, pour une loi normale
PLANCHER_MAD = 0.1  # écart robuste minimal, en part de la médiane (passages presque identiques)
ETAPE_DEBUT, ETAPE_FIN = "OF lancé", "Entrée stock PF"  # fin de fabrication d'un module
GAMMES = jm.GAMMES_COMPAREES
NORMAL, A_SURVEILLER, ANORMAL, SANS_MESURE = ("normal", "à surveiller", "anormal",
                                               "pas assez de mesures")


def texte_duree(minutes: float | None) -> str:
    """Durée lisible : secondes sous 1 min, minutes sous 1 h, sinon heures et minutes."""
    if minutes is None:
        return "—"
    if minutes < 1:
        return f"{round(minutes * jm.SECONDES_PAR_MINUTE)} s"
    if minutes < m.MINUTES_PAR_HEURE:
        return f"{m.formater_nombre(minutes)} min"
    heures, reste = divmod(round(minutes), m.MINUTES_PAR_HEURE)
    return f"{heures} h {reste:02d}"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. Passages mesurés et durées prévues
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _premiers_scans(jumeau: jm.Jumeau) -> dict:
    """{(type, code): {étape: (instant, poste, zone)}} du premier scan accepté de chaque étape."""
    premiers: dict = {}
    for e in jumeau.evenements:
        if (e["resultat"] == "accepte" and e["type"] in GAMMES
                and e["evenement"] in GAMMES[e["type"]]):
            etapes = premiers.setdefault((e["type"], e["code"]), {})
            etapes.setdefault(e["evenement"], (jumeau.instant(e["t"]), e["poste"], e["zone"]))
    return premiers


def passages_par_transition(jumeau: jm.Jumeau) -> dict[tuple, list[dict]]:
    """{(gamme, de, vers): [passages]} triés par fin ; un passage = {code, t_fin, duree, poste,
    zone}, le poste étant celui où l'étape d'arrivée a été scannée (là où le travail s'est
    fait)."""
    resultat: dict = {}
    for (type_piece, code), etapes in _premiers_scans(jumeau).items():
        gamme = GAMMES[type_piece]
        for de, vers in zip(gamme, gamme[1:]):
            if de in etapes and vers in etapes:
                t_fin, poste, zone = etapes[vers]
                resultat.setdefault((type_piece, de, vers), []).append({
                    "code": code, "t_fin": t_fin, "duree": max(0.0, t_fin - etapes[de][0]),
                    "poste": poste, "zone": zone})
    for passages in resultat.values():
        passages.sort(key=lambda p: p["t_fin"])
    return resultat


def durees_prevues(usine) -> dict[tuple, tuple[float, float]]:
    """{(gamme, de, vers): (moyenne, écart-type)} des durées simulées, en minutes du jumeau."""
    echelle = H("echelle_temps_maquette")
    prevues = {}
    for transition, durees in jm.durees_simulees(usine).items():
        ecart = statistics.pstdev(durees) if len(durees) > 1 else 0.0
        prevues[transition] = (statistics.mean(durees) / echelle, ecart / echelle)
    return prevues


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. Option B : postes anormalement lents
# ═════════════════════════════════════════════════════════════════════════════════════════════

def mediane_et_ecart_robuste(durees: list[float]) -> tuple[float, float]:
    """Médiane et écart robuste (écart absolu médian ramené à un écart-type), avec un plancher :
    une valeur aberrante isolée ne déplace pas la référence."""
    mediane = statistics.median(durees)
    mad = statistics.median(abs(d - mediane) for d in durees)
    return mediane, max(mad * MAD_VERS_ECART_TYPE, PLANCHER_MAD * mediane)


def _reference(transition: tuple, anciennes: list[float], prevues: dict | None):
    """(référence, origine) : médiane des passages antérieurs s'il y en a assez, sinon durée
    simulée ; (None, None) sans l'une ni l'autre."""
    if len(anciennes) >= H("passages_reference_min"):
        return statistics.median(anciennes), "passages antérieurs"
    if prevues and transition in prevues:
        return prevues[transition][0], "simulation"
    return None, None


def _etat_poste(rapport: float | None, anomalies_recentes: int) -> str:
    """Anormal si les derniers passages dépassent la référence de plus du seuil ; à surveiller
    si un passage récent est anormal, ou s'ils dépassent la moitié du seuil."""
    seuil = H("seuil_ecart_jumeau")
    if rapport is None:
        return A_SURVEILLER if anomalies_recentes else SANS_MESURE
    if rapport > 1 + seuil:
        return ANORMAL
    if anomalies_recentes or rapport > 1 + seuil / 2:
        return A_SURVEILLER
    return NORMAL


def _ligne_poste(transition: tuple, passages: list[dict], prevues: dict | None) -> dict:
    """Diagnostic d'une étape : référence, moyenne récente, rapport, passages anormaux, état."""
    durees = [p["duree"] for p in passages]
    n_recents = H("passages_recents_derive")
    recents, anciennes = durees[-n_recents:], durees[:-n_recents]
    reference, origine = _reference(transition, anciennes, prevues)
    moyenne_recente = statistics.mean(recents) if len(recents) >= n_recents else None
    rapport = (moyenne_recente / reference
               if moyenne_recente is not None and reference else None)
    anormaux = []
    if len(durees) >= H("passages_reference_min"):
        mediane, ecart = mediane_et_ecart_robuste(durees)
        anormaux = [p for p in passages if p["duree"] > mediane + H("seuil_anomalie_mad") * ecart]
    codes_recents = {p["code"] for p in passages[-n_recents:]}
    poste = statistics.mode(p["poste"] for p in passages)
    zone = next(p["zone"] for p in passages if p["poste"] == poste)
    return {"transition": transition, "gamme": transition[0], "etape": transition[2],
            "poste": poste, "zone": zone, "passages": len(durees),
            "mediane": statistics.median(durees), "reference": reference, "origine": origine,
            "moyenne_recente": moyenne_recente, "rapport": rapport,
            "anormaux": [p["code"] for p in anormaux],
            "etat": _etat_poste(rapport, sum(p["code"] in codes_recents for p in anormaux))}


def analyser_postes(jumeau: jm.Jumeau, prevues: dict | None = None) -> list[dict]:
    """Une ligne par étape mesurée, les plus inquiétantes d'abord."""
    ordre = {ANORMAL: 0, A_SURVEILLER: 1, NORMAL: 2, SANS_MESURE: 3}
    lignes = [_ligne_poste(transition, passages, prevues)
              for transition, passages in passages_par_transition(jumeau).items()]
    return sorted(lignes, key=lambda l: (ordre[l["etat"]], -(l["rapport"] or 0)))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. Option A : fin de fabrication prévue des modules en cours
# ═════════════════════════════════════════════════════════════════════════════════════════════

def estimer_transition(transition: tuple, mesures: dict, prevues: dict | None):
    """(moyenne, variance, mesures) de la durée d'une étape : moyenne des n mesures rapprochée de
    la durée simulée, de poids k = poids_prevision (n = 0 : la simulation seule ; n grand : les
    mesures). None si l'étape n'a jamais été mesurée ni simulée."""
    durees = mesures.get(transition, [])
    prevue = prevues.get(transition) if prevues else None
    n = len(durees)
    if n == 0 and prevue is None:
        return None
    moyenne_p, ecart_p = prevue if prevue else (0.0, 0.0)
    k = H("poids_prevision") if prevue else 0
    moyenne_m = statistics.mean(durees) if n else 0.0
    variance_m = statistics.pvariance(durees) if n > 1 else ecart_p ** 2
    moyenne = (n * moyenne_m + k * moyenne_p) / (n + k)
    variance = (n * variance_m + k * ecart_p ** 2) / (n + k)
    return moyenne, variance, n


def _reste_a_faire(etape: str) -> list[tuple]:
    """Étapes (gamme module) entre l'étape atteinte et la fin de fabrication."""
    gamme = GAMMES["module"]
    debut, fin = gamme.index(etape), gamme.index(ETAPE_FIN)
    return [("module", gamme[i], gamme[i + 1]) for i in range(debut, fin)]


def _modules_en_cours(jumeau: jm.Jumeau, t: float) -> dict[str, tuple[str, float]]:
    """{module: (dernière étape atteinte, instant)} des modules lancés, pas encore en stock PF,
    ni mis au rebut, à l'instant t."""
    gamme, en_cours = GAMMES["module"], {}
    for (type_piece, code), etapes in _premiers_scans(jumeau).items():
        atteintes = [e for e in gamme if e in etapes and etapes[e][0] <= t]
        if type_piece != "module" or not atteintes or ETAPE_FIN in atteintes:
            continue
        etat = jumeau.etat(code, t) if code in jumeau.parcours else None
        if etat is not None and etat[2] == "termine":
            continue
        derniere = max(atteintes, key=gamme.index)
        en_cours[code] = (derniere, etapes[derniere][0])
    return en_cours


def prevoir_module(etape: str, t_etape: float, t: float, mesures: dict,
                   prevues: dict | None) -> dict | None:
    """Fin prévue d'un module à l'étape `etape` depuis t_etape, vue à l'instant t : la première
    étape restante ne peut finir avant t ; fourchette p10–p90 (variances additionnées)."""
    estimations = [estimer_transition(tr, mesures, prevues) for tr in _reste_a_faire(etape)]
    if any(e is None for e in estimations):
        return None
    premiere, *suite = estimations
    fin_premiere = max(t_etape + premiere[0], t)
    fin = fin_premiere + sum(e[0] for e in suite)
    demi = Z_FOURCHETTE * math.sqrt(sum(e[1] for e in estimations))
    en_retard = t > t_etape + premiere[0] + Z_FOURCHETTE * math.sqrt(premiere[1])
    return {"fin": fin, "basse": max(t, fin - demi), "haute": fin + demi,
            "mesures": sum(e[2] for e in estimations), "en_retard": en_retard}


def prevoir_fins(jumeau: jm.Jumeau, prevues: dict | None, t: float) -> list[dict]:
    """Une ligne par module en cours à l'instant t, la fin la plus proche d'abord ; fin None si
    une étape restante n'a été ni mesurée ni simulée."""
    mesures = {tr: [p["duree"] for p in passages]
               for tr, passages in passages_par_transition(jumeau).items()}
    lignes = []
    for code, (etape, t_etape) in _modules_en_cours(jumeau, t).items():
        prevision = prevoir_module(etape, t_etape, t, mesures, prevues) or {
            "fin": None, "basse": None, "haute": None, "mesures": 0, "en_retard": False}
        lignes.append({"code": code, "etape": etape, "t_etape": t_etape, **prevision})
    return sorted(lignes, key=lambda l: (l["fin"] is None, l["fin"] or 0))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. Validation de la prévision sur la simulation
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _modules_termines_simules(usine) -> list[dict]:
    """{étape: instant} des modules simulés allés jusqu'à la fin de fabrication, par OF."""
    normaux = [e for e in usine.tracabilite.journal if not e["alerte"]]
    passages = jm._premiers_passages(normaux, "id", "t", lambda t: t)
    complets = [etapes for (type_piece, _), etapes in passages.items()
                if type_piece == "module" and ETAPE_DEBUT in etapes and ETAPE_FIN in etapes]
    return sorted(complets, key=lambda etapes: etapes[ETAPE_DEBUT])


def evaluer_prevision(usine) -> dict | None:
    """Erreur moyenne absolue (min) de la prévision, apprise sur la première moitié des modules
    terminés et mesurée sur la seconde à chacune de leurs étapes, face à la prévision naïve
    « OF + délai moyen » ; None s'il y a trop peu de modules."""
    modules = _modules_termines_simules(usine)
    moitie = len(modules) // 2
    if moitie < 2:
        return None
    apprentissage, essai = modules[:moitie], modules[moitie:]
    mesures = jm._durees_par_transition({("module", i): e for i, e in enumerate(apprentissage)})
    delai_moyen = statistics.mean(e[ETAPE_FIN] - e[ETAPE_DEBUT] for e in apprentissage)
    erreurs, naives = [], []
    for etapes in essai:
        for etape in GAMMES["module"][:GAMMES["module"].index(ETAPE_FIN)]:
            if etape not in etapes:
                continue
            prevision = prevoir_module(etape, etapes[etape], etapes[etape], mesures, None)
            if prevision is not None:
                erreurs.append(abs(prevision["fin"] - etapes[ETAPE_FIN]))
                naive = max(etapes[etape], etapes[ETAPE_DEBUT] + delai_moyen)
                naives.append(abs(naive - etapes[ETAPE_FIN]))
    return {"erreur_moyenne_min": statistics.mean(erreurs), "erreur_naive_min": statistics.mean(
        naives), "modules_testes": len(essai), "previsions": len(erreurs)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 5. Tests intégrés (py -3 avelis_flux/analyse_jumeau.py)
# ═════════════════════════════════════════════════════════════════════════════════════════════

PAS_NORMAL_S, PAS_LENT_S = 120, 600  # durée d'un passage au poste 2 : normale, ralentie


def atelier_poste_lent(pods: int = 8, lents: int = 3):
    """Atelier de scan en mémoire : `pods` pods passent les 4 postes ; les `lents` derniers
    restent 5 fois plus longtemps au poste 2 (parois). Renvoie (base, horloge, codes des pods)."""
    base, horloge = jm._base_de_test()
    codes = []
    for rang in range(pods):
        pod = base.creer_module_complet("Lyon", avec_composants=False)[1]
        for poste in jm.GAMME_POD_TEST:
            lent = poste == "pod_2" and rang >= pods - lents
            jm._scanner(base, horloge, pod, poste, PAS_LENT_S if lent else PAS_NORMAL_S)
        codes.append(pod)
    return base, horloge, codes


def test_poste_lent_detecte():
    base, horloge, pods = atelier_poste_lent()
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    lignes = {l["etape"]: l for l in analyser_postes(jumeau)}
    parois = lignes["Poste 2 Parois + étanchéité"]
    assert parois["etat"] == ANORMAL and parois["poste"] == "pod_2"
    assert math.isclose(parois["reference"], 2) and math.isclose(parois["moyenne_recente"], 10)
    assert parois["origine"] == "passages antérieurs" and math.isclose(parois["rapport"], 5)
    assert set(parois["anormaux"]) == set(pods[-3:])
    assert lignes["Poste 3 Plomberie-élec"]["etat"] == NORMAL
    assert analyser_postes(jumeau)[0]["etat"] == ANORMAL  # le plus inquiétant d'abord


def test_poste_sans_historique_compare_a_la_simulation():
    base, horloge, pods = atelier_poste_lent(pods=3, lents=0)
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    transition = ("pod", "Poste 1 Châssis", "Poste 2 Parois + étanchéité")
    sans = {l["etape"]: l for l in analyser_postes(jumeau)}["Poste 2 Parois + étanchéité"]
    assert sans["reference"] is None and sans["etat"] == SANS_MESURE
    ligne = {l["etape"]: l for l in analyser_postes(jumeau, {transition: (1.0, 0.1)})}[
        "Poste 2 Parois + étanchéité"]
    assert ligne["origine"] == "simulation" and ligne["etat"] == ANORMAL  # 2 min pour 1 prévue


def test_estimation_rapprochee_de_la_simulation():
    transition = ("module", "Kitting", "Panneaux 2D terminés")
    mesures = {transition: [10.0, 20.0]}
    moyenne, variance, n = estimer_transition(transition, mesures, {transition: (40.0, 5.0)})
    assert math.isclose(moyenne, (2 * 15 + 5 * 40) / 7) and math.isclose(variance, 25) and n == 2
    assert estimer_transition(transition, mesures, None)[:2] == (15.0, 25.0)
    assert estimer_transition(transition, {}, {transition: (40.0, 5.0)})[:2] == (40.0, 25.0)
    assert estimer_transition(transition, {}, None) is None


def test_fin_prevue_d_un_module_en_cours():
    base, horloge, m1, m2 = jm._atelier_de_test()
    module = base.creer_module_complet("Lyon", avec_composants=False)[0]
    jm._scanner(base, horloge, module, "bureau")
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    t = jumeau.duree()
    lignes = {l["code"]: l for l in prevoir_fins(jumeau, None, t)}
    assert m1[0] not in lignes  # expédié
    assert lignes[module]["etape"] == "OF lancé" and lignes[m2[0]]["etape"] == "OF lancé"
    # une seule mesure par étape (le module expédié) : fin = début de la 2e étape + le reste
    mesures = {tr: [p["duree"] for p in ps] for tr, ps in passages_par_transition(jumeau).items()}
    premiere, *suite = _reste_a_faire("OF lancé")
    attendu = (max(lignes[module]["t_etape"] + mesures[premiere][0], t)
               + sum(mesures[tr][0] for tr in suite))
    assert math.isclose(lignes[module]["fin"], attendu)
    assert lignes[module]["basse"] == lignes[module]["fin"] <= lignes[module]["haute"]
    assert lignes[m2[0]]["en_retard"]  # lancé il y a longtemps, toujours à l'OF


def test_prevision_meilleure_que_la_prevision_naive():
    usine = sim.Usine(1500, jm.IMPLANTATION_JUMEAU, "unique", sim.QR, 5, 42).executer()
    bilan = evaluer_prevision(usine)
    assert bilan["previsions"] > bilan["modules_testes"] > 10
    assert 0 < bilan["erreur_moyenne_min"] < bilan["erreur_naive_min"]


def test_texte_duree():
    assert texte_duree(None) == "—" and texte_duree(0.5) == "30 s"
    assert texte_duree(12) == "12 min" and texte_duree(135) == "2 h 15"


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
