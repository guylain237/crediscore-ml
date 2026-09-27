# Plan de features

Ce qui sera construit, à partir de quoi, et surtout **pourquoi**. Chaque choix
s'appuie sur une mesure de [`data_profile.md`](data_profile.md) ou de
[`schema_jointures.md`](schema_jointures.md), jamais sur une habitude.

---

## 1. Les cinq règles opposables

**F1 — Rien qui ne soit connu au moment de la demande.** Vérifié par la mesure :
toutes les colonnes temporelles sont antérieures ou concomitantes à la demande
(voir R3 dans [`strategie_decoupage.md`](strategie_decoupage.md)).

**F2 — Aucune variable sensible, ni aucune variable qui en dérive.** Le contrat
`configs/sensitive_features.yaml` interdit `CODE_GENDER`, `DAYS_BIRTH` et
`NAME_FAMILY_STATUS`. Il interdit donc aussi tout ratio ou toute tranche
construits à partir d'eux (décision D-003).

**F3 — Toute variable doit être calculable dans le budget de latence.** La
décision est rendue en quelques secondes au point de vente : les agrégats lourds
sont précalculés dans le feature store, jamais à la volée.

**F4 — Toute variable doit être explicable à un client.** L'article 22 du RGPD
impose de motiver un refus. Une variable dont on ne sait pas dire ce qu'elle
signifie ne peut pas apparaître dans une explication SHAP présentée à un
demandeur.

**F5 — Une absence n'est pas un zéro.** Un dossier sans historique bureau n'a pas
« zéro dette » : il n'a **pas d'information**. Les deux situations ne se
confondent pas et ne s'imputent pas de la même façon.

---

## 2. Le socle : `application_train` (122 colonnes)

### 2.1 Ce qui porte le signal

Corrélations absolues avec la cible, mesurées sur les 307 511 dossiers :

| Variable | \|corr\| | Nuls | Statut |
|---|---|---|---|
| `EXT_SOURCE_3` | 0,179 | 19,8 % | conservée |
| `EXT_SOURCE_2` | 0,160 | 0,2 % | conservée |
| `EXT_SOURCE_1` | 0,155 | 56,4 % | **conservée malgré 56 % de nuls** |
| `DAYS_BIRTH` | 0,078 | 0 % | **exclue — variable sensible** |
| `REGION_RATING_CLIENT_W_CITY` | 0,061 | 0 % | conservée |
| `DAYS_LAST_PHONE_CHANGE` | 0,055 | 0 % | conservée |
| `DAYS_EMPLOYED` | 0,045 | 0 % | conservée, après traitement (§2.3) |

Deux enseignements. Les trois scores externes `EXT_SOURCE_*` dominent tout le
reste d'un facteur deux — ce sont des scores de bureau de crédit déjà agrégés,
donc le modèle repose en grande partie sur un jugement extérieur, ce qu'il faut
assumer explicitement.

Et surtout : **un taux de nuls élevé n'est pas un critère d'élimination**.
`EXT_SOURCE_1` manque dans 56 % des dossiers et reste la troisième variable la
plus liée à la cible. Éliminer les colonnes sur leur taux de nuls — réflexe
courant — supprimerait ici l'un des meilleurs prédicteurs.

### 2.2 Ce qui est retiré, et sur quelle preuve

| Retrait | Volume | Justification mesurée |
|---|---|---|
| Variables sensibles | 3 colonnes | Contrat D-003 |
| Triplets `_MODE` et `_MEDI` redondants | **28 colonnes** | Corrélations de **0,973 à 0,997** entre `_AVG`, `_MODE` et `_MEDI` du même indicateur : trois mesures du même objet |
| `SK_ID_CURR` | 1 colonne | Identifiant, aucun contenu prédictif |

Les 14 indicateurs de logement existent en trois versions (`APARTMENTS_AVG`,
`APARTMENTS_MODE`, `APARTMENTS_MEDI`…). Mesurées, elles corrèlent entre elles
au-delà de 0,97 : on conserve la version `_AVG` et on retire les deux autres.
Ce sont **28 colonnes en moins sans perte d'information**, et un modèle SHAP
d'autant plus lisible qu'il ne répartit plus l'importance entre trois jumelles.

