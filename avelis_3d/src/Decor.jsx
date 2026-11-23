// Décor du site, en coordonnées du plan (emplacements : decor.js) : arbres, clôture, racks des
// stocks, chariots élévateurs des quais (« Chariot élévateur » au survol, qui les soulève) et
// AGV, véhicules au temps simulé (Vehicules.jsx), portail avec poste de garde et barrière
// levante, qui s'ouvre quand un camion ou une voiture en approche (formes : formesVehicules.js).
// Un InstancedMesh par forme répétée. Racks et engins à l'intérieur des bâtiments ne sont
// dessinés qu'en mode « Intérieurs » ; les panneaux de clôture, translucides, sont exclus de
// l'occlusion ambiante (Rendu.jsx). Le chariot d'un quai va et vient pendant la lecture tant
// qu'un camion y est arrêté. Les chariots qui portent les marchandises : Chariots.jsx.
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { BoxGeometry, Color, CylinderGeometry, IcosahedronGeometry, Object3D } from "three";

import {
  ARBRES, BARRIERE, CLOTURE, GRAINE_DECOR, POSTE_GARDE, RACK, RUGOSITE_OBJETS, SELECTION,
  SURVOL, Z, Z_POSE,
} from "./apparence.js";
import {
  arbresDuSite, clotureDuSite, creerOccupation, enginsDuDecor, portailDuSite, racksDesStocks,
  reculChariot,
} from "./decor.js";
import { segmentActif } from "./donnees.js";
import { formeAgv, formeChariot } from "./formesVehicules.js";
import { useLevee } from "./Objets.jsx";
import { arretEnCours, etatAffiche } from "./trajectoires.js";
import Vehicules from "./Vehicules.jsx";

const FORMES_ENGINS = { chariot: formeChariot, agv: formeAgv };
const adoucir = (p) => p * p * (3 - 2 * p);

const ETIREMENT_HOUPPIER = 1.15; // houppier un peu plus haut que large
const RECUL_NUL = 0.01; // m : en deçà, le chariot est revenu à sa place
const SEGMENTS_TRONC = 7;
const FINESSE_HOUPPIER = 2; // subdivisions de l'icosaèdre : rond sans trop de sommets

/** Pavé unité posé sur z = 0 (pour les poteaux, montants et cartons, mis à l'échelle). */
function paveUnite() {
  return new BoxGeometry(1, 1, 1).translate(0, 0, 0.5);
}

/** Repère {position, rotation z, échelle} → matrice, pour les instances. */
export function matrice(repere, [x, y, z], angle, [sx, sy, sz]) {
  repere.position.set(x, y, z);
  repere.rotation.set(0, 0, angle);
  repere.scale.set(sx, sy, sz);
  repere.updateMatrix();
  return repere.matrix.clone();
}

/** InstancedMesh de la `geometrie` aux `matrices`, teint par instance si `couleurs` est donné ;
 * géométrie libérée au démontage. */
function Instances({ geometrie, matrices, couleurs, ombre = true, children, ...props }) {
  const maillage = useRef(null);
  useLayoutEffect(() => {
    if (!maillage.current) return; // aucune instance : rien n'est monté
    matrices.forEach((m, i) => maillage.current.setMatrixAt(i, m));
    couleurs?.forEach((c, i) => maillage.current.setColorAt(i, c));
    maillage.current.instanceMatrix.needsUpdate = true;
    if (maillage.current.instanceColor) maillage.current.instanceColor.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  }, [matrices, couleurs]);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  if (!matrices.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, matrices.length]}
      castShadow={ombre} receiveShadow {...props}>
      {children}
    </instancedMesh>
  );
}

