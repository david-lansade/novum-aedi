// Ciel de la vue 3D : cycle jour et nuit, réglé sur l'heure affichée par l'horloge, et météo
// légère (nuages, pluie, neige, brume). En relecture, la météo de chaque jour simulé est tirée à
// graine fixe ; en direct (jumeau numérique), elle vient de la météo actuelle de Torcy
// (api.open-meteo.com, coordonnées du site seules). Décor : ne représente aucune donnée.
import { CIEL_JOUR, METEO } from "./apparence.js";
import { aleatoire } from "./decor.js";

const MINUTES_PAR_HEURE = 60;
const DEGRE = Math.PI / 180;

/** Heure décimale (0 à 24) de l'horloge à l'instant t (même calcul que donnees.horloge). */
export function heureDuJour(t, temps) {
  const jour = Math.floor(t / temps.minutes_jour);
  const minutes = temps.heure_ouverture * MINUTES_PAR_HEURE + t - jour * temps.minutes_jour;
  return (minutes / MINUTES_PAR_HEURE) % 24;
}

/** Vrai la nuit (soleil couché, de CIEL_JOUR.coucher à CIEL_JOUR.lever) : ni ouvriers ni
 * opérateurs à pied, parking VL presque vide. */
export function estNuit(h) {
  return h >= CIEL_JOUR.coucher || h < CIEL_JOUR.lever;
}

/** Vrai la nuit à l'instant t de la scène. */
export function nuitA(t, temps) {
  return estNuit(heureDuJour(t, temps));
}

/** Numéro (0, 1…) du jour simulé de l'instant t. */
export function jourDe(t, temps) {
  return Math.floor(t / temps.minutes_jour);
}

/** Lissage d'Hermite de 0 (x ≤ a) à 1 (x ≥ b). */
function lisse(a, b, x) {
  const k = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return k * k * (3 - 2 * k);
}

/** Soleil à l'heure h : {elevation, azimut} en radians (azimut depuis le nord, vers l'est) ;
 * levé à l'est à CIEL_JOUR.lever, au sud à midi, couché à l'ouest à CIEL_JOUR.coucher ; sous
 * l'horizon la nuit (élévation négative). */
export function soleil(h) {
  const { lever, coucher, elevationMax } = CIEL_JOUR;
  const k = (h - lever) / (coucher - lever); // 0 au lever, 1 au coucher
  const elevation = elevationMax * DEGRE * Math.sin(Math.PI * k);
  return { elevation: k >= 0 && k <= 1 ? elevation : -Math.abs(elevation) - DEGRE,
    azimut: (90 + 180 * Math.max(0, Math.min(1, k))) * DEGRE };
}

/** Mélange de deux couleurs « #rrggbb » (k = 0 : a, 1 : b), en « #rrggbb ». */
export function melange(a, b, k) {
  const canaux = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const [ca, cb] = [canaux(a), canaux(b)];
  return `#${ca.map((v, i) => Math.round(v + (cb[i] - v) * k).toString(16).padStart(2, "0"))
    .join("")}`;
}

/** Ambiance à l'heure h sous la `meteo` : {jour (0 nuit à 1 jour), direction [est, nord, haut]
 * de la lumière principale (soleil, ou lune la nuit), intensite, couleur, ciel {haut, bas,
 * intensite}, fond (ciel et brouillard), brouillard (facteur de distance, < 1 : plus près)}. */
