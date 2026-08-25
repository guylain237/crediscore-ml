# Qualité des données et bornes de contrôle

Généré par `src/data/profile_quality.py`. **Toutes les valeurs sont
mesurées sur l'intégralité des fichiers**, sans échantillonnage.

Ce document fournit au pipeline ce qui lui manquait : la preuve qu'il n'y
a pas de doublons à corriger, les bornes chiffrées du contrôle « plages de
valeurs », la liste des divisions à protéger, et la réponse à l'hypothèse
restée ouverte sur les `FLAG_DOCUMENT_*`.

---

## 1. Doublons — la question qui commande la justesse du pipeline

Deux mesures distinctes. Une **ligne strictement identique** est presque
toujours un défaut d'export. Un **doublon de grain** est plus grave : il
signifie que le grain supposé n'est pas le vrai grain, et qu'une
agrégation construite dessus mélangerait des choses distinctes.

| Fichier | Grain supposé | Lignes | Doublons de grain | Lignes identiques |
|---|---|---|---|---|
| `application_train.csv` | SK_ID_CURR | 307 511 | 0 | 0 |
| `bureau.csv` | SK_ID_BUREAU | 1 716 428 | 0 | 0 |
| `bureau_balance.csv` | SK_ID_BUREAU + MONTHS_BALANCE | 27 299 925 | 0 | 0 |
| `previous_application.csv` | SK_ID_PREV | 1 670 214 | 0 | 0 |
| `POS_CASH_balance.csv` | SK_ID_PREV + MONTHS_BALANCE | 10 001 358 | 0 | 0 |
| `credit_card_balance.csv` | SK_ID_PREV + MONTHS_BALANCE | 3 840 312 | 0 | 0 |
| `installments_payments.csv` | SK_ID_PREV + NUM_INSTALMENT_VERSION + NUM_INSTALMENT_NUMBER | 13 605 401 | 653 483 | *non mesuré (volume)* |

**Total des doublons de grain : 653 483**

---

## 2. Distributions — les bornes du contrôle qualité

Les quantiles 0,1 % et 99,9 % fondent les bornes : elles écartent
l'aberration sans rejeter la queue légitime de la distribution.

| variable | count | mean | min | 0.1% | 1% | 50% | 99% | 99.9% | max | nuls_% |
|---|---|---|---|---|---|---|---|---|---|---|
| AMT_INCOME_TOTAL | 307 511.00 | 168 797.92 | 25 650.00 | 31 500.00 | 45 000.00 | 147 150.00 | 472 500.00 | 900 000.00 | 117 000 000.00 | 0.00 |
| AMT_CREDIT | 307 511.00 | 599 026.00 | 45 000.00 | 47 970.00 | 76 410.00 | 513 531.00 | 1 854 000.00 | 2 517 300.00 | 4 050 000.00 | 0.00 |
| AMT_ANNUITY | 307 499.00 | 27 108.57 | 1 615.50 | 3 932.98 | 6 182.91 | 24 903.00 | 70 006.50 | 110 047.50 | 258 025.50 | 0.00 |
| AMT_GOODS_PRICE | 307 233.00 | 538 396.21 | 40 500.00 | 45 000.00 | 67 500.00 | 450 000.00 | 1 800 000.00 | 2 250 000.00 | 4 050 000.00 | 0.09 |
| CNT_FAM_MEMBERS | 307 509.00 | 2.15 | 1.00 | 1.00 | 1.00 | 2.00 | 5.00 | 6.00 | 20.00 | 0.00 |
| DAYS_EMPLOYED | 252 137.00 | -2 384.17 | -17 912.00 | -14 522.00 | -11 338.28 | -1 648.00 | -111.00 | -54.00 | 0.00 | 18.01 |
| DAYS_REGISTRATION | 307 511.00 | -4 986.12 | -24 672.00 | -16 502.98 | -13 879.00 | -4 504.00 | -50.00 | -3.00 | 0.00 | 0.00 |
| RATIO_CREDIT_REVENU | 307 511.00 | 3.96 | 0.00 | 0.31 | 0.60 | 3.27 | 13.03 | 19.29 | 84.74 | 0.00 |
| RATIO_ANNUITE_REVENU | 307 499.00 | 0.18 | 0.00 | 0.02 | 0.04 | 0.16 | 0.48 | 0.73 | 1.88 | 0.00 |
| RATIO_CREDIT_BIEN | 307 233.00 | 1.12 | 0.15 | 1.00 | 1.00 | 1.12 | 1.48 | 1.53 | 6.00 | 0.09 |
| RATIO_ANNUITE_CREDIT | 307 499.00 | 0.05 | 0.02 | 0.03 | 0.03 | 0.05 | 0.11 | 0.12 | 0.12 | 0.00 |
| REVENU_PAR_PERSONNE | 307 509.00 | 93 105.88 | 2 812.50 | 11 250.00 | 18 000.00 | 75 000.00 | 337 500.00 | 675 000.00 | 39 000 000.00 | 0.00 |
| RATIO_ANCIENNETE | 252 073.00 | 3.84 | -0.00 | 0.01 | 0.02 | 0.47 | 38.07 | 522.99 | 10 353.00 | 18.03 |
| NB_DOCUMENTS | 307 511.00 | 0.93 | 0.00 | 0.00 | 0.00 | 1.00 | 2.00 | 2.00 | 4.00 | 0.00 |

---

## 3. Pièges de calcul — les divisions à protéger

Chaque ligne est un `NaN` ou un `inf` qui entrerait silencieusement dans
le feature store si le pipeline divisait naïvement.

