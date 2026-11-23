# avelis_flux — Flux logistiques et données

Imagine & Make 2026, défi Avelis, Bloc 3. Application de bureau qui dimensionne les flux du site de Torcy,
simule la production par événements discrets et démontre la traçabilité de chaque composant.

**Toutes les valeurs estimées sont des hypothèses.** Dans `modele.py`, chaque valeur porte la marque « A »
(donnée Avelis) ou « H » (hypothèse de l'équipe). Les hypothèses ajoutées par l'IA portent en plus la mention
« ajoutée — à valider ».

## Installation sous Windows

1. Python 3.10 ou plus récent : `py -3 --version`.
2. Dépendances (bibliothèque standard + matplotlib, numpy, pillow) :

   ```powershell
   py -3 -m pip install -r avelis_flux/requirements.txt
   ```

3. Facultatif, pour les QR codes et les étiquettes (l'application fonctionne sans) :

   ```powershell
   py -3 -m pip install "qrcode[pil]"
   ```

4. Pour lire les accents dans la console : `$env:PYTHONIOENCODING = "utf-8"`.

La vue 3D (bouton « 4 Vue 3D ») ne demande rien de plus : elle est livrée construite dans `avelis_3d/dist/`
et s'ouvre dans le navigateur par défaut, sans Internet. Node.js n'est nécessaire que pour la modifier
(voir « Modifier la vue 3D »).

## Lancement et vérifications

| Commande | Rôle |
|---|---|
| `py -3 avelis_flux/app.py` | Lance l'application. |
| `py -3 avelis_flux/modele.py` | 28 tests intégrés du modèle, puis chiffres clés à 1 500 logements/an comparés aux ordres de grandeur attendus. |
| `py -3 avelis_flux/simulation.py` | 22 tests intégrés de la simulation, puis résultats des 3 technologies × 2 schémas et contrôle du §6 (environ 7 s). |
| `py -3 avelis_flux/scene_3d.py` | 18 tests intégrés : export de la scène 3D (positions et tableau de pilotage recalculés comparés à la simulation, traçabilité, liens, résultats, volume à 60 jours) et serveur local de la vue 3D. |
| `py -3 avelis_flux/jumeau.py` | 9 tests intégrés du jumeau numérique, sur un vrai atelier de scan en mémoire : positions, indicateurs, base vidée, lecture par l'API et par le fichier, changement de plan, comparaison avec la simulation (environ 10 s). |
| `py -3 avelis_flux/analyse_jumeau.py` | 6 tests intégrés de l'analyse : poste ralenti détecté, prévision vérifiée à la main, prévision meilleure que la prévision naïve sur la simulation (environ 10 s). |
| `py -3 avelis_flux/decisions.py` | 7 tests intégrés des décisions : chaque règle, rien envoyé sans validation, envoi du message modifié, pas de répétition avant le délai. |
| `py -3 avelis_flux/tests_interface.py` | 54 combinaisons × 4 vues, chaque écran contrôlé automatiquement (textes tronqués ou qui se chevauchent, zones de texte écrasées, figures rognées), mise en page à trois tailles d'écran, captures dans `captures/`, exports, jumeau numérique (environ 15 min). |
| `py -3 avelis_flux/tests_interface.py --rapide` | Version courte (4 combinaisons). |

Pendant `tests_interface.py`, la fenêtre de test s'ouvre vraiment et se remet au premier plan avant chaque
capture. Si une capture reste noire (fenêtre réduite, session verrouillée), elle est comptée comme un échec.

### Écran

- La fenêtre s'ouvre en 1 600 × 960 px (à 100 %) si l'écran le permet, sinon agrandie.
- Textes, marges et figures suivent la mise à l'échelle de Windows (125 %, 150 %).
- Taille minimale prise en charge : 1 280 × 650 px à 100 %, soit un écran 1 920 × 1 080 réglé à 150 %.
- À cette largeur, les dernières colonnes de la chronologie (vue 3) se lisent avec la barre de défilement
  horizontale.

## Rôle de chaque commande

### Barre latérale

| Commande | Effet |
|---|---|
| **Cadence (logements/an)** | Curseur de 400 à 2 500 par pas de 50. Pris en compte au prochain « Recalculer ». |
| **Implantation** | « Proposée : Torcy + extension (flux en U) », « Optimisée : Torcy + extension » ou « Actuelle : site seul (sans extension) ». L'implantation optimisée garde le foncier et la voirie de la proposée ; ses zones sont à la taille du besoin à 1 500 logements/an, les lignes 2D et pods sont accolées à la halle d'assemblage, les bureaux sont à l'accueil près du portail et l'expédition au-dessus du stock de produits finis ; une réserve est prévue pour les lignes de 2030. Résultat : 580 m par sous-ensemble au lieu de 681, gamme 2D de 177 m au lieu de 343, aucun croisement de flux. |
| **Schéma industriel** | Usine unique (un module 3D par convoi) ou usine mère + satellites : Torcy fabrique les sous-ensembles (murs 2D et pods) et les consolide en kits modules (3 par semi) ; les usines satellites assemblent les volumes. |
| **Technologie de traçabilité** | RFID + IoT, QR code ou papier : taux de lecture et délai d'affichage différents. |
| **Jours simulés, Graine** | Durée de la simulation (1 à 60 jours) et graine aléatoire. Même graine, mêmes résultats. |
| **Recalculer le scénario** | Relance les calculs et la simulation, puis met à jour les trois vues. Une saisie invalide est refusée avec un message. |
| **1 Statistiques, 2 Schéma de l'usine et flux, 3 Traçabilité d'un module** | Changent de vue ; le bouton de la vue affichée est orange. |
| **5 Jumeau numérique (scans)** | L'atelier tel que les scans d'`avelis_scan` le décrivent, et sa comparaison avec la simulation (voir « Vue 5 »). |
| **4 Vue 3D (navigateur)** | Ouvre la vue 3D du scénario calculé dans le navigateur, à l'instant du curseur de la vue 2 (au milieu de la simulation si le curseur est au début). Un nouveau clic publie le scénario recalculé. |
| **Exporter le journal (CSV ; UTF-8-sig)** | Journal de traçabilité complet. Séparateur « ; », décimales à virgule, lisible dans Excel avec les accents. |
| **Exporter toutes les figures (PNG 300 dpi)** | 11 figures dans `exports/` : les 6 graphiques, la grille 2 × 3, les 2 cartes, la courbe de coût, le schéma à l'instant du curseur. |
| **Générer des étiquettes QR (PNG)** | Une étiquette par module expédié et par pod, dans `exports/etiquettes_qr/`. Désactivé, avec une info-bulle, si `qrcode` est absent. |

### Vue 1 — Statistiques

- **Six tuiles** :
  - cadence atteinte (simulée, dès le jour 3) ;
  - distance d'un sous-ensemble (gamme pod + gamme module) ;
  - m² de stockage pour 1 000 logements/an ;
  - part des modules expédiés tracés de bout en bout ;
  - délai moyen entre une alerte et son affichage ;
  - nombre de ruptures, attentes et blocages.
- **Tableau des chiffres** : 7 catégories (cadence, logistique, surfaces, comparaison des deux implantations,
  simulation, traçabilité, utilisation des ressources), colonne H/A.
- **Graphiques** :
  - modules par jour face à l'objectif ;
  - utilisation des ressources (rouge au-delà de 85 %) ;
  - en-cours et stocks dans le temps ;
  - Pareto des défauts ;
  - coût annuel des réseaux (CO2 en annotation) ;
  - évolutivité (surface nécessaire face aux surfaces utilisables).
- **Réseau** : cartes de l'usine unique et du réseau avec satellites (épaisseur proportionnelle à la demande),
  coût par logement selon la cadence avec les points de bascule, recommandation et tableau comparatif.
- **Paramètres** : toutes les valeurs du modèle sont modifiables, en deux sous-onglets.
  - *Hypothèses* : double-cliquer sur une ligne pour changer sa valeur (une séquence s'écrit avec « ; »
    entre ses valeurs, par exemple `18 ; 35`) ; « ↺ Valeur par défaut » rétablit la valeur d'origine ; les
    lignes modifiées sont sur fond orangé ; un champ « Rechercher » filtre la liste. Chaque saisie est
    contrôlée (nombre entier si la valeur d'origine l'est, valeur positive, taux entre 0 et 1, minimum
    inférieur au maximum).
  - *Réseau : chantiers et usines satellites* : choisir une ville de France puis « Ajouter comme
    chantier » ou « Ajouter comme usine satellite » ; double-cliquer sur une cellule pour changer un nom,
    une position (degrés) ou une part ; « ✕ Retirer » supprime une ligne. Les parts des chantiers doivent
    totaliser 100 % (« Répartir les parts à 100 % » les ajuste proportionnellement).
  - Les modifications restent en attente jusqu'à « Appliquer et recalculer » (ou « Recalculer le
    scénario », ou « Appliquer et voir la carte du réseau », qui ouvre l'onglet Réseau) : tout est
    contrôlé d'un bloc ; si le calcul échoue, les paramètres précédents sont rétablis. « Tout rétablir
    par défaut » remet toutes les valeurs d'origine. Les modifications ne sont pas enregistrées entre
    deux lancements de l'application.

### Vue 2 — Schéma de l'usine et flux

- **Plan** :
  - site et extension, hachurée si elle n'est pas utilisée ;
  - route publique, voirie poids lourds, aire de retournement, portail, quais ;
  - zones colorées par catégorie ;
  - flèches en L par gamme (épaisseur proportionnelle aux unités par jour, distance en m) ;
  - échelle de 50 m, nord, légende.
- **Objets animés** : ronds pour les pods (orange), les kits 2D (bleu clair) et les lots (bleu) ; carrés pour
  les modules (violet) et les camions (gris foncé).
- **Commandes** :
  - **Lecture/Pause** ;
  - **Début** (retour à J1 06:00) ;
  - **Vitesse**, de 5 à 240 minutes simulées par seconde ;
  - **curseur de temps** ;
  - case **Flèches de flux** ;
  - barre d'outils matplotlib (zoom, déplacement, enregistrement).
- **Tableau de pilotage** (fond sombre) : horloge « Jour N · HH:MM », indicateurs instantanés, et les 9
  dernières alertes **déjà affichées** avec leur heure réelle, leur heure d'affichage et le délai.
  « Camions sur site » compte les camions entrés par le portail et pas encore ressortis : ceux qui roulent
  sur la route publique n'en font pas partie.
- **Mode suivi** (lancé depuis la vue 3) : le module ou, avant son assemblage, son pod, est mis en
  surbrillance (halo, marqueur agrandi) avec son trajet déjà parcouru ; le bandeau indique son dernier
  événement. **Arrêter le suivi** pour le quitter.

### Vue 3 — Traçabilité d'un module

- **Module** : liste de tous les modules ; par défaut, le premier dont le pod a eu un défaut.
- **Modules en défaut** (au-dessus de la chronologie) : un clic ouvre la fiche du module.
- **Fiche** :
  - généalogie module ← pod ← lot ← camion ← fournisseur ;
  - destination, délai OF → stock PF, distance parcourue ;
  - trace COMPLÈTE ou INCOMPLÈTE (avec les points manquants) ;
  - qualité : défaut, cause retrouvée ou non ;
  - QR code, à côté de l'identifiant, et son contenu en clair (sans `qrcode`, le contenu seul).
- **Chronologie** : tous les événements du module, de son pod, de son lot et des camions liés. Pod en orange,
  lot en bleu, alertes sur fond rose, événements non lus en gris.
- **Suivre ce module dans le schéma** : passe à la vue 2, place le curseur à l'OF du module et active le
  mode suivi.

### Vue 3D — dans le navigateur

- **Scène** :
  - le site et l'extension (pâle, bordée de tirets, si elle n'est pas utilisée) ;
  - la route publique, la voirie poids lourds, l'aire de retournement, le portail, les quais ;
  - des bâtiments sans toit, aux murs translucides, pour voir ce qu'ils contiennent ;
  - les noms des zones, le nord et l'échelle de 50 m.
- **Objets** : camions, lots, kits 2D, pods et modules (kits modules en schéma satellites), aux gabarits des
  hypothèses et aux couleurs de la vue 2. Ils se déplacent exactement comme dans la simulation ; les camions
  sont orientés dans le sens de la marche.
- **Navigation** : clic gauche pour tourner, clic droit pour déplacer, molette pour zoomer vers le pointeur ;
  au clavier, Z Q S D ou les flèches pour se déplacer, A et E pour tourner. Colonne de boutons : zoom,
  quart de tour, vue d'ensemble, vue de dessus, mode « Intérieurs » ; case **Noms des zones**.
- **Barre du haut** : recherche d'un objet par identifiant ou libellé (la vue va à un instant où il est sur
  le site et le sélectionne), **Lecture/Pause** et horloge « Jour N · HH:MM », alertes affichées par
  l'outil de pilotage (un clic montre l'objet à l'instant de l'alerte), scénario simulé, aide.
