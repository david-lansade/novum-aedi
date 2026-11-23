// Logistique de la vue 3D, tirée des trajets des marchandises de la scène (sans la changer) :
// portes de marchandises là où elles passent d'un bâtiment à l'autre (batiments.js), trajets
// affichés par ces portes (trajectoires.js), chariots élévateurs garés qui viennent les porter
// (chariots.js) et instants de passage par chaque porte (ouverture, gyrophare). Aucune
// dépendance à three.js (testé par « npm test »).
import { GRAINE_DECOR } from "./apparence.js";
import { cheminsDesMarchandises, portesDeMarchandises } from "./batiments.js";
import { flotteDeChariots, passagesDesPortes } from "./chariots.js";
import { creerOccupation, enginsDuDecor, racksDesStocks } from "./decor.js";
import { poserLesPortes } from "./trajectoires.js";

/** Garages des chariots : Map nom de zone → places [{x, y, angle}] (decor.js). */
export function garagesDuSite(scene) {
  const occupation = creerOccupation(scene.site, scene.objets, scene.gabarits);
  const racks = racksDesStocks(scene.site, occupation, GRAINE_DECOR);
  const garages = new Map();
  for (const e of enginsDuDecor(scene.site, occupation, racks, GRAINE_DECOR)) {
    if (!e.garage) continue;
    if (!garages.has(e.zone)) garages.set(e.zone, []);
    garages.get(e.zone).push(e);
  }
  return garages;
}

/** Logistique {portes, chariots, passages} de la scène ; pose les portes dans le contexte des
 * trajectoires (les marchandises y passent). `precedentes` : portes d'une scène précédente du
 * même site, gardées si elles sont les mêmes (les murs ne sont pas redessinés). */
export function creerLogistique(scene, contexte, precedentes = null) {
  const calculees = portesDeMarchandises(scene.site, cheminsDesMarchandises(scene.objets));
  const portes = precedentes && JSON.stringify(precedentes) === JSON.stringify(calculees)
    ? precedentes : calculees;
  poserLesPortes(contexte, portes);
  const chariots = flotteDeChariots(scene, contexte, garagesDuSite(scene));
  return { portes, chariots, passages: passagesDesPortes(scene, contexte, chariots) };
}
