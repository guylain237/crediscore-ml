# Plan de gouvernance — système de scoring CrediScore

**Livrable du Bloc 1 — Certification Architecte en IA**
**Auteur :** Tagne Guylain Florian · **Version 1.0** · **16/08/2026**

---

## 0. Statut de ce document

**Ce document est contraignant pour la suite du projet.** Il n'énonce pas des
intentions : il fixe des politiques numérotées (`P-n`) et des contrôles
techniques numérotés (`C-n`) que le code, l'infrastructure et les pipelines
doivent respecter.

Trois règles d'usage, à tenir jusqu'à la soutenance :

1. **Toute décision technique cite la politique qu'elle applique.** Une entrée de
   `docs/decisions.md` sans référence à un `P-n` est une décision hors cadre.
2. **Tout contrôle annoncé ici existe ou porte une date d'existence.** Un
   contrôle décrit mais absent du dépôt est une non-conformité — c'est le premier
   point qu'un auditeur vérifie, et le premier qu'un jury cherche.
3. **Ce document ne se modifie pas en silence** : voir §10.

> **Précédent qui justifie la règle 2.** La décision D-003 affirmait qu'un test
> d'exclusion des variables sensibles tournait en intégration continue. Ce test
> n'existait pas. Il a été écrit le 16/08 (`tests/test_no_sensitive_features.py`,
> 14 assertions) *avant* la rédaction du présent plan. Un plan de gouvernance qui
> décrit des contrôles inexistants est pire qu'aucun plan : il endort la
> vigilance.

---

## 1. Le système et sa qualification réglementaire

### 1.1 Description

| | |
|---|---|
| Nom | CrediScore — scoring de risque de défaut à l'octroi |
| Finalité | Estimer la probabilité de défaut d'un demandeur de crédit à la consommation, afin de maximiser le taux d'acceptation sous contrainte d'un taux de défaut plafonné |
| Personnes concernées | Demandeurs de crédit — personnes physiques |
| Effet de la décision | Octroi ou refus de crédit — **effet juridique significatif** |
| Volume de référence | 307 511 dossiers, 8,07 % de défauts observés |
| Degré d'automatisation | Score automatique ; décision finale **soumise à contrôle humain** (P-6) |

### 1.2 Qualification

Le système relève **simultanément** de deux régimes. Aucun ne dispense de l'autre.

| Régime | Fondement | Conséquence directe |
|---|---|---|
| **AI Act** (Règl. UE 2024/1689) | **Annexe III, point 5 b)** — évaluation de la solvabilité de personnes physiques | Système **à haut risque** : obligations des articles 9 à 15 et 17 |
| **RGPD** (Règl. UE 2016/679) | **Art. 22** — décision automatisée produisant un effet juridique | Droit à l'intervention humaine, à l'expression d'un point de vue, à la contestation |
| **RGPD art. 35** | Évaluation systématique et automatisée avec effet juridique | **AIPD obligatoire** — voir §4.3 |
| **Droit national** | Code de la consommation, art. L312-16 | Obligation de vérifier la solvabilité de l'emprunteur : le système sert une obligation légale, il ne la contourne pas |

### 1.3 Calendrier d'application — le point à connaître

Les obligations de l'AI Act applicables aux systèmes à haut risque de l'annexe III
s'appliquent **depuis le 2 août 2026**. Ce projet est donc conçu sous un régime
**déjà en vigueur**, et non en anticipation.

> ⚠️ **À vérifier avant l'oral :** le calendrier d'application a fait l'objet de
> discussions de report partiel au niveau européen. Confirmer l'état définitif du
> texte à la date de soutenance — un jury peut poser la question, et répondre
> « je l'ai vérifié le … » vaut mieux que réciter une date.

### 1.4 Ce que la qualification impose, article par article

