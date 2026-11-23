// Chariots élévateurs qui portent les marchandises, tirés de la scène sans la changer : chaque
// trajet d'une marchandise (segment en mouvement) est une tâche. Un chariot garé dans la zone
// où la marchandise attend (garages : decor.js) part à temps pour arriver avant elle, la prend,
// la porte sur tout son trajet (aux mêmes instants que la scène), revient par le même chemin,
// puis rentre au garage si sa prochaine tâche tarde. Chaque chariot est un objet au format de
// la scène (type « chariot », segments, événements) : il se survole, se sélectionne et a sa
// traçabilité. Les portes de marchandises sont ouvertes à chaque passage (marchandise ou
// chariot à vide). Aucune dépendance à three.js (testé par « npm test »).
import { CHARIOT, FLOTTE } from "./apparence.js";
import { parLesPortes, passagesDuChemin, porteDuPassage } from "./batiments.js";
import { preparerObjet, segmentActif } from "./donnees.js";
import { poseDuPorteur } from "./objets.js";
import { avancement, cheminAffiche, etatAffiche } from "./trajectoires.js";

const EPSILON = 1e-6; // min : juste après le début, juste avant la fin d'un trajet
const DEBUT = -1e6; // min : les chariots sont garés avant le début de la scène
const M_PAR_MINUTE = FLOTTE.vitesse * 60;
const ITERATIONS = 30; // inversion de l'avancement par dichotomie

/** Longueur d'une polyligne. */
function longueur(points) {
  let total = 0;
  for (let k = 1; k < points.length; k++) {
    total += Math.hypot(points[k][0] - points[k - 1][0], points[k][1] - points[k - 1][1]);
  }
  return total;
}

/** Zone {nom, libelle…} qui contient le point (la plus petite), ou null. */
function zoneDuPoint(zones, [x, y]) {
  return zones.filter((z) => x >= z.x && x <= z.x + z.largeur && y >= z.y
    && y <= z.y + z.profondeur)
    .sort((a, b) => a.largeur * a.profondeur - b.largeur * b.profondeur)[0] ?? null;
}

/** Distance du point au rectangle d'une zone (0 dedans). */
function distanceALaZone(z, [x, y]) {
  return Math.hypot(Math.max(z.x - x, 0, x - z.x - z.largeur),
    Math.max(z.y - y, 0, y - z.y - z.profondeur));
}

/** Zone de garage d'un point : la sienne si elle a des garages, sinon la plus proche qui en a. */
function zoneDeGarage(zones, garages, point) {
  const sienne = zoneDuPoint(zones, point);
  if (sienne && garages.get(sienne.nom)?.length) return sienne.nom;
  const avec = zones.filter((z) => garages.get(z.nom)?.length);
  return avec.sort((a, b) => distanceALaZone(a, point) - distanceALaZone(b, point))[0]?.nom;
}

/** Tâches {objet, t0, t1, prise, depot, poses [[t, x, y]], chemin} des marchandises, par début
 * croissant : poses du chariot porteur échantillonnées en FLOTTE.pas points ; chemin : trajet
 * affiché de la marchandise (par les portes). */
function tachesDeTransport(objets, contexte, gabarits) {
  const taches = [];
  for (const objet of objets) {
    const longueurCharge = gabarits[objet.type][1];
    objet.segments.forEach(([t0, t1, chemin], i) => {
      if (chemin.length < 2 || t1 === null) return;
      const poses = Array.from({ length: FLOTTE.pas + 1 }, (_, k) => {
        const t = Math.min(t1 - EPSILON, Math.max(t0 + EPSILON,
          t0 + ((t1 - t0) * k) / FLOTTE.pas));
        const pose = poseDuPorteur(etatAffiche(objet, t, contexte), longueurCharge);
        return [t, pose.x, pose.y];
      });
      taches.push({ objet, t0, t1, poses, prise: poses[0].slice(1), depot: poses.at(-1).slice(1),
        chemin: cheminAffiche(objet, i, contexte) });
    });
  }
  return taches.sort((a, b) => a.t0 - b.t0);
}

/** Nouveau chariot de la zone, garé à la place suivante de ses garages. */
function nouveauChariot(numero, zone, garages, rang) {
  const places = garages.get(zone);
  const garage = places[rang % places.length];
  return { id: `CHARIOT-${String(numero).padStart(2, "0")}`, zone, garage: [garage.x, garage.y],
    pos: [garage.x, garage.y], t: DEBUT, auGarage: true, segments: [], charges: [],
    evenements: [] };
}

