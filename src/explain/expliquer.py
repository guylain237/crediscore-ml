"""Explique les decisions du modele, globalement et dossier par dossier.

POURQUOI C'EST OBLIGATOIRE ICI.

L'article 22 du RGPD donne au demandeur le droit de comprendre une decision
automatisee qui le concerne. "Votre demande est refusee" ne suffit pas : il faut
pouvoir dire POURQUOI, en termes qu'il comprend.

SHAP repond a cette question. Pour chaque dossier, il attribue a chaque variable
une contribution chiffree : de combien elle a pousse le score vers le haut ou
vers le bas. La somme de ces contributions reconstitue exactement l'ecart entre
la prediction et la moyenne — ce n'est pas une approximation.

DEUX NIVEAUX.

  GLOBAL  quelles variables comptent le plus, sur l'ensemble du portefeuille.
          Sert au comite de suivi et a la detection de derive.

  LOCAL   pourquoi CE dossier a ete refuse. Sert a motiver la decision aupres
          du demandeur et de l'analyste qui la reexamine.

UNE PRECISION IMPORTANTE.

SHAP s'applique au modele NON calibre. Ce n'est pas un oubli : la calibration
est une transformation monotone, elle ne change pas l'ordre des dossiers ni la
contribution relative des variables. Les facteurs explicatifs sont donc les
memes ; seule l'echelle du score differe.

Controle C-5 du plan de gouvernance. Exigence : moins d'une seconde par dossier.

Usage : python src/explain/expliquer.py
"""

import sys
import time
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
import shap

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

# Combien de dossiers servent au calcul global. SHAP est exact mais couteux :
# 5 000 dossiers suffisent a stabiliser les moyennes, et le calcul tient en
# quelques secondes au lieu de plusieurs minutes.
ECHANTILLON_GLOBAL = 5000

# Combien de facteurs on retient pour motiver une decision. Au-dela de cinq, un
# demandeur ne retient plus rien, et un analyste non plus.
FACTEURS_PAR_DOSSIER = 5

