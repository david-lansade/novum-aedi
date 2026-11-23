// Caméra orthographique isométrique : projection parallèle, comme une maquette vue d'en haut.
// Souris : clic gauche pour tourner, clic droit pour déplacer, molette pour zoomer vers le
// pointeur. Clavier (clavier.js) : Z Q S D ou les flèches pour se déplacer, A et E pour tourner,
// Maj pour aller plus vite. Les commandes (CommandesVue.jsx) zooment, tournent d'un quart de
// tour, recentrent ou passent en vue de dessus, par une courte transition. Calculs du cadrage :
// cadrage.js.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Vector3 } from "three";

import { NAVIGATION } from "./apparence.js";
import {
  MARGES_CARTES, REMPLISSAGE, VUE_ENSEMBLE, cadrer, directionCamera, ecartAngulaire, orientation,
  pointsDuSite, pointsVueEnsemble,
} from "./cadrage.js";
import {
  TOUCHES, actionsDe, approcher, bornerDeplacement, directionAuSol, sensRotation,
  toucheReservee, vitesseAuSol,
} from "./clavier.js";

const DEGRE = Math.PI / 180;
const VUE_ISO = VUE_ENSEMBLE; // au sud-ouest, 35° au-dessus du sol (cadrage.js)
const VUE_DESSUS = { azimut: -90 * DEGRE, elevation: 89.8 * DEGRE }; // le nord reste en haut
const QUART_DE_TOUR = 90 * DEGRE; // la vue reste isométrique
const FACTEUR_ZOOM = 1.5; // par clic sur + ou −
const ZOOM_MAX = 60; // px par mètre
const ZOOM_MIN_ENSEMBLE = 0.5; // au plus loin, en part du zoom de la vue d'ensemble
const ELEVATION_MIN = 12 * DEGRE;
const DUREE_TRANSITION_S = 0.6;
const MARGES = MARGES_CARTES; // place des cartes de l'interface (cadrage.js, style.css)
const ZOOM_VISEE = 3; // en multiples du zoom de la vue d'ensemble, au moins, pour montrer un objet
export const RAYON_ETENDUES = 2; // distance de la caméra à sa cible, en étendues du site
const AXE_VERTICAL = new Vector3(0, 1, 0); // repère de three.js
const ELAN_NUL = 1e-3; // m/s et rad/s : en deçà, la vue est arrêtée

const versThree = ([x, y, z]) => [x, z, -y]; // plan → three.js (y vers le haut, z vers le sud)
const versPlan = ({ x, y, z }) => [x, -z, y];
const adoucir = (p) => p * p * (3 - 2 * p); // départ et arrivée lents

/** État {cible, azimut, elevation, rayon, zoom} interpolé de `de` à `vers` (p de 0 à 1). */
function interpoler(de, vers, p) {
  return {
    cible: de.cible.map((c, k) => c + (vers.cible[k] - c) * p),
    azimut: de.azimut + ecartAngulaire(de.azimut, vers.azimut) * p,
    elevation: de.elevation + (vers.elevation - de.elevation) * p,
    rayon: de.rayon + (vers.rayon - de.rayon) * p,
    zoom: de.zoom * (vers.zoom / de.zoom) ** p, // zoom géométrique : vitesse apparente constante
  };
}

/** Lecture et écriture de l'état de la caméra, et transitions animées vers un nouvel état. */
function useTransitions(camera, controles) {
  const transition = useRef(null);
  const lire = useCallback(() => {
    const cible = versPlan(controles.current.target);
    return { cible, ...orientation(versPlan(camera.position), cible), zoom: camera.zoom };
  }, [camera, controles]);
  const ecrire = useCallback(({ cible, azimut, elevation, rayon, zoom }) => {
    const direction = directionCamera(azimut, elevation);
    camera.position.set(...versThree(cible.map((c, k) => c + rayon * direction[k])));
    controles.current.target.set(...versThree(cible));
    camera.zoom = zoom;
    camera.updateProjectionMatrix();
    controles.current.update();
  }, [camera, controles]);
  const allerVers = useCallback((vers) => {
    const de = lire();
    transition.current = { de, vers: { ...de, ...vers }, ecoule: 0 };
    controles.current.enabled = false;
  }, [controles, lire]);
  const interrompre = useCallback(() => {
    if (!transition.current) return;
    transition.current = null;
    controles.current.enabled = true;
  }, [controles]);
  useFrame((_, secondes) => {
    const enCours = transition.current;
    if (!enCours) return;
    enCours.ecoule += secondes;
    const p = Math.min(1, enCours.ecoule / DUREE_TRANSITION_S);
    ecrire(interpoler(enCours.de, enCours.vers, adoucir(p)));
    if (p < 1) return;
    transition.current = null;
    controles.current.enabled = true;
  });
  return { lire, ecrire, allerVers, interrompre };
}

/** Touches enfoncées (event.code) qui ont une action, sauf celles qui reviennent à l'élément
 * qui a le focus ou vont avec Ctrl, Alt ou Cmd ; toutes relâchées si la fenêtre perd le focus. */
export function useTouches() {
  const touches = useMemo(() => new Set(), []);
  useEffect(() => {
    const appui = (evenement) => {
      const { code, ctrlKey, altKey, metaKey, target } = evenement;
      if (!TOUCHES[code] || ctrlKey || altKey || metaKey || toucheReservee(code, target)) return;
      touches.add(code);
      if (TOUCHES[code] !== "rapide") evenement.preventDefault(); // pas de défilement
    };
    const relache = (evenement) => touches.delete(evenement.code);
    const vider = () => touches.clear();
    window.addEventListener("keydown", appui);
    window.addEventListener("keyup", relache);
    window.addEventListener("blur", vider);
    return () => {
      window.removeEventListener("keydown", appui);
      window.removeEventListener("keyup", relache);
      window.removeEventListener("blur", vider);
    };
  }, [touches]);
  return touches;
}

