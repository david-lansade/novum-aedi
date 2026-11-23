// Ciel de la vue 3D (calculs : ciel.js) : fond et brouillard, lumière d'ambiance et soleil à
// ombres floues. Avec le cycle jour et nuit, ils suivent l'heure de l'horloge et la météo du
// jour (simulée, ou celle de Torcy en direct) ; pluie et neige tombent sur le site. Sans lui,
// la lumière fixe de la maquette (soleil du nord-ouest).
import {
  useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore,
} from "react";
import { useFrame } from "@react-three/fiber";
import { BoxGeometry, Object3D, OctahedronGeometry } from "three";

import { COULEURS_PLAN, METEO } from "./apparence.js";
import { RAYON_ETENDUES } from "./Camera.jsx";
import {
  adresseMeteo, ambiance, heureDuJour, jourDe, meteoOpenMeteo, meteoSimulee,
} from "./ciel.js";
import { aleatoire } from "./decor.js";

// Soleil fixe, en multiples de l'étendue du site autour de son centre (repère de three.js) ;
// `flou` : rayon du filtre des ombres, en texels de leur carte. Venu du nord-ouest, il éclaire
// la face ouest et laisse la face sud dans l'ombre (les deux faces vues depuis la caméra, au
// sud-ouest) : les ombres portées tombent vers le bas et la droite de l'écran.
const SOLEIL = { est: -0.35, hauteur: 0.75, sud: -0.45, intensite: 2.8, ombre: 0.7, carte: 4096,
  flou: 6, distance: 1.0 };
// Lumière d'ambiance fixe : forte, mais pas au point d'effacer les ombres
const CIEL = { haut: "#ffffff", bas: "#d4d8e8", intensite: 1 };
// Brouillard de la couleur du fond, en étendues du site au-delà de la cible de la caméra
const BROUILLARD = { debut: 0.45, fin: 1.3 };
const MS_PAR_MINUTE = 60000;
const GRAINE_PRECIPITATIONS = 4242;

/** Météo à l'instant t : celle de Torcy en direct si elle est connue, sinon celle du jour
 * simulé. */
export function meteoA(scene, t, directe) {
  return directe ?? meteoSimulee(scene.scenario.graine, jourDe(t, scene.temps));
}

/** Météo actuelle de Torcy en direct (jumeau numérique, `scene.direct.lieu`), relue toutes les
 * METEO.rafraichissementMin minutes ; null hors du direct, sans réseau ou cycle coupé. */
export function useMeteoDirecte(scene, actif) {
  const [meteo, changerMeteo] = useState(null);
  const lieu = scene.direct?.lieu;
  useEffect(() => {
    if (!lieu || !actif) return undefined;
    const lire = () => fetch(adresseMeteo(lieu)).then((r) => r.json())
      .then((reponse) => changerMeteo(meteoOpenMeteo(reponse))).catch(() => {});
    lire();
    const minuterie = setInterval(lire, METEO.rafraichissementMin * MS_PAR_MINUTE);
    return () => clearInterval(minuterie);
  }, [lieu?.[0], lieu?.[1], actif]); // eslint-disable-line react-hooks/exhaustive-deps
  return actif ? meteo : null;
}

/** Libellé de la météo affichée (le composant n'est redessiné que s'il change). */
export function useLibelleMeteo(scene, lecteur, directe) {
  return useSyncExternalStore(lecteur.abonner,
    () => meteoA(scene, lecteur.t, directe).libelle);
}

