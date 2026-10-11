# ADR-0010 · Real Overture snapshot as a reproducible research input

**Durum:** Kabul edilen araştırma kararı  
**Tarih:** 2026-10-11  
**Ön koşullar:** ADR-0008, ADR-0009, Issue #13

## Bağlam

KEP'in 4.803 gerçek Overture Places kaydı içeren ilk manuel GitHub Actions işi
başarılı oldu (run `38096227796`, `2026-09-23.1`, 2 dar İstanbul hücresi).
Actions artifact'leri 7 gün sonra silinir. Sadece ephemeral artifact tutmak
araştırmanın test edilebilirliğini azaltır.

## Karar

- Kullanıcılara yayımlanmayan, gerekli POI alanlarıyla sınırlı, 435 KB
  deterministik gzip arşivini ve kaynak manifestini sürümle.
- Arşivin sıkıştırılmış, açılmış ve GitHub artifact SHA-256 kayıtlarını sakla.
  Snapshot ve manifestin kendi aralarındaki hash uyumu yalnız bütünlük kontrolüdür,
  gerçek üretici kimliği veya fiziksel işletme doğrulaması değildir.
- Her PR'da gerçek veri replay'ini Python 3.11/3.13 CI üzerinde çalıştır.
- KEP Core'a dönüşümde **`rights_scope=research_ingest`** ayarla.
  Gelecekte hak izni ayrıca doğrulanana kadar `RIGHTS_NOT_APPROVED` ile
  tüm araştırma adaylarını tüketiciye kapalı tut.
- Zamanla yenilenen veri, bu sürümü yerinden değiştirmeyecek;
  her yeni Overture sürümü ayrı giriş ve bilimsel çalışma olacaktır.
- Ağ erişimi, API anahtarı, LLM değerlendirmesi veya insan kontrolü CI'da yok.

## Sonuç ve kabul

Gerçek Overture veri dağılımına ilişkin bilinen eksikler ve mükerrer adaylar
tekrarlanabilir hâle gelir. **Henüz kalibre edilmiş fiziksel varlık doğruluğu yoktur.**
Issue #13 gerçek saha incelemesi tamamlanana kadar açık kalır.

## Geri dönüş

Bu veri ve kod ayrı araştırma modülüdür. PR geri alınırsa üretim
servisine etkisi olmaz. Arşiv depoda kalsa dahi yayın kapısı açılmaz.
