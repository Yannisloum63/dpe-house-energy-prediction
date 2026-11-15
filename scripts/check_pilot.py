"""Download at most 1,000 records for a quality check, never the full region.

Run from the repository root: python scripts/check_pilot.py --download
Later runs without --download reuse the saved snapshot.
This is an API-order convenience sample, NOT the final stratified sample.
"""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import requests

from extract_dpe import API_URL, COLUMNS, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'pilot'
REPORT = ROOT / 'reports' / 'pilot'
CSV = DATA / 'dpe_region84_pilot_1000.csv.gz'
QUERY = 'type_batiment:maison AND code_region_ban:84'


def download():
    DATA.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    if CSV.exists():
        raise FileExistsError('Snapshot exists. Run without --download to reuse it.')
    with requests.Session() as session:
        response = session.get(API_URL.rsplit('/lines', 1)[0], timeout=60)
        response.raise_for_status()
        metadata = response.json()
        schema = {field['key']: field for field in metadata['schema']}
        absent = sorted(set(COLUMNS) - set(schema))
        if absent:
            raise ValueError(f'Upstream candidate fields absent from schema: {absent}')
        extra = [key for key in ['type_batiment', 'id_rnb'] if key in schema]
        selected = COLUMNS + extra
        params = {'qs': QUERY, 'select': ','.join(selected), 'size': 1000}
        response = session.get(API_URL, params=params, timeout=120)
        response.raise_for_status()
        page = response.json()
        records = page['results']
        if not 0 < len(records) <= 1000:
            raise ValueError('Unexpected pilot record count')
        df = pd.DataFrame(records).reindex(columns=selected)
        if not df['type_batiment'].eq('maison').all():
            raise ValueError('House filter failed')
        if not df['code_region_ban'].astype(str).eq('84').all():
            raise ValueError('Region filter failed')
        df.to_csv(CSV, index=False, compression={'method': 'gzip', 'mtime': 0})
        manifest = {
            'retrieved_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'repository_commit': subprocess.check_output(
                ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
            'source': 'https://data.ademe.fr/datasets/dpe03existant',
            'request_url': response.url, 'query': QUERY,
            'matching_records_at_fetch': page['total'], 'rows_downloaded': len(df),
            'columns': selected, 'candidate_features': FEATURE_COLUMNS,
            'selection': 'First API page in default order; not random or representative.',
            'pagination_followed': False, 'cleaning_applied': False,
            'year_filter': None, 'extra_audit_fields': extra,
            'sha256': hashlib.sha256(CSV.read_bytes()).hexdigest(),
        }
        (DATA / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        (REPORT / 'official_field_metadata.json').write_text(
            json.dumps({key: schema[key] for key in selected}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Saved {len(df)} records; matching region total: {page["total"]}. Pagination NOT followed.')


def profile():
    REPORT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(CSV.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Snapshot checksum mismatch')
    df = pd.read_csv(CSV, dtype={'numero_dpe': 'string', 'numero_dpe_remplace': 'string',
        'code_insee_ban': 'string', 'code_departement_ban': 'string', 'code_region_ban': 'string', 'id_rnb': 'string'})
    summary = pd.DataFrame({
        'field': df.columns, 'dtype': df.dtypes.astype(str).values,
        'missing_count': df.isna().sum().values,
        'missing_pct': (df.isna().mean()*100).round(2).values,
        'distinct_nonmissing': df.nunique().values,
        'role': ['candidate_feature' if c in FEATURE_COLUMNS else 'target_or_audit' for c in df.columns],
    })
    summary.to_csv(REPORT / 'field_quality.csv', index=False, encoding='utf-8-sig')
    values = []
    for col in FEATURE_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            for value, count in df[col].fillna('<MANQUANT>').astype(str).value_counts().head(15).items():
                values.append({'field': col, 'value': value, 'count': int(count)})
    pd.DataFrame(values).to_csv(REPORT / 'categorical_values.csv', index=False, encoding='utf-8-sig')
    df.describe().T.to_csv(REPORT / 'numeric_summary.csv', encoding='utf-8-sig')
    target = pd.to_numeric(df['conso_5_usages_par_m2_ep'], errors='coerce')
    area = pd.to_numeric(df['surface_habitable_logement'], errors='coerce')
    dates = pd.to_datetime(df['date_etablissement_dpe'], errors='coerce')
    rnb = df['id_rnb'].replace(r'^\s*$', pd.NA, regex=True) if 'id_rnb' in df else None
    findings = {
        'rows': len(df), 'columns': len(df.columns), 'candidate_features': len(FEATURE_COLUMNS),
        'target_missing': int(target.isna().sum()), 'target_negative': int(target.lt(0).sum()),
        'target_zero': int(target.eq(0).sum()), 'target_min': float(target.min()),
        'target_median': float(target.median()), 'target_max': float(target.max()),
        'area_nonpositive': int(area.le(0).sum()),
        'duplicate_diagnosis_ids': int(df['numero_dpe'].dropna().duplicated().sum()),
        'replaced_ids_visible_within_pilot': int(df['numero_dpe'].isin(df['numero_dpe_remplace'].dropna()).sum()),
        'invalid_dpe_labels': int((~df['etiquette_dpe'].isin(list('ABCDEFG'))).sum()),
        'date_min': str(dates.min().date()), 'date_max': str(dates.max().date()),
        'rnb_missing': int(rnb.isna().sum()) if rnb is not None else None,
        'rnb_duplicates_among_nonmissing': int(rnb.dropna().duplicated().sum()) if rnb is not None else None,
        'label_counts': {str(k): int(v) for k,v in df['etiquette_dpe'].value_counts(dropna=False).items()},
        'feature_missing_pct': {row['field']: row['missing_pct'] for _,row in summary[summary.role.eq('candidate_feature')].iterrows()},
    }
    (REPORT / 'findings.json').write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if args.download:
        download()
    profile()
