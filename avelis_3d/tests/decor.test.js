// Tests de src/decor.js (« npm test ») : le décor ne gêne ni les routes ni les objets, reste hors
// du foncier ou le long de son pourtour, et ne change pas d'un chargement à l'autre.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  AGV, ARBRES, CHARIOT_ACTIF, CLOTURE, ECART_REPERES, ECHELLE, GRAINE_DECOR, GROUPE_FROID, NORD,
  PARKING_VL, PLACES_DECOR, RACK,
} from "../src/apparence.js";
import { quaisNumerotes } from "../src/batiments.js";
import { preparerScene } from "../src/donnees.js";
import {
  aleatoire, arbresDuSite, clotureDuSite, creerOccupation, empriseEngin, enginsDuDecor,
  groupesFroids, placesDuParkingVl, racksDesStocks, reculChariot,
} from "../src/decor.js";
import {
  dansPolygone, distanceAuBord, distanceAuSegment, distanceEntreSegments, fermer,
} from "../src/traces.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const { site, objets, gabarits } = preparerScene(reference.scene);
const occupation = creerOccupation(site, objets, gabarits);

/** Distance du point `a` (ou du segment [a, b]) à ce qu'occupent les routes et les objets. */
function ecartOccupe(a, b = a) {
  return Math.min(...occupation.troncons.map((t) => distanceEntreSegments(a, b, t.a, t.b)
    - t.rayon));
}

test("tirage pseudo-aléatoire : reproductible, dans [0, 1)", () => {
  const [a, b] = [aleatoire(7), aleatoire(7)];
  const suite = Array.from({ length: 200 }, () => a());
  assert.deepEqual(suite, Array.from({ length: 200 }, () => b()));
  assert.ok(suite.every((x) => x >= 0 && x < 1));
  assert.notDeepEqual(suite.slice(0, 5), Array.from({ length: 5 }, aleatoire(8)));
});

test("occupation : routes, portail et objets occupés, le reste libre", () => {
  assert.equal(occupation.libre(site.voirie[1], 0), false);
  assert.equal(occupation.libre(site.portail, 0), false);
  assert.equal(occupation.libre(site.retournement.centre, 0), false);
  const lot = objets.find((o) => o.type === "lot");
  assert.equal(occupation.libre(lot.segments[0][2][0], 0), false);
  assert.equal(occupation.libre([1000, 1000], 10), true);
  // Repères : flèche du nord et échelle, gardées libres de tout décor
  assert.equal(occupation.libre([NORD.x, NORD.y], ECART_REPERES - 1e-3), false);
  assert.equal(occupation.libre([ECHELLE.x + ECHELLE.longueur / 2, ECHELLE.y],
    ECART_REPERES - 1e-3), false);
});

test("trois implantations : clôture et arbres hors des routes et des repères", () => {
  for (const [nom, autre] of Object.entries(reference.sites)) {
    const occupe = creerOccupation(autre, [], gabarits);
    const ecart = (a, b = a) => Math.min(...occupe.troncons.map((t) => distanceEntreSegments(a,
      b, t.a, t.b) - t.rayon));
    const { panneaux } = clotureDuSite(autre, occupe);
    assert.ok(panneaux.length > 100, nom);
    for (const p of panneaux) {
      const [ux, uy] = [Math.cos(p.angle) * p.longueur / 2, Math.sin(p.angle) * p.longueur / 2];
      assert.ok(ecart([p.x - ux, p.y - uy], [p.x + ux, p.y + uy]) > CLOTURE.marge - 1e-9, nom);
    }
    const arbres = arbresDuSite(autre, occupe, GRAINE_DECOR);
    assert.ok(arbres.length > 50, `${nom} : ${arbres.length} arbres`);
    for (const arbre of arbres) {
      const point = [arbre.x, arbre.y];
      assert.ok(autre.contours.every((c) => !dansPolygone(point, c.points)), nom);
      assert.ok(ecart(point) > arbre.rayon + ARBRES.margeVoie - 1e-9, nom);
    }
  }
});

test("occupation : la grille répond comme l'examen de tous les tronçons", () => {
  const tirage = aleatoire(3);
  for (let i = 0; i < 2000; i++) {
    const a = [-60 + tirage() * 560, -60 + tirage() * 420];
    const b = tirage() < 0.5 ? a : [a[0] + (tirage() - 0.5) * 8, a[1] + (tirage() - 0.5) * 8];
    const marge = tirage() * 6;
    assert.equal(occupation.libre(a, marge, b), ecartOccupe(a, b) > marge, `${a} ${b} ${marge}`);
  }
});

