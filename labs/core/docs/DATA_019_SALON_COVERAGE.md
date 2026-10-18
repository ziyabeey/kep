# KEP-DATA-019 · Faz 0: Overture salon kapsamı (Kadıköy)

Durum: **Overture tarafı çekildi, Randevu listesi bekleniyor. Kapsam (Z) henüz hesaplanmadı.**

Soru: Randevu'yu kullanan salonların ne kadarı Overture Places'te bulunuyor? Faz 1 haritası (Kep salonu = açık kepenk, diğerleri = kapalı kepenk) yalnız Overture ile kurulabilir mi?

## Ön kayıt

- Protokol: [`benchmarks/salon_coverage_protocol.json`](../benchmarks/salon_coverage_protocol.json), commit `660151c79fbe37ab5ff5aa33b063e328f292d164`, SHA-256 `e4b0727a…ae99`. Eşleştirici koddan önce, hiçbir İstanbul kaydı sayılmadan ve Randevu listesi görülmeden girdi.
- Kapı: Z ≥ %70 ve Wilson alt sınırı ≥ %50 → Faz 1. Z < %50 → ilçe ya da sektör değişir. Arası → ikinci ilçeyle yeni protokol. 15'ten az uygun Randevu salonu → karar yok.
- Eşleşme: telefon, ya da isim benzerliği ≥ 0,80 ve 150 m (yalnız elle girilmiş konum), konum yoksa isim + aynı sokak. Birebir atama.
- Google kaynaklı Randevu koordinatları (`places`, `google`) ana metrikte okunmaz.

## Overture tarafı (Randevu'dan bağımsız, betimleyici)

Sürüm `2026-09-23.1` (18 Ekim'de S3'teki en yeni; `2026-10-21.0` henüz yok). Kadıköy sınırı Overture `division_area` `f1be975f-ba35-4e17-9ce4-ecfbdd2524a0` (county, TR-34). Ham çıkarım: İstanbul'un 39 ilçesinde 410.736 kayıt, SHA-256 `44b4158e…49c8`, kod commit'i `66ff3047`; dosya yalnız `.local/data019/` altında.

| Kadıköy salon hunisi | Kayıt |
|---|---|
| Poligondaki salon kategorili kayıt | 844 |
| `operating_status` kapalı olmayan | 844 |
| confidence ≥ 0,70 | 568 |
| Son kaynak güncellemesi ≥ 2025-09-23 (Y_universe) | 568 |

Kategoriler: beauty_salon 419, hair_salon 200, barber 127, nail_salon 71, diğer 27. Kaynak: 786 Meta, 57 Foursquare, 1 Microsoft. 767 kayıtta telefon, 764 kayıtta adres metni var.

Gözlem: bu sürümde İstanbul salonlarında `operating_status` hep boş ve bütün `update_time` değerleri 2026. Yani "taze olmayanı ayıkla" adımında fiilen yalnız confidence eşiği iş görüyor; güncelleme tarihi kapanmış dükkânı ayırt etmiyor. Confidence de doğrulama değildir.

Bu sayılar İstanbul'daki gerçek salon sayısı değildir; Overture'ün listelediği kayıt sayısıdır.

## Sonraki adım

```bash
cd labs/core
python3 scripts/salon_coverage.py match --randevu .local/data019/randevu_salons.csv \
  --extract .local/data019/overture_istanbul_places_2026-09-23.1.jsonl.gz
```

Rapor `coverage_report.json` olarak yazılır ve bu belgeye toplu sayılar eklenir. Salon adları ve eşleşme tablosu repoya girmez.

## Sınırlar

- Randevu salonları İstanbul'daki salonların rastgele örneği değil; Randevu'yu seçen salonlar daha dijital olabilir, bu da kapsamı yukarı çekebilir.
- Telefon eşleşmesi güçlü ama Meta kaynaklı telefonlar eski olabilir; isim eşleşmesi eşik ve genel kelime listesine duyarlı.
- Protokol, eşleştirici ve çıkarım aynı oturumda yazıldı. CLAUDE.md gereği birleştirmeden önce başka bir oturumdan denetim gerekiyor.
