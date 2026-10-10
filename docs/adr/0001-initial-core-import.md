# ADR-0001: KEP Core araştırma laboratuvarını ayrı dizine al

**Durum:** Önerilen (PR incelemesine açık)  
**Tarih:** 2026-10-10

## Bağlam
KEP yalnız native tüketici ürünü olarak planlanıyor; henüz mobil uygulama geliştirilmedi. v0.3 çevrimdışı, Python standard-kütüphane tabanlı test laboratuvarı. Kullanıcı mevcut araştırmanın `ziyabeey/kep` deposunda sürmesini istiyor.

## Karar
Araştırma kodunu `labs/core/` altında, canlı uygulama kodundan ayrı tut. Yerel SQLite ve üretilen sonuçları git dışında bırak. Ham ve seçili gerçek kayıtları kaynak/lisans ile tut. Mevcut 87 unittest ve deney protokolünü her PR'da CI ile çalıştır.

### Bilerek kapsam dışında
- React Native/Expo uygulaması, kullanıcı kaydı, servis deployment'ı
- Gerçek MiMo/Laya bağlantısı veya üretim erişim anahtarı
- Canlı İstanbul etkinlik verisi, sosyal medya scraping
- Model başarısı/kullanıcı memnuniyeti üstünlüğü iddiası

## Sonraki sınanabilir adımlar
1. Kaynak kayıt/izin politikası ve ilk izinli İstanbul kaynakları.
2. Aynı girişle temel sistem, MiMo ve KEP-Core-MiMo performans karşılaştırması.
3. Çekirdeğin doğruluk/güncellik/abonelik sınırları ve native istemci sözleşmesi.
4. Test başarısı ölçütlerini teknik sözleşme ile kullanıcı değeri olarak ayrı raporla.

## Geri dönüş
Bu bir araştırma modülüdür; ana uygulamaya migration yapmıyor. PR kapanırsa üretim sistemine etkisi yoktur.
