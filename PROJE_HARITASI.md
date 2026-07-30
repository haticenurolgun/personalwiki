# PersonalWiki AI v2 — Proje Haritası (Referans)

> Bu dosyayı proje kökünde tut, VS Code'da yan sekmede açık bırak.
> Her yeni dosya yazarken buraya bakıp "bu dosya nerede duruyor,
> görevi ne" diye kontrol edebilirsin.

---

## Genel akış (bir bakışta)

```
main.py  --(kurar, router'lari baglar)-->  app/routers/*.py
                                                  |
                                                  v
                                    app/services/*.py  (is mantigi)
                                                  |
                                                  v
                                    app/models/db_models.py (veritabani)
                                                  |
                                                  v
                                    app/embeddings/embedding_servisi.py (vektor)
```

---

## Kok dizin

| Dosya | Görevi |
|---|---|
| `main.py` | Uygulamanın giriş noktası. FastAPI nesnesini oluşturur, tüm router'ları `app.include_router(...)` ile bağlar. **İş mantığı YOK** — sadece kurulum. ~30-40 satır olmalı. |
| `.env` | Gizli ayarlar (örn. `GEMINI_API_KEY=...`). Asla git'e commit edilmez. |
| `requirements.txt` | Kurulu paketlerin listesi (`pip freeze > requirements.txt` ile üretilir). |

---

## `app/database.py`

**Görevi:** Veritabanı bağlantısını kurar.

- Async SQLAlchemy engine'i oluşturur (`create_async_engine`, `sqlite+aiosqlite:///...`)
- `AsyncSession` üreten bir fonksiyon/dependency tanımlar (`get_db` gibi)
- Tabloları ilk açılışta oluşturan bir fonksiyon içerir

---

## `app/models/`

| Dosya | Görevi |
|---|---|
| `db_models.py` | SQLAlchemy tablo tanımları: `WikiPage`, `Source`, `SemanticUnit`, `ConceptNode`, `KavramTakmaAdi`, `ConceptRelation`, `OnerilenTur`. Veritabanının "şeması" burada. |
| `schemas.py` | Pydantic modelleri — API'ye giren/çıkan verinin şekli. `db_models.py`'deki tablolarla KARIŞTIRILMAMALI: biri veritabanı satırı, diğeri API mesajı. |

---

## `app/routers/`

Her dosya, belirli bir konu etrafındaki endpoint'leri toplar. `main.py` bunları import edip bağlar.

| Dosya | Endpoint'ler | Görevi |
|---|---|---|
| `sources.py` | `POST /sources/markdown`, `POST /sources/web`, `POST /sources/pdf` | Yeni içerik ekleme (3 farklı kaynak türü) |
| `pages.py` | `GET /pages`, `GET /pages/{id}`, `POST /pages/{id}/index`, `POST /pages/{id}/extract-concepts`, `GET /pages/{id}/graph` | Sayfa okuma, indeksleme, kavram çıkarımı, grafik görüntüleme |
| `search.py` | `GET /search` | Hibrit arama (vektör + kavram grafiği) |
| `chat.py` | `POST /chat` | RAG sohbet |
| `ontology.py` | `GET /ontology/suggestions` | Ontolojiye eklenmemiş tip önerileri |

**Kural:** Router dosyaları veritabanı sorgusu yazabilir (SQLAlchemy `select(...)`) ama karmaşık iş mantığını (LLM çağrısı, embedding hesaplama, metin bölme) `services/` veya `embeddings/` katmanına devreder — kendi içinde yazmaz.

---

## `app/services/`

**Kural (mimarinin en önemli ilkesi):** Bu klasördeki dosyalar veritabanına HİÇBİR ŞEY yazmaz. Girdi alır, sade Python nesneleri (`dataclass`) döndürür. Bu sayede her biri veritabanı olmadan tek başına test edilebilir.

| Dosya | Görevi |
|---|---|
| `structural_parser.py` | Markdown başlıklarına (`#`, `##`) göre metni parçalara böler |
| `semantic_splitter.py` | Başlık yoksa, cümle embedding benzerliğine göre anlam kaymasını bulup böler |
| `concept_extractor.py` | Gemini'ye metin gönderip tiplendirilmiş kavram + ilişki çıkarır. Ontoloji (sabit tip listeleri) burada tanımlı. **Async + `asyncio.gather` ile paralel çağrı burada olacak.** |
| `chat_servisi.py` | Bağlam + soru alır, Gemini ile RAG cevabı üretir |

---

## `app/embeddings/embedding_servisi.py`

**Görevi:** Metni vektöre çevirir (`sentence-transformers`), Chroma'ya yazar/okur, benzerlik araması yapar.

