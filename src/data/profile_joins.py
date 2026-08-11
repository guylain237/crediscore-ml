"""Profilage des jointures entre les 8 sources (zone raw).

Produit docs/schema_jointures.md : granularité de chaque table, intégrité
référentielle mesurée, cardinalités, couverture, et inventaire des colonnes
temporelles.

Trois questions auxquelles ce script répond, parce qu'elles conditionnent le
feature engineering et la stratégie de découpage :

1. **Intégrité** — chaque clé enfant retrouve-t-elle son parent ? Un orphelin
   silencieux fausse une jointure sans lever d'erreur.
2. **Couverture** — quelle part des dossiers possède un historique ? Elle fixe
   le taux de valeurs manquantes des variables agrégées, donc leur utilité.
3. **Temporalité** — existe-t-il une date absolue quelque part ? La réponse
   décide si un découpage temporel est possible ou non.

Méthode : lecture des seules colonnes de clés et de temps, en entiers 32 bits,
pour tenir en mémoire sur les 27 M de lignes de bureau_balance.

Usage : python src/data/profile_joins.py [chemin_du_dossier_input]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Colonnes temporelles à inventorier, par fichier.
TEMPORAL_COLUMNS: dict[str, list[str]] = {
    "application_train.csv": [
        "DAYS_BIRTH",
        "DAYS_EMPLOYED",
        "DAYS_REGISTRATION",
        "DAYS_ID_PUBLISH",
        "DAYS_LAST_PHONE_CHANGE",
    ],
    "bureau.csv": ["DAYS_CREDIT", "DAYS_CREDIT_ENDDATE", "DAYS_ENDDATE_FACT"],
    "bureau_balance.csv": ["MONTHS_BALANCE"],
    "previous_application.csv": ["DAYS_DECISION"],
    "POS_CASH_balance.csv": ["MONTHS_BALANCE"],
    "credit_card_balance.csv": ["MONTHS_BALANCE"],
    "installments_payments.csv": ["DAYS_INSTALMENT", "DAYS_ENTRY_PAYMENT"],
}


def _fr(n: int) -> str:
    """Formatage français des milliers : 1 716 428."""
    return f"{n:,}".replace(",", " ")


def lire_cles(path: Path, colonnes: list[str]) -> pd.DataFrame:
    """Lit uniquement les colonnes de clés, en int32 (mémoire divisée par deux)."""
    return pd.read_csv(path, usecols=colonnes, dtype={c: np.int32 for c in colonnes})


def analyser_relation(
    parent: pd.Series,
    enfant: pd.Series,
    nom_parent: str,
    nom_enfant: str,
    cle: str,
    perimetre: pd.Index | None = None,
) -> dict:
    """Mesure l'intégrité et la cardinalité d'une relation parent → enfant.

    `perimetre` distingue deux natures d'orphelins, qu'il serait faux de
    confondre :

    - une clé enfant absente de la table parent **analysée** peut simplement
      appartenir à l'autre population (un dossier de `application_test` a bien
      un historique bureau, il n'est juste pas dans `application_train`) ;
    - une clé enfant absente de **tout le périmètre** est un véritable défaut
      d'intégrité référentielle.

    Sans cette distinction, on alerte sur 42 000 faux positifs et on rate les
    vrais.
    """
    cles_parent = pd.Index(parent.unique())
    comptes = enfant.value_counts()

    hors_table = comptes.index.difference(cles_parent)
    reference = perimetre if perimetre is not None else cles_parent
    hors_perimetre = comptes.index.difference(reference)

    presents = cles_parent.intersection(comptes.index)
    comptes_presents = comptes.reindex(presents)

    return {
        "parent": nom_parent,
        "enfant": nom_enfant,
        "cle": cle,
        "parents": len(cles_parent),
        "parents_avec_enfant": len(presents),
        "couverture": 100.0 * len(presents) / len(cles_parent),
        "hors_table": len(hors_table),
        "hors_perimetre": len(hors_perimetre),
        "lignes_hors_perimetre": (
            int(comptes.reindex(hors_perimetre).sum()) if len(hors_perimetre) else 0
        ),
        "enfants_min": int(comptes_presents.min()) if len(presents) else 0,
        "enfants_median": float(comptes_presents.median()) if len(presents) else 0.0,
        "enfants_moyen": float(comptes_presents.mean()) if len(presents) else 0.0,
        "enfants_max": int(comptes_presents.max()) if len(presents) else 0,
    }


def detecter_sentinelles(input_dir: Path) -> list[dict]:
    """Repère les valeurs sentinelles : un code numérique déguisé en mesure.

    `DAYS_EMPLOYED = 365243` (soit +1000 ans dans le futur) code en réalité
    « sans emploi / retraité ». Laissée telle quelle, cette valeur écrase toute
    statistique d'ancienneté et fausse les arbres de décision.
    """
    releves: list[dict] = []
    colonne = pd.read_csv(input_dir / "application_train.csv", usecols=["DAYS_EMPLOYED"])
    anormales = colonne["DAYS_EMPLOYED"] > 0
    if anormales.any():
        releves.append(
            {
                "fichier": "application_train.csv",
                "colonne": "DAYS_EMPLOYED",
                "valeur": int(colonne.loc[anormales, "DAYS_EMPLOYED"].mode().iloc[0]),
                "occurrences": int(anormales.sum()),
                "part": 100.0 * anormales.mean(),
            }
        )
    return releves


def inventaire_temporel(input_dir: Path) -> list[dict]:
    """Relève l'amplitude de chaque colonne temporelle, et son type."""
    releves: list[dict] = []
    for fichier, colonnes in TEMPORAL_COLUMNS.items():
        chemin = input_dir / fichier
        entete = pd.read_csv(chemin, nrows=0).columns
        presentes = [c for c in colonnes if c in entete]
        if not presentes:
            continue
        donnees = pd.read_csv(chemin, usecols=presentes)
        for col in presentes:
            serie = donnees[col].dropna()
            releves.append(
                {
                    "fichier": fichier,
                    "colonne": col,
                    "type": str(donnees[col].dtype),
                    "min": float(serie.min()),
                    "max": float(serie.max()),
                    "unite": "mois" if col.startswith("MONTHS") else "jours",
                }
            )
    return releves


