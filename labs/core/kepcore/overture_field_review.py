"""KEP-DATA-004: offline, fail-closed intake for the two blind 60-POI Excel sheets.

A workbook is NOT human ground truth simply because cells are filled. This
module validates the frozen sampling frame and visible evidence fields, and
only asks the pre-existing design estimator to compute a prevalence if ALL
sampled records have two concordant, resolved, timely human ballots.

Third-party adjudication is intentionally *not* silently collapsed into a
concordant pair. Disagreements stay unresolved for explicit future review.
No network; no workbook rewriting; no published business status; no AI calls.
"""
from __future__ import annotations

from pathlib import Path
from math import isfinite, log, sqrt
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile
import json
import posixpath
import re

from .calibration import aware
from .overture_real import DATA_DIR, load_archive, prepare_private_audit
from .overture_audit import estimate_existence_error

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
REL_DOC = '{http://schemas.openxmlformats.org/package/2006/relationships}'
MAX_XLSX_BYTES = 2_000_000
MAX_ZIP_EXPANDED = 8_000_000
EXPECTED_HEADERS = (
    'Sıra', 'Overture ID', 'Mekân adı', 'Kategori', 'Kaynak adresi',
    'Enlem', 'Boylam', 'Haritada incele', 'Sonuç', 'Değerlendirici ID',
    'Kontrol zamanı (ISO)', 'Kanıt URL', 'Gerekçe', 'İnceleme durumu',
)
ALLOWED_OUTCOMES = frozenset({'not_reviewed','exists','does_not_exist','unknown'})


def _sheets(path: str | Path) -> dict[str, dict[str, object]]:
    """Read only literal cells from xlsx using bounded OOXML standard library.

    Does not calculate formulas, use links or deserialize macros, relationships
    to remote resources, HTML, embedded media, or custom workbook code.
    """
    p = Path(path)
    if (p.suffix.lower() != '.xlsx' or p.is_symlink() or not p.is_file()
            or not 0 < p.stat().st_size <= MAX_XLSX_BYTES):
        raise ValueError('Missing, symlinked or oversized .xlsx review workbook')
    try:
        with ZipFile(p) as archive:
            entries = archive.infolist()
            names = {x.filename for x in entries}
            if (len(names) != len(entries) or len(entries) > 80
                or sum(x.file_size for x in entries) > MAX_ZIP_EXPANDED
                or any(x.file_size > MAX_ZIP_EXPANDED or x.filename.endswith('.bin')
                       or x.filename.startswith('xl/externalLinks/')
                       or '..' in x.filename.split('/') for x in entries)):
                raise ValueError('Unsafe workbook archive')
            def xml(name: str):
                if name not in names:
                    raise ValueError(f'Missing spreadsheet part: {name}')
                return ET.fromstring(archive.read(name))
            shared=[]
            if 'xl/sharedStrings.xml' in names:
                for item in xml('xl/sharedStrings.xml').findall(f'{NS}si'):
                    shared.append(''.join(n.text or '' for n in item.iter(f'{NS}t')))
            workbook=xml('xl/workbook.xml')
            rels={r.attrib.get('Id'):r.attrib.get('Target') for r in xml('xl/_rels/workbook.xml.rels').findall(f'{REL_DOC}Relationship')}
            all_sheets={}
            for sh in workbook.findall(f'{NS}sheets/{NS}sheet'):
                title=sh.attrib.get('name')
                if title not in {'Saha Denetimi','Araştırma Kimliği'}:
                    continue
                target=rels.get(sh.attrib.get(f'{REL_NS}id'))
                if not target:
                    raise ValueError('Sheet relationship missing')
                name=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
                if not name.startswith('xl/worksheets/') or name not in names:
                    raise ValueError('Invalid worksheet relationship')
                root=xml(name)
                cells={}
                for cell in root.iter(f'{NS}c'):
                    coordinate=cell.attrib.get('r')
                    if not coordinate or not re.fullmatch(r'[A-Z]{1,2}[1-9]\d{0,3}',coordinate):
                        continue
                    if cell.find(f'{NS}f') is not None:
                        raise ValueError('Formula in reviewed or metadata workbook')
                    kind=cell.attrib.get('t')
                    if kind=='inlineStr':
                        inline=cell.find(f'{NS}is')
                        value=''.join(n.text or '' for n in inline.iter(f'{NS}t')) if inline is not None else ''
                    else:
                        value_node=cell.find(f'{NS}v')
                        value=value_node.text if value_node is not None else None
                        if kind=='s' and value is not None:
                            idx=int(value)
                            if idx<0 or idx>=len(shared):
                                raise ValueError('Invalid shared-string index')
                            value=shared[idx]
                        elif kind=='n' or kind is None:
                            if value is not None:
                                value=float(value)
                    if coordinate in cells:
                        raise ValueError('Repeated spreadsheet cell')
                    cells[coordinate]=value
                all_sheets[title]=cells
    except (BadZipFile, ET.ParseError, KeyError, IndexError, OverflowError) as exc:
        raise ValueError('Invalid XLSX review workbook') from exc
    if set(all_sheets) != {'Saha Denetimi','Araştırma Kimliği'}:
        raise ValueError('Required review and study identity worksheets missing')
    return all_sheets


