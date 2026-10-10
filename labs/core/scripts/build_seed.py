"""Reconstruct a selected-field fixture from publicly rendered source results.
NOT a direct HTTP download; content hashes identify these local fixtures only.
"""
from pathlib import Path
import json, hashlib
ROOT=Path(__file__).resolve().parents[1]

def save(name, value):
    path=ROOT/name; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()

hv='Tarihi Havagazı Fabrikası'; aa='Ahmed Adnan Saygun Sanat Merkezi'; ap='Ahmet Piriştina Kent Arşivi ve Müzesi'
rows=[
(6927,'SİNEMA','YENİDEN SİNEMATEK AÇIK HAVA YAZ PROGRAMI - BABA ANNE KIZ KARDEŞ ERKEK KARDEŞ','2026-08-10T21:00:00','2026-08-10T21:00:00',hv,True,'yeniden-sinematek-acik-hava-yaz-programi-baba-anne-kiz-kardes-erkek-kardes'),
(6949,'DİĞER','Müzik Oyunları Çocuk Atölyesi','2026-08-05T11:30:00','2026-08-12T11:30:00',aa,True,'muzik-oyunlari-cocuk-atolyesi-3881'),
(6948,'SİNEMA','GEZİCİ AÇIKHAVA FİLM GÜNLERİ','2026-07-10T21:00:00','2026-08-13T21:00:00','İlçelerde Etkinlik Alanları',True,'gezici-acikhava-film-gunleri-7957'),
(6928,'SİNEMA',' YENİDEN SİNEMATEK AÇIK HAVA YAZ PROGRAMI-JULIA','2026-08-17T21:00:00','2026-08-17T21:00:00',hv,True,'yeniden-sinematek-acik-hava-yaz-programi-E28093-julia'),
(6960,'KONSER','ZEYTİN ALTINDA ``ÜÇ SAZIN DİLİNDEN GECENİN ŞARKILARI``','2026-08-19T21:00:00','2026-08-19T21:30:00',aa,True,'zeytin-altinda-6060uc-sazin-dilinden-gecenin-sarkilari6060'),
(6929,'SİNEMA',' YENİDEN SİNEMATEK AÇIK HAVA YAZ PROGRAMI-ADA','2026-08-24T21:00:00','2026-08-24T21:00:00',hv,False,'yeniden-sinematek-acik-hava-yaz-programiE28093ada'),
(6932,'KONSER','Çim Konserleri 2026','2026-07-07T08:00:00','2026-08-25T08:00:00',hv,True,'cim-konserleri-2026'),
(6958,'SERGİ','Zamanda Bir Kırışıklık','2026-08-04T16:00:00','2026-08-30T18:00:00',aa,True,'zamanda-bir-kirisiklik'),
(6957,'SERGİ','Meserret - İhtimal','2026-08-07T08:00:00','2026-08-31T17:30:00','Tarihi Bıçakçı Han',True,'meserret-ihtimal'),
(6959,'SERGİ','Karşılaşmanın Ardından','2026-08-07T09:00:00','2026-08-31T18:00:00','Tarihi Bıçakçı Han',True,'karsilasmanin-ardindan'),
(6930,'SİNEMA',' YENİDEN SİNEMATEK AÇIK HAVA YAZ PROGRAMI-MANEVİ DEĞER','2026-08-31T21:00:00','2026-08-31T21:00:00',hv,True,'yeniden-sinematek-acik-hava-yaz-programi-manevi-deger'),
(6931,'SERGİ','Peaceful Towns (Barışçıl Şehirler) Sergisi','2026-07-01T15:00:00','2026-08-31T15:00:00','Vasıf Çınar Meydanı',True,'cocuklarin-gozunden-barisinrenkleri-resim-sergisi'),
(6925,'DİĞER','Kent Tarihi ve Kültürü Yaz Atölyeleri','2026-07-01T08:00:00','2026-09-01T08:00:00',ap,True,'kent-tarihi-ve-kulturu-yaz-atolyeleri-872'),
(6956,'SERGİ','Müziğin Tınısı Fotoğraf Sergisi','2026-08-10T08:00:00','2026-09-06T18:00:00',aa,True,'muzigin-tinisi-fotograf-sergisi'),
(6583,'SERGİ','SERGİ: İzmir Fotoğrafhanesi - Görsel Hafızanın İnşası (1840-1922)','2025-12-11T18:00:00','2026-12-13T18:00:00',ap,True,'sergi-E2809Cizmir-fotografhanesi-gorsel-hafizanin-insasi-1840-1922E2809D'),
(6835,'SERGİ','İzmir Mutfak Müzesinin Tanıtım Sergisi  Göl Gazinosunda Ziyarete Açıldı','2026-04-02T08:00:00','2026-12-31T17:00:00','İlçe Çok Amaçlı Salonlar',True,'izmir-mutfak-muzesiE28099nin-tanitim-sergisigol-gazinosuE28099nda-ziyarete-acildi')]
records=[]
for i,t,n,s,e,v,f,u in rows:
    records.append(dict(Id=i,Tur=t,Adi=n,EtkinlikBaslamaTarihi=s,EtkinlikBitisTarihi=e,EtkinlikMerkezi=v,UcretsizMi=f,EtkinlikUrl=u,BiletSatisLinki=('http://kultursanat.izmir.bel.tr/Sayfalar/KoltukSecim.aspx?Salon=20&Seans=8697&Etkinlik=6929' if i==6929 else None)))