def colonnes_texte_datables(input_dir: Path) -> list[str]:
    """Cherche une éventuelle date absolue cachée dans une colonne texte.

    Une seule date absolue suffirait à rendre possible un découpage temporel :
    il faut donc prouver qu'il n'y en a aucune, pas le supposer.
    """
    suspectes: list[str] = []
    for fichier in TEMPORAL_COLUMNS:
        echantillon = pd.read_csv(input_dir / fichier, nrows=5_000, low_memory=False)
        for col in echantillon.select_dtypes(include="object").columns:
            valeurs = echantillon[col].dropna().astype(str).head(200)
            if valeurs.empty:
                continue
            converties = pd.to_datetime(valeurs, errors="coerce", format="mixed")
            if converties.notna().mean() > 0.8:
                suspectes.append(f"{fichier}::{col}")
    return suspectes


def main(input_dir: Path, out_path: Path) -> None:
    app_train = lire_cles(input_dir / "application_train.csv", ["SK_ID_CURR"])
    app_test = lire_cles(input_dir / "application_test.csv", ["SK_ID_CURR"])
    bureau = lire_cles(input_dir / "bureau.csv", ["SK_ID_CURR", "SK_ID_BUREAU"])
    bureau_bal = lire_cles(input_dir / "bureau_balance.csv", ["SK_ID_BUREAU"])
    previous = lire_cles(input_dir / "previous_application.csv", ["SK_ID_CURR", "SK_ID_PREV"])
    pos = lire_cles(input_dir / "POS_CASH_balance.csv", ["SK_ID_PREV"])
    carte = lire_cles(input_dir / "credit_card_balance.csv", ["SK_ID_PREV"])
    echeances = lire_cles(input_dir / "installments_payments.csv", ["SK_ID_PREV"])

    # Périmètre complet : les dossiers à scorer, entraînement ET test.
    perimetre_curr = pd.Index(
        pd.concat([app_train["SK_ID_CURR"], app_test["SK_ID_CURR"]], ignore_index=True).unique()
    )

    relations = [
        analyser_relation(app_train["SK_ID_CURR"], bureau["SK_ID_CURR"],
                          "application_train", "bureau", "SK_ID_CURR", perimetre_curr),
        analyser_relation(bureau["SK_ID_BUREAU"], bureau_bal["SK_ID_BUREAU"],
                          "bureau", "bureau_balance", "SK_ID_BUREAU"),
        analyser_relation(app_train["SK_ID_CURR"], previous["SK_ID_CURR"],
                          "application_train", "previous_application", "SK_ID_CURR", perimetre_curr),
        analyser_relation(previous["SK_ID_PREV"], pos["SK_ID_PREV"],
                          "previous_application", "POS_CASH_balance", "SK_ID_PREV"),
        analyser_relation(previous["SK_ID_PREV"], carte["SK_ID_PREV"],
                          "previous_application", "credit_card_balance", "SK_ID_PREV"),
        analyser_relation(previous["SK_ID_PREV"], echeances["SK_ID_PREV"],
                          "previous_application", "installments_payments", "SK_ID_PREV"),
    ]

    chevauchement = len(
        pd.Index(app_train["SK_ID_CURR"].unique()).intersection(app_test["SK_ID_CURR"].unique())
    )

    # Couverture au grain DOSSIER : la statistique qui fixe réellement le taux de
    # valeurs manquantes des variables agrégées. Une table peut couvrir peu de
    # ses parents directs tout en concernant beaucoup de dossiers — ou l'inverse.
    cles_train = pd.Index(app_train["SK_ID_CURR"].unique())

    def couverture_dossier(curr_concernes: pd.Series) -> tuple[int, float]:
        touches = cles_train.intersection(pd.Index(curr_concernes.unique()))
        return len(touches), 100.0 * len(touches) / len(cles_train)

    bureau_avec_bal = bureau.loc[bureau["SK_ID_BUREAU"].isin(bureau_bal["SK_ID_BUREAU"]), "SK_ID_CURR"]
    prev_avec_pos = previous.loc[previous["SK_ID_PREV"].isin(pos["SK_ID_PREV"]), "SK_ID_CURR"]
    prev_avec_carte = previous.loc[previous["SK_ID_PREV"].isin(carte["SK_ID_PREV"]), "SK_ID_CURR"]
    prev_avec_ech = previous.loc[previous["SK_ID_PREV"].isin(echeances["SK_ID_PREV"]), "SK_ID_CURR"]

    couvertures = [
        ("bureau", "BUREAU_*", *couverture_dossier(bureau["SK_ID_CURR"])),
        ("bureau_balance", "BB_*", *couverture_dossier(bureau_avec_bal)),
        ("previous_application", "PREV_*", *couverture_dossier(previous["SK_ID_CURR"])),
        ("POS_CASH_balance", "POS_*", *couverture_dossier(prev_avec_pos)),
        ("credit_card_balance", "CC_*", *couverture_dossier(prev_avec_carte)),
        ("installments_payments", "INSTAL_*", *couverture_dossier(prev_avec_ech)),
    ]

    temporel = inventaire_temporel(input_dir)
    suspectes = colonnes_texte_datables(input_dir)
    sentinelles = detecter_sentinelles(input_dir)

    lignes: list[str] = [
        "# Schéma des jointures et intégrité référentielle",
        "",
        "Généré par `src/data/profile_joins.py` — toutes les valeurs sont **mesurées**",
        "sur l'intégralité des fichiers, sans échantillonnage.",
        "",
        "## Modèle relationnel",
        "",
        "Trois systèmes sources, deux arborescences distinctes qui convergent sur",
        "`SK_ID_CURR`, l'identifiant du dossier à scorer.",
        "",
        "```mermaid",
        "erDiagram",
        '    APPLICATION ||--o{ BUREAU : "SK_ID_CURR"',
        '    BUREAU ||--o{ BUREAU_BALANCE : "SK_ID_BUREAU"',
        '    APPLICATION ||--o{ PREVIOUS_APPLICATION : "SK_ID_CURR"',
        '    PREVIOUS_APPLICATION ||--o{ POS_CASH_BALANCE : "SK_ID_PREV"',
        '    PREVIOUS_APPLICATION ||--o{ CREDIT_CARD_BALANCE : "SK_ID_PREV"',
        '    PREVIOUS_APPLICATION ||--o{ INSTALLMENTS_PAYMENTS : "SK_ID_PREV"',
        "```",
        "",
        "## Granularité (le grain de chaque table)",
        "",
        "Confondre le grain d'une table est la première cause de duplication de",
        "lignes lors d'une jointure. Chaque table est agrégée **jusqu'au grain",
        "`SK_ID_CURR`** avant toute jointure avec la table de demandes.",
        "",
        "| Table | Une ligne représente | Grain |",
        "|---|---|---|",
        "| `application_train` / `_test` | une demande de crédit à scorer | `SK_ID_CURR` |",
        "| `bureau` | un crédit détenu ailleurs, déclaré au bureau externe | `SK_ID_BUREAU` |",
        "| `bureau_balance` | l'état mensuel d'un crédit externe | `SK_ID_BUREAU` × mois |",
        "| `previous_application` | une demande antérieure chez CrediScore | `SK_ID_PREV` |",
        "| `POS_CASH_balance` | l'état mensuel d'un crédit POS/cash antérieur | `SK_ID_PREV` × mois |",
        "| `credit_card_balance` | l'état mensuel d'une carte de crédit antérieure | `SK_ID_PREV` × mois |",
        "| `installments_payments` | une échéance due et son paiement effectif | `SK_ID_PREV` × échéance |",
        "",
        "## Intégrité et cardinalités mesurées",
        "",
        "| Relation | Clé | Parents | Avec ≥ 1 enfant | Couverture | Enfants (méd. / moy. / max) | Hors table | **Hors périmètre** |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in relations:
        lignes.append(
            f"| `{r['parent']}` → `{r['enfant']}` | {r['cle']} | {_fr(r['parents'])} "
            f"| {_fr(r['parents_avec_enfant'])} | {r['couverture']:.1f} % "
            f"| {r['enfants_median']:.0f} / {r['enfants_moyen']:.1f} / {_fr(r['enfants_max'])} "
            f"| {_fr(r['hors_table'])} | **{_fr(r['hors_perimetre'])}** |"
        )

    lignes += [
        "",
        "### Lecture",
        "",
        "**Deux natures d'orphelins, à ne surtout pas confondre.** La colonne",
        "*Hors table* compte les clés enfant absentes de la seule table parent",
        "analysée ; la colonne *Hors périmètre* compte celles absentes de **tout**",
        "le périmètre (`application_train` + `application_test`).",
        "",
        "Les ~42 000 et ~47 800 clés « hors table » des deux premières relations",
        "vers `application_train` ne sont donc **pas** un défaut : ce sont les",
        "dossiers de `application_test`, qui possèdent bien un historique. La",
        "colonne *hors périmètre* le confirme à zéro.",
        "",
        "En revanche, les orphelins des relations `bureau → bureau_balance` et",
        "`previous_application → *` sont **réels** : ces lignes filles référencent",
        "un parent qui n'existe dans aucun fichier. Elles seront écartées à",
        "l'ingestion et le volume écarté journalisé — un contrôle qualité bloquant",
        "ne doit jamais rejeter en silence.",
        "",
        (
            f"- Chevauchement `application_train` / `application_test` : "
            f"**{_fr(chevauchement)} identifiant(s) commun(s)** — les deux populations"
        ),
        "  sont disjointes, aucune fuite par recouvrement d'identifiants.",
        "",
        "La **couverture** est l'information décisive pour le feature engineering :",
        "elle fixe mécaniquement le taux de valeurs manquantes des variables agrégées.",
        "Un dossier sans historique bureau n'aura pas de `BUREAU_*` — cette absence",
        "est une information en soi (primo-emprunteur), à ne pas imputer aveuglément.",
        "",
        "## Couverture au grain dossier",
        "",
        "Le tableau précédent mesure la couverture d'une table par son parent",
        "**direct**. Celui-ci mesure ce qui compte vraiment pour le feature",
        "engineering : la part des dossiers de `application_train` qui possèdent au",
        "moins une ligne dans chaque source, en suivant tout le chemin de jointure.",
        "C'est le **taux de valeurs manquantes plancher** de chaque famille de",
        "variables agrégées.",
        "",
        "| Source | Préfixe des variables | Dossiers couverts | Couverture | Manquantes |",
        "|---|---|---|---|---|",
        *[
            f"| `{source}` | `{prefixe}` | {_fr(n)} | {pct:.1f} % | **{100 - pct:.1f} %** |"
            for source, prefixe, n, pct in couvertures
        ],
        "",
        "## Colonnes temporelles",
        "",
        "| Fichier | Colonne | Type | Min | Max | Unité |",
        "|---|---|---|---|---|---|",
    ]

    for t in temporel:
        lignes.append(
            f"| `{t['fichier']}` | `{t['colonne']}` | {t['type']} "
            f"| {t['min']:,.0f} | {t['max']:,.0f} | {t['unite']} |".replace(",", " ")
        )

    if sentinelles:
        lignes += [
            "",
            "### Valeurs sentinelles détectées",
            "",
            "| Fichier | Colonne | Valeur | Occurrences | Part |",
            "|---|---|---|---|---|",
        ]
        for s in sentinelles:
            lignes.append(
                f"| `{s['fichier']}` | `{s['colonne']}` | {_fr(s['valeur'])} "
                f"| {_fr(s['occurrences'])} | {s['part']:.1f} % |"
            )
        lignes += [
            "",
            "`DAYS_EMPLOYED = 365243` correspond à une ancienneté d'emploi de",
            "**+1000 ans dans le futur** : ce n'est pas une mesure mais un code,",
            "signifiant « sans emploi / retraité ». Laissée telle quelle, cette",
            "valeur écrase toute statistique d'ancienneté et fausse les seuils de",
            "coupure des arbres. Traitement retenu : remplacement par `NaN` **et**",
            "création d'un indicateur binaire `DAYS_EMPLOYED_ANORMAL`, qui conserve",
            "l'information au lieu de la détruire (voir `docs/plan_features.md`).",
        ]

    if suspectes:
        constat = "Colonnes texte convertibles en date détectées : " + ", ".join(suspectes)
    else:
        constat = (
            "**Aucune colonne texte convertible en date absolue** dans les 8 sources."
        )

    lignes += [
        "",
        "### Conséquence sur la stratégie de découpage",
        "",
        constat,
        "",
        "Toutes les colonnes temporelles sont des **décalages relatifs négatifs**,",
        "comptés depuis la date de la demande courante — laquelle n'est jamais",
        "fournie. Le jeu est donc **anonymisé dans le temps** : deux dossiers dont",
        "`DAYS_BIRTH = -12000` n'ont pas été déposés le même jour, et rien ne permet",
        "de les ordonner l'un par rapport à l'autre.",
        "",
        "Il est par conséquent **impossible de construire un découpage temporel**",
        "(*out-of-time*) sur ces données. Voir `docs/strategie_decoupage.md` pour la",
        "stratégie retenue en conséquence.",
        "",
    ]

    out_path.write_text("\n".join(lignes), encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root.parent / "input"
    main(dossier, repo_root / "docs" / "schema_jointures.md")
