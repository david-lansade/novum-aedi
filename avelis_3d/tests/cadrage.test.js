// Tests de src/cadrage.js (« npm test ») : cadrage de la caméra orthographique sur le site du jeu
// de référence, axes de l'écran, orientation, écart angulaire.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  MARGES_CARTES, axesEcran, cadrer, centreDesBatiments, ecartAngulaire, orientation,
  pointsDesBatiments, pointsDuSite, pointsVueEnsemble, projeter,
} from "../src/cadrage.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const site = reference.scene.site;
const DEGRE = Math.PI / 180;
const MARGES = MARGES_CARTES; // celles de Camera.jsx
const FENETRES = [[1600, 900], [1280, 650]]; // tailles d'écran contrôlées
const VUES = [45, 135, 225, 315].map((a) => [a * DEGRE, 35 * DEGRE])
  .concat([[-90 * DEGRE, 89.8 * DEGRE]]); // quatre vues isométriques et la vue de dessus
const REMPLISSAGE = 0.94;
const RAYON = 900;
const PRECISION = 1e-6;

/** Boîte {g, d, h, b} (px) des points projetés par le cadrage. */
function boiteProjetee(points, cadrage, axes, largeur, hauteur) {
  const ecran = points.map((p) => projeter(p, cadrage, axes, largeur, hauteur));
  const xs = ecran.map((p) => p.x);
  const ys = ecran.map((p) => p.y);
  return { g: Math.min(...xs), d: Math.max(...xs), h: Math.min(...ys), b: Math.max(...ys) };
}

test("cadrage : les points tiennent dans la zone libre, centrés, et la remplissent", () => {
  for (const points of [pointsVueEnsemble(site), pointsDuSite(site)]) {
    for (const [largeur, hauteur] of FENETRES) {
      for (const [azimut, elevation] of VUES) {
        const cadrage = cadrer({ points, azimut, elevation, largeur, hauteur, marges: MARGES,
          rayon: RAYON, remplissage: REMPLISSAGE });
        const boite = boiteProjetee(points, cadrage, axesEcran(azimut, elevation), largeur,
          hauteur);
        const libre = { g: MARGES.gauche, d: largeur - MARGES.droite, h: MARGES.haut,
          b: hauteur - MARGES.bas };
        const cas = `${largeur} × ${hauteur}, azimut ${Math.round(azimut / DEGRE)}°`;
        assert.ok(boite.g >= libre.g - PRECISION && boite.d <= libre.d + PRECISION, cas);
        assert.ok(boite.h >= libre.h - PRECISION && boite.b <= libre.b + PRECISION, cas);
        const parts = [(boite.d - boite.g) / (libre.d - libre.g),
          (boite.b - boite.h) / (libre.b - libre.h)];
        assert.ok(Math.abs(Math.max(...parts) - REMPLISSAGE) < PRECISION, `${cas} : ${parts}`);
        assert.ok(Math.abs((boite.g + boite.d) / 2 - (libre.g + libre.d) / 2) < PRECISION, cas);
        assert.ok(Math.abs((boite.h + boite.b) / 2 - (libre.h + libre.b) / 2) < PRECISION, cas);
      }
    }
  }
});

test("cadrage : caméra à l'azimut, à l'élévation et à la distance demandés, cible au sol", () => {
  for (const [azimut, elevation] of VUES) {
    const { cible, position } = cadrer({ points: pointsDuSite(site), azimut, elevation,
      largeur: 1600, hauteur: 900, marges: MARGES, rayon: RAYON, remplissage: REMPLISSAGE });
    assert.ok(Math.abs(cible[2]) < PRECISION);
    const obtenue = orientation(position, cible);
    assert.ok(Math.abs(ecartAngulaire(obtenue.azimut, azimut)) < PRECISION);
    assert.ok(Math.abs(obtenue.elevation - elevation) < PRECISION);
    assert.ok(Math.abs(obtenue.rayon - RAYON) < PRECISION);
  }
});

test("axes de l'écran orthonormés, perpendiculaires à la visée ; nord en haut, de dessus", () => {
  const scalaire = (a, b) => a.reduce((somme, c, k) => somme + c * b[k], 0);
  for (const [azimut, elevation] of VUES) {
    const { direction, droite, haut } = axesEcran(azimut, elevation);
    for (const [a, b, attendu] of [[droite, droite, 1], [haut, haut, 1], [direction, direction, 1],
      [droite, haut, 0], [droite, direction, 0], [haut, direction, 0]]) {
      assert.ok(Math.abs(scalaire(a, b) - attendu) < PRECISION);
    }
    assert.ok(haut[2] > 0, "le haut de l'écran monte"); // la caméra n'est pas renversée
  }
  const dessus = axesEcran(-90 * DEGRE, 89.8 * DEGRE);
  assert.ok(dessus.haut[1] > 0.99 && dessus.droite[0] > 0.99, "nord en haut, est à droite");
  // Caméra au sud-ouest : le nord-est est en haut, le sud-est à droite
  const iso = axesEcran(225 * DEGRE, 35 * DEGRE);
  assert.ok(iso.haut[0] > 0 && iso.haut[1] > 0 && iso.droite[0] > 0 && iso.droite[1] < 0);
});

test("écart angulaire : plus court chemin, entre −π et π", () => {
  for (const [de, vers, attendu] of [[0, 90, 90], [350, 10, 20], [10, 350, -20], [225, -135, 0],
    [0, 180, 180], [45, 315, -90]]) {
    assert.ok(Math.abs(ecartAngulaire(de * DEGRE, vers * DEGRE) - attendu * DEGRE) < PRECISION,
      `${de} → ${vers}`);
  }
});

test("points cadrés : bâtiments et chemin des camions, ou site entier", () => {
  const batiments = site.zones.filter((zone) => zone.hauteur > 0);
  assert.equal(pointsDesBatiments(site).length, batiments.length * 8);
  const chemin = [...site.voirie, ...site.bretelles.flat(), ...site.acces, site.portail]
    .map(([x, y]) => [x, y, 0]);
  assert.deepEqual(pointsVueEnsemble(site), [...pointsDesBatiments(site), ...chemin]);
  const xs = batiments.flatMap((z) => [z.x, z.x + z.largeur]);
  assert.equal(centreDesBatiments(site)[0], (Math.min(...xs) + Math.max(...xs)) / 2);
  const sommets = site.contours.reduce((somme, contour) => somme + contour.points.length, 0);
  assert.equal(pointsDuSite(site).length, sommets + site.zones.length * 8);
  const sansBatiment = { ...site, zones: site.zones.map((zone) => ({ ...zone, hauteur: 0 })) };
  assert.deepEqual(pointsDesBatiments(sansBatiment), pointsDuSite(sansBatiment));
});
