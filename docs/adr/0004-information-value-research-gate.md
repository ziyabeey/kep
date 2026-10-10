# ADR-0004: KEP SCI-001, hedefli kanıt araştırması ve riskli kararın ertelenmesi

**Durum:** Kabul için PR; araştırma ortamı dışına yetki verilmedi  
**Tarih:** 2026-10-11  
**İlgili:** ADR-0001 (araştırma çekirdeği), ADR-0002 (kaynak izinleri), ADR-0003 (Browser Scout)

## Problem

Kaynakta bir etkinlik hakkında bilgi eksikse üç kötü seçenek vardı: doğrudan öner, her şeyi tekrar tara veya hiç önerme. Bunlar özellikle bütçe/saat/iptal gibi karar değiştirici alanlarda pahalı ya da güvensiz olabilir. KEP'in yeni araştırma sorusu: **Bir doğrulama adımı, beklenen karar faydasını maliyetinden fazla artırıyor mu?**

## Tez – antitez – sentez

- **Tez:** Daha çok araştırma, daha doğru karar getirir. Sorun: bilgi kazanımı karar faydasına eşit değildir; kaynaklar birbirini kopyalayabilir.
- **Antitez:** Sadece sabit kurallar ve otomatik ret kullan. Sorun: gereksiz erteleme veya kaçırılan geçerli etkinlikler.
- **Sentez:** Üretimde sert hak/tarih/bütçe/izin kapıları sabit kalsın. Araştırma laboratuvarında bağımsız kanıt için **tek adımlık beklenen karar değeri (EVSI)** hesaplayıp ek araştırmayı deneylerle karşılaştır.

## Matematik

İkili bir olgu `H` için hipotezsel önsel `p`, ve bağımsız kaynaklara ait hata oranları verildiğinde:

- `P(H | evidence)` Bayes formülüyle hesaplanır, **sadece sentetik veya dışarıda kalibre edilmiş koşullarda**.
- `U(kabul | p) = p × iyi_sonuç_ödülü - (1-p) × yanlış_kabul_cezası`.
- `U(ertele) = 0`.
- `EVSI = E_olası_yanıtlar[max U(yanıt sonrası)] - max U(şimdi)`.
- `Net değer = EVSI - kanıt sorgu maliyeti`.

Model: bir sorgu hakkı, sabit denemelik maliyet/yarar birimleri; kullanıcıya ücret veya gerçek olasılık verilmez. Bilgi kazanımı (Shannon entropy) yalnız karşılaştırma kontrolüdür.

## Kararlar

1. `kepcore/evidence_lab.py` **araştırma-only**. `LAB_ACCEPT` hiçbir koşulda `verified`, kullanıcı bildirimi veya tüketici yayını demek değildir.
2. `candidate_gate` ve kaynak erişim/lisans kontrolleri tarafından reddedilmiş olaylar, Bayes skoru yüksek diye geri dönemez.
3. Bağımsız yayıncı kökü bir kez sayılır. Aynı içeriğin kopyası güveni artıramaz. Önceden denetlenmiş asıl kaynak, türetilmiş gönderinin 'daha güvenilir' sayı iddiası yüzünden geçersizleştirilemez.
4. Aynı kökten çelişkili işaretler otomatik çözümlenmez; `HUMAN_REVIEW`.
5. `field_research_tasks` yalnız gerekli eksik alanları önerir; ağ isteği, tarayıcı veya model çalıştırmaz.
6. Kaynak duyarlılığı/özgüllüğü ve önsel olasılıklar için henüz **gerçek ölçüm yok**. Bunlar uydurularak canlı veriye uygulanamaz. Deney protokolünde belirtilen kalibrasyon veri kümesi oluşturulmadan üretim rotasına bağlama.
7. Araştırma maliyeti normalleştirilmiş ödül birimidir; `$`, token veya çalışan zamanı olarak etiketlenemez.
8. Gerçek saha performansı, kalibrasyon, drift ve yasal veri kullanım hakkı sağlanmadan **rakiplerden iyi** denmez.

## Başarılı ve başarısız karşı koşullar

Sentetik testte veri üretimiyle model varsayımları uyuşuyorsa EVSI fayda üretebilir. Kaynak hata oranları kötüleşince false accept artabilir; özellikle kötüleşme durumunda sistem kendi hatasını fark etmeyebilir. Bu yüzden örneklem kaydırma/drift testleri zorunlu ve regresyon kapısıdır. Mevcut sonuçlar bilimsel yöntem gösterimidir, gerçek saha kanıtı değildir.

## Kanonik değişiklik sınırı

Yeni kanıt denklemleri ve kaynak tahminleri **KEP Core üretim veri sözleşmesini değiştirmez**. MiMo/Laya/Ajanlara yeni veri toplama yetkisi açmaz. Ayrı karşılaştırma ve veri kalibrasyonu olmadan karar sistemi yer değiştirmez. Geri dönüş: `evidence_lab` ve bilimsel benchmarkı kaldır; mevcut karar motoru etkilenmez.

## Akademik dayanaklar (uyarlama, algoritma replikasyonu değil)

- [Deng ve ark., ICML 2026, Uncertainty-Aware Clarification](https://proceedings.mlr.press/v306/deng26l.html)
- [Jin ve ark., UAI 2026, PRISM](https://proceedings.mlr.press/v337/jin26a.html)
- [Wang ve ark., ICML 2026, LEC selective risk control](https://proceedings.mlr.press/v306/wang26a.html) (risk garantisi **uygulanmadı**)
- [Kobayashi ve ark., ICML 2026, Learning-to-Measure](https://proceedings.mlr.press/v306/kobayashi26a.html) (aktif özellik kazanımına araştırma yönü)
- [Lee ve ark., Ağustos 2026 ön yayın, When Offline Evaluation Misleads](https://arxiv.org/abs/2608.11560) (offline ödül yanılsamalarına uyarı)
