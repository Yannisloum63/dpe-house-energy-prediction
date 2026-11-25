# Préparation commune des données

Cette étape fournit les mêmes données et les mêmes ensembles aux trois membres.
Le fichier source de 80 000 diagnostics reste inchangé. Aucun modèle n'est entraîné ici.

**État actuel : le masquage au seuil de 10 est désactivé par défaut.**
L'analyse visuelle sur le train brut doit précéder la décision de traitement :
voir [l'examen des valeurs extrêmes](outlier_review.md).
La version 1 avait proposé de masquer 13 hauteurs et 11 nombres de niveaux,
soit 24 cellules sur 24 diagnostics. Ces nombres restent dans le manifeste
historique ; ils ne décrivent pas le chargement actuel sans masquage.

| Ensemble | Diagnostics |
| --- | ---: |
| Train | 47 974 |
| Validation | 16 007 |
| Test | 16 019 |

Les 78 144 groupes connus ne traversent pas les ensembles. L'écart maximal entre
la proportion d'une classe dans un ensemble et dans la source est de 0,383 point
de pourcentage. Cela ne résout pas les liens de bâtiments inconnus.

## Valeurs suspectes

L'option expérimentale `apply_mask=True` remplace, dans une copie de travail,
les hauteurs sous plafond supérieures à 10 m et les nombres de niveaux supérieurs
à 10 par une valeur manquante. Elle n'est pas activée dans le notebook actuel.
Les valeurs non positives/non finies de surface, hauteur ou nombre de niveaux,
les nombres de niveaux non entiers et les indicateurs d'isolation hors {0, 1}
sont traités de la même façon.

Le seuil de 10 est une convention prudente du projet pour les maisons, **pas une
norme ADEME ni une consigne de l'enseignant**. Elle reste à discuter ; sa sensibilité
pourra être évaluée sur train/validation, jamais en choisissant la meilleure règle
sur le test. Les hauteurs très basses restent à examiner.
On ne devine pas les unités (pas de division automatique par 100), on ne supprime
aucune ligne et on conserve les grandes surfaces ainsi que les consommations élevées.
Le journal historique `data/splits/masked_values.csv` conserve les identifiants et
valeurs concernés par cette proposition. `load_shared_data(..., apply_mask=False)`
conserve les valeurs brutes et renvoie un journal de changements vide.

Les valeurs manquantes sont laissées telles quelles. L'imputation, l'encodage et
la standardisation seront ajustés dans le Pipeline du modèle, sur les données
d'entraînement de chaque pli uniquement. Les trois variables quantitatives sont
la surface, la hauteur et le nombre de niveaux ; les 14 autres entrées sont
catégorielles, y compris l'indicateur binaire d'isolation du toit.

## Séparation commune

Les diagnostics portant le même `id_rnb` sont liés. Les références
`numero_dpe_remplace` relient aussi les diagnostics, y compris par une chaîne de
remplacements ou une référence commune absente du fichier. Les liens sont transitifs.
Sans lien connu, un diagnostic constitue son propre groupe : toutes les valeurs
RNB manquantes ne sont surtout pas regroupées dans un seul bâtiment.

Un [StratifiedGroupKFold à cinq plis](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
avec graine 42 conserve les groupes et cherche à équilibrer les classes A–G.
Les plis 0 et 1 servent respectivement de test et de validation ; les trois autres
forment train, soit environ 60 % / 20 % / 20 %. Les proportions exactes peuvent
varier pour garder chaque groupe entier. Les mêmes ensembles servent à la
régression et à la classification.

**Réutiliser `data/splits/assignments.csv.gz`, sans refaire un tirage.** Les lignes
sont associées par `numero_dpe`, pas par leur position dans le tableau. Le manifeste
enregistre les versions, les effectifs, la politique et les empreintes SHA-256.
Le script de génération refuse d'écraser une séparation existante.

## Utilisation par l'équipe

Dans le Colab partagé, exécuter les cellules jusqu'à la section **5.1**.
Cette section fournit :

- `df_train_raw` : train avant traitement, chargé en section 4.3 ;
- `df_train`, `df_val`, `df_test` : tables avec les groupes, sans masquage par défaut ;
- `X_train`, `X_val`, `X_test` : les 17 entrées uniquement ;
- `y_train_reg`, `y_val_reg`, `y_test_reg` : cibles de régression ;
- `y_train_clf`, `y_val_clf`, `y_test_clf` : cibles de classification ;
- `groups_train` : groupes à conserver lors de la validation croisée.

Pour les nouveaux graphiques qui orientent le modèle, utiliser `df_train`.
Pour la première évaluation, entraîner sur train et mesurer sur validation.
Réserver test à l'évaluation finale. Ne pas inclure les identifiants, `group_id`,
`split` ou les sorties du diagnostic dans les entrées du modèle.

## Limites connues

- 40 698 diagnostics n'ont pas d'identifiant RNB. L'absence de chevauchement des
  groupes **connus** ne prouve pas l'absence de toute répétition de bâtiment.
- Plusieurs années et versions du DPE sont conservées ; les cibles ne sont pas
  harmonisées entre versions. Cette étape n'apporte pas cette garantie.
- Les premières statistiques descriptives ont été examinées sur les 80 000 lignes
  avant le découpage. Cette exposition préalable est documentée ; les choix à venir
  et les nouvelles analyses guidant les modèles doivent se limiter à train/validation.
- La préparation n'est ni une imputation achevée, ni un modèle, ni une évaluation.
