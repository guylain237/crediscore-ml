"""Mesure l'equite du modele sur chaque sous-population (controle C-4).

CE QUE MESURE CE SCRIPT.

Un proxy detecte par C-3 signale un RISQUE. Il ne dit pas s'il y a un
PREJUDICE. C'est ce script qui repond a la seconde question : a decision egale,
le modele traite-t-il les groupes de la meme facon ?

Les six metriques et leurs seuils sont figes dans docs/note_equite.md, §4, le
16/08/2026 — avant l'entrainement du modele. Les fixer apres aurait permis de
les choisir pour qu'ils passent.

  M-1  egalite des chances    : parmi les gens qui remboursent, en accepte-t-on
                                autant dans chaque groupe ?
  M-2  odds egalisees         : la meme question, en ajoutant les defaillants.
  M-3  calibration par groupe : quand le modele annonce 8 %, s'en produit-il 8 %
                                dans chaque groupe ?
  M-4  impact disproportionne : rapport des taux d'acceptation.
  M-5  parite demographique   : ecart brut des taux d'acceptation.
  M-6  ecart d'AUC            : le modele classe-t-il aussi bien partout ?

M-1, M-2 et M-3 sont PRINCIPALES : franchir leur seuil d'arret interdit le
deploiement, et ce script s'arrete alors en erreur. M-4, M-5 et M-6 sont de
surveillance : elles declenchent une analyse, pas un blocage.

POURQUOI PAS LA PARITE DEMOGRAPHIQUE COMME METRIQUE PRINCIPALE.

Exiger le meme taux d'acceptation partout supposerait que le risque reel est
identique partout, ce qui est faux et invérifiable. L'egalite des chances est
plus juste : elle exige qu'a solvabilite egale, on soit accepte pareil.

Usage : python src/fairness/audit.py
"""

import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import roc_auc_score

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

ATTRIBUTS_SENSIBLES = RACINE.parent / "donnees_pipeline" / "clean" / "attributs_sensibles"

# En dessous de cet effectif, un ecart n'est plus qu'un bruit d'echantillonnage.
# Le groupe est alors affiche, mais exclu du calcul des metriques.
EFFECTIF_MINIMUM = 500

TRANCHES_AGE = [20, 30, 40, 50, 60, 70]

# Seuils figes le 16/08/2026 dans docs/note_equite.md, §4.
SEUILS = {
    "M-1": {"libelle": "Ecart d'egalite des chances", "vigilance": 0.03, "arret": 0.05, "principale": True},
    "M-2": {"libelle": "Ecart d'odds egalisees", "vigilance": 0.05, "arret": 0.08, "principale": True},
    "M-3": {"libelle": "Ecart de calibration", "vigilance": 0.015, "arret": 0.025, "principale": True},
    "M-4": {"libelle": "Rapport d'impact disproportionne", "vigilance": 0.90, "arret": 0.80, "principale": False},
    "M-5": {"libelle": "Ecart de parite demographique", "vigilance": 0.10, "arret": None, "principale": False},
    "M-6": {"libelle": "Ecart d'AUC entre groupes", "vigilance": 0.03, "arret": 0.05, "principale": False},
}

# M-4 se lit a l'envers des autres : plus le rapport est BAS, pire c'est.
SENS_INVERSE = {"M-4"}


def charger():
    """Reconstitue le jeu de test, ses probabilites et ses attributs proteges."""
    print("Chargement des donnees")
    _, annotes, _, _, jeux = preparation.tout_charger(silencieux=True)
    _, _, x_test, _, _, y_test = jeux

    if not preparation.MODELE_CALIBRE.exists():
        raise SystemExit(
            "Modele calibre introuvable. L'audit doit porter sur les probabilites "
            "reellement servies. Lancez d'abord python src/models/calibrer.py"
        )
    modele = joblib.load(preparation.MODELE_CALIBRE)
    probabilites = modele.predict_proba(x_test)[:, 1]

    config_seuil = yaml.safe_load(
        (RACINE / "configs" / "seuil_decision.yaml").read_text(encoding="utf-8")
    )
    seuil = config_seuil["seuil"]

    sensibles = pd.read_parquet(ATTRIBUTS_SENSIBLES).set_index("SK_ID_CURR")
    identifiants = annotes.loc[x_test.index, "SK_ID_CURR"]
    sensibles = sensibles.reindex(identifiants.values)
    sensibles.index = x_test.index

    jeu = pd.DataFrame(
        {
            "cible": y_test.values,
            "probabilite": probabilites,
            # La decision reellement rendue : on accorde sous le seuil.
            "accorde": probabilites < seuil,
            "genre": sensibles["genre"].values,
            "situation_familiale": sensibles["situation_familiale"].values,
        },
        index=x_test.index,
    )
    jeu["tranche_age"] = pd.cut(sensibles["age_annees"].values, TRANCHES_AGE)

    print(f"  {len(jeu):,} dossiers de test".replace(",", " "))
    print(f"  seuil de decision applique : {seuil}")
    print(f"  taux d'acceptation global  : {jeu.accorde.mean() * 100:.1f} %")
    return jeu, seuil


