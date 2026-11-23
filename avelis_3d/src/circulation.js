// Véhicules du décor au temps simulé (ne représentent aucune donnée) : tout se lit à l'instant t
// de l'horloge, donc va plus vite quand la lecture accélère et s'arrête à la pause. Sur le
// parking VL, chaque jour : des permanents garés jour et nuit ; les équipes (PERSONNEL) qui
// arrivent peu à peu le matin ou en début d'après-midi, se garent, puis repartent peu à peu ;
// une sortie à midi ; quelques visiteurs. Sur la route publique, des voitures, camionnettes et
// camions de passage, dans les deux sens. Tirage à graine fixe, jour par jour.
import { CIRCULATION_VL, CIEL_JOUR, MODELES_VL, PERSONNEL, VOITURE } from "./apparence.js";
import {
  aDroite, aleatoire, cheminVersLaPlace, parcoursVoiture, placesDuParkingVl, poseSurParcours,
} from "./decor.js";

const MINUTES_PAR_HEURE = 60;
const SECONDES_PAR_MINUTE = 60;
const MODELES_PERSONNEL = ["citadine", "berline", "suv", "camionnette"];
export const MODELES_ROUTE = ["berline", "citadine", "camionnette", "camion"];

/** Durée (min simulées) d'un parcours de `longueur` m à `vitesse` m/s. */
const duree = (longueur, vitesse) => longueur / vitesse / SECONDES_PAR_MINUTE;

/** Tirage dans l'intervalle [a, b]. */
const entre = (tirage, [a, b]) => a + tirage() * (b - a);

/** Modèle d'une voiture du personnel, tiré selon le poids de chaque modèle. */
function modeleTire(tirage) {
  const total = MODELES_PERSONNEL.reduce((s, m) => s + MODELES_VL[m].poids, 0);
  let reste = tirage() * total;
  for (const m of MODELES_PERSONNEL) {
    reste -= MODELES_VL[m].poids;
    if (reste < 0) return m;
  }
  return MODELES_PERSONNEL[0];
}

/** Parcours d'arrivée et de départ {aller, retour} d'une place : sur leur voie, à droite ; la
 * sortie de la place se fait en marche arrière (premier tronçon du retour). */
function parcoursDeLaPlace(site, place) {
  const chemin = cheminVersLaPlace(site, place);
  const inverse = [...chemin].reverse();
  const { voieSite } = CIRCULATION_VL;
  return { aller: parcoursVoiture([...aDroite(chemin.slice(0, -1), voieSite), chemin.at(-1)]),
    retour: parcoursVoiture([inverse[0], ...aDroite(inverse.slice(1), voieSite)]) };
}

/** Circulation du site : {site, temps, graine, places, parcours (par place), route (un parcours
 * par sens), jours (cache)}. */
export function creerCirculation(site, temps, graine) {
  const places = site.parking_vl ? placesDuParkingVl(site.parking_vl).places : [];
  const route = [site.route_publique, [...site.route_publique].reverse()]
    .map((r) => parcoursVoiture(aDroite(r, CIRCULATION_VL.decalageVoie)));
  return { site, temps, graine, places, route, jours: new Map(),
    parcours: places.map((place) => parcoursDeLaPlace(site, place)) };
}

/** Instant t (min simulées) de l'heure h de l'horloge du jour `jour`. */
export function instantDeLHeure(temps, jour, h) {
  return jour * temps.minutes_jour + (h - temps.heure_ouverture) * MINUTES_PAR_HEURE;
}

/** Demandes de stationnement du jour {arrivee, depart (h), personnel, bureaux, modele} :
 * équipes, sorties de midi (deux séjours), visiteurs ; départs avant la nuit. */
function demandesDuJour(nombrePlaces, tirage) {
  const demandes = [];
  const nuit = CIEL_JOUR.coucher;
  const { pause, visiteurs } = PERSONNEL;
  for (const equipe of PERSONNEL.equipes) {
    for (let k = 0; k < Math.round(equipe.part * nombrePlaces); k++) {
      const base = { personnel: true, bureaux: tirage() < equipe.bureaux,
        modele: modeleTire(tirage) };
      const [arrivee, depart] = [entre(tirage, equipe.arrivee),
        Math.min(nuit, entre(tirage, equipe.depart))];
      if (equipe.nom === "journée" && tirage() < pause.part) {
        demandes.push({ ...base, arrivee, depart: entre(tirage, pause.depart) },
          { ...base, arrivee: entre(tirage, pause.retour), depart });
      } else demandes.push({ ...base, arrivee, depart });
    }
  }
  for (let k = 0; k < visiteurs.nombre; k++) {
    const arrivee = entre(tirage, visiteurs.heures);
    demandes.push({ personnel: false, bureaux: true, arrivee,
      depart: Math.min(nuit, arrivee + entre(tirage, visiteurs.duree)),
      modele: tirage() < visiteurs.camionnettes ? "camionnette" : modeleTire(tirage) });
  }
  return demandes.sort((a, b) => a.arrivee - b.arrivee);
}

/** Séjour sur une place libre {id, place, modele, teinte, libelle, personnel, bureaux, arrivee,
 * depart (t), aller, retour}, ou null si toutes les places sont prises à son arrivée.
 * `libres` : instant où chaque place se libère. */
