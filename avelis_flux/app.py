"""Application de bureau « Avelis · Flux logistiques et données » (SPEC §4).

Tkinter (thème « clam ») et matplotlib. Quatre vues : 1 Statistiques, 2 Schéma de l'usine et flux
(animation par blitting, tableau de pilotage, mode suivi), 3 Traçabilité d'un module (fiche,
chronologie, QR code), 5 Jumeau numérique (le même schéma alimenté par les scans d'avelis_scan,
sa comparaison avec la simulation, et les décisions proposées à l'humain avec les prévisions :
jumeau.py, analyse_jumeau.py, decisions.py). Exports : journal CSV (« ; », UTF-8-sig), figures
PNG 300 dpi dans exports/, étiquettes QR (si le module qrcode est installé). Le bouton « 4 Vue 3D » ouvre la vue 3D
du scénario (avelis_3d/dist/) dans le navigateur, servie par un serveur local (scene_3d.py).

Lancement : py -3 avelis_flux/app.py
"""

import ctypes

try:  # rendu et captures nets sur les écrans à mise à l'échelle (Windows)
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass

import matplotlib

matplotlib.use("TkAgg")  # avant tout import de pyplot (l'application n'utilise que Figure)

# Imports placés après le réglage DPI et le choix du moteur graphique
import bisect  # noqa: E402
import csv  # noqa: E402
import math  # noqa: E402
import pathlib  # noqa: E402
import queue  # noqa: E402
import re  # noqa: E402
import textwrap  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import tkinter as tk  # noqa: E402
import types  # noqa: E402
import tkinter.font as tkfont  # noqa: E402
import webbrowser  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

import numpy as np  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, Patch, Polygon, Rectangle  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageTk  # noqa: E402

import analyse_jumeau as ana  # noqa: E402
import decisions as dc  # noqa: E402
import jumeau as jm  # noqa: E402
import modele as m  # noqa: E402
import scene_3d as s3d  # noqa: E402
import simulation as sim  # noqa: E402

try:
    import qrcode  # noqa: E402
except ImportError:  # optionnel : sans lui, l'identifiant en texte remplace le QR code
    qrcode = None


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Charte graphique et constantes d'interface
# ═════════════════════════════════════════════════════════════════════════════════════════════

DOSSIER_PROJET = pathlib.Path(__file__).resolve().parent.parent
DOSSIER_EXPORTS = DOSSIER_PROJET / "exports"
# Logos de l'en-tête (ressources/preparer_logos.py) ; celui d'Avelis est facultatif : fichier
# officiel à déposer sous ce nom, sinon l'en-tête s'en passe.
DOSSIER_RESSOURCES = pathlib.Path(__file__).resolve().parent / "ressources"
LOGO_EQUIPE, LOGO_AVELIS, ICONE_FENETRE = ("logo_novum_bandeau.png", "logo_avelis.png",
                                           "icone_novum.png")
HAUTEUR_LOGO_EQUIPE, HAUTEUR_LOGO_AVELIS = 46, 30  # px logiques (bandeau de ≈ 52 px)
MARGE_LOGO_AVELIS = 5  # px logiques : fond blanc autour du logo Avelis
TAILLE_ICONE = 64  # px

# Palette catégorielle de référence (compétence dataviz), emplacements dans un ordre fixe
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
CRITIQUE, BON = "#d03b3b", "#006300"
ENCRE, ENCRE_2, ENCRE_MUETTE = "#0b0b0b", "#52514e", "#898781"
GRILLE, AXE, SURFACE, PAGE, BARRE = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#f9f9f7", "#eef0f3"
MARINE, MARINE_CLAIR, MARINE_TEXTE = "#14213d", "#22345a", "#d6dbe6"
ORANGE_ACTIF = "#d95926"
SOMBRE, SOMBRE_LIGNE, SOMBRE_TEXTE, SOMBRE_TEXTE_2 = "#1a1a19", "#2c2c2a", "#f0efec", "#c3c2b7"
ROSE_ALERTE, TEXTE_POD, TEXTE_LOT = "#fde4ec", "#b4441a", "#1c5cab"
BANDEAU_SUIVI = "#fff1dc"
COULEUR_SUIVI, HALO_SUIVI = "#d55181", (0.91, 0.48, 0.64, 0.35)
TAILLE_SUIVI = 170  # points² : marqueur de l'objet suivi, environ deux fois la taille normale
POLICE = "Segoe UI"
# Tuiles : (couleur d'accent, fond teinté)
TEINTES_TUILES = ((SERIES[0], "#e6effb"), (SERIES[1], "#fdebe3"), (SERIES[2], "#dff3eb"),
                  (SERIES[3], "#fcf1d8"), (SERIES[6], "#ebe8f9"), (SERIES[7], "#fbe4e4"))
# Marqueurs animés : type d'objet → (forme, remplissage, contour, taille en points²)
MARQUEURS = {
    "pod": ("o", SERIES[1], "#8a3a14", 46),
    "kit 2D": ("o", "#86b6ef", "#1c5cab", 40),
    "lot": ("o", SERIES[0], "#0d366b", 46),
    "module": ("s", SERIES[6], "#2b1f75", 78),
    "camion": ("s", ENCRE_2, ENCRE, 88),
}
LIBELLES_OBJETS = {"pod": "Pod", "kit 2D": "Kit 2D", "lot": "Lot", "module": "Module",
                   "camion": "Camion", "ossature": "Ossature 1D", "composant": "Composant"}
# Jumeau numérique : pièces scannées (pas de camions, mais l'ossature et les composants suivis)
MARQUEURS_JUMEAU = {"lot": MARQUEURS["lot"], "ossature": ("o", SERIES[3], "#7a5300", 34),
                    "composant": ("o", SERIES[2], "#0b5e40", 24),
                    "kit 2D": MARQUEURS["kit 2D"], "pod": MARQUEURS["pod"],
                    "module": MARQUEURS["module"]}
LIBELLE_SIGNALEES = "En défaut / à isoler"
TAILLE_SIGNALEMENT = 230  # points² : anneau autour d'une pièce en défaut ou d'un lot bloqué
COULEURS_GAMMES = {"pod": SERIES[1], "2D": "#5598e7", "module": SERIES[6]}
DECALAGES_GAMMES = {"pod": (-3, -3), "2D": (3, 3), "module": (0, 0)}  # m, pour séparer les flèches
POSITION_DISTANCES = {"pod": 0.3, "2D": 0.7, "module": 0.5}  # place de l'étiquette sur la jambe
FRACTIONS_ETIQUETTE = (0.5, 0.25, 0.75, 0.1, 0.9)  # autres places, si elle recouvre un texte
MARGE_ETIQUETTE_PX = 2  # pixels autour d'un texte du plan (fond blanc arrondi des distances)
LIBELLES_SCHEMAS = {"unique": "Usine unique", "satellites": "Usine mère + satellites"}
NOMS_COURTS_IMPLANTATIONS = {m.IMPLANTATION_PROPOSEE: "Proposée (Torcy + extension)",
                             m.IMPLANTATION_OPTIMISEE: "Optimisée (Torcy + extension)",
                             m.IMPLANTATION_ACTUELLE: "Actuelle (site seul)"}
NOMS_COURTS_RESSOURCES = {
    "Postes de kitting": "Kitting", "Poste 1 Châssis": "Pod 1 Châssis",
    "Poste 2 Parois + étanchéité": "Pod 2 Parois", "Poste 3 Plomberie-élec": "Pod 3 Plomberie",
    "Poste 4 Finitions": "Pod 4 Finitions", "Baies d'assemblage 3D": "Baies d'assemblage",
    "Postes de consolidation": "Consolidation", "Quais de réception": "Quais réception",
    "Quais d'expédition": "Quais expédition",
    "Quais partagés (réception + expédition)": "Quais partagés",
}
CADENCE_MIN, CADENCE_MAX, CADENCE_PAS = 400, 2500, 50  # curseur de cadence (SPEC §4.1)
JOURS_MIN, JOURS_MAX = 1, 60
GRAINE_MAX = 999_999
VITESSES = (5, 15, 30, 60, 120, 240)  # minutes simulées par seconde
VITESSE_DEFAUT = 30
VITESSES_JUMEAU, VITESSE_JUMEAU_DEFAUT = (1, 5, 15, 60, 240), 1  # rejeu des scans, min/s
INTERVALLE_JUMEAU_MS = 1000  # relecture des scans et avance de l'horloge du jumeau
INTERVALLE_IMAGE_MS = 40  # SPEC §4.3 : boucle after(40)
MS_PAR_SECONDE = 1000
NB_ALERTES = 9  # SPEC §4.3 : les 9 dernières alertes affichées
PALIERS_DELAI = (1, 60)  # délais affichés en s sous 1 min, en min sous 1 h, sinon en h
EPAISSEUR_FLUX = (0.6, 0.35)  # épaisseur des flèches (pt) = base + pente × unités par jour
DPI_EXPORT = 300
CADRE_SCHEMA_EXPORT = (0.01, 0.01, 0.98, 0.92)  # axes du plan exporté (fraction de la figure)
METRES_PAR_CARACTERE = 4.5  # largeur moyenne d'un caractère des étiquettes de zones, en m
LAT_CARTE = 46.5  # latitude de référence pour l'échelle des cartes de France
# Noms des cartes : positions essayées autour du point (sens horizontal, sens vertical), dans
# l'ordre ; écart au point en points typographiques (plus grand autour de l'étoile de Torcy)
POSITIONS_NOMS_CARTE = ((1, -1), (1, 1), (-1, -1), (-1, 1), (0, 1), (0, -1))
ECART_NOM_PT, ECART_NOM_TORCY_PT = 3, 7
DISTANCE_NOM_MASQUE_DEG = 0.6  # un chantier ainsi proche d'un satellite n'est pas nommé
GID_CARTE = "carte"  # marque les axes des cartes pour le placement des noms
HALO_TEXTE = [patheffects.withStroke(linewidth=2.5, foreground="white")]
FORMAT_FRANCAIS = FuncFormatter(lambda valeur, _position: m.formater_nombre(valeur))
FORMAT_DECIMAL_FRANCAIS = FuncFormatter(lambda valeur, _position: f"{valeur:g}".replace(".", ","))
LIBELLES_TDB = ("Terminés aujourd'hui / objectif à cette heure", "Expédiés aujourd'hui (total)",
                "En-cours (modules)", "Stock matières (kits)", "Stock produits finis",
                "Pods en cours", "Camions sur site")
# Tailles d'interface en pixels logiques (écran à 100 %), converties par px() : elles suivent la
# mise à l'échelle de Windows comme les polices (×1,5 sur un écran réglé à 150 %)
PIXELS_PAR_POUCE, POINTS_PAR_POUCE = 96, 72
TAILLE_FENETRE = (1600, 960)  # taille souhaitée ; fenêtre agrandie si l'écran est trop petit
TAILLE_MINIMALE = (1280, 650)  # 1 920 × 1 080 à 150 % (ou 1 280 × 720 à 100 %), barres déduites
MARGE_CADRE_FENETRE = (16, 40)  # bordures et barre de titre de Windows autour de la zone cliente
SPI_GETWORKAREA = 0x0030  # SystemParametersInfoW : écran hors barre des tâches
LARGEUR_BARRE_LATERALE = 280
LARGEUR_TABLEAU_BORD = 270
LARGEUR_FICHE = 310  # colonne de gauche de la vue 3 (choix du module et fiche)
TAILLE_QR_FICHE = 104
MARGE_COLONNE = 16  # place laissée autour du contenu le plus large d'une colonne de tableau
MARGE_INTERNE_TEXTE = 8  # bordure et marge internes d'une étiquette Tk, pour son retour à la ligne
RETRAIT_ARBRE = 20  # retrait d'un niveau dans le tableau des chiffres
LIGNES_TABLEAU_RESEAU = 6
LEGENDE_HA = ("H/A : A = donnée fournie par Avelis ; H = hypothèse de l'équipe, à valider. "
              "Une valeur calculée est marquée H quand elle repose sur des hypothèses.")
FOND_MODIFIE = "#fdebe3"  # ligne de l'onglet Paramètres qui diffère de la valeur par défaut
ROUGE_ERREUR = SERIES[7]
TEXTE_RETABLIR = "↺ Valeur par défaut"
TEXTE_RETIRER = "✕ Retirer"
PART_NOUVEAU_CHANTIER = 0.05  # part proposée à un chantier ajouté, à ajuster par l'utilisateur
TAILLE_INITIALE_GRAPHIQUES, TAILLE_INITIALE_RESEAU = (12, 6), (12, 4)  # pouces, avant ajustement
TAILLE_INITIALE_COMPARAISON = (6, 5)
LARGEUR_BARRE_DEFILEMENT = 24  # barre verticale d'un tableau, avec sa marge
LIGNES_TABLEAU_PREVISIONS = 5  # hauteur du tableau des fins de fabrication prévues
LARGEUR_DIALOGUE = 440  # texte des boîtes de dialogue des décisions
INTERVALLE_ANALYSE_S = 5  # nouvelle analyse au plus tôt après ce délai, sans nouveau scan
ENVOYER, IGNORER, PLUS_TARD = "envoyer", "ignorer", "plus tard"  # choix de l'humain
LIGNES_TABLEAU_ETAPES = 8  # hauteur minimale du tableau des étapes (il s'étend et défile)
GID_BARRES_HORIZONTALES = "barres horizontales"  # corps des noms adapté à la hauteur des lignes
CORPS_ETIQUETTES_BARRES = (5, 7)  # points : corps minimal et maximal des noms et valeurs
INTERLIGNE_ETIQUETTE = 1.3  # hauteur d'une ligne de barres / corps du texte, au minimum


def px(widget: tk.Misc, valeur: float) -> int:
    """Pixels physiques d'une longueur exprimée en pixels logiques (écran à 100 %)."""
    return round(valeur * widget.winfo_fpixels("1i") / PIXELS_PAR_POUCE)


def zone_de_travail(racine: tk.Tk) -> tuple[int, int, int, int]:
    """(x, y, largeur, hauteur) de l'écran hors barre des tâches (Windows), sinon l'écran."""
    try:
        from ctypes import wintypes
        zone = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(zone), 0):
            return zone.left, zone.top, zone.right - zone.left, zone.bottom - zone.top
    except (AttributeError, ImportError, OSError, ValueError):  # hors Windows
        pass
    return 0, 0, racine.winfo_screenwidth(), racine.winfo_screenheight()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Scénario : tous les calculs, sans interface
# ═════════════════════════════════════════════════════════════════════════════════════════════

def calculer_scenario(cadence: int, implantation: str, schema: str, techno: str, jours: int,
                      graine: int) -> dict:
    """Calculs du modèle et simulation d'un scénario (aucune dépendance à Tkinter)."""
    usine = sim.Usine(cadence, implantation, schema, techno, jours, graine).executer()
    return {
        "parametres": {"cadence": cadence, "implantation": implantation, "schema": schema,
                       "techno": techno, "jours": jours, "graine": graine},
        "cadence": m.calcul_cadence(cadence),
        "dimension": m.dimensionnement_site(cadence, schema),
        "evolutivite": m.evolutivite(schema),
        "implantations": {nom: {"distances": m.distances_sous_ensemble(nom),
                                "croisements": m.croisements_flux(nom),
                                "anomalies": m.verifier_implantation(nom),
                                "capacite": m.capacite_implantation(nom, cadence, schema)}
                          for nom in m.IMPLANTATIONS},
        "reseau": {variante: m.comparaison_reseau(cadence, variante) for variante in m.VARIANTES},
        "sensibilite": {variante: m.sensibilite_reseau(variante) for variante in m.VARIANTES},
        "bascule": {variante: m.point_bascule(variante) for variante in m.VARIANTES},
        "usine": usine,
        "resultats": usine.resultats(),
    }


def resume_scenario(parametres: dict) -> str:
    """Résumé du scénario sur deux lignes, pour l'en-tête."""
    return (f"{m.formater_nombre(parametres['cadence'])} logements/an · "
            f"{NOMS_COURTS_IMPLANTATIONS[parametres['implantation']]}\n"
            f"{LIBELLES_SCHEMAS[parametres['schema']]} · {parametres['techno']} · "
            f"{parametres['jours']} j · graine {parametres['graine']}")


def formater_delai(minutes: float | None) -> str:
    """Délai lisible : secondes sous 1 min, minutes sous 1 h, sinon heures et minutes."""
    if minutes is None:
        return "—"
    if minutes < PALIERS_DELAI[0]:
        return f"{m.formater_nombre(minutes * sim.SECONDES_PAR_MINUTE)} s"
    if minutes < PALIERS_DELAI[1]:
        return f"{m.formater_nombre(minutes)} min"
    heures, reste = divmod(round(minutes), m.MINUTES_PAR_HEURE)
    return f"{heures} h {reste:02d}"


def formater_valeur(valeur, cle: str = "") -> str:
    """Valeur d'hypothèse affichable : séquences jointes, décimales à la française, année sans
    séparateur de milliers."""
    if isinstance(valeur, tuple):
        return " · ".join(formater_valeur(v) for v in valeur)
    if isinstance(valeur, float) and not valeur.is_integer():
        return f"{valeur:g}".replace(".", ",")
    if cle.startswith("annee"):
        return str(valeur)
    return m.formater_nombre(valeur)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Graphiques (fonctions pures sur un Axes matplotlib)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def styliser(ax, titre: str, ylabel: str = "", xlabel: str = "", grille: str = "y",
             sous_titre: str = "") -> None:
    """Habillage commun : titre court à gauche (sous-titre éventuel), axes discrets, grille fine,
    encre de texte."""
    annotations_hors_marges(ax)
    ax.set_title(titre, loc="left", fontsize=10, fontweight="bold", color=ENCRE,
                 pad=18 if sous_titre else 8)
    if sous_titre:
        ax.text(0, 1.015, sous_titre, transform=ax.transAxes, fontsize=7.5, color=ENCRE_2,
                va="bottom")
    ax.set_facecolor(SURFACE)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(AXE)
    ax.tick_params(colors=ENCRE_2, labelsize=8)
    if grille:
        ax.grid(axis=grille, color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel(ylabel, fontsize=8, color=ENCRE_2)
    ax.set_xlabel(xlabel, fontsize=8, color=ENCRE_2)


def annotations_hors_marges(ax) -> None:
    """Les textes déjà posés dans la zone de tracé n'entrent pas dans le calcul des marges de
    « constrained » : sinon, après un premier dessin à petite taille, ces textes (de taille fixe
    en points) débordent des axes rétrécis, entretiennent des marges démesurées et les axes ne
    retrouvent jamais leur largeur. Titres, sous-titres et libellés d'axes restent comptés."""
    for texte in ax.texts:
        texte.set_in_layout(False)


def legende(ax, position: str = "best", colonnes: int = 1) -> None:
    """Légende sans cadre, en encre de texte, placée dans les axes : elle n'entre pas dans le
    calcul des marges (si elle dépassait des axes, « constrained » les rétrécirait à chaque
    dessin jusqu'à les écraser)."""
    ax.legend(loc=position, fontsize=7, frameon=False, ncol=colonnes,
              labelcolor=ENCRE_2).set_in_layout(False)


def aucune_donnee(ax, titre: str, message: str) -> None:
    """Graphique vide annoté (simulation trop courte, aucun défaut…)."""
    styliser(ax, titre, grille="")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes, fontsize=9,
            color=ENCRE_2)


def tracer_modules_par_jour(ax, scenario: dict) -> None:
    """Modules terminés et expédiés par jour, face à l'objectif journalier."""
    r = scenario["resultats"]
    jours = np.arange(1, len(r["termines_par_jour"]) + 1)
    ax.bar(jours - 0.2, r["termines_par_jour"], 0.4, color=SERIES[0], edgecolor=SURFACE,
           linewidth=1, label="Terminés (entrée stock PF)")
    ax.bar(jours + 0.2, r["expedies_par_jour"], 0.4, color=SERIES[1], edgecolor=SURFACE,
           linewidth=1, label="Expédiés")
    ax.axhline(r["objectif_jour"], color=ENCRE, linestyle="--", linewidth=1.2,
               label=f"Objectif : {m.formater_nombre(r['objectif_jour'], 1)} par jour")
    sommet = max([r["objectif_jour"], *r["termines_par_jour"], *r["expedies_par_jour"]])
    ax.set_ylim(0, sommet * 1.6)  # légende sur deux lignes au-dessus des barres
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    styliser(ax, "Modules par jour et objectif", "modules", "jour simulé")
    legende(ax, "upper left", colonnes=2)


def tracer_utilisation(ax, scenario: dict) -> None:
    """Taux d'utilisation simulé de chaque ressource ; rouge au-delà du seuil critique."""
    usine, seuil = scenario["usine"], m.H("seuil_utilisation_critique")
    ressources = usine.ressources()  # quais partagés : une seule ressource, donc une seule barre
    taux = [r.taux_utilisation(usine.duree) for r in ressources]
    noms = [NOMS_COURTS_RESSOURCES.get(r.nom, r.nom) for r in ressources]
    couleurs = [CRITIQUE if t > seuil else SERIES[0] for t in taux]
    rangs = np.arange(len(noms))
    ax.set_gid(GID_BARRES_HORIZONTALES)  # corps des noms adapté après le dessin
    ax.barh(rangs, [t * 100 for t in taux], height=0.62, color=couleurs, edgecolor=SURFACE)
    ax.axvline(seuil * 100, color=CRITIQUE, linestyle=":", linewidth=1)
    for rang, t in zip(rangs, taux):
        marque = "⚠ " if t > seuil else ""
        ax.text(t * 100 + 1.5, rang, f"{marque}{m.formater_pourcentage(t)}", va="center",
                fontsize=CORPS_ETIQUETTES_BARRES[1], color=ENCRE_2)
    ax.set_yticks(rangs, noms, fontsize=CORPS_ETIQUETTES_BARRES[1])
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    styliser(ax, "Utilisation des ressources", xlabel="% du temps simulé", grille="x",
             sous_titre=f"simulée · en rouge au-delà de {m.formater_pourcentage(seuil)}")


def tracer_en_cours(ax, scenario: dict) -> None:
    """En-cours, stock matières et stock PF échantillonnés toutes les 15 min."""
    echantillons = scenario["usine"].echantillons
    jours = [e["t"] / sim.minutes_jour() for e in echantillons]
    for rang, (cle, libelle) in enumerate((("en_cours", "En-cours (modules)"),
                                           ("stock_matieres", "Stock matières (kits)"),
                                           ("stock_pf", "Stock produits finis"))):
        ax.plot(jours, [e[cle] for e in echantillons], color=SERIES[rang], linewidth=1.6,
                label=libelle)
    sommet = max((max(e["en_cours"], e["stock_matieres"], e["stock_pf"]) for e in echantillons),
                 default=1)
    ax.set_ylim(0, sommet * 2 + 1)  # place pour la légende, sur trois lignes, au-dessus des pics
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    styliser(ax, "En-cours et stocks", "unités", "jour simulé",
             sous_titre="au fil des jours simulés")
    legende(ax, "upper left")


def tracer_pareto(ax, scenario: dict) -> None:
    """Pareto des causes de défauts détectés, de la plus fréquente à la moins fréquente, avec le
    nombre et la part cumulée en étiquette. Barres horizontales : les noms des causes restent
    lisibles quel que soit leur nombre."""
    r = scenario["resultats"]
    titre = "Pareto des défauts"
    if not r["pareto_causes"]:
        aucune_donnee(ax, titre, "Aucun défaut détecté\nsur la période simulée")
        return
    causes, nombres = zip(*r["pareto_causes"])
    total, cumul = sum(nombres), 0
    rangs = np.arange(len(causes))
    ax.set_gid(GID_BARRES_HORIZONTALES)
    ax.barh(rangs, nombres, height=0.62, color=SERIES[0], edgecolor=SURFACE)
    for rang, nombre in zip(rangs, nombres):
        cumul += nombre
        ax.text(nombre + max(nombres) * 0.04, rang,
                f"{nombre} · cumul {m.formater_pourcentage(cumul / total)}", va="center",
                fontsize=7, color=ENCRE_2)
    ax.set_yticks(rangs, [NOMS_COURTS_RESSOURCES.get(c, c) for c in causes], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, max(nombres) * 2.4)  # place des étiquettes à droite des barres
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    retrouvees = m.formater_pourcentage(r["taux_causes_retrouvees"])
    styliser(ax, titre, xlabel="défauts", grille="x",
             sous_titre=f"{total} défauts · causes retrouvées : {retrouvees}")


def tracer_couts_reseau(ax, scenario: dict) -> None:
    """Coût annuel des réseaux : transport + coûts fixes des satellites, CO2 en annotation."""
    reseau = scenario["reseau"]
    options = (("A · usine\nunique", reseau["proche"]["A"]),
               ("B · satellites\nproche", reseau["proche"]["B"]),
               ("B · satellites\nhybride", reseau["hybride"]["B"]))
    transport = [o["cout_transport_an"] / m.EUROS_PAR_MILLION for _, o in options]
    fixes = [o["couts_fixes_an"] / m.EUROS_PAR_MILLION for _, o in options]
    rangs = np.arange(len(options))
    ax.bar(rangs, transport, width=0.55, color=SERIES[0], edgecolor=SURFACE, label="Transport")
    ax.bar(rangs, fixes, width=0.55, bottom=transport, color=SERIES[1], edgecolor=SURFACE,
           linewidth=2, label="Coûts fixes des satellites")
    for rang, (_, option) in zip(rangs, options):
        total = option["cout_total_an"] / m.EUROS_PAR_MILLION
        ax.text(rang, total * 1.02, f"{m.formater_nombre(total, 1)} M€\n"
                f"CO2 {m.formater_nombre(option['co2_t_an'])} t", ha="center", va="bottom",
                fontsize=7, color=ENCRE_2)
    ax.set_xticks(rangs, [libelle for libelle, _ in options], fontsize=7)
    # marge haute : annotations des barres, puis la légende (même sur un petit écran)
    ax.set_ylim(0, max(o["cout_total_an"] for _, o in options) / m.EUROS_PAR_MILLION * 2.2)
    ax.yaxis.set_major_formatter(FORMAT_DECIMAL_FRANCAIS)
    cadence = m.formater_nombre(scenario["parametres"]["cadence"])
    styliser(ax, "Coût annuel des réseaux", "M€ par an",
             sous_titre=f"à {cadence} logements/an · CO2 en annotation")
    legende(ax, "upper left")


def tracer_evolutivite(ax, scenario: dict) -> None:
    """Surface nécessaire selon la cadence, face aux surfaces utilisables."""
    e, cadence = scenario["evolutivite"], scenario["parametres"]["cadence"]
    milliers = [besoin / 1000 for besoin in e["besoins"]]
    ax.plot(e["cadences"], milliers, color=SERIES[0], linewidth=2,
            label=f"Surface nécessaire ({LIBELLES_SCHEMAS[e['schema']].lower()})")
    references = (("utilisable_site_seul", "utilisable, site seul", "--"),
                  ("utilisable_avec_extension", "utilisable, site + extension", "-."))
    for cle, libelle, style in references:  # libellé à 2 points au-dessus de sa ligne
        ax.axhline(e[cle] / 1000, color=ENCRE_2, linestyle=style, linewidth=1)
        ax.annotate(libelle, (e["cadences"][0], e[cle] / 1000), xytext=(2, 2),
                    textcoords="offset points", fontsize=7, color=ENCRE_2, va="bottom")
    ax.axvline(cadence, color=SERIES[1], linestyle=":", linewidth=1.2)
    plafond = max(max(milliers), e["utilisable_avec_extension"] / 1000) * 1.12
    a_gauche = cadence > (e["cadences"][0] + e["cadences"][-1]) / 2  # sinon, sortirait à droite
    ax.text(cadence, plafond * 0.3, f" cadence choisie : {m.formater_nombre(cadence)} ",
            fontsize=7, color=ENCRE_2, va="bottom", ha="right" if a_gauche else "left")
    ax.set_ylim(0, plafond)
    ax.xaxis.set_major_formatter(FORMAT_FRANCAIS)
    styliser(ax, "Évolutivité du site", "milliers de m²", "logements par an",
             sous_titre="surface nécessaire face à l'utilisable")
    legende(ax, "lower right")


