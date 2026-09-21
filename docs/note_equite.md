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
| `CODE_GENDER` | ⛔ **interdit** (P-4) | conservé | F · M *(XNA exclu, n = 4)* |
| `DAYS_BIRTH` (âge) | ⛔ **interdit** (P-4) | conservé | 18-25 · 26-35 · 36-50 · 51-65 · 65+ |
| `NAME_FAMILY_STATUS` | ⛔ **interdit** (P-4) | conservé | Married · Single · Civil marriage · Separated · Widow |

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
| 1 | Instruire les proxys (§6) et retirer les variables sans justification autonome | licite |
| 2 | Rééquilibrer l'échantillon d'entraînement (repondération par groupe) | licite — l'attribut n'est utilisé qu'à l'entraînement |
| 3 | Optimisation sous contrainte d'équité (`fairlearn.reductions.ExponentiatedGradient`, contrainte d'odds égalisées) | licite — contrainte à l'apprentissage, pas à l'inférence |
| 4 | Recalibrer les probabilités globalement | licite |
| 5 | Saisir le comité d'équité — arbitrage explicite | licite |
| 6 | **Refuser le déploiement** | licite — toujours possible |

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

## 8. Résultats — mesurés le 31/08/2026

> Les seuils du §4 ont été figés le 16/08/2026, avant tout entraînement.
> **Aucun n'a été modifié après lecture des résultats.** Deux d'entre eux ne
> sont pas respectés ; la section 8.6 explique pourquoi, et la 8.8 dit ce qui
> en découle.

### 8.0 Conditions de la mesure

| | |
|---|---|
| Modèle | LightGBM calibré (isotonique), 223 variables |
| Jeu | test uniquement — 61 503 dossiers, jamais vus à l'entraînement |
| Seuil de décision | 0,095, issu de la courbe de coût |
| Taux d'acceptation global | 70,2 % |
| Script | `src/fairness/audit.py`, résultats dans `docs/resultats_equite.csv` |

Les attributs protégés proviennent de `clean/attributs_sensibles`, la zone où
le pipeline les **dévie** au lieu de les détruire (`construire_socle.py`). Le
modèle ne lit jamais cette zone ; l'audit est le seul code du dépôt à joindre
les deux.

### 8.1 Genre

| Groupe | n | Défaut réel | Annoncé | Accepté | **TNR** | AUC |
|---|---|---|---|---|---|---|
| F | 40 283 | 6,77 % | 7,46 % | 73,3 % | **76,2 %** | 0,782 |
| M | 21 219 | 10,55 % | 9,44 % | 64,4 % | **68,6 %** | 0,767 |
| XNA | 1 | — | — | — | — | — |

| Métrique | Mesurée | Seuil d'arrêt | Verdict |
|---|---|---|---|
| M-1 — égalité des chances | **0,0763** | 0,05 | **ARRÊT** |
| M-2 — odds égalisées | 0,0763 | 0,08 | vigilance |
| M-3 — calibration | 0,0110 | 0,025 | conforme |
| M-4 — impact disproportionné | 0,8774 | 0,80 | vigilance |
| M-5 — parité démographique | 0,0899 | *surveillance* | conforme |
| M-6 — écart d'AUC | 0,0155 | 0,05 | conforme |

**Le groupe défavorisé est celui des hommes.** À solvabilité égale, 68,6 % des
hommes sont acceptés contre 76,2 % des femmes. Ce sens est l'inverse de
l'attendu ; il est rapporté tel quel, la note n'ayant pas à choisir la
direction qui l'arrange.

Il s'explique en partie par la donnée elle-même : le taux de défaut masculin
est de 10,55 % contre 6,77 %. Mais l'écart de 7,6 points dépasse le seuil
d'arrêt, et le groupe compte 21 219 individus en test — ce n'est pas du bruit.

### 8.2 Âge

