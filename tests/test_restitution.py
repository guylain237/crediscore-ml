"""Verifie l'accessibilite de la page de restitution (RGAA 4.1, politique P-11).

CE QUE CES TESTS SONT, ET CE QU'ILS NE SONT PAS.

Ils verifient les criteres RGAA qui se controlent AUTOMATIQUEMENT sur le code
produit : la langue est-elle declaree, le contraste atteint-il le rapport
exige, le tableau a-t-il de vrais en-tetes, chaque champ a-t-il une etiquette.

Ils ne remplacent pas un audit. Un audit RGAA verifie aussi des choses qu'aucun
programme ne sait juger : la pertinence d'une alternative textuelle, la
coherence de l'ordre de lecture, l'utilisabilite reelle au lecteur d'ecran.
Ces points sont declares comme non testes dans docs/accessibilite.md, plutot
que passes sous silence.

POURQUOI CES TESTS EXISTENT.

L'article 22 du RGPD donne le droit a une explication. Le RGAA exige qu'elle
soit percue. Un demandeur aveugle doit pouvoir ENTENDRE ses cinq motifs — une
explication imperceptible n'est pas une explication.

Le numero de critere est cite dans chaque test : il doit etre possible de
remonter du test au referentiel.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from api import restitution

# Rapport de contraste minimal pour du texte normal (RGAA 3.2, WCAG 1.4.3).
CONTRASTE_MINIMAL = 4.5


def decision_type(etat="refuse", revue_requise=True, revue_faite=False):
    """Une decision journalisee, telle que l'API en produit."""
    return {
        "id_decision": 42,
        "horodatage": "2026-09-08T18:30:00+00:00",
        "sk_id_curr": 100039,
        "probabilite_defaut": 0.12156,
        "seuil_applique": 0.095,
        "zone_grise": [0.08, 0.115],
        "decision": etat,
        "revue_humaine_requise": revue_requise,
        "revue_humaine": revue_faite,
        "identifiant_analyste": "analyste.durand" if revue_faite else None,
        "version_modele": "lgbm-calibre-79e50a3ee977",
        "facteurs": [
            {"variable": "EXT_SOURCE_2", "libelle": "score externe n2",
             "contribution": 0.4602, "sens": "defavorable", "valeur": "0.3217"},
            {"variable": "ORGANIZATION_TYPE", "libelle": "secteur d'activite",
             "contribution": 0.2089, "sens": "defavorable", "valeur": "Self-employed"},
            {"variable": "OWN_CAR_AGE", "libelle": "age du vehicule",
             "contribution": -0.05, "sens": "favorable", "valeur": None},
        ],
    }


class Structure(HTMLParser):
    """Releve ce qu'il faut pour juger la structure de la page."""

    def __init__(self):
        super().__init__()
        self.titres = []
        self.balises = []
        self.attributs = {}
        self.etiquettes = []
        self.champs = []
        self.th = []

    def handle_starttag(self, tag, attrs):
        attributs = dict(attrs)
        self.balises.append(tag)
        self.attributs.setdefault(tag, []).append(attributs)
        if re.fullmatch(r"h[1-6]", tag):
            self.titres.append(int(tag[1]))
        if tag == "label":
            self.etiquettes.append(attributs.get("for"))
        if tag in ("input", "select", "textarea"):
            self.champs.append(attributs)
        if tag == "th":
            self.th.append(attributs)


def analyser(page):
    lecteur = Structure()
    lecteur.feed(page)
    return lecteur


