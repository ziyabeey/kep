# KEP · Çekirdeğe bağlı yerel önizleme

Bu geliştirme arayüzü, mevcut Python Core'un kullanıcı ekranına nasıl
bağlanacağını çalışır halde gösterir. Native iOS/Android uygulamasının yerine
geçmez; internete dağıtılacak üretim servisi değildir.

## Çalıştırma

Depo kökünde Python 3.11 veya 3.13 ile:

```bash
python3 -m apps.kep_preview.server
```

`http://127.0.0.1:4180/` adresini açın. Paket kurulumu, API anahtarı veya model
çağrısı gerekmez. Keşif kataloğu depodaki mevcut kayıtlardır. Harita için
tarayıcı görünür alanın OpenStreetMap karolarını internetten yükler; bağlantı
olmadan kaynak konumları ve yerel uygulama çalışmaya devam eder.
Varsayılan sunucu yalnız loopback'e bağlanır.
Geliştirme proxy'si gerekiyorsa açıkça adres ve tam Host değeri belirtilebilir:

```bash
python3 -m apps.kep_preview.server --host 0.0.0.0 --port 4180 --allow-host terminal.local:4180
```

Bu seçenek erişimi geliştirme ağına açar; kimlik doğrulaması eklemeden üretim
ortamına veya genel internete dağıtılmamalıdır. Sunucu Host/Origin denetimi,
sabit statik dosya listesi ve 16 KiB JSON istek sınırı uygular.

## Çalışan akış

- Keşif, Yemek, Etkinlik ve Hizmet kategori şeridi; tıklama ve yatay kaydırma.
- İlk açılışta Avrupa ve Anadolu yakalarıyla İstanbul genel haritası. Şehir
  görünümüne dönme, Galata sonuçlarına odaklanma ve yer detayından yakınlaştırma.
  Kategori değişimi haritanın konumunu değiştirmez.
- Mevcut örnek kataloğun Core tarafından seçilen İstanbul yerleri; kaynak linki,
  kuş uçuşu mesafe ve doğrulanmamış canlı durumun açık gösterimi.
- Yarıçap, bütçe, açık olma ve sakinlik koşulları. Core `REFRESH` veya `CLARIFY`
  diyorsa arayüz uygun sonuç varmış gibi davranmaz.
- Sınırlı Türkçe keşif komutları. Desteklenmeyen konum, mutfak veya koşul
  sessizce atılmak yerine açıklama isteğine dönüşür.
- Profil dairesine tıklayınca keşif kutusu; basılı tutup yukarı sürükleyince
  profil. Görünür profil düğmesi ve klavye erişimi de bulunur.
- Yerel profil ve gün taslağı. Kimlik doğrulaması, üyelik veya öğrenilmiş
  alışkanlık iddiası yoktur; bu bilgiler yalnız tarayıcıda saklanır.
- Sabit randevular ve aradaki esnek duraklar için süre hesabı. Bilinmeyen
  sürelerde çıkış saati verilmez; sığmayan planın sabit randevuları değiştirilmez.

### Örnek keşif istekleri

“Galata çevresinde 1 km içinde yer bul”, “Şimdi açık ve 500 TL altında yer bul”,
“Sakin bir yer bul”, “Müze bul”. Bu bir LLM sohbeti değildir. Desteklenen
komutlar `service.py` içinde, başarısız yorumlama davranışı testlerde tanımlıdır.

### Gün planı

Maslak 16.00 → Levent 17.00 → esnek ekip yemeği → Zorlu 20.00 örneği
düzenlenebilir bir taslak olarak sunulur. Toplantı/yemek süreleri ve duraklar
arası yol süreleri kullanıcı tarafından girilir. Hesap, sırayı koruyarak ileri
en erken zamanları ve geri en geç çıkış sınırlarını bulur. Giriş payı sabit
hedefe varıştan önce bırakılır. Aynı gün dışına taşan veya çakışan plan
`conflict`; eksik gerekli süreler `needs_input` verir. Eksik bilgi olsa da
bilinen süreler çakışmayı kesinleştiriyorsa `conflict` döner; hesaplanan çıkış
saatleri ve boşluk süreleri boş kalır. Son durağın kalış süresi, oraya varış
hesabı için zorunlu değildir.