/** Le chariot reste où il est jusqu'à `fin`. */
function attendre(c, fin) {
  if (fin <= c.t) return;
  const dernier = c.segments.at(-1);
  if (dernier && dernier[2].length === 1) dernier[1] = fin;
  else {
    c.segments.push([c.t, fin, [c.pos]]);
    c.charges.push(null);
  }
  c.t = fin;
}

/** Le chariot roule à vide sur `points` à partir de `debut` (attend jusque-là). */
function rouler(c, points, debut) {
  attendre(c, debut);
  if (longueur(points) < EPSILON) return;
  const fin = c.t + longueur(points) / M_PAR_MINUTE;
  c.segments.push([c.t, fin, points]);
  c.charges.push(null);
  c.t = fin;
  c.pos = points.at(-1);
}

/** Le chariot rentre au garage à partir de `debut`, par les portes. */
function rentrer(c, debut, outils) {
  if (c.auGarage) return;
  rouler(c, parLesPortes([c.pos, c.garage], outils.couverts, outils.portes), debut);
  c.evenements.push([c.t, "Garé", outils.libelle(c.garage), null, `Au garage de ${c.zone}`]);
  c.auGarage = true;
}

/** Chemin à vide du chariot jusqu'à la prise. */
const approche = (c, prise, outils) => parLesPortes([c.pos, prise], outils.couverts,
  outils.portes);

/** Le chariot va à la prise pour y être FLOTTE.attente min avant `t0` ; d'abord au garage si
 * l'attente le permet. */
function allerA(c, prise, t0, outils) {
  const arrivee = t0 - FLOTTE.attente;
  const direct = longueur(approche(c, prise, outils)) / M_PAR_MINUTE;
  if (!c.auGarage && arrivee - direct - c.t > FLOTTE.retour) rentrer(c, c.t, outils);
  const chemin = approche(c, prise, outils);
  const depart = Math.max(c.t, arrivee - longueur(chemin) / M_PAR_MINUTE);
  if (c.auGarage) {
    c.evenements.push([depart, "Quitte le garage", outils.libelle(c.pos), null,
      `Vers ${outils.libelle(prise)}`]);
  }
  c.auGarage = false;
  rouler(c, chemin, depart);
  attendre(c, t0);
}

/** Le chariot porte la marchandise de la tâche (segments échantillonnés, chacun relié à sa
 * charge), puis revient à vide par le même chemin jusqu'à la prise. */
function porter(c, tache, outils) {
  const { objet, poses, t1 } = tache;
  c.evenements.push([tache.t0, `Prend ${objet.id}`, outils.libelle(tache.prise), null,
    objet.libelle]);
  for (let k = 1; k < poses.length; k++) {
    // bornes exactes du trajet aux deux bouts : pas de trou entre deux segments
    const [debut, fin] = [k === 1 ? tache.t0 : poses[k - 1][0],
      k === poses.length - 1 ? t1 : poses[k][0]];
    c.segments.push([debut, fin, [poses[k - 1].slice(1), poses[k].slice(1)]]);
    c.charges.push(objet);
  }
  c.t = t1;
  c.pos = tache.depot;
  c.evenements.push([t1, `Dépose ${objet.id}`, outils.libelle(tache.depot), null,
    objet.libelle]);
  rouler(c, [tache.depot, ...[...tache.chemin].reverse(), tache.prise], t1 + FLOTTE.attente);
}

/** Meilleur chariot de la zone libre à temps pour la tâche (le plus proche), ou null. */
function chariotLibre(chariots, tache, outils) {
  let meilleur = null;
  let distance = Infinity;
  for (const c of chariots) {
    const d = longueur(approche(c, tache.prise, outils));
    if (c.t + d / M_PAR_MINUTE <= tache.t0 - FLOTTE.attente && d < distance) {
      [meilleur, distance] = [c, d];
    }
  }
  return meilleur;
}

/** Objet de la scène d'un chariot : type « chariot », segments, charges (marchandise portée à
 * chaque segment, ou null), événements de traçabilité ; dernier segment au garage, sans fin. */
function objetDuChariot(c) {
  c.segments.push([c.t, null, [c.garage]]);
  c.charges.push(null);
  return preparerObjet({ id: c.id, type: "chariot", libelle: `Garé à ${c.zone}`, liens: {},
    evenements: c.evenements, segments: c.segments, charges: c.charges, zone: c.zone });
}

/** Chariots élévateurs de la scène (objets au format de la scène, triés par identifiant) ;
 * `garages` : Map nom de zone → places [{x, y, angle}]. */
