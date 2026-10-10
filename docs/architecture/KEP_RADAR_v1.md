# KEP Radar — Kanonik Mimari ve Doğrulama Planı v1.0

**Tarih:** 10 Ekim 2026  
**Durum:** Kanonik teknik taslak; mimari ilkeler sabit, performans tahminleri saha testine tâbi.  
**Kapsam:** KEP'in şehir bilgisini toplayan Radar katmanı, bilgi çekirdeği, MiMo entegrasyonu, uyarlanabilir görev planlayıcısı ve veri kalitesi.  
**Pilot coğrafya:** Beşiktaş ve Karaköy; Kadıköy ancak pilot geçitleri sağlandıktan sonra.  
**Ürün:** KEP — “Etrafında ne oluyor?” Etkinlik, yemek, mekân, yerel hizmet ve AI sohbet keşfi; bilet satışı yok, yetkili haricî bağlantılar var.

> **Temel hüküm:** KEP'in değeri daha çok sayfa taraması değil, doğrulanmış **yer + zaman + kaynak + kullanıcı niyeti** eşleşmesidir. Veri bir kez toplanır; birçok kullanıcıya sunulur.

## I. Tez — Her kaynağı AI ajanına bırakmak

**Sav:** MiMo/Laya benzeri karar modelleri tarayıcı kullanabilir, yeni sayfalara uyum sağlayabilir ve karmaşık açıklamaları yorumlayabilir. Çok sayıda kaynak hızlı entegre edilmiş gibi görünür.

**Avantajlar:** Değişken HTML, belirsiz etkinlik metni, aynı mekânın farklı adları, eksik tarih gibi durumlarda esneklik.

**Riskler:** Her gezinme adımında model kullanımı; yanlış tıklama ve yanlış bilgi çıkarımı; tekrarlanamayan sonuç; kaynak sitenin izin ve erişim koşulları; maliyet oynaklığı; veri doğrulama zorluğu. AI ajanı, bir kaynağın API kısıtlamasını veya veri kullanım yasağını ortadan kaldırmaz.

**Karar:** Serbest dolaşan AI crawler ilk mimari **olmayacak**. AI, belirsizlikte çağrılan kontrollü bir araç olacak.

## II. Antitez — Her şeyi düz script ve zamanlayıcıyla yapmak

**Sav:** Önceden bilinen 10–50 kaynağın hangi alanlarının çekileceği ve kontrol aralığı bellidir. HTTP, RSS/ICS, API, JSON-LD, DOM seçiciler, SQL ve diff/hashing çoğu işi AI olmadan yapar.

**Avantajlar:** En düşük değişken maliyet; denetlenebilirlik; idempotent çalışma; kolay test ve tekrar.

**Riskler:** Dinamik sayfa tasarımları, belirsiz ifade ve doğal dilde kaynaklar için bakım gereksinimi. Tek bir kaynaktaki HTML değişikliği tüm sistemin mimarisini değiştirmemeli.

**Karar:** Yalnızca sabit seçicilerden oluşan, kaynak başına özel ve kırılgan script yığını da **olmayacak**.

## III. Sentez — Kaynak kayıt sistemi + deterministik toplama + seçici MiMo

**KANONİK ÇÖZÜM:**

```text
Onaylı kaynak listesi / Source Registry
             ↓
Uyarlanabilir zamanlayıcı (next_run_at, bütçe, izin, değişim hızı)
             ↓
Toplayıcı adaptörleri: API / RSS-ICS / JSON-LD / HTML / gerekli ise Browser
             ↓
Değişim algılama: ETag / Last-Modified / içerik hash'i
             ↓
Deterministik ayrıştırma → şemaya dönüştürme → birleştirme
             ↓
Belirsizlik varsa MiMo Flash → gerekirse daha güçlü MiMo / insan kontrolü
             ↓
KEP Core: Places + Event Occurrences + Offers + Signals + Evidence
             ↓
KEP arama / Keşfet / PULSE / MiMo sohbet / takip / izinli Web Push
             ↑
İzinli kullanıcı geri bildirimi, ölçümleme, eksik veriler
```

