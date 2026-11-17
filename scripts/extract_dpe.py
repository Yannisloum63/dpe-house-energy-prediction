"""Extraire un échantillon de maisons depuis les données DPE de l'ADEME.

Source: "DPE Logements existants (depuis juillet 2021)", ADEME, Licence Ouverte 2.0
https://data.ademe.fr/datasets/dpe03existant

Le téléchargement couvre tout le périmètre avant nettoyage et tirage par classe
DPE. Les dates ne sont pas filtrées. Les données manquantes ne sont pas imputées.

Usage:
    python scripts/extract_dpe.py --region 84 --n 80000
    python scripts/extract_dpe.py --department 63 --n 0
    python scripts/extract_dpe.py --region 84 --max-rows 1000 --n 1000
"""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import requests

API_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
PAGE_SIZE = 10_000
SEED = 42

# Identifiants de contrôle, exclus des entrées du modèle.
ID_COLUMNS = [
    "numero_dpe",
    "numero_dpe_remplace",
    "date_etablissement_dpe",
    "code_insee_ban",
    "code_departement_ban",
    "code_region_ban",
    "coordonnee_cartographique_x_ban",
    "coordonnee_cartographique_y_ban",
]

# Champs historiques conservés pour l'audit et la comparaison.
CANDIDATE_COLUMNS = [
    "surface_habitable_logement",
    "annee_construction",
    "periode_construction",
    "hauteur_sous_plafond",
    "nombre_niveau_logement",
    "zone_climatique",
    "classe_altitude",
    "classe_inertie_batiment",
    "qualite_isolation_enveloppe",
    "qualite_isolation_murs",
    "qualite_isolation_plancher_bas",
    "qualite_isolation_menuiseries",
    "qualite_isolation_plancher_haut_comble_perdu",
    "qualite_isolation_plancher_haut_comble_amenage",
    "qualite_isolation_plancher_haut_toit_terrasse",
    "isolation_toiture",
    "type_energie_principale_chauffage",
    "type_installation_chauffage",
    "type_generateur_chauffage_principal",
    "type_emetteur_installation_chauffage_n1",
    "type_energie_principale_ecs",
    "type_ventilation",
    "presence_production_pv",
    "surface_totale_capteurs_pv",
]

# Sorties du diagnostic : ne jamais les utiliser comme entrées.
TARGET_COLUMNS = [
    "conso_5_usages_par_m2_ep",
    "etiquette_dpe",
    "emission_ges_5_usages_par_m2",
    "etiquette_ges",
]

RESERVED_COLUMNS = [
    "annee_construction", "type_installation_chauffage",
    "type_generateur_chauffage_principal", "presence_production_pv",
    "surface_totale_capteurs_pv", "qualite_isolation_plancher_haut_comble_perdu",
    "qualite_isolation_plancher_haut_comble_amenage",
    "qualite_isolation_plancher_haut_toit_terrasse",
]

# 17 entrées provisoires. « n1 » décrit la première installation de chauffage.
FEATURE_COLUMNS = [c for c in CANDIDATE_COLUMNS if c not in RESERVED_COLUMNS] + [
    "type_installation_chauffage_n1"
]
AUDIT_COLUMNS = [
    "type_batiment", "id_rnb", "version_dpe",
    "type_installation_chauffage_n2", "ventilation_posterieure_2012",
]
PILOT_COLUMNS = ID_COLUMNS + CANDIDATE_COLUMNS + TARGET_COLUMNS
COLUMNS = list(dict.fromkeys(PILOT_COLUMNS + FEATURE_COLUMNS + AUDIT_COLUMNS))


