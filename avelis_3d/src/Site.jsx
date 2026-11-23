// Plan du site en relief : sol, foncier, routes et leurs marquages, portail, quais, dalles des
// zones et repères (les noms sont dans Etiquettes.jsx, les bâtiments dans Batiments.jsx).
// Coordonnées du plan (x vers l'est, y vers le nord, z vers le haut, en mètres) : le groupe
// parent les tourne dans le repère de three.js.
import { useLayoutEffect, useMemo, useRef } from "react";
import { MeshStandardMaterial, Object3D, Shape, Vector2 } from "three";

import {
  BORDURE, COULEURS_PLAN, ECHELLE, EPAISSEUR_SOL, EPAISSEUR_TRACE, LARGEUR_ROUTE_PUBLIQUE,
  LIGNE_ZONE, NORD, PARKING_VL, QUAI, TIRETS_ROUTE, Z,
} from "./apparence.js";
import { portesDeQuai } from "./batiments.js";
import { lignesDuParkingPl, placesDuParkingVl } from "./decor.js";
import { fermer, pointLePlusProche, rectangle, tirets, troncons } from "./traces.js";

const TAILLE_SOL = 6000; // m : le sol déborde de l'écran même au zoom le plus éloigné
const SEGMENTS_DISQUE = 32;
const DESSUS_SOL = EPAISSEUR_SOL / 2; // face supérieure d'une dalle, au-dessus de son altitude

/** Bandes plates posées à l'altitude z (traces.js), en un seul InstancedMesh. */
function Bandes({ bandes, largeur, couleur, z }) {
  const maillage = useRef(null);
  useLayoutEffect(() => {
    const repere = new Object3D();
    bandes.forEach(({ x, y, longueur, angle }, i) => {
      repere.position.set(x, y, z + EPAISSEUR_TRACE / 2);
      repere.rotation.set(0, 0, angle);
      repere.scale.set(longueur, largeur, EPAISSEUR_TRACE);
      repere.updateMatrix();
      maillage.current.setMatrixAt(i, repere.matrix);
    });
    maillage.current.instanceMatrix.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  }, [bandes, largeur, z]);
  return (
    <instancedMesh ref={maillage} args={[undefined, undefined, bandes.length]} receiveShadow>
      <boxGeometry />
      <meshStandardMaterial color={couleur} />
    </instancedMesh>
  );
}

/** Contour du foncier, bordé d'un trait ; l'extension non utilisée est plus pâle, en tirets. */
function Contour({ contour }) {
  const forme = useMemo(() => new Shape(contour.points.map(([x, y]) => new Vector2(x, y))),
    [contour]);
  const bord = useMemo(() => {
    const ligne = fermer(contour.points);
    return contour.utilise ? troncons(ligne) : tirets(ligne, BORDURE.trait, BORDURE.vide);
  }, [contour]);
  return (
    <group>
      <mesh position-z={Z.site} receiveShadow>
        <shapeGeometry args={[forme]} />
        <meshStandardMaterial color={contour.utilise ? COULEURS_PLAN.site
          : COULEURS_PLAN.extensionLibre} />
      </mesh>
      <Bandes bandes={bord} largeur={BORDURE.largeur} couleur={COULEURS_PLAN.bordure}
        z={Z.site} />
    </group>
  );
}

/** Bande de largeur constante le long d'une polyligne (tronçons et jonctions arrondies). */
function Ruban({ points, largeur, couleur, z }) {
  const materiau = useMemo(() => new MeshStandardMaterial({ color: couleur }), [couleur]);
  return (
    <group>
      {troncons(points).map((t, i) => (
        <mesh key={i} position={[t.x, t.y, z]} rotation-z={t.angle} material={materiau}
          receiveShadow>
          <boxGeometry args={[t.longueur, largeur, EPAISSEUR_SOL]} />
        </mesh>
      ))}
      {points.map(([x, y], i) => (
        <mesh key={`j${i}`} position={[x, y, z]} rotation-x={Math.PI / 2} material={materiau}
          receiveShadow>
          <cylinderGeometry args={[largeur / 2, largeur / 2, EPAISSEUR_SOL, SEGMENTS_DISQUE]} />
        </mesh>
      ))}
    </group>
  );
}

