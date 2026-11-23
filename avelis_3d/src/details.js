// Contenu du panneau de détail, de la timeline de traçabilité et des onglets Quais / Camions /
// Stocks, calculé sans React (testé par « npm test »). Tout vient de la scène : événements de
// traçabilité et liens des objets, positions de référence (etatObjet), arrêts à quai.
import { groupesDeQuais, libelleObjet } from "./apparence.js";
import { etatObjet, horlogeCourte, segmentActif } from "./donnees.js";
import { valeursPilotage } from "./pilotage.js";
import { arretEnCours, quaiDuSegment } from "./trajectoires.js";

// États d'une étape de la timeline : lue et déjà affichée par l'outil de pilotage ; survenue,
// lue, mais pas encore affichée (délai de la technologie) ; survenue sans être lue ; pas encore
// survenue ; position simulée (arrêt à quai d'un camion : un déplacement, pas une lecture).
export const ETATS = {
  affichee: "Lue et affichée", attente: "Lue, affichage à venir", non_lue: "Non lue",
  a_venir: "À venir", position: "Position simulée",
};
const TERMINALES = { module: "Expédié", pod: "Intégré au module" };
const LIBELLES_LIENS = { module: "Module", pod: "Pod", "kit 2D": "Kit 2D", lot: "Lot",
  camion: "Camion", modules: "Modules" };
// Zones de stock et valeur du tableau de pilotage qui les décrit (pilotage.js)
const STOCKS_PILOTES = { "Stock matières": ["stock_matieres", "kit", "kits"],
  "Stock produits finis": ["stock_pf", "produit fini", "produits finis"] };

/** Étape d'un point de contrôle : son événement (s'il est survenu à l'instant t) et son état. */
function etape(nom, evenement, t, temps) {
  if (!evenement || evenement[0] > t) return { nom, etat: "a_venir", heure: null, zone: null };
  const [instant, , zone, affichage, message] = evenement;
  const etat = affichage === null ? "non_lue" : affichage <= t ? "affichee" : "attente";
  return { nom, etat, heure: horlogeCourte(instant, temps), zone, message,
    affichage: affichage === null ? null : horlogeCourte(affichage, temps) };
}

/** Étapes déduites des arrêts à quai d'un camion (position simulée, pas une lecture). */
function etapesDeQuai(objet, t, contexte, temps) {
  const etapes = [];
  objet.segments.forEach(([debut, fin], i) => {
    const quai = quaiDuSegment(objet, i, contexte);
    if (!quai) return;
    for (const [nom, instant] of [[`À quai ${quai.numero}`, debut],
      [`Départ du quai ${quai.numero}`, fin]]) {
      const survenue = instant !== null && instant <= t;
      etapes.push({ nom, etat: survenue ? "position" : "a_venir", zone: null, instant,
        heure: survenue ? horlogeCourte(instant, temps) : null });
    }
  });
  return etapes;
}

/** Étapes d'un chariot élévateur (décor de la logistique, pas une lecture) : ses événements
 * du jour de l'instant t, en position simulée une fois survenus. */
function etapesDuChariot(objet, t, temps) {
  const jour = Math.floor(t / temps.minutes_jour);
  return objet.evenements.filter((e) => Math.floor(e[0] / temps.minutes_jour) === jour)
    .map(([instant, nom, zone, , message]) => (instant <= t
      ? { nom, etat: "position", heure: horlogeCourte(instant, temps), zone, message, instant }
      : { nom, etat: "a_venir", heure: null, zone: null, instant }));
}

/** Étapes {nom, etat, heure, zone, affichage, message} de la timeline de l'objet à l'instant t,
 * et l'indice de l'étape courante (la dernière survenue, −1 avant la première). Module et pod :
 * leurs points de contrôle obligatoires ; camion : ses événements, puis ses arrêts à quai ;
 * chariot élévateur : ses événements du jour ; autres : leurs événements. */
