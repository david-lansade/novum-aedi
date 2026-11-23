// Carte repliable : un en-tête (titre, actions, bouton qui replie ou déplie) et un contenu.
// Ouverte par défaut si la fenêtre est assez haute (HAUTEUR_DEPLIEE), sinon repliée : à
// 1 280 × 650, les cartes du bas laissent la place à la vue.
import { useState } from "react";

import Icone from "./Icone.jsx";

export const HAUTEUR_DEPLIEE = 800; // px de hauteur de fenêtre, au moins, pour déplier d'office

/** Vrai si la fenêtre est assez haute pour déplier une carte d'office. */
export function assezHaute() {
  return typeof window === "undefined" || window.innerHeight >= HAUTEUR_DEPLIEE;
}

/** État ouvert ou replié d'une carte, `ouverte` au départ (par défaut : assezHaute()). */
export function useRepli(ouverte = assezHaute()) {
  const [etat, changer] = useState(ouverte);
  return [etat, () => changer((valeur) => !valeur)];
}

export default function Repliable({ titre, ouverte, basculer, actions, className = "",
  etiquette, children }) {
  return (
    <section className={`carte repliable ${className}`} data-ouverte={ouverte}
      aria-label={etiquette ?? (typeof titre === "string" ? titre : undefined)}>
      <header className="entete-carte">
        <h2>{titre}</h2>
        {actions}
        <button type="button" className="bouton-rond replier" onClick={basculer}
          aria-expanded={ouverte} aria-label={ouverte ? "Replier" : "Déplier"}
          title={ouverte ? "Replier" : "Déplier"}>
          <Icone nom={ouverte ? "replier" : "deplier"} />
        </button>
      </header>
      {ouverte && children}
    </section>
  );
}
