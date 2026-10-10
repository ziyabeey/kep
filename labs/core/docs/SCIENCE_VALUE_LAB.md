# KEP SCI-001 | Bilimsel çekirdek: Kanıtın karar değeri (araştırma)

## Amaç ve kapsam

KEP'in odağı yalnız daha çok etkinlik sayfası toplamak değil, kullanıcının kararını **gerçekten değiştirecek** eksik olguyu tespit etmek. Mevcut `kepcore/core.py` üretim benzeri sert filtrelemeyi korur. Yeni `kepcore/evidence_lab.py` yalnız çevrimdışı matematiksel laboratuvardır. `HYPOTHETICAL_UNCALIBRATED_NOT_PRODUCTION_PROOF` işareti zorunludur. `LAB_ACCEPT` bir yayın yetkisi veya saha güven yüzdesi değildir.

## Çalıştır

```bash
cd labs/core
python scripts/research_intelligence.py
python -m benchmarks.evidence_value
python -m unittest discover -s tests -q
```

`research_intelligence.py` önce mevcut **gerçek kaynak alıntılarının** olduğu katalogda `500 TRY` bütçe koşuluyla bilinen fiyat bilgisi eksiklerini gösterir. Pera Müzesi'ne ait **farklı görüntülenen sürüm/önbelleklerin** fiyat değerlerini çelişki olarak korur. Sonra ayrı bir **yapay ikili doğrulama örneği** sunar. Sondaki `posterior` güncel müze fiyatı veya doğruluğu hakkında hiçbir iddia değildir.

`benchmarks.evidence_value` 3 × 4.000 = 12.000 tamamen sentetik ortamı dört araştırma politikasıyla karşılaştırır. Bütün yöntemler aynı olguları ve önceden örneklenmiş sonraki gözlemleri görür. Sadece **bir ek sorguya** izin verilir. Otomatik internet çekme veya MiMo/Haiku/Laya API'si yoktur.

## Deneyin açık varsayımları

- İkili hipotez: `olgu doğru` / `olgu yanlış`; gerçek olayların tarih/fiyat/kategori gibi çok değerli alanları için doğrudan kullanılamaz.
- Kaynaklar yalnız **publisher_root farklıysa** bağımsız kabul edilir. Kaynak hata oranı ve önsel doğruluk **simülatörce sağlanır**; gerçek kaynak kalibrasyonu yoktur.
- Ödül: doğru kabul `+1`; yanlış kabul `-4`; ertele `0`; doğrulama sorgusunun tasarlanmış maliyeti bu skordan düşülür. Dolar değil.
- `matched`: varsayımlar doğru; `source_degradation`: gerçek kaynak güveni modelin sandığından %22 puan daha düşük; `prior_shift`: gerçek görülme oranı tahmin edilen önselden farklı.
- Maliyet değeri ve kaynak kalitesi, yukarıdaki göreve göre elle belirlenmiş deney parametreleri; gerçek dünya test sonucu değildir.
- Kaynak tekrarları bağımsız kanıt sayılmaz. Daha yüksek bir kopya-skoru, asıl kaynak sahibinin yerini alamaz.

## Kısa sonuç (2026-10-11, sabit seed)

| Rejim | Sorgusuz net fayda | Her seferinde maksimum bilgi sorgulaması | EVSI net fayda | EVSI sorgu oranı | EVSI yanlış kabul / kabul |
|---|---:|---:|---:|---:|---:|
| Uyumluluk | 0.23375 | 0.37375 | **0.40749** | 0.6185 | 0.02364 |
| Kaynak güveni bozulması | 0.00975 | −0.00225 | **0.04698** | 0.6765 | 0.15202 |
| Önsel kayması | 0.14975 | 0.33750 | **0.35643** | 0.6350 | 0.03429 |

**Sınırlamalar:** Bunlar üretilmiş olgular ve seçilmiş deney fayda fonksiyonu üzerinde karşılaştırmadır. Kaynak güveni bozulduğunda EVSI'nin sorgusuz yönteme farkının 95% *simülatör koşullu* bootstrap aralığı **sıfırı kapsıyor**. Yani bu stres rejiminde kazanç kesin değil. İncelemesiz gerçek fiyat/iptal yayını yapılamaz. Gerçek İstanbul kullanıcılarına, rakiplere veya akademik yöntemlerin birebir başarı oranlarına genellenmez.

## Canlı kullanıma geçişten önce kanıt kapıları

1. **Etiketli veri**: Her kaynak + alan türünde tarihsel `doğru / yanlış / eksik / değişti` olayları, kaynağın görebildiği anda dondurulmuş sürümle birlikte.
2. **Kaynak kökenleri**: Ana organizatör, bilet satıcısı, basın bülteni ve kopya yayının açık eşlemesi. Çift sayım önlenmeli.
3. **Kalibrasyon**: Gerçek zaman sıralı kalibrasyon/test ayrımı; doğruluk kalibrasyonu, risk-kapsama eğrisi, güven aralıkları ve bozulma/drift alarmı.
4. **Bağımsız referans**: Eşit sorgu/kanıt/bütçede deterministik filtre, hep sorgula, basit önem sırası ve deneysel EVSI; sorumlu insan incelemesi.
5. **Güvenlik/lisans**: Hakları onaylı kaynak, düşük ayrıcalıklı tarayıcı, robot/koşul uyumu. Sayfadaki talimatlar veri kabul edilir.
6. **Maliyet**: Deneysel utility maliyetleri gerçek API tokenları, görev süresi ve kaynak bakımına bağlanmadan ROI konuşulmaz.

## Sonraki bilimsel deney

**KEP-SCI-002: Kalibre Edilmiş Alan Kanıtı**. İzinli bir İstanbul kaynağındaki tarih/saat/iptal alanlarında en az iki tarihli gözlem ve bağımsız insan doğrulaması biriktir. Bu verilerle risk-kapsama eğrisi ölç, ardından bilgi kazanımıyla gerçek maliyet karşılaştırmasına geç. Önceki toplu veride henüz bu veri **yok**.

## Literatür notu

- ICML 2026, Deng vd. goal-oriented information gain ile soru sorma (bu repo aynı RL eğitimini yapmıyor).
- UAI 2026, Jin vd. kalibre edilmiş olasılıksal fusion ile LLM semantic çıkarımını ayırıyor (bu repo kalibrasyon yöntemlerini henüz uygulamıyor).
- ICML 2026, Wang vd. LEC marginal seçici risk kontrolü sunuyor (bu repo sonlu örnek risk garantisi vermiyor).
- ICML 2026, Kobayashi vd. active feature acquisition ve belirsizlik ölçümü araştırıyor (bu repo yalnız myopic EVSI).

Bağlantılar için [ADR-0004](../../../docs/adr/0004-information-value-research-gate.md) ve [benchmark protokolü](../benchmarks/evidence_protocol.json).
