// Tests de src/details.js (« npm test ») : timeline de traçabilité, statut, progression,
// propriétés, onglets Quais / Camions / Stocks, sur le jeu de référence (tests/reference.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  alertesDeLObjet, etapesTracabilite, lieuDeLObjet, listeCamions, listeQuais, listeStocks,
  progression, proprietes, statutObjet, zoneDuPoint,
} from "../src/details.js";
import { etatObjet, preparerScene } from "../src/donnees.js";
import { arretsAQuai, creerTrajectoires } from "../src/trajectoires.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(structuredClone(reference.scene));
const contexte = creerTrajectoires(scene.site, scene.gabarits);
const arrets = arretsAQuai(scene.objets, contexte);
const duree = scene.temps.duree;
const premier = (type, filtre = () => true) => scene.objets.find((o) => o.type === type
  && filtre(o));

test("timeline d'un module : ses 8 points obligatoires dans l'ordre, états à l'instant", () => {
  const module = premier("module", (o) => o.evenements.some((e) => e[1] === "Expédié"));
  const { etapes, courante } = etapesTracabilite(scene, module, duree, contexte);
  assert.deepEqual(etapes.map((e) => e.nom), scene.tracabilite.points_module);
  assert.equal(courante, etapes.length - 1);
  assert.ok(etapes.every((e) => e.etat === "affichee" || e.etat === "non_lue"));
  const [t0, , , affichage] = module.evenements[0];
  const avant = etapesTracabilite(scene, module, t0 - 1e-6, contexte);
  assert.equal(avant.courante, -1);
  assert.ok(avant.etapes.every((e) => e.etat === "a_venir" && e.heure === null));
  if (affichage !== null && affichage > t0) {
    const entre = etapesTracabilite(scene, module, (t0 + affichage) / 2, contexte);
    assert.equal(entre.etapes[0].etat, "attente");
    assert.equal(entre.courante, 0);
  }
});

test("timeline : un événement non lu reste « non lue », jamais affiché", () => {
  const objet = { type: "lot", id: "LOT-X", evenements: [[1, "Réception", "Réception", null, ""],
    [2, "Entrée stock matières", "Stock matières", 2.5, ""]], segments: [], liens: {} };
  const { etapes } = etapesTracabilite(scene, objet, 3, contexte);
  assert.deepEqual(etapes.map((e) => e.etat), ["non_lue", "affichee"]);
  assert.equal(etapes[0].affichage, null);
});

test("timeline d'un camion : ses événements, puis ses arrêts à quai (position simulée)", () => {
  const camion = premier("camion", (o) => o.segments.some((_, i) =>
    arrets.size && [...arrets.values()].some((l) => l.some((a) => a.objet === o))));
  const { etapes } = etapesTracabilite(scene, camion, duree, contexte);
  assert.equal(etapes[0].nom, "Arrivée sur site");
  const quais = etapes.filter((e) => e.nom.startsWith("À quai"));
  assert.ok(quais.length > 0 && quais.every((e) => e.etat === "position"));
  const instants = etapes.map((e) => e.instant);
  assert.deepEqual(instants, [...instants].sort((a, b) => a - b));
});

test("statut : dernière étape, « bon » à la fin du parcours, alerte plus récente d'abord", () => {
  const module = premier("module", (o) => o.evenements.some((e) => e[1] === "Expédié"));
  assert.deepEqual(statutObjet(scene, module, duree, contexte), { texte: "Expédié", ton: "bon" });
  assert.equal(statutObjet(scene, module, -1, contexte).ton, "neutre");
  const t = module.evenements[2][0];
  assert.deepEqual(statutObjet(scene, module, t, contexte),
    { texte: module.evenements[2][1], ton: "en_cours" });
  const avecAlerte = { ...scene, tracabilite: { ...scene.tracabilite,
    alertes: [[t + 1, t + 1.1, "Attente composant", module.id, "module", "Assemblage 3D", ""]] } };
  assert.deepEqual(statutObjet(avecAlerte, module, t + 2, contexte),
    { texte: "Attente composant", ton: "alerte" });
  assert.equal(alertesDeLObjet(avecAlerte, module, t + 1.05).length, 0); // pas encore affichée
});

