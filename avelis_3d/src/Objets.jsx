// Objets animés : un InstancedMesh par forme (objets.js donne la forme de chaque objet,
// formesVehicules.js et formesCharges.js les dessinent), mis à jour à chaque image depuis le
// lecteur, aux poses de la couche visuelle des trajectoires (trajectoires.js), chacun doublé
// d'un InstancedMesh d'ombres de contact ; les roues des camions, qui tournent de la distance
// parcourue, et les modules chargés sur les plateaux ont aussi le leur ; une marchandise en
// route est levée sur les fourches du chariot qui la porte (Chariots.jsx). L'objet survolé se
// soulève et se détoure ; un clic le sélectionne. Coordonnées du plan, comme Site.jsx ; objets
// posés à Z_POSE. Les ombres de contact et le contour sont exclus de l'occlusion ambiante
// (Rendu.jsx).
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { useFrame } from "@react-three/fiber";
import { Outlines } from "@react-three/drei";
import { Matrix4, Quaternion, Sphere, Vector3 } from "three";

import {
  CHARIOT_PORTEUR, COULEURS_OBJETS, COULEUR_SURVOL, OMBRE_CONTACT, RUGOSITE_OBJETS, SELECTION,
  SURVOL, Z, Z_POSE,
} from "./apparence.js";
import { TYPES_OBJETS } from "./donnees.js";
import { FORMES_CHARGES } from "./formesCharges.js";
import { FORMES_VEHICULES, roueUnite } from "./formesVehicules.js";
import { geometrieOmbre } from "./gabarits.js";
import {
  chargementsDesCamions, enTransport, formeObjet, placesDeCharge, rouesDe,
} from "./objets.js";
import { etatAffiche } from "./trajectoires.js";

const AXE_Y = new Vector3(0, 1, 0);
const AXE_Z = new Vector3(0, 0, 1);
const UNITE = new Vector3(1, 1, 1);
const Z_OMBRE = Z.quai + 0.04; // au-dessus de tous les sols et tracés
const CONSTRUCTEURS = { ...FORMES_VEHICULES, ...FORMES_CHARGES };
const RAPPORTEES = ["roues", "charges"];
const PRIORITE_LEVEE = -1; // avant le placement des objets
const adoucir = (p) => p * p * (3 - 2 * p);

/** Formes présentes parmi les objets d'un type : [{forme, objets, corps}] ; `ombre` : ombre de
 * contact du gabarit, commune aux formes du type. */
function formesDuType(type, objets, gabarit, schema) {
  const parForme = new Map();
  for (const objet of objets) {
    const forme = formeObjet(objet, schema);
    if (!parForme.has(forme)) parForme.set(forme, []);
    parForme.get(forme).push(objet);
  }
  return { ombre: geometrieOmbre(gabarit, OMBRE_CONTACT.marge, Z_OMBRE - Z_POSE),
    liste: [...parForme].map(([forme, liste]) => ({ forme, objets: liste,
      corps: CONSTRUCTEURS[forme](gabarit, COULEURS_OBJETS[type]) })) };
}

/** Matrice de position (x, y, z), sans rotation ni échelle. */
function repere(x, y, z) {
  return new Matrix4().makeTranslation(x, y, z);
}

/** Pièces rapportées des camions, dans leur repère : roues {position, echelle, rayon} (par
 * forme) et modules chargés sur les plateaux (par camion, montrés dès qu'il quitte le quai) ;
 * géométries et nombre d'instances de chacune. */
function piecesRapportees(scene, camions) {
  const gabarit = scene.gabarits.camion;
  const roues = Object.fromEntries(Object.keys(FORMES_VEHICULES).map((forme) => [forme,
    rouesDe(forme, gabarit).map((r) => ({ position: new Vector3(r.x, r.y, r.rayon),
      echelle: new Vector3(r.rayon, r.largeur, r.rayon), rayon: r.rayon }))]));
  const chargements = chargementsDesCamions(scene.objets);
  const charge = scene.gabarits.module;
  for (const c of chargements.values()) {
    c.locales = placesDeCharge(c.modules.length, charge, gabarit[1]).map((p) => repere(p.x, 0,
      p.z));
  }
  const formeCharge = formeObjet({ id: "", type: "module" }, scene.scenario.schema);
  return { roues, chargements,
    geometries: { roues: roueUnite(),
      charges: CONSTRUCTEURS[formeCharge](charge, COULEURS_OBJETS.module) },
    tailles: { roues: camions.reduce((n, o) => n + roues[formeObjet(o)].length, 0),
      charges: [...chargements.values()].reduce((n, c) => n + c.locales.length, 0) } };
}

