# ADR-0034: KEP Core'u kademeli olarak Rust'a taşı, Python laboratuvarı referans kalsın

**Durum:** Önerilen (draft PR incelemesine açık)
**Tarih:** 2026-10-18
**İlgili:** ADR-0001 (araştırma çekirdeği), ADR-0025 (temporal kernel), ADR-0028 (test değeri önce ölçülür)

## Bağlam

KEP Core v0.3, `labs/core` altında bağımlılıksız bir Python laboratuvarıdır: 34 `kepcore` modülü (~7.300 satır), 43 test dosyasında ~880 test, 34 script ve 14 benchmark. Kodun büyük kısmı ürün çekirdeği değil, araştırma ve denetim altyapısıdır (Overture/GERS arşivleri, kör inceleme, kalibrasyon, ön kayıtlı deneyler).

Hedef ürün native iOS/Android uygulamasıdır. Çekirdek karar mantığının (sorgu kapıları, açık/kapalı durumu, alan tazeliği, uzlaşma, model sınırı) cihazda ve sunucuda aynı kodla, tip güvenli ve öngörülebilir çalışması isteniyor. Rust bu hedefe uygun: tek çekirdek, iOS/Android'e FFI (UniFFI) ile, sunucuya CLI/servis olarak bağlanabilir.

Risk şu: Python laboratuvarındaki her sonuç, ön kayıt ve sabitlenmiş hash bugünkü Python davranışına bağlı. Toplu yeniden yazım bu kanıt zincirini koparır.

## Karar

1. **Python laboratuvarı referans uygulama olarak kalır.** Hiçbir Python modülü bu ADR ile silinmez veya dondurulmaz. Bir davranış farkı çıkarsa, aksi yeni bir ADR ile kararlaştırılmadıkça hata Rust tarafındadır.
2. **Yalnız ürün çekirdeği Rust'a taşınır, modül modül.** Araştırma, deney, benchmark ve denetim kodu Python'da kalır.
3. **Her port, Python'un ürettiği denklik vektörleriyle doğrulanır.** Python bir girdi kümesini çalıştırıp beklenen çıktıları JSON olarak yazar; Rust aynı dosyayı okuyup birebir aynı sonucu üretmek zorundadır. CI hem Rust testlerini çalıştırır hem de vektörlerin güncel Python çıktısıyla aynı olduğunu (drift) kontrol eder.
4. **Davranış değişikliği önce Python'da yapılır** (test ile), vektörler yeniden üretilir, sonra Rust güncellenir. Rust'ta Python'da olmayan yeni karar özelliği eklenmez.
5. ADR-0028 ile uyumlu olarak test sayısı hedef değildir: vektör girdileri mevcut testlerin girdilerinden ve küçük, açıklanmış ızgaralardan türetilir; yeni karar testi ancak kapsanmayan önemli bir hata için eklenir.

## Kapsam

**Rust'a taşınacak (ürün çekirdeği):**

| Faz | Python modülü | Rust karşılığı |
|---|---|---|
| 0 | `core.stable_hash`, `availability.py` (`minute`, `intervals`, `opening_status`, `field_is_fresh`) | `kep-canon`, `kep-core::availability` |
| 1 | `core.py` (`dt`, `fold`, `haversine_km`, `Query` doğrulama, `candidate_gate`, `decide`, `reconcile_claims`, `check_model_selection`, katalog normalizasyonu) + `query.py` | `kep-core`, `kep-cli` (`kep-query`, `query.py` ile aynı JSON giriş/çıkış) |
| 2 | `model_boundary.py`, `scheduler.py`, `store.py` (SQLite outbox), `radar.py` politika kapısı (ağ istemcisi hariç) | `kep-core`, `kep-store` |
| 3 (koşullu) | `temporal_pipeline.py`, `budgeted_verify.py`, `adaptive_trust.py`, `evidence_lab.py` matematiği | ayrı ADR ile, yalnız ürün runtime'ına girerlerse |

**Python'da kalacak (araştırma laboratuvarı):** `benchmarks/`, `scripts/`, tüm Overture/GERS modülleri, `calibration.py`, `audit_sampling.py`, `review_intake.py`, `field_pilot.py`, `scout*.py`, `preferences.py` deneyleri, raporlar ve ön kayıt protokolleri. Özellikle tohumlu örnekleme (`random.Random`, Mersenne Twister) Python'da kalır; port edilirse ön kayıtlı tohum replay'leri bozulur.

## Workspace yapısı

