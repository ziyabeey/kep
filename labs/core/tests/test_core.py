"""Known-case engineering invariants, not a held-out scientific benchmark."""
import unittest, copy, json, random
from dataclasses import asdict
from datetime import timedelta
from kepcore.core import *
from kepcore.store import Store
from kepcore.scheduler import SourceClock, due_sources
from run_lab import scenarios

CATALOG=load_catalog()
EVENT=next(r for r in CATALOG if r['id']=='izmir_event:6960')
PLACE=next(r for r in CATALOG if r['id']=='wikidata:Q91274')

def fresh_fixture():
    r=copy.deepcopy(EVENT)
    r.update(synthetic=True,synthetic_overlay='unit_test_only',origin_live_verified=True,
             source_observed_at='2026-08-19T18:00:00+03:00')
    return r

def event_query(**kw):
    args=dict(city='İzmir',kind='event',at='2026-08-19T20:00:00+03:00',budget=0)
    args.update(kw);return Query(**args)

class DataTests(unittest.TestCase):
    def test_real_seed_count(self):self.assertEqual(len(CATALOG),23)
    def test_missing_price_is_not_free(self):
        r=next(r for r in CATALOG if r['id']=='izmir_event:6929')
        self.assertIsNone(r['price']);self.assertFalse(r['source_claim_free'])
    def test_equal_end_is_unknown_duration(self):
        r=next(r for r in CATALOG if r['id']=='izmir_event:6927')
        self.assertIsNone(r['ends_at']);self.assertIn('DURATION_UNKNOWN',' '.join(r['flags']))
    def test_timezone(self):
        self.assertTrue(all(r['starts_at'].endswith('+03:00') for r in CATALOG if r['kind']=='event'))
    def test_multi_day_is_not_daily_event_expansion(self):
        self.assertEqual(len([r for r in CATALOG if r['kind']=='event']),16)
        self.assertEqual(next(r for r in CATALOG if r['id']=='izmir_event:6932')['event_kind'],'program_range')
    def test_unknown_venue_has_no_invented_coordinate(self):
        r=next(r for r in CATALOG if r['id']=='izmir_event:6835')
        self.assertEqual(r['venue_precision'],'unresolved');self.assertIsNone(r['lat'])
    def test_acquisition_date_is_not_observation(self):
        self.assertFalse(any(fresh(r,dt('2026-10-10')) for r in CATALOG))
    def test_manifest_hashes(self):
        manifest=load_json(ROOT/'data/manifest.json')
        for d in manifest['data_sets']:
            self.assertEqual(hashlib.sha256((ROOT/d['file']).read_bytes()).hexdigest(),d['sha256_local_fixture'])
    def test_all_real_entries_not_synthetic(self):self.assertTrue(all(not r['synthetic'] for r in CATALOG))

