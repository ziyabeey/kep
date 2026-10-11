# KEP Core Lab v0.3

**KEP için yerel veri, güvenli aday seçimi ve gerçek geçmiş puanlarla öğrenme laboratuvarı.** Bu paket bir mobil uygulama veya tamamlanmış AI asistanı değildir. GitHub deposunda yalnızca araştırma laboratuvarıdır; canlı mobil uygulama değildir.

## Çalıştır

Python 3.10+ ve IANA saat dilimi verisi bulunan ortam:

```bash
cd labs/core
python3 run_all.py
python3 -m unittest discover -s tests -v
python3 play_preferences.py --user U1001 --method user_mean
python3 play_preferences.py --user U1001 --method item_knn
python3 query.py --query examples/galata_nearby.json
python3 query.py --query examples/galata_open_budget.json
```

Standart kütüphane yeterlidir; ağ ve model anahtarı gerekmez. Saat dilimi verisi olmayan sistemde `tzdata` kurulabilir. `scripts/fetch_open_data.py` ayrı, isteğe bağlı bir ağ aracıdır; laboratuvar bunu otomatik çalıştırmaz.

## Neler var?

- `kepcore/core.py`: sert kullanıcı kısıtları, belirsizlik ve kararlar.
- `kepcore/radar.py` + `sources/registry.json`: kayıtlı kaynak ve kullanım izni denetimi, sınırlı araştırma toplaması. Varsayılan çevrimdışı.
- `scripts/poll_source.py`: açıkça istenmedikçe hiçbir ağa bağlanmayan CLI.
- `kepcore/availability.py`: saat dilimi, tam haftalık açılış aralığı, tarih istisnası ve alan bazlı güncellik.
- `kepcore/store.py`: yerel SQLite, idempotent kayıt, eski güncelleme koruması ve outbox örneği.
- `kepcore/preferences.py`: beş klasik gerçek-puan tahmin yöntemi; uygun aday dışına çıkamayan yeniden sıralama.
- `kepcore/model_boundary.py`: MiMo/Laya için çevrimdışı yapılandırılmış çıktı sınırı. **Gerçek API istemcisi değil.**
- `benchmarks/preference_protocol.json`: eğitim/doğrulama/test yöntemi ve önceden belirlenmiş karşılaştırmalar.
- `data/raw/uci/rating_final.csv`: 1.161 gerçek tarihsel puan, 138 kullanıcı, 130 restoran kimliği. CC BY 4.0 atıflı.
- `results/preference_results.json`: bütün test tahminleri, seçilen parametreler, belirsizlik hesapları.
- `results/release_summary.json`: güncel özet.
- `docs/RESEARCH_REPORT_V03.md`: yorum, başarısızlıklar, kaynak ve sınırlar.
- `docs/LEGACY_V02_REPORT.md`: eski sürümün tarihsel raporu, yeni sonuç olarak okunmamalı.

## Başlıca sonuçlar

87 birim testi geçti. Eski 85 sözleşme durumu korunuyor. Yeni 15 tasarlanmış uç durumda eski v0.2 3/15, v0.3 15/15 verdi. Bu kümeler birim testleriyle örtüşür; toplanıp bağımsız test sayısı yapılmaz.

Gerçek puan testinde eğitim/doğrulama/test: 757/101/303. Test MAE: genel ortalama 0,6713; restoran ortalaması 0,6648; kişisel ortalama 0,5108; kullanıcı+restoran modeli 0,5138; komşuluk modeli 0,5491. **Düşük MAE daha iyidir, yüzde doğruluk değildir.** Doğrulamada seçilen komşuluk modeli testte güçlü basit yöntemlerden kötü çıktı; sonuç saklanmadı ve model otomatik olarak üretime alınmadı.

Kişisel ortalama aynı kullanıcıdaki restoranları sıralamaz; yalnız kişinin puan verme eğilimini tahmin eder. Sıralama üstünlüğü ve İstanbul kullanıcı faydası kanıtlanmadı.

## Veriyi değiştirmek ve deney yapmak

