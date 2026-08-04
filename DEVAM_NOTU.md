# Devam Notu — Chunking Yöntemi Değişikliği

Bu dosya, bu oturumda yapılan büyük işin ("chunking yöntemi deneyi" →
"production entegrasyonu") ara durumunu özetler — böylece farklı bir
prompt/oturumda kaldığımız yerden devam edilebilir. İş tamamlanınca
(migration da bitince) bu dosya silinebilir.

## Genel bağlam

"Adaptive Chunking: Optimizing Chunking-Method Selection for RAG"
(Ekimetrics) makalesindeki yöntemler, projenin kendi verisiyle
(8 test sayfası: düz metin, liste ağırlıklı, PDF kaynaklı, karışık)
ICC/DCC/BI/SC metrikleriyle karşılaştırıldı. Sonuç: tek bir sabit
chunking yöntemi yok, içerik türüne göre değişiyor. Bulgulara dayanan
**kural-bazlı (ucuz, embedding çağrısı gerektirmeyen) bir otomatik
seçici** production'a entegre edildi.

## Git durumu

- **Branch:** `chunking-yontem-deneyi`
- Bu branch `main` değil, `chat-baglama-baslik-ekle` (**PR #1**) üzerine
  kurulu — çünkü deney EmbeddingGemma-300M modeline bağımlı, `main`'de
  henüz o geçiş yok.
- **PR #1:** https://github.com/haticenurolgun/personalwiki/pull/1
  (chat bağlamı başlığı + embedding model geçişi + masaüstü graf UI) —
  henüz merge edilmedi.
- **PR #2:** https://github.com/haticenurolgun/personalwiki/pull/2
  (chunking deneyi + production entegrasyonu) — henüz merge edilmedi,
  base'i PR #1.

### PR #2'de commit edilmiş olanlar
- Chunking deneyi (`test_chunking_yont.py`, `deney_*.py`, CSV sonuçlar,
  `deney_otomatik_secici.py` ilk hali)

### HENÜZ COMMIT EDİLMEMİŞ (`chunking-yontem-deneyi` working tree'de duruyor)
```
modified:   app/connectors/markdown_connector.py
modified:   app/connectors/pdf_connector.py
modified:   app/embeddings/embedding_servisi.py
modified:   app/models/db_models.py
modified:   app/routers/concepts.py
modified:   app/routers/pages.py
modified:   app/routers/sources.py
modified:   app/services/structural_parser.py
modified:   deney_metrikleri.py
modified:   deney_otomatik_secici.py
modified:   desktop_demo.py
modified:   requirements.txt
modified:   test_chunking_yont.py
untracked:  app/services/chunking_secici.py (YENİ)
```

Bu değişiklikler şunları kapsıyor:
1. `structural_parser.py` isimlendirme temizliği (`MetinParcasi`→`Parca`,
   `token_sayan_fonksiyon`→`token_sayici`, vb.) + **gerçek bir hata
   düzeltmesi**: `maks_token` varsayılanı `128` (eski MiniLM sınırı) →
   `1800` (EmbeddingGemma için güvenlik paylı) oldu — production bu
   düzeltmeden önce sessizce 128 token'da bölüyordu.
2. **Yeni production seçicisi**: `app/services/chunking_secici.py` —
   `yontem_sec(content)`, 4 yöntemden (`mevcut`, `genellestirilmis_merge`,
   `semantik`, `overlap_recursive`) içerik türüne göre birini seçip
   çalıştırıyor.
3. `pdf_connector.py`/`markdown_connector.py` artık `list[Parca]`
   DEĞİL, HAM metin (`str`) döndürüyor — bölme kararını tamamen
   `chunking_secici.py`'ye bırakıyor. **Bilinçli tercih**: bu sayede
   `WikiPage.content`'te başlıklar (`#`/`##`) korunuyor (eskiden PDF
   sayfalarında kayboluyordu).
4. `sources.py` (`markdown_ekle`, `pdf_ekle`) ve `pages.py`
   (`sayfayi_indexle`) artık elle yazılmış 4 adımlık pipeline yerine
   `yontem_sec()` çağırıyor.
