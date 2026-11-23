// Tests de src/batiments.js (« npm test ») : toits, portes de quai numérotées, emblème.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  BATIMENT, EMBLEME, GRANDE_PORTE, PORTE, PORTE_PIETONNE, PORTES_NORD,
} from "../src/apparence.js";
import {
  batimentsDuSite, emblemesDuSite, grandesPortes, portesDeQuai, portesPietonnes,
  quaisNumerotes, siteSeul, toitDe,
} from "../src/batiments.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const site = reference.scene.site;
const zone = (nom) => site.zones.find((z) => z.nom === nom);
const actuelle = Object.entries(reference.sites).find(([nom]) => nom.startsWith("Actuelle"))[1];

test("toits : deux pans le long du plus grand côté, plat pour les bureaux", () => {
  const batiments = batimentsDuSite(site);
  assert.equal(batiments.length, site.zones.filter((z) => z.hauteur > 0).length);
  for (const batiment of batiments) {
    const { toit } = batiment;
    if (batiment.categorie === "Accueil et pilotage") {
      assert.equal(toit.forme, "plat", batiment.nom);
      continue;
    }
    assert.equal(toit.axe, batiment.largeur >= batiment.profondeur ? "x" : "y", batiment.nom);
    const portee = Math.min(batiment.largeur, batiment.profondeur);
    const attendue = Math.min(BATIMENT.flecheMax, (portee / 2) * Math.tan(BATIMENT.pente
      * Math.PI / 180));
    assert.ok(Math.abs(toit.fleche - attendue) < 1e-9, batiment.nom);
  }
  assert.equal(toitDe({ largeur: 400, profondeur: 100, categorie: "x" }).fleche,
    BATIMENT.flecheMax);
});

test("quais numérotés : réception puis expédition, un tous les `pas` [dx, dy] m", () => {
  const quais = quaisNumerotes(site.quais);
  const { reception, expedition } = site.quais;
  assert.equal(quais.length, reception.nombre + expedition.nombre);
  assert.deepEqual(quais.map((q) => q.numero), quais.map((_, i) => i + 1));
  assert.deepEqual([quais[1].x - quais[0].x, quais[1].y - quais[0].y], reception.pas);
  assert.deepEqual(quais[0].sens, [0, 1]); // façade est : rangée vers le nord
  assert.deepEqual([quais[reception.nombre].x, quais[reception.nombre].y], expedition.position);
  assert.deepEqual(quais[reception.nombre].sens, [1, 0]);
  const partages = quaisNumerotes({ ...site.quais, partages: true });
  assert.equal(partages.length, reception.nombre);
});

test("portes : sur le mur est de la réception, aucune pour les quais à ciel ouvert", () => {
  const portes = portesDeQuai(site);
  const reception = zone("Réception");
  for (const quai of portes.slice(0, site.quais.reception.nombre)) {
    assert.equal(quai.porte.zone, "Réception");
    assert.equal(quai.porte.mur, "est");
    assert.deepEqual(quai.porte.point, [reception.x + reception.largeur, quai.y]);
    assert.deepEqual(quai.porte.normale, [1, 0]);
  }
  // Les quais d'expédition donnent sur une zone à ciel ouvert, loin de tout mur
  for (const quai of portes.slice(site.quais.reception.nombre)) assert.equal(quai.porte, null);
});

test("portes : le mur le plus proche, et seulement si la porte y tient entière", () => {
  const hall = { nom: "hall", x: 0, y: 0, largeur: 20, profondeur: 20, hauteur: 10 };
  const quais = (x, y) => ({ reception: { position: [x, y], nombre: 1, pas: [10, 0] },
    expedition: { position: [x, y], nombre: 1, pas: [10, 0] }, partages: true });
  const porte = (x, y) => portesDeQuai({ zones: [hall], quais: quais(x, y) })[0].porte;
  assert.equal(porte(10, 24).mur, "nord");
  assert.equal(porte(-3, 10).mur, "ouest");
  assert.equal(porte(10, 20 + PORTE.distanceMax + 1), null); // trop loin
  assert.equal(porte(PORTE.largeur / 2 - 0.5, -2), null); // déborde du coin
  assert.deepEqual(porte(PORTE.largeur / 2, -2).point, [PORTE.largeur / 2, 0]);
});

