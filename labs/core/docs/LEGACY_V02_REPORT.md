# KEP Core v0.2 | Çalıştırılan gerçek-kayıt laboratuvarı

## Sorunun doğru tanımı

Bu çalışma KEP'in gelirini değil çekirdeğinin bilgi ve karar davranışını sınar. Önceki v0.1'in sentetik fayda fonksiyonları, yaratılmış kullanıcı zevkleri ve varsayımsal kaynak güvenilirlikleri bu pakete gerçek performansmış gibi taşınmamıştır.

## Dört kanıt seviyesi

1. **Gerçek kaynak kaydı:** 16 İzmir etkinliği ve 7 İstanbul mekânının gerçekten görülen alanları.
2. **Kaynak tanıklığı:** Bu alanların gözlemlenen yayını; gerçekte etkinliğin gerçekleştiği veya mekânın bugünkü durumunun doğruluğu değil.
3. **Tasarlanmış istek:** Bilinen bir mekân çevresini, bütçeyi veya açık olmayı sorgulayan kontrollü girdi. Gerçek kullanıcı tercihi değil.
4. **Hata enjeksiyonu:** Gerçek kaydın kopyasına test amacıyla iptal/eski zaman/yanlış fiyat eklemek. Gerçek iptal kaydı değil.

Sonuçların birbirine karışmaması için dosyada `origin`, `synthetic`, `source_observed_at`, `origin_live_verified` ve kaynak hash'i saklanır.

## Gerçek verinin öğrettikleri

16 etkinlik: 5 tek seans adayı, 4 seansları listelenmemiş program aralığı, 7 sergi aralığı. Dört kayıtta başlangıç ve bitiş aynı; birinde ücretsiz olmadığı belirtilmiş fakat fiyat tutarı yok. İki mekân ifadesi konum için belirsiz. 10 Ekim değerlendirmesinde 14 kayıt geçmişte; iki sergi ilan edilen aralıkta. O iki sergi için günlük açılış, devam etme veya doluluk kanıtı yok.

İstanbul havuzu 7 seçilmiş kültür mekânıdır. Mutfak, kişi tercihi, sıra/bekleme, canlı fiyat veya yürüme süresi verisi yok. Bu havuz geniş bir restoran öneri başarısı çıkarımına elverişli değildir.

Pera fiyat örneğinde doğruladığımız şey internetten gelen **çıktıların çatışmasıdır**. Arama çıktısında 300/150/200 ve 450/250/300 değerleri birlikte görünürken açılan eski önbellekte eski tarife tutarlıdır. Bu nedenle tek bir güncel fiyat söylemiyoruz. Kaynak bölümünün iki kez sayılması veya aynı sayfanın 50 kez çoğaltılması bağımsız doğrulama sayısını yükseltmiyor.

## Matematiksel kararın uygulanan kısmı

Bir isteğin gerekli alanları `R(q)` olsun. Bir kaydın eldeki ve güvenle kullanılabilir alanları `K(x,t)` olsun.

`Uygun(x,q) = şehir ∧ kategori ∧ mesafe ∧ süre/durum ∧ bütçe ∧ kullanım_hakkı ∧ gerekli_kanıt`

`R(q)` içinde bilmediğimiz bir alan varsa bu alanı varsaymıyoruz. Eksiklik bilgi tazelemesiyle giderilebiliyorsa `REFRESH`; kullanıcının tanımını netleştirmek gerekiyorsa `CLARIFY`; geçerli aday yoksa `ABSTAIN`; izin verilmeyen proaktif durumda `SILENT`. Bir mekânın yalnız yaklaşık konumunu istemek, mevcut fiyatını veya açık olduğunu sormaktan farklıdır.

Bu katman, v0.1'deki bütçenin %40 üstünü aday sayma yaklaşımını kullanmaz. 500 TL sınırında bilinen 501 TL kayıt elenir. Bunun doğru mu iyi mi olduğunu otonom model tartışmasına bırakmıyoruz; kullanıcının sert kısıtı olarak uyguluyoruz.

Tam Bayes inanç güncellemesi, öğrenilmiş yarar fonksiyonu, bilgi kazancının öğrenilmiş tahmini, bandit, kullanıcı seçim olasılığı, çok ajanlı planlama ve LoRA bu sürümde yoktur. Basit, izlenebilir çekirdek kontrolünün yeni model katmanlarına temelini kurar.

