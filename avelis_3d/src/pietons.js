// Employés à pied (décor, ne représentent aucune donnée) : chaque conducteur qui se gare au
// parking VL (circulation.js) va à pied à une porte du personnel, et en revient le soir, par
// des chemins qui contournent les bâtiments (recherche A* sur une grille du site). Au temps
// simulé, comme les voitures.
import { CATEGORIE_BUREAUX, PARKING_VL, PERSONNEL, PIETON } from "./apparence.js";
import { portesPietonnes } from "./batiments.js";
import { circulationDuJour, dureeAller } from "./circulation.js";

const SECONDES_PAR_MINUTE = 60;

const DIAGONALE = Math.SQRT2;
const VOISINS = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, DIAGONALE],
  [1, -1, DIAGONALE], [-1, 1, DIAGONALE], [-1, -1, DIAGONALE]];

/** Grille du site {x0, y0, colonnes, rangees, bloquee(i, j)} : cases de PIETON.case m, bloquées
 * dans les bâtiments (zones couvertes élargies de PIETON.marge m). */
export function grilleDuSite(site) {
  const c = PIETON.case;
  const zones = site.zones.filter((zone) => zone.hauteur > 0);
  const rects = [...site.zones, site.parking_vl].filter(Boolean);
  const x0 = Math.min(...rects.map((r) => r.x)) - PIETON.bord;
  const y0 = Math.min(...rects.map((r) => r.y)) - PIETON.bord;
  const colonnes = Math.ceil((Math.max(...rects.map((r) => r.x + r.largeur)) + PIETON.bord - x0)
    / c);
  const rangees = Math.ceil((Math.max(...rects.map((r) => r.y + r.profondeur)) + PIETON.bord
    - y0) / c);
  const bloque = new Uint8Array(colonnes * rangees);
  const m = PIETON.marge;
  for (const z of zones) {
    for (let i = Math.floor((z.x - m - x0) / c); i <= (z.x + z.largeur + m - x0) / c; i++) {
      for (let j = Math.floor((z.y - m - y0) / c); j <= (z.y + z.profondeur + m - y0) / c; j++) {
        if (i >= 0 && j >= 0 && i < colonnes && j < rangees) bloque[j * colonnes + i] = 1;
      }
    }
  }
  return { x0, y0, colonnes, rangees,
    bloquee: (i, j) => i < 0 || j < 0 || i >= colonnes || j >= rangees
      || bloque[j * colonnes + i] === 1 };
}

/** Case [i, j] d'un point. */
function caseDe(grille, [x, y]) {
  return [Math.floor((x - grille.x0) / PIETON.case), Math.floor((y - grille.y0) / PIETON.case)];
}

/** Centre [x, y] d'une case. */
function centreDe(grille, [i, j]) {
  return [grille.x0 + (i + 0.5) * PIETON.case, grille.y0 + (j + 0.5) * PIETON.case];
}

/** Tas binaire minimal de [priorité, valeur] : ajouter, retirer le plus petit. */
function creerTas() {
  const t = [];
  const echanger = (a, b) => { [t[a], t[b]] = [t[b], t[a]]; };
  return {
    taille: () => t.length,
    ajouter(element) {
      t.push(element);
      for (let k = t.length - 1; k > 0 && t[(k - 1) >> 1][0] > t[k][0]; k = (k - 1) >> 1) {
        echanger(k, (k - 1) >> 1);
      }
    },
    retirer() {
      const haut = t[0];
      const dernier = t.pop();
      if (t.length) {
        t[0] = dernier;
        for (let k = 0; ;) {
          const [g, d] = [2 * k + 1, 2 * k + 2];
          let m = k;
          if (g < t.length && t[g][0] < t[m][0]) m = g;
          if (d < t.length && t[d][0] < t[m][0]) m = d;
          if (m === k) break;
          echanger(k, m);
          k = m;
        }
      }
      return haut;
    },
  };
}

