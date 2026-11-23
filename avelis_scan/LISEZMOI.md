# avelis_scan : scan de l'atelier (traçabilité + kanban)

Application de scan pour la maquette du Bloc 3 :

- le **téléphone** scanne les étiquettes QR ;
- le **PC** fait tourner le serveur et la base de données SQLite.

Chaque pièce est suivie dans tout l'atelier : d'où elle vient, où elle va, le temps passé à chaque poste et ses défauts. Les cartes kanban déclenchent le réapprovisionnement. Le futur jumeau numérique lira la même base.

Il n'y a rien à installer à part Python. Le module `qrcode` est facultatif et sert aux étiquettes.

## 1. Installation (une seule fois, sur le PC Windows)

```powershell
py -3 -m pip install qrcode
```

Ensuite, faire un clic droit sur `autoriser_pare_feu.bat`, puis **Exécuter en tant qu'administrateur**. Ce fichier ouvre le port 8000.

C'est indispensable : Windows classe souvent le partage de connexion d'un téléphone comme un réseau « public » et bloque alors le téléphone.

## 2. Lancement (à chaque séance)

1. Sur le téléphone Android, activer le **partage de connexion** et y connecter le PC.
2. Sur le PC, double-cliquer sur **`demarrer.bat`** (ou lancer `py -3 avelis_scan\serveur.py`).
3. La console affiche deux adresses et un QR code :
   - sur le **PC** : `http://localhost:8000/pc` (gestion de la base) ;
   - sur le **téléphone** : scanner le QR code de la console, ou taper l'adresse affichée (par exemple `http://192.168.43.20:8000/`).
4. Sur le téléphone, choisir son **poste** et son **code opérateur**. Ils sont mémorisés.

Si l'adresse détectée n'est pas la bonne (PC avec plusieurs cartes réseau), utiliser :
`py -3 avelis_scan\serveur.py --adresse 192.168.x.y`.

La base est enregistrée dans `avelis_scan\donnees\atelier.db`. Elle commence **vide**.

## 3. Scanner avec le téléphone

**Méthode simple (recommandée).** Le QR code de chaque étiquette contient l'adresse de la page de scan. Il suffit de le scanner avec l'**appareil photo** du téléphone ou avec Google Lens : la page s'ouvre directement sur la pièce.

**Scan dans la page (bouton orange).** Chrome bloque la caméra sur une adresse `http://` locale. Pour l'autoriser, à faire une seule fois :

1. Ouvrir `chrome://flags` dans Chrome.
2. Chercher « Insecure origins treated as secure ».
3. Ajouter l'adresse du PC (par exemple `http://192.168.43.20:8000`).
4. Choisir **Enabled**, puis **Relancer**.

**Sans caméra.** On peut aussi taper le code dans le champ « ou saisir le code ».

**Attention.** Les QR codes contiennent l'adresse du PC. Si elle change (nouveau partage de connexion), réimprimez les étiquettes depuis l'onglet « Étiquettes » du PC.

### Puces NFC (en plus des QR codes)

Une puce NFC (carte, autocollant, porte-clés NTAG) remplace ou double une étiquette QR. Elle s'utilise exactement de la même façon. Il faut **Chrome sur Android** avec le NFC activé dans les réglages du téléphone. Sur l'adresse `http://` du PC, il faut aussi le même réglage `chrome://flags` que pour la caméra (voir plus haut).

- **Écrire une puce** : ouvrir la fiche de la pièce ou de la carte kanban, puis **Écrire ce code sur une puce NFC**, et tenir la puce contre le dos du téléphone jusqu'à la vibration. La puce reçoit deux informations :
  - la même adresse que le QR code, suivie de `?m=nfc` ;
  - le code en clair.

  Une puce déjà écrite est remplacée. L'écriture est notée dans l'historique de la pièce (« Puce NFC écrite »).
- **Lire une puce** : deux façons.
  - Appuyer sur **Lire une puce NFC**, qui devient vert, puis approcher les puces une à une : chaque puce ouvre sa fiche, comme un scan de QR.
  - Sans l'application, toucher la puce avec le téléphone déverrouillé : Android ouvre directement la page de la pièce.
- **Traçabilité** : chaque scan enregistre son moyen d'identification, QR code, puce NFC ou saisie du code. Il apparaît dans la colonne « Moyen » du journal du PC et dans l'export CSV.
- **Adresse du PC** : si elle change, réécrivez les puces comme on réimprime les étiquettes.
- **Lecteur NFC USB** : un lecteur branché au PC qui tape le code comme un clavier fonctionne déjà avec les champs de saisie.

## 4. Ce que fait l'application

### Les pièces (traçabilité)

| Type | Code | Gamme (étape → poste) |
|---|---|---|
| Module 3D (1 logement) | `MOD-29-00001` | OF lancé (bureau) → Kitting → Début assemblage → Fin assemblage → Contrôle final OK → Entrée stock PF → Expédié |
| Pod salle de bain | `POD-29-00001` | Kitting → Poste 1 Châssis → Poste 2 Parois + étanchéité → Poste 3 Plomberie-élec → Poste 4 Finitions → Contrôle pod OK → Intégré au module |
| Kit panneaux 2D | `K2D-29-00001` | Kitting → Panneaux 2D terminés (ligne 2D) → Intégré au module |
| Ossature acier 1D | `OSS-29-00001` | Réception → Stockage → Kitting → Intégré au module |
| Composant à n° de série | `CMP-29-00001-PAC` | Réception → Stockage → Kitting → Intégré au module |
| Lot fournisseur | `LOT-0001` | Réception lot → Stockage lot |

