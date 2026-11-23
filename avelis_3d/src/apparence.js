// Apparence de la vue 3D. Les couleurs des objets sont celles de la vue 2 (avelis_flux/app.py,
// MARQUEURS), pour que les deux vues se lisent de la même façon. Les tailles ci-dessous sont des
// choix de dessin, pas des données du site : celles-ci viennent toutes de la scène.

export const COULEURS_OBJETS = {
  camion: "#52514e",
  lot: "#2a78d6",
  "kit 2D": "#86b6ef",
  pod: "#eb6834",
  module: "#6250d6",
  chariot: "#f2b42c", // chariots élévateurs (vue 3D seule)
};
export const COULEUR_SURVOL = "#d55181"; // couleur du suivi dans la vue 2

// Palette « maquette » : violet Avelis, accent orange, blanc, beige carton ; sol et routes gris
// bleuté très clairs, marquages blancs, lignes de zones jaune-orangé.
export const PALETTE = { violet: "#3d2a7a", orange: "#e06a2c", blanc: "#ffffff",
  carton: "#d8b88a" };

export const COULEURS_PLAN = {
  fond: "#eef0f6", // ciel et brouillard : le sol lointain s'y fond
  sol: "#e3e6ef",
  site: "#f7f8fb",
  extensionLibre: "#eaecf3",
  bordure: "#c9cfdf", // bord du foncier
  routePublique: "#cbd1e1",
  voirie: "#c3cadc",
  parkingVl: "#cfd5e4", // dalle du parking des véhicules légers
  marquage: "#ffffff",
  ligneZone: "#f0a33c", // zones à ciel ouvert et emplacements des quais
  reperes: PALETTE.violet,
};

/** Libellé d'un type d'objet ; en schéma satellites, ce qui sort de l'assemblage est un kit. */
export function libelleObjet(type, schema, pluriel = false) {
  const libelles = {
    camion: ["Camion", "Camions"],
    lot: ["Lot fournisseur", "Lots fournisseurs"],
    "kit 2D": ["Kit 2D", "Kits 2D"],
    pod: ["Pod", "Pods"],
    module: schema === "satellites" ? ["Kit module", "Kits modules"] : ["Module 3D", "Modules 3D"],
    chariot: ["Chariot élévateur", "Chariots élévateurs"],
  };
  return libelles[type][pluriel ? 1 : 0];
}

export const LIBELLES_SCHEMAS = { unique: "Usine unique", satellites: "Usine mère + satellites" };
export const NOMS_COURTS_IMPLANTATIONS = {
  "Proposée : Torcy + extension (flux en U)": "Proposée (Torcy + extension)",
  "Actuelle : site seul (sans extension)": "Actuelle (site seul)",
};

// Minutes simulées par seconde : celles de la vue 2, et trois plus lentes, où l'on voit les
// camions rouler et manœuvrer à quai (une marche arrière dure environ 0,12 min simulée)
export const VITESSES = [0.05, 0.2, 1, 5, 15, 30, 60, 120, 240];
export const VITESSE_DEFAUT = 30;
// Curseur de temps maintenu appuyé : sans bouger de plus de `tolerance` px pendant `delai` ms,
// il passe en réglage fin, où un pixel vaut `minutesParPixel` min simulées (pas d'une minute) ;
// le pouce du curseur fait `pouce` px (style.css).
export const CURSEUR_FIN = { delai: 350, tolerance: 4, minutesParPixel: 0.25, pouce: 16 };

