// Tests de src/trajectoires.js (« npm test ») : la couche visuelle garde les instants et les
// arrêts de la référence (etatObjet, comparée à Python) et s'en écarte d'une distance bornée ;
// virages, accélérations, marche arrière à quai, odomètre, arrêts à quai, emprises du décor.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { PORTE, QUAI, TRAJECTOIRES } from "../src/apparence.js";
import { etatObjet, preparerScene } from "../src/donnees.js";
import {
  arrondir, arretEnCours, arretsAQuai, avancement, axesDesManoeuvres, creerTrajectoires,
  etatAffiche, quaiDuSegment,
} from "../src/trajectoires.js";

const reference = JSON.parse(readFileSync(new URL("./reference.json", import.meta.url), "utf8"));
const scene = preparerScene(reference.scene);
const contexte = creerTrajectoires(scene.site, scene.gabarits);
const LONGUEUR = scene.gabarits.camion[1];
const PARTS = 40; // instants essayés par segment
const EPS = 1e-6;

/** Écart (rad) entre deux caps, entre 0 et π. */
function ecartDeCap(a, b) {
  const e = Math.abs(a - b) % (2 * Math.PI);
  return Math.min(e, 2 * Math.PI - e);
}

/** Distance d'un point {x, y} à une polyligne. */
function distanceAuChemin({ x, y }, chemin) {
  if (chemin.length === 1) return Math.hypot(x - chemin[0][0], y - chemin[0][1]);
  let minimum = Infinity;
  for (let k = 1; k < chemin.length; k++) {
    const [[ax, ay], [bx, by]] = [chemin[k - 1], chemin[k]];
    const l2 = (bx - ax) ** 2 + (by - ay) ** 2;
    const s = l2 > 0 ? Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay))
      / l2)) : 0;
    minimum = Math.min(minimum, Math.hypot(x - ax - s * (bx - ax), y - ay - s * (by - ay)));
  }
  return minimum;
}

/** Instants intérieurs d'un segment de [t0, t1] (t1 null : 10 min). */
function instantsDu([t0, t1]) {
  const fin = t1 ?? t0 + 10;
  return Array.from({ length: PARTS + 1 }, (_, k) => t0 + ((fin - t0) * k) / PARTS)
    .filter((t) => t < fin);
}

/** [objet, i] de chaque segment de la scène qui vérifie `garder(objet, i)`. */
function segments(garder = () => true) {
  return scene.objets.flatMap((o) => o.segments.map((_, i) => [o, i]))
    .filter(([o, i]) => garder(o, i));
}

const enRoute = (o, i) => o.segments[i][2].length > 1;
// quais à porte (marche arrière) ; à ciel ouvert, le camion se gare en long, en marche avant
const aPorte = (o, k) => Boolean(quaiDuSegment(o, k, contexte)?.porte);
const enLong = (o, k) => quaiDuSegment(o, k, contexte)?.porte === null;
const versQuai = (o, i) => enRoute(o, i) && aPorte(o, i + 1);
const depuisQuai = (o, i) => enRoute(o, i) && aPorte(o, i - 1);

test("mêmes instants : un objet est affiché exactement quand la référence le montre", () => {
  for (const objet of scene.objets) {
    const instants = objet.segments.flatMap(([t0, t1]) => [t0 - 1e-3, t0, t1 ?? t0 + 1,
      (t1 ?? t0 + 1) - 1e-9, ...instantsDu([t0, t1])]);
    for (const t of instants) {
      assert.equal(etatAffiche(objet, t, contexte) === null, etatObjet(objet, t) === null,
        `${objet.id} à ${t}`);
    }
  }
});

test("arrêts : à la place de la référence, sauf les camions à quai, retournés contre le quai",
  () => {
    let aQuai = 0;
    for (const [objet, i] of segments((o, k) => !enRoute(o, k))) {
      const t = objet.segments[i][0];
      const [vu, ref] = [etatAffiche(objet, t, contexte), etatObjet(objet, t)];
      const quai = quaiDuSegment(objet, i, contexte);
      if (!quai) {
        assert.deepEqual([vu.x, vu.y, vu.cap, vu.quai], [ref.x, ref.y, ref.cap, null], objet.id);
        continue;
      }
      aQuai += 1;
      assert.equal(vu.quai, quai.numero);
      if (!quai.porte) { // en long : au point de la référence, dans le sens de la rangée
        assert.deepEqual([vu.x, vu.y], [ref.x, ref.y], objet.id);
        assert.ok(ecartDeCap(vu.cap, Math.atan2(quai.sens[1], quai.sens[0])) < EPS, objet.id);
        continue;
      }
      assert.ok(ecartDeCap(vu.cap, ref.cap + Math.PI) < EPS, `${objet.id} retourné`);
      const entree = [Math.cos(ref.cap), Math.sin(ref.cap)]; // sens d'entrée dans le quai
      const arriere = [vu.x + entree[0] * LONGUEUR / 2, vu.y + entree[1] * LONGUEUR / 2];
      const fond = (quai.porte.point[0] - quai.x) * entree[0]
        + (quai.porte.point[1] - quai.y) * entree[1] - TRAJECTOIRES.recul;
      assert.ok(Math.abs((arriere[0] - quai.x) * entree[0] + (arriere[1] - quai.y) * entree[1]
        - fond) < EPS, `${objet.id} : arrière au fond du quai`);
      assert.ok(Math.abs((arriere[0] - quai.x) * entree[1] - (arriere[1] - quai.y) * entree[0])
        < EPS, `${objet.id} : dans l'axe du quai`);
    }
    assert.ok(aQuai > 0, "la référence a des camions à quai");
  });