export function ambiance(h, meteo) {
  const { elevation, azimut } = soleil(h);
  const jour = lisse(-6 * DEGRE, 6 * DEGRE, elevation);
  const bas = 1 - lisse(0, CIEL_JOUR.hauteurDoree * DEGRE, elevation); // soleil bas : doré
  const couvert = meteo.nuages;
  const lune = elevation <= 0;
  const [el, az] = lune ? [CIEL_JOUR.lune.elevation * DEGRE, CIEL_JOUR.lune.azimut * DEGRE]
    : [Math.max(elevation, 2 * DEGRE), azimut];
  const direction = [Math.cos(el) * Math.sin(az), Math.cos(el) * Math.cos(az), Math.sin(el)];
  const soleilFort = CIEL_JOUR.intensite * lisse(0, 8 * DEGRE, elevation)
    * (1 - METEO.ombreNuages * couvert);
  const intensite = lune ? CIEL_JOUR.lune.intensite * (1 - jour) : soleilFort;
  const fondJour = melange(melange(CIEL_JOUR.fond, CIEL_JOUR.fondCouvert, couvert),
    CIEL_JOUR.fondDore, bas * jour * (1 - couvert));
  return { jour, direction, intensite,
    couleur: lune ? CIEL_JOUR.lune.couleur : melange("#ffffff", CIEL_JOUR.soleilDore, bas),
    ciel: { haut: melange(CIEL_JOUR.nuit.haut, "#ffffff", jour),
      bas: melange(CIEL_JOUR.nuit.bas, CIEL_JOUR.basJour, jour),
      intensite: CIEL_JOUR.nuit.intensite + (1 - CIEL_JOUR.nuit.intensite) * jour },
    fond: melange(CIEL_JOUR.nuit.fond, fondJour, jour),
    brouillard: 1 - METEO.brumeProche * meteo.brume };
}

/** Météo {type, libelle, nuages, pluie, neige, brume} (intensités de 0 à 1) d'un type. */
function meteoDuType(type, libelle = METEO.types[type].libelle) {
  return { type, libelle, ...METEO.types[type].effets };
}

/** Météo du jour simulé `jour`, tirée à graine fixe parmi METEO.types (selon leur poids). */
export function meteoSimulee(graine, jour) {
  const base = Number.isFinite(graine) ? graine : 0; // jumeau : pas de graine
  const tirage = aleatoire(base * METEO.multiplicateur + jour);
  const types = Object.entries(METEO.types);
  let reste = tirage() * types.reduce((somme, [, t]) => somme + t.poids, 0);
  for (const [type, { poids }] of types) {
    reste -= poids;
    if (reste < 0) return meteoDuType(type);
  }
  return meteoDuType(types[0][0]);
}

/** Type de météo d'un code WMO d'Open-Meteo et de la couverture nuageuse (%). */
function typeDuCode(code, couverture) {
  if (code >= 71 && code <= 77) return "neige";
  if (code === 85 || code === 86) return "neige";
  if (code >= 51 && code <= 67) return "pluie";
  if (code >= 80) return "pluie";
  if (code === 45 || code === 48) return "brume";
  return couverture >= METEO.seuilNuageux ? "nuageux" : "clair";
}

/** Météo de la réponse d'Open-Meteo ({current: {weather_code, cloud_cover, temperature_2m}}),
 * libellée « Torcy en direct : … » ; null si la réponse est incomplète. */
export function meteoOpenMeteo(reponse) {
  const actuel = reponse?.current;
  if (!actuel || !Number.isFinite(actuel.weather_code)) return null;
  const couverture = Number.isFinite(actuel.cloud_cover) ? actuel.cloud_cover : 0;
  const type = typeDuCode(actuel.weather_code, couverture);
  const temperature = Number.isFinite(actuel.temperature_2m)
    ? `, ${Math.round(actuel.temperature_2m)} °C` : "";
  const meteo = meteoDuType(type, `Torcy en direct : ${METEO.types[type].libelle.toLowerCase()}`
    + temperature);
  return { ...meteo, nuages: Math.max(meteo.nuages, couverture / 100) };
}

/** Adresse de la météo actuelle d'Open-Meteo au lieu [latitude, longitude]. */
export function adresseMeteo([latitude, longitude]) {
  return `${METEO.adresse}?latitude=${latitude}&longitude=${longitude}`
    + "&current=weather_code,cloud_cover,temperature_2m";
}
