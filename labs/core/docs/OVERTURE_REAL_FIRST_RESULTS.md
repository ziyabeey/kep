# KEP-DATA-003 · 4.803 gerçek İstanbul POI'sinde ilk çevrimdışı kalite deneyi

**Veri türü:** GERÇEK Overture kaynak kaydı, fakat henüz **gerçeklik etiketi olmayan** alanlar.  
**Alım:** GitHub Actions [run #38096227796](https://github.com/ziyabeey/kep/actions/runs/38096227796),
2026-10-10T23:47:38.503435Z.  
**Sürüm:** `2026-09-23.1` / Places v2.0.  
**Pencere:** Beşiktaş merkezi `[29.0020,41.0400,29.0100,41.0455]`,
Karaköy çevresi `[28.9700,41.0200,28.9810,41.0275]`. İlçe sınırları DEĞİLDİR.

## Gerçek kaynak dağılımı

| Ölçü | Sonuç |
|---|---:|
| İşlenmiş ham satır | 4.806 |
| Kabul edilen POI | **4.803** |
| Beşiktaş merkez hücresi | 1.872 |
| Karaköy çevre hücresi | 2.931 |
| Kutunun dışında kalan satır | 3 |
| Adres değeri eksik | 422 (yaklaşık %8,8) |
| Temel taksonomi eksik | 131 (yaklaşık %2,7) |
| Adı eksik | 0 |
| Muhafazakâr olası mükerrer çift | 3 (tam kapsamlı duplicate sayısı DEĞİL) |
| Overture güven puanı: düşük / orta / yüksek | 1.115 / 1.809 / 1.879 |
| Teyit edilmiş fiziksel işletme veya açık olma | **0** |

En büyük temel kategoriler: `restaurant` 548, `hardware_home_and_garden_store`
361, `fashion_and_apparel_store` 220, `cafe` 214, `professional_service`
211, `electronics_store` 173, `hotel` 173, `coffee_shop` 147.
Bu rakamlar **kayıt sayısıdır**, hizmette bulunan işletme sayısı veya
ziyaret/etkileşim oranı değildir.

## Kaynakların kökeni

Aynı kayıtta birden çok kaynak bulunabilir; bu yüzden aşağıdaki katkı
sayılarının toplamı 4.803 etmeyebilir: `overture` 4.803, `meta` 4.381,
`foursquare` 292, `alltheplaces` 71, `microsoft` 59. Lisanslar satırdaki
`source_provenance` ile ilişkilidir; rapordaki özet bir lisans denetiminin
yerini tutmaz. Referans: https://docs.overturemaps.org/attribution/

## Kanıt zinciri ve eksikler

- GitHub artifact ZIP SHA-256: `f4f8efa7cd1b25856a855ee8271a4e10330179e2afddc77a7764afd173ed9dff`.
- Çıkarılan JSON SHA-256: `700be7afce6ecf024dbb10c7d340962fcc4a1705fb4e8a000c54ed60a0d37848`.
- Örneklem nüfusu SHA-256: `26f93817e44e9e94062bcecb26dc60b47e5a6e0e18f8af6a62a6c5f52e010123`.
- Yüklemeyi yapan CLI versiyonu `1.0.2`; STAC digest çekim öncesi ve sonrası aynı.
- **Ham Overture GeoJSON'ları arşivlenmediği için** o dosyaların bildirilen
  hash'leri burada yeniden hesaplanamıyor. Böylece kaynak gerçekliğini imzalayan
  bağımsız zincirimiz henüz eksik.
- İstanbul hücresindeki koordinatlar idarî mahalle sınırları değildir.
  Değişik `locality` değerleri bunun bir işaretidir, sahadaki yanlış konum sayısı değildir.
- `open_now`, etkinlik, canlı fiyat, gerçek güncel adres ve kalabalıklık doğrulanmadı.

## Çalıştır

```bash
cd labs/core
python scripts/real_overture_replay.py
python -m unittest tests.test_overture_real -v
```

Bu kod gerçek 4.803 POI ile veri kalitesini raporlar. **Saha doğruluğu
ölçümü değildir.** Sonraki aşama gerçek 60 öğelik tabakalı rastgele örnek
olup iki insan değerlendiricinin çalışmasını gerektirir. Hazırlanmış rastgele
denetim örnekleminin sonuçları henüz yoktur; kullanıcı yayın kapısı kapalıdır.