test("trajets : à TRAJECTOIRES.rayonVirage m au plus du chemin, sauf en manœuvre près du quai",
  () => {
    const pres = LONGUEUR + PORTE.distanceMax + QUAI.longueur; // quai à moins de 6 m du mur
    for (const [objet, i] of segments(enRoute)) {
      const chemin = objet.segments[i][2];
      const quais = [i - 1, i + 1].map((k) => quaiDuSegment(objet, k, contexte)).filter(Boolean);
      for (const t of instantsDu(objet.segments[i])) {
        const vu = etatAffiche(objet, t, contexte);
        if (distanceAuChemin(vu, chemin) <= TRAJECTOIRES.rayonVirage + EPS) continue;
        assert.ok(quais.some((q) => Math.hypot(vu.x - q.x, vu.y - q.y) <= pres),
          `${objet.id} à ${t} : (${vu.x}, ${vu.y})`);
      }
    }
  });

test("trajets : partent et arrivent sans saut, à la référence quand l'objet paraît ou disparaît",
  () => {
    for (const [objet, i] of segments(enRoute)) {
      const [t0, t1] = objet.segments[i];
      const [debut, fin] = [etatAffiche(objet, t0, contexte), etatAffiche(objet, t1 - 1e-9,
        contexte)];
      // la pose affichée juste avant et juste après, ou celle de la référence s'il est masqué
      const attendus = [etatAffiche(objet, t0 - 1e-9, contexte) ?? etatObjet(objet, t0),
        etatAffiche(objet, t1, contexte) ?? etatObjet(objet, t1 - 1e-9)];
      for (const [vu, attendu] of [[debut, attendus[0]], [fin, attendus[1]]]) {
        assert.ok(Math.hypot(vu.x - attendu.x, vu.y - attendu.y) < 1e-3, objet.id);
      }
    }
  });

test("accélération : vitesse nulle à côté d'un arrêt, constante entre les rampes", () => {
  for (const rampes of [[true, true], [true, false], [false, true], [false, false]]) {
    assert.equal(avancement(0, rampes), 0);
    assert.ok(Math.abs(avancement(1, rampes) - 1) < EPS);
    let avant = 0;
    for (let k = 1; k <= 100; k++) {
      const s = avancement(k / 100, rampes);
      assert.ok(s >= avant - EPS, "toujours en avant");
      avant = s;
    }
    const d = 1e-4;
    const [vDebut, vFin] = [avancement(d, rampes) / d, (1 - avancement(1 - d, rampes)) / d];
    assert.equal(vDebut < 0.01, rampes[0], `départ ${rampes}`);
    assert.equal(vFin < 0.01, rampes[1], `arrivée ${rampes}`);
  }
  assert.ok(Math.abs(avancement(0.37, [false, false]) - 0.37) < EPS);
  const milieu = (p) => avancement(p + 0.01, [true, true]) - avancement(p, [true, true]);
  assert.ok(Math.abs(milieu(0.4) - milieu(0.6)) < EPS, "vitesse constante au milieu");
});

test("virages : arcs tangents de rayon borné, extrémités gardées, demi-tour intact", () => {
  const angle = arrondir([[0, 0], [10, 0], [10, 10]]);
  assert.deepEqual([angle[0], angle.at(-1)], [[0, 0], [10, 10]]);
  const rayon = Math.min(TRAJECTOIRES.rayonVirage, 5); // la moitié du tronçon au plus
  const arc = angle.slice(1, -1);
  assert.ok(arc.length > 2);
  for (const [x, y] of arc) {
    assert.ok(Math.abs(Math.hypot(x - (10 - rayon), y - rayon) - rayon) < EPS, "sur l'arc");
  }
  assert.ok(Math.abs(arc[0][0] - (10 - rayon)) < EPS && Math.abs(arc.at(-1)[1] - rayon) < EPS);
  const court = arrondir([[0, 0], [2, 0], [2, 10]]).slice(1, -1);
  assert.ok(court.every(([x, y]) => x >= 1 - EPS && y <= 1 + EPS), "rayon réduit à 1 m");
  assert.deepEqual(arrondir([[0, 0], [10, 0], [0, 0]]), [[0, 0], [10, 0], [0, 0]]);
});

