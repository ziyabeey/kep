# İstanbul 3B verisi ve Kep'in kendi görünümü

Tarih: 2026-10-21. Durum: kaynak/erişim araştırması; İBB model verisi henüz
temin edilmedi veya uygulamaya aktarılmadı.

## Kullanıcının netleştirdiği hedef

İlk hedef bölgeler **Kadıköy, Beyoğlu ve Beşiktaş**. İBB'nin harita arayüzünü
veya görünümünü kopyalamak hedef değil. Gerçek bina geometrisini veri olarak
alarak Kep'in kendi 3B sahnesini, kategori renklerini ve etkileşimlerini kurmak
isteniyor. Mevcut 2B OSM görünümü, önizlemenin coğrafi bağlamını gösterir;
nihai 3B ürün tasarımı veya İBB veri entegrasyonu değildir.

## Doğrulananlar ve açık kalanlar

| Konu | Kanıt ve sınırı |
| --- | --- |
| İBB'de 3B model var mı? | Resmi CBS Akademi proje sayfaları 3B mekânsal modelleme, mimari detay ve dokulardan söz ediyor. [1][2] |
| Dosya olarak model ürünü var mı? | İBB 2026 Harita Şube Müdürlüğü ücret tarifesinin resmi arama indeksinde LoD2 dış cephe giydirilmiş **CityGML+OBJ** bina modeli kalemi yer alıyor. PDF'nin tamamı bu oturumda zaman aşımına uğradı; fiyat/koşullar kesin teklif olarak alınmadı. [3] |
| Görüntüleyicideki model ile satılan model aynı mı? | Doğrulanmadı. Görüntüleyici modelinin ayrıntısı, ürün sürümü ve dosya teslim biçimi ayrıca sorulmalı. |
| Üç ilçenin tamamı kapsanıyor mu? | Doğrulanmadı. Bir resmi sayfa **Tarihi Yarımada ve çevresi** diyor; diğer sayfa tam kapsam dökümü vermiyor. [1][2] |
| Ölçüm/güncelleme tarihi ve doğruluk | Proje başlangıcının Kasım 2023 olması modelin çekim tarihi değildir. Konum/yükseklik doğruluk ölçüsü, sürüm tarihi ve değişim kapsamı temin edilmeli. [2] |
| Geliştirici API var mı? | Şehir Haritası API'si API anahtarı, iframe ve JavaScript ile marker, rota ve panorama gibi işlevleri belgeliyor. Bu, 3B model indirme/yeniden dağıtma izni veya API'si olduğunu göstermiyor. [4] |
| Ticari kullanım ve dağıtım | Resmi 2026 tarife açıklamaları ticari kullanım için satış sözleşmesi ve telif bedelini ele alıyor. Kamuya açık görüntüleyici erişimi, Kep'te barındırma ve son kullanıcıya 3B veri sunma hakkını tek başına doğrulamıyor. Ürüne ait sözleşmenin dönüştürme/gösterim/dağıtım kapsamı henüz alınmadı. [3] |

## Teknik tercih

**Çıkarım/öneri:** İzinli teslim mümkünse öncelik, ayrı bina kimliklerini ve
coğrafi referansı koruyan CityGML veya eşdeğer nesne tabanlı modeldir.
CityGML, geometriyi, nesneler arası ilişkileri ve görünüm özelliklerini
tanımlayabilen bir şehir veri modelidir; ancak belirli bir İBB dosyasının bütün
bu alanları içerdiği ancak örnek dosya incelenince anlaşılır. [5]

Kep'in renkleri, malzemeleri, ışığı ve seçili binaları vurgulaması ayrı sunum
kararlarıdır. Yapı geometrisini koruyarak özgün görünüm üretmek teknik olarak
mümkündür; dönüşüm/değiştirme hakkı veri kullanım koşullarında doğrulanmalıdır.
Bütün alan tek birleşik ağ olarak teslim edilirse bina başına seçim ve renk
atama için ayrıca bina kimliği/ayırma bilgisi gerekebilir.

