// Onglets Quais / Camions / Stocks (colonne de droite) : état de chaque quai, camions présents
// et leur lieu, zones de stock ; badges de statut colorés. Un clic sur un camion le montre.
// Contenu : details.js. Carte repliable, repliée d'office sur une fenêtre basse.
import { useState } from "react";

import { COULEURS_OBJETS, libelleObjet } from "./apparence.js";
import { listeCamions, listeQuais, listeStocks } from "./details.js";
import Repliable, { useRepli } from "./Repliable.jsx";

const ONGLETS = [["quais", "Quais"], ["camions", "Camions"], ["stocks", "Stocks"]];

/** Identifiant d'un camion, cliquable. */
function Camion({ objet, montrer }) {
  return (
    <button type="button" className="lien" onClick={() => montrer(objet)}>{objet.id}</button>
  );
}

function Quais({ scene, arrets, t, montrer }) {
  return (
    <ul className="liste">
      {listeQuais(scene, arrets, t).map(({ numero, fonction, camion, statut, ton }) => (
        <li key={numero}>
          <span className="principal">Quai {numero}<small>{fonction}</small></span>
          {camion && <Camion objet={camion} montrer={montrer} />}
          <span className="statut" data-ton={ton}>{statut}</span>
        </li>
      ))}
    </ul>
  );
}

function Camions({ scene, t, contexte, montrer }) {
  const camions = listeCamions(scene, t, contexte);
  if (camions.length === 0) return <p className="vide">Aucun camion à cet instant.</p>;
  return (
    <ul className="liste">
      {camions.map(({ objet, role, lieu, ton }) => (
        <li key={objet.id}>
          <span className="principal"><Camion objet={objet} montrer={montrer} />
            <small>{role}</small></span>
          <span className="statut" data-ton={ton}>{lieu}</span>
        </li>
      ))}
    </ul>
  );
}

function Stocks({ scene, t }) {
  const schema = scene.scenario.schema;
  return (
    <ul className="liste">
      {listeStocks(scene, t).map(({ zone, valeur, unite, objets }) => (
        <li key={zone} className="stock">
          <span className="principal">{zone}
            <small>{valeur === null ? "pas de valeur du pilotage" : `${valeur} ${unite}`}</small>
          </span>
          <span className="objets-stock">
            {objets.length === 0 ? <small>vide</small> : objets.map(([type, nombre]) => (
              <span key={type} title={libelleObjet(type, schema, nombre > 1)}>
                <span className="pastille" style={{ background: COULEURS_OBJETS[type] }} />
                {nombre}
              </span>
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function Onglets({ scene, t, contexte, arrets, montrer }) {
  const [ouverte, basculer] = useRepli();
  const [onglet, choisir] = useState("quais");
  const titre = (
    <span className="onglets" role="tablist" aria-label="Quais, camions, stocks">
      {ONGLETS.map(([cle, libelle]) => (
        <button key={cle} type="button" role="tab" aria-selected={onglet === cle}
          onClick={() => {
            choisir(cle);
            if (!ouverte) basculer();
          }}>{libelle}</button>
      ))}
    </span>
  );
  return (
    <Repliable className="cartes-onglets" titre={titre} etiquette="Quais, camions et stocks"
      ouverte={ouverte} basculer={basculer}>
      <div className="contenu-onglet" role="tabpanel">
        {onglet === "quais" && <Quais scene={scene} arrets={arrets} t={t} montrer={montrer} />}
        {onglet === "camions" && <Camions scene={scene} t={t} contexte={contexte}
          montrer={montrer} />}
        {onglet === "stocks" && <Stocks scene={scene} t={t} />}
      </div>
    </Repliable>
  );
}
