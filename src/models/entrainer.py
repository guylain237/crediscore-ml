"""Entraine le modele de scoring sur le socle produit par le pipeline.

Le socle contient 356 255 dossiers et 227 colonnes. Seuls les 307 511 dossiers
annotes servent a l'entrainement : les autres sont ceux qu'il faudra scorer, et
on ne connait pas leur issue.

Trois choses sont faites dans l'ordre :

  1. Verifier qu'aucune variable sensible n'a survecu jusqu'ici. C'est le
     controle C-1, applique une troisieme fois — apres le pipeline et apres la
     base de donnees. Trois barrieres independantes pour une seule regle.

  2. Decouper en 60 / 20 / 20, aleatoire stratifie sur la cible.

  3. Entrainer LightGBM et tout journaliser dans MLflow.

Usage : python src/models/entrainer.py
"""

import hashlib
import os
import sys
from pathlib import Path

import lightgbm as lgb
import mlflow
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from fairness import contract

# Le socle produit par le pipeline. En local il est dans donnees_pipeline ; sur
# la VM, le meme fichier vit dans le data lake S3.
SOCLE = RACINE.parent / "donnees_pipeline" / "curated" / "socle_complet"

# Colonnes qui ne sont pas des variables : identifiant, cible, et le marqueur
# qui distingue les dossiers annotes de ceux a scorer.
NON_VARIABLES = ["SK_ID_CURR", "TARGET", "EST_ANNOTE"]


def charger_configuration():
    chemin = RACINE / "configs" / "entrainement.yaml"
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def charger_socle():
    """Lit le socle et ne garde que les dossiers dont on connait l'issue."""
    socle = pd.read_parquet(SOCLE)
    print(f"  socle complet : {len(socle):,} dossiers".replace(",", " "))

    annotes = socle[socle.EST_ANNOTE == 1].copy()
    print(f"  dossiers annotes : {len(annotes):,}".replace(",", " "))
    print(f"  taux de defaut : {annotes.TARGET.mean() * 100:.2f} %")
    return annotes


def preparer_variables(donnees):
    """Separe les variables de la cible, et type les categorielles.

    LightGBM sait traiter les variables categorielles nativement, a condition
    qu'elles soient declarees comme telles. C'est preferable a un encodage
    one-hot : celui-ci creerait des centaines de colonnes creuses sur des
    variables comme ORGANIZATION_TYPE, qui compte 58 modalites.
    """
    cible = donnees["TARGET"].astype(int)
    variables = donnees.drop(columns=NON_VARIABLES)

    # CONTROLE C-1, troisieme barriere. Le pipeline a deja devie les attributs
    # sensibles et la base les refuse au registre ; on verifie une derniere fois
    # avant d'entrainer. Une regle qui n'est verifiee qu'une fois n'est verifiee
    # que la ou on y a pense.
    contract.exiger_conformite(variables.columns)
    print(f"  controle C-1 : aucune variable sensible parmi {len(variables.columns)}")

    categorielles = variables.select_dtypes(include="object").columns
    for colonne in categorielles:
        variables[colonne] = variables[colonne].astype("category")
    print(f"  {len(categorielles)} variables categorielles, {len(variables.columns) - len(categorielles)} numeriques")

    return variables, cible


def decouper(variables, cible, config):
    """Decoupage 60 / 20 / 20, stratifie sur la cible."""
    graine = config["graine"]
    part_test = config["decoupage"]["part_test"]
    part_validation = config["decoupage"]["part_validation"]

    # Premier decoupage : on met le jeu de test de cote. Il ne sera utilise
    # qu'une seule fois, tout a la fin. S'en servir pour choisir quoi que ce
    # soit reviendrait a s'auto-evaluer.
    x_reste, x_test, y_reste, y_test = train_test_split(
        variables, cible, test_size=part_test, stratify=cible, random_state=graine
    )

    # Second decoupage : la validation est prelevee sur ce qui reste. La part
    # est recalculee pour que le resultat final soit bien 60/20/20 du total.
    part_relative = part_validation / (1 - part_test)
    x_train, x_valid, y_train, y_valid = train_test_split(
        x_reste, y_reste, test_size=part_relative, stratify=y_reste, random_state=graine
    )

    for nom, y in [("entrainement", y_train), ("validation", y_valid), ("test", y_test)]:
        print(f"  {nom:<13} {len(y):>7,} dossiers, {y.mean() * 100:.2f} % de defauts".replace(",", " "))

    return x_train, x_valid, x_test, y_train, y_valid, y_test


def empreinte_decoupage(x_train, x_valid, x_test):
    """Empreinte des indices des trois jeux.

    Journalisee dans MLflow : elle permet de verifier qu'un entrainement
    ulterieur a bien utilise le meme decoupage, sans avoir a conserver les
    indices eux-memes (strategie_decoupage.md section 5).
    """
    texte = "|".join(
        str(sorted(jeu.index.tolist())) for jeu in (x_train, x_valid, x_test)
    )
    return hashlib.sha256(texte.encode()).hexdigest()[:16]


