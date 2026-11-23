// Police Inter (variable, graisses 100 à 900), embarquée par @fontsource-variable/inter :
// seulement son jeu latin (accents, « œ », guillemets français), copié dans dist/ par Vite.
// Tant qu'elle n'est pas chargée, ou si elle ne l'est pas, la page garde la police du système.
// Licence (OFL 1.1) : avelis_3d/LICENCE_POLICE_INTER.txt, à garder avec dist/.
import adresseLatin from "@fontsource-variable/inter/files/inter-latin-wght-normal.woff2?url";

export const NOM_POLICE = "Inter Variable"; // repris par style.css (--police)

/** Déclare la police et lance son chargement ; une erreur est sans conséquence. */
export function chargerPolice() {
  if (typeof FontFace === "undefined") return;
  const police = new FontFace(NOM_POLICE, `url(${adresseLatin}) format("woff2")`,
    { weight: "100 900", style: "normal", display: "swap" });
  document.fonts.add(police);
  police.load().catch(() => {});
}
