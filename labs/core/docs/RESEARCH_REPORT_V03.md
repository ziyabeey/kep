# KEP Core Lab v0.3: gerçek değerlendirme verisi ve çekirdek sağlamlaştırma

**Tarih:** 10 Ekim 2026. **Durum:** Çalıştırılmış yerel araştırma paketi, üretim uygulaması değil.
**Depo:** `ziyabeey/kep` üzerinde dosya, commit, branch veya issue değişikliği yapılmadı.

## 1. Bu sürümün gerçek kapsamı

Önce v0.2 yeniden çalıştırıldı: 50 eski birim testi geçti. Bunun yanında yeni uç durumlar yazıldığında açılış saatlerinin yalnız varlığına bakıldığı, bilinen yüksek kalabalığın elenmediği ve alan bazlı eskiliğin geniş kayıt zamanına karışabildiği görüldü. Bu boşluklar v0.3'te giderildi.

İkinci iş, gerçek geçmiş restoran değerlendirmeleriyle beş klasik tahmin yöntemini karşılaştırmak oldu. Bu araştırma, önceki sentetik kullanıcı fayda fonksiyonunun devamı değildir. Gerçek tarihsel puanlar kullanılır; kullanıcıya gönderilmiş gerçek KEP önerisi veya canlı davranış deneyi yoktur.

**Bu sürümde satın alınmış veri API'si ve gerçek Laya/MiMo çağrısı yok.** İşlem kaynakları tüketildi; bu ifade toplam geliştirme/altyapı maliyetinin sıfır olduğu anlamına gelmez.

## 2. Edinilen veri ve kökeni

UCI Machine Learning Repository, *Restaurant & consumer data*, Medelln ve Serna (2011), DOI `10.24432/C5DP41`.
Resmî kayıt: https://archive.ics.uci.edu/dataset/232/restaurant%2Bconsumer%2Bdata
Resmî sayfa lisansı: **CC BY 4.0**. Atıf bu belgede ve `DATA_LICENSES.md` dosyasında korunur.

- `rating_final.csv`: **1.161 satır**, **138 kullanıcı kimliği**, **130 restoran kimliği**.
- Gözlenmiş değerlendirme ölçeği: 0, 1, 2. Sayılar: 0 için 254, 1 için 421, 2 için 486 kayıt.
- Dosyada 0 gerçek bir değerlendirmedir; eksik değer değildir. Hiç değerlendirilmemiş kullanıcı-restoran çiftlerine olumsuz etiket eklenmedi.
- Kişisel/demografik profil dosyaları alınmadı. Modeller yalnız kullanıcı kimliği, restoran kimliği ve genel puan kullanır. Aynı deneyimin yemek/hizmet puanları tahmin girdisi yapılmaz.
- Zaman damgası yok. Veri İstanbul'u, 2026 güncelliğini veya gelecekteki katılımı temsil etmiyor.

### Edinim şekli ve bütünlük

Bu ortamdan doğrudan UCI/İzmir/Overture indirme denemeleri ad çözümleme hatası verdi. Tam CSV, GitHub bağlayıcısının herkese açık iki ayna dosyasından döndürdüğü içeriklerden yeniden oluşturuldu. Satırların tamamının aynı dosyaya ait olduğu **Git blob SHA-1** karşılaştırmasıyla doğrulandı. Dosya boyutu **22.108 bayt**.

- Git blob SHA-1: `d2072b911d10edf52a1b01c4a481e02490e651ca`
- SHA-256: `fc994ea4e872365fc63e7f0bc970b36f86edeb4e80218d6a674a3d0e51181901`
- Ayna 1: https://github.com/tkarim45/Beginner-Data-Science-Projects/blob/531609b007a4053600d1b9fa1113a509cf24e7b0/Recommendation%20Systems/Restaurant%20Recommendation%20System/data/rating_final.csv
- Ayna 2: https://github.com/ajaysh2193/Restaurant-Recommender-System/blob/master/rating_final.csv