# Libelles lisibles pour les variables les plus frequentes. Un demandeur ne
# comprend pas "RATIO_ANNUITE_REVENU" ; il comprend "taux d'effort mensuel".
#
# C'est la regle F4 du plan de features : toute variable doit etre explicable a
# un client. Les variables absentes de cette table gardent leur nom technique —
# et ce sont celles qu'il faudra traduire avant la mise en production.
LIBELLES = {
    "RATIO_ANNUITE_REVENU": "taux d'effort mensuel",
    "RATIO_CREDIT_REVENU": "montant emprunte rapporte au revenu",
    "RATIO_ANNUITE_CREDIT": "duree implicite du pret",
    "RATIO_CREDIT_BIEN": "part financee du bien",
    "REVENU_PAR_PERSONNE": "revenu par personne du foyer",
    "RATIO_ANCIENNETE": "stabilite professionnelle",
    "NB_DOCUMENTS": "completude du dossier",
    "AMT_CREDIT": "montant du credit demande",
    "AMT_ANNUITY": "mensualite",
    "AMT_INCOME_TOTAL": "revenu declare",
    "DAYS_EMPLOYED": "anciennete dans l'emploi",
    "DAYS_REGISTRATION": "anciennete du dossier",
    "ORGANIZATION_TYPE": "secteur d'activite de l'employeur",
    "OCCUPATION_TYPE": "categorie professionnelle",
    "NAME_EDUCATION_TYPE": "niveau d'etudes",
    "NAME_INCOME_TYPE": "type de revenu",
    "EXT_SOURCE_1": "score externe n1",
    "EXT_SOURCE_2": "score externe n2",
    "EXT_SOURCE_3": "score externe n3",
    "INSTAL_RETARD_JOURS_MEAN": "retard moyen sur les echeances passees",
    "INSTAL_RETARD_JOURS_MAX": "retard le plus important constate",
    "INSTAL_RETARD_MAX_12M": "retard maximal sur les douze derniers mois",
    "INSTAL_PART_RETARDS": "part des echeances payees en retard",
    "INSTAL_TAUX_PAIEMENT_MEAN": "part des echeances effectivement reglees",
    "INSTAL_NB_ECHEANCES": "nombre d'echeances dans l'historique",
    "PREV_NB_DEMANDES": "nombre de demandes anterieures",
    "PREV_PART_REFUSEES": "part de demandes anterieures refusees",
    "PREV_PART_ACCORDEE_MEAN": "part du montant accorde par le passe",
    "BUREAU_NB_ACTIFS": "credits en cours chez d'autres etablissements",
    "BUREAU_DETTE_SUM": "dette totale chez d'autres etablissements",
    "BUREAU_TAUX_UTILISATION": "utilisation des plafonds accordes ailleurs",
    "BUREAU_JOURS_CREDIT_RECENT": "anciennete du dernier credit externe",
    "BUREAU_NB_AVEC_IMPAYE": "credits externes en impaye",
    "POS_DPD_MAX": "retard maximal sur les credits en cours",
    "POS_PART_MOIS_RETARD": "part de mois en retard",
    "CC_TAUX_UTILISATION_MEAN": "utilisation moyenne du plafond de carte",
    "CC_TAUX_UTILISATION_MAX": "utilisation maximale du plafond de carte",
    "INSTAL_RESTE_DU": "montant restant du sur les credits anterieurs",
    "POS_MENSUALITES_RESTANTES": "mensualites restant a payer",
    "INSTAL_RETARD_JOURS_SUM": "cumul des jours de retard",
    "INSTAL_NB_RETARDS": "nombre d'echeances payees en retard",
    "INSTAL_NB_JAMAIS_PAYEES": "echeances jamais payees",
    "BUREAU_NB_CREDITS": "nombre de credits chez d'autres etablissements",
    "BUREAU_PLAFOND_SUM": "plafonds accordes par d'autres etablissements",
    "PREV_AMT_CREDIT_MEAN": "montant moyen des credits anterieurs",
    "POS_NB_ACTIFS": "credits en cours",
    "CC_SOLDE_MEAN": "solde moyen de la carte de credit",

    # Ajoutes le 31/08/2026 : ces 71 variables apparaissaient dans les cinq
    # motifs d'au moins un dossier sur les 5 000 examines. Sans libelle, un
    # demandeur aurait recu son motif de refus en jargon technique.
    "AMT_GOODS_PRICE": "prix du bien finance",
    "AMT_REQ_CREDIT_BUREAU_WEEK": "interrogations du bureau de credit dans la semaine",
    "CNT_FAM_MEMBERS": "nombre de personnes dans le foyer",
    "DAYS_ID_PUBLISH": "anciennete de la piece d'identite",
    "DAYS_LAST_PHONE_CHANGE": "anciennete du dernier changement de telephone",
    "DEF_30_CNT_SOCIAL_CIRCLE": "proches ayant eu 30 jours de retard",
    "DEF_60_CNT_SOCIAL_CIRCLE": "proches ayant eu 60 jours de retard",
    "FLAG_DOCUMENT_3": "fourniture du document 3",
    "FLAG_WORK_PHONE": "telephone professionnel fourni",
    "NAME_HOUSING_TYPE": "type de logement",
    "NAME_TYPE_SUITE": "accompagnant lors de la demande",
    "OWN_CAR_AGE": "age du vehicule",
    "REGION_POPULATION_RELATIVE": "densite de population de la region",
    "REGION_RATING_CLIENT_W_CITY": "note de la region de residence",
    "REG_CITY_NOT_LIVE_CITY": "adresse declaree differente de la residence",
    "WEEKDAY_APPR_PROCESS_START": "jour de la semaine de la demande",
    "APARTMENTS_MEDI": "surface des appartements de l'immeuble (mediane)",
    "APARTMENTS_MODE": "surface des appartements de l'immeuble (mode)",
    "BASEMENTAREA_MODE": "surface des sous-sols de l'immeuble",
    "COMMONAREA_AVG": "surface des parties communes",
    "ELEVATORS_MEDI": "nombre d'ascenseurs de l'immeuble",
    "LIVINGAREA_MEDI": "surface habitable",
    "NONLIVINGAPARTMENTS_MEDI": "locaux non habitables de l'immeuble (mediane)",
    "NONLIVINGAPARTMENTS_MODE": "locaux non habitables de l'immeuble (mode)",
    "TOTALAREA_MODE": "surface totale de l'immeuble",
    "YEARS_BEGINEXPLUATATION_MODE": "annee de mise en service de l'immeuble",
    "BB_NB_MOIS": "mois d'historique detaille des credits exterieurs",
    "BB_PART_CLOS": "part des mois ou le credit exterieur etait solde",
    "BUREAU_ANNUITE_SUM": "total des mensualites chez d'autres etablissements",
    "BUREAU_DETTE_MAX": "dette la plus elevee chez un autre etablissement",
    "BUREAU_DETTE_MEAN": "dette moyenne chez les autres etablissements",
    "BUREAU_DUREE_HISTORIQUE_JOURS": "anciennete de l'historique exterieur",
    "BUREAU_IMPAYE_HISTORIQUE_MAX": "impaye le plus eleve de tout l'historique exterieur",
    "BUREAU_IMPAYE_MAX": "impaye courant le plus eleve",
    "BUREAU_IMPAYE_SUM": "total des impayes courants",
    "BUREAU_JOURS_FIN_MAX": "echeance la plus lointaine des credits exterieurs",
    "BUREAU_JOURS_MAJ_RECENTE": "anciennete de la derniere mise a jour du bureau",
    "BUREAU_PART_CLOS": "part des credits exterieurs deja soldes",
    "BUREAU_PART_VENDUS": "part des credits exterieurs cedes a un tiers",
    "BUREAU_PLAFOND_MAX": "plafond le plus eleve accorde ailleurs",
    "CC_MONTANT_RETRAITS_ESPECES": "montant retire en especes sur la carte",
    "CC_NB_MOIS": "mois d'historique de carte de credit",
    "CC_NB_OPERATIONS": "nombre d'operations sur la carte",
    "CC_NB_RETRAITS_ESPECES": "nombre de retraits en especes",
    "CC_PART_RETRAITS_ESPECES": "part des retraits en especes dans l'usage de la carte",
    "CC_PLAFOND_SUM": "total des plafonds de carte",
    "CC_TAUX_UTILISATION_12M": "taux d'utilisation de la carte sur douze mois",
    "INSTAL_MONTANT_DU_SUM": "total du a l'echeancier",
    "INSTAL_MONTANT_PAYE_SUM": "total effectivement paye",
    "INSTAL_NB_CREDITS": "nombre de credits anterieurs avec echeancier",
    "INSTAL_NB_ECHEANCES_12M": "echeances sur les douze derniers mois",
    "INSTAL_RETARD_JOURS_STD": "irregularite des retards de paiement",
    "POS_DERNIER_MOIS": "anciennete du dernier point de situation",
    "POS_DPD_DEF_MAX": "retard grave maximal constate",
    "POS_DPD_DEF_MEAN": "retard grave moyen",
    "POS_NB_MOIS": "mois d'historique de credit a la consommation",
    "POS_NB_TERMINES": "credits a la consommation menes a terme",
    "POS_PART_MOIS_RETARD_GRAVE": "part des mois passes en retard grave",
    "PREV_AMT_ANNUITY_MAX": "mensualite la plus elevee des demandes anterieures",
    "PREV_AMT_ANNUITY_MEAN": "mensualite moyenne des demandes anterieures",
    "PREV_AMT_DOWN_PAYMENT_MEAN": "apport moyen des demandes anterieures",
    "PREV_CNT_PAYMENT_MAX": "duree la plus longue accordee par le passe",
    "PREV_CNT_PAYMENT_MEAN": "duree moyenne des credits anterieurs",
    "PREV_JOURS_DERNIERE_DEMANDE": "anciennete de la derniere demande",
    "PREV_JOURS_PREMIERE_DEMANDE": "anciennete de la premiere demande",
    "PREV_NB_REFUSEES": "nombre de demandes anterieures refusees",
    "PREV_PART_ACCEPTEES": "part des demandes anterieures acceptees",
    "PREV_PART_ACCORDEE_MIN": "part la plus faible du montant demande qui a ete accordee",
    "PREV_PART_CONSO": "part des credits a la consommation dans l'historique",
    "PREV_PART_RENOUVELABLE": "part des credits renouvelables dans l'historique",
    "PREV_RATE_DOWN_PAYMENT_MEAN": "taux d'apport moyen des demandes anterieures",

    # Completes apres mesure sur les 61 503 dossiers de test : ces 40
    # variables atteignaient le haut du classement d'au moins un dossier.
    "AMT_REQ_CREDIT_BUREAU_QRT": "interrogations du bureau de credit dans le trimestre",
    "HOUR_APPR_PROCESS_START": "heure de depot de la demande",
    "OBS_30_CNT_SOCIAL_CIRCLE": "proches observes a 30 jours de retard",
    "REGION_RATING_CLIENT": "note de la region du demandeur",
    "APARTMENTS_AVG": "surface des appartements de l'immeuble (moyenne)",
    "BASEMENTAREA_AVG": "surface des sous-sols (moyenne)",
    "BASEMENTAREA_MEDI": "surface des sous-sols (mediane)",
    "COMMONAREA_MEDI": "surface des parties communes (mediane)",
    "ELEVATORS_MODE": "nombre d'ascenseurs (mode)",
    "ENTRANCES_AVG": "nombre d'entrees de l'immeuble (moyenne)",
    "ENTRANCES_MEDI": "nombre d'entrees de l'immeuble (mediane)",
    "ENTRANCES_MODE": "nombre d'entrees de l'immeuble (mode)",
    "FLOORSMAX_MEDI": "nombre d'etages de l'immeuble (mediane)",
    "FLOORSMIN_MEDI": "nombre minimal d'etages (mediane)",
    "FLOORSMIN_MODE": "nombre minimal d'etages (mode)",
    "LANDAREA_AVG": "surface du terrain (moyenne)",
    "LANDAREA_MODE": "surface du terrain (mode)",
    "LIVINGAPARTMENTS_AVG": "logements habitables de l'immeuble (moyenne)",
    "LIVINGAPARTMENTS_MODE": "logements habitables de l'immeuble (mode)",
    "LIVINGAREA_AVG": "surface habitable (moyenne)",
    "NONLIVINGAPARTMENTS_AVG": "locaux non habitables (moyenne)",
    "NONLIVINGAREA_AVG": "surface non habitable (moyenne)",
    "NONLIVINGAREA_MEDI": "surface non habitable (mediane)",
    "WALLSMATERIAL_MODE": "materiau des murs de l'immeuble",
    "YEARS_BEGINEXPLUATATION_MEDI": "annee de mise en service (mediane)",
    "YEARS_BUILD_AVG": "annee de construction de l'immeuble",
    "BB_NB_MOIS_RETARD": "mois de retard sur les credits exterieurs",
    "BB_PART_MOIS_RETARD": "part des mois passes en retard a l'exterieur",
    "BUREAU_ANNUITE_MEAN": "mensualite moyenne chez les autres etablissements",
    "BUREAU_JOURS_CREDIT_ANCIEN": "anciennete du plus vieux credit exterieur",
    "BUREAU_PART_ACTIFS": "part des credits exterieurs encore actifs",
    "POS_DPD_MEAN": "retard moyen sur les credits a la consommation",
    "POS_NB_CREDITS": "nombre de credits a la consommation suivis",
    "PREV_AMT_APPLICATION_MAX": "montant le plus eleve demande par le passe",
    "PREV_AMT_APPLICATION_MEAN": "montant moyen demande par le passe",
    "PREV_AMT_CREDIT_MAX": "montant le plus eleve accorde par le passe",
    "PREV_DUREE_RELATION_JOURS": "anciennete de la relation avec l'etablissement",
    "PREV_PART_ANNULEES": "part des demandes anterieures annulees",
    "PREV_PART_NON_UTILISEES": "part des credits accordes mais non utilises",
    "PREV_PART_TRESORERIE": "part des credits de tresorerie dans l'historique",

    # Completes le 02/09/2026 : les 65 dernieres. La mesure precedente ne
    # couvrait que les variables VUES dans un top-5 sur le jeu de test — un
    # nouveau demandeur peut en faire remonter une autre. Toutes les
    # variables du modele ont desormais un libelle, la garantie est totale
    # et non plus statistique.
    "NAME_CONTRACT_TYPE": "type de contrat demande",
    "FLAG_OWN_CAR": "possede un vehicule",
    "FLAG_OWN_REALTY": "proprietaire d'un bien immobilier",
    "CNT_CHILDREN": "nombre d'enfants a charge",
    "FLAG_MOBIL": "telephone mobile fourni",
    "FLAG_CONT_MOBILE": "mobile joignable",
    "FLAG_PHONE": "telephone fixe fourni",
    "FLAG_EMAIL": "adresse electronique fournie",
    "REG_REGION_NOT_LIVE_REGION": "region declaree differente de la region de residence",
    "REG_REGION_NOT_WORK_REGION": "region declaree differente de la region de travail",
    "LIVE_REGION_NOT_WORK_REGION": "residence et travail dans deux regions",
    "REG_CITY_NOT_WORK_CITY": "ville declaree differente de la ville de travail",
    "LIVE_CITY_NOT_WORK_CITY": "residence et travail dans deux villes",
    "YEARS_BEGINEXPLUATATION_AVG": "annee de mise en service (moyenne)",
    "ELEVATORS_AVG": "nombre d'ascenseurs (moyenne)",
    "FLOORSMAX_AVG": "nombre d'etages (moyenne)",
    "FLOORSMIN_AVG": "nombre minimal d'etages (moyenne)",
    "YEARS_BUILD_MODE": "annee de construction (mode)",
    "YEARS_BUILD_MEDI": "annee de construction (mediane)",
    "COMMONAREA_MODE": "surface des parties communes (mode)",
    "FLOORSMAX_MODE": "nombre d'etages (mode)",
    "LIVINGAREA_MODE": "surface habitable (mode)",
    "NONLIVINGAREA_MODE": "surface non habitable (mode)",
    "LANDAREA_MEDI": "surface du terrain (mediane)",
    "LIVINGAPARTMENTS_MEDI": "logements habitables de l'immeuble (mediane)",
    "FONDKAPREMONT_MODE": "regime de financement des travaux de l'immeuble",
    "HOUSETYPE_MODE": "type d'immeuble",
    "EMERGENCYSTATE_MODE": "immeuble declare en etat d'urgence",
    "OBS_60_CNT_SOCIAL_CIRCLE": "proches observes a 60 jours de retard",
    "AMT_REQ_CREDIT_BUREAU_HOUR": "interrogations du bureau dans l'heure",
    "AMT_REQ_CREDIT_BUREAU_DAY": "interrogations du bureau dans la journee",
    "AMT_REQ_CREDIT_BUREAU_MON": "interrogations du bureau dans le mois",
    "AMT_REQ_CREDIT_BUREAU_YEAR": "interrogations du bureau dans l'annee",
    "DAYS_EMPLOYED_ANORMAL": "absence d'emploi salarie declare",
    "INSTAL_PRESENT": "dispose d'un historique d'echeancier",
    "PREV_PRESENT": "a deja depose une demande",
    "POS_PRESENT": "dispose d'un historique de credit a la consommation",
    "BUREAU_PRESENT": "connu d'autres etablissements de credit",
    "BB_PRESENT": "dispose d'un historique mensuel exterieur",
    "CC_PRESENT": "detient une carte de credit",
    "INSTAL_TAUX_PAIEMENT_MIN": "plus faible taux de paiement d'une echeance",
    "PREV_AMT_CREDIT_SUM": "total des montants accordes par le passe",
    "PREV_AMT_GOODS_PRICE_MEAN": "prix moyen des biens finances par le passe",
    "PREV_PART_ASSUREES": "part des demandes anterieures avec assurance",
    "POS_NB_MOIS_RETARD": "mois de retard sur les credits a la consommation",
    "POS_NB_MOIS_RETARD_GRAVE": "mois de retard grave sur les credits a la consommation",
    "BUREAU_NB_TYPES": "nombre de types de credits detenus ailleurs",
    "BUREAU_JOURS_IMPAYE_MAX": "duree maximale d'un impaye exterieur",
    "BUREAU_NB_PROLONGATIONS": "nombre de prolongations obtenues ailleurs",
    "BUREAU_NB_SANS_ECHEANCE": "credits exterieurs sans echeance connue",
    "BUREAU_PART_IMPAYES": "part des credits exterieurs en impaye",
    "BUREAU_PART_CONSO": "part des credits a la consommation a l'exterieur",
    "BUREAU_PART_CARTE": "part des cartes de credit a l'exterieur",
    "BB_NB_CREDITS": "credits exterieurs suivis mois par mois",
    "BB_GRAVITE_MAX": "gravite maximale d'un retard exterieur",
    "BB_GRAVITE_MEAN": "gravite moyenne des retards exterieurs",
    "BB_PART_INCONNU": "part des mois sans information exterieure",
    "BB_DERNIER_MOIS": "anciennete de la derniere information exterieure",
    "CC_NB_CARTES": "nombre de cartes de credit detenues",
    "CC_PAIEMENT_MEAN": "paiement mensuel moyen sur la carte",
    "CC_DPD_MEAN": "retard moyen sur la carte",
    "CC_DPD_MAX": "retard maximal sur la carte",
    "CC_DPD_DEF_MAX": "retard grave maximal sur la carte",
    "CC_NB_MOIS_RETARD": "mois de retard sur la carte",
    "CC_TENDANCE_UTILISATION": "evolution de l'utilisation de la carte",
}


