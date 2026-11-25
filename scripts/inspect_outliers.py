"""Explorer les entrées brutes de train, sans corriger ni supprimer de valeur."""
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import numpy as np
import pandas as pd

FIELDS = {
    "hauteur_sous_plafond": ("Hauteur sous plafond", "m"),
    "nombre_niveau_logement": ("Nombre de niveaux", "niveaux"),
    "surface_habitable_logement": ("Surface habitable", "m²"),
}


def summarize(raw_train):
    rows = []
    for field, (label, unit) in FIELDS.items():
        values = pd.to_numeric(raw_train[field], errors="raise").dropna()
        q1, q3 = values.quantile([.25, .75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        rows.append({"field": field, "n": len(values), "minimum": values.min(),
                     "q01": values.quantile(.01), "q1": q1, "median": values.median(),
                     "q3": q3, "q99": values.quantile(.99), "maximum": values.max(),
                     "iqr": iqr, "iqr_lower": lower, "iqr_upper": upper,
                     "outside_iqr_count": int((values.lt(lower) | values.gt(upper)).sum()),
                     "iqr_warning": "IQR nul : règle dégénérée, pas de nettoyage automatique" if iqr == 0
                                    else "Repérage statistique uniquement, pas une preuve d'erreur"})
    return pd.DataFrame(rows)


def distribution_figure(raw_train):
    fig, axes = plt.subplots(3, 2, figsize=(13.5, 11), layout="constrained")
    fig.suptitle(f"Entrées brutes du train — {len(raw_train):,} diagnostics\nAvant toute règle de masquage", fontsize=17)
    for row, (field, (label, unit)) in enumerate(FIELDS.items()):
        values = pd.to_numeric(raw_train[field], errors="raise").dropna()
        if (values <= 0).any() or not np.isfinite(values).all():
            raise ValueError("Valeurs non positives/non finies à examiner avant une échelle logarithmique.")
        lo, hi = values.quantile([.01, .99])
        middle = values[values.between(lo, hi)]
        outside = len(values) - len(middle)
        ax = axes[row, 0]
        bins = np.arange(int(lo) - .5, int(hi) + 1.5) if field == "nombre_niveau_logement" else 35
        ax.hist(middle, bins=bins, color="#276b83", edgecolor="white", linewidth=.3)
        ax.set(title=f"{label} : zoom P1–P99\n{outside:,} valeurs hors zoom, conservées à droite",
               xlabel=f"{label} ({unit})", ylabel="Nombre de diagnostics")
        ax.grid(axis="y", alpha=.2)
        ax = axes[row, 1]
        ax.boxplot(values, vert=False, widths=.45, patch_artist=True,
                   boxprops={"facecolor": "#d9e8ed", "edgecolor": "#276b83"},
                   medianprops={"color": "#a04a1b", "linewidth": 2},
                   flierprops={"marker": ".", "markersize": 3, "alpha": .55, "markeredgecolor": "#276b83"})
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.set_yticks([])
        ax.set(title=f"{label} : toutes les valeurs\nBoîte à moustaches ; axe logarithmique",
               xlabel=f"{label} ({unit})")
        ax.grid(axis="x", alpha=.2, which="both")
        q1, q3 = values.quantile([.25, .75])
        if q1 == q3:
            ax.text(.03, .85, "Q1 = Q3 = 2,5 m : boîte réduite à un trait\nUn point hors boîte n'est pas forcément erroné.",
                    transform=ax.transAxes, fontsize=10, color="#8b3f18", va="top")
    return fig


def relationship_figure(raw_train):
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), layout="constrained")
    fig.suptitle("Cohérence entre variables — train brut uniquement", fontsize=16)
    for ax, field in zip(axes, ["hauteur_sous_plafond", "nombre_niveau_logement"]):
        label, unit = FIELDS[field]
        ax.scatter(raw_train.surface_habitable_logement, raw_train[field], s=9, alpha=.18,
                   color="#276b83", edgecolors="none", rasterized=True)
        top = raw_train.nlargest(8, field)
        ax.scatter(top.surface_habitable_logement, top[field], s=38, facecolors="none",
                   edgecolors="#a04a1b", linewidths=1, label="8 plus grandes valeurs verticales, à examiner")
        ax.legend(loc="upper left", fontsize=8)
        ax.set(xscale="log", yscale="log", xlabel="Surface habitable (m², échelle log)",
               ylabel=f"{label} ({unit}, échelle log)")
        ax.grid(alpha=.2, which="both")
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.yaxis.set_major_formatter(ScalarFormatter())
    return fig


def tail_figure(raw_train):
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.5), layout="constrained")
    fig.suptitle("Les 15 plus grandes valeurs de train — aucun seuil présélectionné", fontsize=16)
    for ax, field in zip(axes, ["hauteur_sous_plafond", "nombre_niveau_logement"]):
        values = raw_train[field].nlargest(15).to_numpy()
        ax.plot(range(1, len(values) + 1), values, "o-", color="#276b83", markersize=5)
        for rank, value in enumerate(values, 1):
            ax.annotate(f"{value:g}", (rank, value), xytext=(0, 7), textcoords="offset points",
                        ha="center", fontsize=9)
        label, unit = FIELDS[field]
        ax.set(yscale="log", xlabel="Rang décroissant", ylabel=f"{label} ({unit}, échelle log)",
               xticks=range(1, len(values) + 1))
        ax.set_ylim(values.min() / 1.3, values.max() * 1.7)
        ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.grid(alpha=.2, which="both")
    return fig


def extreme_records(raw_train):
    columns = ["numero_dpe", "periode_construction", *FIELDS, "version_dpe"]
    selected = []
    for field in FIELDS:
        for direction, subset in [("largest_8", raw_train.nlargest(8, field)),
                                  ("smallest_5", raw_train.nsmallest(5, field))]:
            subset = subset[columns].copy()
            subset.insert(0, "selection", direction)
            subset.insert(0, "field_examined", field)
            selected.append(subset)
    return pd.concat(selected, ignore_index=True)


def main():
    root = Path(__file__).resolve().parents[1]
    source, assignment = root / "data/dpe_houses.csv.gz", root / "data/splits/assignments.csv.gz"
    raw = pd.read_csv(source, dtype={"numero_dpe": "string"})
    mapping = pd.read_csv(assignment, dtype="string")
    train_ids = mapping.loc[mapping.split.eq("train"), "numero_dpe"]
    raw_train = raw.set_index("numero_dpe", drop=False).loc[train_ids].reset_index(drop=True)
    if len(raw_train) != 47974 or not raw_train.numero_dpe.is_unique:
        raise ValueError("Ensemble train inattendu.")
    out = root / "reports/outliers_train"
    out.mkdir(parents=True, exist_ok=True)
    summarize(raw_train).to_csv(out / "summary.csv", index=False)
    extreme_records(raw_train).to_csv(out / "extreme_records.csv", index=False)
    for name, plot in [("distributions", distribution_figure), ("relationships", relationship_figure),
                       ("largest_values", tail_figure)]:
        fig = plot(raw_train)
        fig.savefig(out / (name + ".png"), dpi=150)
        plt.close(fig)
    info = {"scope": "train_raw_only", "rows": len(raw_train), "values_changed": 0,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "assignments_sha256": hashlib.sha256(assignment.read_bytes()).hexdigest(),
            "note": "Analyse ajoutée après une proposition initiale de seuils ; elle ne constitue pas une validation a posteriori de ces seuils."}
    (out / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summarize(raw_train).to_string(index=False))


if __name__ == "__main__":
    main()