İzinli örnek geldiğinde:

1. Kaynak sürümünü, dosya özetini, koordinat/yükseklik referansını ve bina
   kimliklerini kaydet.
2. Her hedef ilçeden küçük bir örnek alanda konum, ölçek, zemin yüksekliği,
   çatı geometrisi ve eksik binaları kontrol et. LoD düzeyini güncellik veya
   ölçüm doğruluğu garantisi sayma.
3. Modelin özünü koruyarak mobil görüntülemeye uygun biçime dönüştür.
   glTF/GLB ve bölümlenmiş 3D Tiles olası sunum biçimleridir; kesin dönüştürücü
   ve motor örnek veriyle seçilecek. OGC, CityGML ile sunum biçimleri arasındaki
   dönüşümü ve 3D Tiles'ta özellik bazında stillendirmeyi tarif eder. [5][6]
4. Bina kimliğini Kep'in yer/etkinlik kaydıyla eşleştir. Model geometrisi;
   mekânın açık olduğunu, işletme adını, doluluğunu veya etkinlik olduğunu
   tek başına kanıtlamaz.
5. Üç ilçeye büyütmeden önce gerçek hedef cihazda yükleme, bellek ve etkileşim
   ölç. Bu belge bir performans sonucu veya veri kabulü değildir.

## Hazır veri/koşul sorusu taslağı

**Konu:** Kadıköy, Beyoğlu ve Beşiktaş için 3B bina modeli veri erişimi

Kep adlı şehir keşfi ve gün planlama uygulamasının pilotu için Kadıköy,
Beyoğlu ve Beşiktaş'taki 3B bina modellerini değerlendirmek istiyoruz.
Amacımız gerçek bina geometrisini kendi uygulama arayüzümüzde ve kendi
renk/malzeme tasarımımızla görüntülemektir.

Aşağıdaki konularda bilgi ve mümkünse küçük bir teknik değerlendirme örneği
paylaşılmasını rica ederiz:

- Bu ilçelerde mevcut kapsam, modelin ölçüm/üretim ve son güncelleme tarihi;
  konum ve yükseklik doğruluğu bilgileri.
- LoD düzeyi; CityGML sürümü, OBJ veya varsa 3D Tiles/I3S teslim seçenekleri;
  bina başına kalıcı kimlik, koordinat sistemi, yükseklik referansı ve dokuların
  dahil olup olmadığı.
- Dosya teslimi veya servis erişimi; alan/bina bazında örnek ve fiyatlandırma.
- Ticari mobil/web uygulamasında son kullanıcıya gösterim, kendi sunucumuzda
  barındırma/aktarım, biçim dönüştürme, sadeleştirme, renk/malzeme değiştirme,
  önbellek ve gerekli kaynak gösterimi koşulları.
- 3B İstanbul görüntüleyicisindeki model ile bu kapsamda sağlanan veri
  ürününün aynı sürüm/kapsam olup olmadığı.

Bu taslak gönderilmedi; başvuru, ödeme, sözleşme kabulü veya API anahtarı
oluşturma işlemi yapılmadı.

## Kaynaklar

1. [İBB CBS Akademi — 3B İstanbul](https://cbsakademi.ibb.istanbul/proje/3b-istanbul)
2. [İBB CBS Akademi — 3B İstanbul Uygulaması](https://cbsakademi.ibb.istanbul/proje/3b-istanbul-uygulamasi)
3. [İBB 2026 Harita Şube Müdürlüğü ücret tarifesi](https://uploads.ibb.istanbul/uploads/Harita_Sube_Mueduerluegue_72aa5ab47f.pdf)
4. [İBB Şehir Haritası API geliştirici sayfası](https://sehirharitasiapi.ibb.gov.tr/developer/index.html)
5. [OGC CityGML kavramsal model standardı](https://docs.ogc.org/is/20-010/20-010.html)
6. [OGC 3D Tiles 1.1 standardı](https://docs.ogc.org/cs/22-025r4/22-025r4.html)
