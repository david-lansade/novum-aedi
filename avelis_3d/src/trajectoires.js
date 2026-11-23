// Couche visuelle des trajectoires : ce que la vue montre des objets qui roulent, tiré de la scène
// sans la changer (choix validé 5). etatObjet (donnees.js) reste la référence, comparée à Python.
// Ici, mêmes instants (un objet paraît, s'arrête, repart et disparaît aux mêmes instants) et
// mêmes points d'arrêt, mais :
// - virages arrondis : arc de cercle tangent aux deux tronçons ;
// - départ et arrivée progressifs à côté d'un arrêt : accélération, puis freinage ;
// - camions qui reculent à quai : ils dépassent l'entrée du quai, puis leur arrière décrit un
//   quart de tour jusqu'aux butoirs de la porte (au fond du quai s'il est à ciel ouvert), la
//   caisse dans l'axe de sa marche comme une remorque ; ils restent l'arrière contre le quai,
//   puis repartent en marche avant, l'arrière décrivant le quart de tour inverse ;
// - camions garés en long à un quai à ciel ouvert (case d'expédition) : ils quittent la route
//   et la rejoignent en marche avant, par un changement de voie ;
// - odomètre (m parcourus, comptés en négatif en marche arrière), qui fait tourner les roues ;
// - marchandises qui passent d'un bâtiment à l'autre par les portes de marchandises
//   (`poserLesPortes`) : chaque traversée de mur passe dans l'axe de la porte la plus proche.
// L'écart à la référence est borné : à TRAJECTOIRES.rayonVirage m au plus de son chemin (du
// chemin par les portes pour une marchandise), sauf pendant une manœuvre de quai, près du
// quai. Aucune dépendance à three.js (« npm test »).
import { CHARIOT_PORTEUR, TRAJECTOIRES } from "./apparence.js";
import { parLesPortes, portesDeQuai } from "./batiments.js";
import { etatObjet, segmentActif } from "./donnees.js";

const PRECISION = 1e-6; // m : un arrêt est à quai s'il est à l'emplacement du quai
const LONGUEUR_MIN = 1e-9; // m : tronçon nul
const ANGLE_MIN = 1e-6; // rad : en deçà, le chemin ne tourne pas

const ajouter = ([ax, ay], [bx, by], k = 1) => [ax + k * bx, ay + k * by];
const ecart = ([ax, ay], [bx, by]) => [bx - ax, by - ay];
const norme = ([x, y]) => Math.hypot(x, y);
const scalaire = ([ax, ay], [bx, by]) => ax * bx + ay * by;
const direction = (cap) => [Math.cos(cap), Math.sin(cap)];
const capDe = ([x, y]) => Math.atan2(y, x);

/** Vecteur de même sens et de longueur 1 (nul s'il est nul). */
function unitaire(v) {
  const n = norme(v);
  return n > LONGUEUR_MIN ? [v[0] / n, v[1] / n] : [0, 0];
}

/** Angle de `de` à `vers` (rad) par le plus court chemin, entre −π et π. */
function tour(de, vers) {
  const e = (vers - de) % (2 * Math.PI);
  if (e > Math.PI) return e - 2 * Math.PI;
  return e < -Math.PI ? e + 2 * Math.PI : e;
}

/** Rangs des points d'un chemin qui ne doublent pas le précédent (tronçons nuls retirés). */
function rangsUtiles(chemin) {
  return chemin.map((_, k) => k).filter((k) => k === 0
    || norme(ecart(chemin[k - 1], chemin[k])) > LONGUEUR_MIN);
}

/** Chemin sans ses points doubles. */
const sansDoublons = (chemin) => rangsUtiles(chemin).map((k) => chemin[k]);

/** Contexte des trajectoires d'une scène : quais numérotés et leur porte, longueur des camions,
 * calculs faits à la demande pour chaque objet et gardés. */
export function creerTrajectoires(site, gabarits) {
  return { quais: portesDeQuai(site), longueurCamion: gabarits.camion[1], calculs: new WeakMap(),
    couverts: site.zones.filter((zone) => zone.hauteur > 0), portes: [], gabarits };
}

