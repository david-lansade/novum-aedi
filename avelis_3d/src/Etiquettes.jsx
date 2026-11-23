// Noms posés dans la scène : un seul calque HTML au-dessus de la toile, dont chaque étiquette est
// replacée à chaque image en projetant son point 3D (le texte reste net et lisible quel que soit
// le zoom, sans créer une racine React par étiquette). Textes et points : etiquettes.js.
import { useFrame } from "@react-three/fiber";
import { useMemo } from "react";
import { Vector3 } from "three";

import { HAUTEUR_ETIQUETTE } from "./etiquettes.js";

export { etiquettesDuSite } from "./etiquettes.js";

/** Calque HTML des étiquettes ; `registre` relie chaque clé à son élément. */
export function CalqueEtiquettes({ etiquettes, noms, registre }) {
  return (
    <div className="calque-etiquettes" aria-hidden="true">
      {etiquettes.filter((e) => noms || e.toujours).map((e) => (
        <div key={e.cle} ref={(element) => {
          if (element) registre.set(e.cle, element);
          else registre.delete(e.cle);
        }} className={e.discrete ? "etiquette discrete" : "etiquette"}>
          {e.texte}
        </div>
      ))}
    </div>
  );
}

const ECART_PX = 2; // entre deux étiquettes empilées
const ESSAIS_MAX = 8; // décalages successifs dans un même sens, au plus

/** Vrai si deux boîtes {g, h, d, b} (pixels) se recouvrent. */
function chevauchent(a, b) {
  return a.g < b.d && b.g < a.d && a.h < b.b && b.h < a.b;
}

/** Boîte poussée vers le bas (sens 1) ou le haut (sens −1) jusqu'à ne plus recouvrir aucune
 * étiquette posée ; null si ESSAIS_MAX décalages n'y suffisent pas. */
function decaler(boite, posees, sens) {
  for (let essai = 0; essai <= ESSAIS_MAX; essai++) {
    const gene = posees.find((autre) => chevauchent(boite, autre));
    if (!gene) return boite;
    const decalage = sens > 0 ? gene.b + ECART_PX - boite.h : gene.h - ECART_PX - boite.b;
    boite = { ...boite, h: boite.h + decalage, b: boite.b + decalage };
  }
  return null;
}

/** Boîte de l'étiquette centrée en (x, y) ; si elle recouvre une étiquette déjà posée, la plus
 * proche des places libres juste au-dessous ou au-dessus. */
function boiteLibre(element, x, y, posees) {
  const { offsetWidth: largeur, offsetHeight: hauteur } = element;
  const boite = { g: x - largeur / 2, h: y - hauteur / 2, d: x + largeur / 2, b: y + hauteur / 2 };
  const libres = [decaler(boite, posees, 1), decaler(boite, posees, -1)].filter(Boolean);
  const ecart = (autre) => Math.abs(autre.h - boite.h);
  return libres.reduce((a, b) => (ecart(b) < ecart(a) ? b : a), libres[0] ?? boite);
}

// Cartes fixes de l'interface, sans les menus
const CARTES = ".visionneuse > .carte, .indicateurs > .carte, .colonne-droite > .carte";
const IMAGES_ENTRE_MESURES = 10; // les cartes se replient et changent avec la sélection

/** Boîtes {g, h, d, b} des cartes de l'interface, mesurées de nouveau toutes les
 * IMAGES_ENTRE_MESURES images (une dizaine de boîtes : peu coûteux). */
function useEmprisesCartes() {
  const cache = useMemo(() => ({ images: 0, boites: [] }), []);
  return () => {
    if (cache.images % IMAGES_ENTRE_MESURES === 0) {
      cache.boites = [...document.querySelectorAll(CARTES)].map((element) => {
        const { left, top, right, bottom } = element.getBoundingClientRect();
        return { g: left, h: top, d: right, b: bottom };
      });
    }
    cache.images += 1;
    return cache.boites;
  };
}

/** Dans la toile : place chaque étiquette du registre au point projeté de sa position, dans
 * l'ordre de la liste, sans recouvrir celles déjà posées ; celles des bâtiments au-dessus de
 * leurs murs, à la hauteur qu'ils gardent (`maquette.echelleMurs`, Batiments.jsx). Une
 * étiquette qui toucherait une carte de l'interface est masquée. */
export function Projecteur({ etiquettes, registre, maquette }) {
  const point = useMemo(() => new Vector3(), []);
  const emprisesCartes = useEmprisesCartes();
  useFrame(({ camera, size }) => {
    const cartes = emprisesCartes();
    const posees = [];
    for (const { cle, position: [x, y, z], murs } of etiquettes) {
      const element = registre.get(cle);
      if (!element) continue;
      const hauteur = murs > 0 ? murs * maquette.echelleMurs + HAUTEUR_ETIQUETTE : z;
      point.set(x, hauteur, -y).project(camera); // plan (x, y, z) → three.js (x, z, −y)
      const boite = point.z < 1 && boiteLibre(element, ((point.x + 1) / 2) * size.width,
        ((1 - point.y) / 2) * size.height, posees);
      const visible = boite && !cartes.some((carte) => chevauchent(boite, carte));
      element.style.visibility = visible ? "visible" : "hidden";
      if (!visible) continue;
      posees.push(boite);
      element.style.transform = `translate(${boite.g}px, ${boite.h}px)`;
    }
  });
  return null;
}
