# Fonctionnalités des deux logiciels du Bloc 3

Imagine & Make 2026, défi Avelis, Bloc 3. Le projet compte deux logiciels qui fonctionnent ensemble :

| Logiciel | Rôle | Lancement |
|---|---|---|
| **avelis_flux** | Application de bureau (PC). Dimensionne le site de Torcy, simule la production, montre la traçabilité, et porte le **jumeau numérique** alimenté par les scans. | `py -3 avelis_flux/app.py` |
| **avelis_scan** | Application de scan : un serveur sur le PC, une page web sur le téléphone. Enregistre chaque geste de l'atelier dans une base SQLite (traçabilité, défauts, kanban, consignes). | `avelis_scan\demarrer.bat` |

Toutes les valeurs chiffrées sont des hypothèses, marquées « H » dans `avelis_flux/modele.py`, sauf les données Avelis, marquées « A ».

---

## 1. Comment les deux logiciels travaillent ensemble

```
 Téléphone (page de scan)                  PC
 ─────────────────────────      ┌───────────────────────────────┐
 choisit son poste       ──────►│ avelis_scan : serveur + base  │
 scanne une étiquette QR  scan  │ SQLite (atelier.db)           │
 valide une étape               │ règles : séquence, défauts,   │
 reçoit les consignes  ◄────────│ lots bloqués, kanban          │
                       consigne └──────┬───────────────▲────────┘
                                       │ lecture        │ consigne validée
                                       │ chaque seconde │ par un humain
                                ┌──────▼───────────────┴────────┐
                                │ avelis_flux : vue 5           │
                                │ jumeau numérique              │
                                │ plan, pilotage, comparaison   │
                                │ avec la simulation, IA        │
                                └───────────────────────────────┘
```

- **Même vocabulaire.** Les zones des postes du scan (`avelis_scan/config.py`) portent les noms des zones du plan d'`avelis_flux`. Les étapes portent les noms des points de traçabilité de la simulation (OF lancé, Kitting, Poste 1 Châssis…). Chaque scan se place donc directement dans la bonne zone du plan.
- **Sens aller (terrain → jumeau).**
  - Le jumeau lit l'API du serveur (`GET /api/evenements`, `GET /api/pieces`) chaque seconde, sans bloquer l'interface.
  - Si le serveur n'est pas lancé, il lit directement le fichier `avelis_scan/donnees/atelier.db`, en lecture seule. Il fonctionne donc dans les deux cas, serveur lancé ou non.
- **Sens retour (jumeau → terrain).**
  - Une décision proposée par le jumeau et **validée par un humain** est envoyée par `POST /api/consignes`.
  - Elle arrive sur le téléphone du poste concerné, qui vibre.
- **Remise à zéro.** Le bouton « Réinitialiser les scans » du jumeau et le bouton « Vider la base » de la page `/pc` font la même chose, par le serveur ou, à défaut, directement dans le fichier.
- **Quel que soit le plan affiché.** Le jumeau affiche les scans sur l'implantation proposée, optimisée ou actuelle, au choix. Seul le dessin change : les données restent celles des scans.

---

## 2. avelis_flux — l'application de bureau

### 2.1 Barre latérale (toujours visible)

**Réglages du scénario**

| Commande | Fonction |
|---|---|
| **Cadence** | Curseur de 400 à 2 500 logements par an, par pas de 50. |
| **Implantation** | Trois choix. *Proposée* : Torcy + extension, flux en U. *Optimisée* : zones à la taille du besoin, lignes accolées à l'assemblage, 580 m par sous-ensemble au lieu de 681, aucun croisement. *Actuelle* : site seul, sans extension, quais partagés. |
| **Schéma industriel** | *Usine unique* (un module par convoi), ou *usine mère + satellites* : Torcy fabrique les murs 2D et les pods, les consolide en kits modules (3 par semi), et les satellites assemblent les volumes. |
| **Technologie de traçabilité** | RFID + IoT, QR code ou papier. Chacune a son taux de lecture et son délai d'affichage. |
| **Jours simulés, graine** | De 1 à 60 jours. Même graine, mêmes résultats. |
| **Recalculer le scénario** | Relance les calculs et la simulation. Une saisie invalide est refusée avec un message. |