## Deney düzeni

85 önceden isimlendirilmiş sözleşme durumu çalıştırıldı: 76 gerçek kayıt üzerinde tasarlanmış sorgu ve 9 yapay değişiklik/izin senaryosu. Bu küme eğitim/test ayrımı olan kör akademik değerlendirme değildir. Beklenen cevaplar tasarım kurallarını test eder; gerçek dünya etiketlerini keşfetmez.

| Politika | Kurala uygun sonuç | Yanıt veren durum | Yorum |
|---|---:|---:|---|
| `simple_safe` | 85/85 | 9 | KEP ile aynı sert filtre ve mesafe yöntemini paylaşır. Bağımsız rakip değildir. |
| `query_aware` | 85/85 | 9 | Mevcut KEP çekirdeği; fazladan model çağrısı yok. |
| `blanket_verification` | 69/85 | 0 | Gerekmeyen fiyat/saat bilgisi için de her sorguyu durduran aşırı ihtiyatlı varyant. |

9 yanıtın 7'si gerçek mekânın basit katalog bilgisi, 2'si açıkça yapay güncellik eklenen test kopyasındaki öneridir. **Gerçek veriden canlı doğrulanmış etkinlik önerisi: sıfır.** Bu sayı gizlenmedi; tazelik kanıtı yokken tavsiye üretmemek istenen davranıştır.

85/85 sonucu önerilerin gerçek kullanıcıya yararlılık oranı olarak kullanılamaz. Aynı kodu paylaşan iki güvenli politika arasında üstünlük ölçülmedi. Aşırı kapıyı geçmek, bağımsız bir sektör ürününü geçmek değildir. Tüm yöntemlerde aynı girdi, şehir/kısıtlar ve kayıt sayısı korundu.

## Yazılım testleri

50 unittest metodu başarılı. Bunlardan biri 85 durumun tamamını alt test olarak çalıştırır; metrikler toplanıp bağımsız deney sayısı ilan edilmez. Bir başka test 100 giriş sıralamasında öneri sırasının değişmediğini denetler.

Denetlenenler: aynı gözlemin tekrarı; kaydın sırası; yanlış şehir; bütçe sınırı; eksik fiyat; eşit başlangıç/bitiş; seans aralığı; gelecekte görünen gözlem; kaynak hakları; izin ve kullanıcı modu; eski güncellemenin yeni kaydı ezememesi; aynı zaman damgalı çelişkide sessiz overwrite yapmama; kaynak otoritesi değişerek overwrite yapmama; iptal sonrası outbox ve push adayının atomik değişimi.

SQLite referans implementasyonu vardır. Gerçek çoklu işçi, üretim Postgres işlemleri, ağ kesilmesi sonrası teslim, mobil işletim sistemi push teslimi, fiziksel check-in ve harici bilet dönüşümü test edilmedi.

## Yeniden üretim

`python3 run_lab.py` JSON raporlarını ve SQLite örneğini üretir. `python3 -m unittest discover -s tests -v` testleri tekrarlar. Duvar saati çalışma süreleri makineye göre değişir; kalite çıktıları deterministiktir. Orijinal dosya hash'leri manifestte doğrulanır. Ek ağ veya model masrafı doğurmaz.

## Karar

Kaynakların bilinen alanlarını sorgunun gerçekten ihtiyaç duyduğu alanlardan ayırmak uygulanabilir. Bilgi eksikken susmanın yanında, bilinen kısmı açık sınırlarla sunmak da gerekir. Çelişkili içerik için sayfa saymak yerine köken ve alan düzeyi çatışması korunmalıdır. Güven ve öğrenme aynı şey değildir.

Bu sürüm, akademik araştırmaların tamamından oluşan nihai öğrenen KEP değildir. Öğrenen politikanın daha sonra dürüstçe değerlendirilebilmesi için gereken **veri/kısıt/kanıt/yürütme çekirdeğinin ilk çalışan örneğidir**. Bundan sonraki darboğaz model sayısı değil: canlı ve hakları uygun İstanbul veri örneklemi, gerçek değişim geçmişi ve bağımsız değerlendirme etiketleri.