**Çekirdek sahipliği:** Ajanlar bilgi toplar; **KEP Core bilginin tek doğruluk kayıt sistemi** olur. MiMo çekirdeğin sahibi veya veritabanı yazarı değil, araçlarla kontrollü çalışan muhakeme ve sohbet katmanıdır. Ajan sayısı kadar model oturumu yoktur. İlk sürümde küçük/büyük karar modeli isimlerine sıkı bağlılık yoktur; `ModelAdapter` kullanılır. KEP v1'de varsayılan üretken model MiMo'dur. Laya denemeleri sonradan yalnızca ölçülebilir kazançla eklenebilir.

## IV. Sabit ürün sınırları (ADR kararları)

| ID | Değişmeyecek ilke |
|---|---|
| KEP-ADR-001 | KEP kullanıcıya ücretsiz keşif + AI sohbet + takip sunmayı hedefler; bilet satıcısı değildir, yetkili bilet satış sayfalarına yönlendirir. |
| KEP-ADR-002 | Pilot yalnızca Beşiktaş + Karaköy; yeni semt ekleme kaynak yoğunluğu kriterine bağlı. |
| KEP-ADR-003 | Yalnızca kaynak kayıt sisteminde erişim amacı, koşulları ve hızı onaylanmış kaynaklar taranır. Koruma aşma ve izinsiz toplu sosyal medya taraması yok. |
| KEP-ADR-004 | Kaynak, gözlem, doğrulanmış bilgi ve model çıkarımı ayrı kayıt türleridir. Kanıtı olmayan iddia `verified` olamaz. |
| KEP-ADR-005 | Zamanlayıcı akıllı ama yürütme deterministiktir; her işin maliyet ve süre sınırı vardır. |
| KEP-ADR-006 | MiMo sadece değişen/belirsiz içerik, zor eşleştirme, kullanıcı muhakemesi ve sohbet için; varsayılan her fetch'te model çağrılmaz. |
| KEP-ADR-007 | Kaynağa özgü adaptör değişiklikleri Core şemasını ve tüm uygulamayı değiştirmez. Şema sürümlenir. |
| KEP-ADR-008 | Randevu'dan mimari örüntüler alınır; KEP'in kişisel veri amaçları ve veri deposu ayrı tutulur. |
| KEP-ADR-009 | Kullanıcı durumları (İş / Gezinti / Dengeli / Sessiz), radarın kaynak tarama temposundan bağımsızdır. |
| KEP-ADR-010 | Sosyal paylaşım sayısı fiziksel kalabalık değildir; KEP PULSE bunları ayrı açıklar. |
| KEP-ADR-011 | Yeni bir pahalı API yalnızca ölçülen bilgi boşluğu, lisans ve maliyet/fayda testinden sonra eklenir. |
| KEP-ADR-012 | Kaynak içeriği güvenilmez girdidir; prompt injection, SSRF, izinsiz yazma, otomatik sosyal yorum ve veri sızmasına karşı yetki sınırları uygulanır. |

### Neler sabit, neler değişebilir?

- **Sabit:** veri sözleşmeleri, ajan-çekirdek sınırı, kullanıcı gizliliği, kaynak izinleri, kanıt seviyeleri, maliyet sınırı, ürün konumu.
- **Yapılandırılabilir:** kaynak URL'leri, kategori, tarama aralığı, MiMo model sürümü, parser seçicileri, semt listesi ve eşikler.
- **Deneye açık:** öneri sıralaması, MiMo/Laya karşılaştırması, doğrulama eşiği, PULSE sinyal ağırlıkları, veri kaynaklarının eklenmesi.
- **Değişiklik yöntemi:** her mimari değişiklik için `ADR-XXX` (amaç, gerekçe, alternatif, veri, risk, geri dönüş), bir günlük/yedi günlük test ve şema versiyonu; sessiz yeniden tasarım yok. İlk **90 gün** bu omurgayı değiştirmek yerine parametreleri kalibre edeceğiz, ancak kritik güvenlik veya hukuki zorunluluk bunun istisnası.