Her iki ayna aynı Git blob özetini verdi; yerel dosya bu özetle birebir eşleşti. Bu, **ayna dosyalarının bayt bütünlüğünü** kanıtlar; UCI ZIP'i doğrudan indirerek ayrıca karşılaştırdığımız veya gerçek kullanıcı beyanlarını sahada teyit ettiğimiz anlamına gelmez. Edinim ve lisans kaydı `data/uci_manifest.json` içinde.

Eski 16 İzmir etkinliği ve 7 İstanbul mekânı korunmuştur. **Yeni canlı İstanbul kaydı: 0.** Eski kayıtlara güncelmiş gibi tarih basılmadı. UCI restoran kimlikleri bu İstanbul mekânlarının kimlikleriyle birleştirilmedi.

## 3. Teste bakmadan tanımlanan protokol

`benchmarks/preference_protocol.json`, ilk model çalıştırmasından önce yazıldı; dışarıda zaman damgalanmış akademik ön kayıt değildir.

Ana tohum: `20261010`. Her kullanıcı için restoran kimlikleri önce sıralanıp deterministik biçimde karıştırılır. En az altı değerlendirmesi olan kullanıcılarda üç kayıt test, bir kayıt doğrulama, kalanlar eğitim için ayrılır. Diğer kullanıcılar eğitimde kalır, test ölçüsüne girmez.

**Eğitim: 757; doğrulama: 101; test: 303.** Testte **101 kullanıcı**, yalnız eğitimde 37 kullanıcı var. Parametreler doğrulama hatasına göre seçilir. Ardından eğitim+doğrulama ile yeniden fit yapılır; 303 test etiketi bu fit'e girmez.

Yöntemler:

1. `global_mean`: herkes için eğitim genel ortalaması.
2. `item_mean`: restoranın düzenlileştirilmiş ortalaması.
3. `user_mean`: kullanıcının düzenlileştirilmiş puan ortalaması.
4. `bias`: genel ortalama + kullanıcı etkisi + restoran etkisi; L2 düzenlileştirme.
5. `item_knn`: ortak değerlendirmelerden restoran benzerliği, kalıntı puan ve destek küçültmesiyle komşuluk.

Bunlar klasik referans yöntemlerdir; Laya, MiMo, Stanford RecPIE veya başka bir makalenin birebir yeniden üretimi değildir.

Ana ölçü **MAE**, yani `ortalama(|gerçek puan - tahmin|)`. Düşük daha iyi. Puan ölçeği 0..2; MAE bir yüzde veya öneri doğruluğu değildir.

İkincil ölçü **NDCG@3**, yalnız o kullanıcının üç saklı ve gerçekten değerlendirilmiş restoranının kendi arasındaki sırası içindir. Eşit tahminlere rastgele sıra üstünlüğü verilmez; bağlar ortalanır. Bütün gerçek puanları sıfır olan 11 kullanıcı bu ölçü için tanımsızdır. Böylece sıralama ölçüsünde 90 kullanıcı vardır. Bu üç seçenekli dar test, 130 restoranın tümüne karşı keşif kalitesi ölçümü değildir.

## 4. Çalıştırılan ana sonuçlar

| Yöntem | MAE, düşük iyi | RMSE | NDCG@3, yalnız saklı puanlı üç aday |
|---|---:|---:|---:|
| `global_mean` | 0.6713 | 0.7789 | 0.8953 |
| `item_mean` | 0.6648 | 0.7787 | 0.9019 |
| `user_mean` | 0.5108 | 0.6453 | 0.8953 |
| `bias` | 0.5138 | 0.6617 | 0.9159 |
| `item_knn` | 0.5491 | 0.7434 | 0.9043 |

### Sonuçların doğru yorumu

**Kullanıcı geçmişi puan tahminine katkı sağlıyor.** Fakat `user_mean` aynı kullanıcı için bütün restoranlara aynı puanı verdiğinden o kullanıcının restoranlarını zevkine göre sıralamaz. Kazanç, kısmen kişinin cömert/sert puan verme eğiliminin öğrenilmesidir. Bu sonucu “kişisel zevkleri anladık” diye büyütmüyoruz.

`bias` ile `item_mean` MAE farkı **-0,1510**, değerlendirme kullanıcılarını eşli yeniden örnekleyen yüzde 95 koşullu aralık **[-0,2219; -0,0829]**. Bu bölmede kullanıcı bileşeninin yararı var.

