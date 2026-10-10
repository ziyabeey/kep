# KEP Intelligence · Black C'den Öğrenilen Ölçümleme İlkeleri
**Kanonik mimari eki:** KEP-MEA-001  
**Sürüm:** 1.0 (öneri / uygulama öncesi karar)  
**Tarih:** 10 Ekim 2026  
**Kapsam:** KEP Radar → KEP Core → MiMo → Kullanıcı → Ölçüm → Öğrenme  
**Depo:** `ziyabeey/kep` — bu belge depoya yazılmamıştır.

## 0. Amaç ve sınır
KEP bir reklam satın alma platformu, bilet satıcısı veya kitlesel konum gözetim ağı olarak başlamaz. Kullanıcıya etkinlik, yemek, mekân ve hizmet keşfi sunar; izinli ve güvenilir verilere dayanarak öneri üretir. Ölçümün amacı *çok gösterim* değil, **ek yararlı karar ve doğrulanabilen gerçek dünya sonucu** oluşturmaktır.

Bu ek Black C Media / Azira yöntemlerinden **ürün düşüncesini** aktarır; Black C'nin özel veri seti, doğruluk iddiası veya altyapısına sahip olduğumuzu iddia etmez. Azira, Zefr, Equativ, Nexxen, DOOH ve reklam hedefleme modülleri KEP MVP kapsamı dışındadır.

## 1. Tez – antitez – sentez
**Tez: Görünürlük:** Bir etkinliği kaç sayfanın yayınladığına ve kaç kullanıcının gördüğüne bakmak. Bu erişimi ölçer; doğruluğu, kaliteyi ve gerçek sonuçları tek başına ölçmez.

**Antitez: Her şeyi ziyaretle ölçmek:** Fiziksel sonucu tek gerçek kabul etmek. KEP'in başlangıç PWA'sı, kullanıcının başka bilet satıcısında yaptığı satın almayı veya bir restorana girdiğini otomatik doğrulayamaz; yalnız GPS de bir işletmeye girişin güvenilir kanıtı değildir.

**Sentez: Kanıt kademeleri + kontrollü deney:** Kaynağın doğruluğu, önerinin görünmesi, kullanıcının niyeti ve doğrulanmış eylem ayrı ayrı kaydedilir. Gerçek etkiyi tahmin etmek için uygun ölçekte randomize karşılaştırmalar yapılır. Belirsizlik ve erişim sınırları saklanmaz.

## 2. Black C'den alınan yedi ilke
1. **Önce outcome:** “Kullanıcı için işe yarayan keşif” ve “doğrulanmış rezervasyon/katılım” hedefini tanımla.
2. **Sinyalin kanıt seviyesi:** Gösterim, tıklama, Maps yönlendirmesi, RSVP ve check-in farklı türden kanıttır.
3. **Tekilleştirme:** Aynı etkinliğin farklı kaynaklardaki paylaşımları tek ana kayda bağlanır; çok sayıda kopya özgün destek sayılmaz.
4. **Tutarlı ölçüm tanımları:** Olay adları, ölçüm penceresi ve ölçüm yöntemi sürümlenir; karşılaştırılabilir tutulur.
5. **Kontrol grubu:** Ek sonuç iddiası, uygun randomize karşılaştırma veya sınırlılıkları açıklanmış metodoloji gerektirir.
6. **Yerel bağlam:** Semt × kategori × gün/saat × kullanıcının seçtiği mod birlikte değerlendirilir.
7. **Öğrenme ve benchmark:** Sonuçlar maliyet, kanıt gücü ve kullanıcı faydasıyla birlikte zaman içinde kıyaslanır.

## 3. KEP ölçüm katmanları
| Katman | Örnek olay | Ne iddia edilebilir? | Ne iddia edilemez? |
|---|---|---|---|
| Source Evidence | `source_claim_verified` | Organizatör/kurum duyurusu doğrulandı | Etkinlik kesinlikle iyi veya popüler |
| Exposure | `recommendation_rendered` | Öneri istemcide görüntülendi | Kullanıcı dikkat etti veya gitti |
| Intent | `event_saved`, `follow_created`, `outbound_opened` | İlgi veya yönlendirme davranışı | Bilet alındı veya katılım gerçekleşti |
| Reported outcome | `user_reported_visit` | Kullanıcı ziyareti beyan etti | Bağımsız doğrulanmış ziyaret |
| Verified outcome | `organizer_checkin_verified`, `kepenk_service_completed` | Partnerin/onaylı sistemin doğruladığı işlem | Her türlü satış veya kullanıcı memnuniyeti |
| Incremental effect | `experiment_result_accepted` | Belirli deneyin ölçtüğü ek değişim | Tüm İstanbul / tüm kullanıcılar için genellenebilir etki |

