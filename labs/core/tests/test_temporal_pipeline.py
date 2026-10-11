"""KEP-CORE-001 red-first tests: temporal source evidence + Core + model boundary.

All signals/labels in this test module are authored or synthetic. No real
venues, new data capture, external model, reviewer outcomes or network I/O.
"""
import copy
import json
import random
import unittest
from dataclasses import replace

from kepcore.core import Query, load_catalog, decide
from kepcore.model_boundary import validate_structured_reply
from kepcore.temporal_pipeline import Signal, evidence_snapshot, run_pipeline

AT='2026-10-10T12:00:00+03:00'
EARLY='2026-10-10T10:00:00+03:00'
LATENIGHT='2026-10-10T13:00:00+03:00'
BEFORE='2026-10-07T10:00:00+03:00'
PLACE=next(x for x in load_catalog() if x['kind']=='place')


def signal(name, supports=True, *, root='source_a', at=EARLY, received=EARLY,
           record=None, rights='research_ingest', event_id=None):
    return Signal(event_id or name, record or PLACE['id'], root, at, received,
                  supports, rights)


def query(**extra):
    return Query(city='İstanbul',kind='place',at=AT,**extra)


def execute(events, catalog=None, roots=('source_a','source_b','source_c'), q=None):
    return run_pipeline([copy.deepcopy(PLACE)] if catalog is None else catalog,
                        q or query(),events,approved_roots=roots)


