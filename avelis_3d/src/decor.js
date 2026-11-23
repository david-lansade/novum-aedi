// Décor de la vue 3D, en coordonnées du plan (m) : arbres autour du foncier et le long de la
// route publique, clôture sur son pourtour, racks le long des murs des stocks, chariots
// élévateurs et AGV, groupes froids sur les toits plats. Il ne représente aucune donnée : il
// n'est posé que là où ni route ni objet de la scène ne passe (manœuvres de quai comprises,
// trajectoires.js), et toujours au même endroit pour une même scène (tirage à graine fixe).
// Aucune dépendance à three.js (testé par « npm test »).
import {
  AGV, ARBRES, BARRIERE, BATIMENT, CATEGORIE_BUREAUX, CHARIOT, CHARIOT_ACTIF, CLOTURE,
  ECART_REPERES, ECHELLE, FLOTTE, GRANDE_PORTE, GROUPE_FROID, LARGEUR_ROUTE_PUBLIQUE, NORD,
  PARKING_PL, PARKING_VL, PASSAGE, PLACES_DECOR, POSTE_GARDE, PREFIXE_STOCKS, RACK,
} from "./apparence.js";
import { cheminsDesMarchandises, portesDeMarchandises, quaisNumerotes } from "./batiments.js";
import {
  dansPolygone, distanceAuBord, distanceEntreSegments, fermer, pointLePlusProche,
  sensDuPolygone,
} from "./traces.js";
import { axesDesManoeuvres, creerTrajectoires } from "./trajectoires.js";

const ARRONDI = 10; // tronçons identiques au dixième de mètre près : un seul exemplaire
const CAP_PAR_DEFAUT = 0; // vers l'est, pour un objet qui n'a encore jamais roulé (donnees.js)
const DECALAGE_ONGLET = 3; // raccord d'une voie décalée : au plus 3 fois le décalage
const CELLULE = 16; // m, côté des cases de la grille d'occupation