GRAPHIQUES = (tracer_modules_par_jour, tracer_utilisation, tracer_en_cours, tracer_pareto,
              tracer_couts_reseau, tracer_evolutivite)


def _orienter_nom(nom, sens: tuple) -> None:
    """Place un nom de la carte dans la direction `sens` (−1, 0 ou 1 par axe) autour de son
    point."""
    ecart = ECART_NOM_TORCY_PT if nom.get_text() == "Torcy" else ECART_NOM_PT
    nom.xyann = (sens[0] * ecart, sens[1] * ecart)
    nom.set_horizontalalignment({1: "left", -1: "right", 0: "center"}[sens[0]])
    nom.set_verticalalignment("bottom" if sens[1] > 0 else "top")


def _nommer(ax, texte: str, lon: float, lat: float, **style) -> None:
    """Nom d'un lieu, en bas à droite de son point jusqu'au placement (placer_noms_cartes)."""
    nom = ax.annotate(texte, (lon, lat), xytext=(0, 0), textcoords="offset points",
                      path_effects=HALO_TEXTE, zorder=6, **style)
    _orienter_nom(nom, POSITIONS_NOMS_CARTE[0])


def _dans(boite, cadre) -> bool:
    """La boîte est-elle entièrement dans le cadre ?"""
    return (boite.x0 >= cadre.x0 and boite.x1 <= cadre.x1 and boite.y0 >= cadre.y0
            and boite.y1 <= cadre.y1)


def placer_noms_cartes(figure: Figure) -> bool:
    """Chaque nom des cartes, dans l'ordre d'importance où il a été créé, prend la première
    position autour de son point qui reste dans la carte sans recouvrir un nom déjà placé ; sans
    place libre (très petite carte), il est masqué. À appeler après un dessin, les axes étant à
    leur place définitive ; renvoie True si un nom a bougé ou a été masqué."""
    rendu, change = figure.canvas.get_renderer(), False
    for ax in (ax for ax in figure.axes if ax.get_gid() == GID_CARTE):
        occupees = []
        for nom in ax.texts:
            avant = (nom.xyann, nom.get_horizontalalignment(), nom.get_visible())
            nom.set_visible(True)  # un texte masqué se mesure comme une boîte unité
            for sens in POSITIONS_NOMS_CARTE:
                _orienter_nom(nom, sens)
                boite = nom.get_window_extent(rendu)
                if _dans(boite, ax.bbox) and not any(boite.overlaps(b) for b in occupees):
                    occupees.append(boite)
                    break
            else:
                nom.set_visible(False)
            change |= avant != (nom.xyann, nom.get_horizontalalignment(), nom.get_visible())
    return change


def ajuster_etiquettes_barres(figure: Figure) -> bool:
    """Corps des noms et des valeurs des graphiques à barres horizontales adapté à la hauteur
    réelle d'une ligne (5 à 7 points) : sur un petit écran, les noms ne se touchent pas. À
    appeler après un dessin ; renvoie True si un corps a changé."""
    corps_min, corps_max = CORPS_ETIQUETTES_BARRES
    change = False
    for ax in (ax for ax in figure.axes if ax.get_gid() == GID_BARRES_HORIZONTALES):
        ligne_pt = ax.bbox.height / max(len(ax.get_yticks()), 1) * POINTS_PAR_POUCE / figure.dpi
        corps = max(corps_min, min(corps_max, math.floor(ligne_pt / INTERLIGNE_ETIQUETTE * 2) / 2))
        valeurs = [texte for texte in ax.texts if texte.get_transform() is not ax.transAxes]
        if any(texte.get_fontsize() != corps for texte in [*ax.get_yticklabels(), *valeurs]):
            ax.tick_params(axis="y", labelsize=corps)  # reste valable si les graduations changent
            for texte in valeurs:  # le sous-titre (repère des axes) garde son corps
                texte.set_fontsize(corps)
            change = True
    return change


def tracer_carte(ax, bilan: dict, titre: str) -> None:
    """Carte de France du réseau : épaisseur des tronçons proportionnelle à la demande. Noms
    créés par ordre d'importance (Torcy, satellites, chantiers par part de la demande) ; un
    chantier voisin d'un satellite n'est pas nommé (le nom du satellite le recouvrirait)."""
    ax.set_gid(GID_CARTE)
    ax.add_patch(Polygon(m.CONTOUR_FRANCE, closed=True, facecolor="#f0efec", edgecolor=AXE,
                         linewidth=0.8))
    for flux in bilan["flux"]:
        (lat0, lon0), (lat1, lon1) = flux["depart"], flux["arrivee"]
        couleur = SERIES[0] if flux["mode"] == "convoi" else SERIES[1]
        ax.plot([lon0, lon1], [lat0, lat1], color=couleur, linewidth=0.8 + 12 * flux["part"],
                solid_capstyle="round", alpha=0.85, zorder=2)
    satellites = {nom: point for nom, point in m.SATELLITES.items()
                  if any(f["vers"] == f"Satellite {nom}" for f in bilan["flux"])}
    ax.scatter(m.TORCY[1], m.TORCY[0], s=170, marker="*", color=ENCRE, zorder=5)
    _nommer(ax, "Torcy", m.TORCY[1], m.TORCY[0], fontsize=7, fontweight="bold")
    for nom, (lat, lon) in satellites.items():
        ax.scatter(lon, lat, s=60, marker="s", color=SERIES[1], edgecolors=ENCRE, linewidths=0.8,
                   zorder=4)
        _nommer(ax, f"Sat. {nom}", lon, lat, fontsize=6.5, color=ENCRE, fontweight="bold")
    for nom, (lat, lon, _) in sorted(m.CHANTIERS.items(), key=lambda item: -item[1][2]):
        ax.scatter(lon, lat, s=26, color=SERIES[0], edgecolors="white", linewidths=0.8, zorder=3)
        if all(math.dist((lat, lon), point) > DISTANCE_NOM_MASQUE_DEG
               for point in satellites.values()):
            _nommer(ax, nom, lon, lat, fontsize=6.5, color=ENCRE_2)
    ax.set_aspect(1 / math.cos(math.radians(LAT_CARTE)))
    ax.set_xlim(*m.BORNES_CARTE["lon"])
    ax.set_ylim(*m.BORNES_CARTE["lat"])
    ax.axis("off")
    ax.set_title(titre, loc="left", fontsize=10, fontweight="bold", color=ENCRE)
    annotations_hors_marges(ax)


def legende_cartes(figure: Figure) -> None:
    """Légende commune des cartes, sous la figure (hors des cartes, qu'elle masquerait)."""
    figure.legend(handles=[Line2D([], [], color=SERIES[0], linewidth=3,
                                  label="Convoi (module 3D)"),
                           Line2D([], [], color=SERIES[1], linewidth=3, label="Semi (3 kits)")],
                  loc="outside lower left", ncols=2, fontsize=7, frameon=False)


def tracer_cout_par_logement(ax, scenario: dict) -> None:
    """Coût par logement selon la cadence, points de bascule des deux variantes."""
    proche, hybride = scenario["sensibilite"]["proche"], scenario["sensibilite"]["hybride"]
    courbes = (("A : usine unique", proche["A"], SERIES[0]),
               ("B : satellites, variante proche", proche["B"], SERIES[1]),
               ("B : satellites, variante hybride", hybride["B"], SERIES[2]))
    for libelle, couts, couleur in courbes:
        ax.plot(proche["cadences"], couts, color=couleur, linewidth=2, label=libelle)
    plafond = max(proche["A"]) * 2.6
    # étiquettes dans la bande vide sous les courbes, sur trois hauteurs ; légende en haut à droite
    for rang, variante in enumerate(m.VARIANTES):
        bascule = scenario["bascule"][variante]
        if bascule is not None:
            ax.axvline(bascule, color=SERIES[rang + 1], linestyle=":", linewidth=1.2)
            ax.text(bascule, plafond * (0.04 + 0.12 * rang), f" bascule {variante} : "
                    f"{m.formater_nombre(bascule)}", fontsize=7, color=ENCRE_2)
    cadence = scenario["parametres"]["cadence"]
    ax.axvline(cadence, color=ENCRE_MUETTE, linestyle="--", linewidth=1)
    ax.text(cadence, plafond * 0.28, f" cadence choisie : {m.formater_nombre(cadence)}",
            fontsize=7, color=ENCRE_2)
    ax.set_ylim(0, plafond)
    ax.xaxis.set_major_formatter(FORMAT_FRANCAIS)
    ax.yaxis.set_major_formatter(FORMAT_FRANCAIS)
    styliser(ax, "Coût par logement selon la cadence", "€ par logement", "logements par an")
    legende(ax, "upper right")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Plan du site (SPEC §4.3)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _sans_doublons(points: list) -> list:
    """Retire les points consécutifs confondus (tronçons de longueur nulle)."""
    return [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]


def _couper_etiquette(texte: str, largeur_m: float) -> str:
    """Retour à la ligne d'une étiquette selon la largeur de sa zone, sans couper les mots."""
    return textwrap.fill(texte, max(6, int(largeur_m / METRES_PAR_CARACTERE)),
                         break_long_words=False)


def _dessiner_foncier(ax, plan: dict) -> None:
    """Polygones du site ; extension hachurée si l'implantation ne l'utilise pas."""
    ax.add_patch(Polygon(m.SITE_ACTUEL, closed=True, facecolor="#f3f2ee", edgecolor=ENCRE_2,
                         linewidth=1.2, zorder=0))
    utilisee = plan["extension_utilisee"]
    ax.add_patch(Polygon(m.EXTENSION, closed=True, facecolor="#f3f2ee" if utilisee else "none",
                         edgecolor=ENCRE_2 if utilisee else ENCRE_MUETTE, linewidth=1.2,
                         linestyle="-" if utilisee else "--", hatch=None if utilisee else "///",
                         zorder=0))
    if not utilisee:
        ax.text(345, 125, "Extension\n(non utilisée)", ha="center", va="center", fontsize=8,
                color=ENCRE_MUETTE, style="italic")


def _dessiner_parking_vl(ax, plan: dict) -> None:
    """Parking des véhicules légers et sa voie d'accès, s'il y en a un (sans nom : le plan
    est trop serré à côté du stock matières ; la vue 3D y montre les voitures)."""
    parking = plan.get("parking_vl")
    if not parking:
        return
    voie = np.array(parking["voie"])
    ax.plot(voie[:, 0], voie[:, 1], color="#a9a69c", linewidth=3, solid_capstyle="round",
            zorder=1)
    x, y, largeur, hauteur = parking["zone"]
    ax.add_patch(Rectangle((x, y), largeur, hauteur, facecolor="#d9d7cf", edgecolor="#8d8a80",
                           linewidth=0.8, hatch="||", zorder=1))


def _dessiner_voiries(ax, plan: dict) -> None:
    """Route publique et accès au portail, voirie poids lourds et bretelles, aire de
    retournement, parking VL, portail et quais."""
    route = np.array(m.ROUTE_PUBLIQUE)
    ax.plot(route[:, 0], route[:, 1], color="#bdbab0", linewidth=9, solid_capstyle="round",
            zorder=1)
    if len(plan["acces"]) > 1:  # rue publique jusqu'au portail (implantation actuelle)
        acces = np.array(plan["acces"])
        ax.plot(acces[:, 0], acces[:, 1], color="#bdbab0", linewidth=5, solid_capstyle="round",
                zorder=1)
    ax.text(500, 20, "Route publique", rotation=88, fontsize=7, color=ENCRE_2)
    for ligne in (plan["voirie"], *plan["bretelles"]):
        voirie = np.array(ligne)
        ax.plot(voirie[:, 0], voirie[:, 1], color="#8d8a80", linewidth=5,
                solid_capstyle="round", zorder=1)
    (cx, cy), rayon = plan["retournement"], m.H("rayon_retournement")
    ax.add_patch(Circle((cx, cy), rayon, facecolor="#d9d7cf", edgecolor="#8d8a80", zorder=1))
    _dessiner_parking_vl(ax, plan)
    portail = plan["portail"]
    ax.plot(*portail, marker="D", markersize=7, color=ENCRE, zorder=6)
    ax.annotate("Portail", portail, xytext=(8, 10), textcoords="offset points", fontsize=7)
    quais = {plan["quai_reception"]: "Quai réception", plan["quai_expedition"]: "Quai expédition"}
    if plan["quai_reception"] == plan["quai_expedition"]:
        quais = {plan["quai_reception"]: "Quais partagés"}
    for (x, y), libelle in quais.items():
        ax.plot(x, y, marker="^", markersize=6, color=ENCRE, zorder=6)
        # quais de la façade est de la Réception : nom court, à la verticale le long du mur
        # (plus long ou couché, il recouvrirait le nom de la Réception, du parking PL ou du
        # stock matières ; celui de la zone dit s'ils sont partagés)
        if (x, y) == tuple(plan["quai_reception"]):
            ax.annotate("Quais", (x, y), xytext=(3, 6), textcoords="offset points",
                        fontsize=6.5, rotation=90, ha="left", va="bottom")
        else:
            ax.annotate(libelle, (x, y), xytext=(6, 5), textcoords="offset points",
                        fontsize=6.5)


def _dessiner_zones(ax, plan: dict) -> None:
    """Zones en couleur, nom en haut à gauche (les flèches passent par les centres) ; une zone
    partagée est dessinée avec sa zone hôte."""
    partagees = plan["zones_partagees"]
    for nom, (x, y, largeur, hauteur, couleur, _) in plan["zones"].items():
        if nom in partagees:
            continue
        ax.add_patch(Rectangle((x, y), largeur, hauteur, facecolor=couleur, edgecolor=ENCRE_2,
                               linewidth=0.8, zorder=2))
        etiquette = " / ".join([nom, *(zone for zone, hote in partagees.items() if hote == nom)])
        ax.text(x + 1.5, y + hauteur - 1.5, _couper_etiquette(etiquette, largeur), ha="left",
                va="top", fontsize=6.5, color=ENCRE, zorder=7,
                bbox={"boxstyle": "round,pad=0.12", "fc": couleur, "ec": "none", "alpha": 0.9})


def _boites_occupees(ax) -> list:
    """Boîtes (en pixels) des textes déjà posés et de la légende : obstacles des étiquettes."""
    rendu = ax.figure.canvas.get_renderer()
    boites = [texte.get_window_extent(rendu).padded(MARGE_ETIQUETTE_PX) for texte in ax.texts]
    if ax.get_legend() is not None:
        boites.append(ax.get_legend().get_window_extent(rendu))
    return boites


def _points_candidats(points: list, k: float) -> list[tuple]:
    """Emplacements possibles d'une étiquette sur un chemin : la fraction k de la plus longue
    jambe d'abord, puis d'autres fractions de chaque jambe, de la plus longue à la plus courte."""
    jambes = sorted(zip(points, points[1:]), key=lambda jambe: -math.dist(*jambe))
    return [(a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
            for a, b in jambes for f in (k, *FRACTIONS_ETIQUETTE)]


def _decaler_candidats(texte, candidats: list) -> list[tuple]:
    """Mêmes emplacements, décalés d'une hauteur de texte au-dessus puis au-dessous (en
    coordonnées des données) : derniers recours quand la flèche n'offre aucune place libre."""
    rendu, ax = texte.figure.canvas.get_renderer(), texte.axes
    hauteur = texte.get_window_extent(rendu).height + 2 * MARGE_ETIQUETTE_PX
    vers_donnees = ax.transData.inverted()
    decales = []
    for sens in (1, -1):
        for x, y in candidats:
            px_x, px_y = ax.transData.transform((x, y))
            decales.append(tuple(vers_donnees.transform((px_x, px_y + sens * hauteur))))
    return decales


def _placer_sans_chevauchement(texte, candidats: list, occupees: list) -> None:
    """Pose le texte au premier candidat où il ne recouvre aucune boîte occupée (puis aux mêmes
    places décalées hors de la flèche ; à défaut, au premier candidat), puis ajoute sa boîte aux
    boîtes occupées."""
    rendu = texte.figure.canvas.get_renderer()
    for point in [*candidats, *_decaler_candidats(texte, candidats), candidats[0]]:
        texte.set_position(point)
        boite = texte.get_window_extent(rendu).padded(MARGE_ETIQUETTE_PX)
        if not any(boite.overlaps(autre) for autre in occupees):
            break
    occupees.append(boite)


def _dessiner_fleches(ax, plan: dict, cadence: dict, schema: str) -> None:
    """Flèches en L de chaque gamme, épaisseur proportionnelle aux unités par jour ; distance
    posée là où elle ne recouvre ni un nom de zone, ni une autre distance, ni la légende."""
    zones = plan["zones"]
    unites = {"pod": cadence["pods_jour"], "2D": cadence["modules_jour"],
              "module": cadence["modules_jour"]}
    base, pente = EPAISSEUR_FLUX
    occupees = _boites_occupees(ax)
    for gamme, couleur in COULEURS_GAMMES.items():
        dx, dy = DECALAGES_GAMMES[gamme]
        epaisseur = base + pente * unites[gamme]
        for de, vers in m.etapes_gamme(gamme):
            if zones[de][:4] == zones[vers][:4]:
                continue
            points = _sans_doublons([(x + dx, y + dy)
                                     for x, y in m.chemin_zones(zones[de], zones[vers])])
            ax.add_patch(FancyArrowPatch(path=Path(points), arrowstyle="-|>", color=couleur,
                                         linewidth=epaisseur, mutation_scale=8 + 2 * epaisseur,
                                         alpha=0.85, zorder=3, shrinkA=0, shrinkB=6))
            distance = m.distance_zones(zones[de], zones[vers])
            texte = ax.text(*points[0], f"{m.formater_nombre(distance)} m", fontsize=6,
                            color=ENCRE, ha="center", va="center", zorder=4,
                            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none",
                                  "alpha": 0.85})
            _placer_sans_chevauchement(texte, _points_candidats(points, POSITION_DISTANCES[gamme]),
                                       occupees)


def _dessiner_reperes(ax) -> None:
    """Échelle de 50 m et flèche du nord."""
    x0, y0 = 30, 30
    ax.plot([x0, x0 + 50], [y0, y0], color=ENCRE, linewidth=3, solid_capstyle="butt")
    ax.plot([x0, x0], [y0 - 3, y0 + 3], color=ENCRE, linewidth=1)
    ax.plot([x0 + 50, x0 + 50], [y0 - 3, y0 + 3], color=ENCRE, linewidth=1)
    ax.text(x0 + 25, y0 + 5, "50 m", ha="center", fontsize=7)
    ax.annotate("N", xy=(20, 312), xytext=(20, 284), ha="center", va="center", fontsize=9,
                fontweight="bold", arrowprops={"arrowstyle": "-|>", "color": ENCRE, "lw": 1.5})


def _legende_site(ax, marqueurs: dict, signalement: bool) -> None:
    """Légende : catégories de zones, objets animés, gammes de flux (et pièces signalées, pour
    le jumeau numérique)."""
    poignees = [Patch(facecolor=couleur, edgecolor=ENCRE_2, label=categorie)
                for categorie, couleur in m.CATEGORIES_ZONES.items()]
    poignees += [Line2D([], [], linestyle="", marker=forme, markersize=7, markerfacecolor=couleur,
                        markeredgecolor=contour, label=LIBELLES_OBJETS[type_objet])
                 for type_objet, (forme, couleur, contour, _) in marqueurs.items()]
    if signalement:
        poignees.append(Line2D([], [], linestyle="", marker="o", markersize=10,
                               markerfacecolor="none", markeredgecolor=CRITIQUE,
                               markeredgewidth=1.8, label=LIBELLE_SIGNALEES))
    poignees += [Line2D([], [], color=couleur, linewidth=2.5, label=f"Flux {gamme}")
                 for gamme, couleur in COULEURS_GAMMES.items()]
    # Sous l'extension, à gauche de la route publique
    ax.legend(handles=poignees, loc="lower right", bbox_to_anchor=(0.93, 0), fontsize=7, ncol=2,
              frameon=True, framealpha=0.92, edgecolor=GRILLE, labelcolor=ENCRE_2)


def dessiner_site(ax, scenario: dict, fleches: bool = True, marqueurs: dict = MARQUEURS,
                  signalement: bool = False) -> None:
    """Plan complet de l'implantation du scénario (sans les objets animés). Le cadre est fixé
    d'abord : les étiquettes de distance sont placées en pixels, après tous les autres textes.
    `marqueurs` et `signalement` règlent la légende des objets (jumeau numérique)."""
    plan = m.IMPLANTATIONS[scenario["parametres"]["implantation"]]
    ax.set_xlim(-12, 530)
    ax.set_ylim(-20, 322)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.apply_aspect()
    _dessiner_foncier(ax, plan)
    _dessiner_voiries(ax, plan)
    _dessiner_zones(ax, plan)
    _dessiner_reperes(ax)
    _legende_site(ax, marqueurs, signalement)
    if fleches:
        _dessiner_fleches(ax, plan, scenario["cadence"], scenario["parametres"]["schema"])


def dessiner_objets(ax, usine, t: float, animes: bool = False) -> dict:
    """Marqueurs ronds (pods, kits 2D, lots) et carrés (modules, camions) à l'instant t ;
    renvoie {type: artiste}."""
    return creer_marqueurs(ax, usine.positions(t), MARQUEURS, animes)


def creer_marqueurs(ax, positions: dict, marqueurs: dict, animes: bool = False) -> dict:
    """Un nuage de points par type d'objet, aux positions {id: (x, y, type)} ; renvoie
    {type: artiste}."""
    par_type = {type_objet: [] for type_objet in marqueurs}
    for x, y, type_objet in positions.values():
        par_type[type_objet].append((x, y))
    artistes = {}
    for type_objet, (forme, couleur, contour, taille) in marqueurs.items():
        points = np.array(par_type[type_objet]) if par_type[type_objet] else np.empty((0, 2))
        artistes[type_objet] = ax.scatter(points[:, 0], points[:, 1], marker=forme, s=taille,
                                          facecolors=couleur, edgecolors=contour,
                                          linewidths=0.9, zorder=8, animated=animes)
    return artistes


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Traçabilité d'un module : données de la vue 3 (sans interface)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def modules_en_defaut(usine) -> list[str]:
    """Modules dont le pod ou l'assemblage a eu un défaut détecté."""
    resultat = []
    for module in usine.objets_de_type("module"):
        pod = usine.objets.get(module["pod"]) if module["pod"] else None
        if module["cause_retrouvee"] is not None or (pod and pod["cause_retrouvee"] is not None):
            resultat.append(module["id"])
    return resultat


def module_par_defaut(usine) -> str | None:
    """Premier module dont le pod a eu un défaut, sinon premier expédié, sinon premier lancé."""
    for module in usine.objets_de_type("module"):
        if module["pod"] and usine.objets[module["pod"]]["cause_retrouvee"] is not None:
            return module["id"]
    expedies = usine.modules_expedies()
    modules = usine.objets_de_type("module")
    return expedies[0] if expedies else (modules[0]["id"] if modules else None)


def contenu_qr(usine, id_objet: str) -> str:
    """Contenu d'un QR code : AVELIS|<id>|type=…|module/pod=…|lot=… (SPEC §4.4)."""
    objet = usine.objets[id_objet]
    if objet["type"] == "module":
        return f"AVELIS|{id_objet}|type=module|pod={objet['pod'] or '-'}|lot={objet['lot'] or '-'}"
    return (f"AVELIS|{id_objet}|type={objet['type']}|module={objet.get('module', '-')}|"
            f"lot={objet.get('lot') or '-'}")


def _texte_qualite(usine, module: dict) -> str:
    """Défaut éventuel du pod ou de l'assemblage, et cause retrouvée ou non."""
    textes = []
    pod = usine.objets.get(module["pod"]) if module["pod"] else None
    for objet, libelle in ((pod, "pod"), (module, "assemblage")):
        if objet and objet["cause_retrouvee"] is not None:
            cause = (f"cause retrouvée : {objet['cause']}" if objet["cause_retrouvee"]
                     else "cause non retrouvée (trop peu d'événements lus)")
            textes.append(f"Défaut {libelle} — {cause}")
    return " ; ".join(textes) or "Aucun défaut détecté"


def resume_defauts(usine, module: dict) -> str:
    """Défauts du pod et de l'assemblage en une ligne courte (liste des modules en défaut)."""
    pod = usine.objets.get(module["pod"]) if module["pod"] else None
    defauts = []
    for objet, libelle in ((pod, "pod"), (module, "assemblage")):
        if objet and objet["cause_retrouvee"] is not None:
            cause = objet["cause"] if objet["cause_retrouvee"] else "cause non retrouvée"
            defauts.append(f"défaut {libelle} ({cause})")
    return ", ".join(defauts)


def fiche_module(usine, id_module: str) -> dict:
    """Généalogie, destination, délai, distance, état de la trace et qualité d'un module."""
    module = usine.objets[id_module]
    lot = usine.objets.get(module["lot"]) if module["lot"] else None
    pod = usine.objets.get(module["pod"]) if module["pod"] else None
    chaine = [id_module, module["pod"], module["lot"], lot and lot["camion"],
              lot and lot["fournisseur"]]
    complete, manquants = usine.trace_complete(id_module)
    distance_amont = (lot["distance_reception"] + module["distance_matiere"]) if lot else 0.0
    return {
        "genealogie": " ← ".join(element for element in chaine if element),
        "destination": (f"{module['destination']} (camion {module['camion']})"
                        if module["destination"] else "pas encore expédié"),
        "delai": (formater_delai(module["t_stock_pf"] - module["t_of"])
                  if module["t_stock_pf"] is not None else "pas encore en stock PF"),
        "distance": {"module": module["distance"], "pod": pod["distance"] if pod else 0.0,
                     "amont": distance_amont},
        "complete": complete, "manquants": manquants,
        "qualite": _texte_qualite(usine, module),
        "qr": contenu_qr(usine, id_module),
    }


def chronologie_module(usine, id_module: str) -> list[dict]:
    """Événements du module, de son pod, de son lot et des camions liés, dans l'ordre."""
    module = usine.objets[id_module]
    lot = usine.objets.get(module["lot"]) if module["lot"] else None
    objets = [id_module, module["pod"], module["lot"], lot and lot["camion"], module["camion"]]
    evenements = [e for objet in objets if objet
                  for e in usine.tracabilite.par_objet.get(objet, [])]
    return sorted(evenements, key=lambda e: e["t"])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Exports (sans boîte de dialogue : testables directement)
# ═════════════════════════════════════════════════════════════════════════════════════════════

COLONNES_CSV = ("t_min", "horodatage", "id", "type", "evenement", "zone", "lot", "lu",
                "t_affichage_min", "affiche_a", "alerte", "message")


def _decimal(x: float | None) -> str:
    """Nombre à deux décimales avec virgule (tableurs français) ; vide si absent."""
    return "" if x is None else f"{x:.2f}".replace(".", ",")