5. **Otomatik sınıflandırma + kavram çıkarma**: `sources.py`'deki
   upload akışı artık `PUT/POST` ile ayrı tetiklenen adımlar değil,
   embed'den hemen sonra OTOMATİK çalışıyor. `pages.py`'de
   `siniflandirmayi_uygula(db, sayfa)`, `concepts.py`'de
   `kavramlari_uygula(db, unitler)` olarak paylaşılabilir fonksiyonlara
   çıkarıldı (manuel `/classify`, `/extract-concepts` endpoint'leri de
   bunları kullanıyor).
6. `requirements.txt`: `langchain-text-splitters` + bağımlılıkları
   eklendi (`overlap_recursive` için gerekli).
7. `desktop_demo.py`: ayrı "Sınıflandır" ve "Kavram Çıkar" butonları
   KALDIRILDI — `SayfaDetayDialogu`'nda tek bir **"Yeniden İşle"**
   butonu ikisini sırayla tetikliyor (otomatik akış başarısız olursa
   ya da içerik güncellendikten sonra manuel yedek olarak).

**Tümü gerçek API/DB üzerinden test edildi** (geçici sayfalar
oluşturulup silindi) — bkz. oturum geçmişi.

## Sıradaki adım (HENÜZ YAPILMADI)

**Tüm veritabanını yeni seçiciyle yeniden işleyen bir migration.**

- **Kapsam netleşti (kullanıcı onayı):** SADECE türetilmiş veri
  silinip yeniden üretilecek — `SemanticUnit`, `ConceptNode`,
  `ConceptRelation`, `KavramGorulme`, `KavramTakmaAdi`, `OnerilenTur`,
  `SayfaBaglantisi`, `KavramBirlesmesi`. **`WikiPage` ve `Source`
  KORUNACAK** — hiçbir sayfa yeniden yüklenmeyecek.
- Chroma koleksiyonları (`semantic_units`, `concept_names`) da
  silinip yeniden kurulacak (embedding boyutu/içeriği değişecek).
- Her `WikiPage` için: `chunking_secici.yontem_sec(sayfa.content)` ile
  yeniden parçala → yeni `SemanticUnit`'ler → embed et →
  `siniflandirmayi_uygula` + `kavramlari_uygula` ile otomatik
  sınıflandır + kavram çıkar.
- **ÖNEMLİ, KULLANICI ONAYI ALINDI:** migration sonrası eski kavram
  grafiği ile yeni parçalar arasındaki bağlantı kaybolacak — kullanıcı
  bunu kabul etti ("şimdilik bağlantıyı kaybedelim, sonra ConceptNode'lari
  ne yapacağımızı düşünürüz"). Yani migration muhtemelen eski
  `ConceptNode`/`ConceptRelation`/`KavramGorulme` kayıtlarını da TAMAMEN
  SİLECEK, otomatik kavram çıkarma her sayfa için SIFIRDAN yeni bir
  kavram grafiği kuracak. **Bu, sayfa sayısı kadar LLM çağrısı demek —
  süre/maliyet göz önünde bulundurulmalı**, muhtemelen
  `migrate_embeddinggemma.py`'nin desenine benzer, backend KAPALIYKEN
  çalıştırılan bağımsız bir script (`migrate_chunking_secici.py` gibi)
  olarak yazılmalı.
- Migration bitince `POST /graph/global/yeniden-hesapla` da çağrılmalı
  (global graf, sıfırdan kurulan `KavramGorulme`'ye göre yeniden
  hesaplanmalı).

## Bilinmesi gereken diğer önemli noktalar

- **`chunking_secici.py`'nin kullandığı 4 yöntem:** `mevcut`,
  `genellestirilmis_merge`, `semantik`, `overlap_recursive`.
  (`cumle_bazli`, `semantik_stanza`, `split_then_merge_1100/600`
  sadece deneyde kaldı, production'a alınmadı — bu yüzden Stanza
  bağımlılığı da production'a EKLENMEDİ, sadece deney dosyalarında var.)
- **Test sırasında bulunan bir tuzak:** arka planda uvicorn
  başlatırken eski/yetim process'ler port 8000'i tutabiliyor —
  "exit code 3" (bind hatası) görülürse `Get-NetTCPConnection
  -LocalPort 8000` ile GERÇEK process bulunup öldürülmeli, yoksa eski
  (güncel olmayan) kodu çalıştıran bir sunucuya istek atılmış olur.
  Bu oturumda tam olarak bu yüzden bir test yanlış (eksik) sonuç
  vermişti.
- Detaylı bulgular, metrik tabloları ve içerik-türü kırılımı PR #2'nin
  açıklamasında var.
