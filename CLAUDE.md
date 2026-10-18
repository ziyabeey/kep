# KEP · Claude Code çalışma kuralları

KEP bir **araştırma laboratuvarıdır**: mobil uygulama veya canlı servis yok. Kod
`labs/core/` altında, kararlar `docs/adr/` altında. Dil: kullanıcıyla Türkçe;
kod, commit mesajı ve tanımlayıcılar repo geleneğine uyar.

## Çalıştırma

```bash
cd labs/core
python3 -m unittest discover -s tests -v   # ağ, API anahtarı veya ücretli servis gerekmez
python3 run_all.py
```

CI (`.github/workflows/core-lab.yml`) Python 3.11 ve 3.13'te çalışır; ikisinde de
yeşil olmayan iş bitmiş sayılmaz. Gerçek veri indiren workflow'lar yalnız elle
tetiklenir (`overture-*-manual.yml`); sıradan CI hiçbir zaman ağa çıkmaz.

## Değişmez sınırlar

- `source_fetches=0`, `real_human_labels=0`, `consumer_publish=false` varsayılandır.
  Kullanıcı açıkça istemedikçe yeni gerçek veri aranmaz, indirilmez, saha etiketi
  toplanmaz (2026-10-11 kullanıcı talimatı, #13'te kayıtlı).
- Sentetik sonuç gerçek İstanbul doğruluğu, işletme açılış/kapanışı veya
  kullanıcı faydası olarak raporlanmaz. Overture `confidence` doğrulama değildir.
- Özel dosyalar (seed'ler, A/B/C değerlendirici Excel'leri, `.local/`,
  `*_private/`) asla commit edilmez; `.gitignore` bunları korur.
- Arşivlenmiş gerçek veri (`data/real/`) ve donmuş protokoller değiştirilmez.
- Olumsuz sonuç (NO-GO) silinmez, yeniden yorumlanıp başarıya çevrilmez.

## Kör ön kayıt (her yeni deney için)

Bu kurallar #39 "Test Değeri Kapısı" ve ADR-0028/0030'un özetidir.

1. **Önce protokol.** `labs/core/benchmarks/<deney>_protocol.json` karar sorusu,
   karşılaştırıcılar, yeni seed, eşikler, birincil metrik ve GO/NO-GO kapısıyla
   birlikte **değerlendirici veya simülatör kodundan önce** ayrı bir commit olarak
   girer. Protokol commit SHA'sı rapora yazılır.
2. **Yeni seed.** Daha önce sonucu görülmüş bir holdout'un seed'i veya vakaları
   yeniden "holdout" sayılmaz.
3. **Sonuçtan sonra ayar yok.** Eşik, seed, maliyet katsayısı, rejim tanımı veya
   başarı kriteri sonuç görüldükten sonra değişirse bu yeni bir deneydir:
   yeni protokol, yeni seed, yeni deney kimliği.
4. **Politika görünürlüğü.** Gizli doğru etiket, rejim adı, gelecekteki olay ve
   tamamlanmamış denetim sonucu karar girdisine sızamaz; testle kanıtlanır.
5. **Ayırt edicilik pilotu.** Küçük pilotta stratejiler farklı karar vermiyorsa
   büyük benchmark'a geçilmez.
6. **Testin testi.** Yeni test yalnız ölçülmüş, yakalanmayan önemli bir kusur için
   eklenir (ADR-0028). Test sayısı başarı ölçüsü değildir.
7. **Öğrenme defteri.** Rapor şunu yazar: gözlenen sonuç → değişen mühendislik
   kararı → harcanan süre → belirsiz kalan soru.

## Roller ve görev ayrılığı

Rol tanımları `.claude/agents/` altındadır. Bir deneyde roller ayrı oturumlar
(veya ayrı subagent çağrıları) tarafından yürütülür:

| Rol | Dosya | Yapar | Yapamaz |
|---|---|---|---|
| Lider | `kep-lider` | Sıradaki deneyi seçer, ADR yazar, GO/NO-GO verir | Protokolü veya kodu kendisi yazıp kendisi onaylamak |
| Deney tasarımcısı | `kep-deney-tasarimcisi` | Protokolü ve holdout'u sonuç görmeden dondurur | Değerlendirici kodu yazmak, sonuçları görmek, denetlemek |
| Uygulayıcı | `kep-uygulayici` | Ayrı branch'te değerlendirici/simülatör kodu yazar | Donmuş protokolde eşik, seed, metrik değiştirmek |
| Bağımsız denetçi | `kep-denetci` | Sızıntı, mutant ve protokole sadakat denetimi | Aynı deneyin tasarımcısı olmak; kodu "düzeltmek" |
| Veri | `kep-veri` | Overture/GERS sürüm ve arşiv işleri | İzinsiz kaynak çekmek, arşivi değiştirmek |
| Dokümantasyon | `kep-dokumantasyon` | README, issue kutucukları, ADR numaraları | Sonuç uydurmak, bitmemiş kutucuğu işaretlemek |

**Kural:** tasarımcı ile denetçi aynı oturum olamaz. Uygulayıcının PR'ı protokol
dosyasını değiştiriyorsa denetçi reddeder.

## ADR ve kimlik numaraları

- ADR dosyaları `docs/adr/NNNN-kisa-ad.md`. Yeni numara almadan önce
  `ls docs/adr` ve açık PR'lara bakın; paralel çalışan hatlar numarayı koordinatörden
  rezerve eder. Çift numara bir kez oldu (0015 → 0033 olarak düzeltildi).
- Deney kimlikleri `KEP-<ALAN>-NNN` (ör. `KEP-OBS-001`, `KEP-DATA-017`). Aynı kimlik
  iki issue'da kullanılmaz.

## PR

Her PR: ne değişti (Önce/Sonra), protokol commit SHA'sı (deneyse), iki Python
sürümünde CI, rollback adımı. Gerçek veri veya insan etiketi içermez.
