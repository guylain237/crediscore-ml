"""Detecte la derive des donnees et declenche un reentrainement (controle C-10).

LE PROBLEME QU'UN MODELE NE SIGNALE JAMAIS TOUT SEUL.

Un modele entraine sur les dossiers de 2024 continue de repondre en 2026. Il ne
dit pas que la population a change, il ne se plaint pas, il ne renvoie aucune
erreur. Il donne des reponses de moins en moins justes, avec la meme assurance.

C'est le risque le plus insidieux du projet, parce que rien ne le rend visible.
Une panne se voit ; une derive, non.

CE QU'ON MESURE.

Deux choses, et la seconde compte plus que la premiere.

  1. La DERIVE DES VARIABLES. Chaque variable d'entree a-t-elle encore la meme
     distribution qu'a l'entrainement ? On compare par tranches.

  2. La DERIVE DU SCORE. La distribution des probabilites sorties du modele
     a-t-elle bouge ? C'est le signal le plus actionnable : une variable peut
     deriver sans consequence si le modele s'en sert peu, alors qu'un
     deplacement du score change directement le taux d'acceptation.

L'INDICE UTILISE : LE PSI.

Population Stability Index. On decoupe la reference en dix tranches d'effectif
egal, on regarde quelle part du lot courant tombe dans chacune, et on somme :

    PSI = somme sur les tranches de  (part_courante - part_reference)
                                     * ln(part_courante / part_reference)

Il vaut 0 si les deux distributions sont identiques, et grandit avec l'ecart.

SEUILS, FIXES AVANT TOUTE MESURE.

  PSI < 0,10          stable
  0,10 a 0,25         vigilance — on regarde
  PSI >= 0,25         derive — reentrainement

Ce sont les seuils usuels du credit scoring. Ils sont ecrits ici avant d'avoir
regarde le moindre resultat, pour la meme raison que les seuils d'equite du
16/08 : un seuil choisi apres coup ne mesure plus rien.

L'ABSENCE EST UNE TRANCHE COMME UNE AUTRE.

Une variable dont le taux de valeurs manquantes passe de 18 % a 60 % a
lourdement derive, meme si les valeurs presentes sont inchangees. Jeter les
manquants avant de comparer masquerait exactement ce cas. La regle F5 vaut ici
aussi : une absence n'est pas un zero, c'est une information.

Usage :

  python src/monitoring/derive.py --construire   fige la reference apres entrainement
  python src/monitoring/derive.py                compare le lot courant a la reference
  python src/monitoring/derive.py --simuler      verifie que l'alarme se declenche
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "src"))
from explain.libelles import libelle
from models import preparation

REFERENCE = RACINE / "models" / "profil_reference.json"

# Seuils fixes avant mesure. Usuels en credit scoring.
PSI_VIGILANCE = 0.10
PSI_DERIVE = 0.25

# Nombre de tranches pour les variables continues.
TRANCHES = 10

# Plancher applique aux parts nulles. Sans lui, une tranche vide dans un des
# deux lots donnerait ln(0) et un PSI infini.
PLANCHER = 1e-4

# Au-dela de dix valeurs distinctes, la variable est traitee comme continue.
VALEURS_MAX_CATEGORIELLE = 10

# Au-dela de cette part, le PSI vient surtout de la tranche des absents : la
# derive est alors imputee a la SOURCE et non a la population.
PART_ABSENTS_COUVERTURE = 0.50

# Regle de declenchement du reentrainement, fixee elle aussi a l'avance.
VARIABLES_EN_DERIVE_TOLEREES = 2


def est_continue(serie):
    return pd.api.types.is_numeric_dtype(serie) and serie.nunique() > VALEURS_MAX_CATEGORIELLE


def parts_continues(serie, bornes):
    """Part du lot dans chaque tranche, plus une tranche pour les absents."""
    presentes = serie.dropna()
    comptes, _ = np.histogram(presentes, bins=bornes)
    comptes = np.append(comptes, serie.isna().sum())
    return comptes / max(len(serie), 1)


def parts_categorielles(serie, modalites):
    """Part de chaque modalite connue, plus 'autre' et 'absente'."""
    valeurs = serie.astype("object")
    comptes = []
    for modalite in modalites:
        comptes.append(int((valeurs == modalite).sum()))
    connues = valeurs.isin(modalites)
    comptes.append(int((~connues & valeurs.notna()).sum()))  # modalites nouvelles
    comptes.append(int(valeurs.isna().sum()))
    return np.array(comptes) / max(len(serie), 1)


def psi(reference, courant):
    """Ecart entre deux distributions, et la part due aux valeurs absentes.

    La derniere tranche est toujours celle des absents. On rend sa
    contribution separement parce qu'elle raconte une histoire differente du
    reste : voir classer_derive().
    """
    reference = np.clip(reference, PLANCHER, None)
    courant = np.clip(courant, PLANCHER, None)
    contributions = (courant - reference) * np.log(courant / reference)
    total = float(np.sum(contributions))
    part_absents = float(contributions[-1] / total) if total > 0 else 0.0
    return total, part_absents


def classer_derive(nom, valeur, part_absents):
    """Distingue une derive de POPULATION d'une derive de COUVERTURE.

    C'est la distinction la plus importante de ce module, et elle manquait a
    la premiere version.

    Une variable peut se deplacer pour deux raisons opposees :

      POPULATION  les demandeurs ont change. Le modele est perime, il faut le
                  reentrainer sur les donnees recentes.

      COUVERTURE  la SOURCE a change : un fichier arrive moins complet, un
                  fournisseur a modifie son perimetre. Les demandeurs, eux,
                  sont les memes.

    Reentrainer sur une derive de couverture serait une FAUTE. On graverait
    dans le modele un defaut d'alimentation passager ; le jour ou la source
    redevient complete, le modele casserait a nouveau, et cette fois sans
    qu'aucune alarme ne sonne puisqu'on aurait appris sur les donnees
    incompletes.

    Le depart se fait sur l'origine du PSI : s'il vient majoritairement de la
    tranche des valeurs absentes, c'est la source qui a bouge, pas les gens.
    """
    if valeur < PSI_VIGILANCE:
        return "stable", "population"
    # Un drapeau *_PRESENT dit litteralement : cette source a-t-elle des
    # donnees pour ce demandeur. Sa derive EST une information de couverture,
    # par construction — il n'a pas de valeur absente ou l'heuristique
    # ci-dessous pourrait la lire, puisque la presence vaut 0 ou 1.
    if nom.endswith("_PRESENT"):
        return ("DERIVE" if valeur >= PSI_DERIVE else "vigilance"), "couverture"

    origine = "couverture" if part_absents > PART_ABSENTS_COUVERTURE else "population"
    etat = "DERIVE" if valeur >= PSI_DERIVE else "vigilance"
    return etat, origine


def construire_reference(variables, probabilites):
    """Fige la distribution de l'entrainement. A relancer apres chaque modele.

    On enregistre les BORNES, pas les donnees. Le profil de reference ne
    contient aucun dossier : il pourrait etre publie sans risque.
    """
    profil = {
        "construit_le": datetime.now(UTC).date().isoformat(),
        "dossiers": len(variables),
        "variables": {},
    }

    for nom in variables.columns:
        colonne = variables[nom]
        if est_continue(colonne):
            # Des tranches d'effectif egal : chacune porte 10 % de la
            # reference. Des tranches de largeur egale mettraient 95 % des
            # dossiers dans la premiere sur les variables tres asymetriques.
            quantiles = np.linspace(0, 1, TRANCHES + 1)
            bornes = np.unique(np.nanquantile(colonne.dropna(), quantiles))
            bornes[0], bornes[-1] = -np.inf, np.inf
            profil["variables"][nom] = {
                "type": "continue",
                "bornes": bornes.tolist(),
                "parts": parts_continues(colonne, bornes).tolist(),
            }
        else:
            modalites = [str(m) for m in colonne.dropna().unique()]
            profil["variables"][nom] = {
                "type": "categorielle",
                "modalites": modalites,
                "parts": parts_categorielles(colonne.astype("object").astype(str).where(
                    colonne.notna()), modalites).tolist(),
            }

    bornes_score = np.unique(np.nanquantile(probabilites, np.linspace(0, 1, TRANCHES + 1)))
    bornes_score[0], bornes_score[-1] = -np.inf, np.inf
    profil["score"] = {
        "bornes": bornes_score.tolist(),
        "parts": parts_continues(pd.Series(probabilites), bornes_score).tolist(),
    }
    return profil


def mesurer(profil, variables, probabilites):
    """Compare un lot courant au profil de reference."""
    lignes = []
    for nom, attendu in profil["variables"].items():
        if nom not in variables.columns:
            continue
        colonne = variables[nom]

        if attendu["type"] == "continue":
            observe = parts_continues(colonne, np.array(attendu["bornes"]))
        else:
            observe = parts_categorielles(
                colonne.astype("object").astype(str).where(colonne.notna()),
                attendu["modalites"],
            )

        valeur, part_absents = psi(np.array(attendu["parts"]), observe)
        etat, origine = classer_derive(nom, valeur, part_absents)

        lignes.append(
            {
                "variable": nom,
                "libelle": libelle(nom),
                "psi": valeur,
                "etat": etat,
                "origine": origine,
                "part_psi_due_aux_absents": part_absents,
                "part_absente_reference": attendu["parts"][-1],
                "part_absente_courante": observe[-1],
            }
        )

    tableau = pd.DataFrame(lignes).sort_values("psi", ascending=False)

    observe_score = parts_continues(pd.Series(probabilites), np.array(profil["score"]["bornes"]))
    psi_score, _ = psi(np.array(profil["score"]["parts"]), observe_score)
    return tableau, psi_score


def verdict(valeur):
    """Etat du score. Le score n'a pas de tranche d'absents : il est toujours
    calculable, donc la distinction population/couverture ne s'y applique pas.
    """
    if valeur >= PSI_DERIVE:
        return "DERIVE"
    if valeur >= PSI_VIGILANCE:
        return "vigilance"
    return "stable"


def charger_lot_courant(simuler=False):
    """Le lot a scorer : les dossiers dont on ne connait pas encore l'issue.

    C'est exactement ce que le pipeline produit chaque jour en production. On
    n'a pas besoin de leur TARGET pour mesurer une derive des entrees — et
    c'est tout l'interet : la derive se detecte AVANT de connaitre les impayes,
    donc avant que la perte soit constatee.
    """
    socle = pd.read_parquet(preparation.SOCLE)
    lot = socle[socle.EST_ANNOTE == 0].copy()
    variables = lot.drop(columns=preparation.NON_VARIABLES)
    variables = variables.drop(
        columns=[c for c in preparation.VARIABLES_RETIREES_C3 if c in variables.columns]
    )

    if simuler:
        # On vieillit artificiellement la population : moins d'anciennete dans
        # l'emploi, mensualites plus lourdes, et un score externe degrade.
        # C'est le genre de bascule qu'une crise economique produirait.
        print("  SIMULATION : population volontairement deformee")
        variables["DAYS_EMPLOYED"] = variables["DAYS_EMPLOYED"] * 0.35
        variables["AMT_ANNUITY"] = variables["AMT_ANNUITY"] * 1.6
        variables["EXT_SOURCE_2"] = variables["EXT_SOURCE_2"] * 0.55

    for colonne in variables.select_dtypes(include="object").columns:
        variables[colonne] = variables[colonne].astype("category")
    return variables


def afficher(tableau, psi_score, profil):
    print()
    print("=" * 74)
    print("CONTROLE C-10 : DERIVE DES DONNEES")
    print("=" * 74)
    print(f"  reference figee le {profil['construit_le']} "
          f"sur {profil['dossiers']:,} dossiers".replace(",", " "))

    print()
    print(f"  PSI DU SCORE : {psi_score:.4f}  -> {verdict(psi_score)}")
    print("  (il resume l\'effet de toutes les variables sur la decision)")

    print()
    print(f"  Les dix variables les plus deplacees, sur {len(tableau)} :")
    print(f"  {'PSI':>7}  {'etat':<10} {'origine':<12} "
          f"{'% absent':>16}  variable")
    for _, ligne in tableau.head(10).iterrows():
        absents = (f"{ligne.part_absente_reference * 100:5.1f} -> "
                   f"{ligne.part_absente_courante * 100:5.1f}")
        print(f"  {ligne.psi:>7.4f}  {ligne.etat:<10} {ligne.origine:<12} "
              f"{absents:>16}  {ligne.libelle}")

    population = tableau[(tableau.etat == "DERIVE") & (tableau.origine == "population")]
    couverture = tableau[(tableau.etat == "DERIVE") & (tableau.origine == "couverture")]
    vigilance = tableau[tableau.etat == "vigilance"]
    stables = tableau[tableau.etat == "stable"]

    print()
    print(f"  {len(population)} variable(s) en derive de POPULATION")
    print(f"  {len(couverture)} variable(s) en derive de COUVERTURE — la source a change")
    print(f"  {len(vigilance)} en vigilance, {len(stables)} stables")

    if not couverture.empty:
        print()
        print("  Ces variables ne signalent PAS un changement de population :")
        print("  leur taux de valeurs absentes a bouge, donc c est l alimentation")
        print("  qui a change. Reentrainer dessus graverait un defaut de source")
        print("  dans le modele.")
        for _, ligne in couverture.head(6).iterrows():
            print(f"    {ligne.variable:<24} absent "
                  f"{ligne.part_absente_reference * 100:.1f} % -> "
                  f"{ligne.part_absente_courante * 100:.1f} %")

    return population, couverture


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--construire", action="store_true",
                           help="fige la reference a partir du jeu d'entrainement")
    analyseur.add_argument("--simuler", action="store_true",
                           help="deforme le lot courant pour verifier que l'alarme sonne")
    arguments = analyseur.parse_args()

    if not preparation.MODELE_CALIBRE.exists():
        raise SystemExit(
            f"Modele calibre introuvable : {preparation.MODELE_CALIBRE}. "
            f"Lancez entrainer.py puis calibrer.py."
        )
    modele = joblib.load(preparation.MODELE_CALIBRE)

    if arguments.construire:
        print("Construction du profil de reference sur le jeu d'entrainement")
        _, _, _, _, jeux = preparation.tout_charger(silencieux=True)
        x_train = jeux[0]
        probabilites = modele.predict_proba(x_train)[:, 1]
        profil = construire_reference(x_train, probabilites)
        REFERENCE.write_text(json.dumps(profil, ensure_ascii=False), encoding="utf-8")
        taille = REFERENCE.stat().st_size / 1024
        print(f"  {len(profil['variables'])} variables profilees sur "
              f"{profil['dossiers']:,} dossiers".replace(",", " "))
        print(f"  ecrit dans {REFERENCE.relative_to(RACINE)} ({taille:.0f} Kio)")
        print("  ce fichier ne contient AUCUN dossier, seulement des bornes")
        return

    if not REFERENCE.exists():
        raise SystemExit(
            f"Profil de reference absent : {REFERENCE}. "
            f"Lancez d'abord python src/monitoring/derive.py --construire"
        )
    profil = json.loads(REFERENCE.read_text(encoding="utf-8"))

    print("Chargement du lot courant")
    variables = charger_lot_courant(simuler=arguments.simuler)
    print(f"  {len(variables):,} dossiers a scorer".replace(",", " "))
    probabilites = modele.predict_proba(variables)[:, 1]

    tableau, psi_score = mesurer(profil, variables, probabilites)
    population, couverture = afficher(tableau, psi_score, profil)

    chemin = RACINE / "docs" / "resultats_derive.csv"
    tableau.to_csv(chemin, index=False)
    print()
    print(f"  Detail complet dans {chemin.relative_to(RACINE)}")

    # Seule la derive de POPULATION declenche un reentrainement. Une derive
    # de couverture appelle une correction d'alimentation, pas un modele neuf.
    reentrainer = (
        psi_score >= PSI_DERIVE
        or len(population) > VARIABLES_EN_DERIVE_TOLEREES
    )

    print()
    print("=" * 74)
    if reentrainer:
        print("REENTRAINEMENT DECLENCHE")
        print("=" * 74)
        if psi_score >= PSI_DERIVE:
            print(f"  motif : le score a derive (PSI {psi_score:.4f} >= {PSI_DERIVE})")
        if len(population) > VARIABLES_EN_DERIVE_TOLEREES:
            print(f"  motif : {len(population)} variables en derive de population, "
                  f"tolerance {VARIABLES_EN_DERIVE_TOLEREES}")
        print()
        print("  Le DAG de surveillance declenche le DAG d entrainement.")
        print("  Le modele reentraine ne remplace PAS l ancien automatiquement :")
        print("  il doit d abord repasser les controles C-1, C-4 et C-5.")
        raise SystemExit(1)

    if not couverture.empty:
        print("ALERTE D ALIMENTATION — PAS DE REENTRAINEMENT")
        print("=" * 74)
        print(f"  {len(couverture)} variable(s) dont la SOURCE a change de perimetre.")
        print("  A traiter par l equipe donnees, pas par un nouveau modele.")
        print(f"  Le score, lui, n a pas bouge : PSI {psi_score:.4f}.")
        raise SystemExit(2)

    print("AUCUNE DERIVE SIGNIFICATIVE")
    print("=" * 74)
    print(f"  PSI du score {psi_score:.4f}, aucune variable en derive de population")
    print("  Le modele reste valide. Prochaine mesure au prochain lot.")


if __name__ == "__main__":
    main()
