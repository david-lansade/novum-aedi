// Icônes de l'interface, dessinées au trait sur une grille de 24 × 24 (couleur du texte).

export const ICONES = {
  plus: "M12 5v14M5 12h14",
  moins: "M5 12h14",
  gauche: "M4 4v5h5M4.75 8.62A8 8 0 1 1 4.48 14.74",
  droite: "M20 4v5h-5M19.25 8.62A8 8 0 1 0 19.52 14.74",
  maison: "M4 11l8-7 8 7M6 9.5V20h12V9.5M10 20v-5h4v5",
  dessus: "M4 4h16v16H4zM9 9h6v6H9z",
  interieurs: "M3 9l9-6 9 6M5 13v7h14v-7M9 20v-4h6v4", // toit soulevé au-dessus des murs
  loupe: "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM15.5 15.5L20 20",
  lecture: "M8 5v14l11-7z",
  pause: "M8 5v14M16 5v14",
  debut: "M6 5v14M18 5v14l-10-7z",
  cloche: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
  reglages: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
  aide: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"
    + "M12 17.5v.01",
  fermer: "M6 6l12 12M18 6L6 18",
  replier: "M6 15l6-6 6 6",
  deplier: "M6 9l6 6 6-6",
  coche: "M6 12.5l4 4L18 8",
  sablier: "M7 4h10M7 20h10M8 4c0 4 8 5 8 8s-8 4-8 8M16 4c0 4-8 5-8 8",
  barre: "M7 12h10",
  camion: "M3 7h11v9H3zM14 10h4l3 3v3h-7",
  termines: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l2.7 2.7L16 9.5",
  expedies: "M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17 19a1.5 1.5"
    + " 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  en_cours: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  stock_pf: "M4 8l8-4 8 4v9l-8 4-8-4zM4 8l8 4 8-4M12 12v9",
  camions: "M4 18V8l8-4 8 4v10M8 18v-6h8v6M4 18h16",
  ciel: "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4"
    + "M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4", // soleil
  flux: "M4 18c4 0 4-12 8-12s4 12 8 12M4 12h3M17 12h3", // chemins empruntés
  oeil: "M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"
    + "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", // première personne
};

/** Icône au trait ; décorative (aria-hidden) : le nom accessible est porté par le bouton. */
export default function Icone({ nom }) {
  return (
    <svg className="icone" viewBox="0 0 24 24" aria-hidden="true">
      <path d={ICONES[nom]} />
    </svg>
  );
}