| Tranche | n | Défaut réel | Annoncé | Accepté | **TNR** | **TPR** | AUC |
|---|---|---|---|---|---|---|---|
| 20-30 ans | 9 153 | 11,82 % | 12,14 % | 51,4 % | **55,8 %** | 81,9 % | 0,764 |
| 30-40 ans | 16 432 | 9,55 % | 9,03 % | 65,8 % | 69,9 % | 73,3 % | 0,784 |
| 40-50 ans | 15 293 | 7,42 % | 7,52 % | 73,3 % | 76,5 % | 65,9 % | 0,782 |
| 50-60 ans | 13 485 | 6,01 % | 6,67 % | 77,1 % | 79,4 % | 59,1 % | 0,763 |
| 60-70 ans | 7 140 | 5,17 % | 5,10 % | 85,1 % | **86,6 %** | 42,3 % | 0,726 |

| Métrique | Mesurée | Seuil d'arrêt | Verdict |
|---|---|---|---|
| M-1 — égalité des chances | **0,3082** | 0,05 | **ARRÊT** |
| M-2 — odds égalisées | **0,3961** | 0,08 | **ARRÊT** |
| M-3 — calibration | 0,0067 | 0,025 | conforme |
| M-4 — impact disproportionné | **0,6032** | 0,80 | **ARRÊT** |
| M-5 — parité démographique | 0,3378 | *surveillance* | vigilance |
| M-6 — écart d'AUC | **0,0577** | 0,05 | **ARRÊT** |

**C'est ici que le système échoue, et largement.** Parmi les demandeurs qui
auraient remboursé, 55,8 % des 20-30 ans sont acceptés contre 86,6 % des
60-70 ans : **30,8 points d'écart**, six fois le seuil d'arrêt.

Le modèle n'a jamais vu l'âge. Il l'a reconstitué — c'est exactement ce que le
§1.4 redoutait et ce que le contrôle C-3 a mesuré (voir 8.5).

Trois observations que la seule métrique M-1 ne montre pas :

**La colonne TPR s'effondre avec l'âge** : parmi les demandeurs qui font
réellement défaut, on en refuse 81,9 % chez les 20-30 ans et seulement 42,3 %
chez les 60-70 ans. Le système est donc doublement asymétrique : plus sévère
avec les jeunes solvables, plus laxiste avec les seniors défaillants. Le
préjudice est symétrique du côté de l'établissement — plus de la moitié des
défauts seniors passent.

**L'AUC baisse chez les 60-70 ans** (0,726 contre 0,784 chez les trentenaires).
Le modèle ne se contente pas de traiter ce groupe différemment : il le
**prédit moins bien**. M-6 le capte, à 0,0577.

**M-3 est conforme partout, et c'est décisif.** L'écart de calibration
plafonne à 0,0067. Le modèle annonce 12,14 % aux 20-30 ans, il s'en produit
11,82 %. Il ne se trompe donc pas sur les jeunes : il a raison. C'est
l'application d'un **seuil unique à des probabilités honnêtes** qui produit
l'écart, non une erreur d'estimation. Cette distinction commande toute la
remédiation.

### 8.3 Situation familiale

| Groupe | n | Défaut réel | Accepté | **TNR** | AUC |
|---|---|---|---|---|---|
| Mariés | 39 118 | 7,47 % | 71,8 % | 75,0 % | 0,787 |
| Veufs | 3 177 | 6,01 % | 79,4 % | **81,7 %** | 0,739 |
| Séparés | 3 975 | 8,73 % | 72,7 % | 75,7 % | 0,742 |
| Union libre | 6 091 | 9,97 % | 63,6 % | **67,9 %** | 0,778 |
| Célibataires | 9 142 | 9,83 % | 63,8 % | 67,9 % | 0,774 |
| Unknown | 2 | — | — | — | — |

| Métrique | Mesurée | Seuil d'arrêt | Verdict |
|---|---|---|---|
| M-1 — égalité des chances | **0,1376** | 0,05 | **ARRÊT** |
| M-2 — odds égalisées | **0,1894** | 0,08 | **ARRÊT** |
| M-3 — calibration | 0,0099 | 0,025 | conforme |
| M-4 — impact disproportionné | 0,8015 | 0,80 | vigilance |
| M-5 — parité démographique | 0,1576 | *surveillance* | vigilance |
| M-6 — écart d'AUC | 0,0476 | 0,05 | vigilance |

