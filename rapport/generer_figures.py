"""Données et figures du rapport scientifique (rapport/), calculées par le modèle et la simulation.

    py -3 rapport/generer_figures.py

Écrit rapport/donnees_rapport.json et les figures vectorielles rapport/figures/*.pdf. Les valeurs
propres aux cas d'application (parts de la demande, positions des satellites, cadences) sont des
HYPOTHÈSES de scénario, déclarées en tête de fichier ; tout le reste vient de avelis_flux.
"""

import json
import pathlib
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(DOSSIER.parent / "avelis_flux"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import analyse_jumeau as ana  # noqa: E402
import jumeau as jm  # noqa: E402
import modele as m  # noqa: E402
import simulation as sim  # noqa: E402

FIGURES = DOSSIER / "figures"
CADENCE = 1500
GRAINE, JOURS = 42, 10

# ── Hypothèses de scénario (H), propres au rapport ─────────────────────────────────────────────
# Cas « grands chantiers nucléaires » : hébergement des salariés de Gravelines (EPR2) et de
# Flamanville. Parts de la demande : H. Cadence du programme : H (cf. section 6 du rapport).
CAS_NUCLEAIRE = {
    "chantiers": {"Gravelines": (51.000, 2.130, 0.70), "Flamanville": (49.537, -1.881, 0.30)},
    "satellites": {"Arras": (50.291, 2.778), "Caen": (49.183, -0.371)},
    "cadence": 1200,
}
# Variante : unités d'assemblage foraines au plus près des chantiers (Dunkerque, Cherbourg).
SATELLITES_FORAINS = {"Dunkerque": (51.034, 2.377), "Cherbourg": (49.640, -1.616)}
# Cas « classique » : programme résidentiel de la métropole de Lyon.
CAS_CLASSIQUE = {
    "chantiers": {"Lyon": (45.760, 4.840, 1.0)},
    "satellites": {"Lyon-Sud": (45.650, 4.900)},
    "cadence": 300,
}

STYLE = {"font.family": "serif", "font.size": 9, "axes.spines.top": False,
         "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
         "savefig.bbox": "tight", "legend.frameon": False}
BLEU, ORANGE, GRIS, ROUGE, VERT = "#1f4e79", "#d9822b", "#7f7f7f", "#b22222", "#3b7d3b"


def resultats_simulation() -> dict:
    """Indicateurs clés des trois implantations (usine unique, QR code), même graine."""
    sortie = {}
    for implantation in m.IMPLANTATIONS:
        usine = sim.Usine(CADENCE, implantation, "unique", sim.QR, JOURS, GRAINE).executer()
        r = usine.resultats()
        sortie[implantation] = {
            "taux_atteinte": r["taux_atteinte"], "debit": r["debit_regime_etabli"],
            "delai_moyen_h": r["delai_fabrication_moyen_min"] / 60,
            "delai_p90_h": r["delai_fabrication_p90_min"] / 60,
            "en_cours": r["en_cours_moyen"], "distance_totale_km": r["distance_totale"] / 1000,
            "sous_ensemble_m": r["distance_moyenne_sous_ensemble"],
            "ruptures_attentes": r["total_ruptures_attentes"],
            "utilisation": r["utilisation"], "distances_plan": m.distances_sous_ensemble(
                implantation), "croisements": m.croisements_flux(implantation)}
    return sortie


def resultats_jumeau() -> dict:
    """Option A : précision de la prévision sur la simulation de référence ; option B :
    détection d'un poste ralenti sur un atelier de scan en mémoire."""
    usine = sim.Usine(CADENCE, jm.IMPLANTATION_JUMEAU, "unique", sim.QR, JOURS, GRAINE).executer()
    precision = ana.evaluer_prevision(usine)
    base, _horloge, _pods = ana.atelier_poste_lent()
    jumeau = jm.Jumeau()
    jumeau.actualiser(base)
    lignes = [{"etape": l["etape"], "etat": l["etat"], "rapport": l["rapport"],
               "reference_min": l["reference"], "recente_min": l["moyenne_recente"],
               "passages": l["passages"]} for l in ana.analyser_postes(jumeau)]
    return {"precision": precision, "postes": lignes}


def reseau(cas: dict, satellites: dict | None = None) -> dict:
    """Comparaison A / B (variantes proche et hybride) et sensibilité, pour un cas donné."""
    m.appliquer_parametres({}, cas["chantiers"], satellites or cas["satellites"])
    try:
        sortie = {}
        for variante in m.VARIANTES:
            comparaison = m.comparaison_reseau(cas["cadence"], variante)
            sortie[variante] = {code: {cle: comparaison[code][cle] for cle in (
                "cout_par_logement", "cout_total_an", "cout_transport_an", "couts_fixes_an",
                "co2_t_an", "distance_moyenne_km", "delai_moyen_h", "km_an",
                "satellites_utilises", "part_directe")} for code in ("A", "B")}
            sortie[variante]["bascule"] = m.point_bascule(variante)
        sortie["sensibilite"] = m.sensibilite_reseau("proche")
        sortie["distances"] = {nom: m.distance_route_km(m.TORCY, lieu)
                               for nom, lieu in cas["chantiers"].items()}
        return sortie
    finally:
        m.appliquer_parametres({}, m.CHANTIERS_DEFAUT, m.SATELLITES_DEFAUT)


def reseau_national() -> dict:
    """Réseau national par défaut (8 métropoles), à la cadence de référence."""
    sortie = {}
    for variante in m.VARIANTES:
        c = m.comparaison_reseau(CADENCE, variante)
        sortie[variante] = {code: {"cout_par_logement": c[code]["cout_par_logement"],
                                   "co2_t_an": c[code]["co2_t_an"],
                                   "delai_moyen_h": c[code]["delai_moyen_h"]}
                            for code in ("A", "B")}
        sortie[variante]["bascule"] = m.point_bascule(variante)
    return sortie


# ── Figures ────────────────────────────────────────────────────────────────────────────────────

def _enregistrer(figure, nom: str) -> None:
    figure.savefig(FIGURES / f"{nom}.pdf")
    plt.close(figure)


def figure_carte_nucleaire(donnees: dict) -> None:
    """Carte : Torcy, chantiers, satellites, liaisons directes (A) et via satellite (B)."""
    figure, ax = plt.subplots(figsize=(4.6, 4.4))
    lon, lat = zip(*m.CONTOUR_FRANCE)
    ax.fill(lon, lat, color="#f2f2f2", edgecolor=GRIS, linewidth=0.6)
    torcy = m.TORCY
    for nom, (la, lo, part) in CAS_NUCLEAIRE["chantiers"].items():
        ax.plot([torcy[1], lo], [torcy[0], la], color=BLEU, linewidth=1 + 4 * part,
                alpha=0.8, label="A : convoi direct" if nom == "Gravelines" else None)
        sat = min(CAS_NUCLEAIRE["satellites"], key=lambda s: m.haversine_km(
            (la, lo), CAS_NUCLEAIRE["satellites"][s]))
        sla, slo = CAS_NUCLEAIRE["satellites"][sat]
        ax.plot([torcy[1], slo, lo], [torcy[0], sla, la], color=ORANGE, linewidth=1,
                linestyle="--", label="B : semi + convoi via satellite"
                if nom == "Gravelines" else None)
        ax.plot(lo, la, "o", color=ROUGE, markersize=6)
        ax.annotate(f"{nom}\n{donnees['distances'][nom]:.0f} km", (lo, la),
                    textcoords="offset points", xytext=(6, 4), fontsize=8)
    for nom, (la, lo) in CAS_NUCLEAIRE["satellites"].items():
        ax.plot(lo, la, "s", color=ORANGE, markersize=5)
        ax.annotate(nom, (lo, la), textcoords="offset points", xytext=(5, -10), fontsize=7)
    ax.plot(torcy[1], torcy[0], "*", color=BLEU, markersize=12)
    ax.annotate("Torcy (71)", (torcy[1], torcy[0]), textcoords="offset points",
                xytext=(6, -4), fontsize=8)
    ax.set_xlim(-5.3, 8.5)
    ax.set_ylim(42.2, 51.4)
    ax.set_aspect(1 / 0.68)
    ax.set_xlabel("longitude (°)")
    ax.set_ylabel("latitude (°)")
    ax.legend(loc="lower left", fontsize=7)
    _enregistrer(figure, "carte_nucleaire")


def figure_sensibilite(nucleaire: dict, classique: dict) -> None:
    """Coût logistique par logement selon la cadence : A et B, deux cas."""
    figure, axes = plt.subplots(1, 2, figsize=(6.6, 2.6), sharey=False)
    for ax, (titre, donnees) in zip(axes, (("Gravelines + Flamanville", nucleaire),
                                           ("Métropole de Lyon", classique))):
        s = donnees["sensibilite"]
        ax.plot(s["cadences"], [v / 1000 for v in s["A"]], color=BLEU, label="A : usine unique")
        ax.plot(s["cadences"], [v / 1000 for v in s["B"]], color=ORANGE,
                label="B : usine mère + satellites")
        haut = 2.2 * max(s["A"]) / 1000
        ax.set_ylim(0, haut)
        bascule = donnees["proche"]["bascule"]
        if bascule:
            ax.axvline(bascule, color=GRIS, linestyle=":", linewidth=1)
            ax.annotate(f"bascule : {bascule} log./an", (bascule, haut * 0.9),
                        xytext=(5, 0), textcoords="offset points", fontsize=7)
        ax.set_title(titre, fontsize=9)
        ax.set_xlabel("cadence (logements/an)")
    axes[0].set_ylabel("coût logistique (k€/logement)")
    axes[1].legend(fontsize=7, loc="lower right")
    figure.tight_layout()
    _enregistrer(figure, "sensibilite_reseaux")


def figure_implantations(simulation: dict) -> None:
    """Distances de manutention par gamme et par implantation."""
    figure, ax = plt.subplots(figsize=(5.4, 2.4))
    noms = {m.IMPLANTATION_ACTUELLE: "Actuelle\n(site seul)",
            m.IMPLANTATION_PROPOSEE: "Proposée\n(flux en U)",
            m.IMPLANTATION_OPTIMISEE: "Optimisée"}
    ordre = [m.IMPLANTATION_ACTUELLE, m.IMPLANTATION_PROPOSEE, m.IMPLANTATION_OPTIMISEE]
    largeur = 0.25
    for rang, (gamme, couleur) in enumerate((("pod", ORANGE), ("2D", VERT), ("module", BLEU))):
        valeurs = [simulation[i]["distances_plan"][gamme] for i in ordre]
        x = [k + (rang - 1) * largeur for k in range(len(ordre))]
        barres = ax.bar(x, valeurs, largeur, color=couleur, label=f"gamme {gamme}")
        ax.bar_label(barres, fmt="%.0f", fontsize=7, padding=1)
    ax.set_xticks(range(len(ordre)), [noms[i] for i in ordre])
    ax.set_ylabel("distance (m)")
    ax.legend(fontsize=7, ncols=3, loc="upper right")
    ax.set_ylim(0, 680)
    _enregistrer(figure, "distances_implantations")


def figure_option_b(jumeau: dict) -> None:
    """Option B : rapport durée récente / référence par étape (atelier au poste 2 ralenti)."""
    lignes = [l for l in jumeau["postes"] if l["rapport"]]
    lignes.sort(key=lambda l: l["rapport"])
    figure, ax = plt.subplots(figsize=(5.4, 2.3))
    couleurs = {ana.ANORMAL: ROUGE, ana.A_SURVEILLER: ORANGE, ana.NORMAL: VERT}
    ax.barh([l["etape"] for l in lignes], [l["rapport"] for l in lignes],
            color=[couleurs.get(l["etat"], GRIS) for l in lignes])
    for seuil, texte in ((1.25, "à surveiller"), (1.5, "anormal")):
        ax.axvline(seuil, color=GRIS, linestyle=":", linewidth=1)
        ax.annotate(f"{texte} ({seuil:g})".replace(".", ","), (seuil, 1.6), xytext=(3, 0),
                    textcoords="offset points", fontsize=7, color=GRIS)
    ax.set_xlabel("durée récente / durée de référence")
    ax.tick_params(axis="y", labelsize=7)
    _enregistrer(figure, "option_b_postes")


def figure_tracabilite() -> None:
    """Part des modules tracés de bout en bout et délai d'affichage, par technologie."""
    # Moyennes sur 20 graines ± 2 erreurs types (sortie de simulation.py) ; délais : graine 42
    techno = ["RFID + IoT", "QR code", "Papier"]
    tracees, erreurs = [97.5, 71.5, 30.8], [0.8, 1.3, 2.5]
    delais = [0.1, 3.0, 276.5]
    figure, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.4, 2.2))
    barres = ax1.bar(techno, tracees, yerr=erreurs, capsize=3, color=[BLEU, ORANGE, GRIS])
    ax1.bar_label(barres, fmt="%.1f %%", fontsize=7, padding=4)
    ax1.set_ylabel("modules tracés (%)")
    ax1.set_ylim(0, 110)
    ax2.bar(techno, delais, color=[BLEU, ORANGE, GRIS])
    ax2.bar_label(ax2.containers[0], fmt="%.1f", fontsize=7)
    ax2.set_yscale("log")
    ax2.set_ylabel("délai alerte → écran (min)")
    figure.tight_layout()
    _enregistrer(figure, "tracabilite_technologies")


