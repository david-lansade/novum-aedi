// Scène 3D exportée par avelis_flux/scene_3d.py : chargement, position de chaque objet à un
// instant donné, horloge. Aucune dépendance à React ni à three.js (testé par « npm test »).
//
// Même calcul que scene_3d.positions_scene, donc que Usine.positions : le segment actif est le
// dernier commencé (t0 ≤ t) s'il n'est pas fini (t < t1, t1 = null : jusqu'à la fin) ; l'objet y
// est fixe (un seul point) ou avance le long du chemin selon la part du temps écoulée.
// Coordonnées du plan en mètres : x vers l'est, y vers le nord. Temps en minutes d'ouverture.

export const VERSION_SCENE = 4; // scene_3d.VERSION_SCENE
export const TYPES_OBJETS = ["camion", "lot", "kit 2D", "pod", "module"];
const MINUTES_PAR_HEURE = 60;
const CAP_PAR_DEFAUT = 0; // vers l'est, pour un objet qui n'a encore jamais roulé

/** Direction (rad, depuis l'est vers le nord) du dernier tronçon non nul d'un chemin, ou null. */
function capFinal(chemin) {
  for (let i = chemin.length - 1; i > 0; i--) {
    const [ax, ay] = chemin[i - 1];
    const [bx, by] = chemin[i];
    if (bx !== ax || by !== ay) return Math.atan2(by - ay, bx - ax);
  }
  return null;
}

/** Vérifie la version, puis prépare chaque objet : débuts de segments (recherche
 * dichotomique) et cap de repos de chaque segment, hérité du dernier trajet. */
export function preparerScene(scene) {
  if (scene.version !== VERSION_SCENE) {
    throw new Error(
      `version de scène inattendue : ${scene.version} (attendue : ${VERSION_SCENE})`);
  }
  for (const objet of scene.objets) preparerObjet(objet);
  return scene;
}

/** Prépare un objet : débuts de ses segments et cap de repos de chaque segment ; le renvoie. */
export function preparerObjet(objet) {
  objet.debuts = objet.segments.map((segment) => segment[0]);
  let cap = CAP_PAR_DEFAUT;
  objet.capsRepos = objet.segments.map(([, , chemin]) => {
    const capAvant = cap;
    cap = capFinal(chemin) ?? cap;
    return capAvant;
  });
  return objet;
}

/** Charge et prépare la scène (fetch) ; message en français si elle manque. */
export async function chargerScene(adresse) {
  const reponse = await fetch(adresse, { cache: "no-store" });
  if (!reponse.ok) throw new Error(`scène introuvable (${adresse} : erreur ${reponse.status})`);
  return preparerScene(await reponse.json());
}

/** Indice du dernier début ≤ t (bisect_right − 1), −1 si aucun. */
function dernierDebut(debuts, t) {
  let bas = 0;
  let haut = debuts.length;
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (debuts[milieu] <= t) bas = milieu + 1;
    else haut = milieu;
  }
  return bas - 1;
}

/** Point à la part `fraction` (0 à 1) de la longueur du chemin et direction du tronçon où il se
 * trouve (null sur un tronçon nul) ; même parcours que simulation.portion_de_chemin. */
export function pointSurChemin(chemin, fraction) {
  let longueur = 0;
  for (let i = 1; i < chemin.length; i++) {
    longueur += Math.hypot(chemin[i][0] - chemin[i - 1][0], chemin[i][1] - chemin[i - 1][1]);
  }
  let reste = Math.max(0, Math.min(1, fraction)) * longueur;
  for (let i = 1; i < chemin.length; i++) {
    const [ax, ay] = chemin[i - 1];
    const [bx, by] = chemin[i];
    const troncon = Math.hypot(bx - ax, by - ay);
    if (reste <= troncon) {
      const k = troncon > 0 ? reste / troncon : 0;
      const cap = troncon > 0 ? Math.atan2(by - ay, bx - ax) : null;
      return { x: ax + k * (bx - ax), y: ay + k * (by - ay), cap };
    }
    reste -= troncon;
  }
  const [x, y] = chemin[chemin.length - 1];
  return { x, y, cap: null };
}

/** Indice du segment actif à l'instant t : le dernier commencé, s'il n'est pas fini ; −1 si
 * l'objet est masqué. */
