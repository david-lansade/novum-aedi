"""Tests de l'interface (SPEC §5) : combinaisons, mise en page, captures, exports, vue 3D,
jumeau numérique (alimenté par un atelier de scan de test, en mémoire).

    py -3 avelis_flux/tests_interface.py            # 36 combinaisons × 3 vues, captures, exports
    py -3 avelis_flux/tests_interface.py --rapide   # 4 combinaisons (pendant le développement)

La fenêtre s'ouvre réellement (pas de xvfb sous Windows) : root.update(), puis capture avec
PIL.ImageGrab dans captures/. Les exceptions des callbacks Tk sont interceptées par
report_callback_exception : zéro erreur exigée. Chaque écran est aussi contrôlé
automatiquement : aucun widget masqué faute de place, aucun texte tronqué ou hors de la
fenêtre, aucune figure rognée, aucun texte de figure qui en recouvre un autre ; à trois tailles
d'écran (taille par défaut, taille minimale, écran à 100 % simulé).
"""

import csv
import ctypes
import itertools
import json
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
import urllib.error
import urllib.request
from tkinter import ttk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import ImageGrab

import analyse_jumeau as ana
import app as application
import decisions as dc
import jumeau as jm
import modele as m
import scene_3d as s3d
import simulation as sim

DOSSIER_CAPTURES = application.DOSSIER_PROJET / "captures"
CADENCES_TEST = (600, 1500, 2400)  # SPEC §5.2
COMBINAISONS_RAPIDES = (
    (m.IMPLANTATION_PROPOSEE, "unique", sim.RFID, 1500),
    (m.IMPLANTATION_ACTUELLE, "satellites", sim.PAPIER, 600),
    (m.IMPLANTATION_PROPOSEE, "satellites", sim.QR, 2400),
    (m.IMPLANTATION_ACTUELLE, "unique", sim.QR, 1500),
    (m.IMPLANTATION_OPTIMISEE, "unique", sim.QR, 1500),
)
SCENARIOS_CAPTURES = (
    ("cadence2400_satellites", (2400, m.IMPLANTATION_PROPOSEE, "satellites", sim.QR, 10, 42)),
    ("actuelle", (1500, m.IMPLANTATION_ACTUELLE, "unique", sim.PAPIER, 10, 42)),
)
IMAGES_ANIMATION = 6
PAS_ANIMATION_MIN = 75  # minutes simulées entre deux images testées
ONGLETS_VUE_1 = ("tableau", "graphiques", "reseau", "parametres")
ECRANS_PAR_PARCOURS = len(ONGLETS_VUE_1) + 6  # + schéma, traçabilité, suivi, jumeau (3 onglets)
ATTENTE_LECTURE_S = 5  # lecture des scans par le fil d'exécution du jumeau
ES_CONTINUOUS, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000002  # SetThreadExecutionState (Windows)
ESSAIS_CAPTURE, ATTENTE_CAPTURE_S = 3, 1.0
DELAI_REQUETE_S = 5  # requêtes au serveur local de la vue 3D
SCENARIO_VUE_3D = (600, m.IMPLANTATION_ACTUELLE, "satellites", sim.PAPIER, 10, 42)
CLASSES_TEXTE = {"Label", "TLabel", "Button", "TButton", "Checkbutton", "TCheckbutton",
                 "Radiobutton", "TRadiobutton"}
GESTIONNAIRES = {"pack", "grid", "place"}  # pas « notebook » ni « canvas » (onglets, défilement)
TOLERANCE_PX = 1
MARGE_TEXTE_PX = 4  # px logiques : place minimale autour d'une valeur de liste ou de colonne
DEFAUTS_AFFICHES = 12
# (nom, mise à l'échelle simulée, taille cliente forcée en px logiques) ; None : valeur réelle
TAILLES_ECRAN = (("defaut", None, None), ("minimale", None, application.TAILLE_MINIMALE),
                 ("ecran_100", 1.0, None))
captures_noires: list[str] = []


