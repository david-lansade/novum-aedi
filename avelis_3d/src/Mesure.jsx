// Compteur d'images, affiché si l'adresse contient « mesure » (index.html?mesure=1) : images par
// seconde, durée moyenne d'une image, temps de calcul d'une image par la carte graphique (GPU) et
// par le processeur (CPU), appels de dessin et triangles (toutes passes comprises). Les valeurs
// sont aussi publiées dans window.mesureRendu, pour les contrôles par script.
//
// Les temps GPU et CPU ne dépendent pas de la cadence d'affichage : ils restent justes quand le
// navigateur ralentit une page masquée (60 images/s demandent moins de 16,7 ms chacun).
import { useEffect, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";

const PERIODE_MS = 1000;
const PRIORITE_DEBUT = -1000; // avant toute autre mise à jour de l'image
const PRIORITE_FIN = 2; // après le rendu (Rendu.jsx, priorité 1) : les compteurs sont complets
const NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

/** Vrai si l'adresse demande le compteur d'images. */
export function mesureDemandee() {
  return new URLSearchParams(window.location.search).has("mesure");
}

/** Chronomètre GPU (extension EXT_disjoint_timer_query_webgl2), ou null si elle manque :
 * debut() et fin() encadrent une image, lire() rend les durées (ms) des images terminées. */
function chronometreGpu(contexte) {
  const extension = contexte.getExtension("EXT_disjoint_timer_query_webgl2");
  if (!extension) return null;
  const enAttente = [];
  let enCours = null;
  return {
    debut() {
      enCours = contexte.createQuery();
      contexte.beginQuery(extension.TIME_ELAPSED_EXT, enCours);
    },
    fin() {
      if (!enCours) return;
      contexte.endQuery(extension.TIME_ELAPSED_EXT);
      enAttente.push(enCours);
      enCours = null;
    },
    lire() {
      const durees = [];
      const faussees = contexte.getParameter(extension.GPU_DISJOINT_EXT);
      while (enAttente.length
        && contexte.getQueryParameter(enAttente[0], contexte.QUERY_RESULT_AVAILABLE)) {
        const requete = enAttente.shift();
        const nanosecondes = contexte.getQueryParameter(requete, contexte.QUERY_RESULT);
        if (!faussees) durees.push(nanosecondes / 1e6);
        contexte.deleteQuery(requete);
      }
      return durees;
    },
  };
}

/** Texte du compteur. */
function texteMesure({ ips, ms, gpuMs, cpuMs, appels, triangles }) {
  const gpu = gpuMs === null ? "GPU ?" : `GPU ${NOMBRE.format(gpuMs)} ms`;
  return `${NOMBRE.format(ips)} images/s · ${NOMBRE.format(ms)} ms · ${gpu} · `
    + `CPU ${NOMBRE.format(cpuMs)} ms · ${appels} appels · `
    + `${NOMBRE.format(triangles / 1000)} k triangles`;
}

/** Dans la toile : mesure chaque image et écrit le résultat dans l'élément `affichage` (réf.). */
export function Mesure({ affichage }) {
  const { gl, scene, camera } = useThree();
  const chrono = useMemo(() => chronometreGpu(gl.getContext()), [gl]);
  const cumul = useMemo(() => ({ images: 0, debut: performance.now(), gpu: [], cpu: 0,
    debutImage: 0 }), []);
  useEffect(() => {
    gl.info.autoReset = false; // sinon chaque passe remet les compteurs à zéro
    window.vue3d = { gl, scene, camera }; // pour les contrôles par script (caméra, lumières)
    return () => {
      gl.info.autoReset = true;
      delete window.vue3d;
    };
  }, [gl, scene, camera]);
  useFrame(() => {
    cumul.debutImage = performance.now();
    chrono?.debut();
  }, PRIORITE_DEBUT);
  useFrame(() => {
    chrono?.fin();
    const maintenant = performance.now();
    cumul.cpu += maintenant - cumul.debutImage;
    cumul.gpu.push(...(chrono?.lire() ?? []));
    cumul.images += 1;
    const { calls: appels, triangles } = gl.info.render;
    gl.info.reset();
    const ecoule = maintenant - cumul.debut;
    if (ecoule < PERIODE_MS) return;
    const gpuMs = cumul.gpu.length ? cumul.gpu.reduce((a, b) => a + b) / cumul.gpu.length : null;
    const mesure = { ips: (cumul.images * 1000) / ecoule, ms: ecoule / cumul.images, gpuMs,
      cpuMs: cumul.cpu / cumul.images, appels, triangles, toneMapping: gl.toneMapping,
      dpr: gl.getPixelRatio() };
    window.mesureRendu = mesure;
    if (affichage.current) affichage.current.textContent = texteMesure(mesure);
    Object.assign(cumul, { images: 0, debut: maintenant, gpu: [], cpu: 0 });
  }, PRIORITE_FIN);
  return null;
}