/** Fond, brouillard et lumières ; `cycle` : jour et nuit et météo, sinon lumière fixe. */
export default function Ciel({ cadre, scene, lecteur, cycle, directe }) {
  const cible = useMemo(() => new Object3D(), []);
  const [lumiere, hemi] = [useRef(null), useRef(null)];
  const { cx, cy, etendue } = cadre;
  const portee = etendue * SOLEIL.ombre;
  const fixe = [cx + etendue * SOLEIL.est, etendue * SOLEIL.hauteur, -cy + etendue * SOLEIL.sud];
  const rayon = etendue * RAYON_ETENDUES;
  const [debut, fin] = [rayon + etendue * BROUILLARD.debut, rayon + etendue * BROUILLARD.fin];
  useFrame(({ scene: monde }) => {
    if (!lumiere.current || !monde.fog) return;
    if (!cycle) {
      lumiere.current.position.set(...fixe);
      lumiere.current.intensity = SOLEIL.intensite;
      lumiere.current.color.set("#ffffff");
      hemi.current.color.set(CIEL.haut);
      hemi.current.groundColor.set(CIEL.bas);
      hemi.current.intensity = CIEL.intensite;
      monde.background.set(COULEURS_PLAN.fond);
      Object.assign(monde.fog, { near: debut, far: fin });
      monde.fog.color.set(COULEURS_PLAN.fond);
      return;
    }
    const a = ambiance(heureDuJour(lecteur.t, scene.temps), meteoA(scene, lecteur.t, directe));
    const [de, dn, dh] = a.direction;
    const d = etendue * SOLEIL.distance;
    lumiere.current.position.set(cx + de * d, dh * d, -cy - dn * d);
    lumiere.current.intensity = a.intensite;
    lumiere.current.color.set(a.couleur);
    hemi.current.color.set(a.ciel.haut);
    hemi.current.groundColor.set(a.ciel.bas);
    hemi.current.intensity = a.ciel.intensite;
    monde.background.set(a.fond);
    monde.fog.color.set(a.fond);
    Object.assign(monde.fog, { near: rayon + (debut - rayon) * a.brouillard,
      far: rayon + (fin - rayon) * a.brouillard });
  });
  return (
    <>
      <color attach="background" args={[COULEURS_PLAN.fond]} />
      <fog attach="fog" args={[COULEURS_PLAN.fond, debut, fin]} />
      <hemisphereLight ref={hemi} args={[CIEL.haut, CIEL.bas, CIEL.intensite]} />
      <primitive object={cible} position={[cx, 0, -cy]} />
      <directionalLight ref={lumiere} target={cible} intensity={SOLEIL.intensite} castShadow
        position={fixe} shadow-mapSize={[SOLEIL.carte, SOLEIL.carte]} shadow-bias={-0.0004}
        shadow-radius={SOLEIL.flou} shadow-camera-left={-portee} shadow-camera-right={portee}
        shadow-camera-top={portee} shadow-camera-bottom={-portee}
        shadow-camera-far={etendue * 3} />
    </>
  );
}

/** Matrices de `nombre` particules tirées dans le cadre du site, sur METEO.hauteur m. */
function particules(cadre, nombre, echelle) {
  const tirage = aleatoire(GRAINE_PRECIPITATIONS + nombre);
  const repere = new Object3D();
  const { cx, cy, etendue } = cadre;
  return Array.from({ length: nombre }, () => {
    repere.position.set(cx + (tirage() - 0.5) * etendue, cy + (tirage() - 0.5) * etendue,
      tirage() * METEO.hauteur);
    repere.scale.set(...echelle);
    repere.updateMatrix();
    return repere.matrix.clone();
  });
}

/** Champ de particules qui tombe sans fin à `vitesse` m/s : deux copies superposées, décalées
 * d'une hauteur, glissent vers le bas (rien n'est recalculé à chaque image). */
function Chute({ geometrie, matrices, vitesse, couleur, opacite, visible }) {
  const groupe = useRef(null);
  const maillages = [useRef(null), useRef(null)];
  const temps = useRef(0);
  useLayoutEffect(() => {
    for (const maillage of maillages) {
      if (!maillage.current) continue;
      matrices.forEach((m, i) => maillage.current.setMatrixAt(i, m));
      maillage.current.instanceMatrix.needsUpdate = true;
    }
  }, [matrices]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useFrame((_, secondes) => {
    if (!groupe.current) return;
    groupe.current.visible = visible;
    if (!visible) return;
    temps.current += secondes;
    groupe.current.position.z = -((temps.current * vitesse) % METEO.hauteur);
  });
  return (
    <group ref={groupe} visible={false}>
      {[0, METEO.hauteur].map((z, k) => (
        <instancedMesh key={z} ref={maillages[k]} args={[geometrie, undefined, matrices.length]}
          position-z={z} frustumCulled={false} userData={{ sansOcclusion: true }}>
          <meshBasicMaterial color={couleur} transparent opacity={opacite} depthWrite={false} />
        </instancedMesh>
      ))}
    </group>
  );
}

/** Pluie et neige sur le site (coordonnées du plan), selon la météo de l'instant. */
export function Precipitations({ cadre, scene, lecteur, cycle, directe }) {
  const jour = useSyncExternalStore(lecteur.abonner, () => jourDe(lecteur.t, scene.temps));
  const meteo = cycle ? meteoA(scene, jour * scene.temps.minutes_jour, directe) : null;
  const pluie = useMemo(() => ({ geometrie: new BoxGeometry(1, 1, 1),
    matrices: particules(cadre, METEO.gouttes, METEO.goutte) }), [cadre]);
  const neige = useMemo(() => ({ geometrie: new OctahedronGeometry(1, 0),
    matrices: particules(cadre, METEO.flocons, [METEO.flocon, METEO.flocon, METEO.flocon]) }),
  [cadre]);
  return (
    <group>
      <Chute {...pluie} vitesse={METEO.vitessePluie} couleur={METEO.couleurPluie}
        opacite={METEO.opacitePluie} visible={Boolean(meteo?.pluie)} />
      <Chute {...neige} vitesse={METEO.vitesseNeige} couleur={METEO.couleurNeige} opacite={0.9}
        visible={Boolean(meteo?.neige)} />
    </group>
  );
}
