// Vue à la première personne : caméra en perspective à hauteur d'yeux, à la place de la caméra
// isométrique (Camera.jsx). Z Q S D ou les flèches pour marcher (clavier.js), A et E pour
// tourner, Maj pour aller plus vite ; glisser avec la souris pour regarder autour. On part
// juste derrière le portail, tourné vers le centre du site ; on ne s'éloigne pas du site
// (NAVIGATION.bord). Les murs ne retiennent pas : on entre dans les bâtiments en les
// traversant. « Recentrer » ramène au départ.
import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";

import { NAVIGATION, PREMIERE_PERSONNE, Z_POSE } from "./apparence.js";
import { RAYON_ETENDUES, useTouches } from "./Camera.jsx";
import { actionsDe, approcher, directionDeMarche, sensRotation } from "./clavier.js";

const DEGRE = Math.PI / 180;
const ACTIONS_COMMANDES = ["zoomer", "tourner", "vueDessus", "viser"]; // sans effet ici

/** Départ {x, y, lacet, tangage} : PREMIERE_PERSONNE.recul m après le portail, vers le centre
 * du site (au centre s'il n'y a pas de portail). */
export function departPremierePersonne(site, { cx, cy }) {
  if (!site.portail) return { x: cx, y: cy, lacet: Math.PI / 2, tangage: 0 };
  const [px, py] = site.portail;
  const distance = Math.hypot(cx - px, cy - py) || 1;
  const [ux, uy] = [(cx - px) / distance, (cy - py) / distance];
  return { x: px + ux * PREMIERE_PERSONNE.recul, y: py + uy * PREMIERE_PERSONNE.recul,
    lacet: Math.atan2(uy, ux), tangage: 0 };
}

/** Regard à la souris : glisser (bouton enfoncé) tourne la tête. */
function useRegard(element, regard) {
  useEffect(() => {
    let precedent = null;
    const appui = (e) => { precedent = [e.clientX, e.clientY]; };
    const fin = () => { precedent = null; };
    const mouvement = (e) => {
      if (!precedent) return;
      const { sensibilite, tangageMax } = PREMIERE_PERSONNE;
      regard.lacet -= (e.clientX - precedent[0]) * sensibilite;
      regard.tangage = Math.max(-tangageMax * DEGRE, Math.min(tangageMax * DEGRE,
        regard.tangage - (e.clientY - precedent[1]) * sensibilite));
      precedent = [e.clientX, e.clientY];
    };
    element.addEventListener("pointerdown", appui);
    window.addEventListener("pointermove", mouvement);
    window.addEventListener("pointerup", fin);
    return () => {
      element.removeEventListener("pointerdown", appui);
      window.removeEventListener("pointermove", mouvement);
      window.removeEventListener("pointerup", fin);
    };
  }, [element, regard]);
}

/** Les commandes de la vue isométrique n'ont pas d'effet ; « recentrer » ramène au départ.
 * Camera.jsx les rebranche quand elle revient. `maquette.premiere` montre l'intérieur des
 * bâtiments (racks, engins, ouvriers) et le dedans des murs. */
function useCommandes(commandes, maquette, regard, depart) {
  useEffect(() => {
    for (const action of ACTIONS_COMMANDES) commandes[action] = () => {};
    commandes.recentrer = () => Object.assign(regard, depart, { elanX: 0, elanY: 0 });
    maquette.premiere = true;
    return () => { maquette.premiere = false; };
  }, [commandes, maquette, regard, depart]);
}

export default function PremierePersonne({ site, cadre, commandes, maquette }) {
  const camera = useRef(null);
  const element = useThree((etat) => etat.gl.domElement);
  const touches = useTouches();
  const depart = useMemo(() => departPremierePersonne(site, cadre), [site, cadre]);
  const regard = useMemo(() => ({ ...depart, elanX: 0, elanY: 0, rotation: 0 }), [depart]);
  useRegard(element, regard);
  useCommandes(commandes, maquette, regard, depart);
  useFrame((_, secondes) => {
    if (!camera.current) return;
    const actions = actionsDe(touches);
    const { vitesse, rapide, rotation, yeux } = PREMIERE_PERSONNE;
    regard.rotation = approcher(regard.rotation, sensRotation(actions) * rotation, secondes);
    regard.lacet -= regard.rotation * secondes;
    const v = vitesse * (actions.has("rapide") ? rapide : 1);
    const [dx, dy] = directionDeMarche(actions, regard.lacet);
    regard.elanX = approcher(regard.elanX, dx * v, secondes);
    regard.elanY = approcher(regard.elanY, dy * v, secondes);
    const bord = NAVIGATION.bord * cadre.etendue;
    regard.x = Math.max(cadre.cx - bord, Math.min(cadre.cx + bord, regard.x
      + regard.elanX * secondes));
    regard.y = Math.max(cadre.cy - bord, Math.min(cadre.cy + bord, regard.y
      + regard.elanY * secondes));
    const z = Z_POSE + yeux;
    const c = Math.cos(regard.tangage);
    camera.current.position.set(regard.x, z, -regard.y); // plan → three.js
    camera.current.lookAt(regard.x + c * Math.cos(regard.lacet), z + Math.sin(regard.tangage),
      -(regard.y + c * Math.sin(regard.lacet)));
  });
  return (
    <PerspectiveCamera ref={camera} makeDefault fov={PREMIERE_PERSONNE.champ}
      near={PREMIERE_PERSONNE.proche} far={cadre.etendue * RAYON_ETENDUES * 3} />
  );
}
