# Registre des revues de conformité et d'équité

Registre tenu au titre du **§9.4 du [plan de gouvernance](gouvernance.md)**.

> **Règle :** une revue sans trace écrite est réputée ne pas avoir eu lieu.
> Chaque séance — revue trimestrielle de conformité, revue annuelle d'équité,
> ou séance exceptionnelle du comité d'équité — produit une entrée ci-dessous,
> **le jour même**.

## Format d'une entrée

```
## R-nnn — jj/mm/aaaa — [Conformité | Équité | Exceptionnelle]

- **Participants :**
- **Ordre du jour :**
- **Constats :**
- **Décisions :**
- **Actions :** (action — responsable — échéance)
- **Prochaine revue :**
```

---

## R-001 — 16/08/2026 — Revue exceptionnelle : mise en place du cadre

- **Participants :** architecte IA (le candidat cumule les rôles AIA/DS/DE dans
  le cadre du démonstrateur — voir §3.1 du plan de gouvernance).
- **Ordre du jour :** adoption du plan de gouvernance v1.0 et de la note
  d'équité v1.0 ; revue de l'écart constaté sur la décision D-003.
- **Constats :**
  - **Non-conformité constatée et corrigée le jour même :** la décision D-003
    annonçait un test d'exclusion des variables sensibles en intégration
    continue. Ni le test ni la CI n'existaient. Contrôle **C-1** implémenté et
    vérifié (`src/fairness/contract.py`, 14 assertions) avant adoption du plan.
  - Disparités mesurées **dans les données sources**, avant modélisation :
    3,14 points d'écart de taux de défaut selon le genre, 8,63 points selon
    l'âge.
  - Deux sous-populations statistiquement inexploitables : `CODE_GENDER = XNA`
    (n = 4) et `NAME_FAMILY_STATUS = Unknown` (n = 2). Déclarées, non mesurées.
- **Décisions :**
  - Adoption du plan de gouvernance v1.0 (politiques P-1 à P-9, contrôles C-1 à C-12).
  - Adoption de la note d'équité v1.0, **seuils figés avant toute mesure** (D-010).
  - Seuils de décision différenciés par groupe : **exclus** (discrimination directe).
