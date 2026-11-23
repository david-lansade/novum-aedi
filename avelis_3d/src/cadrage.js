// Cadrage de la caméra orthographique, en coordonnées du plan (x vers l'est, y vers le nord,
// z vers le haut, en mètres). Aucune dépendance à three.js (testé par « npm test »).
//
// La caméra est repérée autour de sa cible par un azimut (rad, depuis l'est vers le nord : la
// direction où elle se trouve) et une élévation (rad, au-dessus du sol). En projection
// orthographique, un point se projette à l'écran par ses composantes sur les axes « droite » et
// « haut » de l'écran ; le zoom est le nombre de pixels par mètre.

/** Produit scalaire de deux vecteurs [x, y, z]. */
function scalaire(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/** Vecteur unitaire de la cible vers la caméra. */
export function directionCamera(azimut, elevation) {
  const horizontal = Math.cos(elevation);
  return [horizontal * Math.cos(azimut), horizontal * Math.sin(azimut), Math.sin(elevation)];
}

/** Direction de la caméra et axes unitaires de l'écran {direction, droite, haut} ; « haut » est
 * le produit vectoriel de « droite » et de la visée (−direction). */
export function axesEcran(azimut, elevation) {
  const [ca, sa, ce, se] = [Math.cos(azimut), Math.sin(azimut), Math.cos(elevation),
    Math.sin(elevation)];
  return { direction: directionCamera(azimut, elevation), droite: [-sa, ca, 0],
    haut: [-se * ca, -se * sa, ce] };
}

/** Position à l'écran {x, y} (pixels depuis le coin haut gauche) d'un point du plan, pour une
 * caméra {cible, zoom} et une fenêtre de `largeur` × `hauteur` px. */
export function projeter(point, { cible, zoom }, axes, largeur, hauteur) {
  const relatif = point.map((c, k) => c - cible[k]);
  return { x: largeur / 2 + scalaire(relatif, axes.droite) * zoom,
    y: hauteur / 2 - scalaire(relatif, axes.haut) * zoom };
}

/** Cadrage des `points` [x, y, z] vus sous (azimut, élévation), dans une fenêtre de `largeur` ×
 * `hauteur` px dont les `marges` {haut, bas, gauche, droite} (px) sont couvertes par des
 * panneaux : les points occupent la part `remplissage` de la zone libre, centrés dedans.
 * Renvoie {cible (au sol), position (à `rayon` m de la cible), zoom (px par mètre)}. */
export function cadrer({ points, azimut, elevation, largeur, hauteur, marges, rayon,
  remplissage }) {
  const { direction, droite, haut } = axesEcran(azimut, elevation);
  const us = points.map((p) => scalaire(p, droite));
  const vs = points.map((p) => scalaire(p, haut));
  const [umin, umax, vmin, vmax] = [Math.min(...us), Math.max(...us), Math.min(...vs),
    Math.max(...vs)];
  const libre = [largeur - marges.gauche - marges.droite, hauteur - marges.haut - marges.bas];
  const zoom = remplissage * Math.min(libre[0] / Math.max(umax - umin, 1e-6),
    libre[1] / Math.max(vmax - vmin, 1e-6));
  // Centre des points, décalé pour qu'il tombe au centre de la zone libre et non de la fenêtre
  const u = (umin + umax) / 2 - (marges.gauche - marges.droite) / 2 / zoom;
  const v = (vmin + vmax) / 2 - (marges.bas - marges.haut) / 2 / zoom;
  const centre = droite.map((c, k) => u * c + v * haut[k]);
  // Ramené au sol le long de la visée : sans effet à l'écran en projection orthographique
  const descente = centre[2] / direction[2];
  const cible = centre.map((c, k) => c - descente * direction[k]);
  return { cible, position: cible.map((c, k) => c + rayon * direction[k]), zoom };
}

/** Coins [x, y, z] d'une zone, au sol et à sa hauteur. */
function coinsDeZone({ x, y, largeur, profondeur, hauteur }) {
  const coins = [[x, y], [x + largeur, y], [x, y + profondeur], [x + largeur, y + profondeur]];
  return [0, hauteur].flatMap((z) => coins.map(([px, py]) => [px, py, z]));
}

/** Points du site entier (vue de dessus) : sommets des contours du foncier, coins des zones. */
export function pointsDuSite(site) {
  return [...site.contours.flatMap((contour) => contour.points.map(([x, y]) => [x, y, 0])),
    ...site.zones.flatMap(coinsDeZone)];
}

/** Coins des bâtiments (zones couvertes) ; le site entier s'il n'a aucun bâtiment. */
export function pointsDesBatiments(site) {
  const batiments = site.zones.filter((zone) => zone.hauteur > 0);
  return batiments.length ? batiments.flatMap(coinsDeZone) : pointsDuSite(site);
}

/** Points de la vue d'ensemble : coins des bâtiments et chemin des camions (voirie, bretelles,
 * accès au portail, portail).
 * Plus resserrée que le foncier entier, elle montre le site d'assez près, sans laisser hors
 * champ l'entrée des camions (portail à l'est, loin des bâtiments dans l'implantation
 * actuelle). */
export function pointsVueEnsemble(site) {
  const chemin = [...site.voirie, ...site.bretelles.flat(), ...site.acces, site.portail]
    .map(([x, y]) => [x, y, 0]);
  return [...pointsDesBatiments(site), ...chemin];
}

/** Centre [x, y] de la boîte des bâtiments, au sol. */
export function centreDesBatiments(site) {
  const points = pointsDesBatiments(site);
  return [0, 1].map((k) => {
    const valeurs = points.map((p) => p[k]);
    return (Math.min(...valeurs) + Math.max(...valeurs)) / 2;
  });
}

// Pixels couverts par les cartes autour de la vue d'ensemble : barre du haut et indicateurs,
// curseur de temps, colonne de droite et commandes de la vue (style.css, --reserve-droite)
export const MARGES_CARTES = { haut: 172, bas: 84, gauche: 16, droite: 356 };
// Vue d'ensemble : caméra au sud-ouest du site, 35° au-dessus du sol (le nord-est en haut de
// l'écran) ; les points cadrés occupent cette part de la zone libre
export const VUE_ENSEMBLE = { azimut: (225 * Math.PI) / 180, elevation: (35 * Math.PI) / 180 };
export const REMPLISSAGE = 0.94;

/** Azimut, élévation et distance {azimut, elevation, rayon} d'une caméra placée en `position`
 * autour de `cible` (coordonnées du plan). */
export function orientation(position, cible) {
  const [dx, dy, dz] = position.map((c, k) => c - cible[k]);
  const rayon = Math.hypot(dx, dy, dz);
  return { azimut: Math.atan2(dy, dx), elevation: Math.asin(dz / rayon), rayon };
}

/** Angle de `de` à `vers` (rad) par le plus court chemin, entre −π et π. */
export function ecartAngulaire(de, vers) {
  const ecart = (vers - de) % (2 * Math.PI);
  if (ecart > Math.PI) return ecart - 2 * Math.PI;
  if (ecart < -Math.PI) return ecart + 2 * Math.PI;
  return ecart;
}