test("marche arrière à quai : le camion dépasse l'entrée, recule, repart, sans volte-face",
  () => {
    const manoeuvres = segments((o, i) => versQuai(o, i) || depuisQuai(o, i));
    assert.ok(manoeuvres.length > 0);
    for (const [objet, i] of manoeuvres) {
      const [t0, t1] = objet.segments[i];
      const instants = Array.from({ length: 801 }, (_, k) => t0 + ((t1 - t0) * k) / 800)
        .map((t) => Math.min(t, t1 - 1e-9));
      const poses = instants.map((t) => etatAffiche(objet, t, contexte));
      for (let k = 1; k < poses.length; k++) {
        assert.ok(ecartDeCap(poses[k].cap, poses[k - 1].cap) < 0.35, `${objet.id} à ${k}`);
      }
      const sens = ([a, b]) => (b.x - a.x) * Math.cos(a.cap) + (b.y - a.y) * Math.sin(a.cap);
      if (versQuai(objet, i)) assert.ok(sens(poses.slice(-3, -1)) < 0, `${objet.id} recule`);
      if (depuisQuai(objet, i)) assert.ok(sens(poses.slice(1, 3)) > 0, `${objet.id} avance`);
      const voisin = etatAffiche(objet, versQuai(objet, i) ? t1 : t0 - 1e-9, contexte);
      const bout = versQuai(objet, i) ? poses.at(-1) : poses[0];
      assert.ok(ecartDeCap(voisin.cap, bout.cap) < 0.1, `${objet.id} : cap continu au quai`);
    }
  });

test("quai en long : le camion y entre et en sort en marche avant, sans volte-face", () => {
  const trajets = segments((o, i) => enRoute(o, i) && (enLong(o, i + 1) || enLong(o, i - 1)));
  assert.ok(trajets.length > 0, "la référence a des quais en long");
  for (const [objet, i] of trajets) {
    const [t0, t1] = objet.segments[i];
    const poses = Array.from({ length: 401 }, (_, k) => Math.min(t0 + ((t1 - t0) * k) / 400,
      t1 - 1e-9)).map((t) => etatAffiche(objet, t, contexte));
    for (let k = 1; k < poses.length; k++) {
      assert.ok(ecartDeCap(poses[k].cap, poses[k - 1].cap) < 0.35, `${objet.id} à ${k}`);
      const [a, b] = [poses[k - 1], poses[k]];
      assert.ok((b.x - a.x) * Math.cos(a.cap) + (b.y - a.y) * Math.sin(a.cap) >= -EPS,
        `${objet.id} avance à ${k}`);
    }
  }
});

test("odomètre : continu, croît en marche avant, décroît en marche arrière", () => {
  for (const objet of scene.objets) {
    objet.segments.forEach(([t0, t1], i) => {
      if (i > 0) {
        const [avant, apres] = [etatAffiche(objet, t0 - 1e-9, contexte),
          etatAffiche(objet, t0, contexte)];
        if (avant) assert.ok(Math.abs(avant.odometre - apres.odometre) < 1e-3, objet.id);
      }
      if (!enRoute(objet, i)) return;
      // pas assez court pour que, dans un virage, la corde se confonde avec l'arc
      const [a, b] = [t0 + (t1 - t0) * 0.4, t0 + (t1 - t0) * 0.4001].map((t) => etatAffiche(
        objet, t, contexte));
      const pas = Math.hypot(b.x - a.x, b.y - a.y);
      assert.ok(Math.abs(Math.abs(b.odometre - a.odometre) - pas) < 1e-4, objet.id);
    });
  }
  const [objet, i] = segments(versQuai)[0];
  const t1 = objet.segments[i][1];
  const [a, b] = [t1 - 1e-3, t1 - 1e-4].map((t) => etatAffiche(objet, t, contexte));
  assert.ok(b.odometre < a.odometre, "décroît en reculant");
});

test("arrêts à quai : le camion arrêté à chaque quai, à chaque instant", () => {
  const arrets = arretsAQuai(scene.objets, contexte);
  assert.deepEqual([...arrets.keys()], contexte.quais.map((q) => q.numero));
  for (const t of Array.from({ length: 400 }, (_, k) => (k * scene.temps.duree) / 400)) {
    for (const [numero, liste] of arrets) {
      const enCours = arretEnCours(liste, t);
      const aQuai = scene.objets.filter((o) => etatAffiche(o, t, contexte)?.quai === numero);
      assert.deepEqual(enCours ? [enCours.objet.id] : [], aQuai.map((o) => o.id), `${t}`);
    }
  }
});

test("décor : les emprises des manœuvres couvrent le camion qui recule et celui à quai", () => {
  const axes = axesDesManoeuvres(scene.objets, contexte);
  // entre deux poses des manœuvres, à moins d'un demi-pas de leurs axes
  const surUnAxe = (p) => axes.some((axe) => distanceAuChemin(p, axe) < 0.5);
  for (const [objet, i] of segments(versQuai)) {
    const [t0, t1] = objet.segments[i];
    for (const t of [t1 - (t1 - t0) * 0.01, t1 - 1e-9, t1 + 1e-3]) {
      assert.ok(surUnAxe(etatAffiche(objet, t, contexte)), `${objet.id} à ${t}`);
    }
  }
});
