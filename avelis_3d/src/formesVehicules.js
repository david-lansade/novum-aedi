// Formes des véhicules (three.js), à leur gabarit, l'avant vers +x : semi-remorques (tracteur à
// cabine arrondie, remorque fourgon ou plateau surbaissé à col de cygne) sans leurs roues ; roue
// unité, instanciée à part (objets.js donne la place des roues) ; chariot élévateur (du décor,
// et porteur des marchandises), AGV du décor, voiture du parking VL. Pièces arrondies,
// couleurs par sommets (gabarits.js) ; `accent` : couleur du type.
import {
  AGV, CAMION, CHARIOT, COULEURS_PIECES as P, MODELES_VL, PIETON,
} from "./apparence.js";
import { centre, cylindre, de, fusionner, piece } from "./gabarits.js";
import { rouesDe } from "./objets.js";

const RETRAIT_FACE = 0.08; // devant de la cabine, en retrait du pare-chocs
const BOULONS = 5; // par flanc de roue
const FACETTES_BOULON = 6; // peu de triangles : il y a des centaines de roues

/** Cabine du tracteur, pare-chocs en x = `av` : caisse arrondie, vitrage enveloppant
 * (pare-brise et vitres latérales), calandre, phares, bande d'accent, feux de toit. */
function cabine(av, largeur, accent) {
  const { cabine: c, vitrage: v, calandre: k, pareChocs: p, bande: b } = CAMION;
  const face = av - RETRAIT_FACE;
  const ar = av - c.longueur;
  const pieces = [
    piece([ar, face], centre(largeur - 0.06), [c.bas, c.hauteur], P.blanc, c.rayon),
    piece([face - v.profondeur, face + 0.02], centre(largeur - 0.02), [v.bas, v.haut], P.vitre,
      0.12),
    piece([face - 0.05, face + 0.03], centre(largeur * k.largeur), [k.bas, k.haut], P.sombre,
      0.04),
    piece([face - 0.25, av], centre(largeur - 0.04), [p.bas, p.haut], P.gris, 0.1),
    piece([ar - 0.01, face + 0.01], centre(largeur - 0.02), [b.bas, b.haut], accent, 0.03),
  ];
  for (const s of [-1, 1]) {
    const y = s * (largeur / 2 - 0.32);
    pieces.push(piece([face - 0.05, face + 0.04], [y - 0.18, y + 0.18], [0.95, 1.12], P.phare,
      0.04));
  }
  for (const y of [-0.5, 0, 0.5]) {
    pieces.push(piece([face - 0.4, face - 0.28], [y - 0.09, y + 0.09],
      [c.hauteur - 0.03, c.hauteur + 0.05], P.balise, 0.02));
  }
  return pieces;
}

/** Rétroviseurs de part et d'autre de la cabine, sur leur bras ; seules pièces qui débordent
 * de la largeur du gabarit, comme sur un vrai camion. */
function retroviseurs(av, largeur) {
  const { recul, saillie, bas, haut } = CAMION.retro;
  const x = av - RETRAIT_FACE - recul;
  return [-1, 1].flatMap((s) => {
    const bord = s * (largeur / 2 - 0.03);
    return [
      piece([x - 0.03, x + 0.03], de(bord, bord + s * saillie), [haut - 0.12, haut - 0.06],
        P.sombre, 0.02),
      piece([x - 0.08, x + 0.05], de(bord + s * (saillie - 0.1), bord + s * saillie), [bas, haut],
        P.sombre, 0.04),
    ];
  });
}

/** Tracteur : cabine, rétroviseurs, longerons, sellette au-dessus de l'essieu moteur
 * (`xMoteur`), réservoirs entre les essieux. */
