import unittest,copy,tempfile
from pathlib import Path
from dataclasses import fields
from datetime import datetime
from kepcore.core import Query,decide,dt,temporal_state,stable_hash
from kepcore.availability import opening_status,field_is_fresh
from kepcore.preferences import Rating,PreferenceModel,rerank_eligible
from kepcore.model_boundary import context_for_model,validate_structured_reply
from benchmarks.edge_cases import regression_cases,sample_place,schedule,proof
from benchmarks.ratings import load_ratings,split_rows,tie_ndcg

class AvailabilityTests(unittest.TestCase):
    def test_all_new_regressions(self):
        for c in regression_cases():
            with self.subTest(case=c['id']):
                self.assertEqual(decide([c['record']],Query(**c['query'])).action,c['expected'])
    def test_overnight_open(self):
        h=schedule();h['weekly']['5']=[['22:00','02:00']]
        self.assertEqual(opening_status(h,dt('2026-10-10T01:00:00+03:00')),'OPEN')
    def test_overnight_exact_close(self):
        h=schedule();h['weekly']['5']=[['22:00','02:00']]
        self.assertEqual(opening_status(h,dt('2026-10-10T02:00:00+03:00')),'CLOSED')
    def test_exception_overrides_carry(self):
        h=schedule();h['weekly']['5']=[['22:00','02:00']];h['exceptions']['2026-10-10']=[]
        self.assertEqual(opening_status(h,dt('2026-10-10T01:00:00+03:00')),'CLOSED')
    def test_utc_conversion(self):
        self.assertEqual(opening_status(schedule(),datetime.fromisoformat('2026-10-10T06:00:00+00:00')),'OPEN')
    def test_missing_weekday_not_closed(self):
        h=schedule();del h['weekly']['6']
        self.assertEqual(opening_status(h,dt('2026-10-10T18:00:00+03:00')),'UNKNOWN')
    def test_equal_hours_unknown(self):
        self.assertEqual(opening_status(schedule([['00:00','00:00']]),dt('2026-10-10T18:00:00+03:00')),'UNKNOWN')
    def test_all_day_explicit(self):
        self.assertEqual(opening_status(schedule([['00:00','24:00']]),dt('2026-10-10T23:59:00+03:00')),'OPEN')
    def test_invalid_schedule_unknown(self):
        for h in [None,[],{},'open',schedule([['30:00','31:00']])]:
            self.assertEqual(opening_status(h,dt('2026-10-10T18:00:00+03:00')),'UNKNOWN')
    def test_field_expiry(self):
        r=sample_place();r['price']=100;r['field_evidence']={'price':proof(100)}
        r['field_evidence']['price']['valid_until']='2026-10-10T18:00:00+03:00'
        self.assertFalse(field_is_fresh(r,'price',dt('2026-10-10T18:00:00+03:00'),48))
    def test_loose_clock_text_is_not_open(self):
        # int() accepted ' 9', '+9' and non-Latin digits, so these hours read as OPEN.
        for bad in [' 9:00','+9:00','٠٩:٠٠','09: 0']:
            with self.subTest(text=bad):
                r=sample_place();r['opening_hours']=schedule([[bad,'20:00']])
                d=decide([r],Query(city='İstanbul',kind='place',open_now=True))
                self.assertEqual(d.action,'REFRESH')
                self.assertIn('OPENING_HOURS_UNKNOWN',d.blocked[r['id']])
    def test_malformed_freshness_proof_fails_closed(self):
        # A live record without a usable timestamp used to raise AttributeError mid-decision.
        when=dt('2026-10-10T18:00:00+03:00')
        r=sample_place();r['price']=100;del r['source_observed_at']
        self.assertFalse(field_is_fresh(r,'price',when,48))
        self.assertEqual(decide([r],Query(city='İstanbul',kind='place',budget=500)).action,'REFRESH')
        for bad in [dict(observed_at=1700000000),dict(valid_until=5),dict(status=['disputed'])]:
            with self.subTest(proof=bad):
                r=sample_place();r['price']=100;r['field_evidence']={'price':{**proof(100),**bad}}
                self.assertFalse(field_is_fresh(r,'price',when,48))
    def test_proof_bound_to_value(self):
        r=sample_place();r['price']=200;r['field_evidence']={'price':proof(100)}
        self.assertFalse(field_is_fresh(r,'price',dt('2026-10-10T18:00:00+03:00'),48))
    def test_invalid_price_values(self):
        for p in [float('nan'),float('inf'),-1,True,'free']:
            r=sample_place();r['price']=p
            self.assertFalse(decide([r],Query(city='İstanbul',budget=500)).selected)
    def test_unverified_price_not_in_model_facts(self):
        r=sample_place();r['price']=100;r['origin_live_verified']=False
        d=decide([r],Query(city='İstanbul'))
        self.assertIsNone(d.selected[0]['price'])
    def test_malformed_field_evidence_fails_closed(self):
        r=sample_place();r['field_evidence']=[]
        self.assertFalse(field_is_fresh(r,'price',dt('2026-10-10T18:00:00+03:00'),48))
    def test_invalid_price_not_exposed_without_budget(self):
        r=sample_place();r['price']=True
        self.assertIsNone(decide([r],Query(city='İstanbul')).selected[0]['price'])
    def test_invalid_coordinates_without_radius(self):
        with self.assertRaises(ValueError):Query(city='İstanbul',lat=100,lon=29)
        with self.assertRaises(ValueError):Query(city='İstanbul',lat=41)

class PreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows,cls.audit=load_ratings()
    def test_dataset_byte_integrity(self):
        self.assertEqual(self.audit['git_blob_sha1'],'d2072b911d10edf52a1b01c4a481e02490e651ca')
        self.assertEqual((len(self.rows),self.audit['users'],self.audit['items']),(1161,138,130))
    def test_zero_is_observed_negative_not_missing(self):
        self.assertEqual(sum(r.value==0 for r in self.rows),254)
    def test_no_secondary_labels_in_features(self):
        self.assertEqual({f.name for f in fields(Rating)},{'user','item','value'})
    def test_disjoint_splits(self):
        a,b,c,u=split_rows(self.rows,20261010);keys=lambda rs:{(r.user,r.item) for r in rs}
        self.assertFalse(keys(a)&keys(b));self.assertFalse(keys(a)&keys(c));self.assertFalse(keys(b)&keys(c))
        self.assertEqual((len(a),len(b),len(c),len(u)),(757,101,303,101))
    def test_split_reproducible_and_input_order_invariant(self):
        self.assertEqual(split_rows(self.rows,20261010),split_rows(list(reversed(self.rows)),20261010))
    def test_test_label_changes_do_not_affect_fit(self):
        a,b,c,_=split_rows(self.rows,20261010)
        m=PreferenceModel().fit(a+b);before=[m.predict(r.user,r.item) for r in c]
        mutated=[Rating(r.user,r.item,2-r.value) for r in c]
        self.assertEqual(before,[m.predict(r.user,r.item) for r in mutated])
        self.assertFalse(m.training_pairs & {(r.user,r.item) for r in c})
    def test_row_order_invariant_fit(self):
        m=PreferenceModel().fit(self.rows);n=PreferenceModel().fit(list(reversed(self.rows)))
        self.assertAlmostEqual(m.predict('U1077','135085'),n.predict('U1077','135085'),12)
    def test_cold_fallback(self):
        m=PreferenceModel().fit(self.rows)
        self.assertEqual(m.predict('never_seen','never_seen'),m.mu)
        self.assertTrue(m.support('never_seen','135085')['unknown_user'])
    def test_invalid_training(self):
        with self.assertRaises(ValueError):PreferenceModel().fit([])
        with self.assertRaises(ValueError):PreferenceModel().fit([Rating('u','i',3)])
        with self.assertRaises(ValueError):PreferenceModel().fit([Rating('u','i',1)]*2)
    def test_tie_aware_ranking(self):
        self.assertEqual(tie_ndcg([2,0,1],[1,1,1]),tie_ndcg([0,1,2],[1,1,1]))
        self.assertIsNone(tie_ndcg([0,0,0],[1,2,3]))
        self.assertAlmostEqual(tie_ndcg([2,1,0],[2,1,0]),1)
    def test_pref_cannot_reintroduce_blocked(self):
        r=sample_place();d=decide([r],Query(city='İstanbul'))
        self.assertEqual([a['id'] for a in rerank_eligible(d,{'fake':999,r['id']:1})],[r['id']])
    def test_preference_score_finite(self):
        r=sample_place();d=decide([r],Query(city='İstanbul'))
        with self.assertRaises(ValueError):rerank_eligible(d,{r['id']:float('nan')})

class ModelBoundaryTests(unittest.TestCase):
    def setUp(self):
        r=sample_place();self.context=context_for_model(decide([r],Query(city='İstanbul')))
        c=self.context['candidates'][0]
        self.reply={'snapshot_hash':self.context['snapshot_hash'],'selected_ids':[c['id']],
                    'claims':[{'id':c['id'],'field':'name','value':c['facts']['name'],'source_record_hash':c['source_record_hash']}]}
    def test_valid_envelope(self):self.assertTrue(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_stale_snapshot(self):
        self.reply['snapshot_hash']='old';self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_invented_price(self):
        self.reply['claims'][0].update(field='price',value=100)
        self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_wrong_value(self):
        self.reply['claims'][0]['value']='invented'
        self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_wrong_evidence(self):
        self.reply['claims'][0]['source_record_hash']='fake'
        self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_extra_free_text_not_verified(self):
        self.reply['explanation']='Open until midnight'
        self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_outside_candidate(self):
        self.reply['selected_ids']=['fake'];self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_unhashable_claim_key_rejected(self):
        self.reply['claims'][0]['field']=[]
        self.assertFalse(validate_structured_reply(self.context,self.reply)['accepted'])
    def test_closed_event_cannot_be_resurrected(self):
        r=sample_place();r['lifecycle']='cancelled'
        c=context_for_model(decide([r],Query(city='İstanbul')))
        reply={'snapshot_hash':c['snapshot_hash'],'selected_ids':[r['id']],'claims':[]}
        self.assertFalse(validate_structured_reply(c,reply)['accepted'])

if __name__=='__main__':unittest.main()