// Dessin, en mètres
export const LARGEUR_ROUTE_PUBLIQUE = 9;
export const EPAISSEUR_SOL = 0.08; // dalles, routes et zones
// Quai : emplacement (largeur × longueur) ; sa place au sol fait une longueur de camion plus
// `marge` m, `enLong` m de large pour un camion garé en long (quai à ciel ouvert)
export const QUAI = { largeur: 4.5, longueur: 4, marge: 1, enLong: 3.6 };
// Survol : l'objet se soulève de `soulevement` m en `duree` s et se détoure (`contour` px).
// Sélection (clic) : anneau au sol autour de l'objet, à `marge` m de son emprise, qui palpite
// (`ampleur` de sa taille, `periode` s) ; pilule à `pilule` m au-dessus de lui. Épingles à
// `hauteur` m au-dessus des camions à quai ; la pilule d'un camion à quai passe au-dessus de son
// épingle, à `ecart` px. Un clic où le pointeur a bougé de plus de `clic` px termine un glisser
// (vue tournée) : il ne sélectionne rien.
export const SURVOL = { soulevement: 0.6, duree: 0.12, contour: 3 };
export const SELECTION = { marge: 1.2, epaisseur: 0.45, arrondi: 1.4, ampleur: 0.05,
  periode: 1.6, opacite: 0.9, couleur: PALETTE.orange, pilule: 2.5, clic: 4 };
export const EPINGLE = { hauteur: 2.5, ecart: 4 };

// Couche visuelle des trajectoires (trajectoires.js) : virages arrondis (rayon en m, finesse
// des arcs en rad), accélération et freinage sur la part `rampe` de la durée d'un trajet à côté
// d'un arrêt. Manœuvre de quai : l'arrière du camion suit une courbe de Bézier (tangentes de
// `tangente` fois sa corde, `pointsManoeuvre` points) qui tourne d'un quart de tour sur
// `braquage` m au moins ; la marche arrière est `lenteurArriere` fois plus lente ; à quai,
// l'arrière touche les butoirs de la porte (saillie `recul` m, formesBatiments.js) ; il dépasse
// l'entrée du quai de `depassementMax` m au plus. Quai en long (à ciel ouvert) : changement de
// voie sur `changementDeVoie` m de route.
export const TRAJECTOIRES = { rayonVirage: 6, pasArc: Math.PI / 24, rampe: 0.2, braquage: 3,
  tangente: 0.39, pointsManoeuvre: 24, lenteurArriere: 2, recul: 0.3, depassementMax: 8,
  changementDeVoie: 14 };

// Déplacement au clavier (clavier.js, Camera.jsx) : la largeur de la vue en `traversee` s,
// `rapide` fois plus vite avec Maj ; rotation en rad/s ; vitesse établie en `inertie` s ; la
// cible de la caméra reste à moins de `bord` étendue du site de son centre.
export const NAVIGATION = { traversee: 2.5, rapide: 3, rotation: 1.6, inertie: 0.12,
  bord: 0.75 };
// Altitude (m) de chaque couche du sol, pour qu'elles ne se recouvrent pas à l'écran
export const Z = { sol: -0.3, site: 0, routePublique: 0.06, voirie: 0.12, zone: 0.18, quai: 0.26 };
// Objets et engins posés sur le dessus des dalles des zones (le plus haut des sols) : rien ne s'y
// enfonce, et ils ne flottent que de quelques centimètres au-dessus des routes
export const Z_POSE = Z.zone + EPAISSEUR_SOL / 2;
// Tracés au sol : tirets blancs des routes, bord du foncier (en tirets si l'extension n'est pas
// utilisée), lignes des zones à ciel ouvert et des quais. Largeurs, longueurs, épaisseur en m.
export const TIRETS_ROUTE = { largeur: 0.3, trait: 3, vide: 3 };
export const BORDURE = { largeur: 0.6, trait: 4, vide: 3 };
export const LIGNE_ZONE = { largeur: 0.35 };
export const EPAISSEUR_TRACE = 0.02;
// Ombre de contact : tache estompée sous chaque objet, débordant de `marge` m
export const OMBRE_CONTACT = { marge: 1.6, opacite: 0.34, couleur: "#2a2350" };
// Occlusion ambiante (GTAOPass) : rayon en m, intensité du mélange ; calculée à une fraction de
// la résolution de l'écran, avec moins d'échantillons que par défaut (16), pour 60 images/s
export const OCCLUSION = { rayon: 2.5, epaisseur: 2, echelle: 1, intensite: 0.85,
  resolution: 0.5, echantillons: 12 };