def mesurer_groupe(groupe):
    """Calcule les indicateurs bruts d'un seul groupe."""
    bons = groupe[groupe.cible == 0]
    defaillants = groupe[groupe.cible == 1]

    resultat = {
        "effectif": len(groupe),
        "taux_defaut_reel": groupe.cible.mean(),
        "probabilite_moyenne": groupe.probabilite.mean(),
        "taux_acceptation": groupe.accorde.mean(),
        # Parmi ceux qui auraient rembourse, la part qu'on accepte.
        "tnr": bons.accorde.mean() if len(bons) else np.nan,
        # Parmi ceux qui font defaut, la part qu'on refuse.
        "tpr": (~defaillants.accorde).mean() if len(defaillants) else np.nan,
    }
    resultat["ecart_calibration"] = abs(
        resultat["probabilite_moyenne"] - resultat["taux_defaut_reel"]
    )
    if groupe.cible.nunique() == 2:
        resultat["auc"] = roc_auc_score(groupe.cible, groupe.probabilite)
    else:
        resultat["auc"] = np.nan
    return resultat


def mesurer_axe(jeu, colonne):
    """Mesure tous les groupes d'un axe, puis les six metriques d'ecart."""
    lignes = {}
    for nom, groupe in jeu.groupby(colonne, observed=True):
        lignes[str(nom)] = mesurer_groupe(groupe)
    tableau = pd.DataFrame(lignes).T

    # Les groupes trop petits sont montres mais ne comptent pas.
    retenus = tableau[tableau.effectif >= EFFECTIF_MINIMUM]
    ecartes = tableau[tableau.effectif < EFFECTIF_MINIMUM]

    def etendue(colonne_mesure):
        valeurs = retenus[colonne_mesure].dropna()
        return float(valeurs.max() - valeurs.min()) if len(valeurs) > 1 else 0.0

    metriques = {
        "M-1": etendue("tnr"),
        "M-2": max(etendue("tnr"), etendue("tpr")),
        "M-3": float(retenus.ecart_calibration.max()),
        "M-4": float(retenus.taux_acceptation.min() / retenus.taux_acceptation.max()),
        "M-5": etendue("taux_acceptation"),
        "M-6": etendue("auc"),
    }
    return tableau, retenus, ecartes, metriques


def statut(code, valeur):
    """Traduit une valeur en verdict, selon les seuils figes."""
    regle = SEUILS[code]
    arret, vigilance = regle["arret"], regle["vigilance"]

    if code in SENS_INVERSE:
        if arret is not None and valeur < arret:
            return "ARRET"
        return "vigilance" if valeur < vigilance else "conforme"

    if arret is not None and valeur > arret:
        return "ARRET"
    return "vigilance" if valeur > vigilance else "conforme"


def afficher_axe(titre, tableau, ecartes, metriques):
    print("\n" + "=" * 76)
    print(titre.upper())
    print("=" * 76)
    print(f"{'groupe':<24} {'n':>7} {'defaut':>8} {'annonce':>8} "
          f"{'accepte':>8} {'TNR':>7} {'AUC':>7}")
    for nom, ligne in tableau.iterrows():
        marque = "  (ecarte)" if ligne.effectif < EFFECTIF_MINIMUM else ""
        print(f"{nom:<24} {int(ligne.effectif):>7} "
              f"{ligne.taux_defaut_reel * 100:>7.2f}% {ligne.probabilite_moyenne * 100:>7.2f}% "
              f"{ligne.taux_acceptation * 100:>7.1f}% {ligne.tnr * 100:>6.1f}% "
              f"{ligne.auc:>7.3f}{marque}")

    if not ecartes.empty:
        noms = ", ".join(ecartes.index)
        print(f"\n  Groupes ecartes du calcul (moins de {EFFECTIF_MINIMUM} dossiers) : {noms}")

    print()
    for code, valeur in metriques.items():
        regle = SEUILS[code]
        verdict = statut(code, valeur)
        role = "principale" if regle["principale"] else "surveillance"
        arret = "-" if regle["arret"] is None else f"{regle['arret']:.3f}"
        print(f"  {code}  {regle['libelle']:<36} {valeur:>7.4f}  "
              f"(vigilance {regle['vigilance']:.3f} / arret {arret})  "
              f"{verdict:<10} {role}")


