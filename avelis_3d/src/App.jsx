// Vue 3D du site Avelis de Torcy. Charge la scène (scene.json, publiée par l'application ou
// écrite par « py -3 avelis_flux/scene_3d.py --scene »), puis l'anime. L'adresse peut donner
// l'instant de départ en minutes simulées : index.html?t=1830.
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { NeutralToneMapping } from "three";

import { GRAINE_DECOR } from "./apparence.js";
import BarreHaut from "./BarreHaut.jsx";
import Batiments from "./Batiments.jsx";
import Camera, { RAYON_ETENDUES } from "./Camera.jsx";
import { GABARIT_CHARIOT } from "./chariots.js";
import Chariots from "./Chariots.jsx";
import Ciel, { Precipitations, useLibelleMeteo, useMeteoDirecte } from "./Ciel.jsx";
import { creerCirculation } from "./circulation.js";
import Commandes from "./Commandes.jsx";
import CommandesVue from "./CommandesVue.jsx";
import Decor, { Interieur } from "./Decor.jsx";
import Flux from "./Flux.jsx";
import { cadreDuSite, chargerScene, etatObjet } from "./donnees.js";
import { CalqueEtiquettes, Projecteur, etiquettesDuSite } from "./Etiquettes.jsx";
import { instantVisible } from "./indicateurs.js";
import Indicateurs from "./Indicateurs.jsx";
import Infobulle from "./Infobulle.jsx";
import { creerLecteur, creerSelection, creerSurvol } from "./lecteur.js";
import { creerLogistique } from "./logistique.js";
import { Mesure, mesureDemandee } from "./Mesure.jsx";
import Objets from "./Objets.jsx";
import Panneaux from "./Panneaux.jsx";
import Ouvriers from "./Ouvriers.jsx";
import Pietons from "./Pietons.jsx";
import PremierePersonne from "./PremierePersonne.jsx";
import Rendu from "./Rendu.jsx";
import Site from "./Site.jsx";
import { Anneau, CalqueSuivi, ProjecteurSuivi } from "./Suivi.jsx";
import { arretsAQuai, creerTrajectoires } from "./trajectoires.js";

const ADRESSE_SCENE = "scene.json";
const EXPOSITION = 1.1;
const DPR_MAX = 1.5; // au-delà, l'occlusion ambiante coûte trop pour 60 images par seconde
/** Instant de départ demandé dans l'adresse (?t=…), 0 sinon. */
function instantDemande() {
  const valeur = new URLSearchParams(window.location.search).get("t");
  return valeur === null ? 0 : Number(valeur);
}

/** Ciel et lumières, caméra, plan, bâtiments, décor (opérateurs à pied et précipitations
 * compris), objets, traînées du flux, anneau de sélection, placement des étiquettes, de la
 * pilule et des épingles, et rendu ; fait avancer le lecteur à chaque image. `ciel` : {cycle,
 * directe} (jour et nuit, météo de Torcy en direct) ; `flux` : mode « flux » ; `premiere` :
 * vue à la première personne, à la place de la caméra isométrique. */
function Monde({ scene, suivi, commandes, etiquettes, registre, affichage, interieurs,
  maquette, ciel, flux, premiere }) {
  const { cadre, magasins, arrets, calque, logistique, circulation, gabarits } = suivi;
  useFrame((_, secondes) => magasins.lecteur.avancer(secondes));
  return (
    <>
      <Ciel cadre={cadre} scene={scene} lecteur={magasins.lecteur} {...ciel} />
      {premiere
        ? <PremierePersonne site={scene.site} cadre={cadre} commandes={commandes}
          maquette={maquette} />
        : <Camera site={scene.site} cadre={cadre} commandes={commandes} />}
      <group rotation-x={-Math.PI / 2}>
        <Site site={scene.site} longueurCamion={scene.gabarits.camion[1]} />
        <Batiments site={scene.site} interieurs={interieurs} maquette={maquette}
          vider={() => magasins.selection.choisir(null)} magasins={magasins}
          logistique={logistique} />
        <Decor scene={scene} maquette={maquette} lecteur={magasins.lecteur} arrets={arrets}
          survol={magasins.survol} trajectoires={magasins.trajectoires}
          circulation={circulation} />
        {/* remontés à chaque révision du direct : leurs maillages sont dimensionnés à la scène */}
        <Objets key={scene.direct?.revision ?? 0} scene={scene} cadre={cadre}
          magasins={magasins} />
        <Chariots key={`chariots-${scene.direct?.revision ?? 0}`} chariots={logistique.chariots}
          gabarits={scene.gabarits} magasins={magasins} />
        <Pietons scene={scene} circulation={circulation} lecteur={magasins.lecteur}
          survol={magasins.survol} />
        <Interieur maquette={maquette}>
          <Ouvriers scene={scene} lecteur={magasins.lecteur} survol={magasins.survol} />
        </Interieur>
        <Precipitations cadre={cadre} scene={scene} lecteur={magasins.lecteur} {...ciel} />
        {flux && <Flux objets={scene.objets} site={scene.site} />}
        <Anneau gabarits={gabarits} magasins={magasins} />
      </group>
      <Projecteur etiquettes={etiquettes} registre={registre} maquette={maquette} />
      <ProjecteurSuivi calque={calque} gabarits={gabarits} arrets={arrets}
        magasins={magasins} />
      <Rendu />
      {affichage && <Mesure affichage={affichage} />}
    </>
  );
}

