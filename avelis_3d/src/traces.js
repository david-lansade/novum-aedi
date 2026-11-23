// Tracés au sol (marquages des routes, bord du foncier, lignes des zones), en coordonnées du plan
// (m) : découpage d'une polyligne en tronçons et en tirets. Chaque morceau est une bande
// {x, y (milieu), longueur, angle (rad, depuis l'est)} ; Site.jsx en fait des pavés plats.
// Aussi : distances aux segments et aux polygones, utiles au décor (decor.js).
// Aucune dépendance à three.js (testé par « npm test »).

const EPSILON = 1e-9;

/** Bande de la portion [debut, fin] (m depuis `a`) du tronçon de `a` à `b`. */
function bande([ax, ay], [bx, by], longueur, debut, fin) {
  const milieu = (debut + fin) / 2 / longueur;
  return { x: ax + (bx - ax) * milieu, y: ay + (by - ay) * milieu, longueur: fin - debut,
    angle: Math.atan2(by - ay, bx - ax) };
}

/** Tronçons non nuls d'une polyligne [[x, y], …], chacun en une bande. */
export function troncons(points) {
  const bandes = [];
  for (let i = 1; i < points.length; i++) {
    const longueur = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
    if (longueur > EPSILON) bandes.push(bande(points[i - 1], points[i], longueur, 0, longueur));
  }
  return bandes;
}

/** Tirets de `trait` m séparés de `vide` m le long de la polyligne. Le motif continue d'un
 * tronçon au suivant : un tiret à cheval sur un sommet est coupé en deux bandes. */
export function tirets(points, trait, vide) {
  const periode = trait + vide;
  const bandes = [];
  let phase = 0; // position dans le motif, de 0 à periode
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    const longueur = Math.hypot(b[0] - a[0], b[1] - a[1]);
    let s = 0;
    while (longueur - s > EPSILON) {
      const dansTrait = phase < trait - EPSILON;
      const pas = Math.min((dansTrait ? trait : periode) - phase, longueur - s);
      if (dansTrait) bandes.push(bande(a, b, longueur, s, s + pas));
      s += pas;
      phase = (phase + pas) % periode;
      if (periode - phase < EPSILON) phase = 0;
    }
  }
  return bandes;
}

/** Polyligne fermée du contour d'un rectangle de coin sud-ouest (x, y). */
export function rectangle(x, y, largeur, profondeur) {
  return [[x, y], [x + largeur, y], [x + largeur, y + profondeur], [x, y + profondeur], [x, y]];
}

/** Polyligne fermée d'un contour [[x, y], …] (le premier point répété à la fin). */
export function fermer(points) {
  return [...points, points[0]];
}

/** Point du segment [a, b] le plus proche de `point`. */
export function procheSurSegment([px, py], [ax, ay], [bx, by]) {
  const [dx, dy] = [bx - ax, by - ay];
  const carre = dx * dx + dy * dy;
  const k = carre > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / carre)) : 0;
  return [ax + k * dx, ay + k * dy];
}

/** Distance de `point` au segment [a, b] (un point si a = b). */
export function distanceAuSegment(point, a, b) {
  const [x, y] = procheSurSegment(point, a, b);
  return Math.hypot(point[0] - x, point[1] - y);
}

/** Vrai si les segments [a, b] et [c, d] se coupent (hors cas alignés). */
function secoupent(a, b, c, d) {
  const cote = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  return cote(a, b, c) * cote(a, b, d) < 0 && cote(c, d, a) * cote(c, d, b) < 0;
}

/** Distance entre les segments [a, b] et [c, d] (0 s'ils se coupent). */
export function distanceEntreSegments(a, b, c, d) {
  if (secoupent(a, b, c, d)) return 0;
  return Math.min(distanceAuSegment(a, c, d), distanceAuSegment(b, c, d),
    distanceAuSegment(c, a, b), distanceAuSegment(d, a, b));
}

/** Point de la polyligne le plus proche de `point`. */
export function pointLePlusProche(polyligne, point) {
  let meilleur = null;
  for (let i = 1; i < polyligne.length; i++) {
    const proche = procheSurSegment(point, polyligne[i - 1], polyligne[i]);
    const ecart = Math.hypot(point[0] - proche[0], point[1] - proche[1]);
    if (meilleur === null || ecart < meilleur.ecart) meilleur = { ecart, proche };
  }
  return meilleur.proche;
}

/** Vrai si `point` est à l'intérieur du polygone [[x, y], …] (règle pair-impair). */
export function dansPolygone([px, py], points) {
  let dedans = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [[xi, yi], [xj, yj]] = [points[i], points[j]];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) dedans = !dedans;
  }
  return dedans;
}

/** Distance de `point` au bord du polygone [[x, y], …]. */
export function distanceAuBord(point, points) {
  const bord = fermer(points);
  let distance = Infinity;
  for (let i = 1; i < bord.length; i++) {
    distance = Math.min(distance, distanceAuSegment(point, bord[i - 1], bord[i]));
  }
  return distance;
}

/** Sens de parcours d'un polygone : 1 s'il tourne dans le sens trigonométrique, −1 sinon. */
export function sensDuPolygone(points) {
  let aire = 0;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    aire += points[j][0] * points[i][1] - points[i][0] * points[j][1];
  }
  return aire >= 0 ? 1 : -1;
}
