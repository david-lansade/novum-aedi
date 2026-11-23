// Tests de src/donnees.js (« npm test ») : le calcul des positions et l'horloge doivent redonner
// exactement ce que calcule avelis_flux/scene_3d.py sur le jeu de référence (tests/reference.json,
// régénéré par « py -3 avelis_flux/scene_3d.py --reference »).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  VERSION_SCENE, etatObjet, horloge, horlogeCourte, positions, preparerScene,
} from "../src/donnees.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(structuredClone(reference.scene));
const ECART_MAX_M = 1e-6; // mêmes données, même calcul : seules les erreurs d'arrondi diffèrent

test("positions identiques à celles de scene_3d.py, limites de segments comprises", () => {
  assert.ok(reference.positions.length > 100);
  for (const { t, visibles } of reference.positions) {
    const obtenues = positions(scene, t);
    assert.deepEqual(Object.keys(obtenues).sort(), Object.keys(visibles).sort(), `t = ${t}`);
    for (const [id, [x, y]] of Object.entries(visibles)) {
      const ecart = Math.hypot(obtenues[id].x - x, obtenues[id].y - y);
      assert.ok(ecart <= ECART_MAX_M, `${id} à t = ${t} : écart ${ecart} m`);
      assert.equal(obtenues[id].type, scene.objets.find((o) => o.id === id).type);
    }
  }
});

test("horloges « Jour N · HH:MM » et « JN HH:MM » identiques à celles de Python", () => {
  for (const [t, attendue, courte] of reference.horloges) {
    assert.equal(horloge(t, scene.temps), attendue, `t = ${t}`);
    assert.equal(horlogeCourte(t, scene.temps), courte, `t = ${t}`);
  }
});

test("cap : sens de la marche en trajet, dernier sens connu à l'arrêt", () => {
  const objet = {
    segments: [
      [0, 1, [[5, 5]]], // repos avant tout trajet : cap par défaut
      [1, 11, [[0, 0], [10, 0], [10, 10]]], // vers l'est, puis vers le nord
      [11, null, [[10, 10]]], // arrêt : garde le sens du dernier tronçon
    ],
  };
  preparerScene({ version: VERSION_SCENE, objets: [objet] });
  assert.deepEqual(etatObjet(objet, 0.5), { x: 5, y: 5, cap: 0 });
  assert.deepEqual(etatObjet(objet, 3.5), { x: 5, y: 0, cap: 0 });
  assert.deepEqual(etatObjet(objet, 8.5), { x: 10, y: 5, cap: Math.PI / 2 });
  assert.deepEqual(etatObjet(objet, 20), { x: 10, y: 10, cap: Math.PI / 2 });
  assert.equal(etatObjet(objet, -1), null);
});

test("objet masqué entre deux segments disjoints", () => {
  const objet = { segments: [[0, 2, [[1, 1]]], [5, 6, [[2, 2]]]] };
  preparerScene({ version: VERSION_SCENE, objets: [objet] });
  assert.equal(etatObjet(objet, 2), null); // fin exclue, comme Usine.segment
  assert.equal(etatObjet(objet, 4.9), null);
  assert.deepEqual(etatObjet(objet, 5), { x: 2, y: 2, cap: 0 });
  assert.equal(etatObjet(objet, 6), null);
});

test("version de scène inconnue refusée avec un message en français", () => {
  assert.throws(() => preparerScene({ version: 99, objets: [] }), /version de scène/);
});

test("horloge tapée à la main : jour et heure, heure seule, jour seul, refus", async () => {
  const { instantSaisi, horloge } = await import("../src/donnees.js");
  const temps = { minutes_jour: 960, heure_ouverture: 6 };
  assert.equal(instantSaisi("Jour 2 · 21:21", temps, 0), 960 + 15 * 60 + 21);
  assert.equal(horloge(instantSaisi("Jour 2 · 21:21", temps, 0), temps), "Jour 2 · 21:21");
  assert.equal(instantSaisi("j3 8h", temps, 0), 2 * 960 + 120);
  assert.equal(instantSaisi("10:30", temps, 960 + 5), 960 + 270);
  assert.equal(instantSaisi("jour 2", temps, 0), 960);
  for (const faux of ["", "demain", "Jour 1 · 23:30", "Jour 0", "12:75"]) {
    assert.equal(instantSaisi(faux, temps, 0), null, faux);
  }
});
