#!/usr/bin/env python3
"""Optional live downloader for the reviewed İzmir open-data endpoint.

Not invoked by tests. Requires --download and network access. Saves a new file;
never replaces the checked fixture or silently imports new data into the core.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
import argparse,hashlib,json,socket,sys
URL='https://openapi.izmir.bel.tr/api/ibb/kultursanat/etkinlikler'
FIELDS=['Id','Tur','Adi','EtkinlikBaslamaTarihi','EtkinlikBitisTarihi','EtkinlikMerkezi','UcretsizMi','EtkinlikUrl','BiletSatisLinki']
MAX_BYTES=10_000_000
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise RuntimeError('Redirect refused: review the new endpoint before use')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download',action='store_true')
    p.add_argument('--user-agent',default='KEPResearch/0.2 (small open-data validation request)')
    p.add_argument('--out',type=Path,default=Path('data/raw/live_izmir_events.json'))
    args=p.parse_args()
    if not args.download:
        p.error('No implicit network calls. Add --download to fetch the reviewed endpoint.')
    if args.out.exists():p.error('Output exists; choose a new --out filename to preserve provenance.')
    req=Request(URL,headers={'User-Agent':args.user_agent,'Accept':'application/json'})
    try:
        # One reviewed public endpoint; no arbitrary URLs or auth, and no automatic retries.
        with build_opener(NoRedirect()).open(req,timeout=25) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ValueError('Response exceeds 10 MB safety bound')
            headers={k:response.headers.get(k) for k in ['Date','Age','ETag','Last-Modified','Cache-Control']}
        rows=json.loads(data)
        if not isinstance(rows,list):raise ValueError('Schema changed: expected a list')
        selected=[]
        for row in rows:
            if not isinstance(row,dict) or any(f not in row for f in FIELDS[:6]):raise ValueError('Schema changed; import halted')
            selected.append({f:row.get(f) for f in FIELDS})
        now=datetime.now(timezone.utc).isoformat()
        # A HTTP fetch proves retrieval, not that every event listing is up-to-date.
        envelope={'meta':{'source_id':'izmir_open_events','source_city':'İzmir','source_url':URL,
          'license':'CC-BY-4.0','license_url':'https://acikveri.bizizmir.com/tr/license',
          'attribution':'İzmir Büyükşehir Belediyesi Açık Veri Portalı',
          'acquisition_method':'direct_http_selected_fields','acquired_date':now[:10],
          'http_retrieved_at':now,'source_observed_at':None,'origin_live_verified':False,
          'review_required':'Review response cache headers and listing freshness before accepting live evidence.',
          'response_headers':headers,'sha256_original_http_body':hashlib.sha256(data).hexdigest(),
          'selected_fields_only':True},'records':selected}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'saved':str(args.out),'records':len(rows),'license':'CC-BY-4.0','status':'downloaded_not_live_verified'},ensure_ascii=False))
    except (HTTPError,URLError,socket.timeout,ValueError,RuntimeError) as e:
        print('Fetch failed; no verified data imported: '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