Haricî bilet satıcısına geçiş yalnızca `outbound_opened` olayıdır. Satın alma onayı ancak yetkili dönüşüm bildirimi veya işletme ortaklığıyla alınabilir. KEP'in gerçek zamanlı kalabalık tahmini ayrı bir veri ürünüdür; sosyal mention sayısı ona eşit değildir.

## 4. Dört ayrı skor; tek bir yanıltıcı skor yok
- **Evidence Confidence:** Kaynağın birincilliği, bağımsız doğrulama, tarih/yer tutarlılığı, son kontrol zamanı ve çelişki.
- **Visibility:** Tekilleştirilmiş bağımsız yayıncı sayısı ve artış hızı. Aynı bülten kopyaları tek kök olarak değerlendirilir.
- **Personal Relevance:** Kullanıcının açık ilgi alanları, durum modu, zaman, bütçe ve mesafe (izinlerine tabi).
- **Outcome Quality:** Doğrulanmış katılım/rezervasyon dönüşümü ve kullanıcı geri bildirimi; yetersiz veri varsa “bilinmiyor”.

Küçük, az duyurulan ama resmî olarak doğrulanmış bir etkinlik düşük görünürlüğü nedeniyle bastırılmaz. Sponsorlu içerikler açıkça etiketlenir; ödeme kanıt/güven skorunu artırmaz.

## 5. KEP'in üç bağımsız kayıt defteri
**Evidence Ledger:** `source_id, source_url, object_id, claim_hash, observed_at, published_at, extraction_version, verification_status, license_scope, expires_at, confidence_reason`.

**Decision Ledger:** `decision_id, actor_pseudonym, session_id, candidate_ids, shown_candidate_ids, eligibility_context, policy_version, model_version, evidence_snapshot_ids, reason_codes, experiment_arm, occurred_at`. Pseudonymous kimlik doğrudan organizatöre açılmaz.

**Outcome Ledger:** `outcome_id, decision_id_if_known, object_id, outcome_type, source_system, proof_ref, reported_at, verified_at, status, consent_scope`. Kimlik olmadan birleşmeyen olaylar zorla aynı kullanıcıya bağlanmaz.

Ayrı bir **Cost Ledger**, kaynak kontrolü, tarayıcı süresi, model tokenları, depolama ve insan inceleme emeğini ölçer. Aynı olayın tekrar yazılmasına karşı idempotency anahtarı kullanılır.

## 6. KEP'in kanonik akışı
`SOURCE → VERIFY → DEDUP → SCORE → ELIGIBILITY → RECOMMENDATION → ACTION → PROOF → MEASURE → LEARN`

- **Radar:** Belirlenmiş, izinli kaynakları tarar; yenilik ve veri kalitesi sinyali üretir.
- **Core:** Tekilleştirir, kanıtı ve güncelliği tutar, öneri için sorgulanabilir veri sunar.
- **MiMo:** KEP Core araçlarıyla konuşur ve önerir; doğrulanmamış bilgiyi kesinleştiremez.
- **Kullanıcı:** Uygulamada bakar, sorar, kaydeder, takip eder, dış bağlantıya gider.
- **Measurement:** Eylemin kanıt seviyesiyle sonuç kaydeder; nedensel etkiyi ayrıca araştırır.

## 7. Deney standardı
- İlk aşamada iki varyantı randomize karşılaştır: **genel keşif sıralaması** vs. **MiMo destekli kişisel sıralama**. Her iki grup da kullanıcı tarafından istenen temel etkinlik listesini görür.
- Yalnız isteğe bağlı proaktif öneriler ve kişiselleştirme stratejileri deneylenir. Güvenlik bildirimleri ve kullanıcının açıkça istediği takip uyarıları deney uğruna tutulmaz.
- Randomizasyon mümkün olduğunda kullanıcı düzeyinde sabit atanır; bölge, gün, durum modu gibi önemli değişkenlere göre tabakalanabilir.
- Başarı metriği deney başlamadan seçilir: ör. 7 gün içinde **partner doğrulamalı RSVP** veya **check-in**. Diğer metrikler ikincildir.
- **Mutlak fark (yüzde puan)** ve **göreli lift (%)** birlikte raporlanır. Örn. %5 vs %8 → +3 yüzde puan, +%60 göreli lift. Bu rakamlar örnektir; küçük örneklemde güven aralığı geniş olabilir.
- Olay türüne göre önceden belirlenmiş pencereler kullanılır: aynı gün yeme-içme, tarihli etkinlik rezervasyonu, haftalık takip vb. Black C'nin kullandığı 7 günlük pencere KEP'e otomatik kopyalanmaz.
- Testte örneklem, belirsizlik aralığı, öngörülen/gerçekleşen sonuç ve ölçüm sınırlılıkları zorunlu rapor alanlarıdır. Atfedilen ziyaret ile **artımlı** ziyaret ayrı metriklerdir.

