"""Décisions proposées par le jumeau numérique, validées par un humain avant d'être envoyées.

Le jumeau évalue des règles sur l'état reconstitué par les scans et sur l'analyse
(analyse_jumeau.py) ; chaque règle déclenchée devient une décision « proposée ». Rien ne part
vers un poste sans validation : l'opérateur du PC l'envoie (message modifiable) ou l'ignore
(humain dans la boucle, Industrie 5.0). Une consigne envoyée arrive sur le téléphone du poste
par l'API du serveur de scan (POST /api/consignes), comme celles du PC.

Règles :
  - poste anormalement lent (option B) → le poste et le bureau ;
  - pièce bloquée : pas de nouveau scan depuis seuil_piece_bloquee × la durée estimée de
    l'étape suivante, dans la journée → le poste du dernier scan et le bureau ;
  - défauts répétés : seuil_defauts_repetes défauts de même catégorie au même poste dans la
    fenêtre → le poste et le bureau ;
  - retard sur l'objectif du jour (cadence du scénario), un jour où l'on scanne → le bureau.
Les retards kanban et les lots à isoler sont déjà traités par l'application de scan.

Une décision n'est pas reproposée tant qu'elle attend, ni pendant delai_repetition_decision_min
après avoir été envoyée ou ignorée. Ce module n'importe aucun module graphique.
"""

import sys

import analyse_jumeau as ana
import jumeau as jm
import modele as m
from modele import H

POSTE_BUREAU = "bureau"  # poste « Bureaux / pilotage » de l'application de scan
PROPOSEE, ENVOYEE, IGNOREE = "proposée", "envoyée", "ignorée"
REGLE_LENT, REGLE_BLOQUEE, REGLE_DEFAUTS, REGLE_OBJECTIF = (
    "Poste anormalement lent", "Pièce bloquée", "Défauts répétés", "Retard sur l'objectif")


def _destinataires(poste: str) -> list[str]:
    """Le poste concerné, puis le bureau (une seule fois)."""
    return [poste] if poste == POSTE_BUREAU else [poste, POSTE_BUREAU]


def _candidat(cle: str, regle: str, destinataires: list[str], message: str, motif: str) -> dict:
    """Décision candidate : clé d'unicité, règle, postes destinataires, consigne et motif."""
    return {"cle": cle, "regle": regle, "destinataires": destinataires, "message": message,
            "motif": motif}


def regle_postes_lents(lignes_postes: list[dict]) -> list[dict]:
    """Un candidat par étape dont les derniers passages sont anormalement lents."""
    candidats = []
    for l in lignes_postes:
        if l["etat"] != ana.ANORMAL:
            continue
        message = (f"{l['zone']} ({l['poste']}) : les derniers passages « {l['etape']} » "
                   f"durent {m.formater_nombre(l['rapport'], 1)} fois la normale. Vérifier le "
                   "poste (outil, méthode, approvisionnement).")
        motif = (f"Moyenne des {H('passages_recents_derive')} derniers passages : "
                 f"{ana.texte_duree(l['moyenne_recente'])}, contre "
                 f"{ana.texte_duree(l['reference'])} ({l['origine']}) ; seuil "
                 f"{m.formater_nombre(1 + H('seuil_ecart_jumeau'), 1)} fois.")
        candidats.append(_candidat(f"lent:{l['poste']}:{l['etape']}", REGLE_LENT,
                                   _destinataires(l["poste"]), message, motif))
    return candidats


def _derniers_scans(jumeau: jm.Jumeau, t: float) -> dict[str, dict]:
    """{code: dernier scan accepté d'une étape de gamme jusqu'à t} des modules et des pods."""
    derniers = {}
    for e in jumeau.evenements:
        if (e["resultat"] == "accepte" and e["type"] in ana.GAMMES
                and e["evenement"] in ana.GAMMES[e["type"]] and jumeau.instant(e["t"]) <= t):
            derniers[e["code"]] = e
    return derniers