class QueryTests(unittest.TestCase):
    def test_all_contract_cases(self):
        for c in scenarios(CATALOG):
            with self.subTest(case=c['id']):
                self.assertEqual(decide(c['records'],Query(**c['query'])).action,c['expected_action'])
    def test_cross_city_rejected(self):self.assertFalse(decide(CATALOG,Query(city='İstanbul',kind='event')).selected)
    def test_turkish_city_casing(self):
        self.assertTrue(decide(CATALOG,Query(city='ISTANBUL',kind='place')).selected)
    def test_no_price_40_percent_tolerance(self):
        r=fresh_fixture();r['price']=501
        self.assertEqual(decide([r],event_query(budget=500)).action,'ABSTAIN')
    def test_budget_boundary_inclusive(self):
        r=fresh_fixture();r['price']=500
        self.assertEqual(decide([r],event_query(budget=500)).action,'RECOMMEND')
    def test_missing_coordinates_not_zero_distance(self):
        d=decide([fresh_fixture()],event_query(lat=38.4,lon=27.1,radius_km=1))
        self.assertFalse(d.selected);self.assertIn('COORDINATES_UNKNOWN',d.reasons)
    def test_unavailable_actual_duration(self):
        r=copy.deepcopy(next(r for r in CATALOG if r['id']=='izmir_event:6927'))
        r.update(origin_live_verified=True,source_observed_at='2026-08-10T20:00:00+03:00',synthetic=True)
        d=decide([r],Query(city='İzmir',at='2026-08-10T21:10:00+03:00',open_now=True))
        self.assertFalse(d.selected);self.assertIn('DURATION_UNKNOWN',d.reasons)
    def test_open_future_event_not_started(self):
        self.assertEqual(decide([fresh_fixture()],event_query(open_now=True)).action,'ABSTAIN')
    def test_future_dated_observation_not_fresh(self):
        r=fresh_fixture();r['source_observed_at']='2027-01-01T00:00:00+03:00'
        self.assertFalse(fresh(r,dt('2026-08-19T20:00:00+03:00')))
    def test_no_required_hours_for_metadata(self):self.assertEqual(decide([PLACE],Query(city='İstanbul')).action,'DISCOVER')
    def test_no_crowd_hallucination(self):self.assertEqual(decide([PLACE],Query(city='İstanbul',quiet=True)).action,'CLARIFY')
    def test_explicit_request_allowed_in_silent_mode(self):self.assertEqual(decide([PLACE],Query(city='İstanbul',mode='silent')).action,'DISCOVER')
    def test_proactive_opt_out(self):self.assertEqual(decide([PLACE],Query(city='İstanbul',proactive=True)).action,'SILENT')
    def test_frequency_cap(self):self.assertEqual(decide([PLACE],Query(city='İstanbul',proactive=True,push_opt_in=True,already_sent_today=1)).action,'SILENT')
    def test_no_cross_source_license_bypass(self):
        r=copy.deepcopy(PLACE);r['rights_scope']='pending'
        self.assertFalse(decide([r],Query(city='İstanbul')).selected)
    def test_no_input_mutation(self):
        before=copy.deepcopy(CATALOG)
        for policy in ['blanket_verification','simple_safe','query_aware']:decide(CATALOG,Query(city='İstanbul'),policy)
        self.assertEqual(before,CATALOG)
    def test_permutation_invariance_100_orders(self):
        q=Query(city='İstanbul',kind='place',lat=PLACE['lat'],lon=PLACE['lon'],radius_km=10,limit=7)
        expected=[r['id'] for r in decide(CATALOG,q).selected]
        for seed in range(100):
            other=copy.deepcopy(CATALOG);random.Random(seed).shuffle(other)
            self.assertEqual([r['id'] for r in decide(other,q).selected],expected)
    def test_model_cannot_invent_id(self):
        d=decide([PLACE],Query(city='İstanbul'))
        self.assertFalse(check_model_selection(d,['invented'])['accepted'])
    def test_model_allowed_ids(self):
        d=decide([PLACE],Query(city='İstanbul'))
        self.assertTrue(check_model_selection(d,[PLACE['id']])['accepted'])
    def test_query_validation(self):
        with self.assertRaises(ValueError):Query(city='İstanbul',budget=-1)
        with self.assertRaises(ValueError):Query(city='İstanbul',radius_km=2)
        with self.assertRaises(ValueError):Query(city='İstanbul',mode='unrestricted')

class ConflictTests(unittest.TestCase):
    def setUp(self):self.claims=load_json(ROOT/'data/raw/pera_conflict_research_fixture.json')['claims']
    def test_actual_price_contradiction(self):
        resolved=reconcile_claims(self.claims)
        self.assertEqual(len(resolved),3)
        for x in resolved.values():self.assertEqual(x['status'],'disputed');self.assertIsNone(x['value'])
    def test_repeated_pages_do_not_become_independent(self):
        resolved=reconcile_claims(self.claims*50)
        self.assertTrue(all(x['independent_publisher_count']==1 for x in resolved.values()))
    def test_conflict_order_does_not_pick_latest(self):
        self.assertEqual(reconcile_claims(self.claims),reconcile_claims(list(reversed(self.claims))))