## V. Veri sınıfları ve kalite sözleşmesi

### Veri sınıfları

1. **Place:** restoran, kafe, salon, galeri, kültür merkezi. Kimliği uzun ömürlü; ad/adres/kategori değişebilir.
2. **EventOccurrence:** gerçek bir tarih-saat ve mekânda gerçekleşen tek seans; konserin iki farklı günü iki occurrence olabilir.
3. **Offer/Service:** fiyat, kampanya, hizmet veya müsaitlik; doğrulanma ve bitiş tarihi zorunlu.
4. **Signal:** izinli sosyal duyuru, resmî güncelleme, haber veya trafik olayı. Kendisi etkinlik veya fiziksel kalabalık kanıtı değildir.
5. **Evidence/Claim:** Bir olgu hangi kaynaktan ne zaman alındı, hangi alanı destekliyor, hangi çelişkileri içeriyor, kullanım lisansı ne?

### Asgari kayıt alanları

```yaml
Source:
  id: string
  base_url: string
  source_type: api|rss|ics|jsonld|html|browser|manual
  allow_status: approved|pending|blocked
  usage_rights: reference # insan tarafından incelenmiş koşul kaydı
  polling_min_minutes: integer
  polling_max_minutes: integer
  next_run_at: timestamp
  parser_version: string
  last_success_at: timestamp|null
  error_budget: integer

Observation:
  id: uuid
  source_id: string
  source_url: string
  observed_at: timestamp
  published_at: timestamp|null
  content_hash: string
  extraction_version: string
  retention_until: timestamp|null
  processing_state: new|unchanged|parsed|review|rejected

EventOccurrence:
  id: uuid
  canonical_place_id: uuid|null
  name: string
  starts_at: timestamp
  ends_at: timestamp|null
  timezone: Europe/Istanbul
  original_url: string
  evidence_ids: uuid[]
  status: candidate|verified|disputed|cancelled|expired
  last_verified_at: timestamp|null
  location_precision: exact|approximate|unknown
```

**Yayın kapısı:** Etkinlik adı, başlangıç tarihi, bilinen veya açıkça belirsiz olarak işaretli konum, kaynak bağlantısı ve kanıt durumunu kontrol et. `verified` için yetkili kaynaktan teyit gerekir; çok sayıda benzer paylaşım tek başına teyit değildir. İptal/tarih değişikliği öncelikli tetikleyicidir. Açıkça belirsiz olan bilgi uydurulmaz.

**Gizlilik ve lisans:** Kişisel kullanıcı konumu ve sosyal kimliği, açık şehir kayıtlarıyla aynı tabloda tutulmaz. Üçüncü taraf gönderi metni/görseli/videoyu otomatik olarak kalıcı kopyalamayız. YouTube API'nin saklama/yenileme ve türetilmiş metrik kuralları, Meta'nın izin koşulları ve her etkinlik sitesinin kullanım şartları ayrı uygulanır. Bilet yönlendirmesi, üçüncü taraf sayfaların toplu kopyalanma izni değildir.

## VI. Uyarlanabilir zamanlayıcı (çekirdek algoritma)

**Gün/saat sadece başlangıç ağırlığıdır.** Varsayılan olarak pazartesi–perşembe daha pasif, cuma akşamı ve hafta sonu daha hareketli bir politika uygulanır. Ancak salı akşamı konser yoğunluğu gibi gerçek sinyaller, haftalık kalıbı geçersiz kılabilir. Kaynak özelindeki güncellenme hızı, yaklaşan etkinlikler, kullanıcı talebi, kritik iptal ve izinli sorgu sınırları asıl belirleyicidir. Ani dalgalanmayı önlemek için yükseltme/düşürme kararlarında birkaç ardışık gözlem (histerezis) kullanılır; kaynak izinleri aşılmaz.