/** Ce que la vue suit d'une scène : cadre du site ; magasins {lecteur, survol, selection,
 * trajectoires} ; circulation du décor (circulation.js) ; arrêts des camions à chaque quai ;
 * logistique (portes de marchandises, chariots élévateurs, passages : logistique.js) ; gabarits
 * des objets et des chariots ; calque de la pilule et des épingles. Tout dépend du site, sauf
 * les arrêts et la logistique : une scène relue en direct au même site garde la caméra, le
 * lecteur et la sélection (useDirect), et les portes si elles n'ont pas changé. */
function useSuivi(scene) {
  const precedente = useRef(null);
  const base = useMemo(() => {
    const trajectoires = creerTrajectoires(scene.site, scene.gabarits);
    const lecteur = creerLecteur(scene.temps.duree, instantDemande());
    if (scene.direct) lecteur.suivreDirect();
    return { cadre: cadreDuSite(scene.site), calque: { pilule: null, epingles: new Map() },
      circulation: creerCirculation(scene.site, scene.temps, GRAINE_DECOR),
      gabarits: { ...scene.gabarits, chariot: GABARIT_CHARIOT },
      magasins: { lecteur, survol: creerSurvol(), selection: creerSelection(), trajectoires } };
  }, [scene.site]); // eslint-disable-line react-hooks/exhaustive-deps
  const logistique = useMemo(() => {
    precedente.current = creerLogistique(scene, base.magasins.trajectoires,
      precedente.current?.portes);
    return precedente.current;
  }, [scene.objets, base]); // eslint-disable-line react-hooks/exhaustive-deps
  const arrets = useMemo(() => arretsAQuai(scene.objets, base.magasins.trajectoires),
    [scene.objets, base, logistique]); // eslint-disable-line react-hooks/exhaustive-deps
  return useMemo(() => ({ ...base, arrets, logistique }), [base, arrets, logistique]);
}

/** Scène relue en direct (jumeau numérique) : le lecteur reçoit la nouvelle durée, et l'objet
 * sélectionné est remplacé par sa nouvelle version (ou désélectionné s'il a disparu). */
function useDirect(scene, { lecteur, selection }, objets) {
  useEffect(() => {
    if (!scene.direct) return;
    lecteur.etendre(scene.temps.duree);
    if (selection.objet) selection.choisir(objets.get(selection.objet.id) ?? null);
  }, [scene, lecteur, selection, objets]);
}

/** Échap désélectionne et quitte la vue à la première personne. */
function useEchap(selection, quitterPremiere) {
  useEffect(() => {
    const appui = (evenement) => {
      if (evenement.key !== "Escape") return;
      selection.choisir(null);
      quitterPremiere();
    };
    window.addEventListener("keydown", appui);
    return () => window.removeEventListener("keydown", appui);
  }, [selection, quitterPremiere]);
}

/** `montrer(objet, instant)` : va à l'instant demandé (par défaut l'instant courant), ou au
 * plus proche où l'objet est visible (instantVisible), le sélectionne et centre la vue sur lui
 * (recherche et alertes de la barre du haut). */
function useMontrer(lecteur, selection, commandes) {
  return useMemo(() => (objet, instant = lecteur.t) => {
    const t = instantVisible(objet, instant);
    if (t !== lecteur.t) lecteur.aller(t);
    selection.choisir(objet);
    const etat = etatObjet(objet, t);
    if (etat) commandes.viser?.(etat.x, etat.y);
  }, [lecteur, selection, commandes]);
}

/** Scène chargée : toile 3D et cartes de l'interface (barre du haut, indicateurs, légende,
 * commandes de la vue, curseur de temps, infobulle, pilule et épingles, compteur d'images
 * s'il est demandé). `maquette` : état des
 * bâtiments que lisent les étiquettes et le décor à chaque image (Batiments.jsx). Un clic dans
 * le vide désélectionne. */
