"""API de scoring CrediScore.

Quatre routes :

  GET  /sante                  l'etat du service, du modele et du journal
  POST /score                  une decision motivee, journalisee
  POST /decisions/{id}/revue   un analyste reprend la main (controle C-12)
  GET  /decisions/{id}         relire une decision rendue (article 22)

CE QUI SE PASSE A CHAQUE APPEL DE /score.

  1. On retrouve les variables du dossier dans le magasin.
  2. Le modele calibre rend une probabilite.
  3. La zone grise decide : accorde, refuse, ou revue humaine.
  4. SHAP produit les cinq facteurs qui motivent la decision.
  5. LA DECISION EST JOURNALISEE. Si l'ecriture echoue, on renvoie une erreur
     500 sans rendre la decision.

Le point 5 est le coeur du controle C-2. Une decision non tracee est une
decision a laquelle on ne pourra pas repondre en cas de contestation ; il vaut
mieux ne pas la rendre.

Lancer en developpement :

  .venv/Scripts/python.exe -m uvicorn api.main:application --reload

Documentation interactive : http://127.0.0.1:8000/docs
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
from api import journal
from api.decision import moteur

# Exigence C-5 : moins d'une seconde pour expliquer un dossier. On garde la
# meme borne pour la reponse complete de l'API, journalisation comprise.
LATENCE_MAXIMALE_MS = 1000


@asynccontextmanager
async def cycle_de_vie(app):
    """Charge le modele au demarrage, une seule fois."""
    moteur.charger()
    print(f"Modele charge      : {moteur.version}")
    print(f"Seuil de decision  : {moteur.config['seuil']}")
    print(f"Zone grise         : {moteur.config['zone_grise_bas']} "
          f"a {moteur.config['zone_grise_haut']}")
    print(f"Journal d'audit    : {journal.destination()}")

    manquants = moteur.facteurs_sans_libelle()
    if manquants:
        print(f"ATTENTION : {len(manquants)} variables sans libelle francais")
    yield


application = FastAPI(
    title="CrediScore — API de scoring",
    version="1.0",
    description=(
        "Score une demande de credit a la consommation et rend les facteurs "
        "qui motivent la decision. Chaque appel est journalise (controle C-2, "
        "article 22 du RGPD)."
    ),
    lifespan=cycle_de_vie,
)


class DemandeScore(BaseModel):
    sk_id_curr: int = Field(
        ...,
        description="Numero du dossier dans le magasin de variables",
        examples=[100002],
    )


class DemandeRevue(BaseModel):
    identifiant_analyste: str = Field(
        ...,
        description="Qui a repris la main sur la decision",
        examples=["analyste.durand"],
    )


@application.get("/sante")
def sante():
    """Etat du service. Utilise par la sonde du conteneur."""
    return {
        "statut": "pret" if moteur.pret else "chargement",
        "version_modele": moteur.version,
        "seuil": moteur.config["seuil"] if moteur.pret else None,
        "zone_grise": (
            [moteur.config["zone_grise_bas"], moteur.config["zone_grise_haut"]]
            if moteur.pret else None
        ),
        "journal": journal.destination(),
        "decisions_journalisees": journal.compter(),
        "variables_sans_libelle": len(moteur.facteurs_sans_libelle()) if moteur.pret else None,
    }


@application.post("/score")
def score(demande: DemandeScore):
    """Rend une decision motivee et la journalise."""
    resultat = moteur.decider(demande.sk_id_curr)
    if resultat is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dossier {demande.sk_id_curr} inconnu du magasin de variables",
        )

    # CONTROLE C-2 : rien ne sort sans avoir ete ecrit.
    try:
        id_decision = journal.enregistrer(resultat)
    except Exception as erreur:
        journal.journaliser_trace(f"echec du journal : {erreur}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Decision non rendue : le journal d'audit est indisponible. "
                "Une decision non tracee ne peut pas etre justifiee en cas de "
                "contestation (article 22 du RGPD)."
            ),
        ) from erreur

    journal.journaliser_trace(
        f"dossier {journal.pseudonyme(demande.sk_id_curr)} "
        f"-> {resultat['decision']} en {resultat['duree_ms']} ms"
    )

    if resultat["duree_ms"] > LATENCE_MAXIMALE_MS:
        journal.journaliser_trace(
            f"ATTENTION C-5 : {resultat['duree_ms']} ms, "
            f"au-dela de {LATENCE_MAXIMALE_MS} ms"
        )

    return {"id_decision": id_decision, **resultat}


@application.post("/decisions/{id_decision}/revue")
def revue(id_decision: int, demande: DemandeRevue):
    """Consigne l'intervention d'un analyste (controle C-12).

    La decision automatique n'est pas effacee : on ajoute la trace de qui a
    repris la main. Effacer le score reviendrait a effacer ce qui a ete
    conteste.
    """
    if not journal.marquer_revue(id_decision, demande.identifiant_analyste):
        raise HTTPException(status_code=404, detail=f"Decision {id_decision} inconnue")

    return {
        "id_decision": id_decision,
        "revue_humaine": True,
        "identifiant_analyste": demande.identifiant_analyste,
    }


@application.get("/decisions/{id_decision}")
def relire(id_decision: int):
    """Relit une decision journalisee.

    C'est la route qui rend l'article 22 effectif : sans elle, le journal
    existerait sans que personne ne puisse le consulter.
    """
    ligne = journal.relire(id_decision)
    if ligne is None:
        raise HTTPException(status_code=404, detail=f"Decision {id_decision} inconnue")
    return ligne