export function flotteDeChariots(scene, contexte, garages) {
  const zones = scene.site.zones;
  const outils = { couverts: contexte.couverts, portes: contexte.portes,
    libelle: (point) => zoneDuPoint(zones, point)?.libelle ?? "Voirie" };
  const marchandises = scene.objets.filter((o) => o.type !== "camion");
  const parZone = new Map();
  let numero = 0;
  for (const tache of tachesDeTransport(marchandises, contexte, scene.gabarits)) {
    const zone = zoneDeGarage(zones, garages, tache.prise);
    if (zone === undefined) continue;
    if (!parZone.has(zone)) parZone.set(zone, []);
    const liste = parZone.get(zone);
    let c = chariotLibre(liste, tache, outils);
    if (!c) {
      c = nouveauChariot(++numero, zone, garages, liste.length);
      liste.push(c);
    }
    allerA(c, tache.prise, tache.t0, outils);
    porter(c, tache, outils);
  }
  const chariots = [...parZone.values()].flat();
  for (const c of chariots) rentrer(c, c.t, outils);
  return chariots.map(objetDuChariot).sort((a, b) => a.id.localeCompare(b.id));
}

/** Pose {x, y, cap} affichée du chariot à l'instant t, ou null : sous sa charge quand il la
 * porte (derrière elle, fourches sous son arrière), sinon sur ses propres segments. */
export function poseDuChariot(chariot, t, contexte, gabarits) {
  const i = segmentActif(chariot, t);
  if (i < 0) return null;
  const charge = chariot.charges[i];
  const etat = charge && etatAffiche(charge, t, contexte);
  if (etat) return poseDuPorteur(etat, gabarits[charge.type][1]);
  return etatAffiche(chariot, t, contexte);
}

/** {x, y, cap} affichés d'un objet de la scène ou d'un chariot à l'instant t, ou null (anneau
 * de sélection, pilule). */
export function etatSuivi(objet, t, contexte) {
  return objet.type === "chariot" ? poseDuChariot(objet, t, contexte, contexte.gabarits)
    : etatAffiche(objet, t, contexte);
}

/** Part p (0 à 1) de la durée d'un trajet où la part `d` de sa longueur est faite (inverse de
 * l'avancement, avec accélération et freinage). */
function partDeLaDuree(d) {
  let [bas, haut] = [0, 1];
  for (let k = 0; k < ITERATIONS; k++) {
    const milieu = (bas + haut) / 2;
    if (avancement(milieu, [true, true]) < d) bas = milieu;
    else haut = milieu;
  }
  return (bas + haut) / 2;
}

/** Instants de passage [{porte, t}] d'un trajet `chemin` de t0 à t1 par les portes. */
function passagesDuTrajet(chemin, t0, t1, outils) {
  const total = longueur(chemin);
  if (total < EPSILON) return [];
  return passagesDuChemin(chemin, outils.couverts).flatMap((p) => {
    const porte = porteDuPassage(outils.portes, p);
    if (!porte) return [];
    const fait = longueur([...chemin.slice(0, p.k + 1), p.point]);
    return [{ porte: porte.id, t: t0 + (t1 - t0) * partDeLaDuree(fait / total) }];
  });
}

/** Instants de passage par chaque porte de marchandises : Map id de la porte → instants triés ;
 * marchandises (trajets affichés) et chariots à vide. */
export function passagesDesPortes(scene, contexte, chariots) {
  const outils = { couverts: contexte.couverts, portes: contexte.portes };
  const liste = [];
  for (const objet of scene.objets.filter((o) => o.type !== "camion")) {
    objet.segments.forEach(([t0, t1, chemin], i) => {
      if (chemin.length > 1 && t1 !== null) {
        liste.push(...passagesDuTrajet(cheminAffiche(objet, i, contexte), t0, t1, outils));
      }
    });
  }
  for (const chariot of chariots) {
    chariot.segments.forEach(([t0, t1, chemin], i) => {
      if (chemin.length > 1 && t1 !== null && !chariot.charges[i]) {
        liste.push(...passagesDuTrajet(chemin, t0, t1, outils));
      }
    });
  }
  const parPorte = new Map(contexte.portes.map((p) => [p.id, []]));
  for (const { porte, t } of liste) parPorte.get(porte)?.push(t);
  for (const instants of parPorte.values()) instants.sort((a, b) => a - b);
  return parPorte;
}

/** Vrai si un passage de `instants` (triés) tombe dans [de, a]. */
export function passageEntre(instants, de, a) {
  let [bas, haut] = [0, instants.length];
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (instants[milieu] < de) bas = milieu + 1;
    else haut = milieu;
  }
  return bas < instants.length && instants[bas] <= a;
}

/** Gabarit [largeur, longueur, hauteur] d'un chariot, pour l'anneau et la pilule. */
export const GABARIT_CHARIOT = [CHARIOT.largeur, CHARIOT.longueur, CHARIOT.mat];
