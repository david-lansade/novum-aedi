// Formes des charges (three.js), à leur gabarit, l'avant vers +x : lot en palettes de cartons,
// kit 2D en panneaux sur chevalets, pod, module 3D à fenêtres, kit module (schéma satellites) en
// panneaux cerclés sur un socle. Pièces arrondies, couleurs par sommets (gabarits.js) ;
// `accent` : couleur du type d'objet.
import {
  COULEURS_PIECES as P, KIT_MODULE, MODULE, PALETTE_CARTONS, PANNEAUX, POD,
} from "./apparence.js";
import { centre, de, fusionner, piece } from "./gabarits.js";

/** Nombre de pièces de `cote` m, séparées de `jeu` m, que tient une longueur (au moins 1). */
const nombreDans = (longueur, cote, jeu) => Math.max(1, Math.floor((longueur + jeu)
  / (cote + jeu)));

/** Palette de côtés a × b centrée en (x, y) : plancher sur trois semelles. */
function palette(x, y, [a, b], couleur) {
  const { hauteur, semelle } = PALETTE_CARTONS;
  const pieces = [piece([x - a / 2, x + a / 2], [y - b / 2, y + b / 2], [semelle, hauteur],
    couleur, 0.02)];
  for (const k of [-1, 0, 1]) {
    const ys = y + k * (b / 2 - 0.07);
    pieces.push(piece([x - a / 2, x + a / 2], [ys - 0.06, ys + 0.06], [0, semelle], couleur,
      0.02));
  }
  return pieces;
}

/** Cartons d'une palette (côtés a × b, centrée en (x, y)) jusqu'à `haut` : PALETTE_CARTONS.couches
 * couches de 2 × 2 ; une palette sur trois a une place vide sur le dessus (motif fixe, `rang` :
 * numéro de la palette) ; un ruban adhésif sur chaque carton du dessus. */
function cartons(x, y, [a, b], haut, rang) {
  const { hauteur, couches, jeuCarton: j, scotch, teintes, couleurScotch } = PALETTE_CARTONS;
  const h = (haut - hauteur) / couches;
  const [ca, cb] = [(a - j) / 2, (b - j) / 2];
  const pieces = [];
  for (let k = 0; k < 4; k++) {
    const [cx, cy] = [x + ((k % 2) - 0.5) * (ca + j), y + (Math.floor(k / 2) - 0.5) * (cb + j)];
    const pile = couches - (rang % 3 === 1 && k === rang % 4 ? 1 : 0);
    for (let couche = 0; couche < pile; couche++) {
      const z = hauteur + couche * h;
      pieces.push(piece([cx - ca / 2, cx + ca / 2], [cy - cb / 2, cy + cb / 2], [z, z + h - 0.01],
        teintes[(rang + k + couche) % teintes.length], 0.035));
    }
    const dessus = hauteur + pile * h - 0.01;
    pieces.push(piece([cx - ca / 2 + 0.01, cx + ca / 2 - 0.01], centre(scotch).map((v) => v + cy),
      [dessus - 0.01, dessus + 0.005], couleurScotch, 0.004));
  }
  return pieces;
}

/** Lot : palettes de la couleur du lot, en rangs sur son gabarit, chargées de cartons. */
export function formeLot([largeur, longueur, hauteur], accent) {
  const { cote, jeu } = PALETTE_CARTONS;
  const [n, m] = [nombreDans(longueur, cote, jeu), nombreDans(largeur, cote, jeu)];
  const cotes = [Math.min(cote, longueur / n - jeu), Math.min(cote, largeur / m - jeu)];
  const pieces = [];
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < m; k++) {
      const [x, y] = [((i + 0.5) / n - 0.5) * longueur, ((k + 0.5) / m - 0.5) * largeur];
      pieces.push(...palette(x, y, cotes, accent), ...cartons(x, y, cotes, hauteur, i * m + k));
    }
  }
  return fusionner(pieces);
}

/** Chevalet en travers du kit, centré en x : poutre posée sur deux paires de pieds écartés. */
function chevalet(x, largeur, accent) {
  const { hautChevalet: h, poutre, pied, inclinaison } = PANNEAUX;
  const angle = (inclinaison * Math.PI) / 180;
  const [haut, ecart] = [h - poutre, (h - poutre) * Math.tan(angle)];
  const pieces = [piece([x - 0.06, x + 0.06], centre(largeur), [haut, h], accent, 0.02)];
  for (const s of [-1, 1]) {
    for (const cote of [-1, 1]) {
      const longueurJambe = haut / Math.cos(angle);
      const jambe = piece(centre(pied), centre(pied), centre(longueurJambe), accent, 0.02);
      pieces.push(jambe.rotateY(-s * angle).translate(x + (s * ecart) / 2,
        cote * (largeur / 2 - 0.1), haut / 2));
    }
  }
  return pieces;
}

/** Pile de `nombre` panneaux de côtés longueur × largeur, de z0 à z1, de teintes alternées et un
 * peu décalés les uns des autres, cerclée de deux sangles d'accent. */