/** Arbres : tronc et houppier arrondi, de trois verts. */
function Arbres({ arbres }) {
  const instances = useMemo(() => {
    const repere = new Object3D();
    const teintes = ARBRES.couleurs.map((c) => new Color(c));
    return {
      troncs: arbres.map((a) => matrice(repere, [a.x, a.y, Z.site], 0, [1, 1,
        a.hauteur - a.rayon * ETIREMENT_HOUPPIER])),
      houppiers: arbres.map((a) => matrice(repere, [a.x, a.y, a.hauteur - a.rayon
        * ETIREMENT_HOUPPIER], 0, [a.rayon, a.rayon, a.rayon * ETIREMENT_HOUPPIER])),
      couleurs: arbres.map((a) => teintes[a.teinte]),
    };
  }, [arbres]);
  const tronc = useMemo(() => new CylinderGeometry(ARBRES.tronc * 0.8, ARBRES.tronc, 1,
    SEGMENTS_TRONC).rotateX(Math.PI / 2).translate(0, 0, 0.5), []);
  const houppier = useMemo(() => new IcosahedronGeometry(1, FINESSE_HOUPPIER), []);
  return (
    <group>
      <Instances geometrie={tronc} matrices={instances.troncs}>
        <meshStandardMaterial color={ARBRES.couleurTronc} />
      </Instances>
      <Instances geometrie={houppier} matrices={instances.houppiers} couleurs={instances.couleurs}>
        <meshStandardMaterial />
      </Instances>
    </group>
  );
}

/** Clôture : poteaux, lisse haute et panneaux translucides entre eux. */
function Cloture({ cloture }) {
  const instances = useMemo(() => {
    const repere = new Object3D();
    const { hauteur, poteau } = CLOTURE;
    return {
      poteaux: cloture.poteaux.map(([x, y]) => matrice(repere, [x, y, Z.site], 0,
        [poteau, poteau, hauteur])),
      lisses: cloture.panneaux.map((p) => matrice(repere, [p.x, p.y, hauteur - poteau], p.angle,
        [p.longueur, poteau / 2, poteau / 2])),
      panneaux: cloture.panneaux.map((p) => matrice(repere, [p.x, p.y, Z.site], p.angle,
        [p.longueur, poteau / 4, hauteur - poteau])),
    };
  }, [cloture]);
  const formes = useMemo(() => [paveUnite(), paveUnite(), paveUnite()], []);
  return (
    <group>
      <Instances geometrie={formes[0]} matrices={instances.poteaux} ombre={false}>
        <meshStandardMaterial color={CLOTURE.couleurPoteaux} />
      </Instances>
      <Instances geometrie={formes[1]} matrices={instances.lisses} ombre={false}>
        <meshStandardMaterial color={CLOTURE.couleurPoteaux} />
      </Instances>
      <Instances geometrie={formes[2]} matrices={instances.panneaux} ombre={false}
        userData={{ sansOcclusion: true }}>
        <meshStandardMaterial color={CLOTURE.couleur} transparent opacity={CLOTURE.opacite}
          depthWrite={false} />
      </Instances>
    </group>
  );
}

/** Matrices des montants, lisses et cartons des baies de racks. */
function piecesDeRacks(baies) {
  const repere = new Object3D();
  const { baie: b, profondeur: p, niveaux, etage, montant, lisse, carton } = RACK;
  const haut = niveaux * etage;
  const pieces = { montants: [], lisses: [], cartons: [] };
  for (const { x, y, angle, cartons } of baies) {
    const [ux, uy] = [Math.cos(angle), Math.sin(angle)];
    const place = (u, w, z) => [x + u * ux - w * uy, y + u * uy + w * ux, z];
    for (const [u, w] of [[-b / 2, -p / 2], [-b / 2, p / 2], [b / 2, -p / 2], [b / 2, p / 2]]) {
      pieces.montants.push(matrice(repere, place(u, w, Z.zone), angle, [montant, montant, haut]));
    }
    for (let niveau = 1; niveau <= niveaux; niveau++) {
      for (const w of [-p / 2, p / 2]) {
        pieces.lisses.push(matrice(repere, place(0, w, Z.zone + niveau * etage - lisse), angle,
          [b, montant, lisse]));
      }
    }
    for (const [niveau, cote] of cartons) {
      pieces.cartons.push(matrice(repere, place((cote - 0.5) * (b / 2), 0, Z.zone + niveau
        * etage + (niveau > 0 ? 0 : lisse / 2)), angle, carton));
    }
  }
  return pieces;
}