test("arbres : hors du foncier, loin des voies et des objets, espacés, reproductibles", () => {
  const arbres = arbresDuSite(site, occupation, GRAINE_DECOR);
  assert.ok(arbres.length > 40, `${arbres.length} arbres`);
  for (const arbre of arbres) {
    const point = [arbre.x, arbre.y];
    for (const contour of site.contours) {
      assert.equal(dansPolygone(point, contour.points), false);
      assert.ok(distanceAuBord(point, contour.points) >= ARBRES.margeFoncier + arbre.rayon);
    }
    assert.ok(ecartOccupe(point) > arbre.rayon + ARBRES.margeVoie - 1e-9);
    assert.ok(arbre.hauteur >= ARBRES.hauteur[0] && arbre.hauteur <= ARBRES.hauteur[1]);
  }
  for (let i = 0; i < arbres.length; i++) {
    for (let j = i + 1; j < arbres.length; j++) {
      const ecart = Math.hypot(arbres[i].x - arbres[j].x, arbres[i].y - arbres[j].y);
      assert.ok(ecart >= ARBRES.ecartMin);
    }
  }
  assert.deepEqual(arbresDuSite(site, occupation, GRAINE_DECOR), arbres);
});

/** Vrai si la bande {x, y, longueur, angle} est posée sur un côté du contour. */
function surLeBord(panneau, contour) {
  const [ux, uy] = [Math.cos(panneau.angle), Math.sin(panneau.angle)];
  const bouts = [-1, 1].map((s) => [panneau.x + (s * panneau.longueur * ux) / 2,
    panneau.y + (s * panneau.longueur * uy) / 2]);
  const bord = fermer(contour.points);
  return bord.slice(1).some((b, i) => bouts.every((p) => distanceAuSegment(p, bord[i], b)
    < 1e-6));
}

/** Côtés communs à deux contours (mêmes sommets, dans un sens ou dans l'autre). */
function cotesCommuns(a, b) {
  const cle = (p, q) => [p, q].map((s) => s.join(",")).sort().join(" ");
  const bordB = fermer(b.points);
  const cotesB = new Set(bordB.slice(1).map((q, i) => cle(bordB[i], q)));
  const bordA = fermer(a.points);
  return bordA.slice(1).map((q, i) => [bordA[i], q]).filter(([p, q]) => cotesB.has(cle(p, q)));
}

/** Vrai si la bande {x, y, longueur, angle} est posée sur l'un des côtés [p, q]. */
function surUnCote(panneau, cotes) {
  const [ux, uy] = [Math.cos(panneau.angle), Math.sin(panneau.angle)];
  const bouts = [-1, 1].map((s) => [panneau.x + (s * panneau.longueur * ux) / 2,
    panneau.y + (s * panneau.longueur * uy) / 2]);
  return cotes.some(([p, q]) => bouts.every((b) => distanceAuSegment(b, p, q) < 1e-6));
}

test("clôture : sur le pourtour, sauf la limite commune et le portail", () => {
  const { panneaux, poteaux } = clotureDuSite(site, occupation);
  const utilises = site.contours.filter((c) => c.utilise);
  assert.ok(panneaux.length > 100 && poteaux.length >= panneaux.length);
  for (const panneau of panneaux) {
    assert.ok(utilises.some((c) => surLeBord(panneau, c)));
    assert.ok(panneau.longueur <= CLOTURE.pas + 1e-9);
    const [ux, uy] = [Math.cos(panneau.angle) * panneau.longueur / 2,
      Math.sin(panneau.angle) * panneau.longueur / 2];
    assert.ok(ecartOccupe([panneau.x - ux, panneau.y - uy], [panneau.x + ux, panneau.y + uy])
      > CLOTURE.marge - 1e-9);
  }
  // Limite commune du site actuel et de l'extension, intérieure au foncier : sans clôture
  assert.ok(utilises.length === 2);
  const limite = cotesCommuns(...utilises);
  assert.ok(limite.length > 0);
  assert.equal(panneaux.some((p) => surUnCote(p, limite)), false);
  // Sans extension utilisée, cette limite redevient le bord du foncier
  const seul = { ...site, contours: site.contours.map((c) => ({ ...c,
    utilise: c.nom === "Site actuel" })) };
  const cloture = clotureDuSite(seul, occupation).panneaux;
  assert.ok(cloture.some((p) => surUnCote(p, limite)));
});