common=dict(acquired_date='2026-10-10',acquisition_method='selected_fields_transcribed_from_web_tool',source_observed_at=None,origin_live_verified=False,source_snapshot_notice='Web tool: crawled about 2 months ago. Exact snapshot date unknown.',selected_fields_only=True)
izmir=dict(meta=dict(**common,source_id='izmir_open_events',source_url='https://openapi.izmir.bel.tr/api/ibb/kultursanat/etkinlikler',catalog_url='https://acikveri.bizizmir.com/tr/dataset/kultur-sanat-etkinlikleri',license='CC-BY-4.0',license_url='https://acikveri.bizizmir.com/tr/license',attribution='İzmir Büyükşehir Belediyesi Açık Veri Portalı',source_city='İzmir',tool_reference='turn561805view0'),records=records)
save('data/raw/izmir_events_excerpt.json',izmir)

def dms(d,m,s):return round(d+m/60+s/3600,8)
places=[
 dict(id='wikidata:Q1463961',name='İstanbul Modern',city='İstanbul',category='museum',lat=dms(41,1,33.60),lon=dms(28,58,58.58),source_url='https://www.wikidata.org/wiki/Q1463961',license='CC0-1.0',source_id='wikidata',source_coordinates='41°1\'33.60"N,28°58\'58.58"E',geo_warning='Community coordinate; current entrance/location not independently verified.'),
 dict(id='wikidata:Q91274',name='Galata Kulesi',city='İstanbul',category='museum',lat=dms(41,1,32.27635),lon=dms(28,58,26.95148),source_url='https://www.wikidata.org/wiki/Q91274',license='CC0-1.0',source_id='wikidata',source_coordinates='41°1\'32.27635"N,28°58\'26.95148"E',geo_warning='Coordinate statement has no reference; approximate discovery only.'),
 dict(id='wikipedia:Pera_Museum',name='Pera Müzesi',city='İstanbul',category='museum',lat=41.03181,lon=28.97519,source_url='https://en.wikipedia.org/wiki/Pera_Museum',license='CC-BY-SA-4.0',source_id='wikipedia',source_coordinates='41.03181,28.97519'),
 dict(id='wikipedia:Dolmabahce_Palace',name='Dolmabahçe Sarayı',city='İstanbul',category='heritage',lat=41.03944,lon=29.00167,source_url='https://en.wikipedia.org/wiki/Dolmabah%C3%A7e_Palace',license='CC-BY-SA-4.0',source_id='wikipedia',source_coordinates='41.03944,29.00167'),
 dict(id='wikipedia:Yildiz_Park',name='Yıldız Parkı',city='İstanbul',category='park',lat=41.0483,lon=29.0156,source_url='https://en.wikipedia.org/wiki/Y%C4%B1ld%C4%B1z_Park',license='CC-BY-SA-4.0',source_id='wikipedia',source_coordinates='41.0483,29.0156'),
 dict(id='wikipedia:Sakip_Sabanci_Museum',name='Sakıp Sabancı Müzesi',city='İstanbul',category='museum',lat=41.099116,lon=29.053704,source_url='https://en.wikipedia.org/wiki/Sak%C4%B1p_Sabanc%C4%B1_Museum',license='CC-BY-SA-4.0',source_id='wikipedia',source_coordinates='41.099116,29.053704'),
 dict(id='wikipedia:Rahmi_M_Koc_Museum',name='Rahmi M. Koç Müzesi',city='İstanbul',category='museum',lat=41.04227,lon=28.94926,source_url='https://en.wikipedia.org/wiki/Rahmi_M._Ko%C3%A7_Museum',license='CC-BY-SA-4.0',source_id='wikipedia',source_coordinates='41.04227,28.94926')]
