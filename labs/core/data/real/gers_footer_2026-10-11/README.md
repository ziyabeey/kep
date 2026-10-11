# Actual public GERS footer metadata, 2026-10-11

Research-only access to Overture Maps public changelog partitions for `2026-09-23.0` and `2026-09-23.1`, Places/place. Source: https://docs.overturemaps.org/gers/changelog/ . Attribution and provider-specific licensing: https://docs.overturemaps.org/attribution/ . Existing Places archive attributions in [DATA_LICENSES.md](../../../DATA_LICENSES.md) are not replaced or broadened.

`footers.zip` contains the exact metadata footer and trailer bytes of 128 listed objects plus a canonical normalized metadata manifest. It contains **no data pages, completed event rows, private review files, or seeds**. Footer statistics include published bounding and identifier ranges; they are not verified individual matches or business facts.

- Source capture: https://github.com/ziyabeey/kep/actions/runs/38150426830
- Git capture commit: `4c19d672c880b88a555f5384dc853a136982ee77`
- Inner `footers.zip` SHA-256: `1cefe054f5b61adfa2117d43e441626ab5355fed1096aa105b397d70f619bf9d`
- Downloaded outer Actions artifact SHA-256: `5425121504dccfb7d33e4e28a93baa760f3b24262c1470763a53176113e4793e`
- The code pins the inner digest and verifies every stored footer against the manifest.
- Each source range checked HTTP 206, exact Content-Range/length, ETag and If-Match. These are transport/integrity checks, not independent publisher signatures.

`first_failure_receipt.json` preserves the original length-validation failure from run 38149968929. Its exact SHA-256 is `022f7d64c4f6d16e30b291d602895a8e6cb2c8c0094be7ecda604ea70dc20dc1`; no body bytes were read in that attempt. The failed outer Actions artifact digest was `27866b6e8dc8300bf4e6085b18b7067d0006ac9f20a725afb9148e4f1ba15add`.

Raw S3 listing bodies were not retained, only their hashes and returned object metadata. No full object SHA-256 was acquired. All 128 objects have a metadata counterpart across releases (64 pairs with identical footer SHA/ETag/size), which must not be misrepresented as authenticated equality of event contents or independently generated adjacent-hop changelogs.

Offline protocol and limitations: [GERS_FOOTER_COST.md](../../../docs/GERS_FOOTER_COST.md).
