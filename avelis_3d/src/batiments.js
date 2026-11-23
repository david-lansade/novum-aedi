// Bâtiments de la vue 3D, en coordonnées du plan (x vers l'est, y vers le nord, en m) : un par
// zone couverte (hauteur > 0), avec son toit, ses portes de quai et, pour le plus grand, un
// emblème. Calcul seul, sans three.js (testé par « npm test ») ; les formes sont dans
// formesBatiments.js.
import {
  BATIMENT, CATEGORIE_BUREAUX, CHARIOT_PORTEUR, EMBLEME, GRANDE_PORTE, GRANDES_PORTES_MURS,
  PASSAGE, PORTE, PORTE_PIETONNE, PORTES_NORD, groupesDeQuais,
} from "./apparence.js";

const DEGRE = Math.PI / 180;
const PASSES_DETOUR = 4; // un détour par une porte peut en demander un autre, rarement plus
const EPSILON_PORTE = 1e-6; // m : passage déjà dans l'axe de la porte
// Murs d'un rectangle : normale extérieure, et coordonnée (x ou y) le long du mur
const MURS = {
  sud: { normale: [0, -1], long: 0 },
  nord: { normale: [0, 1], long: 0 },
  ouest: { normale: [-1, 0], long: 1 },
  est: { normale: [1, 0], long: 1 },
};

/** Toit d'une zone : plat pour les bureaux ; sinon à deux pans, faîtage suivant le plus grand
 * côté (`axe` x ou y) à `fleche` m au-dessus du haut des murs. */
export function toitDe(zone) {
  if (zone.categorie === CATEGORIE_BUREAUX) return { forme: "plat" };
  const axe = zone.largeur >= zone.profondeur ? "x" : "y";
  const portee = Math.min(zone.largeur, zone.profondeur);
  const fleche = Math.min(BATIMENT.flecheMax, (portee / 2) * Math.tan(BATIMENT.pente * DEGRE));
  return { forme: "deux pans", axe, fleche };
}

/** Vrai dans l'implantation actuelle (site seul) : son extension n'est pas utilisée. */
export function siteSeul(site) {
  return site.contours.some((contour) => !contour.utilise);
}

/** Quais numérotés {numero, x, y, sens} : ceux de réception puis ceux d'expédition (s'ils ne
 * sont pas partagés), le premier de chaque groupe puis un tous les `pas` [dx, dy] m ; `sens` :
 * direction unitaire de la rangée. */
export function quaisNumerotes(quais) {
  const liste = [];
  for (const [, { position: [x0, y0], nombre, pas: [dx, dy] }] of groupesDeQuais(quais)) {
    const n = Math.hypot(dx, dy) || 1;
    for (let i = 0; i < nombre; i++) {
      liste.push({ numero: liste.length + 1, x: x0 + i * dx, y: y0 + i * dy,
        sens: [dx / n, dy / n] });
    }
  }
  return liste;
}

/** Murs de la zone {mur, normale, distance, point} qui font face au quai : le quai est du côté
 * extérieur, à au plus PORTE.distanceMax m, et la porte tient entière dans la longueur du mur. */
function mursFaceAuQuai({ x, y }, zone) {
  const [x1, y1] = [zone.x + zone.largeur, zone.y + zone.profondeur];
  const candidats = [
    { mur: "sud", distance: zone.y - y, point: [x, zone.y], bornes: [zone.x, x1] },
    { mur: "nord", distance: y - y1, point: [x, y1], bornes: [zone.x, x1] },
    { mur: "ouest", distance: zone.x - x, point: [zone.x, y], bornes: [zone.y, y1] },
    { mur: "est", distance: x - x1, point: [x1, y], bornes: [zone.y, y1] },
  ];
  return candidats.filter(({ mur, distance, point, bornes: [debut, fin] }) => {
    const le = point[MURS[mur].long];
    return distance >= 0 && distance <= PORTE.distanceMax && le - PORTE.largeur / 2 >= debut
      && le + PORTE.largeur / 2 <= fin;
  }).map((c) => ({ mur: c.mur, normale: MURS[c.mur].normale, distance: c.distance,
    point: c.point, zone: zone.nom }));
}

/** Quais numérotés, chacun avec la porte {mur, normale, point, zone} du mur de bâtiment le plus
 * proche qui lui fait face, ou `porte: null` (quai à ciel ouvert). */