def _etape_suivante(evenement: dict) -> tuple | None:
    """Transition suivante dans la gamme ; None en fin de gamme ou en stock de produits finis
    (l'attente du camion n'est pas un blocage de fabrication)."""
    gamme = ana.GAMMES[evenement["type"]]
    rang = gamme.index(evenement["evenement"])
    if rang + 1 >= len(gamme) or evenement["evenement"] == ana.ETAPE_FIN:
        return None
    return (evenement["type"], gamme[rang], gamme[rang + 1])


def _pieces_bloquees(jumeau: jm.Jumeau, t: float, prevues: dict | None) -> dict:
    """{(poste, zone, étape, suivante): [(code, attente)]} des pièces en cours, scannées
    aujourd'hui, sans nouveau scan depuis seuil_piece_bloquee fois la durée estimée de leur étape
    suivante (une nuit d'arrêt n'est pas un blocage)."""
    mesures = {tr: [p["duree"] for p in ps]
               for tr, ps in ana.passages_par_transition(jumeau).items()}
    groupes: dict = {}
    for code, e in _derniers_scans(jumeau, t).items():
        suivante, t_scan = _etape_suivante(e), jumeau.instant(e["t"])
        etat = jumeau.etat(code, t) if code in jumeau.parcours else None
        if (suivante is None or etat is None or etat[2] != "en_cours"
                or jumeau.date(t_scan).date() != jumeau.date(t).date()):
            continue
        estimation = ana.estimer_transition(suivante, mesures, prevues)
        if estimation is not None and t - t_scan > H("seuil_piece_bloquee") * estimation[0]:
            cle = (e["poste"] or POSTE_BUREAU, e["zone"], e["evenement"], suivante[2],
                   estimation[0])
            groupes.setdefault(cle, []).append((code, t - t_scan))
    return groupes


def regle_pieces_bloquees(jumeau: jm.Jumeau, t: float, prevues: dict | None) -> list[dict]:
    """Une décision par poste et par étape où des pièces n'avancent plus (regroupées : une seule
    boîte de dialogue pour plusieurs pièces)."""
    candidats = []
    for (poste, zone, etape, suivante, estimee), pieces in _pieces_bloquees(
            jumeau, t, prevues).items():
        pieces.sort(key=lambda piece: -piece[1])
        codes = ", ".join(code for code, _ in pieces)
        qui = (f"{codes} n'a" if len(pieces) == 1 else f"{len(pieces)} pièces ({codes}) n'ont")
        message = (f"{qui} pas avancé après « {etape} » ({zone}) : attente jusqu'à "
                   f"{ana.texte_duree(pieces[0][1])}. Vérifier où elles en sont.")
        motif = (f"Étape suivante « {suivante} » estimée à {ana.texte_duree(estimee)} ; seuil "
                 f"{m.formater_nombre(H('seuil_piece_bloquee'), 1)} fois.")
        candidats.append(_candidat(f"bloquee:{poste}:{etape}", REGLE_BLOQUEE,
                                   _destinataires(poste), message, motif))
    return candidats


def regle_defauts_repetes(jumeau: jm.Jumeau, t: float) -> list[dict]:
    """Postes où au moins seuil_defauts_repetes défauts de même catégorie ont été déclarés dans
    la fenêtre précédant t (catégorie : début du message du défaut)."""
    groupes: dict[tuple, list[str]] = {}
    for e in jumeau.evenements:
        if (e["evenement"] == jm.DEFAUT and e["poste"]
                and 0 <= t - jumeau.instant(e["t"]) <= H("fenetre_defauts_min")):
            categorie = (e["message"] or "Autre").split(" (")[0]
            groupes.setdefault((e["poste"], e["zone"], categorie), []).append(e["code"])
    candidats = []
    for (poste, zone, categorie), codes in groupes.items():
        if len(codes) < H("seuil_defauts_repetes"):
            continue
        message = (f"{len(codes)} défauts « {categorie} » en moins de "
                   f"{H('fenetre_defauts_min')} min à {zone} ({poste}). Contrôler l'outil et la "
                   "méthode avant de continuer.")
        candidats.append(_candidat(f"defauts:{poste}:{categorie}", REGLE_DEFAUTS,
                                   _destinataires(poste), message,
                                   "Pièces concernées : " + ", ".join(codes)))
    return candidats