/** Générateur pseudo-aléatoire (mulberry32) : chaque appel renvoie un nombre de [0, 1). */
export function aleatoire(graine) {
  let etat = graine >>> 0;
  return () => {
    etat = (etat + 0x6d2b79f5) >>> 0;
    let t = etat;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Nombre tiré entre `bas` et `haut`. */
function entre(tirage, [bas, haut]) {
  return bas + (haut - bas) * tirage();
}

/** Ajoute à `ajouter(a, b, rayon)` l'emprise d'un objet sur chacun de ses segments : son axe,
 * dans le sens de la marche, de rayon sa demi-largeur. En route, chaque tronçon du chemin
 * prolongé d'une demi-longueur à chaque bout ; à l'arrêt, l'axe centré sur le point et orienté
 * selon le dernier trajet (comme donnees.js). */
function empriseObjet(objet, [largeur, longueur], ajouter) {
  let cap = CAP_PAR_DEFAUT;
  for (const [, , chemin] of objet.segments) {
    if (chemin.length === 1) {
      const [x, y] = chemin[0];
      const [ux, uy] = [(Math.cos(cap) * longueur) / 2, (Math.sin(cap) * longueur) / 2];
      ajouter([x - ux, y - uy], [x + ux, y + uy], largeur / 2);
      continue;
    }
    for (let i = 1; i < chemin.length; i++) {
      const [[ax, ay], [bx, by]] = [chemin[i - 1], chemin[i]];
      const troncon = Math.hypot(bx - ax, by - ay);
      if (troncon === 0) continue;
      cap = Math.atan2(by - ay, bx - ax);
      const [ux, uy] = [((bx - ax) / troncon) * (longueur / 2),
        ((by - ay) / troncon) * (longueur / 2)];
      ajouter([ax - ux, ay - uy], [bx + ux, by + uy], largeur / 2);
    }
  }
}

/** Tronçons {a, b, rayon} occupés, sans doublon : routes et bretelles (demi-largeur), accès au
 * portail, aire de retournement, parking VL et sa voie, repères (flèche du nord, échelle),
 * emprise des objets et des camions qui manœuvrent à quai. */
function tronconsOccupes(site, objets, gabarits) {
  const troncons = new Map();
  const ajouter = (a, b, rayon) => {
    const cle = [...a, ...b, rayon].map((c) => Math.round(c * ARRONDI)).join(",");
    if (!troncons.has(cle)) troncons.set(cle, { a, b, rayon });
  };
  const polyligne = (points, rayon) => {
    points.slice(1).forEach((b, i) => ajouter(points[i], b, rayon));
  };
  polyligne(site.route_publique, LARGEUR_ROUTE_PUBLIQUE / 2);
  polyligne(site.voirie, site.largeur_voirie / 2);
  for (const bretelle of site.bretelles) polyligne(bretelle, site.largeur_voirie / 2);
  polyligne([pointLePlusProche(site.route_publique, site.acces[0]), ...site.acces],
    site.largeur_voirie / 2);
  const parking = site.parking_vl;
  if (parking) {
    polyligne(parking.voie, PARKING_VL.voie / 2);
    const [cx, cy] = [parking.x + parking.largeur / 2, parking.y + parking.profondeur / 2];
    const [dx, dy] = parking.largeur >= parking.profondeur
      ? [(parking.largeur - parking.profondeur) / 2, 0]
      : [0, (parking.profondeur - parking.largeur) / 2];
    ajouter([cx - dx, cy - dy], [cx + dx, cy + dy], Math.min(parking.largeur,
      parking.profondeur) / 2);
  }
  const { poste } = portailDuSite(site);
  ajouter([poste.x, poste.y], [poste.x, poste.y], Math.hypot(POSTE_GARDE.largeur,
    POSTE_GARDE.profondeur) / 2);
  ajouter(site.retournement.centre, site.retournement.centre, site.retournement.rayon);
  ajouter([NORD.x, NORD.y - NORD.longueur / 2], [NORD.x, NORD.y + NORD.longueur / 2],
    ECART_REPERES);
  ajouter([ECHELLE.x, ECHELLE.y], [ECHELLE.x + ECHELLE.longueur, ECHELLE.y], ECART_REPERES);
  for (const objet of objets) empriseObjet(objet, gabarits[objet.type], ajouter);
  // passage des marchandises par les portes (trajectoires.js) : de part et d'autre du mur
  const d = 2 * PASSAGE.recul;
  for (const { point: [x, y], normale: [nx, ny] } of portesDeMarchandises(site,
    cheminsDesMarchandises(objets))) {
    ajouter([x + nx * d, y + ny * d], [x - nx * d, y - ny * d], GRANDE_PORTE.largeur / 2);
  }
  for (const [a, b] of axesDesManoeuvres(objets, creerTrajectoires(site, gabarits))) {
    ajouter(a, b, gabarits.camion[0] / 2);
  }
  return [...troncons.values()];
}

/** Cases de CELLULE m de côté couvertes par la boîte [xmin, xmax] × [ymin, ymax]. */
function cases(xmin, xmax, ymin, ymax) {
  const liste = [];
  for (let i = Math.floor(xmin / CELLULE); i <= Math.floor(xmax / CELLULE); i++) {
    for (let j = Math.floor(ymin / CELLULE); j <= Math.floor(ymax / CELLULE); j++) {
      liste.push(`${i},${j}`);
    }
  }
  return liste;
}

/** Occupation du sol par les routes et les objets de la scène : `libre(a, marge, b)` est vrai
 * si le point a (ou le segment [a, b]) est à plus de `marge` m de tout ce qui roule ou
 * s'arrête. Chaque tronçon est rangé dans les cases de la grille que couvre son emprise : une
 * question ne regarde que ceux des cases qu'elle couvre (une scène de 60 jours en compte des
 * dizaines de milliers). */
export function creerOccupation(site, objets, gabarits) {
  const troncons = tronconsOccupes(site, objets, gabarits).map((t) => ({ ...t,
    xmin: Math.min(t.a[0], t.b[0]) - t.rayon, xmax: Math.max(t.a[0], t.b[0]) + t.rayon,
    ymin: Math.min(t.a[1], t.b[1]) - t.rayon, ymax: Math.max(t.a[1], t.b[1]) + t.rayon }));
  const grille = new Map();
  for (const t of troncons) {
    for (const cle of cases(t.xmin, t.xmax, t.ymin, t.ymax)) {
      if (!grille.has(cle)) grille.set(cle, []);
      grille.get(cle).push(t);
    }
  }
  const libre = (a, marge, b = a) => {
    const [xmin, xmax] = [Math.min(a[0], b[0]) - marge, Math.max(a[0], b[0]) + marge];
    const [ymin, ymax] = [Math.min(a[1], b[1]) - marge, Math.max(a[1], b[1]) + marge];
    return cases(xmin, xmax, ymin, ymax).every((cle) => (grille.get(cle) ?? []).every((t) =>
      xmax < t.xmin || xmin > t.xmax || ymax < t.ymin || ymin > t.ymax
      || distanceEntreSegments(a, b, t.a, t.b) > t.rayon + marge));
  };
  return { troncons, libre };
}

/** Places du parking VL et lignes qui les bordent : {places [{x, y, angle}], lignes [[a, b]]}.
 * Bandes du sud au nord, chacune de deux rangées de places de PARKING_VL.largeur m, au sud et
 * au nord d'une allée d'est en ouest ; une voiture garée regarde l'allée (`angle` : sens de son
 * avant). */
export function placesDuParkingVl(parking) {
  const { largeur: l, profondeur: p, allee } = PARKING_VL;
  const nombre = Math.floor(parking.largeur / l);
  const x0 = parking.x + (parking.largeur - nombre * l) / 2;
  const bande = 2 * p + allee;
  const bandes = Math.max(1, Math.floor(parking.profondeur / bande));
  const y0 = parking.y + (parking.profondeur - bandes * bande) / 2;
  const places = [];
  const lignes = [];
  for (let b = 0; b < bandes; b++) {
    for (const [bas, angle] of [[y0 + b * bande, Math.PI / 2],
      [y0 + (b + 1) * bande - p, -Math.PI / 2]]) {
      for (let i = 0; i < nombre; i++) {
        places.push({ x: x0 + (i + 0.5) * l, y: bas + p / 2, angle });
      }
      for (let i = 0; i <= nombre; i++) lignes.push([[x0 + i * l, bas], [x0 + i * l, bas + p]]);
    }
  }
  return { places, lignes };
}

/** Lignes [[a, b]] des places du parking PL (zone « Parking PL ») : rangées nord-sud de
 * PARKING_PL.largeur × PARKING_PL.longueur m, centrées dans la zone, comme les places où
 * simulation.py gare les camions ; [] sans parking PL. */
export function lignesDuParkingPl(site) {
  const zone = site.zones.find((z) => z.nom === "Parking PL");
  if (!zone) return [];
  const { largeur: l, longueur: p } = PARKING_PL;
  const [colonnes, rangees] = [Math.floor(zone.largeur / l),
    Math.max(1, Math.floor(zone.profondeur / p))];
  const [x0, y0] = [zone.x + (zone.largeur - colonnes * l) / 2,
    zone.y + (zone.profondeur - rangees * p) / 2];
  const lignes = [];
  for (let j = 0; j <= rangees; j++) {
    lignes.push([[x0, y0 + j * p], [x0 + colonnes * l, y0 + j * p]]);
  }
  for (let j = 0; j < rangees; j++) {
    for (let i = 0; i <= colonnes; i++) {
      lignes.push([[x0 + i * l, y0 + j * p], [x0 + i * l, y0 + (j + 1) * p]]);
    }
  }
  return lignes;
}

/** Portail du site : sens `u` de la voirie vers l'intérieur du site, `cote` (à gauche de u) ;
 * poste de garde {x, y, angle} sur ce côté, en retrait ; barrière {pivot, angle} : pivot au bord
 * de la voirie côté poste, bras fermé vers l'autre bord (`angle`). */
export function portailDuSite(site) {
  const [px, py] = site.portail;
  const avant = site.voirie.at(-1)[0] === px && site.voirie.at(-1)[1] === py
    ? site.voirie.at(-2) : site.voirie[1];
  const n = Math.hypot(avant[0] - px, avant[1] - py) || 1;
  const u = [(avant[0] - px) / n, (avant[1] - py) / n];
  const cote = [-u[1], u[0]];
  const bord = site.largeur_voirie / 2 + BARRIERE.poteau;
  const ecart = bord + POSTE_GARDE.ecart + POSTE_GARDE.profondeur / 2;
  const poste = { x: px + cote[0] * ecart + u[0] * POSTE_GARDE.recul,
    y: py + cote[1] * ecart + u[1] * POSTE_GARDE.recul, angle: Math.atan2(u[1], u[0]) };
  return { u, cote, poste,
    barriere: { pivot: [px + cote[0] * bord, py + cote[1] * bord],
      angle: Math.atan2(-cote[1], -cote[0]) } };
}

/** Abscisse curviligne et position du point de la polyligne le plus proche de `point`. */
function projeter(polyligne, point) {
  let meilleur = null;
  let abscisse = 0;
  for (let i = 1; i < polyligne.length; i++) {
    const [a, b] = [polyligne[i - 1], polyligne[i]];
    const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
    const longueur = Math.hypot(dx, dy);
    const k = longueur > 0 ? Math.max(0, Math.min(1, ((point[0] - a[0]) * dx
      + (point[1] - a[1]) * dy) / longueur ** 2)) : 0;
    const proche = [a[0] + k * dx, a[1] + k * dy];
    const d = Math.hypot(point[0] - proche[0], point[1] - proche[1]);
    if (!meilleur || d < meilleur.d) meilleur = { d, s: abscisse + k * longueur, proche };
    abscisse += longueur;
  }
  return meilleur ?? { d: 0, s: 0, proche: polyligne[0] };
}

/** Morceau de la polyligne entre les projections de `de` et de `vers`, dans ce sens. */
function leLong(polyligne, de, vers) {
  const [a, b] = [projeter(polyligne, de), projeter(polyligne, vers)];
  let s = 0;
  const sommets = [];
  for (let i = 0; i < polyligne.length; i++) {
    if (i > 0) {
      s += Math.hypot(polyligne[i][0] - polyligne[i - 1][0], polyligne[i][1]
        - polyligne[i - 1][1]);
    }
    if (s > Math.min(a.s, b.s) && s < Math.max(a.s, b.s)) sommets.push(polyligne[i]);
  }
  if (a.s > b.s) sommets.reverse();
  return [a.proche, ...sommets, b.proche];
}

/** Chemin d'une voiture du personnel, du sud de la route publique à la place du parking VL :
 * route publique, accès, portail, voirie, voie du parking, allée, place. */
export function cheminVersLaPlace(site, place) {
  const { profondeur: p, allee } = PARKING_VL;
  const voie = site.parking_vl.voie;
  const yAllee = place.y + Math.sin(place.angle) * (p / 2 + allee / 2);
  return [...leLong(site.route_publique, site.route_publique[0], site.acces[0]), ...site.acces,
    ...leLong(site.voirie, site.portail, voie[0]),
    ...leLong(voie, voie[0], [place.x, yAllee]), [place.x, yAllee], [place.x, place.y]];
}

/** Parcours {points, cumuls, longueur} d'une polyligne, sans tronçon nul. */
export function parcoursVoiture(points) {
  const net = points.filter((q, i) => i === 0 || Math.hypot(q[0] - points[i - 1][0],
    q[1] - points[i - 1][1]) > 1e-6);
  const cumuls = [0];
  for (let i = 1; i < net.length; i++) {
    cumuls.push(cumuls[i - 1] + Math.hypot(net[i][0] - net[i - 1][0], net[i][1]
      - net[i - 1][1]));
  }
  return { points: net, cumuls, longueur: cumuls.at(-1) };
}

/** Polyligne décalée de `d` m à droite du sens de parcours (raccords en onglet, bornés à
 * DECALAGE_ONGLET fois `d` dans les virages serrés). */
export function aDroite(points, d) {
  const net = parcoursVoiture(points).points;
  const normales = net.slice(1).map((b, i) => {
    const a = net[i];
    const n = Math.hypot(b[0] - a[0], b[1] - a[1]);
    return [(b[1] - a[1]) / n, -(b[0] - a[0]) / n];
  });
  return net.map(([x, y], i) => {
    const [p, q] = [normales[Math.max(0, i - 1)], normales[Math.min(normales.length - 1, i)]];
    if (!p) return [x, y];
    const [mx, my] = [p[0] + q[0], p[1] + q[1]];
    const cos = (mx * p[0] + my * p[1]) / (Math.hypot(mx, my) || 1);
    const k = d / Math.max(cos, 1 / DECALAGE_ONGLET) / (Math.hypot(mx, my) || 1);
    return Math.hypot(mx, my) < 1e-9 ? [x + p[0] * d, y + p[1] * d] : [x + mx * k, y + my * k];
  });
}

/** Pose {x, y, angle} à la distance d d'un parcours ; `recule` : l'avant regarde en arrière
 * (sortie de la place en marche arrière). */
export function poseSurParcours({ points, cumuls }, d, recule) {
  let i = 1;
  while (i < points.length - 1 && cumuls[i] < d) i++;
  const [a, b] = [points[i - 1], points[i]];
  const troncon = cumuls[i] - cumuls[i - 1] || 1;
  const k = Math.max(0, Math.min(1, (d - cumuls[i - 1]) / troncon));
  return { x: a[0] + k * (b[0] - a[0]), y: a[1] + k * (b[1] - a[1]),
    angle: Math.atan2(b[1] - a[1], b[0] - a[0]) + (recule ? Math.PI : 0) };
}

/** Points tous les `pas` m le long d'une polyligne (le premier à pas / 2), décalés de `recul` m
 * vers la gauche du sens de parcours (vers la droite si `recul` < 0). */
function jalons(points, pas, recul) {
  const liste = [];
  for (let i = 1; i < points.length; i++) {
    const [[ax, ay], [bx, by]] = [points[i - 1], points[i]];
    const longueur = Math.hypot(bx - ax, by - ay);
    if (longueur === 0) continue;
    const [ux, uy] = [(bx - ax) / longueur, (by - ay) / longueur];
    for (let s = pas / 2; s < longueur; s += pas) {
      liste.push([ax + ux * s - uy * recul, ay + uy * s + ux * recul]);
    }
  }
  return liste;
}

/** Emplacements candidats des arbres : deux rangs à l'extérieur de chaque contour du foncier, et
 * un rang de chaque côté de la route publique. */
function placesArbres(site) {
  const places = site.contours.flatMap((contour) => {
    const vers = -sensDuPolygone(contour.points); // extérieur : à droite du sens trigonométrique
    return ARBRES.reculs.flatMap((recul) => jalons(fermer(contour.points), ARBRES.pas,
      vers * recul));
  });
  for (const cote of [1, -1]) {
    places.push(...jalons(site.route_publique, ARBRES.pasRoute, cote * ARBRES.bordRoute));
  }
  return places;
}

/** Arbres {x, y, hauteur, rayon, teinte} : hors du foncier (à `margeFoncier` m au moins de son
 * bord), loin des routes et des objets, espacés d'au moins `ecartMin` m. */
export function arbresDuSite(site, occupation, graine) {
  const tirage = aleatoire(graine);
  const arbres = [];
  for (const [px, py] of placesArbres(site)) {
    const point = [px + entre(tirage, [-1, 1]) * ARBRES.decalage,
      py + entre(tirage, [-1, 1]) * ARBRES.decalage];
    const [hauteur, rayon] = [entre(tirage, ARBRES.hauteur), entre(tirage, ARBRES.rayon)];
    const teinte = Math.floor(tirage() * ARBRES.couleurs.length);
    const horsFoncier = site.contours.every((c) => !dansPolygone(point, c.points)
      && distanceAuBord(point, c.points) >= ARBRES.margeFoncier + rayon);
    const isole = arbres.every((a) => Math.hypot(a.x - point[0], a.y - point[1])
      >= ARBRES.ecartMin);
    if (horsFoncier && isole && occupation.libre(point, rayon + ARBRES.margeVoie)) {
      arbres.push({ x: point[0], y: point[1], hauteur, rayon, teinte });
    }
  }
  return arbres;
}

/** Vrai si le panneau de milieu `milieu`, de normale extérieure `normale`, longe un autre
 * contour utilisé (limite commune, intérieure au foncier). */
function limiteCommune(milieu, normale, autres) {
  const dehors = [milieu[0] + normale[0], milieu[1] + normale[1]];
  return autres.some((c) => dansPolygone(dehors, c.points));
}

/** Clôture du foncier utilisé {panneaux: [{x, y, longueur, angle}], poteaux: [[x, y]]} :
 * panneaux d'au plus CLOTURE.pas m sur le pourtour, sauf la limite commune de deux contours et
 * là où passe une route ou un objet (le portail reste ainsi ouvert). */
export function clotureDuSite(site, occupation) {
  const utilises = site.contours.filter((c) => c.utilise);
  const panneaux = [];
  const poteaux = new Map();
  for (const contour of utilises) {
    const vers = -sensDuPolygone(contour.points);
    const bord = fermer(contour.points);
    for (let i = 1; i < bord.length; i++) {
      const [[ax, ay], [bx, by]] = [bord[i - 1], bord[i]];
      const longueur = Math.hypot(bx - ax, by - ay);
      const nombre = Math.ceil(longueur / CLOTURE.pas);
      const normale = [(-vers * (by - ay)) / longueur, (vers * (bx - ax)) / longueur];
      for (let k = 0; k < nombre; k++) {
        const [debut, fin] = [k / nombre, (k + 1) / nombre];
        const bouts = [debut, fin].map((f) => [ax + (bx - ax) * f, ay + (by - ay) * f]);
        const milieu = [(bouts[0][0] + bouts[1][0]) / 2, (bouts[0][1] + bouts[1][1]) / 2];
        if (limiteCommune(milieu, normale, utilises.filter((c) => c !== contour))) continue;
        if (!occupation.libre(bouts[0], CLOTURE.marge, bouts[1])) continue;
        panneaux.push({ x: milieu[0], y: milieu[1], longueur: longueur / nombre,
          angle: Math.atan2(by - ay, bx - ax) });
        for (const p of bouts) poteaux.set(p.map((c) => Math.round(c * ARRONDI)).join(","), p);
      }
    }
  }
  return { panneaux, poteaux: [...poteaux.values()] };
}

/** Centres des baies le long des deux grands murs, à l'intérieur d'une zone ; `angle` : 0 si les
 * rangs suivent x, π / 2 s'ils suivent y. */
function baiesDeZone(zone) {
  const suitX = zone.largeur >= zone.profondeur;
  const [longueur, travers] = suitX ? [zone.largeur, zone.profondeur]
    : [zone.profondeur, zone.largeur];
  const nombre = Math.floor((longueur - 2 * RACK.retraitBout) / RACK.baie);
  const depart = (longueur - nombre * RACK.baie) / 2 + RACK.baie / 2;
  const reculs = [RACK.recul + RACK.profondeur / 2, travers - RACK.recul - RACK.profondeur / 2];
  return reculs.flatMap((recul) => Array.from({ length: Math.max(0, nombre) }, (_, i) => {
    const le = depart + i * RACK.baie;
    return suitX ? { x: zone.x + le, y: zone.y + recul, angle: 0 }
      : { x: zone.x + recul, y: zone.y + le, angle: Math.PI / 2 };
  }));
}

/** Baies de racks {x, y, angle, cartons: [[niveau, place]]} des zones de stockage couvertes, le
 * long de leurs deux grands murs, sauf là où un objet passe ou s'arrête. */
export function racksDesStocks(site, occupation, graine) {
  const tirage = aleatoire(graine);
  const stocks = site.zones.filter((zone) => zone.hauteur > 0
    && zone.nom.startsWith(PREFIXE_STOCKS));
  const libre = ({ x, y, angle }) => {
    const [ux, uy] = [(Math.cos(angle) * RACK.baie) / 2, (Math.sin(angle) * RACK.baie) / 2];
    return occupation.libre([x - ux, y - uy], RACK.profondeur / 2 + RACK.marge, [x + ux, y + uy]);
  };
  return stocks.flatMap(baiesDeZone).filter(libre).map((baie) => {
    const cartons = [];
    for (let niveau = 0; niveau < RACK.niveaux; niveau++) {
      for (const place of [0, 1]) if (tirage() < RACK.remplissage) cartons.push([niveau, place]);
    }
    return { ...baie, cartons };
  });
}

/** Emprise d'un engin {a, b, rayon}, comme celle des objets : son axe dans le sens de sa
 * longueur, de rayon sa demi-largeur, prolongé vers l'arrière de sa `course` (m parcourus en
 * marche arrière par un chariot actif). */
export function empriseEngin({ forme, x, y, angle, course = 0 }) {
  const { longueur, largeur } = forme === "chariot" ? CHARIOT : AGV;
  const [ux, uy] = [Math.cos(angle), Math.sin(angle)];
  const demi = (longueur - largeur) / 2;
  return { a: [x - ux * (demi + course), y - uy * (demi + course)],
    b: [x + ux * demi, y + uy * demi], rayon: largeur / 2 };
}

/** Recul (m) d'un chariot actif à `secondes` s de lecture depuis le début de son activité :
 * va-et-vient de 0 à CHARIOT_ACTIF.course m et retour, en CHARIOT_ACTIF.periode s. */
export function reculChariot(secondes) {
  const { course, periode } = CHARIOT_ACTIF;
  return (course * (1 - Math.cos((2 * Math.PI * secondes) / periode))) / 2;
}

/** Situation d'une emprise : la zone couverte qui la contient à PLACES_DECOR.mur m au moins de
 * ses murs, null si elle est dehors à cette distance de tout bâtiment, undefined si elle est à
 * cheval sur un mur ou trop près. */
function situation(site, { a, b, rayon }) {
  const m = PLACES_DECOR.mur;
  const [xmin, xmax] = [Math.min(a[0], b[0]) - rayon, Math.max(a[0], b[0]) + rayon];
  const [ymin, ymax] = [Math.min(a[1], b[1]) - rayon, Math.max(a[1], b[1]) + rayon];
  let dedans = null;
  for (const z of site.zones.filter((zone) => zone.hauteur > 0)) {
    if (xmin >= z.x + m && xmax <= z.x + z.largeur - m && ymin >= z.y + m
      && ymax <= z.y + z.profondeur - m) dedans = z;
    else if (!(xmax <= z.x - m || xmin >= z.x + z.largeur + m || ymax <= z.y - m
      || ymin >= z.y + z.profondeur + m)) return undefined;
  }
  return dedans;
}

/** Axe [a, b] d'une baie de racks. */
function axeDeBaie({ x, y, angle }) {
  const [ux, uy] = [(Math.cos(angle) * RACK.baie) / 2, (Math.sin(angle) * RACK.baie) / 2];
  return [[x - ux, y - uy], [x + ux, y + uy]];
}

/** Places {x, y, angle} le long des murs, à l'intérieur d'une zone : tous les PLACES_DECOR.pas
 * m, à PLACES_DECOR.recul m des murs, parallèles au mur. */
function placesLeLongDesMurs({ x, y, largeur, profondeur }) {
  const { recul, pas } = PLACES_DECOR;
  const places = [];
  for (let s = recul; s <= largeur - recul; s += pas) {
    places.push({ x: x + s, y: y + recul, angle: 0 },
      { x: x + s, y: y + profondeur - recul, angle: Math.PI });
  }
  for (let s = recul; s <= profondeur - recul; s += pas) {
    places.push({ x: x + recul, y: y + s, angle: Math.PI / 2 },
      { x: x + largeur - recul, y: y + s, angle: -Math.PI / 2 });
  }
  return places;
}

/** Places {x, y, angle} essayées à côté d'un quai, de la plus proche à la plus lointaine : de
 * part et d'autre dans le sens de la rangée des quais, sur une grille de PLACES_DECOR.finesse m
 * jusqu'à PLACES_DECOR.autourDuQuai m, fourches tournées vers le quai. */
function placesAutourDuQuai({ x, y, sens: [ux, uy] }) {
  const { autourDuQuai: d, finesse } = PLACES_DECOR;
  const places = []; // [distance, place]
  for (let i = 1; i * finesse <= d; i++) {
    for (let j = -Math.floor(d / finesse); j * finesse <= d; j++) {
      for (const s of [1, -1]) {
        const [a, b] = [s * i * finesse, j * finesse]; // le long de la rangée, en travers
        places.push([Math.hypot(i, j), { x: x + a * ux - b * uy, y: y + a * uy + b * ux,
          angle: Math.atan2(uy, ux) + (s > 0 ? Math.PI : 0) }]);
      }
    }
  }
  return places.sort((p, q) => p[0] - q[0]).map(([, place]) => place);
}

/** Chariots élévateurs et AGV du décor {forme, x, y, angle, dedans} : un chariot à côté de chaque
 * quai (la place libre la plus proche, `quai` : son numéro, `course` : place réservée derrière
 * lui pour son va-et-vient), un AGV dans chaque zone de production couverte (le long des murs,
 * place tirée au hasard) et les garages des chariots des ateliers (`garage` : vrai, non
 * dessinés ici : chariots.js). Toujours là où ni route ni objet ne passe, loin des racks et des
 * autres engins, jamais à cheval sur un mur ; `dedans` : dans un bâtiment. */
export function enginsDuDecor(site, occupation, baies, graine) {
  const tirage = aleatoire(graine);
  const engins = [];
  const marge = PLACES_DECOR.marge;
  const poser = (engin) => {
    const e = empriseEngin(engin);
    const ou = situation(site, e);
    const libre = ou !== undefined && occupation.libre(e.a, e.rayon + marge, e.b)
      && baies.every((baie) => distanceEntreSegments(e.a, e.b, ...axeDeBaie(baie))
        > RACK.profondeur / 2 + e.rayon + marge)
      && engins.map(empriseEngin).every((f) => distanceEntreSegments(e.a, e.b, f.a, f.b)
        > e.rayon + f.rayon + marge);
    return libre ? { ...engin, dedans: ou !== null } : null;
  };
  for (const quai of quaisNumerotes(site.quais)) {
    const place = placesAutourDuQuai(quai).reduce((trouvee, p) => trouvee ?? poser({
      forme: "chariot", ...p, quai: quai.numero, course: CHARIOT_ACTIF.course }), null);
    if (place) engins.push(place);
  }
  const couvertes = site.zones.filter((zone) => zone.hauteur > 0);
  for (const zone of couvertes.filter((z) => z.categorie === AGV.zones)) {
    const places = placesLeLongDesMurs(zone).map((p) => poser({ forme: "agv", ...p }))
      .filter((p) => p?.dedans);
    if (places.length > 0) engins.push(places[Math.floor(tirage() * places.length)]);
  }
  for (const zone of couvertes.filter((z) => z.categorie !== CATEGORIE_BUREAUX)) {
    engins.push(...garagesDeLaZone(zone, poser, engins));
  }
  return engins;
}

/** Garages des chariots élévateurs (chariots.js) dans la zone : jusqu'à FLOTTE.garages places
 * libres le long de ses murs, prises dans l'ordre (les chariots y sont garés côte à côte) ;
 * `garage` : vrai, `zone` : son nom. `poser` vérifie et ajoute la place à `engins`. */
function garagesDeLaZone(zone, poser, engins) {
  const garages = [];
  for (const place of placesLeLongDesMurs(zone)) {
    if (garages.length >= FLOTTE.garages) break;
    const garage = poser({ forme: "chariot", ...place, garage: true, zone: zone.nom });
    if (!garage?.dedans) continue;
    garages.push(garage);
    engins.push(garage); // les suivants s'en écartent
  }
  engins.splice(engins.length - garages.length, garages.length);
  return garages;
}

/** Groupes froids {x, y, z, angle} alignés au milieu du toit plat de chaque bâtiment de
 * bureaux, dans le sens de sa longueur ; z : dessus de la toiture ; angle : direction de la
 * longueur du caisson, en travers du rang. */
export function groupesFroids(site) {
  const bureaux = site.zones.filter((zone) => zone.hauteur > 0
    && zone.categorie === CATEGORIE_BUREAUX);
  return bureaux.flatMap((zone) => {
    const suitX = zone.largeur >= zone.profondeur;
    const longueur = suitX ? zone.largeur : zone.profondeur;
    const nombre = Math.min(GROUPE_FROID.nombreMax,
      Math.floor((longueur - 2 * BATIMENT.retraitVitrage) / GROUPE_FROID.pas));
    const [cx, cy] = [zone.x + zone.largeur / 2, zone.y + zone.profondeur / 2];
    const z = zone.hauteur - BATIMENT.acrotere;
    return Array.from({ length: Math.max(0, nombre) }, (_, i) => {
      const le = (i - (nombre - 1) / 2) * GROUPE_FROID.pas;
      return suitX ? { x: cx + le, y: cy, z, angle: Math.PI / 2 }
        : { x: cx, y: cy + le, z, angle: 0 };
    });
  });
}