/** Portes de marchandises (batiments.js) par où passent les marchandises ; les calculs déjà
 * faits sont oubliés. */
export function poserLesPortes(contexte, portes) {
  contexte.portes = portes;
  contexte.calculs = new WeakMap();
}

/** Chemin affiché du segment i : celui de la scène, par les portes pour une marchandise. */
export function cheminAffiche(objet, i, contexte) {
  const chemin = objet.segments[i][2];
  if (!CHARIOT_PORTEUR.types.includes(objet.type)) return chemin;
  return parLesPortes(chemin, contexte.couverts, contexte.portes);
}

/** Quai {numero, x, y, porte} à l'emplacement duquel le camion s'arrête au segment i, ou null
 * (autre objet, trajet, ou arrêt ailleurs qu'à un quai). */
export function quaiDuSegment(objet, i, contexte) {
  const segment = objet.segments[i];
  if (objet.type !== "camion" || !segment || segment[2].length !== 1) return null;
  const [x, y] = segment[2][0];
  return contexte.quais.find((q) => Math.abs(q.x - x) < PRECISION
    && Math.abs(q.y - y) < PRECISION) ?? null;
}

/** Pose {x, y, cap} de l'objet à l'arrêt au segment i : celle de la référence ; un camion à quai
 * est retourné, l'arrière contre les butoirs de la porte ; à un quai à ciel ouvert, il est garé
 * en long, centré sur le quai, dans le sens de la rangée. */
export function poseDeRepos(objet, i, contexte) {
  const point = objet.segments[i][2][0];
  const cap = objet.capsRepos[i];
  const quai = quaiDuSegment(objet, i, contexte);
  if (!quai) return { x: point[0], y: point[1], cap };
  if (!quai.porte) return { x: point[0], y: point[1], cap: capDe(quai.sens) };
  const entree = direction(cap); // sens dans lequel le camion est entré dans le quai
  const fond = scalaire(ecart(point, quai.porte.point), entree) - TRAJECTOIRES.recul;
  const [x, y] = ajouter(point, entree, fond - contexte.longueurCamion / 2);
  return { x, y, cap: cap + Math.PI };
}

/** Points de l'arc qui arrondit le coin b du chemin a → b → c : tangent aux deux tronçons, de
 * rayon `rayonMax` au plus, et moins s'il devait prendre plus de la moitié d'un tronçon ; [b] si
 * le chemin ne tourne pas, ou fait demi-tour. */
function virage(a, b, c, rayonMax) {
  const [u, v] = [unitaire(ecart(a, b)), unitaire(ecart(b, c))];
  const angle = Math.acos(Math.max(-1, Math.min(1, scalaire(u, v))));
  if (angle < ANGLE_MIN || angle > Math.PI - ANGLE_MIN) return [b];
  const demi = Math.tan(angle / 2);
  const rayon = Math.min(rayonMax, Math.min(norme(ecart(a, b)), norme(ecart(b, c))) / 2 / demi);
  const debut = ajouter(b, u, -rayon * demi);
  const sens = Math.sign(u[0] * v[1] - u[1] * v[0]); // 1 : virage à gauche
  const centre = ajouter(debut, [-u[1] * sens, u[0] * sens], rayon);
  const depart = Math.atan2(debut[1] - centre[1], debut[0] - centre[0]);
  const nombre = Math.max(1, Math.ceil(angle / TRAJECTOIRES.pasArc));
  return Array.from({ length: nombre + 1 }, (_, k) => {
    const theta = depart + (sens * angle * k) / nombre;
    return [centre[0] + rayon * Math.cos(theta), centre[1] + rayon * Math.sin(theta)];
  });
}

/** Chemin aux coins arrondis (points rapprochés le long des arcs), sans points doubles. */
export function arrondir(chemin, rayon = TRAJECTOIRES.rayonVirage) {
  const points = sansDoublons(chemin);
  if (points.length < 3) return points;
  const sortie = [points[0]];
  for (let k = 1; k < points.length - 1; k++) {
    sortie.push(...virage(points[k - 1], points[k], points[k + 1], rayon));
  }
  sortie.push(points.at(-1));
  return sortie;
}