> Les quatre `_MODE` **catégorielles** (`FONDKAPREMONT_MODE`, `HOUSETYPE_MODE`,
> `WALLSMATERIAL_MODE`, `EMERGENCYSTATE_MODE`) et `TOTALAREA_MODE` n'ont pas
> d'équivalent `_AVG` : elles sont conservées.

### 2.3 Le cas `DAYS_EMPLOYED` — une sentinelle, pas une mesure

`DAYS_EMPLOYED = 365243` apparaît **55 374 fois, soit 18,0 %** des dossiers. Cela
signifierait une ancienneté d'emploi de +1000 ans dans le futur : c'est un code,
signifiant « sans emploi / retraité ».

Laissée telle quelle, cette valeur décale la moyenne d'ancienneté de plusieurs
siècles et place tous les seuils de coupure des arbres au mauvais endroit.

**Traitement retenu, en deux temps :**

```python
app["DAYS_EMPLOYED_ANORMAL"] = (app["DAYS_EMPLOYED"] == 365243).astype(int)
app.loc[app["DAYS_EMPLOYED"] == 365243, "DAYS_EMPLOYED"] = np.nan
```

On neutralise la valeur aberrante **et** on conserve l'information qu'elle
portait. Se contenter du `NaN` détruirait un signal qui concerne près d'un
dossier sur cinq.

### 2.4 Ratios métier à construire

Les montants bruts disent peu ; leurs rapports disent la capacité de
remboursement. Sept ratios, tous directement interprétables devant un client :

| Variable | Formule | Sens métier |
|---|---|---|
| `RATIO_CREDIT_REVENU` | `AMT_CREDIT / AMT_INCOME_TOTAL` | endettement global demandé |
| `RATIO_ANNUITE_REVENU` | `AMT_ANNUITY / AMT_INCOME_TOTAL` | **taux d'effort mensuel** |
| `RATIO_CREDIT_BIEN` | `AMT_CREDIT / AMT_GOODS_PRICE` | part financée du bien |
| `RATIO_ANNUITE_CREDIT` | `AMT_ANNUITY / AMT_CREDIT` | durée implicite du prêt |
| `REVENU_PAR_PERSONNE` | `AMT_INCOME_TOTAL / CNT_FAM_MEMBERS` | niveau de vie du foyer |
| `RATIO_ANCIENNETE` | `DAYS_EMPLOYED / DAYS_REGISTRATION` | stabilité professionnelle |
| `NB_DOCUMENTS` | somme des 20 `FLAG_DOCUMENT_*` | complétude du dossier |

Le taux d'effort est le ratio réglementaire de référence du crédit à la
consommation : sa présence dans une explication de refus est immédiatement
compréhensible par le demandeur.

> `RATIO_ANCIENNETE` utilise `DAYS_REGISTRATION` et non `DAYS_BIRTH` : le ratio
> classique ancienneté / âge est **interdit** par F2, puisqu'il dérive d'une
> variable sensible.

Sur les 20 `FLAG_DOCUMENT_*`, seul `FLAG_DOCUMENT_3` apparaît parmi les quinze
variables les plus corrélées à la cible. Hypothèse à vérifier avant de trancher :
conserver `FLAG_DOCUMENT_3` isolément, remplacer les 19 autres par leur seule
somme. Un test de variance et de corrélation individuelle décidera — ce n'est pas
encore mesuré.

---

## 3. Les agrégats des tables filles

### 3.1 Priorisation par la couverture réelle

La couverture au grain **dossier** décide de l'effort à investir, et elle diffère
fortement de la couverture par parent direct :

| Source | Préfixe | Couverture dossier | Manquantes | Priorité |
|---|---|---|---|---|
| `previous_application` | `PREV_*` | 94,6 % | 5,4 % | haute |
| `installments_payments` | `INSTAL_*` | 94,1 % | 5,9 % | **haute** |
| `POS_CASH_balance` | `POS_*` | 93,3 % | 6,7 % | haute |
| `bureau` | `BUREAU_*` | 85,7 % | 14,3 % | haute |
| `bureau_balance` | `BB_*` | 30,0 % | 70,0 % | basse |
| `credit_card_balance` | `CC_*` | 25,3 % | 74,7 % | basse |

