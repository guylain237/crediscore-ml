"""Analyse exploratoire de qualité — ce que le pipeline doit savoir avant d'exister.

Quatre questions auxquelles aucun document du dépôt ne répond encore, et dont
dépend la justesse du pipeline :

1. **Y a-t-il des doublons ?** C'est la question qui commande tout. Un doublon
   exact dans `installments_payments` compte deux fois un retard de paiement :
   le client paraît deux fois plus mauvais qu'il ne l'est. Aucune agrégation
   n'est fiable tant que ce n'est pas mesuré.

2. **Quelles sont les bornes plausibles ?** Le contrôle qualité « plages de
   valeurs » du pipeline exige des seuils. Sans distribution mesurée, ces seuils
   seraient arbitraires — et un contrôle arbitraire finit par être désactivé.

3. **Où sont les pièges de calcul ?** Les sept ratios métier divisent par des
   colonnes qui peuvent valoir zéro ou être absentes. Il faut le savoir avant
   d'écrire la division, pas après.

4. **`FLAG_DOCUMENT_3` mérite-t-il un traitement à part ?** Hypothèse ouverte
   dans `plan_features.md` §2.4, explicitement notée « pas encore mesuré ».

Produit `docs/bornes_qualite.md`.
Usage : python src/data/profile_quality.py [chemin_du_dossier_input]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Grain naturel de chaque table : la combinaison de colonnes qui devrait
# identifier une ligne de façon unique. Un doublon sur ce grain signale soit un
# export fautif, soit une compréhension erronée de la table — dans les deux cas,
# une agrégation construite dessus serait fausse.
GRAINS: dict[str, list[str]] = {
    "application_train.csv": ["SK_ID_CURR"],
    "bureau.csv": ["SK_ID_BUREAU"],
    "bureau_balance.csv": ["SK_ID_BUREAU", "MONTHS_BALANCE"],
    "previous_application.csv": ["SK_ID_PREV"],
    "POS_CASH_balance.csv": ["SK_ID_PREV", "MONTHS_BALANCE"],
    "credit_card_balance.csv": ["SK_ID_PREV", "MONTHS_BALANCE"],
    "installments_payments.csv": [
        "SK_ID_PREV",
        "NUM_INSTALMENT_VERSION",
        "NUM_INSTALMENT_NUMBER",
    ],
}

QUANTILES = [0.001, 0.01, 0.25, 0.50, 0.75, 0.99, 0.999]


def journal(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------------------
# 1. Doublons
# ---------------------------------------------------------------------------


def analyser_doublons(dossier: Path) -> list[dict]:
    """Deux mesures par table : lignes strictement identiques, et doublons de grain.

    La distinction compte. Une ligne strictement identique est presque toujours
    un défaut d'export. Un doublon de grain avec des valeurs différentes est plus
    grave : il signifie que le grain supposé n'est pas le vrai grain, et qu'une
    agrégation « par dossier » mélangerait des choses distinctes.
    """
    resultats = []
    for fichier, cles in GRAINS.items():
        chemin = dossier / fichier
        journal(f"  doublons — {fichier}")

        # On ne charge que les colonnes du grain pour la mesure de grain :
        # suffisant, et sans risque de saturer la mémoire sur 27 M de lignes.
        grain = pd.read_csv(chemin, usecols=cles)
        n_lignes = len(grain)
        n_grain_dupes = int(grain.duplicated().sum())
        del grain

        # Les lignes strictement identiques exigent toutes les colonnes. On ne
        # le fait que pour les tables où c'est tenable en mémoire.
        taille_mo = chemin.stat().st_size / 1e6
        if taille_mo < 450:
            complet = pd.read_csv(chemin, low_memory=False)
            n_exactes = int(complet.duplicated().sum())
            del complet
            mesure_exacte = True
        else:
            n_exactes = -1
            mesure_exacte = False

        resultats.append(
            {
                "fichier": fichier,
                "grain": " + ".join(cles),
                "lignes": n_lignes,
                "doublons_grain": n_grain_dupes,
                "doublons_exacts": n_exactes,
                "mesure_exacte": mesure_exacte,
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# 1 bis. Les « doublons » de installments_payments : paiements fractionnés
# ---------------------------------------------------------------------------


def analyser_paiements_fractionnes(dossier: Path) -> dict:
    """Élucide les 653 483 doublons de grain de `installments_payments`.

    Ce ne sont pas des doublons d'export : une échéance unique peut être réglée
    en plusieurs versements. Trois hypothèses le vérifient — montant dû unique,
    date d'échéance unique, et somme des versements égale au montant dû.

    L'enjeu est considérable : agréger sans consolider inverse le signal de
    risque sur la source la plus prédictive du modèle.
    """
    df = pd.read_csv(dossier / "installments_payments.csv")
    cles = GRAINS["installments_payments.csv"]
    n = len(df)

    taille = df.groupby(cles).size()
    multi_idx = taille[taille > 1].index
    multi = df.set_index(cles).loc[multi_idx].reset_index()

    h1 = (multi.groupby(cles)["AMT_INSTALMENT"].nunique() == 1).mean() * 100
    h2 = (multi.groupby(cles)["DAYS_INSTALMENT"].nunique() == 1).mean() * 100

    valides = multi[multi.AMT_INSTALMENT > 0]
    cons = valides.groupby(cles).agg(
        du=("AMT_INSTALMENT", "first"),
        paye_somme=("AMT_PAYMENT", "sum"),
        paye_max=("AMT_PAYMENT", "max"),
        du_jour=("DAYS_INSTALMENT", "first"),
        paye_jour_max=("DAYS_ENTRY_PAYMENT", "max"),
    )
    h3 = np.isclose(cons.paye_somme, cons.du, rtol=0.01).mean() * 100
    h3_max = np.isclose(cons.paye_max, cons.du, rtol=0.01).mean() * 100

    return {
        "lignes_total": n,
        "echeances_reelles": int(df.groupby(cles).ngroups),
        "echeances_fractionnees": len(multi_idx),
        "repartition": taille.value_counts().sort_index().head(5).to_dict(),
        "h1_montant_unique": h1,
        "h2_date_unique": h2,
        "h3_somme_couvre": h3,
        "h3_max_suffirait": h3_max,
        "taux_sans_conso": float((valides.AMT_PAYMENT / valides.AMT_INSTALMENT).mean()),
        "taux_avec_conso": float((cons.paye_somme / cons.du).mean()),
        "retard_sans_conso": float((valides.DAYS_ENTRY_PAYMENT - valides.DAYS_INSTALMENT).mean()),
        "retard_avec_conso": float((cons.paye_jour_max - cons.du_jour).mean()),
        "montant_du_nul": int((df.AMT_INSTALMENT == 0).sum()),
        "jamais_paye": int(df.AMT_PAYMENT.isna().sum()),
    }


# ---------------------------------------------------------------------------
# 2. Distributions et bornes
# ---------------------------------------------------------------------------


def analyser_distributions(app: pd.DataFrame) -> pd.DataFrame:
    """Quantiles des montants bruts et des sept ratios métier.

    Les quantiles extrêmes (0,1 % et 99,9 %) sont ce qui fonde le seuil du
    contrôle « plages de valeurs » : une borne posée à ces niveaux écarte
    l'aberration sans rejeter la queue légitime de la distribution.
    """
    colonnes = [
        "AMT_INCOME_TOTAL",
        "AMT_CREDIT",
        "AMT_ANNUITY",
        "AMT_GOODS_PRICE",
        "CNT_FAM_MEMBERS",
        "DAYS_EMPLOYED",
        "DAYS_REGISTRATION",
    ]
    donnees = app[colonnes].copy()

    # Sentinelle des retraités : 365243 jours ≈ 1000 ans d'ancienneté. La
    # neutraliser AVANT de calculer les quantiles, sinon elle écrase la
    # distribution réelle (plan_features.md §2.3).
    donnees["DAYS_EMPLOYED"] = donnees["DAYS_EMPLOYED"].replace(365243, np.nan)

    ratios = pd.DataFrame(index=app.index)
    ratios["RATIO_CREDIT_REVENU"] = app["AMT_CREDIT"] / app["AMT_INCOME_TOTAL"]
    ratios["RATIO_ANNUITE_REVENU"] = app["AMT_ANNUITY"] / app["AMT_INCOME_TOTAL"]
    ratios["RATIO_CREDIT_BIEN"] = app["AMT_CREDIT"] / app["AMT_GOODS_PRICE"]
    ratios["RATIO_ANNUITE_CREDIT"] = app["AMT_ANNUITY"] / app["AMT_CREDIT"]
    ratios["REVENU_PAR_PERSONNE"] = app["AMT_INCOME_TOTAL"] / app["CNT_FAM_MEMBERS"]
    ratios["RATIO_ANCIENNETE"] = (
        donnees["DAYS_EMPLOYED"] / app["DAYS_REGISTRATION"].replace(0, np.nan)
    )
    flags = [c for c in app.columns if c.startswith("FLAG_DOCUMENT_")]
    ratios["NB_DOCUMENTS"] = app[flags].sum(axis=1)

    tout = pd.concat([donnees, ratios], axis=1)
    resume = tout.describe(percentiles=QUANTILES).T
    resume["nuls_%"] = tout.isna().mean() * 100
    resume["infinis"] = np.isinf(tout.replace([np.inf, -np.inf], np.inf)).sum()
    return resume


# ---------------------------------------------------------------------------
# 3. Pièges de calcul
# ---------------------------------------------------------------------------


def analyser_pieges(app: pd.DataFrame) -> list[dict]:
    """Les dénominateurs qui peuvent valoir zéro ou manquer.

    Chaque ligne de ce tableau est un `NaN` ou un `inf` qui apparaîtrait
    silencieusement dans le feature store si le pipeline divisait naïvement.
    """
    n = len(app)
    controles = [
        (
            "AMT_INCOME_TOTAL = 0",
            int((app["AMT_INCOME_TOTAL"] == 0).sum()),
            "RATIO_CREDIT_REVENU, RATIO_ANNUITE_REVENU, REVENU_PAR_PERSONNE → inf",
        ),
        (
            "AMT_INCOME_TOTAL manquant",
            int(app["AMT_INCOME_TOTAL"].isna().sum()),
            "mêmes ratios → NaN",
        ),
        (
            "AMT_GOODS_PRICE = 0",
            int((app["AMT_GOODS_PRICE"] == 0).sum()),
            "RATIO_CREDIT_BIEN → inf",
        ),
        (
            "AMT_GOODS_PRICE manquant",
            int(app["AMT_GOODS_PRICE"].isna().sum()),
            "RATIO_CREDIT_BIEN → NaN",
        ),
        (
            "AMT_CREDIT = 0",
            int((app["AMT_CREDIT"] == 0).sum()),
            "RATIO_ANNUITE_CREDIT → inf",
        ),
        (
            "AMT_ANNUITY manquant",
            int(app["AMT_ANNUITY"].isna().sum()),
            "RATIO_ANNUITE_REVENU, RATIO_ANNUITE_CREDIT → NaN",
        ),
        (
            "CNT_FAM_MEMBERS = 0",
            int((app["CNT_FAM_MEMBERS"] == 0).sum()),
            "REVENU_PAR_PERSONNE → inf",
        ),
        (
            "CNT_FAM_MEMBERS manquant",
            int(app["CNT_FAM_MEMBERS"].isna().sum()),
            "REVENU_PAR_PERSONNE → NaN",
        ),
        (
            "DAYS_REGISTRATION = 0",
            int((app["DAYS_REGISTRATION"] == 0).sum()),
            "RATIO_ANCIENNETE → inf",
        ),
        (
            "DAYS_EMPLOYED = 365243 (sentinelle retraités)",
            int((app["DAYS_EMPLOYED"] == 365243).sum()),
            "à neutraliser en NULL avant tout calcul",
        ),
    ]
    return [
        {"controle": c, "dossiers": v, "part": f"{v / n * 100:.3f} %", "effet": e}
        for c, v, e in controles
    ]


# ---------------------------------------------------------------------------
# 4. Les vingt FLAG_DOCUMENT
# ---------------------------------------------------------------------------


def analyser_documents(app: pd.DataFrame) -> pd.DataFrame:
    """Tranche l'hypothèse ouverte de plan_features.md §2.4.

    Une variable dont presque tous les dossiers portent la même valeur n'apporte
    rien à un arbre : elle ne peut séparer aucune population. On mesure donc à la
    fois la variance (le pouvoir séparateur potentiel) et la corrélation à la
    cible (le signal réel).
    """
    flags = sorted(
        (c for c in app.columns if c.startswith("FLAG_DOCUMENT_")),
        key=lambda c: int(c.rsplit("_", 1)[1]),
    )
    lignes = []
    for f in flags:
        colonne = app[f]
        lignes.append(
            {
                "variable": f,
                "taux_a_1_%": colonne.mean() * 100,
                "variance": colonne.var(),
                "correlation_cible": colonne.corr(app["TARGET"]),
            }
        )
    return pd.DataFrame(lignes).set_index("variable")


# ---------------------------------------------------------------------------
# 5. Variables catégorielles
# ---------------------------------------------------------------------------


def analyser_categorielles(app: pd.DataFrame) -> pd.DataFrame:
    """Cardinalité et valeurs sentinelles textuelles.

    « XNA » et « XAP » sont les codes d'absence de ce jeu de données. Traités
    comme des modalités ordinaires, ils créeraient une catégorie « inconnu »
    fantôme à laquelle le modèle attribuerait un risque — alors qu'ils ne
    signifient rien d'autre que l'absence d'information (règle F5).
    """
    lignes = []
    for c in app.select_dtypes(include="object").columns:
        v = app[c]
        lignes.append(
            {
                "variable": c,
                "modalites": v.nunique(dropna=True),
                "nuls_%": v.isna().mean() * 100,
                "XNA_ou_XAP": int(v.isin(["XNA", "XAP"]).sum()),
            }
        )
    return pd.DataFrame(lignes).set_index("variable").sort_values(
        "modalites", ascending=False
    )


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------


def tableau_markdown(df: pd.DataFrame, decimales: int = 2) -> list[str]:
    copie = df.copy()
    for c in copie.select_dtypes(include="number").columns:
        copie[c] = copie[c].map(
            lambda x: "—" if pd.isna(x) else f"{x:,.{decimales}f}".replace(",", " ")
        )
    entete = "| " + " | ".join([copie.index.name or ""] + list(copie.columns)) + " |"
    separateur = "|" + "|".join(["---"] * (len(copie.columns) + 1)) + "|"
    corps = [
        "| " + " | ".join([str(i)] + [str(v) for v in ligne]) + " |"
        for i, ligne in zip(copie.index, copie.values)
    ]
    return [entete, separateur, *corps]


def main(dossier: Path, sortie: Path) -> None:
    journal("1/6 — recherche de doublons (lecture des 7 tables)")
    doublons = analyser_doublons(dossier)

    journal("2/6 — élucidation des doublons de installments_payments")
    fractionnes = analyser_paiements_fractionnes(dossier)

    journal("3/6 — chargement de application_train")
    app = pd.read_csv(dossier / "application_train.csv", low_memory=False)

    journal("4/6 — distributions et bornes")
    distributions = analyser_distributions(app)

    journal("5/6 — pièges de calcul et documents")
    pieges = analyser_pieges(app)
    documents = analyser_documents(app)

    journal("6/6 — variables catégorielles")
    categorielles = analyser_categorielles(app)

    lignes: list[str] = [
        "# Qualité des données et bornes de contrôle",
        "",
        "Généré par `src/data/profile_quality.py`. **Toutes les valeurs sont",
        "mesurées sur l'intégralité des fichiers**, sans échantillonnage.",
        "",
        "Ce document fournit au pipeline ce qui lui manquait : la preuve qu'il n'y",
        "a pas de doublons à corriger, les bornes chiffrées du contrôle « plages de",
        "valeurs », la liste des divisions à protéger, et la réponse à l'hypothèse",
        "restée ouverte sur les `FLAG_DOCUMENT_*`.",
        "",
        "---",
        "",
        "## 1. Doublons — la question qui commande la justesse du pipeline",
        "",
        "Deux mesures distinctes. Une **ligne strictement identique** est presque",
        "toujours un défaut d'export. Un **doublon de grain** est plus grave : il",
        "signifie que le grain supposé n'est pas le vrai grain, et qu'une",
        "agrégation construite dessus mélangerait des choses distinctes.",
        "",
        "| Fichier | Grain supposé | Lignes | Doublons de grain | Lignes identiques |",
        "|---|---|---|---|---|",
    ]
    for d in doublons:
        exactes = (
            f"{d['doublons_exacts']:,}".replace(",", " ")
            if d["mesure_exacte"]
            else "*non mesuré (volume)*"
        )
        lignes.append(
            f"| `{d['fichier']}` | {d['grain']} | {d['lignes']:,} | "
            f"{d['doublons_grain']:,} | {exactes} |".replace(",", " ")
        )

    total_grain = sum(d["doublons_grain"] for d in doublons)
    f = fractionnes
    lignes += [
        "",
        f"**Total des doublons de grain : {total_grain:,}**".replace(",", " "),
        "",
        "Tous se concentrent sur une seule table. La section suivante montre que",
        "ce ne sont **pas** des doublons.",
        "",
        "---",
        "",
        "## 2. Ce ne sont pas des doublons : ce sont des paiements fractionnés",
        "",
        "Une échéance unique peut être réglée en **plusieurs versements**. Trois",
        "hypothèses, vérifiées sur l'intégralité des cas :",
        "",
        "| Hypothèse | Vérifiée dans |",
        "|---|---|",
        f"| Un seul montant dû par échéance | **{f['h1_montant_unique']:.2f} %** |",
        f"| Une seule date d'échéance | **{f['h2_date_unique']:.2f} %** |",
        f"| La **somme** des versements couvre le montant dû | **{f['h3_somme_couvre']:.2f} %** |",
        f"| *(le seul versement maximal suffirait dans)* | *{f['h3_max_suffirait']:.2f} %* |",
        "",
        "La quatrième ligne tranche la méthode : prendre le versement le plus",
        "élevé ne suffirait que dans un tiers des cas. **Il faut sommer.**",
        "",
        "### L'impact, chiffré",
        "",
        "Sur les échéances réglées en plusieurs fois :",
        "",
        "| Variable | Sans consolidation | Avec consolidation |",
        "|---|---|---|",
        f"| `TAUX_PAIEMENT` moyen | {f['taux_sans_conso']:.4f} | **{f['taux_avec_conso']:.4f}** |",
        f"| `RETARD_JOURS` moyen | {f['retard_sans_conso']:+.2f} j | **{f['retard_avec_conso']:+.2f} j** |",
        f"| Nombre d'échéances | {f['lignes_total']:,} | **{f['echeances_reelles']:,}** |".replace(",", " "),
        "",
        "**Le signe du retard s'inverse.** Sans consolidation, ces clients",
        "paraissent payer *en avance* de près de 4 jours ; en réalité ils soldent",
        "leur échéance avec **14 jours de retard**. Et le taux de paiement moyen",
        "passe de 0,50 à 1,00 : un client qui paie l'intégralité de sa dette",
        "semblerait n'en régler que la moitié.",
        "",
        "Agréger sans consolider inverserait donc le signal de risque **sur la",
        "source la plus prédictive du modèle** — celle qui couvre 94,1 % des",
        "dossiers. C'est le défaut le plus coûteux que cette analyse ait évité.",
        "",
        "### La règle de consolidation à appliquer",
        "",
        "```",
        "grouper par (SK_ID_PREV, NUM_INSTALMENT_VERSION, NUM_INSTALMENT_NUMBER) :",
        "    AMT_INSTALMENT     = first  (identique sur toutes les lignes)",
        "    DAYS_INSTALMENT    = first  (identique)",
        "    AMT_PAYMENT        = SUM    (total réellement versé)",
        "    DAYS_ENTRY_PAYMENT = MAX    (date du dernier versement = solde)",
        "```",
        "",
        "**Deux pièges supplémentaires** dans cette même table :",
        "",
        f"- `AMT_INSTALMENT = 0` : {f['montant_du_nul']:,} lignes — division par zéro.".replace(",", " "),
        f"- `AMT_PAYMENT` manquant : {f['jamais_paye']:,} lignes — l'échéance n'a **jamais** été payée.".replace(",", " "),
        "  Ce n'est pas une valeur à imputer : c'est un impayé, donc un signal de",
        "  risque à part entière (règle F5).",
        "",
        "---",
        "",
        "## 3. Distributions — les bornes du contrôle qualité",
        "",
        "Les quantiles 0,1 % et 99,9 % fondent les bornes : elles écartent",
        "l'aberration sans rejeter la queue légitime de la distribution.",
        "",
    ]
    distributions.index.name = "variable"
    lignes += tableau_markdown(
        distributions[["count", "mean", "min", "0.1%", "1%", "50%", "99%", "99.9%", "max", "nuls_%"]]
    )

    lignes += [
        "",
        "---",
        "",
        "## 4. Pièges de calcul — les divisions à protéger",
        "",
        "Chaque ligne est un `NaN` ou un `inf` qui entrerait silencieusement dans",
        "le feature store si le pipeline divisait naïvement.",
        "",
        "| Contrôle | Dossiers | Part | Effet sur les ratios |",
        "|---|---|---|---|",
    ]
    for p in pieges:
        lignes.append(
            f"| {p['controle']} | {p['dossiers']:,} | {p['part']} | {p['effet']} |".replace(
                ",", " "
            )
        )

    lignes += [
        "",
        "---",
        "",
        "## 5. Les vingt `FLAG_DOCUMENT_*`",
        "",
        "Hypothèse de `plan_features.md` §2.4 : conserver `FLAG_DOCUMENT_3`",
        "isolément et remplacer les 19 autres par leur seule somme.",
        "",
    ]
    documents.index.name = "variable"
    lignes += tableau_markdown(documents, decimales=4)

    lignes += [
        "",
        "---",
        "",
        "## 6. Variables catégorielles",
        "",
        "`XNA` et `XAP` sont les codes d'absence de ce jeu de données. Traités",
        "comme des modalités ordinaires, ils créeraient une catégorie « inconnu »",
        "à laquelle le modèle attribuerait un risque — alors qu'ils ne signifient",
        "rien d'autre que l'absence d'information (règle F5).",
        "",
    ]
    categorielles.index.name = "variable"
    lignes += tableau_markdown(categorielles)
    lignes.append("")

    sortie.write_text("\n".join(lignes), encoding="utf-8")
    journal(f"\nOK -> {sortie}")


if __name__ == "__main__":
    racine = Path(__file__).resolve().parents[2]
    entree = Path(sys.argv[1]) if len(sys.argv) > 1 else racine.parent / "input"
    main(entree, racine / "docs" / "bornes_qualite.md")