def exporter_journal_csv(usine, chemin) -> int:
    """Journal de traçabilité en CSV (« ; », UTF-8 avec BOM) ; renvoie le nombre de lignes."""
    journal = sorted(usine.tracabilite.journal, key=lambda e: e["t"])
    with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
        ecrivain = csv.writer(fichier, delimiter=";")
        ecrivain.writerow(COLONNES_CSV)
        for e in journal:
            affiche = sim.horloge_courte(e["t_affichage"]) if e["t_affichage"] is not None else ""
            ecrivain.writerow([_decimal(e["t"]), sim.horloge_courte(e["t"]), e["id"], e["type"],
                               e["evenement"], e["zone"], e["lot"] or "",
                               "oui" if e["lu"] else "non", _decimal(e["t_affichage"]), affiche,
                               "oui" if e["alerte"] else "non", e["message"]])
    return len(journal)


def _figure_seule(tracer, scenario: dict, taille=(6.4, 4.2)) -> Figure:
    """Figure autonome d'un seul graphique, pour l'export."""
    figure = Figure(figsize=taille, facecolor=SURFACE, layout="constrained")
    tracer(figure.add_subplot(), scenario)
    return figure


def figures_a_exporter(scenario: dict, t_schema: float) -> dict[str, Figure]:
    """Toutes les figures du scénario, chacune dans sa propre Figure."""
    figures = {f"{rang:02d}_{tracer.__name__.removeprefix('tracer_')}":
               _figure_seule(tracer, scenario) for rang, tracer in enumerate(GRAPHIQUES, 1)}
    grille = Figure(figsize=(16, 8.4), facecolor=SURFACE, layout="constrained")
    for ax, tracer in zip(grille.subplots(2, 3).flat, GRAPHIQUES):
        tracer(ax, scenario)
    figures["07_statistiques_2x3"] = grille
    proche = scenario["reseau"]["proche"]
    for nom, option, titre in (("08_carte_usine_unique", "A", "Usine unique"),
                               ("09_carte_satellites", "B", "Usine mère + satellites (proche)")):
        figure = Figure(figsize=(5.6, 5.6), facecolor=SURFACE, layout="constrained")
        tracer_carte(figure.add_subplot(), proche[option], titre)
        legende_cartes(figure)
        figures[nom] = figure
    figures["10_cout_par_logement"] = _figure_seule(tracer_cout_par_logement, scenario)
    # cadre fixe et moteur de rendu dès maintenant : les étiquettes du plan sont placées en pixels
    schema = Figure(figsize=(12, 7.8), facecolor=SURFACE)
    FigureCanvasAgg(schema)
    ax = schema.add_axes(CADRE_SCHEMA_EXPORT)
    ax.set_title(f"Schéma de l'usine et flux · {sim.horloge(t_schema)}", loc="left", fontsize=11,
                 fontweight="bold")
    dessiner_site(ax, scenario)
    dessiner_objets(ax, scenario["usine"], t_schema)
    figures["11_schema_usine"] = schema
    return {nom: finaliser_figure(figure) for nom, figure in figures.items()}


def finaliser_figure(figure: Figure) -> Figure:
    """Figure à exporter : premier dessin à sa taille définitive, puis corps des barres et noms
    des cartes ajustés à cette taille (le dessin de l'export les reprend tels quels)."""
    FigureCanvasAgg(figure).draw()
    ajuster_etiquettes_barres(figure)
    placer_noms_cartes(figure)
    return figure


def exporter_figures(scenario: dict, dossier, t_schema: float = 0.0) -> list[pathlib.Path]:
    """Exporte toutes les figures en PNG 300 dpi dans `dossier` ; renvoie les chemins."""
    dossier = pathlib.Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemins = []
    for nom, figure in figures_a_exporter(scenario, t_schema).items():
        chemin = dossier / f"{nom}.png"
        figure.savefig(chemin, dpi=DPI_EXPORT, facecolor=figure.get_facecolor())
        chemins.append(chemin)
    return chemins


def _police(taille: int):
    """Police des étiquettes : Segoe UI si présente, sinon police par défaut de Pillow."""
    try:
        return ImageFont.truetype("segoeui.ttf", taille)
    except OSError:
        return ImageFont.load_default()


def image_qr(contenu: str, cote_px: int) -> Image.Image:
    """Image PIL d'un QR code carré de `cote_px` pixels (qrcode requis)."""
    image = qrcode.make(contenu).get_image().convert("RGB")
    return image.resize((cote_px, cote_px), Image.NEAREST)


def etiquette_qr(contenu: str, titre: str, sous_titre: str) -> Image.Image:
    """Étiquette imprimable : QR code, identifiant et ligne d'information."""
    qr = image_qr(contenu, 360)
    etiquette = Image.new("RGB", (420, 500), "white")
    etiquette.paste(qr, (30, 20))
    dessin = ImageDraw.Draw(etiquette)
    dessin.text((210, 400), titre, fill=ENCRE, font=_police(30), anchor="mm")
    dessin.text((210, 445), sous_titre, fill=ENCRE_2, font=_police(17), anchor="mm")
    dessin.rectangle((0, 0, 419, 499), outline=AXE, width=2)
    return etiquette


def generer_etiquettes_qr(usine, dossier) -> list[pathlib.Path]:
    """Étiquettes QR (PNG) des modules expédiés et de leurs pods ; qrcode requis."""
    if qrcode is None:
        raise RuntimeError("le module qrcode n'est pas installé")
    dossier = pathlib.Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemins = []
    for id_module in usine.modules_expedies():
        module = usine.objets[id_module]
        for id_objet in (id_module, module["pod"]):
            if id_objet:
                sous_titre = f"lot {module['lot']} · vers {module['destination']}"
                chemin = dossier / f"{id_objet}.png"
                etiquette_qr(contenu_qr(usine, id_objet), id_objet, sous_titre).save(chemin)
                chemins.append(chemin)
    return chemins


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Tableau des chiffres (vue 1) : lignes par catégorie
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _f(x, decimales: int = 0) -> str:
    """Raccourci de formatage des nombres."""
    return m.formater_nombre(x, decimales)


def _lignes_cadence(s: dict) -> list[tuple]:
    """Catégorie « Cadence »."""
    c = s["cadence"]
    lignes = [("Cadence étudiée", _f(s["parametres"]["cadence"]), "logements/an", "H"),
              ("Haut de la fourchette Avelis", _f(m.H("logements_par_an")), "logements/an", "A"),
              ("Logements par jour", _f(c["logements_jour"], 2), "logements/j", "H"),
              ("Modules par jour", _f(c["modules_jour"], 2), "modules/j", "H"),
              ("Pods par jour", _f(c["pods_jour"], 2), "pods/j", "H"),
              ("Panneaux 2D par jour", _f(c["panneaux_jour"]), "panneaux/j", "H"),
              ("Temps d'ouverture", _f(c["temps_ouverture_min"]), "min/j", "H"),
              ("Temps net après TRS", _f(c["temps_net_min"]), "min/j", "H"),
              ("Takt module", _f(c["takt_module_min"], 1), "min", "H"),
              ("Takt pod", _f(c["takt_pod_min"], 1), "min", "H")]
    for cle, ressource in c["ressources"].items():
        goulot = " (goulot)" if cle == c["goulot"] else ""
        lignes.append((f"{ressource['libelle']}{goulot}", f"{ressource['nombre']} · charge "
                       f"{m.formater_pourcentage(ressource['charge'])}", "unités", "H"))
    return lignes


def _lignes_logistique(s: dict) -> list[tuple]:
    """Catégorie « Logistique » : camions, quais, réseau national."""
    d, reseau = s["dimension"], s["reseau"]
    lignes = [("Matières reçues", _f(d["tonnes_jour"]), "t/j", "H"),
              ("Camions entrants", _f(d["camions_entrants_jour"], 2), "camions/j", "H"),
              ("Quais de réception (secours compris)", _f(d["quais_reception"]), "quais", "H"),
              ("Unités expédiées (modules ou kits)", _f(d["unites_expediees_jour"], 1),
               "unités/j", "H"),
              ("Camions sortants (convois ou semis)", _f(d["camions_sortants_jour"], 2),
               "camions/j", "H"),
              ("Quais d'expédition (secours compris)", _f(d["quais_expedition"]), "quais", "H"),
              ("Coût par logement, A usine unique", _f(reseau["proche"]["A"]["cout_par_logement"]),
               "€", "H")]
    for variante in m.VARIANTES:
        lignes.append((f"Coût par logement, B satellites ({variante})",
                       _f(reseau[variante]["B"]["cout_par_logement"]), "€", "H"))
        lignes.append((f"Point de bascule ({variante})", _f(s["bascule"][variante]),
                       "logements/an", "H"))
    lignes.append(("Part livrée en direct (hybride)",
                   m.formater_pourcentage(reseau["hybride"]["part_directe"]), "", "H"))
    return lignes


def _lignes_surfaces(s: dict) -> list[tuple]:
    """Catégorie « Surfaces »."""
    d, e = s["dimension"], s["evolutivite"]
    lignes = [(libelle, _f(d["surfaces"][cle]), "m²", "H")
              for cle, libelle in m.LIBELLES_SURFACES.items()]
    lignes += [("Besoin total", _f(d["besoin_total"]), "m²", "H"),
               ("Stockage pour 1 000 logements/an", _f(d["m2_stockage_pour_1000"]), "m²", "H"),
               ("Emprise actuelle de Torcy", _f(m.H("surface_site_actuel")), "m²", "A"),
               ("Foncier disponible (extension)", _f(m.H("surface_extension")), "m²", "A"),
               ("Emprise totale", _f(m.H("surface_totale")), "m²", "A"),
               ("Aire du site par la formule du lacet", _f(m.aire_polygone(m.SITE_ACTUEL)), "m²",
                "H"),
               ("Aire de l'extension par la formule du lacet", _f(m.aire_polygone(m.EXTENSION)),
                "m²", "H"),
               ("Surface utilisable, site seul", _f(d["utilisable_site_seul"]), "m²", "H"),
               ("Surface utilisable, site + extension", _f(d["utilisable_avec_extension"]), "m²",
                "H"),
               ("Cadence max admissible, site seul", _f(e["cadence_max_site_seul"]),
                "logements/an", "H"),
               ("Cadence max admissible, avec extension", _f(e["cadence_max_avec_extension"]),
                "logements/an", "H")]
    return lignes


def _lignes_implantation(s: dict) -> list[tuple]:
    """Catégorie « Implantation » : les plans côte à côte."""
    lignes = []
    for nom, donnees in s["implantations"].items():
        court = NOMS_COURTS_IMPLANTATIONS[nom]
        retenue = " · retenue" if nom == s["parametres"]["implantation"] else ""
        d = donnees["distances"]
        sous = [ligne["zone"] for ligne in donnees["capacite"]
                if ligne["couverture"] is not None and ligne["couverture"] < 1]
        lignes += [(f"{court}{retenue} — distance d'un sous-ensemble", _f(d["sous_ensemble"]),
                    "m", "H"),
                   (f"{court} — gammes pod / module / 2D",
                    f"{_f(d['pod'])} / {_f(d['module'])} / {_f(d['2D'])}", "m", "H"),
                   (f"{court} — croisements de flux", _f(donnees["croisements"]), "", "H"),
                   (f"{court} — contrôle géométrique",
                    "conforme" if not donnees["anomalies"] else
                    f"{len(donnees['anomalies'])} anomalie(s)", "", "H"),
                   (f"{court} — zones sous-dimensionnées", ", ".join(sous) or "aucune", "", "H")]
    return lignes


def _lignes_simulation(s: dict) -> list[tuple]:
    """Catégorie « Simulation »."""
    r = s["resultats"]
    comptes = f"{r['lances']} / {r['termines']} / {r['expedies']}"
    lignes = [("Objectif", _f(r["objectif_jour"], 1), "modules/j", "H"),
              ("Débit en régime établi (dès le jour 3)", _f(r["debit_regime_etabli"], 2),
               "modules/j", "H"),
              ("Taux d'atteinte de l'objectif", m.formater_pourcentage(r["taux_atteinte"], 1), "",
               "H"),
              ("Lancés / terminés / expédiés", comptes, "modules", "H"),
              ("Délai OF → stock PF moyen", formater_delai(r["delai_fabrication_moyen_min"]), "",
               "H"),
              ("Délai OF → stock PF, 90e centile", formater_delai(r["delai_fabrication_p90_min"]),
               "", "H"),
              ("En-cours moyen", _f(r["en_cours_moyen"], 1), "modules", "H"),
              ("Stock matières max / stock PF max",
               f"{r['stock_matieres_max']} / {r['stock_pf_max']}", "unités", "H"),
              ("Ruptures, attentes et blocages", _f(r["total_ruptures_attentes"]), "", "H")]
    lignes += [(f"   dont {nature}", _f(nombre), "", "H")
               for nature, nombre in r["ruptures_attentes"].items()]
    lignes += [("Retards fournisseurs / transporteurs",
                " / ".join(map(str, r["retards"].values())), "", "H"),
               ("Pannes machine", _f(r["pannes"]), "", "H"),
               ("Défauts pod / assemblage", " / ".join(map(str, r["defauts"].values())), "", "H"),
               ("Distance d'un sous-ensemble (simulée)", _f(r["distance_moyenne_sous_ensemble"]),
                "m", "H"),
               ("Distance totale en charge", _f(r["distance_totale"] / sim.METRES_PAR_KM, 1), "km",
                "H")]
    return lignes


def _lignes_tracabilite(s: dict) -> list[tuple]:
    """Catégorie « Traçabilité »."""
    r, techno = s["resultats"], s["parametres"]["techno"]
    return [("Technologie", techno, "", "H"),
            ("Modules expédiés tracés de bout en bout", m.formater_pourcentage(r["pct_traces"], 1),
             "", "H"),
            ("Valeur théorique (taux de lecture ^ points)",
             m.formater_pourcentage(sim.part_tracee_theorique(techno), 1), "", "H"),
            ("Taux de lecture global", m.formater_pourcentage(r["taux_lecture"], 2), "", "H"),
            ("Délai moyen événement → écran", formater_delai(r["delai_alertes_moyen_min"]), "",
             "H"),
            ("Délai maximal événement → écran", formater_delai(r["delai_alertes_max_min"]), "",
             "H"),
            ("Causes de défaut retrouvées", m.formater_pourcentage(r["taux_causes_retrouvees"]),
             "", "H")]


def _lignes_utilisation(s: dict) -> list[tuple]:
    """Catégorie « Utilisation des ressources » (simulée)."""
    usine = s["usine"]
    return [(ressource.nom, m.formater_pourcentage(ressource.taux_utilisation(usine.duree)),
             f"{ressource.capacite} poste(s)", "H") for ressource in usine.ressources()]


def lignes_tableau(scenario: dict) -> list[tuple[str, list[tuple]]]:
    """Tableau des chiffres en 7 catégories : [(catégorie, [(indicateur, valeur, unité, H/A)])]."""
    return [("Cadence", _lignes_cadence(scenario)),
            ("Logistique", _lignes_logistique(scenario)),
            ("Surfaces", _lignes_surfaces(scenario)),
            ("Implantation : comparaison des deux plans", _lignes_implantation(scenario)),
            ("Simulation", _lignes_simulation(scenario)),
            ("Traçabilité", _lignes_tracabilite(scenario)),
            ("Utilisation des ressources", _lignes_utilisation(scenario))]


def lignes_reseau(scenario: dict) -> list[tuple]:
    """Tableau comparatif des réseaux : A, B proche, B hybride."""
    a, b_proche, b_hybride = (scenario["reseau"]["proche"]["A"], scenario["reseau"]["proche"]["B"],
                              scenario["reseau"]["hybride"]["B"])
    options = (a, b_proche, b_hybride)
    million = m.EUROS_PAR_MILLION
    return [
        ("Kilomètres facturés (km/an)", *(_f(o["km_an"]) for o in options)),
        ("Transport (M€/an)", *(_f(o["cout_transport_an"] / million, 2) for o in options)),
        ("Coûts fixes des satellites (M€/an)", *(_f(o["couts_fixes_an"] / million, 2)
                                                for o in options)),
        ("Coût total (M€/an)", *(_f(o["cout_total_an"] / million, 2) for o in options)),
        ("Coût par logement (€)", *(_f(o["cout_par_logement"]) for o in options)),
        ("CO2 (t/an)", *(_f(o["co2_t_an"]) for o in options)),
        ("Distance moyenne pondérée (km)", *(_f(o["distance_moyenne_km"]) for o in options)),
        ("Délai moyen de livraison (h)", *(_f(o["delai_moyen_h"], 1) for o in options)),
        ("Stock tampon des satellites (kits)", *(_f(sum(o["stocks_tampons"].values()), 1)
                                                for o in options)),
        ("Part livrée en direct", *(m.formater_pourcentage(o["part_directe"]) for o in options)),
        ("Point de bascule (logements/an)", "—", _f(scenario["bascule"]["proche"]),
         _f(scenario["bascule"]["hybride"])),
    ]


def analyser_nombre(texte: str, entier: bool) -> int | float:
    """Nombre saisi à la française (virgule décimale, espaces des milliers) ; ValueError sinon."""
    propre = re.sub(r"\s", "", texte).replace(",", ".")  # \s : espaces insécables compris
    try:
        return int(propre) if entier else float(propre)
    except ValueError:
        raise ValueError("nombre entier attendu" if entier else "nombre attendu") from None


def analyser_valeur(texte: str, defaut):
    """Valeur d'hypothèse saisie, au format de sa valeur par défaut : entier, réel, ou séquence
    dont les éléments sont séparés par « ; » ou « · »."""
    if isinstance(defaut, tuple):
        morceaux = re.split(r"[;·]", texte)
        if len(morceaux) != len(defaut):
            raise ValueError(f"{len(defaut)} valeurs attendues, séparées par « ; »")
        return tuple(analyser_valeur(morceau, d) for morceau, d in zip(morceaux, defaut))
    return analyser_nombre(texte, isinstance(defaut, int))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Widgets utilitaires
# ═════════════════════════════════════════════════════════════════════════════════════════════

def configurer_styles(racine: tk.Tk) -> None:
    """Thème « clam » et styles de l'application (marges en pixels logiques)."""
    style = ttk.Style(racine)
    style.theme_use("clam")
    hauteur_ligne = (tkfont.Font(root=racine, family=POLICE, size=9).metrics("linespace")
                     + px(racine, 8))
    style.configure(".", font=(POLICE, 10), background=PAGE, foreground=ENCRE)
    style.configure("Page.TFrame", background=PAGE)
    style.configure("Barre.TFrame", background=BARRE)
    style.configure("Barre.TLabel", background=BARRE, foreground=ENCRE_2, font=(POLICE, 9, "bold"))
    style.configure("Valeur.TLabel", background=BARRE, foreground=ENCRE, font=(POLICE, 10, "bold"))
    style.configure("Statut.TLabel", background=BARRE, foreground=ENCRE_MUETTE, font=(POLICE, 8))
    style.configure("Page.TLabel", background=PAGE, foreground=ENCRE_2)
    style.configure("Reco.TLabel", background=PAGE, foreground=ENCRE_2, font=(POLICE, 9))
    style.configure("Barre.TRadiobutton", background=BARRE)
    style.configure("Barre.TCheckbutton", background=PAGE)
    for nom, fond, texte, survol in (("Nav.TButton", "white", ENCRE, "#e8ebf1"),
                                     ("NavActif.TButton", ORANGE_ACTIF, "white", ORANGE_ACTIF),
                                     ("Action.TButton", MARINE, "white", MARINE_CLAIR)):
        style.configure(nom, font=(POLICE, 10, "bold"), padding=(px(racine, 10), px(racine, 3)),
                        anchor="w", background=fond, foreground=texte, bordercolor=AXE)
        style.map(nom, background=[("active", survol)], foreground=[("active", texte)])
    style.configure("Action.TButton", anchor="center")
    style.configure("Export.TButton", font=(POLICE, 9), padding=(px(racine, 8), px(racine, 3)),
                    anchor="w")
    style.configure("TButton", padding=(px(racine, 8), px(racine, 3)))
    style.configure("Treeview", rowheight=hauteur_ligne, font=(POLICE, 9), background=SURFACE,
                    fieldbackground=SURFACE, indent=px(racine, RETRAIT_ARBRE))
    style.configure("Treeview.Heading", font=(POLICE, 9, "bold"))
    style.configure("TNotebook.Tab", padding=(px(racine, 14), px(racine, 5)), font=(POLICE, 10))
    racine.option_add("*TCombobox*Listbox.font", f"{{{POLICE}}} 9")  # liste ouverte


def retour_automatique(etiquette: tk.Widget) -> None:
    """Le texte de l'étiquette revient à la ligne à sa largeur réelle, bordure et marge internes
    déduites (pas de troncature, quelle que soit la taille de la fenêtre)."""
    def ajuster(evenement) -> None:
        etiquette.configure(wraplength=max(evenement.width - px(etiquette, MARGE_INTERNE_TEXTE),
                                           px(etiquette, 40)))
    etiquette.bind("<Configure>", ajuster, add="+")


class BarreDefilementAuto(ttk.Scrollbar):
    """Barre de défilement (placée avec grid) masquée quand tout le contenu est visible."""

    def set(self, debut, fin) -> None:
        """Montre ou masque la barre, puis la met à jour."""
        if float(debut) <= 0 and float(fin) >= 1:
            self.grid_remove()
        else:
            self.grid()
        super().set(debut, fin)


def _elements(arbre: ttk.Treeview, parent: str = "", profondeur: int = 0):
    """(élément, profondeur) de toutes les lignes d'un Treeview."""
    for element in arbre.get_children(parent):
        yield element, profondeur
        yield from _elements(arbre, element, profondeur + 1)


def colonnes_affichees(arbre: ttk.Treeview) -> list[str]:
    """Colonnes affichées, « #0 » compris pour une arborescence. Après un `configure`, l'option
    « show » revient en objets Tcl et non en texte : on la relit mot par mot."""
    montre = {str(mot) for mot in arbre.tk.splitlist(arbre.cget("show"))}
    return (["#0"] if "tree" in montre else []) + list(arbre.cget("columns"))


def largeur_colonnes(arbre: ttk.Treeview) -> int:
    """Somme des largeurs des colonnes affichées (pixels)."""
    return sum(int(arbre.column(colonne, "width")) for colonne in colonnes_affichees(arbre))


def ajuster_colonnes(arbre: ttk.Treeview) -> None:
    """Chaque colonne prend la largeur de son titre ou de son contenu le plus large : aucun
    texte tronqué. La dernière s'étire ; au-delà de la largeur visible, la barre horizontale
    apparaît."""
    style = ttk.Style(arbre)
    police = tkfont.Font(root=arbre, font=style.lookup("Treeview", "font"))
    gras = tkfont.Font(root=arbre, font=style.lookup("Treeview.Heading", "font"))
    retrait = int(float(style.lookup("Treeview", "indent") or 0))
    colonnes = colonnes_affichees(arbre)
    besoins = {colonne: gras.measure(arbre.heading(colonne, "text")) for colonne in colonnes}
    for element, profondeur in _elements(arbre):
        for colonne in colonnes:
            if colonne == "#0":
                besoin = police.measure(arbre.item(element, "text")) + retrait * (profondeur + 1)
            else:
                besoin = police.measure(arbre.set(element, colonne))
            besoins[colonne] = max(besoins[colonne], besoin)
    for rang, colonne in enumerate(colonnes):
        largeur = besoins[colonne] + px(arbre, MARGE_COLONNE)
        arbre.column(colonne, width=largeur, minwidth=largeur, stretch=rang == len(colonnes) - 1)


def ajuster_figure(canevas: FigureCanvasTkAgg) -> None:
    """Remet la figure à la taille de son widget. À sa première apparition, matplotlib la passe
    au rapport de pixels de l'écran (×1,5 à 150 %) en agrandissant le widget ; si son cadre ne
    s'agrandit pas, aucun <Configure> ne suit et la figure, trop grande, serait rognée."""
    widget = canevas.get_tk_widget()
    largeur, hauteur = widget.winfo_width(), widget.winfo_height()
    actuelle = (round(canevas.figure.bbox.width), round(canevas.figure.bbox.height))
    if largeur > 1 and hauteur > 1 and actuelle != (largeur, hauteur):
        canevas.resize(types.SimpleNamespace(width=largeur, height=hauteur))


def surveiller_taille(canevas: FigureCanvasTkAgg) -> None:
    """Vérifie la taille de la figure chaque fois que son widget apparaît."""
    widget = canevas.get_tk_widget()
    widget.bind("<Map>", lambda _evenement: widget.after_idle(ajuster_figure, canevas), add="+")


class Infobulle:
    """Info-bulle affichée au survol d'un widget, même désactivé."""

    def __init__(self, widget: tk.Widget, texte: str):
        self.widget, self.texte, self.fenetre = widget, texte, None
        widget.bind("<Enter>", self.montrer, add="+")
        widget.bind("<Leave>", self.cacher, add="+")

    def montrer(self, _evenement=None) -> None:
        """Ouvre la bulle sous le widget."""
        x = self.widget.winfo_rootx() + px(self.widget, 12)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + px(self.widget, 4)
        self.fenetre = tk.Toplevel(self.widget)
        self.fenetre.wm_overrideredirect(True)
        self.fenetre.wm_geometry(f"+{x}+{y}")
        tk.Label(self.fenetre, text=self.texte, bg="#fffbe6", fg=ENCRE, relief="solid",
                 borderwidth=1, font=(POLICE, 9), justify="left",
                 wraplength=px(self.widget, 300), padx=px(self.widget, 6),
                 pady=px(self.widget, 4)).pack()

    def cacher(self, _evenement=None) -> None:
        """Ferme la bulle."""
        if self.fenetre is not None:
            self.fenetre.destroy()
            self.fenetre = None


class Tuile(tk.Frame):
    """Tuile d'indicateur : bande d'accent, titre, grande valeur, détail."""

    def __init__(self, parent: tk.Widget, titre: str, accent: str, fond: str):
        super().__init__(parent, bg=fond, highlightthickness=1, highlightbackground=GRILLE)
        marge = px(self, 10)
        tk.Frame(self, bg=accent, height=px(self, 5)).pack(fill="x")
        self.titre = tk.Label(self, text=titre, bg=fond, fg=ENCRE_2, font=(POLICE, 9, "bold"),
                              anchor="w", justify="left")
        self.titre.pack(fill="x", padx=marge, pady=(px(self, 7), 0))
        self.valeur = tk.Label(self, text="—", bg=fond, fg=ENCRE, font=(POLICE, 19, "bold"),
                               anchor="w")
        self.valeur.pack(fill="x", padx=marge)
        self.detail = tk.Label(self, text="", bg=fond, fg=ENCRE_2, font=(POLICE, 8), anchor="w",
                               justify="left")
        self.detail.pack(fill="x", padx=marge, pady=(0, px(self, 8)))
        for etiquette in (self.titre, self.detail):
            retour_automatique(etiquette)

    def afficher(self, valeur: str, detail: str) -> None:
        """Met à jour la valeur et le détail."""
        self.valeur.config(text=valeur)
        self.detail.config(text=detail)


