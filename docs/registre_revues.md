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
  | Mise en place d'une CI exécutant `pytest` à chaque `push` | AIA | 31/08 |
  | Production de l'AIPD formelle | DPO | avant exploitation réelle |

- **Prochaine revue :** **28/08/2026** — revue d'équité, à la publication des
  mesures M-1 à M-6.
