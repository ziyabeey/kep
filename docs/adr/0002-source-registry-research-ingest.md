# ADR-0002: Kaynak Kayıt Sistemi ve kontrollü araştırma toplaması

**Durum:** Kabul adayı; PR ve CI doğrulamasına bağlı  
**Tarih:** 2026-10-11  
**Kapsam:** `labs/core/sources/registry.json`, `kepcore/radar.py`, `scripts/poll_source.py`

## Bağlam

KEP'in ilk yayın alanı İstanbul. Sahip olmadığımız sosyal/içerik lisanslarını veya gizli Instagram konum verisi erişimini var sayamayız. Kullanıcının seçtiği güvenilir İstanbul kaynakları (Zorlu PSM, İstanbul Senin, Kültür İstanbul, OGGUSTO, Pera Müzesi, İstanbul Modern, İBB Kültür Sanat) şimdilik **adaydır**, ticari otomatizasyona onaylı değildir.

## Karar

1. **Kayıt olmadan istek yok.** Her kaynak ID/HTTPS URL/şehir/format/kullanım hakkı/durum/sıklık/kota/dokümantasyon bilgisine sahip olur.
2. **İzin türleri farklı.** `research_ingest` ile `consumer_display` ayrı haklardır. İzin bekleyen yedi İstanbul kaynağı için ağ çağrısı yok.
3. **Onaylı tek araştırma kaynağı:** İzmir BB açık etkinlik JSON akışı; yalnız araştırma indirimi, ticari ürün gösterimine otomatik aktarım **yok**.
4. **İlk adaptör:** Tek, denetlenmiş JSON şeması. Genel amaçlı web tarayıcısı veya serbest ajan gezinmesi yok.
5. **Görevin sonucu:** Gövde hash'i, ETag, Last-Modified ve kaynak bilgisi saklanır. Değişmeyen kayıt yeniden işlenmez; 304 yeni veri değildir.
6. **Güvenlik:** Kaynağa özel asgari sorgu aralığı, günlük kota, boyut sınırı, HTTPS, otomatik yönlendirme/yeniden deneme yok. 401/403/429 ve bozuk/boş şema insan incelemesine alır. Bir kaynak boş göründü diye geçmiş kayıtlar silinmez.
7. **Güncellik:** Başarılı HTTP isteği, etkinliğin gerçekleşeceğini kanıtlamaz. Yeni snapshot `research_only`, `origin_live_verified=false` ve `source_observed_at=null` ile başlar. Manuel kanıt politikası yoksa KEP Core'a kullanıcıya öneri için terfi ettirilmez.
8. **Maliyet:** CI hiçbir ağ kaynağına erişmez ve MiMo/Laya çağırmaz. İsteğe bağlı gerçek HTTP çağrısı `--fetch` ile elle açılır. Poll-state ve canlı indirmeler git dışıdır.

## Çalışma örnekleri

```bash
cd labs/core
python scripts/poll_source.py --list
python scripts/poll_source.py --source zorlu_psm_events
python scripts/poll_source.py --source izmir_open_events
# Yalnız araştırma amaçlı, açıkça onaylanan canlı ağ işi:
python scripts/poll_source.py --source izmir_open_events --fetch --out data/raw/live_izmir_manual_001.json
```

## Güvenlik ve sınırlar

- URL biçimi doğrulaması **tam SSRF/DNS rebinding savunması değildir**. Ağlı çalıştırma güvenlik duvarı/egress allowlist ile sınırlandırılmalıdır.
- Resmî İzmir API'sinin bugün çalıştığı veya dönen verinin güncel olduğu CI tarafından kanıtlanmıyor. Bu PR çevrimdışı kontroller sunuyor.
- Kaynağın HTTP/JSON formatının değişmesi `paused` veya `error` durumuna yol açar. İnsan incelemesi olmadan kaynak yenilenmez.
- Ürün kategorileri, Native iOS/Android uygulaması, MiMo sohbeti ve Pro ticari ürün kapsamı **bu PR'da geliştirilmez**.

## Kabul kriterleri

- İstanbul kaynaklarının hiçbirine, onaylı olmayan kullanım için otomatik çağrı yapılmaması.
- İzinli araştırma feed'i için 200/304/403/429, tekrar, kota, boş/bozuk veri, açık olmayan haklar ve ağ hatası testlerinin geçmesi.
- v0.3 regresyon, değerlendirme bölmeleri ve yeniden üretilebilirlik sonuçlarının değişmemesi.
- Python 3.11 ve 3.13 CI başarılı olmalı; ana dal yalnız CI sonrası güncellenmeli.

## Değişiklik denetimi

Yeni kaynağa izin eklemek içerik hakkı kaydı ve ayrı inceleme gerektirir. Sadece bir metne bakarak `approved` yazılmaz; ticari gösterim hakkı başka bir onaydır. Kaynak eklenmesi çekirdek modelinin değiştirilmesini gerektirmez.