def arbre_avec_defilement(parent: tk.Widget, colonnes: dict, arborescence: bool = False):
    """Treeview avec barres de défilement (l'horizontale n'apparaît qu'au besoin) ; colonnes =
    {identifiant: titre}, largeurs fixées au contenu par ajuster_colonnes."""
    cadre = ttk.Frame(parent, style="Page.TFrame")
    cles = list(colonnes)[1:] if arborescence else list(colonnes)
    arbre = ttk.Treeview(cadre, columns=cles, show="tree headings" if arborescence else "headings")
    for cle, titre in colonnes.items():
        colonne = "#0" if arborescence and cle == list(colonnes)[0] else cle
        arbre.heading(colonne, text=titre, anchor="w")
        arbre.column(colonne, anchor="w")
    verticale = ttk.Scrollbar(cadre, orient="vertical", command=arbre.yview)
    horizontale = BarreDefilementAuto(cadre, orient="horizontal", command=arbre.xview)
    arbre.configure(yscrollcommand=verticale.set, xscrollcommand=horizontale.set)
    arbre.grid(row=0, column=0, sticky="nsew")
    verticale.grid(row=0, column=1, sticky="ns")
    horizontale.grid(row=1, column=0, sticky="ew")
    cadre.rowconfigure(0, weight=1)
    cadre.columnconfigure(0, weight=1)
    ajuster_colonnes(arbre)
    if not arborescence:  # les flèches d'une arborescence ouvrent et ferment ses nœuds
        defilement_horizontal(arbre)
    return cadre, arbre


def defilement_horizontal(arbre: ttk.Treeview) -> None:
    """Décalage à gauche ou à droite : Maj + molette (ou molette inclinée, pavé tactile),
    flèches gauche et droite. Un champ de saisie ouvert se ferme d'abord (il perd le focus),
    sinon il resterait à son ancienne place. Un pas du tableau vaut un pixel."""
    pas = px(arbre, 60)

    def decaler(sens: int) -> str:
        arbre.focus_set()
        arbre.xview_scroll(sens * pas, "units")
        return "break"

    arbre.bind("<Shift-MouseWheel>", lambda e: decaler(-1 if e.delta > 0 else 1))
    arbre.bind("<Left>", lambda _evenement: decaler(-1))
    arbre.bind("<Right>", lambda _evenement: decaler(1))


def editer_cellule(arbre: ttk.Treeview, element: str, colonne: str, valider) -> ttk.Entry | None:
    """Champ de saisie posé sur une cellule. Entrée : `valider(texte)` renvoie None si la saisie
    est acceptée (le champ se ferme) ou le motif du refus (le champ reste ouvert) ; perte du
    focus : même contrôle, mais le champ se ferme dans tous les cas ; Échap : abandon."""
    boite = arbre.bbox(element, colonne)
    if not boite:
        return None
    x, y, largeur, hauteur = boite
    texte = tk.StringVar(value=arbre.set(element, colonne))
    champ = ttk.Entry(arbre, textvariable=texte, font=(POLICE, 9))
    champ.place(x=x, y=y, width=largeur, height=hauteur)
    champ.focus_set()
    champ.select_range(0, "end")
    ouvert = [True]

    def fermer(enregistrer: bool, rester_si_refus: bool) -> None:
        if not ouvert[0]:
            return
        if enregistrer and valider(texte.get()) is not None and rester_si_refus:
            return
        ouvert[0] = False
        champ.destroy()

    for touche in ("<Return>", "<KP_Enter>"):
        champ.bind(touche, lambda _evenement: fermer(True, True))
    champ.bind("<Escape>", lambda _evenement: fermer(False, False))
    champ.bind("<FocusOut>", lambda _evenement: fermer(True, False))
    return champ


def toile(parent: tk.Widget, figure: Figure) -> FigureCanvasTkAgg:
    """Intègre une figure matplotlib dans un widget Tk (taille de la figure surveillée)."""
    canevas = FigureCanvasTkAgg(figure, master=parent)
    canevas.get_tk_widget().pack(fill="both", expand=True)
    surveiller_taille(canevas)
    return canevas


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Onglet « Paramètres » de la vue 1 : hypothèses et réseau modifiables
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _colonne(arbre: ttk.Treeview, nom: str) -> str:
    """Identifiant « #n » d'une colonne nommée (celui que renvoie identify_column)."""
    return f"#{list(arbre.cget('columns')).index(nom) + 1}"


def _differences(a: dict, b: dict) -> int:
    """Nombre d'hypothèses qui diffèrent entre deux états, plus un par liste du réseau
    (chantiers, usines satellites) qui diffère."""
    return (sum(a["hypotheses"][cle] != b["hypotheses"][cle] for cle in a["hypotheses"])
            + (a["chantiers"] != b["chantiers"]) + (a["satellites"] != b["satellites"]))


def _accorder(nombre: int, singulier: str, pluriel: str) -> str:
    """« 1 paramètre », « 3 paramètres »."""
    return f"{nombre} {singulier if nombre <= 1 else pluriel}"


class OngletParametres(ttk.Frame):
    """Hypothèses, chantiers et usines satellites modifiables. Les saisies forment un brouillon,
    contrôlé puis appliqué au modèle par appliquer(), au recalcul du scénario."""

    COLONNES_HYPOTHESES = {"cle": "Paramètre", "valeur": "Valeur", "defaut": "Valeur par défaut",
                           "action": "Rétablir", "unite": "Unité", "marquage": "H/A",
                           "commentaire": "Commentaire"}
    COLONNES_CHANTIERS = {"nom": "Chantier", "lat": "Latitude", "lon": "Longitude",
                          "part": "Part de la demande (%)", "action": "Retirer"}
    COLONNES_SATELLITES = {"nom": "Usine satellite", "lat": "Latitude", "lon": "Longitude",
                           "action": "Retirer"}
    CHAMPS_LIEU = {"lat": 0, "lon": 1, "part": 2}  # rang dans (lat, lon[, part])

    def __init__(self, parent: tk.Widget, app: "Application"):
        super().__init__(parent, style="Page.TFrame", padding=(0, px(parent, 6), 0, 0))
        self.app, self.brouillon = app, m.etat_parametres()
        self.champ, self.message_erreur = None, ""
        self._creer_commandes()  # empaquetées d'abord : leur place est garantie
        self.sous_onglets = ttk.Notebook(self)
        self.sous_onglets.pack(fill="both", expand=True)
        self._creer_hypotheses()
        self._creer_reseau()
        self.rafraichir()

    def _creer_commandes(self) -> None:
        """Barre du bas : état du brouillon, « Tout rétablir », « Appliquer et recalculer »."""
        bas = ttk.Frame(self, style="Page.TFrame")
        bas.pack(side="bottom", fill="x", pady=(px(self, 6), 0))
        ttk.Button(bas, text="Appliquer et recalculer", style="Action.TButton",
                   command=self.app.recalculer).pack(side="right")
        ttk.Button(bas, text="Tout rétablir par défaut", command=self.tout_retablir).pack(
            side="right", padx=px(self, 8))
        self.etat = ttk.Label(bas, style="Reco.TLabel", justify="left", anchor="w")
        self.etat.pack(side="left", fill="x", expand=True)
        retour_automatique(self.etat)

    def _creer_hypotheses(self) -> None:
        """Sous-onglet « Hypothèses » : recherche, aide, tableau de toutes les hypothèses."""
        cadre = ttk.Frame(self.sous_onglets, style="Page.TFrame")
        haut = ttk.Frame(cadre, style="Page.TFrame")
        haut.pack(fill="x", pady=px(self, 6))
        ttk.Label(haut, text="Rechercher", style="Page.TLabel").pack(side="left")
        self.filtre = tk.StringVar()
        ttk.Entry(haut, textvariable=self.filtre, width=22).pack(side="left", padx=px(self, 6))
        self.filtre.trace_add("write", lambda *_arguments: self._remplir_hypotheses())
        aide = ttk.Label(haut, style="Reco.TLabel", justify="left", text=(
            "Double-cliquez sur une ligne pour modifier sa valeur (séquences : valeurs séparées "
            f"par « ; »). « {TEXTE_RETABLIR} » rétablit la valeur d'origine. {LEGENDE_HA}"))
        aide.pack(side="left", fill="x", expand=True)
        retour_automatique(aide)
        tableau, self.arbre_hypotheses = arbre_avec_defilement(cadre, self.COLONNES_HYPOTHESES)
        tableau.pack(fill="both", expand=True)
        self._lier(self.arbre_hypotheses, self._double_clic_hypothese, self._clic_hypothese)
        self.sous_onglets.add(cadre, text="Hypothèses")

    def _creer_reseau(self) -> None:
        """Sous-onglet « Réseau » : ajout d'une ville, tableaux des chantiers et des usines
        satellites, total des parts et commandes du réseau."""
        cadre = ttk.Frame(self.sous_onglets, style="Page.TFrame")
        self._creer_ajout_ville(cadre)
        pied = ttk.Frame(cadre, style="Page.TFrame")
        pied.pack(side="bottom", fill="x", pady=(px(self, 6), 0))
        for texte, commande in (("Appliquer et voir la carte du réseau", self.voir_carte),
                                ("Réseau par défaut", self.reseau_par_defaut),
                                ("Répartir les parts à 100 %", self.repartir_parts)):
            ttk.Button(pied, text=texte, command=commande).pack(side="right",
                                                                padx=(px(self, 8), 0))
        self.total_parts = ttk.Label(pied, style="Reco.TLabel")
        self.total_parts.pack(side="left")
        tableaux = ttk.Frame(cadre, style="Page.TFrame")
        tableaux.pack(fill="both", expand=True)
        self.arbres_reseau = {}
        for cle, colonnes in (("chantiers", self.COLONNES_CHANTIERS),
                              ("satellites", self.COLONNES_SATELLITES)):
            tableau, arbre = arbre_avec_defilement(tableaux, colonnes)
            tableau.pack(side="left", fill="both", expand=True,
                         padx=(0 if cle == "chantiers" else px(self, 10), 0))
            self._lier(arbre, lambda evenement, cle=cle: self._double_clic_lieu(evenement, cle),
                       lambda evenement, cle=cle: self._clic_lieu(evenement, cle))
            self.arbres_reseau[cle] = arbre
        self.sous_onglets.add(cadre, text="Réseau : chantiers et usines satellites")

    def _creer_ajout_ville(self, cadre: ttk.Frame) -> None:
        """Choix d'une ville de France et boutons d'ajout comme chantier ou usine satellite."""
        ajout = ttk.Frame(cadre, style="Page.TFrame")
        ajout.pack(fill="x", pady=px(self, 6))
        ttk.Label(ajout, text="Ville", style="Page.TLabel").pack(side="left")
        villes = list(m.VILLES_FRANCE)
        self.ville = tk.StringVar(value=villes[0])
        ttk.Combobox(ajout, textvariable=self.ville, values=villes, state="readonly",
                     font=(POLICE, 9), width=max(map(len, villes)) + 4).pack(
            side="left", padx=px(self, 6))
        ttk.Button(ajout, text="Ajouter comme chantier",
                   command=lambda: self.ajouter("chantiers")).pack(side="left")
        ttk.Button(ajout, text="Ajouter comme usine satellite",
                   command=lambda: self.ajouter("satellites")).pack(side="left",
                                                                    padx=px(self, 6))
        aide = ttk.Label(ajout, style="Reco.TLabel", justify="left", text=(
            "Double-cliquez sur une cellule pour changer un nom, une position (degrés) ou une "
            "part. Les parts des chantiers totalisent 100 %."))
        aide.pack(side="left", fill="x", expand=True)
        retour_automatique(aide)

    def _lier(self, arbre: ttk.Treeview, double_clic, clic) -> None:
        """Double-clic : édition ; clic sur la colonne d'action : rétablir ou retirer ; main au
        survol de cette colonne ; molette : le champ en cours d'édition est abandonné."""
        arbre.bind("<Double-1>", double_clic)
        arbre.bind("<ButtonRelease-1>", clic)
        arbre.bind("<Motion>", lambda evenement: arbre.configure(cursor="hand2" if (
            arbre.identify_row(evenement.y)
            and arbre.identify_column(evenement.x) == _colonne(arbre, "action")) else ""))
        arbre.bind("<MouseWheel>", lambda _evenement: self._fermer_edition(), add="+")

    # — Hypothèses —

    def _ligne_hypothese(self, cle: str) -> tuple:
        """(valeurs, étiquettes) de la ligne d'une hypothèse ; fond orangé si elle diffère de sa
        valeur par défaut."""
        _, unite, marquage, commentaire = m.HYPOTHESES[cle]
        valeur, defaut = self.brouillon["hypotheses"][cle], m.HYPOTHESES_DEFAUT[cle]
        valeurs = (cle, formater_valeur(valeur, cle), formater_valeur(defaut, cle),
                   TEXTE_RETABLIR, unite, marquage, commentaire)
        return valeurs, ("modifie",) if valeur != defaut else ()

    def _remplir_hypotheses(self) -> None:
        """Lignes des hypothèses dont la clé ou le commentaire contient le texte recherché."""
        filtre = self.filtre.get().strip().lower()
        arbre = self.arbre_hypotheses
        arbre.delete(*arbre.get_children())
        for cle, (_, _, _, commentaire) in m.HYPOTHESES.items():
            if filtre in f"{cle} {commentaire}".lower():
                valeurs, etiquettes = self._ligne_hypothese(cle)
                arbre.insert("", "end", iid=cle, values=valeurs, tags=etiquettes)
        arbre.tag_configure("modifie", background=FOND_MODIFIE)
        ajuster_colonnes(arbre)

    def _maj_hypothese(self, cle: str) -> None:
        """Met à jour la ligne d'une hypothèse sans reconstruire le tableau (défilement gardé)."""
        if self.arbre_hypotheses.exists(cle):
            valeurs, etiquettes = self._ligne_hypothese(cle)
            self.arbre_hypotheses.item(cle, values=valeurs, tags=etiquettes)
            ajuster_colonnes(self.arbre_hypotheses)
        self._afficher_etat()

    def _double_clic_hypothese(self, evenement) -> None:
        """Ouvre l'édition de la valeur de la ligne double-cliquée."""
        arbre, cle = self.arbre_hypotheses, self.arbre_hypotheses.identify_row(evenement.y)
        if cle and arbre.identify_column(evenement.x) != _colonne(arbre, "action"):
            self._editer(arbre, cle, "valeur", lambda texte: self.saisir_hypothese(cle, texte))

    def _clic_hypothese(self, evenement) -> None:
        """Clic sur « ↺ Valeur par défaut » : la ligne reprend sa valeur d'origine."""
        arbre, cle = self.arbre_hypotheses, self.arbre_hypotheses.identify_row(evenement.y)
        if cle and arbre.identify_column(evenement.x) == _colonne(arbre, "action"):
            self.retablir_hypothese(cle)

    def saisir_hypothese(self, cle: str, texte: str) -> str | None:
        """Nouvelle valeur saisie : None si elle est acceptée, sinon le motif du refus."""
        try:
            valeur = analyser_valeur(texte, m.HYPOTHESES_DEFAUT[cle])
        except ValueError as erreur:
            return self._refuser(f"« {cle} » : {erreur}")
        anomalies = m.anomalies_hypothese(cle, valeur)
        if anomalies:
            return self._refuser(anomalies[0])
        self.brouillon["hypotheses"][cle] = valeur
        self.message_erreur = ""
        self._maj_hypothese(cle)
        return None

    def retablir_hypothese(self, cle: str) -> None:
        """Valeur par défaut d'une hypothèse, dans le brouillon."""
        self.brouillon["hypotheses"][cle] = m.HYPOTHESES_DEFAUT[cle]
        self.message_erreur = ""
        self._maj_hypothese(cle)

    # — Réseau —

    def _remplir_reseau(self) -> None:
        """Tableaux des chantiers (part en %) et des usines satellites ; total des parts, en
        rouge s'il n'est pas de 100 %."""
        for cle, arbre in self.arbres_reseau.items():
            arbre.delete(*arbre.get_children())
            for nom, lieu in self.brouillon[cle].items():
                valeurs = [nom, formater_valeur(lieu[0]), formater_valeur(lieu[1])]
                if len(lieu) == 3:
                    valeurs.append(formater_valeur(round(lieu[2] * 100, 2)))
                arbre.insert("", "end", iid=nom, values=(*valeurs, TEXTE_RETIRER))
            ajuster_colonnes(arbre)
        total = sum(part for _, _, part in self.brouillon["chantiers"].values())
        juste = abs(total - 1) <= m.TOLERANCE_PARTS
        self.total_parts.configure(
            text=f"Total des parts : {m.formater_pourcentage(total, 1)}"
                 + ("" if juste else " — doit faire 100 %"),
            foreground=ENCRE_2 if juste else ROUGE_ERREUR)

    def _double_clic_lieu(self, evenement, cle: str) -> None:
        """Ouvre l'édition de la cellule double-cliquée (nom, latitude, longitude ou part)."""
        arbre = self.arbres_reseau[cle]
        nom, colonne = arbre.identify_row(evenement.y), arbre.identify_column(evenement.x)
        if not nom or not colonne.startswith("#") or colonne == "#0":
            return
        champ = arbre.cget("columns")[int(colonne[1:]) - 1]
        if champ != "action":
            self._editer(arbre, nom, champ,
                         lambda texte: self.saisir_lieu(cle, nom, champ, texte))

    def _clic_lieu(self, evenement, cle: str) -> None:
        """Clic sur « ✕ Retirer » : le lieu quitte le brouillon."""
        arbre = self.arbres_reseau[cle]
        nom = arbre.identify_row(evenement.y)
        if nom and arbre.identify_column(evenement.x) == _colonne(arbre, "action"):
            del self.brouillon[cle][nom]
            self.message_erreur = ""
            self.rafraichir()

    def saisir_lieu(self, cle: str, nom: str, champ: str, texte: str) -> str | None:
        """Nom, latitude, longitude ou part (%) saisis : None si acceptés, sinon le motif."""
        lieux = self.brouillon[cle]
        genre = "Chantier" if cle == "chantiers" else "Usine satellite"
        if champ == "nom":
            nouveau = texte.strip()
            if not nouveau or (nouveau != nom and nouveau in lieux):
                return self._refuser(f"nom « {nouveau} » vide ou déjà pris")
            self.brouillon[cle] = {(nouveau if n == nom else n): l for n, l in lieux.items()}
        else:
            try:
                nombre = analyser_nombre(texte, entier=False)
            except ValueError as erreur:
                return self._refuser(f"{genre} « {nom} » : {erreur}")
            lieu = list(lieux[nom])
            lieu[self.CHAMPS_LIEU[champ]] = nombre / 100 if champ == "part" else nombre
            anomalies = m.anomalies_lieu(genre, nom, lieu[0], lieu[1])
            if champ == "part" and not 0 < lieu[2] <= 1:
                anomalies.append(f"{genre} « {nom} » : part comprise entre 0 et 100 % attendue")
            if anomalies:
                return self._refuser(anomalies[0])
            lieux[nom] = tuple(lieu)
        self.message_erreur = ""
        self.rafraichir()
        return None

    def ajouter(self, cle: str) -> None:
        """Ajoute la ville choisie comme chantier (part proposée : PART_NOUVEAU_CHANTIER) ou
        comme usine satellite."""
        nom = self.ville.get()
        if nom in self.brouillon[cle]:
            self._refuser(f"« {nom} » figure déjà dans la liste")
            return
        lat, lon = m.VILLES_FRANCE[nom]
        self.brouillon[cle][nom] = ((lat, lon, PART_NOUVEAU_CHANTIER) if cle == "chantiers"
                                    else (lat, lon))
        self.message_erreur = ""
        self.rafraichir()

    def repartir_parts(self) -> None:
        """Parts des chantiers ramenées proportionnellement à un total de 100 %."""
        chantiers = self.brouillon["chantiers"]
        total = sum(part for _, _, part in chantiers.values())
        if total > 0:
            self.brouillon["chantiers"] = {nom: (lat, lon, part / total)
                                           for nom, (lat, lon, part) in chantiers.items()}
        self.rafraichir()

    def reseau_par_defaut(self) -> None:
        """Chantiers et usines satellites d'origine, dans le brouillon."""
        defaut = m.parametres_par_defaut()
        self.brouillon["chantiers"] = defaut["chantiers"]
        self.brouillon["satellites"] = defaut["satellites"]
        self.message_erreur = ""
        self.rafraichir()

    def voir_carte(self) -> None:
        """Applique et recalcule, puis affiche l'onglet « Réseau » et ses cartes."""
        if self.app.recalculer():
            vue = self.app.vues[1]
            vue.onglets.select(vue.onglet_reseau)

    # — Commun —

    def _editer(self, arbre: ttk.Treeview, element: str, colonne: str, valider) -> None:
        """Ouvre un champ d'édition sur une cellule (un seul à la fois)."""
        self._fermer_edition()
        self.champ = editer_cellule(arbre, element, colonne, valider)

    def _fermer_edition(self) -> None:
        """Abandonne le champ d'édition ouvert, s'il y en a un."""
        if self.champ is not None and self.champ.winfo_exists():
            self.champ.destroy()
        self.champ = None

    def _refuser(self, motif: str) -> str:
        """Affiche le motif d'un refus dans la barre d'état et le renvoie."""
        self.message_erreur = f"Valeur refusée — {motif}"
        self._afficher_etat()
        return motif

    def _afficher_etat(self) -> None:
        """Barre d'état : refus éventuel, modifications non appliquées, écarts aux valeurs
        par défaut."""
        attente = _differences(self.brouillon, m.etat_parametres())
        ecarts = _differences(self.brouillon, m.parametres_par_defaut())
        resume = (f"{_accorder(ecarts, 'paramètre différent', 'paramètres différents')} "
                  "des valeurs par défaut.")
        if self.message_erreur:
            texte, couleur = f"{self.message_erreur}. {resume}", ROUGE_ERREUR
        elif attente:
            en_attente = _accorder(attente, "modification non appliquée",
                                   "modifications non appliquées")
            texte = f"{en_attente} : cliquez sur « Appliquer et recalculer ». {resume}"
            couleur = ORANGE_ACTIF
        else:
            texte, couleur = f"Paramètres appliqués au scénario affiché. {resume}", ENCRE_2
        self.etat.configure(text=texte, foreground=couleur)

    def rafraichir(self) -> None:
        """Redessine les tableaux et la barre d'état à partir du brouillon."""
        self._fermer_edition()
        self._remplir_hypotheses()
        self._remplir_reseau()
        self._afficher_etat()

    def tout_retablir(self) -> None:
        """Toutes les valeurs par défaut, dans le brouillon."""
        self.brouillon, self.message_erreur = m.parametres_par_defaut(), ""
        self.rafraichir()

    def appliquer(self) -> bool:
        """Contrôle le brouillon et l'applique au modèle ; False, avec un message, s'il est
        refusé (les valeurs en vigueur ne changent pas)."""
        if self.champ is not None and self.champ.winfo_exists():
            self.champ.event_generate("<FocusOut>")  # saisie en cours : validée, puis fermée
        self._fermer_edition()
        try:
            m.appliquer_parametres(**self.brouillon)
        except ValueError as erreur:
            messagebox.showerror("Paramètres refusés",
                                 f"Corrigez ces paramètres avant de recalculer :\n\n{erreur}")
            return False
        self.message_erreur = ""
        self._afficher_etat()
        return True


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Vue 1 : Statistiques
# ═════════════════════════════════════════════════════════════════════════════════════════════