`bias` ile daha güçlü basit `user_mean` arasındaki fark **+0,0030**, aralık **[-0,0204; +0,0270]**. Basit kişisel ortalamadan daha iyi olduğumuzu gösteremedik.

**Doğrulama bölümünün seçtiği yöntem `item_knn` oldu; fakat testte başarısı düştü.** `bias` karşısında MAE farkı +0,0353, koşullu aralık [+0,0032; +0,0690]. Test sonucunu gördükten sonra seçilmiş yöntemi sessizce değiştirmedik. Bu sonuç, küçük veriyle seçim kararsızlığını ve karmaşıklığın zarar verebildiğini gösterir.

`bias` için sıralama ölçüsü sayısal olarak daha yüksek, ancak güçlü basit karşılaştırmalara karşı NDCG farkının belirsizlik aralıkları sıfırı içeriyor. **Sıralama üstünlüğü kanıtlanmadı.**

Belirsizlik hesapları 2.000 eşli kullanıcı bootstrap tekrarına dayanır ve **bu fit ve bu veri bölmesi koşulundadır**. Genel nüfus güven aralığı, nedensel katılım artışı veya bağımsız saha tekrarı değildir. Farklı beş tohumla duyarlılık koşusu yapıldı; aynı verinin örtüşen bölmeleri bağımsız 5 deney diye sunulmaz. Tüm sonuçlar ve test tahminleri JSON'da saklıdır.

### Hiç tanınmayan kullanıcı

Ayrı bir denemede **28 kullanıcının bütün geçmişi** saklandı, **238 gerçek puan** test edildi. Restoran ortalaması MAE ≈ **0,6182**, genel ortalama ≈ **0,6497**, kullanıcı+restoran modeli ≈ **0,6242**.

Kullanıcı geçmişi yokken kişisel etki öğrenilemez. Başlangıç için açık tercih sormak veya güvenilir genel seçim kullanmak bir ürün yönüdür; bu çalışmada konuşarak başlangıç tercihi öğrenme deneyi yapılmadı.

## 5. Düzeltilen çekirdek davranışları

`kepcore/availability.py` yedi günün tamamının belirtilmesini isteyen açık bir saat sözleşmesi kullanır. IANA saat dilimi, gece yarısını aşan aralıklar, kapanış anının aralık dışında kalması ve tarih istisnaları test edilir. Rastgele yazılmış bütün opening-hours biçimlerini çözen bir ayrıştırıcı değildir; tanınmayan biçim `UNKNOWN` olur.

- Açılış saati mevcut diye açık sayılmaz; istenen zaman değerlendirilir.
- Bilinen orta/yüksek kalabalık, düşük kalabalık isteyen sorguda elenir. Düşük kalabalık **akustik sessizlik kanıtı değildir**, bu sınır çıktı notuna eklenir.
- Fiyatın kendi doğrulama tarihi, kaydın genel güncelleme tarihinden ayrılır.
- Alan kanıtı varsa içerik özeti alanın mevcut değeriyle eşleşmelidir; eski fiyat kanıtı yeni fiyata aktarılmaz.
- Fiyat para birimi sorguyla eşleşmiyorsa otomatik kur uydurulmaz.
- Eksik, negatif, NaN, sonsuz, metin veya boolean fiyat geçerli sayılmaz.
- Güncel kanıtı olmayan fiyat, basit katalog cevabında dahi modele kesin bilgi diye verilmez.
- Tercih yeniden sıralaması yalnız çekirdeğin zaten izin verdiği adaylar arasında çalışır; kapalı/iptal/engellenmiş bir adayı geri ekleyemez.

**Yeni 15 uç durum eski v0.2'ye de çalıştırıldı: eski sürüm 3/15, yeni sürüm 15/15.** Bunlar gerçek mekân kaydına test amaçlı eklenmiş açılış, fiyat, kalabalık ve izin durumlarıdır. Etiketleri geliştiren kişinin tasarladığı gerileme testleridir, rastgele pazar performansı ölçümü değildir. Özgün kaynak kayıtları değiştirilmemiştir.

## 6. MiMo/Laya bağlanma sınırı

