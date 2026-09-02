"""Choisit le seuil de decision par le cout metier, et non par l'accuracy.

Le modele rend une probabilite entre 0 et 1. Il faut en tirer une decision :
accorder ou refuser. C'est le SEUIL qui tranche, et son choix n'est pas une
question technique — c'est une question metier.

Le reflexe serait de prendre 0,5. Ce serait une erreur, parce que les deux
erreurs possibles ne coutent pas la meme chose :

  Un DEFAUT NON DETECTE  -> on prete a quelqu'un qui ne remboursera pas.
                            On perd le capital.  5 000 EUR dans le scenario.

  Un BON CLIENT REFUSE   -> on refuse quelqu'un qui aurait rembourse.
                            On perd une marge.     500 EUR.

Un defaut coute donc dix fois plus cher qu'un refus a tort. Le seuil optimal
sera bien en dessous de 0,5 : mieux vaut refuser plusieurs bons clients que
d'accorder un mauvais.

Ce script balaie tous les seuils possibles, calcule le cout total de chacun, et
retient celui qui minimise la perte.

Usage : python src/models/seuil.py
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

# Seuils testes : de 1 % a 99 %, par pas de 0,5 %.
SEUILS = np.arange(0.01, 0.99, 0.005)

# Largeur de la zone grise : on retient tous les seuils dont le cout total
# depasse le minimum de moins de 2 %. Dans cet intervalle, deplacer le seuil
# ne change presque rien au cout — autrement dit, la machine n'a pas de
# raison forte de trancher dans un sens plutot que dans l'autre. C'est donc
# la que l'analyste doit decider, et non elle.
#
# La zone n'est pas choisie a la main : elle se deduit de la courbe de cout.
TOLERANCE_ZONE_GRISE = 0.02


def calculer_couts(cible, probabilites, cout_faux_negatif, cout_faux_positif):
    """Cout total du portefeuille pour chaque seuil teste."""
    resultats = []
    for seuil in SEUILS:
        accorde = probabilites < seuil

        # Faux negatif : on a accorde, le client fait defaut.
        faux_negatifs = int(((cible == 1) & accorde).sum())
        # Faux positif : on a refuse, le client aurait rembourse.
        faux_positifs = int(((cible == 0) & ~accorde).sum())

        resultats.append(
            {
                "seuil": seuil,
                "cout_total": faux_negatifs * cout_faux_negatif
                + faux_positifs * cout_faux_positif,
                "faux_negatifs": faux_negatifs,
                "faux_positifs": faux_positifs,
                "taux_acceptation": accorde.mean(),
                # Taux de defaut du portefeuille effectivement accorde : c'est
                # l'indicateur que suit la direction des risques.
                "taux_defaut_portefeuille": (
                    cible[accorde].mean() if accorde.sum() else 0.0
                ),
            }
        )
    return pd.DataFrame(resultats)


def tracer(couts, seuil_retenu, chemin):
    """Deux courbes : le cout, et ce que le seuil implique pour le metier."""
    BLEU, ORANGE, CRITIQUE = "#2a78d6", "#eb6834", "#d03b3b"
    ENCRE_2 = "#52514e"

    _, (haut, bas) = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)

    # Le cout total en millions d'euros.
    haut.plot(couts.seuil, couts.cout_total / 1e6, color=BLEU, linewidth=2)
    haut.axvline(seuil_retenu, color=CRITIQUE, linewidth=1.6, linestyle="--")
    minimum = couts.cout_total.min() / 1e6
    haut.plot([seuil_retenu], [minimum], "o", color=CRITIQUE, markersize=9)
    haut.annotate(
        f"seuil retenu : {seuil_retenu:.3f}\ncout minimal : {minimum:.1f} M EUR",
        xy=(seuil_retenu, minimum),
        xytext=(seuil_retenu + 0.12, minimum + (couts.cout_total.max() / 1e6 - minimum) * 0.25),
        fontsize=9.5, color=CRITIQUE, fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": CRITIQUE, "lw": 1.3},
    )
    haut.set_ylabel("Cout total (M EUR)", fontsize=9.5, color=ENCRE_2)
    haut.set_title(
        "Le seuil se choisit par le cout, pas par l'accuracy",
        fontsize=12, fontweight="bold", loc="left", pad=12,
    )
    haut.grid(alpha=0.4); haut.set_axisbelow(True)
    for cote in ("top", "right"):
        haut.spines[cote].set_visible(False)

    # Deux mesures sur la meme unite — des pourcentages — donc un seul axe.
    bas.plot(couts.seuil, couts.taux_acceptation * 100, color=BLEU,
             linewidth=2, label="Demandes acceptees")
    bas.plot(couts.seuil, couts.taux_defaut_portefeuille * 100, color=ORANGE,
             linewidth=2, label="Defauts dans le portefeuille accorde")
    bas.axvline(seuil_retenu, color=CRITIQUE, linewidth=1.6, linestyle="--")
    bas.set_xlabel("Seuil de decision", fontsize=9.5, color=ENCRE_2)
    bas.set_ylabel("Pourcentage", fontsize=9.5, color=ENCRE_2)
    bas.legend(frameon=False, fontsize=9, loc="center right")
    bas.grid(alpha=0.4); bas.set_axisbelow(True)
    for cote in ("top", "right"):
        bas.spines[cote].set_visible(False)

    plt.tight_layout()
    plt.savefig(chemin, dpi=130, bbox_inches="tight")
    plt.close()


def main():
    print("Chargement des donnees")
    config, _, _, _, jeux = preparation.tout_charger()
    _, _, x_test, _, _, y_test = jeux

    # On prefere le modele CALIBRE quand il existe : le seuil doit se calculer
    # sur des probabilites justes. Calcule sur des scores non calibres, il
    # compenserait deux fois le desequilibre — une fois par scale_pos_weight a
    # l'entrainement, une fois par le cout metier — et l'optimum retomberait
    # artificiellement pres de 0,5.
    if preparation.MODELE_CALIBRE.exists():
        modele = joblib.load(preparation.MODELE_CALIBRE)
        print("  modele calibre")
    elif preparation.MODELE.exists():
        modele = joblib.load(preparation.MODELE)
        print("  modele NON calibre — le seuil sera fausse, lancez calibrer.py")
    else:
        raise SystemExit(
            f"Modele introuvable : {preparation.MODELE}. "
            f"Lancez d'abord python src/models/entrainer.py"
        )
    probabilites = modele.predict_proba(x_test)[:, 1]

    cout_fn = config["cout"]["faux_negatif"]
    cout_fp = config["cout"]["faux_positif"]
    print(f"\nCouts retenus : {cout_fn} EUR par defaut, {cout_fp} EUR par refus a tort")
    print(f"  soit un rapport de {cout_fn / cout_fp:.0f} pour 1")

    couts = calculer_couts(y_test.values, probabilites, cout_fn, cout_fp)
    meilleur = couts.loc[couts.cout_total.idxmin()]

    print("\nSeuil retenu")
    print(f"  seuil                      : {meilleur.seuil:.3f}")
    print(f"  cout total                 : {meilleur.cout_total / 1e6:.2f} M EUR")
    print(f"  taux d'acceptation         : {meilleur.taux_acceptation * 100:.1f} %")
    print(f"  defauts dans le portefeuille : {meilleur.taux_defaut_portefeuille * 100:.2f} %")
    print(f"  defauts non detectes       : {int(meilleur.faux_negatifs):,}".replace(",", " "))
    print(f"  bons clients refuses       : {int(meilleur.faux_positifs):,}".replace(",", " "))

    # La zone grise : la ou le modele ne tranche pas assez nettement pour decider seul.
    plancher = couts.cout_total.min() * (1 + TOLERANCE_ZONE_GRISE)
    zone = couts[couts.cout_total <= plancher]
    bas, haut = float(zone.seuil.min()), float(zone.seuil.max())
    dans_zone = (probabilites >= bas) & (probabilites <= haut)

    print()
    print(f"Zone grise (cout a moins de {TOLERANCE_ZONE_GRISE * 100:.0f} % du minimum)")
    print(f"  de {bas:.3f} a {haut:.3f}")
    print(f"  {dans_zone.sum():,} dossiers, soit {dans_zone.mean() * 100:.1f} % du test".replace(",", " "))
    print(f"  taux de defaut reel dans la zone : {y_test.values[dans_zone].mean() * 100:.2f} %")
    print(f"  sous la zone : {y_test.values[probabilites < bas].mean() * 100:.2f} % de defaut")
    print(f"  au-dessus    : {y_test.values[probabilites > haut].mean() * 100:.2f} % de defaut")

    # Comparaison avec le seuil naif, pour mesurer ce que la demarche apporte.
    naif = couts.iloc[(couts.seuil - 0.5).abs().argmin()]
    economie = naif.cout_total - meilleur.cout_total
    print("\nCompare au seuil naif de 0,5")
    print(f"  cout a 0,5                 : {naif.cout_total / 1e6:.2f} M EUR")
    print(f"  taux d'acceptation a 0,5   : {naif.taux_acceptation * 100:.1f} %")
    print(f"  economie                   : {economie / 1e6:.2f} M EUR "
          f"({economie / naif.cout_total * 100:.1f} %)")

    graphique = RACINE / "docs" / "courbe_cout_seuil.png"
    tracer(couts, meilleur.seuil, graphique)
    couts.to_csv(RACINE / "docs" / "courbe_cout_seuil.csv", index=False)
    print(f"\nGraphique ecrit dans {graphique.relative_to(RACINE)}")

    # Le seuil rejoint la configuration : c'est un parametre de decision, il
    # doit vivre avec les autres et non dans la tete de celui qui l'a calcule.
    chemin_seuil = RACINE / "configs" / "seuil_decision.yaml"
    chemin_seuil.write_text(
        "# Seuil de decision, calcule par src/models/seuil.py.\n"
        "# Ne pas modifier a la main : relancer le script apres tout\n"
        "# reentrainement, car le seuil depend du modele.\n"
        f"seuil: {meilleur.seuil:.3f}\n"
        f"calcule_le: {datetime.now(UTC).date().isoformat()}\n"
        f"taux_acceptation: {meilleur.taux_acceptation:.4f}\n"
        f"taux_defaut_portefeuille: {meilleur.taux_defaut_portefeuille:.4f}\n"
        "\n"
        "# Zone grise : en dessous on accorde, au-dessus on refuse, entre les\n"
        "# deux un analyste tranche. Bornes deduites de la courbe de cout :\n"
        "# ce sont les seuils dont le cout depasse le minimum de moins de 2 %.\n"
        f"zone_grise_bas: {bas:.3f}\n"
        f"zone_grise_haut: {haut:.3f}\n"
        f"zone_grise_part_dossiers: {dans_zone.mean():.4f}\n",
        encoding="utf-8",
    )
    print(f"Seuil ecrit dans {chemin_seuil.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
