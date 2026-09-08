"""Page qui montre une decision a un humain (article 22 du RGPD, RGAA).

POURQUOI CETTE PAGE EXISTE.

Le controle C-12 impose un reexamen humain, et la zone grise l'impose AVANT la
decision sur 11,7 % des dossiers. Mais jusqu'ici l'analyste charge de ce
reexamen recevait du JSON brut, et le demandeur ne recevait rien du tout.

L'article 22 donne le droit a une explication. Le projet la calcule en 24
millisecondes et ne l'affichait nulle part. Cette page comble ce trou.

POURQUOI ELLE EST ACCESSIBLE DES LE DEPART.

Parce qu'une explication imperceptible n'est pas une explication. Un demandeur
aveugle doit pouvoir ENTENDRE ses cinq motifs. Le droit a l'explication et
l'obligation d'accessibilite portent sur le meme ecran : celui qui annonce le
refus.

CE QUE LA PAGE RESPECTE, ET LE CRITERE RGAA CORRESPONDANT.

  8.3 / 8.4   la langue est declaree, le lecteur d'ecran prononce en francais
  3.1         aucune information portee par la seule couleur : la decision est
              ecrite en toutes lettres, jamais par une pastille rouge seule
  3.2         contraste d'au moins 4,5 pour 1, calcule et non estime
  5.6 / 5.7   le tableau des motifs a de vrais en-tetes, avec leur portee
  9.1         les titres se suivent sans saut de niveau
  11.1        chaque champ de formulaire a une etiquette
  12.6        un point de repere principal, pour naviguer directement

AUCUN JAVASCRIPT. Lire sa decision ne doit dependre ni d'un script, ni d'une
connexion rapide, ni d'un navigateur recent.
"""

from html import escape

# Couleurs de la page. Elles vivent ici plutot que dans une feuille de style
# separee pour une raison precise : les tests calculent le contraste a partir
# de ces valeurs. Une couleur choisie a l'oeil ne serait verifiee par personne.
#
# Chaque paire est (texte, fond).
COULEURS = {
    "texte": ("#1a1a1a", "#ffffff"),
    "accorde": ("#14532d", "#e7f5ec"),
    "refuse": ("#7f1d1d", "#fdeaea"),
    "revue_humaine": ("#713f12", "#fdf4e3"),
    "secondaire": ("#404040", "#f5f5f5"),
}

# Ce que chaque decision annonce, EN TOUTES LETTRES. C'est le critere 3.1 :
# l'information ne doit jamais passer par la seule couleur.
LIBELLES_DECISION = {
    "accorde": "Accordée",
    "refuse": "Refusée",
    "revue_humaine": "Réexamen par une personne requis",
}

EXPLICATIONS = {
    "accorde": (
        "Votre demande est acceptée. Le risque estimé est inférieur au seuil "
        "retenu par l'établissement."
    ),
    "refuse": (
        "Votre demande est refusée. Le risque estimé dépasse le seuil retenu "
        "par l'établissement. Vous pouvez demander le réexamen de cette "
        "décision par une personne."
    ),
    "revue_humaine": (
        "Votre demande doit être examinée par une personne. Le risque estimé se "
        "situe dans une zone où le calcul ne permet pas de trancher seul."
    ),
}


def nombre(valeur):
    """Un nombre ecrit en francais : virgule decimale, pas point.

    Ce n'est pas cosmetique. Un lecteur d'ecran prononce "3.3" comme "trois
    point trois", ce qui n'a pas de sens a l'oral en francais.
    """
    return f"{valeur:.1f}".replace(".", ",")


def feuille_de_style():
    """Le style, dans la page. Aucun fichier externe a charger."""
    regles = [
        "  body { margin: 0; font-family: system-ui, sans-serif; line-height: 1.6;",
        f"    color: {COULEURS['texte'][0]}; background: {COULEURS['texte'][1]}; }}",
        "  main { max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem; }",
        "  h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }",
        "  h2 { font-size: 1.2rem; margin-top: 2rem; }",
        "  .decision { display: inline-block; padding: 0.4rem 0.9rem;",
        "    border-radius: 0.25rem; font-weight: 700; margin: 0.5rem 0 1rem; }",
    ]
    for etat, (texte, fond) in COULEURS.items():
        if etat in LIBELLES_DECISION:
            regles.append(f"  .decision-{etat} {{ color: {texte}; background: {fond}; }}")

    regles += [
        "  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }",
        "  th, td { text-align: left; padding: 0.6rem 0.5rem;",
        f"    border-bottom: 1px solid {COULEURS['secondaire'][1]}; }}",
        f"  caption {{ text-align: left; color: {COULEURS['secondaire'][0]};",
        "    padding-bottom: 0.5rem; }",
        "  /* Le focus doit rester visible : on epaissit, on ne supprime pas. */",
        f"  a:focus, button:focus, input:focus {{ outline: 3px solid {COULEURS['texte'][0]};",
        "    outline-offset: 2px; }",
        "  label { display: block; font-weight: 600; margin-bottom: 0.25rem; }",
        "  input[type=text] { padding: 0.5rem; width: 100%; max-width: 22rem;",
        f"    border: 1px solid {COULEURS['secondaire'][0]}; border-radius: 0.2rem; }}",
        "  button { margin-top: 0.75rem; padding: 0.6rem 1.2rem; font-size: 1rem;",
        f"    color: {COULEURS['texte'][1]}; background: {COULEURS['texte'][0]};",
        "    border: 0; border-radius: 0.2rem; cursor: pointer; }",
        f"  .discret {{ color: {COULEURS['secondaire'][0]}; font-size: 0.95rem; }}",
        "  .saut { position: absolute; left: -9999px; }",
        "  .saut:focus { position: static; }",
    ]
    return "\n".join(regles)