class VueStatistiques(ttk.Frame):
    """Six tuiles d'indicateurs et quatre onglets : tableau, graphiques, réseau, paramètres."""

    TITRES_TUILES = ("Cadence atteinte", "Distance d'un sous-ensemble",
                     "Stockage / 1 000 logements", "Tracés de bout en bout",
                     "Délai événement → écran", "Ruptures et attentes")

    def __init__(self, parent: tk.Widget, app: "Application"):
        super().__init__(parent, style="Page.TFrame", padding=(px(parent, 14), px(parent, 10)))
        self.app, self.scenario, self.perime = app, None, True
        rangee = ttk.Frame(self, style="Page.TFrame")
        rangee.pack(fill="x")
        self.tuiles = []
        for rang, (titre, (accent, fond)) in enumerate(zip(self.TITRES_TUILES, TEINTES_TUILES)):
            tuile = Tuile(rangee, titre, accent, fond)
            tuile.grid(row=0, column=rang, sticky="nsew",
                       padx=(0 if rang == 0 else px(self, 8), 0))
            rangee.columnconfigure(rang, weight=1, uniform="tuiles")
            self.tuiles.append(tuile)
        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill="both", expand=True, pady=(px(self, 10), 0))
        self._creer_onglet_tableau()
        self._creer_onglet_graphiques()
        self._creer_onglet_reseau()
        self._creer_onglet_parametres()

    def _creer_onglet_tableau(self) -> None:
        """Onglet « Tableau des chiffres » : Treeview groupé en 7 catégories, légende H/A."""
        cadre = ttk.Frame(self.onglets, style="Page.TFrame")
        legende = ttk.Label(cadre, text=LEGENDE_HA, style="Reco.TLabel", justify="left")
        legende.pack(side="bottom", fill="x", pady=(px(self, 4), 0))  # avant le tableau
        retour_automatique(legende)
        tableau, self.tableau = arbre_avec_defilement(
            cadre, {"indicateur": "Indicateur", "valeur": "Valeur", "unite": "Unité",
                    "source": "H/A"}, arborescence=True)
        tableau.pack(fill="both", expand=True)
        self.onglets.add(cadre, text="Tableau des chiffres")

    def _creer_onglet_graphiques(self) -> None:
        """Onglet « Graphiques » : 2 × 3 graphiques matplotlib."""
        cadre = ttk.Frame(self.onglets, style="Page.TFrame")
        # taille initiale réaliste : un premier dessin trop petit écraserait les axes, et
        # « constrained » ne leur rendrait leur largeur que par petits pas, dessin après dessin
        self.figure_graphiques = Figure(figsize=TAILLE_INITIALE_GRAPHIQUES, facecolor=SURFACE,
                                        layout="constrained")
        # liste et non `.flat` : un itérateur numpy s'épuise au premier dessin et les graphiques
        # resteraient figés sur le premier scénario
        self.axes_graphiques = list(self.figure_graphiques.subplots(2, 3).flat)
        self.toile_graphiques = toile(cadre, self.figure_graphiques)
        self.toile_graphiques.mpl_connect("draw_event", self._apres_dessin_graphiques)
        self.onglets.add(cadre, text="Graphiques")

    def _creer_onglet_reseau(self) -> None:
        """Onglet « Réseau » : deux cartes et courbe de coût, recommandation, tableau comparatif
        (empaquetés avant la figure : leur place est garantie, la figure prend le reste)."""
        cadre = ttk.Frame(self.onglets, style="Page.TFrame")
        bas = ttk.Frame(cadre, style="Page.TFrame")  # recommandation et tableau côte à côte
        bas.pack(side="bottom", fill="x", pady=(px(self, 6), 0))
        tableau, self.tableau_reseau = arbre_avec_defilement(
            bas, {"indicateur": "Indicateur", "a": "A · usine unique",
                  "b_proche": "B · satellites (proche)", "b_hybride": "B · satellites (hybride)"})
        self.tableau_reseau.configure(height=LIGNES_TABLEAU_RESEAU)
        tableau.pack(side="right", fill="y")
        self.recommandation = ttk.Label(bas, style="Reco.TLabel", justify="left", anchor="nw")
        self.recommandation.pack(side="left", fill="both", expand=True, padx=(px(self, 4),
                                                                              px(self, 12)))
        retour_automatique(self.recommandation)
        self.figure_reseau = Figure(figsize=TAILLE_INITIALE_RESEAU, facecolor=SURFACE,
                                    layout="constrained")
        self.toile_reseau = toile(cadre, self.figure_reseau)
        self.toile_reseau.mpl_connect("draw_event", self._apres_dessin_reseau)
        self.onglets.add(cadre, text="Réseau")
        self.onglet_reseau = cadre

    def _creer_onglet_parametres(self) -> None:
        """Onglet « Paramètres » : hypothèses, chantiers et usines satellites modifiables."""
        self.parametres = OngletParametres(self.onglets, self.app)
        self.onglets.add(self.parametres, text="Paramètres")

    def scenario_change(self, scenario: dict) -> None:
        """Nouveau scénario : redessin immédiat si la vue est visible, sinon à l'affichage."""
        self.scenario, self.perime = scenario, True
        if self.winfo_ismapped():
            self.actualiser()

    def montrer(self) -> None:
        """La vue devient visible."""
        if self.perime and self.scenario is not None:
            self.actualiser()

    def cacher(self) -> None:
        """La vue est masquée (rien à suspendre)."""

    def actualiser(self) -> None:
        """Tuiles, tableau, graphiques et réseau du scénario courant."""
        self._actualiser_tuiles()
        self._actualiser_tableau()
        for ax, tracer in zip(self.axes_graphiques, GRAPHIQUES):
            ax.clear()
            tracer(ax, self.scenario)
        self.toile_graphiques.draw_idle()
        self._actualiser_reseau()
        self.perime = False

    def _actualiser_tuiles(self) -> None:
        """Valeurs des six tuiles (SPEC §4.2)."""
        s, r = self.scenario, self.scenario["resultats"]
        d = s["implantations"][s["parametres"]["implantation"]]["distances"]
        dim = s["dimension"]
        attentes = sorted(r["ruptures_attentes"].items(), key=lambda item: -item[1])
        detail_attentes = ", ".join(f"{n} {nature.lower()}" for nature, n in attentes[:2] if n)
        debit = (f"{_f(r['debit_regime_etabli'], 2)} modules/j pour {_f(r['objectif_jour'], 1)} "
                 "(simulé, dès le jour 3)" if r["debit_regime_etabli"] is not None
                 else "simulation trop courte (moins de 3 jours)")
        valeurs = (
            (m.formater_pourcentage(r["taux_atteinte"], 1), debit),
            (f"{_f(d['sous_ensemble'])} m", f"pod {_f(d['pod'])} m + module {_f(d['module'])} m ; "
                                            f"gamme 2D {_f(d['2D'])} m"),
            (f"{_f(dim['m2_stockage_pour_1000'])} m²",
             f"matières {_f(dim['surfaces']['stock_matieres'])} m² + produits finis "
             f"{_f(dim['surfaces']['stock_pf'])} m²"),
            (m.formater_pourcentage(r["pct_traces"], 1),
             f"{s['parametres']['techno']} · {r['expedies']} modules expédiés"),
            (formater_delai(r["delai_alertes_moyen_min"]),
             f"délai moyen des alertes ; maximum {formater_delai(r['delai_alertes_max_min'])}"),
            (_f(r["total_ruptures_attentes"]), f"dont {detail_attentes}" if detail_attentes
             else "aucune rupture ni attente"),
        )
        for tuile, (valeur, detail) in zip(self.tuiles, valeurs):
            tuile.afficher(valeur, detail)

    def _actualiser_tableau(self) -> None:
        """Remplit le tableau des chiffres."""
        self.tableau.delete(*self.tableau.get_children())
        for categorie, lignes in lignes_tableau(self.scenario):
            parent = self.tableau.insert("", "end", text=categorie, open=True)
            for indicateur, valeur, unite, source in lignes:
                self.tableau.insert(parent, "end", text=indicateur, values=(valeur, unite, source))
        ajuster_colonnes(self.tableau)

    def _actualiser_reseau(self) -> None:
        """Cartes, courbe de coût, tableau comparatif et recommandation."""
        self.figure_reseau.clear()
        ax_a, ax_b, ax_cout = self.figure_reseau.subplots(1, 3, width_ratios=(1, 1, 1.5))
        proche = self.scenario["reseau"]["proche"]
        tracer_carte(ax_a, proche["A"], "A · usine unique")
        tracer_carte(ax_b, proche["B"], "B · satellites (proche)")
        legende_cartes(self.figure_reseau)
        tracer_cout_par_logement(ax_cout, self.scenario)
        self.toile_reseau.draw_idle()
        self.tableau_reseau.delete(*self.tableau_reseau.get_children())
        for ligne in lignes_reseau(self.scenario):
            self.tableau_reseau.insert("", "end", values=ligne)
        ajuster_colonnes(self.tableau_reseau)
        self.recommandation.config(text="Recommandation — "
                                   + self.scenario["reseau"]["proche"]["recommandation"]
                                   + " " + self._texte_hybride())

    def _apres_dessin_graphiques(self, _evenement) -> None:
        """Graphiques à leur taille réelle : corps des barres horizontales adapté, et nouveau
        dessin s'il a changé (le suivant ne change plus rien)."""
        if ajuster_etiquettes_barres(self.figure_graphiques):
            self.toile_graphiques.draw_idle()

    def _apres_dessin_reseau(self, _evenement) -> None:
        """Les cartes sont à leur taille réelle : noms replacés, et nouveau dessin s'ils ont
        bougé (le suivant ne change plus rien)."""
        if placer_noms_cartes(self.figure_reseau):
            self.toile_reseau.draw_idle()

    def _texte_hybride(self) -> str:
        """Complément sur la variante hybride (bascule et livraisons directes)."""
        hybride = self.scenario["reseau"]["hybride"]
        return (f"Variante hybride : bascule à {_f(self.scenario['bascule']['hybride'])} "
                f"logements/an, {m.formater_pourcentage(hybride['part_directe'])} de la demande "
                "livrée en direct depuis Torcy (qui garde alors une capacité d'assemblage 3D).")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Vue 2 : Schéma de l'usine, animation et tableau de pilotage
# ═════════════════════════════════════════════════════════════════════════════════════════════

class IndicateursTemps:
    """Indicateurs instantanés du tableau de pilotage, calculés à l'instant t par recherche
    dichotomique dans des listes d'instants triées."""

    def __init__(self, usine):
        modules, pods = usine.objets_de_type("module"), usine.objets_de_type("pod")
        self.usine = usine
        self.objectif_jour = usine.calcul["modules_jour"]
        self.t_of = sorted(module["t_of"] for module in modules)
        self.t_pf = sorted(module["t_stock_pf"] for module in modules
                           if module["t_stock_pf"] is not None)
        self.t_exp = sorted(module["t_expedie"] for module in modules
                            if module["t_expedie"] is not None)
        self.t_pod_debut = sorted(usine.tracabilite.par_objet[pod["id"]][0]["t"] for pod in pods)
        self.t_pod_fin = sorted(pod["t_integre"] for pod in pods if pod["t_integre"] is not None)
        self.t_echantillons = [e["t"] for e in usine.echantillons]
        self.alertes = sorted((e for e in usine.tracabilite.journal if e["alerte"]),
                              key=lambda e: e["t_affichage"])
        self.t_alertes = [e["t_affichage"] for e in self.alertes]

    @staticmethod
    def _nombre(instants: list[float], t: float) -> int:
        """Nombre d'instants ≤ t."""
        return bisect.bisect_right(instants, t)

    def valeurs(self, t: float) -> dict[str, str]:
        """Textes du tableau de pilotage à l'instant t."""
        debut_jour = (sim.jour_de(t) - 1) * sim.minutes_jour()
        termines = self._nombre(self.t_pf, t) - bisect.bisect_left(self.t_pf, debut_jour)
        expedies = self._nombre(self.t_exp, t) - bisect.bisect_left(self.t_exp, debut_jour)
        objectif = self.objectif_jour * (t - debut_jour) / sim.minutes_jour()
        indice = max(0, self._nombre(self.t_echantillons, t) - 1)
        echantillon = self.usine.echantillons[indice] if self.usine.echantillons else {}
        return {
            "Terminés aujourd'hui / objectif à cette heure": f"{termines} / {_f(objectif, 1)}",
            "Expédiés aujourd'hui (total)": f"{expedies} ({self._nombre(self.t_exp, t)})",
            "En-cours (modules)": str(self._nombre(self.t_of, t) - self._nombre(self.t_pf, t)),
            "Stock matières (kits)": str(echantillon.get("stock_matieres", "—")),
            "Stock produits finis": str(echantillon.get("stock_pf", "—")),
            "Pods en cours": str(self._nombre(self.t_pod_debut, t)
                                 - self._nombre(self.t_pod_fin, t)),
            "Camions sur site": str(self.usine.camions_sur_site(t)),
        }

    def alertes_affichees(self, t: float, nombre: int = NB_ALERTES) -> list[dict]:
        """Les `nombre` dernières alertes déjà affichées (t_affichage ≤ t), la plus récente
        d'abord."""
        fin = self._nombre(self.t_alertes, t)
        return list(reversed(self.alertes[max(0, fin - nombre):fin]))


class VueSchema(ttk.Frame):
    """Plan du site, flèches de flux, animation par blitting, tableau de pilotage, mode suivi.
    Le jumeau numérique (PlanJumeau) en hérite : il remplace la source des positions, de
    l'horloge et des indicateurs (méthodes de la section « Source des données »)."""

    LIBELLES = LIBELLES_TDB
    MARQUEURS = MARQUEURS
    VITESSES, VITESSE_DEFAUT = VITESSES, VITESSE_DEFAUT
    signalement = False  # anneau rouge autour des pièces signalées : jumeau numérique seulement

    def __init__(self, parent: tk.Widget, app: "Application"):
        super().__init__(parent, style="Page.TFrame", padding=(px(parent, 12), px(parent, 8)))
        self.app, self.scenario, self.indicateurs = app, None, None
        self.t, self.lecture, self.suivi, self.perime = 0.0, False, None, True
        self._apres, self._fond, self._maj_curseur, self._alertes_vues = None, None, False, None
        self._redessin = None
        self.marqueurs, self.evenements_suivis = {}, []
        self.var_fleches = tk.BooleanVar(value=True)
        self.var_vitesse = tk.StringVar(value=f"{self.VITESSE_DEFAUT} min/s")
        self.var_temps = tk.StringVar(value="")
        self._creer_bandeau_suivi()
        # empaquetés avant la figure, qui prend le reste : leur place est garantie
        self._creer_commandes()
        self.haut = ttk.Frame(self, style="Page.TFrame")
        self.haut.pack(fill="both", expand=True)
        self._creer_tableau_bord(self.haut)
        self._creer_dessin(self.haut)

    # ── Construction ───────────────────────────────────────────────────────────────────────

    def _creer_bandeau_suivi(self) -> None:
        """Bandeau du mode suivi (masqué hors suivi)."""
        self.bandeau = tk.Frame(self, bg=BANDEAU_SUIVI, highlightthickness=1,
                                highlightbackground=COULEUR_SUIVI)
        ttk.Button(self.bandeau, text="Arrêter le suivi", command=self.arreter_suivi).pack(
            side="right", padx=px(self, 8), pady=px(self, 4))
        self.texte_bandeau = tk.Label(self.bandeau, text="", bg=BANDEAU_SUIVI, fg=ENCRE,
                                      font=(POLICE, 10, "bold"), anchor="w", justify="left")
        self.texte_bandeau.pack(side="left", fill="x", expand=True, padx=px(self, 10),
                                pady=px(self, 5))
        retour_automatique(self.texte_bandeau)

    def _creer_dessin(self, parent: tk.Widget) -> None:
        """Figure du site, barre d'outils matplotlib (zoom) et capture du fond pour le blitting."""
        cadre = ttk.Frame(parent, style="Page.TFrame")
        cadre.pack(side="left", fill="both", expand=True)
        self.figure = Figure(figsize=(6, 4), facecolor=SURFACE)
        self.ax = self.figure.add_axes((0.005, 0.005, 0.99, 0.99))
        self.toile = FigureCanvasTkAgg(self.figure, master=cadre)
        self.barre_outils = NavigationToolbar2Tk(self.toile, cadre, pack_toolbar=False)
        self.barre_outils.update()
        self.barre_outils.pack(side="bottom", fill="x")
        self.toile.get_tk_widget().pack(side="top", fill="both", expand=True)
        surveiller_taille(self.toile)
        self.toile.mpl_connect("draw_event", self._apres_dessin)
        self.toile.mpl_connect("resize_event", self._figure_redimensionnee)

    def _creer_tableau_bord(self, parent: tk.Widget) -> None:
        """Tableau de pilotage sur fond sombre : horloge, indicateurs, alertes affichées."""
        panneau = tk.Frame(parent, bg=SOMBRE, width=px(parent, LARGEUR_TABLEAU_BORD),
                           padx=px(parent, 12), pady=px(parent, 10))
        panneau.pack(side="right", fill="y", padx=(px(parent, 10), 0))
        panneau.pack_propagate(False)
        tk.Label(panneau, text="TABLEAU DE PILOTAGE", bg=SOMBRE, fg=SOMBRE_TEXTE_2,
                 font=(POLICE, 9, "bold")).pack(anchor="w")
        self.etiquette_horloge = tk.Label(panneau, text="", bg=SOMBRE, fg=SOMBRE_TEXTE,
                                          font=(POLICE, 20, "bold"))
        self.etiquette_horloge.pack(anchor="w", pady=(px(parent, 2), px(parent, 6)))
        self._creer_cartes(panneau)
        tk.Label(panneau, text=f"{NB_ALERTES} DERNIÈRES ALERTES AFFICHÉES", bg=SOMBRE,
                 fg=SOMBRE_TEXTE_2, font=(POLICE, 9, "bold")).pack(
            anchor="w", pady=(px(parent, 10), px(parent, 4)))
        self.texte_alertes = tk.Text(panneau, bg=SOMBRE_LIGNE, fg=SOMBRE_TEXTE, relief="flat",
                                     font=(POLICE, 9), wrap="word", padx=px(parent, 8),
                                     pady=px(parent, 6), state="disabled", height=4)
        self.texte_alertes.pack(fill="both", expand=True)
        self.texte_alertes.tag_configure("titre", font=(POLICE, 9, "bold"))
        self.texte_alertes.tag_configure("detail", foreground=SOMBRE_TEXTE_2)

    def _creer_cartes(self, panneau: tk.Widget) -> None:
        """Indicateurs instantanés en cartes sur deux colonnes."""
        grille = tk.Frame(panneau, bg=SOMBRE)
        grille.pack(fill="x")
        self.valeurs_tdb = {}
        for rang, libelle in enumerate(self.LIBELLES):
            carte = tk.Frame(grille, bg=SOMBRE_LIGNE, padx=px(panneau, 7), pady=px(panneau, 4))
            carte.grid(row=rang // 2, column=rang % 2, sticky="nsew", pady=px(panneau, 2),
                       padx=(0, px(panneau, 6)) if rang % 2 == 0 else 0)
            titre = tk.Label(carte, text=libelle, bg=SOMBRE_LIGNE, fg=SOMBRE_TEXTE_2,
                             font=(POLICE, 8), anchor="w", justify="left")
            titre.pack(fill="x")
            retour_automatique(titre)
            self.valeurs_tdb[libelle] = tk.Label(carte, text="—", bg=SOMBRE_LIGNE,
                                                 fg=SOMBRE_TEXTE, font=(POLICE, 13, "bold"),
                                                 anchor="w")
            self.valeurs_tdb[libelle].pack(fill="x")
        grille.columnconfigure((0, 1), weight=1, uniform="cartes")

    def _creer_commandes(self) -> None:
        """Lecture/Pause, Début, vitesse, curseur de temps, case « Flèches de flux »."""
        barre = ttk.Frame(self, style="Page.TFrame", padding=(0, px(self, 6), 0, 0))
        barre.pack(side="bottom", fill="x")
        self.barre_commandes = barre
        self.bouton_lecture = ttk.Button(barre, text="▶ Lecture", width=11,
                                         command=self.basculer_lecture)
        self.bouton_lecture.pack(side="left")
        ttk.Button(barre, text="↺ Début", command=self.revenir_au_debut).pack(
            side="left", padx=px(self, 6))
        ttk.Label(barre, text="Vitesse", style="Page.TLabel").pack(
            side="left", padx=(px(self, 8), px(self, 4)))
        ttk.Combobox(barre, textvariable=self.var_vitesse, state="readonly", width=10,
                     values=[f"{v} min/s" for v in self.VITESSES]).pack(side="left")
        ttk.Checkbutton(barre, text="Flèches de flux", variable=self.var_fleches,
                        style="Barre.TCheckbutton", command=self.redessiner_fond).pack(
            side="right", padx=(px(self, 8), 0))
        ttk.Label(barre, textvariable=self.var_temps, width=16, style="Page.TLabel").pack(
            side="right")
        self.curseur_temps = ttk.Scale(barre, from_=0, to=1, orient="horizontal",
                                       command=self._curseur_bouge)
        self.curseur_temps.pack(side="left", fill="x", expand=True, padx=px(self, 12))

    # ── Scénario et dessin du fond ──────────────────────────────────────────────────────────

    def scenario_change(self, scenario: dict) -> None:
        """Nouveau scénario : retour au début, suivi arrêté, fond à redessiner."""
        self.arreter_lecture()
        self.scenario, self.perime = scenario, True
        self.indicateurs = IndicateursTemps(scenario["usine"])
        self.suivi = None
        self.bandeau.pack_forget()
        self.t = 0.0
        self.curseur_temps.configure(to=scenario["usine"].duree)
        if self.winfo_ismapped():
            self.redessiner_fond()

    def montrer(self) -> None:
        """La vue devient visible : redessin si nécessaire."""
        if self.perime and self.scenario is not None:
            self.redessiner_fond()

    def cacher(self) -> None:
        """La vue est masquée : l'animation est suspendue."""
        self.arreter_lecture()

    def redessiner_fond(self) -> None:
        """Redessine le plan (fond fixe) puis recrée les artistes animés."""
        if self.scenario is None:
            return
        self.ax.clear()
        dessiner_site(self.ax, self.scenario, self.var_fleches.get(), self.MARQUEURS,
                      self.signalement)
        self.marqueurs = creer_marqueurs(self.ax, self.positions(self.t), self.MARQUEURS,
                                         animes=True)
        self.trace, = self.ax.plot([], [], color=COULEUR_SUIVI, linewidth=2.4, zorder=9,
                                   animated=True)
        self.halo = self.ax.scatter([], [], s=560, facecolors=[HALO_SUIVI],
                                    edgecolors=COULEUR_SUIVI, linewidths=2, zorder=9,
                                    animated=True)
        self.marqueurs_suivi = {forme: self.ax.scatter([], [], marker=forme, s=TAILLE_SUIVI,
                                                       edgecolors=ENCRE, linewidths=1.6,
                                                       zorder=10, animated=True)
                                for forme in ("o", "s")}  # marqueur agrandi de l'objet suivi
        self._fond = None
        self.barre_outils.update()
        self.perime = False
        self.toile.draw()  # déclenche draw_event : capture du fond, puis objets animés
        self.aller_a(self.t)

    def _apres_dessin(self, _evenement) -> None:
        """Fond mis en cache après chaque dessin complet (zoom, redimensionnement)."""
        self._fond = self.toile.copy_from_bbox(self.figure.bbox)
        self._dessiner_animes()

    def _figure_redimensionnee(self, _evenement) -> None:
        """La figure a changé de taille : le plan sera redessiné (étiquettes de distance replacées
        pour cette taille) dès que Tk sera libre, une seule fois par série de changements."""
        self.perime = True
        if self._redessin is None:
            self._redessin = self.after_idle(self._redessiner_si_visible)

    def _redessiner_si_visible(self) -> None:
        """Redessin différé après un changement de taille (sinon au prochain affichage)."""
        self._redessin = None
        if self.winfo_ismapped():
            self.redessiner_fond()

    # ── Animation ───────────────────────────────────────────────────────────────────────────

    def basculer_lecture(self) -> None:
        """Lecture / Pause."""
        if self.lecture:
            self.arreter_lecture()
        else:
            self.lecture = True
            self.bouton_lecture.config(text="❚❚ Pause")
            self._planifier()

    def arreter_lecture(self) -> None:
        """Met l'animation en pause."""
        self.lecture = False
        self.bouton_lecture.config(text="▶ Lecture")
        if self._apres is not None:
            self.after_cancel(self._apres)
            self._apres = None

    def revenir_au_debut(self) -> None:
        """Bouton « Début »."""
        self.aller_a(0.0)

    def _planifier(self) -> None:
        """Image suivante dans 40 ms, dessinée quand Tk est disponible (after + after_idle)."""
        self._apres = self.after(INTERVALLE_IMAGE_MS, lambda: self.after_idle(self.image_suivante))

    def vitesse(self) -> float:
        """Minutes simulées par seconde de lecture."""
        return float(self.var_vitesse.get().split()[0])

    def image_suivante(self) -> None:
        """Avance l'horloge d'un pas d'image et redessine les objets."""
        if not self.lecture or self.scenario is None:
            return
        pas = self.vitesse() * INTERVALLE_IMAGE_MS / MS_PAR_SECONDE
        self.aller_a(self.t + pas)
        if self.t >= self.duree():
            self.arreter_lecture()
        else:
            self._planifier()

    def aller_a(self, t: float) -> None:
        """Place l'horloge à l'instant t (borné à la durée simulée) et met tout à jour."""
        if self.scenario is None:
            return
        self.t = max(0.0, min(float(t), self.duree()))
        self._maj_curseur = True
        self.curseur_temps.set(self.t)
        self._maj_curseur = False
        self.var_temps.set(self.horloge(self.t))
        self._dessiner_animes()
        self._actualiser_tableau_bord()

    def _curseur_bouge(self, valeur: str) -> None:
        """Déplacement manuel du curseur de temps."""
        if not self._maj_curseur:
            self.aller_a(float(valeur))

    def _dessiner_animes(self) -> None:
        """Restaure le fond, place les objets à l'instant t, puis blit."""
        if self._fond is None or self.scenario is None or not self.marqueurs:
            return
        self.toile.restore_region(self._fond)
        par_type = {type_objet: [] for type_objet in self.MARQUEURS}
        positions = self.positions(self.t)
        for x, y, type_objet in positions.values():
            par_type[type_objet].append((x, y))
        for type_objet, artiste in self.marqueurs.items():
            points = par_type[type_objet]
            artiste.set_offsets(np.array(points) if points else np.empty((0, 2)))
            self.ax.draw_artist(artiste)
        self._dessiner_complements(positions)
        self.toile.blit(self.figure.bbox)

    def _dessiner_complements(self, positions: dict) -> None:
        """Artistes animés dessinés par-dessus les objets : ici, le mode suivi."""
        if self.suivi:
            self._dessiner_suivi(positions)

    # ── Source des données (remplacée par le jumeau numérique) ──────────────────────────────

    def duree(self) -> float:
        """Durée rejouable (min)."""
        return self.scenario["usine"].duree

    def horloge(self, t: float) -> str:
        """Horloge affichée à l'instant t."""
        return sim.horloge(t)

    def positions(self, t: float) -> dict:
        """{id: (x, y, type)} des objets visibles à l'instant t."""
        return self.scenario["usine"].positions(t)

    def valeurs_tableau(self, t: float) -> dict[str, str]:
        """Textes des indicateurs du tableau de pilotage à l'instant t."""
        return self.indicateurs.valeurs(t)

    def alertes_tableau(self, t: float) -> list[dict]:
        """Dernières alertes affichées à l'instant t."""
        return self.indicateurs.alertes_affichees(t)

    # ── Tableau de pilotage ─────────────────────────────────────────────────────────────────

    def _actualiser_tableau_bord(self) -> None:
        """Horloge, indicateurs instantanés et 9 dernières alertes affichées."""
        self.etiquette_horloge.config(text=self.horloge(self.t))
        for libelle, texte in self.valeurs_tableau(self.t).items():
            self.valeurs_tdb[libelle].config(text=texte)
        alertes = self.alertes_tableau(self.t)
        if alertes != self._alertes_vues:
            self._alertes_vues = alertes
            self._ecrire_alertes(alertes)

    def _ecrire_alertes(self, alertes: list[dict]) -> None:
        """Réécrit la liste des alertes : heure réelle, heure d'affichage et délai."""
        self.texte_alertes.config(state="normal")
        self.texte_alertes.delete("1.0", "end")
        if not alertes:
            self.texte_alertes.insert("end", "Aucune alerte affichée pour l'instant.", "detail")
        for alerte in alertes:
            delai = formater_delai(alerte["t_affichage"] - alerte["t"])
            survenue = sim.horloge_courte(alerte["t"])
            affichee = sim.horloge_courte(alerte["t_affichage"])
            self.texte_alertes.insert("end", f"⚠ {alerte['evenement']} · {alerte['id']}\n",
                                      "titre")
            self.texte_alertes.insert("end", f"survenue {survenue}, affichée {affichee} "
                                             f"(délai {delai})\n{alerte['message']}\n\n", "detail")
        self.texte_alertes.config(state="disabled")

    # ── Mode suivi ──────────────────────────────────────────────────────────────────────────

    def suivre(self, id_module: str) -> None:
        """Active le suivi d'un module : curseur placé à son OF, bandeau affiché."""
        usine = self.scenario["usine"]
        module = usine.objets[id_module]
        self.suivi = id_module
        self.evenements_suivis = sorted(
            (e for objet in (id_module, module["pod"]) if objet
             for e in usine.tracabilite.par_objet.get(objet, [])), key=lambda e: e["t"])
        self.bandeau.pack(fill="x", pady=(0, 8), before=self.haut)
        if self.perime:
            self.redessiner_fond()
        self.aller_a(module["t_of"])

    def arreter_suivi(self) -> None:
        """Désactive le mode suivi."""
        self.suivi = None
        self.bandeau.pack_forget()
        self.aller_a(self.t)

    def _objet_suivi_visible(self, positions: dict) -> str | None:
        """Le module s'il est visible, sinon son pod, son kit 2D ou son lot ; rien avant l'OF."""
        module = self.scenario["usine"].objets[self.suivi]
        if self.t < module["t_of"]:
            return None
        for candidat in (self.suivi, module["pod"], module["k2d"], module["lot"]):
            if candidat and candidat in positions:
                return candidat
        return None

    def _dessiner_suivi(self, positions: dict) -> None:
        """Trajet déjà parcouru, halo et bandeau du module suivi."""
        usine = self.scenario["usine"]
        module = usine.objets[self.suivi]
        composant = module["pod"] or module["k2d"]
        points = (usine.trace_parcourue(composant, self.t) if composant else [])
        points += usine.trace_parcourue(self.suivi, self.t)
        self.trace.set_data([p[0] for p in points], [p[1] for p in points])
        self.ax.draw_artist(self.trace)
        cible = self._objet_suivi_visible(positions)
        self.halo.set_offsets([positions[cible][:2]] if cible else np.empty((0, 2)))
        self.ax.draw_artist(self.halo)
        if cible:
            forme, couleur, _, _ = MARQUEURS[positions[cible][2]]
            marqueur = self.marqueurs_suivi[forme]
            marqueur.set_offsets([positions[cible][:2]])
            marqueur.set_facecolor(couleur)
            self.ax.draw_artist(marqueur)
        self._actualiser_bandeau(cible)

    def _actualiser_bandeau(self, cible: str | None) -> None:
        """Identifiant suivi et dernier événement enregistré à l'instant t."""
        fin = bisect.bisect_right([e["t"] for e in self.evenements_suivis], self.t)
        texte = f"Suivi : {self.suivi}"
        if cible and cible != self.suivi:
            texte += f" (en cours de fabrication : {cible})"
        if fin:
            dernier = self.evenements_suivis[fin - 1]
            etat = "lu" if dernier["lu"] else "non lu"
            texte += (f" · dernier événement : {dernier['evenement']} ({dernier['id']}, "
                      f"{sim.horloge_courte(dernier['t'])}, {etat})")
        else:
            t_of = self.scenario["usine"].objets[self.suivi]["t_of"]
            texte += f" · OF pas encore lancé (lancement {sim.horloge_courte(t_of)})"
        self.texte_bandeau.config(text=texte)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Vue 3 : Traçabilité d'un module
