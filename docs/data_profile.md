# Profil des données sources (zone raw)

Généré par `src/data/profile_raw.py` — échantillon de 200 000 lignes pour les taux de nuls des fichiers volumineux (volumétrie et clés : exactes).

## Volumétrie et clés

| Fichier | Taille (Mo) | Lignes | Colonnes | Clé | Clés distinctes | Colonnes avec nuls |
|---|---|---|---|---|---|---|
| application_train.csv | 166.1 | 307 511 | 122 | SK_ID_CURR | 307 511 | 67/122 |
| application_test.csv | 26.6 | 48 744 | 121 | SK_ID_CURR | 48 744 | 64/121 |
| bureau.csv | 170.0 | 1 716 428 | 17 | SK_ID_BUREAU | 1 716 428 | 6/17 |
| bureau_balance.csv | 375.6 | 27 299 925 | 3 | SK_ID_BUREAU | 817 395 | 0/3 |
| previous_application.csv | 405.0 | 1 670 214 | 37 | SK_ID_PREV | 1 670 214 | 15/37 |
| POS_CASH_balance.csv | 392.7 | 10 001 358 | 8 | SK_ID_PREV | 936 325 | 2/8 |
| credit_card_balance.csv | 424.6 | 3 840 312 | 23 | SK_ID_PREV | 104 307 | 9/23 |
| installments_payments.csv | 723.1 | 13 605 401 | 8 | SK_ID_PREV | 997 752 | 0/8 |

## Cible (application_train)

- Taux de défaut (TARGET=1) : **8.07 %** (24 825 défauts sur 307 511 dossiers)
- Classes fortement déséquilibrées : métriques AUC-PR + coût métier, pondération `scale_pos_weight` à l'entraînement.

## Valeurs manquantes — top 10 par fichier

### application_train.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
| COMMONAREA_AVG | 69.9 |
| COMMONAREA_MODE | 69.9 |
| COMMONAREA_MEDI | 69.9 |
| NONLIVINGAPARTMENTS_MEDI | 69.5 |
| NONLIVINGAPARTMENTS_MODE | 69.5 |
| NONLIVINGAPARTMENTS_AVG | 69.5 |
| FONDKAPREMONT_MODE | 68.4 |
| LIVINGAPARTMENTS_AVG | 68.4 |
| LIVINGAPARTMENTS_MEDI | 68.4 |
| LIVINGAPARTMENTS_MODE | 68.4 |

### application_test.csv

| Colonne | % nuls |
|---|---|
| COMMONAREA_AVG | 68.7 |
| COMMONAREA_MEDI | 68.7 |
| COMMONAREA_MODE | 68.7 |
| NONLIVINGAPARTMENTS_AVG | 68.4 |
| NONLIVINGAPARTMENTS_MEDI | 68.4 |
| NONLIVINGAPARTMENTS_MODE | 68.4 |
| FONDKAPREMONT_MODE | 67.3 |
| LIVINGAPARTMENTS_MEDI | 67.2 |
| LIVINGAPARTMENTS_AVG | 67.2 |
| LIVINGAPARTMENTS_MODE | 67.2 |

### bureau.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
| AMT_ANNUITY | 72.0 |
| AMT_CREDIT_MAX_OVERDUE | 65.9 |
| DAYS_ENDDATE_FACT | 37.4 |
| AMT_CREDIT_SUM_LIMIT | 35.1 |
| AMT_CREDIT_SUM_DEBT | 15.0 |
| DAYS_CREDIT_ENDDATE | 6.3 |

### bureau_balance.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|

### previous_application.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
| RATE_INTEREST_PRIVILEGED | 99.6 |
| RATE_INTEREST_PRIMARY | 99.6 |
| AMT_DOWN_PAYMENT | 51.2 |
| RATE_DOWN_PAYMENT | 51.2 |
| NAME_TYPE_SUITE | 48.7 |
| DAYS_TERMINATION | 38.7 |
| DAYS_FIRST_DRAWING | 38.7 |
| DAYS_FIRST_DUE | 38.7 |
| DAYS_LAST_DUE_1ST_VERSION | 38.7 |
| DAYS_LAST_DUE | 38.7 |

### POS_CASH_balance.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
| CNT_INSTALMENT | 0.2 |
| CNT_INSTALMENT_FUTURE | 0.2 |

### credit_card_balance.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
| AMT_PAYMENT_CURRENT | 22.7 |
| CNT_DRAWINGS_POS_CURRENT | 22.6 |
| AMT_DRAWINGS_ATM_CURRENT | 22.6 |
| CNT_DRAWINGS_ATM_CURRENT | 22.6 |
| AMT_DRAWINGS_POS_CURRENT | 22.6 |
| AMT_DRAWINGS_OTHER_CURRENT | 22.6 |
| CNT_DRAWINGS_OTHER_CURRENT | 22.6 |
| CNT_INSTALMENT_MATURE_CUM | 5.9 |
| AMT_INST_MIN_REGULARITY | 5.9 |

### installments_payments.csv *(estimé sur échantillon)*

| Colonne | % nuls |
|---|---|