## 8. Durum modları ve bildirimler
İş, Gezinti, Dengeli ve Sessiz modu öneri sıklığını ve zamanlamasını değiştirir; kişinin değerini ya da reklamla hedeflenme hakkını değiştirmez. Kullanıcı takip bildirimleri ve ticari/sponsorlu bildirimleri ayrıştırır. `push_queued`, `push_sent` ve `push_opened` aynı metrik değildir; açık veya alındı kanıtı olmadan “görüldü” denmez.

## 9. Gizlilik ve işletme raporlaması
- Rutin özellikler için sürekli ham GPS geçmişi tutulmaz; kullanıcının seçtiği yaklaşık konum/sempte göre keşif mümkündür.
- Ham sohbet mesajları yerine kullanıcıya gösterilebilen ve silebildiği yapılandırılmış tercihler saklanır; koruma ve saklama süreleri ayrıca belirlenir.
- İlgi çıkarımı, analitik, pazarlama bildirimi ve üçüncü tarafla iletişim amaçlarının hukuki dayanakları ayrı değerlendirilir; kullanıcı kontrolü zorunludur.
- Organizatörler isim/telefon/ham lokasyon geçmişi değil, yeterli büyüklükte gruplara ait toplam gösterim, yönlendirme, partnerce doğrulanmış katılım ve deney sonuçlarını görür. Bireysel iletişim yalnızca kullanıcının açıkça seçtiği bağlantı akışında mümkündür.
- Kaynağın herkese açık oluşu, kişisel Instagram hesabını izleme veya ticari veri işleme lisansı anlamına gelmez.

## 10. MVP kapıları ve başarı ölçütleri
**Kapı A – Veri doğruluğu:** 10 seçilmiş kaynak; kaynak başına erişim izni, tarama sıklığı, idempotent kayıt, mükerrer etkinlik oranı, yanlış tarih/yer oranı ve güncellik ölçülür.

**Kapı B – Ölçülebilir keşif:** KEP'te `recommendation_rendered`, `event_saved`, `outbound_opened`, `follow_created` logları doğru çalışır. Günlük kaynak maliyeti raporlanır.

**Kapı C – Doğrulanmış sonuç:** En az bir gönüllü etkinlik organizatörü veya Kepenk işletmesiyle RSVP/check-in/hizmet sonucu entegrasyonu denenir. Üçüncü taraf bilet satışına gerek yoktur.

**Kapı D – Incrementality:** Ancak yeterli örneklem ve doğrulanabilir outcome mevcut olduğunda randomize deney raporlanır. Yeterli hacim yoksa “etki henüz ölçülemiyor” denir; uplift uydurulmaz.

**Ürün kuzey yıldızı (ölçülebilir hedef):** `100 uygun keşif oturumu başına doğrulanmış, kullanıcının onayladığı yararlı aksiyon`. Bu metrik, doğrudan rezervasyon/katılımın henüz doğrulanamadığı kaynaklarda daha zayıf bir kanıt seviyesiyle ayrıca gösterilir.

## 11. Sabit ve değişken kararlar
**Dondurulacak:** Üç ledger, kanıt seviyeleri, ürün/ölçüm ayrımı, ölçüm sözcüklerinin anlamı, kullanıcı kontrolü, kontrol deney mantığı, reklam teknolojisi kapsam dışılığı.

**Deneyle değişebilir:** MiMo sürümü, sıralama ağırlıkları, tarama aralıkları, kaynak adaptörleri, zaman pencereleri (ileri dönük sürümle), veri saklama süreleri (hukuki kontrolle), kalite eşikleri.

**Değişiklik kuralı:** Yazılı ADR → ölçülebilir gerekçe → test → rollback planı. Kaynak eklemek mimari değişiklik değildir.

## Dayanaklar
- Black C Media, McDonald's Türkiye (13 kampanya, 7 günlük pencere, kontrol karşılaştırması; **ölçülen ziyaret satış değildir**): https://www.blackcmedia.net/tr/case-studies/mcdonalds-turkiye-footfall-vaka-calismasi
- Black C Media, BYD Türkiye (niyet, tercih, ziyaret zinciri): https://www.blackcmedia.net/tr/case-studies/byd-turkiye
- Black C Media, Azira (kontrol, footfall attribution): https://www.blackcmedia.net/tr/partners/azira-lokasyon-verisi
- KVKK, mobil push amaçları için ayrı tercihler: https://www.kvkk.gov.tr/Icerik/8578/mobil-uygulamalar-uzerinden-gonderilen-anlik-bildirimlere-iliskin-kamuoyu-duyurusu
- KVKK, mobil uygulamalarda mahremiyet: https://www.kvkk.gov.tr/Icerik/7751/Mobil-Uygulamalarda-Mahremiyetin-Korunmasina-Yonelik-Tavsiyeler