| Article AI Act | Exigence | Où elle est traitée |
|---|---|---|
| Art. 9 | Système de gestion des risques | §5 — matrice de risques |
| Art. 10 | Gouvernance des données, examen des biais | P-2, P-3, P-4 · contrôles C-3, C-4, C-6 |
| Art. 11 | Documentation technique | `docs/` des deux dépôts + `decisions.md` |
| Art. 12 | Enregistrement automatique des journaux | C-2 — log d'audit |
| Art. 13 | Transparence envers l'utilisateur professionnel | P-5 · slides Bloc 4 |
| Art. 14 | **Contrôle humain** | P-6 · C-12 |
| Art. 15 | Exactitude, robustesse, cybersécurité | C-8, C-9, C-10, C-11 |
| Art. 17 | Système de gestion de la qualité | §9 — procédures d'audit |
| Art. 86 | **Droit à l'explication d'une décision individuelle** | P-5 · C-5 (SHAP) |

---

## 2. Politiques — le socle opposable

### P-1 — Localisation et souveraineté des données

Toutes les données à caractère personnel sont hébergées et traitées **dans
l'Union européenne**, en région `eu-north-1` (Stockholm). Aucun transfert hors UE
n'est autorisé sans analyse préalable et inscription au registre.

*Application technique :* variable Terraform `region` avec **validation
bloquante** — le code refuse toute région ne commençant pas par `eu-`
(`infra/variables.tf`). Ce n'est pas une consigne, c'est un garde-fou.

### P-2 — Minimisation

Seules les variables nécessaires à la finalité entrent dans le système. Les
122 colonnes sources sont réduites à ≈ 230 variables construites dont chacune est
justifiée dans `docs/plan_features.md`. **28 colonnes ont été retirées** sur
preuve de redondance (corrélations internes de 0,973 à 0,997).

*Corollaire :* une variable qu'on ne sait pas justifier ne rentre pas. La charge
de la preuve pèse sur celui qui ajoute, pas sur celui qui refuse.

### P-3 — Qualité des données

Aucune donnée ne parvient au modèle sans avoir franchi des contrôles
**bloquants** : fraîcheur, typage, unicité de clé, intégrité référentielle.
Le profilage a identifié **130 000 lignes orphelines réelles** (`bureau_balance`,
`POS_CASH`, `credit_card`, `installments`) : elles sont rejetées, **et le volume
rejeté est journalisé**. Un rejet silencieux est interdit.

### P-4 — Non-discrimination

`CODE_GENDER`, `DAYS_BIRTH` et `NAME_FAMILY_STATUS` — ainsi que **toute variable
qui en dérive** — sont interdites comme variables prédictives. Elles sont
**conservées pour l'audit d'équité uniquement** : sans elles, mesurer une
discrimination serait impossible.

> Ces attributs ne relèvent pas des catégories particulières de l'article 9 du
> RGPD. Leur conservation à seule fin de mesure des biais découle de l'obligation
> d'examen et d'atténuation des biais posée par l'**AI Act, art. 10 §2 f) et g)**.

*Application technique :* contrat `configs/sensitive_features.yaml` + module
`src/fairness/contract.py` + test bloquant `tests/test_no_sensitive_features.py`.
L'appel `exiger_conformite(features)` **interrompt l'entraînement** en cas de
violation — il ne se contente pas d'avertir.

*Modification :* toute évolution de cette liste passe par le comité d'équité
(§9.3). Aucune exception.

### P-5 — Explicabilité et motivation

Toute décision défavorable est motivée par les **cinq facteurs déterminants**,
exprimés en termes compréhensibles par le demandeur, calculés en moins d'une
seconde. Une variable dont on ne sait pas énoncer le sens ne peut pas figurer
dans une motivation — donc ne doit pas entrer dans le modèle (lien avec P-2).

*Fondement :* RGPD art. 22 §3 et AI Act art. 86.

### P-6 — Contrôle humain

Le système **n'octroie ni ne refuse** : il produit un score et une
recommandation. Trois garanties :

1. Tout refus recommandé est **réexaminable** par un analyste, qui dispose des
   facteurs SHAP et peut passer outre en motivant sa décision.
2. Le demandeur peut **exprimer son point de vue et contester** (RGPD art. 22 §3).
3. Le seuil de décision est fixé par la direction des risques sur une **courbe de
   coût métier**, pas par un automatisme statistique.

### P-7 — Traçabilité et reproductibilité

Toute décision de scoring est reconstituable : version du modèle, version des
données, valeurs d'entrée, score, seuil appliqué, facteurs déterminants,
horodatage, suite donnée. Conservation **5 ans**, alignée sur la durée de
prescription commerciale et sur la durée de vie des crédits concernés.

