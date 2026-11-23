// Textures dessinées au chargement dans un canevas (aucune image à télécharger) : relief de la
// tôle nervurée, planche des numéros de quais, emblème générique des bâtiments.
import { CanvasTexture, RepeatWrapping, SRGBColorSpace } from "three";

import { COULEURS_BATIMENT, COULEURS_PLAN, EMBLEME, PALETTE } from "./apparence.js";

const PERIODE_PX = 64; // une nervure de la tôle
// Profil trapézoïdal d'une nervure, en part de la période : creux, montée, plat haut, descente
const PROFIL = { montee: 0.36, haut: 0.5, descente: 0.86 };
const INCLINAISON = 0.85; // rad : pente des flancs de la nervure dans la carte de normales
const CASE_PX = 128; // case de la planche des numéros
const EMBLEME_PX = 256;
const POLICE = '"Segoe UI", system-ui, sans-serif';

/** Canevas de `largeur` × `hauteur` px et son contexte de dessin. */
function canevas(largeur, hauteur) {
  const element = document.createElement("canvas");
  element.width = largeur;
  element.height = hauteur;
  return [element, element.getContext("2d")];
}

/** Carte de normales de la tôle nervurée : nervures verticales (selon v), répétées. */
export function textureTole() {
  const [element, contexte] = canevas(PERIODE_PX, 4);
  const image = contexte.createImageData(PERIODE_PX, 4);
  for (let i = 0; i < PERIODE_PX; i++) {
    const p = (i + 0.5) / PERIODE_PX;
    const flanc = p >= PROFIL.montee && p < PROFIL.haut ? 1 : p >= PROFIL.descente ? -1 : 0;
    const [nx, nz] = [-Math.sin(flanc * INCLINAISON), Math.cos(flanc * INCLINAISON)];
    for (let j = 0; j < 4; j++) {
      image.data.set([(nx * 0.5 + 0.5) * 255, 128, (nz * 0.5 + 0.5) * 255, 255],
        (j * PERIODE_PX + i) * 4);
    }
  }
  contexte.putImageData(image, 0, 0);
  const texture = new CanvasTexture(element);
  texture.wrapS = RepeatWrapping;
  texture.wrapT = RepeatWrapping;
  return texture;
}

/** Rectangle aux coins arrondis de rayon r. */
function arrondi(contexte, x, y, largeur, hauteur, r) {
  contexte.beginPath();
  contexte.roundRect(x, y, largeur, hauteur, r);
  contexte.fill();
}

/** Planche des numéros de quais 1 à `nombre` : rangée du haut, plaques blanches à chiffres
 * violets ; rangée du bas, chiffres peints au sol (fond transparent). */
export function plancheNumeros(nombre) {
  const [element, contexte] = canevas(CASE_PX * Math.max(1, nombre), CASE_PX * 2);
  contexte.textAlign = "center";
  contexte.textBaseline = "middle";
  for (let i = 0; i < nombre; i++) {
    const x = i * CASE_PX;
    contexte.fillStyle = COULEURS_BATIMENT.plaque;
    arrondi(contexte, x + 4, 4, CASE_PX - 8, CASE_PX - 8, 14);
    contexte.fillStyle = COULEURS_BATIMENT.numero;
    contexte.font = `700 ${CASE_PX * 0.62}px ${POLICE}`;
    contexte.fillText(String(i + 1), x + CASE_PX / 2, CASE_PX * 0.54);
    contexte.fillStyle = COULEURS_PLAN.ligneZone;
    contexte.font = `700 ${CASE_PX * 0.8}px ${POLICE}`;
    contexte.fillText(String(i + 1), x + CASE_PX / 2, CASE_PX * 1.55);
  }
  const texture = new CanvasTexture(element);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

/** Logo Avelis : pictogramme (carré violet arrondi, « A » blanc incliné barré d'une coupe)
 * suivi du nom « Avelis » en violet, sur fond transparent (découpé par alphaTest). Rapport
 * largeur / hauteur : EMBLEME.rapport. */
export function textureEmbleme() {
  const [l, h] = [Math.round(EMBLEME_PX * EMBLEME.rapport), EMBLEME_PX];
  const [element, contexte] = canevas(l, h);
  contexte.fillStyle = PALETTE.violet;
  arrondi(contexte, 0, h * 0.08, h * 0.84, h * 0.84, h * 0.16);
  contexte.textAlign = "center";
  contexte.textBaseline = "alphabetic";
  contexte.fillStyle = PALETTE.blanc;
  contexte.font = `italic 900 ${h * 0.78}px ${POLICE}`;
  contexte.fillText("A", h * 0.44, h * 0.8);
  contexte.strokeStyle = PALETTE.violet; // coupe en biais à travers le « A »
  contexte.lineWidth = h * 0.07;
  contexte.beginPath();
  contexte.moveTo(h * 0.12, h * 0.62);
  contexte.lineTo(h * 0.8, h * 0.3);
  contexte.stroke();
  contexte.textAlign = "left";
  contexte.fillStyle = PALETTE.violet;
  contexte.font = `italic 800 ${h * 0.82}px ${POLICE}`;
  contexte.fillText("Avelis", h * 1.0, h * 0.8, l - h * 1.05);
  const texture = new CanvasTexture(element);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}
