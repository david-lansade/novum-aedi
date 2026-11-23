// Déplacement au clavier dans la vue 3D. Les touches sont lues à leur place sur le clavier
// (event.code, nommé d'après un clavier QWERTY) : Z Q S D sur un clavier AZERTY sont W A S D sur
// un clavier QWERTY. Z et S avancent et reculent dans le sens où regarde la caméra, Q et D vont à
// gauche et à droite de l'écran ; les flèches aussi ; A et E tournent la vue ; Maj va plus vite.
// Coordonnées du plan (x vers l'est, y vers le nord). Aucune dépendance (testé par « npm test »).
import { NAVIGATION } from "./apparence.js";

/** Action de chaque touche, par sa place (event.code). */
export const TOUCHES = {
  KeyW: "avant", ArrowUp: "avant", KeyS: "arriere", ArrowDown: "arriere",
  KeyA: "gauche", ArrowLeft: "gauche", KeyD: "droite", ArrowRight: "droite",
  KeyQ: "tournerGauche", KeyE: "tournerDroite",
  ShiftLeft: "rapide", ShiftRight: "rapide",
};
const FLECHES = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
const SAISIES = new Set(["TEXTAREA", "SELECT"]); // gardent toutes les touches
const ENTREES_SANS_SAISIE = new Set(["checkbox", "radio", "button", "submit", "reset", "range"]);

/** Actions demandées par les touches enfoncées (ensemble de event.code). */
export function actionsDe(touches) {
  return new Set([...touches].map((code) => TOUCHES[code]).filter(Boolean));
}

/** Direction [x, y] du déplacement au sol demandé (longueur 1, ou nulle), pour une caméra
 * d'azimut donné (rad, direction où elle se trouve vue de sa cible, cadrage.js). */
export function directionAuSol(actions, azimut) {
  const avant = [-Math.cos(azimut), -Math.sin(azimut)]; // de la caméra vers sa cible
  const droite = [-Math.sin(azimut), Math.cos(azimut)]; // axe « droite » de l'écran
  const a = (actions.has("avant") ? 1 : 0) - (actions.has("arriere") ? 1 : 0);
  const d = (actions.has("droite") ? 1 : 0) - (actions.has("gauche") ? 1 : 0);
  const [x, y] = [a * avant[0] + d * droite[0], a * avant[1] + d * droite[1]];
  const longueur = Math.hypot(x, y);
  return longueur > 0 ? [x / longueur, y / longueur] : [0, 0];
}

/** Direction [x, y] de la marche à la première personne (longueur 1, ou nulle), pour un
 * regard de cap `lacet` (rad, depuis l'est vers le nord) : Z avance, S recule, Q et D vont de
 * côté. */
export function directionDeMarche(actions, lacet) {
  const avant = [Math.cos(lacet), Math.sin(lacet)];
  const droite = [Math.sin(lacet), -Math.cos(lacet)];
  const a = (actions.has("avant") ? 1 : 0) - (actions.has("arriere") ? 1 : 0);
  const d = (actions.has("droite") ? 1 : 0) - (actions.has("gauche") ? 1 : 0);
  const [x, y] = [a * avant[0] + d * droite[0], a * avant[1] + d * droite[1]];
  const longueur = Math.hypot(x, y);
  return longueur > 0 ? [x / longueur, y / longueur] : [0, 0];
}

/** Sens de rotation demandé : −1 vers la gauche, 1 vers la droite (comme les quarts de tour
 * des commandes de la vue), 0 sinon. */
export function sensRotation(actions) {
  return (actions.has("tournerDroite") ? 1 : 0) - (actions.has("tournerGauche") ? 1 : 0);
}

/** Vitesse au sol (m/s) : la largeur visible de la vue (`largeurPx` px à `zoom` px par m) en
 * NAVIGATION.traversee s, NAVIGATION.rapide fois plus avec Maj. */
export function vitesseAuSol(largeurPx, zoom, rapide) {
  return (largeurPx / zoom / NAVIGATION.traversee) * (rapide ? NAVIGATION.rapide : 1);
}

/** Vrai si la touche revient à l'élément qui a le focus : zone de saisie ou liste déroulante
 * (toutes les touches), curseur (les flèches) ; un bouton ou une case n'en garde aucune. */
export function toucheReservee(code, element) {
  if (!element) return false;
  if (element.isContentEditable || SAISIES.has(element.tagName)) return true;
  if (element.tagName !== "INPUT") return false;
  const type = (element.type ?? "text").toLowerCase();
  if (type === "range") return FLECHES.has(code);
  return !ENTREES_SANS_SAISIE.has(type);
}

/** Déplacement [dx, dy] de la cible, en [x, y], ramené pour qu'elle ne s'éloigne pas à plus de
 * NAVIGATION.bord × étendue du centre du site (cadre {cx, cy, etendue}), axe par axe. Si la
 * souris l'a déjà menée au-delà, elle peut revenir, pas s'éloigner davantage. */
export function bornerDeplacement([dx, dy], [x, y], { cx, cy, etendue }) {
  const bord = NAVIGATION.bord * etendue;
  const borner = (v, d, c) => {
    const suivant = v + d;
    if (Math.abs(suivant - c) <= bord || Math.abs(suivant - c) <= Math.abs(v - c)) return d;
    return Math.abs(v - c) >= bord ? 0 : c + Math.sign(suivant - c) * bord - v;
  };
  return [borner(x, dx, cx), borner(y, dy, cy)];
}

/** Valeur qui tend vers `cible` avec une constante de temps NAVIGATION.inertie, après
 * `secondes` s : la vitesse monte et baisse en douceur. */
export function approcher(valeur, cible, secondes) {
  return cible + (valeur - cible) * Math.exp(-secondes / NAVIGATION.inertie);
}