`kepcore/model_boundary.py`, izinli adayların kaynak kimliği, kayıt sürümü, bilinen alanları ve belirsizliklerinden bir bağlam oluşturur. Modelin yapılandırılmış cevabında şu kontroller yapılır:

- Aynı bağlam sürümü mü?
- Seçilen aday izinli listede mi?
- İddia edilen alan gerçekten verilmiş mi?
- Alan değeri ve kaynak sürümü eşleşiyor mu?

Bu **çalışan bir gerçek EVREN istemcisi değil**, çevrimdışı sözleşmedir. Serbest doğal dil açıklamasının bütün cümlelerini doğrulamıyoruz; desteklenmeyen serbest açıklama alanını doğrulanmış gibi kabul etmiyoruz. Gerçek Laya/MiMo çağrısı ve prompt-injection dayanıklılık ölçümü sonraki bağımsız deney gereksinimleridir.

`rerank_eligible` verilen izinli listenin içinde çalışır. Üretimde tüm havuza kişiselleştirme isteniyorsa önce daha geniş uygun aday havuzu çıkarılmalı, kişisel sıralamadan sonra son limit uygulanmalıdır. Mevcut küçük adaptör otomatik tam-katalog keşfi iddiası taşımaz.

## 7. Test ve yeniden üretim özeti

- **87 birim testi geçti.**
- Eski sözleşme kümesindeki **85 durum**, güncel çekirdekle beklenen kararı verdi.
- Yeni gerileme kümesindeki **15 durum**, güncel çekirdekle beklenen kararı verdi.
- Bu senaryo kümeleri birim testlerinin de içindedir; sayılar bağımsız deney sayısı olarak toplanamaz.
- Aynı gerçek veri ve tohumlarla tercih deneyi iki kez çalıştırıldı; süre hariç bütün ölçüler, bölmeler ve tahmin çıktıları birebir aynı çıktı.
- Geçmiş karşılaştırma: `results/regression_comparison.json`; tekrar koşulan güncel karşılaştırma: `results/regression_current/`.
- Test günlükleri, kaynak özetleri, seçilen parametreler ve kullanıcı düzeyindeki hata değerleri paket içinde.

## 8. Son hüküm ve değiştirmediğimiz kararlar

Bu sürümde **veri/kanıt/kısıt çekirdeğini güçlendirdik ve gerçek geçmiş veride öğrenme referanslarını kurduk**. En karmaşık yöntemin kazandığını göstermedik; tersine güçlü basit yöntemlerin önemini gördük.

Canlı İstanbul kaynağı, gerçek değişim geçmişi, anlık niyet, yürüyüş rotası, gerçek bildirim faydası, bilet/katılım sonucu, çevrimiçi bandit, bütünleşik bilgi-değeri planlayıcısı ve çok ajanlı muhakeme bu veriden ölçülemez. Bunların yerine sahte başarı yüzdesi yazılmadı.

Bir sonraki teknik kabul kapısı: çekirdeğin aynı kaynak bağlamında gerçek MiMo/Laya ile nasıl davrandığını ölçmek ve uygun lisanslı daha zengin mekân/kullanım verisi eklemek. Bu rapor o işlerin yapıldığı iddiasını taşımaz. Depo yazma yasağı korunur.

## 9. Çalıştırma

Python 3.10+ ve sistem IANA saat dilimi veritabanı gerekir. Haricî Python ML kütüphanesi veya model anahtarı gerekmez. Ortamda saat dilimi verisi yoksa `tzdata` paketi eklenebilir.

```bash
python3 run_all.py
python3 play_preferences.py --user U1001 --method user_mean
python3 play_preferences.py --user U1001 --method item_knn
python3 query.py --query examples/galata_nearby.json
python3 query.py --query examples/galata_open_budget.json
```

`run_all.py` yalnız paket içindeki `results/` ve normalleştirilmiş katalog çıktısını yeniler. Ağa bağlanmaz, üçüncü taraf hesabına veya GitHub'a yazmaz. Orijinal v0.2 klasörü varsa `--old-v02-root /tam/yol/kep_core_lab_v0_2` ile eski-yeni karşılaştırma yeniden yapılabilir. Bu seçenek olmadan da bütün güncel testler çalışır.