class TemporalContractTests(unittest.TestCase):
    def test_two_distinct_fresh_roots_support_lab_only(self):
        out=execute([signal('a'),signal('b',root='source_b')])
        self.assertEqual(out['action'],'LAB_CORROBORATED')
        self.assertEqual(out['selected_ids'],[PLACE['id']])
        self.assertEqual(out['evidence'][PLACE['id']]['status'],'MULTI_ROOT_SUPPORT')
        self.assertFalse(out['consumer_publish'])
        self.assertTrue(out['laboratory_only'])
        self.assertIsNone(out['real_world_accuracy'])
        self.assertFalse(out['model_used'])

    def test_one_root_many_echoes_never_independent(self):
        original=signal('origin')
        many=[original]+[signal('echo'+str(i),root='source_a') for i in range(80)]
        out=execute(many)
        self.assertEqual(out['action'],'LAB_ABSTAIN')
        self.assertEqual(out['evidence'][PLACE['id']]['independent_roots'],['source_a'])
        self.assertEqual(out['evidence'][PLACE['id']]['status'],'ONE_ROOT_ONLY')

    def test_root_conflict_at_equal_observation_clock_stops(self):
        x=[signal('a',True),signal('b',False)]
        out=execute(x)
        self.assertEqual(out['action'],'LAB_ABSTAIN')
        self.assertEqual(out['evidence'][PLACE['id']]['status'],'DISPUTED')

    def test_across_root_disagreement_never_source_majority_winner(self):
        r=execute([signal('a'),signal('b',root='source_b'),signal('c',False,root='source_c')])
        self.assertEqual(r['action'],'LAB_ABSTAIN')
        self.assertEqual(r['evidence'][PLACE['id']]['status'],'DISPUTED')

    def test_negative_reports_do_not_prove_closure(self):
        r=execute([signal('a',False),signal('b',False,root='source_b')])
        self.assertEqual(r['evidence'][PLACE['id']]['status'],'NEGATIVE_REPORTS_REQUIRE_REVIEW')
        self.assertEqual(r['selected_ids'],[])
        self.assertIsNone(r['real_world_accuracy'])

    def test_newer_same_root_supersedes_old_without_double_count(self):
        r=execute([signal('old',False,at='2026-10-10T08:00:00+03:00',
                          received='2026-10-10T08:01:00+03:00'),
                   signal('new',True,at=EARLY,received=EARLY),
                   signal('other',True,root='source_b')])
        self.assertEqual(r['action'],'LAB_CORROBORATED')

    def test_future_delivery_is_not_known_early(self):
        delayed=signal('b',root='source_b',received=LATENIGHT)
        r=execute([signal('a'),delayed])
        self.assertEqual(r['action'],'LAB_ABSTAIN')
        late=replace(query(),at='2026-10-10T14:00:00+03:00')
        self.assertEqual(execute([signal('a'),delayed],q=late)['action'],'LAB_CORROBORATED')

    def test_future_observation_and_stale_both_refused(self):
        r=execute([signal('old',at=BEFORE,received=BEFORE),
                   signal('future',root='source_b',at=LATENIGHT,received=LATENIGHT)])
        self.assertEqual(r['action'],'LAB_ABSTAIN')
        self.assertEqual(r['evidence'][PLACE['id']]['status'],'STALE_OR_UNAVAILABLE')

    def test_ttl_inclusive_boundary_then_expires(self):
        border='2026-10-08T12:00:00+03:00'
        xs=[signal('a',at=border,received=border),
            signal('b',root='source_b',at=border,received=border)]
        self.assertEqual(execute(xs)['action'],'LAB_CORROBORATED')
        late=replace(query(),at='2026-10-10T12:00:01+03:00')
        self.assertEqual(execute(xs,q=late)['action'],'LAB_ABSTAIN')

    def test_unapproved_root_and_source_rights_never_count(self):
        r=execute([signal('a'),signal('b',root='source_b',rights='blocked'),
                   signal('c',root='unregistered')])
        self.assertEqual(r['action'],'LAB_ABSTAIN')
        self.assertEqual(r['evidence'][PLACE['id']]['independent_roots'],['source_a'])

    def test_core_rights_gate_not_bypassed(self):
        blocked=copy.deepcopy(PLACE)
        blocked['rights_scope']='pending'
        r=execute([signal('a'),signal('b',root='source_b')],catalog=[blocked])
        self.assertEqual(r['action'],'CORE_REFUSED')
        self.assertEqual(r['base_action'],'ABSTAIN')
        self.assertEqual(r['selected_ids'],[])
        self.assertEqual(r['model_context']['candidates'],[])

    def test_core_missing_required_price_cannot_be_filled_by_boolean_rumor(self):
        r=execute([signal('a'),signal('b',root='source_b')],q=query(budget=10))
        self.assertEqual(r['action'],'CORE_REFUSED')
        self.assertEqual(r['base_action'],'REFRESH')
        self.assertEqual(r['selected_ids'],[])

    def test_model_only_receives_corrob_candidates(self):
        approved=execute([signal('a'),signal('b',root='source_b')])
        context=approved['model_context']
        self.assertEqual([x['id'] for x in context['candidates']],[PLACE['id']])
        bad=validate_structured_reply(context,{
            'snapshot_hash':context['snapshot_hash'],
            'selected_ids':['invented:item'],'claims':[]})
        self.assertFalse(bad['accepted'])
        no=execute([signal('a')])
        self.assertEqual(no['model_context']['candidates'],[])
        bad=validate_structured_reply(no['model_context'],{
            'snapshot_hash':no['model_context']['snapshot_hash'],
            'selected_ids':[PLACE['id']]})
        self.assertFalse(bad['accepted'])

    def test_metamorphic_permutations_and_duplicate_replay_are_stable(self):
        events=[signal('a'),signal('b',root='source_b'),signal('echo'),
                signal('late',False,root='source_c',received=LATENIGHT)]
        base=execute(events)
        for i in range(30):
            other=events[:]
            random.Random(i).shuffle(other)
            self.assertEqual(execute(other),base)
        repeated=execute(events+[events[0]]*5)
        self.assertEqual(repeated,base)

    def test_same_event_id_different_payload_rejected(self):
        with self.assertRaises(ValueError):
            execute([signal('same',True),signal('same',False)])

    def test_timestamps_must_be_aware_and_causal(self):
        for kw in ({'at':'2026-10-10T10:00:00'},
                   {'at':LATENIGHT,'received':EARLY}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                signal('bad',**kw)
        with self.assertRaises(ValueError):
            run_pipeline([PLACE],query(),[signal('a')],
                         approved_roots=('source_a',),ttl_hours=-1)

    def test_source_event_has_no_truth_field_and_input_not_mutated(self):
        events=[signal('a'),signal('b',root='source_b')]
        old=events[:]
        r=execute(events)
        self.assertEqual(events,old)
        self.assertNotIn('true_business_status',json.dumps(r))
        self.assertNotIn('ground_truth',json.dumps(r))
        self.assertFalse(r['consumer_publish'])


if __name__=='__main__':
    unittest.main()
