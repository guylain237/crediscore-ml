"""Cherche les variables qui reconstituent un attribut protege (controle C-3).

LE PROBLEME.

Retirer CODE_GENDER et DAYS_BIRTH du modele ne suffit pas. Si une autre
variable permet de deviner le genre ou l'age, le modele peut discriminer sans
jamais avoir vu l'attribut interdit. C'est ce qu'on appelle un PROXY.

L'exemple classique : l'anciennete dans l'emploi. Un demandeur employe depuis
trente ans a forcement plus de cinquante ans. Retirer l'age et garder
DAYS_EMPLOYED, c'est retirer l'age d'une main et le rendre de l'autre.

CE QUE FAIT CE SCRIPT.

Il mesure l'association entre chacune des variables du modele et chacun des
trois attributs proteges. Toute variable au-dessus de 0,50 est declaree
candidate et doit etre instruite a la main : soit elle a une justification
metier autonome et on la garde en l'ecrivant, soit elle n'en a pas et on la
retire.

Le seuil de 0,50 et cette procedure sont fixes dans docs/note_equite.md, §6,
avant d'avoir vu le moindre resultat.

DEUX MESURES, PARCE QUE DEUX RISQUES.

1. La VALEUR de la variable trahit-elle l'attribut protege ?
   Spearman quand les deux sont continus, V de Cramer sinon.

2. Le fait que la variable soit ABSENTE trahit-il l'attribut protege ?
   C'est la regle F5 prise au serieux : une absence n'est pas un zero, c'est
   une information. Si les femmes ont plus souvent une valeur manquante sur
   une variable, le trou lui-meme devient un proxy du genre.

Usage : python src/fairness/proxys.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, spearmanr

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from models import preparation

ATTRIBUTS_SENSIBLES = RACINE.parent / "donnees_pipeline" / "clean" / "attributs_sensibles"

# Seuil fixe dans la note d'equite, §6, avant tout resultat.
SEUIL_PROXY = 0.50

# Au-dela de dix valeurs distinctes, on considere la variable comme continue.
VALEURS_MAX_CATEGORIELLE = 10


def cramers_v(premiere, seconde):
    """Mesure l'association entre deux variables categorielles, de 0 a 1.

    Le test du khi-deux dit s'il y a un lien ; il ne dit pas s'il est fort.
    Sur 300 000 lignes, absolument tout est significatif. Le V de Cramer
    normalise le khi-deux par la taille de l'echantillon : il repond a la
    question qui nous interesse, celle de l'intensite.
    """
    table = pd.crosstab(premiere, seconde)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return 0.0
    khi2 = chi2_contingency(table)[0]
    effectif = table.values.sum()
    plus_petit_cote = min(table.shape) - 1
    return float(np.sqrt((khi2 / effectif) / plus_petit_cote))


def est_continue(serie):
    return pd.api.types.is_numeric_dtype(serie) and serie.nunique() > VALEURS_MAX_CATEGORIELLE


def en_tranches(serie):
    """Prepare une variable pour une table de contingence.

    Les valeurs manquantes deviennent une modalite a part entiere, "absente".
    Les jeter reviendrait a se cacher le cas ou c'est justement l'absence qui
    porte l'information.
    """
    if est_continue(serie):
        serie = pd.qcut(serie, 10, duplicates="drop")
    brute = serie.astype("object")
    return brute.where(brute.notna(), "absente")


def associer(variable, attribut):
    """Mesure l'association entre une variable et un attribut protege."""
    if est_continue(variable) and est_continue(attribut):
        commun = variable.notna() & attribut.notna()
        if commun.sum() < 100:
            return 0.0, "spearman"
        rho = spearmanr(variable[commun], attribut[commun]).statistic
        return abs(float(rho)), "spearman"
    return cramers_v(en_tranches(variable), en_tranches(attribut)), "cramer"


def charger():
    """Joint les variables du modele et les attributs proteges.

    C'est le SEUL endroit du depot ou les deux se rencontrent, et c'est pour
    les auditer. Le module d'entrainement, lui, ne lit jamais ce fichier.
    """
    print("Chargement du socle")
    annotes = preparation.charger_socle()
    variables, _ = preparation.preparer_variables(annotes)

    print("Chargement des attributs proteges (zone clean, usage audit)")
    sensibles = pd.read_parquet(ATTRIBUTS_SENSIBLES)
    sensibles = sensibles.set_index("SK_ID_CURR")

    # On aligne sur les identifiants du socle annote.
    identifiants = annotes["SK_ID_CURR"].values
    sensibles = sensibles.reindex(identifiants)
    sensibles.index = variables.index

    print(f"  {len(sensibles):,} dossiers, {len(variables.columns)} variables a tester"
          .replace(",", " "))
    return variables, sensibles


