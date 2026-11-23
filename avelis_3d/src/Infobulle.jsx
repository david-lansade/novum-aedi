// Infobulle de l'objet survolé : identifiant, type et libellé (fournisseur, besoin de pod…).
import { useSyncExternalStore } from "react";

import { libelleObjet } from "./apparence.js";

const DECALAGE_PX = 14; // entre le pointeur et l'infobulle
const PART_DROITE = 0.7; // au-delà, l'infobulle passe à gauche du pointeur

export default function Infobulle({ survol, schema }) {
  useSyncExternalStore(survol.abonner, survol.lireVersion);
  if (survol.objet === null) return null;
  const { objet, x, y } = survol;
  const aGauche = x > window.innerWidth * PART_DROITE;
  // voiture du décor : son nom seul
  return (
    <div className="infobulle" role="tooltip" style={{
      left: aGauche ? x - DECALAGE_PX : x + DECALAGE_PX,
      top: y + DECALAGE_PX,
      transform: aGauche ? "translateX(-100%)" : "none",
    }}>
      <strong>{objet.decor ? objet.libelle : objet.id}</strong>
      {!objet.decor && <span>{libelleObjet(objet.type, schema)} · {objet.libelle}</span>}
    </div>
  );
}