/** Parcours {points, caps, cumuls, longueur, arriere} : longueurs cumulées depuis le premier
 * point, sens de la marche ; `caps` (un par point) si la caisse n'est pas dans l'axe du chemin
 * (manœuvre), null sinon. */
function parcours({ points, caps = null, arriere = false }) {
  const rangs = rangsUtiles(points);
  const net = rangs.map((k) => points[k]);
  const cumuls = [0];
  for (let k = 1; k < net.length; k++) {
    cumuls.push(cumuls[k - 1] + norme(ecart(net[k - 1], net[k])));
  }
  return { points: net, caps: caps && rangs.map((k) => caps[k]), cumuls,
    longueur: cumuls.at(-1), arriere };
}

/** Point {x, y, cap} à la distance d du début d'un parcours ; cap : celui de la manœuvre, sinon
 * le sens du tronçon, retourné en marche arrière (null sur un parcours d'un seul point). */
function pointDuParcours({ points, caps, cumuls, arriere }, d) {
  if (points.length === 1) return { x: points[0][0], y: points[0][1], cap: caps?.[0] ?? null };
  let [bas, haut] = [1, points.length - 1]; // premier k tel que cumuls[k] ≥ d
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (cumuls[milieu] < d) bas = milieu + 1;
    else haut = milieu;
  }
  const [a, b] = [points[bas - 1], points[bas]];
  const part = Math.max(0, Math.min(1, (d - cumuls[bas - 1]) / (cumuls[bas] - cumuls[bas - 1])));
  const cap = caps ? caps[bas - 1] + tour(caps[bas - 1], caps[bas]) * part
    : capDe(ecart(a, b)) + (arriere ? Math.PI : 0);
  return { x: a[0] + part * (b[0] - a[0]), y: a[1] + part * (b[1] - a[1]), cap };
}

/** Points d'un parcours au-delà de la distance d, le premier à cette distance. */
function auDela(trace, d) {
  const { x, y } = pointDuParcours(trace, d);
  return [[x, y], ...trace.points.filter((_, k) => trace.cumuls[k] > d)];
}

/** Poses d'une manœuvre {points, caps} : l'arrière du camion va de `de` à `vers` le long d'une
 * courbe de Bézier qui part dans le sens `tDe` et arrive dans le sens `tVers` ; la caisse reste
 * dans l'axe de la marche de l'arrière (cap retourné en marche arrière), son centre à une
 * demi-longueur devant l'arrière. */
function manoeuvre(de, tDe, vers, tVers, arriere, longueur) {
  const k = TRAJECTOIRES.tangente * norme(ecart(de, vers));
  const p = [de, ajouter(de, tDe, k), ajouter(vers, tVers, -k), vers];
  const nombre = TRAJECTOIRES.pointsManoeuvre;
  const poses = Array.from({ length: nombre + 1 }, (_, n) => {
    const s = n / nombre;
    const poids = [(1 - s) ** 3, 3 * (1 - s) ** 2 * s, 3 * (1 - s) * s ** 2, s ** 3];
    const derivee = [3 * (1 - s) ** 2, 6 * (1 - s) * s, 3 * s ** 2];
    const point = [0, 1].map((j) => poids.reduce((somme, w, q) => somme + w * p[q][j], 0));
    const sens = [0, 1].map((j) => derivee.reduce((somme, w, q) => somme + w * (p[q + 1][j]
      - p[q][j]), 0));
    const cap = capDe(norme(sens) > LONGUEUR_MIN ? sens : (s < 1 ? tDe : tVers))
      + (arriere ? Math.PI : 0);
    return [ajouter(point, direction(cap), longueur / 2), cap];
  });
  return { points: poses.map(([point]) => point), caps: poses.map(([, cap]) => cap), arriere };
}

/** Arrière {point, sens d'entrée} d'un camion à sa pose de repos à quai, et la distance à
 * laquelle l'arrière tourne autour de l'entrée du quai `entree` : sa profondeur, au moins
 * TRAJECTOIRES.braquage m. */
