# KEP-DATA-018 · Üçüncü gerçek Overture sürümü (Ekim 2026)

Durum: **hazır, çalıştırılmadı.** Overture takvimi (18 Ekim 2026'da okundu) bir sonraki sürümü `2026-10-21.0` olarak planlıyor; şema sürümü henüz açıklanmadı. Bu çalışma için hiçbir veri indirilmedi. Karar ve sınırlar: [ADR-0032](../../../docs/adr/0032-third-overture-release-preregistration.md).

## Ne ölçülecek (ön kayıt)

Protokol [`sources/overture_third_release.json`](../sources/overture_third_release.json) dosyasında, veri yokken donduruldu. SHA-256 değeri kodda sabit; sonradan değiştirilirse testler kırılır.

| Kod | Soru |
|---|---|
| M1 | Ağustos'ta olup Eylül'de kaybolan 69 kaydın kaçı Ekim'de geri geliyor? |
| M2 | Eylül'de yeni görünen 222 kaydın kaçı Ekim'de yine kayboluyor? |
| M3 | Eylül→Ekim ardışık kaynak farkı (ekleme, çıkma, alan, confidence) |
| M4 | İlk adımda alanı değişen kayıtlar ikinci adımda da değişiyor mu? |
| M5 | Confidence'ı 0,05'ten fazla oynayan kayıtlar ters yöne dönüyor mu? |
| M6 | Hücrelerdeki yerel ekleme/çıkma, resmî GERS changelog'unun bölgesel satırlarıyla uyuşuyor mu? |

Hepsi iki sabit örnekleme hücresinde **kaynak kayıt** ölçümüdür. Geri gelen kayıt "yeniden açılan işletme" değildir; çıkan kayıt "kapanan işletme" değildir. M6 yalnız Ekim'in STAC önceli `2026-09-23.1` ise ve seçilen bütün satır grupları okunduysa hesaplanır. Aksi halde M6 değeri `null` olur; Places karşılaştırması yapıldıysa `regional_gers.status` her zaman nedenini söyler (`ABSTAIN_GERS_CAPTURE_MISSING`, `ABSTAIN_GERS_CAPTURE_INVALID`, `ABSTAIN_INCOMPLETE_CAPTURE`, `ABSTAIN_REQUIRES_INTERMEDIATE_RELEASE` ya da `ABSTAIN_CONFLICTING_OFFICIAL_ROWS`).

Bir GO/NO-GO kapısı ya da birincil metrik yok: DATA-008…017 gibi bu da betimleyici bir kaynak çalışması ve sonucuna bağlı bir ürün kararı yok (protokolde `decision_gate`). M5'te farklar önce 9 basamağa yuvarlanır; tam 0,05'lik bir oynama hiçbir yönde sayılmaz.

## Sürüm çıkınca ne yapılacak

1. Sürüm notlarından şema sürümünü öğren (ör. `v2.0.0`). STAC kataloğunda `schema:version` varsa iş bu değeri de okur; girdiğin değer onunla çelişirse Places verisi okunmadan durur. Girdiğin değer makbuza yazılır ve sonraki offline çalıştırmalarda değiştirilemez.
2. GitHub → Actions → **Overture third release capture (manual research, KEP-DATA-018)** → Run workflow, `main` dalı:
   - `research_confirmation`: `RESEARCH_ONLY` (başka bir metin yazılırsa iş kırmızı biter, hiçbir şey okunmaz)
   - `release`: STAC'te görünen tam kimlik (planlanan `2026-10-21.0`)
   - `publisher_schema_version`: 1. adımdaki değer
3. Bu iş **Kasım sürümü (planlanan 2026-11-18) STAC'te latest olmadan önce** çalışmalı. Sonra çalışırsa STAC kontrolü işi durdurur.
4. İş önce offline testleri çalıştırır, sonra iki hücreyi indirir, sonra 16 MiB sınırlı GERS okumasını yapar ve offline karşılaştırma raporunu üretir. Arrow ön testi ya da GERS adımı başarısız olursa, ya da GERS verisi Places verisiyle tutarsız çıkarsa, M1–M5 yine hesaplanır ve M6 nedeniyle birlikte `ABSTAIN` olur; iş yeşil biter ama bir `::warning::` satırı basar.
5. Her makbuz protokolün SHA-256 değerini (`759cb0bb…`) ve veriyi indiren kodun commit'ini taşır. Rapor bunlara `compare`'i çalıştıran commit'i de ekler (`compare_code_commit`; GitHub Actions dışında `null`), iş de iki commit'in aynı olduğunu doğrular. Başka bir protokol sürümüyle yapılmış bir capture `compare` tarafından reddedilir.
6. Raporun `status` alanı `COMPARED` değilse iş bir uyarı basar. `ABSTAIN_NORMALIZATION_REJECTED_IN_CELL_RECORDS`, yeni sürümde normalleştiricinin bazı hücre içi kayıtları reddettiği anlamına gelir (ör. yeni şema alanı). Bu durumda hiçbir metrik hesaplanmaz, çünkü düşen kayıtlar yanlışlıkla "listeden çıktı" sayılırdı. Normalleştiriciyi düzeltip Kasım sürümünden önce işi yeniden çalıştırmak gerekir.
7. Artifact 7 gün yaşar. İndirip bir takip PR'ıyla `data/real/` altına SHA-256 ile sabitlemek gerekir (Ağustos'taki gibi). İş birden fazla kez çalıştıysa takip PR'ı **bütün** çalıştırmaların artifact'ını ve run ID'lerini sabitler; içlerinden biri seçilmez.
8. Takip PR'ı CLAUDE.md'deki öğrenme defterini de yazar: gözlenen sonuç → değişen mühendislik kararı → harcanan süre → belirsiz kalan soru.

