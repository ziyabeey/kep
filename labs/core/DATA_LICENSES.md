# Veri kökeni, atıflar ve kullanım sınırları

Bu paket farklı lisanslı ve farklı kanıt seviyesindeki küçük örnekleri birlikte bulundurur; tek bir veri lisansı varmış gibi yayımlanmamalıdır. Kodun ve verinin kapsamı ayrıdır.

## İzmir Büyükşehir Belediyesi

Kaynak: https://openapi.izmir.bel.tr/api/ibb/kultursanat/etkinlikler
Katalog: https://acikveri.bizizmir.com/tr/dataset/kultur-sanat-etkinlikleri
Lisans bildirimi: https://acikveri.bizizmir.com/tr/license
Lisans: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
Atıf: İzmir Büyükşehir Belediyesi Açık Veri Portalı.

Bu çalışma seçili olgusal alanları alır, tarihleri saat dilimli normalize eder ve kalite işaretleri ekler. Değişiklikler: alan seçimi, boşluk temizliği, şema dönüşümü, eşit başlangıç/bitişin bilinmeyen süre olarak işaretlenmesi. Afiş, video, görsel ve açıklama metinlerinin tamamı pakete alınmadı. Lisans sağlayıcısı doğruluk, süreklilik veya eksiksizlik garantisi vermez.

## Wikidata

Kaynaklar:
- https://www.wikidata.org/wiki/Q1463961 (İstanbul Modern)
- https://www.wikidata.org/wiki/Q91274 (Galata Kulesi)

Yapılandırılmış veri CC0 1.0: https://www.wikidata.org/wiki/Wikidata:Licensing
https://creativecommons.org/publicdomain/zero/1.0/
Atıf (gönüllü): Wikidata contributors.
Değişiklik: koordinatları derece/dakika/saniyeden ondalığa dönüştürme; Türkçe gösterim ve KEP sınıfı ekleme. Koordinatlar bağımsız saha ölçümü değildir.

## Wikipedia

Atıf: Wikipedia contributors. Kaynak sayfaların ilgili sürümleri/katkıcı geçmişleri kendi history bağlantılarından görülebilir.
- https://en.wikipedia.org/wiki/Pera_Museum
- https://en.wikipedia.org/wiki/Dolmabah%C3%A7e_Palace
- https://en.wikipedia.org/wiki/Y%C4%B1ld%C4%B1z_Park
- https://en.wikipedia.org/wiki/Sak%C4%B1p_Sabanc%C4%B1_Museum
- https://en.wikipedia.org/wiki/Rahmi_M._Ko%C3%A7_Museum

Kaynak içerik lisansı: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
Bu kaynaktan türetilen örnek satırlar CC BY-SA 4.0 kapsamında bırakılmıştır. Fotoğraf alınmadı. Seçilen ad/konum/kategori olgularının şeması değiştirilmiştir. Bu atıf tek başına kaydın güncel veya doğru olduğunu garanti etmez.

## Pera Müzesi: sınırlı olgusal araştırma notu, açık veri akışı değil

https://www.peramuseum.org/faq
İncelenen arama çıktısı: SSS yanıtında 300/150/200 TRY; alt bölümde 450/250/300 TRY. Ayrı açma aracındaki eski görüntü iki bölümde de eski tarifeyi gösterdi. Altı olgusal değer, 3 alan ve sayfa/alan işaretleri dışında metin ya da medya kopyalanmadı. Bu örnek bir canlı fiyat doğrulaması değildir; kurumdan scraping, toplu içerik kullanımı veya üretimde yeniden dağıtım izni alındığı iddia edilmez. `rights_scope` onaylı üretim kaynağı değildir. Fiyat değişimi mi, bölüm senkronizasyonu mu, önbellek farkı mı olduğunu canlı birincil veri olmadan çözemiyoruz.

## Overture

https://docs.overturemaps.org/getting-data/
https://docs.overturemaps.org/attribution/
Sadece gelecekteki indirme yöntemi verilmiştir. Overture verisi bu arşivde bulunmaz. İndirilecek sürümün kaynak bazlı lisanslarını ve atıflarını koruyun.

## Korunan edinim zinciri

- Erişim/derleme tarihi: 10 Ekim 2026.
- Toplu HTTP indirmesi bu çalışma ortamında başarısız.
- Dahil edilen veriler, gerçekten dönen araç çıktılarındaki seçili alanların transkripsiyonudur.
- Kaynak anlık görüntüsünün kesin zamanı bilinmiyor; erişim günü kaynak doğrulama zamanı yapılmadı.
- Her kaynak dosyasının yerel SHA-256 değeri `data/manifest.json` içinde.
- Yapay iptal, fiyat, izin ve zaman değişiklikleri sadece test kopyalarında; ham kaynak kayıtlarında değil.


## v0.3 ek veri: UCI Restaurant & consumer data

Medelln, R. & Serna, J. (2011). Restaurant & consumer data [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5DP41 . Lisans: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/ . Resmî sayfa: https://archive.ics.uci.edu/dataset/232/restaurant%2Bconsumer%2Bdata .

Yalnız `rating_final.csv` alınmıştır; ham dosyaya değişiklik yapılmamış, araç metninden iki GitHub aynasının baytlarıyla aynı olacak şekilde yeniden oluşturulmuştur. Model girdileri üç alana indirgenir, eğitim/test bölmeleri türetilmiş araştırma verisidir. Profil dosyaları alınmadı. Ayrıntılı aynalar ve hashler `data/uci_manifest.json` içinde. UCI ZIP'indeki baytlar bu ortamda doğrudan indirilerek teyit edilemedi.

UCI puanları mevcut İstanbul kültür mekânlarının puanları değildir. Bu paket hiçbir tarihsel çalışma saati veya fiyatı 2026 güncel gerçeği saymaz.