/** Plus court chemin de cases (8 voisins, sans couper le coin d'un bâtiment) de `de` à `vers`,
 * ou null ; recherche A* à heuristique octile. */
export function rechercheAEtoile(grille, de, vers) {
  const cle = ([i, j]) => j * grille.colonnes + i;
  const estimer = ([i, j]) => {
    const [dx, dy] = [Math.abs(i - vers[0]), Math.abs(j - vers[1])];
    return Math.max(dx, dy) + (DIAGONALE - 1) * Math.min(dx, dy);
  };
  const couts = new Map([[cle(de), 0]]);
  const parents = new Map();
  const ouverts = creerTas();
  ouverts.ajouter([estimer(de), de]);
  if (grille.bloquee(...vers)) return null;
  while (ouverts.taille()) {
    const [, courante] = ouverts.retirer();
    if (courante[0] === vers[0] && courante[1] === vers[1]) {
      const chemin = [courante];
      while (parents.has(cle(chemin[0]))) chemin.unshift(parents.get(cle(chemin[0])));
      return chemin;
    }
    for (const [di, dj, pas] of VOISINS) {
      const voisine = [courante[0] + di, courante[1] + dj];
      if (grille.bloquee(...voisine)) continue;
      if (di && dj && (grille.bloquee(courante[0] + di, courante[1])
        || grille.bloquee(courante[0], courante[1] + dj))) continue;
      const cout = couts.get(cle(courante)) + pas;
      if (cout >= (couts.get(cle(voisine)) ?? Infinity)) continue;
      couts.set(cle(voisine), cout);
      parents.set(cle(voisine), courante);
      ouverts.ajouter([cout + estimer(voisine), voisine]);
    }
  }
  return null;
}

/** Vrai si le segment [a, b] ne traverse aucune case bloquée (pas d'un quart de case). */
function aVue(grille, a, b) {
  const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / (PIETON.case / 4));
  for (let k = 0; k <= n; k++) {
    const p = [a[0] + ((b[0] - a[0]) * k) / (n || 1), a[1] + ((b[1] - a[1]) * k) / (n || 1)];
    if (grille.bloquee(...caseDe(grille, p))) return false;
  }
  return true;
}

/** Polyligne simplifiée : depuis chaque sommet gardé, le plus lointain encore en vue. */
function simplifier(grille, points) {
  const gardes = [points[0]];
  let k = 0;
  while (k < points.length - 1) {
    let suivant = k + 1;
    for (let m = points.length - 1; m > k + 1; m--) {
      if (aVue(grille, points[k], points[m])) { suivant = m; break; }
    }
    gardes.push(points[suivant]);
    k = suivant;
  }
  return gardes;
}

/** Point du rectangle {x, y, largeur, profondeur} le plus proche de p. */
function plusProche({ x, y, largeur, profondeur }, [px, py]) {
  return [Math.max(x, Math.min(x + largeur, px)), Math.max(y, Math.min(y + profondeur, py))];
}

/** Chemins à pied {porte, points} de chaque porte piétonne au bord le plus proche du parking
 * VL : sortie de PIETON.sortie m devant la porte, puis contour des bâtiments ; [] sans parking
 * VL. Une porte sans chemin est laissée de côté. */
export function cheminsAPied(site) {
  if (!site.parking_vl) return [];
  const grille = grilleDuSite(site);
  return portesPietonnes(site).flatMap((porte) => {
    const [px, py] = porte.point;
    const [nx, ny] = porte.normale;
    const dehors = [px + nx * PIETON.sortie, py + ny * PIETON.sortie];
    const arrivee = plusProche(site.parking_vl, dehors);
    const cases = rechercheAEtoile(grille, caseDe(grille, dehors), caseDe(grille, arrivee));
    if (!cases) return [];
    const milieu = cases.slice(1, -1).map((c) => centreDe(grille, c));
    return [{ porte, points: [porte.point, dehors, ...simplifier(grille, [dehors, ...milieu,
      arrivee]).slice(1)] }];
  });
}

