// Tests de src/objets.js (« npm test ») : forme de chaque objet, roues des camions, modules
// chargés sur les camions d'expédition et leur place sur le plateau.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { CAMION, CHARIOT, CHARIOT_PORTEUR } from "../src/apparence.js";
import { preparerScene } from "../src/donnees.js";
import {
  chargementsDesCamions, enTransport, formeObjet, placesDeCharge, plateauLibre, poseDuPorteur,
  rouesDe, transportsSimultanes,
} from "../src/objets.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const { objets, gabarits } = reference.scene;
const EPS = 1e-9;

test("formes : le type se lit à la forme, le camion selon son rôle, le module selon le schéma",
  () => {
    const forme = (id, type, schema = "unique") => formeObjet({ id, type }, schema);
    assert.equal(forme("CAM-0012", "camion"), "fourgon");
    assert.equal(forme("EXP-0016", "camion"), "plateau");
    assert.equal(forme("LOT-0012", "lot"), "palettes");
    assert.equal(forme("K2D-29-00001", "kit 2D"), "panneaux");
    assert.equal(forme("POD-29-00001", "pod"), "pod");
    assert.equal(forme("MOD-29-00001", "module"), "module");
    assert.equal(forme("MOD-29-00001", "module", "satellites"), "kit module");
    const camions = objets.filter((o) => o.type === "camion");
    assert.ok(camions.some((o) => formeObjet(o) === "plateau"));
    assert.ok(camions.some((o) => formeObjet(o) === "fourgon"));
  });

test("roues : dans l'emprise du camion, symétriques, au sol ; jumelées sauf à l'avant", () => {
  const [largeur, longueur] = gabarits.camion;
  for (const forme of ["fourgon", "plateau"]) {
    const roues = rouesDe(forme, gabarits.camion);
    assert.equal(roues.length, 2 * (2 + CAMION.essieux.remorque.length), forme);
    for (const r of roues) {
      assert.ok(Math.abs(r.x) + r.rayon <= longueur / 2 + EPS, forme);
      assert.ok(Math.abs(r.y) + r.largeur / 2 <= largeur / 2 + EPS, forme);
      assert.ok(roues.some((o) => o.x === r.x && o.y === -r.y), forme);
    }
    const avant = Math.max(...roues.map((r) => r.x));
    for (const r of roues) {
      assert.equal(r.largeur, CAMION.roue.largeur * (r.x === avant ? 1 : 2), forme);
    }
    // les roues de la remorque passent sous la caisse ou sous le plateau
    const dessous = forme === "plateau" ? CAMION.plateau.bas : CAMION.caisse.bas;
    for (const r of roues.filter((o) => o.x < 0)) assert.ok(2 * r.rayon <= dessous, forme);
  }
  const petites = rouesDe("plateau", gabarits.camion).filter((r) => r.x < 0);
  assert.ok(petites.every((r) => r.rayon === CAMION.roue.petite));
});

test("chargements : les modules dont la présence finit au départ du quai d'un plateau", () => {
  const chargements = chargementsDesCamions(objets);
  assert.ok(chargements.size > 0);
  const charges = [...chargements.values()].flatMap((c) => c.modules);
  assert.equal(new Set(charges).size, charges.length); // un module sur un seul camion
  for (const [id, { depart, modules }] of chargements) {
    const camion = objets.find((o) => o.id === id);
    assert.equal(formeObjet(camion), "plateau");
    const i = camion.segments.findIndex(([, fin, chemin]) => fin === depart
      && chemin.length === 1);
    assert.ok(i >= 0 && camion.segments[i + 1][2].length > 1, id); // arrêt, puis départ
    for (const m of modules) {
      assert.equal(objets.find((o) => o.id === m).segments.at(-1)[1], depart, m);
    }
  }
});

