"""Mesure ce que couterait le retrait des proxys d'age.

POURQUOI CE SCRIPT EXISTE.

L'audit C-4 a bloque le deploiement : 32 points d'ecart d'acceptation entre les
demandeurs solvables de 20-30 ans et ceux de 60-70 ans, alors que le modele n'a
jamais vu l'age. C-3 avait designe les coupables presumes.

La reaction naturelle serait de retirer ces variables. Mais retirer une
variable a un cout : le modele predit moins bien, donc refuse a tort des gens
qui auraient rembourse — y compris des jeunes. Une correction d'equite qui
degrade la prediction peut nuire au groupe qu'elle pretend proteger.

Ce script ne suppose rien. Il reentraine le modele sans les proxys et mesure,
pour chaque scenario, ce qu'on perd en prediction et ce qu'on gagne en equite.

Usage : python src/fairness/ablation.py
"""

import sys
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import roc_auc_score

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation
from models import seuil as module_seuil

ATTRIBUTS_SENSIBLES = RACINE.parent / "donnees_pipeline" / "clean" / "attributs_sensibles"
TRANCHES_AGE = [20, 30, 40, 50, 60, 70]

# Les proxys designes par C-3, par ordre de gravite mesuree.
PROXYS_FRANCS = [
    "DAYS_EMPLOYED_ANORMAL",   # 0,751 avec l'age
    "FLAG_EMP_PHONE",          # 0,751 — identique a la precedente
    "EXT_SOURCE_1",            # 0,600 avec l'age, 3e variable du modele
]

# Celles dont ce n'est pas la valeur mais l'ABSENCE qui trahit l'age.
PROXYS_PAR_ABSENCE = [
    "DAYS_EMPLOYED",           # trou = 0,751 avec l'age
    "RATIO_ANCIENNETE",        # derivee de la precedente, meme trou
    "OCCUPATION_TYPE",         # trou = 0,527 avec l'age
]

SCENARIOS = {
    "reference": [],
    "sans proxys francs": PROXYS_FRANCS,
    "sans proxys francs et absences": PROXYS_FRANCS + PROXYS_PAR_ABSENCE,
}


def entrainer_et_calibrer(x_train, y_train, x_valid, y_valid, config):
    """Meme recette que src/models/entrainer.py, puis calibration isotonique."""
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
    calibre = CalibratedClassifierCV(FrozenEstimator(modele), method="isotonic")
    calibre.fit(x_valid, y_valid)
    return calibre


def mesurer_ecart_age(probabilites, cible, tranches, seuil):
    """Ecart d'egalite des chances (M-1) sur l'axe de l'age."""
    jeu = pd.DataFrame(
        {"cible": cible, "accorde": probabilites < seuil, "tranche": tranches}
    )
    bons = jeu[jeu.cible == 0]
    taux = bons.groupby("tranche", observed=True).accorde.mean()
    return float(taux.max() - taux.min()), taux


def main():
    print("Chargement des donnees")
    config, annotes, variables, _, jeux = preparation.tout_charger(silencieux=True)
    x_train, x_valid, x_test, y_train, y_valid, y_test = jeux

    sensibles = pd.read_parquet(ATTRIBUTS_SENSIBLES).set_index("SK_ID_CURR")
    ages = sensibles.reindex(annotes.loc[x_test.index, "SK_ID_CURR"].values)["age_annees"]
    tranches = pd.cut(ages.values, TRANCHES_AGE)

    cout_fn = config["cout"]["faux_negatif"]
    cout_fp = config["cout"]["faux_positif"]

    resultats = []
    for nom, a_retirer in SCENARIOS.items():
        presentes = [v for v in a_retirer if v in variables.columns]
        manquantes = [v for v in a_retirer if v not in variables.columns]
        if manquantes:
            print(f"\nAttention : {manquantes} absentes du socle, ignorees")

        print(f"\n--- {nom} ({len(variables.columns) - len(presentes)} variables) ---")
        modele = entrainer_et_calibrer(
            x_train.drop(columns=presentes), y_train,
            x_valid.drop(columns=presentes), y_valid,
            config,
        )
        probabilites = modele.predict_proba(x_test.drop(columns=presentes))[:, 1]

        # Le seuil se recalcule : il depend du modele, on ne le fige pas.
        couts = module_seuil.calculer_couts(y_test.values, probabilites, cout_fn, cout_fp)
        meilleur = couts.loc[couts.cout_total.idxmin()]

        auc = roc_auc_score(y_test, probabilites)
        ecart, taux = mesurer_ecart_age(probabilites, y_test.values, tranches, meilleur.seuil)

        print(f"  AUC-ROC          : {auc:.4f}")
        print(f"  seuil optimal    : {meilleur.seuil:.3f}")
        print(f"  cout total       : {meilleur.cout_total / 1e6:.2f} M EUR")
        print(f"  M-1 sur l'age    : {ecart:.4f}")
        print("  acceptation des solvables par tranche :")
        for intervalle, valeur in taux.items():
            print(f"    {intervalle!s:<12} {valeur * 100:5.1f} %")

        resultats.append(
            {
                "scenario": nom,
                "variables": len(variables.columns) - len(presentes),
                "auc": auc,
                "seuil": meilleur.seuil,
                "cout_millions": meilleur.cout_total / 1e6,
                "m1_age": ecart,
            }
        )

    tableau = pd.DataFrame(resultats)
    reference = tableau.iloc[0]

    print("\n" + "=" * 76)
    print("CE QUE COUTE CHAQUE CORRECTION")
    print("=" * 76)
    print(f"{'scenario':<32} {'var.':>5} {'AUC':>7} {'M-1 age':>8} "
          f"{'cout M EUR':>11} {'AUC perdue':>11}")
    for _, ligne in tableau.iterrows():
        perte = reference.auc - ligne.auc
        print(f"{ligne.scenario:<32} {int(ligne.variables):>5} {ligne.auc:>7.4f} "
              f"{ligne.m1_age:>8.4f} {ligne.cout_millions:>11.2f} {perte:>11.4f}")

    print("\nRappel : le seuil d'arret de M-1 est 0,05.")
    conformes = tableau[tableau.m1_age <= 0.05]
    if conformes.empty:
        print("Aucun scenario ne ramene M-1 sous le seuil d'arret.")
        print("Le retrait de variables ne suffit donc pas : l'ecart ne vient pas")
        print("d'un proxy isole mais d'une difference reelle de taux de defaut")
        print("entre les tranches d'age. La correction doit etre organisationnelle,")
        print("pas seulement technique.")
    else:
        print(f"Scenario(s) conforme(s) : {', '.join(conformes.scenario)}")

    chemin = RACINE / "docs" / "resultats_ablation.csv"
    tableau.to_csv(chemin, index=False)
    print(f"\nResultats ecrits dans {chemin.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