test("racks : dans les stocks couverts, le long des murs, hors du passage des objets", () => {
  const baies = racksDesStocks(site, occupation, GRAINE_DECOR);
  const stocks = site.zones.filter((z) => z.hauteur > 0 && z.nom.startsWith("Stock"));
  assert.ok(baies.length > 10, `${baies.length} baies`);
  for (const baie of baies) {
    const zone = stocks.find((z) => baie.x > z.x && baie.x < z.x + z.largeur && baie.y > z.y
      && baie.y < z.y + z.profondeur);
    assert.ok(zone, `baie hors des stocks : ${baie.x}, ${baie.y}`);
    const [ux, uy] = [Math.cos(baie.angle) * RACK.baie / 2, Math.sin(baie.angle) * RACK.baie / 2];
    assert.ok(ecartOccupe([baie.x - ux, baie.y - uy], [baie.x + ux, baie.y + uy])
      > RACK.profondeur / 2 + RACK.marge - 1e-9);
    assert.ok(baie.cartons.every(([niveau, place]) => niveau < RACK.niveaux && place < 2));
  }
  assert.deepEqual(racksDesStocks(site, occupation, GRAINE_DECOR), baies);
});

test("groupes froids : en rang sur le toit plat des bureaux", () => {
  const groupes = groupesFroids(site);
  const bureaux = site.zones.filter((z) => z.categorie === "Accueil et pilotage"
    && z.hauteur > 0);
  assert.ok(groupes.length > 0 && groupes.length <= GROUPE_FROID.nombreMax * bureaux.length);
  for (const groupe of groupes) {
    assert.ok(bureaux.some((z) => groupe.x - GROUPE_FROID.longueur / 2 > z.x
      && groupe.x + GROUPE_FROID.longueur / 2 < z.x + z.largeur
      && groupe.y - GROUPE_FROID.longueur / 2 > z.y
      && groupe.y + GROUPE_FROID.longueur / 2 < z.y + z.profondeur && groupe.z < z.hauteur));
  }
});

/** Vérifie les engins du site : hors du passage des objets, loin des racks et les uns des
 * autres, jamais à cheval sur un mur (dedans, ou à PLACES_DECOR.mur m au moins de tout
 * bâtiment), AGV en zone de production. */
function verifierEngins(lieu, engins, baies) {
  const { marge, mur } = PLACES_DECOR;
  const couvertes = lieu.zones.filter((z) => z.hauteur > 0);
  const dans = (z, [x, y], m) => x >= z.x + m && x <= z.x + z.largeur - m && y >= z.y + m
    && y <= z.y + z.profondeur - m;
  for (const e of engins) {
    const { a, b, rayon } = empriseEngin(e);
    assert.ok(ecartOccupe(a, b) > rayon + marge - 1e-9, `${e.forme} en ${e.x}, ${e.y}`);
    for (const { x, y, angle } of baies) {
      const [ux, uy] = [Math.cos(angle) * RACK.baie / 2, Math.sin(angle) * RACK.baie / 2];
      assert.ok(distanceEntreSegments(a, b, [x - ux, y - uy], [x + ux, y + uy])
        > RACK.profondeur / 2 + rayon);
    }
    for (const autre of engins.filter((o) => o !== e)) {
      const f = empriseEngin(autre);
      assert.ok(distanceEntreSegments(a, b, f.a, f.b) > rayon + f.rayon);
    }
    const coins = [a, b].flatMap(([x, y]) => [[x - rayon, y - rayon], [x + rayon, y + rayon]]);
    const zone = couvertes.find((z) => coins.every((c) => dans(z, c, mur)));
    assert.equal(Boolean(zone), e.dedans, `${e.forme} en ${e.x}, ${e.y}`);
    if (!zone) {
      assert.ok(couvertes.every((z) => coins.every((c) => !dans(z, c, -mur))),
        `${e.forme} à cheval sur un mur en ${e.x}, ${e.y}`);
    }
    if (e.forme === "agv") assert.equal(zone.categorie, AGV.zones);
  }
}

test("engins : chariots aux quais et dans les stocks, AGV en production, hors du passage", () => {
  const baies = racksDesStocks(site, occupation, GRAINE_DECOR);
  const engins = enginsDuDecor(site, occupation, baies, GRAINE_DECOR);
  // Quais d'expédition : un chariot à côté de chacun. Ceux de la façade est de la réception
  // n'ont pas de place libre entre les camions et la bretelle : aucun chariot n'y est posé.
  const quais = quaisNumerotes(site.quais);
  for (const quai of quais.slice(site.quais.reception.nombre)) {
    assert.ok(engins.some((e) => e.forme === "chariot" && !e.dedans && e.quai === quai.numero
      && Math.hypot(e.x - quai.x, e.y - quai.y) <= PLACES_DECOR.autourDuQuai * Math.SQRT2),
    `chariot au quai ${quai.numero}`);
  }
  for (const e of engins.filter((e) => e.quai)) {
    const quai = quais.find((q) => q.numero === e.quai);
    assert.ok(Math.hypot(e.x - quai.x, e.y - quai.y) <= PLACES_DECOR.autourDuQuai * Math.SQRT2);
  }
  assert.ok(engins.some((e) => e.forme === "agv"));
  verifierEngins(site, engins, baies);
  assert.deepEqual(enginsDuDecor(site, occupation, baies, GRAINE_DECOR), engins);
});