/** Groupe visible seulement en mode « Intérieurs » (dès que les bâtiments s'ouvrent). */
export function Interieur({ maquette, children }) {
  const groupe = useRef(null);
  useFrame(() => {
    groupe.current.visible = maquette.ouverture > 0 || Boolean(maquette.premiere);
  });
  return <group ref={groupe} visible={false}>{children}</group>;
}

/** Racks : montants violets, lisses orange, cartons. */
function Racks({ baies }) {
  const pieces = useMemo(() => piecesDeRacks(baies), [baies]);
  const formes = useMemo(() => [paveUnite(), paveUnite(), paveUnite()], []);
  return (
    <group>
      <Instances geometrie={formes[0]} matrices={pieces.montants}>
        <meshStandardMaterial color={RACK.couleurMontants} />
      </Instances>
      <Instances geometrie={formes[1]} matrices={pieces.lisses}>
        <meshStandardMaterial color={RACK.couleurLisses} />
      </Instances>
      <Instances geometrie={formes[2]} matrices={pieces.cartons}>
        <meshStandardMaterial color={RACK.couleurCartons} />
      </Instances>
    </group>
  );
}

/** Chariots élévateurs et AGV posés aux places `engins` : un InstancedMesh par forme. */
function Engins({ engins }) {
  const instances = useMemo(() => {
    const repere = new Object3D();
    return Object.keys(FORMES_ENGINS).map((forme) => [forme, engins.filter((e) => e.forme
      === forme).map((e) => matrice(repere, [e.x, e.y, Z_POSE], e.angle, [1, 1, 1]))]);
  }, [engins]);
  const formes = useMemo(() => Object.fromEntries(Object.entries(FORMES_ENGINS)
    .map(([forme, construire]) => [forme, construire()])), []);
  return (
    <group>
      {instances.map(([forme, matrices]) => (
        <Instances key={forme} geometrie={formes[forme]} matrices={matrices}>
          <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
        </Instances>
      ))}
    </group>
  );
}

/** Gestionnaires de pointeur des voitures : survol ou clic montrent leur nom dans l'infobulle
 * (pseudo-objet du décor, jamais sélectionné). */
export function nomAuSurvol(survol, libelles) {
  const montrer = (evenement) => {
    evenement.stopPropagation();
    const libelle = libelles[evenement.instanceId];
    if (!libelle) return;
    const { clientX, clientY } = evenement.nativeEvent;
    survol.montrer({ type: "voiture", id: libelle, libelle, decor: true }, clientX, clientY);
    document.body.style.cursor = "pointer";
  };
  return {
    onPointerMove: montrer,
    onPointerOut: () => {
      survol.cacher("voiture");
      document.body.style.cursor = "";
    },
    onClick: (evenement) => {
      if (evenement.delta <= SELECTION.clic) montrer(evenement);
    },
  };
}

/** Gestionnaires de pointeur d'engins nommés : l'instance survolée montre son pseudo-objet
 * `noms[i]` (toujours le même, pour qu'il se soulève). */
function survolDe(survol, noms) {
  const montrer = (evenement) => {
    evenement.stopPropagation();
    const objet = noms[evenement.instanceId];
    if (!objet) return;
    survol.montrer(objet, evenement.nativeEvent.clientX, evenement.nativeEvent.clientY);
    document.body.style.cursor = "pointer";
  };
  return { onPointerMove: montrer, onClick: montrer,
    onPointerOut: () => {
      survol.cacher("engin");
      document.body.style.cursor = "";
    } };
}

/** Vrai si un camion (pose affichée) ou une voiture qui circule est à moins de
 * BARRIERE.distance m du portail. */