function Visionneuse({ scene }) {
  const suivi = useSuivi(scene);
  const { cadre, magasins: { lecteur, survol, selection, trajectoires } } = suivi;
  const [premiere, changerPremiere] = useState(false);
  const quitterPremiere = useMemo(() => () => changerPremiere(false), []);
  useEchap(selection, quitterPremiere);
  const commandes = useMemo(() => ({}), []);
  const montrer = useMontrer(lecteur, selection, commandes);
  const objets = useMemo(() => new Map(scene.objets.map((objet) => [objet.id, objet])), [scene]);
  useDirect(scene, suivi.magasins, objets);
  const etiquettes = useMemo(() => etiquettesDuSite(scene.site), [scene.site]);
  const registre = useMemo(() => new Map(), []);
  const [noms, changerNoms] = useState(true);
  const [interieurs, changerInterieurs] = useState(false);
  const [cycle, changerCycle] = useState(true);
  const [flux, changerFlux] = useState(false);
  const directe = useMeteoDirecte(scene, cycle);
  const meteo = useLibelleMeteo(scene, lecteur, directe);
  const ciel = useMemo(() => ({ cycle, directe }), [cycle, directe]);
  const maquette = useMemo(() => ({ ouverture: 0, echelleMurs: 1 }), []);
  const affichage = useRef(null);
  const mesure = useMemo(() => mesureDemandee(), []);
  const rayon = cadre.etendue * RAYON_ETENDUES;
  return (
    <main className="visionneuse">
      <Canvas orthographic shadows="percentage" dpr={[1, DPR_MAX]}
        gl={{ antialias: false, toneMapping: NeutralToneMapping,
          toneMappingExposure: EXPOSITION }}
        camera={{ near: 1, far: rayon * 3, position: [cadre.cx, rayon, -cadre.cy] }}
        onPointerMissed={() => selection.choisir(null)}>
        <Monde scene={scene} suivi={suivi} commandes={commandes} etiquettes={etiquettes}
          registre={registre} affichage={mesure ? affichage : null} interieurs={interieurs}
          maquette={maquette} ciel={ciel} flux={flux} premiere={premiere} />
      </Canvas>
      <CalqueEtiquettes etiquettes={etiquettes} noms={noms && !premiere} registre={registre} />
      <CalqueSuivi calque={suivi.calque} quais={trajectoires.quais} selection={selection}
        schema={scene.scenario.schema} />
      <BarreHaut scene={scene} lecteur={lecteur} objets={objets} montrer={montrer} />
      <Indicateurs scene={scene} lecteur={lecteur} />
      <CommandesVue commandes={commandes} interieurs={interieurs}
        basculerInterieurs={() => changerInterieurs((valeur) => !valeur)} cycle={cycle}
        basculerCycle={() => changerCycle((valeur) => !valeur)} meteo={meteo} flux={flux}
        basculerFlux={() => changerFlux((valeur) => !valeur)} premiere={premiere}
        basculerPremiere={() => changerPremiere((valeur) => !valeur)} />
      <Panneaux scene={scene} magasins={suivi.magasins} arrets={suivi.arrets} objets={objets}
        montrer={montrer} noms={noms} changerNoms={changerNoms} />
      <Commandes lecteur={lecteur} scene={scene} />
      <Infobulle survol={survol} schema={scene.scenario.schema} />
      {mesure && <output className="carte mesure" ref={affichage} />}
    </main>
  );
}

/** Message plein écran (chargement ou erreur). */
function Message({ titre, texte }) {
  return (
    <main className="message">
      <h1>{titre}</h1>
      {texte && <p>{texte}</p>}
    </main>
  );
}

const AIDE_OUVERTURE = "Ouvrez la vue 3D depuis l'application, avec le bouton « 4 Vue 3D ».";
const MS_PAR_S = 1000;

/** Même site ? Comparé sur le JSON : une scène relue garde alors l'objet site de la
 * précédente, et la vue ne recadre rien. */
function memeSite(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Scène en direct (jumeau numérique) : relue toutes les `intervalle_s` secondes ; remplacée
 * quand sa révision change (nouveaux scans). Une relecture manquée est simplement refaite. */
function useRelecture(scene, changerEtat) {
  const courante = useRef(scene);
  courante.current = scene;
  const intervalle = scene?.direct?.intervalle_s;
  useEffect(() => {
    if (!intervalle) return undefined;
    const minuterie = setInterval(() => {
      chargerScene(ADRESSE_SCENE).then((nouvelle) => {
        const ancienne = courante.current;
        if (!nouvelle.direct || nouvelle.direct.revision === ancienne.direct.revision) return;
        if (memeSite(nouvelle.site, ancienne.site)) {
          Object.assign(nouvelle, { site: ancienne.site, gabarits: ancienne.gabarits });
        }
        changerEtat({ scene: nouvelle, erreur: null });
      }).catch(() => {});
    }, intervalle * MS_PAR_S);
    return () => clearInterval(minuterie);
  }, [intervalle, changerEtat]);
}

/** Charge la scène, puis l'affiche ; en cas d'échec, dit pourquoi et comment ouvrir la vue. */
export default function App() {
  const [etat, changerEtat] = useState({ scene: null, erreur: null });
  useEffect(() => {
    chargerScene(ADRESSE_SCENE)
      .then((scene) => changerEtat({ scene, erreur: null }))
      .catch((erreur) => changerEtat({ scene: null, erreur: erreur.message }));
  }, []);
  useRelecture(etat.scene, changerEtat);
  if (etat.erreur) {
    return (
      <Message titre="La scène 3D n'a pas pu être chargée"
        texte={`${etat.erreur}. ${AIDE_OUVERTURE}`} />
    );
  }
  if (!etat.scene) return <Message titre="Chargement de la scène 3D…" />;
  return <Visionneuse scene={etat.scene} />;
}
