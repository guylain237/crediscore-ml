"""Met les valeurs d'un dossier en francais lisible.

POURQUOI CE MODULE EXISTE.

Une capture d'ecran de la page de restitution, le 08/09/2026, montrait ceci
comme motif de refus presente a un demandeur :

    anciennete dans l'emploi          -637.0            defavorable
    secteur d'activite de l'employeur Business Entity Type 3
    score externe n3                  0.13937578009978951

Trois problemes dans trois lignes.

  -637.0        un nombre NEGATIF de jours. Cela signifie 637 jours AVANT la
                demande, donc un an et neuf mois d'anciennete. Pour un
                demandeur, "-637" ressemble a une panne.

  Business...   de l'anglais brut, sur un ecran destine a un demandeur
                francais.

  0.139375...   dix-sept decimales. Illisible, et un lecteur d'ecran les
                prononce toutes.

Aucun de mes tests d'accessibilite ne les avait vus : ils verifiaient la
STRUCTURE de la page, pas la lisibilite des VALEURS. C'est exactement ce que
docs/accessibilite.md annoncait comme demandant un oeil humain — un oeil
humain l'a trouve.

CE QUE CE MODULE NE FAIT PAS.

Il ne traduit pas les valeurs dans les donnees. Le modele continue de voir
"Business Entity Type 3" : traduire en amont changerait les modalites
apprises. La traduction est une couche d'AFFICHAGE, appliquee au dernier
moment.
"""

# --- Variables exprimees en jours AVANT la demande ---------------------------
#
# Leur valeur est negative par construction : -1663 veut dire "il y a 1663
# jours". La liste est etablie a la main et non par le signe : certaines
# variables sont negatives pour une tout autre raison. INSTAL_RETARD_JOURS_MEAN
# vaut -10 parce que le client paie DIX JOURS EN AVANCE, pas parce que c'est
# une date passee. Les confondre inverserait le sens du motif.
JOURS_AVANT_LA_DEMANDE = {
    "DAYS_EMPLOYED",
    "DAYS_REGISTRATION",
    "DAYS_ID_PUBLISH",
    "DAYS_LAST_PHONE_CHANGE",
    "BUREAU_JOURS_CREDIT_ANCIEN",
    "BUREAU_JOURS_CREDIT_RECENT",
    "BUREAU_JOURS_MAJ_RECENTE",
    "PREV_JOURS_DERNIERE_DEMANDE",
    "PREV_JOURS_PREMIERE_DEMANDE",
}

# Meme chose, comptees en mois.
MOIS_AVANT_LA_DEMANDE = {"POS_DERNIER_MOIS", "BB_DERNIER_MOIS"}

# Une date qui peut etre passee OU future : l'echeance des credits en cours.
JOURS_RELATIFS = {"BUREAU_JOURS_FIN_MAX"}

# Retards de paiement : negatif veut dire EN AVANCE, positif EN RETARD.
RETARDS_EN_JOURS = {
    "INSTAL_RETARD_JOURS_MEAN",
    "INSTAL_RETARD_JOURS_SUM",
    "INSTAL_RETARD_JOURS_MAX",
    "INSTAL_RETARD_MAX_12M",
}

# Variables exprimees en euros.
MONTANTS = {
    "AMT_CREDIT", "AMT_ANNUITY", "AMT_GOODS_PRICE", "AMT_INCOME_TOTAL",
    "REVENU_PAR_PERSONNE", "INSTAL_RESTE_DU", "INSTAL_MONTANT_DU_SUM",
    "INSTAL_MONTANT_PAYE_SUM", "BUREAU_DETTE_MAX", "BUREAU_DETTE_MEAN",
    "BUREAU_IMPAYE_MAX", "BUREAU_IMPAYE_SUM", "BUREAU_PLAFOND_MAX",
    "BUREAU_PLAFOND_SUM", "BUREAU_ANNUITE_SUM", "BUREAU_ANNUITE_MEAN",
    "CC_PLAFOND_SUM", "CC_PAIEMENT_MEAN", "CC_MONTANT_RETRAITS_ESPECES",
    "PREV_AMT_CREDIT_SUM", "PREV_AMT_ANNUITY_MAX", "PREV_AMT_ANNUITY_MEAN",
    "PREV_AMT_APPLICATION_MAX", "PREV_AMT_APPLICATION_MEAN",
    "PREV_AMT_GOODS_PRICE_MEAN", "PREV_AMT_DOWN_PAYMENT_MEAN",
}

