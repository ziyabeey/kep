# KEP

**Etrafında ne oluyor?**

KEP, etkinlik, yemek, mekân ve yerel hizmet keşfi için araştırma aşamasındaki **native iOS/Android uygulama** fikridir. Kullanıcı sohbeti MiMo, veriler ve kanıtlar KEP Core, onaylı veri kaynakları Radar, değerlendirmeler LAB şeklinde planlanmaktadır. Bu depo **şu an bir mobil uygulama veya çalışan çevrim içi servis içermiyor**.

## Çekirdeğe bağlı yerel önizleme

Harita/kategori, yazılı keşif isteği, profil ve günlük plan hesabını tarayıcıda
incelemek için depo kökünde çalıştırın:

```bash
python3 -m apps.kep_preview.server
```

Ardından `http://127.0.0.1:4180/` adresini açın. [Önizleme rehberi](apps/kep_preview/README.md)
ve [ADR-0036](docs/adr/0036-connected-local-preview.md) kapsamı açıklar.
Keşif istekleri mevcut Python Core'a gider; güncel işletme, fiyat veya açık olma
iddiası üretilmez. Yazılı komutlar sınırlı bir ayrıştırıcıyla anlaşılır; gerçek
MiMo, ses veya canlı trafik bağlantısı yoktur. Gün planı yalnız kullanıcının girdiği yol
süreleriyle hesaplanır. Native ürün hedefi sürer.

Önizlemenin 2B İstanbul haritası için tarayıcı görünür alanın OSM görüntülerini
internetten yükler. Asıl 3B hedef, Kadıköy/Beyoğlu/Beşiktaş bina geometrisini
Kep'in kendi tasarımında kullanmaktır; [İBB 3B veri araştırması ve erişim
taslağı](docs/architecture/ISTANBUL_3D_DATA.md) doğrulananları ve eksik bilgileri
ayırır. İBB modeli henüz temin edilmedi.

## Geliştirmeye nereden başlayalım?