def _as_text(value: object) -> str | None:
    if value is None: return None
    if not isinstance(value, str):
        raise ValueError('Expected text cell')
    return value.strip()


def _as_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value,(int,float)):
        raise ValueError('Expected numeric coordinate/index')
    from math import isfinite
    if not isfinite(value):raise ValueError('Non-finite coordinate')
    return float(value)


def read_review_sheet(path: str | Path, *, role: str, plan: dict, frozen: dict,
                      source_run_url: str | None=None) -> dict:
    """Review 60 exact sampled POIs; protect displayed fixed fields from editing.

    `plan` MUST separately be regenerated from the private sampling seed by
    `load_and_resolve`; do not pass unverified plan in operational code.
    """
    if role not in ('A','B'):raise ValueError('Expected reviewer role A or B')
    sheets=_sheets(path)
    ws=sheets['Saha Denetimi']; meta=sheets['Araştırma Kimliği']
    if tuple(_as_text(ws.get(f'{chr(65+i)}5')) for i in range(14))!=EXPECTED_HEADERS:
        raise ValueError('Review template headers were changed')
    expected_metadata={
        'B2':'KEP-DATA-003 / 002 physical existence survey',
        'B3':plan['source_release'],
        'B4':plan['population_n'],
        'B5':plan['audit_budget'],
        'B6':plan['population_sha256'],
        'B7':plan['seed_commitment_sha256'],
        'B9':role,
    }
    if source_run_url is not None:
        expected_metadata['B8']=source_run_url
    for coordinate, expected in expected_metadata.items():
        if meta.get(coordinate)!=expected:
            raise ValueError(f'Frozen study identity mismatch at {coordinate}')
    selections=plan['selected']; ids={s['overture_id'] for s in selections}
    if len(ids)!=60 or len(selections)!=60:
        raise ValueError('Only the preregistered 60-sample template is supported')
    if any(re.fullmatch(r'[A-N](?:6[6-9]|[7-9]\d|[1-9]\d{2,})',key) and value not in (None,'')
           for key,value in ws.items()):
        raise ValueError('Unexpected appended review rows')
    rows={}
    for line in range(6,66):
        rid=_as_text(ws.get(f'B{line}'))
        if not rid or rid in rows or rid not in ids:
            raise ValueError('Missing, duplicate or changed sampled place identifier')
        row=frozen.get(rid)
        if row is None:raise ValueError('Place absent from pinned Overture archive')
        if _as_number(ws.get(f'A{line}'))!=line-5:
            raise ValueError('Review sheet index changed')
        for col,key in [('C','name'),('D','basic_category'),('E','address')]:
            if _as_text(ws.get(f'{col}{line}'))!=row[key]:
                raise ValueError(f'Review sheet place {key} was modified')
        for col,key in [('F','lat'),('G','lon')]:
            if abs(_as_number(ws.get(f'{col}{line}'))-row[key])>1e-7:
                raise ValueError('Review coordinate was modified')
        link=_as_text(ws.get(f'H{line}'))
        expected_map=f'https://www.google.com/maps/search/?api=1&query={row["lat"]:.7f},{row["lon"]:.7f}'
        if link != expected_map:
            raise ValueError('Original coordinate lookup link changed')
        status=_as_text(ws.get(f'I{line}'))
        if status not in ALLOWED_OUTCOMES:
            raise ValueError('Invalid or empty review outcome')
        reviewer=_as_text(ws.get(f'J{line}'))
        timestamp=_as_text(ws.get(f'K{line}'))
        evidence=_as_text(ws.get(f'L{line}'))
        reason=_as_text(ws.get(f'M{line}'))
        if status=='not_reviewed':
            if any([timestamp,evidence,reason]):
                raise ValueError('Unreviewed row contains partial evidence: finish or clear the ballot')
            if reviewer not in (None, f'reviewer-{role.lower()}'):
                raise ValueError('Unreviewed row contains changed reviewer identity')
            vote=None
        else:
            if (not reviewer or reviewer.casefold() in {'ai','model','simulator','unknown',
                 'reviewer-a','reviewer-b'}):
                raise ValueError('Replace placeholder with a real pseudonymous human reviewer ID')
            if not timestamp or not evidence or not reason:
                raise ValueError('Completed review must have date, independent URL and reason')
            checked=aware(timestamp)
            if checked<aware(plan['sampled_at']):
                raise ValueError('Review predates frozen sampling')
            target=urlsplit(evidence)
            if (target.scheme!='https' or not target.hostname or target.username or target.password
                or len(evidence)>2048 or any(ch.isspace() for ch in evidence)
                or link==evidence):
                raise ValueError('Evidence must be a specific HTTPS citation, not coordinate-search URL')
            if not 8<=len(reason)<=1000:
                raise ValueError('Reviewer explanation must have 8-1000 characters')
            vote={
                'reviewer_id':reviewer,'outcome':status,
                'checked_at':timestamp,'evidence_url':evidence,
            }
        rows[rid]=vote
    if set(rows)!=ids:raise ValueError('Workbook rows do not cover frozen sample')
    return {'role':role,'votes':rows,'completed':sum(v is not None for v in rows.values())}


