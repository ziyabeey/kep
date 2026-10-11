"""KEP-FIELD-001: empirical source-existence audit versus frozen claim policies.

Uses the existing independent A/B review intake and weighted sample estimator.
No field labels, models, new data extraction, automatic consumer publication, or
actual early opening/closure accuracy are produced by this module.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

from .overture_field_review import evaluate_review_workbooks
from .overture_places import canonical
from .overture_real import DATA_DIR

EXPERIMENT = 'KEP-FIELD-001'
FROZEN_POLICIES = (
    'naive_all_overture_records_claim_physical_existence',
    'kep_current_unverified_source_abstains',
)


def protocol():
    """Preregistered policies: no private read, no empirical labels."""
    return {
        'experiment': EXPERIMENT,
        'status': 'AWAITING_INDEPENDENT_HUMAN_REVIEW',
        'population': 'pinned Overture 2026-09-23.1, two small Istanbul pilot cells',
        'sampling': '60 unique records, proportional six-stratum confidence x cell random design',
        'policies': list(FROZEN_POLICIES),
        'primary_estimate': 'design_weighted_source_nonexistence_diagnostic',
        'naive_assertions': 'all selected Overture-listed records; not validated',
        'kep_automatic_assertions': 0,
        'human_verified_labels': 0,
        'source_nonexistence_estimate': None,
        'claim_false_positive_rate': None,
        'business_openings_accuracy': None,
        'business_closures_accuracy': None,
        'consumer_publish': False,
        'model_training': False,
        'no_original_cohort_resampling': True,
        'notes': ('Policy safety/coverage comparison only, not KEP predictive superiority. '
                  'New private seed must stay off-repo.'),
    }


def evaluate_pilot(*, reviewer_a: str | Path, reviewer_b: str | Path,
                   audit_plan: str | Path, seed_file: str | Path,
                   evaluation_asof: str, directory: Path | str = DATA_DIR) -> dict:
    """The same strict original A/B intake and estimator; aggregates only.

    A completed workbook never proves the reviewers are independent humans.
    The operator must verify human independence and evidence roots separately.
    """
    base = evaluate_review_workbooks(
        reviewer_a=reviewer_a, reviewer_b=reviewer_b,
        audit_plan=audit_plan, seed_file=seed_file,
        evaluation_asof=evaluation_asof, directory=directory,
    )
    plan_path = Path(audit_plan)
    if plan_path.is_symlink() or not plan_path.is_file():
        raise ValueError('Missing or unsafe private frozen plan')
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    if canonical(plan) != raw or plan.get('audit_budget') != 60 or base['selected_n'] != 60:
        raise ValueError('Only the immutable preregistered 60-place cohort is supported')
    if base['status'] not in {'INCOMPLETE_BLIND_AUDIT', 'COMPLETE_DESIGN_BASED_DIAGNOSTIC'}:
        raise ValueError('Unreviewed estimator status')
    complete = (base['missing_or_late'] == 0 and base['disagreements'] == 0
                and base['unknown_responses'] == 0 and base['concordant_resolved'] == 60)
    rate = base['error_fraction_estimate']
    if (not complete and rate is not None) or (complete and rate is None):
        raise ValueError('Inconsistent review completeness and source estimate')
    return {
        'experiment': EXPERIMENT,
        'origin': 'pinned_source_records_plus_private_review_ballots',
        'research_only': True, 'consumer_publish': False,
        'status': ('ALL_BALLOTS_RESOLVED_INDEPENDENCE_REQUIRES_MANUAL_ATTESTATION'
                   if complete else 'INCOMPLETE_BLIND_AUDIT'),
        'sample_plan_sha256': sha256(raw).hexdigest(),
        'source_release': base['source_release'],
        'population_n': base['population_n'], 'sample_n': base['selected_n'],
        'reviewer_a_completed': base['reviewer_a_completed'],
        'reviewer_b_completed': base['reviewer_b_completed'],
        'concordant_resolved': base['concordant_resolved'],
        'missing_or_late': base['missing_or_late'],
        'disagreements': base['disagreements'],
        'unknown_responses': base['unknown_responses'],
        'design_precision_forecast': base['design_precision_forecast'],
        'baseline_always_asserts_existence_n': 60,
        'kep_current_unverified_source_automatic_existence_assertions_n': 0,
        'naive_source_nonexistence_fraction': rate if complete else None,
        'naive_source_nonexistence_band': base['confidence_band'] if complete else None,
        'kep_predictive_accuracy': None,
        'independent_human_field_truth_authenticated': False,
        'real_openings_accuracy': None, 'real_closures_accuracy': None,
        'comparison_explanation': (
            'Naive coverage is 100%; KEP safety policy abstains on these unverified records. '
            'Zero automated assertions is not an accuracy or usefulness advantage.'
        ),
    }