*Application technique :* log d'audit (C-2), MLflow, hachage du snapshot de la
zone `raw/`, `requirements.lock.txt`, `.terraform.lock.hcl`, graine fixée.

### P-8 — Sécurité et moindre privilège

Chiffrement au repos et en transit. Aucune clé d'accès longue durée : identités
temporaires via IAM Identity Center pour les opérateurs, rôles IAM pour les
applications. L'identité applicative n'a accès qu'aux préfixes `curated/` en
lecture et `audit/` en écriture — **jamais aux données brutes**.

### P-10 — Traçabilité des scores fournis par des tiers

Aucun score externe ne peut peser dans une décision sans que sa composition
soit connue et attestée exempte d'attribut protégé.

> **Cette politique naît d'une mesure, le 31/08/2026.** `EXT_SOURCE_1` est la
> troisième variable du modèle au sens SHAP. Elle est corrélée à 0,600 avec
> l'âge du demandeur : 0,332 en moyenne chez les 20-30 ans, 0,739 chez les
> 60-70 ans. Nous avons exclu l'âge du modèle et un fournisseur nous le rend
> dans un score dont nous ignorons la recette.
>
> Deux exigences s'en trouvent en défaut. L'AI Act impose qu'un système à haut
> risque soit explicable : nous expliquons ici une décision par un score que
> nous ne savons pas expliquer. Et la note d'équité interdit les proxys sans
> justification autonome : celle du score externe est invérifiable par
> construction.
>
> **Conséquence opérationnelle.** La mise en production est conditionnée à
> l'obtention, auprès du fournisseur, de la liste des variables composant le
> score et de l'attestation qu'aucun attribut protégé n'y figure. À défaut,
> `EXT_SOURCE_1`, `EXT_SOURCE_2` et `EXT_SOURCE_3` sont retirées — au prix
> d'une baisse de performance qu'il faudra alors mesurer. Le démonstrateur les
> conserve délibérément : les retirer masquerait le problème au lieu de le
> poser.

### P-9 — Maîtrise et sobriété des ressources

Toute ressource facturée à l'heure est créée **exclusivement par Terraform**, et
détruite hors sessions de travail.

> **Cette politique naît d'un incident réel.** Une base RDS `db.r7g.large` créée
> à la console le 29/07, jamais utilisée, a coûté 6,66 USD/jour pendant 7 jours
> (≈ 50 USD) avant détection. Invisible pour Terraform, elle n'apparaissait ni
> dans `terraform state list` ni dans un `terraform destroy`. La gouvernance des
> coûts n'est pas une question comptable : une ressource non gouvernée est une
> ressource non sécurisée et non auditée.

---

## 3. Rôles et responsabilités

### 3.1 Avertissement de portée

Ce projet est un démonstrateur porté par une personne. Le candidat assume
effectivement les rôles **AIA**, **DS** et **DE**. Les autres rôles décrivent la
répartition **cible** en établissement, telle qu'elle devrait être mise en place
avant une exploitation réelle. Le dire est plus solide que de simuler une équipe.

### 3.2 Matrice RACI

**R**esponsable · **A**pprobateur · **C**onsulté · **I**nformé

| Activité | DR | AIA | DS | DE | DPO | RSSI | CE |
|---|---|---|---|---|---|---|---|
| Définir la finalité et le périmètre | **A** | R | I | I | C | I | I |
| Choisir les variables du modèle | C | **A** | R | I | C | I | C |
| Modifier le contrat des variables sensibles | C | R | C | I | C | I | **A** |
| Entraîner et versionner un modèle | I | C | **R** | C | I | I | I |
| Fixer le seuil de décision | **A** | R | C | I | I | I | C |
| Autoriser la mise en production | **A** | R | C | C | C | C | C |
| Traiter une réclamation art. 22 | R | C | C | I | **A** | I | I |
| Déclencher un réentraînement sur dérive | I | **A** | R | R | I | I | I |
| Auditer l'équité | I | C | C | I | C | I | **R/A** |
| Gérer un incident de sécurité | I | C | I | C | C | **R/A** | I |