Les noms des zones et des étapes sont ceux de `avelis_flux`. Les gammes, les postes et les causes de défaut se modifient dans **`config.py`**.

**Attributs de chaque pièce :**

- type, désignation, référence, n° de série ;
- **origine** (fournisseur ou fabriquée sur site) et **destination** (module parent ou chantier) ;
- lot et module parent ;
- étape et poste actuels, statut ;
- **temps passé à chaque poste** (table `sejours`) ;
- **défauts** (catégorie, cause présumée, gravité, description, statut) ;
- historique complet.

**Règles automatiques :**

1. **Étape hors séquence** : refusée. On peut la forcer, mais avec un motif obligatoire, et elle est tracée.
2. **Double scan** au même poste en moins de 60 s : ignoré.
3. **Code inconnu** : refusé, avec un bouton « Créer cette pièce ».
4. **Défaut ouvert** : la pièce est bloquée jusqu'à la « Retouche terminée » ou au rebut. Le poste reçoit une consigne.
5. **Défaut de cause « Matière / lot fournisseur »**, ou **2 défauts sur un même lot** : le **lot est bloqué**. Chaque poste où se trouve une pièce de ce lot reçoit la consigne « isoler … ». Ces pièces sont ensuite refusées partout. Le lot se débloque depuis le PC.
6. **Assemblage** : au début, alerte si un composant du module n'est pas prêt ; à la fin, alerte si un composant n'est pas intégré.
7. **Intégration** : elle exige un module existant. **Expédition** : elle exige un chantier.

### Le kanban

| État de la carte | Qui scanne | Action | Effet |
|---|---|---|---|
| Pleine | Poste consommateur | **Bac vide** | Demande créée, consigne « Préparer … » au magasin |
| Vide | Magasin | **Bac préparé** | Consigne « Bac en route » au poste consommateur |
| En route | Poste consommateur | **Bac livré** | Carte de nouveau pleine, durée du cycle enregistrée (en retard ou non) |

Une demande non livrée dans le délai cible (30 min par défaut, 3 min pour le jeu d'essai) déclenche la consigne **« RISQUE DE RUPTURE »** au poste et au magasin. Un bac signalé vide deux fois est refusé. L'onglet « Créer » du PC calcule le nombre de cartes nécessaires.

### Les consignes (retour vers le terrain)

Le téléphone affiche en haut les consignes de son poste et vibre quand il en arrive une nouvelle. L'opérateur appuie sur « Vu » pour l'acquitter.

Les consignes viennent des règles automatiques (lot bloqué, bac à préparer, retard, défaut, composant en attente). Le PC peut aussi en envoyer à la main.

## 5. La page PC (`/pc`)

| Onglet | Contenu |
|---|---|
| **Tableau de bord** | Compteurs, en-cours par poste, derniers scans (mise à jour toutes les 3 s) |
| **Pièces** | Liste filtrable. Un clic ouvre la fiche : gamme, temps à chaque poste, défauts, composants, historique, blocage ou déblocage du lot |
| **Créer** | Module complet, lot, pièce isolée, carte kanban, calcul du nombre de cartes, jeu d'essai, vider la base |
| **Kanban** | Tableau en 3 colonnes et performance du réapprovisionnement |
| **Consignes** | Envoyer une consigne, acquitter |
| **Journal et exports** | 300 derniers événements, export CSV de chaque table (Excel : « ; », UTF-8) |
| **Étiquettes** | Cocher les pièces et cartes, puis imprimer (Ctrl+P) |

## 6. Jumeau numérique

Le jumeau numérique est la vue « 5 Jumeau numérique (scans) » de l'application `avelis_flux`
(`py -3 avelis_flux/app.py`). Il lit ce serveur à `http://localhost:8000` chaque seconde, ou, si le
serveur n'est pas lancé, la base `donnees/atelier.db` en lecture seule.

La base `donnees/atelier.db` est en SQLite, et l'API est en JSON :

- `GET /api/evenements?depuis=<id>` renvoie les nouveaux événements, avec `poste`, `zone` (nom de la zone du plan dans `avelis_flux`), `code`, `t` (heure du serveur) et `t_client` (heure du téléphone). Le délai d'affichage vaut `t - t_client`.
- `GET /api/etat` donne la photographie de l'atelier, et `GET /api/pieces` la liste des pièces.
- `POST /api/consignes` permet d'envoyer une décision vers un poste : c'est le sens retour du jumeau.

## 7. Fichiers

| Fichier | Rôle |
|---|---|
| `serveur.py` | Serveur web et API (bibliothèque standard uniquement) |
| `base.py` | Base SQLite et toutes les règles (traçabilité, défauts, lots, kanban, consignes) |
| `config.py` | Postes, gammes, causes de défaut, seuils, délais : **à adapter à la maquette** |
| `web/scan.html` | Page du téléphone |
| `web/pc.html` | Page de gestion du PC |
| `tests_scan.py` | 19 tests (règles, NFC, mise à niveau d'une base existante, serveur) : `py -3 avelis_scan\tests_scan.py` |
| `demarrer.bat`, `autoriser_pare_feu.bat` | Lancement et pare-feu sous Windows |
