// Tests de la logistique de la vue 3D (« npm test ») : circulation du décor au temps simulé
// (circulation.js), portes de marchandises et trajets par les portes (batiments.js), chariots
// élévateurs garés qui viennent porter les marchandises (chariots.js, logistique.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  CHARIOT_PORTEUR, CIRCULATION_VL, FLOTTE, GRAINE_DECOR, GRANDE_PORTE, MODELES_VL, VOITURE,
} from "../src/apparence.js";
import { passagesDuChemin } from "../src/batiments.js";
import { passageEntre, poseDuChariot } from "../src/chariots.js";
import {
  circulationDuJour, creerCirculation, instantDeLHeure, poseDuSejour, vehiculesA,
} from "../src/circulation.js";
import { placesDuParkingVl } from "../src/decor.js";
import { preparerScene } from "../src/donnees.js";
import { creerLogistique } from "../src/logistique.js";
import { cheminAffiche, creerTrajectoires } from "../src/trajectoires.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(reference.scene);
const { site, temps } = scene;
const contexte = creerTrajectoires(site, scene.gabarits);
const logistique = creerLogistique(scene, contexte);
const MURS_LONG = { sud: 0, nord: 0, ouest: 1, est: 1 };

/** Voitures garées (arrivées, pas encore reparties) à l'heure h du jour 1. */
function garees(circulation, h) {
  const t = instantDeLHeure(temps, 1, h);
  return circulationDuJour(circulation, 1).sejours.filter((s) => t >= s.arrivee
    && t < s.depart && poseDuSejour(s, t)).length;
}

/** Longueur d'une polyligne. */
function longueur(chemin) {
  let l = 0;
  for (let j = 1; j < chemin.length; j++) {
    l += Math.hypot(chemin[j][0] - chemin[j - 1][0], chemin[j][1] - chemin[j - 1][1]);
  }
  return l;
}

test("parking VL : se remplit peu à peu le matin, se vide le soir, des allées et venues", () => {
  const circulation = creerCirculation(site, temps, GRAINE_DECOR);
  const suite = [6, 7, 8, 10, 12, 15, 18, 20, 21].map((h) => garees(circulation, h));
  const [h6, h7, h8, h10, , , h18, h20, h21] = suite;
  assert.ok(h6 < h7 && h7 < h8 && h8 < h10, suite.join(", "));
  assert.ok(h18 > h20 && h20 > h21, suite.join(", "));
  assert.ok(Math.max(...suite) <= circulation.places.length);
  // en journée, des voitures arrivent et partent (pause de midi, visiteurs)
  const { sejours } = circulationDuJour(circulation, 1);
  const [a, b] = [instantDeLHeure(temps, 1, 11), instantDeLHeure(temps, 1, 16)];
  assert.ok(sejours.some((s) => s.arrivee > a && s.arrivee < b));
  assert.ok(sejours.some((s) => s.depart > a && s.depart < b));
  // reproductible, plusieurs modèles, de couleurs connues
  assert.equal(garees(creerCirculation(site, temps, GRAINE_DECOR), 10), h10);
  assert.ok(new Set(sejours.map((s) => s.modele)).size >= 3);
  assert.ok(sejours.every((s) => s.modele in MODELES_VL && s.teinte >= 0
    && s.teinte < VOITURE.couleurs.length));
  // deux voitures ne sont jamais garées à la même place en même temps
  for (const [i, s] of sejours.entries()) {
    for (const r of sejours.slice(i + 1).filter((v) => v.place === s.place)) {
      assert.ok(r.arrivee >= s.depart || s.arrivee >= r.depart, `${s.id} et ${r.id}`);
    }
  }
});

test("véhicules : vitesse au temps simulé, garés sur leur place, camions sur la route", () => {
  const circulation = creerCirculation(site, temps, GRAINE_DECOR);
  const places = placesDuParkingVl(site.parking_vl).places;
  const { sejours, passages } = circulationDuJour(circulation, 1);
  const s = sejours.find((v) => Number.isFinite(v.arrivee));
  // en 0,1 min simulée, la voiture fait CIRCULATION_VL.vitesse × 6 m
  const t = s.arrivee + 0.05;
  const [p, q] = [poseDuSejour(s, t), poseDuSejour(s, t + 0.1)];
  assert.ok(Math.hypot(q.x - p.x, q.y - p.y) <= CIRCULATION_VL.vitesse * 6 + 1e-6);
  assert.ok(Math.hypot(q.x - p.x, q.y - p.y) > CIRCULATION_VL.vitesse * 6 * 0.7);
  const garee = poseDuSejour(s, s.depart - 0.01);
  assert.ok(Math.hypot(garee.x - places[s.place].x, garee.y - places[s.place].y) < 1e-6);
  assert.equal(poseDuSejour(s, s.arrivee - 0.01), null);
  const camions = passages.filter((v) => v.modele === "camion");
  assert.ok(camions.length > 0 && camions.every((v) => v.libelle === "Camion"));
  const visibles = vehiculesA(circulation, instantDeLHeure(temps, 1, 10));
  assert.ok(visibles.some(({ vehicule }) => vehicule.id.startsWith("ROUTE-")));
});