/** Polyligne de la place de parking à la porte (`vers` porte) ou inverse. */
function trajet(chemin, place, versPorte) {
  const { profondeur: p, allee } = PARKING_VL;
  const yAllee = place.y + Math.sin(place.angle) * (p / 2 + allee / 2);
  const cote = [...chemin.points, [chemin.points.at(-1)[0], yAllee], [place.x, yAllee],
    [place.x, place.y]];
  return versPorte ? cote.reverse() : cote;
}

/** Polyligne {points, longueurs} et sa longueur cumulée. */
function polyligne(points) {
  const longueurs = [0];
  for (let i = 1; i < points.length; i++) {
    longueurs.push(longueurs[i - 1] + Math.hypot(points[i][0] - points[i - 1][0],
      points[i][1] - points[i - 1][1]));
  }
  return { points, longueurs };
}

/** Chemins à pied possibles d'un séjour : vers les bureaux (s'il y en a) pour les visiteurs et
 * le personnel des bureaux, sinon vers les ateliers. */
function cheminsDuSejour(sejour, chemins, bureaux) {
  const vers = chemins.filter((c) => bureaux.has(c.porte.zone) === sejour.bureaux);
  return vers.length ? vers : chemins;
}

/** Marches du jour {id, points, longueurs, debut (t)} : chaque conducteur garé descend de sa
 * voiture PERSONNEL.descente min après s'être garé et va à pied à une porte du personnel ; au
 * départ, il sort par la même porte et arrive à sa voiture PERSONNEL.descente min avant
 * qu'elle reparte. Pas de marche pour les permanents. Gardées dans `circulation.marches`. */
export function marchesDuJour(circulation, chemins, jour) {
  circulation.marches ??= new Map();
  if (circulation.marches.has(jour)) return circulation.marches.get(jour);
  const bureaux = new Set(circulation.site.zones.filter((z) => z.categorie === CATEGORIE_BUREAUX)
    .map((z) => z.nom));
  const marches = [];
  const vitesse = PIETON.vitesse * SECONDES_PAR_MINUTE; // m par minute simulée
  const { sejours } = circulationDuJour(circulation, jour);
  sejours.forEach((sejour, k) => {
    if (!Number.isFinite(sejour.arrivee) || !chemins.length) return;
    const possibles = cheminsDuSejour(sejour, chemins, bureaux);
    const chemin = possibles[(sejour.place + k) % possibles.length];
    const place = circulation.places[sejour.place];
    const vers = polyligne(trajet(chemin, place, true));
    marches.push({ id: `${sejour.id}-a`, ...vers,
      debut: sejour.arrivee + dureeAller(sejour) + PERSONNEL.descente });
    const retour = polyligne(trajet(chemin, place, false));
    marches.push({ id: `${sejour.id}-d`, ...retour,
      debut: sejour.depart - PERSONNEL.descente - retour.longueurs.at(-1) / vitesse });
  });
  circulation.marches.set(jour, marches);
  return marches;
}

/** Pose {x, y, angle, phase} d'un marcheur à l'instant t, ou null (pas encore parti, ou
 * arrivé) ; phase : pour le balancement de la marche. */
export function poseDuMarcheur({ points, longueurs, debut }, t) {
  const d = (t - debut) * PIETON.vitesse * SECONDES_PAR_MINUTE;
  if (d < 0 || d >= longueurs.at(-1)) return null;
  let i = 1;
  while (i < points.length - 1 && longueurs[i] < d) i++;
  const [a, b] = [points[i - 1], points[i]];
  const k = (d - longueurs[i - 1]) / (longueurs[i] - longueurs[i - 1] || 1);
  return { x: a[0] + k * (b[0] - a[0]), y: a[1] + k * (b[1] - a[1]),
    angle: Math.atan2(b[1] - a[1], b[0] - a[0]), phase: d / PIETON.foulee };
}
