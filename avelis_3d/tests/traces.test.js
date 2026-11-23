// Tests de src/traces.js (« npm test ») : tronçons et tirets des tracés au sol.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  dansPolygone, distanceAuBord, distanceAuSegment, fermer, pointLePlusProche, rectangle,
  sensDuPolygone, tirets, troncons,
} from "../src/traces.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const PRECISION = 1e-9;

/** Longueur d'une polyligne. */
function longueur(points) {
  return points.slice(1).reduce((somme, [x, y], i) => somme
    + Math.hypot(x - points[i][0], y - points[i][1]), 0);
}

/** Vrai si la bande est entièrement posée sur un tronçon de la polyligne, dans son sens. */
function surLaPolyligne(bande, points) {
  const [ux, uy] = [Math.cos(bande.angle), Math.sin(bande.angle)];
  const bouts = [-1, 1].map((s) => [bande.x + (s * bande.longueur * ux) / 2,
    bande.y + (s * bande.longueur * uy) / 2]);
  return points.slice(1).some(([bx, by], i) => {
    const [ax, ay] = points[i];
    const troncon = Math.hypot(bx - ax, by - ay);
    const memeSens = Math.abs(Math.atan2(by - ay, bx - ax) - bande.angle) < PRECISION;
    return memeSens && bouts.every(([px, py]) => Math.abs(Math.hypot(px - ax, py - ay)
      + Math.hypot(bx - px, by - py) - troncon) < 1e-6);
  });
}

test("tronçons : un par segment non nul, longueurs, milieux et angles", () => {
  const points = [[0, 0], [10, 0], [10, 0], [10, 5]];
  const bandes = troncons(points);
  assert.equal(bandes.length, 2); // le segment nul est ignoré
  assert.deepEqual(bandes[0], { x: 5, y: 0, longueur: 10, angle: 0 });
  assert.deepEqual(bandes[1], { x: 10, y: 2.5, longueur: 5, angle: Math.PI / 2 });
  const voirie = reference.scene.site.voirie;
  const somme = troncons(voirie).reduce((total, bande) => total + bande.longueur, 0);
  assert.ok(Math.abs(somme - longueur(voirie)) < 1e-6);
});

test("tirets : motif trait + vide le long d'une droite", () => {
  const bandes = tirets([[0, 0], [20, 0]], 3, 2);
  assert.deepEqual(bandes.map((b) => [b.x, b.longueur]), [[1.5, 3], [6.5, 3], [11.5, 3],
    [16.5, 3]]);
});

test("tirets : le motif continue après un sommet, un tiret à cheval est coupé en deux", () => {
  const bandes = tirets([[0, 0], [2, 0], [2, 10]], 3, 2);
  assert.deepEqual(bandes.slice(0, 2).map((b) => [b.x, b.y, b.longueur]), [[1, 0, 2],
    [2, 0.5, 1]]); // 2 m avant le sommet, 1 m après
  // Tiret suivant : de 5 à 8 m le long de la polyligne, soit de 3 à 6 m après le sommet
  assert.ok(Math.abs(bandes[2].y - 4.5) < PRECISION);
  assert.equal(bandes[2].longueur, 3);
});

test("tirets : longueur totale et position sur les routes du jeu de référence", () => {
  const site = reference.scene.site;
  for (const points of [site.voirie, site.route_publique]) {
    for (const [trait, vide] of [[3, 3], [4, 3], [0.5, 1.7]]) {
      const bandes = tirets(points, trait, vide);
      const total = longueur(points);
      const attendu = Math.floor(total / (trait + vide)) * trait
        + Math.min(trait, total % (trait + vide));
      const obtenu = bandes.reduce((somme, bande) => somme + bande.longueur, 0);
      assert.ok(Math.abs(obtenu - attendu) < 1e-6, `${obtenu} ≠ ${attendu}`);
      assert.ok(bandes.every((bande) => bande.longueur <= trait + PRECISION));
      assert.ok(bandes.every((bande) => surLaPolyligne(bande, points)));
    }
  }
});

test("rectangle et contour fermés", () => {
  assert.deepEqual(rectangle(1, 2, 3, 4), [[1, 2], [4, 2], [4, 6], [1, 6], [1, 2]]);
  assert.deepEqual(fermer([[0, 0], [1, 0], [1, 1]]), [[0, 0], [1, 0], [1, 1], [0, 0]]);
  const bandes = troncons(rectangle(0, 0, 4, 2));
  assert.equal(bandes.reduce((somme, bande) => somme + bande.longueur, 0), 12);
});

test("distances : segment, polyligne, polygone et sens de parcours", () => {
  assert.equal(distanceAuSegment([5, 3], [0, 0], [10, 0]), 3);
  assert.equal(distanceAuSegment([13, 4], [0, 0], [10, 0]), 5); // au-delà du bout
  assert.equal(distanceAuSegment([3, 4], [0, 0], [0, 0]), 5); // segment réduit à un point
  assert.deepEqual(pointLePlusProche([[0, 0], [10, 0], [10, 10]], [12, 6]), [10, 6]);
  const carre = [[0, 0], [10, 0], [10, 10], [0, 10]];
  assert.equal(dansPolygone([5, 5], carre), true);
  assert.equal(dansPolygone([15, 5], carre), false);
  assert.equal(distanceAuBord([5, 2], carre), 2);
  assert.equal(distanceAuBord([-3, 5], carre), 3);
  assert.equal(sensDuPolygone(carre), 1);
  assert.equal(sensDuPolygone([...carre].reverse()), -1);
});