13,8 points séparent les veufs des célibataires et des couples en union libre.
Cet axe est **fortement confondu avec l'âge** — les veufs sont
mécaniquement plus âgés, les célibataires plus jeunes. Il n'est donc pas traité
comme un troisième problème indépendant : le corriger sur l'âge le corrigera en
grande partie ici.

### 8.4 Le prix de la conformité (décision D-008)

Modèle **témoin**, entraîné avec le genre, l'âge et la situation familiale.
Il n'est **ni déployé, ni enregistré sur disque** : `src/fairness/temoin.py`
le construit en mémoire et le laisse mourir avec le processus. C'est le seul
endroit du dépôt qui contourne volontairement le contrôle C-1.

| Modèle | Variables | AUC-ROC | AUC-PR |
|---|---|---|---|
| **Conforme** — celui qui est déployé | 223 | **0,7804** | 0,2699 |
| Témoin — avec les attributs protégés | 226 | 0,7843 | 0,2752 |
| **Prix de la conformité** | | **0,0039** | 0,0052 |

Place des attributs interdits dans le modèle témoin, quand on l'autorise à
les voir :

| Attribut | Usages | Rang sur 226 |
|---|---|---|
| Âge | 164 | **7ᵉ** |
| Genre | 48 | 57ᵉ |
| Situation familiale | 42 | 64ᵉ |

**Ce tableau se lit dans le mauvais sens si on n'y prend garde.** La lecture
naïve : « l'exclusion ne coûte que 0,0039 d'AUC, la conformité est presque
gratuite ». La lecture juste : l'âge serait la **septième variable la plus
utilisée sur 226** si on l'autorisait, et pourtant l'interdire ne coûte
presque rien.

Une seule explication tient : **l'information passe déjà par ailleurs.**
Le faible prix de la conformité n'est pas une preuve d'équité, c'est la mesure
de la fuite. Le §8.5 la localise.

### 8.5 Ce que le contrôle C-3 a trouvé

`src/fairness/proxys.py` mesure l'association de chacune des 223 variables avec
chaque attribut protégé — Spearman pour deux continues, V de Cramér sinon — et,
séparément, le pouvoir révélateur du **motif d'absence**. Seuil d'instruction :
0,50, fixé au §6 le 16/08.

| Variable | Attribut | Association | Décision |
|---|---|---|---|
| `DAYS_EMPLOYED_ANORMAL` | âge | 0,751 | **conservée**, justifiée |
| `FLAG_EMP_PHONE` | âge | 0,751 | **retirée** |
| `CNT_FAM_MEMBERS` | situation familiale | 0,607 | conservée, justifiée |
| `EXT_SOURCE_1` | âge | 0,600 | **conservée sous réserve** |
| `REVENU_PAR_PERSONNE` | situation familiale | 0,508 | conservée, justifiée |

Et par le motif d'absence, que la règle F5 imposait de regarder :

| Variable | Attribut | Association du trou | % absent |
|---|---|---|---|
| `DAYS_EMPLOYED` | âge | 0,751 | 18,0 % |
| `RATIO_ANCIENNETE` | âge | 0,751 | 18,0 % |
| `OCCUPATION_TYPE` | âge | 0,527 | 31,3 % |

**Instruction de chaque cas.**

**`FLAG_EMP_PHONE` — retirée.** Mesurée identique à `DAYS_EMPLOYED_ANORMAL`
sur **100,00 % des dossiers** (55 374 contre 55 374, douze exceptions). Deux
variables, une seule information. Aucune justification autonome ne survit à ce
constat : le retrait ne relève même pas de l'équité, mais de l'hygiène. On
conserve `DAYS_EMPLOYED_ANORMAL`, explicite et documentée dans le pipeline,
plutôt que celle du fournisseur, dont le nom cache le sens.

**`DAYS_EMPLOYED_ANORMAL` — conservée.** Le drapeau marque l'absence d'emploi
salarié déclaré : 83,4 % des 60-70 ans le portent contre 0,3 % des 20-30 ans.
C'est bien un proxy d'âge. Mais le statut d'emploi est un critère de
solvabilité **légitime et universel**, ce qui constitue la justification
autonome qu'exige le §6. À noter, contre l'intuition : les porteurs du drapeau
font **moins** défaut (5,40 % contre 8,66 %) — ce sont majoritairement des
retraités à pension stable. La variable joue ici *en faveur* des seniors.
Défaut de conception assumé : le jeu de données ne permet pas de distinguer
« retraité » de « sans emploi », deux situations de risque opposées.

