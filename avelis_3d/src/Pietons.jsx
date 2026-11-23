// Employés à pied (décor, calculs : pietons.js) : chacun descend de sa voiture garée au parking
// VL et va à une porte du personnel ; le soir, il en sort et rejoint sa voiture. Au temps
// simulé (accélérés avec la lecture, arrêtés à la pause). Survol ou clic : « Opérateur ».
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Object3D } from "three";

import { RUGOSITE_OBJETS, Z_POSE } from "./apparence.js";
import { matrice, nomAuSurvol } from "./Decor.jsx";
import { formePieton } from "./formesVehicules.js";
import { cheminsAPied, marchesDuJour, poseDuMarcheur } from "./pietons.js";

const CAPACITE = 60; // marcheurs à la fois, au plus
const BALANCEMENT = 0.035; // m : la marche fait monter et descendre l'employé

export default function Pietons({ scene, circulation, lecteur, survol }) {
  const chemins = useMemo(() => cheminsAPied(scene.site), [scene.site]);
  const maillage = useRef(null);
  const geometrie = useMemo(() => formePieton(), []);
  const repere = useMemo(() => new Object3D(), []);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useFrame(() => {
    if (!maillage.current) return;
    const t = lecteur.t;
    const jour = Math.floor(t / scene.temps.minutes_jour);
    let n = 0;
    for (const marcheur of marchesDuJour(circulation, chemins, jour)) {
      const pose = n < CAPACITE && poseDuMarcheur(marcheur, t);
      if (!pose) continue;
      maillage.current.setMatrixAt(n, matrice(repere, [pose.x, pose.y, Z_POSE
        + BALANCEMENT * Math.abs(Math.sin(Math.PI * pose.phase))], pose.angle, [1, 1, 1]));
      n += 1;
    }
    maillage.current.count = n;
    maillage.current.instanceMatrix.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  });
  const gestion = useMemo(() => nomAuSurvol(survol, Array(CAPACITE).fill("Opérateur")),
    [survol]);
  if (!chemins.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, CAPACITE]} castShadow
      frustumCulled={false} count={0} {...gestion}>
      <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
    </instancedMesh>
  );
}