/** Accès au portail depuis la route publique : rue publique s'il passe par plusieurs points
 * (implantation actuelle : Rue Alain Bombard), sinon bout de voirie. */
function Acces({ site }) {
  const points = useMemo(() => [pointLePlusProche(site.route_publique, site.acces[0]),
    ...site.acces], [site]);
  const rue = site.acces.length > 1;
  return <Ruban points={points} largeur={site.largeur_voirie}
    couleur={rue ? COULEURS_PLAN.routePublique : COULEURS_PLAN.voirie}
    z={rue ? Z.routePublique : Z.voirie} />;
}

/** Parking des véhicules légers : dalle, voie d'accès et lignes blanches des places (les
 * voitures sont dans Decor.jsx). */
function ParkingVl({ parking }) {
  const lignes = useMemo(() => placesDuParkingVl(parking).lignes.flatMap((l) => troncons(l)),
    [parking]);
  const { x, y, largeur, profondeur } = parking;
  return (
    <group>
      <Ruban points={parking.voie} largeur={PARKING_VL.voie} couleur={COULEURS_PLAN.voirie}
        z={Z.voirie} />
      <mesh position={[x + largeur / 2, y + profondeur / 2, Z.voirie]} receiveShadow>
        <boxGeometry args={[largeur, profondeur, EPAISSEUR_SOL]} />
        <meshStandardMaterial color={COULEURS_PLAN.parkingVl} />
      </mesh>
      <Bandes bandes={lignes} largeur={PARKING_VL.ligne} couleur={COULEURS_PLAN.marquage}
        z={Z.voirie + DESSUS_SOL} />
    </group>
  );
}

/** Route publique, voirie poids lourds, bretelles et voie du parking VL, avec leurs tirets
 * blancs ; accès au portail, aire de retournement, parking VL (le portail est dans Decor.jsx). */
function Voiries({ site }) {
  const marquages = useMemo(() => [[site.route_publique], [site.voirie, ...site.bretelles,
    ...(site.parking_vl ? [site.parking_vl.voie] : [])]].map((lignes) => lignes
    .flatMap((ligne) => tirets(ligne, TIRETS_ROUTE.trait, TIRETS_ROUTE.vide))), [site]);
  const { centre: [cx, cy], rayon } = site.retournement;
  return (
    <group>
      <Ruban points={site.route_publique} largeur={LARGEUR_ROUTE_PUBLIQUE}
        couleur={COULEURS_PLAN.routePublique} z={Z.routePublique} />
      <Acces site={site} />
      {[site.voirie, ...site.bretelles].map((ligne, i) => (
        <Ruban key={i} points={ligne} largeur={site.largeur_voirie}
          couleur={COULEURS_PLAN.voirie} z={Z.voirie} />
      ))}
      {site.parking_vl && <ParkingVl parking={site.parking_vl} />}
      <Bandes bandes={marquages[0]} largeur={TIRETS_ROUTE.largeur}
        couleur={COULEURS_PLAN.marquage} z={Z.routePublique + DESSUS_SOL} />
      <Bandes bandes={marquages[1]} largeur={TIRETS_ROUTE.largeur}
        couleur={COULEURS_PLAN.marquage} z={Z.voirie + DESSUS_SOL} />
      <mesh position={[cx, cy, Z.voirie]} rotation-x={Math.PI / 2} receiveShadow>
        <cylinderGeometry args={[rayon, rayon, EPAISSEUR_SOL, SEGMENTS_DISQUE]} />
        <meshStandardMaterial color={COULEURS_PLAN.voirie} />
      </mesh>
    </group>
  );
}

/** Rectangle [x, y, largeur, profondeur] de la place d'un camion à quai : du mur de la porte
 * jusqu'à une longueur de camion devant lui, de la largeur d'un quai ; à ciel ouvert, centré
 * sur le quai, en long dans le sens de la rangée. */
function placeDuQuai({ x, y, sens, porte }, longueurCamion) {
  const long = longueurCamion + QUAI.marge;
  if (!porte) {
    const [l, p] = Math.abs(sens[0]) >= Math.abs(sens[1]) ? [long, QUAI.enLong]
      : [QUAI.enLong, long];
    return [x - l / 2, y - p / 2, l, p];
  }
  const [nx, ny] = porte.normale;
  const [mx, my] = [porte.point[0] + (nx * long) / 2, porte.point[1] + (ny * long) / 2];
  const [l, p] = nx !== 0 ? [long, QUAI.largeur] : [QUAI.largeur, long];
  return nx !== 0 ? [mx - l / 2, y - p / 2, l, p] : [x - l / 2, my - p / 2, l, p];
}

