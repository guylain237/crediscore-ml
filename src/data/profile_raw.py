"""Profilage des 8 fichiers sources bruts (zone raw).

Produit docs/data_profile.md : volumétrie exacte, clés, cible,
et taux de valeurs manquantes estimés sur échantillon.

Méthode :
- comptage de lignes et de clés distinctes par lecture de la seule colonne clé
  (exact, faible mémoire, y compris sur les fichiers de 27 M de lignes) ;
- types et taux de nuls estimés sur les SAMPLE_ROWS premières lignes
  (suffisant pour orienter le feature engineering, signalé dans le rapport).

Usage : python src/data/profile_raw.py [chemin_du_dossier_input]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SAMPLE_ROWS = 200_000

# fichier -> colonne clé principale (granularité de la table)
FILES: dict[str, str] = {
    "application_train.csv": "SK_ID_CURR",
    "application_test.csv": "SK_ID_CURR",
    "bureau.csv": "SK_ID_BUREAU",
    "bureau_balance.csv": "SK_ID_BUREAU",
    "previous_application.csv": "SK_ID_PREV",
    "POS_CASH_balance.csv": "SK_ID_PREV",
    "credit_card_balance.csv": "SK_ID_PREV",
    "installments_payments.csv": "SK_ID_PREV",
}


def profile_file(path: Path, key: str) -> dict:
    keys = pd.read_csv(path, usecols=[key])
    sample = pd.read_csv(path, nrows=SAMPLE_ROWS, low_memory=False)
    null_rates = (sample.isna().mean() * 100).sort_values(ascending=False)
    return {
        "file": path.name,
        "size_mb": path.stat().st_size / 1e6,
        "rows": len(keys),
        "cols": sample.shape[1],
        "key": key,
        "distinct_keys": keys[key].nunique(),
        "null_top": null_rates.head(10),
        "cols_with_nulls": int((null_rates > 0).sum()),
        "sampled": len(keys) > SAMPLE_ROWS,
    }


def main(input_dir: Path, out_path: Path) -> None:
    lines: list[str] = [
        "# Profil des données sources (zone raw)",
        "",
        f"Généré par `src/data/profile_raw.py` — échantillon de {SAMPLE_ROWS:,} lignes".replace(",", " ")
        + " pour les taux de nuls des fichiers volumineux (volumétrie et clés : exactes).",
        "",
        "## Volumétrie et clés",
        "",
        "| Fichier | Taille (Mo) | Lignes | Colonnes | Clé | Clés distinctes | Colonnes avec nuls |",
        "|---|---|---|---|---|---|---|",
    ]
    profiles = []
    for name, key in FILES.items():
        p = profile_file(input_dir / name, key)
        profiles.append(p)
        lines.append(
            f"| {p['file']} | {p['size_mb']:.1f} | {p['rows']:,} | {p['cols']} "
            f"| {p['key']} | {p['distinct_keys']:,} | {p['cols_with_nulls']}/{p['cols']} |".replace(",", " ")
        )

    train = pd.read_csv(input_dir / "application_train.csv", usecols=["TARGET"])
    lines += [
        "",
        "## Cible (application_train)",
        "",
        f"- Taux de défaut (TARGET=1) : **{train['TARGET'].mean() * 100:.2f} %** "
        f"({int(train['TARGET'].sum()):,} défauts sur {len(train):,} dossiers)".replace(",", " "),
        (
            "- Classes fortement déséquilibrées : métriques AUC-PR + coût métier, "
            "pondération `scale_pos_weight` à l'entraînement."
        ),
        "",
        "## Valeurs manquantes — top 10 par fichier",
        "",
    ]
    for p in profiles:
        note = " *(estimé sur échantillon)*" if p["sampled"] else ""
        lines.append(f"### {p['file']}{note}")
        lines.append("")
        lines.append("| Colonne | % nuls |")
        lines.append("|---|---|")
        for col, rate in p["null_top"].items():
            if rate == 0:
                break
            lines.append(f"| {col} | {rate:.1f} |")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root.parent / "input"
    main(input_dir, repo_root / "docs" / "data_profile.md")
