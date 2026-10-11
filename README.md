# KEP

**Etrafında ne oluyor?**

KEP, etkinlik, yemek, mekân ve yerel hizmet keşfi için araştırma aşamasındaki **native iOS/Android uygulama** fikridir. Kullanıcı sohbeti MiMo, veriler ve kanıtlar KEP Core, onaylı veri kaynakları Radar, değerlendirmeler LAB şeklinde planlanmaktadır. Bu depo **şu an bir mobil uygulama veya çalışan çevrim içi servis içermiyor**.

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