def conservative_precision_budget(plan: dict, *, alpha: float=.05, target_half_width: float=.10) -> dict:
    """Pre-review finite-frame precision forecast for the EXISTING estimator.

    Uses precisely the stratified Hoeffding union bound implemented in
    `estimate_existence_error`, not an optimistic sample standard error.
    The nominal level assumes correct human labels and random within-stratum
    sampling; it is NOT a guarantee about all Istanbul venues or future data.
    """
    if (not isinstance(alpha,(int,float)) or isinstance(alpha,bool) or not isfinite(alpha)
        or not 0<alpha<1 or not isinstance(target_half_width,(int,float))
        or isinstance(target_half_width,bool) or not isfinite(target_half_width)
        or not 0<target_half_width<1):
        raise ValueError('Invalid nominal confidence/precision parameters')
    strata=plan.get('strata')
    N=plan.get('population_n')
    if not isinstance(strata,list) or not strata or type(N)!=int or N<1:
        raise ValueError('Incomplete frozen sampling design')
    if (sum(x['population_n'] for x in strata)!=N or
        sum(x['selected_n'] for x in strata)!=plan.get('audit_budget') or
        any(type(x['population_n'])!=int or type(x['selected_n'])!=int or
            not 1<=x['selected_n']<=x['population_n'] for x in strata)):
        raise ValueError('Inconsistent sample allocation')
    H=len(strata)
    radius=sum(
        (x['population_n']/N)*sqrt(log(2*H/alpha)/(2*x['selected_n']))
        if x['selected_n']<x['population_n'] else 0.
        for x in strata
    )
    return {
        'method':'preregistered_stratified_Hoeffding_union_bound',
        'population_n':N,'sample_n':plan['audit_budget'],
        'nominal_confidence':round(1-alpha,4),
        'worst_case_half_width_fraction':round(radius,6),
        'target_half_width_fraction':round(target_half_width,6),
        'target_met':radius<=target_half_width,
        'human_truth_labels_collected':False,
        'interpretation':'Pre-review conservative design bound, not a source correctness estimate.',
    }