export function etapesTracabilite(scene, objet, t, contexte) {
  const { temps, tracabilite } = scene;
  const points = { module: tracabilite.points_module, pod: tracabilite.points_pod }[objet.type];
  let etapes;
  if (objet.type === "chariot") etapes = etapesDuChariot(objet, t, temps);
  else if (points) {
    etapes = points.map((nom) => etape(nom, objet.evenements.find((e) => e[1] === nom), t, temps));
  } else {
    etapes = objet.evenements.map((e) => ({ ...etape(e[1], e, t, temps), instant: e[0] }));
    if (objet.type === "camion") {
      etapes = [...etapes, ...etapesDeQuai(objet, t, contexte, temps)]
        .sort((a, b) => (a.instant ?? Infinity) - (b.instant ?? Infinity));
    }
  }
  return { etapes, courante: etapes.findLastIndex((e) => e.etat !== "a_venir") };
}

/** Alertes visant l'objet, déjà affichées à l'instant t. */
export function alertesDeLObjet(scene, objet, t) {
  return scene.tracabilite.alertes.filter((a) => a[3] === objet.id && a[1] <= t);
}

/** Zone {nom, libelle} du site qui contient le point (la plus petite), ou null. */
export function zoneDuPoint(site, x, y) {
  const dedans = site.zones.filter((z) => x >= z.x && x <= z.x + z.largeur && y >= z.y
    && y <= z.y + z.profondeur);
  return dedans.reduce((a, b) => (!a || b.largeur * b.profondeur < a.largeur * a.profondeur
    ? b : a), null);
}

/** Où est l'objet à l'instant t : « À quai n », « En route », le nom de sa zone, « Sur la
 * voirie », ou « Hors du site » s'il est masqué. */
export function lieuDeLObjet(scene, objet, t, contexte) {
  const i = segmentActif(objet, t);
  if (i < 0) return "Hors du site";
  const quai = quaiDuSegment(objet, i, contexte);
  if (quai) return `À quai ${quai.numero}`;
  if (objet.segments[i][2].length > 1) return "En route";
  const { x, y } = etatObjet(objet, t);
  return zoneDuPoint(scene.site, x, y)?.libelle ?? "Sur la voirie";
}

/** Statut {texte, ton} : dernière alerte affichée depuis la dernière étape survenue ; sinon
 * cette étape (« bon » si c'est la dernière de son parcours) ; sinon son lieu (« En route »…). */
export function statutObjet(scene, objet, t, contexte) {
  const { etapes, courante } = etapesTracabilite(scene, objet, t, contexte);
  const derniere = etapes[courante];
  const alertes = alertesDeLObjet(scene, objet, t);
  const alerte = alertes.at(-1);
  const instantEtape = objet.evenements.find((e) => e[1] === derniere?.nom)?.[0] ?? -Infinity;
  if (alerte && alerte[0] >= instantEtape) return { texte: alerte[2], ton: "alerte" };
  if (!derniere) return { texte: lieuDeLObjet(scene, objet, t, contexte), ton: "neutre" };
  const ton = derniere.nom === TERMINALES[objet.type] ? "bon" : "en_cours";
  return { texte: derniere.nom, ton };
}

/** Progression {faits, total, affiches} des points obligatoires (module, pod), ou null. */
export function progression(scene, objet, t, contexte) {
  if (!(objet.type in TERMINALES)) return null;
  const { etapes } = etapesTracabilite(scene, objet, t, contexte);
  return { total: etapes.length, faits: etapes.filter((e) => e.etat !== "a_venir").length,
    affiches: etapes.filter((e) => e.etat === "affichee").length };
}

