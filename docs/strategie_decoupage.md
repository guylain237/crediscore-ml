# Stratégie de découpage train / validation / test

Ce document fixe le protocole d'évaluation **avant** tout entraînement. L'ordre
n'est pas une formalité : un protocole écrit après coup se plie toujours aux
résultats obtenus.

Les chiffres proviennent de [`data_profile.md`](data_profile.md) et de
[`schema_jointures.md`](schema_jointures.md), tous deux générés par script sur
l'intégralité des données.

---

## 1. Le constat qui commande tout : aucune temporalité absolue

Le plan de projet prévoyait un découpage **temporel si possible**. La mesure
tranche : **ce n'est pas possible**, et il faut le dire clairement plutôt que
simuler une rigueur qu'on n'a pas.

Les 14 colonnes temporelles des 8 sources sont **toutes** des décalages relatifs,
comptés depuis la date de la demande courante — laquelle n'est jamais fournie :

| Colonne | Amplitude mesurée | Nature |
|---|---|---|
| `DAYS_BIRTH` | −25 229 → −7 489 | jours avant la demande |
| `DAYS_CREDIT` (bureau) | −2 922 → 0 | jours avant la demande |
| `DAYS_DECISION` (previous) | −2 922 → −1 | jours avant la demande |
| `MONTHS_BALANCE` | −96 → 0 | mois avant la demande |

Aucune colonne texte des 8 fichiers n'est convertible en date absolue — vérifié
par script, pas supposé.

**Conséquence :** deux dossiers dont `DAYS_BIRTH = −12 000` peuvent avoir été
déposés à trois ans d'intervalle. Rien ne permet de les ordonner. Une validation
*out-of-time* — entraîner sur le passé, valider sur le futur — est donc
**structurellement impossible**, et non simplement écartée par facilité.

### Ce que cela nous coûte, et comment nous le compensons

Une validation *out-of-time* mesure la résistance du modèle à la dérive : la
population de demandeurs, les conditions économiques et les politiques d'octroi
changent avec le temps. Nous ne pouvons pas mesurer cette résistance hors ligne.

La parade n'est pas de faire semblant, mais de **déplacer le contrôle en
production** :

| Ce qu'on ne peut pas faire hors ligne | Le contrôle compensatoire mis en place |
|---|---|
| Valider sur une période postérieure | Détection de dérive en continu (Evidently, PSI / KS) sur les variables d'entrée et sur la distribution des scores |
| Mesurer la décroissance de performance dans le temps | Suivi de l'AUC glissante dès que les défauts observés remontent, avec seuil d'alerte |
| Décider a priori d'une fréquence de réentraînement | Réentraînement **déclenché par la dérive**, pas par le calendrier |

C'est une limite du jeu de données, assumée et documentée — et le contrôle
compensatoire est précisément ce que le pipeline de données et la chaîne
d'industrialisation mettent en œuvre.

---

## 2. Le découpage retenu

**Découpage aléatoire stratifié sur la cible, en trois jeux disjoints, au grain
`SK_ID_CURR`.**

| Jeu | Part | Dossiers | Défauts attendus | Rôle |
|---|---|---|---|---|
| Entraînement | 60 % | 184 507 | 14 895 | apprentissage des paramètres |
| Validation | 20 % | 61 502 | 4 965 | choix des hyperparamètres, du seuil de décision, arrêt anticipé |
| Test | 20 % | 61 502 | 4 965 | **estimation finale, une seule utilisation** |

Total : 307 511 dossiers, 24 825 défauts (**8,07 %**).

### Pourquoi ces choix

**Stratification sur `TARGET`.** À 8,07 % de positifs, un découpage purement
aléatoire ferait varier le taux de défaut de plusieurs dixièmes de point d'un
jeu à l'autre — assez pour rendre deux expériences incomparables. La
stratification garantit un taux identique dans les trois jeux.

**Grain `SK_ID_CURR`, et pas la ligne.** `application_train` contient
307 511 lignes pour 307 511 identifiants distincts : un dossier = une ligne, la
vérification est faite. Le découpage ne peut donc pas couper un dossier en deux.
Cette vérification n'est pas superflue — sur les tables filles, une ligne ≠ un
dossier, et un découpage naïf y provoquerait une fuite immédiate.

**Un jeu de test scellé.** Le test n'est ouvert qu'une fois, à la toute fin, pour
produire le chiffre communiqué. Tout ajustement effectué après l'avoir consulté
le transforme en second jeu de validation, et le chiffre annoncé devient
optimiste. Cette règle est plus facile à écrire qu'à tenir : elle est donc posée
ici, par avance.

**Trois jeux plutôt qu'une validation croisée seule.** La validation croisée sert
à l'optimisation ; un jeu de test indépendant sert à l'estimation finale. Les
confondre revient à choisir ses hyperparamètres sur la donnée qui les évalue.

### Le cas de `application_test.csv`

Ce fichier de 48 744 dossiers **ne contient pas `TARGET`** (121 colonnes contre
122). Il ne peut donc servir à aucune évaluation. Son usage dans ce projet est
strictement opérationnel : **répétition à blanc de l'inférence** — même schéma,
même pipeline de features, même format de sortie — pour valider le service de
scoring de bout en bout. Il ne produit aucune métrique.