def regle_retard_objectif(jumeau: jm.Jumeau, t: float, modules_jour: float) -> list[dict]:
    """Bureau prévenu si les modules terminés aujourd'hui sont sous seuil_retard_objectif de
    l'objectif à cette heure (au moins un module attendu, et des scans aujourd'hui)."""
    jour = jumeau.date(t).date()
    if not any(e["resultat"] == "accepte" and jumeau.date(jumeau.instant(e["t"])).date() == jour
               and jumeau.instant(e["t"]) <= t for e in jumeau.evenements):
        return []
    objectif = jumeau.objectif_a(t, modules_jour)
    debut_jour = jumeau.instant(jumeau.date(t).replace(hour=0, minute=0, second=0,
                                                       microsecond=0).timestamp())
    termines = sum(1 for x in jumeau.instants("module", ana.ETAPE_FIN, t) if x >= debut_jour)
    if objectif < 1 or termines >= H("seuil_retard_objectif") * objectif:
        return []
    message = (f"{termines} module(s) terminé(s) aujourd'hui pour "
               f"{m.formater_nombre(objectif, 1)} attendus à cette heure. Revoir les priorités "
               "ou renforcer le poste goulot.")
    motif = (f"Seuil : {m.formater_pourcentage(H('seuil_retard_objectif'))} de l'objectif ; "
             f"cadence du scénario : {m.formater_nombre(modules_jour, 2)} modules par jour.")
    return [_candidat(f"objectif:{jour.isoformat()}", REGLE_OBJECTIF, [POSTE_BUREAU], message,
                      motif)]


