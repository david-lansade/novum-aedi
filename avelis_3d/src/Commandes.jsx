// Curseur de temps, en bas : retour au début, curseur sur toute la durée simulée, avec le début
// de chaque jour et les instants d'affichage des alertes, et vitesse de lecture. La lecture et
// l'horloge sont dans la barre du haut (BarreHaut.jsx). Jumeau numérique : bouton « Direct », qui
// suit l'heure réelle. Maintenu appuyé sans bouger, le curseur passe en réglage fin (à la
// minute, curseurTemps.js) ; tant qu'il est appuyé, une bulle affiche l'heure précise.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { CURSEUR_FIN, VITESSES } from "./apparence.js";
import { immobile, instantAuPointeur, instantFin } from "./curseurTemps.js";
import { horloge } from "./donnees.js";
import Icone from "./Icone.jsx";
import { reperesTemps } from "./indicateurs.js";

const NOMBRE = new Intl.NumberFormat("fr-FR"); // 0,05 min/s
const JOURS_ETIQUETES_MAX = 15; // au-delà, un numéro de jour sur deux, sur trois…

/** Repères sous le curseur : traits et numéros des jours, marques des alertes. */
function Reperes({ scene }) {
  const { jours, alertes } = useMemo(() => reperesTemps(scene), [scene]);
  const pas = Math.ceil(jours.length / JOURS_ETIQUETES_MAX);
  return (
    <div className="reperes" aria-hidden="true">
      {alertes.map((part, i) => (
        <span key={`a${i}`} className="marque-alerte" style={{ "--part": part }} />
      ))}
      {jours.map(({ part, numero }) => (
        <span key={numero} className="jour" style={{ "--part": part }}>
          {(numero - 1) % pas === 0 && `J${numero}`}
        </span>
      ))}
    </div>
  );
}

/** Glisser sur le curseur de temps : le pointeur est capturé par la zone du curseur (l'entrée
 * elle-même ne reçoit que le clavier). Rend {appuye, fin, gestes} : gestes à poser sur la zone. */
function useGlisserTemps(lecteur, entree) {
  const geste = useRef(null);
  const [etat, changerEtat] = useState({ appuye: false, fin: false });
  const attendre = (g) => {
    clearTimeout(g.minuterie);
    g.attente = g.x;
    g.minuterie = setTimeout(() => {
      Object.assign(g, { fin: true, tDepart: lecteur.t, xDepart: g.x });
      changerEtat({ appuye: true, fin: true });
    }, CURSEUR_FIN.delai);
  };
  const suivre = (e) => {
    const g = geste.current;
    const cadre = e.currentTarget.getBoundingClientRect();
    g.x = e.clientX - cadre.left;
    if (g.fin) lecteur.aller(instantFin(g.tDepart, g.x - g.xDepart, lecteur.duree));
    else {
      if (!immobile(g.attente, g.x)) attendre(g);
      lecteur.aller(instantAuPointeur(g.x, cadre.width, lecteur.duree));
    }
  };
  const finir = () => {
    if (!geste.current) return;
    clearTimeout(geste.current.minuterie);
    geste.current = null;
    changerEtat({ appuye: false, fin: false });
  };
  useEffect(() => finir, []);
  const gestes = {
    onPointerDown: (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      entree.current?.focus();
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // pointeur déjà relâché : le glisser s'arrêtera à son premier mouvement hors du curseur
      }
      geste.current = { fin: false, x: 0, attente: Infinity };
      suivre(e);
      attendre(geste.current);
      changerEtat({ appuye: true, fin: false });
    },
    onPointerMove: (e) => { if (geste.current) suivre(e); },
    onPointerUp: finir,
    onPointerCancel: finir,
  };
  return { ...etat, gestes };
}

/** Bulle au-dessus du pouce : l'heure précise, et « Réglage fin » une fois passé à la minute. */
function BulleTemps({ t, temps, fin, progression }) {
  return (
    <output className="bulle-temps" data-fin={fin} style={{ "--progression": progression }}>
      <strong>{horloge(t, temps)}</strong>
      <span>{fin ? "Réglage fin · à la minute" : "Maintenir pour régler à la minute"}</span>
    </output>
  );
}

export default function Commandes({ lecteur, scene }) {
  useSyncExternalStore(lecteur.abonner, lecteur.lireVersion);
  const entree = useRef(null);
  const glisser = useGlisserTemps(lecteur, entree);
  const progression = lecteur.duree > 0 ? lecteur.t / lecteur.duree : 0;
  return (
    <footer className="carte commandes">
      <button type="button" className="bouton-rond" onClick={() => lecteur.aller(0)}
        aria-label="Revenir au début" title="Revenir au début">
        <Icone nom="debut" />
      </button>
      <div className="temps" data-fin={glisser.fin} {...glisser.gestes}>
        {glisser.appuye && <BulleTemps t={lecteur.t} temps={scene.temps} fin={glisser.fin}
          progression={progression} />}
        <input ref={entree} className="curseur" type="range" min={0} max={lecteur.duree} step={1}
          value={lecteur.t} onChange={(e) => lecteur.aller(Number(e.target.value))}
          aria-label="Instant simulé" style={{ "--progression": `${progression * 100}%` }} />
        <Reperes scene={scene} />
      </div>
      {scene.direct && (
        <button type="button" className="direct" data-actif={lecteur.direct}
          onClick={() => lecteur.suivreDirect()} aria-pressed={lecteur.direct}
          title="Suivre l'heure réelle (scans du jumeau numérique)">
          ● Direct
        </button>
      )}
      <label className="vitesse">
        <span>Vitesse</span>
        <select value={lecteur.vitesse} onChange={(e) => lecteur.regler(Number(e.target.value))}>
          {VITESSES.map((v) => <option key={v} value={v}>{NOMBRE.format(v)} min/s</option>)}
        </select>
      </label>
    </footer>
  );
}
