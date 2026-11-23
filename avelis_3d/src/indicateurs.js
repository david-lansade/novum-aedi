// Contenu des panneaux de l'interface, calculé sans React (testé par « npm test ») : cartes
// d'indicateurs, recherche d'un objet, instant où le montrer, repères du curseur de temps.
// Toutes les valeurs viennent du tableau de pilotage (pilotage.js) : rien n'est inventé.
import { etatObjet } from "./donnees.js";
import { valeursPilotage } from "./pilotage.js";

export const HEURE_MIN = 60; // la variation d'une carte se lit sur la dernière heure simulée
export const RESULTATS_MAX = 8; // propositions de la recherche
const NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const MOINS = "−"; // signe moins typographique

/** Nombre à la française (1 décimale au plus), « — » s'il est inconnu. */
export function formater(n) {
  return n === null || n === undefined ? "—" : NOMBRE.format(n);
}

/** Écart signé, « +2 », « −0,6 » ou « 0 ». */
export function signe(n) {
  const texte = formater(Math.abs(n));
  if (texte === "0") return "0";
  return n > 0 ? `+${texte}` : `${MOINS}${texte}`;
}

/** Variation d'un compte sur la dernière heure : {texte, ton}. Une hausse est « bonne » pour
 * ce qui sort de l'usine, neutre ailleurs (un en-cours ou un stock qui monte n'est ni bien ni
 * mal en soi). */
function variationHoraire(maintenant, avant, cle, bonne) {
  const ecart = maintenant[cle] - avant[cle];
  const ton = ecart === 0 ? "stable" : bonne && ecart > 0 ? "bon" : "neutre";
  return { texte: `${signe(ecart)} en 1 h`, ton };
}

/** Cartes d'indicateurs à l'instant t : {cle, libelle, valeur, detail, variation {texte, ton,
 * titre?}}. La première compare les terminés du jour à l'objectif au prorata de l'heure. */
export function cartesIndicateurs(scene, t) {
  const v = valeursPilotage(scene, t);
  const avant = valeursPilotage(scene, Math.max(0, t - HEURE_MIN));
  const ecart = v.termines_jour - v.objectif_heure;
  const variation = (cle, bonne = false) => variationHoraire(v, avant, cle, bonne);
  return [
    { cle: "termines", libelle: "Terminés aujourd'hui", valeur: formater(v.termines_jour),
      detail: `objectif ${formater(v.objectif_heure)} à cette heure`,
      variation: { texte: signe(Math.round(ecart * 10) / 10),
        ton: ecart >= 0 ? "bon" : "alerte", titre: "Écart à l'objectif à cette heure" } },
    { cle: "expedies", libelle: "Expédiés aujourd'hui", valeur: formater(v.expedies_jour),
      detail: `${formater(v.expedies)} au total`, variation: variation("expedies", true) },
    { cle: "en_cours", libelle: "En-cours", valeur: formater(v.en_cours),
      detail: `${formater(v.pods_en_cours)} pods en cours`, variation: variation("en_cours") },
    { cle: "stock_pf", libelle: "Stock produits finis", valeur: formater(v.stock_pf),
      detail: `matières : ${formater(v.stock_matieres)} kits`,
      variation: variation("stock_pf") },
    { cle: "camions", libelle: "Camions sur site", valeur: formater(v.camions_sur_site),
      detail: "présents à cet instant", variation: variation("camions_sur_site") },
  ];
}

/** Rang d'un objet pour un texte cherché (en minuscules) : 0 identifiant qui commence par le
 * texte, 1 identifiant qui le contient, 2 libellé qui le contient, null sinon. */
function rang(objet, texte) {
  const id = objet.id.toLowerCase();
  if (id.startsWith(texte)) return 0;
  if (id.includes(texte)) return 1;
  return objet.libelle.toLowerCase().includes(texte) ? 2 : null;
}

/** Les objets qui répondent au texte, les meilleurs d'abord, puis dans l'ordre de la scène. */
export function rechercherObjets(scene, texte, nombre = RESULTATS_MAX) {
  const cherche = texte.trim().toLowerCase();
  if (cherche === "") return [];
  const trouves = [];
  for (const objet of scene.objets) {
    const r = rang(objet, cherche);
    if (r !== null) trouves.push([r, trouves.length, objet]);
  }
  return trouves.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, nombre).map((x) => x[2]);
}

/** Instant où montrer l'objet : t s'il y est visible ; sinon le début de son prochain segment,
 * ou à défaut celui du dernier (l'objet a déjà quitté le site). */
export function instantVisible(objet, t) {
  if (etatObjet(objet, t) !== null) return t;
  const suivant = objet.segments.find(([t0]) => t0 > t);
  return (suivant ?? objet.segments[objet.segments.length - 1])[0];
}

/** Repères du curseur de temps, en part de la durée (0 à 1) : début de chaque jour (avec son
 * numéro) et instants d'affichage des alertes. */
export function reperesTemps(scene) {
  const { duree, minutes_jour: minutes } = scene.temps;
  const jours = [];
  for (let debut = 0, n = 1; debut < duree; debut += minutes, n += 1) {
    jours.push({ part: debut / duree, numero: n });
  }
  const alertes = scene.tracabilite.alertes.map((alerte) => Math.min(1, alerte[1] / duree));
  return { jours, alertes };
}