| Kaynak sınıfı | Düşük aktivite | Normal | Yüksek hareket |
|---|---:|---:|---:|
| Haftalık kültür takvimi | 12–24 saat | 6–12 saat | 2–4 saat |
| Sık güncellenen bilet/organizasyon akışı | 4–6 saat | 1–2 saat | 15–30 dakika, izin varsa |
| Menü / işletme sayfası | 24–72 saat | 24 saat | 6–12 saat |
| Trafik/yoğunluk lisanslı olay akışı | Ürüne göre | Ürüne göre | Sağlayıcının izin verdiği hızda |

**İş seçimi:** Her dakika çalışan tek bir planlayıcı `next_run_at <= now` koşulunu sağlayan görevleri bulup kuyruğa bırakabilir. Tarama hızını artırmak için yeni cron eklemeye gerek yoktur. Kaynak başına `min_interval`, `max_interval`, `daily_request_cap`, `backoff_until`, `change_rate`, `priority` tutulur. Kaynak `429`, `403`, `robots/terms` engeli veya şüpheli davranış bildirirse otomasyon durur, korumayı aşmaz.

**İş durumu:** `scheduled → fetched → unchanged | changed → parsed → candidate → verified | needs_review → published`. Hatalar retry/backoff ve karantina kuyruğuna gider. Aynı işlem tekrar geldiğinde aynı veriyi ikinci kez eklemez (idempotency key).

**Maliyet kontrolü:** Dakikalık global kaynak isteği sınırı, kaynak bazlı kota, aylık browser zamanı, günlük MiMo token bütçesi, beklenmeyen maliyette otomatik durdurma. Trafik artışı tek başına tüm kaynaklarda agresif taramayı başlatmaz; yalnızca ilgili ve güncellenen kaynaklar hızlandırılır.

## VII. Veri miktarı projeksiyonu: ölçüm değil hipotez

İki havuzu ayırıyoruz: **mekân envanteri** (toplu başlangıç ithali) ve **sürekli yeni etkinlik/duyuru akışı**.

**Mekân:** Overture/izinli açık veriden seçilen alanın ham place kayıtları saatler içinde indirilebilir; ama yararlı katalog için kategori, geometri, açık/kapalı, tekrar ve popülerlik temizliği gerekir. İlk pilot kalite hedefi **200–500 yayımlanabilir mekân**; gerçek ham kayıt miktarı ve kapsama oranı ancak İstanbul bölgesel çekimiyle ölçülecek. Bu 200–500 bir üretim hedefidir, iddia edilen kaynak sonucu değil.

**Etkinlik verimi formülü:** `4 haftadaki doğrulanmış yeni occurrence ≈ aktif kaynak × haftalık hedef bölgeye uygun duyuru × 4 × tekillik oranı × doğrulama oranı`.

| Senaryo | Aktif kaynak | Kaynak başına haftalık ilgili duyuru | 4 hafta ham | Yayımlanabilir hedef* |
|---|---:|---:|---:|---:|
| Alt | 10 | 2 | 80 | 48 |
| Pilot | 30 | 3 | 360 | 216 |
| Genişletme | 60 | 3 | 720 | 432 |

\* Örnek matematik: `%75 tekillik × %80 doğrulama = %60`. Bu oranlar gerçek veriden ölçülmüş değildir. Birçok organizatör aynı etkinliği duyurabilir; aynı kaynağın hiç yeni duyuru üretmediği haftalar olabilir. İlk toplu ithalde daha önce yayımlanmış gelecek etkinlikler ayrıca eklenebilir. Eski etkinlikler canlı keşif kartlarından çıkartılır.

