"""Configuration de l'application de scan (avelis_scan) : postes de l'atelier, gammes, défauts, kanban.

Tout ce qui décrit l'atelier est ici : on adapte l'application à la maquette en modifiant ce
fichier, sans toucher au reste. Les noms de zones sont ceux de avelis_flux/modele.py et les noms
d'étapes ceux de avelis_flux/simulation.py (POINTS_MODULE, POINTS_POD) : le futur jumeau numérique
pourra relier chaque scan à une zone du plan.

Les valeurs chiffrées (délais, seuils) sont des HYPOTHÈSES de l'équipe, à valider.
"""

PORT = 8000

# ─────────────────────────────────────────────────────────────────────────────────────────────
# Postes de l'atelier : ce que l'opérateur choisit sur son téléphone
# id : identifiant court ; nom : affiché ; zone : zone du plan (avelis_flux) ; role : nature
# ─────────────────────────────────────────────────────────────────────────────────────────────
POSTES = [
    {"id": "bureau", "nom": "Bureaux / pilotage (lancement OF)", "zone": "Bureaux / pilotage", "role": "bureau"},
    {"id": "reception", "nom": "Réception", "zone": "Réception", "role": "quai"},
    {"id": "magasin", "nom": "Stock matières / magasin", "zone": "Stock matières", "role": "magasin"},
    {"id": "kitting", "nom": "Kitting", "zone": "Kitting", "role": "poste"},
    {"id": "ligne_2d", "nom": "Ligne 2D robotisée", "zone": "Ligne 2D robotisée", "role": "poste"},
    {"id": "pod_1", "nom": "Pod · Poste 1 Châssis", "zone": "Ligne pods", "role": "poste"},
    {"id": "pod_2", "nom": "Pod · Poste 2 Parois + étanchéité", "zone": "Ligne pods", "role": "poste"},
    {"id": "pod_3", "nom": "Pod · Poste 3 Plomberie-élec", "zone": "Ligne pods", "role": "poste"},
    {"id": "pod_4", "nom": "Pod · Poste 4 Finitions", "zone": "Ligne pods", "role": "poste"},
    {"id": "controle_pod", "nom": "Contrôle pod", "zone": "Ligne pods", "role": "controle"},
    {"id": "assemblage", "nom": "Assemblage 3D", "zone": "Assemblage 3D", "role": "poste"},
    {"id": "controle_final", "nom": "Contrôle final", "zone": "Contrôle final", "role": "controle"},
    {"id": "stock_pf", "nom": "Stock produits finis", "zone": "Stock produits finis", "role": "stock"},
    {"id": "expedition", "nom": "Expédition", "zone": "Expédition", "role": "quai"},
]
POSTE_MAGASIN = "magasin"  # poste qui prépare les bacs kanban

# ─────────────────────────────────────────────────────────────────────────────────────────────
# Types de pièces et gammes (étapes dans l'ordre : nom de l'événement, poste où on le scanne)
# 1 module = 1 logement (hypothèse simplificatrice de l'équipe)
# ─────────────────────────────────────────────────────────────────────────────────────────────
INTEGRATION = "Intégré au module"
EXPEDITION = "Expédié"

TYPES = {
    "module": {
        "libelle": "Module 3D (1 logement)", "prefixe": "MOD-29-",
        "gamme": [("OF lancé", "bureau"), ("Kitting", "kitting"),
                  ("Début assemblage", "assemblage"), ("Fin assemblage", "assemblage"),
                  ("Contrôle final OK", "controle_final"), ("Entrée stock PF", "stock_pf"),
                  (EXPEDITION, "expedition")],
    },
    "pod": {
        "libelle": "Pod salle de bain", "prefixe": "POD-29-",
        "gamme": [("Kitting", "kitting"), ("Poste 1 Châssis", "pod_1"),
                  ("Poste 2 Parois + étanchéité", "pod_2"), ("Poste 3 Plomberie-élec", "pod_3"),
                  ("Poste 4 Finitions", "pod_4"), ("Contrôle pod OK", "controle_pod"),
                  (INTEGRATION, "assemblage")],
    },
    "kit2d": {
        "libelle": "Kit panneaux 2D (12 panneaux)", "prefixe": "K2D-29-",
        "gamme": [("Kitting", "kitting"), ("Panneaux 2D terminés", "ligne_2d"),
                  (INTEGRATION, "assemblage")],
    },
    "ossature": {
        "libelle": "Ossature acier 1D", "prefixe": "OSS-29-",
        "gamme": [("Réception", "reception"), ("Stockage", "magasin"), ("Kitting", "kitting"),
                  (INTEGRATION, "assemblage")],
    },
    "composant": {
        "libelle": "Composant suivi par n° de série", "prefixe": "CMP-29-",
        "gamme": [("Réception", "reception"), ("Stockage", "magasin"), ("Kitting", "kitting"),
                  (INTEGRATION, "assemblage")],
    },
    "lot": {
        "libelle": "Lot de matières (fournisseur)", "prefixe": "LOT-",
        "gamme": [("Réception lot", "reception"), ("Stockage lot", "magasin")],
    },
}
CHIFFRES_NUMERO = {"lot": 4}  # LOT-0001 ; les autres : 00001
PREFIXE_KANBAN = "KB-"