function arriereAQuai(repos, entree, longueur) {
  const sens = direction(repos.cap + Math.PI); // l'arrière regarde le fond du quai
  const point = ajouter([repos.x, repos.y], sens, longueur / 2);
  const profondeur = Math.abs(scalaire(ecart(entree, point), sens));
  return { point, sens, rayon: Math.max(TRAJECTOIRES.braquage,
    Math.min(profondeur, TRAJECTOIRES.depassementMax)) };
}

/** Arrière d'un camion de pose {x, y, cap} : une demi-longueur derrière son centre. */
const arriereDe = ({ x, y, cap }, longueur) => ajouter([x, y], direction(cap), -longueur / 2);

/** Points d'un parcours jusqu'à la distance d, le dernier à cette distance. */
function enDeca(trace, d) {
  const { x, y } = pointDuParcours(trace, d);
  return [...trace.points.filter((_, k) => trace.cumuls[k] < d), [x, y]];
}

/** Sortie d'un quai en long : {courbe} en marche avant, par un changement de voie, jusqu'à la
 * route (le chemin après le quai), rejointe à TRAJECTOIRES.changementDeVoie m ; {reste}. */
function sortieEnLong(chemin, repos, longueur) {
  const trace = parcours({ points: sansDoublons(chemin).slice(1) });
  const d = Math.min(trace.longueur, TRAJECTOIRES.changementDeVoie);
  const jonction = pointDuParcours(trace, d);
  const courbe = manoeuvre(arriereDe(repos, longueur), direction(repos.cap),
    arriereDe({ ...jonction, cap: jonction.cap ?? repos.cap }, longueur),
    direction(jonction.cap ?? repos.cap), false, longueur);
  return { courbe, reste: arrondir(auDela(trace, d)) };
}

/** Arrivée à un quai en long : {avant} le chemin jusqu'à TRAJECTOIRES.changementDeVoie m avant
 * le point de la route d'où il part vers le quai ; {courbe} le changement de voie. */
function entreeEnLong(chemin, repos, longueur) {
  const trace = parcours({ points: sansDoublons(chemin).slice(0, -1) });
  const d = Math.max(0, trace.longueur - TRAJECTOIRES.changementDeVoie);
  const jonction = pointDuParcours(trace, d);
  const cap = jonction.cap ?? repos.cap;
  const courbe = manoeuvre(arriereDe({ ...jonction, cap }, longueur), direction(cap),
    arriereDe(repos, longueur), direction(repos.cap), false, longueur);
  return { avant: enDeca(trace, d), courbe };
}

/** Sortie d'un quai, de la pose de repos : {courbe} en marche avant jusqu'au chemin, que le
 * camion rejoint dans son axe, l'arrière à un quart de tour de l'entrée du quai (le premier coin
 * du chemin) ; puis {reste} du chemin, arrondi. */
function sortieDuQuai(chemin, repos, longueur) {
  const trace = parcours({ points: chemin });
  const arriere = arriereAQuai(repos, trace.points[1] ?? trace.points[0], longueur);
  const d = Math.min(trace.longueur, (trace.cumuls[1] ?? 0) + arriere.rayon + longueur / 2);
  const jonction = pointDuParcours(trace, d);
  const sens = direction(jonction.cap ?? repos.cap);
  const vers = ajouter([jonction.x, jonction.y], sens, -longueur / 2);
  const courbe = manoeuvre(arriere.point, direction(repos.cap), vers, sens, false, longueur);
  return { courbe, reste: arrondir(auDela(trace, d)) };
}

/** Arrivée à un quai : {avant} le chemin jusqu'à l'entrée du quai (son dernier coin), prolongé
 * jusqu'à ce que l'arrière la dépasse d'un quart de tour ({depassement} : ce prolongement) ;
 * puis {arriere} la marche arrière jusqu'à la pose de repos. */
function entreeAuQuai(chemin, repos, longueur) {
  const points = sansDoublons(chemin);
  const entree = points.at(-2) ?? points[0];
  const fond = arriereAQuai(repos, entree, longueur);
  const avant = points.length > 2 ? unitaire(ecart(points.at(-3), entree))
    : [fond.sens[1], -fond.sens[0]]; // sans coin : de côté
  const depart = ajouter(entree, avant, fond.rayon);
  const centre = ajouter(depart, avant, longueur / 2);
  const arriere = manoeuvre(depart, [-avant[0], -avant[1]], fond.point, fond.sens, true,
    longueur);
  return { avant: [...points.slice(0, -1), centre], depassement: [entree, centre], arriere };
}