**Önemli:** Kaynak sayısının fazlalığı kalite göstergesi değildir. 10 yoğun, güncel ve izinli kaynak; 100 terk edilmiş siteyi geçebilir.

## VIII. İş programı (tek tam zamanlı geliştirici + AI geliştirme araçları)

| Dönem | Yapılacak iş | Çıkış kriteri |
|---|---|---|
| Gün 1–3 | Kaynak sözleşmesi; 3–5 basit kaynaktan PoC; Overture bölgesel çekim | Kaynak URL → normalize edilmiş kayda tekrarlanabilir dönüşüm |
| Hafta 1 | Source Registry, basit API/RSS/ICS/JSON-LD adaptörleri, 10–15 **kolay** kaynak hedefi | En az 3 kaynak türü, test ve hata kaydı |
| Hafta 2 | PostGIS, entity matching, kanıt modeli, idempotency, basit arayüz ve ilk yayın | 20–30 kaynak **ancak çoğunluğu basit kaynaksa**; ilk kalite örneklemi |
| Hafta 3–4 | Cron/Queue, değişim takibi, cancellation, adaptif schedule, MiMo belirsizlik araçları, kaynak gözlem paneli | 7 gün kararlı çalışma ve elle denetlenebilen veri |
| Hafta 5–6 | KEP keşif/sohbet entegrasyonu, takip/Web Push, kaynak kalitesi ve günlük maliyet panosu | Kapalı pilotta kullanıcı soruları doğrulanmış veriyle yanıtlanıyor |
| Hafta 7–10 | Kritik kaynaklar için browser fallback, hata kurtarma, insan inceleme akışı, yük testi, izin denetimi | Stabil pilot ve gerçek zaman/güvenilirlik ölçümü |

**Karmaşıklık katsayısı:** API/RSS/ICS kaynağı ~1–3 saat; yapılandırılmış HTML/JSON-LD ~0,5–1 gün; dinamik JavaScript/browser ~1–3 gün veya daha fazla. Bunlar önceden genel adaptörler geliştirilmişse kaynak başına tahminlerdir; izin engeli olan bir kaynak için süre yerine 'entegre edilmeyecek' kararı çıkabilir. Çok sayıda dinamik kaynak, 10 haftalık hedefi uzatır.

## IX. Kalite kapıları (pazarlık konusu olmayan ölçüm)

**Gate 0: Kaynak gerçekliği.** İlk 10 kaynağın erişimi, lisansı, formatı ve haftalık uygun duyuru sayısı elle denetlenir. Çıkan oranlar tahminleri günceller, mimariyi değiştirmez.

**Gate 1: İşleyen Radar.** 7 günlük koşuda en az 10 kaynak; başarılı otomatik kontrol oranı `≥ %95` (planlı ve izinli çağrılar için), sıfır yetkisiz erişim, tekrar çalıştırmada mükerrer veri eklenmemesi.

**Gate 2: Veri kalitesi.** Rastgele seçilen 100 yayımlanabilir olay/olgu üzerinde en az `%95 doğru temel alanlar` hedefi; kritik tarih ve mekân hatası varsa kayıt saklanır fakat doğrulanmış etiket verilmez. Hatalı kayıt kullanıcıya iletilmişse düzeltme kaydı üretilir.

**Gate 3: Yaşayan semt.** Kullanıcıya açık her pilot semtte ileriye dönük en az 30–50 yararlı etkinlik/deneyim kartı veya mekân keşif alternatifi (salt statik POI sayısı tek başına kapıyı geçirmez); boş bölgede kapsam genişletme yok.

**Gate 4: Ekonomi.** Ölç: 1.000 fetch başına yeni doğrulanmış bilgi, doğru kayıt başına maliyet, MiMo çağrısı/changed page oranı, model ve browser maliyeti, insan doğrulama dakikası, kaynaktan kullanıcıya yayın gecikmesi. Eşik aşımlarında iş sıklığı düşürülür veya kaynak kapatılır.