## Offline prova

Sürüm çıkmadan tüm karşılaştırma yolu sentetik bir "Ekim" ile denenebilir. Bu sentetik sürüm gerçek Eylül arşivinden türetilir ve raporda `SYNTHETIC_REHEARSAL_NOT_A_REAL_RELEASE` diye işaretlenir. Sayıları İstanbul hakkında hiçbir şey söylemez.

```bash
cd labs/core
python -m unittest tests.test_third_release -v
python -m benchmarks.third_release_rehearsal
python scripts/capture_third_release.py          # ağ kullanmaz
```

## Bilinen sınırlar

- Protokol ve analiz kodu aynı commit'te geldi; "önce protokol" sırası harfiyen uygulanmadı. Körlük, sürümün henüz yayımlanmamış olmasına dayanıyor. Veri gelmeden yapılan dört protokol sürümü ve hash'leri ADR-0032'de listeli.
- Denetim, protokolü yazan oturumda ayrı subagent çağrılarıyla yapıldı. CLAUDE.md tasarımcı ile denetçinin aynı oturum olmasını yasakladığı için birleştirmeden önce başka bir oturumdan denetim gerekiyor.
- Şema sürümü operatör girdisidir; STAC kataloğunda `schema:version` yoksa yalnız makbuza yazılır, doğrulanmaz.
- Arrow testi sıradan CI'da pyarrow olmadığı için atlanır; yalnız elle tetiklenen işte, ağdan önce çalışır.
- Plan, okunacak satır grubu sayısını 128 istek sınırına göre önceden kontrol etmez. pyarrow her satır grubu için yaklaşık 7 istek yapar, yani 18'den fazla satır grubu seçilirse okuma yarıda kalır ve M6 `ABSTAIN_INCOMPLETE_CAPTURE` olur. Eylül footer'larında yalnız 2 grup seçilmişti.
- M4 yalnız protokoldeki `m4_factual_fields` alanlarını sayar; `source_provenance` ve kategori alanları dışarıda. M3 ise mevcut DATA-010 karşılaştırıcısını kullanır, bu yüzden bir kayıt M3'te "değişti" olup M4'te sayılmayabilir.
- STAC `prev` bağlantısı gezinme kanıtıdır; changelog'un hangi tabana göre üretildiğini yayıncı imzalamaz.
- GERS okuması yalnız hücrelere dokunan satır gruplarını kapsar; hücre dışına taşınan kimlikler görünmez.
- Places ve GERS aynı yayıncıdan gelir; uyuşma bağımsız doğrulama değildir.
- `overturemaps==1.0.2` her zaman "latest" indirir; bu yüzden indirmeden önce ve sonra STAC kontrolü yapılır.