/** Morceaux [{points, caps, arriere}] du trajet du segment i : chemin arrondi ; sortie du quai
 * si le camion y était arrêté ; dépassement et marche arrière s'il s'y arrête ensuite. */
function morceauxDuTrajet(objet, i, contexte) {
  const chemin = cheminAffiche(objet, i, contexte);
  const longueur = contexte.longueurCamion;
  const quais = [i - 1, i + 1].map((k) => quaiDuSegment(objet, k, contexte));
  const [depart, arrivee] = [i - 1, i + 1].map((k, j) => (quais[j]
    ? poseDeRepos(objet, k, contexte) : null));
  const enAvant = (points) => {
    if (!depart) return [{ points: arrondir(points) }];
    const sortie = quais[0].porte ? sortieDuQuai : sortieEnLong;
    const { courbe, reste } = sortie(points, depart, longueur);
    return reste.length > 1 ? [courbe, { points: reste }] : [courbe];
  };
  if (!arrivee) return enAvant(chemin);
  if (!quais[1].porte) {
    const entree = entreeEnLong(chemin, arrivee, longueur);
    return [...enAvant(entree.avant), entree.courbe];
  }
  const entree = entreeAuQuai(chemin, arrivee, longueur);
  return [...enAvant(entree.avant), entree.arriere];
}

/** Pièces {parcours, debut, fin, rampes} : chacune prend une part de la durée du trajet (debut et
 * fin, de 0 à 1) à la mesure de sa longueur, la marche arrière comptant
 * TRAJECTOIRES.lenteurArriere fois ; rampes [début, fin] : elle accélère ou freine à côté d'un
 * arrêt (`arrets`, avant et après le trajet) et d'un changement de sens. */
function repartir(morceaux, arrets) {
  const liste = morceaux.map(parcours);
  const poids = liste.map((p) => p.longueur * (p.arriere ? TRAJECTOIRES.lenteurArriere : 1));
  const total = poids.reduce((a, b) => a + b, 0);
  let debut = 0;
  return liste.map((trace, k) => {
    const dernier = k === liste.length - 1;
    const fin = dernier ? 1 : debut + (total > 0 ? poids[k] / total : 0);
    const rampes = [k === 0 ? arrets[0] : liste[k - 1].arriere !== trace.arriere,
      dernier ? arrets[1] : liste[k + 1].arriere !== trace.arriere];
    const piece = { parcours: trace, debut, fin, rampes };
    debut = fin;
    return piece;
  });
}

/** Part du parcours faite à la part p (0 à 1) de sa durée : vitesse constante, sauf sur la part
 * TRAJECTOIRES.rampe de la durée au début (accélération) et à la fin (freinage), si `rampes`
 * [début, fin] le demande. */
export function avancement(p, [auDebut, aLaFin]) {
  const a = TRAJECTOIRES.rampe;
  const [ra, rb] = [auDebut ? a : 0, aLaFin ? a : 0];
  const vitesse = 1 / (1 - ra / 2 - rb / 2);
  const q = Math.max(0, Math.min(1, p));
  if (q < ra) return (vitesse * q * q) / (2 * ra);
  if (q > 1 - rb) return 1 - (vitesse * (1 - q) ** 2) / (2 * rb);
  return vitesse * (q - ra / 2);
}

/** Pièces d'une suite de morceaux dans un même sens réunies en une : leur vitesse reste la même
 * d'un morceau à l'autre (pas de rampe entre eux). */
function reunir(pieces) {
  const reunies = [];
  for (const piece of pieces) {
    const precedente = reunies.at(-1);
    if (!precedente || precedente.at(-1).parcours.arriere !== piece.parcours.arriere) {
      reunies.push([piece]);
    } else precedente.push(piece);
  }
  return reunies;
}

/** Calcul du segment i, gardé : {repos, quai} à l'arrêt, {pieces} en route ; parcouru : m
 * parcourus pendant le segment (en négatif en marche arrière). */