- **Cartes d'indicateurs** : terminés du jour face à l'objectif à cette heure, expédiés, en-cours, stock
  produits finis, camions sur site, avec leur variation sur la dernière heure simulée : les valeurs du
  tableau de pilotage de la vue 2.
- **Curseur de temps** : début de chaque jour et instants des alertes ; **Début** et **Vitesse** (0,05 à
  240 minutes simulées par seconde). La légende donne le nombre d'objets visibles par type.
- **Sélection** (clic sur un objet, recherche ou alerte ; Échap pour désélectionner) : un panneau de
  détail remplace la légende (type, identifiant, statut, avancement des points de contrôle,
  propriétés, objets liés cliquables), et une timeline de traçabilité s'ouvre en bas : étapes
  reliées, heure de chaque événement, étape courante entourée, couleur selon l'état (lue et
  affichée, en attente de lecture, non lue, à venir). Le toit du bâtiment où se trouve l'objet
  est retiré.
- **Onglets Quais / Camions / Stocks** : état de chaque quai (libre, chargement, déchargement),
  camions présents et leur lieu, zones de stock (valeur du tableau de pilotage et objets posés).
- **Cartes repliables** : légende, onglets et timeline se replient ; sous 800 px de haut, les
  onglets sont repliés d'office.
- **Survol** : identifiant, type et description de l'objet (fournisseur, conformité, pod…), entouré d'un halo
  rose.
