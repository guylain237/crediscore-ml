# Note d'équité — protocole de non-discrimination

**Livrable du Bloc 1 — Certification Architecte en IA**
**Auteur :** Tagne Guylain Florian · **Version 1.0** · **16/08/2026**
**Application de la politique P-4 du [plan de gouvernance](gouvernance.md)**

---

## 0. La règle méthodologique qui fonde ce document

**Les seuils sont fixés maintenant, avant toute mesure.**

Ce document est rédigé le 16/08. Les mesures d'équité sont produites le 28/08.
L'ordre n'est pas un hasard : un seuil choisi après avoir vu les résultats n'est
pas un seuil, c'est une justification. En figeant les seuils par avance, on
s'interdit l'ajustement rétrospectif — celui qui consiste à décréter acceptable
ce qu'on a obtenu.

Les seuils du §4 ne peuvent être modifiés que par **décision unanime du comité
d'équité**, tracée dans `decisions.md` (§10 du plan de gouvernance). Les
résultats du §8 seront reportés **tels que mesurés**, favorables ou non.

---

## 1. État des lieux : les disparités existent avant le modèle

Mesuré sur les 307 511 dossiers d'`application_train`, **avant toute
modélisation**. Ces chiffres décrivent la réalité observée, pas un défaut du
système.

### 1.1 Genre

| `CODE_GENDER` | Effectif | Taux de défaut |
|---|---|---|
| F | 202 448 | **7,00 %** |
| M | 105 059 | **10,14 %** |
| XNA | **4** | — |

Écart : **3,14 points**, soit un risque 1,45 fois supérieur chez les hommes.

### 1.2 Âge

| Tranche | Effectif | Taux de défaut |
|---|---|---|
| 18–25 ans | 12 233 | **12,29 %** |
| 26–35 ans | 72 429 | 10,66 % |
| 36–50 ans | 119 454 | 8,12 % |
| 51–65 ans | 95 519 | 5,88 % |
| 65 ans et + | 7 876 | **3,66 %** |

Écart : **8,63 points**, soit un rapport de **1 à 3,4** entre la tranche la plus
risquée et la moins risquée.

### 1.3 Situation familiale

| `NAME_FAMILY_STATUS` | Effectif | Taux de défaut |
|---|---|---|
| Married | 196 432 | 7,56 % |
| Single / not married | 45 444 | 9,81 % |
| Civil marriage | 29 775 | 9,94 % |
| Separated | 19 770 | 8,19 % |
| Widow | 16 088 | 5,82 % |
| Unknown | **2** | — |

### 1.4 Ce que ces chiffres imposent

**Premier constat : exclure une variable ne supprime pas la discrimination.**
L'âge est retiré des variables prédictives (P-4), mais il reste **fortement
structurant du risque réel**. Le modèle le reconstruira par des variables
corrélées — ancienneté d'emploi, statut de retraité (`NAME_INCOME_TYPE`),
ancienneté d'enregistrement, historique de crédit long. C'est le mécanisme de la
**discrimination indirecte**, et c'est précisément pourquoi le protocole ne se
contente pas de l'exclusion : il **mesure** (§4) et **traque les proxys** (§6).

**Second constat : la parité démographique n'est pas le bon critère principal
ici.** Les taux de défaut diffèrent réellement entre groupes. Exiger des taux
d'acceptation identiques imposerait soit d'accepter des dossiers plus risqués
chez les hommes, soit de refuser des femmes solvables. Le critère retenu est
donc l'**égalité des chances** — voir §3.

**Troisième constat : deux groupes sont statistiquement inexploitables.**
`XNA` (4 individus) et `Unknown` (2 individus). Ils seront **déclarés exclus des
métriques avec leur effectif**, jamais silencieusement écartés.

---

## 2. Attributs protégés et sous-populations