DR = direction des risques · AIA = architecte IA · DS = data scientist ·
DE = data/MLOps engineer · DPO = délégué à la protection des données ·
RSSI = sécurité SI · CE = comité d'équité

---

## 4. Registre des traitements (RGPD art. 30)

### 4.1 Fiche de traitement

| Rubrique | Contenu |
|---|---|
| **Nom** | Évaluation automatisée de la solvabilité — CrediScore |
| **Responsable de traitement** | CrediScore SA (entité fictive du projet) |
| **Finalité** | Évaluer le risque de défaut afin de décider de l'octroi d'un crédit à la consommation |
| **Base légale** | Art. 6 §1 b) — mesures précontractuelles à la demande de la personne ; art. 6 §1 c) — obligation légale de vérification de solvabilité (C. consom. art. L312-16) |
| **Catégories de personnes** | Demandeurs de crédit à la consommation |
| **Catégories de données** | Identification pseudonymisée · situation professionnelle et de revenus · charges et patrimoine · historique de crédit interne · historique de bureau externe · scores externes |
| **Catégories particulières (art. 9)** | **Aucune** |
| **Destinataires** | Analystes crédit · direction des risques · sous-traitant d'hébergement (AWS, UE) |
| **Transferts hors UE** | **Aucun** (P-1) |
| **Durées de conservation** | Voir §4.2 |
| **Mesures de sécurité** | Chiffrement au repos (SSE-S3/KMS) et en transit (TLS) · IAM au moindre privilège · identités temporaires · journalisation d'audit · blocage de tout accès public |
| **Décision automatisée** | Oui — art. 22 : contrôle humain, explication, contestation (P-5, P-6) |

### 4.2 Durées de conservation

