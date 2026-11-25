# Predicting the Energy Performance of French Houses

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1xNeqSggpeeaq414OgVXmAWM-mgFp0aQ0?usp=sharing)

Nous travaillons dans [ce Colab partagé](https://colab.research.google.com/drive/1xNeqSggpeeaq414OgVXmAWM-mgFp0aQ0?usp=sharing).
Nous gardons aussi une copie dans [notebook.ipynb](notebook.ipynb).
Après une modification dans Colab, il faut exporter le notebook pour mettre à jour cette copie sur GitHub.

We predict the energy performance of French houses from their physical characteristics only
(surface, construction period, insulation, heating system, climate zone...), using the official
Energy Performance Diagnostics (DPE). The problem is treated in two ways:

| Task | Target | Description |
| --- | --- | --- |
| Regression | `conso_5_usages_par_m2_ep` | Annual primary energy consumption, kWh/m²/year |
| Classification | `etiquette_dpe` | Energy label, 7 classes from A to G |

## Data

- **Source:** [DPE Logements existants (depuis juillet 2021)](https://data.ademe.fr/datasets/dpe03existant), ADEME,
  also published on [data.gouv.fr](https://www.data.gouv.fr/datasets/dpe-logements-existants-depuis-juillet-2021).
- **Licence:** [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
  We extracted and filtered the ADEME data on the date shown below.
- **Full dataset:** about 15.9 million DPEs and 230 columns, including 4.7 million houses.
- **Our sample:** houses only, one area, replaced DPEs removed, sample stratified on the energy label.
  It is stored in `data/` so that the notebook loads it directly from GitHub.

| File | Content | Extraction date |
| --- | --- | --- |
| `data/dpe_houses.csv.gz` | 80,000 house diagnostics, region 84 | 2026-11-17 |

### Préparation et séparation des données

Nous avons gardé le fichier d'origine et fixé le découpage dans `data/splits/assignments.csv.gz` :
environ 60 % pour l'entraînement, 20 % pour la validation et 20 % pour le test.
Les diagnostics que nous avons pu relier au même bâtiment restent dans le même ensemble.
Le détail est dans [nos notes de préparation](docs/data_preparation.md).

Nous avons aussi [examiné les valeurs extrêmes du train](docs/outlier_review.md).
Le seuil de 10 proposé pour la hauteur et le nombre de niveaux reste à vérifier ;
pour l'instant, le notebook conserve ces valeurs.

To regenerate the sample:

```bash
pip install -r requirements.txt
python scripts/extract_dpe.py --region 84 --n 80000
```

In the notebook, the data is loaded with:

```python
import pandas as pd
URL = "https://raw.githubusercontent.com/Yannisloum63/dpe-house-energy-prediction/main/data/dpe_houses.csv.gz"
df = pd.read_csv(URL)
```

### Data leakage

Since the July 2021 reform, the DPE label is the worse of two classes, one computed from primary
energy consumption and one from greenhouse gas emissions. Every column computed by the official
3CL method (consumptions, emissions, costs, needs, heat losses) is therefore excluded from the
model inputs. `emission_ges_5_usages_par_m2` and `etiquette_ges` are kept in the file only to
illustrate this rule in the exploratory analysis.

## Planning et suivi du projet

Nous suivons l’avancement dans
[notre tableau partagé](https://docs.google.com/spreadsheets/d/1p3WM9Ru5RT2jJuyxUvpzaOwex7UnbAlDauQU4YWrPl0/edit).

Nous ajusterons les dates intermédiaires selon ce qu’il nous reste à faire.

## Repository structure

```
notebook.ipynb              main notebook: EDA, baseline models, tuning
what_did_not_work.ipynb     approaches we tried and dropped
scripts/extract_dpe.py      reproducible extraction of the sample from the ADEME API
data/                       versioned data used by the notebooks
requirements.txt            extra Python libraries (Colab already has most of them)
```
