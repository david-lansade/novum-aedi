// Ouvriers dans les bâtiments (décor, calculs : ouvriers.js) : ils vont d'un poste à l'autre en
// temps de lecture réel (arrêtés à la pause) ; aucun la nuit. Visibles quand l'intérieur l'est
// (mode « Intérieurs », première personne). Survol ou clic : « Opérateur ».
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Object3D } from "three";

import { GRAINE_DECOR, RUGOSITE_OBJETS, Z_POSE } from "./apparence.js";
import { nuitA } from "./ciel.js";
import { matrice, nomAuSurvol } from "./Decor.jsx";
import { formePieton } from "./formesVehicules.js";
import { ouvriersDesBatiments, poseOuvrier } from "./ouvriers.js";

const BALANCEMENT = 0.035; // m : la marche fait monter et descendre l'ouvrier
const MASQUE = new Object3D();
MASQUE.scale.set(0, 0, 0);
MASQUE.updateMatrix();

export default function Ouvriers({ scene, lecteur, survol }) {
  const ouvriers = useMemo(() => ouvriersDesBatiments(scene.site, GRAINE_DECOR + 7),
    [scene.site]);
  const maillage = useRef(null);
  const geometrie = useMemo(() => formePieton(), []);
  const repere = useMemo(() => new Object3D(), []);
  const horloge = useRef(0);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useFrame((_, secondes) => {
    if (!maillage.current) return;
    if (lecteur.lecture || lecteur.direct) horloge.current += secondes;
    const nuit = nuitA(lecteur.t, scene.temps);
    ouvriers.forEach((ouvrier, i) => {
      const pose = !nuit && poseOuvrier(ouvrier, horloge.current);
      maillage.current.setMatrixAt(i, pose ? matrice(repere, [pose.x, pose.y, Z_POSE
        + BALANCEMENT * Math.abs(Math.sin(Math.PI * pose.phase))], pose.angle, [1, 1, 1])
        : MASQUE.matrix);
    });
    maillage.current.instanceMatrix.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  });
  const gestion = useMemo(() => nomAuSurvol(survol, ouvriers.map(() => "Opérateur")),
    [survol, ouvriers]);
  if (!ouvriers.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, ouvriers.length]} castShadow
      frustumCulled={false} {...gestion}>
      <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
    </instancedMesh>
  );
}
