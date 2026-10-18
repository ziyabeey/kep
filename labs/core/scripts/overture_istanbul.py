"""KEP-DATA-001 bounded Overture Places pilot, offline by default.

Requires a manual --fetch flag and an external overturemaps CLI for network
acquisition. The CLI's 'latest' is checked against a pinned STAC release both
before and after download, preventing silent source-version drift.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.overture_places import (
    PILOT, MAX_INPUT_BYTES, canonical, check_release, ingest_geojson,
    pilot_audit_plan, valid_stac_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'sources/overture_places_pilot.json'
STAC = 'https://stac.overturemaps.org/catalog.json'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def live_catalog() -> tuple[bytes, str]:
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(STAC, headers={'User-Agent':'KEP-Core-Research/0.1', 'Cache-Control':'no-cache'})
    with opener.open(req, timeout=15) as response:
        if response.status != 200 or response.geturl() != STAC:
            raise ValueError('Unexpected STAC response or redirect')
        body = response.read(200_001)
        if len(body) > 200_000:
            raise ValueError('STAC catalog is too large')
        return body, datetime.now(timezone.utc).isoformat()


def acquire(paths: dict, release: str, *, timeout_seconds: int = 180) -> dict:
    catalog, _ = live_catalog()
    pre = valid_stac_catalog(catalog, pinned=release)
    try:
        client_version = version('overturemaps')
    except PackageNotFoundError as exc:
        raise RuntimeError('Install overturemaps CLI to fetch, never required for offline CI') from exc
    for cell in sorted(paths):
        west, south, east, north = PILOT[cell]
        command = [
            'overturemaps', 'download', '--bbox',
            f'{west},{south},{east},{north}', '-f', 'geojson', '--type', 'place',
            '-o', str(paths[cell]),
        ]
        subprocess.run(command, check=True, timeout=timeout_seconds, capture_output=True, text=True)
        if not Path(paths[cell]).is_file() or Path(paths[cell]).stat().st_size > MAX_INPUT_BYTES:
            raise ValueError('Downloaded cell is missing or exceeds size bound')
    check, retrieved_at = live_catalog()
    post = valid_stac_catalog(check, pinned=release)
    return {'method':'manual_overturemaps_cli_stac_pinned', 'downloaded_at_utc':retrieved_at,
            'client_version':client_version, 'stac_catalog_sha256_before':pre['stac_sha256'],
            'stac_catalog_sha256_after':post['stac_sha256']}


def execute(*, output: Path, inputs: dict | None, fetch: bool, seed_file: Path | None,
            release: str | None = None) -> dict:
    """`release` overrides the DATA-001 pin only for a caller that has already
    checked it against its own frozen protocol (DATA-018 third release)."""
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    release = config['release'] if release is None else check_release(release)
    if set(config['cells']) != set(PILOT) or any(tuple(config['cells'][key]) != PILOT[key] for key in PILOT):
        raise ValueError('Changed pilot bbox must be reviewed in both config and code')
    if fetch and inputs is not None:
        raise ValueError('Cannot combine remote and local data acquisition')
    if not fetch and (inputs is None or set(inputs) != set(PILOT)):
        raise ValueError('Offline processing requires both pilot-cell inputs')
    output.mkdir(parents=True, exist_ok=False)
    if fetch:
        raw_dir = output / 'raw_private'
        raw_dir.mkdir()
        paths = {c:raw_dir / f'{c}.geojson' for c in PILOT}
        proof = acquire(paths, release)
    else:
        paths = inputs
        proof = {'method':'operator_supplied_local_files',
                 'network_fetch_performed':False,
                 'warning':'Local file bytes not independently authenticated as Overture data.'}
    processed = ingest_geojson(paths, pinned_release=release, max_features=config['max_records_total'])
    normalized = {'dataset':'KEP-DATA-001', 'release':release,
                  'study_only':True, 'records':processed['normalized_places']}
    bytes_out = canonical(normalized)
    (output/'places_minimal.json').write_bytes(bytes_out)
    manifest = {
        'study':'KEP-DATA-001', 'pinned_release':release,
        'schema':config['schema'], 'research_only':True,
        'consumer_display_approved':False,
        'license_evidence_url':config['rights']['attribution_url'],
        'sample_cell_bounds_not_district_boundary':config['cells'],
        'acquisition':proof,
        'source_files':processed['source_files'],
        'normalized_sha256':sha256(bytes_out).hexdigest(),
        'population_sha256':processed['population_sha256'],
        'audit':processed['audit'],
        'human_verified_labels':0,
        'no_automatic_entity_merge':True,
        'release_quality_claim':'POI schema/data completeness only; no real-world correctness claim',
    }
    (output/'manifest.json').write_bytes(canonical(manifest))
    if seed_file is not None:
        if seed_file.is_symlink() or not seed_file.is_file():
            raise ValueError('Audit seed must be read from a local non-symlink file')
        seed = seed_file.read_text(encoding='utf-8').strip()
        if len(seed) < 16:
            raise ValueError('Audit seed too short')
        count = len(processed['normalized_places'])
        if count:
            budget = min(count, max(2, min(60, count//10)))
            plan = pilot_audit_plan(processed, budget=budget, seed=seed)
            (output/'audit_plan_unlabeled.json').write_bytes(canonical(plan))
    # No raw snapshots get published by the GH workflow artifact; only minimal fields + manifest.
    return {'output':str(output), 'rows_accepted':processed['audit']['accepted'],
            'potential_duplicates':len(processed['audit']['potential_duplicate_pairs']),
            'acquisition':proof['method'], 'publish_enabled':False}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true',help='Explicit live Overture download; optional overturemaps CLI and network')
    parser.add_argument('--besiktas-geojson',type=Path)
    parser.add_argument('--karakoy-geojson',type=Path)
    parser.add_argument('--output',type=Path,help='New output directory, never overwrite')
    parser.add_argument('--audit-seed-file',type=Path,help='Private seed file, never put the seed in CLI args or git')
    args=parser.parse_args()
    if not args.output:
        print(json.dumps({'mode':'offline_default', 'pinned_release':'2026-09-23.1',
             'network_calls':0, 'required':'Provide both GeoJSON inputs and --output OR --fetch --output',
             'pilot_cells':PILOT}, ensure_ascii=False, indent=2))
        return
    sources=None
    if not args.fetch:
        if not args.besiktas_geojson or not args.karakoy_geojson:
            parser.error('Offline import requires both --besiktas-geojson and --karakoy-geojson')
        sources={'besiktas_center':args.besiktas_geojson,'karakoy_center':args.karakoy_geojson}
    elif args.besiktas_geojson or args.karakoy_geojson:
        parser.error('No local inputs allowed together with --fetch')
    result=execute(output=args.output,inputs=sources,fetch=args.fetch,seed_file=args.audit_seed_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__=='__main__':
    main()