export const PORTAIL = { cote: 1.2, hauteur: 3 };
// Repères hors du foncier, là où la vue d'ensemble des trois implantations les montre, aux deux
// tailles contrôlées (tests/etiquettes.test.js) : nord au-dessus de la pointe nord, échelle au
// sud. Pas aux places de la vue 2 : sous la vue isométrique, elles tombent sous les cartes.
export const NORD = { x: 215, y: 335, longueur: 22 };
export const ECHELLE = { x: 250, y: 30, longueur: 50, largeur: 1.5 };
export const ECART_REPERES = 4; // m gardés libres de tout décor autour des repères

/** [libellé, quais] de chaque groupe de quais : un seul groupe s'ils sont partagés. */
export function groupesDeQuais(quais) {
  return quais.partages
    ? [["Quais partagés", quais.reception]]
    : [["Quais de réception", quais.reception], ["Quais d'expédition", quais.expedition]];
}

// Bâtiments (batiments.js, Batiments.jsx) : murs en tôle nervurée blanche sur un soubassement
// violet, toits de la couleur de leur zone (celle de la légende). Halls à toit à deux pans dont
// le faîtage suit le plus grand côté, sous un lanterneau filant ; bureaux à toit plat derrière
// un acrotère, à bandeaux vitrés et groupes froids. Longueurs en m, pente en degrés.
export const CATEGORIE_BUREAUX = "Accueil et pilotage";
export const PREFIXE_STOCKS = "Stock"; // zones où le décor pose des racks
export const BATIMENT = {
  epaisseurMur: 0.4, soubassement: 1.1, saillie: 0.05, pasNervure: 0.9, nervure: 0.6,
  pente: 8, flecheMax: 6, debord: 0.6, epaisseurToit: 0.35, lanterneau: 2.4,
  acrotere: 1, etage: 4, vitrage: 1.6, retraitVitrage: 2,
  coupe: 2.5, // hauteur des murs coupés en mode « Intérieurs »
  dureeOuverture: 0.6, // s, passage d'un mode à l'autre
};
export const COULEURS_BATIMENT = {
  murs: "#f7f7fb", soubassement: PALETTE.violet, lanterneau: "#e4eaf7", vitrage: "#56609c",
  baie: "#2a2440", // intérieur sombre d'une porte ouverte
  sas: "#5a5668", tablier: "#d9dbe4", butoir: "#1f1d24", borne: PALETTE.orange,
  plaque: PALETTE.blanc, numero: PALETTE.violet,
};
// Portes de quai : sur le mur d'un bâtiment à au plus `distanceMax` m du quai ; sas d'étanchéité
// autour, tablier relevé, butoirs, bornes orange de part et d'autre, plaque numérotée au-dessus
export const PORTE = { largeur: 3, bas: 1.1, haut: 4.3, distanceMax: 6, cadre: 0.35, sas: 0.5,
  plaque: [1.7, 1.7], borne: { rayon: 0.18, hauteur: 1.2, ecart: 0.9, avancee: 1.2 } };
export const NUMERO_QUAI = 2.4; // hauteur des numéros peints au sol des quais
// Logo Avelis sur les murs sud et ouest des hangars `halls` : hauteur `cote` (m), largeur
// `cote × rapport`, réduite à `partMur` de la longueur du mur ; `marge` sous le haut du mur.
// `nord` : hangars qui l'ont aussi sur leur face nord ; `estSiteSeul` : sur leur face est, dans
// l'implantation actuelle (site seul, reconnue à son extension non utilisée).
export const EMBLEME = { cote: 4, rapport: 3.6, partMur: 0.8, marge: 1.2,
  halls: ["Stock produits finis", "Assemblage 3D", "Ligne pods", "Réception"],
  nord: ["Assemblage 3D"], estSiteSeul: ["Kitting"] };
// Grande porte de marchandises (porte sectionnelle de plain-pied) sur le mur qui fait face à
// chaque groupe de quais, à au plus `distanceMax` m ; `lames` : nombre de lames du tablier.
export const GRANDE_PORTE = { largeur: 5, hauteur: 5, distanceMax: 20, cadre: 0.3, lames: 6,
  couleur: "#c4c8d6", lame: "#9fa4b8", balise: PALETTE.orange };
