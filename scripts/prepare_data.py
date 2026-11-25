"""Préparation commune : masquage prudent et séparation fixe par bâtiment.

Génération unique : python scripts/prepare_data.py
Les notebooks réutilisent data/splits/assignments.csv.gz, sans nouveau tirage.
"""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
SOURCE_SHA256 = "2ad294f1e64669e1d92e8a6238b1bed6dbcd8acfc62616b72e0542b5795604de"
TARGET_REG = "conso_5_usages_par_m2_ep"
TARGET_CLF = "etiquette_dpe"
NUMERIC_FEATURES = ["surface_habitable_logement", "hauteur_sous_plafond", "nombre_niveau_logement"]
POLICY = {
    "version": "preparation_v1",
    "height_max_m": 10,
    "levels_max": 10,
    "reason": "Seuils prudents de projet pour les maisons, pas des seuils réglementaires. "
              "Valeurs non positives, non finies ou au-delà des bornes mises à NaN. "
              "Les nombres de niveaux non entiers sont également masqués.",
    "unchanged": "Aucune ligne supprimée ; aucune correction supposée d'unité ; "
                 "pas de plafond sur la surface ou les cibles ; pas d'imputation ni de normalisation.",
}
DTYPES = {c: "string" for c in ["numero_dpe", "numero_dpe_remplace", "id_rnb",
          "code_insee_ban", "code_departement_ban", "code_region_ban"]}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def prepare_inputs(raw, features):
    """Masquer les entrées douteuses dans une copie ; conserver la source intacte."""
    if len(features) != 17 or len(set(features)) != 17:
        raise ValueError("La liste commune doit contenir 17 variables distinctes.")
    forbidden = {TARGET_REG, TARGET_CLF, "emission_ges_5_usages_par_m2", "etiquette_ges",
                 "numero_dpe", "numero_dpe_remplace", "id_rnb", "version_dpe"}
    if forbidden.intersection(features):
        raise ValueError("Cible ou identifiant présent parmi les entrées.")
    data, changes = raw.copy(), []
    checks = {
        "surface_habitable_logement": lambda x: np.isfinite(x) & x.gt(0),
        "hauteur_sous_plafond": lambda x: np.isfinite(x) & x.gt(0) & x.le(POLICY["height_max_m"]),
        "nombre_niveau_logement": lambda x: np.isfinite(x) & x.gt(0) & x.le(POLICY["levels_max"]) & x.mod(1).eq(0),
        "isolation_toiture": lambda x: x.isin([0, 1]),
    }
    for field, check in checks.items():
        values = pd.to_numeric(raw[field], errors="coerce")
        bad = raw[field].notna() & ~check(values).fillna(False)
        for index in raw.index[bad]:
            changes.append({"numero_dpe": raw.at[index, "numero_dpe"], "field": field,
                            "original_value": raw.at[index, field], "action": "set_missing"})
        data[field] = values.mask(bad)
    return data, pd.DataFrame(changes, columns=["numero_dpe", "field", "original_value", "action"])


def building_groups(data):
    """Relier les RNB connus et les chaînes de remplacement, même indirectes."""
    ids = data["numero_dpe"].astype("string").str.strip()
    if ids.isna().any() or ids.eq("").any() or ids.duplicated().any():
        raise ValueError("Les identifiants de diagnostic doivent être uniques et renseignés.")
    parent = {x: x for x in ids}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    first_rnb = {}
    for diagnosis, rnb, old in zip(ids, data["id_rnb"], data["numero_dpe_remplace"]):
        if pd.notna(rnb) and str(rnb).strip():
            key = str(rnb).strip()
            union(diagnosis, first_rnb.setdefault(key, diagnosis))
        if pd.notna(old) and str(old).strip():
            union(diagnosis, str(old).strip())
    return ids.map(lambda x: "g_" + find(x)).rename("group_id")


def make_assignments(data):
    """Cinq plis groupés : trois train, un validation, un test (~60/20/20)."""
    from sklearn.model_selection import StratifiedGroupKFold
    ordered = data.sort_values("numero_dpe").reset_index(drop=True)
    groups = building_groups(ordered)
    folds = np.full(len(ordered), -1)
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    for fold, (_, held_out) in enumerate(splitter.split(
            np.zeros((len(ordered), 1)), ordered[TARGET_CLF], groups)):
        folds[held_out] = fold
    assignments = pd.DataFrame({"numero_dpe": ordered.numero_dpe, "group_id": groups,
                                "split": np.where(folds == 0, "test", np.where(folds == 1, "validation", "train"))})
    validate_assignments(ordered, assignments)
    return assignments


def validate_assignments(data, assignments):
    required = {"numero_dpe", "group_id", "split"}
    if not required.issubset(assignments.columns) or assignments[list(required)].isna().any().any():
        raise ValueError("Fichier de séparation incomplet.")
    if data.numero_dpe.duplicated().any() or assignments.numero_dpe.duplicated().any():
        raise ValueError("Identifiant répété dans les données ou la séparation.")
    if set(assignments.numero_dpe) != set(data.numero_dpe):
        raise ValueError("La séparation ne correspond pas exactement aux diagnostics.")
    if set(assignments.split) != {"train", "validation", "test"}:
        raise ValueError("Les trois ensembles sont requis.")
    expected_groups = pd.Series(building_groups(data).to_numpy(), index=data.numero_dpe)
    indexed = assignments.set_index("numero_dpe")
    if not indexed.group_id.eq(expected_groups.reindex(indexed.index)).all():
        raise ValueError("Groupes incohérents avec les identifiants de bâtiment.")
    if assignments.groupby("group_id").split.nunique().max() != 1:
        raise ValueError("Un bâtiment connu traverse plusieurs ensembles.")
    labels = data.set_index("numero_dpe")[TARGET_CLF]
    for name in ["train", "validation", "test"]:
        subset = assignments.loc[assignments.split.eq(name), "numero_dpe"]
        if set(labels.loc[subset]) != set("ABCDEFG"):
            raise ValueError(f"Classe manquante dans {name}.")