# ═════════════════════════════════════════════════════════════════════════════════════════════

class VueTracabilite(ttk.Frame):
    """Choix d'un module, fiche (généalogie, trace, qualité, QR) et chronologie colorée."""

    COLONNES = {"jour": "Jour", "heure": "Heure", "id": "Identifiant", "evenement": "Événement",
                "zone": "Zone", "lot": "Lot", "lu": "Lecture", "affiche": "Affiché à",
                "detail": "Détail"}
    RUBRIQUES = ("Généalogie", "Destination", "Délai OF → stock PF", "Distance parcourue",
                 "Trace", "Qualité")
    RUBRIQUES_A_COTE_DU_QR = 2  # les premières rubriques longent le QR code, les autres non
    STYLES_LIGNES = (("pod", {"foreground": TEXTE_POD}), ("lot", {"foreground": TEXTE_LOT}),
                     ("alerte", {"background": ROSE_ALERTE}),
                     ("non_lu", {"foreground": ENCRE_MUETTE}))

    def __init__(self, parent: tk.Widget, app: "Application"):
        super().__init__(parent, style="Page.TFrame", padding=(px(parent, 14), px(parent, 10)))
        self.app, self.scenario, self.perime, self.image_qr = app, None, True, None
        self.var_module = tk.StringVar()
        gauche = ttk.Frame(self, style="Page.TFrame", width=px(parent, LARGEUR_FICHE))
        gauche.pack(side="left", fill="y")
        gauche.pack_propagate(False)
        droite = ttk.Frame(self, style="Page.TFrame")
        droite.pack(side="left", fill="both", expand=True, padx=(px(parent, 12), 0))
        self._creer_selection(gauche)
        self._creer_fiche(gauche)
        self._creer_liste_defauts(droite)
        cadre, self.chronologie = arbre_avec_defilement(droite, self.COLONNES)
        cadre.pack(fill="both", expand=True)
        for tag, options in self.STYLES_LIGNES:  # le dernier configuré l'emporte : non lu en gris
            self.chronologie.tag_configure(tag, **options)

    def _creer_selection(self, parent: tk.Widget) -> None:
        """Liste déroulante des modules et bouton de suivi dans le schéma."""
        ligne = ttk.Frame(parent, style="Page.TFrame")
        ligne.pack(fill="x")
        ttk.Label(ligne, text="Module", style="Page.TLabel").pack(side="left",
                                                                  padx=(0, px(parent, 8)))
        self.choix = ttk.Combobox(ligne, textvariable=self.var_module, state="readonly")
        self.choix.pack(side="left", fill="x", expand=True)
        self.choix.bind("<<ComboboxSelected>>",
                        lambda _e: self.selectionner(self.var_module.get()))
        ttk.Button(parent, text="Suivre ce module dans le schéma", style="Action.TButton",
                   command=self.suivre_module).pack(fill="x", pady=(px(parent, 8), px(parent, 8)))

    def _creer_liste_defauts(self, parent: tk.Widget) -> None:
        """Modules dont le pod a eu un défaut, au-dessus de la chronologie (un clic l'affiche)."""
        ttk.Label(parent, text="Modules en défaut", style="Page.TLabel").pack(anchor="w")
        self.liste_defauts = tk.Listbox(parent, height=4, font=(POLICE, 9), activestyle="none",
                                        selectbackground=SERIES[0], relief="solid",
                                        borderwidth=1, highlightthickness=0)
        self.liste_defauts.pack(fill="x", pady=(0, px(parent, 8)))
        self.liste_defauts.bind("<<ListboxSelect>>", self._defaut_choisi)

    def _creer_fiche(self, parent: tk.Widget) -> None:
        """Fiche du module : titre et QR code côte à côte, rubriques, contenu du QR en clair."""
        fiche = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=GRILLE,
                         padx=px(parent, 12), pady=px(parent, 10))
        fiche.pack(fill="both", expand=True)
        fiche.columnconfigure(0, weight=1)
        self.titre_fiche = tk.Label(fiche, text="", bg=SURFACE, fg=ENCRE,
                                    font=(POLICE, 16, "bold"), anchor="w")
        self.titre_fiche.grid(row=0, column=0, sticky="ew")
        self.qr = tk.Label(fiche, bg=SURFACE)
        self.qr.grid(row=0, column=1, rowspan=1 + 2 * self.RUBRIQUES_A_COTE_DU_QR, sticky="ne",
                     padx=(px(parent, 8), 0))
        self.champs = {}
        for rang, cle in enumerate(self.RUBRIQUES):
            ligne, largeur = 1 + 2 * rang, 1 if rang < self.RUBRIQUES_A_COTE_DU_QR else 2
            tk.Label(fiche, text=cle.upper(), bg=SURFACE, fg=ENCRE_MUETTE,
                     font=(POLICE, 8, "bold"), anchor="w").grid(
                row=ligne, column=0, columnspan=largeur, sticky="ew", pady=(px(parent, 5), 0))
            self.champs[cle] = tk.Label(fiche, text="", bg=SURFACE, fg=ENCRE, font=(POLICE, 9),
                                        anchor="w", justify="left")
            self.champs[cle].grid(row=ligne + 1, column=0, columnspan=largeur, sticky="ew")
            retour_automatique(self.champs[cle])
        self.texte_qr = tk.Label(fiche, bg=SURFACE, fg=ENCRE_2, font=(POLICE, 8), anchor="w",
                                 justify="left")
        self.texte_qr.grid(row=1 + 2 * len(self.RUBRIQUES), column=0, columnspan=2, sticky="ew",
                           pady=(px(parent, 8), 0))
        retour_automatique(self.texte_qr)

    def scenario_change(self, scenario: dict) -> None:
        """Nouveau scénario : la vue sera remplie à son prochain affichage."""
        self.scenario, self.perime = scenario, True
        if self.winfo_ismapped():
            self.actualiser()

    def montrer(self) -> None:
        """La vue devient visible."""
        if self.perime and self.scenario is not None:
            self.actualiser()

    def cacher(self) -> None:
        """La vue est masquée (rien à suspendre)."""

    def actualiser(self) -> None:
        """Listes de modules et module par défaut (premier pod en défaut)."""
        usine = self.scenario["usine"]
        self.choix.configure(values=[module["id"] for module in usine.objets_de_type("module")])
        self.liste_defauts.delete(0, "end")
        for id_module in modules_en_defaut(usine):
            self.liste_defauts.insert("end", f"{id_module} — "
                                             f"{resume_defauts(usine, usine.objets[id_module])}")
        if not self.liste_defauts.size():
            self.liste_defauts.insert("end", "aucun module en défaut sur la période simulée")
        self.perime = False
        self.selectionner(module_par_defaut(usine))

    def _defaut_choisi(self, _evenement) -> None:
        """Clic dans la liste des modules en défaut."""
        selection = self.liste_defauts.curselection()
        if selection:
            id_module = self.liste_defauts.get(selection[0]).split(" — ")[0]
            if id_module in self.scenario["usine"].objets:
                self.selectionner(id_module)

    def selectionner(self, id_module: str | None) -> None:
        """Affiche la fiche et la chronologie du module."""
        if id_module is None:
            self.titre_fiche.config(text="Aucun module lancé")
            return
        self.var_module.set(id_module)
        usine = self.scenario["usine"]
        fiche = fiche_module(usine, id_module)
        self._remplir_fiche(id_module, fiche)
        self._remplir_chronologie(chronologie_module(usine, id_module))

    def _remplir_fiche(self, id_module: str, fiche: dict) -> None:
        """Champs de la fiche et QR code (ou identifiant si qrcode est absent)."""
        d = fiche["distance"]
        total = d["module"] + d["pod"] + d["amont"]
        self.titre_fiche.config(text=id_module)
        self.champs["Généalogie"].config(text=fiche["genealogie"])
        self.champs["Destination"].config(text=fiche["destination"])
        self.champs["Délai OF → stock PF"].config(text=fiche["delai"])
        self.champs["Distance parcourue"].config(
            text=f"{_f(total)} m (amont {_f(d['amont'])} m, pod {_f(d['pod'])} m, "
                 f"module {_f(d['module'])} m)")
        if fiche["complete"]:
            self.champs["Trace"].config(text="✓ COMPLÈTE : tous les points obligatoires sont lus",
                                        fg=BON)
        else:
            manquants = ", ".join(fiche["manquants"])
            self.champs["Trace"].config(text=f"✗ INCOMPLÈTE — points manquants : {manquants}",
                                        fg=CRITIQUE)
        self.champs["Qualité"].config(text=fiche["qualite"])
        lisible = fiche["qr"].replace("|", "|​")  # coupures de ligne permises après « | »
        if qrcode is not None:
            self.image_qr = ImageTk.PhotoImage(image_qr(fiche["qr"], px(self, TAILLE_QR_FICHE)))
            self.qr.config(image=self.image_qr)
            self.texte_qr.config(text=f"Contenu du QR code : {lisible}")
        else:
            self.qr.config(image="")
            self.texte_qr.config(text=f"QR code indisponible (module qrcode absent) : {lisible}")

    def _remplir_chronologie(self, evenements: list[dict]) -> None:
        """Lignes chronologiques colorées : pod orange, lot bleu, alertes roses, non lus gris."""
        self.chronologie.delete(*self.chronologie.get_children())
        for e in evenements:
            conditions = (("pod", e["type"] == "pod"), ("lot", e["type"] == "lot"),
                          ("alerte", e["alerte"]), ("non_lu", not e["lu"]))
            tags = [tag for tag, actif in conditions if actif]
            affiche = sim.horloge_courte(e["t_affichage"]) if e["t_affichage"] is not None else "—"
            self.chronologie.insert("", "end", tags=tags, values=(
                f"J{sim.jour_de(e['t'])}", sim.horloge_courte(e["t"]).split()[1], e["id"],
                e["evenement"], e["zone"], e["lot"] or "", "✓ lu" if e["lu"] else "✗ non lu",
                affiche, e["message"]))
        ajuster_colonnes(self.chronologie)

    def suivre_module(self) -> None:
        """Bascule en vue 2 et suit le module sélectionné."""
        id_module = self.var_module.get()
        if id_module in self.scenario["usine"].objets:
            self.app.afficher_vue(2)
            self.app.vues[2].suivre(id_module)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Vue 5 : Jumeau numérique (scans d'avelis_scan, usine unique avec extension)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def scenario_du_plan_jumeau(cadence: float, implantation: str) -> dict:
    """Ce dont dessiner_site a besoin pour le plan du jumeau : implantation choisie, schéma et
    cadence (épaisseur des flèches de flux)."""
    return {"parametres": {"implantation": implantation, "schema": jm.SCHEMA_JUMEAU},
            "cadence": m.calcul_cadence(cadence)}


def _texte_mesure(valeur: float | None, unite: str) -> str:
    """Valeur d'un indicateur comparé, avec son unité."""
    if valeur is None:
        return "—"
    if unite == "%":
        return m.formater_pourcentage(valeur, 1)
    if unite == "min":
        return formater_delai(valeur)
    decimales = 2 if abs(valeur) < 10 else 1 if abs(valeur) < 100 else 0
    texte = m.formater_nombre(valeur, decimales)
    return texte if unite == "—" else f"{texte} {unite}"


def _texte_ecart(ligne: dict) -> str:
    """Écart qualifié et rapport réel / simulé d'une étape."""
    if ligne["rapport"] is None:
        return ligne["ecart"]
    return f"{ligne['ecart']} (× {m.formater_nombre(ligne['rapport'], 2)})"


def nom_court_etape(ligne: dict) -> str:
    """Nom d'une étape sur le graphique : « Pod 2 Parois + étanchéité » plutôt que
    « Poste 2 Parois + étanchéité » ; les étapes du pod sont préfixées."""
    nom = ligne["vers"]
    if ligne["gamme"] != "pod":
        return nom
    return nom.replace("Poste ", "Pod ", 1) if nom.startswith("Poste ") else f"Pod · {nom}"


def tracer_comparaison_etapes(ax, lignes: list[dict]) -> None:
    """Durée moyenne pour atteindre chaque étape depuis la précédente : scans (en minutes
    d'usine) face à la simulation, échelle logarithmique (une maquette va bien plus vite)."""
    titre = "Durée des étapes"
    lignes = [l for l in lignes if l["reel_min"] or l["sim_min"]]
    if not any(l["reel_min"] for l in lignes):
        aucune_donnee(ax, titre, "Aucune étape mesurée par les scans :\n"
                                 "il faut au moins deux étapes scannées d'une même pièce")
        return
    rangs = np.arange(len(lignes))
    ax.set_gid(GID_BARRES_HORIZONTALES)
    for decalage, cle, couleur, libelle in ((-0.2, "reel_min", SERIES[1], "Scans (réel)"),
                                            (0.2, "sim_min", SERIES[0], "Simulation")):
        valeurs = [l[cle] or np.nan for l in lignes]
        ax.barh(rangs + decalage, valeurs, height=0.38, color=couleur, edgecolor=SURFACE,
                label=libelle)
    noms = [nom_court_etape(l) for l in lignes]
    ax.set_yticks(rangs, noms, fontsize=CORPS_ETIQUETTES_BARRES[1])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(
        lambda valeur, _position: m.formater_nombre(valeur, 0 if valeur >= 1 else 2)))
    styliser(ax, titre, xlabel="min d'usine (échelle log.)", grille="x",
             sous_titre="moyenne depuis l'étape précédente")
    legende(ax, "lower right")


class PlanJumeau(VueSchema):
    """Atelier reconstitué par les scans : même vue que le schéma de la simulation (plan, objets,
    tableau de pilotage, alertes, lecture et curseur de temps, suivi), à l'heure réelle. En mode
    « Direct », la vue suit le dernier instant ; Lecture, Début ou le curseur rejouent le passé."""

    LIBELLES = jm.LIBELLES_INDICATEURS
    MARQUEURS = MARQUEURS_JUMEAU
    VITESSES, VITESSE_DEFAUT = VITESSES_JUMEAU, VITESSE_JUMEAU_DEFAUT
    signalement = True

    def __init__(self, parent: tk.Widget, conteneur: "VueJumeau"):
        self.conteneur, self.jumeau, self.direct = conteneur, conteneur.jumeau, True
        self.anneaux = None
        super().__init__(parent, conteneur.app)
        self.cadence = m.H("logements_par_an")
        self.scenario = scenario_du_plan_jumeau(self.cadence, self.jumeau.implantation)
        self.var_suivi = tk.StringVar(value="")
        self._creer_barre_source()
        self.bouton_direct = ttk.Button(self.barre_commandes, text="", width=17,
                                        command=self.basculer_direct)
        self.bouton_direct.pack(side="left", padx=(px(self, 6), 0), after=self.bouton_lecture)
        self._afficher_direct()

    def _creer_barre_source(self) -> None:
        """Bandeau du haut, sur une ligne : serveur de scan, réinitialisation, état de la lecture
        et plan affiché. La liste « Suivre » est dans la barre du bas (place du plan préservée à la
        taille minimale de la fenêtre)."""
        barre = ttk.Frame(self, style="Page.TFrame", padding=(0, 0, 0, px(self, 6)))
        barre.pack(side="top", fill="x", before=self.haut)
        self.liste_plans = ttk.Combobox(barre, textvariable=self.conteneur.var_plan,
                                        state="readonly", width=30, font=(POLICE, 9),
                                        values=list(NOMS_COURTS_IMPLANTATIONS.values()))
        self.liste_plans.pack(side="right")
        self.liste_plans.bind("<<ComboboxSelected>>", lambda _e: self.conteneur.changer_plan())
        Infobulle(self.liste_plans, "Plan sur lequel les scans sont dessinés (les données ne "
                                    "changent pas) ; la comparaison utilise la simulation de ce "
                                    "plan.")
        ttk.Label(barre, text="Plan", style="Page.TLabel").pack(
            side="right", padx=(px(self, 10), px(self, 6)))
        ttk.Label(barre, text="Serveur de scan", style="Page.TLabel").pack(side="left")
        ttk.Entry(barre, textvariable=self.conteneur.var_adresse, width=20,
                  font=(POLICE, 9)).pack(side="left", padx=px(self, 6))
        ttk.Button(barre, text="Se connecter", command=self.conteneur.reconnecter).pack(
            side="left")
        self.bouton_vider = ttk.Button(barre, text="Réinitialiser les scans",
                                       command=self.conteneur.reinitialiser_scans)
        self.bouton_vider.pack(side="left", padx=(px(self, 6), 0))
        self.bouton_3d = ttk.Button(barre, text="Vue 3D en direct", style="Action.TButton",
                                    command=self.conteneur.ouvrir_vue_3d)
        self.bouton_3d.pack(side="left", padx=(px(self, 6), 0))
        Infobulle(self.bouton_3d, "Ouvre l'atelier en 3D dans le navigateur ; la vue suit les "
                                  "scans en direct (relue toutes les 2 s).")
        Infobulle(self.bouton_vider, "Vide la base de l'application de scan (pièces, scans, "
                                     "défauts, kanban, consignes) pour repartir de zéro. "
                                     "Une confirmation est demandée.")
        self.etat_source = tk.Label(barre, text="", bg=PAGE, fg=ENCRE_2, font=(POLICE, 9),
                                    anchor="w", justify="left")
        self.etat_source.pack(side="left", fill="x", expand=True, padx=(px(self, 10), 0))
        retour_automatique(self.etat_source)
        self._creer_liste_suivi()

    def _creer_liste_suivi(self) -> None:
        """Liste « Suivre » dans la barre du bas, à gauche de l'horloge."""
        self.liste_suivi = ttk.Combobox(self.barre_commandes, textvariable=self.var_suivi,
                                        state="readonly", width=15, font=(POLICE, 9))
        self.liste_suivi.pack(side="right", padx=(0, px(self, 8)), before=self.curseur_temps)
        self.liste_suivi.bind("<<ComboboxSelected>>", lambda _e: self.suivre(self.var_suivi.get()))
        ttk.Label(self.barre_commandes, text="Suivre", style="Page.TLabel").pack(
            side="right", padx=(px(self, 8), px(self, 4)), before=self.curseur_temps)

    # ── Source des données : le jumeau ──────────────────────────────────────────────────────

    def duree(self) -> float:
        """Du premier scan à maintenant."""
        return self.jumeau.duree(self.conteneur.maintenant())

    def horloge(self, t: float) -> str:
        """Heure réelle de l'instant t."""
        return self.jumeau.horloge(t) if self.jumeau.evenements else "Aucun scan"

    def positions(self, t: float) -> dict:
        """Pièces sur le plan à l'instant t, d'après leur dernier scan."""
        return self.jumeau.positions(t)

    def valeurs_tableau(self, t: float) -> dict[str, str]:
        """Indicateurs mesurés par les scans ; objectif à la cadence du scénario."""
        if not self.jumeau.evenements:
            return {libelle: "—" for libelle in self.LIBELLES}
        return self.jumeau.valeurs(t, self.scenario["cadence"]["modules_jour"])

    def alertes_tableau(self, t: float) -> list[dict]:
        """Défauts, blocages de lots, scans refusés et retards kanban enregistrés jusqu'à t."""
        return self.jumeau.alertes_affichees(t, NB_ALERTES)

    def _ecrire_alertes(self, alertes: list[dict]) -> None:
        """Réécrit la liste des alertes : heure du scan, zone et délai d'enregistrement."""
        self.texte_alertes.config(state="normal")
        self.texte_alertes.delete("1.0", "end")
        if not alertes:
            self.texte_alertes.insert("end", "Aucune alerte enregistrée pour l'instant.", "detail")
        for alerte in alertes:
            delai = ("—" if alerte["delai_s"] is None
                     else formater_delai(alerte["delai_s"] / sim.SECONDES_PAR_MINUTE))
            lieu = alerte["zone"] or "bureau / PC"
            self.texte_alertes.insert("end", f"⚠ {alerte['evenement']} · {alerte['code']}\n",
                                      "titre")
            self.texte_alertes.insert(
                "end", f"{lieu}, {self.jumeau.horloge_courte(alerte['t_jumeau'])} (délai {delai})"
                       f"\n{alerte['message']}\n\n", "detail")
        self.texte_alertes.config(state="disabled")

    # ── Scénario, mise à jour des données, mode direct ──────────────────────────────────────

    def scenario_change(self, scenario: dict) -> None:
        """Cadence du scénario : objectif du tableau de pilotage et épaisseur des flèches (le plan
        reste celui de l'usine unique avec extension)."""
        self.cadence = scenario["parametres"]["cadence"]
        self.plan_change()

    def plan_change(self) -> None:
        """Plan choisi ou cadence changés : fond à redessiner (les scans ne changent pas)."""
        self.scenario = scenario_du_plan_jumeau(self.cadence, self.jumeau.implantation)
        self.perime = True
        if self.winfo_ismapped():
            self.redessiner_fond()

    def donnees_changees(self) -> None:
        """Nouveaux scans (ou base vidée) : liste des pièces à suivre, puis horloge."""
        self.liste_suivi.configure(values=sorted(
            code for code, (type_affiche, _) in self.jumeau.parcours.items()
            if type_affiche in ("module", "pod")))
        if self.suivi and self.suivi not in self.jumeau.parcours:
            self.arreter_suivi()
        self.tic()

    def tic(self) -> None:
        """Chaque seconde : borne du curseur à l'heure réelle ; en direct, la vue la suit."""
        self._maj_curseur = True  # le changement de borne rappelle le curseur : pas un rejeu
        self.curseur_temps.configure(to=max(self.duree(), 1e-6))
        self._maj_curseur = False
        if self._fond is not None:
            self.aller_a(self.duree() if self.direct else self.t)

    def _afficher_direct(self) -> None:
        """Texte du bouton selon le mode."""
        self.bouton_direct.config(text="● En direct" if self.direct else "○ Revenir au direct")

    def basculer_direct(self) -> None:
        """Bouton « Direct » : retour au dernier instant, ou arrêt du suivi en temps réel."""
        self.direct = not self.direct
        if self.direct:
            self.arreter_lecture()
        self._afficher_direct()
        self.tic()

    def _quitter_direct(self) -> None:
        """Le rejeu du passé quitte le mode direct."""
        if self.direct:
            self.direct = False
            self._afficher_direct()

    def basculer_lecture(self) -> None:
        """Lecture / Pause (rejeu des scans)."""
        self._quitter_direct()
        super().basculer_lecture()

    def revenir_au_debut(self) -> None:
        """Retour au premier scan."""
        self._quitter_direct()
        super().revenir_au_debut()

    def _curseur_bouge(self, valeur: str) -> None:
        """Déplacement manuel du curseur de temps."""
        if not self._maj_curseur:
            self._quitter_direct()
        super()._curseur_bouge(valeur)

    # ── Dessin : pièces signalées et suivi ──────────────────────────────────────────────────

    def redessiner_fond(self) -> None:
        """Plan, puis artistes animés (les anneaux des pièces signalées sont recréés)."""
        self.anneaux = None
        super().redessiner_fond()

    def _dessiner_complements(self, positions: dict) -> None:
        """Anneau rouge autour des pièces en défaut ou à isoler, puis suivi."""
        if self.anneaux is None:
            self.anneaux = self.ax.scatter([], [], s=TAILLE_SIGNALEMENT, facecolors="none",
                                           edgecolors=CRITIQUE, linewidths=1.8, zorder=9,
                                           animated=True)
        points = [positions[code][:2] for code in self.jumeau.signalees(self.t)]
        self.anneaux.set_offsets(np.array(points) if points else np.empty((0, 2)))
        self.ax.draw_artist(self.anneaux)
        super()._dessiner_complements(positions)

    def suivre(self, code: str) -> None:
        """Suit une pièce (module ou pod) : trajet entre les zones scannées et halo."""
        if code not in self.jumeau.parcours:
            return
        self.suivi = code
        self.var_suivi.set(code)
        self.bandeau.pack(fill="x", pady=(0, 8), before=self.haut)
        if self.perime:
            self.redessiner_fond()
        self.aller_a(self.t)

    def arreter_suivi(self) -> None:
        """Désactive le suivi."""
        self.var_suivi.set("")
        super().arreter_suivi()

    def _objet_suivi_visible(self, positions: dict) -> str | None:
        """La pièce suivie si elle est sur le plan, sinon l'un de ses composants."""
        candidats = [self.suivi] + sorted(p["code"] for p in self.jumeau.pieces.values()
                                          if p.get("parent") == self.suivi)
        return next((code for code in candidats if code in positions), None)

    def _dessiner_suivi(self, positions: dict) -> None:
        """Trajet déjà parcouru, halo et bandeau de la pièce suivie."""
        points = self.jumeau.trace_parcourue(self.suivi, self.t)
        self.trace.set_data([p[0] for p in points], [p[1] for p in points])
        self.ax.draw_artist(self.trace)
        cible = self._objet_suivi_visible(positions)
        self.halo.set_offsets([positions[cible][:2]] if cible else np.empty((0, 2)))
        self.ax.draw_artist(self.halo)
        if cible:
            forme, couleur, _, _ = self.MARQUEURS[positions[cible][2]]
            marqueur = self.marqueurs_suivi[forme]
            marqueur.set_offsets([positions[cible][:2]])
            marqueur.set_facecolor(couleur)
            self.ax.draw_artist(marqueur)
        self._actualiser_bandeau(cible)

    def _actualiser_bandeau(self, cible: str | None) -> None:
        """Pièce suivie et dernier scan enregistré à l'instant t."""
        passes = [e for e in self.jumeau.evenements_de(self.suivi)
                  if self.jumeau.instant(e["t"]) <= self.t]
        texte = f"Suivi : {self.suivi}"
        if cible and cible != self.suivi:
            texte += f" (visible : {cible})"
        if passes:
            dernier = passes[-1]
            texte += (f" · dernier scan : {dernier['evenement']} ({dernier['code']}, "
                      f"{dernier['zone'] or 'bureau / PC'}, "
                      f"{self.jumeau.horloge_courte(self.jumeau.instant(dernier['t']))})")
        else:
            texte += " · pas encore scanné à cet instant"
        self.texte_bandeau.config(text=texte)