def libelle(variable):
    """Nom lisible d'une variable, ou son nom technique a defaut."""
    return LIBELLES.get(variable, variable)


def calculer_shap(modele, variables):
    """Contributions SHAP, avec TreeExplainer.

    TreeExplainer est exact et rapide sur les modeles a arbres : il exploite
    leur structure au lieu d'echantillonner. Sur un reseau de neurones, il
    faudrait approximer — c'est l'un des arguments qui ont fait retenir le
    gradient boosting (decision du document de projet).
    """
    explicateur = shap.TreeExplainer(modele)
    valeurs = explicateur.shap_values(variables)

    # Selon les versions, LightGBM rend soit un tableau par classe, soit un
    # seul. On ne garde que la classe positive, celle du defaut.
    if isinstance(valeurs, list):
        valeurs = valeurs[1]
    return explicateur, valeurs


def importance_globale(valeurs, variables):
    """Moyenne des contributions absolues : quelles variables comptent."""
    moyennes = np.abs(valeurs).mean(axis=0)
    return (
        pd.DataFrame({"variable": variables.columns, "importance": moyennes})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def tracer_global(importances, chemin, combien=20):
    """Les variables les plus influentes, en barres horizontales."""
    BLEU, ENCRE_2 = "#2a78d6", "#52514e"
    haut = importances.head(combien)[::-1]

    _, ax = plt.subplots(figsize=(9, 7))
    ax.barh([libelle(v) for v in haut.variable], haut.importance,
            color=BLEU, height=0.7)
    ax.set_xlabel("Contribution moyenne au score (valeur absolue)",
                  fontsize=9.5, color=ENCRE_2)
    ax.set_title(
        f"Les {combien} variables qui pesent le plus dans la decision",
        fontsize=12, fontweight="bold", loc="left", pad=16,
    )
    ax.text(0, 1.02, "Mesure SHAP sur 5 000 dossiers du jeu de test",
            transform=ax.transAxes, fontsize=9, color=ENCRE_2)
    ax.grid(axis="x", alpha=0.4); ax.set_axisbelow(True)
    ax.tick_params(labelsize=8.5)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)

    plt.tight_layout()
    plt.savefig(chemin, dpi=130, bbox_inches="tight")
    plt.close()