| Attribut | Statut comme variable prédictive | Statut pour l'audit | Sous-populations |
|---|---|---|---|
| `CODE_GENDER` | ⛔ **interdit** (P-4) | ✅ conservé | F · M *(XNA exclu, n = 4)* |
| `DAYS_BIRTH` (âge) | ⛔ **interdit** (P-4) | ✅ conservé | 18-25 · 26-35 · 36-50 · 51-65 · 65+ |
| `NAME_FAMILY_STATUS` | ⛔ **interdit** (P-4) | ✅ conservé | Married · Single · Civil marriage · Separated · Widow |

**Règle d'effectif minimal : 500 individus dans le jeu de test.** En dessous, la
métrique n'est pas calculée et le groupe est déclaré avec son effectif. Vérifié :
seul `XNA` tombe sous ce seuil ; toutes les tranches d'âge le franchissent.

**Base juridique de la conservation.** Ces attributs ne relèvent pas des
catégories particulières de l'article 9 du RGPD. Leur conservation à seule fin de
mesure des biais découle de l'obligation d'examen et d'atténuation posée par
l'**AI Act, art. 10 §2 f) et g)** : on ne peut pas démontrer une absence de
discrimination sans mesurer sur les groupes concernés.

---

## 3. Convention d'orientation — à lire avant les métriques

Le modèle prédit le **défaut**. Une prédiction positive vaut donc **refus**. Pour
éviter toute confusion, toutes les métriques ci-dessous sont exprimées du point
de vue de **l'issue favorable au demandeur : l'acceptation**.

| Terme | Définition retenue |
|---|---|
| Taux d'acceptation | P(score < seuil \| groupe) |
| **Égalité des chances** | Parmi les demandeurs **qui n'auraient pas fait défaut**, le taux d'acceptation doit être comparable entre groupes |
| Parité démographique | Taux d'acceptation comparables entre groupes, sans condition |

L'égalité des chances est le **critère principal** : elle mesure le préjudice
subi par une personne solvable injustement refusée — le tort concret que la
réglementation vise. Elle tolère un écart d'acceptation justifié par un risque
réellement différent, ce que la parité démographique interdirait à tort.

---

## 4. Métriques et seuils — figés le 16/08/2026

Deux niveaux : **vigilance** déclenche une analyse ; **arrêt** interdit le
déploiement.

| # | Métrique | Rôle | Vigilance | **Arrêt** |
|---|---|---|---|---|
| **M-1** | **Écart d'égalité des chances** — max des \|TNR_a − TNR_b\| | **principal** | > 0,03 | **> 0,05** |
| **M-2** | **Écart d'odds égalisées** — max(\|ΔTNR\|, \|ΔTPR\|) | principal | > 0,05 | **> 0,08** |
| **M-3** | **Écart de calibration** — \|proba moyenne − taux observé\| par groupe | **principal** | > 0,015 | **> 0,025** |
| **M-4** | Rapport d'impact disproportionné — min/max des taux d'acceptation | surveillance | < 0,90 | **< 0,80** |
| **M-5** | Écart de parité démographique — max des \|acceptation_a − acceptation_b\| | surveillance | > 0,10 | *pas de seuil d'arrêt* |
| **M-6** | Écart d'AUC entre groupes | surveillance | > 0,03 | **> 0,05** |

### Pourquoi ces seuils

**M-1 à 0,05** : au-delà de 5 points d'écart sur le taux d'acceptation des
demandeurs solvables, l'écart cesse d'être imputable au bruit d'échantillonnage
sur nos effectifs de test (le plus petit groupe exploitable compte ≈ 1 575
individus en test) et devient un préjudice systématique.

**M-3, la métrique la plus exigeante et la plus ignorée.** Si le modèle annonce
8 % de risque à deux groupes dont les taux réels sont 6 % et 11 %, il est
*discriminatoire même à seuil unique* : la probabilité affichée ne signifie pas
la même chose selon la personne. C'est une exigence directe de P-5 — une
probabilité communiquée doit être juste, pas seulement bien ordonnée.

**M-4 à 0,80** : c'est la « règle des quatre cinquièmes », héritée du droit
américain de l'emploi. Elle n'a **aucune valeur juridique en droit européen du
crédit** et figure ici comme **indicateur de surveillance**, pas comme norme.
Le dire évite de se voir reprocher de l'invoquer à tort.

