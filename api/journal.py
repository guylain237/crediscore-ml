"""Ecrit une ligne dans le journal des decisions (controle C-2).

POURQUOI CE JOURNAL EXISTE.

L'article 22 du RGPD donne a toute personne le droit de contester une decision
automatisee. Pour y repondre six mois plus tard, il faut pouvoir dire : quel
score, quel seuil, quels facteurs, quelle version du modele, et si un analyste
est intervenu. Rien de tout cela ne se reconstitue apres coup.

La table journal.decisions attend ces colonnes exactement (pipelines/sql/
01_schemas.sql du depot mlops).

DEUX DESTINATIONS, ET C'EST VOLONTAIRE.

  DATABASE_URL definie  -> PostgreSQL, sur la VM
  sinon                 -> un fichier JSONL local, en developpement

Une decision n'est JAMAIS rendue sans etre journalisee. Si l'ecriture echoue,
l'API renvoie une erreur plutot qu'une decision non tracee : mieux vaut un
service indisponible qu'une decision dont on ne pourra pas rendre compte.

L'IDENTIFIANT EN CLAIR, ET POURQUOI.

Le controle C-7 remplace les identifiants par un pseudonyme dans les journaux
Airflow, qui sont lisibles par quiconque a le mot de passe de l'interface web.
Ici c'est l'inverse : la table vit dans PostgreSQL, derriere le reseau prive,
et son objet meme est de retrouver un demandeur qui conteste. Un pseudonyme
irreversible rendrait le journal inutile.

En revanche, les traces techniques imprimees par l'API n'affichent que le
pseudonyme : l'identifiant ne sort pas de la base.
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

# Le fichier de repli, en developpement. Ignore par git comme tout .jsonl de
# donnees : il contient des identifiants de dossiers.
JOURNAL_LOCAL = RACINE / "data" / "journal_decisions.jsonl"

INSERTION = """
INSERT INTO journal.decisions (
    sk_id_curr, probabilite_defaut, seuil_applique, decision,
    facteurs_shap, version_modele, duree_ms, revue_humaine
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id_decision
"""

MARQUER_REVUE = """
UPDATE journal.decisions
   SET revue_humaine = TRUE, identifiant_analyste = %s
 WHERE id_decision = %s
RETURNING id_decision
"""


def url_base():
    return os.environ.get("DATABASE_URL")


def destination():
    """Ou part le journal, en une phrase lisible au demarrage."""
    if url_base():
        return "PostgreSQL (journal.decisions)"
    return f"fichier local {JOURNAL_LOCAL.name} — developpement uniquement"


def _ecrire_postgres(resultat):
    import psycopg

    with psycopg.connect(url_base()) as connexion, connexion.cursor() as curseur:
        curseur.execute(
            INSERTION,
            (
                resultat["sk_id_curr"],
                resultat["probabilite_defaut"],
                resultat["seuil_applique"],
                resultat["decision"],
                json.dumps(resultat["facteurs"], ensure_ascii=False),
                resultat["version_modele"],
                resultat["duree_ms"],
                False,
            ),
        )
        return curseur.fetchone()[0]


def _ecrire_fichier(resultat):
    JOURNAL_LOCAL.parent.mkdir(parents=True, exist_ok=True)

    # L'identifiant de ligne est le nombre de lignes deja presentes. Suffisant
    # en developpement ; en base, c'est un BIGSERIAL qui s'en charge.
    if JOURNAL_LOCAL.exists():
        with JOURNAL_LOCAL.open(encoding="utf-8") as fichier:
            id_decision = sum(1 for _ in fichier) + 1
    else:
        id_decision = 1

    ligne = {
        "id_decision": id_decision,
        "horodatage": datetime.now(UTC).isoformat(),
        "revue_humaine": False,
        "identifiant_analyste": None,
        **resultat,
    }
    with JOURNAL_LOCAL.open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return id_decision


def enregistrer(resultat):
    """Journalise une decision et rend son identifiant.

    Leve une exception si l'ecriture echoue : l'appelant doit alors refuser de
    rendre la decision.
    """
    if url_base():
        return _ecrire_postgres(resultat)
    return _ecrire_fichier(resultat)


def _revue_postgres(id_decision, analyste):
    import psycopg

    with psycopg.connect(url_base()) as connexion, connexion.cursor() as curseur:
        curseur.execute(MARQUER_REVUE, (analyste, id_decision))
        return curseur.fetchone() is not None


def _revue_fichier(id_decision, analyste):
    if not JOURNAL_LOCAL.exists():
        return False

    lignes = JOURNAL_LOCAL.read_text(encoding="utf-8").splitlines()
    trouve = False
    for numero, texte in enumerate(lignes):
        ligne = json.loads(texte)
        if ligne.get("id_decision") == id_decision:
            ligne["revue_humaine"] = True
            ligne["identifiant_analyste"] = analyste
            ligne["revue_le"] = datetime.now(UTC).isoformat()
            lignes[numero] = json.dumps(ligne, ensure_ascii=False)
            trouve = True
            break

    if trouve:
        JOURNAL_LOCAL.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return trouve


def marquer_revue(id_decision, analyste):
    """Consigne qu'un analyste a repris la main sur une decision (C-12).

    On ne remplace pas la decision d'origine : on ajoute la trace de
    l'intervention. Effacer le score automatique reviendrait a effacer la
    preuve de ce qui a ete conteste.
    """
    if url_base():
        return _revue_postgres(id_decision, analyste)
    return _revue_fichier(id_decision, analyste)


RELECTURE = """
SELECT id_decision, horodatage, sk_id_curr, probabilite_defaut, seuil_applique,
       decision, facteurs_shap, version_modele, duree_ms, revue_humaine,
       identifiant_analyste
  FROM journal.decisions
 WHERE id_decision = %s
"""


def _relire_postgres(id_decision):
    import psycopg

    with psycopg.connect(url_base()) as connexion, connexion.cursor() as curseur:
        curseur.execute(RELECTURE, (id_decision,))
        ligne = curseur.fetchone()
        if ligne is None:
            return None
        colonnes = [description.name for description in curseur.description]
        resultat = dict(zip(colonnes, ligne, strict=True))
        resultat["horodatage"] = resultat["horodatage"].isoformat()
        resultat["probabilite_defaut"] = float(resultat["probabilite_defaut"])
        resultat["seuil_applique"] = float(resultat["seuil_applique"])
        return resultat


def _relire_fichier(id_decision):
    if not JOURNAL_LOCAL.exists():
        return None
    with JOURNAL_LOCAL.open(encoding="utf-8") as fichier:
        for texte in fichier:
            ligne = json.loads(texte)
            if ligne.get("id_decision") == id_decision:
                return ligne
    return None


def relire(id_decision):
    """Retrouve une decision journalisee, telle qu'elle a ete rendue.

    C'est ce qui rend l'article 22 effectif : un journal qu'on ne peut pas
    consulter ne prouve rien.
    """
    if url_base():
        return _relire_postgres(id_decision)
    return _relire_fichier(id_decision)


def etat():
    """Etat du journal, pour la sonde de sante. Ne leve JAMAIS.

    Une sonde qui meurt quand la dependance est en panne ne sert a rien :
    son travail est justement de dire que ca va mal. La premiere version
    appelait compter() sans filet et l'API renvoyait une trace d'exception au
    lieu d'un diagnostic.
    """
    try:
        return {
            "destination": destination(),
            "joignable": True,
            "decisions_journalisees": compter(),
            "erreur": None,
        }
    # On attrape TOUT, et c'est voulu : reseau, authentification, base
    # absente, pilote casse. Une sonde qui ne rattrape que les pannes
    # prevues meurt sur les autres, c'est-a-dire exactement celles qu'on
    # aurait voulu voir signalees.
    except Exception as erreur:  # noqa: BLE001
        return {
            "destination": destination(),
            "joignable": False,
            "decisions_journalisees": None,
            # Le message de la base, tronque : il peut contenir l'hote et le
            # port, utiles au diagnostic, mais pas plus.
            "erreur": f"{type(erreur).__name__}: {str(erreur)[:120]}",
        }


def compter():
    """Nombre de decisions journalisees, pour le controle de sante."""
    if url_base():
        import psycopg

        with psycopg.connect(url_base()) as connexion, connexion.cursor() as curseur:
            curseur.execute("SELECT count(*) FROM journal.decisions")
            return curseur.fetchone()[0]

    if not JOURNAL_LOCAL.exists():
        return 0
    with JOURNAL_LOCAL.open(encoding="utf-8") as fichier:
        return sum(1 for _ in fichier)


def pseudonyme(sk_id_curr):
    """Empreinte de l'identifiant, pour les traces techniques.

    Reprend la logique du controle C-7 du depot mlops : le meme dossier donne
    toujours le meme pseudonyme, mais on ne remonte pas a l'identifiant sans
    le sel.
    """
    import hashlib

    sel = os.environ.get("CREDISCORE_SEL_PSEUDO", "sel-de-developpement")
    return hashlib.sha256((sel + str(sk_id_curr)).encode()).hexdigest()[:12]


def journaliser_trace(message):
    """Trace technique sur la sortie standard, sans identifiant en clair."""
    print(message, file=sys.stderr, flush=True)