// Porte piétonne de chaque bâtiment, mur sud, au quart de sa longueur (ou aux trois quarts si
// la place est prise) ; auvent au-dessus. `degagement` : place libre devant le mur. Portes
// piétonnes en plus sur la face nord (PORTES_NORD) : des bâtiments `toutes`, dans toutes les
// implantations ; de `siteSeul`, dans l'implantation actuelle seulement.
export const PORTE_PIETONNE = { largeur: 1.1, hauteur: 2.3, cadre: 0.12, degagement: 3,
  couleur: PALETTE.violet, cadreCouleur: "#e4e6ee", poignee: PALETTE.orange,
  auvent: { largeur: 1.9, avancee: 1, epaisseur: 0.12 } };
// Grandes portes de marchandises en plus des quais, par bâtiment : murs sud ou nord
export const GRANDES_PORTES_MURS = { "Kitting": ["nord"], "Stock matières": ["sud"],
  "Assemblage 3D": ["nord"], "Contrôle final": ["nord"] };
export const PORTES_NORD = { toutes: ["Assemblage 3D", "Kitting"],
  siteSeul: ["Bureaux / pilotage"] };
// Groupes froids sur les toits plats : caisson, deux ventilateurs, un tous les `pas` m
export const GROUPE_FROID = { longueur: 2.6, largeur: 1.4, hauteur: 1.2, pas: 4.5, nombreMax: 4,
  couleur: "#dfe2ea", ventilateur: "#5c5f6e" };

// Décor (decor.js, Decor.jsx) : arbres, clôture, racks. Jamais posé là où passe une route ou un
// objet de la scène ; tirage pseudo-aléatoire à graine fixe, toujours le même pour une scène.
export const GRAINE_DECOR = 2026;
export const ARBRES = {
  reculs: [7, 15], // m à l'extérieur du bord du foncier, deux rangs
  pas: 11, decalage: 2.5, // m entre deux arbres d'un rang, écart aléatoire autour
  bordRoute: 9.5, pasRoute: 13, // de part et d'autre de la route publique
  ecartMin: 6, margeFoncier: 3, margeVoie: 1.5,
  hauteur: [5, 8.5], rayon: [2.2, 3.4], tronc: 0.28,
  couleurs: ["#86b874", "#74a967", "#98c483"], couleurTronc: "#8c735e",
};
export const CLOTURE = { pas: 3, hauteur: 1.8, poteau: 0.12, marge: 1.2, opacite: 0.42,
  couleur: "#b9bfd1", couleurPoteaux: "#8e95aa" };
export const RACK = { baie: 2.8, profondeur: 1.1, niveaux: 3, etage: 2, recul: 1.2,
  retraitBout: 3, marge: 0.8, remplissage: 0.75, carton: [1.15, 0.95, 1.1], montant: 0.1,
  lisse: 0.12, couleurMontants: PALETTE.violet, couleurLisses: PALETTE.orange,
  couleurCartons: PALETTE.carton };

// Objets (objets.js, formesVehicules.js, formesCharges.js) : formes arrondies (aucune arête
// vive), à leur gabarit (celui de la scène), l'avant vers +x ; la couleur de leur type (celle de
// la vue 2) en accent : bandes des camions, palettes des lots, chevalets et sangles des kits 2D,
// socle et rebord des pods et des modules. Longueurs en m.
export const ARRONDI = 0.05; // rayon par défaut des arêtes
export const RUGOSITE_OBJETS = 0.8;
export const COULEURS_PIECES = { blanc: "#f5f5f9", vitre: "#2b2a3d", pneu: "#26252b",
  jante: "#c3c6d0", sombre: "#3a3944", gris: "#8d909e", clair: "#d9dbe4", phare: "#fff1c2",
  feu: "#d8464b", balise: PALETTE.orange };