**M-5 sans seuil d'arrêt** : voir §3. Les taux de défaut diffèrent réellement de
3,14 points selon le genre. Imposer la parité stricte reviendrait à discriminer
dans l'autre sens. La métrique est **publiée pour transparence**, elle ne bloque
pas.

---

## 5. Protocole de mesure

| | |
|---|---|
| **Quand** | À chaque entraînement, avant toute mise en production. Puis à chaque réentraînement, et au minimum une fois par an |
| **Sur quoi** | Le **jeu de test scellé** (61 502 dossiers, D-005) — jamais sur l'entraînement, qui donnerait des écarts optimistes |
| **Au seuil** | Le seuil de décision retenu par la direction des risques, pas à 0,5 |
| **Outil** | `fairlearn` (`MetricFrame`) — déjà dans `requirements.txt` |
| **Sortie** | Tableau chiffré par attribut × sous-population, versionné et joint à MLflow |
| **Qui décide** | Comité d'équité (§9.3 du plan de gouvernance) |

**Un dépassement de seuil d'arrêt interdit le déploiement.** Pas de dérogation
sans décision unanime du comité, motivée et tracée dans `decisions.md`.

---

## 6. Détection des proxys (contrôle C-3)

L'exclusion d'une variable ne suffit pas : encore faut-il vérifier qu'aucune
autre ne la reconstitue. Le §1.4 montre que le risque est réel pour l'âge.

**Procédure, exécutée le 28/08 :**

1. Calculer la corrélation de **chaque variable du modèle** avec chaque attribut
   protégé (Spearman pour le continu, V de Cramér pour le catégoriel).
2. Toute variable dont |corrélation| **> 0,50** avec un attribut protégé est
   déclarée **proxy candidat** et instruite individuellement.
3. Pour chaque proxy candidat, trancher :
   - **justification métier autonome** → conservée, justification écrite ;
   - **pas de justification hors de l'attribut protégé** → retirée.
4. Consigner la décision dans `decisions.md`, avec le chiffre.

**Cas déjà identifiés comme à instruire** : `DAYS_EMPLOYED`,
`DAYS_REGISTRATION`, `DAYS_ID_PUBLISH`, `NAME_INCOME_TYPE` (modalité
« Pensioner »), `ORGANIZATION_TYPE` (modalité « XNA », fréquente chez les
retraités).

> Un seuil de corrélation ne détecte qu'un proxy **direct**. Une combinaison de
> trois variables faiblement corrélées peut reconstituer l'âge sans qu'aucune ne
> dépasse le seuil. C'est la raison d'être des métriques M-1 à M-3 : elles
> mesurent l'**effet** sur les personnes, indépendamment du mécanisme.

---

## 7. Échelle de remédiation

En cas de dépassement, dans cet ordre — chaque étape n'est engagée que si la
précédente a échoué.

| # | Action | Licéité |
|---|---|---|
| 1 | Instruire les proxys (§6) et retirer les variables sans justification autonome | ✅ |
| 2 | Rééquilibrer l'échantillon d'entraînement (repondération par groupe) | ✅ l'attribut n'est utilisé qu'à l'entraînement |
| 3 | Optimisation sous contrainte d'équité (`fairlearn.reductions.ExponentiatedGradient`, contrainte d'odds égalisées) | ✅ contrainte à l'apprentissage, pas à l'inférence |
| 4 | Recalibrer les probabilités globalement | ✅ |
| 5 | Saisir le comité d'équité — arbitrage explicite | ✅ |
| 6 | **Refuser le déploiement** | ✅ toujours possible |

### L'option écartée, et pourquoi

**Appliquer un seuil de décision différent selon le genre ou l'âge est exclu.**
C'est ce que fait `fairlearn.postprocessing.ThresholdOptimizer`, et c'est
techniquement le moyen le plus rapide d'égaliser les métriques.

