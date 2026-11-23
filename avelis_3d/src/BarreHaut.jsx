// Barre du haut : emblème et titre, recherche d'un objet, lecture et horloge simulée, alertes
// affichées par l'outil de pilotage, scénario simulé et aide. Les menus (alertes, scénario,
// aide) s'ouvrent un à la fois et se ferment d'un clic ailleurs ou avec Échap.
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { LIBELLES_SCHEMAS, NOMS_COURTS_IMPLANTATIONS, libelleObjet } from "./apparence.js";
import { horloge, horlogeCourte, instantSaisi } from "./donnees.js";
import Icone from "./Icone.jsx";
import { formater, rechercherObjets } from "./indicateurs.js";
import { alertesAffichees, valeursPilotage } from "./pilotage.js";

/** Menu ouvert (nom ou null) ; un clic hors de `conteneur` ou Échap le ferme. */
function useMenu(conteneur) {
  const [ouvert, changer] = useState(null);
  useEffect(() => {
    if (ouvert === null) return undefined;
    const fermer = (evenement) => {
      if (evenement.type === "keydown" ? evenement.key === "Escape"
        : !conteneur.current?.contains(evenement.target)) changer(null);
    };
    window.addEventListener("pointerdown", fermer);
    window.addEventListener("keydown", fermer);
    return () => {
      window.removeEventListener("pointerdown", fermer);
      window.removeEventListener("keydown", fermer);
    };
  }, [ouvert, conteneur]);
  return [ouvert, (nom) => changer((actuel) => (actuel === nom ? null : nom))];
}

/** Emblème générique (un module sur son socle) et titre. */
function Titre() {
  return (
    <div className="titre">
      <svg className="embleme" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="9" />
        <path d="M8 21V13l8-5 8 5v8zM8 24h16M13 21v-4h6v4" />
      </svg>
      <div>
        <strong>Avelis</strong>
        <span>Vue 3D du site de Torcy</span>
      </div>
    </div>
  );
}