# Le sens d'un motif, accentue. Le code interne reste en ASCII ; ce qui est
# montre a un demandeur ne le peut pas.
SENS = {"defavorable": "défavorable", "favorable": "favorable"}

# --- Traduction des modalites ------------------------------------------------

SECTEURS = {
    "Advertising": "Publicité",
    "Agriculture": "Agriculture",
    "Bank": "Banque",
    "Cleaning": "Nettoyage",
    "Construction": "Construction",
    "Culture": "Culture",
    "Electricity": "Électricité",
    "Emergency": "Services d'urgence",
    "Government": "Fonction publique",
    "Hotel": "Hôtellerie",
    "Housing": "Logement",
    "Insurance": "Assurance",
    "Kindergarten": "Petite enfance",
    "Legal Services": "Services juridiques",
    "Medicine": "Santé",
    "Military": "Armée",
    "Mobile": "Téléphonie mobile",
    "Other": "Autre",
    "Police": "Police",
    "Postal": "Services postaux",
    "Realtor": "Immobilier",
    "Religion": "Culte",
    "Restaurant": "Restauration",
    "School": "Enseignement scolaire",
    "Security": "Sécurité",
    "Security Ministries": "Ministères de la sécurité",
    "Self-employed": "Indépendant",
    "Services": "Services",
    "Telecom": "Télécommunications",
    "Transport": "Transport",
    "University": "Enseignement supérieur",
    "XNA": "non renseigné",
}
# Les familles numerotees : "Business Entity Type 3", "Industry: type 11"...
# Le numero ne designe rien de public dans le jeu de donnees ; on le conserve
# tel quel plutot que d'inventer un libelle.
for numero in range(1, 4):
    SECTEURS[f"Business Entity Type {numero}"] = f"Entreprise (type {numero})"
for numero in range(1, 14):
    SECTEURS[f"Industry: type {numero}"] = f"Industrie (type {numero})"
for numero in range(1, 8):
    SECTEURS[f"Trade: type {numero}"] = f"Commerce (type {numero})"
for numero in range(1, 5):
    SECTEURS[f"Transport: type {numero}"] = f"Transport (type {numero})"

MODALITES = {
    "ORGANIZATION_TYPE": SECTEURS,
    "NAME_CONTRACT_TYPE": {
        "Cash loans": "Prêt personnel",
        "Revolving loans": "Crédit renouvelable",
    },
    "FLAG_OWN_CAR": {"Y": "oui", "N": "non"},
    "FLAG_OWN_REALTY": {"Y": "oui", "N": "non"},
    "EMERGENCYSTATE_MODE": {"Yes": "oui", "No": "non"},
    "NAME_TYPE_SUITE": {
        "Unaccompanied": "seul",
        "Family": "en famille",
        "Spouse, partner": "avec le conjoint",
        "Children": "avec les enfants",
        "Group of people": "en groupe",
        "Other_A": "autre",
        "Other_B": "autre",
    },
    "NAME_INCOME_TYPE": {
        "Working": "Salarié",
        "Commercial associate": "Associé commercial",
        "Pensioner": "Retraité",
        "State servant": "Fonctionnaire",
        "Businessman": "Chef d'entreprise",
        "Student": "Étudiant",
        "Unemployed": "Sans emploi",
        "Maternity leave": "Congé maternité",
    },
    "NAME_EDUCATION_TYPE": {
        "Secondary / secondary special": "Enseignement secondaire",
        "Higher education": "Enseignement supérieur",
        "Incomplete higher": "Supérieur non achevé",
        "Lower secondary": "Secondaire premier cycle",
        "Academic degree": "Diplôme universitaire",
    },
    "NAME_HOUSING_TYPE": {
        "House / apartment": "Maison ou appartement",
        "With parents": "Chez les parents",
        "Municipal apartment": "Logement social",
        "Rented apartment": "Location",
        "Office apartment": "Logement de fonction",
        "Co-op apartment": "Coopérative d'habitation",
    },
    "OCCUPATION_TYPE": {
        "Laborers": "Ouvrier",
        "Low-skill Laborers": "Ouvrier non qualifié",
        "Sales staff": "Vente",
        "Core staff": "Employé",
        "Managers": "Cadre",
        "Drivers": "Conducteur",
        "High skill tech staff": "Technicien qualifié",
        "Accountants": "Comptabilité",
        "Medicine staff": "Personnel de santé",
        "Security staff": "Sécurité",
        "Cooking staff": "Cuisine",
        "Cleaning staff": "Entretien",
        "Private service staff": "Services à la personne",
        "Secretaries": "Secrétariat",
        "Waiters/barmen staff": "Service en salle",
        "Realty agents": "Agent immobilier",
        "HR staff": "Ressources humaines",
        "IT staff": "Informatique",
    },
    "WEEKDAY_APPR_PROCESS_START": {
        "MONDAY": "lundi", "TUESDAY": "mardi", "WEDNESDAY": "mercredi",
        "THURSDAY": "jeudi", "FRIDAY": "vendredi", "SATURDAY": "samedi",
        "SUNDAY": "dimanche",
    },
    "HOUSETYPE_MODE": {
        "block of flats": "immeuble collectif",
        "terraced house": "maison mitoyenne",
        "specific housing": "logement spécifique",
    },
    "WALLSMATERIAL_MODE": {
        "Stone, brick": "pierre ou brique",
        "Panel": "panneaux",
        "Block": "blocs",
        "Wooden": "bois",
        "Mixed": "mixte",
        "Monolithic": "monolithique",
        "Others": "autre",
    },
    "FONDKAPREMONT_MODE": {
        "reg oper account": "compte de gestion",
        "org spec account": "compte dédié de l'organisme",
        "reg oper spec account": "compte de gestion dédié",
        "not specified": "non précisé",
    },
}