- `local_files_only=True` unutulmamalı (bkz. eski projedeki ders — yoksa Hugging Face Hub'a gereksiz istek atıp yavaşlıyor)
- Chroma'nın veri klasörü mutlak yol ile hesaplanmalı

---

## `app/connectors/`

| Dosya | Görevi |
|---|---|
| `web_connector.py` | Bir URL'den `httpx.AsyncClient` ile (async!) HTML çeker, BeautifulSoup ile temizler, asıl metni çıkarır |
| `pdf_connector.py` | Yüklenen PDF dosyasından `pypdf` ile metin çıkarır |

---

## `app/uploads/`

Yüklenen PDF dosyalarının fiziksel olarak saklandığı klasör. Kod yok, sadece veri.

---

## Graph mimarisi (2 katmanlı, kullanıcı kararı ile netleşti)

**Katman 1 — Sayfa içi graph:**
- `ConceptNode` ve `ConceptRelation` zaten `page_id` üzerinden bir sayfaya bağlı
- `GET /pages/{id}/graph` bu tabloları `WHERE page_id = X` ile filtreleyerek döner
- Ekstra tablo gerekmiyor, sadece filtrelenmiş bir sorgu

**Katman 2 — Global graph (sayfalar arası, "içindekiler" haritası gibi):**
- Yeni tablo: `SayfaBaglantisi` (sayfa_id_1, sayfa_id_2, ortak_kavram_adi, olusturulma_tarihi)
- Düğümler: WikiPage'lerin kendisi (kavramlar değil)
- Kenarlar: iki sayfa aynı/eşanlamlı bir kavramı paylaşıyorsa (KavramTakmaAdi tablosu üzerinden eşanlamlılar da dahil)
- **Hesaplama şekli:** anlık değil, önceden hesaplanıp saklanan tablo — ama olay bazlı otomatik senkronizasyon YOK. Bunun yerine `global_graf_yeniden_hesapla()` adlı bir fonksiyon var, bu fonksiyon çağrıldığında tabloyu tamamen temizleyip sıfırdan yeniden kurar (kısmi güncelleme yapmaz, DELETE + yeniden INSERT).
- Bu fonksiyon `POST /pages/{id}/extract-concepts` sonrasında veya manuel `POST /graph/global/yeniden-hesapla` ile tetiklenir.
- **Neden bu yaklaşım seçildi:** tam anlık hesaplama basit ama her istekte tekrar tekrar hesaplama yapar; tam olay-bazlı senkronizasyon (her ekleme/silmede otomatik güncelleme) karmaşık ve hataya açık. "Yeniden hesapla" fonksiyonu ikisi arasında bir denge: veri saklanıyor (hızlı okunuyor) ama güncelleme mantığı basit ve tutarlı (race condition riski yok).

## PROJENİN ASIL AMACI (netleşti — bu tüm tasarım kararlarını yönlendirir)

> PersonalWiki AI, kullanıcının dağınık dosyalarını (markdown notları, PDF'ler,
> web sayfaları) tek bir yerde toplayan, hem **"bu dosya ne hakkındaydı / nerede"**
> tarzı HATIRLAMA sorularına hem de **"1NF nedir"** tarzı İÇERİK sorularına
> aynı arama kutusundan cevap veren bir kişisel bilgi asistanı.

Bunun mimariye etkileri:
- `WikiPage.title` opsiyonel olabilmeli — kullanıcı vermezse dosya
  yüklendiğinde LLM otomatik özet üretip başlık olarak kullanacak
  (pdf_connector / web_connector içeriği çektikten sonra tetiklenecek
  küçük bir LLM çağrısı).
- `GET /search` hem semantik içerik cevabını HEM DE "hangi WikiPage/Source'a
  ait, hangi dosya adıyla, ne zaman eklendi" bilgisini BİRLİKTE döndürmeli —
  tek arama kutusu, iki ihtiyacı da karşılıyor.
- `Source` tablosuna muhtemelen bir "orijinal dosya adı" alanı eklenmesi
  gerekebilir (kullanıcının bildiği isim, sunucudaki kayıt yolundan farklı
  olabilir — örn. kullanıcı için "staj_raporu_2025.pdf", sunucuda
  "app/uploads/xyz123.pdf").

## Knowledge-base tabanlı arama prensibi (RAG)

Sistem, kullanicinin kendi yukledigi icerikten (knowledge base) DISARI
CIKMAMALI. Yani LLM'in genel egitim bilgisi degil, SADECE kullanicinin
yukledigi dosyalardan gelen baglam kullanilarak cevap uretilmeli.

Bunun teknik karsiligi (chat_servisi.py'de uygulanacak):
1. Kullanici soru sorar
2. Embedding araması ile kullanicinin KENDI icerigi icinden en alakali
   parcalar bulunur (benzer_parcalari_bul)
3. Bu parcalar, LLM'e "SADECE bu baglamdaki bilgiyi kullanarak cevap ver,
   yoksa yok oldugunu soyle" talimatiyla birlikte gonderilir
4. Bu sayede LLM'in kendi genel bilgisini "uydurmasi" (halüsinasyon)
   pratikte engellenmis olur

## Kavram çıkarımı prensibi: Ontoloji hizalaması + Deduplication

Kullanıcının paylaştığı "Wikontic" akademik çalışmasının metodolojisi
referans alınıyor (bkz. görsel: metin -> aday üçlemeler -> ontoloji
hizalaması -> mevcut bilgi grafiğine deduplike ederek ekleme).

concept_extractor.py bu üç aşamayı uygulayacak:

1. **Aday çıkarım:** LLM, metinden (varlık, iliski, varlik) üçlemeleri
   çıkarır (örn. "Nolan yönetti Inception").

2. **Ontoloji hizalaması:** Çıkarılan varlıklar ve ilişkiler, ÖNCEDEN
   TANIMLI bir ontolojiye (varlık tipleri + ilişki tipleri) göre
   sınıflandırılır. Ontolojide olmayan yeni bir tip önerilirse,
   OnerilenTur tablosuna düşer (otomatik onaylanmaz, kullanıcı/admin
   onayı bekler) — bu eski projede de vardı, korunuyor.

3. **Deduplication (mevcut KG'ye ekleme):** Yeni çıkarılan bir kavram,
   veritabanına eklenmeden önce "bu zaten var mı" diye kontrol edilir:
   - Aynı isimde bir ConceptNode var mı?
   - KavramTakmaAdi tablosunda bu ismin bir eşanlamlısı var mı
     (örn. "Nolan" ile "Christopher Nolan" aynı kavram sayılsın)?
   - Varsa: yeni node oluşturulmaz, var olan node'a bağlanılır
     (farklı sayfalardan gelse bile aynı kavram = tek node).
   - Yoksa: yeni ConceptNode oluşturulur.

   Bu mantık, daha önce konuşulan "global graph" (sayfalar arası
   bağlantı) fikriyle doğrudan bağlantılı: iki sayfa aynı ConceptNode'a
   bağlıysa, bu iki sayfa global graph'ta otomatik olarak bağlanmış olur.

## İleride yapılacaklar (ertelenen kararlar)

- **Uzaklık eşiği (threshold):** Şu an GET /search ve POST /chat, "en yakın N sonucu getir" mantığıyla çalışıyor, ama yeterince yakın olmayan (alakasız) sonuçları da zorla listeye dahil ediyor. İleride bir uzaklık eşiği eklenip (örn. belli bir değerden uzak sonuçlar bağlama dahil edilmesin) hem LLM'e daha temiz bağlam verilmesi hem de kullanilan_kaynaklar listesinin daha doğru olması sağlanabilir. Test edilirken gözlemlendi: "event loop nedir" sorusuna 3 kaynak dönmüştü, oysa sadece 1 tanesi gerçekten alakalıydı.

## Ontoloji (nihai karar — concept_extractor.py bunu kullanacak)

**Varlık (kavram) tipleri (10 tip):**
| Tip | Açıklama | Örnek |
|---|---|---|
| KONU | Genel bir bilgi alanı/başlık | "Veritabanı Normalizasyonu" |
| TERIM | Teknik bir terim/tanım | "1NF", "Event Loop" |
| DOSYA | Yüklenen bir dosyanın kendisi | "staj_raporu.pdf" |
| KISI | Bahsedilen bir kişi | "Christopher Nolan" |
| PROJE | Bir proje adı | "Bitirme Projesi X" |
| ARAC | Kullanılan bir yazılım/araç/teknoloji | "FastAPI", "Chroma" |
| TARIH_OLAYI | Belirli bir tarihe bağlı olay | "2025 Bootcamp Başlangıcı" |
| KURUM | Şirket/okul/organizasyon | "Anthropic", "XYZ Üniversitesi" |
| KAYNAK | Dış bir referans (makale, kitap, web sitesi) | "Wikontic makalesi" |
| GOREV | Yapılacak bir iş/görev | "PDF connector yazmak" |

**İlişki tipleri (8 tip):**
| İlişki | Açıklama | Örnek |
|---|---|---|
| ILGILI | Genel ilişki, başka hiçbiri uymuyorsa | "Async" ILGILI "Event Loop" |
| ICERIR | Bir kavram diğerini kapsıyor | "Normalizasyon" ICERIR "1NF" |
| ONKOSUL | Biri diğerinin önkoşulu | "1NF" ONKOSUL "2NF" |
| BAHSEDER | Bir dosya/kaynak, bir kavramdan bahsediyor | "staj_raporu.pdf" BAHSEDER "Python" |
| KULLANIR | Bir proje/görev, bir aracı kullanıyor | "Bitirme Projesi" KULLANIR "FastAPI" |
| AITTIR | Bir şey birine/bir kuruma ait | "Staj Raporu" AITTIR "XYZ Şirketi" |
| PARCASI | Biri diğerinin bir parçası | "1NF" PARCASI "Normalizasyon Süreci" |
| KAYNAKLANIR | Bir bilgi bir kaynaktan geliyor | "Bu not" KAYNAKLANIR "Wikontic makalesi" |

Ontolojide olmayan yeni bir tip LLM tarafından önerilirse, OnerilenTur
tablosuna düşer, otomatik onaylanmaz (bkz. yukarıdaki "ontoloji hizalaması"
bölümü).

## Ontoloji dışı tip önerisi ne olacak (nihai karar)

LLM, kavram çıkarırken ontolojide OLMAYAN bir tip önerirse (örn. "GPU" için
"DONANIM" tipi, oysa ontolojide böyle bir tip yok):

**Strateji B seçildi: reddet + OnerilenTur'a düş, insan onayı bekle.**

Akış:
1. LLM'den kavram çıkarımı istenir, prompt'ta mevcut ontoloji listesi verilir
2. LLM bir kavram döndürür: {"isim": "GPU", "tip": "DONANIM"}
3. Kod kontrol eder: "DONANIM", KAVRAM_TIPLERI listesinde var mı?
4. YOKSA: bu kavram ConceptNode olarak KAYDEDİLMEZ. Bunun yerine
   OnerilenTur tablosuna bir satır düşülür/sayacı artırılır
   (onerilen_tip="DONANIM", ornek_kavram="GPU", kac_kere_onerildi=N).
   Otomatik ontoloji genişlemesi YOK — proje sahibi bu tabloya bakıp
   elle karar verir (ontolojiye eklenir mi, eklenmez mi).
5. VARSA: normal şekilde ConceptNode olarak kaydedilir.

Bu, ontolojinin kontrolsüz büyümesini engelliyor, aynı zamanda hangi
yeni tiplere gerçekten ihtiyaç olduğu konusunda veri topluyor.

## Masaüstü Uygulaması ve Toplu Dosya Yükleme (yeni yön)

> Bu bölüm, projenin taşınacağı yeni bir yönü tanımlıyor: kullanıcının
> masaüstünde dağınık duran dosyalarını (kendi SEÇTİĞİ dosyaları,
> otomatik tüm klasör/masaüstü taraması DEĞİL) uygulamaya sürükleyip
> içeri aktarabilmesi ve bunun gerçek bir masaüstü uygulaması olarak
> paketlenmesi.

### Genel yön (karar verildi)

- **Masaüstü paketleme:** Electron değil, **Tauri**. Gerekçe: çok
  daha hafif (Electron ~150MB'a karşı Tauri ~10MB civarı), mevcut
  Python/FastAPI backend'i bir "sidecar" process olarak içine
  gömülebiliyor - backend kodunda esaslı bir değişiklik gerektirmiyor,
  Rust bilgisi de gerekmiyor (sadece config).
- **Dosya seçimi:** sürükle-bırak alanı (frontend'de yeni bir sayfa).
- **Sınıflandırma kapsamı:** SADECE kullanıcının sürükleyip bıraktığı
  dosyalarda çalışır. Otomatik olarak tüm masaüstünü veya bir klasörü
  tarayıp sınıflandırma YOK - bu bilinçli bir sınır, kullanıcı hangi
  dosyanın sisteme gireceğine kendisi karar veriyor.
- Bu bir bootcamp projesi değil, zaman baskısı yok - kararlar
  kalibrasyon.py'deki gibi düşünülüp test edilerek verilecek, aceleye
  getirilmeyecek.

### Sıralama (önce temel, sonra üstüne ekleme)

Tauri'yi en başta kurup her adımda paketleme derdiyle uğraşmak yerine,
önce her şeyi TARAYICIDA çalışır hale getirip paketlemeyi EN SONA
bırakma kararı verildi:

1. **Backend**: yeni connector'lar (`text_connector.py`,
   `docx_connector.py`) + `POST /sources/upload` endpoint'i
   (çoklu dosya kabul eden, tip algılayıp doğru connector'a yönlendiren)
2. **Sınıflandırma mantığı**: yüklenen dosyaya LLM ile kategori/etiket
   önerisi - `concept_extractor.py`'nin yanına ayrı bir servis olarak
   düşünülüyor (henüz tasarlanmadı)
3. **Sürükle-bırak arayüzü**: `app/static/` altına yeni bir HTML sayfası
   (`upload.html`), graph.html ile aynı desende (fetch + vis benzeri
   basit JS, framework yok)
4. **Tauri paketleme**: en son adım, her şey tarayıcıda çalıştıktan sonra

### 1. adım için netleşen teknik kararlar

| Konu | Karar | Gerekçe |
|---|---|---|
| Desteklenecek dosya tipleri | `.md`, `.txt`, `.pdf`, `.docx` | Kullanıcının masaüstünde gerçekte bulunma ihtimali en yüksek 4 tip |
| docx → parçalama yaklaşımı | **Seçenek B**: docx'i önce markdown'a çevir, sonra mevcut `structural_parser.markdown_bol` ile böl | `pdf_connector.py` ile AYNI deseni izliyor (pymupdf4llm de aynı şekilde önce markdown'a çevirip sonra `markdown_bol`'a sokuyor) - tek bir bölme fonksiyonu tüm dosya tipleri için tekrar kullanılıyor, ayrı ayrı bölme mantığı yazılmıyor. Alternatif olan "python-docx ile doğrudan Heading stillerini oku" seçeneği reddedildi çünkü Word dosyalarında gerçek "Heading" stili kullanılmamışsa (çoğu gündelik dosyada böyle) bölme hiç çalışmaz. |
| docx → markdown dönüşüm kütüphanesi | **pypandoc** | Mammoth (dış bağımlılık gerektirmeyen alternatif) yerine tercih edildi - pypandoc'un dönüşüm motoru (pandoc) daha olgun/güçlü. Bunun bedeli: sistemde ayrıca pandoc kurulu olması gerekiyor (kullanıcı tarafından elle kurulacak, pip ile gelmiyor). |
| `.md`/`.txt` için connector | **Ayrı bir `text_connector.py`** yazılacak | Mevcut `POST /sources/markdown` endpoint'i (kullanıcının DOĞRUDAN yapıştırdığı metin için) ile karıştırılmasın, dosyadan okuma akışı tutarlılık için `connectors/` klasöründe kendi dosyasında yaşasın. |
| `POST /sources/upload` | **Tek seferde birden fazla dosya (liste)** kabul edecek | Sürükle-bırak ile aynı anda birden fazla dosya seçilebilmesi gerekiyor - tek dosya kabul eden bir endpoint frontend'de gereksiz döngü/çoklu istek gerektirirdi. |

### Henüz karara bağlanmamış açık noktalar

- `text_connector.py`, başlıksız düz `.txt` dosyalarını nasıl bölecek?
  Muhtemelen tamamı tek bir `MetinParcasi` olarak mı kalacak, yoksa
  ileride yazılacak `semantic_splitter.py` (anlam kaymasına göre bölme,
  henüz yazılmadı) mı devreye girecek - netleşmedi.
- `POST /sources/upload` dosya tipini nasıl algılayacak: sadece dosya
  uzantısına mı bakılacak, yoksa MIME type de kontrol edilecek mi -
  netleşmedi.
- Sınıflandırma (kategori/etiket önerisi) mimarisi henüz hiç
  tasarlanmadı - ontoloji hizalaması gibi sabit bir kategori listesi mi
  olacak, yoksa serbest metin etiketleme mi - bu 2. adımda ele alınacak.

## Neden bu ayrım önemli (mülakat/jüri sorusu olabilir)

- **Router** = "hangi adrese hangi istek geldi, ne cevap dönecek" (HTTP katmanı)
- **Service** = "asıl iş mantığı ne" (LLM'e ne soracağız, metni nasıl böleceğiz)
- **Model** = "veri nasıl saklanıyor" (tablo şeması)
- **Embedding/Connector** = "dış dünyayla (Chroma, Gemini, web, dosya sistemi) nasıl konuşuyoruz"

Bu ayrım olmadan (eski projedeki gibi tek `main.py`'de her şey), bir değişiklik yapmak istediğinde nereye bakacağını bulmak zorlaşır ve kod tek bir kişinin kafasında yaşayan bir "yumak" haline gelir — bu tam olarak modülerliğin çözmeye çalıştığı sorun.