Mais traiter deux dossiers identiques différemment **en raison du genre** est une
**discrimination directe**, prohibée — là où la discrimination indirecte peut
être justifiée par un objectif légitime et des moyens proportionnés. Corriger une
discrimination indirecte par une discrimination directe est juridiquement
régressif, quel que soit le gain sur les métriques.

Cette distinction est la plus importante de la présente note.

---

## 8. Résultats — à compléter le 28/08/2026

> **Section volontairement vide à ce stade.** Les seuils du §4 sont figés ; les
> chiffres viendront s'y confronter. Aucune ligne du §4 ne sera modifiée après
> lecture des résultats.

### 8.1 Genre

| Métrique | Valeur mesurée | Seuil | Verdict |
|---|---|---|---|
| M-1 — égalité des chances | *à mesurer* | 0,05 | — |
| M-2 — odds égalisées | *à mesurer* | 0,08 | — |
| M-3 — calibration | *à mesurer* | 0,025 | — |
| M-4 — impact disproportionné | *à mesurer* | 0,80 | — |
| M-5 — parité démographique | *à mesurer* | *surveillance* | — |
| M-6 — écart d'AUC | *à mesurer* | 0,05 | — |

### 8.2 Âge · 8.3 Situation familiale

*(mêmes tableaux, à compléter)*

### 8.4 Le prix de la conformité (décision D-008)

| Modèle | AUC-ROC | Écart |
|---|---|---|
| Conforme — sans attributs protégés | *à mesurer* | référence |
| Témoin — avec attributs protégés | *à mesurer* | *à mesurer* |

Rappel : `DAYS_BIRTH` est la **quatrième variable la plus corrélée à la cible**
(|r| = 0,078). Son exclusion a un coût, que ce tableau chiffrera. Le modèle
témoin **n'est jamais déployé** : il documente un arbitrage, il ne sert pas.

---

## 9. Limites reconnues

Trois limites qui seront **énoncées en soutenance**, pas dissimulées.

**L-1 — Aucune donnée d'origine ni d'appartenance ethnique.** Le jeu de données
n'en contient pas. La discrimination fondée sur l'origine — pourtant un critère
prohibé majeur en droit français — est donc **non mesurable ici**. En
établissement réel, la question devrait être traitée par des méthodes
d'estimation indirecte encadrées, sous supervision du DPO.

**L-2 — Biais de sélection.** Le taux de 8,07 % est celui des dossiers
**acceptés** par la politique d'octroi en vigueur. Les dossiers refusés n'ont pas
de défaut observé. Le modèle apprend donc le risque *conditionnellement à une
acceptation passée*, laquelle pouvait déjà être discriminatoire. Une
discrimination héritée du passé peut ainsi passer inaperçue (risque R-4). La
correction — *reject inference* — dépasse le cadre du démonstrateur.

**L-3 — Groupes trop petits.** `XNA` (4 individus) et `Unknown` (2) : aucune
métrique fiable. Déclarés, non mesurés.

---

## 10. Comité d'équité

**Composition :** DPO (préside) · direction des risques · architecte IA · un
représentant métier · un profil externe à l'équipe de développement.

**Saisine :** de droit à chaque entraînement et à chaque réentraînement ; à la
demande de tout membre ; sur réclamation fondée d'un demandeur.

**Pouvoirs :**

- valider ou refuser toute modification de `configs/sensitive_features.yaml` ;
- valider ou refuser toute modification des seuils du §4 (**unanimité requise**) ;
- **exiger le retrait d'un modèle en production** en cas de discrimination avérée.

**Traçabilité :** chaque séance produit une entrée dans `docs/registre_revues.md`.
Une revue sans trace écrite est réputée ne pas avoir eu lieu.

---

## 11. Journal des révisions

| Version | Date | Modification |
|---|---|---|
| 1.0 | 16/08/2026 | Création. État des lieux mesuré, métriques M-1 à M-6, **seuils figés avant mesure**, procédure de détection des proxys, échelle de remédiation, limites déclarées. |
