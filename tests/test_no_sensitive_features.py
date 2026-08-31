"""Garde-fou d'équité : aucune variable sensible ne doit entrer dans le modèle.

Contrôle C-1 du plan de gouvernance (`docs/gouvernance.md`), application de la
décision D-003. Ce test doit rester **bloquant** en intégration continue : son
échec interdit la publication d'un modèle.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.fairness.contract import (
    CHEMIN_CONTRAT,
    ViolationContratEquite,
    charger_contrat,
    exiger_conformite,
    variables_exceptees,
    variables_interdites,
    verifier,
)

RACINE_DEPOT = Path(__file__).resolve().parents[1]
FEATURES_MODELE = RACINE_DEPOT / "configs" / "features_modele.yaml"


# --------------------------------------------------------------------------
# Le contrat lui-même
# --------------------------------------------------------------------------

def test_le_contrat_existe_et_est_valide() -> None:
    contrat = charger_contrat()
    assert contrat["sensitive_features"], "La liste des variables sensibles ne peut pas être vide."


def test_le_contrat_couvre_les_trois_attributs_proteges() -> None:
    """Genre, âge et situation familiale sont les attributs protégés retenus.

    Les retirer du contrat sans passage en comité d'équité doit casser le build.
    """
    attendues = {"CODE_GENDER", "DAYS_BIRTH", "NAME_FAMILY_STATUS"}
    assert attendues.issubset(variables_interdites()), (
        "Le contrat ne couvre plus les trois attributs protégés du projet. "
        "Toute réduction du périmètre passe par le comité d'équité (docs/note_equite.md)."
    )


def test_les_variables_d_audit_restent_disponibles() -> None:
    """Les attributs protégés servent à MESURER l'équité : ils doivent rester lisibles.

    Les interdire comme features n'interdit pas de les conserver pour l'audit —
    sans eux, aucun test de non-discrimination n'est possible.
    """
    contrat = charger_contrat()
    assert contrat.get("audit_only_features"), (
        "Aucune variable d'audit déclarée : les tests d'équité deviendraient impossibles."
    )


# --------------------------------------------------------------------------
# Le mécanisme de détection
# --------------------------------------------------------------------------

def test_detecte_usage_direct() -> None:
    violations = verifier(["EXT_SOURCE_2", "CODE_GENDER", "AMT_CREDIT"])
    assert [nom for nom, _ in violations] == ["CODE_GENDER"]


@pytest.mark.parametrize(
    "feature",
    [
        "DAYS_BIRTH_BINNED",      # nom dérivé
        "AGE",                    # dérivation connue
        "TRANCHE_AGE",            # dérivation connue
        "RATIO_EMPLOI_DAYS_BIRTH",  # ratio construit sur une variable sensible
        "IS_FEMALE",              # dérivation connue du genre
    ],
)
def test_detecte_les_variables_derivees(feature: str) -> None:
    """Une dérivation d'une variable sensible reste une variable sensible.

    C'est la clause explicite du contrat : interdire `DAYS_BIRTH` sans interdire
    `TRANCHE_AGE` ne protégerait personne.
    """
    assert verifier([feature]), f"{feature} aurait dû être refusée."


def test_laisse_passer_un_jeu_conforme() -> None:
    conformes = [
        "EXT_SOURCE_1",
        "EXT_SOURCE_2",
        "AMT_CREDIT",
        "RATIO_ANNUITE_REVENU",
        "DAYS_EMPLOYED",
        "BUREAU_AMT_CREDIT_SUM_DEBT_MEAN",
        "INSTAL_RETARD_JOURS_MAX",
    ]
    assert verifier(conformes) == []


def test_exiger_conformite_interrompt_l_entrainement() -> None:
    """Le contrôle doit BLOQUER, pas seulement signaler."""
    with pytest.raises(ViolationContratEquite):
        exiger_conformite(["AMT_CREDIT", "DAYS_BIRTH"])


# --------------------------------------------------------------------------
# Le jeu de features réellement utilisé par le modèle
# --------------------------------------------------------------------------

@pytest.mark.skipif(
    not FEATURES_MODELE.exists(),
    reason="configs/features_modele.yaml pas encore produit (entraînement prévu le 26/08).",
)
def test_les_features_du_modele_respectent_le_contrat() -> None:
    """Contrôle final : ce que le modèle consomme réellement.

    Les tests précédents valident le mécanisme ; celui-ci valide le résultat.
    Il devient actif dès que l'entraînement publie sa liste de features.
    """
    features = yaml.safe_load(FEATURES_MODELE.read_text(encoding="utf-8"))["features"]
    violations = verifier(features)
    assert not violations, "Variables interdites dans le modèle : " + ", ".join(
        f"{nom} ({motif})" for nom, motif in violations
    )


def test_le_chemin_du_contrat_est_bien_dans_le_depot() -> None:
    assert CHEMIN_CONTRAT.exists(), f"Contrat attendu à {CHEMIN_CONTRAT}"


# ---------------------------------------------------------------------------
# Les exceptions au contrat
# ---------------------------------------------------------------------------
#
# Le mecanisme d'exception est la seule porte de sortie du controle C-1. Il doit
# donc etre lui-meme sous surveillance : sans cela, il suffirait d'y ajouter une
# ligne pour faire passer n'importe quelle variable.


def test_chaque_exception_porte_un_motif_ecrit() -> None:
    """Une exception sans justification n'en est pas une."""
    for variable, motif in variables_exceptees().items():
        assert len(motif) > 40, (
            f"L'exception accordee a {variable} n'est pas justifiee. "
            f"Une derogation au controle C-1 exige un motif ecrit, "
            f"pas une mention."
        )


def test_aucun_attribut_protege_n_est_excepte() -> None:
    """On ne peut pas excepter une variable sensible elle-meme.

    Sans ce test, une ligne d'exception sur CODE_GENDER suffirait a annuler
    toute la politique P-4.
    """
    exceptees = set(variables_exceptees())
    interdites = variables_interdites()
    conflit = exceptees & interdites
    assert not conflit, (
        f"Ces variables sont a la fois interdites et exceptees : {conflit}. "
        f"Une exception ne peut porter que sur un faux positif de detection, "
        f"jamais sur un attribut protege."
    )
