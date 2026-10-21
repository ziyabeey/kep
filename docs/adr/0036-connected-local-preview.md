# ADR-0036 · Mevcut Core'a bağlı yerel kullanıcı akışı

**Tarih:** 20 Ekim 2026

**Durum:** Özellik dalında uygulanmış, inceleme bekliyor

**Kapsam:** Araştırma çekirdeğini kullanıcı etkileşimleriyle birleştiren yerel geliştirme önizlemesi

## İhtiyaç

Mevcut depo aday seçimi, alan güncelliği, kaynak hakları ve model çıktı sınırını
test ediyor; kullanıcı bu kuralları bir harita/keşif akışında deneyemiyordu.
20 Ekim konuşmasında kullanıcı renk/kategori haritaları, Kep kutusu/profil
hareketleri ve saatli günlük planı tarif etti; mevcut repo karşılaştırmasından
sonra geliştirmeye devam edilmesini istedi.

## Karar

1. `apps/kep_preview` altında bağımlılıksız, yerel HTTP adapter'ı ve tarayıcı
   arayüzü ekle. Yer sorguları Python referans `load_catalog` + `decide`
   üzerinden çalışır. Rust portunun mevcut PR zinciri ayrı kalır.
2. Native iOS/Android hedefi korunur. Tarayıcı önizlemesi yeni üretim platformu
   seçimi veya genel internete dağıtım kararı değildir.
3. Başlangıçta mevcut İstanbul örnekleri kullanılır. Overture arşivleri ve
   donmuş protokoller değişmez; hiçbir kaynağa tüketici yayın hakkı verilmez.
4. Yazılı keşif, kapsamı belirtilen sınırlı bir Türkçe ayrıştırıcıdır. Tanınmayan
   anlamlı koşullar elenip geniş sorgu yapılmaz. MiMo, ses ve sosyal platform
   entegrasyonunun tamamlandığı iddia edilmez.
5. Gün planı ayrı saf fonksiyondur: kullanıcı süreleri, sabit/esnek duraklar ve
   varış payıyla hesap yapar. Eksikte çekimser kalır, çakışmada randevu saatini
   değiştirmez. Her sonuç elle verilmiş süreleri ve canlı trafik olmadığını belirtir.
6. Profil/plan taslağı tarayıcıda tutulur. Gerçek kullanıcı üyeliği, davet,
   kimlik doğrulaması veya otomatik alışkanlık öğrenmesi bu değişikliğe dahil değildir.
7. 21 Ekim'deki tam İstanbul haritası isteği üzerine ilk görünüm iki yakayı ve
   İstanbul çevresini kapsayan kamera alanına sığar; idari sınır çizilmez.
   Sokak, kıyı ve 2B bina izleri görünür alanla sınırlı standart OSM
   karolarından gelir. Yakın kaynaklar sayılı grupta gösterilir. Ayrı İstanbul
   ve Galata odağı bulunur; kategori seçimi kamerayı sıfırlamaz. Harita
   görüntülemesi tarayıcıda internet ister; API ve CI kaynak verisi çekmez.
   Başarısız karo istekleri yalnız açık kullanıcı eylemiyle tekrar edilir.

## Doğrulama ve ölçüm

Bu bir yeni bilimsel deney veya model üstünlüğü iddiası değildir. Yeni testler
adapter'ın gerçek risklerini kapsar: tür/kullanım hakkı atlatma, talepteki
koşulun kaybolması, eksik bilgiden kesin öneri üretme, sabit planı sessizce
oynatma ve HTTP üzerinden repo dosyalarını açığa çıkarma. Mevcut çekirdek
davranışları korunur. Python 3.11 ve 3.13 CI, JS sözdizimi ve tarayıcıda
masaüstü/mobil etkileşim kontrolü tamamlanma kanıtlarıdır.

## Sonraki bağlanacak işler

Yayımlanabilir güncel pilot katalog; gerçek model adapter'ı; rota/trafik
sağlayıcısı; native bağlama; üye doğrulaması; izinli sosyal kaynaklar ve gerçek
doluluk/avantaj bağlantıları. Bunlar mevcut önizlemede varmış gibi gösterilmez.

## Geri alma

`apps/kep_preview`, `preview.yml` ve README'nin önizleme bölümü çıkarılabilir.
Core, Rust, kaynak izinleri, arşivler ve mevcut deneylerin davranışı etkilenmez.