L'écart entre couverture directe et couverture dossier est instructif :
`installments_payments` ne couvre que 57,4 % des demandes antérieures, mais
**94,1 % des dossiers** — parce qu'un dossier compte en médiane 4 demandes
antérieures, et qu'il suffit que l'une d'elles ait un historique de paiement.
Juger cette table sur ses 57,4 % aurait conduit à la sous-investir, alors que
c'est la source la plus riche en signal de comportement de remboursement.

### 3.2 `installments_payments` — le comportement de paiement

La source la plus prédictive, parce qu'elle décrit ce que le client **a fait**,
pas ce qu'il déclare. Deux variables dérivées à la ligne, puis agrégation par
dossier :

```
RETARD_JOURS  = DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT   # > 0 : payé en retard
TAUX_PAIEMENT = AMT_PAYMENT / AMT_INSTALMENT           # < 1 : paiement partiel
```

Agrégations : `mean`, `max`, `sum`, `std` du retard ; `mean` et `min` du taux de
paiement ; nombre d'échéances ; nombre et part d'échéances en retard ; retard
maximal sur les 12 derniers mois. **≈ 20 variables.**

### 3.3 `previous_application` — l'historique de la relation

Répartition mesurée des issues : **62,1 % acceptées**, 18,9 % annulées,
17,4 % refusées, 1,6 % offres non utilisées.

Un taux de refus antérieur élevé est un signal fort — CrediScore avait déjà
jugé ce demandeur risqué. Variables : nombre de demandes ; part de chaque issue ;
`AMT_APPLICATION / AMT_CREDIT` moyen (écart entre le demandé et l'accordé) ;
ancienneté de la dernière demande (`DAYS_DECISION` max) ; statistiques des
montants. **≈ 35 variables.**

### 3.4 `bureau` — l'exposition chez les autres établissements

Variables : nombre de crédits actifs / clos (`CREDIT_ACTIVE`) ; somme et maximum
des dettes en cours (`AMT_CREDIT_SUM_DEBT`) ; ratio dette / plafond ; montants
en souffrance (`AMT_CREDIT_SUM_OVERDUE`) ; ancienneté du crédit le plus récent
(`DAYS_CREDIT` max) ; nombre de types de crédits distincts. **≈ 40 variables.**

> `DAYS_CREDIT_ENDDATE` atteint +31 199 jours, soit 85 ans dans le futur. Une
> date de fin prévue est légitime, cette amplitude ne l'est pas : écrêtage au
> 99ᵉ centile avant agrégation.

### 3.5 `POS_CASH_balance` — la tenue des crédits en cours

Variables : nombre de mois d'historique ; `SK_DPD` et `SK_DPD_DEF` (jours de
retard, tolérant et strict) en `mean`, `max`, dernière valeur ; part de mois avec
retard ; statut du dernier mois observé. **≈ 12 variables.**

### 3.6 `bureau_balance` — priorité basse assumée

Répartition mesurée de `STATUS` : `C` (clos) 50,0 %, `0` (aucun retard) 27,5 %,
`X` (inconnu) 21,3 %, et **1,26 % seulement** répartis sur les statuts de retard
`1` à `5`.

Deux raisons de ne pas y investir en premier : 70 % des dossiers n'en ont aucune
ligne, et l'information de retard y est très rare. Version minimale : nombre de
mois d'historique, part de mois en retard, pire statut atteint. **≈ 8 variables.**

### 3.7 `credit_card_balance` — priorité basse assumée

74,7 % des dossiers n'ont aucune carte. Pour le quart restant, le **taux
d'utilisation** est le signal reconnu du secteur : un client qui frôle en
permanence son plafond est en tension de trésorerie.

```
TAUX_UTILISATION = AMT_BALANCE / AMT_CREDIT_LIMIT_ACTUAL
```

Agrégations : `mean`, `max`, tendance sur 12 mois ; fréquence des retraits
d'espèces (`CNT_DRAWINGS_ATM_CURRENT`) ; `SK_DPD` moyen. **≈ 15 variables.**

---