| Donnée | Durée | Justification |
|---|---|---|
| Dossier de demande (zone `raw/`) | 5 ans après la décision | Prescription commerciale ; rejouabilité d'un audit |
| Variables construites (`curated/`) | 5 ans | Reconstitution d'une décision |
| Journal d'audit des décisions | **5 ans** | Art. 22 · AI Act art. 12 |
| Modèles et métriques (MLflow) | 5 ans après retrait du modèle | Traçabilité d'une décision produite par ce modèle |
| Attributs protégés (audit d'équité) | Durée du modèle + 1 an | Strictement nécessaire à la mesure des biais |
| Journaux techniques d'infrastructure | 1 an | Sécurité |

### 4.3 Analyse d'impact (AIPD)

Une AIPD est **obligatoire** : évaluation systématique et automatisée d'aspects
personnels produisant des effets juridiques (RGPD art. 35 §3 a).

Le présent plan en fournit la matière — description du traitement (§1),
nécessité et proportionnalité (P-2), risques pour les personnes (§5), mesures
d'atténuation (§7). **L'AIPD formelle reste à produire et à faire valider par le
DPO** avant toute exploitation réelle : ce point est déclaré comme tel, il n'est
pas escamoté.

---

## 5. Gestion des risques (AI Act art. 9)

Cotation : probabilité (P) et impact (I) de 1 à 4 · criticité = P × I.

| # | Risque | P | I | Crit. | Mesure d'atténuation | Contrôle |
|---|---|---|---|---|---|---|
| R-1 | **Discrimination indirecte** par variable proxy | 3 | 4 | **12** | Exclusion des attributs protégés et de leurs dérivées · détection des proxys par corrélation · mesures d'équité chiffrées | C-1, C-3, C-4 |
| R-2 | **Décision non motivable** au demandeur | 2 | 4 | **8** | SHAP local systématique · aucune variable inexplicable admise (P-2, P-5) | C-5 |
| R-3 | **Dérive** de population non détectée | 3 | 3 | **9** | Suivi PSI/KS sur entrées et scores · réentraînement déclenché par la dérive | C-10 |
| R-4 | **Biais de sélection** : le modèle apprend sur les seuls dossiers acceptés | 4 | 2 | **8** | Limite documentée (D-005) · non corrigée dans le démonstrateur · à traiter par *reject inference* avant exploitation réelle | — |
| R-5 | **Fuite de données personnelles** | 2 | 4 | **8** | Chiffrement · moindre privilège · aucun accès public · pseudonymisation à l'ingestion | C-7, C-8, C-9 |
| R-6 | **Données de mauvaise qualité** publiées au feature store | 3 | 3 | **9** | Contrôles bloquants à l'ingestion · rejets journalisés | C-6 |
| R-7 | **Dépendance aux scores externes** `EXT_SOURCE_*` (3 premiers prédicteurs) | 3 | 3 | **9** | Dépendance documentée · surveillance de leur taux de disponibilité · le modèle doit rester exploitable sans eux | C-10 |
| R-8 | **Perte de reproductibilité** d'une décision contestée | 2 | 4 | **8** | Graine fixée · verrous de dépendances · hachage des données · MLflow | C-11 |
| R-9 | **Automatisation sans contrôle humain** | 2 | 4 | **8** | Procédure de réexamen · le système recommande, il ne décide pas | C-12 |
| R-10 | **Dérapage des coûts cloud** | 3 | 2 | **6** | Tout par Terraform · destruction hors session · alerte budget | P-9 |

**Seuil d'action :** toute criticité ≥ 9 exige une mesure d'atténuation **active
et vérifiable**, pas seulement documentée. R-1, R-3, R-6 et R-7 sont dans ce cas.

---

## 6. Droits des personnes

| Droit | Article | Mise en œuvre |
|---|---|---|
| Information | 13-14 | Mention d'information au dépôt du dossier : existence d'un traitement automatisé, logique, conséquences |
| Accès | 15 | Extraction depuis le journal d'audit par identifiant de dossier |
| Rectification | 16 | Correction en source puis **rescoring tracé** — l'ancienne décision est conservée, jamais écrasée |
| Effacement | 17 | Limité par l'obligation légale de conservation ; effacement à l'échéance des durées du §4.2 |
| Limitation | 18 | Marquage du dossier, suspension du scoring automatique |
| Opposition | 21 | Sans objet : base légale contractuelle et obligation légale |
| **Non-soumission à une décision automatisée** | **22** | **Réexamen humain, expression d'un point de vue, contestation** (P-6) |
| Explication d'une décision individuelle | AI Act art. 86 | Cinq facteurs déterminants issus de SHAP (P-5) |

**Délai de traitement d'une demande : 1 mois**, extensible à 3 mois pour les
demandes complexes (RGPD art. 12 §3).

---

## 7. Contrôles techniques

C'est ici que la gouvernance devient vérifiable. Chaque contrôle a un
propriétaire, un artefact et une date.

| # | Contrôle | Artefact | Statut |
|---|---|---|---|
| **C-1** | Exclusion des variables sensibles, **bloquante** | `src/fairness/contract.py` · `tests/test_no_sensitive_features.py` · `.github/workflows/ci.yml` | ✅ **16/08** — 14 assertions, **exécutées à chaque `push`** |
| **C-2** | Journal d'audit de chaque décision, **bloquant** | `api/journal.py` · `journal.decisions` · `tests/test_api.py` | ✅ **02/09** — si le journal est indisponible, l'API renvoie 500 **sans rendre la décision** ; un test le vérifie en cassant volontairement l'écriture |
| **C-3** | Détection de proxys par corrélation aux attributs protégés | `src/fairness/proxys.py` · `docs/resultats_proxys.csv` | ✅ **31/08** — 223 variables × 3 attributs, valeur **et** motif d'absence · 5 proxys instruits, 1 retirée |
| **C-4** | Mesures d'équité chiffrées par sous-population, **bloquante** | `src/fairness/audit.py` · `docs/note_equite.md` §8 · `docs/resultats_equite.csv` | ✅ **31/08** — M-1 à M-6 sur 3 axes · **a bloqué le déploiement** : M-1 = 0,3082 sur l'âge |
| **C-5** | Explicabilité SHAP globale et locale (< 1 s) **et lisible** | `src/explain/expliquer.py` · `docs/shap_importance_globale.csv` | ✅ **31/08** — 24 ms/dossier · 150 variables montrables, toutes libellées en français |
| **C-6** | Contrôles qualité **bloquants** | `dag_ingestion_quotidienne.py` (sources) · `dag_construction_variables.py` (socle) | ✅ 29/08 — 3 + 4 contrôles, un échec bloque la publication |
| **C-7** | Pseudonymisation des identifiants dans les journaux | `pipelines/spark_jobs/pseudonyme.py` | ✅ 30/08 |
| **C-8** | Chiffrement au repos et en transit | `infra/datalake.tf` (S3) · `infra/compute.tf` (disque VM) | ✅ 30/07 · ✅ 22/08 |
| **C-9** | IAM au moindre privilège | Identity Center · `infra/iam.tf` (2 rôles dérivés du contrat des zones) | ✅ 29/07 · ✅ 22/08 — écriture dans `raw/` refusée, vérifié le 29/08 |
| **C-10** | Détection de dérive PSI/KS → réentraînement | `src/monitoring/derive.py` · DAG `surveillance_derive` · `docs/resultats_derive.csv` | ✅ **02/09** — distingue dérive de **population** (réentraîner) et de **couverture** (corriger la source) ; a trouvé une asymétrie réelle de `bureau_balance` dès la première mesure |
| **C-11** | Reproductibilité : graine, verrous, hachage | `tests/test_reproductibilite.py` · `requirements.lock.txt` · `.terraform.lock.hcl` · empreinte MLflow | ✅ **02/09** — 6 tests exécutables : découpage déterministe, graine hors du code, verrou sans version souple |
| **C-12** | Procédure de contrôle humain (réexamen) | `POST /decisions/{id}/revue` · zone grise de `configs/seuil_decision.yaml` | ✅ **02/09** — tout refus ouvre le réexamen ; la **zone grise l'impose** avant décision sur 11,7 % des dossiers |

**Règle :** un contrôle qui dépasse sa date sans être livré devient un point de
non-conformité à déclarer explicitement en soutenance. Le masquer serait la faute
la plus grave de ce projet.

---

## 8. Matrice de traçabilité

Le tableau que le jury peut dérouler de bout en bout : de l'exigence
réglementaire jusqu'au fichier qui la met en œuvre.

| Exigence | Source | Politique | Contrôle | Preuve vérifiable |
|---|---|---|---|---|
| Examen et atténuation des biais | AI Act art. 10 §2 f) g) | P-4 | C-1, C-3, C-4 | `pytest tests/test_no_sensitive_features.py` |
| Gouvernance et qualité des données | AI Act art. 10 | P-2, P-3 | C-6, C-7 | `docs/schema_jointures.md` · rejets journalisés |
| Documentation technique | AI Act art. 11 | — | — | `docs/` + `decisions.md` (D-001→D-008, D-101→D-104) |
| Enregistrement des journaux | AI Act art. 12 | P-7 | C-2 | Log d'audit horodaté |
| Contrôle humain | AI Act art. 14 | P-6 | C-12 | Procédure de réexamen |
| Exactitude et robustesse | AI Act art. 15 | P-7 | C-10, C-11 | AUC-PR · dérive · runs MLflow |
| Explication d'une décision | AI Act art. 86 · RGPD art. 22 §3 | P-5 | C-5 | 5 facteurs SHAP par dossier |
| Registre des traitements | RGPD art. 30 | — | — | §4 du présent document |
| Sécurité du traitement | RGPD art. 32 | P-8 | C-8, C-9 | `aws s3api get-bucket-encryption` · état Terraform |
| Localisation UE | RGPD chap. V | P-1 | — | Validation bloquante dans `infra/variables.tf` |
| Minimisation | RGPD art. 5 §1 c) | P-2 | — | `docs/plan_features.md` — 28 colonnes retirées sur preuve |