def figure_yamazumi(cadence: dict) -> None:
    """Yamazumi : temps de cycle effectif par module (cycle / nombre de ressources) face au
    takt module et à la charge maximale admise."""
    r = cadence["ressources"]
    pods_par_module = m.H("pods_par_logement") / m.H("modules_par_logement")
    postes = [("Kitting", m.H("temps_kitting") / r["postes_kitting"]["nombre"]),
              ("Ligne 2D", m.H("cycle_ligne_2d_module") / r["lignes_2d"]["nombre"]),
              ("Ligne pods\n(poste goulot)",
               max(m.H("cycle_pod_postes")) * pods_par_module / r["lignes_pods"]["nombre"]),
              ("Assemblage 3D\n(12 baies)",
               m.H("travail_assemblage_3d") / r["baies_assemblage"]["nombre"])]
    takt = cadence["takt_module_min"]
    figure, ax = plt.subplots(figsize=(5.4, 2.5))
    goulot = max(c for _, c in postes)
    couleurs = [ORANGE if c == goulot else VERT for _, c in postes]
    barres = ax.bar([p for p, _ in postes], [c for _, c in postes], color=couleurs, width=0.6)
    ax.bar_label(barres, labels=[f"{c:.0f} min ({c / takt:.0%})".replace("%", " %")
                                 for _, c in postes], fontsize=7, padding=2)
    ax.axhline(takt, color=ROUGE, linewidth=1.2)
    ax.annotate(f"takt module = {takt:.1f} min".replace(".", ","), (3.35, takt),
                xytext=(0, 3), textcoords="offset points", fontsize=7, color=ROUGE, ha="right")
    charge_max = m.H("charge_max_poste")
    ax.axhline(charge_max * takt, color=GRIS, linestyle=":", linewidth=1)
    ax.annotate(f"charge max. admise {charge_max:.0%}".replace("%", " %"),
                (-0.35, charge_max * takt), xytext=(0, 3), textcoords="offset points",
                fontsize=7, color=GRIS, ha="left")
    ax.set_ylabel("cycle effectif (min/module)")
    ax.set_ylim(0, 112)
    ax.tick_params(axis="x", labelsize=7)
    _enregistrer(figure, "yamazumi")


