"""KEP-DATA-019 (Faz 0) runner: Overture extract and Randevu coverage report.

  extract --fetch   Reads Overture (pinned release in the protocol) from the
                    public S3 bucket with DuckDB and writes every Istanbul place
                    with its county name to labs/core/.local/data019/. Needs
                    `pip install duckdb` plus the httpfs and spatial extensions;
                    never used by CI.
  match             Offline. Reads that extract and the private Randevu CSV and
                    writes the aggregate report plus a private match table.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.salon_coverage import evaluate, load_protocol, protocol_sha256, PROTOCOL_PATH

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/data019'
ISTANBUL_BBOX = (27.9, 40.8, 29.95, 41.6)   # xmin, ymin, xmax, ymax; county polygons decide membership


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def git_head() -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def extract(out_dir: Path) -> dict:
    import duckdb  # only on the manual path

    protocol = load_protocol()
    release = protocol['overture']['release']
    base = f's3://overturemaps-us-west-2/release/{release}/theme='
    con = duckdb.connect()
    con.sql('LOAD httpfs')
    con.sql('LOAD spatial')
    con.sql("CREATE SECRET overture_anon (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2')")
    con.sql(f"""
        CREATE TABLE county AS
        SELECT id, names.primary AS name, geometry
        FROM read_parquet('{base}divisions/type=division_area/*')
        WHERE country = 'TR' AND region = 'TR-34' AND subtype = 'county' AND is_land
    """)
    counties = con.sql('SELECT count(*) FROM county').fetchone()[0]
    xmin, ymin, xmax, ymax = ISTANBUL_BBOX
    con.sql(f"""
        CREATE TABLE place AS
        SELECT id, names.primary AS name, ST_Y(geometry) AS lat, ST_X(geometry) AS lon, geometry,
               taxonomy.primary AS category, taxonomy.alternates AS alternates,
               confidence, operating_status, phones,
               list_transform(addresses, a -> a.freeform) AS freeform,
               list_transform(sources, s -> s.update_time) AS update_times,
               list_distinct(list_transform(sources, s -> s.dataset)) AS datasets
        FROM read_parquet('{base}places/type=place/*')
        WHERE bbox.xmin BETWEEN {xmin} AND {xmax} AND bbox.ymin BETWEEN {ymin} AND {ymax}
    """)
    rows = con.sql("""
        SELECT p.id, p.name, p.lat, p.lon, p.category, p.alternates, p.confidence, p.operating_status,
               p.phones, p.freeform, p.update_times, p.datasets, c.name AS district, c.id AS district_id
        FROM place p JOIN county c ON ST_Intersects(c.geometry, p.geometry)
        ORDER BY p.id
    """).fetchall()
    cols = ['id', 'name', 'lat', 'lon', 'category', 'alternates', 'confidence', 'operating_status',
            'phones', 'freeform', 'update_times', 'datasets', 'district', 'district_id']
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'overture_istanbul_places_{release}.jsonl.gz'
    # mtime=0 so the same release gives the same SHA-256 on every run
    with path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as fh:
        for row in rows:
            fh.write((json.dumps(dict(zip(cols, row)), ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))
    receipt = {
        'study': protocol['study'], 'release': release, 'protocol_sha256': protocol_sha256(),
        'code_commit': git_head(), 'extracted_at_utc': datetime.now(timezone.utc).isoformat(),
        'duckdb_version': duckdb.__version__, 'istanbul_bbox': ISTANBUL_BBOX,
        'istanbul_counties': counties, 'places': len(rows), 'extract_file': path.name,
        'extract_sha256': file_sha256(path),
    }
    (out_dir / f'extract_receipt_{release}.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return receipt


def match(randevu_csv: Path, extract_path: Path, out_dir: Path, *, allow_google: bool) -> dict:
    protocol = load_protocol()
    with randevu_csv.open(encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    with gzip.open(extract_path, 'rt', encoding='utf-8') as fh:
        places = [json.loads(line) for line in fh]
    report = evaluate(rows, places, protocol, allow_google=allow_google)
    private = report.pop('_private', None)
    report.update({
        'protocol_sha256': protocol_sha256(), 'code_commit': git_head(),
        'randevu_export_sha256': file_sha256(randevu_csv), 'overture_extract_sha256': file_sha256(extract_path),
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    })
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'coverage_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if private is not None:
        (out_dir / 'coverage_private_matches.json').write_text(json.dumps(private, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    ex = sub.add_parser('extract')
    ex.add_argument('--fetch', action='store_true', help='required: confirms a manual network read')
    ex.add_argument('--out', type=Path, default=LOCAL)
    ma = sub.add_parser('match')
    ma.add_argument('--randevu', type=Path, required=True)
    ma.add_argument('--extract', type=Path, required=True)
    ma.add_argument('--out', type=Path, default=LOCAL)
    ma.add_argument('--allow-google-coords', action='store_true',
                    help='only after Ziya allows it in the thread; adds SENSITIVITY_GOOGLE_COORDS')
    args = ap.parse_args()
    if args.cmd == 'extract':
        if not args.fetch:
            print('extract reads the network; pass --fetch to confirm', file=sys.stderr)
            return 2
        print(json.dumps(extract(args.out), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(match(args.randevu, args.extract, args.out, allow_google=args.allow_google_coords),
                         indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