export function portesDeQuai(site) {
  const couverts = site.zones.filter((zone) => zone.hauteur > 0);
  return quaisNumerotes(site.quais).map((quai) => {
    const murs = couverts.flatMap((zone) => mursFaceAuQuai(quai, zone));
    const proche = murs.reduce((a, b) => (b.distance < a.distance ? b : a), murs[0]);
    if (!proche) return { ...quai, porte: null };
    const { mur, normale, point, zone } = proche;
    return { ...quai, porte: { mur, normale, point, zone } };
  });
}

/** Logo {mur, normale, largeur, centre [x, y, z]} au milieu du mur `mur` du hangar, en haut. */
function emblemeDuMur(hall, mur) {
  const long = MURS[mur].long === 0 ? hall.largeur : hall.profondeur;
  const largeur = Math.min(EMBLEME.cote * EMBLEME.rapport, long * EMBLEME.partMur);
  const z = hall.hauteur - EMBLEME.marge - largeur / EMBLEME.rapport / 2;
  const [cx, cy] = [hall.x + hall.largeur / 2, hall.y + hall.profondeur / 2];
  const centres = { sud: [cx, hall.y], nord: [cx, hall.y + hall.profondeur], ouest: [hall.x, cy],
    est: [hall.x + hall.largeur, cy] };
  return { mur, normale: MURS[mur].normale, largeur, centre: [...centres[mur], z] };
}

/** Logos {mur, normale, largeur, centre [x, y, z]} : au milieu des faces sud et ouest (vues
 * par la caméra de la vue d'ensemble) des hangars d'EMBLEME.halls, de la face nord de ceux
 * d'EMBLEME.nord et, dans l'implantation actuelle, de la face est de ceux d'EMBLEME.estSiteSeul,
 * en haut des murs. */
export function emblemesDuSite(site) {
  const seul = siteSeul(site);
  return site.zones.filter((zone) => zone.hauteur > 0).flatMap((hall) => [
    ...(EMBLEME.halls.includes(hall.nom) ? ["sud", "ouest"] : []),
    ...(EMBLEME.nord.includes(hall.nom) ? ["nord"] : []),
    ...(seul && EMBLEME.estSiteSeul.includes(hall.nom) ? ["est"] : []),
  ].map((mur) => emblemeDuMur(hall, mur)));
}

/** Bâtiments du site : chaque zone couverte, avec son toit. */
export function batimentsDuSite(site) {
  return site.zones.filter((zone) => zone.hauteur > 0).map((zone) => ({ ...zone,
    toit: toitDe(zone) }));
}

/** Mur {mur, normale, point, bornes, distance, zone} de `zone` qui fait face au point (x, y),
 * du côté extérieur et à au plus `distanceMax` m, ou null. */
function murFace({ x, y }, zone, distanceMax) {
  const [x1, y1] = [zone.x + zone.largeur, zone.y + zone.profondeur];
  const dansX = x >= zone.x && x <= x1;
  const dansY = y >= zone.y && y <= y1;
  return [
    { mur: "sud", distance: zone.y - y, point: [x, zone.y], bornes: [zone.x, x1], ok: dansX },
    { mur: "nord", distance: y - y1, point: [x, y1], bornes: [zone.x, x1], ok: dansX },
    { mur: "ouest", distance: zone.x - x, point: [zone.x, y], bornes: [zone.y, y1], ok: dansY },
    { mur: "est", distance: x - x1, point: [x1, y], bornes: [zone.y, y1], ok: dansY },
  ].filter((c) => c.ok && c.distance >= 0 && c.distance <= distanceMax)
    .map(({ ok: _, ...c }) => ({ ...c, normale: MURS[c.mur].normale, zone: zone.nom }))
    .sort((a, b) => a.distance - b.distance)[0] ?? null;
}

/** Vrai si une ouverture de demi-largeur `demi` centrée en `le` tient dans `bornes` sans
 * toucher les ouvertures `prises` [{le, demi}] du même mur. */
function placeLibre(le, demi, [debut, fin], prises) {
  return le - demi >= debut + 0.5 && le + demi <= fin - 0.5
    && prises.every((p) => Math.abs(p.le - le) >= p.demi + demi + 0.5);
}

/** Ouvertures déjà posées sur le mur `mur` de la zone `zone` : [{le, demi}]. */
function ouverturesDuMur(portes, zone, mur) {
  return portes.filter((p) => p.zone === zone && p.mur === mur)
    .map((p) => ({ le: p.point[MURS[mur].long], demi: p.demi }));
}