/** Fixe le nombre d'instances dessinées d'un maillage et signale le changement à three. */
function compter(maillage, nombre) {
  maillage.count = nombre;
  maillage.instanceMatrix.needsUpdate = true;
}

/** Pose de l'objet à l'instant t : sa matrice dans `outils.matrice` (sens de la marche, posé à
 * Z_POSE et soulevé de `hauteur` m), celle de son ombre, au sol, dans `outils.ombre` ; renvoie
 * son état affiché, ou null s'il est masqué. */
function poser(objet, t, hauteur, outils, trajectoires) {
  const etat = etatAffiche(objet, t, trajectoires);
  if (etat === null) return null;
  const { matrice, ombre, position, rotation } = outils;
  rotation.setFromAxisAngle(AXE_Z, etat.cap);
  ombre.compose(position.set(etat.x, etat.y, Z_POSE), rotation, UNITE);
  matrice.compose(position.set(etat.x, etat.y, Z_POSE + hauteur), rotation, UNITE);
  return etat;
}

/** Roues, tournées de la distance parcourue, et chargement du camion posé (sa matrice dans
 * `outils.matrice`). */
function rapporter(camion, forme, etat, t, { rapportees, maillages, proprietaires, outils }) {
  const ajouter = (cle, locale) => {
    maillages.get(cle).corps.setMatrixAt(proprietaires[cle].length,
      outils.piece.multiplyMatrices(outils.matrice, locale));
    proprietaires[cle].push(camion);
  };
  for (const { position, echelle, rayon } of rapportees.roues[forme]) {
    outils.rotationRoue.setFromAxisAngle(AXE_Y, etat.odometre / rayon);
    ajouter("roues", outils.locale.compose(position, outils.rotationRoue, echelle));
  }
  const chargement = rapportees.chargements.get(camion.id);
  if (chargement && t >= chargement.depart) {
    for (const locale of chargement.locales) ajouter("charges", locale);
  }
}

/** Place les objets visibles d'une forme (corps, ombres, pièces rapportées) ; l'objet soulevé
 * l'est de `hauteur` m et le contour se pose sur lui ; une marchandise en route est levée sur
 * les fourches de son chariot. Renvoie les visibles, dans l'ordre des instances. */
function placerForme({ forme, objets }, t, contexte, { hauteur, levee, contour, trajectoires }) {
  const { corps, ombres } = contexte.maillages.get(forme);
  const liste = [];
  for (const objet of objets) {
    const leve = objet === levee.objet;
    const porte = enTransport(objet, t);
    const etat = poser(objet, t, (leve ? hauteur : 0) + (porte ? CHARIOT_PORTEUR.levage : 0),
      contexte.outils, trajectoires);
    if (!etat) continue;
    corps.setMatrixAt(liste.length, contexte.outils.matrice);
    ombres.setMatrixAt(liste.length, contexte.outils.ombre);
    if (contexte.rapportees) rapporter(objet, forme, etat, t, contexte);
    if (leve && contour) {
      contour.matrix.copy(contexte.outils.matrice);
      contour.visible = true;
    }
    liste.push(objet);
  }
  compter(corps, liste.length);
  compter(ombres, liste.length);
  return liste;
}

/** Place les objets visibles à l'instant t de chaque forme et leurs pièces rapportées ;
 * renvoie les visibles de chaque forme et les propriétaires des pièces rapportées, dans l'ordre
 * des instances (pour le pointeur). */
function placer(formes, maillages, rapportees, t, outils, reglages) {
  const contexte = { rapportees, maillages, outils, proprietaires: { roues: [], charges: [] } };
  const { levee, contour } = reglages;
  if (contour) contour.visible = false;
  const options = { ...reglages, hauteur: SURVOL.soulevement * adoucir(levee.valeur) };
  const visibles = formes.liste.map((forme) => placerForme(forme, t, contexte, options));
  for (const cle of RAPPORTEES) {
    const maillage = maillages.get(cle)?.corps;
    if (maillage) compter(maillage, contexte.proprietaires[cle].length);
  }
  return { visibles, proprietaires: contexte.proprietaires };
}