function garer(circulation, jour, demande, libres, tirage) {
  const { temps } = circulation;
  const [arrivee, depart] = [instantDeLHeure(temps, jour, demande.arrivee),
    instantDeLHeure(temps, jour, demande.depart)];
  const candidates = libres.map((fin, i) => [fin, i]).filter(([fin]) => fin <= arrivee);
  if (!candidates.length) return null;
  const [, place] = candidates[Math.floor(tirage() * candidates.length)];
  const { aller, retour } = circulation.parcours[place];
  libres[place] = depart + duree(retour.longueur, CIRCULATION_VL.vitesse);
  return { place, modele: demande.modele, teinte: Math.floor(tirage() * VOITURE.couleurs.length),
    libelle: demande.personnel ? "Voiture du personnel" : MODELES_VL[demande.modele].libelle,
    personnel: demande.personnel, bureaux: demande.bureaux, arrivee, depart, aller, retour };
}

/** Séjours du jour sur le parking VL : permanents (toujours les mêmes places, arrivés avant et
 * repartis après), puis les demandes du jour, chacune sur une place libre. */
function sejoursDuJour(circulation, jour) {
  const { places, graine } = circulation;
  if (!places.length) return [];
  const fixe = aleatoire(graine);
  const permanents = new Set();
  const nombre = Math.round(PERSONNEL.permanents * places.length);
  while (permanents.size < nombre) permanents.add(Math.floor(fixe() * places.length));
  const libres = places.map((_, i) => (permanents.has(i) ? Infinity : -Infinity));
  const sejours = [...permanents].map((place) => ({ place, modele: modeleTire(fixe),
    teinte: Math.floor(fixe() * VOITURE.couleurs.length), libelle: "Voiture du personnel",
    personnel: true, bureaux: false, arrivee: -Infinity, depart: Infinity,
    ...circulation.parcours[place] }));
  const tirage = aleatoire(graine * 31 + jour + 1);
  for (const demande of demandesDuJour(places.length, tirage)) {
    const sejour = garer(circulation, jour, demande, libres, tirage);
    if (sejour) sejours.push(sejour);
  }
  return sejours.map((s, k) => ({ ...s, id: `VL-${jour}-${k}` }));
}

/** Passages du jour sur la route publique {id, modele, teinte, libelle, debut (t), parcours} :
 * CIRCULATION_VL.parHeure par heure de la journée affichée et par modèle (la part
 * CIRCULATION_VL.partNuit la nuit), à des instants tirés. */
function passagesDuJour(circulation, jour) {
  const { temps, route, graine } = circulation;
  const tirage = aleatoire(graine * 53 + jour + 7);
  const passages = [];
  const heures = temps.minutes_jour / MINUTES_PAR_HEURE;
  for (let k = 0; k < heures; k++) {
    const h = temps.heure_ouverture + k;
    const facteur = h >= CIEL_JOUR.coucher || h < CIEL_JOUR.lever ? CIRCULATION_VL.partNuit : 1;
    for (const modele of MODELES_ROUTE) {
      const nombre = Math.floor(CIRCULATION_VL.parHeure[modele] * facteur + tirage());
      for (let n = 0; n < nombre; n++) {
        passages.push({ modele, teinte: Math.floor(tirage() * VOITURE.couleurs.length),
          libelle: modele === "camion" ? "Camion" : MODELES_VL[modele].libelle,
          debut: instantDeLHeure(temps, jour, h + tirage()),
          parcours: route[tirage() < 0.5 ? 0 : 1] });
      }
    }
  }
  return passages.sort((a, b) => a.debut - b.debut)
    .map((p, k) => ({ ...p, id: `ROUTE-${jour}-${k}` }));
}

/** Séjours et passages du jour (calculés une fois). */
export function circulationDuJour(circulation, jour) {
  if (!circulation.jours.has(jour)) {
    circulation.jours.set(jour, { sejours: sejoursDuJour(circulation, jour),
      passages: passagesDuJour(circulation, jour) });
  }
  return circulation.jours.get(jour);
}

/** Pose {x, y, angle} de la voiture d'un séjour à l'instant t, ou null (pas encore arrivée,
 * ou repartie) : elle roule de son arrivée au bout de l'aller, reste garée, puis repart. */
export function poseDuSejour({ arrivee, depart, aller, retour }, t) {
  const v = CIRCULATION_VL.vitesse * SECONDES_PAR_MINUTE; // m par minute simulée
  if (t < arrivee) return null;
  if (t < depart) {
    return poseSurParcours(aller, Math.min(aller.longueur, (t - arrivee) * v), false);
  }
  const d = (t - depart) * v;
  if (d >= retour.longueur) return null;
  return poseSurParcours(retour, d, d < retour.cumuls[1]);
}

/** Pose {x, y, angle} d'un passage sur la route publique à l'instant t, ou null. */
export function poseDuPassage({ debut, parcours }, t) {
  const d = (t - debut) * CIRCULATION_VL.vitesseRoute * SECONDES_PAR_MINUTE;
  if (d < 0 || d >= parcours.longueur) return null;
  return poseSurParcours(parcours, d, false);
}

/** Véhicules visibles à l'instant t : [{vehicule (séjour ou passage), pose}]. */
export function vehiculesA(circulation, t) {
  const jour = Math.floor(t / circulation.temps.minutes_jour);
  const { sejours, passages } = circulationDuJour(circulation, jour);
  const visibles = [];
  for (const vehicule of sejours) {
    const pose = poseDuSejour(vehicule, t);
    if (pose) visibles.push({ vehicule, pose });
  }
  for (const vehicule of passages) {
    if (vehicule.debut > t) break; // triés par début
    const pose = poseDuPassage(vehicule, t);
    if (pose) visibles.push({ vehicule, pose });
  }
  return visibles;
}

/** Durée (min simulées) de l'aller d'un séjour : instant où la voiture est garée. */
export function dureeAller(sejour) {
  return duree(sejour.aller.longueur, CIRCULATION_VL.vitesse);
}