/** Portes de quai du site, sous la forme {zone, mur, point, demi}. */
function portesQuaiPosees(site) {
  return portesDeQuai(site).filter((q) => q.porte)
    .map(({ porte: p }) => ({ ...p, demi: PORTE.largeur / 2 + PORTE.cadre }));
}

/** Grandes portes de marchandises {mur, normale, point, zone} : une par groupe de quais, sur le
 * mur couvert le plus proche qui lui fait face, juste après (ou avant) la rangée des quais, ou
 * à son milieu si les quais n'y ont pas de porte. */
export function grandesPortes(site) {
  const couverts = site.zones.filter((zone) => zone.hauteur > 0);
  const posees = portesQuaiPosees(site);
  const demi = GRANDE_PORTE.largeur / 2 + GRANDE_PORTE.cadre;
  const resultat = [];
  for (const [, { position: [x0, y0], nombre, pas }] of groupesDeQuais(site.quais)) {
    const [xf, yf] = [x0 + (nombre - 1) * pas[0], y0 + (nombre - 1) * pas[1]];
    const mur = couverts.map((z) => murFace({ x: (x0 + xf) / 2, y: (y0 + yf) / 2 }, z,
      GRANDE_PORTE.distanceMax)).filter(Boolean).sort((a, b) => a.distance - b.distance)[0];
    if (!mur) continue;
    const long = MURS[mur.mur].long;
    const [debut, fin] = [Math.min([x0, y0][long], [xf, yf][long]),
      Math.max([x0, y0][long], [xf, yf][long])];
    // au-delà de la dernière porte de quai, d'un pas au moins, sans la toucher
    const ecart = Math.max(Math.hypot(...pas), PORTE.largeur / 2 + PORTE.cadre + demi + 1);
    const prises = ouverturesDuMur([...posees, ...resultat], mur.zone, mur.mur);
    const choix = [fin + ecart, debut - ecart, (debut + fin) / 2]
      .find((le) => placeLibre(le, demi, mur.bornes, prises));
    if (choix === undefined) continue;
    const point = [...mur.point];
    point[MURS[mur.mur].long] = choix;
    resultat.push({ mur: mur.mur, normale: mur.normale, point, zone: mur.zone, demi });
  }
  resultat.push(...grandesPortesDesMurs(site, [...posees, ...resultat], demi));
  return resultat.map(({ demi: _, ...p }) => p);
}

/** Grandes portes en plus, sur les murs de GRANDES_PORTES_MURS : au milieu, au tiers ou aux deux
 * tiers du mur, à une place libre (ni porte, ni bâtiment devant). */
function grandesPortesDesMurs(site, prises, demi) {
  const couverts = site.zones.filter((zone) => zone.hauteur > 0);
  const resultat = [];
  for (const zone of couverts) {
    for (const mur of GRANDES_PORTES_MURS[zone.nom] ?? []) {
      const bornes = [zone.x, zone.x + zone.largeur];
      const ouvertures = ouverturesDuMur([...prises, ...resultat], zone.nom, mur);
      const x = [0.5, 1 / 3, 2 / 3].map((f) => zone.x + f * zone.largeur).find((v) =>
        placeLibre(v, demi, bornes, ouvertures) && !devantOccupe(zone, mur, v, couverts));
      if (x === undefined) continue;
      const y = mur === "sud" ? zone.y : zone.y + zone.profondeur;
      resultat.push({ mur, normale: MURS[mur].normale, point: [x, y], zone: zone.nom, demi });
    }
  }
  return resultat;
}

/** Vrai si une autre zone couverte est à moins de PORTE_PIETONNE.degagement m devant le mur
 * sud ou nord (`mur`) de `zone`, au droit de l'abscisse x. */
function devantOccupe(zone, mur, x, couverts) {
  const d = PORTE_PIETONNE.degagement;
  const [bas, haut] = mur === "sud" ? [zone.y - d, zone.y]
    : [zone.y + zone.profondeur, zone.y + zone.profondeur + d];
  return couverts.some((z) => z !== zone && x >= z.x && x <= z.x + z.largeur
    && z.y + z.profondeur > bas && z.y < haut);
}

/** Porte piétonne {mur, normale, point, zone} du mur sud ou nord de `zone`, au quart, aux trois
 * quarts ou au milieu de sa longueur, à une place libre (ni porte, ni bâtiment devant), ou
 * null. */
