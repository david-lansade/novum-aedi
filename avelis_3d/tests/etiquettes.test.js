// Tests de src/etiquettes.js et de la vue d'ensemble (« npm test ») sur le site des trois
// implantations du jeu de référence : entrée des camions, noms et repères visibles, hors des
// cartes ; repères hors du foncier et des routes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { ECHELLE, NORD } from "../src/apparence.js";
import {
  MARGES_CARTES, REMPLISSAGE, VUE_ENSEMBLE, axesEcran, cadrer, pointsVueEnsemble, projeter,
} from "../src/cadrage.js";
import { ANCRE_ECHELLE, ANCRE_NORD, ancreRoute, etiquettesDuSite } from "../src/etiquettes.js";
import { dansPolygone, distanceAuBord, distanceAuSegment } from "../src/traces.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const SITES = Object.entries(reference.sites);
const FENETRES = [[1600, 900], [1280, 650]]; // tailles d'écran contrôlées
const RETRAIT_PX = 24; // un nom, centré sur son point, déborde de la moitié de sa largeur
const ECART_FONCIER = 5; // m, au moins, entre un repère et la clôture
const axes = axesEcran(VUE_ENSEMBLE.azimut, VUE_ENSEMBLE.elevation);

const PRECISION_PX = 1e-6;
const PRES_DU_PORTAIL = 15; // m : le nom de la route est posé au carrefour du portail

/** Fonction (point [x, y] du plan) → vrai s'il se projette dans la zone libre de la vue
 * d'ensemble, à `retrait` px au moins des cartes et des bords. */
function visibleDans(site, largeur, hauteur, retrait = RETRAIT_PX) {
  const cadrage = cadrer({ points: pointsVueEnsemble(site), ...VUE_ENSEMBLE, largeur, hauteur,
    marges: MARGES_CARTES, rayon: 1000, remplissage: REMPLISSAGE });
  return ([x, y]) => {
    const p = projeter([x, y, 0], cadrage, axes, largeur, hauteur);
    return p.x >= MARGES_CARTES.gauche + retrait && p.y >= MARGES_CARTES.haut + retrait
      && p.x <= largeur - MARGES_CARTES.droite - retrait
      && p.y <= hauteur - MARGES_CARTES.bas - retrait;
  };
}

/** Points des repères : bouts de la flèche du nord et de la barre d'échelle, et leurs noms. */
const POINTS_REPERES = [[NORD.x, NORD.y - NORD.longueur / 2], ANCRE_NORD,
  [ECHELLE.x, ECHELLE.y], [ECHELLE.x + ECHELLE.longueur, ECHELLE.y], ANCRE_ECHELLE];

test("trois implantations dans le jeu de référence, dont l'actuelle et l'optimisée", () => {
  assert.equal(SITES.length, 3);
  assert.ok(SITES.some(([nom]) => nom.startsWith("Actuelle")));
  assert.ok(SITES.some(([nom]) => nom.startsWith("Optimisée")));
});

test("vue d'ensemble : portail et voirie dans le cadre, pour les trois implantations", () => {
  for (const [nom, site] of SITES) {
    for (const [largeur, hauteur] of FENETRES) {
      // Points cadrés eux-mêmes : dans la zone libre, au bord pour les plus éloignés
      const visible = visibleDans(site, largeur, hauteur, -PRECISION_PX);
      for (const point of [site.portail, ...site.voirie]) {
        assert.ok(visible(point), `${nom}, ${largeur} × ${hauteur} : ${point}`);
      }
    }
  }
});

test("nom de la route : sur la route, au carrefour de l'accès au portail", () => {
  // La route longe le bord est du site : dans la vue d'ensemble, elle passe sous les cartes ;
  // son nom, au carrefour, apparaît dès que l'on zoome ou tourne la vue.
  for (const [nom, site] of SITES) {
    const ancre = ancreRoute(site);
    const route = site.route_publique;
    assert.ok(route.slice(1).some((b, i) => distanceAuSegment(ancre, route[i], b) < 1e-6), nom);
    const [dx, dy] = [ancre[0] - site.acces[0][0], ancre[1] - site.acces[0][1]];
    assert.ok(Math.hypot(dx, dy) < PRES_DU_PORTAIL, `${nom} : ${ancre}`);
    const etiquette = etiquettesDuSite(site).find((e) => e.cle === "route");
    assert.deepEqual(etiquette.position.slice(0, 2), ancre);
  }
});

test("nord et échelle : dans la vue d'ensemble des trois implantations, hors du foncier", () => {
  for (const [nom, site] of SITES) {
    for (const [largeur, hauteur] of FENETRES) {
      const visible = visibleDans(site, largeur, hauteur);
      for (const point of POINTS_REPERES) {
        assert.ok(visible(point), `${nom}, ${largeur} × ${hauteur} : ${point}`);
      }
    }
    for (const point of POINTS_REPERES) {
      for (const contour of site.contours) {
        assert.equal(dansPolygone(point, contour.points), false, `${nom} : ${point}`);
        assert.ok(distanceAuBord(point, contour.points) >= ECART_FONCIER, `${nom} : ${point}`);
      }
    }
  }
});
