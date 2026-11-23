// Mode « flux » (Flux.jsx) : chemins les plus empruntés, en traînées d'autant plus épaisses que
// le trafic est fort. Marchandises : chaque trajet (segment en mouvement d'un objet) compte pour
// le couple de zones qu'il relie, dessiné en courbe d'un centre à l'autre. Camions : chaque
// trajet est échantillonné tous les FLUX.pas m et ramené à une grille de FLUX.case m ; chaque
// arête entre deux cases voisines compte une fois par camion qui l'emprunte.
import { FLUX } from "./apparence.js";

/** Cases successives [i, j], sans doublon consécutif, d'une polyligne échantillonnée. */
function casesDuChemin(points) {
  const cases = [];
  const ajouter = ([x, y]) => {
    const c = [Math.round(x / FLUX.case), Math.round(y / FLUX.case)];
    const d = cases.at(-1);
    if (!d || d[0] !== c[0] || d[1] !== c[1]) cases.push(c);
  };
  ajouter(points[0]);
  for (let k = 1; k < points.length; k++) {
    const [a, b] = [points[k - 1], points[k]];
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / FLUX.pas);
    for (let m = 1; m <= n; m++) {
      ajouter([a[0] + ((b[0] - a[0]) * m) / n, a[1] + ((b[1] - a[1]) * m) / n]);
    }
  }
  return cases;
}

/** Zone qui contient le point (la plus petite s'il y en a plusieurs), ou null. */
function zoneDuPoint(zones, [x, y]) {
  const dedans = zones.filter((z) => x >= z.x && x <= z.x + z.largeur && y >= z.y
    && y <= z.y + z.profondeur);
  return dedans.sort((p, q) => p.largeur * p.profondeur - q.largeur * q.profondeur)[0] ?? null;
}

/** Centre d'une zone. */
const centreDe = (z) => [z.x + z.largeur / 2, z.y + z.profondeur / 2];

/** Courbe de a à b (FLUX.points points), bombée vers la droite du sens de a vers b de
 * FLUX.bombe fois leur distance : deux flux opposés ne se recouvrent pas. */
function courbe([ax, ay], [bx, by]) {
  const [mx, my] = [(ax + bx) / 2 + (by - ay) * FLUX.bombe, (ay + by) / 2 - (bx - ax)
    * FLUX.bombe];
  return Array.from({ length: FLUX.points + 1 }, (_, k) => {
    const u = k / FLUX.points;
    return [(1 - u) ** 2 * ax + 2 * u * (1 - u) * mx + u * u * bx,
      (1 - u) ** 2 * ay + 2 * u * (1 - u) * my + u * u * by];
  });
}

/** Flux de zone à zone des objets (hors camions) : [{de, vers, trafic, part, points}], un par
 * couple de zones relié par au moins FLUX.traficMin trajets ; `points` : courbe entre leurs
 * centres. */
function fluxDesObjets(objets, zones) {
  const couples = new Map();
  for (const objet of objets.filter((o) => o.type !== "camion")) {
    for (const [, , points] of objet.segments) {
      if (points.length < 2) continue;
      const [de, vers] = [zoneDuPoint(zones, points[0]), zoneDuPoint(zones, points.at(-1))];
      if (!de || !vers || de === vers) continue;
      const cle = `${de.nom}→${vers.nom}`;
      const couple = couples.get(cle) ?? { de, vers, trafic: 0 };
      couple.trafic += 1;
      couples.set(cle, couple);
    }
  }
  const gardes = [...couples.values()].filter((c) => c.trafic >= FLUX.traficMin);
  const max = Math.max(1, ...gardes.map((c) => c.trafic));
  return gardes.map(({ de, vers, trafic }) => ({ de: de.nom, vers: vers.nom, trafic,
    part: trafic / max, points: courbe(centreDe(de), centreDe(vers)) }));
}

/** Traînées des camions : arêtes de la grille [{a, b, trafic, part}], empruntées par au
 * moins FLUX.traficMin camions (ils suivent les routes, que la grille épouse). */
function fluxDesCamions(objets) {
  const aretes = new Map();
  for (const objet of objets.filter((o) => o.type === "camion")) {
    const vues = new Set();
    for (const [, , points] of objet.segments) {
      if (points.length < 2) continue;
      const cases = casesDuChemin(points);
      for (let k = 1; k < cases.length; k++) {
        const [p, q] = [cases[k - 1], cases[k]].sort((u, v) => u[0] - v[0] || u[1] - v[1]);
        const cle = `${p}|${q}`;
        if (vues.has(cle)) continue;
        vues.add(cle);
        const arete = aretes.get(cle) ?? { p, q, trafic: 0 };
        arete.trafic += 1;
        aretes.set(cle, arete);
      }
    }
  }
  const gardees = [...aretes.values()].filter((a) => a.trafic >= FLUX.traficMin);
  const max = Math.max(1, ...gardees.map((a) => a.trafic));
  return gardees.map(({ p, q, trafic }) => ({ a: [p[0] * FLUX.case, p[1] * FLUX.case],
    b: [q[0] * FLUX.case, q[1] * FLUX.case], trafic, part: trafic / max }));
}

/** Traînées du flux {objets, camions} : flux de zone à zone des marchandises (fluxDesObjets)
 * et chemins des camions (fluxDesCamions), chacun rapporté à son plus fort trafic, pour que la
 * voirie ne noie pas le flux de production. */
export function trainees(objets, site) {
  return { objets: fluxDesObjets(objets, site.zones), camions: fluxDesCamions(objets) };
}

/** Largeur (m) d'une traînée de part `part` : de FLUX.largeurMin à FLUX.largeurMax, en racine
 * carrée de la part (les faibles trafics restent visibles). */
export function largeurTrainee(part) {
  return FLUX.largeurMin + (FLUX.largeurMax - FLUX.largeurMin) * Math.sqrt(part);
}