- La page est servie par un serveur local, accessible depuis ce poste seulement. Elle cesse de répondre
  à la fermeture de l'application.

### Vue 5 — Jumeau numérique (scans)

Configuration retenue : **usine unique, implantation avec extension** (plan affiché au choix : liste
**Plan**, en haut à droite). Les données viennent de
l'application de scan `avelis_scan` (téléphone + PC) : chaque scan accepté place la pièce dans la zone du
plan de son poste (les noms de zones de `avelis_scan/config.py` sont ceux du plan).

- **Source des scans** : le serveur de scan à l'adresse indiquée (par défaut `http://localhost:8000`,
  API `GET /api/evenements?depuis=…` et `GET /api/pieces`) ; s'il n'est pas lancé, la base
  `avelis_scan/donnees/atelier.db` est lue directement, en lecture seule. Les scans sont relus chaque
  seconde, sans bloquer l'interface. **Se connecter** relit tout (autre adresse, base vidée…). Le bandeau
  indique la source lue et le nombre d'événements, ou l'erreur en rouge.
- **Réinitialiser les scans** : après confirmation, vide toute la base de scan (pièces, scans, défauts,
  cartes kanban, consignes) pour repartir de zéro, par le serveur de scan ou, s'il n'est pas lancé,
  directement dans le fichier. C'est la même action que « Vider la base » de la page `/pc`.