**`EXT_SOURCE_1` — conservée sous réserve, et c'est le cas le plus gênant.**
Le score externe monte de 0,332 chez les 20-30 ans à 0,739 chez les 60-70 ans
(Spearman 0,600). Or c'est la **troisième variable du modèle** au sens SHAP.
Nous avons retiré l'âge par la porte et un fournisseur nous le rend par la
fenêtre, dans un score dont **nous ignorons la composition**.

C'est une difficulté de conformité à l'AI Act autant que d'équité : un système
à haut risque doit être explicable, et nous expliquons ici une décision par un
score que nous ne savons pas expliquer nous-mêmes.

> **Réserve P-10 (nouvelle).** La mise en production est conditionnée à
> l'obtention, auprès du fournisseur du score externe, de la liste des
> variables qui le composent et de l'attestation qu'aucun attribut protégé n'y
> figure. À défaut, `EXT_SOURCE_1`, `EXT_SOURCE_2` et `EXT_SOURCE_3` sont
> retirées. Le démonstrateur les conserve pour ne pas masquer le problème.

**`CNT_FAM_MEMBERS` et `REVENU_PAR_PERSONNE` — conservées.** La taille du foyer
révèle la situation familiale (2,51 personnes chez les mariés contre 1,10 chez
les veufs), et le revenu par personne en hérite mécaniquement, puisqu'il divise
par cette taille. Les deux mesurent une capacité de remboursement réelle :
justification autonome. `REVENU_PAR_PERSONNE` est une variable **que nous avons
construite** ; le lien lui a été transmis par sa formule, non découvert dans la
donnée.

**Les motifs d'absence — conservés.** Le trou de `DAYS_EMPLOYED` *est* le
drapeau d'anomalie, puisque le pipeline neutralise la sentinelle 365243 en
NULL. Même instruction, même conclusion.

### 8.6 Retirer les proxys ne suffit pas — c'est mesuré

`src/fairness/ablation.py` réentraîne le modèle sans les proxys, recalibre et
recalcule le seuil à chaque fois. Le tableau ci-dessous n'est pas une
projection.

| Scénario | Variables | AUC | **M-1 âge** | Coût | AUC perdue |
|---|---|---|---|---|---|
| Référence | 224 | 0,7813 | **0,3215** | 15,14 M€ | — |
| Sans proxys francs | 221 | 0,7761 | 0,3095 | 15,49 M€ | 0,0053 |
| Sans proxys **et** absences | 218 | 0,7739 | **0,2756** | 15,50 M€ | 0,0075 |

Retirer les six variables fait passer M-1 de 0,3215 à 0,2756 : **4,6 points
gagnés, pour 0,36 M€ et 0,0075 d'AUC**. On reste à cinq fois le seuil d'arrêt.

C'est la raison pour laquelle cinq des six proxys sont conservés : les retirer
paierait le coût sans emporter le bénéfice. Cette décision repose sur une
mesure, pas sur une préférence.

**L'écart ne vient donc pas des proxys.** Il vient d'une différence réelle de
taux de défaut — 11,82 % contre 5,17 % — à laquelle on applique un seuil unique.

### 8.7 La note du 16/08 se contredisait, et la mesure l'a montré

Le §4 exige simultanément :

- **M-3 conforme** : la probabilité annoncée doit valoir dans chaque groupe ;
- **M-1 conforme** : à solvabilité égale, l'acceptation doit être la même.

Ces deux exigences sont **incompatibles dès que les taux de défaut diffèrent
entre groupes**. C'est un résultat démontré — Kleinberg, Mullainathan et
Raghavan (2016), Chouldechova (2017) —, pas une limite de notre implémentation :
un classifieur ne peut être à la fois calibré par groupe et égalisé sur les
taux d'erreur, sauf si les taux de base coïncident.

