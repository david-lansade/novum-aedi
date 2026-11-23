// Tests de src/clavier.js (« npm test ») : touches lues à leur place (Z Q S D d'un clavier
// AZERTY), direction au sol selon l'orientation de la caméra, vitesse, touches gardées par
// l'élément qui a le focus, déplacement borné autour du site, montée en douceur de la vitesse.
import { test } from "node:test";
import assert from "node:assert/strict";

import { NAVIGATION } from "../src/apparence.js";
import { axesEcran } from "../src/cadrage.js";
import {
  TOUCHES, actionsDe, approcher, bornerDeplacement, directionAuSol, sensRotation,
  toucheReservee, vitesseAuSol,
} from "../src/clavier.js";

const DEGRE = Math.PI / 180;
const PRECISION = 1e-9;

/** Vérifie que deux vecteurs [x, y] sont égaux à PRECISION près. */
function egaux(u, v, message) {
  assert.ok(Math.abs(u[0] - v[0]) < PRECISION && Math.abs(u[1] - v[1]) < PRECISION,
    `${message} : ${u} au lieu de ${v}`);
}

test("touches : Z Q S D d'un clavier AZERTY, à leur place QWERTY, et les flèches", () => {
  // place W = touche Z, A = Q, Q = A sur un clavier AZERTY
  assert.equal(TOUCHES.KeyW, "avant");
  assert.equal(TOUCHES.KeyA, "gauche");
  assert.equal(TOUCHES.KeyS, "arriere");
  assert.equal(TOUCHES.KeyD, "droite");
  assert.equal(TOUCHES.KeyQ, "tournerGauche");
  assert.equal(TOUCHES.KeyE, "tournerDroite");
  assert.deepEqual(actionsDe(["ArrowUp", "ArrowLeft", "ShiftRight", "KeyX"]),
    new Set(["avant", "gauche", "rapide"]));
});

test("direction : avancer va de la caméra vers sa cible, droite suit l'écran", () => {
  for (const azimut of [45, 135, 225, 315, -90].map((a) => a * DEGRE)) {
    const { direction, droite } = axesEcran(azimut, 35 * DEGRE);
    const horizontale = Math.hypot(direction[0], direction[1]);
    egaux(directionAuSol(new Set(["avant"]), azimut),
      [-direction[0] / horizontale, -direction[1] / horizontale], "avant");
    egaux(directionAuSol(new Set(["droite"]), azimut), [droite[0], droite[1]], "droite");
    egaux(directionAuSol(new Set(["gauche"]), azimut), [-droite[0], -droite[1]], "gauche");
  }
  // caméra au sud-ouest (vue par défaut) : avancer va au nord-est, droite au sud-est
  const r = Math.SQRT1_2;
  egaux(directionAuSol(new Set(["avant"]), 225 * DEGRE), [r, r], "nord-est");
  egaux(directionAuSol(new Set(["droite"]), 225 * DEGRE), [r, -r], "sud-est");
});

test("direction : touches opposées annulées, diagonale de longueur 1", () => {
  const azimut = 225 * DEGRE;
  assert.deepEqual(directionAuSol(new Set(["avant", "arriere"]), azimut), [0, 0]);
  assert.deepEqual(directionAuSol(new Set(["gauche", "droite"]), azimut), [0, 0]);
  assert.deepEqual(directionAuSol(new Set(), azimut), [0, 0]);
  const [x, y] = directionAuSol(new Set(["avant", "droite"]), azimut);
  assert.ok(Math.abs(Math.hypot(x, y) - 1) < PRECISION);
  egaux([x, y], [1, 0], "nord-est + sud-est = est");
});

test("rotation et vitesse", () => {
  assert.equal(sensRotation(new Set(["tournerGauche"])), -1);
  assert.equal(sensRotation(new Set(["tournerDroite"])), 1);
  assert.equal(sensRotation(new Set(["tournerGauche", "tournerDroite"])), 0);
  assert.equal(sensRotation(new Set(["avant"])), 0);
  const lente = vitesseAuSol(1600, 4, false);
  assert.ok(Math.abs(lente * NAVIGATION.traversee - 400) < PRECISION); // 400 m visibles
  assert.ok(Math.abs(vitesseAuSol(1600, 4, true) - lente * NAVIGATION.rapide) < PRECISION);
  assert.ok(vitesseAuSol(1600, 8, false) < lente); // plus de zoom, plus lent au sol
});

test("touches gardées par l'élément qui a le focus", () => {
  assert.equal(toucheReservee("KeyW", null), false);
  assert.equal(toucheReservee("KeyW", { tagName: "BUTTON" }), false);
  assert.equal(toucheReservee("ArrowUp", { tagName: "INPUT", type: "checkbox" }), false);
  assert.equal(toucheReservee("ArrowLeft", { tagName: "INPUT", type: "range" }), true);
  assert.equal(toucheReservee("KeyW", { tagName: "INPUT", type: "range" }), false);
  assert.equal(toucheReservee("KeyW", { tagName: "INPUT", type: "text" }), true);
  assert.equal(toucheReservee("KeyW", { tagName: "INPUT" }), true);
  assert.equal(toucheReservee("KeyD", { tagName: "SELECT" }), true);
  assert.equal(toucheReservee("KeyS", { tagName: "TEXTAREA" }), true);
  assert.equal(toucheReservee("KeyS", { tagName: "DIV", isContentEditable: true }), true);
});

test("déplacement borné autour du site, axe par axe", () => {
  const cadre = { cx: 100, cy: 50, etendue: 200 };
  const bord = NAVIGATION.bord * cadre.etendue;
  assert.deepEqual(bornerDeplacement([10, -10], [100, 50], cadre), [10, -10]);
  // s'arrête au bord, sans le dépasser
  egaux(bornerDeplacement([20, 0], [100 + bord - 5, 50], cadre), [5, 0], "jusqu'au bord");
  assert.deepEqual(bornerDeplacement([0, -20], [100, 50 - bord], cadre), [0, 0]);
  // mené au-delà par la souris : revenir oui, s'éloigner non
  assert.deepEqual(bornerDeplacement([5, 3], [100 + bord + 30, 50], cadre), [0, 3]);
  assert.deepEqual(bornerDeplacement([-5, 0], [100 + bord + 30, 50], cadre), [-5, 0]);
});

test("vitesse : montée et descente en douceur, sans dépasser la cible", () => {
  assert.equal(approcher(0, 10, 0), 0);
  const suite = [0.01, 0.05, 0.1, 0.5, 2].map((s) => approcher(0, 10, s));
  assert.ok(suite.every((v, i) => v > 0 && v < 10 && (i === 0 || v > suite[i - 1])));
  assert.ok(Math.abs(approcher(0, 10, NAVIGATION.inertie) - 10 * (1 - Math.exp(-1)))
    < PRECISION);
  assert.ok(approcher(10, 0, 0.5) < 10 && approcher(10, 0, 0.5) > 0);
});
