// Étiquettes du site : texte et point 3D (plan, m) de chaque nom posé dans la scène. Calque et
// projection à l'écran : Etiquettes.jsx. Aucune dépendance à three.js (testé par « npm test »).
import { ECHELLE, NORD, PORTAIL } from "./apparence.js";
import { centreDesBatiments } from "./cadrage.js";
import { pointLePlusProche } from "./traces.js";

export const HAUTEUR_ETIQUETTE = 2; // m au-dessus de ce qu'elle nomme

/** Moyenne des points d'un contour. */
function centre(points) {
  return [0, 1].map((k) => points.reduce((somme, p) => somme + p[k], 0) / points.length);
}

/** Point de la route publique où poser son nom : le plus proche des bâtiments, donc dans la vue
 * d'ensemble (la route longe le site, ses bouts sortent du cadre). */
export function ancreRoute(site) {
  return pointLePlusProche(site.route_publique, centreDesBatiments(site));
}

/** Point du nom du nord (au bout de la flèche) et de l'échelle (sous la barre). */
export const ANCRE_NORD = [NORD.x, NORD.y + NORD.longueur / 2 + 4];
export const ANCRE_ECHELLE = [ECHELLE.x + ECHELLE.longueur / 2, ECHELLE.y - 5];

/** Étiquettes du site : {cle, texte, position (plan, m), discrete, toujours, murs}. Les repères
 * (nord, échelle) restent affichés quand les noms sont masqués. Les quais n'ont pas de nom : il
 * recouvrait celui des zones voisines, et la légende donne leur couleur. `murs` : hauteur du
 * bâtiment nommé, dont l'étiquette suit le haut des murs quand ils s'abaissent. */
export function etiquettesDuSite(site) {
  const etiquettes = site.zones.map((zone) => ({
    cle: `zone ${zone.nom}`, texte: zone.libelle, murs: zone.hauteur,
    position: [zone.x + zone.largeur / 2, zone.y + zone.profondeur / 2,
      zone.hauteur + HAUTEUR_ETIQUETTE],
  }));
  for (const contour of site.contours.filter((c) => !c.utilise)) {
    etiquettes.push({ cle: `contour ${contour.nom}`, texte: `${contour.nom} (non utilisée)`,
      position: [...centre(contour.points), HAUTEUR_ETIQUETTE], discrete: true });
  }
  etiquettes.push(
    { cle: "route", texte: "Route publique", position: [...ancreRoute(site), HAUTEUR_ETIQUETTE],
      discrete: true },
    { cle: "portail", texte: "Portail", position: [...site.portail,
      PORTAIL.hauteur + HAUTEUR_ETIQUETTE] },
    { cle: "nord", texte: "N", toujours: true, position: [...ANCRE_NORD, HAUTEUR_ETIQUETTE] },
    { cle: "échelle", texte: `${ECHELLE.longueur} m`, toujours: true,
      position: [...ANCRE_ECHELLE, HAUTEUR_ETIQUETTE] },
  );
  return etiquettes;
}
