// Ciel (cycle jour et nuit, météo), nuit, opérateurs à pied et ouvriers, mode « flux », marche
// à la première personne, sur le jeu de référence.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { CIEL_JOUR, GRAINE_DECOR, PERSONNEL, PIETON } from "../src/apparence.js";
import {
  ambiance, estNuit, heureDuJour, meteoOpenMeteo, meteoSimulee, soleil,
} from "../src/ciel.js";
import { directionDeMarche } from "../src/clavier.js";
import {
  circulationDuJour, creerCirculation, dureeAller, instantDeLHeure, poseDuSejour,
} from "../src/circulation.js";
import { ouvriersDesBatiments, poseOuvrier } from "../src/ouvriers.js";
import { preparerScene } from "../src/donnees.js";
import { trainees } from "../src/flux.js";
import { cheminsAPied, marchesDuJour, poseDuMarcheur } from "../src/pietons.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(reference.scene);
const sites = Object.entries(reference.sites);

test("ciel : heure de l'horloge, soleil levé le jour, au sud à midi, nuit sombre", () => {
  assert.equal(heureDuJour(0, scene.temps), scene.temps.heure_ouverture);
  assert.equal(heureDuJour(scene.temps.minutes_jour, scene.temps), scene.temps.heure_ouverture);
  const midi = soleil(13);
  assert.ok(midi.elevation > 0 && Math.abs(midi.azimut - Math.PI) < 0.3);
  assert.ok(soleil(CIEL_JOUR.coucher + 1).elevation < 0);
  const clair = meteoSimulee(1, 0);
  const [jour, nuit] = [ambiance(13, { ...clair, nuages: 0 }), ambiance(23, clair)];
  assert.equal(jour.jour, 1);
  assert.equal(nuit.jour, 0);
  assert.ok(nuit.intensite < jour.intensite && nuit.ciel.intensite < jour.ciel.intensite);
  assert.ok(jour.direction[2] > 0 && nuit.direction[2] > 0); // la lune éclaire d'en haut
});

test("météo : tirée à graine fixe par jour ; Open-Meteo traduit (pluie, neige, brume)", () => {
  assert.deepEqual(meteoSimulee(3, 2), meteoSimulee(3, 2));
  const types = new Set(Array.from({ length: 40 }, (_, j) => meteoSimulee(1, j).type));
  assert.ok(types.size >= 3, [...types].join(", "));
  assert.equal(meteoSimulee(Number.NaN, 0).type, meteoSimulee(0, 0).type); // jumeau
  const lire = (code, nuages = 0) => meteoOpenMeteo({ current: { weather_code: code,
    cloud_cover: nuages, temperature_2m: 11.4 } });
  assert.equal(lire(61).type, "pluie");
  assert.equal(lire(73).type, "neige");
  assert.equal(lire(45).type, "brume");
  assert.equal(lire(1, 90).type, "nuageux");
  assert.match(lire(0).libelle, /^Torcy en direct : ciel clair, 11 °C$/);
  assert.equal(meteoOpenMeteo({}), null);
});

test("opérateurs : chemins des portes au parking VL, hors des bâtiments", () => {
  for (const [nom, site] of sites) {
    const chemins = cheminsAPied(site);
    if (!site.parking_vl) {
      assert.equal(chemins.length, 0, nom);
      continue;
    }
    assert.ok(chemins.length > 0, nom);
    const couverts = site.zones.filter((z) => z.hauteur > 0);
    for (const { points } of chemins) {
      for (let k = 2; k < points.length; k++) { // après la sortie de la porte
        const [a, b] = [points[k - 1], points[k]];
        for (let u = 0; u <= 20; u++) {
          const [x, y] = [a[0] + ((b[0] - a[0]) * u) / 20, a[1] + ((b[1] - a[1]) * u) / 20];
          assert.ok(couverts.every((z) => x <= z.x || x >= z.x + z.largeur || y <= z.y
            || y >= z.y + z.profondeur), `${nom} : (${x}, ${y})`);
        }
      }
    }
  }
});