def garder_ecran_allume(actif: bool) -> None:
    """Empêche l'extinction de l'affichage pendant les tests (sinon ImageGrab capture du noir) ;
    sans effet sur une session verrouillée."""
    try:
        etat = ES_CONTINUOUS | (ES_DISPLAY_REQUIRED if actif else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(etat)
    except AttributeError:  # hors Windows
        pass


class ErreursTk:
    """Remplace report_callback_exception : chaque exception de callback est enregistrée."""

    def __init__(self, racine):
        self.erreurs: list[str] = []
        racine.report_callback_exception = self.enregistrer

    def enregistrer(self, type_exception, valeur, trace) -> None:
        """Enregistre l'exception au lieu de l'afficher dans la console."""
        self.erreurs.append("".join(traceback.format_exception(type_exception, valeur, trace)))


class Dialogues:
    """Remplace filedialog et messagebox par des fonctions de test qui mémorisent les appels."""

    def __init__(self, chemin_csv, reponse: bool = True):
        self.chemin_csv, self.messages, self.reponse = str(chemin_csv), [], reponse
        self.originaux = (application.filedialog.asksaveasfilename,
                          application.messagebox.showinfo, application.messagebox.showerror,
                          application.messagebox.showwarning, application.messagebox.askyesno)

    def __enter__(self):
        application.filedialog.asksaveasfilename = lambda **options: self.chemin_csv
        for nom in ("showinfo", "showerror", "showwarning"):
            setattr(application.messagebox, nom,
                    lambda titre, texte, nom=nom: self.messages.append((nom, titre, texte)))
        application.messagebox.askyesno = self.demander
        return self

    def demander(self, titre, texte, **_options) -> bool:
        """Question oui / non : mémorisée, réponse fixée par le test."""
        self.messages.append(("askyesno", titre, texte))
        return self.reponse

    def __exit__(self, *exception):
        (application.filedialog.asksaveasfilename, application.messagebox.showinfo,
         application.messagebox.showerror, application.messagebox.showwarning,
         application.messagebox.askyesno) = self.originaux


class Navigateur:
    """Remplace webbrowser.open : mémorise les adresses au lieu d'ouvrir le navigateur."""

    def __init__(self):
        self.adresses: list[str] = []
        self.original = application.webbrowser.open

    def ouvrir(self, adresse: str, *_options) -> bool:
        """Mémorise l'adresse ; True, comme un navigateur qui s'est ouvert."""
        self.adresses.append(adresse)
        return True

    def __enter__(self):
        application.webbrowser.open = self.ouvrir
        return self

    def __exit__(self, *exception):
        application.webbrowser.open = self.original


def lire_adresse(adresse: str) -> tuple[int, bytes]:
    """(code, corps) de la réponse du serveur local, sans proxy ; code 0 si la connexion est
    refusée."""
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with ouvreur.open(adresse, timeout=DELAI_REQUETE_S) as reponse:
            return reponse.status, reponse.read()
    except urllib.error.HTTPError as erreur:
        return erreur.code, b""
    except urllib.error.URLError:
        return 0, b""


def pomper(racine, tours: int = 3) -> None:
    """Laisse Tk traiter ses événements en attente."""
    for _ in range(tours):
        racine.update_idletasks()
        racine.update()


def capturer(widget, nom: str):
    """Capture d'écran d'un widget (bbox calculée à partir de winfo_root*) dans captures/.
    Une capture entièrement noire (écran éteint ou session verrouillée) est refaite, puis
    signalée si elle le reste."""
    fenetre = widget.winfo_toplevel()
    for _ in range(ESSAIS_CAPTURE):
        fenetre.deiconify()  # fenêtre réduite ou masquée : coordonnées hors écran, capture noire
        fenetre.lift()
        fenetre.attributes("-topmost", True)
        pomper(fenetre, 2)
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        bbox = (x, y, x + widget.winfo_width(), y + widget.winfo_height())
        image = ImageGrab.grab(bbox=bbox)
        if image.convert("L").getextrema()[1] > 0:
            break
        time.sleep(ATTENTE_CAPTURE_S)
    else:
        captures_noires.append(f"{nom} (bbox {bbox}, état {fenetre.state()})")
    chemin = DOSSIER_CAPTURES / f"{nom}.png"
    image.save(chemin)
    return chemin


def animer(app, images: int = IMAGES_ANIMATION, depuis_maintenant: bool = False) -> None:
    """Fait avancer l'animation de la vue 2 de quelques images (depuis J2 13:30, ou depuis
    l'instant courant, par exemple l'OF d'un module suivi)."""
    vue = app.vues[2]
    if not depuis_maintenant:
        vue.aller_a(sim.minutes_jour() * 1.3)
    for _ in range(images):
        vue.aller_a(vue.t + PAS_ANIMATION_MIN)
        pomper(app, 1)
    vue.lecture = True
    vue.image_suivante()  # une image par la boucle réelle (after + after_idle)
    pomper(app, 2)
    vue.arreter_lecture()


def verifier_graphiques_a_jour(app) -> None:
    """Les graphiques de la vue 1 montrent le scénario courant : la ligne d'objectif du premier
    graphique vaut l'objectif journalier simulé (et non celui d'un scénario précédent)."""
    objectif = app.scenario["resultats"]["objectif_jour"]
    # lecture par figure.axes : ne touche pas au conteneur d'axes de la vue (un itérateur numpy
    # indexé ici serait réarmé, ce qui masquerait justement le défaut recherché)
    premier_axe = app.vues[1].figure_graphiques.axes[0]
    lignes = [ligne for ligne in premier_axe.get_lines()
              if ligne.get_label().startswith("Objectif")]
    assert lignes and abs(lignes[0].get_ydata()[0] - objectif) < 1e-9, (
        f"graphiques périmés : objectif tracé {lignes[0].get_ydata()[0] if lignes else '—'}, "
        f"attendu {objectif}")


def descendants(widget):
    """Tous les widgets sous `widget`, en profondeur d'abord."""
    for enfant in widget.winfo_children():
        yield enfant
        yield from descendants(enfant)


def decrire(widget) -> str:
    """Classe, texte et chemin Tk d'un widget, pour les messages d'échec."""
    texte = ""
    for option in ("text", "textvariable"):
        try:
            valeur = str(widget.cget(option))
            texte = widget.getvar(valeur) if option == "textvariable" and valeur else valeur
        except tk.TclError:
            continue
        if texte:
            break
    return f"{widget.winfo_class()} « {str(texte)[:45]} » ({widget})"


def hauteur_ligne_texte(zone) -> int:
    """Hauteur d'au moins deux lignes d'une zone de texte (marges internes comprises) : en
    dessous, ses alertes ou consignes sont illisibles."""
    police = tkfont.Font(root=zone, font=zone.cget("font"))
    return 2 * police.metrics("linespace") + 2 * int(zone.cget("pady"))


def defauts_widgets(app) -> list[str]:
    """Widgets masqués faute de place, textes tronqués ou sortant de la fenêtre, zones de texte
    écrasées."""
    defauts = []
    gauche, haut = app.winfo_rootx(), app.winfo_rooty()
    droite, bas = gauche + app.winfo_width(), haut + app.winfo_height()
    for widget in descendants(app):
        if widget.winfo_manager() not in GESTIONNAIRES or not widget.master.winfo_viewable():
            continue  # retiré volontairement (pack_forget, grid_remove) ou parent caché
        if not widget.winfo_ismapped():
            defauts.append(f"masqué faute de place : {decrire(widget)}")
            continue
        if widget.winfo_class() == "Text" and widget.winfo_height() < hauteur_ligne_texte(widget):
            defauts.append(f"zone de texte écrasée ({widget.winfo_height()} px) : "
                           f"{decrire(widget)}")
        if widget.winfo_class() not in CLASSES_TEXTE:
            continue
        largeur, hauteur = widget.winfo_width(), widget.winfo_height()
        if (largeur + TOLERANCE_PX < widget.winfo_reqwidth()
                or hauteur + TOLERANCE_PX < widget.winfo_reqheight()):
            defauts.append(f"texte tronqué ({largeur} × {hauteur} px pour "
                           f"{widget.winfo_reqwidth()} × {widget.winfo_reqheight()}) : "
                           f"{decrire(widget)}")
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        if x < gauche or y < haut or x + largeur > droite or y + hauteur > bas:
            defauts.append(f"hors de la fenêtre : {decrire(widget)}")
    return defauts


def defauts_listes(app) -> list[str]:
    """Listes déroulantes et listes visibles trop étroites pour l'une de leurs valeurs."""
    defauts = []
    marge = application.px(app, MARGE_TEXTE_PX)
    for widget in descendants(app):
        classe = widget.winfo_class()
        if classe not in ("TCombobox", "Listbox") or not widget.winfo_viewable():
            continue
        police = tkfont.Font(root=app, font=widget.cget("font") or "TkTextFont")
        if classe == "TCombobox":  # la flèche, à droite, est à peu près carrée
            valeurs = widget.cget("values") or (widget.get(),)
            place = widget.winfo_width() - widget.winfo_height()
        else:
            valeurs, place = widget.get(0, "end"), widget.winfo_width()
        defauts += [f"valeur tronquée « {valeur} » : {decrire(widget)}" for valeur in valeurs
                    if police.measure(valeur) + marge > place]
    return defauts


def elements(arbre, parent: str = "", profondeur: int = 0):
    """(élément, profondeur) de toutes les lignes d'un Treeview."""
    for element in arbre.get_children(parent):
        yield element, profondeur
        yield from elements(arbre, element, profondeur + 1)


def largeur_necessaire(arbre, colonne: str, police, gras) -> int:
    """Largeur du titre ou du contenu le plus large d'une colonne (retrait compris pour #0)."""
    retrait = int(float(ttk.Style(arbre).lookup("Treeview", "indent") or 0))
    besoin = gras.measure(arbre.heading(colonne, "text"))
    for element, profondeur in elements(arbre):
        if colonne == "#0":
            besoin = max(besoin, police.measure(arbre.item(element, "text"))
                         + retrait * (profondeur + 1))
        else:
            besoin = max(besoin, police.measure(arbre.set(element, colonne)))
    return besoin


def defauts_colonnes(app) -> list[str]:
    """Colonnes de tableaux visibles trop étroites pour leur titre ou leur contenu."""
    defauts = []
    style = ttk.Style(app)
    police = tkfont.Font(root=app, font=style.lookup("Treeview", "font"))
    gras = tkfont.Font(root=app, font=style.lookup("Treeview.Heading", "font"))
    marge = application.px(app, MARGE_TEXTE_PX)
    for arbre in descendants(app):
        if arbre.winfo_class() != "Treeview" or not arbre.winfo_viewable():
            continue
        colonnes = application.colonnes_affichees(arbre)
        for colonne in colonnes:
            besoin, largeur = largeur_necessaire(arbre, colonne, police, gras), arbre.column(
                colonne, "width")
            if largeur < besoin + marge:
                defauts.append(f"colonne « {arbre.heading(colonne, 'text')} » de {largeur} px "
                               f"pour un contenu de {besoin} px ({arbre})")
    return defauts


def graduations_dessinees(ax) -> list:
    """Étiquettes des graduations réellement dessinées : axes visibles, et valeur comprise dans
    les limites de l'axe (matplotlib prépare aussi des graduations au-delà, sans les dessiner)."""
    if not ax.axison:
        return []
    etiquettes = []
    for rang, (limites, liste) in enumerate(((ax.get_xlim(), ax.get_xticklabels()),
                                             (ax.get_ylim(), ax.get_yticklabels()))):
        bas, haut = sorted(limites)
        marge = (haut - bas) * 1e-6
        etiquettes += [texte for texte in liste
                       if bas - marge <= texte.get_position()[rang] <= haut + marge]
    return etiquettes


def textes_qui_se_chevauchent(figure) -> list[str]:
    """Titres, étiquettes, graduations, annotations et légendes d'une figure qui se recouvrent ou
    sortent de la figure (mesurés après un dessin complet)."""
    figure.canvas.draw()
    rendu = figure.canvas.get_renderer()
    boites = []
    for ax in figure.axes:
        for texte in (ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label,
                      *ax.texts, *graduations_dessinees(ax)):
            if texte.get_visible() and texte.get_text().strip():
                boites.append((texte.get_text(), texte.get_window_extent(rendu)))
        if ax.get_legend() is not None:
            boites.append(("légende", ax.get_legend().get_window_extent(rendu)))
    boites += [("légende de la figure", legende.get_window_extent(rendu))
               for legende in figure.legends]
    cadre = figure.bbox
    defauts = [f"« {texte[:35]} » sort de la figure" for texte, boite in boites
               if boite.x0 < cadre.x0 - TOLERANCE_PX or boite.x1 > cadre.x1 + TOLERANCE_PX
               or boite.y0 < cadre.y0 - TOLERANCE_PX or boite.y1 > cadre.y1 + TOLERANCE_PX]
    for (texte_a, a), (texte_b, b) in itertools.combinations(boites, 2):
        if (min(a.x1, b.x1) - max(a.x0, b.x0) > TOLERANCE_PX
                and min(a.y1, b.y1) - max(a.y0, b.y0) > TOLERANCE_PX):
            defauts.append(f"« {texte_a[:35]} » recouvre « {texte_b[:35]} »")
    return defauts


def defauts_figures(app) -> list[str]:
    """Figures affichées qui n'ont pas la taille de leur cadre (rognées ou trop petites), ou dont
    des textes se chevauchent."""
    defauts = []
    toiles = {"graphiques": app.vues[1].toile_graphiques, "réseau": app.vues[1].toile_reseau,
              "schéma": app.vues[2].toile, "jumeau": app.vues[5].plan.toile,
              "comparaison": app.vues[5].comparaison.toile}
    for nom, toile in toiles.items():
        widget = toile.get_tk_widget()
        if not widget.winfo_viewable():
            continue
        largeur, hauteur = round(toile.figure.bbox.width), round(toile.figure.bbox.height)
        if (abs(largeur - widget.winfo_width()) > TOLERANCE_PX
                or abs(hauteur - widget.winfo_height()) > TOLERANCE_PX):
            defauts.append(f"figure {nom} de {largeur} × {hauteur} px dans un cadre de "
                           f"{widget.winfo_width()} × {widget.winfo_height()} px")
        defauts += [f"figure {nom} : {defaut}" for defaut in textes_qui_se_chevauchent(
            toile.figure)]
    return defauts


def defauts_mise_en_page(app) -> list[str]:
    """Tous les défauts de mise en page de l'écran affiché."""
    return defauts_widgets(app) + defauts_listes(app) + defauts_colonnes(app) + defauts_figures(
        app)


def brancher_atelier_de_test(app) -> tuple:
    """Le jumeau lit un atelier de scan de test (en mémoire) au lieu du serveur de scan ;
    renvoie (base, horloge, codes du module expédié, codes du module en défaut)."""
    atelier = jm._atelier_de_test()
    app.vues[5].utiliser_source(atelier[0])
    return atelier


def parcourir_jumeau(app, observer_ecran) -> None:
    """Vue 5 : atelier en direct (pièce suivie), puis comparaison avec la simulation."""
    vue = app.vues[5]
    if vue.source_imposee is None:
        brancher_atelier_de_test(app)
    app.afficher_vue(5)
    vue.onglets.select(0)
    pomper(app)
    vue.lire_maintenant()
    vue.plan.suivre(sorted(vue.plan.liste_suivi.cget("values"))[0])
    pomper(app)
    observer_ecran("vue5_jumeau")
    vue.plan.arreter_suivi()
    vue.onglets.select(1)
    pomper(app)
    observer_ecran("vue5_comparaison")
    vue.onglets.select(2)
    pomper(app)
    assert vue.decisions.dialogue is None, "décision proposée sur l'atelier de test de la veille"
    observer_ecran("vue5_decisions")
    vue.onglets.select(0)


def parcourir_vues(app, observer=None) -> None:
    """Affiche les quatre vues (et les quatre onglets de la vue 1, les deux du jumeau), anime la
    vue 2, active puis arrête le mode suivi ; `observer(app, écran)` est appelé sur chaque écran
    (capture, contrôle de mise en page)."""
    def observer_ecran(ecran: str) -> None:
        if observer is not None:
            observer(app, ecran)

    app.afficher_vue(1)
    verifier_graphiques_a_jour(app)
    for rang, onglet in enumerate(ONGLETS_VUE_1):
        app.vues[1].onglets.select(rang)
        pomper(app)
        observer_ecran(f"vue1_{onglet}")
    app.afficher_vue(2)
    pomper(app)
    animer(app)
    observer_ecran("vue2_schema")
    app.afficher_vue(3)
    pomper(app)
    observer_ecran("vue3_tracabilite")
    app.vues[3].suivre_module()
    pomper(app)
    animer(app, 8, depuis_maintenant=True)
    assert app.vue_active == 2 and app.vues[2].suivi, "mode suivi non activé"
    observer_ecran("vue2_suivi")
    app.vues[2].arreter_suivi()
    parcourir_jumeau(app, observer_ecran)


def controle_mise_en_page(defauts: list[str], prefixe_captures: str | None = None):
    """Observateur de parcourir_vues : défauts de chaque écran ajoutés à `defauts`, capture de
    chaque écran si un préfixe est donné."""
    def observer(app, ecran: str) -> None:
        defauts.extend(f"{ecran} : {defaut}" for defaut in defauts_mise_en_page(app))
        if prefixe_captures:
            capturer(app, f"{prefixe_captures}_{ecran}")
    return observer


def afficher_defauts(defauts: list[str]) -> None:
    """Les premiers défauts, indentés sous la ligne de résultat."""
    for defaut in defauts[:DEFAUTS_AFFICHES]:
        print(f"      {defaut}")
    if len(defauts) > DEFAUTS_AFFICHES:
        print(f"      … et {len(defauts) - DEFAUTS_AFFICHES} autre(s)")


def tester_combinaisons(app, combinaisons, erreurs: ErreursTk) -> list[str]:
    """Chaque combinaison : paramètres, recalcul, trois vues contrôlées ; renvoie les échecs."""
    echecs = []
    for rang, (implantation, schema, techno, cadence) in enumerate(combinaisons, 1):
        libelle = (f"{rang:02d} {application.NOMS_COURTS_IMPLANTATIONS[implantation]} · {schema}"
                   f" · {techno} · {cadence}")
        avant, debut, defauts = len(erreurs.erreurs), time.perf_counter(), []
        try:
            app.appliquer_parametres(cadence, implantation, schema, techno, 10, 42)
            assert app.recalculer(), "recalcul refusé"
            parcourir_vues(app, controle_mise_en_page(defauts))
        except Exception:  # noqa: BLE001 — on veut le bilan de toutes les combinaisons
            erreurs.erreurs.append(traceback.format_exc())
        nouvelles = len(erreurs.erreurs) - avant
        etat = "✓" if nouvelles == 0 and not defauts else (
            f"✗ ({nouvelles} erreur(s), {len(defauts)} défaut(s) de mise en page)")
        print(f"  {etat} {libelle} ({time.perf_counter() - debut:.1f} s)")
        afficher_defauts(defauts)
        if nouvelles or defauts:
            echecs.append(libelle)
    return echecs


def tester_mise_en_page() -> list[str]:
    """À chaque taille d'écran, aucun défaut de mise en page sur les sept écrans ; captures
    captures/mise_en_page_<taille>_<écran>.png."""
    echecs = []
    for nom, echelle, taille in TAILLES_ECRAN:
        app = application.Application(echelle=echelle)
        erreurs = ErreursTk(app)
        if taille is not None:
            app.state("normal")
            app.geometry("{}x{}+0+0".format(*(application.px(app, cote) for cote in taille)))
        pomper(app, 5)
        defauts = []
        try:
            parcourir_vues(app, controle_mise_en_page(defauts, f"mise_en_page_{nom}"))
        except Exception:  # noqa: BLE001
            erreurs.erreurs.append(traceback.format_exc())
        facteur = app.winfo_fpixels("1i") / application.PIXELS_PAR_POUCE
        largeur, hauteur = app.winfo_width(), app.winfo_height()
        app.fermer()
        defauts += erreurs.erreurs
        print(f"  {'✓' if not defauts else '✗'} {nom} : {largeur} × {hauteur} px, soit "
              f"{largeur / facteur:.0f} × {hauteur / facteur:.0f} px à 100 % (×{facteur:.2f}), "
              f"{len(defauts)} défaut(s)")
        afficher_defauts(defauts)
        if defauts:
            echecs.append(f"mise en page {nom}")
    return echecs


def tester_simulation_courte(app, erreurs: ErreursTk) -> list[str]:
    """Un seul jour simulé : aucun module expédié (premier convoi à 1,6 j), ratios absents ;
    les trois vues et le mode suivi doivent rester utilisables (point de vigilance n° 4)."""
    avant = len(erreurs.erreurs)
    try:
        app.appliquer_parametres(1500, m.IMPLANTATION_PROPOSEE, "unique", sim.PAPIER, 1, 42)
        assert app.recalculer(), "recalcul refusé"
        assert app.scenario["resultats"]["expedies"] == 0, "un module expédié en un jour ?"
        parcourir_vues(app)
        assert app.vues[1].tuiles[0].valeur.cget("text") == "—", "taux d'atteinte affiché"
    except Exception:  # noqa: BLE001
        erreurs.erreurs.append(traceback.format_exc())
    reussi = len(erreurs.erreurs) == avant
    print(f"  {'✓' if reussi else '✗'} un jour simulé : vues, suivi et tuiles « — » sans erreur")
    app.var_jours.set("10")
    return [] if reussi else ["simulation d'un jour"]


def tester_exports(app) -> list[str]:
    """Exports CSV, figures et étiquettes QR avec boîtes de dialogue remplacées."""
    echecs = []
    app.vues[2].aller_a(0.0)  # curseur au début : le schéma exporté ne doit pas être vide
    instant = app.instant_schema_export()
    reussi = 0 < instant <= app.scenario["usine"].duree
    print(f"  {'✓' if reussi else '✗'} schéma exporté à {sim.horloge(instant)}, "
          "même curseur au début")
    if not reussi:
        echecs.append("instant du schéma exporté")
    chemin_csv = DOSSIER_CAPTURES / "test_journal.csv"
    with Dialogues(chemin_csv) as dialogues:
        app.exporter_journal()
        figures = app.exporter_figures()
        etiquettes = app.generer_qr()
    with open(chemin_csv, encoding="utf-8-sig", newline="") as fichier:
        lignes = list(csv.reader(fichier, delimiter=";"))
    textes = {cellule for ligne in lignes for cellule in ligne}
    chevauchements = []
    for nom, figure in application.figures_a_exporter(app.scenario, instant).items():
        FigureCanvasAgg(figure)  # moteur de rendu pour mesurer les textes
        chevauchements += [f"{nom} : {defaut}" for defaut in textes_qui_se_chevauchent(figure)]
    controles = (
        ("CSV présent avec en-tête", lignes and tuple(lignes[0]) == application.COLONNES_CSV),
        ("CSV : une ligne par événement",
         len(lignes) - 1 == len(app.scenario["usine"].tracabilite.journal)),
        ("CSV relu avec les accents", {"Entrée stock PF", "Réception"} <= textes),
        ("11 figures PNG présentes", len(figures) == 11 and all(f.exists() for f in figures)),
        ("étiquettes QR présentes", bool(etiquettes) and all(e.exists() for e in etiquettes)),
        ("trois messages de confirmation", len(dialogues.messages) == 3),
        ("figures exportées sans textes qui se chevauchent", not chevauchements),
    )
    for libelle, reussi in controles:
        print(f"  {'✓' if reussi else '✗'} {libelle}")
        if not reussi:
            echecs.append(libelle)
    afficher_defauts(chevauchements)
    return echecs


def tester_saisie_invalide(app) -> list[str]:
    """Jours simulés non numériques ou hors bornes : recalcul refusé, message d'erreur."""
    echecs = []
    for jours in ("abc", "0", "999"):
        with Dialogues(DOSSIER_CAPTURES / "inutile.csv") as dialogues:
            app.var_jours.set(jours)
            refuse = app.recalculer() is False
        reussi = refuse and dialogues.messages and dialogues.messages[0][0] == "showerror"
        print(f"  {'✓' if reussi else '✗'} saisie « {jours} » refusée avec un message")
        if not reussi:
            echecs.append(f"saisie {jours}")
    app.var_jours.set("10")
    return echecs


def decalage_horizontal(app, onglet) -> bool:
    """Flèche droite puis Maj + molette vers le haut : le tableau des hypothèses va à droite,
    puis revient à gauche (s'il est plus large que la fenêtre)."""
    app.vues[1].onglets.select(onglet)
    arbre = onglet.arbre_hypotheses
    pomper(app)
    if arbre.xview() == (0.0, 1.0):
        return True  # tout tient en largeur : rien à décaler
    arbre.xview_moveto(0)
    arbre.focus_force()  # la flèche va au widget qui a le focus clavier
    pomper(app)
    arbre.event_generate("<Right>")
    a_droite = arbre.xview()[0] > 0
    arbre.event_generate("<Shift-MouseWheel>", delta=120)
    return a_droite and arbre.xview()[0] < 1e-9


def tester_parametres(app) -> list[str]:
    """Onglet « Paramètres » : saisies refusées, hypothèse et réseau appliqués au recalcul,
    brouillon invalide refusé avec un message, retour aux valeurs par défaut."""
    onglet, controles = app.vues[1].parametres, []
    controles.append(("taux > 1 et entier décimal refusés",
                      onglet.saisir_hypothese("trs", "1,4") is not None
                      and onglet.saisir_hypothese("jours_ouvres", "220,5") is not None))
    onglet.saisir_hypothese("trs", "0,75")
    onglet.ville.set("Toulouse")
    onglet.ajouter("satellites")
    controles.append(("hypothèse et usine satellite appliquées au recalcul",
                      app.recalculer() and m.H("trs") == 0.75 and "Toulouse" in m.SATELLITES))
    onglet.ajouter("chantiers")  # parts à 105 % : refusé, valeurs en vigueur inchangées
    with Dialogues(DOSSIER_CAPTURES / "inutile.csv") as dialogues:
        refuse = app.recalculer() is False
    controles.append(("parts à 105 % refusées avec un message",
                      refuse and dialogues.messages and dialogues.messages[0][0] == "showerror"
                      and "Toulouse" not in m.CHANTIERS))
    controles.append(("tableau décalé à droite puis à gauche", decalage_horizontal(app, onglet)))
    onglet.tout_retablir()
    controles.append(("valeurs par défaut rétablies",
                      app.recalculer() and m.etat_parametres() == m.parametres_par_defaut()))
    for libelle, reussi in controles:
        print(f"  {'✓' if reussi else '✗'} {libelle}")
    return [libelle for libelle, reussi in controles if not reussi]


def tester_sans_qrcode() -> list[str]:
    """Sans le module qrcode : bouton désactivé, fiche affichant l'identifiant en texte."""
    original, application.qrcode = application.qrcode, None
    try:
        app = application.Application()
        erreurs = ErreursTk(app)
        pomper(app)
        app.afficher_vue(3)
        pomper(app)
        desactive = app.bouton_qr.instate(["disabled"])
        texte_seul = "QR code indisponible" in app.vues[3].texte_qr.cget("text")
        app.fermer()
    finally:
        application.qrcode = original
    echecs = [libelle for libelle, reussi in (("bouton QR désactivé", desactive),
                                               ("identifiant en texte", texte_seul),
                                               ("aucune erreur Tk", not erreurs.erreurs))
              if not reussi]
    print(f"  {'✓' if not echecs else '✗'} sans qrcode : bouton désactivé, QR remplacé par "
          "l'identifiant")
    return echecs


def scene_servie(adresse: str) -> dict:
    """Scène servie à côté de la page ouverte à `adresse`."""
    code, corps = lire_adresse(adresse.split("?")[0].rsplit("/", 1)[0] + "/scene.json")
    assert code == 200, f"scene.json : code {code}"
    return json.loads(corps.decode("utf-8"))


def ouvrir_vue_3d(app, navigateur: Navigateur) -> tuple[str, dict]:
    """Clic sur « 4 Vue 3D » ; adresse ouverte et scène servie."""
    app.bouton_vue_3d.invoke()
    pomper(app)
    assert navigateur.adresses, "navigateur non ouvert"
    return navigateur.adresses[-1], scene_servie(navigateur.adresses[-1])


def controles_vue_3d(app, navigateur: Navigateur, dialogues: Dialogues) -> list[tuple]:
    """(libellé, réussi) des contrôles du bouton « 4 Vue 3D » (navigateur et dialogues
    remplacés)."""
    app.vues[2].aller_a(sim.minutes_jour() * 1.4)
    adresse, scene = ouvrir_vue_3d(app, navigateur)
    usine, port = app.scenario["usine"], app.serveur_3d.port
    defauts = defauts_mise_en_page(app)  # message de la barre latérale changé
    afficher_defauts(defauts)
    controles = [
        ("bouton « 4 Vue 3D » visible", app.bouton_vue_3d.winfo_ismapped()),
        ("navigateur ouvert à l'instant du curseur de la vue 2",
         adresse == app.serveur_3d.adresse(app.vues[2].t)),
        ("page servie", lire_adresse(adresse)[0] == 200),
        ("scène du scénario courant", scene["scenario"] == app.scenario["parametres"]
         and len(scene["objets"]) == len(usine.timelines())),
        ("mise en page sans défaut après l'ouverture", not defauts),
    ]
    app.appliquer_parametres(*SCENARIO_VUE_3D)
    app.recalculer()
    _, scene = ouvrir_vue_3d(app, navigateur)
    controles.append(("autre scénario : nouvelle scène, même serveur",
                      scene["scenario"]["cadence"] == SCENARIO_VUE_3D[0]
                      and app.serveur_3d.port == port))
    dossier, ouvertures = app.serveur_3d.dossier, len(navigateur.adresses)
    app.serveur_3d.dossier = DOSSIER_CAPTURES / "dist_absent"
    try:
        refusee = app.ouvrir_vue_3d() is None
    finally:
        app.serveur_3d.dossier = dossier
    dernier = dialogues.messages[-1] if dialogues.messages else ("", "", "")
    controles.append(("dist/ absent : message clair, navigateur non ouvert",
                      refusee and len(navigateur.adresses) == ouvertures
                      and dernier[0] == "showerror" and "npm run build" in dernier[2]))
    return controles


def tester_vue_3d() -> list[str]:
    """Bouton « 4 Vue 3D » : scène du scénario courant servie, navigateur ouvert à l'instant de
    la vue 2, message si dist/ manque, serveur arrêté à la fermeture."""
    app = application.Application()
    erreurs = ErreursTk(app)
    pomper(app)
    controles = []
    try:
        with Navigateur() as navigateur, Dialogues(DOSSIER_CAPTURES / "inutile.csv") as dialogues:
            controles = controles_vue_3d(app, navigateur, dialogues)
    except Exception:  # noqa: BLE001
        erreurs.erreurs.append(traceback.format_exc())
    port = app.serveur_3d.port
    app.fermer()
    controles += [("serveur arrêté à la fermeture",
                   port is not None and lire_adresse(f"http://{s3d.HOTE_LOCAL}:{port}/")[0] == 0),
                  ("aucune erreur Tk", not erreurs.erreurs)]
    for libelle, reussi in controles:
        print(f"  {'✓' if reussi else '✗'} {libelle}")
    for erreur in erreurs.erreurs:
        print(erreur)
    return [libelle for libelle, reussi in controles if not reussi]


def attendre(app, condition, delai_s: float = ATTENTE_LECTURE_S) -> bool:
    """Laisse tourner Tk jusqu'à ce que la condition soit vraie (ou le délai écoulé)."""
    fin = time.perf_counter() + delai_s
    while time.perf_counter() < fin:
        pomper(app, 1)
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def controles_jumeau(app) -> list[tuple]:
    """(libellé, réussi) des contrôles de la vue 5, alimentée par un atelier de test."""
    base, horloge, m1, m2 = brancher_atelier_de_test(app)
    vue, plan = app.vues[5], app.vues[5].plan
    app.afficher_vue(5)
    pomper(app)
    controles = [
        ("tous les scans lus", attendre(app, lambda: len(vue.jumeau.evenements)
                                        == len(base.evenements(0, 10_000)))),
        ("en direct : dernier instant", plan.direct and abs(plan.t - plan.duree()) < 1),
        ("pod en défaut sur la ligne pods, signalé", m2[1] in plan.positions(plan.t)
         and m2[1] in vue.jumeau.signalees(plan.t)),
        ("défaut dans les alertes", "Défaut déclaré" in plan.texte_alertes.get("1.0", "end")),
    ]
    plan.revenir_au_debut()
    controles.append(("« Début » quitte le direct", not plan.direct and plan.t == 0))
    plan.basculer_direct()
    avant = len(vue.jumeau.evenements)
    jm._scanner(base, horloge, base.creer_module_complet(avec_composants=False)[0], "bureau")
    controles.append(("nouveau scan lu en direct (fil d'exécution)",
                      attendre(app, lambda: len(vue.jumeau.evenements) == avant + 5)))
    base.vider()
    base.creer_lot("FOUR-B")
    controles.append(("base vidée : tout relu", attendre(app, lambda: len(vue.jumeau.evenements)
                                                         == 1)))
    return (controles + controles_plan(app) + controles_reinitialisation(app)
            + controles_decisions(app) + controles_comparaison(app))


def dialogue_ouvert(vue):
    """Boîte de dialogue de décision ouverte, ou None."""
    dialogue = vue.decisions.dialogue
    return dialogue if dialogue is not None and dialogue.winfo_exists() else None


def controles_decisions(app) -> list[tuple]:
    """Onglet « Décisions et prévisions » sur un atelier dont le poste 2 ralentit : décision
    proposée dans une boîte de dialogue, rien envoyé sans l'humain, envoi du message modifié,
    les suivantes ignorées ; puis fins de fabrication prévues et leur précision."""
    base, horloge, pods = ana.atelier_poste_lent()
    vue = app.vues[5]
    vue.maintenant = lambda: horloge[0]
    try:
        vue.utiliser_source(base)
        vue.onglets.select(2)
        pomper(app)
        dialogue = dialogue_ouvert(vue)
        controles = [("décision proposée dans une boîte de dialogue, rien envoyé sans l'humain",
                      dialogue is not None and dialogue.decision["regle"] == dc.REGLE_LENT
                      and not base.consignes())]
        dialogue.texte.delete("1.0", "end")
        dialogue.texte.insert("1.0", "Consigne validée par le chef d'atelier")
        dialogue.bouton_envoyer.invoke()
        pomper(app)
        controles.append(("consigne envoyée au poste 2 et au bureau après validation",
                          {(c["poste"], c["message"]) for c in base.consignes()} >= {
                              ("pod_2", "Consigne validée par le chef d'atelier"),
                              ("bureau", "Consigne validée par le chef d'atelier")}))
        while dialogue_ouvert(vue) is not None:
            dialogue_ouvert(vue).bouton_ignorer.invoke()
            pomper(app)
        etats = [vue.decisions.tableau_postes.set(ligne, "etat")
                 for ligne in vue.decisions.tableau_postes.get_children()]
        controles += [("décisions suivantes ignorées, aucune en attente",
                       not vue.decideur.en_attente() and vue.decideur.compter()[dc.IGNOREE]),
                      ("étape anormalement lente signalée (option B)", etats[0] == ana.ANORMAL)]
    finally:
        vue.maintenant = time.time
    brancher_atelier_de_test(app)
    vue.analyser()
    pomper(app)
    controles.append(("fin de fabrication prévue d'un module en cours et précision (option A)",
                      vue.decisions.tableau_previsions.get_children()
                      and "erreur moyenne" in vue.decisions.validation.cget("text")
                      and dialogue_ouvert(vue) is None))
    vue.onglets.select(0)
    return controles


def controles_plan(app) -> list[tuple]:
    """Liste « Plan affiché » : mêmes scans, pièces redessinées dans les zones du plan choisi,
    comparaison avec la simulation de ce plan ; retour au plan par défaut."""
    base, *_ = brancher_atelier_de_test(app)
    vue = app.vues[5]
    vue.lire_maintenant()
    nombre, t = len(vue.jumeau.evenements), vue.plan.t
    vue.changer_plan(m.IMPLANTATION_OPTIMISEE)
    pomper(app)
    zones = m.IMPLANTATIONS[m.IMPLANTATION_OPTIMISEE]["zones"]
    dans_zone = all(any(z[0] <= x <= z[0] + z[2] and z[1] <= y <= z[1] + z[3]
                        for z in zones.values())
                    for x, y, _ in vue.plan.positions(t).values())
    controles = [
        ("plan optimisé : mêmes scans, pièces dans ses zones",
         len(vue.jumeau.evenements) == nombre and vue.plan.positions(t) and dans_zone
         and vue.plan.scenario["parametres"]["implantation"] == m.IMPLANTATION_OPTIMISEE),
        ("plan optimisé : comparaison avec la simulation de ce plan",
         vue.simulation_de_reference()["parametres"]["implantation"]
         == m.IMPLANTATION_OPTIMISEE),
    ]
    vue.changer_plan(jm.IMPLANTATION_JUMEAU)
    return controles


def controles_reinitialisation(app) -> list[tuple]:
    """Bouton « Réinitialiser les scans » : rien sans confirmation, base vide avec."""
    base, *_ = brancher_atelier_de_test(app)
    vue = app.vues[5]
    with Dialogues(DOSSIER_CAPTURES / "inutile.csv", reponse=False) as dialogues:
        vue.plan.bouton_vider.invoke()
    controles = [("réinitialisation : confirmation demandée, rien effacé si « non »",
                  dialogues.messages[0][0] == "askyesno" and base.evenements(0, 1)
                  and vue.jumeau.evenements)]
    with Dialogues(DOSSIER_CAPTURES / "inutile.csv", reponse=True):
        vue.plan.bouton_vider.invoke()
    pomper(app)
    controles.append(("réinitialisation : base de scan et jumeau vides si « oui »",
                      not base.evenements(0, 1) and not base.pieces()
                      and not vue.jumeau.evenements and not vue.plan.positions(0)))
    return controles


def controles_comparaison(app) -> list[tuple]:
    """Comparaison avec la simulation, puis source indisponible."""
    vue = app.vues[5]
    brancher_atelier_de_test(app)
    vue.onglets.select(1)
    pomper(app)
    etapes = vue.comparaison.tableau_etapes
    lignes = sum(len(etapes.get_children(parent)) for parent in etapes.get_children())
    controles = [
        ("comparaison : toutes les étapes des gammes", lignes == len(jm.comparaison_etapes(
            vue.jumeau, vue.simulation_de_reference()["usine"]))),
        ("comparaison : indicateurs", len(vue.comparaison.tableau_indicateurs.get_children())
         == len(jm.INDICATEURS_COMPARES)),
        ("comparaison : simulation de l'usine unique avec extension",
         vue.simulation_de_reference()["parametres"]["implantation"] == jm.IMPLANTATION_JUMEAU),
    ]
    vue.onglets.select(0)
    vue.source_imposee, base = None, vue.base
    vue.base = DOSSIER_CAPTURES / "absente.db"
    vue.var_adresse.set("http://127.0.0.1:9")
    try:
        vue.reconnecter()
        controles.append(("sans source : message d'erreur, aucun scan",
                          vue.etat.startswith("Aucune source") and not vue.jumeau.evenements))
    finally:
        vue.base = base
        vue.var_adresse.set(jm.ADRESSE_SCAN_DEFAUT)
    brancher_atelier_de_test(app)
    return controles


def tester_jumeau(app) -> list[str]:
    """Vue 5 : lecture des scans (directe et par le fil d'exécution), direct et rejeu, base
    vidée, comparaison, source indisponible."""
    try:
        controles = controles_jumeau(app)
    except Exception:  # noqa: BLE001
        controles = [("contrôles du jumeau sans exception", False)]
        print(traceback.format_exc())
    app.vues[5].cacher()
    for libelle, reussi in controles:
        print(f"  {'✓' if reussi else '✗'} {libelle}")
    return [libelle for libelle, reussi in controles if not reussi]


def tester_captures(app) -> list[str]:
    """Captures de chaque écran pour deux autres scénarios que celui par défaut (capturé à
    chaque taille d'écran) : cadence 2 400 avec satellites, implantation actuelle."""
    app.lift()
    app.attributes("-topmost", True)
    pomper(app, 5)
    defauts = []
    for prefixe, parametres in SCENARIOS_CAPTURES:
        app.appliquer_parametres(*parametres)
        app.recalculer()
        parcourir_vues(app, controle_mise_en_page(defauts, prefixe))
    app.attributes("-topmost", False)
    return defauts


def main() -> int:
    """Lance tous les tests d'interface ; code de sortie 0 si tout passe."""
    rapide = "--rapide" in sys.argv
    DOSSIER_CAPTURES.mkdir(parents=True, exist_ok=True)
    combinaisons = (COMBINAISONS_RAPIDES if rapide else
                    [(i, s, t, c) for i, s, t, c in itertools.product(
                        m.IMPLANTATIONS, m.SCHEMAS, sim.TECHNOLOGIES, CADENCES_TEST)])
    app = application.Application()
    erreurs = ErreursTk(app)
    pomper(app, 5)
    print(f"Combinaisons ({len(combinaisons)}) × 4 vues, animation et mode suivi :")
    echecs = tester_combinaisons(app, combinaisons, erreurs)
    print("Cas limite :")
    echecs += tester_simulation_courte(app, erreurs)
    print("Captures d'écran (deux autres scénarios) :")
    defauts = tester_captures(app)
    print(f"  {'✓' if not defauts else '✗'} {len(SCENARIOS_CAPTURES) * ECRANS_PAR_PARCOURS} "
          f"captures dans {DOSSIER_CAPTURES}, {len(defauts)} défaut(s) de mise en page")
    afficher_defauts(defauts)
    if defauts:
        echecs.append("mise en page des captures")
    print("Exports (boîtes de dialogue remplacées) :")
    echecs += tester_exports(app)
    print("Saisies invalides :")
    echecs += tester_saisie_invalide(app)
    print("Onglet Paramètres :")
    echecs += tester_parametres(app)
    print("Jumeau numérique (atelier de scan de test) :")
    echecs += tester_jumeau(app)
    app.fermer()
    print("Sans le module qrcode :")
    echecs += tester_sans_qrcode()
    print("Vue 3D (navigateur remplacé) :")
    echecs += tester_vue_3d()
    print("Mise en page à trois tailles d'écran (scénario par défaut, captures) :")
    echecs += tester_mise_en_page()
    if captures_noires:
        print(f"  ✗ captures noires (écran éteint ou verrouillé) : {', '.join(captures_noires)}")
        echecs.append("captures noires")
    for erreur in erreurs.erreurs:
        print(erreur)
    total = len(erreurs.erreurs)
    print(f"\n{total} erreur(s) Tk interceptée(s), {len(echecs)} échec(s).")
    return 0 if total == 0 and not echecs else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    garder_ecran_allume(True)
    try:
        code = main()
    finally:
        garder_ecran_allume(False)
    sys.exit(code)