def _boite(ax, x, y, texte, couleur, largeur=2.3, hauteur=0.9):
    ax.add_patch(matplotlib.patches.FancyBboxPatch(
        (x - largeur / 2, y - hauteur / 2), largeur, hauteur,
        boxstyle="round,pad=0.04,rounding_size=0.12", facecolor=couleur, edgecolor="#333333",
        linewidth=0.7))
    ax.text(x, y, texte, ha="center", va="center", fontsize=6.4)


def _fleche(ax, depart, arrivee, texte="", couleur="#333333", decalage=(0, 0.18), style="-|>"):
    ax.annotate("", arrivee, depart, arrowprops={"arrowstyle": style, "color": couleur,
                                                 "linewidth": 1, "shrinkA": 2, "shrinkB": 2})
    if texte:
        x = (depart[0] + arrivee[0]) / 2 + decalage[0]
        y = (depart[1] + arrivee[1]) / 2 + decalage[1]
        ax.text(x, y, texte, ha="center", va="center", fontsize=6.5, color=couleur)


def figure_architecture() -> None:
    """Boucle du jumeau : terrain → base de scan → synchronisation → analyse → proposition →
    validation humaine → consigne au poste."""
    figure, ax = plt.subplots(figsize=(7.0, 3.3))
    ax.set_xlim(0, 17)
    ax.set_ylim(0, 7)
    ax.axis("off")
    terrain, donnees, jumeau, humain = "#e8eef6", "#fdf0e2", "#e6f2e6", "#f6e6ea"
    _boite(ax, 2.0, 5.7, "Atelier physique\n(pièces étiquetées QR)", terrain, 3.7, 1.0)
    _boite(ax, 2.0, 2.4, "Téléphone du poste\n(scan, défaut, consigne)", terrain, 3.7, 1.0)
    _boite(ax, 6.2, 4.0, "avelis_scan\nAPI HTTP + SQLite\nrègles : séquence,\nlots, kanban",
           donnees, 3.0, 1.9)
    _boite(ax, 10.6, 5.8, "Synchronisation\nétat de chaque pièce\n(zone, étape, défaut)",
           jumeau, 3.6, 1.3)
    _boite(ax, 10.6, 3.9, "Analyse\nA : fin prévue\nB : étapes lentes", jumeau, 3.3, 1.3)
    _boite(ax, 10.6, 2.1, "Règles de décision\n→ propositions", jumeau, 3.3, 1.0)
    _boite(ax, 15.1, 3.9, "Simulation\nde référence\n(SED)", jumeau, 2.9, 1.3)
    _boite(ax, 15.1, 2.1, "Chef d'atelier :\nvalide, modifie\nou ignore", humain, 2.9, 1.3)
    _fleche(ax, (1.9, 5.2), (1.9, 2.9), "geste\nscanné", decalage=(-0.75, 0))
    _fleche(ax, (3.75, 2.6), (4.7, 3.3), "POST /api/scan", decalage=(0.9, -0.5))
    _fleche(ax, (7.7, 4.6), (8.8, 5.6), "GET /api/evenements\n(chaque seconde)",
            decalage=(-0.6, 0.75))
    _fleche(ax, (10.6, 5.15), (10.6, 4.55))
    _fleche(ax, (10.6, 3.25), (10.6, 2.6))
    _fleche(ax, (13.65, 3.9), (12.25, 3.9), "durées\nsimulées", decalage=(0, 0.45))
    _fleche(ax, (12.25, 2.1), (13.65, 2.1), "boîte de\ndialogue", decalage=(0, 0.45))
    ax.plot([15.1, 15.1, 1.9], [1.45, 0.75, 0.75], color=ROUGE, linewidth=1)
    ax.annotate("", (1.9, 1.9), (1.9, 0.75), arrowprops={"arrowstyle": "-|>", "color": ROUGE,
                                                         "linewidth": 1, "shrinkA": 0})
    ax.text(8.5, 0.35, "consigne validée : POST /api/consignes (le téléphone du poste vibre)",
            ha="center", fontsize=6.8, color=ROUGE)
    _enregistrer(figure, "architecture_jumeau")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(STYLE)
    donnees = {
        "simulation": resultats_simulation(),
        "jumeau": resultats_jumeau(),
        "nucleaire": reseau(CAS_NUCLEAIRE),
        "nucleaire_forains": reseau(CAS_NUCLEAIRE, SATELLITES_FORAINS),
        "classique": reseau(CAS_CLASSIQUE),
        "national": reseau_national(),
        "dimensionnement": m.dimensionnement_site(CADENCE, "unique"),
        "cadence": m.calcul_cadence(CADENCE),
    }
    figure_carte_nucleaire(donnees["nucleaire"])
    figure_sensibilite(donnees["nucleaire"], donnees["classique"])
    figure_implantations(donnees["simulation"])
    figure_option_b(donnees["jumeau"])
    figure_tracabilite()
    figure_yamazumi(donnees["cadence"])
    figure_architecture()
    for cas in ("nucleaire", "nucleaire_forains", "classique"):
        donnees[cas].pop("sensibilite")
    (DOSSIER / "donnees_rapport.json").write_text(
        json.dumps(donnees, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: donnees[k] for k in ("jumeau", "nucleaire", "nucleaire_forains",
                                                 "classique", "national")},
                     ensure_ascii=False, indent=1, default=str))
    for implantation, r in donnees["simulation"].items():
        print(implantation, {k: v for k, v in r.items() if k != "utilisation"})


if __name__ == "__main__":
    main()