// Semi-remorque : tracteur à cabine arrondie (vitrage enveloppant, calandre, phares,
// rétroviseurs), remorque fourgon (camions fournisseurs) ou plateau surbaissé à col de cygne
// (camions d'expédition, qui portent les modules chargés) ; essieux : avant et moteur depuis
// l'avant du tracteur, remorque depuis l'arrière.
export const CAMION = {
  cabine: { longueur: 2.4, hauteur: 3.1, bas: 0.6, rayon: 0.28 },
  vitrage: { bas: 1.95, haut: 2.85, profondeur: 1.15 },
  calandre: { bas: 0.95, haut: 1.7, largeur: 0.62 }, pareChocs: { bas: 0.45, haut: 0.85 },
  bande: { bas: 1.25, haut: 1.45 }, // bande d'accent de la cabine
  retro: { recul: 0.35, saillie: 0.3, bas: 2, haut: 2.6 },
  chassis: { bas: 0.45, haut: 1, largeur: 0.75 }, ecart: 0.3, // cabine ↔ remorque
  caisse: { bas: 1.2, bande: 0.45 },
  plateau: { col: 2.2, basCol: 1.15, hautCol: 1.5, bas: 0.8, haut: 1.05, jeu: 0.3 },
  roue: { rayon: 0.5, petite: 0.4, largeur: 0.3 },
  essieux: { avant: 1, moteur: 0.9, remorque: [1.4, 2.75, 4.1] },
};
// Lot : palettes (de la couleur du lot) chargées de cartons, en rangs sur son gabarit
export const PALETTE_CARTONS = { cote: 1.1, jeu: 0.15, hauteur: 0.14, semelle: 0.1, couches: 2,
  jeuCarton: 0.04, scotch: 0.07, teintes: ["#d8b88a", "#cdaa7a", "#e2c79c"],
  couleurScotch: "#ecdcbc" };
// Kit 2D : pile de panneaux posée sur des chevalets, cerclée de deux sangles
export const PANNEAUX = { chevalets: 4, hautChevalet: 0.5, poutre: 0.1, pied: 0.08,
  inclinaison: 14, nombre: 5, jeu: 0.035, retrait: 0.12, decalage: 0.05, sangle: 0.08,
  teintes: ["#f3f1ec", "#e4d5bd"] };
// Pod : cabine préfabriquée sur un socle, rebord de toit, porte sur sa face avant
export const POD = { socle: 0.18, rebord: 0.14, rayon: 0.12, porte: [0.8, 2] };
// Module 3D : boîte-logement sur châssis, fenêtres sur les longs côtés et au bout arrière, porte
// vitrée au bout avant ; kit module (schéma satellites) : panneaux cerclés sur un socle
export const MODULE = { chassis: 0.25, rebord: 0.18, rayon: 0.14, pasFenetres: 2.6,
  fenetre: { largeur: 1.2, bas: 1, haut: 2.25 }, cadre: 0.08, porte: [0.95, 2.1] };
export const KIT_MODULE = { socle: 0.18, panneaux: 8 };

// Chariots élévateurs et AGV de décor (decor.js, Decor.jsx) : un chariot à côté de chaque quai
// et dans chaque stock couvert, un AGV dans chaque zone de production couverte. Ils ne
// représentent aucune donnée.
export const CHARIOT = { longueur: 3.4, largeur: 1.15, fourches: 1.1, mat: 2.25, cage: 2.15,
  capot: 0.95, roues: [0.3, 0.25],
  couleurs: { caisse: "#f2b42c", chassis: PALETTE.violet, cage: "#2b2933",
    gilet: PALETTE.orange, peau: "#efc39f", casque: PALETTE.blanc } };
export const AGV = { longueur: 1.5, largeur: 0.9, hauteur: 0.38, bande: PALETTE.violet,
  zones: "Production" }; // catégorie des zones où ils stationnent
// Chariot porteur : toute marchandise qui roule (lot, kit, pod, module) est portée par un
// chariot élévateur, derrière elle, ses fourches dessous ; la charge est levée de `levage` m.
export const CHARIOT_PORTEUR = { levage: 0.3, types: ["lot", "kit 2D", "pod", "module"] };
// Parking des véhicules légers : places de `largeur` × `profondeur` m de part et d'autre d'une
// allée d'est en ouest, bordées de lignes blanches de `ligne` m ; voie d'accès de `voie` m de
// large ; une voiture garée sur la part `remplissage` des places (tirage à graine fixe), sur la
// part `remplissageNuit` la nuit (sans équipe sur le site).
export const PARKING_VL = { largeur: 2.5, profondeur: 5, ligne: 0.15, voie: 6, allee: 6,
  remplissage: 0.7, remplissageNuit: 0.1 };