# Separateur de milliers : ESPACE FINE INSECABLE (U+202F), et non une
# espace ordinaire.
#
# C'est la forme recommandee en typographie francaise, et surtout elle est
# INSECABLE : un montant ne doit pas se couper en fin de ligne, sans quoi
# on lit "24" a la fin d'une ligne et "903 EUR" au debut de la suivante.
#
# Elle etait arrivee ici par une faute de frappe. Elle y reste parce
# qu'elle est juste — mais nommee, pour que personne ne la remplace par une
# espace ordinaire en croyant corriger une coquille.
ESPACE_MILLIERS = chr(0x202F)


def duree(jours):
    """Un nombre de jours, ecrit comme on le dit."""
    jours = abs(round(jours))
    annees, reste = divmod(jours, 365)
    mois = reste // 30

    if annees and mois:
        return f"{annees} an{'s' if annees > 1 else ''} et {mois} mois"
    if annees:
        return f"{annees} an{'s' if annees > 1 else ''}"
    if mois:
        return f"{mois} mois"
    return f"{jours} jour{'s' if jours > 1 else ''}"


def nombre(valeur, decimales=2):
    """Un nombre en francais : virgule, espaces de milliers, arrondi utile.

    Les dix-sept decimales d'un flottant ne disent rien de plus que deux, et un
    lecteur d'ecran les prononce toutes.
    """
    arrondi = round(float(valeur), decimales)
    if arrondi == int(arrondi):
        texte = f"{int(arrondi):,}".replace(",", ESPACE_MILLIERS)
    else:
        texte = f"{arrondi:,.{decimales}f}".replace(",", ESPACE_MILLIERS).replace(".", ",")
    return texte


def formater(variable, valeur):
    """Rend une valeur de dossier lisible par un demandeur."""
    if valeur is None or valeur == "":
        return "non renseignée"

    # 1. Une modalite a traduire.
    if variable in MODALITES:
        return MODALITES[variable].get(str(valeur), str(valeur))

    # 2. Tout le reste doit etre un nombre. Si ce n'en est pas un, on le rend
    #    tel quel plutot que de masquer le probleme derriere une erreur.
    try:
        chiffre = float(valeur)
    except (TypeError, ValueError):
        return str(valeur)

    if variable in JOURS_AVANT_LA_DEMANDE:
        return f"il y a {duree(chiffre)}"

    if variable in MOIS_AVANT_LA_DEMANDE:
        mois = abs(round(chiffre))
        return f"il y a {mois} mois" if mois else "ce mois-ci"

    if variable in JOURS_RELATIFS:
        return f"dans {duree(chiffre)}" if chiffre > 0 else f"il y a {duree(chiffre)}"

    if variable in RETARDS_EN_JOURS:
        if chiffre > 0:
            return f"{duree(chiffre)} de retard"
        if chiffre < 0:
            return f"{duree(chiffre)} d'avance"
        return "à l'heure"

    if variable in MONTANTS:
        return f"{nombre(chiffre, 0)} €"

    return nombre(chiffre)


def sens(valeur):
    """Le sens d'un motif, accentue pour l'affichage."""
    return SENS.get(str(valeur), str(valeur))