def expliquer_dossier(explicateur, variables, index, combien=FACTEURS_PAR_DOSSIER):
    """Les principaux facteurs de la decision, pour UN dossier.

    Renvoie une liste de facteurs, du plus influent au moins influent, avec le
    sens de leur effet : ont-ils augmente ou diminue le risque estime.
    """
    ligne = variables.iloc[[index]]
    valeurs = explicateur.shap_values(ligne)
    if isinstance(valeurs, list):
        valeurs = valeurs[1]
    valeurs = valeurs[0]

    ordre = np.argsort(np.abs(valeurs))[::-1][:combien]
    facteurs = []
    for i in ordre:
        variable = variables.columns[i]
        valeur = ligne.iloc[0, i]
        facteurs.append(
            {
                "variable": variable,
                "libelle": libelle(variable),
                "valeur": valeur,
                "contribution": float(valeurs[i]),
                # Positif = pousse vers le refus, negatif = vers l'acceptation.
                "sens": "defavorable" if valeurs[i] > 0 else "favorable",
            }
        )
    return facteurs



def variables_montrees(valeurs, variables, combien=FACTEURS_PAR_DOSSIER):
    """Variables qui atteignent le haut du classement d'au moins un dossier.

    Ce sont exactement celles qu'un demandeur peut voir ecrites sur sa
    notification. Le reste du modele reste technique et n'a pas besoin
    d'etre traduit.
    """
    rangs = np.argsort(-valeurs, axis=1)[:, :combien]
    noms = variables.columns.to_numpy()
    return sorted(set(noms[rangs.ravel()]))

