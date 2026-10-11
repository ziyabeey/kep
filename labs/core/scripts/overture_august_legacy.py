"""Manual Overture August 2026 historical Places research, NEVER 'latest'.

Default is OFFLINE. `--fetch` explicitly reads *2026-08-19.0* Parquet from a
public S3 bucket with DuckDB and two bounded, previously frozen Istanbul cells.
This is research-only metadata, not a verified operating-business list.

Optional dependency: duckdb==1.4.1 (with spatial and httpfs extensions).
No API keys. Do not automatically run in CI or on a schedule.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.overture_places import PILOT, MAX_INPUT_BYTES, MAX_FEATURES, canonical
from kepcore.overture_august import (AUGUST, STAC_URL, S3_PREFIX,
    validate_august_stac, prepare_august_bundle)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'sources/overture_august_research.json'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def source_query(cell: str) -> str:
    """No user-supplied SQL, release, host, bbox or model-driven navigation."""
    if cell not in PILOT: raise ValueError('Unknown study cell')
    west, south, east, north = PILOT[cell]
    return f"""
        SELECT id, ST_X(geometry) AS lon, ST_Y(geometry) AS lat,
               names, categories, basic_category, taxonomy,
               confidence, operating_status, addresses, sources
        FROM read_parquet('{S3_PREFIX}*.parquet', hive_partitioning=false)
        WHERE bbox.xmin BETWEEN {west} AND {east}
          AND bbox.ymin BETWEEN {south} AND {north}
    """


def _catalog() -> bytes:
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(STAC_URL,
        headers={'User-Agent':'KEP-Research-Historical-Places/0.1', 'Cache-Control':'no-cache'})
    with opener.open(req, timeout=20) as response:
        if response.status != 200 or response.geturl() != STAC_URL:
            raise ValueError('Unexpected STAC redirect/response')
        raw = response.read(200_001)
    validate_august_stac(raw)
    return raw


def _minimal_feature(row: tuple) -> dict:
    (rid,lon,lat,names,categories,basic,taxonomy,confidence,operating,addresses,sources)=row
    # Minimal fields only; no phones, socials, emails, websites, photos, reviews.
    first_address=next((x for x in (addresses or []) if isinstance(x,dict)),{})
    attr_sources=[{k:src.get(k) for k in ('dataset','provider','license')}
                  for src in (sources or [])[:8] if isinstance(src,dict)]
    return {'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},
            'properties':{
                'id':rid,'theme':'places','type':'place',
                'names':{'primary':names.get('primary') if isinstance(names,dict) else None},
                'categories':{'primary':categories.get('primary')} if isinstance(categories,dict) else None,
                'basic_category':basic,
                'taxonomy':{'primary':taxonomy.get('primary')} if isinstance(taxonomy,dict) else None,
                'confidence':confidence,'operating_status':operating,
                'addresses':[{'freeform':first_address.get('freeform'),
                              'locality':first_address.get('locality'),
                              'country':first_address.get('country')}],
                'sources':attr_sources}}


def _bounded_duckdb_extract(temporary: Path) -> dict[str, Path]:
    """Public, fixed release query; metadata failure must stop the workflow."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('Manual historical fetch requires pinned duckdb==1.4.1') from exc
    db=duckdb.connect(':memory:')
    paths={}
    try:
        db.execute("SET memory_limit='1GB'")
        db.execute('INSTALL httpfs; LOAD httpfs;')
        db.execute('INSTALL spatial; LOAD spatial;')
        db.execute("SET s3_region='us-west-2'")
        db.execute("SET s3_url_style='path'")
        for cell in sorted(PILOT):
            query=source_query(cell)
            cursor=db.execute(query)
            features=[]
            while True:
                batch=cursor.fetchmany(250)
                if not batch:break
                for row in batch:
                    features.append(_minimal_feature(row))
                    if len(features)>MAX_FEATURES:
                        raise ValueError('Historical window exceeded predefined record limit')
            body=canonical({'type':'FeatureCollection','features':features})
            if not 0<len(body)<=MAX_INPUT_BYTES:
                raise ValueError('Historical source extract empty or oversized; stop, do not fabricate')
            target=temporary/f'{cell}.geojson'
            target.write_bytes(body)
            paths[cell]=target
    finally:
        db.close()
    return paths


def run(output: Path) -> dict:
    from tempfile import TemporaryDirectory
    config=json.loads(CONFIG.read_text(encoding='utf-8'))
    if (config.get('release')!=AUGUST or config.get('schema')!='v1.18.0'
       or config.get('cells')!={k:list(v) for k,v in PILOT.items()}
       or config.get('research_only') is not True
       or config.get('consumer_display_approved') is not False):
        raise ValueError('Unreviewed pinned configuration; abort historical fetch')
    if output.exists():
        raise ValueError('Output directory already exists; never overwrite')
    before=_catalog()
    with TemporaryDirectory(prefix='kep-overture-august-') as tmp:
        paths=_bounded_duckdb_extract(Path(tmp))
        after=_catalog()
        validate_august_stac(after)
        observed=datetime.now(timezone.utc).isoformat()
        report=prepare_august_bundle(paths,output=output,
            stac_bytes=before,observed_at=observed,
            acquisition='historical_duckdb_public_s3',stac_after_bytes=after)
    report['stac_catalog_sha256_before']=sha256(before).hexdigest()
    report['stac_catalog_sha256_after']=sha256(after).hexdigest()
    report['upstream_raw_parquet_preserved']=False
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true',help='Explicit public-S3 historical research download')
    p.add_argument('--output',type=Path,help='New research-only output directory')
    args=p.parse_args()
    if not args.fetch:
        print(json.dumps({'mode':'OFFLINE', 'network_calls':0,
            'release':AUGUST,'schema':'v1.18.0','s3_prefix':S3_PREFIX,
            'pilot_cells':PILOT,'manual_fetch_only':True},sort_keys=True,ensure_ascii=False,indent=2))
        return
    if args.output is None:
        p.error('--fetch requires --output')
    print(json.dumps(run(args.output),sort_keys=True,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