```
rust/
  Cargo.toml              # workspace, edition 2024, MSRV sabit
  crates/
    kep-canon/            # Python json.dumps(sort_keys, ensure_ascii=False, separators=(',',':')) ile bayt-bayt aynı kanonik JSON + SHA-256
    kep-core/             # availability, gate, decide, reconcile; I/O yok
    kep-cli/              # kep-query (Faz 1)
  parity/
    export_vectors.py     # labs/core'u çalıştırıp vektörleri yazar (Python referans)
    *.json                # denklik vektörleri, commit'li
.github/workflows/rust-core.yml            # fmt, clippy -D warnings, test, vektör drift kontrolü
```

**Bağımlılık ilkesi:** Coğrafi işler için georust ekosistemi kullanılır: mesafe ve koordinatlar için `geo` (`Haversine`, yarıçapı Python'daki 6371.0088 km ile aynı), GeoJSON için `geojson`. Zaman için `chrono` + `chrono-tz`, hash için `sha2`, JSON için `serde_json`, Unicode için `unicode-normalization`. Python'un `haversine_km` koordinat doğrulaması (sonlu değer, enlem/boylam aralığı) `geo` çağrısından önce Rust'ta aynen korunur; `geo` sonucu vektörlerle `round(x, 4)` düzeyinde eşleşmek zorundadır.

Bu Rust kararı yalnız KEP içindir; başka projelere emsal oluşturmaz.

`rust/` kök dizinde ayrı tutulur; `labs/core` altında hiçbir dosya değişmez ve mevcut Python CI'ı olduğu gibi kalır. Mobil bağlama (UniFFI) ve sunucu servisi bu ADR'ın kapsamı dışındadır.

## Bilinen denklik riskleri

- **Kanonik JSON ve hash:** Python float yazımı (`1e-05`, `1.0`, `-0.0`), int/float ayrımı ve `ensure_ascii=False` birebir taklit edilmeli; aksi halde `source_record_hash` ve `value_hash` değişir. `kep-canon` bunun için ayrı crate ve ayrı vektör setidir.
- **Saat dilimleri:** `zoneinfo` sistem tzdata'sını, `chrono-tz` 0.10.4 kendi gömülü 2025b sürümünü kullanır; DST sonuçları bu iki kaynağa bağlıdır ve ileride bir tz kuralı değişirse denklik açıklamasız kırılabilir (o zaman `chrono-tz` güncellenir ya da vaka çıkarılır). Vektörler Europe/Istanbul ve kurallarıyla oturmuş birkaç DST'li bölgeyle sınırlı tutulur. Python'un tanıyıp tanımadığı da ortama bağlıdır: Ubuntu eski takma adları (`US/Eastern`, `Turkey`, `GB` …) ayrı `tzdata-legacy` paketine taşıdığı için CI'daki referans bunları `UNKNOWN` sayar. Rust bu 101 takma adı açıkça reddeder; Python bunları tanıyan bir ortamda çalışsa bile Rust "bilinmiyor" der, yani fark hep güvenli yöndedir.
- **ISO tarih ayrıştırma:** `datetime.fromisoformat` (3.11+) çok gevşektir (herhangi bir ayırıcı karakter, hafta tarihi, temel biçim). Rust yalnız açıkça yazılmış bir alt kümeyi kabul eder; Python'un kabul edip Rust'un reddettiği biçimler `KNOWN_GAPS` listesinde gerekçesiyle durur. Bu farklar hep "taze değil" yönündedir, yani güvenli tarafta kalır.
- **Mesafe:** `geo::Haversine` ile Python formülü aynı yarıçapı kullanır ama işlem sırası farklı olabilir; son basamak farkları vektörlerle ölçülür, `OUTSIDE_RADIUS` sınırındaki durumlar ayrıca vektörlenir.
- **Yuvarlama ve Unicode:** `round(x, 4)` (doğru yuvarlanmış ondalık) ve `fold()` içindeki NFD normalizasyonu ayrıca vektörlenir.

## Faz 0 bulguları

İlk port Python referansında iki tuhaflık ortaya çıkardı. İkisi de kuralına uygun şekilde önce Python'da düzeltildi (#47), vektörler yeniden üretildi, Rust da ardından aynı davranışa çekildi:

- `availability.minute` Python'un `int()` gevşekliği yüzünden `" 9:30"`, `"+9:30"`, `"09: 5"` ve Arapça-Hint rakamlı `"٠٩:٣٠"` değerlerini geçerli saat sayıyordu. Artık her iki tarafta tam iki ASCII rakam gerekiyor; Unicode rakam farkı da kalmadı.
- `field_is_fresh` bozuk kanıtta (`source_observed_at` eksik canlı kayıt, string olmayan `observed_at`/`valid_until`, liste tipinde `status`) karar ortasında çöküyordu; `0` gibi falsy bir `valid_until` ise "son tarih yok" sayılıyordu. Artık hepsi "taze değil".

## Faz 1 durumu

`core.py` ve `query.py` taşındı (`kep-core::{catalog, query, decision, distance, text}`, `kep-cli`). Python'un ürettiği ~380 karar vakası, katalog normalizasyonu, sorgu doğrulama, uzlaşma ve model koruması Rust'ta birebir tutuyor; `kep-query` örnek sorgularda `query.py` ile bayt bayt aynı çıktıyı veriyor.

- **Mesafe:** `geo::Haversine` 200 bin rastgele nokta çiftinde Python'la `round(d, 4)` düzeyinde %100 aynı, ham değerde ise ~%70 bit-bit aynı (son bit farkı). Yarıçap karşılaştırması ham mesafeyle yapıldığı için sınırdan bir ulp uzaklıktaki bir kayıt iki tarafta farklı karar alabilir; pratikte ihmal edilebilir, vektörlerde 1 km sınırının iki yanı ayrıca sınanıyor.
- **İstanbul saatleri:** Python aynı `tzinfo`'yu paylaşan iki zamanı duvar saatine göre karşılaştırır ve çıkarır, DST boşluğundaki naif saati de olduğu gibi tutar. Rust `IstDateTime` aynı kuralı izler (2016 öncesi geçiş anları dahil); başka bölgelerle karşılaştırmada Python'un `utcoffset()` değeri kullanılır.
- **Sorgu tipleri:** Python `Query` tip kontrolü yapmaz (ör. `limit: true` geçer); Rust yanlış tipli alanları `TypeError` ile reddeder.

## Faz 2 durumu

`model_boundary.py` ve `scheduler.py` taşındı (`kep-core::{model_boundary, scheduler}`). Model bağlamı (anahtar sırası ve `snapshot_hash` dahil), yapılandırılmış yanıt doğrulaması ve `due_sources` sıralaması Python vektörleriyle birebir. `SourceClock` alanlarında Rust, `Query`'deki gibi yanlış tipleri `TypeError` ile reddeder: Python tip denetlemediği için `approved: 1`, `elapsed_hours: true` ya da sayısal `source_id` orada planlanır, Rust'ta reddedilir (kapalı başarısız). `calls_today` ve `daily_cap` f64 tutulur; 2^53 üstündeki iki farklı tamsayı eşit görünür ve Rust kaynağı atlar, bu da güvenli yöndedir ve pratikte ulaşılamaz. `store.py` de `kep-store` olarak taşındı (paketli SQLite, `rusqlite`). Şema birebir aynı, bu yüzden iki taraf birbirinin dosyasını açabilir; 22 senaryoda her işlemin sonucu ve tabloların son içeriği (saklanan JSON metni dahil) bayt bayt Python'la aynı. Rust `id` alanında yalnız metin, `source_*` alanlarında metin veya null kabul eder; Python'un sqlite3 bağlaması başka skalerleri metin olarak saklardı. `radar.py` politika kapısı da `kep-core::radar` olarak taşındı: kaynak kaydı, `_public_https` URL denetimi ve tek kontrollü yoklama (`poll`). HTTP istemcisi taşınmadı; Rust tarafı aktarımı çağırandan alır, bu yüzden çağıran bir aktarım bağlamadıkça ağa hiçbir şey gitmez. 138 vektör (URL, kaynak, kayıt dosyası ve 44 yoklama senaryosu: kota, aralık, saat geri gitmesi, 304/401/403/429, boyut sınırı, şema reddi, ağ hatası) Python 3.11, 3.12 ve 3.13'te aynı üretiliyor ve Rust'ta birebir eşleşiyor. Rust'ın bilinçli olarak daha katı olduğu yerler, hepsi kapalı başarısız olur: köşeli parantezli host reddedilir (Python 3.12+ `[v1.fe]` gibi bir IPvFuture biçimini kabul eder), kayıt alanları beyan edilen JSON tipinde olmalıdır, `rights_reviewed_at` genişletilmiş ISO tarihi olmalıdır (Python `20261010` ve `2026-W41-6` biçimlerini de kabul eder; vektörlerde bilinen fark olarak duruyor), yanıt gövdesi UTF-8 olmalıdır (Python UTF-16/32 gövdeyi ve JSON içindeki `NaN`'ı da kabul ederdi).

## Faz geçiş ölçütü

Bir faz ancak şu koşullarla tamam sayılır: vektörlerin %100'ü eşleşir, Python testlerinin tamamı yeşil kalır, Rust `clippy -D warnings` temiz, ve Python modülünde hiçbir davranış değişmemiştir.

## Geri alma

`rust/` dizini, `rust-core.yml` ve bu ADR silinir. Python laboratuvarı, testleri, arşivleri ve CI'ı hiç değişmediği için etkilenmez.