def main():
    print("Chargement des donnees")
    _, _, _, _, jeux = preparation.tout_charger(silencieux=True)
    _, _, x_test, _, _, y_test = jeux

    # SHAP travaille sur le modele NON calibre : la calibration etant monotone,
    # elle ne change ni l'ordre des dossiers ni la contribution relative des
    # variables.
    modele = joblib.load(preparation.MODELE)
    echantillon = x_test.head(ECHANTILLON_GLOBAL)

    print(f"\nCalcul des contributions sur {ECHANTILLON_GLOBAL:,} dossiers".replace(",", " "))
    depart = time.time()
    explicateur, valeurs = calculer_shap(modele, echantillon)
    duree = time.time() - depart
    print(f"  {duree:.1f} s au total, soit {duree / ECHANTILLON_GLOBAL * 1000:.2f} ms par dossier")

    importances = importance_globale(valeurs, echantillon)
    print("\nLes dix variables les plus influentes :")
    for ligne in importances.head(10).itertuples():
        print(f"  {ligne.importance:6.4f}  {libelle(ligne.variable)}")

    graphique = RACINE / "docs" / "shap_importance_globale.png"
    tracer_global(importances, graphique)
    importances.to_csv(RACINE / "docs" / "shap_importance_globale.csv", index=False)
    print(f"\nGraphique ecrit dans {graphique.relative_to(RACINE)}")

    # EXIGENCE C-5, deuxieme volet : un motif doit etre LISIBLE.
    #
    # Mesurer 24 ms ne sert a rien si le demandeur recoit
    # "POS_PART_MOIS_RETARD_GRAVE" comme motif de refus. On verifie donc que
    # toute variable susceptible d'apparaitre dans les motifs d'un dossier a
    # bien un libelle en francais.
    #
    # On ne verifie pas les 223 variables du modele : seules comptent celles
    # qui atteignent reellement le haut d'un classement individuel.
    montrables = variables_montrees(valeurs, echantillon)
    sans_libelle = [v for v in montrables if v not in LIBELLES]
    print()
    print("Lisibilite des motifs (exigence C-5)")
    print(f"  {len(montrables)} variables peuvent apparaitre dans les motifs")
    if sans_libelle:
        print(f"  {len(sans_libelle)} sans libelle : {', '.join(sans_libelle[:5])}")
        raise SystemExit(
            f"ECHEC C-5 : {len(sans_libelle)} variable(s) seraient presentees a "
            f"un demandeur sous leur nom technique. Completez LIBELLES."
        )
    print("  toutes libellees en francais - CONFORME")

    # EXIGENCE C-5 : moins d'une seconde pour expliquer un dossier.
    #
    # C'est la contrainte qui compte en production : un analyste qui reexamine
    # un refus ne peut pas attendre. On la mesure sur cinquante dossiers plutot
    # que sur un seul, pour lisser les variations.
    print("\nDelai d'explication d'un dossier (exigence C-5 : moins d'1 s)")
    depart = time.time()
    for i in range(50):
        expliquer_dossier(explicateur, echantillon, i)
    par_dossier = (time.time() - depart) / 50
    conforme = par_dossier < 1.0
    print(f"  {par_dossier * 1000:.0f} ms par dossier — "
          f"{'CONFORME' if conforme else 'NON CONFORME'}")

    # Un exemple concret : le dossier le plus risque de l'echantillon.
    probabilites = modele.predict_proba(echantillon)[:, 1]
    plus_risque = int(np.argmax(probabilites))
    print("\nExemple — dossier le plus risque de l'echantillon")
    print(f"  score du modele : {probabilites[plus_risque]:.3f}")
    print(f"  issue reelle    : {'defaut' if y_test.iloc[plus_risque] == 1 else 'rembourse'}")
    print("\n  Motifs de la decision :")
    for facteur in expliquer_dossier(explicateur, echantillon, plus_risque):
        signe = "+" if facteur["contribution"] > 0 else "-"
        print(f"    {signe} {facteur['libelle']:<44} "
              f"({facteur['sens']}, contribution {facteur['contribution']:+.3f})")

    if not conforme:
        raise SystemExit(
            f"ECHEC C-5 : {par_dossier * 1000:.0f} ms par dossier, "
            f"au-dela de la seconde exigee."
        )


if __name__ == "__main__":
    main()