Sonuç `basis=manual_estimates`, `traffic_live=false` taşır. Bir rota servisi
veya canlı trafik tahmini bağlı değildir; rezervasyon veya gerçek bildirim
oluşturulmaz.

## Veri sınırı

`load_catalog()` içindeki mevcut tarihsel örnekler kullanılır. Harita İstanbul
genelini gösterir; keşif verisi yedi Wikimedia kaynaklı mekân örneğiyle,
arama merkezi Galata ile sınırlıdır. Ücret, çalışma
saati, fiziksel doluluk ve güncel faaliyet durumu doğrulanmış sayılmaz. Boş
kategorileri doldurmak için sahte restoran/etkinlik eklenmez.

4.803 kayıtlık Overture araştırma arşivi bu arayüze aktarılmaz. Kaynak kayıt
sistemindeki araştırma/tüketici hakları ve izinler değiştirilmez. JSON API
kullanıcının `rights_scope`, `consumer_publish` gibi alanları değiştirmesini
ve tüm repo dosyalarına erişmesini kabul etmez.

Harita ilk açılışta İstanbul'u kapsayan yaklaşık bir kamera alanına sığar;
bu alan idari sınır çizgisi değildir. Sokaklar, kıyılar ve yakınlaştırıldığında
görünen 2B bina izleri OpenStreetMap karolarından gelir. Sentetik geometri,
3B bina modeli veya bütün binaların güncel/doğrulanmış olduğu iddiası yoktur.
Uzak görünümde birbirine yakın kaynak kayıtları sayılı grupta gösterilir;
gruba basınca aynı kayıtların gerçek koordinatlarına yakınlaşılır.

Tarayıcı yalnız görünür alanın OpenStreetMap karolarını ister. Atıf görünür
kalır; normal HTTP önbelleği kullanılır; çevrimdışı karo arşivi/prefetch yoktur.
Yükleme hatası açıkça gösterilir. Başarısız karolar otomatik tekrar istenmez;
“Haritayı tekrar yükle” yalnız o an görünen başarısız karoları yeniden ister.
API/CI kaynak verisi çekmez; API'deki `source_fetches=0` bu veri sınırını
ifade eder, tarayıcının harita görüntüsü isteklerini değil.
[OSM kullanım politikası](https://operations.osmfoundation.org/policies/tiles/).

## HTTP sözleşmesi

| Yol | İşlev |
|---|---|
| `GET /api/health` | Önizleme ve canlı entegrasyon durumları |
| `GET /api/bootstrap` | Meta, kategori listesi ve ilk Core sonucu |
| `POST /api/discover` | Tipleri denetlenen filtreleri mevcut Core'a uygular |
| `POST /api/chat` | Desteklenen keşif ifadesini aynı sorguya dönüştürür |
| `POST /api/plan` | Kullanıcının süreleriyle gün taslağını değerlendirir |

Sunucu kullanıcı mesajlarını veya profilini bir veritabanına yazmaz. Model
sınırı ve kaynak hakları `labs/core` içinde değişmeden kalır. Yeni ürün
adapter'ları bu arayüzün arkasına sonradan bağlanabilir.

## Doğrulama

```bash
python3 -m unittest discover -s apps/kep_preview/tests -t . -v
node --check apps/kep_preview/static/app.js
node apps/kep_preview/tests/frontend_state.test.js
```

HTTP testleri yalnız geçici localhost sunucusu açar; dış bağlantı yapmaz.
Testler kaynak/alan geçişini, desteklenmeyen isteğin kaybolmamasını, gerçek
Core'un eksik bilgi kararını, plan çakışmalarını ve HTTP sınırlarını denetler.
Python 3.11/3.13 CI ayrı `preview.yml` iş akışındadır. Mevcut araştırma CI'ı da
çalışmaya devam eder.