function portePietonneDuMur(zone, mur, autres, couverts) {
  const prises = ouverturesDuMur(autres, zone.nom, mur);
  const bornes = [zone.x, zone.x + zone.largeur];
  const demi = PORTE_PIETONNE.auvent.largeur / 2;
  const x = [0.25, 0.75, 0.5].map((f) => zone.x + f * zone.largeur)
    .find((v) => placeLibre(v, demi, bornes, prises) && !devantOccupe(zone, mur, v, couverts));
  const y = mur === "sud" ? zone.y : zone.y + zone.profondeur;
  return x === undefined ? null : { mur, normale: MURS[mur].normale, point: [x, y],
    zone: zone.nom };
}

/** Portes piétonnes {mur, normale, point, zone} : une sur le mur sud de chaque bâtiment, et une
 * sur le mur nord de ceux de PORTES_NORD (`siteSeul` : dans l'implantation actuelle), chacune à
 * une place libre. */
export function portesPietonnes(site) {
  const couverts = site.zones.filter((zone) => zone.hauteur > 0);
  const grandes = grandesPortes(site).map((p) => ({ ...p,
    demi: GRANDE_PORTE.largeur / 2 + GRANDE_PORTE.cadre }));
  const autres = [...portesQuaiPosees(site), ...grandes];
  const nord = [...PORTES_NORD.toutes, ...(siteSeul(site) ? PORTES_NORD.siteSeul : [])];
  return couverts.flatMap((zone) => [portePietonneDuMur(zone, "sud", autres, couverts),
    nord.includes(zone.nom) ? portePietonneDuMur(zone, "nord", autres, couverts) : null])
    .filter(Boolean);
}

/** Passages du segment [a, b] à travers les murs des bâtiments `couverts` : [{zone, mur, u,
 * point, entree}], u de 0 (a) à 1 (b), dans l'ordre ; `entree` : de dehors vers dedans. */
function passagesDuSegment(a, b, couverts) {
  const liste = [];
  for (const z of couverts) {
    const [x1, y1] = [z.x + z.largeur, z.y + z.profondeur];
    for (const [mur, axe, c, dehorsAvant] of [["ouest", 0, z.x, true], ["est", 0, x1, false],
      ["sud", 1, z.y, true], ["nord", 1, y1, false]]) {
      if ((a[axe] - c) * (b[axe] - c) >= 0) continue;
      const u = (c - a[axe]) / (b[axe] - a[axe]);
      const point = [a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])];
      const [bas, haut] = axe === 0 ? [z.y, y1] : [z.x, x1];
      const le = point[1 - axe];
      if (le < bas || le > haut) continue;
      liste.push({ zone: z.nom, mur, u, point, entree: (a[axe] < c) === dehorsAvant });
    }
  }
  return liste.sort((p, q) => p.u - q.u);
}

/** Passages d'un chemin (polyligne) à travers les murs des bâtiments : [{zone, mur, point,
 * entree, k (tronçon), u}], dans l'ordre du chemin. */
export function passagesDuChemin(chemin, couverts) {
  return chemin.slice(1).flatMap((b, k) => passagesDuSegment(chemin[k], b, couverts)
    .map((p) => ({ ...p, k })));
}

/** Groupes de positions triées, chacun d'au plus `portee` m. */
function grouper(positions, portee) {
  const groupes = [];
  for (const le of [...positions].sort((a, b) => a - b)) {
    const groupe = groupes.at(-1);
    if (groupe && le - groupe[0] <= portee) groupe.push(le);
    else groupes.push([le]);
  }
  return groupes;
}

/** Place libre la plus proche de `le` sur le mur (pas de 1 m, jusqu'à la moitié du mur), ou
 * undefined. */
function placeProche(le, demi, bornes, prises) {
  const [debut, fin] = bornes;
  const borne = Math.max(debut + demi + 0.5, Math.min(fin - demi - 0.5, le));
  for (let d = 0; d <= (fin - debut) / 2; d += 1) {
    for (const v of [borne + d, borne - d]) if (placeLibre(v, demi, bornes, prises)) return v;
  }
  return undefined;
}

/** Portes de marchandises {id, zone, mur, normale, point, nouvelle} : les grandes portes, et
 * une porte de plus par groupe de passages (PASSAGE.portee m au plus) d'un mur où aucune
 * grande porte n'est assez proche, à une place libre (ni quai, ni porte piétonne). `chemins` :
 * trajets des marchandises (polylignes). */
