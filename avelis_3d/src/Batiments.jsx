// Bâtiments du site, en coordonnées du plan (comme Site.jsx) : murs en tôle nervurée, toits,
// portes de quai numérotées, emblème (formes : formesBatiments.js). En mode « Intérieurs », les
// murs s'abaissent jusqu'à BATIMENT.coupe et les toits disparaissent, pour voir les objets à
// l'intérieur. `maquette.ouverture` (0 : fermé, 1 : ouvert) suit ce passage et
// `maquette.echelleMurs` la part de leur hauteur que gardent les murs : le décor et les
// étiquettes les lisent. Le toit du bâtiment où se trouve l'objet sélectionné est retiré, pour
// le montrer : un toit par bâtiment remplace alors le toit d'un seul tenant.
import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { DoubleSide, FrontSide, MeshStandardMaterial, Vector2 } from "three";

import { BATIMENT, EPAISSEUR_TRACE, SELECTION, Z } from "./apparence.js";
import {
  batimentsDuSite, emblemesDuSite, portesDeQuai, portesPietonnes,
} from "./batiments.js";
import { groupesFroids } from "./decor.js";
import { etatObjet } from "./donnees.js";
import {
  emblemes, mursEtToits, plaquesEtNumeros, portesDesQuais,
} from "./formesBatiments.js";
import PortesMarchandises from "./PortesMarchandises.jsx";
import { plancheNumeros, textureEmbleme, textureTole } from "./textures.js";

const ALPHA_DECOUPE = 0.5; // les numéros et l'emblème sont découpés selon leur transparence
const adoucir = (p) => p * p * (3 - 2 * p);

/** Géométries et matériaux des bâtiments du site, libérés quand le site change ; `portes` :
 * portes de marchandises (batiments.js), qui percent les murs. */
function useFormes(site, portes) {
  const anisotropie = useThree((etat) => etat.gl.capabilities.getMaxAnisotropy());
  const formes = useMemo(() => {
    const batiments = batimentsDuSite(site);
    const quais = portesDeQuai(site);
    const tole = textureTole();
    tole.anisotropy = anisotropie;
    const numeros = plancheNumeros(quais.length);
    const embleme = textureEmbleme();
    const decoupe = (map) => new MeshStandardMaterial({ map, alphaTest: ALPHA_DECOUPE });
    return {
      batiments,
      ...mursEtToits(batiments, groupesFroids(site), portes),
      portes: portesDesQuais(quais, portes, portesPietonnes(site)),
      ...plaquesEtNumeros(quais, Z.quai + EPAISSEUR_TRACE + 0.01),
      emblemes: emblemes(emblemesDuSite(site)),
      hauteurMax: Math.max(0, ...batiments.map((b) => b.hauteur)),
      tole: new MeshStandardMaterial({ vertexColors: true, normalMap: tole,
        normalScale: new Vector2(BATIMENT.nervure, BATIMENT.nervure) }),
      peint: new MeshStandardMaterial({ vertexColors: true }),
      numeros: decoupe(numeros), embleme: decoupe(embleme), textures: [tole, numeros, embleme],
    };
  }, [site, portes, anisotropie]);
  useEffect(() => () => {
    for (const cle of ["murs", "toits", "portes", "plaques", "sol", "emblemes"]) {
      formes[cle]?.dispose();
    }
    for (const { geometrie } of formes.toitsSepares) geometrie?.dispose();
    for (const materiau of [formes.tole, formes.peint, formes.numeros, formes.embleme]) {
      materiau.dispose();
    }
    for (const texture of formes.textures) texture.dispose();
  }, [formes]);
  return formes;
}

/** Fait tendre `maquette.ouverture` vers 1 (Intérieurs) ou 0, puis abaisse les murs et cache
 * les toits et les détails des murs dès que le bâtiment s'ouvre. */
function useOuverture(maquette, interieurs, hauteurMax, refs) {
  useFrame((_, secondes) => {
    const cible = interieurs ? 1 : 0;
    const pas = secondes / BATIMENT.dureeOuverture;
    const avant = maquette.ouverture;
    maquette.ouverture = cible > avant ? Math.min(cible, avant + pas)
      : Math.max(cible, avant - pas);
    const coupe = hauteurMax > 0 ? Math.min(1, BATIMENT.coupe / hauteurMax) : 1;
    maquette.echelleMurs = 1 - adoucir(maquette.ouverture) * (1 - coupe);
    refs.murs.current.scale.z = maquette.echelleMurs;
    refs.dessus.current.visible = maquette.ouverture === 0;
  });
}