- **Onglet « Atelier en direct (scans) »**, construit comme la vue 2 :
  - même plan, mêmes flèches de flux (à la cadence du scénario), même légende ;
  - pièces scannées : modules (carrés violets), pods, kits 2D, lots, ossatures et composants suivis par
    numéro de série ; anneau rouge autour d'une pièce **en défaut** ou **à isoler** (lot bloqué) ;
    une pièce intégrée, expédiée ou mise au rebut quitte le plan ;
  - tableau de pilotage à l'heure réelle : terminés aujourd'hui face à l'objectif à cette heure (cadence du
    scénario, ouverture à 06:00), expédiés, en-cours de modules et de pods, défauts ouverts et lots
    bloqués, stocks ; les 9 dernières alertes (défauts, blocages de lots, scans refusés, retards kanban)
    avec le délai entre le scan sur le téléphone et son enregistrement ;
  - **● En direct** : la vue suit l'heure réelle ; **Lecture**, **Début** ou le curseur rejouent les
    scans passés (1 à 240 minutes par seconde) ; **○ Revenir au direct** pour revenir à maintenant ;
  - **Suivre** (barre du bas) : un module ou un pod, avec son trajet de zone en zone et son dernier
    scan ;
  - **Plan** : implantation proposée, optimisée ou actuelle. Seul le dessin change : les mêmes
    scans placent les pièces dans les zones de même nom du plan choisi.