def load_shared_data(base_url):
    """Lire la source et la séparation publiées ; aucun nouvel apprentissage."""
    import requests
    def fetch(relative):
        response = requests.get(base_url.rstrip("/") + "/" + relative, timeout=120)
        response.raise_for_status()
        return response.content
    source = fetch("data/dpe_houses.csv.gz")
    manifest = json.loads(fetch("data/dpe_houses.csv.gz.manifest.json"))
    report = json.loads(fetch("data/splits/manifest.json"))
    assignment_bytes = fetch("data/splits/assignments.csv.gz")
    if sha256(source) != SOURCE_SHA256 or sha256(source) != manifest["sha256"]:
        raise ValueError("La source ne correspond pas à l'échantillon fixé.")
    if report["policy"] != POLICY or report["source_sha256"] != SOURCE_SHA256:
        raise ValueError("Politique ou source de préparation incompatible.")
    if sha256(assignment_bytes) != report["assignments_sha256"]:
        raise ValueError("Le fichier de séparation a changé.")
    raw = pd.read_csv(io.BytesIO(source), compression="gzip", dtype=DTYPES)
    assignments = pd.read_csv(io.BytesIO(assignment_bytes), compression="gzip", dtype="string")
    features = manifest["feature_columns"]
    if len(raw) != 80000 or features != report["features"]:
        raise ValueError("Dimensions ou variables incompatibles.")
    validate_assignments(raw, assignments)
    prepared, changes = prepare_inputs(raw, features)
    prepared = prepared.merge(assignments, on="numero_dpe", how="left", validate="one_to_one")
    splits = {name: prepared.loc[prepared.split.eq(name)].copy()
              for name in ["train", "validation", "test"]}
    return raw, splits, features, changes, report


def main():
    import sklearn
    root = Path(__file__).resolve().parents[1]
    out = root / "data/splits"
    if out.exists():
        raise FileExistsError("La séparation existe déjà : réutiliser les fichiers publiés.")
    source = root / "data/dpe_houses.csv.gz"
    if sha256(source.read_bytes()) != SOURCE_SHA256:
        raise ValueError("Source différente de l'échantillon commun.")
    manifest = json.loads(source.with_name(source.name + ".manifest.json").read_text(encoding="utf-8"))
    raw = pd.read_csv(source, dtype=DTYPES)
    features = manifest["feature_columns"]
    if len(raw) != 80000 or raw[TARGET_REG].isna().any() or not raw[TARGET_CLF].isin(list("ABCDEFG")).all():
        raise ValueError("Échantillon ou cibles invalides.")
    prepared, changes = prepare_inputs(raw, features)
    assignments = make_assignments(raw)
    labels = raw[["numero_dpe", TARGET_CLF]].merge(assignments, validate="one_to_one")
    counts = pd.crosstab(labels.split, labels[TARGET_CLF]).reindex(["train", "validation", "test"])
    out.mkdir(parents=True)
    assignment_file = out / "assignments.csv.gz"
    assignments.to_csv(assignment_file, index=False, compression={"method": "gzip", "mtime": 0})
    changes.to_csv(out / "masked_values.csv", index=False)
    counts.to_csv(out / "class_counts.csv")
    report = {
        "policy": POLICY, "source_sha256": SOURCE_SHA256, "seed": SEED,
        "algorithm": "StratifiedGroupKFold(5), fold 0=test, fold 1=validation, remaining=train",
        "sklearn_version_at_generation": sklearn.__version__, "features": features,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": [c for c in features if c not in NUMERIC_FEATURES],
        "rows": len(raw), "rows_removed": 0, "masked_cells": len(changes),
        "affected_rows": int(changes.numero_dpe.nunique()),
        "masked_by_field": changes.field.value_counts().to_dict(),
        "split_sizes": assignments.split.value_counts().to_dict(),
        "unique_groups": int(assignments.group_id.nunique()), "cross_split_groups": 0,
        "rnb_missing": int(raw.id_rnb.isna().sum()),
        "class_counts": counts.to_dict(orient="index"),
        "assignments_sha256": sha256(assignment_file.read_bytes()),
        "script_sha256": sha256(Path(__file__).read_bytes()),
        "limits": [
            "Les RNB manquants ne permettent pas de garantir l'absence de tout bâtiment commun.",
            "Les références de remplacement sont aussi regroupées ; les liens inconnus restent invisibles.",
            "DPE de versions et années différentes conservés : les cibles ne sont pas harmonisées.",
            "L'exploration descriptive initiale portait sur les 80000 lignes avant la séparation.",
            "Le test est désormais réservé ; toute nouvelle analyse guidant le modèle utilise train.",
            "Les seuils de masquage sont une convention de projet à discuter et tester sur train/validation.",
            "Imputation, encodage, standardisation et sélection doivent être ajustés dans les plis d'entraînement.",
            "Réutiliser les groupes lors de la validation croisée ; ne jamais inclure group_id ou split dans X.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["rows", "masked_by_field", "affected_rows", "split_sizes", "unique_groups", "cross_split_groups", "rnb_missing"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