/** À la première personne (`maquette.premiere`), la tôle se voit aussi de l'intérieur. */
function useDedans(maquette, tole) {
  useFrame(() => {
    const cote = maquette.premiere ? DoubleSide : FrontSide;
    if (tole.side === cote) return;
    tole.side = cote;
    tole.needsUpdate = true;
  });
}

/** Bâtiment {nom, x, y, largeur, profondeur} où se trouve l'objet à l'instant t, ou null. */
function batimentDe(batiments, objet, t) {
  const etat = objet && etatObjet(objet, t);
  if (!etat) return null;
  return batiments.find((b) => etat.x >= b.x && etat.x <= b.x + b.largeur && etat.y >= b.y
    && etat.y <= b.y + b.profondeur)?.nom ?? null;
}

/** À chaque image : toit d'un seul tenant si l'objet sélectionné n'est dans aucun bâtiment ;
 * sinon un toit par bâtiment, sauf le sien. */
function useToitOuvert(formes, magasins, refs) {
  useFrame(() => {
    const ouvert = batimentDe(formes.batiments, magasins.selection.objet, magasins.lecteur.t);
    if (refs.toits.current) refs.toits.current.visible = ouvert === null;
    refs.separes.current?.children.forEach((maillage, i) => {
      maillage.visible = ouvert !== null && formes.toitsSepares[i].nom !== ouvert;
    });
  });
}

/** Vrai si l'objet et tous ses parents sont visibles. */
function visible(objet) {
  for (let o = objet; o; o = o.parent) if (!o.visible) return false;
  return true;
}

/** Gestionnaires du pointeur d'un mur ou d'un toit : s'il arrête le pointeur (`arrete()`, et
 * s'il est visible), un objet qu'il cache ne se survole ni ne se clique, et un clic sur lui
 * désélectionne (`vider`). */
function arretDuPointeur(arrete, vider) {
  const arreteIci = (evenement) => arrete() && visible(evenement.eventObject);
  return {
    onPointerMove: (evenement) => {
      if (arreteIci(evenement)) evenement.stopPropagation();
    },
    onClick: (evenement) => {
      if (!arreteIci(evenement)) return;
      evenement.stopPropagation();
      if (evenement.delta <= SELECTION.clic) vider?.();
    },
  };
}

/** Tous les bâtiments ; `interieurs` : murs coupés et sans toits. Les murs, et les toits tant
 * qu'ils sont posés, arrêtent le pointeur (un objet masqué reste touché par le lancer de rayon,
 * d'où le test sur l'ouverture et la visibilité) ; `vider` : désélectionne ; `magasins` :
 * sélection et lecteur, pour retirer le toit du bâtiment de l'objet sélectionné ;
 * `logistique` : portes de marchandises et instants de passage (logistique.js). */
export default function Batiments({ site, interieurs, maquette, vider, magasins, logistique }) {
  const formes = useFormes(site, logistique.portes);
  const refs = { murs: useRef(null), dessus: useRef(null), toits: useRef(null),
    separes: useRef(null) };
  useOuverture(maquette, interieurs, formes.hauteurMax, refs);
  useToitOuvert(formes, magasins, refs);
  useDedans(maquette, formes.tole);
  const mur = arretDuPointeur(() => true, vider);
  const toit = arretDuPointeur(() => maquette.ouverture === 0, vider);
  return (
    <group>
      <group ref={refs.murs}>
        {formes.murs && <mesh geometry={formes.murs} material={formes.tole} castShadow
          receiveShadow {...mur} />}
        <group ref={refs.dessus}>
          {formes.toits && <mesh ref={refs.toits} geometry={formes.toits}
            material={formes.tole} castShadow receiveShadow {...toit} />}
          <group ref={refs.separes}>
            {formes.toitsSepares.map(({ nom, geometrie }) => (
              <mesh key={nom} geometry={geometrie} material={formes.tole} castShadow
                receiveShadow {...toit} />
            ))}
          </group>
          {formes.portes && <mesh geometry={formes.portes} material={formes.peint} castShadow
            receiveShadow />}
          {formes.plaques && <mesh geometry={formes.plaques} material={formes.numeros} />}
          {formes.emblemes && <mesh geometry={formes.emblemes} material={formes.embleme} />}
          <PortesMarchandises portes={logistique.portes} passages={logistique.passages}
            lecteur={magasins.lecteur} />
        </group>
      </group>
      {formes.sol && <mesh geometry={formes.sol} material={formes.numeros} receiveShadow />}
    </group>
  );
}
