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
