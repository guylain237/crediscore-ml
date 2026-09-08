# Accessibilité numérique — analyse de périmètre et déclaration

**Version 1.0 — 08/09/2026** · Politique **P-11** du [plan de gouvernance](gouvernance.md)

> **Ce document ne déclare pas un taux de conformité.** Il dit ce qui a été
> vérifié, comment, et ce qui reste à auditer. Annoncer « 87 % de conformité »
> sans avoir évalué les critères manuels serait un chiffre inventé — le §6
> explique précisément ce qui manque pour pouvoir le produire.

---

## 1. Ce qu'est le RGAA, et à qui il s'impose

Le **Référentiel Général d'Amélioration de l'Accessibilité**, version 4.1, est
la déclinaison française de la norme internationale **WCAG 2.1 niveau AA**. Il
compte **106 critères** répartis en 13 thèmes.

| | |
|---|---|
| **Base légale** | loi du 11 février 2005, art. 47 · décret 2019-768 · directive (UE) 2016/2102 |
| **Assujettis** | secteur public, et **entreprises privées dont le chiffre d'affaires en France dépasse 250 M€** |
| **Périmètre matériel** | « sites internet, intranets, extranets, progiciels, applications mobiles et mobilier urbain numérique » |
| **Obligations** | déclaration d'accessibilité, schéma pluriannuel, mention du taux de conformité |
| **Sanction** | jusqu'à 50 000 € par service et par an (décret 2023-931) |

---

## 2. Ce qui, dans CrediScore, entre dans le périmètre — et ce qui n'y entre pas

### 2.1 Hors périmètre, et pourquoi

| Composant | Motif |
|---|---|
| **API `POST /score`** | interface machine-à-machine ; aucun utilisateur humain ne la consulte |
| **Page `/docs`** | Swagger généré par FastAPI — outil de développement, non destiné aux demandeurs |
| **Airflow, MLflow, Grafana, Prometheus** | progiciels tiers non développés par le projet ; leur accessibilité relève de leurs éditeurs |

> Un intranet **est** dans le périmètre du RGAA pour un organisme assujetti.
> Les outils ci-dessus le seraient donc si l'établissement les mettait à
> disposition de ses agents. Mais le projet ne les a pas développés : la
> conformité se traiterait alors par le choix du produit, à l'achat, et non par
> une correction de code.

### 2.2 Dans le périmètre

**Une seule page, et c'est la plus importante du projet :**

```
GET /decisions/{id}/restitution
```

C'est l'écran qui annonce sa décision au demandeur et lui présente les cinq
motifs. Un établissement de crédit dépasse très largement le seuil de 250 M€ :
cette page sera assujettie.

### 2.3 Pourquoi cette page existe — elle n'a pas été ajoutée pour l'audit

Le contrôle **C-12** impose un réexamen humain, et la zone grise l'impose
**avant** la décision sur 11,7 % des dossiers. Jusqu'au 08/09/2026, l'analyste
chargé de ce réexamen recevait du JSON brut, et le demandeur ne recevait rien.

L'article 22 du RGPD donne le droit à une explication ; le projet la calculait
en 24 millisecondes et ne l'affichait nulle part. **La page comble ce trou, et
c'est le RGAA qui l'a rendu visible.**

---

## 3. Le point qui justifie de traiter le sujet sérieusement

> **L'article 22 du RGPD et le RGAA portent sur le même écran.**
>
> L'article 22 donne le droit à une explication. Le RGAA exige qu'elle soit
> **perçue**. Un demandeur aveugle doit pouvoir *entendre* ses cinq motifs avec
> son lecteur d'écran ; un demandeur daltonien ne doit pas dépendre d'une
> pastille rouge pour comprendre qu'il est refusé.
>
> **Une explication imperceptible n'est pas une explication.** Elle est
> seulement écrite.

Le travail déjà fait sur la lisibilité — les 223 variables libellées en
français, le contrôle C-5 qui échoue s'il en manque une — en est la moitié
amont. Le RGAA en est la moitié aval.

---

## 4. Ce que la page respecte, et comment c'est vérifié

Chaque ligne correspond à un test de `tests/test_restitution.py`. Le numéro de
critère est cité dans le test : on remonte du test au référentiel.

| Critère | Exigence | Comment la page y répond |
|---|---|---|
| **3.1** | aucune information par la seule couleur | la décision est écrite : « Refusée », « Accordée », « Réexamen par une personne requis » ; le sens de chaque motif est le mot « favorable » ou « défavorable » |
| **3.2** | contraste ≥ 4,5:1 | **calculé**, pas estimé — la luminance relative WCAG 2.1 est appliquée à chaque paire de couleurs du module |
| **5.4 / 5.5** | titre de tableau associé et pertinent | `<caption>` : « Les cinq éléments ayant le plus pesé, du plus au moins influent » |
| **5.6 / 5.7** | en-têtes identifiés, technique appropriée | `<th scope="col">` sur les quatre colonnes |
| **8.1** | doctype présent | `<!DOCTYPE html>` |
| **8.3 / 8.4** | langue déclarée et pertinente | `<html lang="fr">` |
| **8.5 / 8.6** | titre de page présent et pertinent | « Décision n° 42 — CrediScore » |
| **9.1** | titres hiérarchisés sans saut | un seul `h1`, puis des `h2` ; vérifié niveau par niveau |
| **11.1** | chaque champ a une étiquette | `<label for="analyste">` lié au champ par son `id` |
| **12.6** | zones de regroupement atteignables | `<main id="contenu">` |
| **12.7** | lien d'évitement | « Aller au contenu », visible à la prise de focus |