function tracteur(av, largeur, accent, xMoteur) {
  const { cabine: c, chassis: ch } = CAMION;
  const ar = av - c.longueur;
  const pieces = [...cabine(av, largeur, accent), ...retroviseurs(av, largeur),
    piece([ar - 1.9, av - 0.3], centre(largeur * ch.largeur), [ch.bas, ch.haut], P.sombre),
    piece([xMoteur - 0.5, xMoteur + 0.5], centre(1.2), [ch.haut - 0.05, ch.haut + 0.15],
      P.sombre, 0.04)];
  for (const s of [-1, 1]) {
    const travers = de(s * (largeur / 2 - 0.5), s * (largeur / 2 - 0.08));
    pieces.push(piece([ar + 0.05, ar + 0.75], travers, [0.5, 0.95], P.jante, 0.12));
  }
  return pieces;
}

/** Pare-chocs et feux arrière d'une remorque qui finit en x = `ar`, feux entre z0 et z1. */
function arriere(ar, largeur, [z0, z1]) {
  const pieces = [piece([ar + 0.12, ar + 0.32], centre(largeur - 0.2), [z0 - 0.06, z1 + 0.06],
    P.sombre, 0.04)];
  for (const s of [-1, 1]) {
    const y = s * (largeur / 2 - 0.35);
    pieces.push(piece([ar + 0.06, ar + 0.14], [y - 0.16, y + 0.16], [z0, z1], P.feu, 0.03));
  }
  return pieces;
}

/** Remorque fourgon, de `ar` à `av` : caisse blanche à bande d'accent, portes arrière,
 * sous-châssis, protections latérales entre ses essieux et l'essieu moteur (`xMoteur`). */
function remorqueFourgon(ar, av, [largeur, hauteur], accent, xMoteur) {
  const { caisse, chassis, roue, essieux } = CAMION;
  const devantEssieux = ar + Math.max(...essieux.remorque) + roue.rayon + 0.3;
  const pieces = [
    piece([ar + 0.15, av - 0.3], centre(largeur * chassis.largeur), [0.9, caisse.bas], P.sombre),
    piece([ar + 0.06, av - 0.02], centre(largeur - 0.04), [caisse.bas, hauteur], P.blanc, 0.12),
    piece([ar + 0.05, av], centre(largeur), [caisse.bas - 0.01, caisse.bas + caisse.bande],
      accent, 0.04),
    piece([ar + 0.02, ar + 0.1], centre(largeur - 0.14), [caisse.bas + 0.08, hauteur - 0.08],
      P.clair, 0.03),
    piece([ar, ar + 0.04], centre(0.05), [caisse.bas + 0.15, hauteur - 0.15], P.gris, 0.01),
    ...arriere(ar, largeur, [0.68, 0.86]),
  ];
  for (const s of [-1, 1]) {
    pieces.push(piece([devantEssieux, xMoteur - roue.rayon - 0.3],
      de(s * (largeur / 2 - 0.1), s * (largeur / 2 - 0.04)), [0.55, 0.85], P.gris, 0.02));
  }
  return pieces;
}

/** Remorque à plateau surbaissé, de `ar` à `av` : col de cygne posé sur la sellette et sa
 * retombée, poutres d'accent sous un plancher clair, feux latéraux orange. */
function remorquePlateau(ar, av, largeur, accent) {
  const p = CAMION.plateau;
  const col = av - p.col;
  const pieces = [
    piece([col, av], centre(largeur), [p.basCol, p.hautCol], accent, 0.08),
    piece([col, col + 0.4], centre(largeur), [p.bas, p.hautCol], accent, 0.06),
    piece([ar + 0.03, col + 0.05], centre(largeur - 0.04), [p.bas, p.haut - 0.05], accent, 0.05),
    piece([ar + 0.06, col], centre(largeur - 0.12), [p.haut - 0.08, p.haut], P.clair, 0.02),
    ...arriere(ar, largeur, [p.bas - 0.2, p.bas - 0.04]),
  ];
  for (let x = ar + 1; x < col; x += 2.5) {
    for (const s of [-1, 1]) {
      pieces.push(piece([x - 0.08, x + 0.08], de(s * (largeur / 2 - 0.03), s * largeur / 2),
        [p.bas + 0.06, p.bas + 0.14], P.balise, 0.01));
    }
  }
  return pieces;
}

