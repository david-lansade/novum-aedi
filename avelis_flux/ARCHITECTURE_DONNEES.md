# Architecture des données — avelis_flux

Ce document décrit les données de traçabilité produites par la simulation (`simulation.py`) et affichées
par l'outil de pilotage (`app.py`), puis les échanges avec les deux autres blocs du défi. Les valeurs
chiffrées sont des hypothèses (voir l'onglet « Hypothèses » de l'application).

## 1. Identifiants

| Préfixe | Objet | Exemple | Créé à | Rattaché à |
|---|---|---|---|---|
| `MOD-29-xxxxx` | module 3D, c'est-à-dire un ordre de fabrication (OF) | `MOD-29-00016` | lancement de l'OF | son pod, son kit 2D, son lot, son camion d'expédition |
| `POD-29-xxxxx` | pod salle de bain | `POD-29-00016` | kitting | son module ; le lot du kit consommé (hérité) |
| `K2D-29-xxxxx` | kit de panneaux 2D | `K2D-29-00016` | kitting | son module et son lot |
| `LOT-xxxx` | lot de matières d'un camion fournisseur | `LOT-0012` | réception | son camion, son fournisseur, sa conformité |
| `CAM-xxxx` | camion fournisseur (un camion livre un lot) | `CAM-0012` | arrivée sur site | son lot |
| `FOUR-A` à `FOUR-D` | fournisseur | `FOUR-A` | — | ses lots |
| `EXP-xxxx` | camion d'expédition (convoi ou semi) | `EXP-0016` | départ planifié | les modules ou kits chargés, la destination |

Le module, son pod et son kit 2D partagent le même numéro : la généalogie
`MOD-29-00016 ← POD-29-00016 ← LOT-0012 ← CAM-0012 ← FOUR-A` se lit d'un coup d'œil. Les lots du stock
initial (reçus avant le jour 1) ont aussi un camion et un fournisseur.

## 2. Enregistrement d'événement

Chaque événement, capté ou non, est un enregistrement du journal de traçabilité :