/** Places des camions aux quais, tracées au sol (leurs numéros sont dans Batiments.jsx). */
function Quais({ site, longueurCamion }) {
  const lignes = useMemo(() => portesDeQuai(site).flatMap((quai) => troncons(
    rectangle(...placeDuQuai(quai, longueurCamion)))), [site, longueurCamion]);
  return <Bandes bandes={lignes} largeur={LIGNE_ZONE.largeur} couleur={COULEURS_PLAN.ligneZone}
    z={Z.quai} />;
}

/** Places du parking PL, lignes blanches au sol. */
function ParkingPl({ site }) {
  const lignes = useMemo(() => lignesDuParkingPl(site).flatMap((l) => troncons(l)), [site]);
  return <Bandes bandes={lignes} largeur={TIRETS_ROUTE.largeur}
    couleur={COULEURS_PLAN.marquage} z={Z.zone + DESSUS_SOL + EPAISSEUR_TRACE} />;
}

/** Zone : dalle de sa couleur (sol du bâtiment si elle est couverte). */
function Zone({ zone }) {
  const { x, y, largeur, profondeur, couleur } = zone;
  return (
    <mesh position={[x + largeur / 2, y + profondeur / 2, Z.zone]} receiveShadow>
      <boxGeometry args={[largeur, profondeur, EPAISSEUR_SOL]} />
      <meshStandardMaterial color={couleur} />
    </mesh>
  );
}

/** Lignes jaune-orangé au bord intérieur des zones à ciel ouvert. */
function LignesDesZones({ zones }) {
  const lignes = useMemo(() => {
    const retrait = LIGNE_ZONE.largeur / 2;
    return zones.filter((zone) => zone.hauteur === 0).flatMap((zone) => troncons(rectangle(
      zone.x + retrait, zone.y + retrait, zone.largeur - 2 * retrait,
      zone.profondeur - 2 * retrait)));
  }, [zones]);
  return <Bandes bandes={lignes} largeur={LIGNE_ZONE.largeur} couleur={COULEURS_PLAN.ligneZone}
    z={Z.zone + DESSUS_SOL} />;
}

/** Flèche du nord et barre d'échelle, posées au sol. */
function Reperes() {
  const fleche = useMemo(() => new Shape([[0, 1], [-0.35, -0.45], [0, -0.2], [0.35, -0.45]]
    .map(([u, v]) => new Vector2((u * NORD.longueur) / 2, (v * NORD.longueur) / 2))), []);
  return (
    <group>
      <mesh position={[NORD.x, NORD.y, Z.quai]}>
        <shapeGeometry args={[fleche]} />
        <meshBasicMaterial color={COULEURS_PLAN.reperes} />
      </mesh>
      <mesh position={[ECHELLE.x + ECHELLE.longueur / 2, ECHELLE.y, Z.quai]}>
        <boxGeometry args={[ECHELLE.longueur, ECHELLE.largeur, EPAISSEUR_SOL]} />
        <meshBasicMaterial color={COULEURS_PLAN.reperes} />
      </mesh>
    </group>
  );
}

/** Plan complet de l'implantation de la scène ; `longueurCamion` : pour les places à quai. */
export default function Site({ site, longueurCamion }) {
  return (
    <group>
      <mesh position-z={Z.sol} receiveShadow>
        <planeGeometry args={[TAILLE_SOL, TAILLE_SOL]} />
        <meshStandardMaterial color={COULEURS_PLAN.sol} />
      </mesh>
      {site.contours.map((contour) => <Contour key={contour.nom} contour={contour} />)}
      <Voiries site={site} />
      <Quais site={site} longueurCamion={longueurCamion} />
      {site.zones.map((zone) => <Zone key={zone.nom} zone={zone} />)}
      <LignesDesZones zones={site.zones} />
      <ParkingPl site={site} />
      <Reperes />
    </group>
  );
}