`examples/` dosyalarında tarih, bütçe, mesafe, `open_now`, `quiet` (kalabalık sinyali), `mode` ve bildirim izinlerini değiştirebilirsiniz. Tarihler açık ve sabittir; eski kaynaklar bugün geçerli sayılmaz.

`play_preferences.py`, belirlenen kullanıcı için üç saklı tarihsel puanı ve modelin tahminini ayrı gösterir. Gerçek puanlar modele eğitim sırasında verilmez. Bu ekran bugünkü restoran tavsiyesi değildir.

Kendi araştırma modeliniz için `PreferenceModel` arayüzüne yeni bir yöntem ekleyin; test bölümüne göre parametre ayarlamayın. Aynı veride defalarca geliştirme yaptıktan sonra bağımsız yeni test verisi gerekir. `benchmarks/preference_protocol.json` değişirse deney sürümünü de değiştirin.

## Sınırlar

Yeni canlı İstanbul verisi alınmadı. Eski 16 İzmir etkinliği + 7 İstanbul mekânı aynı kalır. UCI restoranları bu yerlerle eşleştirilmez. Gerçek MiMo/Laya çağrısı, mobil uygulama, doğrudan gözlenmiş kalabalık, AR-GE/bandit/RecPIE replikasyonu veya kullanıcıya gerçek öneri deneyi yoktur.

`model_boundary` yalnız yapılandırılmış alanları doğrular; serbest açıklamaların tamamının doğru olduğunu kanıtlamaz. Araştırma skorları kanıt ve kullanıcı kısıtlarının üstüne çıkamaz. Tam üretim servisi güvenlik, yük, izin ve gerçek entegrasyon testleri gerektirir.

Kaynak ve atıflar `DATA_LICENSES.md`, `data/manifest.json`, `data/uci_manifest.json` içinde. Yerel veri kaynağı baytları iki açık GitHub aynasının Git blob SHA-1 değeriyle doğrulanmıştır; bu ortamda UCI ZIP'i doğrudan alınamadı.

## Tekrarlanabilirlik ve üretilen çıktılar

`python3 run_all.py`, git dışı `results/` klasörüne SQLite ve JSON deney çıktılarını yeniden üretir. Üretilen veritabanı/loglar commit edilmez. UCI ham CSV'nin yerel dosya özeti deneyde kontrol edilir. Kaynak fixture dosyalarının atıfları `DATA_LICENSES.md` içerisindedir.

## KEP-SRC-001 (v0.4 araştırma eklemesi)

`python3 scripts/poll_source.py --list` kayıtları gösterir. İstanbul kaynaklarının tamamı izin incelemesinde `pending` durumundadır. İzmir açık verisi yalnız `research_ingest` için onaylıdır; `--fetch` işlemi ayrıca açıkça talep edilmelidir. Bu işlem bir araştırma snapshotı üretir, **canlı etkinlik doğrulaması veya tüketici yayını yapmaz**. Detay için `sources/README.md`.

### EVAL-002 · Browser Scout research (read-only)

The optional Haiku 5.5 browser pilot is NOT used in CI or in the consumer app. The deterministic and hand-authored browser-replay test can be run offline:

```bash
python -m benchmarks.scout_eval
python scripts/haiku_browser_scout.py --source zorlu_psm_events
```

See [SCOUT_BETA_EVAL.md](docs/SCOUT_BETA_EVAL.md) and [ADR-0003](../../docs/adr/0003-read-only-browser-scout-experiment.md). Hand-authored replay is not actual model performance. No Istanbul website is currently approved for automated browser collection.

## KEP-SCI-001 · Scientific Evidence Value Lab

Yerelde `python scripts/research_intelligence.py` (gerçek kayıtların eksik alanları + ayrı **sentetik** örnek), `python -m benchmarks.evidence_value` (12.000 tamamen sentetik vaka, karar değerine göre araştırma ve sabit baseline karşılaştırması), `python -m unittest discover -s tests -q` (regresyonlar) çalıştırılabilir. [Deney raporu](docs/SCIENCE_VALUE_LAB.md). Bu Bayes sayıları gerçek İstanbul olasılığı değildir; Core'un üretim doğrulama/izin kapılarına bağlanmamıştır.