class ComparaisonJumeau(ttk.Frame):
    """Scans comparés à la simulation de la même usine (unique, avec extension) : tuiles,
    indicateurs globaux, durée de chaque étape (tableau et graphique)."""

    TITRES_TUILES = ("Scans enregistrés", "Modules lancés (scans)", "Période observée",
                     "Étapes en écart")

    def __init__(self, parent: tk.Widget, conteneur: "VueJumeau"):
        super().__init__(parent, style="Page.TFrame", padding=(px(parent, 12), px(parent, 8)))
        self.conteneur, self.perime = conteneur, True
        self._creer_commandes()
        self.tuiles = creer_tuiles(self, self.TITRES_TUILES)
        corps = ttk.Frame(self, style="Page.TFrame")
        corps.pack(fill="both", expand=True, pady=(px(self, 8), 0))
        self._creer_tableaux(corps)
        cadre = ttk.Frame(corps, style="Page.TFrame")
        cadre.pack(side="left", fill="both", expand=True, padx=(px(self, 10), 0))
        self.figure = Figure(figsize=TAILLE_INITIALE_COMPARAISON, facecolor=SURFACE,
                             layout="constrained")
        self.ax = self.figure.add_subplot()
        self.toile = toile(cadre, self.figure)
        self.toile.mpl_connect("draw_event", self._apres_dessin)

    def _creer_commandes(self) -> None:
        """Bouton d'actualisation et description de la simulation comparée."""
        barre = ttk.Frame(self, style="Page.TFrame")
        barre.pack(fill="x", pady=(0, px(self, 8)))
        ttk.Button(barre, text="Actualiser la comparaison", style="Action.TButton",
                   command=self.actualiser).pack(side="left")
        self.description = ttk.Label(barre, style="Reco.TLabel", justify="left")
        self.description.pack(side="left", fill="x", expand=True, padx=(px(self, 12), 0))
        retour_automatique(self.description)

    def _creer_tableaux(self, corps: ttk.Frame) -> None:
        """Indicateurs globaux (en haut) et étapes des gammes (en dessous, défilant)."""
        gauche = ttk.Frame(corps, style="Page.TFrame")
        gauche.pack(side="left", fill="y")
        gauche.pack_propagate(False)  # largeur fixée au contenu des tableaux après remplissage
        self.gauche = gauche
        cadre, self.tableau_indicateurs = arbre_avec_defilement(
            gauche, {"indicateur": "Indicateur", "reel": "Scans (réel)", "simule": "Simulation",
                     "ecart": "Écart"})
        self.tableau_indicateurs.configure(height=len(jm.INDICATEURS_COMPARES))
        cadre.pack(fill="x")
        cadre, self.tableau_etapes = arbre_avec_defilement(
            gauche, {"etape": "Étape atteinte", "mesures": "Mesures",
                     "reel": "Scans (réel)", "simule": "Simulation", "ecart": "Écart"},
            arborescence=True)
        self.tableau_etapes.configure(height=LIGNES_TABLEAU_ETAPES)
        cadre.pack(fill="both", expand=True, pady=(px(self, 8), 0))

    def montrer(self) -> None:
        """L'onglet devient visible : comparaison recalculée si elle est périmée."""
        if self.perime:
            self.actualiser()

    def actualiser(self) -> None:
        """Relit les scans, puis compare à la simulation de référence (calculée au besoin)."""
        self.conteneur.lire_maintenant()
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            reference = self.conteneur.simulation_de_reference()
        finally:
            self.config(cursor="")
        jumeau = self.conteneur.jumeau
        etapes = jm.comparaison_etapes(jumeau, reference["usine"])
        indicateurs = jm.comparaison_indicateurs(jumeau, reference["resultats"])
        self._actualiser_description(reference["parametres"])
        self._actualiser_tuiles(jumeau, etapes)
        self._remplir_indicateurs(indicateurs)
        self._remplir_etapes(etapes)
        self._ajuster_largeur()
        self.ax.clear()
        tracer_comparaison_etapes(self.ax, etapes)
        self.toile.draw_idle()
        self.perime = False

    def _actualiser_description(self, p: dict) -> None:
        """Simulation comparée et échelle de temps de la maquette."""
        echelle = m.H("echelle_temps_maquette")
        self.description.config(text=(
            f"Simulation de référence : {m.formater_nombre(p['cadence'])} logements/an · usine "
            f"unique · {NOMS_COURTS_IMPLANTATIONS[p['implantation']]} · {p['techno']} · "
            f"{p['jours']} j · graine {p['graine']}. "
            f"Échelle de temps de la maquette : 1 min scannée = {formater_valeur(echelle)} min "
            "d'usine (hypothèse modifiable dans Statistiques › Paramètres)."))

    def _actualiser_tuiles(self, jumeau, etapes: list[dict]) -> None:
        """Volumes observés et nombre d'étapes en écart."""
        reels = jm.indicateurs_reels(jumeau)
        en_ecart = [l for l in etapes if l["ecart"] in ("plus lent", "plus rapide")]
        lents = sum(1 for l in en_ecart if l["ecart"] == "plus lent")
        mesurees = sum(1 for l in etapes if l["n_reel"])
        debut = jumeau.horloge(0) if jumeau.evenements else "—"
        valeurs = (
            (_f(reels["scans"]), f"{_f(len(jumeau.evenements))} événements · "
                                 f"{m.formater_pourcentage(reels['pct_refus'])} refusés"),
            (_f(reels["modules_lances"]), f"{_f(len(jumeau.instants('module', jm.EXPEDITION)))} "
                                          "expédiés"),
            (formater_delai(jumeau.duree()), f"depuis le premier scan ({debut})"),
            (f"{len(en_ecart)} / {mesurees}", f"{lents} plus lentes, {len(en_ecart) - lents} plus "
                                              "rapides que simulé (étapes mesurées)"),
        )
        for tuile, (valeur, detail) in zip(self.tuiles, valeurs):
            tuile.afficher(valeur, detail)

    def _remplir_indicateurs(self, lignes: list[dict]) -> None:
        """Tableau des indicateurs globaux."""
        self.tableau_indicateurs.delete(*self.tableau_indicateurs.get_children())
        for l in lignes:
            self.tableau_indicateurs.insert("", "end", values=(
                l["libelle"], _texte_mesure(l["reel"], l["unite"]),
                _texte_mesure(l["simule"], l["unite"]), l["ecart"]))
        ajuster_colonnes(self.tableau_indicateurs)

    def _remplir_etapes(self, lignes: list[dict]) -> None:
        """Tableau des étapes, regroupées par gamme."""
        self.tableau_etapes.delete(*self.tableau_etapes.get_children())
        parents = {gamme: self.tableau_etapes.insert("", "end", text=libelle, open=True)
                   for gamme, libelle in (("module", "Module 3D"), ("pod", "Pod salle de bain"))}
        for l in lignes:
            self.tableau_etapes.insert(parents[l["gamme"]], "end", text=l["vers"], values=(
                f"{l['n_reel']} / {l['n_sim']}", formater_delai(l["reel_min"]),
                formater_delai(l["sim_min"]), _texte_ecart(l)))
        ajuster_colonnes(self.tableau_etapes)

    def _ajuster_largeur(self) -> None:
        """La colonne des tableaux prend la largeur de leurs colonnes, barre de défilement
        comprise : ni colonne rognée, ni défilement horizontal."""
        barre = px(self, LARGEUR_BARRE_DEFILEMENT)
        self.gauche.configure(width=max(largeur_colonnes(arbre) for arbre in (
            self.tableau_indicateurs, self.tableau_etapes)) + barre)

    def _apres_dessin(self, _evenement) -> None:
        """Corps des noms des étapes adapté à la hauteur réelle des lignes."""
        if ajuster_etiquettes_barres(self.figure):
            self.toile.draw_idle()


class DialogueDecision(tk.Toplevel):
    """Boîte de dialogue d'une décision proposée par le jumeau : règle, motif, destinataires et
    consigne modifiable. L'humain tranche : Envoyer la consigne, Ignorer, ou Décider plus tard
    (la décision reste en attente dans l'onglet)."""

    def __init__(self, onglet: "OngletDecisions", decision: dict, traiter):
        super().__init__(onglet)
        self.withdraw()  # placée puis affichée une fois sa taille connue (voir _centrer)
        self.decision, self.traiter = decision, traiter
        self.title("Décision proposée par le jumeau numérique")
        self.configure(background=PAGE)
        self.transient(onglet.winfo_toplevel())
        self.resizable(False, False)
        cadre = ttk.Frame(self, style="Page.TFrame", padding=px(self, 16))
        cadre.pack(fill="both", expand=True)
        self._creer_textes(cadre, onglet.conteneur)
        self._creer_boutons(cadre)
        self.protocol("WM_DELETE_WINDOW", lambda: self.choisir(PLUS_TARD))
        self._centrer(onglet.winfo_toplevel())

    def _creer_textes(self, cadre: ttk.Frame, conteneur: "VueJumeau") -> None:
        """Règle, motif, destinataires, puis la consigne dans une zone modifiable."""
        largeur = px(self, LARGEUR_DIALOGUE)
        d = self.decision
        for texte, police, couleur, marge in (
                (f"⚠ {d['regle']}", (POLICE, 12, "bold"), ENCRE, 0),
                (d["motif"], (POLICE, 9), ENCRE_2, 4),
                ("Destinataires : "
                 + ", ".join(conteneur.nom_poste(p) for p in d["destinataires"]),
                 (POLICE, 9), ENCRE_2, 4),
                ("Consigne envoyée au téléphone des postes (modifiable) :", (POLICE, 9, "bold"),
                 ENCRE, 10)):
            tk.Label(cadre, text=texte, font=police, fg=couleur, bg=PAGE, anchor="w",
                     justify="left", wraplength=largeur).pack(fill="x", pady=(px(self, marge), 0))
        self.texte = tk.Text(cadre, height=4, wrap="word", font=(POLICE, 10), relief="solid",
                             borderwidth=1, padx=px(self, 6), pady=px(self, 4))
        chiffre = tkfont.Font(root=self, font=(POLICE, 10)).measure("0")
        self.texte.configure(width=round(largeur / chiffre))  # largeur en caractères
        self.texte.insert("1.0", d["message"])
        self.texte.pack(fill="x", pady=(px(self, 4), 0))

    def _creer_boutons(self, cadre: ttk.Frame) -> None:
        """Envoyer (action principale), Ignorer, Décider plus tard."""
        barre = ttk.Frame(cadre, style="Page.TFrame")
        barre.pack(fill="x", pady=(px(self, 12), 0))
        self.bouton_envoyer = ttk.Button(barre, text="Envoyer la consigne",
                                         style="Action.TButton",
                                         command=lambda: self.choisir(ENVOYER))
        self.bouton_envoyer.pack(side="left")
        self.bouton_ignorer = ttk.Button(barre, text="Ignorer",
                                         command=lambda: self.choisir(IGNORER))
        self.bouton_ignorer.pack(side="left", padx=px(self, 8))
        ttk.Button(barre, text="Décider plus tard", command=lambda: self.choisir(PLUS_TARD)).pack(
            side="right")

    def _centrer(self, fenetre: tk.Misc) -> None:
        """Au centre de la fenêtre principale, au premier plan."""
        self.update_idletasks()
        x = fenetre.winfo_rootx() + (fenetre.winfo_width() - self.winfo_reqwidth()) // 2
        y = fenetre.winfo_rooty() + (fenetre.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.attributes("-topmost", True)  # une décision qui attend l'humain reste visible
        self.lift()
        self.focus_set()

    def choisir(self, action: str) -> None:
        """Transmet le choix de l'humain ; la boîte se ferme s'il a été appliqué (un envoi
        impossible la laisse ouverte)."""
        if self.traiter(self.decision, action, self.texte.get("1.0", "end").strip()):
            self.destroy()


class OngletDecisions(ttk.Frame):
    """Onglet « Décisions et prévisions » du jumeau : décisions proposées (humain dans la
    boucle), fin de fabrication prévue des modules en cours (option A), détection des étapes
    anormalement lentes (option B)."""

    TITRES_TUILES = ("Décisions à valider", "Consignes envoyées", "Étapes anormalement lentes",
                     "Prochaine fin de fabrication")
    COLONNES_DECISIONS = {"heure": "Proposée à", "regle": "Règle", "statut": "Statut",
                          "destinataires": "Destinataires", "message": "Consigne"}
    COLONNES_PREVISIONS = {"module": "Module", "etape": "Dernière étape", "depuis": "Depuis",
                           "fin": "Fin prévue", "fourchette": "Fourchette p10–p90",
                           "mesures": "Mesures"}
    COLONNES_POSTES = {"etape": "Étape", "poste": "Poste", "passages": "Passages",
                       "recente": "Récente", "reference": "Référence", "rapport": "Rapport",
                       "etat": "État"}

    def __init__(self, parent: tk.Widget, conteneur: "VueJumeau"):
        super().__init__(parent, style="Page.TFrame", padding=(px(parent, 12), px(parent, 8)))
        self.conteneur, self.file, self.dialogue = conteneur, [], None
        self._creer_commandes()
        self.tuiles = creer_tuiles(self, self.TITRES_TUILES)
        corps = ttk.Frame(self, style="Page.TFrame")
        corps.pack(fill="both", expand=True, pady=(px(self, 8), 0))
        corps.columnconfigure((0, 1), weight=1, uniform="colonnes")
        corps.rowconfigure(0, weight=1)
        self._creer_decisions(corps)
        self._creer_analyse(corps)

    def _creer_commandes(self) -> None:
        """Analyser maintenant, et rappel du mode « proposer »."""
        barre = ttk.Frame(self, style="Page.TFrame")
        barre.pack(fill="x", pady=(0, px(self, 8)))
        ttk.Button(barre, text="Analyser maintenant", style="Action.TButton",
                   command=self.conteneur.analyser).pack(side="left")
        mode = ttk.Label(barre, style="Reco.TLabel", justify="left", text=(
            "Mode proposition : le jumeau propose, un humain décide. Chaque décision s'ouvre "
            "dans une boîte de dialogue ; aucune consigne ne part vers un poste sans validation."))
        mode.pack(side="left", fill="x", expand=True, padx=(px(self, 12), 0))
        retour_automatique(mode)

    def _titre(self, parent: tk.Widget, texte: str) -> None:
        """Titre d'une partie de l'onglet."""
        ttk.Label(parent, text=texte, style="Page.TLabel", font=(POLICE, 9, "bold")).pack(
            anchor="w", pady=(0, px(self, 3)))

    def _creer_decisions(self, corps: ttk.Frame) -> None:
        """Historique des décisions et bouton pour reprendre celle qui est sélectionnée."""
        gauche = ttk.Frame(corps, style="Page.TFrame")
        gauche.grid(row=0, column=0, sticky="nsew", padx=(0, px(self, 10)))
        self._titre(gauche, "Décisions proposées par le jumeau")
        ttk.Button(gauche, text="Valider ou ignorer la décision sélectionnée",
                   command=self.reprendre_selection).pack(side="bottom", anchor="w",
                                                          pady=(px(self, 6), 0))
        cadre, self.tableau_decisions = arbre_avec_defilement(gauche, self.COLONNES_DECISIONS)
        cadre.pack(fill="both", expand=True)
        self.tableau_decisions.bind("<Double-1>", lambda _e: self.reprendre_selection())
        for statut, fond in ((dc.PROPOSEE, BANDEAU_SUIVI), (dc.IGNOREE, GRILLE)):
            self.tableau_decisions.tag_configure(statut, background=fond)

    def _creer_analyse(self, corps: ttk.Frame) -> None:
        """Prévisions (option A) en haut, lenteurs par étape (option B) en dessous."""
        droite = ttk.Frame(corps, style="Page.TFrame")
        droite.grid(row=0, column=1, sticky="nsew")
        self._titre(droite, "Fin de fabrication prévue des modules en cours (option A)")
        cadre, self.tableau_previsions = arbre_avec_defilement(droite, self.COLONNES_PREVISIONS)
        self.tableau_previsions.configure(height=LIGNES_TABLEAU_PREVISIONS)
        cadre.pack(fill="x")
        self.tableau_previsions.tag_configure("retard", background=ROSE_ALERTE)
        self.validation = ttk.Label(droite, style="Reco.TLabel", justify="left")
        self.validation.pack(fill="x", pady=(px(self, 3), px(self, 8)))
        retour_automatique(self.validation)
        self._titre(droite, "Détection des étapes anormalement lentes (option B)")
        cadre, self.tableau_postes = arbre_avec_defilement(droite, self.COLONNES_POSTES)
        cadre.pack(fill="both", expand=True)
        for etat, fond in ((ana.ANORMAL, ROSE_ALERTE), (ana.A_SURVEILLER, BANDEAU_SUIVI)):
            self.tableau_postes.tag_configure(etat, background=fond)

    # ── Affichage ───────────────────────────────────────────────────────────────────────────

    def montrer(self) -> None:
        """L'onglet devient visible : analyse si elle n'a jamais été faite, puis affichage."""
        if self.conteneur.analyse is None:
            self.conteneur.analyser()
        self.actualiser()

    def actualiser(self) -> None:
        """Tuiles et tableaux à partir de la dernière analyse et de l'historique."""
        analyse = self.conteneur.analyse or ANALYSE_VIDE
        self._actualiser_tuiles(analyse)
        self._remplir_decisions()
        self._remplir_previsions(analyse["previsions"])
        self._remplir_postes(analyse["postes"])
        self.validation.config(text=texte_validation(analyse["validation"]))

    def _actualiser_tuiles(self, analyse: dict) -> None:
        """Décisions en attente et envoyées, étapes lentes, prochaine fin prévue."""
        compte = self.conteneur.decideur.compter()
        lentes = [l for l in analyse["postes"] if l["etat"] == ana.ANORMAL]
        prochaine = next((l for l in analyse["previsions"] if l["fin"] is not None), None)
        jumeau = self.conteneur.jumeau
        valeurs = (
            (_f(compte[dc.PROPOSEE]), f"{_f(compte[dc.IGNOREE])} ignorée(s) par l'humain"),
            (_f(compte[dc.ENVOYEE]), "après validation, vers les téléphones des postes"),
            (_f(len(lentes)), ", ".join(l["zone"] for l in lentes[:2]) or "aucune"),
            ((self.date_heure(prochaine["fin"]), f"{prochaine['code']} · "
              f"{_f(len(analyse['previsions']))} module(s) en cours")
             if prochaine else ("—", "aucun module en cours prévisible")),
        )
        for tuile, (valeur, detail) in zip(self.tuiles, valeurs):
            tuile.afficher(valeur, detail)

    def _remplir_decisions(self) -> None:
        """Historique, la plus récente d'abord ; décisions en attente sur fond orangé."""
        arbre, conteneur = self.tableau_decisions, self.conteneur
        arbre.delete(*arbre.get_children())
        for d in reversed(conteneur.decideur.decisions):
            heure = time.strftime("%H:%M:%S", time.localtime(d["t_proposee"]))
            arbre.insert("", "end", iid=str(d["id"]), tags=(d["statut"],), values=(
                heure, d["regle"], d["statut"],
                ", ".join(conteneur.nom_poste(p) for p in d["destinataires"]),
                d["envoye"] or d["message"]))
        ajuster_colonnes(arbre)

    def _remplir_previsions(self, previsions: list[dict]) -> None:
        """Modules en cours ; en rose ceux qui ont dépassé la durée prévue de leur étape."""
        arbre, heure = self.tableau_previsions, self.date_heure
        arbre.delete(*arbre.get_children())
        for l in previsions:
            fin = heure(l["fin"]) if l["fin"] is not None else "—"
            fourchette = (f"{heure(l['basse'])} – {heure(l['haute'])}" if l["fin"] is not None
                          else "—")
            arbre.insert("", "end", tags=("retard",) if l["en_retard"] else (), values=(
                l["code"], l["etape"], heure(l["t_etape"]), fin, fourchette, _f(l["mesures"])))
        ajuster_colonnes(arbre)

    def date_heure(self, t: float) -> str:
        """« JJ/MM HH:MM » d'un instant du jumeau (une fin prévue tombe souvent un autre jour)."""
        return f"{self.conteneur.jumeau.date(t):%d/%m %H:%M}"

    def _remplir_postes(self, lignes: list[dict]) -> None:
        """Étapes mesurées, les plus inquiétantes d'abord."""
        arbre = self.tableau_postes
        arbre.delete(*arbre.get_children())
        for l in lignes:
            rapport = (f"{m.formater_nombre(l['rapport'], 1)} ×" if l["rapport"] is not None
                       else "—")
            arbre.insert("", "end", tags=(l["etat"],), values=(
                l["etape"], l["zone"], _f(l["passages"]), ana.texte_duree(l["moyenne_recente"]),
                ana.texte_duree(l["reference"]), rapport, l["etat"]))
        ajuster_colonnes(arbre)

    # ── Décisions et boîtes de dialogue ────────────────────────────────────────────────────

    def proposer(self, decision: dict) -> None:
        """Nouvelle décision : boîte de dialogue tout de suite, ou dès que la précédente est
        fermée."""
        self.file.append(decision)
        self._ouvrir_suivante()

    def _ouvrir_suivante(self) -> None:
        """Ouvre la boîte de la prochaine décision encore en attente (une à la fois)."""
        if self.dialogue is not None and self.dialogue.winfo_exists():
            return
        self.dialogue = None
        while self.file:
            decision = self.file.pop(0)
            if decision["statut"] == dc.PROPOSEE:
                self.dialogue = DialogueDecision(self, decision, self.traiter)
                return

    def reprendre_selection(self) -> None:
        """Rouvre la boîte de dialogue de la décision sélectionnée, si elle attend encore."""
        selection = self.tableau_decisions.selection()
        decision = next((d for d in self.conteneur.decideur.decisions
                         if selection and str(d["id"]) == selection[0]), None)
        if decision is None or decision["statut"] != dc.PROPOSEE:
            messagebox.showinfo("Décisions", "Sélectionnez une décision « proposée » : les "
                                             "autres ont déjà été envoyées ou ignorées.")
            return
        self.file.insert(0, decision)
        self._ouvrir_suivante()

    def traiter(self, decision: dict, action: str, message: str) -> bool:
        """Applique le choix de l'humain ; True si la boîte de dialogue peut se fermer."""
        if action == ENVOYER and not self.conteneur.envoyer_decision(decision, message):
            return False
        if action == IGNORER:
            self.conteneur.ignorer_decision(decision)
        self.after_idle(self._apres_choix)
        return True

    def _apres_choix(self) -> None:
        """Tableaux à jour, puis la décision suivante."""
        self.actualiser()
        self._ouvrir_suivante()


ANALYSE_VIDE = {"postes": [], "previsions": [], "validation": None}


def texte_validation(validation: dict | None) -> str:
    """Précision de la prévision, mesurée sur la simulation de référence."""
    if validation is None:
        return "Précision de la prévision : simulation de référence trop courte pour la mesurer."
    return (f"Prévision validée sur la simulation de référence : erreur moyenne "
            f"{ana.texte_duree(validation['erreur_moyenne_min'])} sur la fin de fabrication, "
            f"contre {ana.texte_duree(validation['erreur_naive_min'])} pour la prévision naïve "
            f"(OF + délai moyen) ; {_f(validation['previsions'])} prévisions sur "
            f"{_f(validation['modules_testes'])} modules.")


def creer_tuiles(parent: tk.Widget, titres: tuple) -> list[Tuile]:
    """Rangée de tuiles d'indicateurs, de même largeur."""
    rangee = ttk.Frame(parent, style="Page.TFrame")
    rangee.pack(fill="x")
    tuiles = []
    for rang, (titre, (accent, fond)) in enumerate(zip(titres, TEINTES_TUILES)):
        tuile = Tuile(rangee, titre, accent, fond)
        tuile.grid(row=0, column=rang, sticky="nsew", padx=(0 if rang == 0 else px(parent, 8), 0))
        rangee.columnconfigure(rang, weight=1, uniform="tuiles")
        tuiles.append(tuile)
    return tuiles


class VueJumeau(ttk.Frame):
    """Vue 5 : jumeau numérique alimenté par les scans d'avelis_scan (serveur de scan, ou sa
    base lue directement) ; onglets « Atelier en direct », « Comparaison avec la simulation » et
    « Décisions et prévisions ». Les scans sont relus chaque seconde dans un fil d'exécution, sans
    bloquer l'interface ; l'analyse et les règles de décision tournent après chaque lecture."""

    def __init__(self, parent: tk.Widget, app: "Application"):
        super().__init__(parent, style="Page.TFrame")
        self.app, self.jumeau = app, jm.Jumeau()
        self.var_adresse = tk.StringVar(value=jm.ADRESSE_SCAN_DEFAUT)
        self.var_plan = tk.StringVar(value=NOMS_COURTS_IMPLANTATIONS[jm.IMPLANTATION_JUMEAU])
        self.source, self.source_imposee, self.base = None, None, jm.BASE_SCAN_DEFAUT
        self.reponses: queue.Queue = queue.Queue()
        self.generation, self._fil, self._apres, self.actif = 0, None, None, False
        self.etat, self.references = "", {}
        self.decideur, self.analyse, self.maintenant = dc.Decideur(), None, time.time
        self._t_analyse, self._prevues = 0.0, (None, None, None)
        self.serveur_3d, self.revision_3d = s3d.ServeurScene(), 0  # démarré au premier clic
        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill="both", expand=True, padx=px(self, 6), pady=(px(self, 6), 0))
        self.plan = PlanJumeau(self.onglets, self)
        self.onglets.add(self.plan, text="Atelier en direct (scans)")
        self.comparaison = ComparaisonJumeau(self.onglets, self)
        self.onglets.add(self.comparaison, text="Comparaison avec la simulation")
        self.decisions = OngletDecisions(self.onglets, self)
        self.onglets.add(self.decisions, text="Décisions et prévisions (IA)")
        self.onglets.bind("<<NotebookTabChanged>>", self._onglet_change)

    # ── Vue ─────────────────────────────────────────────────────────────────────────────────

    def scenario_change(self, scenario: dict) -> None:
        """Nouveau scénario : cadence du plan ; la comparaison sera recalculée."""
        self.plan.scenario_change(scenario)
        self.comparaison.perime = True

    def montrer(self) -> None:
        """La vue devient visible : lecture des scans relancée."""
        self.actif = True
        self._onglet_change()
        self._interroger()

    def cacher(self) -> None:
        """La vue est masquée : lecture suspendue, animation arrêtée."""
        self.actif = False
        if self._apres is not None:
            self.after_cancel(self._apres)
            self._apres = None
        self.plan.cacher()

    def _onglet_change(self, _evenement=None) -> None:
        """Le sous-onglet affiché est mis à jour ; l'autre est suspendu."""
        if not self.actif:
            return
        choisi = self.onglets.select()
        if choisi == str(self.plan):
            self.plan.montrer()
            self.plan.tic()
            return
        self.plan.cacher()
        (self.decisions if choisi == str(self.decisions) else self.comparaison).montrer()

    # ── Lecture des scans ───────────────────────────────────────────────────────────────────

    def changer_plan(self, implantation: str | None = None) -> None:
        """Liste « Plan affiché » (ou test) : les pièces sont redessinées sur ce plan ; la
        comparaison se fera avec la simulation de cette implantation."""
        if implantation is None:
            courts = {court: nom for nom, court in NOMS_COURTS_IMPLANTATIONS.items()}
            implantation = courts[self.var_plan.get()]
        self.var_plan.set(NOMS_COURTS_IMPLANTATIONS[implantation])
        self.jumeau.choisir_plan(implantation)
        self.publier_3d()
        self.plan.plan_change()
        self.plan.tic()
        self.comparaison.perime = True

    def utiliser_source(self, source) -> None:
        """Impose une source (tests, autre base), puis relit tout."""
        self.source_imposee = source
        self.reconnecter()

    def reconnecter(self) -> None:
        """Bouton « Se connecter » : oublie la source et les scans lus, puis relit tout."""
        self.generation += 1
        self.source = None
        self.jumeau.vider()
        self.publier_3d()
        self.analyse = None
        self.plan.donnees_changees()
        self.decisions.actualiser()
        self.comparaison.perime = True
        if self.actif:
            self.lire_maintenant()

    def reinitialiser_scans(self) -> bool:
        """Bouton « Réinitialiser les scans » : après confirmation, vide la base de scan (par le
        serveur, ou le fichier s'il n'est pas lancé), puis relit tout ; False si l'utilisateur
        renonce ou si la base n'a pas pu être vidée."""
        if not messagebox.askyesno("Réinitialiser les scans", (
                "Toute la base de l'application de scan sera effacée définitivement : pièces, "
                "scans, défauts, cartes kanban et consignes.\n\nRepartir de zéro ?"),
                icon="warning", default="no"):
            return False
        try:
            source = self.source or self._ouvrir(self.var_adresse.get())
            source.vider()
        except jm.SourceIndisponible as erreur:
            messagebox.showerror("Réinitialiser les scans", f"Base non vidée.\n\n{erreur}")
            return False
        self.reconnecter()
        self.app.var_statut.set("Scans réinitialisés : la base de scan est vide.")
        return True

    def _ouvrir(self, adresse: str):
        """Source imposée, sinon serveur de scan, sinon base en lecture seule."""
        return self.source_imposee or jm.ouvrir_source(adresse, self.base)

    def _lire(self, generation: int, source, adresse: str, depuis: int, premier) -> None:
        """Fil d'exécution (aucun appel à Tk) : lecture déposée dans la file des réponses."""
        try:
            source = source or self._ouvrir(adresse)
            self.reponses.put((generation, source, jm.lire_source(source, depuis, premier), None))
        except jm.SourceIndisponible as erreur:
            self.reponses.put((generation, None, None, str(erreur)))

    def _interroger(self) -> None:
        """Chaque seconde : réponses reçues intégrées, nouvelle lecture lancée, horloge avancée."""
        self._apres = None
        if not self.actif:
            return
        self._relever()
        if self._fil is None or not self._fil.is_alive():
            self._fil = threading.Thread(target=self._lire, daemon=True, args=(
                self.generation, self.source, self.var_adresse.get(), self.jumeau.dernier_id,
                self.jumeau.premier))
            self._fil.start()
        self.plan.tic()
        self._apres = self.after(INTERVALLE_JUMEAU_MS, self._interroger)

    def _relever(self) -> None:
        """Intègre les réponses du fil d'exécution (celles d'une ancienne source sont ignorées)."""
        while not self.reponses.empty():
            generation, source, lecture, erreur = self.reponses.get()
            if generation == self.generation:
                self._integrer(source, lecture, erreur)

    def lire_maintenant(self) -> None:
        """Lecture immédiate, dans le fil de l'interface (comparaison, tests)."""
        try:
            source = self.source or self._ouvrir(self.var_adresse.get())
            lecture = jm.lire_source(source, self.jumeau.dernier_id, self.jumeau.premier)
            self._integrer(source, lecture, None)
        except jm.SourceIndisponible as erreur:
            self._integrer(None, None, str(erreur))

    def _integrer(self, source, lecture: dict | None, erreur: str | None) -> None:
        """Applique une lecture (ou son échec) au jumeau et aux deux onglets."""
        if erreur is not None:
            self.source = None
            self._afficher_etat(f"Aucune source de scans : {erreur}", CRITIQUE)
            return
        self.source = source
        nouveaux = self.jumeau.appliquer(lecture) or lecture["reinitialiser"]
        if nouveaux:
            self.publier_3d()
            self.plan.donnees_changees()
            self.comparaison.perime = True
        if nouveaux or time.monotonic() - self._t_analyse >= INTERVALLE_ANALYSE_S:
            self.analyser()
        dernier = (f", dernier à {self.jumeau.horloge_courte(self.jumeau.duree())}"
                   if self.jumeau.evenements else "")
        nom = getattr(source, "nom", "source imposée")
        self._afficher_etat(f"● Scans lus : {nom} · {_f(len(self.jumeau.evenements))} "
                            f"événements{dernier}", BON)

    def _afficher_etat(self, texte: str, couleur: str) -> None:
        """État de la lecture, dans le bandeau du plan."""
        self.etat = texte
        self.plan.etat_source.config(text=texte, fg=couleur)

    # ── Vue 3D en direct ────────────────────────────────────────────────────────────────────

    def ouvrir_vue_3d(self) -> str | None:
        """Bouton « Vue 3D en direct » : publie la scène du jumeau et ouvre la vue 3D, qui la
        relit ensuite d'elle-même ; renvoie l'adresse, ou None (avec un message) si la vue
        n'est pas construite."""
        try:
            self.serveur_3d.demarrer()
        except FileNotFoundError as erreur:
            messagebox.showerror("Vue 3D", str(erreur))
            return None
        self.publier_3d()
        adresse = f"http://{s3d.HOTE_LOCAL}:{self.serveur_3d.port}/{s3d.PAGE_PAR_DEFAUT}"
        if not webbrowser.open(adresse):
            messagebox.showinfo("Vue 3D", f"Ouvrez cette adresse dans un navigateur :\n{adresse}")
        self.app.var_statut.set("Vue 3D du jumeau ouverte dans le navigateur, en direct.")
        return adresse

    def publier_3d(self) -> None:
        """Nouvelle révision de la scène du jumeau, si la vue 3D a été ouverte."""
        if self.serveur_3d.port is None:
            return
        self.revision_3d += 1
        self.serveur_3d.publier(s3d.scene_jumeau(self.jumeau, self.plan.cadence,
                                                 self.maintenant(), self.revision_3d))

    # ── Analyse et décisions (humain dans la boucle) ───────────────────────────────────────

    def analyser(self) -> list[dict]:
        """Lenteurs par étape (option B), fins de fabrication prévues (option A), puis règles de
        décision ; chaque nouvelle décision ouvre une boîte de dialogue. Renvoie les nouvelles."""
        self._t_analyse = time.monotonic()
        if not self.jumeau.evenements:
            self.analyse = dict(ANALYSE_VIDE)
            self.decisions.actualiser()
            return []
        prevues, validation = self.durees_prevues()
        maintenant = self.maintenant()
        postes = ana.analyser_postes(self.jumeau, prevues)
        self.analyse = {"postes": postes, "validation": validation, "previsions":
                        ana.prevoir_fins(self.jumeau, prevues, self.jumeau.instant(maintenant))}
        nouvelles = self.decideur.evaluer(self.jumeau, maintenant,
                                          self.plan.scenario["cadence"]["modules_jour"], prevues,
                                          postes)
        self.decisions.actualiser()
        for decision in nouvelles:
            self.decisions.proposer(decision)
        return nouvelles

    def durees_prevues(self) -> tuple[dict, dict | None]:
        """Durées simulées par étape et précision de la prévision, calculées une fois par
        simulation de référence et par échelle de temps de la maquette."""
        usine = self.simulation_de_reference()["usine"]
        cle = (id(usine), m.H("echelle_temps_maquette"))
        if self._prevues[0] != cle:
            self._prevues = (cle, ana.durees_prevues(usine), ana.evaluer_prevision(usine))
        return self._prevues[1], self._prevues[2]

    def nom_poste(self, poste: str) -> str:
        """Nom lisible d'un poste de l'application de scan : sa zone et son identifiant."""
        if poste == dc.POSTE_BUREAU:
            return "Bureaux / pilotage"
        zone = next((e["zone"] for e in reversed(self.jumeau.evenements)
                     if e["poste"] == poste and e["zone"]), "")
        return f"{zone} ({poste})" if zone else poste

    def envoyer_decision(self, decision: dict, message: str) -> bool:
        """Envoie la consigne validée par l'humain ; message d'erreur et False si la source ne
        peut pas l'envoyer (serveur de scan arrêté)."""
        try:
            source = self.source or self._ouvrir(self.var_adresse.get())
            self.decideur.envoyer(decision, source, self.maintenant(), message)
        except jm.SourceIndisponible as erreur:
            messagebox.showerror("Décision non envoyée", (
                f"La consigne n'a pas pu être envoyée.\n\n{erreur}\n\nLancez le serveur de scan "
                "(avelis_scan) : les consignes passent par lui pour arriver sur les téléphones."))
            return False
        self.app.var_statut.set(f"Consigne envoyée : {decision['regle']}.")
        return True

    def ignorer_decision(self, decision: dict) -> None:
        """L'humain ne donne pas suite à la décision."""
        self.decideur.ignorer(decision, self.maintenant())

    # ── Simulation de référence ─────────────────────────────────────────────────────────────

    def simulation_de_reference(self) -> dict:
        """Simulation de l'usine du jumeau (unique, plan affiché, QR code), aux cadence,
        durée et graine du scénario courant ; celle du scénario si elle convient déjà. Les
        simulations calculées sont gardées tant que les paramètres (onglet Paramètres) ne
        changent pas."""
        p = self.app.scenario["parametres"]
        implantation = self.jumeau.implantation
        if (p["implantation"], p["schema"], p["techno"]) == (implantation, jm.SCHEMA_JUMEAU,
                                                            sim.QR):
            return self.app.scenario
        cle = (p["cadence"], p["jours"], p["graine"], repr(m.etat_parametres()), implantation)
        if cle not in self.references:
            self.references = {k: v for k, v in self.references.items() if k[3] == cle[3]}
            self.references[cle] = calculer_scenario(p["cadence"], implantation,
                                                     jm.SCHEMA_JUMEAU, sim.QR, p["jours"],
                                                     p["graine"])
        return self.references[cle]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Fenêtre principale
