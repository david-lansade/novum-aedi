// État partagé hors de React, pour que la scène 3D ne soit pas re-rendue à chaque image :
// - le lecteur : instant simulé, lecture, vitesse, nombre d'objets visibles par type ;
// - le survol : objet sous le pointeur et position du pointeur ;
// - la sélection : objet choisi d'un clic.
// Les composants s'y abonnent avec useSyncExternalStore (version incrémentée à chaque changement).
import { VITESSE_DEFAUT } from "./apparence.js";

const PAS_MAX_S = 0.1; // au-delà (onglet en arrière-plan), l'animation ne saute pas d'un coup
const MS_PAR_MINUTE = 60000; // direct : une minute de la scène par minute réelle

/** Abonnements et numéro de version communs aux deux magasins. */
function magasin(etat) {
  const abonnes = new Set();
  etat.version = 0;
  etat.abonner = (rappel) => {
    abonnes.add(rappel);
    return () => abonnes.delete(rappel);
  };
  etat.lireVersion = () => etat.version;
  etat.notifier = () => {
    etat.version += 1;
    for (const rappel of abonnes) rappel();
  };
  return etat;
}

/** Lecteur du temps simulé, de 0 à `duree` minutes. En direct (jumeau numérique), l'instant
 * suit l'heure réelle : `etendre` reçoit la durée de chaque nouvelle scène, et l'instant avance
 * d'une minute par minute réelle au-delà ; aller à un instant quitte le direct. */
export function creerLecteur(duree, instantInitial) {
  const borner = (t) => (Number.isFinite(t) ? Math.max(0, Math.min(lecteur.duree, t)) : 0);
  const lecteur = magasin({ t: 0, lecture: false, vitesse: VITESSE_DEFAUT, duree, comptes: {},
    direct: false, dureeRecue: duree, recue: performance.now() });
  lecteur.t = borner(instantInitial);
  lecteur.aller = (t) => {
    lecteur.direct = false;
    lecteur.t = borner(t);
    lecteur.notifier();
  };
  lecteur.basculer = () => {
    if (!lecteur.lecture && lecteur.t >= lecteur.duree) lecteur.t = 0;
    lecteur.direct = false;
    lecteur.lecture = !lecteur.lecture;
    lecteur.notifier();
  };
  lecteur.regler = (vitesse) => {
    lecteur.vitesse = vitesse;
    lecteur.notifier();
  };
  lecteur.etendre = (nouvelle, maintenant = performance.now()) => {
    Object.assign(lecteur, { duree: nouvelle, dureeRecue: nouvelle, recue: maintenant });
    lecteur.t = lecteur.direct ? lecteur.t : borner(lecteur.t);
    lecteur.notifier();
  };
  lecteur.suivreDirect = (maintenant = performance.now()) => {
    Object.assign(lecteur, { direct: true, lecture: false });
    lecteur.avancer(0, maintenant);
  };
  lecteur.avancer = (secondes, maintenant = performance.now()) => {
    if (lecteur.direct) {
      lecteur.t = lecteur.dureeRecue + (maintenant - lecteur.recue) / MS_PAR_MINUTE;
      lecteur.duree = Math.max(lecteur.duree, lecteur.t);
      lecteur.notifier();
      return;
    }
    if (!lecteur.lecture) return;
    const fin = lecteur.duree;
    lecteur.t = Math.min(fin, lecteur.t + lecteur.vitesse * Math.min(secondes, PAS_MAX_S));
    if (lecteur.t >= fin) lecteur.lecture = false;
    lecteur.notifier();
  };
  lecteur.publierCompte = (type, nombre) => {
    if (lecteur.comptes[type] === nombre) return;
    lecteur.comptes = { ...lecteur.comptes, [type]: nombre };
    lecteur.notifier();
  };
  return lecteur;
}

/** Objet survolé (ou null) et position du pointeur dans la page. */
export function creerSurvol() {
  const survol = magasin({ objet: null, x: 0, y: 0 });
  survol.montrer = (objet, x, y) => {
    Object.assign(survol, { objet, x, y });
    survol.notifier();
  };
  survol.cacher = (type = null) => {
    // le pointeur peut passer d'un type d'objet à un autre : ne cacher que le type quitté
    if (survol.objet === null || (type !== null && survol.objet.type !== type)) return;
    survol.objet = null;
    survol.notifier();
  };
  return survol;
}

/** Objet sélectionné, ou null. */
export function creerSelection() {
  const selection = magasin({ objet: null });
  selection.choisir = (objet) => {
    if (selection.objet === objet) return;
    selection.objet = objet;
    selection.notifier();
  };
  return selection;
}

/** Abonnement au magasin ralenti : au plus un rappel toutes les `ms` millisecondes, et un
 * dernier rappel après une rafale (l'état final est toujours vu). Pour les panneaux dont le
 * contenu coûte plus qu'une horloge. */
export function ralentir(etat, ms) {
  return (rappel) => {
    let dernier = 0;
    let attente = null;
    const appeler = () => {
      attente = null;
      dernier = performance.now();
      rappel();
    };
    const desabonner = etat.abonner(() => {
      if (attente !== null) return;
      const reste = dernier + ms - performance.now();
      if (reste <= 0) appeler();
      else attente = setTimeout(appeler, reste);
    });
    return () => {
      clearTimeout(attente);
      desabonner();
    };
  };
}