class Decideur:
    """Propose les décisions, garde leur historique et applique le choix de l'humain."""

    def __init__(self):
        self.decisions: list[dict] = []

    def en_attente(self) -> list[dict]:
        """Décisions proposées, ni envoyées ni ignorées."""
        return [d for d in self.decisions if d["statut"] == PROPOSEE]

    def _deja_traitee(self, cle: str, maintenant_s: float) -> bool:
        """Vrai si la décision attend encore, ou a été tranchée il y a moins du délai."""
        delai_s = H("delai_repetition_decision_min") * jm.SECONDES_PAR_MINUTE
        return any(d["cle"] == cle and (d["statut"] == PROPOSEE
                                        or maintenant_s - d["t_statut"] < delai_s)
                   for d in self.decisions)

    def evaluer(self, jumeau: jm.Jumeau, maintenant_s: float, modules_jour: float,
                prevues: dict | None = None,
                lignes_postes: list[dict] | None = None) -> list[dict]:
        """Évalue toutes les règles à l'instant réel maintenant_s ; renvoie les décisions
        nouvellement proposées (déjà ajoutées à l'historique)."""
        if not jumeau.evenements:
            return []
        t = jumeau.instant(maintenant_s)
        if lignes_postes is None:
            lignes_postes = ana.analyser_postes(jumeau, prevues)
        candidats = (regle_postes_lents(lignes_postes) + regle_pieces_bloquees(jumeau, t, prevues)
                     + regle_defauts_repetes(jumeau, t)
                     + regle_retard_objectif(jumeau, t, modules_jour))
        nouvelles = []
        for c in candidats:
            if not self._deja_traitee(c["cle"], maintenant_s):
                decision = {**c, "id": len(self.decisions) + 1, "t_proposee": maintenant_s,
                            "statut": PROPOSEE, "t_statut": None, "envoye": None}
                self.decisions.append(decision)
                nouvelles.append(decision)
        return nouvelles

    def envoyer(self, decision: dict, source, maintenant_s: float,
                message: str | None = None) -> None:
        """Envoie la consigne (éventuellement modifiée par l'humain) à chaque destinataire par la
        source des scans ; jm.SourceIndisponible si elle ne sait pas envoyer."""
        texte = (message or decision["message"]).strip()
        if not hasattr(source, "envoyer_consigne"):
            raise jm.SourceIndisponible("cette source de scans ne peut pas envoyer de consigne")
        for poste in decision["destinataires"]:
            source.envoyer_consigne(poste, texte)
        decision.update(statut=ENVOYEE, t_statut=maintenant_s, envoye=texte)

    def ignorer(self, decision: dict, maintenant_s: float) -> None:
        """L'humain ne donne pas suite : la décision n'est pas reproposée avant le délai."""
        decision.update(statut=IGNOREE, t_statut=maintenant_s)

    def compter(self) -> dict[str, int]:
        """Nombre de décisions par statut."""
        return {statut: sum(d["statut"] == statut for d in self.decisions)
                for statut in (PROPOSEE, ENVOYEE, IGNOREE)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Tests intégrés (py -3 avelis_flux/decisions.py)
# ═════════════════════════════════════════════════════════════════════════════════════════════

MODULES_JOUR_TEST = 8.0


def _jumeau_de(base) -> jm.Jumeau:
    """Jumeau qui a lu toute la base."""
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    return jumeau


def test_poste_lent_propose_au_poste_et_au_bureau():
    base, horloge, pods = ana.atelier_poste_lent()
    decideur = Decideur()
    nouvelles = decideur.evaluer(_jumeau_de(base), horloge[0], MODULES_JOUR_TEST)
    lentes = [d for d in nouvelles if d["regle"] == REGLE_LENT]
    assert len(lentes) == 1 and lentes[0]["destinataires"] == ["pod_2", POSTE_BUREAU]
    assert "5 fois la normale" in lentes[0]["message"].replace(",0", "")
    assert all(d["statut"] == PROPOSEE for d in nouvelles)  # rien n'est envoyé sans l'humain
    assert not base.consignes()


def test_envoi_apres_validation_humaine():
    base, horloge, pods = ana.atelier_poste_lent()
    decideur = Decideur()
    decision = next(d for d in decideur.evaluer(_jumeau_de(base), horloge[0], MODULES_JOUR_TEST)
                    if d["regle"] == REGLE_LENT)
    decideur.envoyer(decision, base, horloge[0], "Message modifié par le chef d'atelier")
    textes = {(c["poste"], c["message"]) for c in base.consignes(actives=True)}
    assert ("pod_2", "Message modifié par le chef d'atelier") in textes
    assert (POSTE_BUREAU, "Message modifié par le chef d'atelier") in textes
    assert decision["statut"] == ENVOYEE and decideur.compter()[ENVOYEE] == 1
    try:
        decideur.envoyer(decision, object(), horloge[0])
        raise AssertionError("envoi accepté par une source qui ne sait pas envoyer")
    except jm.SourceIndisponible:
        pass


def test_pas_de_repetition_avant_le_delai():
    base, horloge, pods = ana.atelier_poste_lent()
    jumeau, decideur = _jumeau_de(base), Decideur()
    premieres = decideur.evaluer(jumeau, horloge[0], MODULES_JOUR_TEST)
    assert premieres and decideur.evaluer(jumeau, horloge[0] + 10, MODULES_JOUR_TEST) == []
    for decision in premieres:
        decideur.ignorer(decision, horloge[0])
    delai_s = H("delai_repetition_decision_min") * jm.SECONDES_PAR_MINUTE
    assert decideur.evaluer(jumeau, horloge[0] + delai_s - 1, MODULES_JOUR_TEST) == []
    reproposees = decideur.evaluer(jumeau, horloge[0] + delai_s + 1, MODULES_JOUR_TEST)
    assert {d["cle"] for d in reproposees} >= {d["cle"] for d in premieres
                                                if d["regle"] == REGLE_LENT}


def test_piece_bloquee_dans_la_journee_seulement():
    base, horloge, pods = ana.atelier_poste_lent(pods=4, lents=0)
    pod = base.creer_module_complet("Lyon", avec_composants=False)[1]
    jm._scanner(base, horloge, pod, "kitting")
    jm._scanner(base, horloge, pod, "pod_1")
    jumeau = _jumeau_de(base)
    t_scan = horloge[0]
    attente_normale = Decideur().evaluer(jumeau, t_scan + 3 * 60, MODULES_JOUR_TEST)
    assert not [d for d in attente_normale if d["regle"] == REGLE_BLOQUEE]  # 3 min pour 2
    bloquees = [d for d in Decideur().evaluer(jumeau, t_scan + 5 * 60, MODULES_JOUR_TEST)
                if d["regle"] == REGLE_BLOQUEE]
    assert [d["cle"] for d in bloquees] == ["bloquee:pod_1:Poste 1 Châssis"]
    assert bloquees[0]["destinataires"] == ["pod_1", POSTE_BUREAU] and pod in bloquees[0][
        "message"]
    lendemain = t_scan + 24 * 3600
    assert not [d for d in Decideur().evaluer(jumeau, lendemain, MODULES_JOUR_TEST)
                if d["regle"] == REGLE_BLOQUEE]


def test_defauts_repetes():
    base, horloge, pods = ana.atelier_poste_lent(pods=2, lents=0)
    for _ in range(2):
        pod = base.creer_module_complet("Lyon", avec_composants=False)[1]
        jm._scanner(base, horloge, pod, "kitting")
        horloge[0] += 120
        base.scanner(pod, "pod_1", "OP1", "defaut", {"categorie": "Dimension / géométrie",
                                                     "cause": "Machine"}, t_client=horloge[0])
    jumeau = _jumeau_de(base)
    defauts = [d for d in Decideur().evaluer(jumeau, horloge[0], MODULES_JOUR_TEST)
               if d["regle"] == REGLE_DEFAUTS]
    assert len(defauts) == 1 and defauts[0]["destinataires"] == ["pod_1", POSTE_BUREAU]
    assert "2 défauts « Dimension / géométrie »" in defauts[0]["message"]
    plus_tard = horloge[0] + (H("fenetre_defauts_min") + 1) * jm.SECONDES_PAR_MINUTE
    assert not [d for d in Decideur().evaluer(jumeau, plus_tard, MODULES_JOUR_TEST)
                if d["regle"] == REGLE_DEFAUTS]


def test_retard_objectif_un_jour_de_production():
    base, horloge, pods = ana.atelier_poste_lent(pods=1, lents=0)
    jumeau = _jumeau_de(base)
    objectif = jumeau.objectif_a(jumeau.instant(horloge[0]), MODULES_JOUR_TEST)
    retards = [d for d in Decideur().evaluer(jumeau, horloge[0], MODULES_JOUR_TEST)
               if d["regle"] == REGLE_OBJECTIF]
    assert objectif >= 1 and len(retards) == 1 and retards[0]["destinataires"] == [POSTE_BUREAU]
    lendemain = horloge[0] + 24 * 3600  # aucun scan ce jour-là : pas de retard proposé
    assert not [d for d in Decideur().evaluer(jumeau, lendemain, MODULES_JOUR_TEST)
                if d["regle"] == REGLE_OBJECTIF]


def test_base_vide_rien_a_proposer():
    assert Decideur().evaluer(jm.Jumeau(), 0, MODULES_JOUR_TEST) == []


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
