// Légende (catégories de zones, objets avec leur nombre visible à l'instant simulé, voiries) et
// affichage des noms des zones. Les cadrages sont dans les commandes de la vue (CommandesVue.jsx).
import { useSyncExternalStore } from "react";

import { COULEURS_OBJETS, COULEURS_PLAN, libelleObjet } from "./apparence.js";
import { TYPES_OBJETS } from "./donnees.js";
import Repliable, { useRepli } from "./Repliable.jsx";

const REPERES = [
  ["Route publique", COULEURS_PLAN.routePublique],
  ["Voirie poids lourds", COULEURS_PLAN.voirie],
  ["Quais et zones extérieures", COULEURS_PLAN.ligneZone],
];

/** Liste de pastilles de couleur et de libellés, suivis d'un nombre s'il est donné. */
function Pastilles({ titre, entrees }) {
  return (
    <>
      <h2>{titre}</h2>
      <ul>
        {entrees.map(([libelle, couleur, nombre]) => (
          <li key={libelle}>
            <span className="pastille" style={{ background: couleur }} />
            {libelle}
            {nombre !== undefined && <span className="nombre">{nombre}</span>}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function Legende({ scene, lecteur, noms, changerNoms }) {
  useSyncExternalStore(lecteur.abonner, lecteur.lireVersion);
  const [ouverte, basculer] = useRepli(true);
  const categories = [...new Map(scene.site.zones.map((zone) => [zone.categorie, zone.couleur]))];
  const objets = TYPES_OBJETS.map((type) => [libelleObjet(type, scene.scenario.schema),
    COULEURS_OBJETS[type], lecteur.comptes[type] ?? 0]);
  return (
    <Repliable className="legende" titre="Légende" ouverte={ouverte} basculer={basculer}>
      <Pastilles titre="Zones" entrees={categories} />
      <Pastilles titre="Objets" entrees={objets} />
      <Pastilles titre="Voiries" entrees={REPERES} />
      <label className="case">
        <input type="checkbox" checked={noms} onChange={(e) => changerNoms(e.target.checked)} />
        Noms des zones
      </label>
    </Repliable>
  );
}
