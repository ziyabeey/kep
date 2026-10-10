# KEP

**Etrafında ne oluyor?**

KEP, etkinlik, yemek, mekân ve yerel hizmet keşfi için araştırma aşamasındaki **native iOS/Android uygulama** fikridir. Kullanıcı sohbeti MiMo, veriler ve kanıtlar KEP Core, onaylı veri kaynakları Radar, değerlendirmeler LAB şeklinde planlanmaktadır. Bu depo **şu an bir mobil uygulama veya çalışan çevrim içi servis içermiyor**.

## Geliştirmeye nereden başlayalım?

- [Çalışan KEP Core v0.3 araştırma laboratuvarı](labs/core/README.md)
- [Veri lisansları ve kökeni](labs/core/DATA_LICENSES.md)
- [Radar mimari taslağı](docs/architecture/KEP_RADAR_v1.md)
- [Black C'den ölçüm ilkeleri](docs/measurement/KEP_MEASUREMENT_v1.md)
- [İlk geçiş kararı](docs/adr/0001-initial-core-import.md)

### Yerelde çalıştır

Python 3.10+ gerektirir; testler için ücretli API veya gizli anahtar gerekmez.

```bash
cd labs/core
python3 -m unittest discover -s tests -v
python3 run_all.py
python3 query.py --query examples/galata_nearby.json
```

**Önemli:** Laboratuvarın 16 İzmir etkinliği ve 7 İstanbul mekânı canlı veri değildir; ayrıca tarihsel UCI restoran puanlarıyla test yapılır. Bu veriler İstanbul'da güncel öneri kalitesi, ziyaret veya rezervasyon sonucu ispatlamaz. MiMo/Laya gerçek API entegrasyonu henüz yoktur.

**Veri politikası:** Ticari otomatik veri toplama yalnız izinli kaynaklardan ve uygun kullanım şartlarıyla yapılmalıdır. Test fixture'ları üretim verisi sayılmaz.