Vérification faite : **0 identifiant commun** entre `application_train` et
`application_test`. Les deux populations sont disjointes.

---

## 3. Protocole d'évaluation

**Validation croisée stratifiée à 5 plis, sur le jeu d'entraînement uniquement**
(`StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)`).

1. Optimisation des hyperparamètres par validation croisée sur l'entraînement.
2. Sélection du **seuil de décision** sur le jeu de validation, par minimisation
   du coût métier — pas sur un critère statistique. Un défaut coûte le capital
   prêté, un bon client refusé ne coûte qu'un manque à gagner : ces deux erreurs
   n'ont pas le même prix, et le seuil de 0,5 n'a aucune justification ici.
3. Réentraînement du modèle retenu sur entraînement + validation.
4. Évaluation **unique** sur le test scellé.

### Métriques, dans cet ordre

| Métrique | Pourquoi |
|---|---|
| **Coût métier** (€ par dossier) | la seule qui décide ; intègre l'asymétrie des erreurs |
| **AUC-PR** | adaptée aux classes déséquilibrées : se concentre sur la classe rare |
| **AUC-ROC** | comparabilité avec la littérature et les benchmarks du secteur |
| **Brier / courbe de calibration** | une probabilité affichée à un client doit être juste, pas seulement bien ordonnée |
| **Écarts d'équité par sous-population** | exigence AI Act, mesurée sur les variables réservées à l'audit |

L'AUC-ROC seule est trompeuse à 8 % de positifs : un modèle peut afficher 0,75
tout en étant inutilisable sur la population qui compte.

---

## 4. Prévention des fuites — les règles opposables

Une fuite ne se voit pas : elle produit d'excellents résultats hors ligne et un
échec en production. D'où des règles écrites, testées, plutôt qu'une vigilance.

**R1 — Aucune statistique globale avant découpage.** Imputations, encodages de
variables catégorielles par la cible, normalisations : tous ajustés sur le seul
jeu d'entraînement, puis appliqués tels quels à validation et test. Un `fit` sur
l'ensemble complet fait fuiter la distribution du test dans le modèle.

**R2 — Les agrégats des tables filles sont calculés par dossier.** Chaque
variable `BUREAU_*`, `PREV_*`, `INSTAL_*` n'utilise que l'historique **du dossier
concerné**. Aucune information ne traverse la frontière entre dossiers, donc ces
agrégats peuvent être calculés avant le découpage sans risque. C'est la
distinction avec R1, et elle est subtile : ce n'est pas *quand* on calcule qui
compte, c'est *sur quelle population*.

**R3 — Aucune variable postérieure à la demande.** Vérifié par la mesure :
`DAYS_DECISION` plafonne à −1, `MONTHS_BALANCE` à 0, `DAYS_INSTALMENT` à −1.
Toutes les informations sont antérieures ou concomitantes à la demande.

> Exception apparente à documenter : `DAYS_CREDIT_ENDDATE` monte à +31 199 jours.
> Il s'agit d'une date de **fin prévue** d'un crédit externe en cours, connue au
> moment de la demande — donc légitime. La valeur extrême (85 ans) est en
> revanche une anomalie de qualité à écrêter.

**R4 — Le test ne sert qu'une fois.** Voir §2.

**R5 — Les variables sensibles n'entrent jamais dans les features.** Contrat
`configs/sensitive_features.yaml`, vérifié par `tests/test_no_sensitive_features.py`
(décision D-003). Ce n'est pas une fuite au sens statistique, mais une fuite de
conformité — aux conséquences juridiques bien plus lourdes.

---

## 5. Reproductibilité

| Élément | Mise en œuvre |
|---|---|
| Graine aléatoire | constante unique `SEED`, dans `configs/`, jamais redéfinie localement |
| Indices des trois jeux | sauvegardés et hachés ; le hachage est journalisé dans MLflow |
| Version des données | hachage du snapshot de la zone `raw/` du data lake (décision D-002) |
| Environnement | `requirements.lock.txt` (décision D-004) |

Un résultat que l'on ne sait pas reproduire n'est pas un résultat. Ces quatre
éléments réunis permettent de rejouer à l'identique n'importe quelle expérience
publiée.

---

## 6. Ce que ce protocole ne démontre pas

Par honnêteté méthodologique, les limites à énoncer :

- **Aucune garantie de tenue dans le temps** — impossible à mesurer ici (§1).
- **Aucune garantie sur une population différente** : le modèle est validé sur
  des demandeurs Home Credit, pas sur une autre clientèle ni un autre pays.
- **Le taux de défaut de 8,07 % est celui des dossiers acceptés**, pas de la
  population des demandeurs. Les dossiers refusés n'ont pas de `TARGET` observé :
  c'est un **biais de sélection** classique en scoring d'octroi. Le modèle
  apprend donc à prédire le défaut *sachant que le dossier a été accepté par la
  politique en vigueur* — pas le risque intrinsèque du demandeur. Le corriger
  (*reject inference*) dépasse le cadre de ce projet, mais l'ignorer serait une
  faute d'analyse.