test("portes de marchandises : les grandes portes, puis une porte par mur franchi", () => {
  const { portes } = logistique;
  assert.ok(portes.some((p) => !p.nouvelle) && portes.some((p) => p.nouvelle));
  assert.deepEqual(portes.map((p) => p.id), portes.map((_, i) => i));
  const couverts = site.zones.filter((z) => z.hauteur > 0);
  for (const p of portes) {
    const z = couverts.find((c) => c.nom === p.zone);
    const long = MURS_LONG[p.mur];
    const [bas, haut] = long === 0 ? [z.x, z.x + z.largeur] : [z.y, z.y + z.profondeur];
    assert.ok(p.point[long] - GRANDE_PORTE.largeur / 2 >= bas - 1e-6, `porte ${p.id}`);
    assert.ok(p.point[long] + GRANDE_PORTE.largeur / 2 <= haut + 1e-6, `porte ${p.id}`);
  }
});

test("trajets affichés : les marchandises franchissent les murs par une porte", () => {
  const couverts = site.zones.filter((z) => z.hauteur > 0);
  let [total, parUnePorte] = [0, 0];
  for (const objet of scene.objets.filter((o) => CHARIOT_PORTEUR.types.includes(o.type))) {
    objet.segments.forEach(([, , chemin], i) => {
      if (chemin.length < 2) return;
      for (const p of passagesDuChemin(cheminAffiche(objet, i, contexte), couverts)) {
        const long = MURS_LONG[p.mur];
        total += 1;
        if (logistique.portes.some((porte) => porte.zone === p.zone && porte.mur === p.mur
          && Math.abs(porte.point[long] - p.point[long]) <= GRANDE_PORTE.largeur / 2 + 1e-6)) {
          parUnePorte += 1;
        }
      }
    });
  }
  assert.ok(total > 0);
  assert.equal(parUnePorte, total, `${parUnePorte} sur ${total}`);
});

test("chariots : garés, ils viennent à la marchandise avant son départ, sans saut", () => {
  const { chariots } = logistique;
  assert.ok(chariots.length > 1);
  for (const c of chariots) {
    assert.equal(c.type, "chariot");
    c.segments.slice(1).forEach(([t0, , chemin], k) => {
      const [, t1, avant] = c.segments[k];
      assert.ok(Math.abs(t1 - t0) < 1e-9, `${c.id} : trou au segment ${k + 1}`);
      const [a, b] = [avant.at(-1), chemin[0]];
      assert.ok(Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6, `${c.id} : saut, segment ${k + 1}`);
    });
    c.segments.forEach(([t0, t1, chemin], k) => {
      if (c.charges[k] || chemin.length < 2) return;
      assert.ok(longueur(chemin) / (t1 - t0) <= FLOTTE.vitesse * 60 + 1e-6, `${c.id} : vite`);
    });
    // à la prise : juste avant le départ de la charge, le chariot est déjà sous elle
    c.charges.forEach((charge, k) => {
      if (!charge || c.charges[k - 1] === charge) return;
      const t0 = c.segments[k][0];
      const [p, q] = [poseDuChariot(c, t0 - FLOTTE.attente / 2, contexte, scene.gabarits),
        poseDuChariot(c, t0 + 1e-4, contexte, scene.gabarits)];
      assert.ok(p && q && Math.hypot(p.x - q.x, p.y - q.y) < 0.5, `${c.id} : ${charge.id}`);
    });
    assert.ok(c.evenements.some((e) => e[1] === "Quitte le garage"));
    assert.equal(c.segments.at(-1)[1], null, "garé à la fin");
  }
});

test("passages : instants triés pour chaque porte, trouvés dans leur intervalle", () => {
  const { passages, portes } = logistique;
  assert.equal(passages.size, portes.length);
  assert.ok([...passages.values()].flat().length > 0);
  for (const liste of passages.values()) {
    assert.deepEqual(liste, [...liste].sort((a, b) => a - b));
  }
  const [premier] = [...passages.values()].find((l) => l.length);
  assert.equal(passageEntre([premier], premier - 0.1, premier + 0.1), true);
  assert.equal(passageEntre([premier], premier + 0.1, premier + 0.2), false);
});