---

## 9. Procédures d'audit

### 9.1 Revue trimestrielle de conformité

| | |
|---|---|
| Fréquence | Trimestrielle, et à chaque mise en production majeure |
| Participants | AIA (anime) · DPO · RSSI · DR |
| Ordre du jour | État des contrôles C-1 à C-12 · incidents · réclamations art. 22 · évolutions réglementaires · dettes de conformité |
| Sorties | Compte rendu · actions datées et nommées · mise à jour de la matrice de risques |
| Déclencheur exceptionnel | Tout incident de sécurité ou toute réclamation fondée |

### 9.2 Revue annuelle d'équité

| | |
|---|---|
| Fréquence | Annuelle, **et à chaque réentraînement** |
| Participants | Comité d'équité (§9.3) |
| Ordre du jour | Mesures d'équité par sous-population · évolution depuis la revue précédente · nouveaux proxys détectés · pertinence des seuils |
| Sorties | Rapport d'équité chiffré · décision de maintien, correction ou retrait du modèle |
| Protocole | `docs/note_equite.md` |

### 9.3 Comité d'équité

**Composition :** DPO (préside) · direction des risques · architecte IA · un
représentant métier · un profil externe à l'équipe de développement.

**Pouvoirs — c'est ce qui en fait un comité et non une formalité :**