## KEP-SCI-002 · Historical claim calibration (research only)

`python -m benchmarks.calibration_eval` runs deterministic synthetic source-drift experiments using **separate train/calibration/test time periods**. `kepcore/calibration.py` estimates field+publisher-root correctness from dated, independently reviewed outcomes and reports Brier, ECE, risk–coverage and source changes. This is **not** a trained MiMo/Laya calibration model, a verified Istanbul source audit or an automatic publication gate.

For rights-reviewed human labels, see [`docs/CALIBRATION_REVIEW_PROTOCOL.md`](docs/CALIBRATION_REVIEW_PROTOCOL.md) and [`docs/adr/0005-temporal-evidence-calibration.md`](../../docs/adr/0005-temporal-evidence-calibration.md). `python scripts/calibrate_source_confidence.py --help` documents the opt-in, fully offline JSONL evaluation. Do not commit non-public reviewer files.

## SCI-002B · Human review intake (research-only)

Before attempting real source reliability calibration, independently adjudicate the selected field claims with `kepcore/review_intake.py`. Critical `starts_at`, `venue`, `cancelled` fields require two distinct human review ballots; disagreements need a third reviewer. The offline CLI accepts historical snapshots only with valid SHA-256 bytes and registered `research_ingest` rights at **export** time. No production confidence score, source authorization, publish or notification action follows. See [`docs/REVIEW_INTAKE_PROTOCOL.md`](docs/REVIEW_INTAKE_PROTOCOL.md).

```bash
python scripts/intake_human_reviews.py --help
```

All examples in CI are **synthetic mock review records**, not real human labels or an Istanbul calibration set.

## KEP-SCI-003 · Randomized source audit (research only)

Targeted verification is excellent for **finding mistakes**, but cannot estimate the error rate of **all observations** without correcting review selection bias. `kepcore/audit_sampling.py` now separates a frozen, rights-checked, stratified-random audit from the targeted SCI-001/SCI-002B queue. The audit log contains each stratum size, inclusion probability, SHA-256 population hash and a secret-seed commitment; replay verifies that the sample was not changed after labels were observed. Any missing or late label gives **no estimated population error rate**. The completed sample uses stratum weights and a conservative finite-population Hoeffding band; it is not a guarantee under reviewer error or future source drift.

```bash
python -m benchmarks.audit_bias_eval         # 1,000 SYNTHETIC claims, 40 SRS trials; offline
python scripts/audit_source_reliability.py --help  # No live source access
```

See [RANDOM_AUDIT_PROTOCOL.md](docs/RANDOM_AUDIT_PROTOCOL.md) and [ADR-0007](../../docs/adr/0007-random-audit-vs-targeted-verification.md). Real Istanbul human adjudications are **not** available and `Issue #9` remains open. No model tokens or browser traffic are incurred.

## KEP-DATA-001 · Overture Places v2 research adapter

`python -m benchmarks.overture_places_eval` is a five-record **synthetic fixture** that tests the new September-2026 schema, coordinate integrity, missing categories, record identity and unmerged possible duplicates. `python scripts/overture_istanbul.py` is offline by default. [Pilot protocol](docs/OVERTURE_PLACES_PILOT.md) and [ADR-0008](../../docs/adr/0008-overture-pinned-places-pilot.md) document the exact `2026-09-23.1` release, separate manual GitHub retrieval, licensing and uncertainty rules. An Overture importer is not an Istanbul live events feed.

## KEP-DATA-002 · Source manifest integrity and unbiased POI existence survey

`kepcore/overture_audit.py` checks internally consistent, pinned Overture minimal artifacts, and creates a frozen randomized survey stratified by sample cell and Overture existence score. `scripts/verify_overture_pilot.py` runs offline and never changes Core or consumer records. The manual Overture workflow validates its artifact before upload. `python -m benchmarks.overture_audit_eval` shows **synthetic** sampling bias effects; `tests/test_overture_audit.py` covers corruption, missing reviewers and future dates. See [OVERTURE_EXISTENCE_AUDIT.md](docs/OVERTURE_EXISTENCE_AUDIT.md).

