// Formes des bâtiments (three.js), en coordonnées du plan, d'après batiments.js et decor.js : un
// seul maillage pour tous les murs, un pour tous les toits (et ce qui s'y pose), un pour les
// portes de quai, un pour les plaques et numéros, un pour les emblèmes. Couleurs par sommets ;
// coordonnées de texture en mètres, pour que la tôle nervurée garde le même pas partout.
import {
  BoxGeometry, BufferGeometry, CylinderGeometry, ExtrudeGeometry, Float32BufferAttribute,
  Matrix4, Shape,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

import {
  BATIMENT, COULEURS_BATIMENT, EMBLEME, GRANDE_PORTE, GROUPE_FROID, GYROPHARE, NUMERO_QUAI,
  PORTE, PORTE_PIETONNE,
} from "./apparence.js";
import { colorer } from "./gabarits.js";

const SEGMENTS_CYLINDRE = 16;

/** Coordonnées de texture en mètres (divisées par `pas`), prises dans le plan de chaque face :
 * u horizontal le long d'un mur, ou le long du faîtage sur un pan (les nervures suivent v). */
function uvMetriques(geometrie, pas = BATIMENT.pasNervure) {
  const { position, normal } = geometrie.attributes;
  const uv = new Float32Array(position.count * 2);
  for (let i = 0; i < position.count; i++) {
    const [x, y, z] = [position.getX(i), position.getY(i), position.getZ(i)];
    const [nx, ny, nz] = [normal.getX(i), normal.getY(i), normal.getZ(i)].map(Math.abs);
    const [u, v] = nz >= Math.max(nx, ny) ? [x, y] : ny >= nx ? [x, z] : [y, z];
    uv.set([u / pas, v / pas], 2 * i);
  }
  geometrie.setAttribute("uv", new Float32BufferAttribute(uv, 2));
  return geometrie;
}

/** Géométrie non indexée (seule forme que l'on fusionne ici). */
function aplatir(geometrie) {
  return geometrie.index ? geometrie.toNonIndexed() : geometrie;
}

/** Géométrie prête à fusionner : coordonnées de texture en mètres, teinte, non indexée. */
function preparer(geometrie, couleur) {
  return aplatir(colorer(uvMetriques(geometrie), couleur));
}

/** Pavé de centre `centre` [x, y, z] et de côtés `cotes` [x, y, z]. */
function bloc(centre, cotes, couleur) {
  return preparer(new BoxGeometry(...cotes).translate(...centre), couleur);
}

/** Pavés d'un mur le long de l'axe `axe` (x ou y), à la coordonnée `fixe` de l'autre axe, de
 * `debut` à `fin` et de z0 à z1, percé des ouvertures `trous` [[a, b, haut]] (de a à b, du sol
 * à `haut`) : pans pleins entre elles, linteau au-dessus. */
function murPerce(axe, fixe, [debut, fin], [z0, z1], epaisseur, trous, couleur) {
  const pave = (a, b, bas) => bloc(axe === "x" ? [(a + b) / 2, fixe, (bas + z1) / 2]
    : [fixe, (a + b) / 2, (bas + z1) / 2], axe === "x" ? [b - a, epaisseur, z1 - bas]
    : [epaisseur, b - a, z1 - bas], couleur);
  const parties = [];
  let c = debut;
  for (const [a, b, haut] of [...trous].sort((p, q) => p[0] - q[0])) {
    if (b <= c || a >= fin) continue;
    if (a > c) parties.push(pave(c, a, z0));
    if (haut < z1) parties.push(pave(Math.max(a, c), Math.min(b, fin), Math.max(z0, haut)));
    c = Math.min(fin, b);
  }
  if (c < fin) parties.push(pave(c, fin, z0));
  return parties;
}

/** Pavés des quatre murs d'un bâtiment de z0 à z1, épaissis de `saillie` m de chaque côté ;
 * avec `retrait`, raccourcis d'autant à chaque bout (bandeaux vitrés) ; `trous` : ouvertures
 * de chaque mur {sud, nord, ouest, est: [[a, b, haut]]}. */
function ceinture({ x, y, largeur, profondeur }, [z0, z1], saillie, couleur, retrait = 0,
  trous = {}) {
  const e = BATIMENT.epaisseurMur;
  const [epaisseur, bord] = [e + 2 * saillie, e / 2];
  const long = retrait > 0 ? [x + retrait, x + largeur - retrait]
    : [x - saillie, x + largeur + saillie];
  const court = retrait > 0 ? [y + retrait, y + profondeur - retrait]
    : [y + e, y + profondeur - e];
  const mur = (axe, fixe, bornes, nom) => murPerce(axe, fixe, bornes, [z0, z1], epaisseur,
    trous[nom] ?? [], couleur);
  return [...mur("x", y + bord, long, "sud"), ...mur("x", y + profondeur - bord, long, "nord"),
    ...mur("y", x + bord, court, "ouest"), ...mur("y", x + largeur - bord, court, "est")];
}

/** Ouvertures {sud, nord, ouest, est: [[a, b, haut]]} des portes de marchandises de la zone. */
function trousDe(nom, portes) {
  const trous = {};
  for (const { zone, mur, point, normale } of portes) {
    if (zone !== nom) continue;
    const le = point[Math.abs(normale[1]) > 0 ? 0 : 1];
    (trous[mur] ??= []).push([le - GRANDE_PORTE.largeur / 2, le + GRANDE_PORTE.largeur / 2,
      GRANDE_PORTE.hauteur]);
  }
  return trous;
}

/** Murs d'un bâtiment : tôle blanche, soubassement violet ; bandeaux vitrés à chaque étage pour
 * les bureaux (sous l'acrotère) ; percés au droit des portes de marchandises `portes`. */
function mursDe(batiment, portes = []) {
  const trous = trousDe(batiment.nom, portes);
  const parties = [...ceinture(batiment, [0, batiment.hauteur], 0, COULEURS_BATIMENT.murs, 0,
    trous), ...ceinture(batiment, [0, BATIMENT.soubassement], BATIMENT.saillie,
    COULEURS_BATIMENT.soubassement, 0, trous)];
  if (batiment.toit.forme !== "plat") return parties;
  const allege = (BATIMENT.etage - BATIMENT.vitrage) / 2;
  for (let z = allege; z + BATIMENT.vitrage < batiment.hauteur - BATIMENT.acrotere;
    z += BATIMENT.etage) {
    parties.push(...ceinture(batiment, [z, z + BATIMENT.vitrage], BATIMENT.saillie,
      COULEURS_BATIMENT.vitrage, BATIMENT.retraitVitrage, trous));
  }
  return parties;
}

/** Pignon triangulaire (base `portee`, flèche `fleche`) dans le repère local d'un toit : plan
 * (y, z), épaisseur d'un mur centrée en x = `abscisse`. */
function pignon(portee, fleche, abscisse) {
  const forme = new Shape([[-portee / 2, 0], [portee / 2, 0], [0, fleche]]
    .map(([s, t]) => ({ x: s, y: t })));
  const geometrie = uvMetriques(new ExtrudeGeometry(forme, { depth: BATIMENT.epaisseurMur,
    bevelEnabled: false }));
  // (s, t, profondeur) → (x, y, z) = (profondeur, s, t) : rotation, l'orientation est conservée
  const versToit = new Matrix4().set(0, 0, 1, abscisse - BATIMENT.epaisseurMur / 2,
    1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1);
  return aplatir(colorer(geometrie.applyMatrix4(versToit), COULEURS_BATIMENT.murs));
}

/** Pan de toit dans le repère local (faîtage suivant x, en z = flèche ; sens −1 : pan sud). */
function pan(longueur, portee, fleche, sens, couleur) {
  const pente = Math.atan2(fleche, portee / 2);
  const rampant = (portee / 2 + BATIMENT.debord) / Math.cos(pente);
  const e = BATIMENT.epaisseurToit;
  const geometrie = uvMetriques(new BoxGeometry(longueur, rampant, e));
  geometrie.rotateX(-sens * pente);
  geometrie.translate(0, sens * ((rampant / 2) * Math.cos(pente) - (e / 2) * Math.sin(pente)),
    fleche - (rampant / 2) * Math.sin(pente) - (e / 2) * Math.cos(pente));
  return aplatir(colorer(geometrie, couleur));
}

/** Toit à deux pans, pignons et lanterneau filant, posé sur les murs (z = hauteur). */
function toitDeuxPans(batiment) {
  const { x, y, largeur, profondeur, hauteur, toit: { axe, fleche } } = batiment;
  const [longueur, portee] = axe === "x" ? [largeur, profondeur] : [profondeur, largeur];
  const bout = longueur / 2 - BATIMENT.epaisseurMur / 2;
  const parties = [
    pan(longueur + 2 * BATIMENT.debord, portee, fleche, -1, batiment.couleur),
    pan(longueur + 2 * BATIMENT.debord, portee, fleche, 1, batiment.couleur),
    pignon(portee, fleche, -bout), pignon(portee, fleche, bout),
    bloc([0, 0, fleche + 0.1], [longueur * 0.8, BATIMENT.lanterneau, 0.8],
      COULEURS_BATIMENT.lanterneau),
  ];
  const toit = mergeGeometries(parties);
  if (axe === "y") toit.rotateZ(Math.PI / 2);
  return toit.translate(x + largeur / 2, y + profondeur / 2, hauteur);
}

/** Groupe froid : caisson et deux ventilateurs, posé en (x, y, z), longueur suivant `angle`. */
function groupeFroid({ x, y, z, angle }) {
  const { longueur, largeur, hauteur } = GROUPE_FROID;
  const [ux, uy] = [Math.cos(angle), Math.sin(angle)];
  const cotes = Math.abs(ux) > Math.abs(uy) ? [longueur, largeur, hauteur]
    : [largeur, longueur, hauteur];
  const parties = [bloc([x, y, z + hauteur / 2], cotes, GROUPE_FROID.couleur)];
  for (const s of [-1, 1]) {
    const helice = new CylinderGeometry(largeur * 0.32, largeur * 0.32, 0.12, SEGMENTS_CYLINDRE)
      .rotateX(Math.PI / 2).translate(x + (s * ux * longueur) / 4, y + (s * uy * longueur) / 4,
        z + hauteur + 0.04);
    parties.push(preparer(helice, GROUPE_FROID.ventilateur));
  }
  return parties;
}

/** Toit plat des bureaux (sous l'acrotère), avec ses groupes froids. */
function toitPlat(batiment, groupes) {
  const { x, y, largeur, profondeur, hauteur } = batiment;
  const e = BATIMENT.epaisseurMur;
  const z = hauteur - BATIMENT.acrotere - BATIMENT.epaisseurToit / 2;
  const dalle = bloc([x + largeur / 2, y + profondeur / 2, z],
    [largeur - 2 * e, profondeur - 2 * e, BATIMENT.epaisseurToit], batiment.couleur);
  const dessus = groupes.filter((g) => g.x > x && g.x < x + largeur && g.y > y
    && g.y < y + profondeur);
  return [dalle, ...dessus.flatMap(groupeFroid)];
}

/** Fusion des géométries en une seule, null s'il n'y en a aucune. */
function fusionner(parties) {
  return parties.length ? mergeGeometries(parties) : null;
}

/** Géométries du toit d'un bâtiment (et de ce qui s'y pose). */
function partiesDuToit(batiment, groupes) {
  return batiment.toit.forme === "plat" ? toitPlat(batiment, groupes) : [toitDeuxPans(batiment)];
}

/** Murs et toits de tous les bâtiments, en deux géométries (null sans bâtiment) ; et le toit de
 * chaque bâtiment à part, {nom, geometrie}, pour masquer celui de l'objet sélectionné. Murs
 * percés au droit des portes de marchandises `portes`. */
export function mursEtToits(batiments, groupes, portes = []) {
  return { murs: fusionner(batiments.flatMap((b) => mursDe(b, portes))),
    toits: fusionner(batiments.flatMap((b) => partiesDuToit(b, groupes))),
    toitsSepares: batiments.map((b) => ({ nom: b.nom,
      geometrie: fusionner(partiesDuToit(b, groupes)) })) };
}

/** Repère d'une porte posée au point `point` d'un mur de normale `normale` : place(u, w, z)
 * donne le point à u m le long du mur (vers la droite, vu de dehors), w m devant, z m de haut ;
 * cotes(du, dw, dz) les côtés d'un pavé dans le repère du plan. */
function repereMur(point, normale) {
  const droite = [-normale[1], normale[0]];
  const place = (u, w, z) => [point[0] + u * droite[0] + w * normale[0],
    point[1] + u * droite[1] + w * normale[1], z];
  const cotes = (du, dw, dz) => (Math.abs(normale[1]) > 0 ? [du, dw, dz] : [dw, du, dz]);
  return { droite, place, cotes };
}

/** Porte de quai ouverte : baie sombre, tablier relevé, sas, butoirs, bornes orange. */
function porte({ point, normale }) {
  const { place, cotes } = repereMur(point, normale);
  const { largeur, bas, haut, cadre, sas, borne } = PORTE;
  const c = COULEURS_BATIMENT;
  const parties = [
    bloc(place(0, 0.04, (bas + haut) / 2), cotes(largeur, 0.08, haut - bas), c.baie),
    bloc(place(0, 0.1, haut - 0.25), cotes(largeur, 0.12, 0.5), c.tablier),
    bloc(place(0, sas / 2, haut + cadre / 2), cotes(largeur + 2 * cadre, sas, cadre), c.sas),
  ];
  for (const s of [-1, 1]) {
    parties.push(
      bloc(place(s * (largeur + cadre) / 2, sas / 2, (bas - 0.3 + haut) / 2),
        cotes(cadre, sas, haut - bas + 0.3), c.sas),
      bloc(place(s * (largeur / 2 - 0.35), 0.15, bas - 0.25), cotes(0.3, 0.3, 0.5), c.butoir),
      preparer(new CylinderGeometry(borne.rayon, borne.rayon, borne.hauteur, SEGMENTS_CYLINDRE)
        .rotateX(Math.PI / 2).translate(...place(s * (largeur / 2 + cadre + borne.ecart),
          borne.avancee, borne.hauteur / 2)), c.borne),
    );
  }
  return parties;
}

// Face extérieure des murs (mur centré sur le bord de la zone, soubassement en saillie)
const DEVANT = BATIMENT.epaisseurMur / 2 + BATIMENT.saillie;

/** Repère de la face intérieure du mur d'une porte : même porte, vue du dedans (normale
 * retournée, point sur la face intérieure, la droite vue du dedans). */
function dedans({ point, normale }) {
  const e = BATIMENT.epaisseurMur;
  return { point: [point[0] - normale[0] * e, point[1] - normale[1] * e],
    normale: [-normale[0], -normale[1]] };
}

/** Cadre d'une porte de marchandises sur une face (`face` : repère de la porte) : linteau,
 * montants, socle du gyrophare au-dessus. Le rideau et le gyrophare sont animés à part
 * (PortesMarchandises.jsx). */
function cadreDePorte(face) {
  const { place, cotes } = repereMur(face.point, face.normale);
  const { largeur, hauteur, cadre } = GRANDE_PORTE;
  const c = COULEURS_BATIMENT;
  const parties = [
    bloc(place(0, DEVANT + 0.12, hauteur + cadre / 2), cotes(largeur + 2 * cadre, 0.24, cadre),
      c.sas),
    preparer(new CylinderGeometry(GYROPHARE.rayon * 1.25, GYROPHARE.rayon * 1.25, 0.1,
      SEGMENTS_CYLINDRE).rotateX(Math.PI / 2).translate(...place(0, DEVANT + 0.2,
      hauteur + cadre + 0.05)), GYROPHARE.socle),
  ];
  for (const s of [-1, 1]) {
    parties.push(bloc(place(s * (largeur + cadre) / 2, DEVANT + 0.12, hauteur / 2),
      cotes(cadre, 0.24, hauteur), c.sas));
  }
  return parties;
}

/** Porte de marchandises : cadre et socle du gyrophare dehors et dedans (le mur est percé). */
function grandePorte(porte) {
  return [...cadreDePorte(porte), ...cadreDePorte(dedans(porte))];
}

/** Gyrophares {position [x, y, z], porte} des portes de marchandises : au-dessus du linteau,
 * dehors et dedans. */
export function gyrophares(portes) {
  const z = GRANDE_PORTE.hauteur + GRANDE_PORTE.cadre + 0.1 + GYROPHARE.hauteur / 2;
  return portes.flatMap((porte) => [porte, dedans(porte)].map((face) => ({ porte: porte.id,
    position: repereMur(face.point, face.normale).place(0, DEVANT + 0.2, z) })));
}

/** Rideau {centre [x, y, z] du haut, axe} d'une porte de marchandises : au milieu de
 * l'épaisseur du mur ; `axe` : "x" si le mur suit x. */
export function rideaux(portes) {
  return portes.map((porte) => {
    const { place } = repereMur(porte.point, porte.normale);
    return { porte: porte.id, centre: place(0, -BATIMENT.epaisseurMur / 2, GRANDE_PORTE.hauteur),
      axe: Math.abs(porte.normale[1]) > 0 ? "x" : "y" };
  });
}

/** Rideau à lames d'une porte de marchandises, le haut en z = 0, le long de x (de la largeur
 * de la porte, du sol au linteau). */
export function formeRideau() {
  const { largeur, hauteur, lames, couleur, lame } = GRANDE_PORTE;
  const parties = [bloc([0, 0, -hauteur / 2], [largeur, 0.1, hauteur], couleur)];
  for (let i = 1; i < lames; i++) {
    for (const s of [-1, 1]) {
      parties.push(bloc([0, s * 0.05, -(i * hauteur) / lames], [largeur, 0.03, 0.06], lame));
    }
  }
  return fusionner(parties);
}

/** Porte piétonne sur une face : cadre clair, vantail violet, poignée, auvent (dehors). */
function facePietonne({ point, normale }, auvent) {
  const { place, cotes } = repereMur(point, normale);
  const { largeur, hauteur, cadre, couleur, cadreCouleur, poignee } = PORTE_PIETONNE;
  const parties = [
    bloc(place(0, DEVANT + 0.05, (hauteur + cadre) / 2),
      cotes(largeur + 2 * cadre, 0.1, hauteur + cadre), cadreCouleur),
    bloc(place(0, DEVANT + 0.1, hauteur / 2), cotes(largeur, 0.06, hauteur), couleur),
    bloc(place(largeur * 0.32, DEVANT + 0.17, hauteur * 0.45), cotes(0.08, 0.08, 0.22), poignee),
  ];
  if (auvent) {
    const { auvent: a } = PORTE_PIETONNE;
    parties.push(bloc(place(0, DEVANT + a.avancee / 2, hauteur + 0.45),
      cotes(a.largeur, a.avancee, a.epaisseur), cadreCouleur));
  }
  return parties;
}

/** Porte piétonne, dehors (avec son auvent) et dedans. */
function portePietonne(porte) {
  return [...facePietonne(porte, true), ...facePietonne(dedans(porte), false)];
}

/** Porte de quai vue du dedans : rideau fermé à lames dans son cadre. */
function porteDeQuaiDedans(porte) {
  const { place, cotes } = repereMur(dedans(porte).point, dedans(porte).normale);
  const { largeur, bas, haut, cadre } = PORTE;
  const c = COULEURS_BATIMENT;
  const parties = [
    bloc(place(0, DEVANT + 0.05, (bas + haut) / 2), cotes(largeur, 0.08, haut - bas),
      GRANDE_PORTE.couleur),
    bloc(place(0, DEVANT + 0.1, haut + cadre / 2), cotes(largeur + 2 * cadre, 0.16, cadre),
      c.sas),
  ];
  for (const s of [-1, 1]) {
    parties.push(bloc(place(s * (largeur + cadre) / 2, DEVANT + 0.1, (bas + haut) / 2),
      cotes(cadre, 0.16, haut - bas), c.sas));
  }
  return parties;
}

/** Portes de quai (de tous les quais qui en ont une, vues des deux côtés), cadres des portes de
 * marchandises et portes piétonnes (des deux côtés), en une géométrie (null s'il n'y en a
 * aucune). */
export function portesDesQuais(quais, marchandises = [], pietonnes = []) {
  const deQuai = quais.filter((q) => q.porte);
  return fusionner([...deQuai.flatMap((q) => [...porte(q.porte), ...porteDeQuaiDedans(q.porte)]),
    ...marchandises.flatMap(grandePorte), ...pietonnes.flatMap(portePietonne)]);
}

/** Quadrilatère texturé de centre `centre`, d'axes unitaires `droite` et `haut` (face vers
 * droite × haut), aux coordonnées de texture [u0, v0, u1, v1]. */
function quad(centre, droite, haut, [largeur, hauteur], [u0, v0, u1, v1]) {
  const coin = (s, t) => centre.map((c, k) => c + (s * largeur * droite[k]) / 2
    + (t * hauteur * haut[k]) / 2);
  const [a, b, c, d] = [coin(-1, -1), coin(1, -1), coin(1, 1), coin(-1, 1)];
  const normale = [droite[1] * haut[2] - droite[2] * haut[1],
    droite[2] * haut[0] - droite[0] * haut[2], droite[0] * haut[1] - droite[1] * haut[0]];
  const geometrie = new BufferGeometry();
  geometrie.setAttribute("position", new Float32BufferAttribute([a, b, c, a, c, d].flat(), 3));
  geometrie.setAttribute("normal", new Float32BufferAttribute(Array(6).fill(normale).flat(), 3));
  geometrie.setAttribute("uv", new Float32BufferAttribute([u0, v0, u1, v0, u1, v1, u0, v0, u1,
    v1, u0, v1], 2));
  return geometrie;
}

/** Case (colonne, rangée) d'une planche de `colonnes` × 2 cases en coordonnées de texture. */
function casePlanche(colonne, rangee, colonnes) {
  return [colonne / colonnes, 1 - (rangee + 1) / 2, (colonne + 1) / colonnes, 1 - rangee / 2];
}

/** Plaques numérotées au-dessus des portes (rangée 0 de la planche des numéros) et numéros
 * peints au sol des quais (rangée 1), à l'altitude `zSol`, lisibles depuis le sud. */
export function plaquesEtNumeros(quais, zSol) {
  const colonnes = quais.length;
  const plaques = quais.filter((q) => q.porte).map(({ numero, porte: { point, normale } }) => {
    const { droite, place } = repereMur(point, normale);
    return quad(place(0, 0.12, PORTE.haut + PORTE.cadre + 0.4 + PORTE.plaque[1] / 2),
      [...droite, 0], [0, 0, 1], PORTE.plaque, casePlanche(numero - 1, 0, colonnes));
  });
  const sol = quais.map(({ numero, x, y }) => quad([x, y, zSol], [1, 0, 0], [0, 1, 0],
    [NUMERO_QUAI, NUMERO_QUAI], casePlanche(numero - 1, 1, colonnes)));
  return { plaques: fusionner(plaques), sol: fusionner(sol) };
}

/** Emblèmes posés devant leur mur, en une géométrie (null s'il n'y en a aucun). */
export function emblemes(liste) {
  const quads = liste.map(({ centre, normale, largeur }) => {
    const { droite } = repereMur(centre, normale);
    const devant = [centre[0] + normale[0] * 0.06, centre[1] + normale[1] * 0.06, centre[2]];
    return quad(devant, [...droite, 0], [0, 0, 1], [largeur, largeur / EMBLEME.rapport],
      [0, 0, 1, 1]);
  });
  return fusionner(quads);
}
