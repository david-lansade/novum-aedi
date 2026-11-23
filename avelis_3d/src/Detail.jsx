// Objet sélectionné : panneau de détail (type, identifiant, statut, progression des points de
// contrôle, propriétés et objets liés) et timeline de traçabilité (étapes reliées, heure de
// chaque événement, étape courante en avant). Contenu : details.js. Mis à jour au rythme de
// PAS_PANNEAUX_MS pendant la lecture, aussitôt à un changement de sélection.
import { useMemo, useSyncExternalStore } from "react";

import { COULEURS_OBJETS, libelleObjet } from "./apparence.js";
import {
  ETATS, etapesTracabilite, progression, proprietes, statutObjet,
} from "./details.js";
import Icone from "./Icone.jsx";
import { ralentir } from "./lecteur.js";
import Repliable, { useRepli } from "./Repliable.jsx";

export const PAS_PANNEAUX_MS = 125;
const ICONES_ETATS = { affichee: "coche", attente: "sablier", non_lue: "barre", a_venir: null,
  position: "camion" };

/** Instant du lecteur, relu au plus toutes les PAS_PANNEAUX_MS ms. */
export function useInstantRalenti(lecteur) {
  const abonner = useMemo(() => ralentir(lecteur, PAS_PANNEAUX_MS), [lecteur]);
  useSyncExternalStore(abonner, lecteur.lireVersion);
  return lecteur.t;
}

/** Objet sélectionné, ou null. */
export function useSelection(selection) {
  useSyncExternalStore(selection.abonner, selection.lireVersion);
  return selection.objet;
}

/** Identifiant cliquable s'il est dans la scène (montre l'objet), texte sinon. */
function Lien({ id, objets, montrer }) {
  const objet = objets.get(id);
  if (!objet) return <span>{id}</span>;
  return <button type="button" className="lien" onClick={() => montrer(objet)}>{id}</button>;
}

/** Barre de progression des points de contrôle obligatoires. */
function Progression({ valeur }) {
  const { faits, total, affiches } = valeur;
  return (
    <div className="progression">
      <div className="piste" role="progressbar" aria-valuemin={0} aria-valuemax={total}
        aria-valuenow={faits} aria-label="Points de contrôle survenus">
        <span className="survenus" style={{ width: `${(faits / total) * 100}%` }} />
        <span className="affiches" style={{ width: `${(affiches / total) * 100}%` }} />
      </div>
      <p>{faits} / {total} points de contrôle · {affiches} affichés</p>
    </div>
  );
}

/** Panneau de détail de l'objet sélectionné (colonne de droite). */
export function PanneauDetail({ scene, objet, t, contexte, objets, montrer, fermer }) {
  const statut = statutObjet(scene, objet, t, contexte);
  const avancement = progression(scene, objet, t, contexte);
  return (
    <section className="carte panneau-detail" aria-label={`Détail de ${objet.id}`}>
      <header className="entete-carte">
        <span className="pastille" style={{ background: COULEURS_OBJETS[objet.type] }} />
        <h2>{libelleObjet(objet.type, scene.scenario.schema)}</h2>
        <button type="button" className="bouton-rond" onClick={fermer}
          aria-label="Fermer le détail (désélectionner)" title="Fermer (Échap)">
          <Icone nom="fermer" />
        </button>
      </header>
      <p className="identifiant">{objet.id}</p>
      <span className="statut" data-ton={statut.ton}>{statut.texte}</span>
      {avancement && <Progression valeur={avancement} />}
      <dl className="proprietes">
        {proprietes(scene, objet, t, contexte).map(({ nom, valeur, liens }) => (
          <div key={nom}>
            <dt>{nom}</dt>
            <dd>{liens ? liens.map((id) => <Lien key={id} id={id} objets={objets}
              montrer={montrer} />) : valeur}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Infobulle d'une étape : zone, heure d'affichage, message. */
function titreEtape({ nom, etat, zone, affichage, message }) {
  return [nom, ETATS[etat], zone, affichage && `affichée à ${affichage}`, message]
    .filter(Boolean).join(" · ");
}

/** Étapes reliées, la courante en avant. */
function Etapes({ etapes, courante }) {
  return (
    <ol className="etapes">
      {etapes.map((etape, i) => (
        <li key={`${etape.nom}-${i}`} data-etat={etape.etat} data-courante={i === courante}
          title={titreEtape(etape)}>
          <span className="rond">{ICONES_ETATS[etape.etat] ? <Icone
            nom={ICONES_ETATS[etape.etat]} /> : i + 1}</span>
          <span className="nom">{etape.nom}</span>
          <time>{etape.heure ?? "—"}</time>
        </li>
      ))}
    </ol>
  );
}

/** Légende des états des étapes présents dans la timeline. */
function LegendeEtats({ etapes }) {
  const presents = Object.keys(ETATS).filter((etat) => etapes.some((e) => e.etat === etat));
  return (
    <ul className="legende-etats">
      {presents.map((etat) => <li key={etat} data-etat={etat}>{ETATS[etat]}</li>)}
    </ul>
  );
}

/** Timeline de traçabilité de l'objet sélectionné (en bas à gauche), repliable. */
export function Tracabilite({ scene, objet, t, contexte, objets, montrer }) {
  const [ouverte, basculer] = useRepli(true);
  const { etapes, courante } = etapesTracabilite(scene, objet, t, contexte);
  const titre = <>Traçabilité · {objet.id} <span>{scene.scenario.techno}</span></>;
  return (
    <Repliable className="tracabilite" titre={titre} etiquette={`Traçabilité de ${objet.id}`}
      ouverte={ouverte} basculer={basculer}
      actions={ouverte && etapes.length > 0 && <LegendeEtats etapes={etapes} />}>
      {etapes.length > 0 ? <Etapes etapes={etapes} courante={courante} /> : (
        <p className="vide">
          Pas de point de contrôle propre : ses panneaux sont tracés sur leur module
          {objet.liens?.module && <> (<Lien id={objet.liens.module} objets={objets}
            montrer={montrer} />)</>}.
        </p>
      )}
    </Repliable>
  );
}