# ═════════════════════════════════════════════════════════════════════════════════════════════

def charger_logo(widget, nom: str, hauteur: int | None) -> ImageTk.PhotoImage | None:
    """Image du dossier ressources/ réduite à `hauteur` px logiques (TAILLE_ICONE px pour
    l'icône, hauteur None) ; None si le fichier est absent ou illisible."""
    try:
        image = Image.open(DOSSIER_RESSOURCES / nom)
        image.load()
    except (OSError, ValueError):
        return None
    cible = TAILLE_ICONE if hauteur is None else px(widget, hauteur)
    largeur = max(1, round(image.width * cible / image.height))
    return ImageTk.PhotoImage(image.resize((largeur, cible), Image.LANCZOS), master=widget)


class Application(tk.Tk):
    """En-tête, barre latérale (paramètres, navigation, exports) et quatre vues."""

    def __init__(self, echelle: float | None = None):
        super().__init__()
        if echelle is not None:  # tests : simule un écran réglé à une autre mise à l'échelle
            self.tk.call("tk", "scaling", echelle * PIXELS_PAR_POUCE / POINTS_PAR_POUCE)
        self.title("Avelis · Flux logistiques et données")
        self._dimensionner_fenetre()
        self.configure(background=PAGE)
        configurer_styles(self)
        self._creer_variables()
        self._creer_entete()
        corps = ttk.Frame(self, style="Page.TFrame")
        corps.pack(fill="both", expand=True)
        self._creer_barre_laterale(corps)
        contenu = ttk.Frame(corps, style="Page.TFrame")
        contenu.pack(side="left", fill="both", expand=True)
        self.vues = {1: VueStatistiques(contenu, self), 2: VueSchema(contenu, self),
                     3: VueTracabilite(contenu, self), 5: VueJumeau(contenu, self)}
        self.scenario, self.vue_active = None, None
        self.serveur_3d = s3d.ServeurScene()  # démarré au premier clic sur « 4 Vue 3D »
        self.protocol("WM_DELETE_WINDOW", self.fermer)
        self.recalculer()
        self.afficher_vue(1)

    def _dimensionner_fenetre(self) -> None:
        """Taille souhaitée, centrée, si l'écran la contient ; sinon fenêtre agrandie (écran
        portable, mise à l'échelle de 125 ou 150 %)."""
        x0, y0, largeur_zone, hauteur_zone = zone_de_travail(self)
        marge_x, marge_y = (px(self, cote) for cote in MARGE_CADRE_FENETRE)
        self.minsize(min(px(self, TAILLE_MINIMALE[0]), largeur_zone - marge_x),
                     min(px(self, TAILLE_MINIMALE[1]), hauteur_zone - marge_y))
        largeur, hauteur = (px(self, cote) for cote in TAILLE_FENETRE)
        if largeur + marge_x <= largeur_zone and hauteur + marge_y <= hauteur_zone:
            x = x0 + (largeur_zone - largeur - marge_x) // 2
            y = y0 + (hauteur_zone - hauteur - marge_y) // 2
            self.geometry(f"{largeur}x{hauteur}+{x}+{y}")
            return
        # taille « normale » = zone de travail : « Restaurer » ne dépasse pas l'écran
        self.geometry(f"{largeur_zone - marge_x}x{hauteur_zone - marge_y}+{x0}+{y0}")
        try:
            self.state("zoomed")
        except tk.TclError:  # hors Windows : la zone de travail suffit
            pass

    def _creer_variables(self) -> None:
        """Variables Tk des paramètres du scénario."""
        self.var_cadence = tk.IntVar(value=m.H("logements_par_an"))
        self.var_cadence_texte = tk.StringVar(value=_f(m.H("logements_par_an")))
        self.var_implantation = tk.StringVar(value=m.IMPLANTATION_PROPOSEE)
        self.var_schema = tk.StringVar(value="unique")
        self.var_techno = tk.StringVar(value=sim.RFID)
        self.var_jours = tk.StringVar(value="10")
        self.var_graine = tk.StringVar(value="42")
        self.var_statut = tk.StringVar(value="")

    def _creer_entete(self) -> None:
        """Bandeau bleu marine : logo de l'équipe, titre, sous-titre, résumé du scénario, logo
        Avelis s'il est fourni."""
        entete = tk.Frame(self, bg=MARINE)
        entete.pack(fill="x")
        self._logos = {nom: charger_logo(self, nom, hauteur) for nom, hauteur in (
            (LOGO_EQUIPE, HAUTEUR_LOGO_EQUIPE), (LOGO_AVELIS, HAUTEUR_LOGO_AVELIS),
            (ICONE_FENETRE, None))}
        if self._logos[ICONE_FENETRE] is not None:
            self.iconphoto(True, self._logos[ICONE_FENETRE])
        if self._logos[LOGO_EQUIPE] is not None:
            tk.Label(entete, image=self._logos[LOGO_EQUIPE], bg=MARINE, bd=0).pack(
                side="left", padx=(px(self, 14), px(self, 10)), pady=px(self, 3))
            tk.Frame(entete, bg=MARINE_CLAIR, width=px(self, 2)).pack(
                side="left", fill="y", pady=px(self, 9))
        tk.Label(entete, text="Avelis · Flux logistiques et données", bg=MARINE, fg="white",
                 font=(POLICE, 17, "bold")).pack(side="left", padx=(px(self, 12), px(self, 12)),
                                                 pady=px(self, 9))
        if self._logos[LOGO_AVELIS] is not None:
            tk.Label(entete, image=self._logos[LOGO_AVELIS], bg="white", bd=0,
                     padx=px(self, MARGE_LOGO_AVELIS), pady=px(self, MARGE_LOGO_AVELIS)).pack(
                side="right", padx=(0, px(self, 14)))
        tk.Label(entete, text="Toutes les valeurs estimées sont des HYPOTHÈSES", bg=MARINE,
                 fg=MARINE_TEXTE, font=(POLICE, 11)).pack(side="left",
                                                          pady=(px(self, 14), px(self, 8)))
        self.etiquette_scenario = tk.Label(entete, text="", bg=MARINE, fg=MARINE_TEXTE,
                                           font=(POLICE, 9), justify="right")
        self.etiquette_scenario.pack(side="right", padx=px(self, 18))

    def _section(self, parent: tk.Widget, titre: str) -> None:
        """Titre de section de la barre latérale."""
        ttk.Label(parent, text=titre, style="Barre.TLabel").pack(
            anchor="w", pady=(px(self, 3), px(self, 1)))

    def _creer_barre_laterale(self, parent: tk.Widget) -> None:
        """Paramètres du scénario, navigation entre les vues et exports."""
        barre = ttk.Frame(parent, style="Barre.TFrame", width=px(self, LARGEUR_BARRE_LATERALE),
                          padding=(px(self, 14), px(self, 2), px(self, 14), px(self, 8)))
        barre.pack(side="left", fill="y")
        barre.pack_propagate(False)
        statut = ttk.Label(barre, textvariable=self.var_statut, style="Statut.TLabel",
                           justify="left")
        statut.pack(side="bottom", fill="x")  # empaqueté d'abord : sa place est garantie
        retour_automatique(statut)
        self._creer_parametres(barre)
        ttk.Button(barre, text="Recalculer le scénario", style="Action.TButton",
                   command=self.recalculer).pack(fill="x", pady=(px(self, 5), px(self, 4)))
        self.boutons_vues = {}
        for numero, libelle in ((1, "1   Statistiques"), (2, "2   Schéma de l'usine et flux"),
                                (3, "3   Traçabilité d'un module")):
            self.boutons_vues[numero] = ttk.Button(barre, text=libelle, style="Nav.TButton",
                                                   command=lambda n=numero: self.afficher_vue(n))
            self.boutons_vues[numero].pack(fill="x", pady=px(self, 1))
        self.bouton_vue_3d = ttk.Button(barre, text="4   Vue 3D (navigateur)", style="Nav.TButton",
                                        command=self.ouvrir_vue_3d)
        self.bouton_vue_3d.pack(fill="x", pady=px(self, 1))
        self.boutons_vues[5] = ttk.Button(barre, text="5   Jumeau numérique (scans)",
                                          style="Nav.TButton",
                                          command=lambda: self.afficher_vue(5))
        self.boutons_vues[5].pack(fill="x", pady=px(self, 1))
        self._creer_exports(barre)

    def _creer_parametres(self, barre: ttk.Frame) -> None:
        """Cadence, implantation, schéma, technologie, jours simulés et graine."""
        self._section(barre, "Cadence (logements/an)")
        ligne = ttk.Frame(barre, style="Barre.TFrame")
        ligne.pack(fill="x")
        self.curseur_cadence = ttk.Scale(ligne, from_=CADENCE_MIN, to=CADENCE_MAX,
                                         orient="horizontal", command=self._cadence_bougee)
        self.curseur_cadence.set(self.var_cadence.get())
        self.curseur_cadence.pack(side="left", fill="x", expand=True)
        ttk.Label(ligne, textvariable=self.var_cadence_texte, style="Valeur.TLabel", width=6,
                  anchor="e").pack(side="left")
        self._section(barre, "Implantation")
        ttk.Combobox(barre, textvariable=self.var_implantation, values=list(m.IMPLANTATIONS),
                     state="readonly", font=(POLICE, 9)).pack(fill="x")
        self._section(barre, "Schéma industriel")
        for valeur, libelle in LIBELLES_SCHEMAS.items():
            ttk.Radiobutton(barre, text=libelle, value=valeur, variable=self.var_schema,
                            style="Barre.TRadiobutton").pack(anchor="w")
        self._section(barre, "Technologie de traçabilité")
        ttk.Combobox(barre, textvariable=self.var_techno, values=list(sim.TECHNOLOGIES),
                     state="readonly", font=(POLICE, 9)).pack(fill="x")
        ligne = ttk.Frame(barre, style="Barre.TFrame")
        ligne.pack(fill="x", pady=(px(self, 6), 0))
        for colonne, (libelle, variable, bornes, largeur) in enumerate(
                (("Jours simulés", self.var_jours, (JOURS_MIN, JOURS_MAX), 3),
                 ("Graine", self.var_graine, (0, GRAINE_MAX), 7))):
            ttk.Label(ligne, text=libelle, style="Barre.TLabel").grid(
                row=0, column=2 * colonne, sticky="w", padx=(px(self, 10) if colonne else 0,
                                                             px(self, 4)))
            ttk.Spinbox(ligne, textvariable=variable, from_=bornes[0], to=bornes[1],
                        width=largeur).grid(row=0, column=2 * colonne + 1, sticky="w")

    def _creer_exports(self, barre: ttk.Frame) -> None:
        """Boutons d'export ; étiquettes QR désactivées (avec info-bulle) sans qrcode."""
        self._section(barre, "Exports")
        for texte, commande in (("Exporter le journal (CSV ; UTF-8-sig)", self.exporter_journal),
                                ("Exporter toutes les figures (PNG 300 dpi)",
                                 self.exporter_figures)):
            ttk.Button(barre, text=texte, style="Export.TButton", command=commande).pack(
                fill="x", pady=px(self, 1))
        self.bouton_qr = ttk.Button(barre, text="Générer des étiquettes QR (PNG)",
                                    style="Export.TButton", command=self.generer_qr)
        self.bouton_qr.pack(fill="x", pady=px(self, 1))
        if qrcode is None:
            self.bouton_qr.state(["disabled"])
            Infobulle(self.bouton_qr, "Module « qrcode » absent : installez-le avec\n"
                                      "py -3 -m pip install qrcode[pil]")

    def _cadence_bougee(self, valeur: str) -> None:
        """Curseur de cadence : valeur arrondie au pas de 50."""
        cadence = int(round(float(valeur) / CADENCE_PAS) * CADENCE_PAS)
        self.var_cadence.set(cadence)
        self.var_cadence_texte.set(_f(cadence))

    def appliquer_parametres(self, cadence: int | None = None, implantation: str | None = None,
                             schema: str | None = None, techno: str | None = None,
                             jours: int | None = None, graine: int | None = None) -> None:
        """Positionne les contrôles de la barre latérale (utilisé par les tests)."""
        if cadence is not None:
            self.curseur_cadence.set(cadence)
            self._cadence_bougee(str(cadence))
        for variable, valeur in ((self.var_implantation, implantation),
                                 (self.var_schema, schema), (self.var_techno, techno),
                                 (self.var_jours, jours), (self.var_graine, graine)):
            if valeur is not None:
                variable.set(str(valeur))

    def lire_parametres(self) -> dict | None:
        """Paramètres saisis et validés ; message d'erreur et None si une saisie est invalide."""
        try:
            jours, graine = int(self.var_jours.get()), int(self.var_graine.get())
        except ValueError:
            messagebox.showerror("Saisie invalide",
                                 "Jours simulés et graine : des nombres entiers sont attendus.")
            return None
        if not JOURS_MIN <= jours <= JOURS_MAX:
            messagebox.showerror("Saisie invalide",
                                 f"Jours simulés : entre {JOURS_MIN} et {JOURS_MAX}.")
            return None
        return {"cadence": self.var_cadence.get(), "implantation": self.var_implantation.get(),
                "schema": self.var_schema.get(), "techno": self.var_techno.get(),
                "jours": jours, "graine": graine}

    def recalculer(self) -> bool:
        """Applique les paramètres de l'onglet « Paramètres », recalcule le scénario et met à
        jour les trois vues ; False si une saisie est refusée ou si le calcul échoue."""
        parametres = self.lire_parametres()
        if parametres is None:
            return False
        precedents = m.etat_parametres()
        if not self.vues[1].parametres.appliquer():
            return False
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.scenario = calculer_scenario(**parametres)
        except Exception as erreur:  # combinaison de paramètres que le calcul ne supporte pas
            m.appliquer_parametres(**precedents)
            self.vues[1].parametres.rafraichir()
            messagebox.showerror("Calcul impossible", (
                "Le scénario n'a pas pu être calculé avec ces paramètres : les précédents sont "
                "rétablis (vos saisies restent à corriger).\n\n"
                f"{type(erreur).__name__} : {erreur}"))
            return False
        finally:
            self.config(cursor="")
        self.etiquette_scenario.config(text=resume_scenario(parametres))
        for vue in self.vues.values():
            vue.scenario_change(self.scenario)
        r = self.scenario["resultats"]
        self.var_statut.set(f"Scénario calculé : {r['lances']} modules lancés, "
                            f"{r['expedies']} expédiés en {parametres['jours']} jours simulés.")
        return True

    def afficher_vue(self, numero: int) -> None:
        """Affiche la vue demandée ; son bouton passe en orange."""
        if self.vue_active is not None:
            self.vues[self.vue_active].cacher()
            self.vues[self.vue_active].pack_forget()
        self.vue_active = numero
        self.vues[numero].pack(fill="both", expand=True)
        self.update_idletasks()
        self.vues[numero].montrer()
        for n, bouton in self.boutons_vues.items():
            bouton.configure(style="NavActif.TButton" if n == numero else "Nav.TButton")

    def exporter_journal(self) -> str | None:
        """Export CSV du journal, dans le fichier choisi par l'utilisateur."""
        DOSSIER_EXPORTS.mkdir(parents=True, exist_ok=True)
        p = self.scenario["parametres"]
        nom = f"journal_{p['cadence']}_{p['schema']}_{p['graine']}.csv"
        chemin = filedialog.asksaveasfilename(title="Exporter le journal",
                                              initialdir=str(DOSSIER_EXPORTS), initialfile=nom,
                                              defaultextension=".csv",
                                              filetypes=[("CSV", "*.csv")])
        if not chemin:
            return None
        lignes = exporter_journal_csv(self.scenario["usine"], chemin)
        messagebox.showinfo("Export du journal", f"{lignes} événements exportés dans\n{chemin}")
        return chemin

    def instant_schema_export(self) -> float:
        """Instant du schéma exporté : celui du curseur de la vue 2, ou le milieu de la simulation
        si le curseur est resté au début (le site serait presque vide à J1 06:00)."""
        return self.vues[2].t or self.scenario["usine"].duree / 2

    def ouvrir_vue_3d(self) -> str | None:
        """Publie la scène du scénario courant et ouvre la vue 3D dans le navigateur, au même
        instant que le schéma exporté ; renvoie l'adresse, ou None (avec un message) si la vue
        n'est pas construite."""
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.serveur_3d.demarrer()
            self.serveur_3d.publier(s3d.scene_3d(self.scenario["usine"]))
        except FileNotFoundError as erreur:
            messagebox.showerror("Vue 3D", str(erreur))
            return None
        finally:
            self.config(cursor="")
        instant = self.instant_schema_export()
        adresse = self.serveur_3d.adresse(instant)
        if not webbrowser.open(adresse):
            messagebox.showinfo("Vue 3D", f"Ouvrez cette adresse dans un navigateur :\n{adresse}")
        self.var_statut.set(f"Vue 3D ouverte dans le navigateur, à {sim.horloge(instant)}.")
        return adresse

    def exporter_figures(self) -> list[pathlib.Path]:
        """Export PNG 300 dpi de toutes les figures dans exports/."""
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            chemins = exporter_figures(self.scenario, DOSSIER_EXPORTS,
                                       self.instant_schema_export())
        finally:
            self.config(cursor="")
        messagebox.showinfo("Export des figures", f"{len(chemins)} figures PNG ({DPI_EXPORT} dpi)"
                                                  f" exportées dans\n{DOSSIER_EXPORTS}")
        return chemins

    def generer_qr(self) -> list[pathlib.Path]:
        """Étiquettes QR des modules expédiés et de leurs pods, dans exports/etiquettes_qr."""
        if qrcode is None:
            messagebox.showwarning("Étiquettes QR", "Le module qrcode n'est pas installé.")
            return []
        dossier = DOSSIER_EXPORTS / "etiquettes_qr"
        chemins = generer_etiquettes_qr(self.scenario["usine"], dossier)
        messagebox.showinfo("Étiquettes QR",
                            f"{len(chemins)} étiquettes PNG créées dans\n{dossier}")
        return chemins

    def fermer(self) -> None:
        """Arrête les animations, la lecture des scans et le serveur de la vue 3D, puis ferme la
        fenêtre."""
        self.vues[2].arreter_lecture()
        self.vues[5].cacher()
        self.serveur_3d.arreter()
        self.vues[5].serveur_3d.arreter()
        self.destroy()


if __name__ == "__main__":
    Application().mainloop()