def fetch_all(query: str, max_rows: int = 0) -> pd.DataFrame:
    """Suivre la pagination ; max_rows réserve un mode de vérification limité."""
    if max_rows < 0:
        raise ValueError("max_rows doit être positif ou nul.")
    params = {"qs": query, "select": ",".join(COLUMNS),
              "size": min(PAGE_SIZE, max_rows) if max_rows else PAGE_SIZE}
    url, rows = API_URL, []
    total, visited = None, set()
    with requests.Session() as session:
        metadata = session.get(API_URL.rsplit("/lines", 1)[0], timeout=60)
        metadata.raise_for_status()
        schema = {field["key"] for field in metadata.json()["schema"]}
        absent = set(COLUMNS) - schema
        if absent:
            raise ValueError(f"Champs absents du schéma ADEME : {sorted(absent)}")
        while url:
            if url in visited:
                raise ValueError("Pagination répétée : extraction interrompue.")
            visited.add(url)
            for attempt in range(5):
                try:
                    response = session.get(url, params=params, timeout=120)
                    response.raise_for_status()
                    break
                except requests.RequestException as error:
                    if attempt == 4:
                        raise
                    print(f"  Nouvelle tentative : {error}", file=sys.stderr)
                    time.sleep(2 ** (attempt + 1))
            page = response.json()
            # Les pages suivantes peuvent omettre total : garder celui de départ.
            page_total = page.get("total")
            if total is None or "total" in page:
                if type(page_total) is not int or page_total < 0:
                    raise ValueError("Nombre total absent ou invalide dans la réponse ADEME.")
                if total is not None and page_total != total:
                    raise ValueError("Le volume source a changé pendant l'extraction. Relancer.")
                total = page_total
            if max_rows and len(page["results"]) > max_rows - len(rows):
                raise ValueError("L'API a dépassé la limite demandée.")
            rows.extend(page["results"])
            print(f"  {len(rows):>8} / {total} lignes", file=sys.stderr)
            if max_rows and len(rows) >= max_rows:
                break
            # L'URL suivante contient déjà les filtres et le curseur.
            url, params = page.get("next"), None
            if url and max_rows:
                parts = urlsplit(url)
                query_params = dict(parse_qsl(parts.query))
                query_params["size"] = min(PAGE_SIZE, max_rows - len(rows))
                url = urlunsplit(parts._replace(query=urlencode(query_params)))
    expected = min(total, max_rows) if max_rows else total
    if len(rows) != expected:
        raise ValueError(f"Extraction incomplète : {len(rows)} lignes au lieu de {expected}.")
    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    df.attrs["source_total"] = total
    return df


def drop_replaced(df: pd.DataFrame) -> pd.DataFrame:
    """Retirer les remplacements connus dans le périmètre, pas dédupliquer les bâtiments."""
    replaced = set(df["numero_dpe_remplace"].dropna())
    df = df[~df["numero_dpe"].isin(replaced)]
    return df.drop_duplicates(subset="numero_dpe")


