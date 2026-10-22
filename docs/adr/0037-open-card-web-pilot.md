# ADR-0037: Açık kart web pilotu (S0) gerçek kullanıcıya açılır, lab sınırlarının dışında

**Durum:** Önerilen (PR incelemesine açık; eşikler Ziya onayıyla dondurulur)
**Tarih:** 2026-10-22
**Deney kimliği:** KEP-SOC-001
**İlgili:** ADR-0028 (test değeri önce ölçülür), ADR-0030 (ön kayıt), ADR-0036 / PR #54 (yerel tarayıcı önizlemesi)

## Bağlam

22 Ekim 2026'da Ziya, uygulama planı v0.2'deki sosyal hattın ilk adımını (S0) esnaf
hattının Faz 0-1'iyle paralel başlatmayı seçti. S0'ın sorusu tek: **insanlar KEP'te
ücretsiz bir buluşma kartı açıp paylaşıyor ve bu kartlar gerçekten gerçekleşiyor mu?**
Sohbet, anı ve konum paylaşımı bu sorunun cevabına bağlı yatırımlar; cevap olmadan
kurulmaz.

KEP'in bugünkü sınırları buna izin vermiyor:

- `labs/core` bir araştırma laboratuvarı: `consumer_publish=false`,
  `real_human_labels=0`, gerçek kullanıcı verisi yok.
- ADR-0036 (PR #54) tarayıcı önizlemesini yerel çalışmayla sınırlıyor ve açıkça
  "genel internete dağıtım kararı değil" diyor.

S0 ise gerçek insanların hesap açtığı, internete açık bir servis. Bu yüzden ayrı bir
karar gerekiyor.

## Karar

1. **S0 web pilotu internete açılır, ama lab'ın dışında.** Uygulama kodu ayrı bir ürün
   reposunda yaşar (repo ve hosting seçimi bu ADR'nin açık sorusu, aşağıda).
   `labs/core`'daki hiçbir varsayılan değişmez: lab `consumer_publish=false`,
   `source_fetches=0`, `real_human_labels=0` olarak kalır ve pilot verisine erişmez.
   Bu ADR ve ön kayıt protokolü bu repoda (`docs/`) durur, çünkü KEP'in karar
   kaydı burada.
2. **Kapsam yalnız dört eylem:** kart aç, linki paylaş (WhatsApp/Instagram), katıl,
   haritada gör. Sohbet, anı, canlı konum, ödeme, bildirim dışında push yok.
3. **Bölge:** Kadıköy, önce Moda. Harita altlığı ve yer verisi Overture/OSM tabanlı;
   Google Maps verisi ve Google yer araması kullanılmaz.
4. **Mock yok.** Sahte kart, sahte kullanıcı, "örnek etkinlik" yok. Soğuk başlangıç
   Ziya'nın aracılık ettiği 2-3 gerçek Moda topluluğuyla (koşu/yürüyüş grubu, kitap
   kulübü, kafe etkinliği) yapılır. Ekibin açtığı kartlar ölçümde ayrı sayılır.
5. **Ön kayıt.** Karar sorusu, metrikler, pencere ve GO/NO-GO eşikleri
   `docs/pilots/kep-soc-001_protocol.json` dosyasında, uygulama kodundan önce ayrı bir
   commit olarak donar. Eşikleri Ziya onaylar; onaydan sonra eşik, pencere veya metrik
   tanımı değişirse bu yeni bir deneydir (KEP-SOC-002).
6. **Yayın öncesi zorunlular (kapı):** aşağıdakilerin hepsi hazır olmadan link
   paylaşılmaz.
   - KVKK aydınlatma metni ve açık rıza ekranı (hangi veri, ne kadar saklanır, kim
     görür); veri sorumlusu bilgisi.
   - 18+ beyanı ve doğum yılı kontrolü; açık kartlar yalnız 18+.
   - Her kartta ve her profilde şikâyet; kullanıcı engelleme; şikâyet edilen kartı
     açan kişinin 24 saat içinde gözden geçirmesi (pilotta Ziya).
   - Telefon numarası başka kullanıcılara hiç gösterilmez; kartı açanın ev/iş konumu
     gösterilmez; buluşma noktası kamuya açık bir yer olmak zorunda.
   - Profilde fotoğraf yok; takipçi ve beğeni sayacı yok.
   - Silme: kullanıcı hesabını ve kartlarını kendisi silebilir; pilot bitince ham veri
     protokolde yazan süre sonunda silinir.
7. **Durdurma kuralı.** Doğrulanmış bir taciz, tehdit veya reşit olmayan kullanıcı
   olayı pilotu eşiklerden bağımsız olarak durdurur; sonuç rapora NO-GO (güvenlik)
   olarak yazılır.

## Sonuçlar

- GO: S1 (uygulamada kart + sohbet + süreli konum) için ayrı ADR ve protokol açılır.
- NO-GO: sonuç silinmez, yeniden yorumlanmaz; sosyal hat yeniden tasarlanır, esnaf
  hattı etkilenmez.
- Lab'ın sentetik sonuçları pilotun başarısı ya da başarısızlığı olarak raporlanmaz;
  pilot sonucu da İstanbul yer verisi doğruluğu olarak raporlanmaz.

## Açık soru

- Uygulama kodunun reposu ve hosting (öneri: yeni repo + Supabase + Vercel/Cloudflare
  Pages; Randevu ile aynı Supabase organizasyonu). Ziya'nın seçimi bu bölüme yazılır.
- 5651 (yer sağlayıcı) ve KVKK için kısa bir hukukçu görüşü yayından önce alınmalı mı,
  yoksa pilot ölçeğinde aydınlatma metni yeterli mi?

## Rollback

Pilot alan adı kapatılır, link ölü sayfaya döner; veritabanı protokoldeki silme
adımıyla temizlenir. Bu repoda geri alınacak kod yok; ADR "Reddedildi" olarak
işaretlenir.