// Places du parking PL marquées au sol (largeur × longueur, m) : celles de PLACE_PARKING_PL de
// modele.py, où la simulation gare les camions
export const PARKING_PL = { largeur: 4.5, longueur: 17 };
// Véhicules qui circulent (décor, au temps simulé : accélérés avec lui, arrêtés à la pause) :
// sur le site à `vitesse` m/s simulées, sur leur voie à `voieSite` m à droite de l'axe ; sur la
// route publique à `vitesseRoute` m/s, à `decalageVoie` m à droite, `parHeure` passages par
// heure et par modèle (camion : semi-remorque gris `couleurCamion`), `partNuit` d'entre eux la
// nuit.
export const CIRCULATION_VL = { vitesse: 9, vitesseRoute: 13, decalageVoie: 2.2, voieSite: 1.6,
  parHeure: { berline: 60, citadine: 40, camionnette: 15, camion: 8 }, partNuit: 0.25,
  couleurCamion: "#8d909e" };
// Personnel et visiteurs du parking VL (circulation.js), en heures de l'horloge : chaque équipe
// (part des places) arrive en voiture entre les heures `arrivee`, se gare, va à pied à une porte
// du personnel, et repart entre les heures `depart` ; une part `pause` de l'équipe de journée
// sort à midi et revient ; `visiteurs` viennent pour `duree` h ; `permanents` : part des places
// prises jour et nuit. Descente et montée en voiture : `descente` min simulées. Personne ne
// reste sur le site la nuit (à partir de CIEL_JOUR.coucher), sauf les permanents.
export const PERSONNEL = {
  equipes: [
    { nom: "matin", part: 0.33, arrivee: [5.3, 6.35], depart: [14, 14.9], bureaux: 0 },
    { nom: "journée", part: 0.24, arrivee: [7.4, 9.3], depart: [16.4, 19], bureaux: 0.6 },
    { nom: "après-midi", part: 0.24, arrivee: [13.1, 14.1], depart: [19.3, 20.4], bureaux: 0 },
  ],
  pause: { part: 0.3, depart: [11.9, 12.6], retour: [13, 13.8] },
  visiteurs: { nombre: 6, heures: [8.5, 17], duree: [0.4, 2], camionnettes: 0.35 },
  permanents: 0.1, descente: 0.35,
};
// Portail : poste de garde (m) à côté de la voirie, `ecart` m après la barrière, en retrait de
// `recul` m vers l'intérieur ; barrière levante, qui s'ouvre en `duree` s quand un véhicule est
// à moins de `distance` m du portail.
export const POSTE_GARDE = { largeur: 3.2, profondeur: 2.6, hauteur: 2.7, ecart: 1.2, recul: 3,
  toit: 0.25, debord: 0.4, vitre: 1, couleur: "#e9ebf2", toitCouleur: PALETTE.violet,
  vitreCouleur: "#9fc3e6" };
export const BARRIERE = { poteau: 0.6, hauteur: 1, bras: 0.14, duree: 1.2, distance: 24,
  levee: Math.PI * 0.45, couleur: PALETTE.blanc, bande: "#d8343c", socle: "#5b5d6b" };
// Voiture de tourisme du parking : caisse de l'une des `couleurs`, habitacle vitré, roues
export const VOITURE = { longueur: 4.3, largeur: 1.8, hauteur: 1.45, caisse: [0.3, 0.95],
  roue: 0.32, couleurs: ["#f5f5f9", "#3a3944", "#8d909e", "#2f5fa8", "#b8323a", "#d9dbe4"] };