**Et un point qui n'est pas un critère numéroté mais relève de la même
exigence** : les nombres sont écrits à la française. « 12,2 % » et non
« 12.2 % » — un lecteur d'écran prononce le point comme un point, ce qui n'a
pas de sens à l'oral.

### 4.1 Choix techniques qui servent l'accessibilité

**Aucun JavaScript.** Lire sa décision ne dépend ni d'un script, ni d'un
navigateur récent, ni d'une connexion rapide. Le formulaire de réexamen
fonctionne en HTML pur.

**Le focus reste visible.** L'`outline` est épaissie, jamais supprimée — la
suppression du contour de focus est l'un des défauts d'accessibilité les plus
répandus, et l'un des plus faciles à éviter.

**Une valeur absente est écrite « non renseignée »**, jamais laissée vide. Une
cellule vide est annoncée « vide » par un lecteur d'écran, ce qui ne distingue
pas l'absence de donnée d'un défaut d'affichage.

---

## 5. Comment la vérification est faite

```bash
.venv/Scripts/python.exe -m pytest tests/test_restitution.py -v
```

**21 tests.** Ils analysent le HTML produit — structure, attributs, couleurs —
sans lancer de serveur ni de navigateur, ce qui les rend exécutables en
intégration continue à chaque poussée.

**Le calcul de contraste est lui-même testé.** Sans cela, une fonction qui
renverrait toujours 21 ferait passer tous les autres tests :

```python
contraste("#000000", "#ffffff") == 21,00     # noir sur blanc
contraste("#767676", "#ffffff") ==  4,54     # le gris de référence, à la limite
```

**Les tests ont été vérifiés en régression le 08/09/2026** — chaque contrôle a
été cassé volontairement pour confirmer qu'il rougit :

| Régression introduite | Détection |
|---|---|
| `lang="fr"` retiré | ✅ 1 échec |
| couleur du refus dégradée à `#d98b8b` | ✅ 1 échec — « contraste insuffisant : refuse 2,26 pour 1 » |
| `scope="col"` retiré des en-têtes | ✅ 1 échec |

---

## 6. Ce qui n'est PAS vérifié — et pourquoi aucun taux n'est déclaré

Un audit RGAA évalue les **106 critères**, dont beaucoup exigent un jugement
humain. Ceux-ci n'ont pas été évalués :

| Ce qui manque | Pourquoi un programme n'y suffit pas |
|---|---|
| **Pertinence** des textes et des titres | un titre peut être présent et ne rien vouloir dire |
| **Ordre de lecture** réel | l'ordre du code peut différer de l'ordre visuel |
| **Restitution au lecteur d'écran** | NVDA, JAWS et VoiceOver ne se comportent pas identiquement |
| **Zoom à 200 % et reflow à 320 px** | demande un rendu réel dans un navigateur |
| **Parcours complet au clavier** | l'ordre de tabulation doit être éprouvé, pas déduit |
| **Validité du code source** (8.2) | demande le validateur du W3C |

**Conséquence assumée :**

> **Statut de conformité au 08/09/2026 : non audité.**
>
> Aucun taux n'est déclaré. La page a été construite selon les critères du §4 et
> ceux-ci sont vérifiés automatiquement, mais un taux de conformité au sens du
> décret 2019-768 suppose l'évaluation des 106 critères par un auditeur — y
> compris ceux du §6.

---

## 7. Déclaration d'accessibilité — modèle à compléter après audit

*Ce cadre reprend la structure imposée par l'arrêté du 5 septembre 2019. Il est
prêt à être renseigné dès que l'audit du §6 aura été conduit.*

> **Déclaration d'accessibilité**
>
> *[Établissement]* s'engage à rendre son service accessible, conformément à
> l'article 47 de la loi n° 2005-102 du 11 février 2005.
>
> Cette déclaration s'applique à **l'écran de restitution des décisions de
> crédit**.
>
> **État de conformité** : *à compléter — non conforme / partiellement conforme /
> totalement conforme.*
>
> **Résultats des tests** : l'audit de conformité réalisé par *[auditeur]*
> révèle que **X %** des critères du RGAA 4.1 sont respectés.
>
> **Contenus non accessibles** : *à compléter.*
>
> **Établissement de cette déclaration** : le *[date]*, à l'aide de *[outils]*.
>
> **Retour d'information et contact** : *[adresse]*. Si vous n'obtenez pas de
> réponse, vous pouvez saisir le Défenseur des droits.

---

## 8. Ce qui reste à faire

| # | Action | Responsable | Échéance |
|---|---|---|---|
| 1 | Audit RGAA complet de l'écran de restitution | prestataire spécialisé | avant mise en production |
| 2 | Test réel au lecteur d'écran (NVDA et VoiceOver) | équipe produit | avant l'audit |
| 3 | Vérification du zoom 200 % et du reflow à 320 px | équipe produit | avant l'audit |
| 4 | Validation W3C du code source (critère 8.2) | équipe produit | immédiat |
| 5 | Publication de la déclaration du §7, complétée | DPO | à la mise en production |
| 6 | Schéma pluriannuel d'accessibilité | direction | exercice suivant |

---

## 9. Journal des révisions

| Version | Date | Modification |
|---|---|---|
| 1.0 | 08/09/2026 | Création. Analyse de périmètre, écran de restitution créé et vérifié sur 11 critères automatisables, 21 tests dont la régression est éprouvée, déclaration en attente d'audit. **Aucun taux de conformité déclaré.** |
