// Commandes de la vue, en colonne : zoom avant et arrière, quart de tour dans chaque sens,
// recentrer (vue d'ensemble) et vue de dessus (actions de Camera.jsx) ; mode « Intérieurs »
// (murs coupés, sans toits : Batiments.jsx) ; cycle jour et nuit et météo (Ciel.jsx), dont le
// titre donne la météo affichée ; mode « flux » (Flux.jsx) ; vue à la première personne
// (PremierePersonne.jsx).
import Icone from "./Icone.jsx";

/** Bouton carré à icône ; le titre sert d'infobulle et de nom accessible. `enfonce` (booléen)
 * en fait un bouton à bascule. */
function Bouton({ icone, titre, action, enfonce }) {
  return (
    <button type="button" title={titre} aria-label={titre} onClick={action}
      aria-pressed={enfonce}>
      <Icone nom={icone} />
    </button>
  );
}

export default function CommandesVue({ commandes, interieurs, basculerInterieurs, cycle,
  basculerCycle, meteo, flux, basculerFlux, premiere, basculerPremiere }) {
  return (
    <nav className="carte commandes-vue" aria-label="Commandes de la vue">
      <Bouton icone="plus" titre="Zoom avant" action={() => commandes.zoomer?.(1)} />
      <Bouton icone="moins" titre="Zoom arrière" action={() => commandes.zoomer?.(-1)} />
      <span className="separateur" />
      <Bouton icone="gauche" titre="Tourner d'un quart de tour vers la gauche"
        action={() => commandes.tourner?.(-1)} />
      <Bouton icone="droite" titre="Tourner d'un quart de tour vers la droite"
        action={() => commandes.tourner?.(1)} />
      <span className="separateur" />
      <Bouton icone="maison" titre="Recentrer (vue d'ensemble)"
        action={() => commandes.recentrer?.()} />
      <Bouton icone="dessus" titre="Vue de dessus" action={() => commandes.vueDessus?.()} />
      <span className="separateur" />
      <Bouton icone="interieurs" titre="Intérieurs : murs coupés, sans toits"
        action={basculerInterieurs} enfonce={interieurs} />
      <Bouton icone="ciel" titre={`Jour, nuit et météo${cycle ? ` (${meteo})` : ""}`}
        action={basculerCycle} enfonce={cycle} />
      <Bouton icone="flux" titre="Flux : chemins les plus empruntés, plus épais selon le trafic"
        action={basculerFlux} enfonce={flux} />
      <Bouton icone="oeil"
        titre="Première personne : Z Q S D pour marcher, glisser pour regarder, Échap pour sortir"
        action={basculerPremiere} enfonce={premiere} />
    </nav>
  );
}