**Navigation** : boutons 1, 2, 3 et 5, plus le bouton 4 (vue 3D, qui s'ouvre dans le navigateur). Le bouton de la vue affichée est orange.

**Exports**

| Commande | Fonction |
|---|---|
| **Exporter le journal** | CSV (`;`, décimales à virgule, UTF-8-sig, lisible dans Excel). |
| **Exporter toutes les figures** | 11 PNG à 300 dpi dans `exports/`. |
| **Générer des étiquettes QR** | Une étiquette par module expédié et par pod. Le bouton est désactivé si `qrcode` est absent. |

### 2.2 Vue 1 — Statistiques

**Six tuiles** :
- cadence atteinte ;
- distance d'un sous-ensemble ;
- m² de stockage pour 1 000 logements par an ;
- part des modules tracés de bout en bout ;
- délai entre une alerte et son affichage ;
- ruptures, attentes et blocages.

| Onglet | Fonctions |
|---|---|
| **Tableau des chiffres** | 7 catégories : cadence, logistique, surfaces, comparaison des implantations, simulation, traçabilité, ressources. Une colonne H/A indique l'origine de chaque valeur. |
| **Graphiques** | Modules par jour face à l'objectif ; utilisation des ressources (en rouge au-delà de 85 %) ; en-cours et stocks ; Pareto des défauts ; coût annuel des réseaux, avec le CO2 ; évolutivité (surface nécessaire face aux surfaces disponibles). |
| **Réseau** | Cartes de l'usine unique et du réseau avec satellites (épaisseur des liaisons selon la demande) ; coût par logement selon la cadence, avec les points de bascule ; recommandation et tableau comparatif. |
| **Paramètres › Hypothèses** | Toutes les valeurs du modèle sont modifiables. Double-clic pour modifier ; recherche ; « ↺ Valeur par défaut » ; lignes modifiées sur fond orangé ; chaque saisie est contrôlée (entier, valeur positive, taux entre 0 et 1, minimum < maximum). |
| **Paramètres › Réseau** | Ajouter une ville comme chantier ou comme usine satellite ; modifier nom, position ou part ; « ✕ Retirer » ; « Répartir les parts à 100 % ». |
| *Commun aux Paramètres* | « Appliquer et recalculer », « Appliquer et voir la carte du réseau », « Tout rétablir par défaut ». En cas d'échec du calcul, les paramètres précédents sont rétablis. Les modifications ne sont pas conservées d'un lancement à l'autre. |

### 2.3 Vue 2 — Schéma de l'usine et flux

**Plan**
- Site et extension, route publique, voirie poids lourds, aire de retournement, portail, quais.
- Zones colorées par catégorie.
- Flèches de flux en L par gamme, avec la distance en mètres.
- Échelle de 50 m, nord, légende.

**Objets animés**
- Pods, kits 2D et lots : ronds.
- Modules et camions : carrés.

**Commandes**
- Lecture/Pause, Début, vitesse de 5 à 240 minutes simulées par seconde, curseur de temps.
- Case « Flèches de flux ».
- Barre d'outils : zoom, déplacement, enregistrement.

**Tableau de pilotage**
- Horloge « Jour N · HH:MM ».
- Indicateurs instantanés, dont les camions sur site.
- Les 9 dernières alertes affichées, avec leur délai d'affichage.

**Mode suivi** (lancé depuis la vue 3) : un module ou son pod est mis en surbrillance avec son trajet. Le bouton « Arrêter le suivi » le désactive.

### 2.4 Vue 3 — Traçabilité d'un module

- **Choix du module**, et liste des **modules en défaut** : un clic ouvre la fiche.
- **Fiche du module** :
  - généalogie : module ← pod ← lot ← camion ← fournisseur ;
  - destination, délai entre l'OF et le stock de produits finis, distance parcourue ;
  - trace COMPLÈTE ou INCOMPLÈTE, avec les points manquants ;
  - défaut éventuel et cause retrouvée ;
  - QR code du module.
- **Chronologie** de tous les événements du module, de son pod, de son lot et des camions liés. Les alertes sont en rose et les événements non lus en gris.
- **Suivre ce module dans le schéma** : bascule vers la vue 2 en mode suivi.

### 2.5 Vue 4 — Vue 3D (navigateur)

- **Scène** : site en 3D, bâtiments aux murs translucides, noms des zones, nord, échelle.
- **Objets** : aux gabarits des hypothèses, ils se déplacent exactement comme dans la simulation.
- **Navigation** : rotation, déplacement, zoom ; « Vue d'ensemble », « Vue de dessus », case « Noms des zones ».
- **Commandes** : Lecture/Pause, Début, vitesse, curseur, horloge, nombre d'objets visibles par type.
- **Survol d'un objet** : identifiant, type et description.
- **Accès** : servie en local, sans Internet, accessible depuis ce poste uniquement.

### 2.6 Vue 5 — Jumeau numérique (scans)

Configuration retenue : **usine unique, implantation avec extension**.

**Barre commune**
- Adresse du serveur de scan et bouton **Se connecter**. Sans serveur, le jumeau lit le fichier.
- Bandeau d'état : source lue, nombre d'événements, ou l'erreur en rouge.
- **Réinitialiser les scans** : vide la base, après confirmation.
- Liste **Plan** : proposé, optimisé ou actuel.

| Onglet | Fonctions |
|---|---|
| **Atelier en direct (scans)** | Même plan que la vue 2, mais les pièces sont placées d'après les scans (modules, pods, kits 2D, lots, ossatures, composants). Un anneau rouge signale une pièce en défaut ou à isoler. Une pièce intégrée, expédiée ou rebutée quitte le plan. Tableau de pilotage à l'heure réelle : terminés face à l'objectif à cette heure, expédiés, en-cours, défauts et lots bloqués, stocks, 9 dernières alertes avec le délai entre le téléphone et l'enregistrement. **● En direct**, ou relecture des scans passés (1 à 240 min par seconde) et **○ Revenir au direct**. **Suivre** : un module ou un pod avec son trajet. |
| **Comparaison avec la simulation** | La même usine simulée (plan affiché, QR code, cadence et graine du scénario). Tuiles : scans, modules lancés, période observée, étapes en écart. 6 indicateurs comparés (délai OF → stock PF, modules par jour, défauts par module, délai d'affichage, part tracée, scans refusés). Durée de chaque étape des gammes module et pod (scans face à la simulation), qualifiée « plus lent » ou « plus rapide » au-delà de 50 %, avec un graphique en échelle logarithmique. `echelle_temps_maquette` convertit les minutes de la maquette en minutes d'usine. |
| **Décisions et prévisions (IA)** | Voir le détail ci-dessous. |

**Détail de l'onglet « Décisions et prévisions (IA) »**

Le jumeau propose et un humain décide.

- **Analyse** après chaque lecture des scans, au plus toutes les 5 s sans nouveau scan.
- **Quatre règles** :

  | Règle | Déclenchement | Destinataires |
  |---|---|---|
  | Étape anormalement lente | — | poste et bureau |
  | Pièces bloquées | pas de nouveau scan depuis 2 fois la durée estimée, regroupées par poste | poste et bureau |
  | Défauts répétés | 2 défauts de même catégorie au même poste en 60 min | poste et bureau |
  | Retard sur l'objectif du jour | moins de 80 % de l'objectif à cette heure | bureau |

- **Boîte de dialogue** à chaque proposition : règle, motif chiffré, destinataires, consigne modifiable. Trois choix :
  - **Envoyer la consigne** : elle part vers le téléphone ;
  - **Ignorer** ;
  - **Décider plus tard** : la décision reste en attente dans le tableau.
- **Historique** des décisions avec leur statut. Une décision envoyée ou ignorée n'est pas reproposée avant 60 min.
- **Option A — fin de fabrication prévue** de chaque module en cours :
  - durées apprises des scans, rapprochées de la simulation tant qu'il y a peu de mesures ;
  - fourchette p10–p90 ;
  - en rose, les modules en retard sur leur étape ;
  - précision mesurée sur la simulation et affichée : 53 min d'erreur moyenne, contre 1 h 20 pour la prévision naïve.
- **Option B — étapes anormalement lentes** :
  - on compare les 3 derniers passages à la médiane des passages précédents, ou à la simulation tant qu'il n'y a pas d'historique ;
  - chaque étape est classée « anormal », « à surveiller », « normal » ou « sans mesure ».
- **Seuils** : tous sont des hypothèses « H », modifiables dans Vue 1 › Paramètres.

---

## 3. avelis_scan — l'application de scan

### 3.1 Le téléphone (page de scan, `http://<adresse du PC>:8000/`)

| Fonction | Détail |
|---|---|
| **Réglages** | Choix du poste (14 postes, du bureau à l'expédition) et du code opérateur. Ils sont mémorisés ; le bouton **Poste** permet d'en changer. |
| **Scan** | Avec l'appareil photo ou Google Lens (le QR code ouvre directement la pièce), avec le bouton **Scanner une étiquette**, ou en saisissant le code. |
| **Puce NFC : lecture** | Bouton **Lire une puce NFC** (Chrome sur Android) : chaque puce approchée ouvre la fiche de sa pièce, comme un QR. Hors de l'application, toucher la puce ouvre directement la page. |
| **Puce NFC : écriture** | Sur la fiche d'une pièce ou d'une carte kanban : **Écrire ce code sur une puce NFC**. La puce reçoit l'adresse de scan et le code ; l'écriture est notée dans l'historique. |
| **Fiche de la pièce** | Gamme avec les étapes faites, prochaine étape attendue et son poste, lot, module parent, défauts. |
| **Valider : étape** | Enregistre l'étape suivante si l'on est au bon poste. |
| **Forcer hors séquence** | Possible, mais avec un motif obligatoire ; la saisie est tracée. |
| **Déclarer un défaut** | Catégorie, cause présumée, gravité, description. |
| **Retouche terminée / Mettre au rebut** | Pour une pièce en défaut. |
| **Intégré au module** | Le champ module est prérempli. |
| **Expédié** | Choix du chantier de destination. |
| **Kanban** | Bac vide, bac préparé, bac livré, selon le poste. |
| **Créer cette pièce** | Proposé quand le code est inconnu. |
| **Consignes** | Affichées en haut de l'écran, avec vibration ; le bouton **Vu** les acquitte. |

### 3.2 Les pièces suivies et leurs gammes

| Pièce | Code | Gamme (étape → poste) |
|---|---|---|
| Module 3D | `MOD-29-00001` | OF lancé (bureau) → Kitting → Début assemblage → Fin assemblage → Contrôle final OK → Entrée stock PF → Expédié |
| Pod | `POD-29-00001` | Kitting → Poste 1 Châssis → Poste 2 Parois + étanchéité → Poste 3 Plomberie-élec → Poste 4 Finitions → Contrôle pod OK → Intégré au module |
| Kit 2D | `K2D-29-00001` | Kitting → Panneaux 2D terminés (ligne 2D) → Intégré au module |
| Ossature acier 1D | `OSS-29-00001` | Réception → Stockage → Kitting → Intégré au module |
| Composant à n° de série | `CMP-29-00001-PAC` | Réception → Stockage → Kitting → Intégré au module |
| Lot fournisseur | `LOT-0001` | Réception lot → Stockage lot |

**Attributs enregistrés pour chaque pièce** :
- type, désignation, référence, n° de série ;
- origine et destination ;
- lot et module parent ;
- étape, poste et statut ;
- temps passé à chaque poste ;
- défauts ;
- historique complet.

### 3.3 Règles automatiques

1. **Étape hors séquence** : refusée. Elle peut être forcée, avec un motif, et reste tracée.
2. **Double scan** au même poste en moins de 60 s : ignoré.
   Chaque scan garde son **moyen d'identification** (QR code, puce NFC, saisie), visible dans le journal du PC.
3. **Code inconnu** : refusé, avec la proposition de créer la pièce.
4. **Défaut ouvert** : la pièce est bloquée jusqu'à la retouche ou au rebut, et le poste reçoit une consigne.
5. **Défaut de cause « Matière / lot fournisseur »**, ou 2 défauts sur un même lot : **le lot est bloqué**. Chaque pièce de ce lot reçoit la consigne « isoler » et est refusée partout, jusqu'au déblocage depuis le PC.
6. **Assemblage** : une alerte est levée si un composant n'est pas prêt au début, ou pas intégré à la fin.
7. **Intégration** : elle exige un module existant. **Expédition** : elle exige un chantier.
8. **Kanban** : une demande non livrée dans le délai cible (30 min, ou 3 min pour le jeu d'essai) déclenche « RISQUE DE RUPTURE » au poste et au magasin. Un bac signalé vide deux fois est refusé.

### 3.4 La page PC (`http://localhost:8000/pc`)

| Onglet | Fonctions |
|---|---|
| **Tableau de bord** | Compteurs, en-cours par poste, derniers scans (mis à jour toutes les 3 s). |
| **Pièces** | Liste filtrable par type, statut ou recherche. Un clic ouvre la fiche : gamme, temps à chaque poste, défauts, composants, historique, blocage ou déblocage du lot. |
| **Créer** | Module complet : module, pod, kit 2D, ossature et, en option, 4 composants à n° de série, au même numéro, avec le chantier et les lots ; jusqu'à 50 à la fois. Lot de matières. Pièce isolée. Carte kanban, et calcul du nombre de cartes. Jeu d'essai (2 lots, 1 module, 3 cartes). Vider la base. |
| **Kanban** | Tableau en 3 colonnes (pleine, vide, en route) et performance du réapprovisionnement. |
| **Consignes** | Envoyer une consigne à un poste ; acquitter. |
| **Journal et exports** | 300 derniers événements ; export CSV de chaque table (`;`, UTF-8). |
| **Étiquettes** | Cocher des pièces et des cartes, puis imprimer avec Ctrl+P. Chaque QR code contient l'adresse de scan de la pièce. |

### 3.5 L'API (utilisée par le téléphone, la page PC et le jumeau)

| Méthode | Adresse | Rôle |
|---|---|---|
| GET | `/api/evenements?depuis=&limite=` | Nouveaux événements (poste, zone, code, heure du serveur et du téléphone). C'est ce que lit le jumeau. |
| GET | `/api/pieces`, `/api/etat`, `/api/defauts`, `/api/cartes`, `/api/objet/<code>` | Liste des pièces, photographie de l'atelier, défauts, cartes kanban, fiche d'un code. |
| GET | `/api/consignes?poste=` | Consignes d'un poste. |
| POST | `/api/scan` | Un scan : code, poste, opérateur, action. |
| POST | `/api/pieces`, `/api/modules`, `/api/lots`, `/api/cartes` | Créations. |
| POST | `/api/consignes` | Envoi d'une consigne. C'est le sens retour du jumeau. |
| POST | `/api/nfc/ecriture` | Trace l'écriture d'une puce NFC pour une pièce ou une carte. |
| POST | `/api/lots/<lot>/bloquer`, `/api/lots/<lot>/debloquer` | Blocage ou déblocage d'un lot. |
| POST | `/api/demo`, `/api/vider` | Jeu d'essai ; vider la base (confirmation « VIDER »). |
| GET | `/export/<table>.csv`, `/etiquettes`, `/qr/<code>.svg` | Exports CSV, planche d'étiquettes, QR code d'une pièce. |

---

## 4. Vérifications intégrées

| Commande | Contenu |
|---|---|
| `py -3 avelis_flux/modele.py` | 28 tests du modèle, puis chiffres clés comparés aux ordres de grandeur attendus. |
| `py -3 avelis_flux/simulation.py` | 22 tests de la simulation. |
| `py -3 avelis_flux/scene_3d.py` | 18 tests de la scène 3D et du serveur local. |
| `py -3 avelis_flux/jumeau.py` | 9 tests du jumeau, sur un vrai atelier de scan en mémoire. |
| `py -3 avelis_flux/analyse_jumeau.py` | 6 tests des options A et B. |
| `py -3 avelis_flux/decisions.py` | 7 tests des décisions (rien n'est envoyé sans validation). |
| `py -3 avelis_flux/tests_interface.py` | 54 combinaisons, mise en page contrôlée à 3 tailles d'écran, captures, exports, jumeau (≈ 15 min). |
| `py -3 avelis_scan\tests_scan.py` | 19 tests des règles de scan, du NFC et du serveur. |
