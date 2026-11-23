// Mode « flux » : traînées des chemins les plus empruntés (flux.js), d'autant plus épaisses et
// orangées que le trafic est fort, dessinées par-dessus les bâtiments : flux des marchandises de
// zone à zone, en courbes fléchées, et chemins des camions en gris. Elles montrent par exemple
// le flux en U de l'implantation proposée.
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { BoxGeometry, Color, CylinderGeometry, Object3D } from "three";

import { FLUX, Z } from "./apparence.js";
import { largeurTrainee, trainees } from "./flux.js";

const DESSUS = 20; // ordre de rendu : après les bâtiments et les objets

/** Matrices et teintes des traînées : un pavé par arête, prolongé d'une demi-largeur à chaque
 * bout pour que les arêtes se raccordent. */
function piecesDuFlux(liste) {
  const repere = new Object3D();
  const [faible, fort] = [new Color(FLUX.faible), new Color(FLUX.fort)];
  return {
    matrices: liste.map(({ a, b, part }) => {
      const largeur = largeurTrainee(part);
      repere.position.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, Z.site + FLUX.hauteur);
      repere.rotation.set(0, 0, Math.atan2(b[1] - a[1], b[0] - a[0]));
      repere.scale.set(Math.hypot(b[0] - a[0], b[1] - a[1]) + largeur, largeur, 0.05);
      repere.updateMatrix();
      return repere.matrix.clone();
    }),
    couleurs: liste.map(({ part }) => faible.clone().lerp(fort, Math.sqrt(part))),
  };
}

/** Un lot de traînées (objets, ou camions) : InstancedMesh translucide, sans test de
 * profondeur. */
function Trainees({ liste, couleur, opacite }) {
  const maillage = useRef(null);
  const geometrie = useMemo(() => new BoxGeometry(1, 1, 1), []);
  const pieces = useMemo(() => piecesDuFlux(liste), [liste]);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useLayoutEffect(() => {
    if (!maillage.current) return;
    pieces.matrices.forEach((m, i) => maillage.current.setMatrixAt(i, m));
    if (!couleur) pieces.couleurs.forEach((c, i) => maillage.current.setColorAt(i, c));
    maillage.current.instanceMatrix.needsUpdate = true;
    if (maillage.current.instanceColor) maillage.current.instanceColor.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  }, [pieces, couleur]);
  if (!liste.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, liste.length]}
      renderOrder={DESSUS + (couleur ? 0 : 1)} raycast={() => null}
      userData={{ sansOcclusion: true }}>
      <meshBasicMaterial color={couleur ?? "#ffffff"} transparent opacity={opacite}
        depthTest={false} depthWrite={false} toneMapped={false} />
    </instancedMesh>
  );
}

/** Morceaux [{a, b, part}] des courbes des flux de zone à zone. */
function morceauxDesCourbes(flux) {
  return flux.flatMap(({ points, part }) => points.slice(1).map((b, k) => ({ a: points[k], b,
    part })));
}

/** Flèches des flux de zone à zone : triangle plat sombre aux trois quarts de chaque courbe,
 * dans son sens, à l'échelle de la traînée. */
function Fleches({ flux }) {
  const maillage = useRef(null);
  const geometrie = useMemo(() => new CylinderGeometry(1, 1, 1, 3).rotateX(Math.PI / 2)
    .rotateZ(Math.PI / 2), []); // pointe vers +x
  const pieces = useMemo(() => {
    const repere = new Object3D();
    const teinte = new Color(FLUX.couleurFleche);
    return flux.map(({ points, part }) => {
      const k = Math.round(points.length * 0.75);
      const [a, b] = [points[k - 1], points[k]];
      const taille = FLUX.fleche * (0.5 + Math.sqrt(part) / 2);
      repere.position.set(b[0], b[1], Z.site + FLUX.hauteur + 0.05);
      repere.rotation.set(0, 0, Math.atan2(b[1] - a[1], b[0] - a[0]));
      repere.scale.set(taille / 2, taille / 2, 0.05);
      repere.updateMatrix();
      return [repere.matrix.clone(), teinte];
    });
  }, [flux]);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useLayoutEffect(() => {
    if (!maillage.current) return;
    pieces.forEach(([m, c], i) => {
      maillage.current.setMatrixAt(i, m);
      maillage.current.setColorAt(i, c);
    });
    maillage.current.instanceMatrix.needsUpdate = true;
    if (maillage.current.instanceColor) maillage.current.instanceColor.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  }, [pieces]);
  if (!flux.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, flux.length]}
      renderOrder={DESSUS + 2} raycast={() => null} userData={{ sansOcclusion: true }}>
      <meshBasicMaterial color="#ffffff" depthTest={false} depthWrite={false}
        toneMapped={false} transparent />
    </instancedMesh>
  );
}

/** Traînées du flux de la scène : camions en gris dessous, marchandises en couleur dessus,
 * fléchées. */
export default function Flux({ objets, site }) {
  const { objets: flux, camions } = useMemo(() => trainees(objets, site), [objets, site]);
  const morceaux = useMemo(() => morceauxDesCourbes(flux), [flux]);
  return (
    <group>
      <Trainees liste={camions} couleur={FLUX.camion} opacite={FLUX.opaciteCamion} />
      <Trainees liste={morceaux} opacite={FLUX.opacite} />
      <Fleches flux={flux} />
    </group>
  );
}