| Contrôle | Dossiers | Part | Effet sur les ratios |
|---|---|---|---|
| AMT_INCOME_TOTAL = 0 | 0 | 0.000 % | RATIO_CREDIT_REVENU  RATIO_ANNUITE_REVENU  REVENU_PAR_PERSONNE → inf |
| AMT_INCOME_TOTAL manquant | 0 | 0.000 % | mêmes ratios → NaN |
| AMT_GOODS_PRICE = 0 | 0 | 0.000 % | RATIO_CREDIT_BIEN → inf |
| AMT_GOODS_PRICE manquant | 278 | 0.090 % | RATIO_CREDIT_BIEN → NaN |
| AMT_CREDIT = 0 | 0 | 0.000 % | RATIO_ANNUITE_CREDIT → inf |
| AMT_ANNUITY manquant | 12 | 0.004 % | RATIO_ANNUITE_REVENU  RATIO_ANNUITE_CREDIT → NaN |
| CNT_FAM_MEMBERS = 0 | 0 | 0.000 % | REVENU_PAR_PERSONNE → inf |
| CNT_FAM_MEMBERS manquant | 2 | 0.001 % | REVENU_PAR_PERSONNE → NaN |
| DAYS_REGISTRATION = 0 | 80 | 0.026 % | RATIO_ANCIENNETE → inf |
| DAYS_EMPLOYED = 365243 (sentinelle retraités) | 55 374 | 18.007 % | à neutraliser en NULL avant tout calcul |

---

## 4. Les vingt `FLAG_DOCUMENT_*`

Hypothèse de `plan_features.md` §2.4 : conserver `FLAG_DOCUMENT_3`
isolément et remplacer les 19 autres par leur seule somme.

| variable | taux_a_1_% | variance | correlation_cible |
|---|---|---|---|
| FLAG_DOCUMENT_2 | 0.0042 | 0.0000 | 0.0054 |
| FLAG_DOCUMENT_3 | 71.0023 | 0.2059 | 0.0443 |
| FLAG_DOCUMENT_4 | 0.0081 | 0.0001 | -0.0027 |
| FLAG_DOCUMENT_5 | 1.5115 | 0.0149 | -0.0003 |
| FLAG_DOCUMENT_6 | 8.8055 | 0.0803 | -0.0286 |
| FLAG_DOCUMENT_7 | 0.0192 | 0.0002 | -0.0015 |
| FLAG_DOCUMENT_8 | 8.1376 | 0.0748 | -0.0080 |
| FLAG_DOCUMENT_9 | 0.3896 | 0.0039 | -0.0044 |
| FLAG_DOCUMENT_10 | 0.0023 | 0.0000 | -0.0014 |
| FLAG_DOCUMENT_11 | 0.3912 | 0.0039 | -0.0042 |
| FLAG_DOCUMENT_12 | 0.0007 | 0.0000 | -0.0008 |
| FLAG_DOCUMENT_13 | 0.3525 | 0.0035 | -0.0116 |
| FLAG_DOCUMENT_14 | 0.2936 | 0.0029 | -0.0095 |
| FLAG_DOCUMENT_15 | 0.1210 | 0.0012 | -0.0065 |
| FLAG_DOCUMENT_16 | 0.9928 | 0.0098 | -0.0116 |
| FLAG_DOCUMENT_17 | 0.0267 | 0.0003 | -0.0034 |
| FLAG_DOCUMENT_18 | 0.8130 | 0.0081 | -0.0080 |
| FLAG_DOCUMENT_19 | 0.0595 | 0.0006 | -0.0014 |
| FLAG_DOCUMENT_20 | 0.0507 | 0.0005 | 0.0002 |
| FLAG_DOCUMENT_21 | 0.0335 | 0.0003 | 0.0037 |

---

## 5. Variables catégorielles

`XNA` et `XAP` sont les codes d'absence de ce jeu de données. Traités
comme des modalités ordinaires, ils créeraient une catégorie « inconnu »
à laquelle le modèle attribuerait un risque — alors qu'ils ne signifient
rien d'autre que l'absence d'information (règle F5).

| variable | modalites | nuls_% | XNA_ou_XAP |
|---|---|---|---|
| ORGANIZATION_TYPE | 58.00 | 0.00 | 55 374.00 |
| OCCUPATION_TYPE | 18.00 | 31.35 | 0.00 |
| NAME_INCOME_TYPE | 8.00 | 0.00 | 0.00 |
| NAME_TYPE_SUITE | 7.00 | 0.42 | 0.00 |
| WALLSMATERIAL_MODE | 7.00 | 50.84 | 0.00 |
| WEEKDAY_APPR_PROCESS_START | 7.00 | 0.00 | 0.00 |
| NAME_FAMILY_STATUS | 6.00 | 0.00 | 0.00 |
| NAME_HOUSING_TYPE | 6.00 | 0.00 | 0.00 |
| NAME_EDUCATION_TYPE | 5.00 | 0.00 | 0.00 |
| FONDKAPREMONT_MODE | 4.00 | 68.39 | 0.00 |
| HOUSETYPE_MODE | 3.00 | 50.18 | 0.00 |
| CODE_GENDER | 3.00 | 0.00 | 4.00 |
| FLAG_OWN_CAR | 2.00 | 0.00 | 0.00 |
| NAME_CONTRACT_TYPE | 2.00 | 0.00 | 0.00 |
| FLAG_OWN_REALTY | 2.00 | 0.00 | 0.00 |
| EMERGENCYSTATE_MODE | 2.00 | 47.40 | 0.00 |