test("employés : descendent de leur voiture, vont à une porte du personnel, et retour", () => {
  const site = sites.find(([, s]) => s.parking_vl)[1];
  const circulation = creerCirculation(site, scene.temps, GRAINE_DECOR);
  const chemins = cheminsAPied(site);
  const marches = marchesDuJour(circulation, chemins, 1);
  const { sejours } = circulationDuJour(circulation, 1);
  const portes = chemins.map((c) => c.porte.point);
  const proche = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6;
  assert.ok(marches.length > 0 && marches.length % 2 === 0);
  for (const sejour of sejours.filter((s) => Number.isFinite(s.arrivee))) {
    const place = circulation.places[sejour.place];
    const [aller, retour] = [marches.find((m) => m.id === `${sejour.id}-a`),
      marches.find((m) => m.id === `${sejour.id}-d`)];
    // il descend une fois la voiture garée, et finit à une porte du personnel
    assert.ok(aller.debut >= sejour.arrivee + dureeAller(sejour), sejour.id);
    assert.ok(Math.hypot(aller.points[0][0] - place.x, aller.points[0][1] - place.y)
      < PIETON.sortie + 4, sejour.id);
    assert.ok(portes.some((p) => proche(p, aller.points.at(-1))), sejour.id);
    // le soir, il sort par une porte et rejoint sa voiture avant qu'elle reparte
    assert.ok(portes.some((p) => proche(p, retour.points[0])), sejour.id);
    const finRetour = retour.debut + retour.longueurs.at(-1) / (PIETON.vitesse * 60);
    assert.ok(finRetour <= sejour.depart + 1e-9, sejour.id);
    assert.equal(poseDuMarcheur(aller, aller.debut - 0.01), null);
    assert.ok(poseDuMarcheur(aller, aller.debut + 0.01));
  }
});

test("flux : la proposée relie les zones en U, de la Réception à l'Expédition", () => {
  const { objets, camions } = trainees(scene.objets, scene.site);
  const couples = new Set(objets.map((f) => `${f.de}→${f.vers}`));
  for (const couple of ["Réception→Stock matières", "Stock produits finis→Expédition"]) {
    assert.ok(couples.has(couple), [...couples].join(" ; "));
  }
  assert.ok(objets.every((f) => f.part > 0 && f.part <= 1));
  assert.ok(objets.some((f) => f.part === 1) && camions.some((c) => c.part === 1));
});

test("nuit : soleil couché ; parking VL presque vide, seulement les permanents", () => {
  assert.equal(estNuit(13), false);
  assert.equal(estNuit(CIEL_JOUR.coucher + 0.5), true);
  assert.equal(estNuit(CIEL_JOUR.lever - 0.5), true);
  const site = sites.find(([, s]) => s.parking_vl)[1];
  const circulation = creerCirculation(site, scene.temps, GRAINE_DECOR);
  const { sejours } = circulationDuJour(circulation, 1);
  const garees = (h) => sejours.filter((s) => poseDuSejour(s,
    instantDeLHeure(scene.temps, 1, h))).length;
  const permanents = Math.round(PERSONNEL.permanents * circulation.places.length);
  assert.equal(garees(CIEL_JOUR.coucher + 0.6), permanents);
  assert.ok(garees(11) > 3 * permanents, `${garees(11)} à 11 h`);
});

test("ouvriers : dans leur bâtiment, à l'arrêt ou en marche, à graine fixe", () => {
  for (const [nom, site] of sites) {
    const ouvriers = ouvriersDesBatiments(site, 5);
    assert.ok(ouvriers.length > 0, nom);
    assert.deepEqual(ouvriersDesBatiments(site, 5), ouvriers);
    for (const o of ouvriers) {
      const z = site.zones.find((zone) => zone.nom === o.zone);
      assert.ok(z.hauteur > 0, nom);
      const etats = new Set();
      for (let s = 0; s < 2 * o.periode; s += o.periode / 37) {
        const p = poseOuvrier(o, s);
        etats.add(p.marche);
        assert.ok(p.x > z.x && p.x < z.x + z.largeur && p.y > z.y
          && p.y < z.y + z.profondeur, `${nom} : ${o.zone}`);
      }
      assert.equal(etats.size, 2, o.zone);
    }
  }
});

test("première personne : Z avance dans le regard, D va à droite, Q à gauche", () => {
  const proche = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 1e-9);
  assert.ok(proche(directionDeMarche(new Set(["avant"]), 0), [1, 0]));
  assert.ok(proche(directionDeMarche(new Set(["droite"]), Math.PI / 2), [1, 0]));
  assert.ok(proche(directionDeMarche(new Set(["gauche"]), 0), [0, 1]));
  assert.ok(proche(directionDeMarche(new Set(), 0), [0, 0]));
});