A passing artifact test **does not authenticate Overture upstream**: hashes within an untrusted supplied manifest can be forged. Two reviewer IDs **do not authenticate real reviewer independence**. That paragraph documents the state at DATA-002 release time. DATA-003 now archives 4,803 **real Overture records**, without ground-truth labels; Issue #13 remains open for physical verification.

## KEP-DATA-003 · Pinned real Istanbul Places replay

The GitHub Actions Overture download **succeeded** on 2026-10-11 Istanbul time, with
4,803 real source records from two very small sample cells. The source-derived minimal
archive is now committed as deterministic gzip with a separately pinned original
manifest and acquisition metadata. This is **real source data, not verified business reality**.

```bash
python scripts/real_overture_replay.py
python -m unittest tests.test_overture_real -v
# A real survey sample requires a private seed kept OFF GitHub and two human reviews per POI:
python scripts/real_overture_replay.py --audit-seed-file .local/private_seed.txt \
    --audit-output .local/real-audit-output --audit-budget 60 \
    --sampled-at 2026-10-11T03:00:00+03:00
```

The default replay makes no network calls and reads no secrets. Audits do not
assign existence labels; all rows begin `UNREVIEWED`.
Source and sampling caveats: [OVERTURE_REAL_FIRST_RESULTS.md](docs/OVERTURE_REAL_FIRST_RESULTS.md).

## KEP-DATA-004: Çift kör insan denetimi alımı

- `kepcore/overture_field_review.py`: mevcut 60-POI örnekleme planını özel seed ile yeniden doğrular, saha Excel dosyalarını (`.xlsx`) standard kütüphaneyle okur, adı/adresi/koordinatı/harita linkini sabitler ve iki insan değerlendirmesi eksikse hata oranını üretmez.
- `scripts/intake_overture_field_workbooks.py`: ağsız, model anahtarsız, üretimden ayrılmış komut satırı.
- `docs/OVERTURE_FIELD_AUDIT_INTAKE.md`: değerlendirme protokolü ve kritik **±51,8 yüzde puan** muhafazakâr yarıçap uyarısı.
- Bağımsız insan sonucu henüz sıfır; testler sentetik oyları kullanır, gerçek saha sonuçları değildir.

## KEP-DATA-005 · Blind third human review + new holdout size

`kepcore/overture_adjudication.py` handles **only binary physical-existence** disputes between two independently completed worksheets. It emits a C-review template without A/B verdicts, binds any completed third decision to a SHA-256 commitment to the original ballots, and leaves the weighted error estimate unset if any selected record is missing, unknown, or not explicitly adjudicated. Reviewer data and the sampling seed remain **off-repo**. The same module estimates human workload and conservative precision for a NEW sampling frame of the remaining **4,743** POIs, without drawing a new sample or asserting field accuracy.

Instructions: [third-review and holdout protocol](docs/OVERTURE_THIRD_REVIEW_AND_HOLDOUT.md).
Offline check: `python -m unittest tests.test_overture_adjudication -q`; CLI: `python scripts/adjudicate_overture_field.py --help`. No paid API, browser or push actions.

## KEP-DATA-006 · Time-aware source-record delta (NOT business closure)

`kepcore/overture_delta.py` compares two versioned, schema-compatible and SHA-pinned minimalist Overture research snapshots. IDs added/removed, field edits, coordinate changes, missingness and source/confidence changes are distinct. Possible ID replacements are **human-review-only**, never auto-merged. `scripts/overture_release_delta.py` defaults to a test where **the 4,803 records are genuine September data, and October edits are entirely synthetic**. No real second release or real-world closures have been observed.

```bash
python -m unittest tests.test_overture_delta -v
python -m benchmarks.overture_delta_eval
python scripts/overture_release_delta.py
```

