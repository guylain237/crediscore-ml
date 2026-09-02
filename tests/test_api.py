"""Verifie que l'API rend des decisions tracables (controles C-2, C-5, C-12).

Ces tests ne verifient pas que le modele est bon — c'est le travail de
l'evaluation. Ils verifient que le SERVICE respecte ses obligations :

  - il refuse de rendre une decision qu'il ne peut pas journaliser ;
  - il motive chaque decision en francais, pas en noms de colonnes ;
  - il permet de relire une decision rendue et d'y consigner une revue humaine.

Le journal est redirige vers un fichier temporaire : les tests ne doivent pas
polluer le journal de developpement.
"""

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

fastapi_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("shap")

from api import journal
from api.decision import moteur
from api.main import application


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Un client de test, avec un journal isole."""
    # En integration continue, ni le modele ni le socle ne sont presents : ce
    # sont des artefacts, pas du code. Les tests d'API sont alors ignores, et
    # le journal de la CI le dit explicitement.
    if not (RACINE / "models" / "modele_calibre.pkl").exists():
        pytest.skip("modele calibre absent : lancez entrainer.py puis calibrer.py")

    journal.JOURNAL_LOCAL = tmp_path_factory.mktemp("journal") / "decisions.jsonl"
    with fastapi_testclient.TestClient(application) as client:
        yield client


@pytest.fixture(scope="module")
def dossiers(client):
    """Trois dossiers, un par issue possible, cherches dans le magasin.

    On ne code pas en dur des numeros de dossier : ils dependraient du modele.
    On les cherche, et le test dit lesquels il a trouves.
    """
    trouves = {}
    for sk_id_curr in moteur.socle.index[:400]:
        resultat = moteur.decider(int(sk_id_curr))
        trouves.setdefault(resultat["decision"], int(sk_id_curr))
        if len(trouves) == 3:
            break
    return trouves


def test_sante_expose_l_essentiel(client):
    reponse = client.get("/sante")
    assert reponse.status_code == 200

    corps = reponse.json()
    assert corps["statut"] == "pret"
    assert corps["version_modele"].startswith("lgbm-calibre-")
    assert corps["seuil"] == pytest.approx(0.095, abs=0.05)
    assert corps["zone_grise"][0] < corps["seuil"] < corps["zone_grise"][1]


def test_toute_variable_montrable_a_un_libelle(client):
    """Controle C-5 : un motif de refus ne doit jamais etre du jargon."""
    assert client.get("/sante").json()["variables_sans_libelle"] == 0


def test_score_rend_une_decision_motivee(client, dossiers):
    identifiant = next(iter(dossiers.values()))
    reponse = client.post("/score", json={"sk_id_curr": identifiant})
    assert reponse.status_code == 200

    corps = reponse.json()
    assert corps["decision"] in ("accorde", "refuse", "revue_humaine")
    assert 0.0 <= corps["probabilite_defaut"] <= 1.0
    assert len(corps["facteurs"]) == 5

    # Chaque facteur doit etre lisible par un demandeur.
    for facteur in corps["facteurs"]:
        assert facteur["libelle"] != facteur["variable"], (
            f"{facteur['variable']} serait presentee sous son nom technique"
        )
        assert facteur["sens"] in ("favorable", "defavorable")


def test_la_zone_grise_impose_une_revue(client, dossiers):
    """Controle C-12 : dans la zone grise, la machine ne decide pas seule."""
    if "revue_humaine" not in dossiers:
        pytest.skip("aucun dossier en zone grise parmi les 400 examines")

    corps = client.post("/score", json={"sk_id_curr": dossiers["revue_humaine"]}).json()
    bas, haut = corps["zone_grise"]
    assert bas <= corps["probabilite_defaut"] <= haut
    assert corps["revue_humaine_requise"] is True


def test_tout_refus_ouvre_droit_au_reexamen(client, dossiers):
    """Article 22 : un refus automatique est toujours contestable."""
    if "refuse" not in dossiers:
        pytest.skip("aucun refus parmi les 400 dossiers examines")

    corps = client.post("/score", json={"sk_id_curr": dossiers["refuse"]}).json()
    assert corps["revue_humaine_requise"] is True


def test_chaque_decision_est_journalisee(client, dossiers):
    """Controle C-2 : le journal grandit d'une ligne par decision."""
    avant = client.get("/sante").json()["decisions_journalisees"]
    identifiant = next(iter(dossiers.values()))
    reponse = client.post("/score", json={"sk_id_curr": identifiant}).json()
    apres = client.get("/sante").json()["decisions_journalisees"]

    assert apres == avant + 1
    assert reponse["id_decision"] > 0


def test_une_decision_se_relit(client, dossiers):
    """Sans relecture, le journal ne prouve rien."""
    identifiant = next(iter(dossiers.values()))
    rendue = client.post("/score", json={"sk_id_curr": identifiant}).json()

    relue = client.get(f"/decisions/{rendue['id_decision']}")
    assert relue.status_code == 200

    corps = relue.json()
    assert corps["sk_id_curr"] == identifiant
    assert corps["decision"] == rendue["decision"]
    assert corps["version_modele"] == rendue["version_modele"]


def test_la_revue_humaine_se_consigne(client, dossiers):
    """Controle C-12 : l'intervention d'un analyste laisse une trace."""
    identifiant = next(iter(dossiers.values()))
    rendue = client.post("/score", json={"sk_id_curr": identifiant}).json()

    reponse = client.post(
        f"/decisions/{rendue['id_decision']}/revue",
        json={"identifiant_analyste": "analyste.durand"},
    )
    assert reponse.status_code == 200

    relue = client.get(f"/decisions/{rendue['id_decision']}").json()
    assert relue["revue_humaine"] is True
    assert relue["identifiant_analyste"] == "analyste.durand"
    # La decision automatique n'a pas ete effacee : c'est elle qu'on conteste.
    assert relue["decision"] == rendue["decision"]


def test_dossier_inconnu_rend_404(client):
    reponse = client.post("/score", json={"sk_id_curr": 999999999})
    assert reponse.status_code == 404


def test_journal_indisponible_bloque_la_decision(client, dossiers, monkeypatch):
    """Une decision non tracable ne doit pas etre rendue du tout."""

    def echouer(_resultat):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(journal, "enregistrer", echouer)
    reponse = client.post("/score", json={"sk_id_curr": next(iter(dossiers.values()))})

    assert reponse.status_code == 500
    assert "journal d'audit" in reponse.json()["detail"]


def test_sonde_signale_la_panne_au_lieu_de_mourir(client, monkeypatch):
    """Une sonde de sante doit dire que ca va mal, pas s'ecrouler avec.

    La premiere version appelait le journal sans filet : quand la base etait
    injoignable, /sante renvoyait une trace d'exception au lieu d'un
    diagnostic. Le conteneur restait alors en rotation.
    """

    def injoignable():
        raise ConnectionError("base injoignable")

    monkeypatch.setattr(journal, "compter", injoignable)
    reponse = client.get("/sante")

    # 503 et non 500 : le service est vivant mais hors d'etat de servir.
    assert reponse.status_code == 503
    corps = reponse.json()
    assert corps["statut"] == "degrade"
    assert corps["journal_joignable"] is False
    assert "base injoignable" in corps["journal_erreur"]
