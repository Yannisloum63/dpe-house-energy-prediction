# Préparation des données

Nous utilisons les mêmes 80 000 diagnostics et gardons le fichier d'origine.
Le découpage est fait ; le traitement des valeurs suspectes reste à terminer.
Nous n'avons pas encore entraîné de modèle.

| Ensemble | Diagnostics |
| --- | ---: |
| Train | 47 974 |
| Validation | 16 007 |
| Test | 16 019 |

## Valeurs suspectes

Nous avions d'abord proposé de remplacer par une valeur manquante les hauteurs
supérieures à 10 m et les nombres de niveaux supérieurs à 10. Cela concernait
13 hauteurs et 11 nombres de niveaux, soit 24 cellules sur 24 diagnostics.
Nous avons ensuite [examiné les distributions et les fiches](outlier_review.md).
Pour l'instant, nous gardons les valeurs brutes : le seuil de 10 reste à vérifier.
C'était notre proposition, pas une règle ADEME ni une consigne du cours.

Le notebook utilise donc `load_shared_data(..., apply_mask=False)` :
les valeurs sont conservées et le journal de changements est vide.
Avec `apply_mask=True`, nous pouvons essayer le remplacement dans une copie
de travail. Cette option traite aussi les surfaces, hauteurs et nombres de niveaux
non positifs ou non finis, les niveaux non entiers et les indicateurs d'isolation
hors {0, 1}. Les 24 cellules inscrites dans le manifeste et dans
`data/splits/masked_values.csv` correspondent à cet essai de traitement ;
elles ne sont pas masquées avec le réglage actuel.

Nous n'avons supprimé aucune ligne, corrigé aucune unité supposée ni plafonné
les surfaces ou les consommations. Les hauteurs très basses restent aussi à examiner.
Nous comparerons les traitements sur train/validation, en gardant le test pour la fin.

Les valeurs manquantes restent telles quelles pour le moment. Nous ajusterons
l'imputation, l'encodage et la standardisation dans le Pipeline, uniquement sur
les données d'entraînement de chaque pli. Nous avons trois entrées quantitatives
(surface, hauteur, nombre de niveaux) et 14 entrées catégorielles, dont
l'indicateur binaire d'isolation du toit.

## Découpage

Nous regroupons les diagnostics qui ont le même `id_rnb` ou qui sont reliés
par `numero_dpe_remplace`. Cela comprend les chaînes de remplacement et les
références communes à un diagnostic absent du fichier. Si nous ne trouvons
aucun lien, le diagnostic reste dans son propre groupe. Nous ne regroupons
donc pas tous les RNB manquants ensemble.

Nous avons utilisé [StratifiedGroupKFold à cinq plis](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
avec une graine de 42 pour garder les groupes entiers tout en équilibrant les classes A–G.
Le pli 0 sert de test, le pli 1 de validation et les trois autres d'entraînement,
soit environ 60 % / 20 % / 20 %. Nous utilisons ce même découpage pour la régression
et la classification.

Les 78 144 groupes obtenus ne se chevauchent pas entre les ensembles.
L'écart maximal de proportion d'une classe par rapport au fichier source est de
0,383 point de pourcentage. Des liens entre bâtiments peuvent toutefois nous échapper
lorsque les identifiants manquent.

Pour retrouver ces ensembles, nous chargeons `data/splits/assignments.csv.gz`,
sans refaire de tirage. L'association se fait par `numero_dpe`, pas par position.
Le manifeste garde les versions, les effectifs, les règles de traitement proposées
et les empreintes SHA-256. Le script refuse d'écraser un découpage existant.

## Variables dans le notebook

Après avoir exécuté les cellules du Colab jusqu'à la section **5.1**, nous avons :

- `df_train_raw` : le train avant traitement, chargé en section 4.3 ;
- `df_train`, `df_val`, `df_test` : les tables avec les groupes, sans masquage par défaut ;
- `X_train`, `X_val`, `X_test` : les 17 entrées ;
- `y_train_reg`, `y_val_reg`, `y_test_reg` : les cibles de régression ;
- `y_train_clf`, `y_val_clf`, `y_test_clf` : les cibles de classification ;
- `groups_train` : les groupes à garder ensemble pendant la validation croisée.

Pour la suite, nous partirons de `df_train` pour les graphiques qui orientent
nos choix de modèle. Nous entraînerons sur train, comparerons sur validation
et utiliserons le test pour l'évaluation finale. Les identifiants, `group_id`,
`split` et les sorties du diagnostic restent hors des entrées du modèle.

## Points encore à vérifier

- 40 698 diagnostics n'ont pas d'identifiant RNB. Certains bâtiments peuvent donc
  encore apparaître dans plusieurs ensembles sans que nous puissions les repérer.
- Nous avons gardé plusieurs années et versions du DPE, sans harmoniser les cibles
  entre versions.
- Nous avions regardé les premières statistiques sur les 80 000 lignes avant le
  découpage. Pour la suite, nous limiterons les analyses qui guident nos choix à
  train/validation.
