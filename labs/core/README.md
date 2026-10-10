# KEP Core Lab v0.3

**KEP için yerel veri, güvenli aday seçimi ve gerçek geçmiş puanlarla öğrenme laboratuvarı.** Bu paket bir mobil uygulama veya tamamlanmış AI asistanı değildir. GitHub deposunda yalnızca araştırma laboratuvarıdır; canlı mobil uygulama değildir.

## Çalıştır

Python 3.10+ ve IANA saat dilimi verisi bulunan ortam:

```bash
cd labs/core
python3 run_all.py
python3 -m unittest discover -s tests -v
python3 play_preferences.py --user U1001 --method user_mean
python3 play_preferences.py --user U1001 --method item_knn
python3 query.py --query examples/galata_nearby.json
python3 query.py --query examples/galata_open_budget.json
```

Standart kütüphane yeterlidir; ağ ve model anahtarı gerekmez. Saat dilimi verisi olmayan sistemde `tzdata` kurulabilir. `scripts/fetch_open_data.py` ayrı, isteğe bağlı bir ağ aracıdır; laboratuvar bunu otomatik çalıştırmaz.

## Neler var?

- `kepcore/core.py`: sert kullanıcı kısıtları, belirsizlik ve kararlar.
- `kepcore/availability.py`: saat dilimi, tam haftalık açılış aralığı, tarih istisnası ve alan bazlı güncellik.
- `kepcore/store.py`: yerel SQLite, idempotent kayıt, eski güncelleme koruması ve outbox örneği.
- `kepcore/preferences.py`: beş klasik gerçek-puan tahmin yöntemi; uygun aday dışına çıkamayan yeniden sıralama.
- `kepcore/model_boundary.py`: MiMo/Laya için çevrimdışı yapılandırılmış çıktı sınırı. **Gerçek API istemcisi değil.**
- `benchmarks/preference_protocol.json`: eğitim/doğrulama/test yöntemi ve önceden belirlenmiş karşılaştırmalar.
- `data/raw/uci/rating_final.csv`: 1.161 gerçek tarihsel puan, 138 kullanıcı, 130 restoran kimliği. CC BY 4.0 atıflı.
- `results/preference_results.json`: bütün test tahminleri, seçilen parametreler, belirsizlik hesapları.
- `results/release_summary.json`: güncel özet.
- `docs/RESEARCH_REPORT_V03.md`: yorum, başarısızlıklar, kaynak ve sınırlar.
- `docs/LEGACY_V02_REPORT.md`: eski sürümün tarihsel raporu, yeni sonuç olarak okunmamalı.

## Başlıca sonuçlar

87 birim testi geçti. Eski 85 sözleşme durumu korunuyor. Yeni 15 tasarlanmış uç durumda eski v0.2 3/15, v0.3 15/15 verdi. Bu kümeler birim testleriyle örtüşür; toplanıp bağımsız test sayısı yapılmaz.

Gerçek puan testinde eğitim/doğrulama/test: 757/101/303. Test MAE: genel ortalama 0,6713; restoran ortalaması 0,6648; kişisel ortalama 0,5108; kullanıcı+restoran modeli 0,5138; komşuluk modeli 0,5491. **Düşük MAE daha iyidir, yüzde doğruluk değildir.** Doğrulamada seçilen komşuluk modeli testte güçlü basit yöntemlerden kötü çıktı; sonuç saklanmadı ve model otomatik olarak üretime alınmadı.

Kişisel ortalama aynı kullanıcıdaki restoranları sıralamaz; yalnız kişinin puan verme eğilimini tahmin eder. Sıralama üstünlüğü ve İstanbul kullanıcı faydası kanıtlanmadı.

## Veriyi değiştirmek ve deney yapmak

`examples/` dosyalarında tarih, bütçe, mesafe, `open_now`, `quiet` (kalabalık sinyali), `mode` ve bildirim izinlerini değiştirebilirsiniz. Tarihler açık ve sabittir; eski kaynaklar bugün geçerli sayılmaz.

`play_preferences.py`, belirlenen kullanıcı için üç saklı tarihsel puanı ve modelin tahminini ayrı gösterir. Gerçek puanlar modele eğitim sırasında verilmez. Bu ekran bugünkü restoran tavsiyesi değildir.

Kendi araştırma modeliniz için `PreferenceModel` arayüzüne yeni bir yöntem ekleyin; test bölümüne göre parametre ayarlamayın. Aynı veride defalarca geliştirme yaptıktan sonra bağımsız yeni test verisi gerekir. `benchmarks/preference_protocol.json` değişirse deney sürümünü de değiştirin.

## Sınırlar

Yeni canlı İstanbul verisi alınmadı. Eski 16 İzmir etkinliği + 7 İstanbul mekânı aynı kalır. UCI restoranları bu yerlerle eşleştirilmez. Gerçek MiMo/Laya çağrısı, mobil uygulama, doğrudan gözlenmiş kalabalık, AR-GE/bandit/RecPIE replikasyonu veya kullanıcıya gerçek öneri deneyi yoktur.

`model_boundary` yalnız yapılandırılmış alanları doğrular; serbest açıklamaların tamamının doğru olduğunu kanıtlamaz. Araştırma skorları kanıt ve kullanıcı kısıtlarının üstüne çıkamaz. Tam üretim servisi güvenlik, yük, izin ve gerçek entegrasyon testleri gerektirir.

Kaynak ve atıflar `DATA_LICENSES.md`, `data/manifest.json`, `data/uci_manifest.json` içinde. Yerel veri kaynağı baytları iki açık GitHub aynasının Git blob SHA-1 değeriyle doğrulanmıştır; bu ortamda UCI ZIP'i doğrudan alınamadı.

## Tekrarlanabilirlik ve üretilen çıktılar

`python3 run_all.py`, git dışı `results/` klasörüne SQLite ve JSON deney çıktılarını yeniden üretir. Üretilen veritabanı/loglar commit edilmez. UCI ham CSV'nin yerel dosya özeti deneyde kontrol edilir. Kaynak fixture dosyalarının atıfları `DATA_LICENSES.md` içerisindedir.