function vehiculeAuPortail(portail, camions, lecteur, trajectoires, circulation) {
  const proche = (pose) => pose && Math.hypot(pose.x - portail[0], pose.y - portail[1])
    < BARRIERE.distance;
  if (circulation.poses.some(proche)) return true;
  return camions.some((camion) => segmentActif(camion, lecteur.t) >= 0
    && proche(etatAffiche(camion, lecteur.t, trajectoires)));
}

/** Poste de garde : murs clairs, bandeau vitré, toit plat débordant. */
function PosteDeGarde({ poste }) {
  const { largeur: l, profondeur: p, hauteur: h, toit, debord, vitre } = POSTE_GARDE;
  return (
    <group position={[poste.x, poste.y, Z_POSE]} rotation-z={poste.angle}>
      <mesh position-z={h / 2} castShadow receiveShadow>
        <boxGeometry args={[l, p, h]} />
        <meshStandardMaterial color={POSTE_GARDE.couleur} />
      </mesh>
      <mesh position-z={h - vitre / 2 - toit * 2}>
        <boxGeometry args={[l + 0.04, p + 0.04, vitre]} />
        <meshStandardMaterial color={POSTE_GARDE.vitreCouleur} roughness={0.2} />
      </mesh>
      <mesh position-z={h + toit / 2} castShadow>
        <boxGeometry args={[l + 2 * debord, p + 2 * debord, toit]} />
        <meshStandardMaterial color={POSTE_GARDE.toitCouleur} />
      </mesh>
    </group>
  );
}

/** Portail : poste de garde et barrière levante, qui se lève quand un véhicule approche et
 * se rabaisse après son passage. */
function Portail({ site, camions, lecteur, trajectoires, circulation }) {
  const { poste, barriere } = useMemo(() => portailDuSite(site), [site]);
  const bras = useRef(null);
  const ouverture = useRef(0);
  const longueur = site.largeur_voirie + BARRIERE.poteau;
  useFrame((_, secondes) => {
    const cible = vehiculeAuPortail(site.portail, camions, lecteur, trajectoires, circulation)
      ? 1 : 0;
    const pas = secondes / BARRIERE.duree;
    ouverture.current += Math.max(-pas, Math.min(pas, cible - ouverture.current));
    if (bras.current) bras.current.rotation.y = -ouverture.current * BARRIERE.levee;
  });
  const { poteau, hauteur, bras: section } = BARRIERE;
  const [bx, by] = barriere.pivot;
  return (
    <group>
      <PosteDeGarde poste={poste} />
      <mesh position={[bx, by, Z_POSE + hauteur / 2]} castShadow>
        <boxGeometry args={[poteau, poteau, hauteur]} />
        <meshStandardMaterial color={BARRIERE.socle} />
      </mesh>
      <group position={[bx, by, Z_POSE + hauteur]} rotation-z={barriere.angle}>
        <group ref={bras}>
          <mesh position-x={longueur / 2} castShadow>
            <boxGeometry args={[longueur, section, section]} />
            <meshStandardMaterial color={BARRIERE.couleur} />
          </mesh>
          {[0.25, 0.5, 0.75].map((f) => (
            <mesh key={f} position-x={longueur * f}>
              <boxGeometry args={[longueur / 8, section * 1.1, section * 1.1]} />
              <meshStandardMaterial color={BARRIERE.bande} />
            </mesh>
          ))}
        </group>
      </group>
    </group>
  );
}

/** Chariots des quais : pendant la lecture, tant qu'un camion est arrêté à leur quai, ils vont
 * et viennent en marche arrière sur la place réservée derrière eux (reculChariot), puis
 * reviennent à leur place ; à la pause, ils s'arrêtent. */
