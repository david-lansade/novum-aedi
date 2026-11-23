"""Prépare les logos de l'en-tête à partir du logo fourni par l'équipe (script ponctuel).

    py -3 avelis_flux/ressources/preparer_logos.py <chemin du logo NOVUM>

Écrit dans ce dossier :
- logo_novum.png : logo d'origine, marges blanches retirées ;
- logo_novum_bandeau.png : illustration détourée + mot-symbole en blanc, pour le bandeau marine ;
- icone_novum.png : le robot, carré, pour l'icône de la fenêtre.
Le logo Avelis n'est pas fabriqué ici : déposer le fichier officiel sous logo_avelis.png.
"""

import pathlib
import sys

import numpy
from PIL import Image, ImageChops

DOSSIER = pathlib.Path(__file__).resolve().parent
SEUIL_BLANC = 25  # écart au blanc en dessous duquel un pixel est du fond
HAUTEUR_BANDEAU = 240  # px de l'image préparée (réduite à l'affichage)
RAPPORT_TEXTE = 0.58  # hauteur du mot-symbole / hauteur de l'illustration
ECART = 0.12  # espace entre illustration et texte, en fraction de la hauteur


def boite_non_blanche(image: Image.Image, seuil: int = SEUIL_BLANC) -> tuple:
    """Boîte englobante des pixels qui ne sont pas du fond blanc."""
    fond = Image.new("RGB", image.size, (255, 255, 255))
    masque = ImageChops.difference(image, fond).convert("L").point(
        lambda v: 255 if v > seuil else 0)
    return masque.getbbox()


def masque_marine(image: Image.Image) -> Image.Image:
    """Pixels du mot-symbole : sombres et bleutés (le bois et le robot sont jaunes ou bruns)."""
    pixels = numpy.asarray(image, dtype=numpy.int16)
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    marine = (b - r > 25) & (r + g + b < 450)
    return Image.fromarray((marine * 255).astype(numpy.uint8), "L")


def detourer(image: Image.Image) -> Image.Image:
    """Fond blanc rendu transparent ; l'opacité suit l'écart au blanc (bords adoucis)."""
    rgba = image.convert("RGBA")
    ecart = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255)))
    alpha = ecart.convert("L").point(lambda v: min(255, v * 4))
    rgba.putalpha(alpha)
    return rgba


def texte_en_blanc(image: Image.Image) -> Image.Image:
    """Mot-symbole sombre sur blanc → blanc sur transparent (opacité = noirceur)."""
    alpha = image.convert("L").point(lambda v: max(0, min(255, (235 - v) * 2)))
    blanc = Image.new("RGBA", image.size, (255, 255, 255, 0))
    blanc.putalpha(alpha)
    return blanc


def main(chemin: str) -> None:
    logo = Image.open(chemin).convert("RGB")
    logo.crop(boite_non_blanche(logo)).save(DOSSIER / "logo_novum.png")
    largeur, hauteur = logo.size
    # Le mot-symbole est à droite de l'illustration : zone des pixels sombres (marine)
    x0 = int(largeur * 0.6)
    droite = logo.crop((x0, 0, largeur, hauteur))
    boite_texte = masque_marine(droite).getbbox()
    texte = droite.crop(boite_texte)
    # L'illustration (bûches comprises) : tout le non-blanc qui n'est pas du texte marine
    sans_texte = logo.copy()
    sans_texte.paste((255, 255, 255), (x0 + boite_texte[0] - 4, boite_texte[1] - 4,
                                       x0 + boite_texte[2] + 4, boite_texte[3] + 4))
    dessin = sans_texte.crop(boite_non_blanche(sans_texte, 40))
    # Composition : illustration à gauche, texte blanc à droite, centré verticalement
    h = HAUTEUR_BANDEAU
    dessin = detourer(dessin).resize((round(dessin.width * h / dessin.height), h),
                                     Image.LANCZOS)
    ht = round(h * RAPPORT_TEXTE)
    texte = texte_en_blanc(texte).resize((round(texte.width * ht / texte.height), ht),
                                         Image.LANCZOS)
    ecart = round(h * ECART)
    bandeau = Image.new("RGBA", (dessin.width + ecart + texte.width, h), (0, 0, 0, 0))
    bandeau.alpha_composite(dessin, (0, 0))
    bandeau.alpha_composite(texte, (dessin.width + ecart, (h - ht) // 2))
    bandeau.save(DOSSIER / "logo_novum_bandeau.png")
    # Icône : le robot (moitié droite de l'illustration), carré
    robot = sans_texte.crop((int(largeur * 0.39), int(hauteur * 0.17), int(largeur * 0.73),
                             int(hauteur * 0.85)))
    cote = max(robot.size)
    icone = Image.new("RGB", (cote, cote), (255, 255, 255))
    icone.paste(robot, ((cote - robot.width) // 2, (cote - robot.height) // 2))
    icone.resize((256, 256), Image.LANCZOS).save(DOSSIER / "icone_novum.png")
    print("logos écrits dans", DOSSIER)


if __name__ == "__main__":
    main(sys.argv[1])
