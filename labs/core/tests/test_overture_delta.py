"""KEP-DATA-006: temporal data revisions, NOT validated city changes."""
from __future__ import annotations
import copy
from dataclasses import replace
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
import json
import subprocess
import sys
import unittest

from kepcore.overture_delta import (
    ResearchSnapshot, SCHEMA, compare_snapshots, controlled_future_example,
    synthetic_overlay, snapshot_from_frozen_archive,
    load_operator_research_bundle,
)
from kepcore.overture_places import PILOT,canonical

SYN_DATE='2026-10-22T10:00:00+03:00'
SYN_RELEASE='2026-10-21.0'  # FUTURE HYPOTHESIS, NOT an October observed release


class DeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference=snapshot_from_frozen_archive()
        cls.base=copy.deepcopy(list(cls.reference.records[:9]))
        cls.rows=sorted(cls.base,key=lambda x:x['overture_id'])

    def reference_short(self,rows=None):
        data=self.rows if rows is None else rows
        order=sorted(copy.deepcopy(data),key=lambda x:x['overture_id'])
        return ResearchSnapshot(
            release='2026-09-23.1',observed_at='2026-10-10T23:47:38Z',
            normalized_sha256=sha256(canonical(order)).hexdigest(),
            population_sha256=sha256(canonical(order)).hexdigest(),
            origin='pinned_real_archive',records=tuple(order),
            sampling_cells=tuple(sorted(PILOT)),
        )

    def future(self,before=None,rows=None):
        b=before if before is not None else self.reference_short()
        return synthetic_overlay(b,list(b.records) if rows is None else rows,
            hypothetical_release=SYN_RELEASE,hypothetical_observed_at=SYN_DATE)

    def test_full_real_reference_is_pinned_and_4803(self):
        self.assertEqual(len(self.reference.records),4803)
        self.assertEqual(self.reference.origin,'pinned_real_archive')
        self.assertEqual(self.reference.release,'2026-09-23.1')

    def test_full_synthetic_stress_is_explicit(self):
        r=controlled_future_example()
        self.assertEqual(r['old_population_n'],4803)
        self.assertTrue(r['synthetic_second_release'])
        self.assertFalse(r['upstream_change_authenticated_by_comparison'])
        self.assertFalse(r['real_world_business_changes_estimated'])

    def test_stress_expected_counts(self):
        c=controlled_future_example()['source_record_churn']
        self.assertEqual((c['retained_ids'],c['newly_listed_ids'],c['no_longer_listed_ids']), (4801,2,2))
        self.assertEqual((c['field_or_geometry_revised_ids'],c['confidence_only_revised_ids']), (5,1))
        self.assertEqual(len(c['possible_id_reassignment_hints']),1)

    def test_identical_fields_are_unchanged(self):
        b=self.reference_short();a=self.future(b)
        r=compare_snapshots(b,a)['source_record_churn']
        self.assertEqual(r['unchanged_ids'],len(b.records))
        self.assertEqual((r['newly_listed_ids'],r['no_longer_listed_ids']), (0,0))

    def test_name_only_is_a_data_revision(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['name']='synthetic new name'
        r=compare_snapshots(b,self.future(b,rs))
        self.assertEqual(r['source_record_churn']['field_change_counts'],{'name':1})
        self.assertEqual(r['human_verified_closures'],0)

    def test_confidence_change_not_property_revision(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['confidence']=.02
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['confidence_only_revised_ids'],1)
        self.assertEqual(r['field_or_geometry_revised_ids'],0)

    def test_source_provenance_reorder_not_a_revision(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records))
        rs[0]['source_provenance'].reverse()
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['unchanged_ids'],len(b.records))

    def test_source_provenance_changes_are_reported_as_data(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records))
        rs[0]['source_provenance']=[{'dataset':'synthetic','provider':'TEST','license':'CC0'}]
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['field_change_counts'].get('source_provenance'),1)
        self.assertEqual(r['provenance_only_revised_ids'],1)

    def test_missingness_transition(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records))
        old=rs[0]['address'];rs[0]['address']=None if old else 'synthetic address'
        direction='address_became_unknown' if old else 'address_became_known'
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['missingness_transitions'][direction],1)

    def test_geometry_revision_not_relocation(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['lat']+=.00001
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['field_change_counts']['geometry'],1)
        self.assertEqual(r['modified_examples'][0]['decision'],'SOURCE_RECORD_REVISION_ONLY')

    def test_operating_status_not_open_now(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['operating_status']='permanently_closed'
        r=compare_snapshots(b,self.future(b,rs))
        self.assertEqual(r['source_record_churn']['field_change_counts']['operating_status'],1)
        self.assertEqual(r['human_verified_closures'],0)
        self.assertIn('currently_open_from_operating_status',r['conclusions_forbidden'])

    def test_absent_id_not_a_closure(self):
        b=self.reference_short();rs=list(b.records)[1:]
        r=compare_snapshots(b,self.future(b,rs))
        self.assertEqual(r['source_record_churn']['no_longer_listed_ids'],1)
        self.assertFalse(r['real_world_business_changes_estimated'])
        self.assertIn('closed_business_from_missing_id',r['conclusions_forbidden'])

    def test_added_id_not_a_new_business(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));z=copy.deepcopy(rs[0])
        z['overture_id']=str(UUID(int=10));rs.append(z)
        r=compare_snapshots(b,self.future(b,rs))
        self.assertEqual(r['source_record_churn']['newly_listed_ids'],1)
        self.assertIn('new_business_from_added_id',r['conclusions_forbidden'])

    def test_new_id_exact_nearby_queues_human_review_only(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));z=rs.pop(0)
        z['overture_id']=str(UUID(int=10));rs.append(z)
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(len(r['possible_id_reassignment_hints']),1)
        self.assertEqual(r['possible_id_reassignment_hints'][0]['decision'],'HUMAN_REVIEW_IDENTITY_ONLY')
        self.assertEqual(r['retained_ids'],len(b.records)-1)

    def test_possible_id_reassignment_respects_cap(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));z=rs.pop(0)
        z['overture_id']=str(UUID(int=10));rs.append(z)
        r=compare_snapshots(b,self.future(b,rs),max_churn_hints=0)['source_record_churn']
        self.assertTrue(r['id_reassignment_review_truncated'])
        self.assertEqual(r['possible_id_reassignment_hints'],[])

    def test_no_hint_when_category_disagrees(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));z=rs.pop(0)
        z['overture_id']=str(UUID(int=10));z['basic_category']='another_category';rs.append(z)
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertFalse(r['possible_id_reassignment_hints'])

    def test_release_equal_rejected(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(b,b)

    def test_release_reversed_rejected(self):
        b=self.reference_short();a=self.future(b)
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(a,b)

    def test_timestamp_reversed_rejected(self):
        b=self.reference_short();a=self.future(b)
        later_old=replace(b,observed_at='2026-10-23T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(later_old,a)

    def test_exact_historical_backfill_allows_later_download_not_reversed_release(self):
        september=self.reference_short()
        august=replace(september,release='2026-08-19.0',
            observed_at='2026-10-11T06:00:00Z',origin='operator_supplied_research')
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(august,september)
        report=compare_snapshots(august,september,allow_historical_backfill=True)
        self.assertEqual(report['old_release'],'2026-08-19.0')
        self.assertEqual(report['new_release'],'2026-09-23.1')
        self.assertEqual(report['source_record_churn']['retained_ids'],len(august.records))
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(september,august,allow_historical_backfill=True)

    def test_backfill_exception_is_exact_and_cannot_accept_other_release_or_origin(self):
        september=self.reference_short()
        other=replace(september,release='2026-09-20.0',
            observed_at='2026-10-11T06:00:00Z',origin='operator_supplied_research')
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(other,september,allow_historical_backfill=True)
        actual=replace(september,release='2026-08-19.0',
            observed_at='2026-10-11T06:00:00Z',origin='pinned_real_archive')
        with self.assertRaisesRegex(ValueError,'unordered'):
            compare_snapshots(actual,september,allow_historical_backfill=True)
        with self.assertRaisesRegex(ValueError,'boolean'):
            compare_snapshots(actual,september,allow_historical_backfill=1)

    def test_future_source_record_before_release_date_rejected(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'before release'):
            synthetic_overlay(b,list(b.records),hypothetical_release=SYN_RELEASE,
                              hypothetical_observed_at='2026-10-11T00:00:00+03:00')

    def test_schema_transition_requires_migration(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'schema'):
            replace(b,schema='Overture Places schema v1.18')

    def test_future_sampling_footprint_change_rejected(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'sampling'):
            replace(b,sampling_cells=('besiktas_center',))

    def test_added_personal_field_rejected(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['phone']='555-000'
        with self.assertRaisesRegex(ValueError,'minimal POI schema'):
            self.future(b,rs)

    def test_fake_verified_and_open_now_rejected(self):
        b=self.reference_short()
        for k,v in [('consumer_verified',True),('open_now',True)]:
            rs=copy.deepcopy(list(b.records));rs[0][k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):self.future(b,rs)

    def test_duplicate_ids_rejected(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs.append(copy.deepcopy(rs[0]))
        with self.assertRaisesRegex(ValueError,'Repeated identity'):
            self.future(b,rs)

    def test_noncanonical_order_of_ids_rejected_by_snapshot(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'deterministic'):
            replace(b,records=tuple(reversed(b.records)))

    def test_population_hash_mutation_rejected(self):
        b=self.reference_short()
        with self.assertRaisesRegex(ValueError,'hash'):
            replace(b,population_sha256='a'*64)

    def test_out_of_cell_coordinate_rejected(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records));rs[0]['lat']=41.9
        with self.assertRaisesRegex(ValueError,'outside'):
            self.future(b,rs)

    def test_changed_schema_and_wrong_fields_not_silently_ignored(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records))
        rs[0]['taxonomy_primary']='another_category'
        r=compare_snapshots(b,self.future(b,rs))['source_record_churn']
        self.assertEqual(r['field_change_counts']['taxonomy_primary'],1)

    def test_detail_cap_reports_truncation(self):
        b=self.reference_short();rs=copy.deepcopy(list(b.records))
        for row in rs:row['name']='INVENTED NAME'
        r=compare_snapshots(b,self.future(b,rs),max_detail=0)['source_record_churn']
        self.assertTrue(r['detail_truncated'])
        self.assertEqual(r['modified_examples'],[])

    def test_invalid_cap_rejected(self):
        b=self.reference_short();f=self.future(b)
        for v in [True,-1,1001]:
            with self.subTest(v=v),self.assertRaises(ValueError):compare_snapshots(b,f,max_detail=v)

    def test_synthetic_fixture_same_report_repeat(self):
        self.assertEqual(controlled_future_example(),controlled_future_example())

    def _write_bundle(self,root:Path,*,tamper=None):
        b=self.reference_short();after=self.future(b)
        doc={'dataset':'KEP-DATA-001','release':SYN_RELEASE,'study_only':True,
             'records':list(after.records)}
        data=canonical(doc)
        m={'pinned_release':SYN_RELEASE,'research_only':True,'consumer_display_approved':False,
           'schema':SCHEMA, 'sample_cell_bounds_not_district_boundary':{k:list(v) for k,v in PILOT.items()},
           'human_verified_labels':0,'no_automatic_entity_merge':True,
           'license_evidence_url':'https://docs.overturemaps.org/attribution/',
           'source_files':[{'cell':cell,'sha256':'a'*64,'bytes':300} for cell in sorted(PILOT)],
           'normalized_sha256':sha256(data).hexdigest(),
           'population_sha256':sha256(canonical(list(after.records))).hexdigest(),
           'acquisition':{'method':'manual_overturemaps_cli_stac_pinned',
                          'downloaded_at_utc':SYN_DATE,'stac_catalog_sha256_before':'a'*64,
                          'stac_catalog_sha256_after':'a'*64}}
        if tamper:tamper(doc,m)
        (root/'places_minimal.json').write_bytes(canonical(doc))
        (root/'manifest.json').write_bytes(canonical(m))
        return sha256(data).hexdigest()

    def test_operator_bundle_parsed_but_not_upstream_authenticated(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp))
            x=load_operator_research_bundle(tmp,expected_release=SYN_RELEASE,
                         expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)
            self.assertEqual(x.origin,'operator_supplied_research')
            # Even if operator claims live retrieval, the comparator cannot authenticate S3.
            y=compare_snapshots(self.reference_short(),x)
            self.assertFalse(y['upstream_change_authenticated_by_comparison'])

    def test_wrong_operator_sha_rejected(self):
        with TemporaryDirectory() as tmp:
            self._write_bundle(Path(tmp))
            with self.assertRaisesRegex(ValueError,'Unpinned'):
                load_operator_research_bundle(tmp,expected_release=SYN_RELEASE,
                    expected_normalized_sha256='b'*64,expected_observed_at=SYN_DATE)

    def test_operator_bundle_rights_rejected(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp),tamper=lambda doc,m:m.update(consumer_display_approved=True))
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)

    def test_operator_bundle_schema_rejected(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp),tamper=lambda doc,m:m.update(schema='v1.18'))
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)

    def test_operator_bundle_wrong_time_rejected(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp))
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,
                expected_observed_at='2026-10-25T10:00:00+03:00')

    def test_operator_bundle_canonical_enforced(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp))
            path=Path(tmp)/'places_minimal.json'
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)


    def test_post_validation_mutation_rejected(self):
        b=self.reference_short();n=self.future(b)
        n.records[0]['name']='Mutated after validation'
        with self.assertRaisesRegex(ValueError,'changed after integrity'):
            compare_snapshots(b,n)

    def test_patch_versions_compare_numerically(self):
        b=self.reference_short();a=self.future(b)
        older=replace(b,release='2026-09-23.2')
        newer=replace(a,release='2026-09-23.10')
        self.assertEqual(compare_snapshots(older,newer)['old_release'],'2026-09-23.2')

    def test_op_bundle_missing_attribution_rejected(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp),tamper=lambda d,m:m.update(license_evidence_url=None))
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)

    def test_op_bundle_missing_canonical_geographical_source_rejected(self):
        with TemporaryDirectory() as tmp:
            sha=self._write_bundle(Path(tmp),tamper=lambda d,m:m.update(source_files=[]))
            with self.assertRaises(ValueError):load_operator_research_bundle(tmp,
                expected_release=SYN_RELEASE,expected_normalized_sha256=sha,expected_observed_at=SYN_DATE)

    def test_cli_offline_synthetic_uses_no_model_and_no_network(self):
        base=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,'scripts/overture_release_delta.py'],cwd=base,
                         capture_output=True,text=True,timeout=12)
        self.assertEqual(p.returncode,0,p.stderr)
        out=json.loads(p.stdout)
        self.assertTrue(out['synthetic_second_release'])
        self.assertFalse(out['real_world_business_changes_estimated'])

    def test_cli_incomplete_candidate_arguments_rejected(self):
        base=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,'scripts/overture_release_delta.py','--candidate-release',SYN_RELEASE],
                         cwd=base,capture_output=True,text=True,timeout=12)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('ALL four',p.stderr)

    def test_cli_future_observation_for_real_bundle_forbidden(self):
        base=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,'scripts/overture_release_delta.py','--candidate-dir','.',
            '--candidate-release',SYN_RELEASE,'--candidate-sha256','a'*64,
            '--candidate-observed-at','2099-01-01T00:00:00+03:00'],
            cwd=base,capture_output=True,text=True,timeout=12)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('Future-dated',p.stderr)

if __name__=='__main__':unittest.main()