Nos taux de base : 11,82 % contre 5,17 %. Ils ne coïncident pas.

**Le §4 était donc mathématiquement insatisfiable, et nous l'ignorions en
l'écrivant.** Ce n'est pas un défaut du modèle mais du cadre de gouvernance.
La mesure a servi à cela : révéler une contradiction que la relecture n'avait
pas vue.

Le §4 **n'est pas modifié pour autant** : un seuil qu'on desserre après l'avoir
échoué ne vaut plus rien. Il reste tel quel, il reste franchi, et le franchissement
suit la procédure prévue — la dérogation motivée du §8.8.

### 8.8 Remédiation : l'échelle du §7, appliquée

| # | Action prévue au §7 | État |
|---|---|---|
| 1 | Instruire les proxys, retirer ceux sans justification | **fait** — 1 retirée, 5 conservées et motivées (8.5) |
| 2 | Repondération par groupe à l'entraînement | **non engagée** — voir ci-dessous |
| 3 | Contrainte d'équité (`ExponentiatedGradient`) | **non engagée** |
| 4 | Recalibrer globalement | **fait** — Brier 0,1706 → 0,0664 ; M-3 conforme partout |
| 5 | Saisir le comité d'équité | **fait** — séance du 01/09, registre des revues |
| 6 | Refuser le déploiement | **effectif** : `audit.py` sort en erreur |

Les étapes 2 et 3 ne sont pas engagées, et il faut le dire franchement : le
calendrier du démonstrateur ne le permet pas. Elles sont **la première tâche
d'une suite**, et non une option écartée. L'ablation du §8.6 donne une
indication du gain à en attendre — modéré, l'écart étant structurel.

**L'option toujours écartée.** Un seuil de décision par tranche d'âge
égaliserait M-1 immédiatement. Il exigerait de **collecter l'âge au moment de
la décision** — ce que toute l'architecture interdit — et constituerait un
traitement différencié **direct** fondé sur un attribut protégé, là où nous ne
subissons aujourd'hui qu'une discrimination indirecte. Le §7 le disait avant de
connaître les chiffres ; les chiffres ne changent rien à l'argument.

### 8.9 Dérogation motivée du comité d'équité — 01/09/2026

Le comité constate le franchissement des seuils d'arrêt de M-1 et M-2 sur
l'âge, et de M-1 sur le genre et la situation familiale.

Il **refuse la mise en production** et **autorise l'usage en démonstrateur**,
sous cinq conditions :

1. **Aucune décision réelle** n'est prise sur la base de ce modèle.
2. **Revue humaine systématique**, et non sur demande, de tout refus concernant
   un demandeur de moins de 30 ans — art. 22 RGPD appliqué au groupe le plus
   pénalisé, sans utiliser l'âge dans le calcul du score.
3. **Réserve P-10** sur les scores externes (§8.5) levée avant toute production.
4. **Mesure trimestrielle** de M-1 à M-6, publiée au comité, avec un objectif
   chiffré de réduction de M-1 sur l'âge.
5. **Étapes 2 et 3 du §7** engagées avant tout examen d'une mise en production.

Cette dérogation est **datée, motivée et limitée**. Elle n'assouplit aucun
seuil : elle constate un échec, en tire les conséquences, et fixe ce qu'il
faudra prouver pour revenir.

---

## 9. Limites reconnues

Trois limites **énoncées explicitement**, pas dissimulées.

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
| 1.1 | 01/09/2026 | **§8 mesuré.** M-1 et M-2 franchissent le seuil d'arrêt sur l'âge (0,3082 et 0,3961). Instruction des cinq proxys détectés par C-3, retrait de `FLAG_EMP_PHONE`. Ablation chiffrée : retirer les proxys ne suffit pas. Prix de la conformité mesuré (0,0039 d'AUC). Contradiction interne du §4 reconnue (§8.7). Réserve P-10 sur les scores externes. Dérogation motivée du comité. **Aucun seuil du §4 modifié.** |
| 1.0 | 16/08/2026 | Création. État des lieux mesuré, métriques M-1 à M-6, **seuils figés avant mesure**, procédure de détection des proxys, échelle de remédiation, limites déclarées. |