## X. Pilot işletme maliyeti: çerçeve, kesin fatura değil

**Resmî kamuya açık 10 Ekim 2026 fiyatlarından örnek:** Cloudflare Workers Paid asgari **$5/ay**, Supabase Pro **$25/ay**. Browser Run ücretli planda **ayda 10 saat dahil**, ardından **$0,09/saat**; ücretsiz planda **günde 10 dakika**. Cloudflare Queues, Workers Free planında **10.000 operasyon/gün**, Paid planında **1 milyon operasyon/ay dahil**. Bunlar paket sınırlarıdır, ek kullanım/hesap bazlı koşullar ayrıca değerlendirilir.

**MiMo v2.6 Flash (yurt dışı, pay-as-you-go, örnek):** giriş **$0,14/1M token**, çıkış **$0,28/1M token**. Batch API için sırasıyla **$0,07 / $0,14**. Model sürümü değişebilir; birim fiyat konfigürasyondan yönetilir.

**Toplama senaryosu:** 30 kaynak × günde 4 kontrol × 30 gün = **3.600 kontrol/ay**. `%8 değişiklik` varsayımı ile ~288 değişen kaynak sonucu; bunların `%20'si belirsiz` ise ~58 MiMo çağrısı. Çağrı başına 3.000 giriş + 1.000 çıkış tokenı kullanılırsa salt model ücreti yaklaşık **$0,04/ay**. Bu hesap yalnızca belirlenen belirsizlik çağrılarının çıkarım maliyetidir. Playwright, web araması, ek model adımları, iş gücü ve token çıktısının büyümesi dahil değildir.

**Kullanıcı sohbet örneği:** Ayda 5.000 yanıt; yanıt başına 3.000 input + 700 output token varsayımında salt MiMo Flash token bedeli yaklaşık **$3,08/ay**. Araç aramaları, muhakeme adımları, tekrar denemeler ve kaynak getirmenin maliyeti eklenir.

**Pilot nakit hedefi:** Ek ücretli veri API'si olmadan ve ücretsiz dahil kullanım kotaları içinde yaklaşık **$35–100/ay teknik harcama bandı** bir bütçe hedefidir; güvence değil. Personel, telif/lisans, hukuk, manuel doğrulama, alan adı, ek veri depolama ve servis aşımları hariç. Esas pahalı kalem veri kalitesi operasyonu olabilir.

## XI. Güvenlik / veri hakları / operasyon

- Sadece izinli ve belgelenmiş kaynaklar. `robots.txt` yanında ilgili lisans, kullanım ve API koşullarını incele; anti-bot aşma yok.
- URL allowlist, iç ağ IP'sine/metadata adreslerine erişim engeli (SSRF), düşük ayrıcalıklı browser oturumu, otomatik sosyal yorum/gönderi yok.
- Kaynaktan gelen bütün metinler **güvenilmeyen veri**; içerikte yazan talimatlar ajan komutu sayılmaz. MiMo'nun kullanabileceği araçlar izinli, deterministik ve loglu.
- İçerik kaynağı, zaman ve lisans bağlamından koparılmaz. Telifli görselleri/videoları kopyalayarak kalıcı KEP arşivi oluşturma yok.
- Instagram'ın yaygın bölgesel paylaşım arşivine sınırsız erişimimiz yok. YouTube'un veri saklama ve türetilmiş metrik şartları var. Sosyal veriler için varsayılan sonuç 'bağlantılı sinyal', insanı takip eden gizli profil değil.
- KEP PULSE sayıları 'sosyal hareketlilik', 'trafik' ve 'fiziksel doluluk' etiketleriyle ayrı gösterir. Fiziksel yoğunluk erişimi yoksa tahmin uydurmaz.
- KEP kullanıcılarının konum ve sohbet hafızası işletmelerin gözlem kayıtlarına aktarılmaz; ayrı izinler, saklama süresi, silme ve izlenebilir erişim kontrolleri.

