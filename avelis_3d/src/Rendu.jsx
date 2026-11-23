// Rendu final, à la place de celui de React Three Fiber : la scène est dessinée dans une cible
// multi-échantillonnée (anticrénelage), l'occlusion ambiante de three (GTAOPass) assombrit les
// recoins et le contact des objets avec le sol, puis la passe de sortie applique le tone mapping
// et l'espace de couleurs de l'écran.
import { useEffect, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { HalfFloatType, WebGLRenderTarget } from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";

import { OCCLUSION } from "./apparence.js";

const ECHANTILLONS_MSAA = 4;
const PRIORITE_RENDU = 1; // un useFrame de priorité positive remplace le rendu par défaut

/** GTAO calculé à une résolution réduite (OCCLUSION.resolution), puis étiré à la taille de
 * l'écran : l'occlusion est floue par nature, et à pleine résolution elle coûtait à elle seule
 * plus de 30 ms par image sur le GPU intégré de l'équipe. Il ignore aussi ce qui est translucide
 * (`userData.sansOcclusion` : clôtures, ombres de contact, halo) et les arêtes de drei, en plus
 * des points et lignes que GTAOPass ignore déjà : sinon leur profondeur assombrirait ce que l'on
 * voit au travers. */
class OcclusionDouce extends GTAOPass {
  setSize(largeur, hauteur) {
    const reduire = (taille) => Math.max(1, Math.round(taille * OCCLUSION.resolution));
    super.setSize(reduire(largeur), reduire(hauteur));
  }

  _overrideVisibility() {
    super._overrideVisibility();
    this.scene.traverse((objet) => {
      if ((objet.userData.sansOcclusion || objet.isLineSegments2) && objet.visible) {
        objet.visible = false;
        this._visibilityCache.push(objet);
      }
    });
  }
}

/** Chaîne de passes : rendu anticrénelé, occlusion ambiante, sortie. */
function creerChaine(gl, scene, camera) {
  const cible = new WebGLRenderTarget(1, 1, { type: HalfFloatType, samples: ECHANTILLONS_MSAA });
  const chaine = new EffectComposer(gl, cible);
  chaine.addPass(new RenderPass(scene, camera));
  const occlusion = new OcclusionDouce(scene, camera);
  occlusion.updateGtaoMaterial({ radius: OCCLUSION.rayon, thickness: OCCLUSION.epaisseur,
    scale: OCCLUSION.echelle, samples: OCCLUSION.echantillons });
  occlusion.updatePdMaterial({ samples: OCCLUSION.echantillons });
  occlusion.blendIntensity = OCCLUSION.intensite;
  chaine.addPass(occlusion);
  chaine.addPass(new OutputPass());
  return chaine;
}

export default function Rendu() {
  const { gl, scene, camera, size, viewport } = useThree();
  const chaine = useMemo(() => creerChaine(gl, scene, camera), [gl, scene, camera]);
  useEffect(() => {
    chaine.setPixelRatio(viewport.dpr);
    chaine.setSize(size.width, size.height);
  }, [chaine, size, viewport.dpr]);
  useEffect(() => () => {
    for (const passe of chaine.passes) passe.dispose();
    chaine.dispose();
  }, [chaine]);
  useFrame((_, secondes) => chaine.render(secondes), PRIORITE_RENDU);
  return null;
}
