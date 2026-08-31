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
    "BUREAU_NB_CREDITS": "nombre de credits chez d'autres etablissements",
    "BUREAU_PLAFOND_SUM": "plafonds accordes par d'autres etablissements",
    "PREV_AMT_CREDIT_MEAN": "montant moyen des credits anterieurs",
    "POS_NB_ACTIFS": "credits en cours",
    "CC_SOLDE_MEAN": "solde moyen de la carte de credit",
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