def evaluate_review_workbooks(*, reviewer_a: str|Path, reviewer_b: str|Path,
                              audit_plan: str|Path, seed_file: str|Path,
                              evaluation_asof: str, directory: Path|str=DATA_DIR) -> dict:
    """No rate until full, concordant, in-time double review of every sample.

    Private seed, reviewer identifiers and evidence URLs are NOT emitted.
    """
    if Path(seed_file).is_symlink() or not Path(seed_file).is_file():
        raise ValueError('Missing or unsafe private seed file')
    seed=Path(seed_file).read_text(encoding='utf-8').strip()
    if len(seed)<16:raise ValueError('Private seed too short')
    plan=json.loads(Path(audit_plan).read_text(encoding='utf-8'))
    if not isinstance(plan,dict) or plan.get('research_only') is not True:
        raise ValueError('Invalid research-only sampling plan')
    frozen=prepare_private_audit(directory,budget=plan['audit_budget'],seed=seed,
                                 sampled_at=plan['sampled_at'])
    if plan != frozen['plan']:
        raise ValueError('Private seed or frozen sample/weights were tampered with')
    doc,manifest,meta=load_archive(directory,verify=False)
    records={r['overture_id']:r for r in doc['records']}
    a=read_review_sheet(reviewer_a,role='A',plan=plan,frozen=records,
                        source_run_url=meta['original_actions_run_url'])
    b=read_review_sheet(reviewer_b,role='B',plan=plan,frozen=records,
                        source_run_url=meta['original_actions_run_url'])
    selected_ids=sorted(a['votes'])
    labels=[]
    missing=[];conflicting=[];unknown=[];complete=[]
    asof=aware(evaluation_asof)
    for rid in selected_ids:
        x=a['votes'][rid]; y=b['votes'][rid]
        if x is None or y is None:
            missing.append(rid)
            continue
        if x['reviewer_id'].casefold()==y['reviewer_id'].casefold():
            raise ValueError('Same reviewer identity used on both blind worksheets')
        if aware(x['checked_at'])>asof or aware(y['checked_at'])>asof:
            missing.append(rid)
            continue
        if x['outcome']=='unknown' or y['outcome']=='unknown':
            unknown.append(rid)
        elif x['outcome']!=y['outcome']:
            conflicting.append(rid)
        else:
            complete.append(rid)
        labels.append({'overture_id':rid,'votes':[x,y]})
    report={
        'study':'KEP-DATA-004','research_only':True,'consumer_publish':False,
        'source_release':meta['release'],'population_n':len(records),
        'selected_n':len(selected_ids),'sampled_n_by_stratum':plan['strata'],
        'design_precision_forecast':conservative_precision_budget(plan),
        'reviewer_a_completed':a['completed'],'reviewer_b_completed':b['completed'],
        'concordant_resolved':len(complete),'missing_or_late':len(missing),
        'disagreements':len(conflicting),'unknown_responses':len(unknown),
        'requires_third_independent_adjudication':len(conflicting),
        'error_fraction_estimate':None,'confidence_band':None,
        'survey_label_truth_verified_independently':False,
        'warning':'Source-only POIs; reviewer-ID distinction is not proof of human independence. No current-open/venue verification guarantee.',
    }
    if len(complete)!=len(selected_ids):
        return {**report,'status':'INCOMPLETE_BLIND_AUDIT'}
    # Release estimator only after all 60 have two reconciled resolved votes.
    from tempfile import TemporaryDirectory
    from .overture_places import canonical
    with TemporaryDirectory(prefix='kep-field-estimator-') as tmp:
        temp=Path(tmp)
        (temp/'places_minimal.json').write_bytes(canonical(doc))
        (temp/'manifest.json').write_bytes(canonical(manifest))
        measured=estimate_existence_error(temp,plan=plan,seed=seed,labels=labels,
                                          evaluation_asof=evaluation_asof)
    return {**report,'status':measured['status'],
            'error_fraction_estimate':measured['error_fraction_estimate'],
            'confidence_band':measured['confidence_band'],
            'per_confidence_band':measured.get('per_confidence_band'),
            'estimator':measured['confidence_band']['method'] if measured['confidence_band'] else None,
            'interpretation':'Sample-frame diagnostic only, conditional on accurate human labels and sampling assumptions.',
    }