- **Actions :**

  | Action | Responsable | Échéance |
  |---|---|---|
  | Contrôles C-7 (pseudonymisation) et C-6 (qualité bloquante) | AIA | 23–25/08 |
  | Contrôles C-3, C-4, C-5 (proxys, équité chiffrée, SHAP) | AIA | 28/08 |
  | Contrôles C-2, C-12 (log d'audit, réexamen humain) | AIA | 29/08 |
  | Contrôle C-10 (dérive) | AIA | 01/09 |
  | Report des résultats au §8 de la note d'équité | AIA | 28/08 |
  | ~~Mise en place d'une CI exécutant `pytest` à chaque `push`~~ | AIA | ✅ **fait le 16/08** — `.github/workflows/ci.yml` |
  | Production de l'AIPD formelle | DPO | avant exploitation réelle |

- **Prochaine revue :** **28/08/2026** — revue d'équité, à la publication des
  mesures M-1 à M-6.

---

## R-002 — 01/09/2026 — Revue d'équité : publication des mesures M-1 à M-6

- **Participants :** DPO (préside) · direction des risques · architecte IA ·
  représentant métier · profil externe.

- **Ordre du jour :**
  1. Résultats du contrôle C-3 (détection des proxys).
  2. Résultats du contrôle C-4 (métriques d'équité par sous-population).
  3. Instruction des proxys détectés (§6 de la note d'équité, étape 3).
  4. Suite à donner au franchissement des seuils d'arrêt.

- **Constats :**

  - **C-4 a bloqué le déploiement.** Sur l'axe de l'âge, M-1 = **0,3082** pour
    un seuil d'arrêt de 0,05, et M-2 = **0,3961** pour un seuil de 0,08. Parmi
    les demandeurs qui remboursent, 55,8 % des 20-30 ans sont acceptés contre
    86,6 % des 60-70 ans. M-1 est également franchi sur le genre (0,0763, au
    détriment des hommes) et sur la situation familiale (0,1376).

  - **M-3 est conforme sur les trois axes** (0,0110 au pire). Les probabilités
    annoncées sont justes dans chaque groupe : le modèle n'estime pas mal le
    risque des jeunes, il l'estime bien. L'écart d'acceptation vient du **seuil
    unique appliqué à des probabilités honnêtes**, non d'une erreur de mesure.

  - **Cinq proxys détectés par C-3** au-dessus du seuil de 0,50 :
    `DAYS_EMPLOYED_ANORMAL` (0,751), `FLAG_EMP_PHONE` (0,751),
    `CNT_FAM_MEMBERS` (0,607), `EXT_SOURCE_1` (0,600),
    `REVENU_PAR_PERSONNE` (0,508). Trois motifs d'absence également
    révélateurs de l'âge.

  - **`FLAG_EMP_PHONE` est identique à `DAYS_EMPLOYED_ANORMAL`** sur 100,00 %
    des dossiers. Deux variables portaient la même information.

  - **`EXT_SOURCE_1` réencode l'âge** (0,600) alors qu'il s'agit de la
    troisième variable du modèle. Sa composition est inconnue du fournisseur.

  - **L'ablation chiffrée établit que le retrait des proxys ne corrige pas
    l'écart** : retirer les six variables ramène M-1 de 0,3215 à 0,2756 — cinq
    fois le seuil d'arrêt encore — pour 0,0075 d'AUC et 0,36 M€.

  - **Prix de la conformité mesuré (D-008) : 0,0039 d'AUC-ROC.** Le modèle
    témoin, entraîné avec les attributs protégés et jamais enregistré, atteint
    0,7843 contre 0,7804. L'âge y serait la 7ᵉ variable la plus utilisée sur
    226 : le faible coût de son exclusion mesure la **fuite d'information par
    les proxys**, non l'équité du modèle.

  - **Le §4 de la note d'équité se contredisait.** Exiger simultanément M-3
    (calibration par groupe) et M-1 (égalité des chances) est mathématiquement
    impossible dès que les taux de base diffèrent — 11,82 % contre 5,17 % ici.
    Résultat démontré (Kleinberg *et al.* 2016, Chouldechova 2017), ignoré à la
    rédaction du 16/08.

- **Décisions :**

  - **Retrait de `FLAG_EMP_PHONE`** — aucune justification autonome ne survit
    au constat de redondance parfaite. Consigné dans
    `src/models/preparation.py`.

  - **Conservation des cinq autres proxys**, chacun avec justification écrite
    au §8.5 de la note d'équité. Motif : justification métier autonome, et
    l'ablation démontre que leur retrait paierait le coût sans le bénéfice.

  - **Aucun seuil du §4 n'est modifié.** Un seuil desserré après avoir été
    échoué ne vaut plus rien. Le §4 reste tel quel, il reste franchi, et le
    franchissement suit la procédure de dérogation prévue.

  - **Refus de la mise en production. Usage en démonstrateur autorisé** sous
    les cinq conditions du §8.9 de la note d'équité.

  - **Confirmation du refus des seuils par tranche d'âge** — la mesure ne
    change rien à l'argument juridique : corriger une discrimination indirecte
    par une discrimination directe est régressif.

  - **Création de la politique P-10** — traçabilité des scores fournis par des
    tiers.

- **Actions :**

  | Action | Responsable | Échéance |
  |---|---|---|
  | Obtenir la composition du score externe auprès du fournisseur (P-10) | DPO | avant toute production |
  | Étapes 2 et 3 du §7 : repondération, puis contrainte d'équité | AIA | avant réexamen d'une mise en production |
  | Revue humaine systématique de tout refus des moins de 30 ans | Métier | à l'ouverture du service |
  | Mesure trimestrielle de M-1 à M-6, publiée au comité | AIA | trimestriel |
  | Contrôles C-2, C-12 (journal d'audit, réexamen humain) | AIA | 02/09 |
  | Contrôle C-10 (dérive PSI/KS) | AIA | 03/09 |
  | Production de l'AIPD formelle | DPO | avant exploitation réelle |

- **Prochaine revue :** à la levée de la réserve P-10, ou au premier
  réentraînement — la saisine est de droit à chacun d'eux.
