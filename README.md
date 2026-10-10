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