- [Çalışan KEP Core v0.3 araştırma laboratuvarı](labs/core/README.md)
- [Veri lisansları ve kökeni](labs/core/DATA_LICENSES.md)
- [Radar mimari taslağı](docs/architecture/KEP_RADAR_v1.md)
- [Black C'den ölçüm ilkeleri](docs/measurement/KEP_MEASUREMENT_v1.md)
- [İlk geçiş kararı](docs/adr/0001-initial-core-import.md)
- [KEP-SRC-001 kaynak kayıtları](labs/core/sources/README.md)
- [Kaynak yönetimi kararı](docs/adr/0002-source-registry-research-ingest.md)
- [Independent human review intake (SCI-002B)](labs/core/docs/REVIEW_INTAKE_PROTOCOL.md)

### Yerelde çalıştır

Python 3.10+ gerektirir; testler için ücretli API veya gizli anahtar gerekmez.

```bash
cd labs/core
python3 -m unittest discover -s tests -v
python3 run_all.py
python3 query.py --query examples/galata_nearby.json
python3 scripts/poll_source.py --list  # Ağ kullanmaz
```

**Önemli:** Laboratuvarın 16 İzmir etkinliği ve 7 İstanbul mekânı canlı veri değildir; ayrıca tarihsel UCI restoran puanlarıyla test yapılır. Bu veriler İstanbul'da güncel öneri kalitesi, ziyaret veya rezervasyon sonucu ispatlamaz. MiMo/Laya gerçek API entegrasyonu henüz yoktur.

**Veri politikası:** Ticari otomatik veri toplama yalnız izinli kaynaklardan ve uygun kullanım şartlarıyla yapılmalıdır. Test fixture'ları üretim verisi sayılmaz.

## EVAL-002 · Browser Scout araştırması

[Haiku 5.5 Browser Scout ADR](docs/adr/0003-read-only-browser-scout-experiment.md) ve [deney rehberi](labs/core/docs/SCOUT_BETA_EVAL.md) ile offline karşılaştırma kullanılabilir. Gerçek Haiku SDK bağlantısı **yalnız açıkça tetiklenen, izinli araştırma** için hazırlanmıştır; hiçbir canlı İstanbul sayfası veya ücretli API, CI'da çalışmaz.

## KEP-SCI-001 · Kanıtın beklenen karar değeri

[Kanonik bilimsel karar](docs/adr/0004-information-value-research-gate.md) ve [laboratuvar kullanım rehberi](labs/core/docs/SCIENCE_VALUE_LAB.md) ile artık KEP, **araştırma ortamında** hangi eksik olgunun yeniden araştırılmaya değer olduğunu sınayabiliyor. Sadece offline/sentetik Bayes testi; gerçek kalibrasyon, İstanbul saha doğruluğu veya otomatik yayın **yok**. CI iki Python sürümünde tekrar çalıştırır.

### Bilimsel kaynak kalibrasyonu (KEP-SCI-002)

`labs/core/kepcore/calibration.py` kaynak/alan güvenini geçmiş **tarihli ve gerçekten değerlendirilmiş** iddialarla sınamak için bir araştırma katmanıdır. Şu anda yalnız **sentetik** testlerin metodolojisi çalışır; gerçek İstanbul kaynaklarına ait bağımsız hakemli veri yoktur. `python -m benchmarks.calibration_eval` (çalışma dizini `labs/core`) ile tekrar edilebilir. Bu hesap otomatik yayın veya kullanıcı bildirimi oluşturamaz.

### KEP SCI-003: tarafsız kaynak kalite denetimi

Kanıt toplama ajanlarının **şüpheli kayıtları hedefli incelemesi**, kaynakların tümünün hata oranını ölçmekle aynı şey değildir. `labs/core/kepcore/audit_sampling.py`, izinli ve zaman damgalı gözlemlerden ayrı bir tabakalı rastgele denetim planı üretir; araştırma raporunu yalnızca tüm örneklem insan tarafından değerlendirildiyse hesaplar. Araştırma kodu ve testler için: [SCI-003 protokolü](labs/core/docs/RANDOM_AUDIT_PROTOCOL.md).

## KEP-DATA-001 · Overture Istanbul Places pilot (research-only)

[GeoJSON v2 import, SHA256 provenance and unbiased audit plan](labs/core/docs/OVERTURE_PLACES_PILOT.md). Offline CI exercises synthetic fixtures; **real Overture POI download is a separately and explicitly triggered GitHub Actions workflow**. No data is displayed to consumers.

## KEP-DATA-002 · Overture snapshot integrity + existence audit

[Research audit protocol](labs/core/docs/OVERTURE_EXISTENCE_AUDIT.md) adds post-download artifact checks, preregistered confidence-band random sampling, private seed replay and a complete dual-human-reviewed estimator. GitHub CI uses synthetic fixtures; **no real Istanbul field labels or verified POIs** are claimed. The source download remains separately/manual-only.

## İlk gerçek İstanbul Overture mekân arşivi (KEP-DATA-003)

Manuel Overture iş akışı **başarıyla çalıştı** ([run #38096227796](https://github.com/ziyabeey/kep/actions/runs/38096227796)).
`labs/core/data/real/overture_istanbul_2026-09-23.1/` altında **4.803 gerçek Overture kaydının**
küçültülmüş, sıkıştırılmış ve SHA-256 ile sabitlenmiş araştırma kopyası bulunuyor.
Beşiktaş merkezindeki küçük hücrede 1.872, Karaköy çevresindekinde 2.931 kayıt var.
`python3 labs/core/scripts/real_overture_replay.py` çıktısı açıklayıcı veri kalitesi özetidir.
Bu kayıtlar **sahada doğrulanmış işletmeler değildir**; `consumer_display_approved=false`, canlı
açılış/etkinlik/ücret bilgisi yoktur. Kaynak başına atıf ve [deney raporu](labs/core/docs/OVERTURE_REAL_FIRST_RESULTS.md) geçerlidir.

## KEP-DATA-004 · Kör saha denetimi Excel içe aktarma

`labs/core/kepcore/overture_field_review.py` iki ayrı insanın 60 gerçek Overture POI'si için hazırlanan Excel dosyalarını **çevrimdışı** doğrular. Örneklem ve görünen kaynak iddiaları değiştirilemez; boş, çelişkili veya sonradan girilen cevaplarla kaynak hata oranı yayımlanmaz. Çalıştırma: [saha veri protokolü](labs/core/docs/OVERTURE_FIELD_AUDIT_INTAKE.md). 60 örneğin %95 muhafazakâr hata aralığı yarıçapı yaklaşık **±51,8 yüzde puandır**; gerçek saha doğruluğu hâlâ ölçülmemiştir.

## KEP-DATA-006 · Overture sürümleri arasında değişim zekâsı

[Zamansal POI karşılaştırma protokolü](labs/core/docs/OVERTURE_TEMPORAL_DIFF.md) ve [ADR-0013](docs/adr/0013-temporal-source-delta-and-identity.md): bir sonraki harita veri sürümünde eklenen, listeden çıkan, sınıflandırması veya koordinatı değişen kayıtları ayrı işle. **Listeden çıkması işletmenin kapandığını kanıtlamaz.** Bugünkü offline örnek 4.803 gerçek Eylül kaydı + **sentetik sonraki sürüm** kullanır; gerçek Ekim değişim sonucu henüz yoktur.

```bash
cd labs/core
python -m benchmarks.overture_delta_eval
python scripts/overture_release_delta.py
```

### KEP-DATA-011 · Gerçek Overture kaynak güven puanı değişimi

Ağustos/Eylül 2026 Overture kaydı üzerine iki-sürümlü, ağsız araştırma tanısı ve **rastgele olmayan** hedefli inceleme kuyruğu: [çalışma rehberi](labs/core/docs/OVERTURE_CONFIDENCE_DRIFT.md). Güven puanı değişimi işletme varlığının doğrulanması anlamına gelmez.

## KEP-DATA-012 · Real August preservation beyond artifact retention

The exact [August 2026 historical research ZIP](labs/core/data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip) is now pinned in Git. [Reproduce the two real Overture release comparison offline](labs/core/docs/OVERTURE_DURABLE_AUGUST_REPLAY.md): `cd labs/core && python scripts/replay_pinned_august.py`. No transient GitHub artifact or network is required. These are *source* changes, not verified business openings/closures.

## KEP-DATA-013 · GERS source reconciliation and compatibility

[Offline replay and scientific boundaries](labs/core/docs/GERS_RECONCILIATION.md). The two real archives are unchanged. Actual STAC evidence requires the intermediate `2026-09-23.0` release; the bounded official-event capture is incomplete, so no official membership agreement or business opening/closure accuracy is claimed. Run `python scripts/reconcile_gers_releases.py --check` from `labs/core`. Ordinary CI remains offline.
