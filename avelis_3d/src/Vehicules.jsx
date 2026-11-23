// Véhicules du décor au temps simulé (calculs : circulation.js) : voitures du personnel et des
// visiteurs sur le parking VL, voitures, camionnettes et camions de passage sur la route
// publique. Un InstancedMesh par modèle, rempli à chaque image avec les véhicules visibles à
// l'instant du lecteur. Survol : son nom (« Voiture du personnel », « Camion »…) et il se
// soulève, comme les objets de la scène.
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, Object3D } from "three";

import {
  CIRCULATION_VL, MODELES_VL, RUGOSITE_OBJETS, SURVOL, VOITURE, Z_POSE,
} from "./apparence.js";
import { vehiculesA } from "./circulation.js";
import { matrice } from "./Decor.jsx";
import { formeCamionDeRoute, formeVL } from "./formesVehicules.js";
import { useLevee } from "./Objets.jsx";

const MODELES = [...Object.keys(MODELES_VL), "camion"];
const CAPACITE = 90; // instances par modèle : plus que de places au parking et de passages
const BLANC = new Color("#ffffff");
const adoucir = (p) => p * p * (3 - 2 * p);

/** Pseudo-objet du survol d'un véhicule, le même à chaque survol (le soulèvement le suit). */
function objetDeSurvol(cache, vehicule) {
  if (!cache.has(vehicule.id)) {
    cache.set(vehicule.id, { type: "voiture", id: vehicule.id, libelle: vehicule.libelle,
      decor: true });
  }
  return cache.get(vehicule.id);
}

/** Gestionnaires de pointeur des véhicules d'un modèle : `lire()` donne le véhicule de chaque
 * instance. */
function pointeur(survol, lire, cache) {
  const montrer = (evenement) => {
    evenement.stopPropagation();
    const vehicule = lire()[evenement.instanceId];
    if (!vehicule) return;
    const { clientX, clientY } = evenement.nativeEvent;
    survol.montrer(objetDeSurvol(cache, vehicule), clientX, clientY);
    document.body.style.cursor = "pointer";
  };
  return {
    onPointerMove: montrer,
    onPointerOut: () => {
      survol.cacher("voiture");
      document.body.style.cursor = "";
    },
    onClick: montrer,
  };
}

/** Place les véhicules visibles d'un modèle ; renvoie leur liste, dans l'ordre des instances. */
function placerModele(maillage, liste, { levee, repere, teintes, camion }) {
  const items = liste.slice(0, CAPACITE);
  items.forEach(({ vehicule, pose }, i) => {
    const leve = levee.objet?.id === vehicule.id ? SURVOL.soulevement * adoucir(levee.valeur)
      : 0;
    maillage.setMatrixAt(i, matrice(repere, [pose.x, pose.y, Z_POSE + leve], pose.angle,
      [1, 1, 1]));
    maillage.setColorAt(i, camion ? BLANC : teintes[vehicule.teinte]);
  });
  maillage.count = items.length;
  maillage.instanceMatrix.needsUpdate = true;
  if (maillage.instanceColor) maillage.instanceColor.needsUpdate = true;
  maillage.computeBoundingSphere();
  return items.map((item) => item.vehicule);
}

/** Retient le maillage du modèle ; un nouveau maillage reçoit ses couleurs d'instance (que le
 * matériau lit dès son premier rendu) et ne montre rien avant la première image. */
function brancher(maillages, modele, maillage) {
  if (maillage && maillages[modele] !== maillage) {
    for (let i = 0; i < CAPACITE; i++) maillage.setColorAt(i, BLANC);
    maillage.count = 0;
  }
  maillages[modele] = maillage;
}

/** Véhicules ; `circulation` : circulation.js ; `portail.poses` reçoit les poses des voitures
 * du site (barrière du portail). */
export default function Vehicules({ circulation, gabarits, lecteur, survol, portail }) {
  const geometries = useMemo(() => Object.fromEntries(MODELES.map((m) => [m, m === "camion"
    ? formeCamionDeRoute(gabarits.camion, CIRCULATION_VL.couleurCamion)
    : formeVL(MODELES_VL[m])])), [gabarits]);
  useEffect(() => () => Object.values(geometries).forEach((g) => g.dispose()), [geometries]);
  const maillages = useRef({});
  const visibles = useRef({});
  const cache = useMemo(() => new Map(), []);
  const levee = useLevee(survol);
  const outils = useMemo(() => ({ levee, repere: new Object3D(),
    teintes: VOITURE.couleurs.map((c) => new Color(c)) }), [levee]);
  useFrame(() => {
    const liste = vehiculesA(circulation, lecteur.t);
    portail.poses = liste.filter(({ vehicule }) => vehicule.aller).map(({ pose }) => pose);
    for (const m of MODELES) {
      const maillage = maillages.current[m];
      if (!maillage) continue;
      visibles.current[m] = placerModele(maillage, liste.filter(({ vehicule }) =>
        vehicule.modele === m), { ...outils, camion: m === "camion" });
    }
  });
  return (
    <group>
      {MODELES.map((m) => (
        <instancedMesh key={m} ref={(maillage) => brancher(maillages.current, m, maillage)}
          args={[geometries[m], undefined, CAPACITE]} castShadow receiveShadow
          frustumCulled={false}
          {...pointeur(survol, () => visibles.current[m] ?? [], cache)}>
          <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
        </instancedMesh>
      ))}
    </group>
  );
}
