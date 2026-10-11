"""DATA-014: offline review of captured metadata, not publisher event truth."""
from collections import defaultdict
from .gers_access_cost import RELEASES, validate_objects


def review_metadata(objects):
    """Same footer bytes/ETag/length are an alias signal, not a full object hash.

    STAC previous-release navigation does not independently authenticate the
    comparison baseline used to generate a patch release's changelog.
    """
    validate_objects(objects)
    seen = defaultdict(lambda: defaultdict(int))
    for obj in objects:
        signature = (obj['change_type'], obj['size'], obj['etag'], obj['footer_sha256'])
        seen[signature][obj['release']] += 1
    pairs = sum(min(counts.get(RELEASES[0], 0), counts.get(RELEASES[1], 0))
                for counts in seen.values())
    all_paired = pairs > 0 and pairs * 2 == len(objects)
    return {
        'cross_release_identical_footer_etag_size_pairs': pairs,
        'all_objects_have_cross_release_metadata_counterpart': all_paired,
        'unique_footer_hashes': len({o['footer_sha256'] for o in objects}),
        'full_object_sha256_available': False,
        'event_content_equality_verified': False,
        'independent_source_count': 1,
        'verified_changelog_comparison_baseline': None,
        'stac_prev_is_not_changelog_baseline_authentication': True,
        'safe_to_compose_as_independent_adjacent_hops': False,
        'assessment': 'PATCH_BASELINE_REQUIRES_PUBLISHER_VERIFICATION',
    }