def ligne_motif(rang, facteur):
    """Une ligne du tableau des motifs.

    Le sens est ecrit ("defavorable"), jamais signale par la seule couleur.
    """
    valeur = facteur.get("valeur")
    valeur = "non renseignée" if valeur in (None, "") else str(valeur)
    return (
        "        <tr>"
        f"<td>{rang}</td>"
        f"<td>{escape(str(facteur['libelle']))}</td>"
        f"<td>{escape(valeur)}</td>"
        f"<td>{escape(str(facteur['sens']))}</td>"
        "</tr>"
    )


def construire(decision):
    """Rend la page HTML d'une decision journalisee.

    Fonction pure : elle prend un dictionnaire et rend une chaine. C'est ce qui
    permet aux tests de verifier les criteres RGAA sans lancer de serveur ni de
    navigateur.
    """
    etat = decision["decision"]
    libelle = LIBELLES_DECISION.get(etat, etat)
    probabilite = float(decision["probabilite_defaut"]) * 100
    seuil = float(decision["seuil_applique"]) * 100

    motifs = "\n".join(
        ligne_motif(rang, facteur)
        for rang, facteur in enumerate(decision.get("facteurs", []), start=1)
    )

    revue = ""
    if decision.get("revue_humaine"):
        analyste = escape(str(decision.get("identifiant_analyste") or "non précisé"))
        revue = (
            "      <h2>Réexamen</h2>\n"
            f"      <p>Cette décision a été réexaminée par&nbsp;: {analyste}.</p>\n"
        )
    elif decision.get("revue_humaine_requise"):
        revue = (
            "      <h2>Demander un réexamen</h2>\n"
            "      <p>Vous avez le droit d'obtenir l'intervention d'une personne "
            "sur cette décision (article&nbsp;22 du RGPD).</p>\n"
            f'      <form method="post" action="/decisions/{decision["id_decision"]}/revue-formulaire">\n'
            '        <label for="analyste">Identifiant de l\'analyste</label>\n'
            '        <input type="text" id="analyste" name="identifiant_analyste" '
            'autocomplete="username">\n'
            "        <button type=\"submit\">Enregistrer le réexamen</button>\n"
            "      </form>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Décision n° {decision["id_decision"]} — CrediScore</title>
  <style>
{feuille_de_style()}
  </style>
</head>
<body>
  <a class="saut" href="#contenu">Aller au contenu</a>
  <main id="contenu">
    <h1>Décision n°&nbsp;{decision["id_decision"]}</h1>
    <p class="decision decision-{escape(etat)}">{libelle}</p>

    <p>{EXPLICATIONS.get(etat, "")}</p>

    <h2>Éléments chiffrés</h2>
    <p>Probabilité de défaut estimée&nbsp;: <strong>{nombre(probabilite)}&nbsp;%</strong>.<br>
       Seuil appliqué par l'établissement&nbsp;: <strong>{nombre(seuil)}&nbsp;%</strong>.</p>

    <h2>Motifs de la décision</h2>
    <table>
      <caption>Les cinq éléments ayant le plus pesé, du plus au moins influent.</caption>
      <thead>
        <tr>
          <th scope="col">Rang</th>
          <th scope="col">Élément examiné</th>
          <th scope="col">Valeur de votre dossier</th>
          <th scope="col">Sens</th>
        </tr>
      </thead>
      <tbody>
{motifs}
      </tbody>
    </table>

{revue}
    <h2>Traçabilité</h2>
    <p class="discret">
      Décision rendue le {escape(str(decision["horodatage"]))}<br>
      Modèle&nbsp;: {escape(str(decision["version_modele"]))}
    </p>
  </main>
</body>
</html>
"""
