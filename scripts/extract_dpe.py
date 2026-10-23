"""Extract a reproducible sample of houses from the ADEME DPE dataset.

Source: "DPE Logements existants (depuis juillet 2021)", ADEME, Licence Ouverte 2.0
https://data.ademe.fr/datasets/dpe03existant

The script downloads every house ("maison") of the chosen area through the
data-fair API, removes DPEs that were later replaced, keeps a fixed list of
columns and draws a sample stratified on the energy label.

Usage:
    python scripts/extract_dpe.py --region 84 --n 80000
    python scripts/extract_dpe.py --department 63 --n 0   # 0 = keep everything
"""

import argparse
import datetime as dt
import sys
import time

import pandas as pd
import requests

API_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
PAGE_SIZE = 10_000
SEED = 42

# Identifiers, kept only to deduplicate and join other sources
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

# Inputs entered by the diagnostician (candidate features)
FEATURE_COLUMNS = [
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

# Targets, plus the GHG columns used only to show the label rule in the EDA.
# None of these may ever be used as model inputs (data leakage).
TARGET_COLUMNS = [
    "conso_5_usages_par_m2_ep",
    "etiquette_dpe",
    "emission_ges_5_usages_par_m2",
    "etiquette_ges",
]

COLUMNS = ID_COLUMNS + FEATURE_COLUMNS + TARGET_COLUMNS


def fetch_all(query: str) -> pd.DataFrame:
    """Download every line matching `query`, following the API pagination."""
    params = {"qs": query, "select": ",".join(COLUMNS), "size": PAGE_SIZE}
    url, rows = API_URL, []
    with requests.Session() as session:
        while url:
            for attempt in range(5):
                try:
                    response = session.get(url, params=params, timeout=120)
                    response.raise_for_status()
                    break
                except requests.RequestException as error:
                    if attempt == 4:
                        raise
                    print(f"  retry after error: {error}", file=sys.stderr)
                    time.sleep(2 ** (attempt + 1))
            page = response.json()
            rows.extend(page["results"])
            print(f"  {len(rows):>8} / {page['total']} lines", file=sys.stderr)
            # The "next" URL already carries every parameter
            url, params = page.get("next"), None
    return pd.DataFrame(rows).reindex(columns=COLUMNS)


def drop_replaced(df: pd.DataFrame) -> pd.DataFrame:
    """Remove DPEs replaced by a newer one, so a house appears only once."""
    replaced = set(df["numero_dpe_remplace"].dropna())
    df = df[~df["numero_dpe"].isin(replaced)]
    return df.drop_duplicates(subset="numero_dpe")


def stratified_sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Sample n lines keeping the energy label proportions."""
    if n <= 0 or n >= len(df):
        return df
    frac = n / len(df)
    return (
        df.groupby("etiquette_dpe", group_keys=False)
        .sample(frac=frac, random_state=SEED)
        .sample(frac=1, random_state=SEED)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    area = parser.add_mutually_exclusive_group(required=True)
    area.add_argument("--region", help="INSEE region code, e.g. 84")
    area.add_argument("--department", help="department code, e.g. 63")
    parser.add_argument("--n", type=int, default=80_000, help="sample size, 0 = all")
    parser.add_argument("--out", default="data/dpe_houses.csv.gz")
    args = parser.parse_args()

    if args.region:
        area_filter = f"code_region_ban:{args.region}"
    else:
        area_filter = f"code_departement_ban:{args.department}"
    query = f"type_batiment:maison AND {area_filter}"

    print(f"Extraction on {dt.date.today()} with qs = {query}", file=sys.stderr)
    raw = fetch_all(query)
    deduplicated = drop_replaced(raw.dropna(subset=["etiquette_dpe"]))
    sample = stratified_sample(deduplicated, args.n).drop(columns="numero_dpe_remplace")
    sample.to_csv(args.out, index=False)

    print(
        f"{len(raw)} lines downloaded, {len(deduplicated)} after deduplication, "
        f"{len(sample)} written to {args.out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