test("chargements : rien sans départ du quai, ni pour un module encore présent à la fin", () => {
  const trajet = (t0, t1) => [t0, t1, [[0, 0], [10, 0]]];
  const camion = (id, segments) => ({ id, type: "camion", segments });
  const module = (id, fin) => ({ id, type: "module", segments: [[0, fin, [[5, 5]]]] });
  const scene = [
    camion("EXP-0001", [trajet(0, 10), [10, 20, [[10, 0]]], trajet(20, 30)]),
    camion("EXP-0002", [trajet(0, 10), [10, null, [[20, 0]]]]), // reste à quai
    camion("CAM-0003", [trajet(0, 10), [10, 25, [[30, 0]]], trajet(25, 35)]), // fournisseur
    module("MOD-1", 20), module("MOD-2", 21), module("MOD-3", null), module("MOD-4", 25),
  ];
  const chargements = chargementsDesCamions(scene);
  assert.deepEqual([...chargements], [["EXP-0001", { depart: 20, modules: ["MOD-1"] }]]);
});

test("places de charge : sur la partie libre du plateau, en rang puis en couches", () => {
  const longueur = gabarits.camion[1];
  const [debut, fin] = plateauLibre(longueur);
  assert.ok(debut > -longueur / 2 && fin < longueur / 2 - CAMION.cabine.longueur);
  const [une] = placesDeCharge(1, gabarits.module, longueur);
  assert.ok(Math.abs(une.x - (debut + fin) / 2) < EPS);
  assert.equal(une.z, CAMION.plateau.haut);
  assert.ok(gabarits.module[1] <= fin - debut); // un module 3D tient sur le plateau
  const kit = [2.4, 5, 2.5];
  const trois = placesDeCharge(3, kit, longueur);
  assert.deepEqual(trois.map((p) => p.z), [CAMION.plateau.haut, CAMION.plateau.haut,
    CAMION.plateau.haut + kit[2]]);
  for (const { x } of trois) {
    assert.ok(x - kit[1] / 2 >= debut - EPS && x + kit[1] / 2 <= fin + EPS);
  }
  assert.ok(trois[0].x + kit[1] / 2 <= trois[1].x - kit[1] / 2 + EPS); // côte à côte
});

test("chariots porteurs : chaque marchandise en route, jamais un camion", () => {
  const { objets: prepares } = preparerScene(reference.scene);
  const marchandise = prepares.find((o) => CHARIOT_PORTEUR.types.includes(o.type)
    && o.segments.some(([, , chemin]) => chemin.length > 1));
  const [t0, t1] = marchandise.segments.find(([, , chemin]) => chemin.length > 1);
  assert.equal(enTransport(marchandise, (t0 + t1) / 2), true);
  assert.equal(enTransport(marchandise, t1), t1 === null);
  const camion = prepares.find((o) => o.type === "camion");
  const [c0, c1] = camion.segments.find(([, , chemin]) => chemin.length > 1);
  assert.equal(enTransport(camion, (c0 + c1) / 2), false);
  // Nombre de chariots : le plus grand nombre de trajets de marchandises qui se recouvrent
  const trajet = (t, u) => ({ type: "lot", segments: [[t, u, [[0, 0], [1, 0]]]] });
  assert.equal(transportsSimultanes([trajet(0, 2), trajet(1, 3), trajet(2, 4)]), 2);
  assert.equal(transportsSimultanes([trajet(0, 1), trajet(1, 2)]), 1); // fin exclue
  assert.equal(transportsSimultanes([{ type: "camion", segments: [[0, 1, [[0, 0], [1, 0]]]] }]),
    0);
  assert.ok(transportsSimultanes(prepares) >= 1);
});

test("chariot porteur : derrière la charge, ses fourches sous son arrière", () => {
  const pose = poseDuPorteur({ x: 10, y: 5, cap: Math.PI / 2 }, 6);
  const recul = 3 + CHARIOT.longueur / 2 - CHARIOT.fourches;
  assert.ok(Math.abs(pose.x - 10) < EPS && Math.abs(pose.y - (5 - recul)) < EPS);
  assert.equal(pose.cap, Math.PI / 2);
  // le bout des fourches est sous la charge, le mât derrière elle
  const bout = pose.y + CHARIOT.longueur / 2;
  assert.ok(bout > 5 - 3 && bout - CHARIOT.fourches <= 5 - 3 + EPS);
});