function ChariotsDesQuais({ engins, lecteur, arrets, survol }) {
  const maillage = useRef(null);
  const geometrie = useMemo(() => formeChariot(), []);
  const actifs = useMemo(() => engins.map(() => ({ secondes: 0 })), [engins]);
  const repere = useMemo(() => new Object3D(), []);
  const levee = useLevee(survol);
  const noms = useMemo(() => engins.map((e) => ({ type: "engin", id: `chariot-quai-${e.quai}`,
    libelle: "Chariot élévateur", decor: true })), [engins]);
  useEffect(() => () => geometrie.dispose(), [geometrie]);
  useFrame((_, secondes) => {
    if (!maillage.current) return;
    engins.forEach((engin, i) => {
      const actif = actifs[i];
      const occupe = arretEnCours(arrets.get(engin.quai) ?? [], lecteur.t) !== null;
      if (lecteur.lecture && (occupe || reculChariot(actif.secondes) > RECUL_NUL)) {
        actif.secondes += secondes;
      } else if (lecteur.lecture) actif.secondes = 0;
      const recul = reculChariot(actif.secondes);
      const [x, y] = [engin.x - recul * Math.cos(engin.angle),
        engin.y - recul * Math.sin(engin.angle)];
      const leve = levee.objet === noms[i] ? SURVOL.soulevement * adoucir(levee.valeur) : 0;
      maillage.current.setMatrixAt(i, matrice(repere, [x, y, Z_POSE + leve], engin.angle,
        [1, 1, 1]));
    });
    maillage.current.instanceMatrix.needsUpdate = true;
    maillage.current.computeBoundingSphere();
  });
  const gestion = useMemo(() => survolDe(survol, noms), [survol, noms]);
  if (!engins.length) return null;
  return (
    <instancedMesh ref={maillage} args={[geometrie, undefined, engins.length]} castShadow
      receiveShadow frustumCulled={false} {...gestion}>
      <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
    </instancedMesh>
  );
}

/** Tout le décor de la scène ; `arrets` : arrêts des camions à chaque quai (trajectoires.js) ;
 * `survol` : nom des véhicules et des engins ; `trajectoires` : camions au portail ;
 * `circulation` : véhicules au temps simulé (circulation.js). Les garages des chariots
 * (`garage`) sont dessinés par Chariots.jsx. */
export default function Decor({ scene, maquette, lecteur, arrets, survol, trajectoires,
  circulation }) {
  const decor = useMemo(() => {
    const occupation = creerOccupation(scene.site, scene.objets, scene.gabarits);
    const racks = racksDesStocks(scene.site, occupation, GRAINE_DECOR);
    return { arbres: arbresDuSite(scene.site, occupation, GRAINE_DECOR),
      cloture: clotureDuSite(scene.site, occupation), racks,
      engins: enginsDuDecor(scene.site, occupation, racks, GRAINE_DECOR)
        .filter((e) => !e.garage) };
    // un décor par site : une scène relue en direct (jumeau) ne le déplace pas
  }, [scene.site]); // eslint-disable-line react-hooks/exhaustive-deps
  const [dehors, dedans, desQuais] = useMemo(() => [
    // un chariot de quai posé dans un bâtiment reste immobile, comme ceux des stocks
    decor.engins.filter((e) => !e.dedans && !e.quai), decor.engins.filter((e) => e.dedans),
    decor.engins.filter((e) => e.quai && !e.dedans)], [decor]);
  const camions = useMemo(() => scene.objets.filter((o) => o.type === "camion"), [scene]);
  const portail = useMemo(() => ({ poses: [] }), []);
  return (
    <group>
      <Arbres arbres={decor.arbres} />
      <Cloture cloture={decor.cloture} />
      <Engins engins={dehors} />
      <Vehicules circulation={circulation} gabarits={scene.gabarits} lecteur={lecteur}
        survol={survol} portail={portail} />
      <Portail site={scene.site} camions={camions} lecteur={lecteur} trajectoires={trajectoires}
        circulation={portail} />
      <ChariotsDesQuais engins={desQuais} lecteur={lecteur} arrets={arrets} survol={survol} />
      <Interieur maquette={maquette}>
        <Racks baies={decor.racks} />
        <Engins engins={dedans} />
      </Interieur>
    </group>
  );
}