def mesurer_tout(variables, sensibles):
    """Passe chaque variable devant chaque attribut protege."""
    lignes = []
    for nom_attribut in sensibles.columns:
        attribut = sensibles[nom_attribut]
        print(f"\n  contre {nom_attribut}...", end="", flush=True)

        for nom_variable in variables.columns:
            colonne = variables[nom_variable]

            valeur, methode = associer(colonne, attribut)

            # Deuxieme mesure : le TROU est-il informatif ?
            part_absente = colonne.isna().mean()
            if 0.01 < part_absente < 0.99:
                absence = cramers_v(colonne.isna(), en_tranches(attribut))
            else:
                absence = 0.0

            lignes.append(
                {
                    "variable": nom_variable,
                    "attribut": nom_attribut,
                    "association": valeur,
                    "methode": methode,
                    "association_absence": absence,
                    "part_absente": part_absente,
                }
            )
        print(" fait")

    return pd.DataFrame(lignes)


def main():
    variables, sensibles = charger()
    resultats = mesurer_tout(variables, sensibles)

    resultats = resultats.sort_values("association", ascending=False)

    print("\n" + "=" * 68)
    print("CONTROLE C-3 : les dix associations les plus fortes")
    print("=" * 68)
    print(f"{'variable':<32} {'attribut':<20} {'assoc.':>7}  methode")
    for _, ligne in resultats.head(10).iterrows():
        print(f"{ligne.variable:<32} {ligne.attribut:<20} "
              f"{ligne.association:>7.3f}  {ligne.methode}")

    candidats = resultats[resultats.association > SEUIL_PROXY]
    print(f"\nSeuil d'instruction : {SEUIL_PROXY}")
    if candidats.empty:
        print("Aucune variable ne depasse le seuil. Aucun proxy a instruire.")
    else:
        print(f"{len(candidats)} association(s) au-dessus du seuil, a instruire :")
        for _, ligne in candidats.iterrows():
            print(f"  {ligne.variable} <-> {ligne.attribut} : {ligne.association:.3f}")

    # Le motif d'absence, mesure a part.
    absences = resultats.sort_values("association_absence", ascending=False)
    print("\n" + "=" * 68)
    print("L'ABSENCE COMME PROXY : les cinq motifs de trous les plus revelateurs")
    print("=" * 68)
    print(f"{'variable':<32} {'attribut':<20} {'assoc.':>7}  {'% absent':>8}")
    for _, ligne in absences.head(5).iterrows():
        print(f"{ligne.variable:<32} {ligne.attribut:<20} "
              f"{ligne.association_absence:>7.3f}  {ligne.part_absente * 100:>7.1f} %")

    candidats_absence = absences[absences.association_absence > SEUIL_PROXY]
    if candidats_absence.empty:
        print(f"\nAucun motif d'absence au-dessus de {SEUIL_PROXY}.")
    else:
        print(f"\n{len(candidats_absence)} motif(s) d'absence a instruire.")

    # Les variables que la note designait deja comme a instruire, §6.
    print("\n" + "=" * 68)
    print("LES CAS ANNONCES DANS LA NOTE D'EQUITE, §6")
    print("=" * 68)
    annonces = ["DAYS_EMPLOYED", "DAYS_REGISTRATION", "DAYS_ID_PUBLISH",
                "NAME_INCOME_TYPE", "ORGANIZATION_TYPE"]
    for nom in annonces:
        lignes = resultats[resultats.variable == nom]
        if lignes.empty:
            print(f"  {nom:<22} absent du socle")
            continue
        pire = lignes.loc[lignes.association.idxmax()]
        verdict = "A INSTRUIRE" if pire.association > SEUIL_PROXY else "sous le seuil"
        print(f"  {nom:<22} {pire.association:.3f} avec {pire.attribut:<20} {verdict}")

    chemin = RACINE / "docs" / "resultats_proxys.csv"
    resultats.to_csv(chemin, index=False)
    print(f"\nResultats complets ecrits dans {chemin.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
