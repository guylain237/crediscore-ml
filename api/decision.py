"""Rend une decision de credit a partir d'un numero de dossier.

CE QUE FAIT CE MODULE.

Il charge une fois pour toutes le modele calibre, le seuil et l'explicateur
SHAP, puis rend pour chaque dossier : une probabilite, une decision, et les
cinq facteurs qui l'ont motivee.

TROIS DECISIONS POSSIBLES, PAS DEUX.

  probabilite < 0,080          -> accorde
  entre 0,080 et 0,115         -> REVUE HUMAINE
  probabilite > 0,115          -> refuse

La zone du milieu n'est pas un choix de confort. Elle est calculee par
src/models/seuil.py : ce sont les seuils dont le cout total depasse le minimum
de moins de 2 %. Autrement dit, la ou deplacer le seuil ne change presque rien
au cout, la machine n'a pas de raison forte de trancher — c'est donc a un
analyste de le faire.

Mesure du 02/09/2026 sur le jeu de test :

  sous la zone   :  3,15 % de defaut  ->  on accorde sans hesiter
  dans la zone   :  9,42 % de defaut  ->  11,7 % des dossiers, on fait examiner
  au-dessus      : 20,58 % de defaut  ->  on refuse sans hesiter

CONTROLE C-12. Tout refus ouvre droit a un reexamen humain (article 22 du
RGPD). La zone grise va plus loin : elle IMPOSE l'examen avant la decision, au
lieu de l'offrir apres.
"""

import hashlib
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))
from explain.expliquer import LIBELLES, libelle
from models import preparation

# Nombre de facteurs rendus au demandeur. Cinq : au-dela, un motif de refus
# cesse d'etre lisible.
FACTEURS = 5


def modele_sous_jacent(modele):
    """Retrouve l'arbre LightGBM sous les couches d'emballage.

    Le modele servi est un CalibratedClassifierCV qui enveloppe un
    FrozenEstimator qui enveloppe le LGBMClassifier. SHAP ne sait travailler
    que sur le dernier : il refuse les deux premiers.

    PIEGE : on ne peut pas s'arreter des qu'un objet "a un booster_".
    FrozenEstimator transmet les attributs du modele qu'il enveloppe, donc
    hasattr(emballage, "booster_") repond vrai — et on rendrait l'emballage.
    C'est exactement l'erreur qui a fait echouer les dix tests de l'API.

    On descend donc TOUJOURS jusqu'au bout des .estimator, et on ne verifie le
    booster_ qu'a l'arrivee.
    """
    courant = modele
    for _ in range(5):
        if not hasattr(courant, "estimator"):
            break
        courant = courant.estimator

    if hasattr(courant, "booster_"):
        return courant

    raise RuntimeError(
        f"Impossible de retrouver le modele a arbres sous {type(modele).__name__}. "
        f"SHAP ne peut pas expliquer ce modele."
    )