/** Champ de recherche par identifiant ou libellé ; Entrée ou un clic montre l'objet. */
function Recherche({ scene, montrer }) {
  const [texte, changerTexte] = useState("");
  const trouves = rechercherObjets(scene, texte);
  const choisir = (objet) => {
    montrer(objet);
    changerTexte("");
  };
  return (
    <div className="recherche" role="search">
      <Icone nom="loupe" />
      <input type="search" value={texte} placeholder="Rechercher un objet…"
        title="Identifiant (MOD-, CAM-, LOT-…) ou libellé" aria-label="Rechercher un objet"
        onChange={(e) => changerTexte(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && trouves.length > 0) choisir(trouves[0]);
          if (e.key === "Escape") changerTexte("");
        }} />
      {trouves.length > 0 && (
        <ul className="carte menu propositions" aria-label="Objets trouvés">
          {trouves.map((objet) => (
            <li key={objet.id}>
              <button type="button" onClick={() => choisir(objet)}>
                <strong>{objet.id}</strong>
                <span>{libelleObjet(objet.type, scene.scenario.schema)} · {objet.libelle}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Horloge simulée ; un clic la change en zone de saisie : l'instant tapé (« Jour 2 · 21:21 »,
 * « 21:21 », « jour 3 ») est atteint à Entrée ; Échap ou un clic ailleurs annule. */
function Horloge({ lecteur, temps }) {
  const [saisie, changerSaisie] = useState(null);
  const [invalide, changerInvalide] = useState(false);
  if (saisie === null) {
    return (
      <button type="button" className="horloge" title="Cliquer pour taper un jour ou une heure"
        onClick={() => { changerInvalide(false); changerSaisie(horloge(lecteur.t, temps)); }}>
        {horloge(lecteur.t, temps)}
      </button>
    );
  }
  const valider = () => {
    const t = instantSaisi(saisie, temps, lecteur.t);
    if (t === null) { changerInvalide(true); return; }
    lecteur.aller(t);
    changerSaisie(null);
  };
  return (
    <input className="horloge" aria-label="Aller au jour et à l'heure" autoFocus
      value={saisie} aria-invalid={invalide} onFocus={(e) => e.target.select()}
      onChange={(e) => { changerInvalide(false); changerSaisie(e.target.value); }}
      onBlur={() => changerSaisie(null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") valider();
        if (e.key === "Escape") { e.stopPropagation(); changerSaisie(null); }
      }} />
  );
}

/** Lecture et pause, et horloge simulée (point animé pendant la lecture). */
function Lecture({ lecteur, temps }) {
  return (
    <div className="lecture-horloge" data-lecture={lecteur.lecture}>
      <button type="button" className="bouton-lecture" onClick={lecteur.basculer}
        aria-label={lecteur.lecture ? "Pause" : "Lecture"}
        title={lecteur.lecture ? "Pause" : "Lecture"}>
        <Icone nom={lecteur.lecture ? "pause" : "lecture"} />
      </button>
      <span className="point" aria-hidden="true" />
      <Horloge lecteur={lecteur} temps={temps} />
    </div>
  );
}

/** Une alerte du menu ; un clic montre l'objet visé, s'il est dans la scène, à l'instant de
 * l'alerte, et ferme le menu. */
function LigneAlerte({ alerte, scene, objets, montrer, fermer }) {
  const [t, , nature, id, , zone, message] = alerte;
  const objet = objets.get(id);
  const contenu = (
    <>
      <span className="entete-alerte">
        <span className="nature">{nature}</span>
        <time>{horlogeCourte(t, scene.temps)}</time>
      </span>
      <span className="texte-alerte">{message}</span>
      <span className="zone">{zone}</span>
    </>
  );
  return (
    <li>
      {objet ? (
        <button type="button" onClick={() => {
          montrer(objet, t);
          fermer();
        }}>{contenu}</button>
      )
        : <div>{contenu}</div>}
    </li>
  );
}

/** Cloche des alertes : pastille des alertes affichées depuis la dernière ouverture du menu,
 * menu des dernières alertes, la plus récente d'abord. */
function Alertes({ scene, lecteur, objets, ouvert, basculer, montrer }) {
  const nombre = valeursPilotage(scene, lecteur.t).alertes;
  const [vues, changerVues] = useState(0);
  const nouvelles = Math.max(0, nombre - vues);
  const ouvrir = () => {
    changerVues(nombre);
    basculer();
  };
  return (
    <div className="menu-ancre">
      <button type="button" className="bouton-rond" onClick={ouvrir} aria-expanded={ouvert}
        aria-label={`Alertes : ${nombre} affichées, ${nouvelles} nouvelles`} title="Alertes">
        <Icone nom="cloche" />
        {nouvelles > 0 && <span className="badge">{formater(nouvelles)}</span>}
      </button>
      {ouvert && (
        <section className="carte menu alertes" aria-label="Dernières alertes">
          <h2>Alertes <span>{formater(nombre)} affichées à cet instant</span></h2>
          {nombre === 0 ? <p className="vide">Aucune alerte affichée pour l'instant.</p> : (
            <ul>
              {alertesAffichees(scene, lecteur.t).map((alerte) => (
                <LigneAlerte key={`${alerte[3]}-${alerte[1]}`} alerte={alerte} scene={scene}
                  objets={objets} montrer={montrer} fermer={basculer} />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

/** Pastille du scénario simulé et son détail (choisi dans l'application). */
function Scenario({ scenario, ouvert, basculer }) {
  const implantation = NOMS_COURTS_IMPLANTATIONS[scenario.implantation] ?? scenario.implantation;
  const lignes = [["Implantation", scenario.implantation],
    ["Schéma", LIBELLES_SCHEMAS[scenario.schema]], ["Traçabilité", scenario.techno],
    ["Durée simulée", `${scenario.jours} jours`], ["Graine", scenario.graine]];
  return (
    <div className="menu-ancre">
      <button type="button" className="scenario" onClick={basculer} aria-expanded={ouvert}
        title="Scénario simulé">
        <Icone nom="reglages" />
        <span>{formater(scenario.cadence)} logements/an · {implantation}</span>
      </button>
      {ouvert && (
        <section className="carte menu details-scenario" aria-label="Scénario simulé">
          <h2>Scénario simulé</h2>
          <dl>
            {lignes.map(([nom, valeur]) => (
              <div key={nom}><dt>{nom}</dt><dd>{valeur}</dd></div>
            ))}
          </dl>
          <p className="vide">Il se choisit dans l'application, avant d'ouvrir la vue 3D.</p>
        </section>
      )}
    </div>
  );
}

/** Aide à la navigation, à la souris et au clavier. */
function Aide({ ouvert, basculer }) {
  return (
    <div className="menu-ancre">
      <button type="button" className="bouton-rond" onClick={basculer} aria-expanded={ouvert}
        aria-label="Aide à la navigation" title="Aide à la navigation">
        <Icone nom="aide" />
      </button>
      {ouvert && (
        <section className="carte menu aide" aria-label="Aide à la navigation">
          <h2>Souris</h2>
          <p>Clic gauche : tourner · clic droit : déplacer · molette : zoomer · clic sur un
            objet : le sélectionner</p>
          <h2>Clavier</h2>
          <p><kbd>Z</kbd> <kbd>Q</kbd> <kbd>S</kbd> <kbd>D</kbd> ou flèches : se déplacer
            · <kbd>A</kbd> <kbd>E</kbd> : tourner · <kbd>Maj</kbd> : plus vite
            · <kbd>Échap</kbd> : désélectionner</p>
        </section>
      )}
    </div>
  );
}

/** Barre du haut ; `montrer(objet)` va à un instant où l'objet est visible, le sélectionne et
 * centre la vue sur lui. */
export default function BarreHaut({ scene, lecteur, objets, montrer }) {
  useSyncExternalStore(lecteur.abonner, lecteur.lireVersion);
  const barre = useRef(null);
  const [ouvert, basculer] = useMenu(barre);
  const menu = (nom) => ({ ouvert: ouvert === nom, basculer: () => basculer(nom) });
  return (
    <header className="carte barre-haut" ref={barre}>
      <Titre />
      <Recherche scene={scene} montrer={montrer} />
      <Lecture lecteur={lecteur} temps={scene.temps} />
      <span className="espace" />
      <Alertes scene={scene} lecteur={lecteur} objets={objets} montrer={montrer}
        {...menu("alertes")} />
      <Scenario scenario={scene.scenario} {...menu("scenario")} />
      <Aide {...menu("aide")} />
    </header>
  );
}
