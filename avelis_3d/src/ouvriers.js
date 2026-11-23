// Ouvriers dans les bâtiments (décor, ne représentent aucune donnée) : chacun fait sans fin le
// tour de quelques postes de son bâtiment, à pied, et s'arrête à chacun. Absents la nuit
// (Ouvriers.jsx). Tirage à graine fixe.
import { OUVRIERS, PIETON } from "./apparence.js";
import { aleatoire } from "./decor.js";

/** Tronçons {de, vers, angle, longueur, duree, pause} de la boucle fermée de postes `points`
 * (pause tirée, au poste de départ du tronçon). */
function boucle(points, tirage) {
  return points.map((de, i) => {
    const vers = points[(i + 1) % points.length];
    const longueur = Math.hypot(vers[0] - de[0], vers[1] - de[1]);
    return { de, vers, longueur, angle: Math.atan2(vers[1] - de[1], vers[0] - de[0]),
      duree: longueur / OUVRIERS.vitesse,
      pause: OUVRIERS.pauseMin + tirage() * (OUVRIERS.pauseMax - OUVRIERS.pauseMin) };
  });
}

/** Ouvriers {zone, troncons, periode, decalage} des bâtiments (zones couvertes) du site : un
 * par OUVRIERS.surface m², au moins un et au plus OUVRIERS.max par bâtiment ; leurs postes
 * restent à OUVRIERS.marge m des murs. */
export function ouvriersDesBatiments(site, graine) {
  const tirage = aleatoire(graine);
  const m = OUVRIERS.marge;
  const liste = [];
  for (const z of site.zones.filter((zone) => zone.hauteur > 0)) {
    if (z.largeur <= 2 * m || z.profondeur <= 2 * m) continue;
    const nombre = Math.min(OUVRIERS.max, Math.max(1, Math.round(z.largeur * z.profondeur
      / OUVRIERS.surface)));
    for (let k = 0; k < nombre; k++) {
      const points = Array.from({ length: OUVRIERS.etapes }, () => [
        z.x + m + tirage() * (z.largeur - 2 * m), z.y + m + tirage() * (z.profondeur - 2 * m)]);
      const troncons = boucle(points, tirage);
      const periode = troncons.reduce((somme, t) => somme + t.duree + t.pause, 0);
      liste.push({ zone: z.nom, troncons, periode, decalage: tirage() * periode });
    }
  }
  return liste;
}

/** Pose {x, y, angle, phase, marche} d'un ouvrier `secondes` s après le début de la lecture :
 * arrêté à un poste (marche fausse), ou entre deux ; phase : balancement de la marche. */
export function poseOuvrier({ troncons, periode, decalage }, secondes) {
  let s = (((secondes + decalage) % periode) + periode) % periode;
  for (const t of troncons) {
    if (s < t.pause) return { x: t.de[0], y: t.de[1], angle: t.angle, phase: 0, marche: false };
    s -= t.pause;
    if (s < t.duree) {
      const k = s / t.duree;
      return { x: t.de[0] + k * (t.vers[0] - t.de[0]), y: t.de[1] + k * (t.vers[1] - t.de[1]),
        angle: t.angle, phase: (k * t.longueur) / PIETON.foulee, marche: true };
    }
    s -= t.duree;
  }
  const [premier] = troncons;
  return { x: premier.de[0], y: premier.de[1], angle: premier.angle, phase: 0, marche: false };
}
