// Ce que la vue 3D tire de la scène pour dessiner les objets : forme de chaque objet, roues des
// camions, modules chargés sur les camions d'expédition et leur place sur le plateau, chariots
// élévateurs qui portent les marchandises en route. Aucune
// dépendance à three.js (testé par « npm test ») ; les formes elles-mêmes sont dans
// formesVehicules.js et formesCharges.js.
import { CAMION, CHARIOT, CHARIOT_PORTEUR } from "./apparence.js";
import { segmentActif } from "./donnees.js";

const PREFIXE_EXPEDITION = "EXP-"; // camions d'expédition (ARCHITECTURE_DONNEES.md, identifiants)
const FORMES = { lot: "palettes", "kit 2D": "panneaux", pod: "pod" };
const PRECISION_INSTANT = 1e6; // instants comparés au millionième de minute

/** Forme d'un objet, à laquelle se lit son type (choix validé 7) : camion fournisseur en
 * fourgon, camion d'expédition en plateau surbaissé ; ce qui sort de l'assemblage est un module
 * 3D, ou un kit module en schéma « satellites ». */
export function formeObjet({ id, type }, schema) {
  if (type === "camion") return id.startsWith(PREFIXE_EXPEDITION) ? "plateau" : "fourgon";
  if (type === "module") return schema === "satellites" ? "kit module" : "module";
  return FORMES[type];
}

/** Roues {x, y, rayon, largeur} d'un camion de gabarit [largeur, longueur], dans son repère :
 * essieu avant simple, essieu moteur et essieux de remorque jumelés (une roue jumelée est
 * deux fois plus large) ; petites roues sous le plateau surbaissé. */
export function rouesDe(forme, [largeur, longueur]) {
  const { roue, essieux, cabine } = CAMION;
  const avant = longueur / 2;
  const rayonRemorque = forme === "plateau" ? roue.petite : roue.rayon;
  const liste = [
    { x: avant - essieux.avant, rayon: roue.rayon, jumelee: false },
    { x: avant - cabine.longueur - essieux.moteur, rayon: roue.rayon, jumelee: true },
    ...essieux.remorque.map((d) => ({ x: d - avant, rayon: rayonRemorque, jumelee: true })),
  ];
  return liste.flatMap(({ x, rayon, jumelee }) => {
    const l = roue.largeur * (jumelee ? 2 : 1);
    return [-1, 1].map((s) => ({ x, y: s * (largeur / 2 - l / 2), rayon, largeur: l }));
  });
}

/** Instant où un camion quitte le quai : fin de son dernier arrêt suivi d'un trajet ; null s'il
 * ne repart pas dans la scène. */
function departDuQuai({ segments }) {
  for (let i = segments.length - 2; i >= 0; i--) {
    const [, fin, chemin] = segments[i];
    if (chemin.length === 1 && segments[i + 1][2].length > 1 && fin !== null) return fin;
  }
  return null;
}

/** Clé d'un instant, pour comparer deux instants calculés par la simulation. */
const cleInstant = (t) => Math.round(t * PRECISION_INSTANT);

/** Modules chargés sur chaque camion d'expédition : Map id du camion → {depart, modules}, les
 * modules (id) dont la présence s'arrête à l'instant où le camion quitte le quai (choix validé
 * 3 : déduit de la scène, rien d'inventé). Un module encore présent à la fin n'est sur aucun. */
export function chargementsDesCamions(objets) {
  const departs = new Map();
  for (const objet of objets) {
    if (objet.type !== "camion" || formeObjet(objet) !== "plateau") continue;
    const depart = departDuQuai(objet);
    if (depart !== null) departs.set(cleInstant(depart), { camion: objet.id, depart });
  }
  const chargements = new Map();
  for (const objet of objets) {
    const fin = objet.type === "module" ? objet.segments.at(-1)?.[1] : null;
    const depart = fin == null ? undefined : departs.get(cleInstant(fin));
    if (!depart) continue;
    if (!chargements.has(depart.camion)) {
      chargements.set(depart.camion, { depart: depart.depart, modules: [] });
    }
    chargements.get(depart.camion).modules.push(objet.id);
  }
  return chargements;
}

/** Vrai si l'objet est une marchandise (CHARIOT_PORTEUR.types) qui roule à l'instant t : un
 * chariot élévateur la porte (aux mêmes instants que son trajet dans la scène). */
export function enTransport(objet, t) {
  if (!CHARIOT_PORTEUR.types.includes(objet.type)) return false;
  const i = segmentActif(objet, t);
  return i >= 0 && objet.segments[i][2].length > 1;
}

/** Pose {x, y, cap} du chariot qui porte une charge de longueur `longueur` posée en
 * {x, y, cap} : derrière elle dans le sens de la marche, ses fourches sous son arrière. */
export function poseDuPorteur({ x, y, cap }, longueur) {
  const recul = longueur / 2 + CHARIOT.longueur / 2 - CHARIOT.fourches;
  return { x: x - recul * Math.cos(cap), y: y - recul * Math.sin(cap), cap };
}

/** Plus grand nombre de marchandises en route au même instant : chariots porteurs à dessiner.
 * Un trajet finit à son t1 (exclu), avant qu'un autre ne commence au même instant. */
export function transportsSimultanes(objets) {
  const bornes = [];
  for (const objet of objets) {
    if (!CHARIOT_PORTEUR.types.includes(objet.type)) continue;
    for (const [t0, t1, chemin] of objet.segments) {
      if (chemin.length > 1) bornes.push([t0, 1], [t1 ?? Infinity, -1]);
    }
  }
  bornes.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let [enCours, plus] = [0, 0];
  for (const [, pas] of bornes) {
    enCours += pas;
    plus = Math.max(plus, enCours);
  }
  return plus;
}

/** Partie libre [début, fin] (x, repère du camion) du plateau surbaissé d'un camion de longueur
 * `longueur` : de l'arrière au col de cygne, moins un jeu à chaque bout ; dessus à
 * CAMION.plateau.haut. */
export function plateauLibre(longueur) {
  const { cabine, ecart, plateau } = CAMION;
  const col = longueur / 2 - cabine.longueur - ecart - plateau.col;
  return [-longueur / 2 + plateau.jeu, col - plateau.jeu];
}

/** Places {x, z} (repère du camion) de `nombre` charges de longueur `longueurCharge` et de
 * hauteur `hauteurCharge` sur le plateau : en rang, autant que le plateau en tient, chacune au
 * milieu de sa part ; puis en couches. */
export function placesDeCharge(nombre, [, longueurCharge, hauteurCharge], longueur) {
  const [debut, fin] = plateauLibre(longueur);
  const parCouche = Math.max(1, Math.floor((fin - debut) / longueurCharge));
  return Array.from({ length: nombre }, (_, i) => {
    const couche = Math.floor(i / parCouche);
    const dansCouche = Math.min(parCouche, nombre - couche * parCouche);
    const pas = (fin - debut) / dansCouche;
    return { x: debut + ((i % parCouche) + 0.5) * pas,
      z: CAMION.plateau.haut + couche * hauteurCharge };
  });
}