/** Semi-remorque de forme « fourgon » ou « plateau », de gabarit [largeur, longueur, hauteur],
 * sans ses roues. */
export function formeCamion(forme, [largeur, longueur, hauteur], accent) {
  const { cabine: c, ecart, essieux } = CAMION;
  const av = longueur / 2;
  const avantRemorque = av - c.longueur - ecart;
  const xMoteur = av - c.longueur - essieux.moteur;
  const remorque = forme === "plateau" ? remorquePlateau(-av, avantRemorque, largeur, accent)
    : remorqueFourgon(-av, avantRemorque, [largeur, hauteur], accent, xMoteur);
  return fusionner([...tracteur(av, largeur, accent, xMoteur), ...remorque]);
}

/** Roue unité (rayon 1, largeur 1, axe y, centrée) : pneu aux flancs arrondis, jante claire,
 * moyeu, et sur chaque flanc BOULONS boulons sombres, qui montrent qu'elle tourne ; mise à
 * l'échelle de chaque roue par instance (objets.js, rouesDe). */
export function roueUnite() {
  const boulons = [-1, 1].flatMap((s) => Array.from({ length: BOULONS }, (_, k) => {
    const angle = (2 * Math.PI * k) / BOULONS;
    return cylindre([0.38 * Math.cos(angle), s * 0.505, 0.38 * Math.sin(angle)], 0.08, 0.04,
      P.sombre, "y", FACETTES_BOULON);
  }));
  return fusionner([
    cylindre([0, 0, 0], 1, 0.84, P.pneu), cylindre([0, 0, 0], 0.93, 1, P.pneu),
    cylindre([0, 0, 0], 0.58, 1.02, P.jante), cylindre([0, 0, 0], 0.22, 1.05, P.sombre),
    ...boulons,
  ]);
}

/** Constructeurs des véhicules animés, par nom de forme (objets.js, formeObjet). */
export const FORMES_VEHICULES = {
  fourgon: (gabarit, accent) => formeCamion("fourgon", gabarit, accent),
  plateau: (gabarit, accent) => formeCamion("plateau", gabarit, accent),
};

/** Caisse du chariot élévateur (de `ar` au mât en `xm`) : châssis violet, contrepoids et capot
 * jaunes, siège, colonne de direction et volant. */
function caisseChariot(ar, xm) {
  const { largeur: l, capot, couleurs: c } = CHARIOT;
  return [
    piece([ar + 0.1, xm - 0.05], centre(l - 0.06), [0.18, 0.62], c.chassis, 0.1),
    piece([ar, ar + 0.75], centre(l), [0.3, 1.25], c.caisse, 0.2),
    piece([ar + 0.7, xm - 0.12], centre(l - 0.06), [0.6, capot], c.caisse, 0.12),
    piece([ar + 0.75, ar + 1.2], centre(0.55), [capot, capot + 0.12], c.cage, 0.04),
    piece([ar + 0.72, ar + 0.84], centre(0.55), [capot, capot + 0.55], c.cage, 0.04),
    piece([ar + 1.45, ar + 1.53], centre(0.08), [capot, capot + 0.38], c.cage, 0.02),
    piece([ar + 1.38, ar + 1.6], centre(0.34), [capot + 0.36, capot + 0.4], c.cage, 0.02),
  ];
}

/** Cariste stylisé, assis face à l'avant : gilet orange, tête, casque. */
function cariste(ar) {
  const { capot, couleurs: c } = CHARIOT;
  return [
    piece([ar + 0.82, ar + 1.14], centre(0.42), [capot + 0.1, capot + 0.66], c.gilet, 0.1),
    piece([ar + 0.9, ar + 1.1], centre(0.22), [capot + 0.7, capot + 0.9], c.peau, 0.1),
    piece([ar + 0.88, ar + 1.12], centre(0.26), [capot + 0.84, capot + 0.98], c.casque, 0.1),
  ];
}

