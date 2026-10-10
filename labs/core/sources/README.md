# KEP Source Registry

`registry.json` içindeki her URL bir *aday veya onaylı kaynak kaydıdır*. Bir URL'nin listelenmesi, otomatik tarama için izin verildiği anlamına gelmez.

**2026-10-11 durum:** İstanbul'a ait 7 aday `pending`; İzmir Belediyesi'nin araştırma kapsamlı etkinlik akışı `approved` + yalnızca `research_ingest`. **Hiçbir kaynak `consumer_display` hakkına sahip değil.**

`poll_source.py` varsayılan olarak *offline* çalışır. `--fetch` isteği bile kayıt defteri, kullanım amacı, min aralık, günlük kota ve yanıt biçimi kontrolüne bağlıdır. Kaynak güncelleme durumları: `changed`, `unchanged`, `not_modified`, `skipped`, `denied`, `paused`, `error`.

İndirilen ham kayıt otomatik olarak kullanıcıya yayımlanmaz veya veri çekirdeğine yazılmaz. HTTP erişiminin başarılı olması etkinliğin güncel/var olduğunun teyidi değildir. Kullanım hakları, kaynağın sürümü, özgün kaynak URL'si ve çelişkiler ayrı tutulur.

Üretimde DNS/IP tabanlı ağ çıkış filtresi, düşük ayrıcalıklı süreç, insan onayı, telemetri ve geri dönüş prosedürü eklenecektir.