class StoreTests(unittest.TestCase):
    def setUp(self):self.s=Store()
    def tearDown(self):self.s.close()
    def test_ingest_twice_idempotent(self):
        for r in CATALOG:self.s.ingest(r)
        for r in CATALOG:self.assertEqual(self.s.ingest(r),'unchanged')
        self.assertEqual(self.s.counts()['objects'],23);self.assertEqual(self.s.counts()['outbox'],23)
    def test_older_update_ignored(self):
        r=fresh_fixture();self.s.ingest(r)
        old=copy.deepcopy(r);old['source_observed_at']='2026-08-19T17:00:00+03:00';old['price']=100
        self.assertEqual(self.s.ingest(old),'ignored_older');self.assertEqual(self.s.get(r['id'])['price'],0)
    def test_same_timestamp_conflict_not_silent_overwrite(self):
        r=fresh_fixture();self.s.ingest(r);other=copy.deepcopy(r);other['price']=100
        with self.assertRaises(ValueError):self.s.ingest(other)
    def test_source_change_cannot_overwrite_authority(self):
        r=fresh_fixture();self.s.ingest(r);r['source_id']='copied_blog'
        with self.assertRaises(ValueError):self.s.ingest(r)
    def test_cancellation_invalidates_queued_push(self):
        r=fresh_fixture();self.s.ingest(r);p=self.s.queue_push(r['id'],'synthetic-user',consent=True)
        q=event_query(proactive=True,push_opt_in=True)
        self.assertTrue(self.s.preview_dispatch(p,q)['send'])
        r.update(lifecycle='cancelled',source_observed_at='2026-08-19T19:00:00+03:00')
        self.assertEqual(self.s.ingest(r),'updated')
        self.assertFalse(self.s.preview_dispatch(p,q)['send'])
        self.assertEqual(self.s.db.execute('SELECT status FROM push_queue WHERE push_id=?',(p,)).fetchone()[0],'cancelled')
        self.assertEqual(self.s.counts()['outbox'],2)
    def test_duplicate_push_queue_not_duplicate(self):
        r=fresh_fixture();self.s.ingest(r)
        p=self.s.queue_push(r['id'],'x',consent=True)
        self.assertEqual(p,self.s.queue_push(r['id'],'x',consent=True));self.assertEqual(self.s.counts()['push_queue'],1)
    def test_no_push_without_consent(self):
        r=fresh_fixture();self.s.ingest(r)
        with self.assertRaises(PermissionError):self.s.queue_push(r['id'],'x',consent=False)
    def test_no_push_from_stale_snapshot(self):
        self.s.ingest(EVENT);p=self.s.queue_push(EVENT['id'],'x',consent=True)
        self.assertFalse(self.s.preview_dispatch(p,event_query(proactive=True,push_opt_in=True))['send'])
    def test_rights_block(self):
        r=copy.deepcopy(PLACE);r['rights_scope']='pending'
        with self.assertRaises(PermissionError):self.s.ingest(r)
    def test_empty_fetch_does_not_delete_existing_records(self):
        self.s.ingest(EVENT)
        for row in []:self.s.ingest(row)
        self.assertEqual(self.s.counts()['objects'],1)

class SchedulerTests(unittest.TestCase):
    def test_rate_cap_and_rights(self):
        clocks=[SourceClock('blocked',20,1,12,approved=False),SourceClock('quota',20,1,12,calls_today=24),SourceClock('backoff',20,1,12,retry_after_hours=2),SourceClock('ok',20,1,12)]
        self.assertEqual(due_sources(clocks,4),['ok'])
    def test_quiet_source_heartbeat(self):
        clocks=[SourceClock('popular',3,1,24,observed_change_rate=100),SourceClock('quiet',25,1,24)]
        self.assertEqual(due_sources(clocks,1),['quiet'])
    def test_min_interval(self):self.assertEqual(due_sources([SourceClock('x',.5,1,24)],1),[])
    def test_budget_cap(self):self.assertEqual(len(due_sources([SourceClock(str(i),5,1,12) for i in range(10)],3)),3)
    def test_zero_budget(self):self.assertEqual(due_sources([SourceClock('x',5,1,12)],0),[])

class GeographyTests(unittest.TestCase):
    def test_zero(self):self.assertAlmostEqual(haversine_km(41,29,41,29),0)
    def test_symmetry(self):self.assertAlmostEqual(haversine_km(41,29,38,27),haversine_km(38,27,41,29))
    def test_invalid(self):
        with self.assertRaises(ValueError):haversine_km(100,0,0,0)

if __name__=='__main__':unittest.main(verbosity=2)
