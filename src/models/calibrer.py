"""Corrige les probabilites du modele pour qu'elles soient justes.

LE PROBLEME.

Le modele a ete entraine avec scale_pos_weight = 11,39, qui compense le
desequilibre : la classe rare pese autant que la classe majoritaire. Sans cela,
il apprendrait surtout a predire "pas de defaut", vrai dans 92 % des cas et
parfaitement inutile.

Mais ce poids a un effet de bord : le modele apprend comme si les defauts
etaient aussi frequents que les remboursements. Sa sortie n'est donc plus une
probabilite, c'est un score reordonne.

Mesure du 31/08/2026 sur le jeu de test :

  taux de defaut reel         :  8,07 %
  probabilite moyenne predite : 36,71 %   -> 4,5 fois trop elevee

  le modele annonce 49 %  ->  il s'en produit  9,5 %
  le modele annonce 85 %  ->  il s'en produit 39,3 %

LE CLASSEMENT RESTE JUSTE. L'AUC ne depend que de l'ordre des dossiers, et elle
vaut bien 0,7817. C'est la VALEUR affichee qui est fausse.

POURQUOI C'EST BLOQUANT ICI.

Annoncer a un demandeur "votre probabilite de defaut est de 49 %" alors qu'elle
est de 9,5 % n'est pas une imprecision : c'est une information trompeuse dans
une decision qui releve de l'article 22 du RGPD. La strategie de decoupage le
disait deja : une probabilite affichee a un client doit etre juste, pas
seulement bien ordonnee.

LA CORRECTION.

Une regression isotonique apprend, sur le jeu de validation, la correspondance
entre le score du modele et la frequence reelle observee. Elle est MONOTONE :
elle ne change jamais l'ordre des dossiers, donc l'AUC est preservee. Seule
l'echelle est corrigee.

Usage : python src/models/calibrer.py
"""

import sys
from pathlib import Path

import joblib
import matplotlib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import brier_score_loss, roc_auc_score

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

# Tranches de score utilisees pour comparer l'annonce et le reel.
TRANCHES = [0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]


def mesurer_calibration(cible, probabilites):
    """Compare, par tranche de score, ce qui est annonce et ce qui arrive."""
    tranches = pd.cut(probabilites, TRANCHES, include_lowest=True)
    resume = (
        pd.DataFrame({"predit": probabilites, "reel": cible})
        .groupby(tranches, observed=True)
        .agg(dossiers=("reel", "size"), annonce=("predit", "mean"), reel=("reel", "mean"))
    )
    return resume


def tracer(cible, avant, apres, chemin):
    """Courbe de fiabilite : l'annonce en abscisse, le reel en ordonnee.

    Un modele parfaitement calibre suit la diagonale : quand il annonce 20 %,
    il s'en produit 20 %.
    """
    BLEU, ORANGE, ENCRE_2 = "#2a78d6", "#eb6834", "#52514e"

    _, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], color="#8a8880", linewidth=1.2, linestyle="--",
            label="calibration parfaite")

    for probabilites, couleur, libelle in [
        (avant, ORANGE, "avant calibration"),
        (apres, BLEU, "apres calibration"),
    ]:
        resume = mesurer_calibration(cible, probabilites)
        ax.plot(resume.annonce, resume.reel, "o-", color=couleur, linewidth=2,
                markersize=7, label=libelle)

    ax.set_xlabel("Probabilite annoncee par le modele", fontsize=9.5, color=ENCRE_2)
    ax.set_ylabel("Frequence de defaut reellement observee", fontsize=9.5, color=ENCRE_2)
    ax.set_title(
        "Le modele annoncait 4,5 fois trop de defauts",
        fontsize=12, fontweight="bold", loc="left", pad=14,
    )
    ax.text(0, 1.02, "Plus la courbe s'ecarte de la diagonale, plus l'annonce est fausse",
            transform=ax.transAxes, fontsize=9, color=ENCRE_2)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.grid(alpha=0.4); ax.set_axisbelow(True)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)

    plt.tight_layout()
    plt.savefig(chemin, dpi=130, bbox_inches="tight")
    plt.close()


def afficher(titre, cible, probabilites):
    brier = brier_score_loss(cible, probabilites)
    auc = roc_auc_score(cible, probabilites)
    print(f"\n{titre}")
    print(f"  probabilite moyenne : {probabilites.mean() * 100:5.2f} %  "
          f"(reel : {cible.mean() * 100:.2f} %)")
    print(f"  score de Brier      : {brier:.4f}  (plus bas = mieux)")
    print(f"  AUC-ROC             : {auc:.4f}")
    return brier, auc


def main():
    print("Chargement des donnees")
    _, _, _, _, jeux = preparation.tout_charger(silencieux=True)
    _, x_valid, x_test, _, y_valid, y_test = jeux

    if not preparation.MODELE.exists():
        raise SystemExit(
            f"Modele introuvable : {preparation.MODELE}. "
            f"Lancez d'abord python src/models/entrainer.py"
        )
    modele = joblib.load(preparation.MODELE)

    avant = modele.predict_proba(x_test)[:, 1]
    brier_avant, auc_avant = afficher("AVANT calibration", y_test.values, avant)

    # La calibration apprend sur la VALIDATION, jamais sur le test.
    #
    # FrozenEstimator gele le modele : la calibration ne le reentraine pas,
    # elle ajoute seulement une correction d'echelle par-dessus. C'est ce que
    # faisait cv="prefit", retire de scikit-learn depuis la version 1.6.
    print("\nApprentissage de la correction sur le jeu de validation")
    calibre = CalibratedClassifierCV(FrozenEstimator(modele), method="isotonic")
    calibre.fit(x_valid, y_valid)

    apres = calibre.predict_proba(x_test)[:, 1]
    brier_apres, auc_apres = afficher("APRES calibration", y_test.values, apres)

    print("\nCe qui change, et ce qui ne change pas")
    print(f"  score de Brier : {brier_avant:.4f} -> {brier_apres:.4f}  "
          f"({(1 - brier_apres / brier_avant) * 100:.0f} % de mieux)")
    print(f"  AUC-ROC        : {auc_avant:.4f} -> {auc_apres:.4f}  "
          f"(inchangee : la correction est monotone)")

    print("\nAnnonce contre realite, apres correction :")
    resume = mesurer_calibration(y_test.values, apres)
    for tranche, ligne in resume.iterrows():
        print(f"  {tranche!s:<16} {int(ligne.dossiers):>6} dossiers | "
              f"annonce {ligne.annonce * 100:5.1f} % | reel {ligne.reel * 100:5.1f} %")

    graphique = RACINE / "docs" / "courbe_calibration.png"
    tracer(y_test.values, avant, apres, graphique)
    print(f"\nGraphique ecrit dans {graphique.relative_to(RACINE)}")

    joblib.dump(calibre, preparation.MODELE_CALIBRE)
    print(f"Modele calibre ecrit dans {preparation.MODELE_CALIBRE.relative_to(RACINE)}")

    # LIMITE ASSUMEE : le jeu de validation a deja servi a l'arret anticipe de
    # l'entrainement. La calibration apprise dessus est donc legerement
    # optimiste. L'evaluation ci-dessus se fait bien sur le TEST, qui n'a servi
    # a rien d'autre — c'est elle qui fait foi.
    print("\nNote : la correction est apprise sur la validation, mesuree sur le test.")


if __name__ == "__main__":
    main()
