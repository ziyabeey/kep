# KEP-DATA-010: İki gerçek Overture sürümünü bağımsız tekrar hesaplama

**Kaynak verisi gerçek, işletme durumu doğrulanmış değil.** 2026-08-19.0 Overture Places v1.18 ile 2026-09-23.1 v2.0, Beşiktaş ve Karaköy'deki aynı iki küçük araştırma penceresidir. Mahallelerin tamamını temsil etmez.

Ağustos'un başarılı manuel GitHub koşusu [#38121005943](https://github.com/ziyabeey/kep/actions/runs/38121005943), artifact ID **11695042455**. Orijinal ZIP SHA-256:

`cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05`

Bu ZIP, GitHub Actions'ta yedi gün tutulur. Kaybolmadan ayrı erişim kontrollü araştırma alanına kaydedilmelidir. Bu PR **ZIP'in kendisini GitHub'a commit etmiyor**. Kullanıcı ZIP'i yerel olarak temin ettiğinde kod onu eşleşen SHA ile doğrulayıp kaynak kayıtlarını yeniden hesaplar:

```bash
cd labs/core
python scripts/verify_real_august_artifact.py --zip /path/to/kep-overture-august-2026-08-19.0.zip
python -m unittest tests.test_overture_archive_artifact -v
```

## Gözlenen kaynak farkı

| Ölçüm | Sonuç |
|---|---:|
| Ağustos kaydı | 4.650 |
| Eylül kaydı | 4.803 |
| Ortak ID | 4.581 |
| Yeni listelenen ID | 222 |
| Artık listelenmeyen ID | 69 |
| Confidence-only değişen ID | 3.337 |
| Diğer alan/konum değişen ID | 198 |
| Koordinatı değişen ID | 63 |
| Adı değişen ID | 42 |
| Adresi değişen ID | 122 |

Ağustos sürümü yayımlandığı tarihten daha geç, **11 Ekim'de**, Eylül sürümü ise **10 Ekim'de** indirilmiştir. Karşılaştırma **sürüm sırasına** göre yapılır. Orijinal ham Parquet bölümleri saklanmadı; SHA'lar içerik bütünlüğü sağlar, bağımsız kaynak imzası veya gerçek işletme varlığı doğrulamaz.

Eski kategorilerden yeni kategori şemasına otomatik eşdeğerlik atanmıyor. Ortadan kaybolan Overture ID, işletmenin kapandığı anlamına gelmez. Yeni ID, açılış anlamına gelmez. Confidence puanındaki değişiklik kullanıcıya bildirim sebebi sayılmaz.

Kaynak ve lisans: https://docs.overturemaps.org/attribution/
Referans: [Overture Ağustos sürümü](https://docs.overturemaps.org/blog/2026/08/19/release-notes/), [Eylül sürümü](https://docs.overturemaps.org/blog/2026/09/23/release-notes/).

**CI varsayılan çevrimdışıdır.** Gerçek ZIP dosyası CI'da bulunmadığından testler saf ayrım ve fail-closed davranışı denetler. Yerelde ZIP ile tam tekrar çalışma ayrıca yapılmıştır; gerçek fiziksel saha etiketleri henüz yoktur.