/** Vrai quand tous les maillages à remplir sont montés. */
function prets(formes, rapportees, maillages) {
  const cles = formes.liste.map((f) => f.forme);
  const montes = cles.every((cle) => maillages.get(cle)?.corps && maillages.get(cle)?.ombres);
  return montes && (!rapportees || RAPPORTEES.every((cle) => rapportees.tailles[cle] === 0
    || maillages.get(cle)?.corps));
}

/** À chaque nouvel instant du lecteur, ou quand l'objet soulevé bouge, replace les instances et
 * publie le nombre d'objets visibles du type ; renvoie la réf. de ce que `placer` a renvoyé. */
function usePlacement(type, formes, rapportees, maillages, { lecteur, levee, contour,
  trajectoires }) {
  const etat = useRef({ visibles: [], proprietaires: { roues: [], charges: [] } });
  const dernier = useRef({});
  const outils = useMemo(() => ({ matrice: new Matrix4(), ombre: new Matrix4(),
    piece: new Matrix4(), locale: new Matrix4(), position: new Vector3(),
    rotation: new Quaternion(), rotationRoue: new Quaternion() }), []);
  useFrame(() => {
    const cle = { lecteur, t: lecteur.t, formes, objet: levee.objet, valeur: levee.valeur,
      contour: contour.current };
    // Un nouveau lecteur (rechargement à chaud) attend ses comptes, même au même instant
    if (Object.keys(cle).every((k) => cle[k] === dernier.current[k])) return;
    if (!prets(formes, rapportees, maillages)) return;
    dernier.current = cle;
    etat.current = placer(formes, maillages, rapportees, cle.t, outils, { levee,
      contour: contour.current, trajectoires });
    lecteur.publierCompte(type, etat.current.visibles.reduce((n, l) => n + l.length, 0));
  });
  return etat;
}

/** Libère les géométries des formes et des pièces rapportées quand elles changent. */
function useLiberer(formes, rapportees) {
  useEffect(() => () => {
    for (const { corps } of formes.liste) corps.dispose();
    formes.ombre.dispose();
    for (const geometrie of Object.values(rapportees?.geometries ?? {})) geometrie.dispose();
  }, [formes, rapportees]);
}

/** InstancedMesh d'objets ou de pièces : matériau mat, couleurs des sommets ; enveloppe fixe
 * (tout le site) pour le pointeur, les instances se déplaçant. */
function Maillage({ geometrie, nombre, brancher, enveloppe, ...evenements }) {
  const ref = (maillage) => {
    if (maillage) maillage.boundingSphere = enveloppe;
    brancher(maillage);
  };
  return (
    <instancedMesh ref={ref} args={[geometrie, undefined, nombre]} castShadow receiveShadow
      frustumCulled={false} {...evenements}>
      <meshStandardMaterial vertexColors roughness={RUGOSITE_OBJETS} />
    </instancedMesh>
  );
}

/** Gestionnaires de pointeur d'un maillage : l'instance survolée ou cliquée désigne l'objet que
 * `lire()` donne à son rang (l'objet lui-même, ou le camion d'une roue ou d'une charge). Un
 * clic le sélectionne, sauf au bout d'un glisser. */
function pointeur({ survol, selection }, type, lire) {
  return {
    onPointerMove: (evenement) => {
      evenement.stopPropagation();
      const objet = lire()[evenement.instanceId];
      const { clientX, clientY } = evenement.nativeEvent;
      if (objet) survol.montrer(objet, clientX, clientY);
      document.body.style.cursor = "pointer";
    },
    onPointerOut: () => {
      survol.cacher(type);
      document.body.style.cursor = "";
    },
    onClick: (evenement) => {
      if (evenement.delta > SELECTION.clic) return;
      evenement.stopPropagation();
      const objet = lire()[evenement.instanceId];
      if (objet) selection.choisir(objet);
    },
  };
}

/** Contour de l'objet survolé du type : sa forme, invisible, détourée (Outlines de drei).
 * `placer` pose le groupe sur l'objet soulevé et le montre. */
