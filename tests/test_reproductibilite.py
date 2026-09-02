"""Verifie qu'un entrainement peut etre rejoue a l'identique (controle C-11).

POURQUOI CE CONTROLE EXISTE.

Devant une contestation, il faut pouvoir refaire tourner le modele qui a rendu
la decision et retrouver le meme resultat. Un modele qu'on ne sait pas rejouer
n'est pas auditable : on ne peut ni verifier ce qu'il a fait, ni corriger ce
qu'il a mal fait.

Trois choses doivent tenir, et ce sont trois choses differentes :

  1. LE DECOUPAGE. La meme graine doit donner les memes trois jeux. Sans cela,
     deux entrainements successifs ne voient pas les memes dossiers et leurs
     scores ne sont pas comparables.

  2. LA GRAINE EST UNE DONNEE, PAS DU CODE. Elle vit dans
     configs/entrainement.yaml. Une graine ecrite en dur dans un script se
     modifie sans laisser de trace dans la configuration.

  3. LES VERSIONS SONT FIGEES. requirements.lock.txt epingle chaque paquet a
     une version exacte. LightGBM ne produit pas le meme arbre d'une version
     mineure a l'autre.

CE QUE CE TEST NE VERIFIE PAS.

Il ne reentraine pas le modele : ce serait plusieurs minutes a chaque `pytest`.
Il verifie que le DECOUPAGE est deterministe, ce qui est la partie fragile.
L'entrainement lui-meme est rendu reproductible par random_state, et son
empreinte est journalisee dans MLflow a chaque execution — c'est la qu'on
verifie apres coup que deux runs ont bien vu les memes dossiers.
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from models import preparation


def empreinte(*jeux):
    """Le meme calcul que src/models/entrainer.py."""
    texte = "|".join(str(sorted(jeu.index.tolist())) for jeu in jeux)
    return hashlib.sha256(texte.encode()).hexdigest()[:16]


def jeu_factice(lignes=2000):
    """Un socle minuscule, suffisant pour tester un decoupage.

    On ne lit pas le vrai socle : il pese plusieurs centaines de Mio et n'est
    pas present en integration continue. Le determinisme du decoupage ne
    depend pas du contenu.
    """
    import numpy as np

    generateur = np.random.default_rng(7)
    return (
        pd.DataFrame(
            {
                "montant": generateur.normal(size=lignes),
                "duree": generateur.integers(0, 60, size=lignes),
            }
        ),
        pd.Series(generateur.integers(0, 2, size=lignes)),
    )


def test_la_graine_vit_dans_la_configuration():
    """Une graine ecrite en dur se change sans laisser de trace."""
    config = preparation.charger_configuration()
    assert "graine" in config, "la graine doit etre dans configs/entrainement.yaml"
    assert isinstance(config["graine"], int)

    # Elle ne doit pas non plus etre dupliquee dans le code : deux valeurs
    # divergeraient sans que personne ne s'en apercoive.
    sources = (RACINE / "src" / "models" / "preparation.py").read_text(encoding="utf-8")
    assert "random_state=graine" in sources, (
        "le decoupage doit utiliser la graine de la configuration, pas un nombre en dur"
    )


def test_le_decoupage_est_deterministe():
    """Deux appels successifs voient exactement les memes dossiers."""
    config = preparation.charger_configuration()
    variables, cible = jeu_factice()

    premier = preparation.decouper(variables, cible, config, silencieux=True)
    second = preparation.decouper(variables, cible, config, silencieux=True)

    assert empreinte(*premier[:3]) == empreinte(*second[:3])


def test_une_autre_graine_donne_un_autre_decoupage():
    """Garde-fou : si l'empreinte ne bougeait jamais, le test precedent ne
    prouverait rien — il passerait meme avec un decoupage constant."""
    config = preparation.charger_configuration()
    variables, cible = jeu_factice()

    attendu = preparation.decouper(variables, cible, config, silencieux=True)
    autre = preparation.decouper(
        variables, cible, {**config, "graine": config["graine"] + 1}, silencieux=True
    )

    assert empreinte(*attendu[:3]) != empreinte(*autre[:3])


def test_les_proportions_sont_respectees():
    """60 / 20 / 20, et la cible est stratifiee de la meme facon partout."""
    config = preparation.charger_configuration()
    variables, cible = jeu_factice(lignes=10_000)
    x_train, x_valid, x_test, y_train, y_valid, y_test = preparation.decouper(
        variables, cible, config, silencieux=True
    )

    total = len(variables)
    assert len(x_test) / total == pytest.approx(config["decoupage"]["part_test"], abs=0.01)
    assert len(x_valid) / total == pytest.approx(
        config["decoupage"]["part_validation"], abs=0.01
    )
    assert len(x_train) + len(x_valid) + len(x_test) == total

    # La stratification : le taux de defaut doit etre le meme dans les trois.
    for jeu in (y_train, y_valid, y_test):
        assert jeu.mean() == pytest.approx(cible.mean(), abs=0.01)


def test_les_versions_sont_figees():
    """requirements.lock.txt doit epingler, pas encadrer.

    LightGBM ne construit pas le meme arbre d'une version mineure a l'autre.
    Un `>=` dans le fichier de verrouillage rendrait le rejeu approximatif.
    """
    verrou = RACINE / "requirements.lock.txt"
    assert verrou.exists(), "requirements.lock.txt absent : aucun rejeu garanti"

    souples = []
    for ligne in verrou.read_text(encoding="utf-8-sig").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if "==" not in ligne:
            souples.append(ligne)

    assert not souples, f"versions non epinglees dans le verrou : {souples[:5]}"


def test_la_configuration_du_modele_est_complete():
    """Tout ce qui change un resultat doit etre dans la configuration."""
    config = preparation.charger_configuration()
    for cle in ("graine", "decoupage", "cout", "lightgbm"):
        assert cle in config, f"'{cle}' absent de configs/entrainement.yaml"

    # Le seuil aussi : il fait partie de la decision, pas du hasard.
    seuil = yaml.safe_load(
        (RACINE / "configs" / "seuil_decision.yaml").read_text(encoding="utf-8")
    )
    for cle in ("seuil", "zone_grise_bas", "zone_grise_haut", "calcule_le"):
        assert cle in seuil, f"'{cle}' absent de configs/seuil_decision.yaml"