- **Onglet « Comparaison avec la simulation »** : la simulation de la même usine (unique, plan affiché,
  QR code), aux cadence, durée et graine du scénario.
  - Tuiles : scans enregistrés, modules lancés, période observée, étapes en écart.
  - Indicateurs : délai OF → stock PF, modules terminés par jour, défauts par module, délai d'affichage
    d'un scan, part des modules expédiés tracés de bout en bout, scans refusés.
  - Durée de chaque étape des gammes module et pod (depuis l'étape précédente) : nombre de mesures, scans
    et simulation, écart (« plus lent », « plus rapide » au-delà de 50 %, hypothèse
    `seuil_ecart_jumeau`), et graphique en échelle logarithmique.
  - Sur la maquette, les gestes durent quelques minutes au lieu de plusieurs heures :
    l'hypothèse `echelle_temps_maquette` (onglet Paramètres) convertit une minute scannée en minutes
    d'usine. À 1, les durées sont comparées telles quelles (atelier réel).
- **Onglet « Décisions et prévisions (IA) »** : le jumeau propose, un humain décide.
  - Après chaque lecture des scans (au plus toutes les 5 s sans nouveau scan), le jumeau analyse
    l'atelier et évalue ses règles. Chaque décision nouvelle ouvre une **boîte de dialogue** :
    règle, motif chiffré, destinataires et consigne **modifiable** ; **Envoyer la consigne**
    (elle arrive sur le téléphone des postes par le serveur de scan), **Ignorer**, ou **Décider
    plus tard** (la décision reste en attente : la sélectionner dans le tableau, puis « Valider ou
    ignorer la décision sélectionnée »). Aucune consigne ne part sans validation.
  - Règles :
    - étape anormalement lente → le poste et le bureau ;
    - pièces bloquées (sans nouveau scan depuis 2 fois la durée estimée de l'étape suivante,
      dans la journée), regroupées par poste → le poste et le bureau ;
    - défauts répétés (2 de même catégorie au même poste en 60 min) → le poste et le bureau ;
    - retard sur l'objectif du jour (moins de 80 % de l'objectif à cette heure) → le bureau.
    Les retards kanban et les lots à isoler restent gérés par l'application de scan. Une décision
    envoyée ou ignorée n'est pas reproposée avant 60 min.
  - **Option A, fin de fabrication prévue** de chaque module en cours : somme des durées des étapes
    qui restent, chacune apprise des scans et rapprochée de la durée simulée tant qu'il y a peu de
    mesures, avec une fourchette p10–p90 ; en rose, un module qui a dépassé la durée prévue de son
    étape. Sa précision est mesurée sur la simulation de référence et affichée (par exemple 53 min
    d'erreur moyenne, contre 1 h 20 pour la prévision naïve « OF + délai moyen »).
  - **Option B, étapes anormalement lentes** : pour chaque étape, moyenne des 3 derniers passages
    face à la médiane des passages antérieurs (sinon à la durée simulée) ; « anormal » au-delà de
    1,5 fois, « à surveiller » au-delà de 1,25 fois ou si un passage récent dépasse la médiane de
    plus de 3 écarts robustes.
  - Tous les seuils sont des hypothèses « H » modifiables dans l'onglet Paramètres
    (`seuil_ecart_jumeau`, `passages_recents_derive`, `seuil_piece_bloquee`, etc.).

## Hypothèses à remplacer en priorité par des données Avelis

| Donnée à demander à Avelis | Clés concernées (`modele.py`) | Ce qui en dépend |
|---|---|---|
| **Flux actuels de Torcy** (réception, stockage, expédition) | `tonnes_par_logement`, `charge_utile_camion`, `temps_quai_reception`, `dechargement_min`, `jours_stock_matieres`, `densite_stockage`, `jours_stock_modules`, `temps_chargement_module`, `chargement_min`, `taux_retard_fournisseur`, `taux_retard_transporteur`, `taux_lots_non_conformes` | Camions et quais, surfaces de stockage, attentes et ruptures simulées. |
| **Moyens de transport et gabarits** | `dim_module`, `modules_par_convoi`, `kits_par_camion_std`, `m2_kit`, `cout_km_convoi`, `cout_km_semi`, `coef_retour_vide_convoi`, `coef_retour_semi`, `vitesse_convoi`, `vitesse_semi`, `co2_km_pl` | Stock PF, coûts et CO2 des réseaux, points de bascule. |
| **Systèmes d'information et identification existante** | `taux_lecture_rfid`, `taux_lecture_qr`, `taux_lecture_papier`, `delai_rfid_s`, `delai_qr_min`, `delai_papier_min`, `evenements_lus_cause` | Part des modules tracés de bout en bout, délai d'affichage, causes retrouvées. |
| **Localisation des chantiers et des fournisseurs** | `CHANTIERS` (coordonnées et parts de la demande), `SATELLITES`, `coef_detour_route`, `nombre_fournisseurs` | Distances, coûts du réseau, affectation aux satellites. |

Viennent ensuite les temps de cycle et la nomenclature (`cycle_ligne_2d_module`, `cycle_pod_postes`,
`travail_assemblage_3d`, `modules_par_logement`, `pods_par_logement`), à obtenir avec le Bloc Production. La
géométrie du site (`SITE_ACTUEL`, `EXTENSION`, zones) a été reconstituée d'après les plans : elle reste à
confirmer. Les gabarits de la vue 3D (`dim_camion`, `dim_pod`, `dim_kit_2d`, `dim_lot`, `dim_kit_module`) et
`hauteur_batiments` ne servent qu'au dessin.

## Modifier la vue 3D

Le code de la vue 3D est dans `avelis_3d/` (React, Three.js, React Three Fiber, Vite ; versions figées par
`package-lock.json`). Il faut Node.js LTS (v26.13.0 sur le poste de l'équipe). Dans `avelis_3d/` :

| Commande | Rôle |
|---|---|
| `npm install` | Installe les dépendances dans `node_modules/` (ignoré par git). |
| `npm test` | 105 tests : positions, horloges, cap et tableau de pilotage recalculés, comparés au jeu de référence produit par Python ; calculs du rendu et de l'interface (cadrage, tracés, bâtiments, décor, objets, formes, trajectoires, clavier, cartes d'indicateurs, recherche, détail, timeline, onglets). |
| `npm run build` | Reconstruit `dist/`, à committer : c'est ce que sert l'application. |
| `npm run dev` | Serveur de développement (rechargement à chaud) sur la scène `avelis_3d/scene.json`. |

- `py -3 avelis_flux/scene_3d.py --scene` écrit cette scène de développement. Options : `--actuelle`,
  `--schema satellites`, `--techno 0|1|2`, `--cadence`, `--jours`, `--graine`.
- `py -3 avelis_flux/scene_3d.py --reference` régénère `avelis_3d/tests/reference.json` quand la simulation
  ou le format de la scène change.
- Le format de la scène est décrit dans `ARCHITECTURE_DONNEES.md`, section 8.

## À savoir

- Logos de l'en-tête : `avelis_flux/ressources/`. Celui de l'équipe (NOVUM AEDI) et l'icône de la
  fenêtre sont produits par `py -3 avelis_flux/ressources/preparer_logos.py <logo>`. Le logo
  Avelis s'affiche à droite de l'en-tête dès que le fichier officiel est déposé sous
  `avelis_flux/ressources/logo_avelis.png` ; sans lui, l'en-tête s'en passe.
- Les tests intégrés sont calibrés sur les hypothèses actuelles (non-régression). Si une hypothèse est
  remplacée par une donnée Avelis, les tests concernés signalent les valeurs de référence à mettre à jour.
  Les ordres de grandeur attendus sont seulement affichés : les hypothèses ne sont jamais ajustées
  pour les atteindre.
- La zone « Stock produits finis » de l'implantation proposée a été rognée pour rester dans l'extension.
