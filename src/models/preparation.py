"""Chargement et decoupage des donnees, partages par tous les scripts.

Ces fonctions vivaient dans entrainer.py. Elles sont extraites ici parce que le
calcul du seuil et l'analyse SHAP doivent travailler sur EXACTEMENT le meme
decoupage que l'entrainement.

La graine etant fixee dans configs/entrainement.yaml, rejouer le decoupage
donne toujours les memes trois jeux. On n'a donc pas besoin de sauvegarder les
indices : il suffit de rappeler la meme fonction.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from fairness import contract

# OU LIRE LE SOCLE.
#
# En developpement : le dossier local produit par le pipeline joue sur le
# poste. En production : le data lake, ou le pipeline Spark ecrit vraiment.
#
#   CREDISCORE_SOCLE absent  -> ../donnees_pipeline/curated/socle_complet
#   CREDISCORE_SOCLE definie -> s3://<bucket>/curated/socle_complet
#
# pandas lit les deux de la meme facon, via pyarrow et s3fs. Le code ne
# change pas, seule l'adresse change — comme pour MLFLOW_TRACKING_URI et
# comme pour les zones du data lake cote pipeline. C'est ce qui garantit que
# le modele consomme la sortie du pipeline, et non une copie locale qui
# aurait diverge.

SOCLE = os.environ.get(
    "CREDISCORE_SOCLE",
    str(RACINE.parent / "donnees_pipeline" / "curated" / "socle_complet"),
)
MODELE = RACINE / "models" / "modele.pkl"

# Le modele calibre. Il produit les memes classements que le precedent, mais
# des probabilites justes. C'est celui que l'API doit servir.
MODELE_CALIBRE = RACINE / "models" / "modele_calibre.pkl"

NON_VARIABLES = ["SK_ID_CURR", "TARGET", "EST_ANNOTE"]

# Variables retirees a l'issue de la revue des proxys du 31/08/2026
# (controle C-3, docs/note_equite.md §6). Ce n'est pas une liste technique :
# chaque retrait a ete instruit et motive par ecrit.
#
# FLAG_EMP_PHONE : le demandeur a-t-il fourni un telephone d'employeur.
#   Mesuree identique a DAYS_EMPLOYED_ANORMAL sur 100,00 % des dossiers
#   (55 374 contre 55 374, douze exceptions). Les deux disent la meme chose :
#   ce demandeur n'a pas d'employeur. Garder les deux dedouble le poids de ce
#   signal et eclate arbitrairement son attribution SHAP entre elles.
#   On conserve DAYS_EMPLOYED_ANORMAL, explicite et documentee dans le
#   pipeline, plutot que celle du fournisseur, dont le nom cache le sens.
#
# Les cinq autres proxys detectes par C-3 sont CONSERVES : ils ont une
# justification metier autonome, et l'ablation du 31/08 a mesure que les
# retirer tous ne ramenerait M-1 qu'a 0,2756 — toujours cinq fois au-dessus
# du seuil d'arret. Le cout serait donc paye sans le benefice.
VARIABLES_RETIREES_C3 = ["FLAG_EMP_PHONE"]


def charger_configuration():
    chemin = RACINE / "configs" / "entrainement.yaml"
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def charger_socle(silencieux=False):
    """Lit le socle et ne garde que les dossiers dont on connait l'issue."""
    socle = pd.read_parquet(SOCLE)
    annotes = socle[socle.EST_ANNOTE == 1].copy()
    if not silencieux:
        print(f"  {len(annotes):,} dossiers annotes".replace(",", " "))
        print(f"  taux de defaut : {annotes.TARGET.mean() * 100:.2f} %")
    return annotes


def preparer_variables(donnees, silencieux=False):
    """Separe les variables de la cible, et type les categorielles."""
    cible = donnees["TARGET"].astype(int)
    variables = donnees.drop(columns=NON_VARIABLES)

    retirees = [v for v in VARIABLES_RETIREES_C3 if v in variables.columns]
    if retirees:
        variables = variables.drop(columns=retirees)
        if not silencieux:
            print(f"  revue des proxys C-3 : {', '.join(retirees)} retiree(s)")

    # Controle C-1 : aucune variable sensible ne doit atteindre le modele.
    contract.exiger_conformite(variables.columns)

    for colonne in variables.select_dtypes(include="object").columns:
        variables[colonne] = variables[colonne].astype("category")

    if not silencieux:
        print(f"  {len(variables.columns)} variables, controle C-1 passe")
    return variables, cible


def decouper(variables, cible, config, silencieux=False):
    """Decoupage 60 / 20 / 20, stratifie sur la cible.

    Deterministe : la meme graine donne toujours les memes trois jeux.
    """
    graine = config["graine"]
    part_test = config["decoupage"]["part_test"]
    part_validation = config["decoupage"]["part_validation"]

    x_reste, x_test, y_reste, y_test = train_test_split(
        variables, cible, test_size=part_test, stratify=cible, random_state=graine
    )
    part_relative = part_validation / (1 - part_test)
    x_train, x_valid, y_train, y_valid = train_test_split(
        x_reste, y_reste, test_size=part_relative, stratify=y_reste, random_state=graine
    )

    if not silencieux:
        for nom, y in [("entrainement", y_train), ("validation", y_valid), ("test", y_test)]:
            print(f"  {nom:<13} {len(y):>7,} dossiers".replace(",", " "))

    return x_train, x_valid, x_test, y_train, y_valid, y_test


def tout_charger(silencieux=False):
    """Raccourci : socle, variables, decoupage, en une seule fois."""
    config = charger_configuration()
    annotes = charger_socle(silencieux)
    variables, cible = preparer_variables(annotes, silencieux)
    jeux = decouper(variables, cible, config, silencieux)
    return config, annotes, variables, cible, jeux
