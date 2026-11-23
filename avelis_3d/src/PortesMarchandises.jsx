// Portes de marchandises (calculs : batiments.js, chariots.js) : un rideau à lames par porte,
// qui se lève quand une marchandise ou un chariot va passer et redescend après ; pendant qu'il
// monte ou descend, le gyrophare orange au-dessus de la porte (dehors et dedans) tourne et
// éclaire. L'ouverture se règle en temps réel (PASSAGE) d'après les passages au temps simulé.
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending, BoxGeometry, Color, Matrix4, Quaternion, SphereGeometry, Vector3,
} from "three";

import { GYROPHARE, PASSAGE } from "./apparence.js";
import { passageEntre } from "./chariots.js";
import { formeRideau, gyrophares, rideaux } from "./formesBatiments.js";

const AXE_Z = new Vector3(0, 0, 1);
const TEINTES = { allume: new Color(GYROPHARE.allume), eteint: new Color(GYROPHARE.eteint) };
const CACHE = new Vector3(0, 0, 0);
const adoucir = (p) => p * p * (3 - 2 * p);

/** Vrai si une marchandise ou un chariot passe par la porte entre les deux derniers instants
 * (avec PASSAGE.apres avant et PASSAGE.avance après), ou d'ici la fin d'une ouverture. */
function demandee(instants, avant, t, lecteur) {
  // en `duree` s réelles, la lecture avance de vitesse × duree min simulées
  const anticipation = lecteur.lecture ? lecteur.vitesse * PASSAGE.duree : 0;
  return passageEntre(instants ?? [], Math.min(avant, t) - PASSAGE.apres,
    Math.max(avant, t) + PASSAGE.avance + anticipation);
}

/** Fait avancer l'état {ouverture (0 à 1), cible, fin (s réelles)} d'une porte ; renvoie vrai
 * si le rideau bouge. */
function avancerPorte(etat, ouvrir, maintenant, secondes) {
  if (ouvrir) Object.assign(etat, { cible: 1, fin: maintenant + PASSAGE.tenue });
  else if (maintenant > etat.fin) etat.cible = 0;
  const pas = secondes / PASSAGE.duree;
  const avant = etat.ouverture;
  etat.ouverture = etat.cible > avant ? Math.min(1, avant + pas) : Math.max(0, avant - pas);
  return etat.ouverture !== avant || etat.ouverture !== etat.cible;
}

/** Matrices fixes : rideaux (haut de la porte, tournés selon le mur) et gyrophares. */
function usePlaces(portes) {
  return useMemo(() => ({
    rideaux: rideaux(portes).map(({ centre, axe }) => ({ position: new Vector3(...centre),
      rotation: new Quaternion().setFromAxisAngle(AXE_Z, axe === "y" ? Math.PI / 2 : 0) })),
    feux: gyrophares(portes).map(({ porte, position }) => ({
      rang: portes.findIndex((p) => p.id === porte), position: new Vector3(...position) })),
  }), [portes]);
}

/** Géométries : rideau, dôme du gyrophare, réflecteur qui tourne, halo. */
function useGeometries() {
  const g = useMemo(() => ({ rideau: formeRideau(),
    dome: new SphereGeometry(GYROPHARE.rayon, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2)
      .rotateX(Math.PI / 2), // le haut de la demi-sphère vers z
    reflecteur: new BoxGeometry(GYROPHARE.rayon * 1.6, GYROPHARE.rayon * 0.35,
      GYROPHARE.hauteur * 0.6),
    halo: new SphereGeometry(GYROPHARE.halo, 12, 8) }), []);
  useEffect(() => () => Object.values(g).forEach((geometrie) => geometrie.dispose()), [g]);
  return g;
}

/** Pose des rideaux et des feux à l'image courante ; `bouge[i]` : la porte i est en
 * mouvement ; `angle` : rotation du réflecteur. */
function poser(refs, places, etats, bouge, angle) {
  const m = new Matrix4();
  const q = new Quaternion();
  const echelle = new Vector3();
  places.rideaux.forEach(({ position, rotation }, i) => {
    echelle.set(1, 1, 1 - PASSAGE.rideau * adoucir(etats[i].ouverture));
    refs.rideaux.current.setMatrixAt(i, m.compose(position, rotation, echelle));
  });
  places.feux.forEach(({ rang, position }, i) => {
    const allume = bouge[rang];
    refs.domes.current.setColorAt(i, allume ? TEINTES.allume : TEINTES.eteint);
    q.setFromAxisAngle(AXE_Z, angle + i);
    const vu = allume ? echelle.set(1, 1, 1) : CACHE;
    refs.reflecteurs.current.setMatrixAt(i, m.compose(position, q, vu));
    refs.halos.current.setMatrixAt(i, m.compose(position, q, vu));
  });
  for (const cle of ["rideaux", "reflecteurs", "halos"]) {
    refs[cle].current.instanceMatrix.needsUpdate = true;
  }
  if (refs.domes.current.instanceColor) refs.domes.current.instanceColor.needsUpdate = true;
}

/** Portes de marchandises `portes` ; `passages` : Map id → instants de passage triés. */
export default function PortesMarchandises({ portes, passages, lecteur }) {
  const places = usePlaces(portes);
  const g = useGeometries();
  const refs = { rideaux: useRef(null), domes: useRef(null), reflecteurs: useRef(null),
    halos: useRef(null) };
  const memoire = useMemo(() => ({ avant: lecteur.t, horloge: 0,
    etats: portes.map(() => ({ ouverture: 0, cible: 0, fin: 0 })) }), [portes, lecteur]);
  useFrame((_, secondes) => {
    if (!refs.rideaux.current || !refs.domes.current) return;
    memoire.horloge += secondes;
    const t = lecteur.t;
    const bouge = portes.map((porte, i) => avancerPorte(memoire.etats[i],
      demandee(passages.get(porte.id), memoire.avant, t, lecteur), memoire.horloge, secondes));
    memoire.avant = t;
    poser(refs, places, memoire.etats, bouge, memoire.horloge * PASSAGE.tours * 2 * Math.PI);
  });
  if (!portes.length) return null;
  const nFeux = places.feux.length;
  return (
    <group>
      <instancedMesh ref={refs.rideaux} args={[g.rideau, undefined, portes.length]} castShadow
        receiveShadow frustumCulled={false}>
        <meshStandardMaterial vertexColors />
      </instancedMesh>
      <instancedMesh ref={(m) => { refs.domes.current = m; if (m) poserDomes(m, places); }}
        args={[g.dome, undefined, nFeux]} frustumCulled={false}>
        <meshStandardMaterial roughness={0.35} />
      </instancedMesh>
      <instancedMesh ref={refs.reflecteurs} args={[g.reflecteur, undefined, nFeux]}
        frustumCulled={false}>
        <meshBasicMaterial color={GYROPHARE.allume} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={refs.halos} args={[g.halo, undefined, nFeux]} frustumCulled={false}>
        <meshBasicMaterial color={GYROPHARE.allume} transparent opacity={0.28}
          blending={AdditiveBlending} depthWrite={false} toneMapped={false} />
      </instancedMesh>
    </group>
  );
}

/** Dômes posés une fois pour toutes (seule leur couleur change), éteints. */
function poserDomes(maillage, places) {
  const m = new Matrix4();
  places.feux.forEach(({ position }, i) => {
    maillage.setMatrixAt(i, m.makeTranslation(position.x, position.y, position.z));
    maillage.setColorAt(i, TEINTES.eteint);
  });
  maillage.instanceMatrix.needsUpdate = true;
}