function segmentCalcule(objet, i, contexte) {
  if (!contexte.calculs.has(objet)) contexte.calculs.set(objet, { segments: [], odometres: [0] });
  const calculs = contexte.calculs.get(objet);
  if (calculs.segments[i]) return calculs.segments[i];
  const segments = objet.segments;
  let calcul;
  if (segments[i][2].length === 1) {
    calcul = { repos: poseDeRepos(objet, i, contexte), parcouru: 0,
      quai: quaiDuSegment(objet, i, contexte)?.numero ?? null };
  } else {
    const arrets = [i - 1, i + 1].map((k) => segments[k]?.[2].length === 1);
    const pieces = repartir(morceauxDuTrajet(objet, i, contexte), arrets);
    calcul = { pieces: reunir(pieces), parcouru: pieces.reduce((somme, { parcours: p }) => somme
      + (p.arriere ? -p.longueur : p.longueur), 0) };
  }
  calculs.segments[i] = calcul;
  return calcul;
}

/** Odomètre de l'objet au début du segment i : somme de ce qu'il a parcouru avant. */
function odometreAuDebut(objet, i, contexte) {
  segmentCalcule(objet, 0, contexte); // crée les calculs de l'objet
  const { odometres } = contexte.calculs.get(objet);
  while (odometres.length <= i) {
    const k = odometres.length - 1;
    odometres.push(odometres[k] + segmentCalcule(objet, k, contexte).parcouru);
  }
  return odometres[i];
}

/** Pose {x, y, cap, parcouru} sur un groupe de pièces dans un même sens, à la part p (0 à 1) de
 * la durée du trajet : le groupe suit une seule rampe, de sa première à sa dernière pièce. */
function poseDansLeGroupe(groupe, p) {
  const [premiere, derniere] = [groupe[0], groupe.at(-1)];
  const longueur = groupe.reduce((somme, piece) => somme + piece.parcours.longueur, 0);
  const duree = derniere.fin - premiere.debut;
  const part = duree > 0 ? (p - premiere.debut) / duree : 1;
  let d = avancement(part, [premiere.rampes[0], derniere.rampes[1]]) * longueur;
  const signe = premiere.parcours.arriere ? -1 : 1;
  const parcouru = signe * d;
  for (const { parcours: trace } of groupe) {
    if (d <= trace.longueur || trace === derniere.parcours) {
      return { ...pointDuParcours(trace, Math.min(d, trace.longueur)), parcouru };
    }
    d -= trace.longueur;
  }
  return null; // jamais : la dernière pièce répond
}

/** Pose {x, y, cap, parcouru} à la part p (0 à 1) de la durée d'un trajet ; parcouru : m depuis
 * le début du trajet (en négatif en marche arrière). */
function poseEnRoute(groupes, p) {
  let parcouru = 0;
  for (const [k, groupe] of groupes.entries()) {
    if (p > groupe.at(-1).fin && k < groupes.length - 1) {
      parcouru += groupe.reduce((s, { parcours: t }) => s + (t.arriere ? -1 : 1) * t.longueur, 0);
      continue;
    }
    const pose = poseDansLeGroupe(groupe, p);
    return { ...pose, parcouru: parcouru + pose.parcouru };
  }
  return null; // aucune pièce : jamais pour un trajet de la scène
}

/** {x, y, cap, odometre, quai} affichés de l'objet à l'instant t, ou null s'il est masqué (aux
 * mêmes instants qu'etatObjet). odometre : m parcourus depuis son apparition (en négatif en
 * marche arrière) ; quai : numéro du quai où le camion est arrêté, ou null. */
export function etatAffiche(objet, t, contexte) {
  const i = segmentActif(objet, t);
  if (i < 0) return null;
  const calcul = segmentCalcule(objet, i, contexte);
  const odometre = odometreAuDebut(objet, i, contexte);
  if (calcul.repos) return { ...calcul.repos, odometre, quai: calcul.quai };
  const [t0, t1] = objet.segments[i];
  const pose = poseEnRoute(calcul.pieces, (t - t0) / (t1 - t0));
  return { x: pose.x, y: pose.y, cap: pose.cap ?? etatObjet(objet, t).cap,
    odometre: odometre + pose.parcouru, quai: null };
}