## 4. Valeurs manquantes : aucune imputation

**Décision : on n'impute pas, et c'est un choix, pas un oubli.**

LightGBM traite nativement les valeurs manquantes : à chaque nœud, il apprend de
quel côté envoyer les absents, en fonction du gain observé. Imputer par la
médiane reviendrait à affirmer une valeur qu'on ne connaît pas, et à effacer
l'information portée par l'absence — laquelle est ici substantielle : 14,3 % des
dossiers n'ont aucun historique bureau, et ce sont potentiellement des
primo-emprunteurs, profil de risque à part entière (règle F5).

En complément, un indicateur binaire de présence par famille de variables —
`A_HISTORIQUE_BUREAU`, `A_CARTE_CREDIT`, `A_DEMANDE_ANTERIEURE` — rend cette
information explicite et directement lisible dans une explication SHAP.

---

## 5. Variables catégorielles

16 colonnes texte, de cardinalité très inégale.

| Cardinalité | Colonnes | Encodage |
|---|---|---|
| 2 à 8 modalités | 11 colonnes | natif LightGBM (`category`) |
| 18 modalités (`OCCUPATION_TYPE`, 31,3 % de nuls) | 1 colonne | natif, `NaN` comme modalité à part entière |
| **58 modalités** (`ORGANIZATION_TYPE`) | 1 colonne | natif ; encodage par la cible **écarté** |

L'encodage par la cible (*target encoding*) est écarté délibérément : il fait
fuiter la cible dans les variables et exige un dispositif hors-pli rigoureux pour
un gain incertain face au traitement catégoriel natif de LightGBM. Un risque de
fuite pour un gain non démontré est un mauvais échange.

---

## 6. Le prix de la conformité, chiffré

`DAYS_BIRTH` est la **quatrième variable la plus corrélée à la cible**
(|r| = 0,078), et elle est exclue. `CODE_GENDER` et `NAME_FAMILY_STATUS` le sont
également, ainsi que tout ratio qui en dériverait.

Ce n'est pas neutre, et l'honnêteté consiste à le mesurer plutôt qu'à le taire.
**Protocole prévu :** entraîner un modèle témoin *avec* les variables sensibles,
et comparer son AUC à celui du modèle conforme. L'écart chiffre le coût de la
conformité.

Ce modèle témoin ne sera **jamais déployé** : il sert uniquement à documenter
l'arbitrage, avec ses résultats consignés dans MLflow. Un architecte doit
connaître le prix de ses contraintes — pas prétendre
qu'elles sont gratuites.

---

## 7. Volumétrie cible et conventions

| Groupe | Variables |
|---|---|
| Socle `application` après retraits | ≈ 90 |
| Ratios métier | 7 |
| `PREV_*` | ≈ 35 |
| `BUREAU_*` | ≈ 40 |
| `INSTAL_*` | ≈ 20 |
| `CC_*` | ≈ 15 |
| `POS_*` | ≈ 12 |
| `BB_*` | ≈ 8 |
| Indicateurs de présence | 4 |
| **Total** | **≈ 230** |

Nommage : `SOURCE_COLONNE_AGREGAT` en majuscules —
`BUREAU_AMT_CREDIT_SUM_DEBT_MEAN`, `INSTAL_RETARD_JOURS_MAX`. Le préfixe permet
de retrouver l'origine d'une variable dans un graphique SHAP sans consulter le
code.

---

## 8. Contrôles automatiques à mettre en place

| Test | Ce qu'il empêche |
|---|---|
| `test_no_sensitive_features` | qu'une variable sensible ou dérivée entre dans le modèle (D-003) |
| `test_no_duplicate_rows_after_join` | qu'une jointure sur un mauvais grain duplique des dossiers |
| `test_feature_count_stable` | qu'une variable disparaisse ou apparaisse sans que personne ne le voie |
| `test_no_future_information` | qu'une variable temporelle positive s'introduise (hors `DAYS_CREDIT_ENDDATE`, exception documentée) |
| `test_aggregates_are_per_dossier` | qu'un agrégat mélange l'historique de plusieurs dossiers |

Ces tests tournent en intégration continue. Un plan de features non testé n'est
qu'une intention.
