// Cartes qui dépendent de la sélection : colonne de droite (panneau de détail de l'objet
// sélectionné, sinon la légende ; puis les onglets Quais / Camions / Stocks) et timeline de
// traçabilité en bas à gauche. Relues au rythme de PAS_PANNEAUX_MS pendant la lecture.
import { PanneauDetail, Tracabilite, useInstantRalenti, useSelection } from "./Detail.jsx";
import Legende from "./Legende.jsx";
import Onglets from "./Onglets.jsx";

export default function Panneaux({ scene, magasins, arrets, objets, montrer, noms,
  changerNoms }) {
  const { lecteur, selection, trajectoires: contexte } = magasins;
  const t = useInstantRalenti(lecteur);
  const objet = useSelection(selection);
  const communs = { scene, t, contexte, objets, montrer };
  return (
    <>
      <div className="colonne-droite">
        {objet ? <PanneauDetail key={objet.id} objet={objet} {...communs}
          fermer={() => selection.choisir(null)} /> : (
          <Legende scene={scene} lecteur={lecteur} noms={noms} changerNoms={changerNoms} />
        )}
        <Onglets scene={scene} t={t} contexte={contexte} arrets={arrets} montrer={montrer} />
      </div>
      {objet && <Tracabilite key={objet.id} objet={objet} {...communs} />}
    </>
  );
}
