// Briques des formes des objets (formesVehicules.js, formesCharges.js) et leurs ombres de
// contact. Une forme est posée en z = 0, l'avant vers +x, la largeur suivant y. Chaque pièce
// porte la couleur de ses sommets ; le matériau reste blanc. Pièces à arêtes arrondies
// (RoundedBoxGeometry de three) : aucune arête vive.
import {
  BufferAttribute, BufferGeometry, Color, CylinderGeometry, Float32BufferAttribute,
} from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

import { ARRONDI } from "./apparence.js";

const SEGMENTS_ARRONDI = 1; // une facette de plus à chaque arête : arrondie, avec peu de sommets
const SEGMENTS_CYLINDRE = 18;

/** Donne à tous les sommets de la géométrie la même couleur ; la renvoie. */
export function colorer(geometrie, couleur) {
  const { r, g, b } = new Color(couleur);
  const sommets = geometrie.attributes.position.count;
  const couleurs = new Float32Array(sommets * 3);
  for (let i = 0; i < sommets; i++) couleurs.set([r, g, b], i * 3);
  geometrie.setAttribute("color", new BufferAttribute(couleurs, 3));
  return geometrie;
}

/** Intervalle [−cote / 2, cote / 2] (pièces centrées sur l'axe). */
export const centre = (cote) => [-cote / 2, cote / 2];

/** Intervalle de a à b, dans l'ordre croissant (pièces posées d'un côté ou de l'autre). */
export const de = (a, b) => [Math.min(a, b), Math.max(a, b)];

/** Pièce arrondie de [x0, x1] × [y0, y1] × [z0, z1], d'une couleur ; le rayon des arêtes est
 * borné par la moitié du plus petit côté. */
export function piece([x0, x1], [y0, y1], [z0, z1], couleur, rayon = ARRONDI) {
  const geometrie = new RoundedBoxGeometry(x1 - x0, y1 - y0, z1 - z0, SEGMENTS_ARRONDI, rayon);
  geometrie.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return colorer(geometrie, couleur);
}

/** Cylindre de centre [x, y, z], d'axe y (roues) ou z (balises), à `segments` facettes. */
export function cylindre([x, y, z], rayon, longueur, couleur, axe = "y",
  segments = SEGMENTS_CYLINDRE) {
  const geometrie = new CylinderGeometry(rayon, rayon, longueur, segments).toNonIndexed();
  if (axe === "z") geometrie.rotateX(Math.PI / 2);
  return colorer(geometrie.translate(x, y, z), couleur);
}

/** Une seule géométrie à partir des pièces (toutes non indexées, aux mêmes attributs). */
export function fusionner(pieces) {
  return mergeGeometries(pieces);
}

/** Ombre de contact d'un objet de gabarit [largeur, longueur] : son emprise, opaque, bordée d'une
 * frange de `marge` m qui s'estompe jusqu'à la transparence (alpha des sommets), à l'altitude z.
 * Grille de 4 × 4 sommets, l'avant vers +x comme les formes. */
export function geometrieOmbre([largeur, longueur], marge, z) {
  const xs = [-longueur / 2 - marge, -longueur / 2, longueur / 2, longueur / 2 + marge];
  const ys = [-largeur / 2 - marge, -largeur / 2, largeur / 2, largeur / 2 + marge];
  const [positions, couleurs, indices] = [[], [], []];
  ys.forEach((y, j) => xs.forEach((x, i) => {
    positions.push(x, y, z);
    couleurs.push(1, 1, 1, i % 3 > 0 && j % 3 > 0 ? 1 : 0); // opaque à l'intérieur seulement
  }));
  for (let j = 0; j < 3; j++) {
    for (let i = 0; i < 3; i++) {
      const a = j * 4 + i;
      indices.push(a, a + 1, a + 5, a, a + 5, a + 4); // face vers le haut
    }
  }
  const geometrie = new BufferGeometry();
  geometrie.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometrie.setAttribute("color", new Float32BufferAttribute(couleurs, 4));
  geometrie.setIndex(indices);
  return geometrie;
}
