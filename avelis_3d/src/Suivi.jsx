// Suivi des objets : anneau au sol autour de l'objet sélectionné ; pilule (son identifiant et son
// libellé) au-dessus de lui ; épingles au-dessus des camions à quai, flèche vers le bas pour un
// déchargement (fourgon), vers le haut pour un chargement (plateau). L'anneau est dans la scène
// 3D, en coordonnées du plan ; la pilule et les épingles sont sur un calque HTML, replacées à
// chaque image en projetant leur point 3D, comme les étiquettes (Etiquettes.jsx). Positions :
// couche visuelle des trajectoires (trajectoires.js).
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { useFrame } from "@react-three/fiber";
import { Path, Shape, ShapeGeometry, Vector3 } from "three";

import { EPINGLE, SELECTION, Z_POSE, libelleObjet } from "./apparence.js";
import { etatSuivi } from "./chariots.js";
import { formeObjet } from "./objets.js";
import { arretEnCours, etatAffiche } from "./trajectoires.js";

const Z_ANNEAU = 0.05; // m au-dessus du dessus des dalles
const SEGMENTS_COIN = 6;
// Icônes des épingles, au trait sur une grille de 24 × 24 : caisse et flèche
const ICONES = {
  dechargement: "M12 3v9M8 8.5l4 4 4-4M5 14v6h14v-6",
  chargement: "M12 13V4M8 7.5l4-4 4 4M5 14v6h14v-6",
};

/** Trace dans `chemin` (Shape ou Path de three) un rectangle centré de demi-côtés a et b, aux
 * coins arrondis de rayon r. */
function rectangleArrondi(chemin, a, b, r) {
  chemin.moveTo(-a + r, -b);
  chemin.lineTo(a - r, -b);
  chemin.absarc(a - r, -b + r, r, -Math.PI / 2, 0, false);
  chemin.lineTo(a, b - r);
  chemin.absarc(a - r, b - r, r, 0, Math.PI / 2, false);
  chemin.lineTo(-a + r, b);
  chemin.absarc(-a + r, b - r, r, Math.PI / 2, Math.PI, false);
  chemin.lineTo(-a, -b + r);
  chemin.absarc(-a + r, -b + r, r, Math.PI, 1.5 * Math.PI, false);
  return chemin;
}

/** Anneau plat, aux coins arrondis, autour d'une emprise [largeur, longueur] (l'avant vers +x),
 * à SELECTION.marge m de son bord. */
function geometrieAnneau([largeur, longueur]) {
  const { marge, epaisseur, arrondi } = SELECTION;
  const [a, b] = [longueur / 2 + marge, largeur / 2 + marge];
  const exterieur = rectangleArrondi(new Shape(), a + epaisseur, b + epaisseur,
    arrondi + epaisseur);
  exterieur.holes.push(rectangleArrondi(new Path(), a, b, arrondi));
  return new ShapeGeometry(exterieur, SEGMENTS_COIN);
}

/** Anneau orange au sol autour de l'objet sélectionné, qui le suit et palpite. */
export function Anneau({ gabarits, magasins }) {
  const { lecteur, selection, trajectoires } = magasins;
  useSyncExternalStore(selection.abonner, selection.lireVersion);
  const type = selection.objet?.type ?? null;
  const maillage = useRef(null);
  const geometrie = useMemo(() => type && geometrieAnneau(gabarits[type]), [type, gabarits]);
  useEffect(() => () => geometrie?.dispose(), [geometrie]);
  useFrame(({ clock }) => {
    if (!maillage.current) return;
    const objet = selection.objet;
    const etat = objet && etatSuivi(objet, lecteur.t, trajectoires);
    maillage.current.visible = Boolean(etat);
    if (!etat) return;
    const phase = (2 * Math.PI * clock.elapsedTime) / SELECTION.periode;
    maillage.current.position.set(etat.x, etat.y, Z_POSE + Z_ANNEAU);
    maillage.current.rotation.set(0, 0, etat.cap);
    maillage.current.scale.setScalar(1 + SELECTION.ampleur * Math.sin(phase));
  });
  if (!geometrie) return null;
  return (
    <mesh ref={maillage} geometry={geometrie} visible={false} userData={{ sansOcclusion: true }}>
      <meshBasicMaterial color={SELECTION.couleur} transparent opacity={SELECTION.opacite}
        depthWrite={false} />
    </mesh>
  );
}

/** Dans la toile : place chaque épingle au-dessus du camion arrêté à son quai et la pilule
 * au-dessus de l'objet sélectionné (et de son épingle s'il en a une) ; masque celles qui n'ont
 * rien à suivre. `calque` : éléments {pilule, epingles (Map numéro du quai → élément)}. */
export function ProjecteurSuivi({ calque, gabarits, arrets, magasins }) {
  const { lecteur, selection, trajectoires } = magasins;
  const point = useMemo(() => new Vector3(), []);
  useFrame(({ camera, size }) => {
    const suivre = (element, etat, hauteur, decalage = 0) => {
      if (!element) return;
      if (etat) point.set(etat.x, Z_POSE + hauteur, -etat.y).project(camera); // plan → three.js
      const visible = Boolean(etat) && point.z < 1;
      element.style.visibility = visible ? "visible" : "hidden";
      if (!visible) return;
      const [x, y] = [((point.x + 1) / 2) * size.width, ((1 - point.y) / 2) * size.height];
      element.style.transform = `translate(${x}px, ${y - decalage}px) translate(-50%, -100%)`;
    };
    const objet = selection.objet;
    let sousLaPilule = 0; // px : hauteur de l'épingle de l'objet sélectionné
    for (const [numero, element] of calque.epingles) {
      const arret = arretEnCours(arrets.get(numero) ?? [], lecteur.t);
      if (arret) {
        element.dataset.operation = formeObjet(arret.objet) === "plateau" ? "chargement"
          : "dechargement";
        if (arret.objet === objet) sousLaPilule = element.offsetHeight + EPINGLE.ecart;
      }
      suivre(element, arret && etatAffiche(arret.objet, lecteur.t, trajectoires),
        gabarits.camion[2] + EPINGLE.hauteur);
    }
    suivre(calque.pilule, objet && etatSuivi(objet, lecteur.t, trajectoires),
      objet && gabarits[objet.type][2] + SELECTION.pilule, sousLaPilule);
  });
  return null;
}

/** Calque HTML de la pilule de l'objet sélectionné et des épingles des quais. */
export function CalqueSuivi({ calque, quais, selection, schema }) {
  useSyncExternalStore(selection.abonner, selection.lireVersion);
  const objet = selection.objet;
  const ranger = (numero) => (element) => {
    if (element) calque.epingles.set(numero, element);
    else calque.epingles.delete(numero);
  };
  return (
    <div className="calque-suivi" aria-hidden="true">
      <div className="pilule" ref={(element) => { calque.pilule = element; }}>
        {objet && <strong>{objet.id}</strong>}
        {objet && <span>{libelleObjet(objet.type, schema)} · {objet.libelle}</span>}
      </div>
      {quais.map(({ numero }) => (
        <div key={numero} className="epingle" ref={ranger(numero)}>
          {Object.entries(ICONES).map(([operation, trace]) => (
            <svg key={operation} className={operation} viewBox="0 0 24 24">
              <path d={trace} />
            </svg>
          ))}
        </div>
      ))}
    </div>
  );
}