// Modèles de véhicules légers (formesVehicules.js) : longueur, largeur, hauteur (m), caisse
// [bas, haut], habitacle [arrière, avant] en part de la longueur, rayon des roues ; `poids` au
// tirage d'une voiture du personnel ; `libelle` au survol d'une voiture de passage.
export const MODELES_VL = {
  citadine: { longueur: 3.7, largeur: 1.7, hauteur: 1.48, caisse: [0.3, 0.92],
    habitacle: [-0.4, 0.16], roue: 0.29, poids: 3, libelle: "Voiture" },
  berline: { longueur: 4.6, largeur: 1.8, hauteur: 1.42, caisse: [0.3, 0.92],
    habitacle: [-0.3, 0.14], roue: 0.32, poids: 4, libelle: "Voiture" },
  suv: { longueur: 4.5, largeur: 1.86, hauteur: 1.7, caisse: [0.38, 1.08],
    habitacle: [-0.42, 0.16], roue: 0.36, poids: 2, libelle: "Voiture" },
  camionnette: { longueur: 5.3, largeur: 2, hauteur: 2.4, caisse: [0.35, 1.05],
    habitacle: [0.22, 0.36], roue: 0.34, poids: 0.5, libelle: "Camionnette" },
};
// Chariot d'un quai où un camion est arrêté : pendant la lecture, va-et-vient en marche arrière
// sur `course` m (place réservée par decor.js), en `periode` s
export const CHARIOT_ACTIF = { course: 2.5, periode: 5 };
// Places des engins : `marge` m libres autour d'eux, `mur` m de tout mur (jamais à cheval) ; le
// long des murs, à `recul` m, tous les `pas` m ; à côté d'un quai, la plus proche sur une
// grille de `finesse` m jusqu'à `autourDuQuai` m, fourches vers le quai
export const PLACES_DECOR = { marge: 0.4, mur: 0.5, recul: 1.5, pas: 3, autourDuQuai: 10,
  finesse: 0.5 };

// Cycle jour et nuit (Ciel.jsx), sur l'heure de l'horloge : soleil levé à l'est à `lever` h,
// au sud à midi (`elevationMax` degrés), couché à l'ouest à `coucher` h, doré en dessous de
// `hauteurDoree` degrés ; la nuit, une lune bleutée et un ciel sombre gardent le site lisible.
export const CIEL_JOUR = { lever: 5.5, coucher: 20.5, elevationMax: 48, hauteurDoree: 14,
  intensite: 2.8, fond: "#eef0f6", fondCouvert: "#d9dce2", fondDore: "#f4dcc4",
  soleilDore: "#ffc58f", basJour: "#d4d8e8",
  lune: { elevation: 40, azimut: 200, intensite: 0.55, couleur: "#9fb4e8" },
  nuit: { haut: "#55648c", bas: "#1e2433", intensite: 0.42, fond: "#1b2130" } };
// Météo légère (Ciel.jsx) : types, leur poids au tirage d'un jour simulé et leurs effets (0 à
// 1) ; `ombreNuages` : part du soleil ôtée par un ciel couvert ; `brumeProche` : part de la
// distance du brouillard ôtée par la brume ; gouttes et flocons tombent sur `hauteur` m.
export const METEO = {
  adresse: "https://api.open-meteo.com/v1/forecast", rafraichissementMin: 10,
  multiplicateur: 7919, seuilNuageux: 60, ombreNuages: 0.55, brumeProche: 0.45,
  types: {
    clair: { poids: 4, libelle: "Ciel clair",
      effets: { nuages: 0, pluie: 0, neige: 0, brume: 0 } },
    nuageux: { poids: 3, libelle: "Nuageux",
      effets: { nuages: 0.7, pluie: 0, neige: 0, brume: 0 } },
    pluie: { poids: 2, libelle: "Pluie légère",
      effets: { nuages: 0.9, pluie: 1, neige: 0, brume: 0.2 } },
    brume: { poids: 1, libelle: "Brume",
      effets: { nuages: 0.6, pluie: 0, neige: 0, brume: 1 } },
    neige: { poids: 0, libelle: "Neige",
      effets: { nuages: 0.9, pluie: 0, neige: 1, brume: 0.3 } },
  },
  gouttes: 1400, flocons: 900, hauteur: 36, vitessePluie: 14, vitesseNeige: 1.6,
  goutte: [0.03, 0.03, 0.9], flocon: 0.12, couleurPluie: "#a9bed6", couleurNeige: "#ffffff",
  opacitePluie: 0.45,
};
// Employés à pied (pietons.js) : entre leur voiture et une porte du personnel, à `vitesse` m/s
// simulées, foulée de `foulee` m ; chemins sur une grille de `case` m, à `marge` m des murs,
// sortis à `sortie` m devant la porte, `bord` m autour du site.
export const PIETON = { vitesse: 1.4, foulee: 0.7,
  case: 2, marge: 0.5, sortie: 3, bord: 12, echelle: 1.3,
  couleurs: { gilet: "#f2c230", bande: "#d9dbe4", pantalon: "#2f3446", peau: "#d9a47e" } };