export function portesDeMarchandises(site, chemins) {
  const couverts = site.zones.filter((zone) => zone.hauteur > 0);
  const demi = GRANDE_PORTE.largeur / 2 + GRANDE_PORTE.cadre;
  const portes = grandesPortes(site).map((p) => ({ ...p, demi, nouvelle: false }));
  const prises = [...portesQuaiPosees(site), ...portesPietonnes(site).map((p) => ({ ...p,
    demi: PORTE_PIETONNE.auvent.largeur / 2 }))];
  const parMur = new Map();
  for (const p of chemins.flatMap((c) => passagesDuChemin(c, couverts))) {
    const cle = `${p.zone}|${p.mur}`;
    if (!parMur.has(cle)) parMur.set(cle, []);
    parMur.get(cle).push(p.point[MURS[p.mur].long]);
  }
  for (const [cle, positions] of [...parMur].sort(([a], [b]) => a.localeCompare(b))) {
    const [nom, mur] = cle.split("|");
    const zone = couverts.find((z) => z.nom === nom);
    const long = MURS[mur].long;
    const bornes = long === 0 ? [zone.x, zone.x + zone.largeur]
      : [zone.y, zone.y + zone.profondeur];
    for (const groupe of grouper(positions, PASSAGE.portee)) {
      const median = groupe[Math.floor(groupe.length / 2)];
      const voisine = portes.some((p) => p.zone === nom && p.mur === mur
        && Math.abs(p.point[long] - median) <= PASSAGE.portee / 2);
      if (voisine) continue;
      const le = placeProche(median, demi, bornes, ouverturesDuMur([...prises, ...portes], nom,
        mur));
      if (le === undefined) continue;
      const point = [0, 0];
      point[long] = le;
      point[1 - long] = { sud: zone.y, nord: zone.y + zone.profondeur, ouest: zone.x,
        est: zone.x + zone.largeur }[mur];
      portes.push({ mur, normale: MURS[mur].normale, point, zone: nom, demi, nouvelle: true });
    }
  }
  return portes.map(({ demi: _, ...p }, i) => ({ ...p, id: i }));
}

/** Porte de marchandises du mur `mur` de la zone `zone` la plus proche du point, ou null. */
export function porteDuPassage(portes, { zone, mur, point }) {
  const long = MURS[mur].long;
  let meilleure = null;
  for (const p of portes) {
    if (p.zone !== zone || p.mur !== mur) continue;
    if (!meilleure || Math.abs(p.point[long] - point[long])
      < Math.abs(meilleure.point[long] - point[long])) meilleure = p;
  }
  return meilleure;
}

/** Chemin qui passe par les portes : chaque passage à travers un mur est remplacé par deux
 * points, à PASSAGE.recul m de part et d'autre du mur, dans l'axe de la porte de
 * marchandises la plus proche sur ce mur (inchangé s'il n'y en a pas). Un détour peut couper
 * un autre mur : on recommence jusqu'à ce que tout passage soit à une porte. */
export function parLesPortes(chemin, couverts, portes) {
  let resultat = chemin;
  for (let passe = 0; passe < PASSES_DETOUR; passe++) {
    const suivant = unDetour(resultat, couverts, portes);
    if (suivant === resultat) break;
    resultat = suivant;
  }
  return resultat;
}

/** Un tour de parLesPortes : le chemin lui-même s'il passe déjà partout par une porte. */
function unDetour(chemin, couverts, portes) {
  if (chemin.length < 2 || !portes.length) return chemin;
  const passages = passagesDuChemin(chemin, couverts).filter((p) => {
    const porte = porteDuPassage(portes, p);
    return porte && Math.abs(porte.point[MURS[p.mur].long] - p.point[MURS[p.mur].long])
      > EPSILON_PORTE;
  });
  if (!passages.length) return chemin;
  const resultat = [chemin[0]];
  let suivant = 0;
  for (let k = 0; k < chemin.length - 1; k++) {
    while (suivant < passages.length && passages[suivant].k === k) {
      const passage = passages[suivant++];
      const porte = porteDuPassage(portes, passage);
      const [nx, ny] = porte.normale;
      const r = PASSAGE.recul;
      const [dehors, dedans] = [[porte.point[0] + nx * r, porte.point[1] + ny * r],
        [porte.point[0] - nx * r, porte.point[1] - ny * r]];
      resultat.push(...(passage.entree ? [dehors, dedans] : [dedans, dehors]));
    }
    resultat.push(chemin[k + 1]);
  }
  return resultat;
}

/** Trajets (polylignes) des marchandises de la scène, que portent les chariots. */
export function cheminsDesMarchandises(objets) {
  return objets.filter((o) => CHARIOT_PORTEUR.types.includes(o.type))
    .flatMap((o) => o.segments.map((s) => s[2]).filter((chemin) => chemin.length > 1));
}