/** Toit de protection du cariste : quatre montants, deux longerons, lattes, gyrophare. */
function cageChariot(ar, xm) {
  const { largeur: l, capot, cage: h, couleurs: c } = CHARIOT;
  const [x0, x1] = [ar + 0.62, xm - 0.2];
  const pieces = [cylindre([ar + 0.8, 0, h + 0.05], 0.06, 0.1, P.balise, "z")];
  for (const s of [-1, 1]) {
    const y = de(s * (l / 2 - 0.1), s * (l / 2 - 0.03));
    for (const x of [x0, x1]) {
      pieces.push(piece([x - 0.03, x + 0.03], y, [capot, h], c.cage, 0.02));
    }
    pieces.push(piece([x0 - 0.04, x1 + 0.04], y, [h - 0.06, h], c.cage, 0.02));
  }
  for (let i = 0; i < 4; i++) {
    const x = x0 + ((i + 0.5) * (x1 - x0)) / 4;
    pieces.push(piece([x - 0.04, x + 0.04], centre(l - 0.1), [h - 0.05, h - 0.01], c.cage, 0.01));
  }
  return pieces;
}

/** Mât (deux montants, traverses), tablier et fourches, du mât en `xm` à l'avant en `av`. */
function matChariot(xm, av) {
  const { mat, couleurs: c } = CHARIOT;
  const pieces = [
    piece([xm - 0.1, xm], centre(0.84), [mat - 0.1, mat], c.cage, 0.02),
    piece([xm - 0.1, xm], centre(0.84), [0.3, 0.4], c.cage, 0.02),
    piece([xm, xm + 0.08], centre(0.9), [0.12, 0.75], P.sombre, 0.02),
  ];
  for (const s of [-1, 1]) {
    pieces.push(piece([xm - 0.1, xm], de(s * 0.32, s * 0.42), [0.08, mat], c.cage, 0.02),
      piece([xm + 0.04, av], de(s * 0.24, s * 0.36), [0.04, 0.1], P.sombre, 0.015));
  }
  return pieces;
}

/** Roues du chariot : grandes à l'avant, petites sous le contrepoids. */
function rouesChariot(ar, xm) {
  const { largeur: l, roues: [avant, arriere] } = CHARIOT;
  return [[xm - 0.45, avant], [ar + 0.42, arriere]].flatMap(([x, r]) => [-1, 1].flatMap((s) => [
    cylindre([x, s * (l / 2 - 0.12), r], r, 0.22, P.pneu),
    cylindre([x, s * (l / 2 - 0.11), r], r * 0.55, 0.24, P.jante),
  ]));
}

/** Chariot élévateur jaune du décor, centré, fourches vers +x. */
export function formeChariot() {
  const { longueur, fourches } = CHARIOT;
  const [ar, av] = [-longueur / 2, longueur / 2];
  const xm = av - fourches;
  return fusionner([...caisseChariot(ar, xm), ...cariste(ar), ...cageChariot(ar, xm),
    ...matChariot(xm, av), ...rouesChariot(ar, xm)]);
}

/** Caisse vitrée d'une voiture de modèle `m` (MODELES_VL) : habitacle vitré sous son toit ; pour
 * la camionnette, caisse haute, pare-brise et vitres de la cabine à l'avant. */
function hautDeCaisse(m) {
  const { longueur: l, largeur: w, hauteur: h, caisse: [, haut], habitacle: [ar, av] } = m;
  if (h < 2) {
    return [piece([l * ar, l * av], centre(w - 0.14), [haut - 0.05, h - 0.08], P.vitre, 0.2),
      piece([l * ar + 0.1, l * av - 0.06], centre(w - 0.2), [h - 0.12, h], P.blanc, 0.1)];
  }
  return [piece([-l / 2 + 0.05, l * ar], centre(w - 0.04), [haut - 0.05, h], P.blanc, 0.15),
    piece([l * ar - 0.1, l * av], centre(w - 0.12), [haut - 0.05, h - 0.5], P.vitre, 0.15),
    piece([l * ar - 0.75, l * ar - 0.1], centre(w + 0.01), [haut + 0.25, h - 0.6], P.vitre,
      0.04)];
}