/** Déplace la cible et la caméra de [dx, dy] m au sol (plan), puis tourne la caméra de `angle`
 * rad autour de la cible (azimut croissant). */
function deplacer(camera, controles, [dx, dy], angle) {
  const decalage = new Vector3(dx, 0, -dy); // plan → three.js
  controles.target.add(decalage);
  camera.position.add(decalage);
  if (angle !== 0) {
    const relatif = camera.position.clone().sub(controles.target);
    camera.position.copy(controles.target).add(relatif.applyAxisAngle(AXE_VERTICAL, angle));
  }
  controles.update();
}

/** Déplacement et rotation de la vue au clavier (clavier.js) : vitesse qui s'établit et retombe
 * en douceur, cible gardée près du site ; une touche interrompt la transition en cours et marque
 * la vue comme touchée. */
function useClavier({ camera, controles, cadre, interrompre, intacte }) {
  const touches = useTouches();
  const elan = useMemo(() => ({ x: 0, y: 0, rotation: 0 }), []);
  const largeur = useThree((etat) => etat.size.width);
  useFrame((_, secondes) => {
    const actions = actionsDe(touches);
    const cible = versPlan(controles.current.target);
    const { azimut } = orientation(versPlan(camera.position), cible);
    const vitesse = vitesseAuSol(largeur, camera.zoom, actions.has("rapide"));
    const [dx, dy] = directionAuSol(actions, azimut);
    elan.x = approcher(elan.x, dx * vitesse, secondes);
    elan.y = approcher(elan.y, dy * vitesse, secondes);
    elan.rotation = approcher(elan.rotation, sensRotation(actions) * NAVIGATION.rotation,
      secondes);
    if (Math.hypot(elan.x, elan.y) < ELAN_NUL && Math.abs(elan.rotation) < ELAN_NUL) {
      Object.assign(elan, { x: 0, y: 0, rotation: 0 });
      return;
    }
    if (actions.size > 0) {
      interrompre();
      intacte.current = false;
    }
    deplacer(camera, controles.current, bornerDeplacement([elan.x * secondes,
      elan.y * secondes], cible, cadre), elan.rotation * secondes);
  });
}

/** Cadrages {ensemble, dessus} pour la taille actuelle de la toile : la vue d'ensemble sur les
 * bâtiments et le chemin des camions, la vue de dessus sur le foncier entier. */
function useCadrages(site, cadre) {
  const { width: largeur, height: hauteur } = useThree((etat) => etat.size);
  return useMemo(() => {
    const rayon = cadre.etendue * RAYON_ETENDUES;
    const cadrage = (vue, points) => ({ ...vue, rayon, ...cadrer({ points, ...vue, largeur,
      hauteur, marges: MARGES, rayon, remplissage: REMPLISSAGE }) });
    return { ensemble: cadrage(VUE_ISO, pointsVueEnsemble(site)),
      dessus: cadrage(VUE_DESSUS, pointsDuSite(site)) };
  }, [site, cadre, largeur, hauteur]);
}

/** Branche les commandes de la vue ; toutes, sauf « recentrer », marquent la vue comme touchée. */
function brancherCommandes(commandes, { lire, allerVers, cadrages, intacte }) {
  const { ensemble, dessus } = cadrages;
  const borner = (zoom) => Math.min(ZOOM_MAX, Math.max(ensemble.zoom * ZOOM_MIN_ENSEMBLE, zoom));
  const toucher = (action) => (...args) => {
    intacte.current = false;
    action(...args);
  };
  commandes.zoomer = toucher((sens) => allerVers({ zoom: borner(lire().zoom
    * FACTEUR_ZOOM ** sens) }));
  commandes.tourner = toucher((sens) => allerVers({ azimut: lire().azimut
    + sens * QUART_DE_TOUR }));
  commandes.vueDessus = toucher(() => allerVers(dessus));
  commandes.viser = toucher((x, y) => allerVers({ cible: [x, y, 0],
    zoom: borner(Math.max(lire().zoom, ensemble.zoom * ZOOM_VISEE)) }));
  commandes.recentrer = () => {
    intacte.current = true;
    allerVers(ensemble);
  };
}

/** Contrôles orbitaux et cadrages ; `commandes` reçoit zoomer, tourner, recentrer, vueDessus
 * et viser (centrer la vue sur un point du plan).
 * Tant que l'utilisateur n'a pas bougé la vue, elle se recadre si la fenêtre change de taille. */
export default function Camera({ site, cadre, commandes }) {
  const controles = useRef(null);
  const intacte = useRef(true);
  const camera = useThree((etat) => etat.camera);
  const { lire, ecrire, allerVers, interrompre } = useTransitions(camera, controles);
  const cadrages = useCadrages(site, cadre);
  useClavier({ camera, controles, cadre, interrompre, intacte });
  useLayoutEffect(() => {
    if (intacte.current) ecrire(cadrages.ensemble);
  }, [cadrages, ecrire]);
  useEffect(() => {
    brancherCommandes(commandes, { lire, allerVers, cadrages, intacte });
  }, [commandes, lire, allerVers, cadrages]);
  return (
    <OrbitControls ref={controles} makeDefault enableDamping zoomToCursor
      screenSpacePanning={false} maxPolarAngle={Math.PI / 2 - ELEVATION_MIN}
      minZoom={cadrages.ensemble.zoom * ZOOM_MIN_ENSEMBLE} maxZoom={ZOOM_MAX}
      onStart={() => { intacte.current = false; }} />
  );
}