export function segmentActif(objet, t) {
  const i = dernierDebut(objet.debuts, t);
  if (i < 0) return -1;
  const t1 = objet.segments[i][1];
  return t1 !== null && t >= t1 ? -1 : i;
}

/** {x, y, cap} de l'objet à l'instant t, ou null s'il est masqué. Le cap (rad) est le sens de
 * la marche ; à l'arrêt, celui du dernier trajet. */
export function etatObjet(objet, t) {
  const i = segmentActif(objet, t);
  if (i < 0) return null;
  const [t0, t1, chemin] = objet.segments[i];
  if (chemin.length === 1) return { x: chemin[0][0], y: chemin[0][1], cap: objet.capsRepos[i] };
  const point = pointSurChemin(chemin, (t - t0) / (t1 - t0));
  return { ...point, cap: point.cap ?? objet.capsRepos[i] };
}

/** {id: {x, y, cap, type}} des objets visibles à l'instant t. */
export function positions(scene, t) {
  const visibles = {};
  for (const objet of scene.objets) {
    const etat = etatObjet(objet, t);
    if (etat !== null) visibles[objet.id] = { ...etat, type: objet.type };
  }
  return visibles;
}

/** Centre {cx, cy} et étendue (plus grand côté, m) du foncier et de la route publique : cadre
 * de la caméra et enveloppe des objets animés. */
export function cadreDuSite(site) {
  const points = [...site.contours.flatMap((contour) => contour.points), ...site.route_publique];
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const [xmin, xmax, ymin, ymax] = [Math.min(...xs), Math.max(...xs), Math.min(...ys),
    Math.max(...ys)];
  return { cx: (xmin + xmax) / 2, cy: (ymin + ymax) / 2,
    etendue: Math.max(xmax - xmin, ymax - ymin) };
}

/** {jour, heure, minute} affichés pour l'instant t (simulation._jour_heure_minute). */
function jourHeureMinute(t, temps) {
  const entier = Math.floor(t);
  const jour = Math.floor(entier / temps.minutes_jour);
  const total = temps.heure_ouverture * MINUTES_PAR_HEURE + entier - jour * temps.minutes_jour;
  const heure = Math.floor(total / MINUTES_PAR_HEURE);
  return { jour: jour + 1, heure, minute: total - heure * MINUTES_PAR_HEURE };
}

const deuxChiffres = (n) => String(n).padStart(2, "0");

/** Horloge du tableau de pilotage, « Jour N · HH:MM » (simulation.horloge). */
export function horloge(t, temps) {
  const { jour, heure, minute } = jourHeureMinute(t, temps);
  return `Jour ${jour} · ${deuxChiffres(heure)}:${deuxChiffres(minute)}`;
}

/** Horodatage compact, « JN HH:MM » (simulation.horloge_courte). */
export function horlogeCourte(t, temps) {
  const { jour, heure, minute } = jourHeureMinute(t, temps);
  return `J${jour} ${deuxChiffres(heure)}:${deuxChiffres(minute)}`;
}

/** Instant t (min simulées) d'une horloge tapée à la main : « Jour 2 · 21:21 », « J2 21h21 »,
 * « jour 3 » (à l'ouverture) ou « 21:21 » (jour de `tActuel`) ; null si le texte ne se lit pas
 * ou si l'heure est hors de la journée affichée (ouverture à ouverture + minutes_jour). */
export function instantSaisi(texte, temps, tActuel) {
  const motif = /^\s*(?:j(?:our)?\s*(\d+))?\s*[·,.\-]?\s*(?:(\d{1,2})\s*[:h]\s*(\d{0,2}))?\s*$/i;
  const lu = motif.exec(texte);
  if (!lu || (lu[1] === undefined && lu[2] === undefined)) return null;
  const jour = lu[1] === undefined ? Math.floor(tActuel / temps.minutes_jour) : Number(lu[1]) - 1;
  const ouverture = temps.heure_ouverture * MINUTES_PAR_HEURE;
  let minutes = lu[2] === undefined ? ouverture : Number(lu[2]) * MINUTES_PAR_HEURE
    + Number(lu[3] || 0);
  if (minutes < ouverture) minutes += 24 * MINUTES_PAR_HEURE; // après minuit
  const dansJour = minutes - ouverture;
  if (jour < 0 || Number(lu[3] || 0) >= MINUTES_PAR_HEURE || dansJour > temps.minutes_jour) {
    return null;
  }
  return jour * temps.minutes_jour + dansJour;
}