// Portes de marchandises (batiments.js, PortesMarchandises.jsx) : une par groupe de passages
// d'un mur, groupe d'au plus `portee` m ; une grande porte existante à moins de `portee` / 2 m
// sert ; les marchandises passent à `recul` m de part et d'autre du mur, dans l'axe de la porte.
// Elle s'ouvre `avance` min simulées avant un passage et reste ouverte `apres` min après (au
// moins `tenue` s réelles) ; elle s'ouvre ou se ferme en `duree` s réelles, gyrophare orange
// allumé (`tours` tours par seconde) pendant le mouvement.
export const PASSAGE = { portee: 36, recul: 2.5, avance: 0.15, apres: 0.15, tenue: 0.6,
  duree: 1.1, tours: 2.2, rideau: 0.9 };
export const GYROPHARE = { rayon: 0.18, hauteur: 0.26, socle: "#3a3944", eteint: "#8a4a26",
  allume: "#ffa040", halo: 0.9 };
// Chariots élévateurs (chariots.js) : garés le long des murs, `garages` places au plus par
// zone ; à vide à `vitesse` m/s simulées ; ils arrivent `attente` min avant la prise et rentrent
// au garage si la prochaine est à plus de `retour` min ; trajet en charge suivi en `pas` points.
export const FLOTTE = { garages: 6, vitesse: 2.2, attente: 0.05, retour: 1.5, pas: 12,
  couleur: "#f2b42c" };
// Ouvriers dans les bâtiments (ouvriers.js) : un par `surface` m² de bâtiment, `max` par
// bâtiment au plus ; chacun fait le tour de `etapes` postes tirés à `marge` m des murs, à
// `vitesse` m/s, et s'arrête de `pauseMin` à `pauseMax` s à chacun. Absents la nuit.
export const OUVRIERS = { surface: 350, max: 10, marge: 3, etapes: 4, vitesse: 1.3,
  pauseMin: 4, pauseMax: 14 };
// Vue à la première personne (PremierePersonne.jsx) : yeux à `yeux` m du sol, marche à
// `vitesse` m/s (`rapide` fois plus avec Maj), champ vertical de `champ`°, rotation au clavier
// de `rotation` rad/s et à la souris de `sensibilite` rad par pixel, tête levée ou baissée de
// `tangageMax`° au plus ; départ `recul` m à l'intérieur du portail ; plan proche à `proche` m.
export const PREMIERE_PERSONNE = { yeux: 1.7, vitesse: 5, rapide: 3, champ: 70, rotation: 1.8,
  sensibilite: 0.004, tangageMax: 80, recul: 6, proche: 0.1 };
// Mode « flux » (flux.js) : flux de zone à zone en courbes de `points` points, bombées de
// `bombe` fois leur longueur, flèche de `fleche` m ; camions sur une grille de `case` m, trajets
// échantillonnés tous les `pas` m ; traînées d'au moins `traficMin` trajets, de `largeurMin` à
// `largeurMax` m, du violet (faible trafic) à l'orange (fort) ; camions en gris ; posées
// `hauteur` m au-dessus du sol et dessinées par-dessus les toits.
export const FLUX = { case: 4, pas: 1, traficMin: 2, largeurMin: 0.8, largeurMax: 7,
  points: 24, bombe: 0.12, fleche: 12, couleurFleche: PALETTE.violet,
  hauteur: 0.4, faible: "#6c5ce0", fort: PALETTE.orange, camion: "#8d909e", opacite: 0.8,
  opaciteCamion: 0.45 };
