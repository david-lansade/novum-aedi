// Calcul du curseur de temps (Commandes.jsx) : instant sous le pointeur, et réglage fin quand on
// le maintient appuyé sans bouger (CURSEUR_FIN d'apparence.js).
import { CURSEUR_FIN } from "./apparence.js";

/** Borne t entre 0 et `duree`, arrondi à la minute. */
function borner(t, duree) {
  return Math.max(0, Math.min(duree, Math.round(t)));
}

/** Instant sous le pointeur à `x` px du bord gauche d'un curseur de `largeur` px : le centre du
 * pouce va de pouce / 2 à largeur − pouce / 2, comme les repères sous le curseur. */
export function instantAuPointeur(x, largeur, duree, pouce = CURSEUR_FIN.pouce) {
  const utile = Math.max(1, largeur - pouce);
  return borner(((x - pouce / 2) / utile) * duree, duree);
}

/** Réglage fin : instant `tDepart` décalé de `dx` px du point où il a commencé, à
 * CURSEUR_FIN.minutesParPixel min par pixel. */
export function instantFin(tDepart, dx, duree) {
  return borner(tDepart + dx * CURSEUR_FIN.minutesParPixel, duree);
}

/** Vrai si le pointeur, parti de x0, est resté assez immobile pour passer en réglage fin. */
export function immobile(x0, x) {
  return Math.abs(x - x0) <= CURSEUR_FIN.tolerance;
}