| Champ | Type | Signification |
|---|---|---|
| `t` | minutes d'ouverture depuis J1 06:00 (1 jour = 960 min) | instant où l'événement se produit |
| `id` | texte | identifiant de l'objet (section 1) ou nom de machine |
| `type` | `module`, `pod`, `lot`, `camion`, `machine` | famille de l'objet |
| `evenement` | texte | point de contrôle (section 3) ou nature de l'alerte |
| `zone` | texte | zone du site où l'événement a lieu |
| `lot` | texte ou vide | lot de matières associé |
| `lu` | booléen | l'identifiant a-t-il été lu par la technologie ? |
| `t_affichage` | minutes, ou vide si non lu | instant d'apparition dans l'outil de pilotage |
| `alerte` | booléen | alerte (toujours lue, avec le délai de la technologie) |
| `message` | texte | détail lisible (fournisseur, cause d'un défaut, destination…) |

L'export CSV reprend ces champs, en ajoutant l'horodatage lisible (« J3 09:22 ») et l'heure d'affichage. Il
utilise le séparateur « ; », l'encodage UTF-8 avec BOM et des décimales à virgule.

## 3. Points de contrôle et règles de traçabilité

| Objet | Points de contrôle obligatoires |
|---|---|
| Module (8) | OF lancé, Kitting, Panneaux 2D terminés, Début assemblage, Fin assemblage, Contrôle final OK, Entrée stock PF, Expédié |
| Pod (7) | Kitting, Poste 1 Châssis, Poste 2 Parois + étanchéité, Poste 3 Plomberie-élec, Poste 4 Finitions, Contrôle pod OK, Intégré au module |

- **Tracé de bout en bout** : un module expédié l'est si tous ses points obligatoires sont lus et, s'il a un
  pod, tous ceux de son pod aussi.
- **Cause d'un défaut retrouvée** : il faut qu'au moins 5 événements de l'objet en défaut aient été lus
  (`evenements_lus_cause`).
- **Alertes** :
  - retard fournisseur et retard transporteur ;
  - attente de quai (au-delà de 30 min) ;
  - rupture matière ;
  - attente composant (au-delà de 60 min) ;
  - attente produit fini (camion sans module au-delà de 30 min) ;
  - blocage du stock PF ;
  - défaut pod, défaut assemblage ;
  - panne machine.

  Ruptures, attentes et blocages forment l'indicateur « ruptures ou attentes ».

## 4. Technologies d'identification

| Technologie | Taux de lecture | Délai d'affichage | Effet à 1 500 logements/an (moyenne de 20 graines) |
|---|---|---|---|
| RFID + IoT (automatique) | 0,998 | 2 à 10 s | ≈ 97,7 % de modules tracés de bout en bout, alertes à l'écran en quelques secondes |
| QR code (scan manuel) | 0,975 | 0,5 à 6 min | ≈ 70 % tracés, alertes en ≈ 3 min |
| Papier / saisie en fin de poste | 0,92 | fin de l'équipe + 5 à 30 min | ≈ 33 % tracés, alertes en ≈ 4 h 20 en moyenne |

À graine égale, les trois technologies voient exactement le même flux physique : seules la lecture et
l'affichage changent. La comparaison isole donc l'effet de la technologie.

## 5. Contenu des QR codes

Format : `AVELIS|<id>|type=<type>|<lien>=<id lié>|lot=<lot>`.

- Module : `AVELIS|MOD-29-00016|type=module|pod=POD-29-00016|lot=LOT-0012`
- Pod : `AVELIS|POD-29-00016|type=pod|module=MOD-29-00016|lot=LOT-0012`

L'étiquette imprimable porte le QR code, l'identifiant, le lot et la destination.

## 6. Flux de données vers l'outil de pilotage

```
 lecteurs RFID, scans QR, saisies papier
            │  (lu ? avec le taux de la technologie)
            ▼
 journal de traçabilité ── t_affichage = t + délai (ou fin d'équipe + délai pour le papier)
            │
            ├── tableau de pilotage (vue 2) : seuls les événements où t_affichage ≤ instant courant
            │       horloge, en-cours, stocks, 9 dernières alertes affichées avec leur délai
            ├── traçabilité d'un module (vue 3) : généalogie, chronologie, trace complète ou non
            └── indicateurs (vue 1) et exports CSV
```

Les cinq indicateurs d'évaluation du bloc sont calculés à partir de ces données :
- distance parcourue par un sous-ensemble (somme des trajets journalisés) ;
- surfaces de stockage rapportées à la cadence ;
- part des composants tracés de bout en bout ;
- délai entre une alerte et son affichage (`t_affichage − t`) ;
- nombre de ruptures ou d'attentes.

## 7. Interfaces avec les autres blocs

| Bloc | Le Bloc Flux et données **reçoit** | Le Bloc Flux et données **fournit** |
|---|---|---|
| **Conception** | Identifiants des composants (préfixes de la section 1), nomenclatures (modules, pods et panneaux par logement, gabarit d'un module), ordres de fabrication (`MOD-…`) | Contraintes de transport et de stockage (gabarit des convois, kits par semi, m² de stock par module ou par kit), retours de défauts (Pareto des causes, export CSV) |
| **Production** | Temps de cycle (ligne 2D, postes pods, assemblage), états des machines (pannes), sous-ensembles finis identifiés (pods et kits 2D) | Approvisionnements et kits au bon moment (stock initial, kitting, lancement décalé du kit 2D pour arriver en même temps que le pod), ordres de fabrication |

Échanges proposés :
- avec le Bloc Conception : fichiers CSV ou JSON reprenant les champs de la section 2, les identifiants
  étant attribués par lui ;
- avec le Bloc Production : états des machines publiés au fil de l'eau, sous forme d'événements `machine`
  du journal.

## 8. Scène de la vue 3D (`scene.json`)

`scene_3d.py` traduit un scénario simulé en un fichier JSON, que lit la vue 3D (`avelis_3d/`) :

```
 Usine simulée ── scene_3d(usine) ── ServeurScene (127.0.0.1, port libre)
                                        ├── /index.html?t=<minutes>   page construite (avelis_3d/dist/)
                                        └── /scene.json               scène du scénario courant
```

Unités : mètres et minutes d'ouverture (t = 0 : jour 1 à l'heure d'ouverture). Plan : x vers l'est, y vers
le nord. Points arrondis au centimètre ; JSON compact, en UTF-8, sans `inf` ni `NaN`.

| Champ | Contenu |
|---|---|
| `version` | Version du format (4). La vue 3D refuse une autre version, avec un message. |
| `scenario` | `cadence`, `implantation`, `schema`, `techno`, `jours`, `graine` : les paramètres de l'application. |
| `temps` | `duree` (minutes simulées), `minutes_jour` (minutes d'ouverture par jour), `heure_ouverture`, `changements_equipe` (heures de l'horloge des changements d'équipe, 6, 14 et 22 : les opérateurs à pied y marchent entre les portes et le parking VL). |
| `site.contours` | Site actuel et extension : `nom`, `points` [[x, y], …], `utilise`. |
| `site.route_publique`, `site.voirie`, `site.largeur_voirie` | Polylignes [[x, y], …] et largeur de la voirie poids lourds. |
| `site.bretelles` | Polylignes de voirie raccordées à la voirie par leur premier point : la bretelle des quais de réception (façade est de la Réception). |
| `site.portail`, `site.acces`, `site.retournement` | Portail [x, y] de l'implantation ; accès, polyligne de la route publique au portail (voie publique ; un seul point, le portail, sauf dans l'implantation actuelle : Rue Alain Bombard, portail à l'entrée du site) ; aire de retournement {`centre`, `rayon`}. |
| `site.parking_vl` | Parking des véhicules légers {`x`, `y`, `largeur`, `profondeur`, `voie`} (voie d'accès : polyligne), ou `null`. Décor : aucun objet n'y passe. |
| `site.quais` | `reception` et `expedition` : {`position` du premier quai, `nombre`, `pas` [dx, dy] d'un quai au suivant} ; `partages` (implantation actuelle). |
| `site.zones` | `nom`, `libelle` (une zone partagée apparaît avec sa zone hôte : « Réception / Expédition »), `x`, `y` (coin sud-ouest), `largeur`, `profondeur`, `couleur`, `categorie`, `hauteur` (0 à ciel ouvert : parking, aire d'expédition, toute zone de la catégorie « Réserve foncière » ; sinon `hauteur_batiments`). |
| `gabarits` | Par type d'objet : [largeur, longueur, hauteur] en m, lus dans `HYPOTHESES` (`dim_module` ou, en schéma satellites, `dim_kit_module`). |
| `objets` | `id` (identifiants de la section 1), `type` (`camion`, `lot`, `kit 2D`, `pod`, `module`), `libelle` (texte du survol), `liens`, `evenements`, `segments`. |
| `objets[].liens` | Objets liés, quand ils sont connus : `module`, `pod`, `kit 2D`, `lot`, `camion` (identifiants), `modules` (liste, camion d'expédition). |
| `objets[].evenements` | Enregistrements de la section 2 hors alertes, dans l'ordre du journal : `[t, evenement, zone, t_affichage, message]` ; `t_affichage` vaut `null` pour un événement non lu. |
| `tracabilite` | `points_module`, `points_pod` : points de contrôle obligatoires (section 3) ; `alertes` : `[t, t_affichage, nature, id, type, zone, message]`, triées par `t_affichage`. |
| `pilotage` | Instants triés : `of`, `entrees_pf`, `expeditions`, `debuts_pods`, `fins_pods` ; `camions` : `[t_arrivee, t_sortie]` (`null` : encore sur site) ; `objectif_jour` ; `echantillons` : `pas` (min) et valeurs de `stock_matieres` et `stock_pf` aux instants k × `pas`. |
| `resultats` | Indicateurs de fin de simulation (`Usine.resultats`), le Pareto des causes en listes `[cause, nombre]`. |

Chaque segment est `[t0, t1, points]` :
- `t1` vaut `null` pour une présence qui dure jusqu'à la fin de la simulation ;
- un seul point : l'objet est immobile ; plusieurs : il parcourt la polyligne à vitesse constante entre
  `t0` et `t1`.

Position d'un objet à l'instant t (`positions_scene` en Python, `etatObjet` en JavaScript, comparés par
`npm test`) :
1. le segment actif est le dernier commencé (`t0 ≤ t`) ;
2. l'objet est visible tant que `t < t1` : la fin est exclue, et l'objet est masqué entre deux segments
   disjoints ;
3. sur un trajet, son cap suit la portion parcourue ; à l'arrêt, il garde le cap de son dernier trajet.

Ces positions redonnent celles de la simulation (`Usine.positions`) à 2 cm près (arrondi des points).

Tableau de pilotage à l'instant t (`pilotage_scene` en Python, `valeursPilotage` de `src/pilotage.js`,
comparés par `npm test` ; `pilotage_scene` est lui-même comparé au calcul de la vue 2 sur l'usine) :
1. un instant compte dès qu'il est ≤ t ; « aujourd'hui » part du début du jour en cours ;
2. terminés et expédiés du jour, objectif au prorata de l'heure, expédiés au total, en-cours (OF lancés
   moins entrées en stock PF), pods en cours, camions sur site (`t_arrivee ≤ t < t_sortie`), stocks du
   dernier échantillon ;
3. alertes et événements ne s'affichent qu'à `t_affichage` (délai de lecture de la technologie), un
   événement non lu jamais ; la vue garde les 9 dernières alertes affichées.

Un module n'est dessiné qu'à partir de son assemblage (avant, ce sont son kit 2D et son pod) : un module
pas encore assemblé à la fin de la simulation n'a pas d'objet, ses événements ne sont donc pas dans la
scène, mais il compte dans `pilotage.of`.

### Scène du jumeau numérique (vue 3D en direct)

`scene_jumeau(jumeau, cadence, maintenant, revision)` écrit, au même format, l'atelier reconstitué par
les scans d'avelis_scan (vue 5). Le bouton « Vue 3D en direct » de la vue 5 l'ouvre ; le jumeau a son
propre `ServeurScene` et republie la scène à chaque lecture qui apporte de nouveaux scans.

| Écart au format de la simulation | Contenu |
|---|---|
| `direct` | `revision` (augmente à chaque publication) et `intervalle_s` : la page relit `scene.json` toutes les `intervalle_s` s et ne garde la nouvelle scène que si la révision a changé ; `lieu` : [latitude, longitude] de Torcy, d'où la page lit la météo actuelle (api.open-meteo.com) pour le ciel. |
| `temps` | t = 0 au minuit du jour du premier scan ; `minutes_jour` = 1 440, `heure_ouverture` = 0 : l'horloge affiche l'heure réelle (« Jour 1 · 16:05 »). `duree` = maintenant. |
| `objets` | Pièces scannées de type module, pod, kit 2D et lot (ossatures et composants n'ont pas de forme 3D). Un segment fixe par scan, à la position de `Jumeau.repos` dans la zone du scan, jusqu'au scan suivant ; `evenements` : scans acceptés, affichés dès leur enregistrement. `liens` : module parent et lot. |
| `tracabilite.alertes` | Alertes du serveur de scan (défauts, blocages, refus). |
| `pilotage` | Tiré des scans ; `camions` vide ; l'objectif du jour est réparti sur 24 h (et non sur les heures d'ouverture). |
| `resultats` | Vide. |

En direct, le lecteur suit l'heure réelle (une minute de scène par minute) ; aller à un instant le
quitte, le bouton « ● Direct » y revient. Une scène relue au même site garde caméra, décor, lecteur et
sélection ; les objets sont remontés à chaque révision.