function Contour({ type, formes, survol, schema, groupe }) {
  useSyncExternalStore(survol.abonner, survol.lireVersion);
  const objet = survol.objet?.type === type ? survol.objet : null;
  const forme = objet && formes.liste.find((f) => f.forme === formeObjet(objet, schema));
  return (
    <group ref={groupe} matrixAutoUpdate={false} userData={{ sansOcclusion: true }}>
      {forme && (
        <mesh key={forme.forme} geometry={forme.corps}>
          <meshBasicMaterial visible={false} />
          <Outlines thickness={SURVOL.contour} color={COULEUR_SURVOL} />
        </mesh>
      )}
    </group>
  );
}

/** Objets d'un type : une forme par InstancedMesh, avec ses ombres de contact, et pour les
 * camions leurs roues et leurs chargements. Seuls les visibles à l'instant du lecteur sont
 * dessinés ; chaque instance (corps, roue, charge) est reliée à son objet pour le pointeur. */
function ObjetsDuType({ type, objets, scene, enveloppe, levee, magasins }) {
  const gabarit = scene.gabarits[type];
  const schema = scene.scenario.schema;
  const formes = useMemo(() => formesDuType(type, objets, gabarit, schema),
    [type, objets, gabarit, schema]);
  const rapportees = useMemo(() => (type === "camion" ? piecesRapportees(scene, objets) : null),
    [type, scene, objets]);
  useLiberer(formes, rapportees);
  const maillages = useMemo(() => new Map(), []);
  const contour = useRef(null);
  const etat = usePlacement(type, formes, rapportees, maillages, { ...magasins, levee,
    contour });
  const brancher = (cle, partie) => (maillage) => {
    maillages.set(cle, { ...maillages.get(cle), [partie]: maillage });
  };
  return (
    <group>
      {formes.liste.map(({ forme, corps, objets: liste }, i) => (
        <group key={forme}>
          <Maillage geometrie={corps} nombre={liste.length} brancher={brancher(forme, "corps")}
            enveloppe={enveloppe}
            {...pointeur(magasins, type, () => etat.current.visibles[i] ?? [])} />
          <instancedMesh ref={brancher(forme, "ombres")} args={[formes.ombre, undefined,
            liste.length]} frustumCulled={false} userData={{ sansOcclusion: true }}>
            <meshBasicMaterial vertexColors transparent depthWrite={false}
              color={OMBRE_CONTACT.couleur} opacity={OMBRE_CONTACT.opacite} />
          </instancedMesh>
        </group>
      ))}
      {rapportees && RAPPORTEES.filter((cle) => rapportees.tailles[cle] > 0).map((cle) => (
        <Maillage key={cle} geometrie={rapportees.geometries[cle]} nombre={rapportees.tailles[cle]}
          brancher={brancher(cle, "corps")} enveloppe={enveloppe}
          {...pointeur(magasins, type, () => etat.current.proprietaires[cle])} />
      ))}
      <Contour type={type} formes={formes} survol={magasins.survol} schema={schema}
        groupe={contour} />
    </group>
  );
}

/** Soulèvement de l'objet survolé : {objet, valeur} où valeur va de 0 (posé) à 1 (soulevé) en
 * SURVOL.duree s ; l'objet quitté redescend, celui qu'on survole ensuite part de 0. */
export function useLevee(survol) {
  const levee = useMemo(() => ({ objet: null, valeur: 0 }), []);
  useFrame((_, secondes) => {
    const cible = survol.objet;
    if (cible && cible !== levee.objet) Object.assign(levee, { objet: cible, valeur: 0 });
    const pas = secondes / SURVOL.duree;
    levee.valeur = cible ? Math.min(1, levee.valeur + pas) : Math.max(0, levee.valeur - pas);
    if (!cible && levee.valeur === 0) levee.objet = null;
  }, PRIORITE_LEVEE);
  return levee;
}

/** Tous les objets animés de la scène ; `magasins` : {lecteur, survol, selection,
 * trajectoires}. */
export default function Objets({ scene, cadre, magasins }) {
  const parType = useMemo(() => TYPES_OBJETS.map((type) => [type,
    scene.objets.filter((objet) => objet.type === type)]), [scene]);
  const enveloppe = useMemo(() => new Sphere(new Vector3(cadre.cx, cadre.cy, 0), cadre.etendue),
    [cadre]);
  const levee = useLevee(magasins.survol);
  return (
    <group>
      {parType.filter(([, objets]) => objets.length > 0).map(([type, objets]) => (
        <ObjetsDuType key={type} type={type} objets={objets} scene={scene} enveloppe={enveloppe}
          levee={levee} magasins={magasins} />
      ))}
    </group>
  );
}