class Moteur:
    """Le modele, le seuil et l'explicateur, charges une seule fois.

    Charger le modele a chaque appel prendrait plusieurs secondes. On paie le
    chargement au demarrage du service, une fois, et chaque requete se contente
    de calculer.
    """

    def __init__(self):
        self.modele = None
        self.socle = None
        self.explicateur = None
        self.config = None
        self.version = None
        self.colonnes = None

    def charger(self):
        if not preparation.MODELE_CALIBRE.exists():
            raise RuntimeError(
                f"Modele calibre introuvable : {preparation.MODELE_CALIBRE}. "
                f"Lancez src/models/entrainer.py puis src/models/calibrer.py."
            )
        self.modele = joblib.load(preparation.MODELE_CALIBRE)

        chemin_seuil = RACINE / "configs" / "seuil_decision.yaml"
        self.config = yaml.safe_load(chemin_seuil.read_text(encoding="utf-8"))
        for cle in ("seuil", "zone_grise_bas", "zone_grise_haut"):
            if cle not in self.config:
                raise RuntimeError(
                    f"'{cle}' absent de {chemin_seuil.name}. "
                    f"Relancez src/models/seuil.py."
                )

        # Le socle sert de magasin de variables. En production ce serait le
        # schema feature_store de PostgreSQL ; le contenu est le meme, seul le
        # moyen de lecture change.
        socle = pd.read_parquet(preparation.SOCLE)
        self.colonnes = [
            c for c in socle.columns
            if c not in preparation.NON_VARIABLES
            and c not in preparation.VARIABLES_RETIREES_C3
        ]

        # On reduit et on type UNE FOIS, au demarrage. La version precedente
        # selectionnait les 223 colonnes et convertissait les categorielles a
        # chaque requete, sur un tableau de 356 255 lignes : 465 ms par appel,
        # dont l'essentiel passait la.
        self.socle = socle.set_index("SK_ID_CURR")[self.colonnes]
        for colonne in self.socle.select_dtypes(include="object").columns:
            self.socle[colonne] = self.socle[colonne].astype("category")

        # La version du modele identifie ce qui a servi a decider. Une
        # contestation six mois plus tard doit pouvoir retrouver le modele
        # exact, pas seulement "le modele de l'epoque".
        empreinte = hashlib.sha256(preparation.MODELE_CALIBRE.read_bytes()).hexdigest()
        self.version = f"lgbm-calibre-{empreinte[:12]}"

        # SHAP travaille sur le modele SOUS la calibration : la correction
        # isotonique est monotone, elle ne change pas l'ordre des facteurs.
        import shap
        self.explicateur = shap.TreeExplainer(modele_sous_jacent(self.modele))

    @property
    def pret(self):
        return self.modele is not None

    def variables_du_dossier(self, sk_id_curr):
        """Retrouve la ligne d'un dossier, typee comme a l'entrainement."""
        if sk_id_curr not in self.socle.index:
            return None
        # Le tableau est deja reduit et type : il n'y a plus qu'a extraire.
        return self.socle.loc[[sk_id_curr]]

    def decider(self, sk_id_curr):
        """Score un dossier et rend la decision avec ses motifs."""
        depart = time.perf_counter()

        ligne = self.variables_du_dossier(sk_id_curr)
        if ligne is None:
            return None

        probabilite = float(self.modele.predict_proba(ligne)[0, 1])

        bas = self.config["zone_grise_bas"]
        haut = self.config["zone_grise_haut"]
        if probabilite < bas:
            decision = "accorde"
        elif probabilite > haut:
            decision = "refuse"
        else:
            decision = "revue_humaine"

        # Un refus se motive toujours ; un accord n'a pas a l'etre autant, mais
        # on calcule quand meme les facteurs : le journal d'audit doit pouvoir
        # expliquer une decision favorable si elle est contestee plus tard.
        facteurs = self.expliquer(ligne)

        return {
            "sk_id_curr": int(sk_id_curr),
            "probabilite_defaut": round(probabilite, 5),
            "seuil_applique": self.config["seuil"],
            "zone_grise": [bas, haut],
            "decision": decision,
            # Un refus reste contestable meme hors zone grise : c'est le droit
            # au reexamen humain de l'article 22.
            "revue_humaine_requise": decision in ("refuse", "revue_humaine"),
            "facteurs": facteurs,
            "version_modele": self.version,
            "duree_ms": int((time.perf_counter() - depart) * 1000),
        }

    def expliquer(self, ligne):
        """Les cinq facteurs les plus defavorables, en francais."""
        valeurs = self.explicateur.shap_values(ligne)
        if isinstance(valeurs, list):
            valeurs = valeurs[1]
        valeurs = np.asarray(valeurs).reshape(-1)

        rangs = np.argsort(-valeurs)[:FACTEURS]
        facteurs = []
        for rang in rangs:
            nom = self.colonnes[rang]
            valeur_brute = ligne.iloc[0, rang]
            facteurs.append(
                {
                    "variable": nom,
                    "libelle": libelle(nom),
                    "contribution": round(float(valeurs[rang]), 4),
                    "sens": "defavorable" if valeurs[rang] > 0 else "favorable",
                    "valeur": None if pd.isna(valeur_brute) else str(valeur_brute),
                }
            )
        return facteurs

    def facteurs_sans_libelle(self):
        """Variables qui seraient presentees sous leur nom technique.

        Sert au controle de sante : une decision motivee en jargon n'est pas
        une decision motivee.
        """
        return [c for c in self.colonnes if c not in LIBELLES]


moteur = Moteur()