def clean_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Filtrer les erreurs certaines, sans supprimer les lignes pour un simple manque."""
    df = raw.copy()
    for field in ["numero_dpe", "numero_dpe_remplace", "id_rnb"]:
        df[field] = df[field].astype("string").str.strip().replace("", pd.NA)
    log = {"raw_rows": len(df)}
    # Détecter les remplacements avant d'écarter une nouvelle fiche invalide.
    replaced = set(df["numero_dpe_remplace"].dropna())
    steps = [
        ("missing_diagnosis_id", lambda d: d["numero_dpe"].isna()),
        ("replaced_diagnoses", lambda d: d["numero_dpe"].isin(replaced)),
        ("duplicate_diagnosis_ids", lambda d: d["numero_dpe"].duplicated()),
    ]
    for reason, mask_fn in steps:
        mask = mask_fn(df)
        log[reason] = int(mask.sum())
        df = df.loc[~mask].copy()
    df["etiquette_dpe"] = df["etiquette_dpe"].astype("string").str.strip().str.upper()
    target = pd.to_numeric(df["conso_5_usages_par_m2_ep"], errors="coerce")
    area = pd.to_numeric(df["surface_habitable_logement"], errors="coerce")
    df["conso_5_usages_par_m2_ep"], df["surface_habitable_logement"] = target, area
    for reason, valid in [
        ("invalid_dpe_label", df["etiquette_dpe"].isin(list("ABCDEFG"))),
        ("invalid_regression_target", target.notna() & target.ge(0) & target.lt(float("inf"))),
        ("invalid_surface", area.notna() & area.gt(0) & area.lt(float("inf"))),
    ]:
        mask = valid.reindex(df.index).fillna(False)
        log[reason] = int((~mask).sum())
        df = df.loc[mask].copy()
    log["eligible_rows"] = len(df)
    return df.sort_values("numero_dpe"), log


def stratified_sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Tirer exactement n lignes par allocation proportionnelle aux classes DPE."""
    if n < 0:
        raise ValueError("n doit être positif ou nul.")
    if n == 0 or n >= len(df):
        return df
    counts = df["etiquette_dpe"].value_counts().sort_index()
    quotas = counts * n / len(df)
    sizes = quotas.astype(int)
    # Les plus grands restes absorbent les arrondis sans changer le total demandé.
    remainder = (quotas - sizes).sort_values(ascending=False, kind="stable")
    sizes.loc[remainder.index[:n - int(sizes.sum())]] += 1
    parts = [df.loc[df["etiquette_dpe"].eq(label)].sample(n=int(size), random_state=SEED)
             for label, size in sizes.items() if size]
    return pd.concat(parts).sample(frac=1, random_state=SEED).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    area = parser.add_mutually_exclusive_group(required=True)
    area.add_argument("--region", help="Code région INSEE, par exemple 84")
    area.add_argument("--department", help="Code département, par exemple 63 ou 2A")
    parser.add_argument("--n", type=int, default=80_000, help="Nombre final souhaité ; 0 = tout conserver")
    parser.add_argument("--max-rows", type=int, default=0, help="Limiter le téléchargement pour un essai ; 0 = périmètre complet")
    parser.add_argument("--out", help="Fichier de sortie CSV ou CSV.gz")
    args = parser.parse_args()
    if args.n < 0 or args.max_rows < 0:
        parser.error("--n et --max-rows doivent être positifs ou nuls.")
    code = args.region or args.department
    if not re.fullmatch(r"[0-9A-Za-z]+", code):
        parser.error("Code géographique invalide.")
    out = Path(args.out or ("data/dpe_houses_preview.csv.gz" if args.max_rows else "data/dpe_houses.csv.gz"))
    record = out.with_name(out.name + ".manifest.json")
    if out.exists() or record.exists():
        parser.error("La sortie existe déjà. Utiliser --out pour une nouvelle version.")
    if args.region:
        area_filter = f"code_region_ban:{args.region}"
    else:
        area_filter = f"code_departement_ban:{args.department}"
    query = f"type_batiment:maison AND {area_filter}"

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    print(f"Extraction : {query}. --n limite le tirage final, pas le téléchargement.", file=sys.stderr)
    raw = fetch_all(query, max_rows=args.max_rows)
    area_column = "code_region_ban" if args.region else "code_departement_ban"
    if not raw["type_batiment"].eq("maison").all() or not raw[area_column].astype(str).eq(code).all():
        raise ValueError("Le résultat ne respecte pas le filtre géographique ou le type de bâtiment.")
    eligible, cleaning = clean_data(raw)
    if eligible.empty:
        raise ValueError("Aucune ligne exploitable après nettoyage.")
    sample = stratified_sample(eligible, args.n)
    if args.n > len(eligible):
        print(f"Seulement {len(eligible)} lignes exploitables, toutes conservées.", file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    compression = {"method": "gzip", "mtime": 0} if out.suffix == ".gz" else None
    sample.to_csv(out, index=False, compression=compression)
    rnb = sample["id_rnb"].dropna()
    dates = pd.to_datetime(sample["date_etablissement_dpe"], errors="coerce")
    manifest = {
        "source": API_URL, "query": query, "started_at_utc": started,
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "verification_limitee" if args.max_rows else "echantillon_projet",
        "year_filter": None, "seed": SEED, "requested_rows": args.n,
        "download_limit": args.max_rows, "source_total": raw.attrs["source_total"],
        "cleaning": cleaning, "saved_rows": len(sample), "feature_columns": FEATURE_COLUMNS,
        "columns": list(sample.columns),
        "class_counts_eligible": eligible["etiquette_dpe"].value_counts().sort_index().to_dict(),
        "class_counts_sample": sample["etiquette_dpe"].value_counts().sort_index().to_dict(),
        "feature_missing_pct": sample[FEATURE_COLUMNS].isna().mean().mul(100).round(3).to_dict(),
        "version_counts": sample["version_dpe"].fillna("inconnue").astype(str).value_counts().to_dict(),
        "diagnosis_year_counts": dates.dt.year.fillna(-1).astype(int).value_counts().sort_index().to_dict(),
        "invalid_dates": int(dates.isna().sum()), "rnb_missing": int(sample["id_rnb"].isna().sum()),
        "rnb_repeated_occurrences": int(rnb.duplicated().sum()),
        "limits": ["Remplacements connus uniquement dans le périmètre téléchargé.",
                   "Plusieurs diagnostics peuvent encore concerner le même bâtiment.",
                   "Versions DPE et groupes de bâtiments à vérifier avant la séparation entraînement/test.",
                   "Aucune imputation, normalisation ou séparation entraînement/test effectuée.",
                   "Le mode limité suit l'ordre API et ne constitue pas un échantillon représentatif."],
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(raw)} lignes reçues, {len(eligible)} exploitables, {len(sample)} enregistrées dans {out}", file=sys.stderr)
    print(f"Journal : {record}", file=sys.stderr)


if __name__ == "__main__":
    main()
