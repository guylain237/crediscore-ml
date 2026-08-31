"""Chiffre le prix de la conformite (decision D-008).

CE MODELE N'EST JAMAIS DEPLOYE. IL N'EST MEME JAMAIS ENREGISTRE.

Exclure le genre, l'age et la situation familiale a un cout de prediction.
Ce cout, on l'a decide sans le connaitre — ce qui etait la bonne facon de
proceder : si on l'avait chiffre d'abord, la tentation aurait ete de le trouver
trop eleve.

Maintenant que la decision est prise et tenue, on peut la chiffrer. Un
arbitrage documente vaut mieux qu'un arbitrage suppose : le comite d'equite
doit savoir ce que sa regle coute, et le jury a le droit de le demander.

CE SCRIPT CONTOURNE VOLONTAIREMENT LE CONTROLE C-1.

C'est le seul endroit du depot ou c'est le cas, et c'est explicite. Le modele
produit reste en memoire, n'est pas ecrit sur disque, et ne sort pas de cette
fonction. Il ne peut donc pas etre servi par erreur.

Usage : python src/fairness/temoin.py
"""

import sys
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

ATTRIBUTS_SENSIBLES = RACINE.parent / "donnees_pipeline" / "clean" / "attributs_sensibles"


def entrainer(x_train, y_train, x_valid, y_valid, config):
    """Meme recette que le modele conforme, aux variables pres."""
    parametres = dict(config["lightgbm"])
    arret = parametres.pop("early_stopping_rounds")
    parametres["scale_pos_weight"] = (y_train == 0).sum() / (y_train == 1).sum()
    parametres["random_state"] = config["graine"]
    parametres["verbose"] = -1

    modele = lgb.LGBMClassifier(**parametres)
    modele.fit(
        x_train, y_train,
        eval_set=[(x_valid, y_valid)],
        eval_metric="average_precision",
        callbacks=[lgb.early_stopping(arret, verbose=False)],
    )
    return modele


def evaluer(modele, x, y):
    probabilites = modele.predict_proba(x)[:, 1]
    return roc_auc_score(y, probabilites), average_precision_score(y, probabilites)


def main():
    print("Chargement des donnees")
    config, annotes, variables, cible, jeux = preparation.tout_charger(silencieux=True)
    x_train, x_valid, x_test, y_train, y_valid, y_test = jeux

    print("\n--- Modele conforme (celui qui est deploye) ---")
    conforme = entrainer(x_train, y_train, x_valid, y_valid, config)
    auc_conforme, pr_conforme = evaluer(conforme, x_test, y_test)
    print(f"  {len(variables.columns)} variables")
    print(f"  AUC-ROC {auc_conforme:.4f}   AUC-PR {pr_conforme:.4f}")

    # On remet les trois attributs proteges. C'est interdit partout ailleurs.
    print("\n--- Modele temoin (avec les attributs proteges) ---")
    sensibles = pd.read_parquet(ATTRIBUTS_SENSIBLES).set_index("SK_ID_CURR")
    sensibles = sensibles.reindex(annotes["SK_ID_CURR"].values)
    sensibles.index = variables.index
    for colonne in ("genre", "situation_familiale"):
        sensibles[colonne] = sensibles[colonne].astype("category")

    enrichies = variables.join(sensibles)
    jeux_temoin = preparation.decouper(
        enrichies, cible, config, silencieux=True
    )
    xt_train, xt_valid, xt_test, yt_train, yt_valid, yt_test = jeux_temoin

    temoin = entrainer(xt_train, yt_train, xt_valid, yt_valid, config)
    auc_temoin, pr_temoin = evaluer(temoin, xt_test, yt_test)
    print(f"  {len(enrichies.columns)} variables (genre, age, situation familiale)")
    print(f"  AUC-ROC {auc_temoin:.4f}   AUC-PR {pr_temoin:.4f}")

    # Ce que le temoin regarde vraiment, parmi ce qu'on lui a interdit ailleurs.
    usages = pd.Series(temoin.feature_importances_, index=enrichies.columns)
    rang = usages.rank(ascending=False)
    print("\n  Place des attributs proteges dans le modele temoin :")
    for colonne in ("age_annees", "genre", "situation_familiale"):
        print(f"    {colonne:<22} {int(usages[colonne]):>5} usages, "
              f"rang {int(rang[colonne])} sur {len(usages)}")

    print("\n" + "=" * 66)
    print("LE PRIX DE LA CONFORMITE (decision D-008)")
    print("=" * 66)
    print(f"  AUC-ROC perdue : {auc_temoin - auc_conforme:.4f} "
          f"({auc_conforme:.4f} contre {auc_temoin:.4f})")
    print(f"  AUC-PR perdue  : {pr_temoin - pr_conforme:.4f} "
          f"({pr_conforme:.4f} contre {pr_temoin:.4f})")
    print("\n  C'est ce que coute le respect de la regle. Le comite d'equite")
    print("  connait desormais ce chiffre, et l'assume.")

    chemin = RACINE / "docs" / "resultats_temoin.csv"
    pd.DataFrame(
        [
            {"modele": "conforme", "variables": len(variables.columns),
             "auc_roc": auc_conforme, "auc_pr": pr_conforme},
            {"modele": "temoin", "variables": len(enrichies.columns),
             "auc_roc": auc_temoin, "auc_pr": pr_temoin},
        ]
    ).to_csv(chemin, index=False)
    print(f"\nResultats ecrits dans {chemin.relative_to(RACINE)}")

    # Le modele temoin meurt ici. Aucun joblib.dump, aucun enregistrement
    # MLflow : il ne doit exister aucun fichier a partir duquel on pourrait le
    # servir par inadvertance.
    print("Le modele temoin n'est pas enregistre. Il disparait avec ce processus.")


if __name__ == "__main__":
    main()
