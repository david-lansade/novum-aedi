// Tests des formes des objets (src/formesVehicules.js, src/formesCharges.js ; « npm test ») :
// chacune tient dans son gabarit, posée au sol, l'avant vers +x, avec la couleur de son type.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Box3, Color, Vector3 } from "three";

import { AGV, CAMION, CHARIOT } from "../src/apparence.js";
import { FORMES_CHARGES } from "../src/formesCharges.js";
import { FORMES_VEHICULES, formeAgv, formeChariot, roueUnite } from "../src/formesVehicules.js";
import { formeObjet } from "../src/objets.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const { gabarits } = reference.scene;
const FORMES = { ...FORMES_VEHICULES, ...FORMES_CHARGES };
const TYPE_DE_FORME = { fourgon: "camion", plateau: "camion", palettes: "lot",
  panneaux: "kit 2D", pod: "pod", module: "module", "kit module": "module" };
const GABARIT_KIT_MODULE = [2.4, 5, 2.5]; // dim_kit_module (scène « satellites »)
const TOLERANCE = 0.02; // m : pieds inclinés des chevalets, moyeux des roues
const ACCENT = "#6250d6";

/** Boîte englobante de la géométrie. */
const boite = (geometrie) => new Box3().setFromBufferAttribute(geometrie.attributes.position);

/** Vérifie que la boîte tient dans [−l/2, l/2] × [−w/2 − debord, w/2 + debord] × [0, h]. */
function tientDans({ min, max }, [largeur, longueur, hauteur], nom, debord = 0) {
  assert.ok(min.x >= -longueur / 2 - TOLERANCE && max.x <= longueur / 2 + TOLERANCE, nom);
  assert.ok(Math.max(-min.y, max.y) <= largeur / 2 + debord + TOLERANCE, nom);
  assert.ok(min.z >= -TOLERANCE && max.z <= hauteur + TOLERANCE, nom);
}

test("formes : toutes celles des objets de la scène existent", () => {
  for (const objet of reference.scene.objets) assert.ok(FORMES[formeObjet(objet, "unique")]);
  assert.ok(FORMES[formeObjet({ id: "MOD-1", type: "module" }, "satellites")]);
});

test("formes : dans leur gabarit, au sol, aux couleurs par sommets dont l'accent", () => {
  const accent = new Color(ACCENT);
  for (const [nom, construire] of Object.entries(FORMES)) {
    const gabarit = nom === "kit module" ? GABARIT_KIT_MODULE : gabarits[TYPE_DE_FORME[nom]];
    const geometrie = construire(gabarit, ACCENT);
    const { position, color } = geometrie.attributes;
    assert.ok(position.count > 0 && color.count === position.count, nom);
    // seuls les rétroviseurs débordent de la largeur d'un camion
    tientDans(boite(geometrie), gabarit, nom, nom in FORMES_VEHICULES ? CAMION.retro.saillie : 0);
    if (!(nom in FORMES_VEHICULES)) {
      assert.ok(Math.abs(boite(geometrie).min.z) <= TOLERANCE, `${nom} posé au sol`);
    }
    let avecAccent = false;
    for (let i = 0; i < color.count && !avecAccent; i++) {
      avecAccent = Math.abs(color.getX(i) - accent.r) < 1e-6
        && Math.abs(color.getY(i) - accent.g) < 1e-6 && Math.abs(color.getZ(i) - accent.b) < 1e-6;
    }
    assert.ok(avecAccent, `${nom} porte la couleur de son type`);
  }
});

test("camions : cabine à l'avant (+x), caisse du fourgon à la hauteur du gabarit", () => {
  const [, longueur, hauteur] = gabarits.camion;
  for (const forme of Object.keys(FORMES_VEHICULES)) {
    const { position } = FORMES[forme](gabarits.camion, ACCENT).attributes;
    const point = new Vector3();
    let [hautAvant, hautArriere] = [0, 0];
    for (let i = 0; i < position.count; i++) {
      point.fromBufferAttribute(position, i);
      const avant = point.x > longueur / 2 - CAMION.cabine.longueur;
      if (avant) hautAvant = Math.max(hautAvant, point.z);
      else hautArriere = Math.max(hautArriere, point.z);
    }
    assert.ok(hautAvant <= CAMION.cabine.hauteur + 0.1, forme);
    if (forme === "fourgon") assert.ok(Math.abs(hautArriere - hauteur) < 1e-6);
    else assert.ok(hautArriere < CAMION.cabine.hauteur, forme); // plateau surbaissé
  }
});

test("roue unité, chariot et AGV : à leurs dimensions", () => {
  const { min, max } = boite(roueUnite()); // centrée, de rayon 1 et de largeur 1 (moyeu en plus)
  assert.ok(Math.abs(min.z + 1) < 1e-6 && Math.abs(max.z - 1) < 1e-6);
  assert.ok(Math.max(-min.x, max.x) <= 1 && Math.max(-min.y, max.y) <= 0.5 + 2 * TOLERANCE);
  tientDans(boite(formeChariot()), [CHARIOT.largeur, CHARIOT.longueur, CHARIOT.mat], "chariot");
  tientDans(boite(formeAgv()), [AGV.largeur, AGV.longueur, AGV.hauteur], "AGV");
});
