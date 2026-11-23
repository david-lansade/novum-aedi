// Tableau de pilotage, alertes et événements de traçabilité à un instant donné, d'après la
// scène (version 2) exportée par avelis_flux/scene_3d.py. Aucune dépendance à React ni à
// three.js (testé par « npm test »).
//
// Même calcul que scene_3d.pilotage_scene, alertes_affichees_scene et evenements_affiches, donc
// que le tableau de pilotage de la vue 2 : un instant compte dès qu'il est ≤ t ; « aujourd'hui »
// part du début du jour en cours ; l'outil de pilotage n'affiche un événement ou une alerte
// qu'après son délai de lecture (t_affichage), et jamais un événement non lu.

export const NB_ALERTES_AFFICHEES = 9; // scene_3d.NB_ALERTES_AFFICHEES (SPEC §4.3)
const T_AFFICHAGE = 3; // [t, evenement, zone, t_affichage, message]
const T_AFFICHAGE_ALERTE = 1; // [t, t_affichage, nature, id, type, zone, message]

/** Nombre d'éléments triés ≤ t (bisect_right) ; `cle` lit l'instant d'un élément. */
function compter(elements, t, cle = (x) => x) {
  let bas = 0;
  let haut = elements.length;
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (cle(elements[milieu]) <= t) bas = milieu + 1;
    else haut = milieu;
  }
  return bas;
}

/** Nombre d'instants triés du jour en cours : debutJour ≤ instant ≤ t (bisect_left). */
function compterDuJour(instants, t, debutJour) {
  let bas = 0;
  let haut = instants.length;
  while (bas < haut) {
    const milieu = (bas + haut) >> 1;
    if (instants[milieu] < debutJour) bas = milieu + 1;
    else haut = milieu;
  }
  return compter(instants, t) - bas;
}

/** Dernière valeur échantillonnée (tous les `pas`, depuis t = 0) à l'instant t, ou null. */
function echantillon(echantillons, cle, t) {
  const valeurs = echantillons[cle];
  if (valeurs.length === 0) return null;
  const i = Math.floor(t / echantillons.pas);
  return valeurs[Math.max(0, Math.min(i, valeurs.length - 1))];
}

/** Alerte déjà affichée à l'instant t ? Les alertes sont triées par t_affichage. */
const tAffichageAlerte = (alerte) => alerte[T_AFFICHAGE_ALERTE];

/** Tableau de pilotage à l'instant t : terminés et expédiés du jour, objectif à cette heure,
 * expédiés au total, en-cours, stocks, pods en cours, camions sur site, alertes affichées. */
export function valeursPilotage(scene, t) {
  const p = scene.pilotage;
  const minutes = scene.temps.minutes_jour;
  const debutJour = Math.floor(t / minutes) * minutes;
  return {
    termines_jour: compterDuJour(p.entrees_pf, t, debutJour),
    objectif_heure: (p.objectif_jour * (t - debutJour)) / minutes,
    expedies_jour: compterDuJour(p.expeditions, t, debutJour),
    expedies: compter(p.expeditions, t),
    en_cours: compter(p.of, t) - compter(p.entrees_pf, t),
    stock_matieres: echantillon(p.echantillons, "stock_matieres", t),
    stock_pf: echantillon(p.echantillons, "stock_pf", t),
    pods_en_cours: compter(p.debuts_pods, t) - compter(p.fins_pods, t),
    camions_sur_site: p.camions.filter(([arrivee, sortie]) =>
      arrivee <= t && (sortie === null || t < sortie)).length,
    alertes: compter(scene.tracabilite.alertes, t, tAffichageAlerte),
  };
}

/** Les `nombre` dernières alertes déjà affichées (t_affichage ≤ t), la plus récente d'abord. */
export function alertesAffichees(scene, t, nombre = NB_ALERTES_AFFICHEES) {
  const alertes = scene.tracabilite.alertes;
  const fin = compter(alertes, t, tAffichageAlerte);
  return alertes.slice(Math.max(0, fin - nombre), fin).reverse();
}

/** Événements de l'objet déjà affichés à l'instant t (lus, t_affichage ≤ t), dans l'ordre du
 * journal. */
export function evenementsAffiches(objet, t) {
  return objet.evenements.filter((e) => e[T_AFFICHAGE] !== null && e[T_AFFICHAGE] <= t);
}