def tracer(mesures, chemin):
    """Une colonne par axe protege : acceptation des solvables, et calibration."""
    BLEU, ORANGE, ENCRE_2 = "#2a78d6", "#eb6834", "#52514e"

    _, axes = plt.subplots(2, len(mesures), figsize=(5.2 * len(mesures), 8))

    for colonne, (titre, tableau) in enumerate(mesures.items()):
        haut, bas = axes[0][colonne], axes[1][colonne]
        noms = list(tableau.index)
        positions = np.arange(len(noms))

        # Haut : le taux d'acceptation des demandeurs solvables (M-1).
        haut.barh(positions, tableau.tnr * 100, color=BLEU, height=0.62)
        moyenne = tableau.tnr.mean() * 100
        haut.axvline(moyenne, color=ENCRE_2, linewidth=1.2, linestyle="--")
        haut.set_yticks(positions); haut.set_yticklabels(noms, fontsize=8.5)
        haut.invert_yaxis()
        haut.set_xlim(0, 100)
        haut.set_xlabel("% des demandeurs solvables acceptes", fontsize=9, color=ENCRE_2)
        haut.set_title(titre, fontsize=11, fontweight="bold", loc="left", pad=10)

        # Bas : ce que le modele annonce contre ce qui arrive (M-3).
        largeur = 0.38
        bas.barh(positions - largeur / 2, tableau.probabilite_moyenne * 100,
                 height=largeur, color=ORANGE, label="annonce par le modele")
        bas.barh(positions + largeur / 2, tableau.taux_defaut_reel * 100,
                 height=largeur, color=BLEU, label="observe reellement")
        bas.set_yticks(positions); bas.set_yticklabels(noms, fontsize=8.5)
        bas.invert_yaxis()
        bas.set_xlabel("Taux de defaut (%)", fontsize=9, color=ENCRE_2)
        if colonne == 0:
            bas.legend(frameon=False, fontsize=8.5, loc="lower right")

        for graphe in (haut, bas):
            graphe.grid(alpha=0.35, axis="x"); graphe.set_axisbelow(True)
            for cote in ("top", "right", "left"):
                graphe.spines[cote].set_visible(False)

    plt.tight_layout()
    plt.savefig(chemin, dpi=130, bbox_inches="tight")
    plt.close()


def main():
    jeu, seuil = charger()

    axes = {
        "Genre": "genre",
        "Tranche d'age": "tranche_age",
        "Situation familiale": "situation_familiale",
    }

    toutes_metriques, pour_graphique, lignes_csv = {}, {}, []

    for titre, colonne in axes.items():
        tableau, retenus, ecartes, metriques = mesurer_axe(jeu, colonne)
        afficher_axe(titre, tableau, ecartes, metriques)
        toutes_metriques[titre] = metriques
        pour_graphique[titre] = retenus
        for nom, ligne in tableau.iterrows():
            lignes_csv.append({"axe": titre, "groupe": nom, **ligne.to_dict()})

    # Verdict global : c'est toujours le pire axe qui decide.
    print("\n" + "=" * 76)
    print("VERDICT — CONTROLE C-4")
    print("=" * 76)

    bloquants = []
    for code in SEUILS:
        pire_axe = max(
            toutes_metriques,
            key=lambda axe: (
                -toutes_metriques[axe][code] if code in SENS_INVERSE
                else toutes_metriques[axe][code]
            ),
        )
        valeur = toutes_metriques[pire_axe][code]
        verdict = statut(code, valeur)
        print(f"  {code}  {SEUILS[code]['libelle']:<36} {valeur:>7.4f}  "
              f"pire axe : {pire_axe:<22} {verdict}")
        if verdict == "ARRET" and SEUILS[code]["principale"]:
            bloquants.append((code, pire_axe, valeur))

    chemin_csv = RACINE / "docs" / "resultats_equite.csv"
    pd.DataFrame(lignes_csv).to_csv(chemin_csv, index=False)
    graphique = RACINE / "docs" / "equite_groupes.png"
    tracer(pour_graphique, graphique)
    print(f"\nTableau ecrit dans {chemin_csv.relative_to(RACINE)}")
    print(f"Graphique ecrit dans {graphique.relative_to(RACINE)}")

    if bloquants:
        print("\nSEUIL D'ARRET FRANCHI SUR UNE METRIQUE PRINCIPALE.")
        for code, axe, valeur in bloquants:
            print(f"  {code} = {valeur:.4f} sur l'axe {axe}")
        raise SystemExit(
            "Deploiement interdit tant que l'ecart n'est pas corrige ou justifie "
            "par le comite d'equite (note d'equite, §4)."
        )

    print(f"\nAucun seuil d'arret franchi. Modele deployable au seuil {seuil}.")


if __name__ == "__main__":
    main()
