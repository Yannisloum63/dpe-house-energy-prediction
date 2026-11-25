# Préparation des données

La section **5.1 du notebook** charge les 80 000 diagnostics et les répartit
selon `data/splits/assignments.csv.gz`. Ce fichier permet de retrouver les mêmes
ensembles à chaque exécution, pour la régression comme pour la classification.

| Ensemble | Diagnostics | Usage |
| --- | ---: | --- |
| Train | 47 974 | Entraînement et choix du prétraitement |
| Validation | 16 007 | Comparaison des modèles |
| Test | 16 019 | Évaluation finale |

## Variables disponibles

- `df_train_raw` : train brut utilisé pour les graphiques de la section 4.3.
- `df_train`, `df_val`, `df_test` : tables avec les identifiants de groupe.
- `X_train`, `X_val`, `X_test` : 17 entrées — 3 quantitatives (surface, hauteur,
  niveaux) et 14 catégorielles, dont l'indicateur d'isolation du toit.
- `y_*_reg` : consommation conventionnelle d'énergie primaire par m².
- `y_*_clf` : classe DPE A–G.
- `groups_train` : groupes à garder ensemble pendant la validation croisée.

L'imputation, l'encodage et la standardisation sont à ajuster dans le Pipeline,
sur les données d'entraînement de chaque pli. Les identifiants, `group_id`,
`split` et les sorties du diagnostic ne sont pas des entrées du modèle.

## Découpage par bâtiment

Les diagnostics sont reliés par `id_rnb` et `numero_dpe_remplace`, y compris
les chaînes de remplacement et les références communes. Sans lien connu,
un diagnostic forme son propre groupe.

[StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
à cinq plis, avec une graine de 42 : pli 0 pour test, pli 1 pour validation,
les trois autres pour train. Les 78 144 groupes ne se chevauchent pas entre
ensembles ; l'écart maximal de proportion d'une classe par rapport à la source
est de 0,383 point de pourcentage. Les affectations sont associées par `numero_dpe`.

**Limites :** 40 698 diagnostics sans RNB peuvent cacher des répétitions de bâtiment.
Les cibles de plusieurs versions du DPE sont conservées sans harmonisation.
Les statistiques générales des sections 4.1, 4.2 et 4.4 portent sur les 80 000 lignes ;
les analyses guidant les modèles doivent utiliser train/validation.

## Valeurs suspectes et options de chargement

`load_shared_data(..., apply_mask=True)`, utilisé dans le notebook, remplace
par une valeur manquante :

- les hauteurs supérieures à 10 m et les nombres de niveaux supérieurs à 20 ;
- les surfaces, hauteurs et niveaux non positifs ou non finis ;
- les niveaux non entiers et les indicateurs d'isolation hors {0, 1}.

Ces bornes de projet isolent les écarts les plus marqués du train
([graphiques et justification](outlier_review.md)) ; ce ne sont pas des normes ADEME.
Elles s'appliquent à l'identique aux trois ensembles.
`data/splits/masked_values.csv` liste les 20 cellules remplacées :
13 hauteurs et 7 nombres de niveaux, sur 20 diagnostics. Le train en contient 9.
Les niveaux 10, 11 et 15, les grandes surfaces et les hauteurs basses restent inchangés.

Les valeurs manquantes seront remplies dans le Pipeline d'entraînement.
Aucune ligne n'est supprimée et le fichier source reste intact.
`apply_mask=False` permet de charger les valeurs brutes pour comparer les modèles.