def luminance(couleur):
    """Luminance relative d'une couleur, selon la formule WCAG 2.1."""
    canaux = [int(couleur[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineaires = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        for c in canaux
    ]
    return 0.2126 * lineaires[0] + 0.7152 * lineaires[1] + 0.0722 * lineaires[2]


def contraste(premiere, seconde):
    """Rapport de contraste entre deux couleurs, de 1 a 21."""
    claire, sombre = sorted((luminance(premiere), luminance(seconde)), reverse=True)
    return (claire + 0.05) / (sombre + 0.05)


# --- Le calcul de contraste lui-meme, verifie sur des cas connus -------------


def test_le_calcul_de_contraste_est_juste():
    """Sans ce test, celui du contraste ne prouverait rien.

    Une fonction qui rendrait toujours 21 ferait passer tous les autres.
    """
    assert contraste("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contraste("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)
    # Gris de reference : #767676 sur blanc vaut 4,54 — la limite du critere.
    assert contraste("#767676", "#ffffff") == pytest.approx(4.54, abs=0.05)


# --- Criteres RGAA verifiables automatiquement -------------------------------


def test_la_langue_est_declaree():
    """RGAA 8.3 — sans lang, un lecteur d'ecran prononce en anglais.

    "mensualite" lu avec la phonetique anglaise est incomprehensible.
    """
    page = restitution.construire(decision_type())
    assert re.search(r'<html[^>]+lang="fr"', page), "attribut lang absent ou incorrect"


def test_le_titre_de_page_identifie_la_decision():
    """RGAA 8.5 / 8.6 — le titre est la premiere chose annoncee."""
    page = restitution.construire(decision_type())
    titre = re.search(r"<title>(.*?)</title>", page).group(1)
    assert "42" in titre, "le titre doit identifier la decision"
    assert len(titre) > 10


def test_l_encodage_est_declare():
    """Prealable au critere 8.2 (code source valide).

    Le RGAA 4.1 ne numerote pas l'encodage separement, mais sans charset les
    accents se rendent en caracteres parasites : "mensualite" devient
    illisible a l'ecran comme au lecteur d'ecran.
    """
    page = restitution.construire(decision_type())
    assert re.search(r'<meta charset="utf-8"', page, re.IGNORECASE)


@pytest.mark.parametrize("etat", ["accorde", "refuse", "revue_humaine"])
def test_la_decision_est_ecrite_en_toutes_lettres(etat):
    """RGAA 3.1 — l'information ne doit jamais passer par la seule couleur.

    Une pastille rouge ne dit rien a qui ne distingue pas le rouge, et rien du
    tout a un lecteur d'ecran.
    """
    page = restitution.construire(decision_type(etat=etat))
    mot = restitution.LIBELLES_DECISION[etat]
    assert mot in page, f"la decision '{etat}' n'est pas ecrite en toutes lettres"


def test_le_sens_de_chaque_motif_est_un_mot():
    """RGAA 3.1 — un motif defavorable doit se lire, pas se deviner."""
    page = restitution.construire(decision_type())
    # Accentue : "defavorable" est du code interne, le demandeur lit du francais.
    assert "défavorable" in page
    assert "favorable" in page


def test_tous_les_contrastes_atteignent_le_seuil():
    """RGAA 3.2 — rapport d'au moins 4,5 pour 1 sur le texte normal.

    Les couleurs sont lues dans le module, et la feuille de style est generee a
    partir des memes valeurs : ce qui est mesure ici est bien ce qui est rendu.
    """
    insuffisants = []
    for nom, (texte, fond) in restitution.COULEURS.items():
        rapport = contraste(texte, fond)
        if rapport < CONTRASTE_MINIMAL:
            insuffisants.append(f"{nom} : {rapport:.2f} pour 1")

    assert not insuffisants, f"contraste insuffisant — {insuffisants}"


def test_le_tableau_des_motifs_a_de_vrais_en_tetes():
    """RGAA 5.6 / 5.7 — sans scope, un lecteur d'ecran ne relie pas la cellule
    a sa colonne : il lit une suite de mots sans structure."""
    lecteur = analyser(restitution.construire(decision_type()))
    assert lecteur.th, "aucun en-tete de tableau"
    for entete in lecteur.th:
        assert entete.get("scope") == "col", "en-tete sans portee declaree"


def test_le_tableau_a_un_resume():
    """RGAA 5.4 — le caption dit a quoi sert le tableau avant de le lire."""
    page = restitution.construire(decision_type())
    assert "<caption>" in page


def test_les_titres_se_suivent_sans_saut():
    """RGAA 9.1 — passer de h1 a h3 casse la navigation par titres.

    Beaucoup d'utilisateurs de lecteur d'ecran parcourent une page uniquement
    par ses titres.
    """
    lecteur = analyser(restitution.construire(decision_type()))
    assert lecteur.titres, "aucun titre"
    assert lecteur.titres[0] == 1, "la page doit commencer par un h1"
    assert lecteur.titres.count(1) == 1, "un seul h1 par page"

    for precedent, suivant in zip(lecteur.titres, lecteur.titres[1:], strict=False):
        assert suivant <= precedent + 1, (
            f"saut de niveau : h{precedent} suivi de h{suivant}"
        )


def test_chaque_champ_de_formulaire_a_une_etiquette():
    """RGAA 11.1 — un champ sans etiquette est annonce "zone d'edition", sans
    dire ce qu'il attend."""
    lecteur = analyser(restitution.construire(decision_type(revue_requise=True)))
    assert lecteur.champs, "le formulaire de reexamen est absent"

    for champ in lecteur.champs:
        identifiant = champ.get("id")
        assert identifiant, f"champ sans id : {champ}"
        assert identifiant in lecteur.etiquettes, (
            f"aucune etiquette ne pointe vers le champ '{identifiant}'"
        )


def test_aucun_javascript_n_est_requis():
    """Lire sa decision ne doit dependre ni d'un script, ni d'un navigateur
    recent, ni d'une connexion rapide."""
    page = restitution.construire(decision_type())
    assert "<script" not in page.lower()
    assert "onclick" not in page.lower()


def test_la_page_a_un_point_de_repere_principal():
    """RGAA 12.6 — le landmark main permet d'atteindre le contenu directement."""
    lecteur = analyser(restitution.construire(decision_type()))
    assert lecteur.balises.count("main") == 1


def test_un_lien_d_evitement_ouvre_la_page():
    """RGAA 12.7 — sauter la navigation, sans avoir a la parcourir au clavier."""
    page = restitution.construire(decision_type())
    assert 'href="#contenu"' in page
    assert 'id="contenu"' in page


def test_les_nombres_sont_ecrits_en_francais():
    """Un lecteur d'ecran prononce "3.3" comme "trois point trois".

    Ce n'est pas un critere RGAA numerote, mais cela releve de la meme
    exigence : le contenu doit etre comprehensible a l'oral.
    """
    page = restitution.construire(decision_type())
    assert "12,2&nbsp;%" in page, "la virgule decimale francaise n'est pas utilisee"
    assert "12.2" not in page


def test_une_valeur_absente_est_dite_et_non_vide():
    """Une cellule vide est annoncee "vide" par un lecteur d'ecran, ce qui ne
    distingue pas l'absence de donnee d'un defaut d'affichage."""
    page = restitution.construire(decision_type())
    assert "non renseignée" in page


def test_le_contenu_est_echappe():
    """Une valeur venue des donnees ne doit pas pouvoir injecter de balise."""
    decision = decision_type()
    decision["facteurs"][0]["libelle"] = "<script>alerte()</script>"
    page = restitution.construire(decision)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


# --- Les deux etats de la revue ----------------------------------------------


def test_le_reexamen_est_propose_quand_il_est_de_droit():
    """Article 22 : un refus automatique ouvre le droit a une intervention."""
    page = restitution.construire(decision_type(revue_requise=True))
    assert "<form" in page
    assert "article&nbsp;22" in page


def test_le_reexamen_realise_est_affiche_avec_son_auteur():
    """La trace de qui a repris la main doit etre visible, pas seulement
    enregistree."""
    page = restitution.construire(
        decision_type(revue_requise=True, revue_faite=True)
    )
    assert "analyste.durand" in page
    assert "<form" not in page, "le formulaire ne doit plus etre propose"


# --- Lisibilite des valeurs montrees au demandeur ----------------------------
#
# Ces tests sont nes d'une capture d'ecran. La page affichait "-637.0" comme
# anciennete dans l'emploi, "Business Entity Type 3" comme secteur, et
# "0.13937578009978951" comme score. Les tests de structure ci-dessus passaient
# tous : ils verifiaient le HTML, pas ce qu'on y lit.


def test_un_nombre_de_jours_negatif_devient_une_duree():
    """-637 jours veut dire "il y a un an et neuf mois", pas "moins 637"."""
    from api import valeurs

    assert valeurs.formater("DAYS_EMPLOYED", -637.0) == "il y a 1 an et 9 mois"
    assert valeurs.formater("DAYS_REGISTRATION", -4502) == "il y a 12 ans et 4 mois"


def test_un_retard_n_est_pas_une_date():
    """LE PIEGE de ce module, et il aurait inverse le sens d'un motif.

    INSTAL_RETARD_JOURS_MEAN vaut -10 parce que le client paie DIX JOURS EN
    AVANCE. Le classer avec les dates passees aurait affiche "il y a 10 jours"
    a la place de "10 jours d'avance" — un comportement favorable presente
    comme une date sans rapport.
    """
    from api import valeurs

    assert valeurs.formater("INSTAL_RETARD_JOURS_MEAN", -10) == "10 jours d'avance"
    assert valeurs.formater("INSTAL_RETARD_MAX_12M", 21) == "21 jours de retard"
    assert valeurs.formater("INSTAL_RETARD_MAX_12M", 0) == "à l'heure"


def test_aucune_modalite_n_est_laissee_en_anglais():
    """Un demandeur francais ne doit pas lire son motif de refus en anglais."""
    from api import valeurs

    assert valeurs.formater("ORGANIZATION_TYPE", "Business Entity Type 3") == (
        "Entreprise (type 3)"
    )
    assert valeurs.formater("ORGANIZATION_TYPE", "Self-employed") == "Indépendant"
    assert valeurs.formater("OCCUPATION_TYPE", "Drivers") == "Conducteur"
    assert valeurs.formater("NAME_EDUCATION_TYPE", "Higher education") == (
        "Enseignement supérieur"
    )


def test_les_modalites_couvrent_toutes_les_valeurs_du_socle():
    """Une modalite oubliee ressortirait en anglais sur la page.

    Le test lit les modalites reellement presentes dans les donnees plutot que
    de faire confiance a la table.
    """
    from api import valeurs

    attendues = {
        "ORGANIZATION_TYPE": 58, "OCCUPATION_TYPE": 18, "NAME_INCOME_TYPE": 8,
        "NAME_EDUCATION_TYPE": 5, "NAME_HOUSING_TYPE": 6, "NAME_TYPE_SUITE": 7,
        "WEEKDAY_APPR_PROCESS_START": 7, "WALLSMATERIAL_MODE": 7,
        "FONDKAPREMONT_MODE": 4, "HOUSETYPE_MODE": 3, "NAME_CONTRACT_TYPE": 2,
        "FLAG_OWN_CAR": 2, "FLAG_OWN_REALTY": 2, "EMERGENCYSTATE_MODE": 2,
    }
    for variable, nombre_attendu in attendues.items():
        assert variable in valeurs.MODALITES, f"{variable} sans traduction"
        assert len(valeurs.MODALITES[variable]) >= nombre_attendu, (
            f"{variable} : {len(valeurs.MODALITES[variable])} traductions "
            f"pour {nombre_attendu} modalites dans les donnees"
        )


def test_les_nombres_sont_arrondis_et_a_la_francaise():
    """Dix-sept decimales sont illisibles, et un lecteur d'ecran les prononce."""
    from api import valeurs

    assert valeurs.formater("EXT_SOURCE_3", 0.13937578009978951) == "0,14"
    assert "," in valeurs.formater("RATIO_ANNUITE_CREDIT", 0.0614)
    assert "." not in valeurs.formater("EXT_SOURCE_2", 0.3217)


def test_le_separateur_de_milliers_est_insecable():
    """Un montant ne doit pas se couper en fin de ligne.

    Sans espace insecable, on lirait "24" a la fin d'une ligne et "903 EUR" au
    debut de la suivante.
    """
    from api import valeurs

    montant = valeurs.formater("AMT_ANNUITY", 24903.0)
    assert montant == f"24{valeurs.ESPACE_MILLIERS}903 €"
    assert " " not in montant.replace(" €", ""), "espace ordinaire dans le montant"


def test_le_sens_est_accentue():
    """"defavorable" est du code interne ; le demandeur lit du francais."""
    from api import valeurs

    assert valeurs.sens("defavorable") == "défavorable"


def test_la_page_ne_montre_plus_de_valeur_brute():
    """Le controle de bout en bout : ce que la capture d'ecran montrait."""
    decision = decision_type()
    decision["facteurs"] = [
        {"variable": "DAYS_EMPLOYED", "libelle": "anciennete dans l'emploi",
         "contribution": 0.3, "sens": "defavorable", "valeur": "-637.0"},
        {"variable": "ORGANIZATION_TYPE", "libelle": "secteur d'activite",
         "contribution": 0.2, "sens": "defavorable", "valeur": "Business Entity Type 3"},
        {"variable": "EXT_SOURCE_3", "libelle": "score externe n3",
         "contribution": 0.1, "sens": "defavorable", "valeur": "0.13937578009978951"},
    ]
    page = restitution.construire(decision)

    assert "-637.0" not in page
    assert "Business Entity Type 3" not in page
    assert "0.13937578009978951" not in page

    assert "il y a 1 an et 9 mois" in page
    assert "Entreprise (type 3)" in page
    assert "0,14" in page
    assert "défavorable" in page


def test_un_accord_montre_ce_qui_a_aide_pas_ce_qui_a_nui():
    """Sur un dossier accorde, les cinq motifs doivent etre FAVORABLES.

    La premiere version affichait toujours les cinq facteurs les plus
    defavorables. Un demandeur accepte lisait donc :

        Accordee — probabilite 1,7 %
        1. score externe n1 ... defavorable
        ... et ainsi de suite sur les cinq

    Une contradiction apparente, et une explication fausse : ce qui a emporte
    la decision, ce sont les facteurs favorables, qu'on ne montrait pas.
    """

    from api.decision import moteur
    from models import preparation

    if not preparation.MODELE_CALIBRE.exists():
        pytest.skip("modele calibre absent")
    if moteur.modele is None:
        moteur.charger()

    # On cherche un dossier accorde, puis on regarde le sens de ses motifs.
    for sk_id_curr in moteur.socle.index[:400]:
        resultat = moteur.decider(int(sk_id_curr))
        if resultat["decision"] == "accorde":
            sens = {f["sens"] for f in resultat["facteurs"]}
            assert sens == {"favorable"}, (
                f"un accord affiche des motifs {sens} : ils doivent tous etre "
                f"favorables"
            )
            return
    pytest.skip("aucun dossier accorde parmi les 400 examines")


def test_la_legende_du_tableau_suit_la_decision():
    """« ce qui a le plus pesé » n'a pas le même sens selon l'issue."""
    accorde = restitution.construire(decision_type(etat="accorde"))
    refuse = restitution.construire(decision_type(etat="refuse"))

    assert "en faveur de votre demande" in accorde
    assert "contre votre demande" in refuse