See [OVERTURE_TEMPORAL_DIFF.md](docs/OVERTURE_TEMPORAL_DIFF.md) and [ADR-0013](../../docs/adr/0013-temporal-source-delta-and-identity.md) for the future separately reviewed download contract, licence and holdout expectations. This code does not enable the consumer catalogue or any background polling.

## KEP-DATA-011 · Gerçek sürümlerde kaynak puanı değişimi

`python scripts/overture_confidence_drift.py --august-zip .local/august-original.zip` sadece **orijinal SHA-pinned** Ağustos GitHub Actions ZIP'iyle çalışır; Eylül'ün repodaki sabit arşivini yeniden denetler. Tekil kayıt bilgisi içermeyen toplu rapor `reports/` altında; 60 adaylık **hedefli** inceleme kuyruğu yalnız `.local` altında yaratılır ve SCI-003 rastgele denetimiyle karıştırılmaz. [Protokol](docs/OVERTURE_CONFIDENCE_DRIFT.md).

## KEP-DATA-012 · Permanent two-release source replay

The exact August Actions research ZIP is preserved under `data/real/overture_istanbul_2026-08-19.0/`; source bytes and Git hashes are checked by `kepcore/overture_archive_artifact.py`.

```bash
python scripts/replay_pinned_august.py
python -m unittest tests.test_overture_durable_original -v
```

Source-record changes are NOT human-reviewed business events. [Protocol](docs/OVERTURE_DURABLE_AUGUST_REPLAY.md).

## KEP-DATA-013 · GERS source reconciliation and compatibility

[Offline replay and scientific boundaries](docs/GERS_RECONCILIATION.md). The two real archives are unchanged. Actual STAC evidence requires the intermediate `2026-09-23.0` release; the bounded official-event capture is incomplete, so no official membership agreement or business opening/closure accuracy is claimed. Run `python scripts/reconcile_gers_releases.py --check` from `labs/core`. Ordinary CI remains offline.

## KEP-DATA-016 · Cross-patch regional GERS event fingerprint

[Research evidence and boundaries](docs/GERS_PATCH_REGIONAL_EQUIVALENCE.md). The original September .0 and separately captured September .1 geographically selected added/removed GERS row sets have identical canonical fingerprints (218 added, 67 removed; 285 regional IDs), but this **does not** prove full Parquet equality, the patch changelog generation baseline, all-ID agreement or physical business events. The exact original aggregate receipts are SHA-256 pinned. Replay without network: `python scripts/review_gers_patch.py --check`.

## KEP-FIELD-001 | 60 genuine Istanbul source records, private blind field review

The next bottleneck is **real-world validity**, not source-byte optimization. We have frozen a NEW random 60-place source sample, with secret seed/individual review sheets kept outside GitHub, and preregistered the naive-assert versus KEP-abstain claim-coverage comparison. **Actual independent human labels: 0**. No citywide or business-change accuracy claim.

```bash
cd labs/core
python scripts/evaluate_field_pilot.py --protocol
python -m unittest tests.test_field_pilot tests.test_field_prereg_real -v
```

The original DATA-003/004/005 blinded-sample and third-review engine is reused unchanged. The first 60 reviews are a process pilot: the existing conservative nominal 95% Hoeffding design half-width is about **51.75 percentage points**, not a measured error rate. A proper prospective change-prediction holdout is a separate future experiment. See [field pilot protocol](docs/REAL_FIELD_PILOT_001.md) and [ADR-0024](../../docs/adr/0024-real-field-pilot-evaluation.md). Neither private seed, reviewer workbooks, real case IDs nor field evidence are tracked in Git.

## KEP-CORE-001 | Sentetik şehir, zaman-duyarlı karar çekirdeği

**Yeni gerçek veri arama veya indirme yok.** Eldeki donmuş arşivleri değiştirmeden Core'un kaynak, hak ve belirsizlik kurallarını tek bir sentetik end-to-end karar akışında test ediyoruz. Tek yayıncının kopyaları iki bağımsız gözlem sayılmaz. Henüz KEP'e ulaşmamış bir kaynak olayı geçmiş bir kararı etkileyemez. Core'un hak/fiyat/zaman kapıları hiçbir model veya kaynak eklemesiyle aşılamaz. Model adapter'a yalnız iki kapıdan da geçen laboratuvar adayları verilir. İki kaynak anlaşsa bile gerçek işletme varlığı kanıtlanmış sayılmaz.