test("progression des points obligatoires ; null pour un camion", () => {
  const pod = premier("pod", (o) => o.evenements.some((e) => e[1] === "Intégré au module"));
  const fin = progression(scene, pod, duree, contexte);
  assert.equal(fin.total, scene.tracabilite.points_pod.length);
  assert.equal(fin.faits, fin.total);
  assert.ok(fin.affiches <= fin.faits);
  assert.equal(progression(scene, premier("camion"), duree, contexte), null);
});

test("propriétés : lieu, événements, liens cliquables", () => {
  const module = premier("module", (o) => o.liens.camion);
  const lignes = Object.fromEntries(proprietes(scene, module, duree, contexte)
    .map((l) => [l.nom, l]));
  assert.equal(lignes.Type.valeur, "Module 3D");
  assert.deepEqual(lignes.Pod.liens, [module.liens.pod]);
  assert.deepEqual(lignes.Camion.liens, [module.liens.camion]);
  assert.match(lignes["Événements"].valeur, /^\d+ affichés sur 8 survenus$/);
  const camion = scene.objets.find((o) => o.id === module.liens.camion);
  assert.deepEqual(Object.fromEntries(proprietes(scene, camion, duree, contexte)
    .map((l) => [l.nom, l])).Modules.liens, camion.liens.modules);
});

test("lieu et zone : quai, trajet, zone du site, hors du site", () => {
  const zone = scene.site.zones.find((z) => z.nom === "Stock matières");
  assert.equal(zoneDuPoint(scene.site, zone.x + 1, zone.y + 1).nom, "Stock matières");
  assert.equal(zoneDuPoint(scene.site, -1e6, -1e6), null);
  const [numero, liste] = [...arrets].find(([, l]) => l.length > 0);
  const arret = liste[0];
  assert.equal(lieuDeLObjet(scene, arret.objet, arret.debut, contexte), `À quai ${numero}`);
  const camion = arret.objet;
  const trajet = camion.segments.find((s) => s[2].length > 1);
  assert.equal(lieuDeLObjet(scene, camion, (trajet[0] + trajet[1]) / 2, contexte), "En route");
  assert.equal(lieuDeLObjet(scene, camion, -1e9, contexte), "Hors du site");
});

test("onglet Quais : chaque quai, libre ou occupé par le camion qui y est arrêté", () => {
  const [numero, liste] = [...arrets].find(([, l]) => l.length > 0);
  const { debut, objet } = liste[0];
  const quais = listeQuais(scene, arrets, debut);
  assert.equal(quais.length, contexte.quais.length);
  const quai = quais.find((q) => q.numero === numero);
  assert.equal(quai.camion, objet);
  assert.equal(quai.statut, objet.id.startsWith("EXP-") ? "Chargement" : "Déchargement");
  assert.ok(quais.every((q) => q.fonction !== ""));
  assert.ok(listeQuais(scene, arrets, -1).every((q) => q.statut === "Libre"));
});

test("onglet Camions : les camions visibles, à quai d'abord", () => {
  const { debut } = [...arrets.values()].find((l) => l.length > 0)[0];
  const camions = listeCamions(scene, debut, contexte);
  const visibles = scene.objets.filter((o) => o.type === "camion" && etatObjet(o, debut));
  assert.equal(camions.length, visibles.length);
  assert.ok(camions[0].lieu.startsWith("À quai"));
  const rangs = camions.map((c) => ["bon", "en_cours", "attente"].indexOf(c.ton));
  assert.deepEqual(rangs, [...rangs].sort((a, b) => a - b));
});

test("onglet Stocks : zones de stock, valeur du pilotage, objets posés", () => {
  const t = duree / 2;
  const stocks = listeStocks(scene, t);
  assert.deepEqual(stocks.map((s) => s.zone).sort(),
    scene.site.zones.filter((z) => z.nom.startsWith("Stock")).map((z) => z.libelle).sort());
  const matieres = stocks.find((s) => s.zone.startsWith("Stock matières"));
  assert.equal(matieres.unite, "kits");
  assert.ok(Number.isInteger(matieres.valeur));
  for (const { objets } of stocks) assert.ok(objets.every(([, n]) => n > 0));
});
