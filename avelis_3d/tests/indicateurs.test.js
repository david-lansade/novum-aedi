// Tests de src/indicateurs.js (« npm test ») : cartes d'indicateurs tirées du tableau de
// pilotage, recherche d'un objet, instant où le montrer, repères du curseur de temps ; réglage
// fin du curseur maintenu appuyé (src/curseurTemps.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { CURSEUR_FIN } from "../src/apparence.js";
import { immobile, instantAuPointeur, instantFin } from "../src/curseurTemps.js";
import { etatObjet, preparerScene } from "../src/donnees.js";
import {
  HEURE_MIN, cartesIndicateurs, formater, instantVisible, rechercherObjets, reperesTemps, signe,
} from "../src/indicateurs.js";
import { valeursPilotage } from "../src/pilotage.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(structuredClone(reference.scene));

test("nombres et écarts à la française", () => {
  assert.equal(formater(1500), "1 500");
  assert.equal(formater(3.5555), "3,6");
  assert.equal(formater(null), "—");
  assert.equal(signe(2), "+2");
  assert.equal(signe(-0.6), "−0,6");
  assert.equal(signe(0), "0");
  assert.equal(signe(-0.01), "0"); // arrondi à zéro : pas de « −0 »
});

test("cartes : valeurs du tableau de pilotage, variation sur la dernière heure", () => {
  for (const t of [0, 30, 455.5, 899.99, 900, 1340.37]) {
    const v = valeursPilotage(scene, t);
    const avant = valeursPilotage(scene, Math.max(0, t - HEURE_MIN));
    const cartes = Object.fromEntries(cartesIndicateurs(scene, t).map((c) => [c.cle, c]));
    assert.deepEqual(Object.keys(cartes), ["termines", "expedies", "en_cours", "stock_pf",
      "camions"]);
    assert.equal(cartes.termines.valeur, formater(v.termines_jour));
    assert.equal(cartes.en_cours.valeur, formater(v.en_cours));
    assert.equal(cartes.stock_pf.valeur, formater(v.stock_pf));
    assert.equal(cartes.camions.valeur, formater(v.camions_sur_site));
    assert.equal(cartes.expedies.detail, `${formater(v.expedies)} au total`);
    assert.equal(cartes.en_cours.variation.texte, `${signe(v.en_cours - avant.en_cours)} en 1 h`);
    const enAvance = v.termines_jour >= v.objectif_heure;
    assert.equal(cartes.termines.variation.ton, enAvance ? "bon" : "alerte", `t = ${t}`);
  }
});

test("cartes : une hausse des expéditions est bonne, celle d'un stock reste neutre", () => {
  const p = scene.pilotage;
  const t = p.expeditions.find((x) => x > HEURE_MIN) + 1e-6;
  const cartes = Object.fromEntries(cartesIndicateurs(scene, t).map((c) => [c.cle, c]));
  assert.equal(cartes.expedies.variation.ton, "bon");
  assert.ok(["neutre", "stable"].includes(cartes.stock_pf.variation.ton));
  assert.ok(["neutre", "stable"].includes(cartes.en_cours.variation.ton));
});

test("recherche : début d'identifiant, puis identifiant qui le contient, puis libellé", () => {
  const camion = scene.objets.find((o) => o.type === "camion");
  assert.equal(rechercherObjets(scene, camion.id.toLowerCase())[0], camion);
  const trouves = rechercherObjets(scene, "  cam-  ");
  assert.ok(trouves.length > 0 && trouves.length <= 8);
  assert.ok(trouves.every((o) => o.id.startsWith("CAM-")));
  const parLibelle = rechercherObjets(scene, "fournisseur", 50);
  assert.ok(parLibelle.length > 0 && parLibelle.every((o) => o.libelle.includes("Fournisseur")));
  assert.deepEqual(rechercherObjets(scene, ""), []);
  assert.deepEqual(rechercherObjets(scene, "introuvable"), []);
});

test("instant visible : t s'il y est, sinon son prochain segment, sinon son dernier", () => {
  const objet = scene.objets.find((o) => o.segments.length > 1 && o.segments[0][0] > 0);
  const [debut] = objet.segments[0];
  assert.equal(instantVisible(objet, debut - 1), debut);
  assert.equal(instantVisible(objet, debut), debut);
  const parti = scene.objets.find((o) => o.segments.at(-1)[1] !== null
    && o.segments.at(-1)[1] < scene.temps.duree);
  const t = scene.temps.duree;
  assert.equal(etatObjet(parti, t), null);
  assert.equal(instantVisible(parti, t), parti.segments.at(-1)[0]);
  assert.notEqual(etatObjet(parti, instantVisible(parti, t)), null);
});

test("repères du temps : un début de jour par jour simulé, alertes entre 0 et 1", () => {
  const { jours, alertes } = reperesTemps(scene);
  assert.deepEqual(jours.map((j) => j.numero), [1, 2]);
  assert.deepEqual(jours.map((j) => j.part), [0, 0.5]);
  assert.equal(alertes.length, scene.tracabilite.alertes.length);
  assert.ok(alertes.every((part) => part >= 0 && part <= 1));
});

test("curseur de temps : instant sous le pointeur, réglage fin à la minute au maintien", () => {
  const { pouce, minutesParPixel, tolerance } = CURSEUR_FIN;
  const [largeur, duree] = [pouce + 800, 4800];
  assert.equal(instantAuPointeur(pouce / 2, largeur, duree), 0);
  assert.equal(instantAuPointeur(largeur - pouce / 2, largeur, duree), duree);
  assert.equal(instantAuPointeur(pouce / 2 + 400, largeur, duree), 2400);
  assert.equal(instantAuPointeur(-50, largeur, duree), 0);
  // un pixel vaut 6 min sur le curseur, minutesParPixel min en réglage fin, arrondi à la minute
  assert.ok(duree / 800 > 4 * minutesParPixel);
  assert.equal(instantFin(1000, 1 / minutesParPixel, duree), 1001);
  assert.equal(instantFin(1000, -10 / minutesParPixel, duree), 990);
  assert.ok(Number.isInteger(instantFin(1000, 3, duree)));
  assert.equal(instantFin(duree - 1, 1000, duree), duree);
  assert.equal(immobile(100, 100 + tolerance), true);
  assert.equal(immobile(100, 101 + tolerance), false);
});