- valider ou refuser toute modification de `configs/sensitive_features.yaml` ;
- **exiger le retrait d'un modèle en production** en cas de discrimination avérée ;
- valider les seuils d'équité **avant** toute mesure (§ note d'équité).

**Saisine :** de droit à chaque réentraînement, et à la demande de tout membre.

### 9.4 Registre des revues

Chaque revue produit une entrée horodatée dans `docs/registre_revues.md` :
date, participants, décisions, actions, échéances. **Une revue sans trace écrite
est réputée ne pas avoir eu lieu.**

---

## 10. Modification de ce document

| Type de modification | Approbation requise |
|---|---|
| Correction de forme | AIA seul |
| Ajout ou modification d'un contrôle `C-n` | AIA + entrée dans `decisions.md` |
| Modification d'une politique `P-n` | DR + DPO + entrée dans `decisions.md` |
| **Modification de P-4** (variables sensibles) ou des seuils d'équité | **Comité d'équité, à l'unanimité** |

Toute modification incrémente la version et alimente le §11. **Une politique
qu'on peut changer discrètement n'est pas une politique.**

---

## 11. Journal des révisions

| Version | Date | Modification |
|---|---|---|
| 1.3 | 02/09/2026 | **C-10 et C-11 exécutés — les douze contrôles sont tenus.** La détection de dérive distingue un changement de *population* d'un changement de *couverture de source* : réentraîner sur le second graverait un défaut d'alimentation dans le modèle. Elle a trouvé, dès sa première mesure, que `bureau_balance` couvre 30 % des dossiers d'entraînement contre 86,8 % de ceux à scorer. C-11 devient exécutable : 6 tests au lieu d'une intention. |
| 1.2 | 02/09/2026 | **C-2 et C-12 exécutés.** L'API de scoring journalise chaque décision et refuse d'en rendre une qu'elle ne peut pas tracer. Introduction d'une **zone grise** (0,080 à 0,115), déduite de la courbe de coût et non choisie : sur 11,7 % des dossiers, la machine ne décide pas seule. C-5 étendu à la lisibilité — les 223 variables ont un libellé français. |
| 1.1 | 01/09/2026 | **C-3, C-4 et C-5 exécutés.** C-4 a bloqué le déploiement (M-1 = 0,3082 sur l'âge, seuil 0,05) ; dérogation motivée au §8.9 de la note d'équité. Nouvelle politique **P-10** — traçabilité des scores de tiers, née de la corrélation mesurée entre `EXT_SOURCE_1` et l'âge. |
| 1.0 | 16/08/2026 | Création. Politiques P-1 à P-9, contrôles C-1 à C-12, registre art. 30, matrice de risques, procédures d'audit. Contrôle C-1 implémenté et testé le même jour. |

---

## Documents liés

| Document | Objet |
|---|---|
| [`note_equite.md`](note_equite.md) | Protocole de non-discrimination, métriques, seuils, comité |
| [`decisions.md`](decisions.md) | Journal des décisions d'architecte (D-001 → D-008) |
| [`data_profile.md`](data_profile.md) | Profil mesuré des 8 sources |
| [`schema_jointures.md`](schema_jointures.md) | Intégrité référentielle, couverture, colonnes temporelles |
| [`strategie_decoupage.md`](strategie_decoupage.md) | Protocole d'évaluation et règles anti-fuite |
| [`plan_features.md`](plan_features.md) | Variables construites et traitements |
| `configs/sensitive_features.yaml` | Contrat des variables interdites |