## XII. 90 günlük değişiklik disiplini

**İlk 30 gün:** Çekirdek altyapı, 10–30 kaynak; gerçek kaynak verimi ölçümü. Başarı: doğru kayıtların oluşması, maliyetin izlenmesi.

**31–60 gün:** 30–50 kaliteli kaynak, kontrol aralıklarını optimize etme, MiMo sohbeti ve takip entegrasyonu. Başarı: yaşayan pilot bölgeler ve hataların hızla düzeltilmesi.

**61–90 gün:** 7/30 günlük kararlılık incelemesi, kaynak ve kullanıcı katkısı karşılaştırması, yeni semt için karar. Mimari değişikliği değil ölçülmüş parametre ayarı esas.

**90 günde bir karar dosyası:** `KEEP` / `TUNE` / `REPLACE`. Yalnızca kanıtlanmış maliyet veya kalite başarısızlığında adaptör/sağlayıcı değiştirme. Çekirdek veri sözleşmesi değişecekse göç planı, çift okuma, test ve geriye dönüş yolu gerektirir.

## XIII. İlk gerçek deneyin talimatı

1. Yetkisi kontrol edilmiş **10 kaynak** belirle: beş etkinlik takvimi, iki müzik/kültür mekânı, iki restoran veya yerel hizmet kaynağı, bir sosyal/YouTube kaynağı (API koşullarına uygun).
2. 7 gün boyunca kaynak başına `fetch_count`, `changed_count`, `candidate_count`, `unique_count`, `verified_count`, `wrong_count`, `manual_review_minutes`, `MiMo_tokens`, `fetch_duration_ms` tut.
3. Aynı anda bölgesel Overture Places çekimi yap; kayıt sayısı, coğrafi isabet, mükerrerlik ve kullanılabilirlik oranını ölç.
4. Gerçek verimle 30/50 kaynak projeksiyonunu tekrar hesapla; mimariyi değil hedef sayıları güncelle.
5. Kaynak başına 'değer puanı' = **doğrulanmış yeni bilgi / (istek + model + browser + insan zamanı maliyeti)**. Zayıf kaynakları yavaşlat veya kaldır.

**Son hüküm:** KEP'i baştan dev bir AI internet gezgini olarak değil, **küçük, güvenilir, ucuz ve kendini güncelleyen bir şehir bilgi sistemi** olarak inşa et. Ajanlar çekirdeği besler, çekirdek MiMo'yu besler, MiMo kullanıcıyla konuşur. Bu katman sınırı v1.0 için sabittir.

---

### Resmî dayanaklar ve kontrol bağlantıları

- Overture Places ve bölgesel veri indirme: https://docs.overturemaps.org/guides/places/ ve https://docs.overturemaps.org/getting-data/
- Overture kaynak lisansları: https://docs.overturemaps.org/attribution/
- Google Event/JSON-LD alanları: https://developers.google.com/search/docs/appearance/structured-data/event
- Cloudflare Cron: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Queues: https://developers.cloudflare.com/queues/platform/pricing/
- Cloudflare Browser Run fiyatları: https://developers.cloudflare.com/browser-run/pricing/
- Cloudflare Workers fiyatları: https://developers.cloudflare.com/workers/platform/pricing/
- Supabase fiyatları: https://supabase.com/pricing
- Xiaomi MiMo API fiyatları: https://mimo.mi.com/docs/pricing
- YouTube API kullanım, saklama ve türetilmiş metrik politikaları: https://developers.google.com/youtube/terms/developer-policies ve https://developers.google.com/youtube/terms/developer-policies-guide
- İstanbul İBB Kültür etkinlik örneği (izin/kullanım koşulu ayrıca incelenmeli): https://kultursanat.istanbul/etkinliklerimiz
