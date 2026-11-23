// Tests de src/pilotage.js (« npm test ») : tableau de pilotage, alertes et événements affichés
// doivent redonner exactement ce que calcule avelis_flux/scene_3d.py (pilotage_scene,
// alertes_affichees_scene, evenements_affiches) sur le jeu de référence (tests/reference.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { preparerScene } from "../src/donnees.js";
import {
  NB_ALERTES_AFFICHEES, alertesAffichees, evenementsAffiches, valeursPilotage,
} from "../src/pilotage.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(structuredClone(reference.scene));
const ECART_OBJECTIF = 1e-9; // seul nombre non entier : objectif au prorata de l'heure

test("tableau de pilotage identique à pilotage_scene, changements de jour compris", () => {
  assert.ok(reference.pilotage.length > 100);
  for (const { t, valeurs } of reference.pilotage) {
    const { objectif_heure: objectif, ...obtenues } = valeursPilotage(scene, t);
    const { objectif_heure: attendu, ...attendues } = valeurs;
    assert.ok(Math.abs(objectif - attendu) <= ECART_OBJECTIF, `objectif à t = ${t}`);
    assert.deepEqual(obtenues, attendues, `t = ${t}`);
  }
});

test("alertes affichées : les dernières déjà lues, la plus récente d'abord", () => {
  const alertes = scene.tracabilite.alertes;
  assert.ok(reference.pilotage.some(({ alertes: a }) => a.length > 0));
  for (const { t, alertes: indices } of reference.pilotage) {
    const obtenues = alertesAffichees(scene, t).map((alerte) => alertes.indexOf(alerte));
    assert.deepEqual(obtenues, indices, `t = ${t}`);
    assert.ok(obtenues.length <= NB_ALERTES_AFFICHEES);
  }
});

test("événements affichés de quelques objets identiques à scene_3d.evenements_affiches", () => {
  const objets = new Map(scene.objets.map((objet) => [objet.id, objet]));
  for (const { t, evenements } of reference.pilotage) {
    for (const [id, nombre] of Object.entries(evenements)) {
      assert.equal(evenementsAffiches(objets.get(id), t).length, nombre, `${id} à t = ${t}`);
    }
  }
});

test("un événement non lu n'est jamais affiché ; un lu l'est dès son délai écoulé", () => {
  const objet = { evenements: [[1, "Kitting", "Kitting", 1.5, ""], [2, "Poste 1", "Ligne", null,
    ""], [3, "Contrôle", "Ligne", 3.2, ""]] };
  assert.deepEqual(evenementsAffiches(objet, 1.4), []);
  assert.deepEqual(evenementsAffiches(objet, 1.5).map((e) => e[1]), ["Kitting"]);
  assert.deepEqual(evenementsAffiches(objet, 99).map((e) => e[1]), ["Kitting", "Contrôle"]);
});
