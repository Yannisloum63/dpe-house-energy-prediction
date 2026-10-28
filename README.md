# Predicting the Energy Performance of French Houses

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Yannisloum63/dpe-house-energy-prediction/blob/main/notebook.ipynb)


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
  Data produced by ADEME, extracted and filtered by the authors (extraction date given below).
- **Full dataset:** about 15.9 million DPEs and 230 columns, including 4.7 million houses.
- **Our sample:** houses only, one area, replaced DPEs removed, sample stratified on the energy label.
  It is stored in `data/` so that the notebook loads it directly from GitHub.

| File | Content | Extraction date |
| --- | --- | --- |
| `data/dpe_houses.csv.gz` | DPE sample (to be generated, see below) | to fill in |

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

## Repository structure

```
notebook.ipynb              main notebook: EDA, baseline models, tuning
what_did_not_work.ipynb     approaches we tried and dropped
scripts/extract_dpe.py      reproducible extraction of the sample from the ADEME API
data/                       versioned data used by the notebooks
requirements.txt            extra Python libraries (Colab already has most of them)
```
