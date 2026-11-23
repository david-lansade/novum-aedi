// Chariots élévateurs (calculs : chariots.js) : garés, ils partent chercher la marchandise, la
// portent sur les fourches, reviennent et rentrent au garage, au temps simulé. Survol :
// « Chariot élévateur » et il se soulève ; clic : sélection, avec sa traçabilité.
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Matrix4, Quaternion, Vector3 } from "three";

import { RUGOSITE_OBJETS, SELECTION, SURVOL, Z_POSE } from "./apparence.js";
import { poseDuChariot } from "./chariots.js";
import { formeChariot } from "./formesVehicules.js";
import { useLevee } from "./Objets.jsx";

const AXE_Z = new Vector3(0, 0, 1);
const UNITE = new Vector3(1, 1, 1);
const adoucir = (p) => p * p * (3 - 2 * p);

/** Gestionnaires de pointeur : l'instance survolée ou cliquée désigne le chariot de même rang
 * parmi les visibles. */
function pointeur({ survol, selection }, lire) {
  return {
    onPointerMove: (evenement) => {
      evenement.stopPropagation();
      const chariot = lire()[evenement.instanceId];
      if (chariot) survol.montrer(chariot, evenement.nativeEvent.clientX,
        evenement.nativeEvent.clientY);
      document.body.style.cursor = "pointer";
    },
    onPointerOut: () => {
      survol.cacher("chariot");
      document.body.style.cursor = "";
    },
    onClick: (evenement) => {
      if (evenement.delta > SELECTION.clic) return;
      evenement.stopPropagation();
      const chariot = lire()[evenement.instanceId];
      if (chariot) selection.choisir(chariot);
    },
  };
}

export default function Chariots({ chariots, gabarits, magasins }) {
  const { lecteur, survol, trajectoires } = magasins;
  const maillage = useRef(null);
  const visibles = useRef([]);
  const geometrie = useMemo(() => formeChariot(), []);
  const outils = useMemo(() => ({ matrice: new Matrix4(), position: new Vector3(),
    rotation: new Quaternion() }), []);
  const levee = useLevee(survol);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useFrame(() => {
    if (!maillage.current) return;
    const liste = [];
    for (const chariot of chariots) {
      const pose = poseDuChariot(chariot, lecteur.t, trajectoires, gabarits);
      if (!pose) continue;
      const leve = levee.objet === chariot ? SURVOL.soulevement * adoucir(levee.valeur) : 0;
      outils.rotation.setFromAxisAngle(AXE_Z, pose.cap);
      outils.matrice.compose(outils.position.set(pose.x, pose.y, Z_POSE + leve),
        outils.rotation, UNITE);
      maillage.current.setMatrixAt(liste.length, outils.matrice);
      liste.push(chariot);
    }
    visibles.current = liste;
    maillage.current.count = liste.length;
    maillage.current.instanceMatrix.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  });
  if (!chariots.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, chariots.length]} castShadow
      receiveShadow frustumCulled={false} count={0}
      {...pointeur(magasins, () => visibles.current)}>
      <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
    </instancedMesh>
  );
}