test("logo : au milieu des faces sud et ouest des hangars choisis, sous le haut du mur", () => {
  assert.equal(siteSeul(site), false);
  const emblemes = emblemesDuSite(site);
  const halls = batimentsDuSite(site).filter((b) => EMBLEME.halls.includes(b.nom));
  assert.equal(halls.length, EMBLEME.halls.length);
  assert.equal(emblemes.length, 2 * halls.length + EMBLEME.nord.length);
  halls.forEach((hall) => {
    const murs = (mur) => emblemes.filter((e) => e.mur === mur
      && e.centre[0] >= hall.x && e.centre[0] <= hall.x + hall.largeur
      && e.centre[1] >= hall.y && e.centre[1] <= hall.y + hall.profondeur);
    const [[sud], [ouest], nord] = [murs("sud"), murs("ouest"), murs("nord")];
    assert.equal(nord.length, EMBLEME.nord.includes(hall.nom) ? 1 : 0);
    if (nord.length) {
      assert.deepEqual(nord[0].centre.slice(0, 2), [hall.x + hall.largeur / 2,
        hall.y + hall.profondeur]);
    }
    assert.deepEqual(sud.centre.slice(0, 2), [hall.x + hall.largeur / 2, hall.y]);
    assert.deepEqual(ouest.centre.slice(0, 2), [hall.x, hall.y + hall.profondeur / 2]);
    assert.ok(sud.largeur <= hall.largeur * EMBLEME.partMur);
    assert.ok(sud.centre[2] + sud.largeur / EMBLEME.rapport / 2 < hall.hauteur);
  });
  assert.deepEqual(emblemesDuSite({ zones: [], contours: [] }), []);
});

test("logo : face est du kitting dans l'implantation actuelle seulement", () => {
  assert.equal(siteSeul(actuelle), true);
  const est = (s) => emblemesDuSite(s).filter((e) => e.mur === "est");
  assert.deepEqual(est(site), []);
  const kitting = actuelle.zones.find((z) => z.nom === "Kitting");
  assert.deepEqual(est(actuelle).map((e) => e.centre.slice(0, 2)), EMBLEME.estSiteSeul.length
    ? [[kitting.x + kitting.largeur, kitting.y + kitting.profondeur / 2]] : []);
  assert.deepEqual(est(actuelle)[0].normale, [1, 0]);
});

test("grandes portes : une par groupe de quais, sans toucher les portes de quai", () => {
  const grandes = grandesPortes(site);
  assert.ok(grandes.length >= 1);
  const quais = portesDeQuai(site).filter((q) => q.porte);
  for (const g of grandes) {
    const z = zone(g.zone);
    assert.ok(g.point[0] >= z.x && g.point[0] <= z.x + z.largeur);
    assert.ok(g.point[1] >= z.y && g.point[1] <= z.y + z.profondeur);
    const k = ["sud", "nord"].includes(g.mur) ? 0 : 1; // coordonnée le long du mur
    for (const q of quais.filter((q) => q.porte.zone === g.zone && q.porte.mur === g.mur)) {
      assert.ok(Math.abs(q.porte.point[k] - g.point[k]) > (PORTE.largeur
        + GRANDE_PORTE.largeur) / 2);
    }
  }
  // la réception a la sienne sur sa façade est, au nord de ses quais
  const reception = grandes.find((g) => g.zone === "Réception");
  assert.equal(reception?.mur, "est");
  assert.ok(reception.point[1] > Math.max(...quais.filter((q) => q.porte.zone === "Réception")
    .map((q) => q.y)));
});

test("portes piétonnes : une sur le mur sud, et sur le mur nord des bâtiments choisis", () => {
  for (const [s, nord] of [[site, PORTES_NORD.toutes],
    [actuelle, [...PORTES_NORD.toutes, ...PORTES_NORD.siteSeul]]]) {
    const pietonnes = portesPietonnes(s);
    const sud = pietonnes.filter((p) => p.mur === "sud").map((p) => p.zone);
    assert.equal(new Set(sud).size, sud.length);
    assert.ok(sud.length >= batimentsDuSite(s).length - 2);
    assert.ok(sud.includes("Réception")); // libre depuis que les quais sont à l'est
    const auNord = pietonnes.filter((p) => p.mur === "nord");
    assert.deepEqual(auNord.map((p) => p.zone).sort(), [...nord].sort());
    for (const p of pietonnes) {
      const z = s.zones.find((zz) => zz.nom === p.zone);
      assert.equal(p.point[1], p.mur === "sud" ? z.y : z.y + z.profondeur);
      assert.ok(p.point[0] - PORTE_PIETONNE.auvent.largeur / 2 > z.x);
    }
  }
});