/** Lignes {nom, valeur, liens?} du tableau de propriétés ; `liens` : identifiants cliquables. */
export function proprietes(scene, objet, t, contexte) {
  const survenus = objet.evenements.filter((e) => e[0] <= t);
  const affiches = survenus.filter((e) => e[3] !== null && e[3] <= t);
  const lignes = [
    { nom: "Type", valeur: libelleObjet(objet.type, scene.scenario.schema) },
    { nom: "Description", valeur: objet.libelle },
    { nom: "Lieu", valeur: lieuDeLObjet(scene, objet, t, contexte) },
    { nom: "Événements", valeur: objet.type === "chariot" ? `${survenus.length} survenus`
      : `${affiches.length} affichés sur ${survenus.length} survenus` },
    { nom: "Alertes", valeur: String(alertesDeLObjet(scene, objet, t).length) },
  ];
  const charge = objet.type === "chariot" && objet.charges[segmentActif(objet, t)];
  if (charge) lignes.push({ nom: "Charge", valeur: charge.id, liens: [charge.id] });
  for (const [cle, valeur] of Object.entries(objet.liens ?? {})) {
    const liens = Array.isArray(valeur) ? valeur : [valeur];
    lignes.push({ nom: LIBELLES_LIENS[cle] ?? cle, valeur: liens.join(", "), liens });
  }
  return lignes;
}

/** Quais {numero, fonction, camion, statut, ton} à l'instant t : libre, ou déchargement
 * (fourgon) ou chargement (plateau, camion EXP-) du camion à quai. */
export function listeQuais(scene, arrets, t) {
  const fonctions = groupesDeQuais(scene.site.quais).flatMap(([nom, { nombre }]) =>
    Array(nombre).fill(nom.replace(/^Quais (de |d')?/, "")));
  return [...arrets.keys()].sort((a, b) => a - b).map((numero) => {
    const camion = arretEnCours(arrets.get(numero), t)?.objet ?? null;
    const statut = !camion ? "Libre" : camion.id.startsWith("EXP-") ? "Chargement"
      : "Déchargement";
    return { numero, fonction: fonctions[numero - 1] ?? "", camion, statut,
      ton: camion ? "en_cours" : "neutre" };
  });
}

/** Camions visibles à l'instant t {objet, role, lieu, ton}, à quai d'abord, puis par
 * identifiant. */
export function listeCamions(scene, t, contexte) {
  const ordre = (c) => (c.ton === "bon" ? 0 : c.ton === "en_cours" ? 1 : 2);
  return scene.objets.filter((o) => o.type === "camion" && segmentActif(o, t) >= 0)
    .map((objet) => {
      const lieu = lieuDeLObjet(scene, objet, t, contexte);
      const ton = lieu.startsWith("À quai") ? "bon" : lieu === "En route" ? "en_cours"
        : "attente";
      return { objet, role: objet.id.startsWith("EXP-") ? "Expédition" : "Fournisseur", lieu,
        ton };
    })
    .sort((a, b) => ordre(a) - ordre(b) || a.objet.id.localeCompare(b.objet.id));
}

/** Zones de stock {zone, valeur, unite, objets: [[type, nombre]]} à l'instant t : valeur du
 * tableau de pilotage quand il la donne, et objets visibles posés dans la zone. */
export function listeStocks(scene, t) {
  const pilotage = valeursPilotage(scene, t);
  const zones = scene.site.zones.filter((z) => z.nom.startsWith("Stock"));
  const comptes = new Map(zones.map((z) => [z.nom, new Map()]));
  for (const objet of scene.objets) {
    if (objet.type === "camion") continue;
    const etat = etatObjet(objet, t);
    const zone = etat && zoneDuPoint(scene.site, etat.x, etat.y);
    const compte = zone && comptes.get(zone.nom);
    if (compte) compte.set(objet.type, (compte.get(objet.type) ?? 0) + 1);
  }
  return zones.map((zone) => {
    const [cle, singulier, pluriel] = STOCKS_PILOTES[zone.nom] ?? [null, null, null];
    const valeur = cle ? pilotage[cle] : null;
    return { zone: zone.libelle, valeur, unite: valeur > 1 ? pluriel : singulier,
      objets: [...comptes.get(zone.nom)] };
  });
}