# Quand le kit 2D d'un module atteint cette étape, l'événement est aussi noté sur le module
# (point de contrôle « Panneaux 2D terminés » du module dans la simulation)
ETAPES_RECOPIEES_SUR_MODULE = {"Panneaux 2D terminés"}

# Ce que contient un « module complet » créé d'un coup (même numéro pour tout le module)
COMPOSITION_MODULE = [
    ("pod", "Pod salle de bain", ""),
    ("kit2d", "Kit panneaux 2D : plancher, murs, toiture, cloisons", ""),
    ("ossature", "Ossature acier 1D (poteaux, longerons, traverses)", "FOUR-A"),
]
COMPOSANTS_SERIE = [  # suffixe du code, désignation, fournisseur
    ("FEN", "Fenêtre séjour", "FOUR-D"),
    ("POR", "Porte d'entrée", "FOUR-D"),
    ("PAC", "Pompe à chaleur", "FOUR-C"),
    ("TAB", "Tableau électrique", "FOUR-C"),
]

FOURNISSEURS = {  # HYPOTHÈSE : mêmes codes que la simulation
    "FOUR-A": "Acier (ossature 1D)",
    "FOUR-B": "Panneaux bois/acier (2D)",
    "FOUR-C": "Sanitaire et équipements techniques",
    "FOUR-D": "Menuiseries et second œuvre",
}
CHANTIERS = ["Île-de-France", "Lyon", "Marseille", "Lille", "Strasbourg", "Dijon", "Bordeaux",
             "Nantes"]

# ─────────────────────────────────────────────────────────────────────────────────────────────
# Défauts
# ─────────────────────────────────────────────────────────────────────────────────────────────
CATEGORIES_DEFAUT = ["Étanchéité", "Dimension / géométrie", "Finition / aspect", "Plomberie",
                     "Électricité", "Assemblage / jonction", "Pièce manquante", "Autre"]
CAUSES_DEFAUT = {  # cause présumée : bloque-t-elle tout le lot ?
    "Matière / lot fournisseur": True,
    "Poste (méthode, main-d'œuvre)": False,
    "Machine": False,
    "Conception": False,
    "Manutention / transport": False,
    "Inconnue": False,
}
GRAVITES = ["Mineure", "Majeure", "Critique"]
SEUIL_DEFAUTS_LOT = 2  # HYPOTHÈSE : à partir de 2 défauts sur un même lot, le lot est bloqué

# ─────────────────────────────────────────────────────────────────────────────────────────────
# Règles de scan et kanban
# ─────────────────────────────────────────────────────────────────────────────────────────────
ANTI_DOUBLE_SCAN_S = 60  # un même scan au même poste dans ce délai est ignoré

# Moyens d'identification d'une pièce, notés avec chaque scan : étiquette QR (caméra), puce NFC
# (lue ou écrite par le téléphone, Web NFC d'Android) ou code saisi au clavier
MOYENS_IDENTIFICATION = {"qr": "QR code", "nfc": "Puce NFC", "saisie": "Saisie du code"}
EVENEMENT_ECRITURE_NFC = "Puce NFC écrite"
DELAI_KANBAN_MIN = 30  # HYPOTHÈSE : délai cible de réapprovisionnement (mettre 3 pour la démo)
INTERVALLE_SURVEILLANCE_S = 20  # vérification des demandes kanban en retard
ETATS_KANBAN = ("pleine", "vide", "en_preparation")  # « livrée » ramène la carte à « pleine »
