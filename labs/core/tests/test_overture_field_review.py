"""KEP-DATA-004: wholly synthetic ballots on real frozen source records.

NO physical venue was verified by these tests. The 60 genuine sampled source
records provide structure; all positive/negative field labels here are fake.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import json
import shutil
import subprocess
import sys
import unittest

from kepcore.overture_real import DATA_DIR, prepare_private_audit, load_archive
from kepcore.overture_field_review import (
    _sheets, read_review_sheet, evaluate_review_workbooks, conservative_precision_budget,
)

SEED='KEP-DATA-004-PUBLIC-UNITTEST-SEED-NOT-HUMAN'
AT='2026-10-11T01:00:00+00:00'
REVIEW_AT='2026-10-11T12:00:00+03:00'
BEFORE='2026-10-11T10:30:00+03:00'
EVAL='2026-10-12T12:00:00+03:00'
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NSREL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def cell(addr, v, *, formula=False):
    if v is None:return ''
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        return f'<c r="{addr}" t="n"><v>{v}</v></c>'
    value=escape(str(v))
    if formula:
        return f'<c r="{addr}"><f>{value}</f><v>0</v></c>'
    return f'<c r="{addr}" t="inlineStr"><is><t>{value}</t></is></c>'


def worksheet(cells):
    byrow={}
    for addr,value in cells.items():
        import re
        row=int(re.search(r'\d+',addr).group())
        byrow.setdefault(row,[]).append(cell(addr,value))
    ordered=''.join(f'<row r="{n}">{"".join(v)}</row>' for n,v in sorted(byrow.items()))
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}"><sheetData>{ordered}</sheetData></worksheet>'


def make_book(path,role,plan,lookup,*,votes=None,edit=None):
    rows={}
    from kepcore.overture_field_review import EXPECTED_HEADERS
    for j,title in enumerate(EXPECTED_HEADERS):rows[f'{chr(65+j)}5']=title
    for i,s in enumerate(plan['selected'],6):
        rid=s['overture_id'];r=lookup[rid]
        for c,v in {
            'A':i-5,'B':rid,'C':r['name'],'D':r['basic_category'],
            'E':r['address'],'F':r['lat'],'G':r['lon'],
            'H':f'https://www.google.com/maps/search/?api=1&query={r["lat"]:.7f},{r["lon"]:.7f}',
            'I':'not_reviewed','J':f'reviewer-{role.lower()}',
            'N':'REVIEW_REQUIRED',
        }.items():rows[f'{c}{i}']=v
        if votes and rid in votes:
            outcome=votes[rid];rows[f'I{i}']=outcome
            rows[f'J{i}']=f'synthetic-human-{role.lower()}-fixture'
            rows[f'K{i}']=REVIEW_AT
            rows[f'L{i}']=f'https://example.org/synthetic-not-real-evidence/{rid}'
            rows[f'M{i}']='This is a synthetic unit test vote and not field evidence.'
    meta={
        'A1':'Alan','B1':'Değer',
        'B2':'KEP-DATA-003 / 002 physical existence survey','B3':plan['source_release'],
        'B4':plan['population_n'],'B5':plan['audit_budget'],
        'B6':plan['population_sha256'],'B7':plan['seed_commitment_sha256'],
        'B8':'https://github.com/ziyabeey/kep/actions/runs/38096227796',
        'B9':role,
    }
    if edit:
        if edit[0]=='meta':meta[edit[1]]=edit[2]
        else:rows[edit[1]]=edit[2]
    workbook=f'''<?xml version="1.0"?><workbook xmlns="{NS}" xmlns:r="{NSREL}"><sheets><sheet name="Saha Denetimi" sheetId="1" r:id="rId1"/><sheet name="Araştırma Kimliği" sheetId="2" r:id="rId2"/></sheets></workbook>'''
    rels='''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>'''
    with ZipFile(path,'w',ZIP_DEFLATED) as out:
        out.writestr('xl/workbook.xml',workbook)
        out.writestr('xl/_rels/workbook.xml.rels',rels)
        out.writestr('xl/worksheets/sheet1.xml',worksheet(rows))
        out.writestr('xl/worksheets/sheet2.xml',worksheet(meta))


class FieldTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freeze=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AT)
        cls.plan=cls.freeze['plan']
        doc,_,cls.meta=load_archive(DATA_DIR,verify=False)
        cls.lookup={r['overture_id']:r for r in doc['records']}
        cls.ids=[s['overture_id'] for s in cls.plan['selected']]

    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.plan_file=self.path/'plan.json';self.plan_file.write_text(json.dumps(self.plan))
        self.seed_file=self.path/'private-seed.txt';self.seed_file.write_text(SEED)

    def pack(self,role='A',votes=None,edit=None):
        path=self.path/f'reviewer_{role}.xlsx'
        make_book(path,role,self.plan,self.lookup,votes=votes,edit=edit)
        return path

    def run_two(self,a=None,b=None,plan=None,seed=None,asof=EVAL):
        return evaluate_review_workbooks(
            reviewer_a=a or self.pack('A'),reviewer_b=b or self.pack('B'),
            audit_plan=plan or self.plan_file,seed_file=seed or self.seed_file,
            evaluation_asof=asof)

    def test_genuine_sample_size_and_strata(self):
        self.assertEqual(len(self.ids),60)
        self.assertEqual(len(self.plan['strata']),6)
        self.assertEqual(self.plan['population_n'],4803)

    def test_conservative_design_interval_wide_for_60(self):
        r=conservative_precision_budget(self.plan)
        self.assertAlmostEqual(r['worst_case_half_width_fraction'],.517502,places=5)
        self.assertFalse(r['target_met'])
        self.assertFalse(r['human_truth_labels_collected'])

    def test_precision_forecast_plan_accounting_fail_closed(self):
        edited=dict(self.plan);edited['population_n']=6000
        with self.assertRaisesRegex(ValueError,'Inconsistent'):
            conservative_precision_budget(edited)

    def test_precision_forecast_bad_parameters_rejected(self):
        with self.assertRaises(ValueError):
            conservative_precision_budget(self.plan,alpha=float('nan'))

    def test_blank_template_gives_no_rate(self):
        result=self.run_two()
        self.assertEqual(result['status'],'INCOMPLETE_BLIND_AUDIT')
        self.assertEqual(result['reviewer_a_completed'],0)
        self.assertEqual(result['reviewer_b_completed'],0)
        self.assertEqual(result['missing_or_late'],60)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_one_partial_response_no_rate(self):
        a=self.pack('A',votes={self.ids[0]:'exists'})
        result=self.run_two(a=a)
        self.assertEqual(result['reviewer_a_completed'],1)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_one_sided_all_responses_no_rate(self):
        a=self.pack('A',votes=dict.fromkeys(self.ids,'exists'))
        result=self.run_two(a=a)
        self.assertEqual(result['reviewer_a_completed'],60)
        self.assertEqual(result['reviewer_b_completed'],0)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_complete_two_synthetic_agree_runs_design_estimator(self):
        fake={rid:'does_not_exist' if n%17==0 else 'exists'
              for n,rid in enumerate(self.ids)}
        a=self.pack('A',votes=fake);b=self.pack('B',votes=fake)
        result=self.run_two(a=a,b=b)
        self.assertEqual(result['status'],'COMPLETE_DESIGN_BASED_DIAGNOSTIC')
        self.assertEqual(result['concordant_resolved'],60)
        self.assertIsInstance(result['error_fraction_estimate'],float)
        self.assertFalse(result['consumer_publish'])
        self.assertFalse(result['survey_label_truth_verified_independently'])

    def test_conflicting_votes_stop_rate(self):
        a=dict.fromkeys(self.ids,'exists');b=a.copy();b[self.ids[0]]='does_not_exist'
        result=self.run_two(a=self.pack('A',votes=a),b=self.pack('B',votes=b))
        self.assertEqual(result['disagreements'],1)
        self.assertEqual(result['requires_third_independent_adjudication'],1)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_unknown_vote_stops_rate(self):
        a=dict.fromkeys(self.ids,'exists');b=a.copy();b[self.ids[0]]='unknown'
        result=self.run_two(a=self.pack('A',votes=a),b=self.pack('B',votes=b))
        self.assertEqual(result['unknown_responses'],1)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_reviewer_role_swap_rejected(self):
        with self.assertRaisesRegex(ValueError,'B9'):
            self.run_two(a=self.pack('B'),b=self.pack('A'))

    def test_frozen_place_name_tamper_rejected(self):
        a=self.pack('A',edit=('row','C6','Fake Store Name'))
        with self.assertRaisesRegex(ValueError,'name was modified'):
            self.run_two(a=a)

    def test_frozen_address_tamper_rejected(self):
        a=self.pack('A',edit=('row','E6','Changed by attacker'))
        with self.assertRaisesRegex(ValueError,'address was modified'):
            self.run_two(a=a)

    def test_coordinate_tamper_rejected(self):
        a=self.pack('A',edit=('row','F6',41.0001))
        with self.assertRaisesRegex(ValueError,'coordinate was modified'):
            self.run_two(a=a)

    def test_map_link_tamper_rejected(self):
        a=self.pack('A',edit=('row','H6','https://www.google.com/maps/search/?api=1&query=41,30'))
        with self.assertRaisesRegex(ValueError,'lookup link changed'):
            self.run_two(a=a)

    def test_source_provenance_tamper_rejected(self):
        a=self.pack('A',edit=('meta','B8','https://example.com/fake-run'))
        with self.assertRaisesRegex(ValueError,'B8'):
            self.run_two(a=a)

    def test_sample_id_tamper_rejected(self):
        a=self.pack('A',edit=('row','B6','fake-id'))
        with self.assertRaisesRegex(ValueError,'sampled place identifier'):
            self.run_two(a=a)

    def test_appended_hidden_review_row_rejected(self):
        a=self.pack('A',edit=('row','B66','forged-extra-row'))
        with self.assertRaisesRegex(ValueError,'appended'):
            self.run_two(a=a)

    def test_seed_mismatch_rejected(self):
        other=self.path/'other.txt';other.write_text(SEED+'different')
        with self.assertRaisesRegex(ValueError,'tampered'):
            self.run_two(seed=other)

    def test_sample_plan_tamper_rejected(self):
        changed=dict(self.plan)
        changed['selected']=self.plan['selected'][:-1]
        self.plan_file.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'tampered'):
            self.run_two()

    def test_future_review_excluded(self):
        fake=dict.fromkeys(self.ids,'exists')
        res=self.run_two(a=self.pack('A',votes=fake),b=self.pack('B',votes=fake),asof=BEFORE)
        self.assertEqual(res['missing_or_late'],60)
        self.assertIsNone(res['error_fraction_estimate'])

    def test_placeholder_reviewer_not_human_verification(self):
        a=self.pack('A',votes={self.ids[0]:'exists'},edit=('row','J6','reviewer-a'))
        with self.assertRaisesRegex(ValueError,'placeholder'):
            self.run_two(a=a)

    def test_partial_label_not_accepted(self):
        a=self.pack('A',edit=('row','K6',REVIEW_AT))
        with self.assertRaisesRegex(ValueError,'partial evidence'):
            self.run_two(a=a)

    def test_invalid_evidence_url_rejected(self):
        a=self.pack('A',votes={self.ids[0]:'exists'},edit=('row','L6','http://example.org'))
        with self.assertRaisesRegex(ValueError,'HTTPS'):
            self.run_two(a=a)

    def test_original_map_link_not_independent_evidence(self):
        row=self.lookup[self.ids[0]]
        same=f'https://www.google.com/maps/search/?api=1&query={row["lat"]:.7f},{row["lon"]:.7f}'
        a=self.pack('A',votes={self.ids[0]:'exists'},edit=('row','L6',same))
        with self.assertRaisesRegex(ValueError,'coordinate-search'):
            self.run_two(a=a)

    def test_invalid_zip_rejected(self):
        a=self.path/'invalid.xlsx';a.write_bytes(b'NOT A ZIP')
        with self.assertRaisesRegex(ValueError,'Invalid XLSX'):
            self.run_two(a=a)

    def test_non_workbook_extension_rejected(self):
        a=self.path/'bad.xls';a.write_text('not excel')
        with self.assertRaisesRegex(ValueError,'.xlsx'):
            self.run_two(a=a)

    def test_formula_in_review_field_rejected(self):
        a=self.pack('A');shutil.copyfile(a,self.path/'old.xlsx')
        # Safely rebuild XML as a formula to assert formula execution never occurs.
        from zipfile import ZipFile, ZIP_DEFLATED
        old=self.path/'old.xlsx'
        with ZipFile(old) as z:
            old_parts={n:z.read(n) for n in z.namelist()}
        xml=old_parts['xl/worksheets/sheet1.xml'].decode()
        xml=xml.replace('<c r="I6" t="inlineStr"><is><t>not_reviewed</t></is></c>',
                        '<c r="I6"><f>1+1</f><v>2</v></c>')
        with ZipFile(a,'w',ZIP_DEFLATED) as z:
            for n,data in old_parts.items():z.writestr(n,xml if n=='xl/worksheets/sheet1.xml' else data)
        with self.assertRaisesRegex(ValueError,'Formula'):
            self.run_two(a=a)

    def test_public_cli_help_no_auth(self):
        path=Path(__file__).resolve().parents[1]/'scripts/intake_overture_field_workbooks.py'
        proc=subprocess.run([sys.executable,str(path),'--help'],capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('--reviewer-a',proc.stdout)


if __name__ == '__main__':unittest.main()