function pileDePanneaux(longueur, largeur, [z0, z1], nombre, accent) {
  const { jeu, decalage: d, sangle, teintes } = PANNEAUX;
  const e = (z1 - z0 - (nombre - 1) * jeu) / nombre;
  const pieces = [];
  for (let i = 0; i < nombre; i++) {
    const [z, s] = [z0 + i * (e + jeu), i % 2 === 0 ? 1 : -1];
    pieces.push(piece(centre(longueur - 2 * d).map((v) => v + s * d),
      centre(largeur - 2 * d).map((v) => v - (s * d) / 2), [z, z + e], teintes[i % teintes.length],
      0.03));
  }
  for (const x of [-longueur / 4, longueur / 4]) {
    pieces.push(piece([x - sangle / 2, x + sangle / 2], centre(largeur), [z0, z1 + 0.015], accent,
      0.02));
  }
  return pieces;
}

/** Kit 2D : pile de panneaux sur des chevalets (de la couleur du kit), cerclée de sangles. */
export function formeKit2D([largeur, longueur, hauteur], accent) {
  const { chevalets, hautChevalet, nombre, retrait } = PANNEAUX;
  const pieces = [];
  for (let i = 0; i < chevalets; i++) {
    pieces.push(...chevalet(((i + 0.5) / chevalets - 0.5) * longueur, largeur, accent));
  }
  pieces.push(...pileDePanneaux(longueur - 2 * retrait, largeur - 2 * retrait,
    [hautChevalet, hauteur - 0.02], nombre, accent));
  return fusionner(pieces);
}

/** Plaque posée sur la face d'un corps centré (axe « x » ou « y », côté s = ±1, face à `demi`
 * m du centre), de [u0, u1] le long de la face et de [z0, z1], saillante de `saillie` m. */
function plaque(axe, s, demi, [u0, u1], [z0, z1], saillie, couleur) {
  const travers = de(s * (demi - 0.02), s * (demi + saillie));
  return axe === "y" ? piece([u0, u1], travers, [z0, z1], couleur, 0.02)
    : piece(travers, [u0, u1], [z0, z1], couleur, 0.02);
}

/** Pod : cabine blanche sur un socle et sous un rebord d'accent, porte sur la face avant,
 * grille d'aération sur un côté. */
export function formePod([largeur, longueur, hauteur], accent) {
  const { socle, rebord, rayon, porte: [lp, hp] } = POD;
  const [dx, dy] = [longueur / 2 - 0.04, largeur / 2 - 0.04];
  const haut = hauteur - rebord;
  return fusionner([
    piece(centre(longueur), centre(largeur), [0, socle], accent, 0.04),
    piece(centre(longueur - 0.08), centre(largeur - 0.08), [socle, haut], P.blanc, rayon),
    piece(centre(longueur), centre(largeur), [haut, hauteur], accent, 0.05),
    plaque("x", 1, dx, centre(lp), [socle + 0.06, socle + 0.06 + hp], 0.02, P.clair),
    plaque("x", 1, dx + 0.02, [lp / 2 - 0.16, lp / 2 - 0.08], [socle + 1, socle + 1.1], 0.02,
      P.sombre),
    plaque("y", 1, dy, centre(0.6), [haut - 0.5, haut - 0.25], 0.02, P.gris),
  ]);
}

/** Baie d'un module : cadre clair et vitre sombre, sur la face (axe, s, demi), centrée en u,
 * de largeur l, de z0 à z1. */
function baie(axe, s, demi, u, [l, z0, z1]) {
  const c = MODULE.cadre;
  return [plaque(axe, s, demi, [u - l / 2 - c, u + l / 2 + c], [z0 - c, z1 + c], 0.02, P.clair),
    plaque(axe, s, demi, [u - l / 2, u + l / 2], [z0, z1], 0.035, P.vitre)];
}

/** Module 3D : boîte-logement blanche sur un châssis et sous un rebord d'accent ; fenêtres sur
 * les longs côtés et au bout arrière, porte vitrée au bout avant. */
export function formeModule([largeur, longueur, hauteur], accent) {
  const { chassis, rebord, rayon, pasFenetres, fenetre: f, porte: [lp, hp] } = MODULE;
  const [dx, dy] = [longueur / 2 - 0.04, largeur / 2 - 0.04];
  const pieces = [
    piece(centre(longueur), centre(largeur), [0, chassis], accent, 0.05),
    piece(centre(longueur - 0.08), centre(largeur - 0.08), [chassis, hauteur - rebord], P.blanc,
      rayon),
    piece(centre(longueur), centre(largeur), [hauteur - rebord, hauteur], accent, 0.06),
    ...baie("x", -1, dx, 0, [f.largeur, f.bas, f.haut]),
    ...baie("x", 1, dx, 0, [lp, chassis + 0.1, chassis + 0.1 + hp]),
  ];
  const n = Math.max(1, Math.floor(longueur / pasFenetres));
  for (let i = 0; i < n; i++) {
    const u = ((i + 0.5) / n - 0.5) * longueur;
    for (const s of [-1, 1]) pieces.push(...baie("y", s, dy, u, [f.largeur, f.bas, f.haut]));
  }
  return fusionner(pieces);
}

/** Kit module : panneaux cerclés sur un socle de la couleur du type. */
export function formeKitModule([largeur, longueur, hauteur], accent) {
  const { socle, panneaux } = KIT_MODULE;
  return fusionner([piece(centre(longueur), centre(largeur), [0, socle], accent, 0.04),
    ...pileDePanneaux(longueur - 0.1, largeur - 0.1, [socle + 0.02, hauteur - 0.02], panneaux,
      accent)]);
}

/** Constructeurs des charges animées, par nom de forme (objets.js, formeObjet). */
export const FORMES_CHARGES = {
  palettes: formeLot, panneaux: formeKit2D, pod: formePod, module: formeModule,
  "kit module": formeKitModule,
};
