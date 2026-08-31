"""Contrat d'équité : les variables sensibles n'entrent jamais dans le modèle.

Ce module est le **point d'application technique** de la décision D-003 et du
plan de gouvernance (`docs/gouvernance.md`, politique P-4). Il transforme une
exigence réglementaire — non-discrimination, AI Act art. 10 §2 f) et g) — en
contrôle exécutable, vérifié à chaque exécution des tests.

Le contrat lui-même vit dans `configs/sensitive_features.yaml` : le code ne
décide de rien, il applique.

Limite assumée et documentée : ce contrôle raisonne sur les **noms** de
variables. Il attrape `DAYS_BIRTH`, `DAYS_BIRTH_BINNED` ou `AGE_ANS`, mais il
ne peut pas détecter un proxy nommé autrement — par exemple une variable
construite à partir de l'âge sous un nom neutre. La détection des proxys relève
de l'audit d'équité par corrélation avec les attributs protégés
(`docs/note_equite.md`, contrôle C-3), pas de ce module.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

RACINE_DEPOT = Path(__file__).resolve().parents[2]
CHEMIN_CONTRAT = RACINE_DEPOT / "configs" / "sensitive_features.yaml"

# Dérivations connues, à interdire même si leur nom ne contient pas celui de la
# variable sensible d'origine. Cette liste s'enrichit à chaque revue d'équité.
DERIVATIONS_CONNUES: dict[str, tuple[str, ...]] = {
    "DAYS_BIRTH": ("AGE", "AGE_ANS", "AGE_ANNEES", "TRANCHE_AGE", "CLASSE_AGE", "YEARS_BIRTH"),
    "CODE_GENDER": ("SEXE", "GENRE", "GENDER", "IS_FEMALE", "IS_MALE"),
    "NAME_FAMILY_STATUS": ("STATUT_FAMILIAL", "SITUATION_FAMILIALE", "EST_MARIE"),
}


class ViolationContratEquite(AssertionError):
    """Levée quand une variable interdite entre dans les features du modèle."""


def charger_contrat(chemin: Path | None = None) -> dict:
    """Charge et valide la structure du contrat d'équité."""
    chemin = chemin or CHEMIN_CONTRAT
    if not chemin.exists():
        raise FileNotFoundError(
            f"Contrat d'équité introuvable : {chemin}. "
            "Sans lui, aucun entraînement n'est autorisé (politique P-4)."
        )
    contrat = yaml.safe_load(chemin.read_text(encoding="utf-8"))

    if not isinstance(contrat, dict) or "sensitive_features" not in contrat:
        raise ValueError(f"{chemin} : clé 'sensitive_features' absente ou fichier malformé.")
    if not contrat["sensitive_features"]:
        raise ValueError(f"{chemin} : la liste des variables sensibles est vide.")
    return contrat


def variables_interdites(chemin: Path | None = None) -> set[str]:
    """Les variables qui ne doivent jamais servir de variable prédictive."""
    return {str(v).strip().upper() for v in charger_contrat(chemin)["sensitive_features"]}


def _motif_violation(feature: str, interdite: str) -> str | None:
    """Renvoie la raison si `feature` viole l'interdiction de `interdite`."""
    nom = feature.strip().upper()

    if nom == interdite:
        return "variable sensible utilisée directement"
    if interdite in nom:
        return f"variable dérivée de {interdite} (nom dérivé)"
    for derivation in DERIVATIONS_CONNUES.get(interdite, ()):
        if nom == derivation or nom.startswith(f"{derivation}_") or nom.endswith(f"_{derivation}"):
            return f"variable dérivée de {interdite} (dérivation connue : {derivation})"
    return None


def variables_exceptees(chemin: Path | None = None) -> dict[str, str]:
    """Variables examinees et explicitement autorisees, avec leur motif.

    Le controle detecte les derivations par le nom, ce qui produit des faux
    positifs : OWN_CAR_AGE est l'age d'une voiture, pas d'une personne. Plutot
    que d'affaiblir la detection, on garde le filet large et on documente les
    exceptions une par une.

    Une exception sans motif ecrit n'est pas acceptee : ce serait rouvrir la
    porte que le controle ferme.
    """
    contrat = charger_contrat(chemin)
    accordees = {}
    for exception in contrat.get("exceptions", []) or []:
        variable = exception.get("variable", "").strip().upper()
        motif = (exception.get("motif") or "").strip()
        if not variable or not motif:
            raise ValueError(
                f"Exception mal formee dans le contrat : {exception}. "
                "Chaque exception exige une variable ET un motif ecrit."
            )
        accordees[variable] = motif
    return accordees


def verifier(features: Iterable[str], chemin: Path | None = None) -> list[tuple[str, str]]:
    """Retourne la liste des violations, sous forme (variable, motif).

    Une liste vide signifie que le jeu de features respecte le contrat.
    """
    interdites = variables_interdites(chemin)
    exceptees = variables_exceptees(chemin)
    violations: list[tuple[str, str]] = []
    for feature in features:
        for interdite in sorted(interdites):
            motif = _motif_violation(feature, interdite)
            if motif:
                if feature.strip().upper() in exceptees:
                    # Une exception accordee ne passe jamais en silence.
                    print(
                        f"  exception appliquee : {feature} — "
                        f"{exceptees[feature.strip().upper()][:70]}"
                    )
                    break
                violations.append((feature, motif))
                break
    return violations


def exiger_conformite(features: Iterable[str], chemin: Path | None = None) -> None:
    """Interrompt l'exécution si une variable interdite est présente.

    À appeler **avant tout `fit`**, dans le script d'entraînement : le contrôle
    doit bloquer la production du modèle, pas seulement la signaler.
    """
    violations = verifier(features, chemin)
    if violations:
        detail = "\n".join(f"  - {nom} : {motif}" for nom, motif in violations)
        raise ViolationContratEquite(
            "Contrat d'équité violé — entraînement interrompu (politique P-4, D-003).\n"
            f"{detail}\n"
            "Retirez ces variables, ou faites évoluer configs/sensitive_features.yaml "
            "après passage en comité d'équité (docs/note_equite.md)."
        )