/** Arrêts des camions à quai : Map numéro du quai → [{debut, fin, objet}], par début croissant
 * (fin null : jusqu'au bout de la scène). */
export function arretsAQuai(objets, contexte) {
  const arrets = new Map(contexte.quais.map((q) => [q.numero, []]));
  for (const objet of objets) {
    objet.segments.forEach(([debut, fin], i) => {
      const quai = quaiDuSegment(objet, i, contexte);
      if (quai) arrets.get(quai.numero).push({ debut, fin, objet });
    });
  }
  for (const liste of arrets.values()) liste.sort((a, b) => a.debut - b.debut);
  return arrets;
}

/** Arrêt en cours à l'instant t parmi des arrêts triés par début, ou null. */
export function arretEnCours(arrets, t) {
  let [bas, haut] = [0, arrets.length];
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (arrets[milieu].debut <= t) bas = milieu + 1;
    else haut = milieu;
  }
  const arret = arrets[bas - 1];
  return arret && (arret.fin === null || t < arret.fin) ? arret : null;
}

/** Axes [a, b] qu'occupe la caisse des camions pendant leurs manœuvres de quai et à quai (pour
 * le décor) : l'axe du camion à chaque pose des manœuvres et à quai ; le dépassement, prolongé
 * d'une demi-longueur de camion à chaque bout. Une même manœuvre (même quai, même chemin) n'est
 * comptée qu'une fois. */
export function axesDesManoeuvres(objets, contexte) {
  const demi = contexte.longueurCamion / 2;
  const vues = new Set();
  const axes = [];
  for (const objet of objets.filter((o) => o.type === "camion")) {
    objet.segments.forEach(([, , chemin], i) => {
      const quais = [i - 1, i, i + 1].map((k) => quaiDuSegment(objet, k, contexte)?.numero);
      const cle = `${quais.join(",")}:${JSON.stringify(chemin)}`;
      if (quais.every((q) => q === undefined) || vues.has(cle)) return;
      vues.add(cle);
      for (const [[x, y], cap] of posesDesManoeuvres(objet, i, contexte)) {
        const u = direction(cap);
        axes.push([ajouter([x, y], u, -demi), ajouter([x, y], u, demi)]);
      }
    });
  }
  return axes;
}

/** Poses [point, cap] des manœuvres du segment i d'un camion : à quai, la pose de repos ; en
 * route, la sortie du quai d'où il part, le dépassement (un point tous les mètres) et la marche
 * arrière vers celui où il va. */
function posesDesManoeuvres(objet, i, contexte) {
  const longueur = contexte.longueurCamion;
  const chemin = objet.segments[i][2];
  const poses = (morceau) => morceau.points.map((point, k) => [point, morceau.caps[k]]);
  if (chemin.length === 1) {
    if (!quaiDuSegment(objet, i, contexte)) return [];
    const { x, y, cap } = poseDeRepos(objet, i, contexte);
    return [[[x, y], cap]];
  }
  const liste = [];
  const [avant, apres] = [i - 1, i + 1].map((k) => quaiDuSegment(objet, k, contexte));
  if (avant) {
    const sortie = avant.porte ? sortieDuQuai : sortieEnLong;
    liste.push(...poses(sortie(chemin, poseDeRepos(objet, i - 1, contexte), longueur).courbe));
  }
  if (apres && !apres.porte) {
    liste.push(...poses(entreeEnLong(chemin, poseDeRepos(objet, i + 1, contexte), longueur)
      .courbe));
  } else if (apres) {
    const entree = entreeAuQuai(chemin, poseDeRepos(objet, i + 1, contexte), longueur);
    const [a, b] = entree.depassement;
    const pas = Math.max(1, Math.ceil(norme(ecart(a, b))));
    const cap = capDe(ecart(a, b));
    for (let k = 0; k <= pas; k++) liste.push([ajouter(a, ecart(a, b), k / pas), cap]);
    liste.push(...poses(entree.arriere));
  }
  return liste;
}
