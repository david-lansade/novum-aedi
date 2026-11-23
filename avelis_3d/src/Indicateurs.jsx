// Rangée de cartes d'indicateurs, en haut à gauche : valeur du tableau de pilotage à l'instant
// simulé, détail, et variation (écart à l'objectif, ou évolution sur la dernière heure).
import { useSyncExternalStore } from "react";

import Icone from "./Icone.jsx";
import { cartesIndicateurs } from "./indicateurs.js";

export default function Indicateurs({ scene, lecteur }) {
  useSyncExternalStore(lecteur.abonner, lecteur.lireVersion);
  return (
    <section className="indicateurs" aria-label="Indicateurs à l'instant simulé">
      {cartesIndicateurs(scene, lecteur.t).map(({ cle, libelle, valeur, detail, variation }) => (
        <article key={cle} className="carte indicateur" data-cle={cle}>
          <span className="pictogramme"><Icone nom={cle} /></span>
          <div className="corps">
            <h2>{libelle}</h2>
            <p className="valeur">
              {valeur}
              <span className="variation" data-ton={variation.ton} title={variation.titre}>
                {variation.texte}
              </span>
            </p>
            <p className="detail">{detail}</p>
          </div>
        </article>
      ))}
    </section>
  );
}