/** Véhicule léger de modèle `m` (MODELES_VL), centré, l'avant vers +x : caisse blanche
 * (teintée par instance), haut de caisse, phares, feux, quatre roues. */
export function formeVL(m) {
  const { longueur: l, largeur: w, caisse: [bas, haut], roue: r } = m;
  const pieces = [piece(centre(l), centre(w), [bas, haut], P.blanc, 0.18), ...hautDeCaisse(m)];
  for (const s of [-1, 1]) {
    const y = de(s * (w / 2 - 0.42), s * (w / 2 - 0.12));
    pieces.push(piece([l / 2 - 0.06, l / 2 + 0.01], y, [haut - 0.24, haut - 0.1], P.phare, 0.03),
      piece([-l / 2 - 0.01, -l / 2 + 0.06], y, [haut - 0.22, haut - 0.08], P.feu, 0.03));
    for (const x of [l / 2 - 0.85, -l / 2 + 0.8]) {
      pieces.push(cylindre([x, s * (w / 2 - 0.16), r], r, 0.22, P.pneu));
    }
  }
  return fusionner(pieces);
}

/** Voiture de tourisme (berline), pour ce qui n'a pas de modèle. */
export function formeVoiture() {
  return formeVL(MODELES_VL.berline);
}

/** Semi-remorque fourgon de passage sur la route publique, roues comprises, d'accent
 * `accent`. */
export function formeCamionDeRoute(gabarit, accent) {
  const roues = rouesDe("fourgon", gabarit).map(({ x, y, rayon, largeur }) => roueUnite()
    .scale(rayon, largeur, rayon).translate(x, y, rayon));
  return fusionner([formeCamion("fourgon", gabarit, accent), ...roues]);
}

/** AGV plat du décor : jupe sombre, corps blanc à bande violette, plateau clair, capteur avant
 * et voyant orange. */
export function formeAgv() {
  const { longueur: l, largeur: w, hauteur: h, bande } = AGV;
  return fusionner([
    piece(centre(l - 0.1), centre(w - 0.1), [0.02, 0.12], P.sombre, 0.03),
    piece(centre(l - 0.04), centre(w - 0.04), [0.1, h - 0.04], P.blanc, 0.1),
    piece(centre(l), centre(w), [0.15, 0.21], bande, 0.03),
    piece(centre(l - 0.3), centre(w - 0.3), [h - 0.06, h], P.clair, 0.03),
    piece([l / 2 - 0.05, l / 2], centre(0.34), [0.23, 0.3], P.vitre, 0.02),
    cylindre([l / 2 - 0.2, w / 2 - 0.16, h - 0.02], 0.05, 0.06, P.balise, "z"),
  ]);
}

/** Opérateur à pied, centré, face à +x : jambes sombres, gilet haute visibilité à bande claire,
 * bras, tête ; à PIETON.echelle de la taille réelle, pour être vu de loin. */
export function formePieton() {
  const c = PIETON.couleurs;
  const pieces = [
    piece(centre(0.24), [-0.2, -0.02], [0, 0.86], c.pantalon, 0.07),
    piece(centre(0.24), [0.02, 0.2], [0, 0.86], c.pantalon, 0.07),
    piece(centre(0.3), centre(0.5), [0.82, 1.48], c.gilet, 0.1),
    piece(centre(0.31), centre(0.51), [1.08, 1.16], c.bande, 0.03),
    piece(centre(0.2), centre(0.2), [1.52, 1.76], c.peau, 0.09),
  ];
  for (const y of [-0.31, 0.31]) {
    pieces.push(piece(centre(0.14), centre(0.12), [0.86, 1.44], c.gilet, 0.05));
    pieces[pieces.length - 1].translate(0, y, 0);
  }
  return fusionner(pieces).scale(PIETON.echelle, PIETON.echelle, PIETON.echelle);
}