test("chariots des quais : place réservée à leur va-et-vient, recul de 0 à la course", () => {
  const baies = racksDesStocks(site, occupation, GRAINE_DECOR);
  const actifs = enginsDuDecor(site, occupation, baies, GRAINE_DECOR).filter((e) => e.quai);
  assert.ok(actifs.length > 0);
  for (const e of actifs) {
    assert.equal(e.course, CHARIOT_ACTIF.course);
    const { a, rayon } = empriseEngin(e);
    assert.ok(ecartOccupe(a) > rayon, `recul du chariot du quai ${e.quai} sur le passage`);
  }
  const { course, periode } = CHARIOT_ACTIF;
  assert.equal(reculChariot(0), 0);
  assert.ok(Math.abs(reculChariot(periode / 2) - course) < 1e-9);
  assert.ok(Math.abs(reculChariot(periode)) < 1e-9);
  const suite = Array.from({ length: 50 }, (_, i) => reculChariot((i * periode) / 49));
  assert.ok(suite.every((r) => r >= 0 && r <= course + 1e-9));
});

test("engins : un mur qui passe sur la place d'un chariot le fait changer de place", () => {
  const baies = racksDesStocks(site, occupation, GRAINE_DECOR);
  const [chariot] = enginsDuDecor(site, occupation, baies, GRAINE_DECOR);
  const essai = { nom: "Essai", libelle: "Essai", categorie: "Essai", couleur: "#000000",
    hauteur: 12, x: chariot.x - 0.3, y: chariot.y - 20, largeur: 20, profondeur: 40 };
  const lieu = { ...site, zones: [...site.zones, essai] };
  const engins = enginsDuDecor(lieu, occupation, baies, GRAINE_DECOR);
  assert.notDeepEqual([engins[0].x, engins[0].y], [chariot.x, chariot.y]);
  verifierEngins(lieu, engins, baies);
});

test("parking VL : dans le site, hors des zones ; places de part et d'autre de l'allée", () => {
  for (const [nom, s] of Object.entries(reference.sites)) {
    const p = s.parking_vl;
    const coins = [[p.x, p.y], [p.x + p.largeur, p.y], [p.x, p.y + p.profondeur],
      [p.x + p.largeur, p.y + p.profondeur]];
    assert.ok(coins.every((c) => dansPolygone(c, s.contours[0].points)), nom);
    for (const z of s.zones) {
      assert.ok(p.x >= z.x + z.largeur || z.x >= p.x + p.largeur || p.y >= z.y + z.profondeur
        || z.y >= p.y + p.profondeur, `${nom} : ${z.nom}`);
    }
    // la voie d'accès longe le côté est du parking sans le recouvrir, jusqu'à son nord
    const [vx, vy] = p.voie.at(-1);
    assert.equal(vx - PARKING_VL.voie / 2, p.x + p.largeur, nom);
    assert.ok(vy > p.y + p.profondeur - PARKING_VL.voie && vy <= p.y + p.profondeur, nom);
  }
  const { places, lignes } = placesDuParkingVl(site.parking_vl);
  const parRangee = Math.floor(site.parking_vl.largeur / PARKING_VL.largeur);
  const bandes = Math.floor(site.parking_vl.profondeur / (2 * PARKING_VL.profondeur
    + PARKING_VL.allee));
  assert.ok(bandes >= 3, "parking triplé vers le nord");
  assert.equal(places.length, 2 * bandes * parRangee);
  assert.equal(lignes.length, 2 * bandes * (parRangee + 1));
  for (const place of places) {
    const { x, y, largeur, profondeur } = site.parking_vl;
    assert.ok(place.x > x && place.x < x + largeur);
    // l'avant de la voiture regarde l'allée, dans le parking
    const allee = place.y + Math.sin(place.angle) * (PARKING_VL.profondeur + PARKING_VL.allee)
      / 2;
    assert.ok(allee > y && allee < y + profondeur);
  }
});