for p in places:
    p.update(opening_hours=None,admission_price=None,crowd=None,source_observed_at=None,origin_live_verified=False,acquired_date='2026-10-10',coordinate_accuracy_m=None,geo_warning=p.get('geo_warning','Approximate community coordinate; not a verified entrance.'))
save('data/raw/istanbul_places_excerpt.json',dict(meta=dict(acquisition_method=common['acquisition_method'],data_kind='real_source_selected_facts',coverage='7 deliberately selected Istanbul landmarks; not a representative POI inventory.',attribution='Wikidata contributors (2 records); Wikipedia contributors (5 records).',license_urls=['https://www.wikidata.org/wiki/Wikidata:Licensing','https://creativecommons.org/licenses/by-sa/4.0/']),records=places))
# These are factual annotations of an actual contradiction, NOT an open data feed.
claims=[]
for section,vals in [('faq_answer',(300,150,200)),('page_footer',(450,250,300))]:
    for field,value in zip(['adult_admission_try','concession_admission_try','group_admission_try'],vals):
        claims.append(dict(entity_id='wikipedia:Pera_Museum',field=field,value=value,currency='TRY',section=section,source_id='pera_official',publisher_root='pera_museum',source_url='https://www.peramuseum.org/faq',source_published_at=None,source_observed_at=None,acquired_date='2026-10-10',independent_support=False))
save('data/raw/pera_conflict_research_fixture.json',dict(meta=dict(source_url='https://www.peramuseum.org/faq',tool_reference='turn103517search1',acquired_date='2026-10-10',data_kind='retrieved_source_snapshot_contradiction_factual_annotation',license='NO_OPEN_FEED_LICENSE_ESTABLISHED',use_scope='limited_research_fixture_not_production_feed',notice='No automated scraping or redistribution license is asserted. Six factual values only; no images or full text. No claim which tariff is current. The search extract showed mixed FAQ/footer prices; a separate opened cache rendered an older consistent 300/150/200 tariff. This is a retrieval/version conflict, not independently confirmed simultaneous live website inconsistency.'),claims=claims))
manifest=dict(version='0.2',assembled_date='2026-10-10',direct_http_download_succeeded=False,external_llm_calls=0,github_changed=False,data_sets=[dict(file='data/raw/izmir_events_excerpt.json',kind='real_open_event_records',count=len(records),license='CC-BY-4.0'),dict(file='data/raw/istanbul_places_excerpt.json',kind='real_open_place_facts',count=len(places),license='per_record_CC0_or_CC-BY-SA-4.0'),dict(file='data/raw/pera_conflict_research_fixture.json',kind='real_conflict_research_annotation',count=len(claims),license='not_an_open_feed')],blocked_attempts=[dict(target='bulk HTTP downloads / pip',reason='working-container external DNS resolution failed'),dict(target='Overture bulk and Istanbul municipal CKAN',reason='No actual bulk data downloaded; do not infer absence of data.')],scope='Offline research on real source excerpts. Synthetic corruptions isolated in tests. Not native app or deployed API.')
for ds in manifest['data_sets']:
    ds['sha256_local_fixture']=hashlib.sha256((ROOT/ds['file']).read_bytes()).hexdigest()
save('data/manifest.json',manifest)
print('Created',len(records),'event records,',len(places),'places,',len(claims),'research claims')