def entrainer(x_train, y_train, x_valid, y_valid, config):
    """Entraine LightGBM avec arret anticipe sur la validation."""
    parametres = dict(config["lightgbm"])
    arret = parametres.pop("early_stopping_rounds")

    # Compense le desequilibre : la classe rare pese autant que la classe
    # majoritaire dans la fonction de perte. Sans cela, le modele apprendrait
    # surtout a predire "pas de defaut", ce qui est vrai dans 92 % des cas et
    # parfaitement inutile.
    poids = (y_train == 0).sum() / (y_train == 1).sum()
    parametres["scale_pos_weight"] = poids
    parametres["random_state"] = config["graine"]
    parametres["verbose"] = -1
    print(f"  scale_pos_weight : {poids:.2f}")

    modele = lgb.LGBMClassifier(**parametres)
    modele.fit(
        x_train,
        y_train,
        eval_set=[(x_valid, y_valid)],
        eval_metric="average_precision",
        callbacks=[lgb.early_stopping(arret, verbose=False), lgb.log_evaluation(200)],
    )
    print(f"  arret a {modele.best_iteration_} arbres sur {parametres['n_estimators']} possibles")
    return modele


def evaluer(modele, variables, cible, nom):
    """AUC-PR et AUC-ROC, dans cet ordre d'importance."""
    probabilites = modele.predict_proba(variables)[:, 1]
    auc_pr = average_precision_score(cible, probabilites)
    auc_roc = roc_auc_score(cible, probabilites)
    print(f"  {nom:<12} AUC-PR {auc_pr:.4f}   AUC-ROC {auc_roc:.4f}")
    return {"auc_pr": auc_pr, "auc_roc": auc_roc}, probabilites


def main():
    config = charger_configuration()

    print("Chargement du socle")
    annotes = charger_socle()

    print("\nPreparation des variables")
    variables, cible = preparer_variables(annotes)

    print("\nDecoupage 60 / 20 / 20")
    x_train, x_valid, x_test, y_train, y_valid, y_test = decouper(variables, cible, config)
    empreinte = empreinte_decoupage(x_train, x_valid, x_test)
    print(f"  empreinte du decoupage : {empreinte}")

    # Suivi des experiences.
    #
    # En local : une base SQLite dans le depot. Le stockage fichier de MLflow
    # est deprecie et refuse desormais de demarrer.
    #
    # Sur la VM : la variable MLFLOW_TRACKING_URI pointe vers le serveur MLflow
    # de la pile, dont les metadonnees vivent dans PostgreSQL et les artefacts
    # dans le data lake. Meme code des deux cotes, seule l'adresse change —
    # comme pour les zones du data lake.
    suivi = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{RACINE / 'mlflow.db'}")
    mlflow.set_tracking_uri(suivi)
    mlflow.set_experiment("crediscore-scoring")
    print(f"  suivi des experiences : {suivi}")

    with mlflow.start_run(run_name="lightgbm-socle-complet"):
        print("\nEntrainement")
        modele = entrainer(x_train, y_train, x_valid, y_valid, config)

        print("\nEvaluation")
        scores_valid, _ = evaluer(modele, x_valid, y_valid, "validation")
        scores_test, _ = evaluer(modele, x_test, y_test, "test")

        # Tout ce qui permet de rejouer l'experience est journalise : les
        # parametres, la graine, l'empreinte du decoupage, et les scores.
        mlflow.log_params(config["lightgbm"])
        mlflow.log_param("graine", config["graine"])
        mlflow.log_param("nb_variables", len(variables.columns))
        mlflow.log_param("empreinte_decoupage", empreinte)
        mlflow.log_param("arbres_retenus", modele.best_iteration_)
        for jeu, scores in [("valid", scores_valid), ("test", scores_test)]:
            for nom, valeur in scores.items():
                mlflow.log_metric(f"{jeu}_{nom}", valeur)

        mlflow.lightgbm.log_model(modele, name="modele")

        # Les vingt variables les plus utilisees par le modele. Un premier
        # regard avant l'analyse SHAP, qui viendra ensuite.
        importances = pd.DataFrame(
            {"variable": variables.columns, "importance": modele.feature_importances_}
        ).sort_values("importance", ascending=False)
        chemin = RACINE / "docs" / "importances_modele.csv"
        importances.to_csv(chemin, index=False)
        mlflow.log_artifact(str(chemin))

        print("\nLes dix variables les plus utilisees :")
        for ligne in importances.head(10).itertuples():
            print(f"  {ligne.variable:<34} {ligne.importance:>6}")

    objectif = config["objectif_auc_roc"]
    atteint = scores_test["auc_roc"] >= objectif
    print(f"\nObjectif AUC-ROC >= {objectif} : {'ATTEINT' if atteint else 'NON ATTEINT'} "
          f"({scores_test['auc_roc']:.4f})")


if __name__ == "__main__":
    main()