Çevrimdışı tekrar:

    cd labs/core
    python -m unittest tests.test_temporal_pipeline tests.test_temporal_core_eval -v
    python -m benchmarks.temporal_core_eval

Beş önceden belirlenmiş tamamen sentetik rejimde 3.000 örnek, beş politika, gizli sentetik gerçekler ve dürüst kapsam / yanlış olumlu / karar faydası karşılaştırması bulunur. Sonuçlar gerçek İstanbul işletme doğruluğu veya ticari üstünlük değildir; kaynak kalitesinin bozulduğu senaryolar başarısızlıkları da göstermelidir. [Metodoloji](docs/TEMPORAL_SYNTHETIC_KERNEL.md), [ADR-0025](../../docs/adr/0025-temporal-evidence-kernel.md). Önceki FIELD-001 saha kohortu ayrı, etiket bekleyen ve değişmemiştir.


## KEP-CORE-002 | Sanal sensörlerin bilgi değeri ve karar bütçesi

**Yeni gerçek veri toplama yok.** CORE-001'in zaman-duyarlı kaynak doğrulamasını ve SCI-001'in varsayımsal bilgi-değeri hesabını birleştiren, sadece araştırma amaçlı bir doğrulama **öneri** motoru. Core hak/fiyat/zaman kararlarını aşamaz; tek kaynaktan kopya gelen tekrarları doğrulama olarak saymaz; maliyet bütçesi ve cevap süresini aşan isteği önermez. Öneri otomatik olarak sensör çağrısı yapmaz; nihai karar yine LAB düzeyindedir.

Çevrimdışı:

    cd labs/core
    python -m unittest tests.test_budgeted_verify tests.test_budgeted_core_eval -v
    python -m benchmarks.budgeted_core_eval

Altı tamamen sentetik rejimde 2.400 örnek, beş önceden belirlenmiş maliyet/karar yöntemi, gizli sentetik doğru yanıtlar ve eşlenik senaryolarda karar faydası, yanlış olumlu, kaynak kontrol maliyeti ve kaçan fırsatlar raporlanır. Bu ölçüler gerçek İstanbul kaynağı doğruluğu, model performansı veya API maliyet tasarrufu değildir. [Protokol](docs/CORE_002_BUDGETED_EVIDENCE.md) ve [ADR-0026](../../docs/adr/0026-one-step-budgeted-evidence.md).


## KEP-CORE-003 | Sanal tarihsel kaynak güveni ve belirsizlik

Yeni gerçek veri aramıyoruz. CORE-002'nin sentetik dünyasında güvenilir sandığımız kaynakların kalite kaybını, sadece daha önce tamamlanmış **bağımsız sanal denetimlerden** öğreniyoruz. Kaynağın duyarlılığı/özgüllüğü ayrı tutulur; geç sonuçlanan bir etiket geçmiş kararı değiştiremez. Yetersiz denetim ve zayıf alt-güven sınırı yeni sorgu önerisini durdurur. Kullanıcı yayını, gerçek doğruluk, otomatik web araması veya üretim kapısı YOK.

    cd labs/core
    python -m unittest tests.test_adaptive_trust tests.test_adaptive_trust_eval -v
    python -m benchmarks.adaptive_trust_eval

Altı önceden sabitlenmiş tamamen sentetik kaynak kalitesi/kayıp/ortak-rumor rejiminde, bağımsız denetim gecikmesi ve kaçırılan doğru fırsatlar dâhil bütçe/fayda sonuçları karşılaştırılır. [Araştırma protokolü](docs/CORE_003_TEMPORAL_TRUST.md), [ADR-0027](../../docs/adr/0027-causal-synthetic-source-calibration.md).
