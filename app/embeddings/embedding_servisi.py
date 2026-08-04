import os
import numpy as np
from sentence_transformers import SentenceTransformer
import chromadb


BU_DOSYANIN_KLASORU = os.path.dirname(os.path.abspath(__file__))
CHROMA_VERI_YOLU = os.path.join(BU_DOSYANIN_KLASORU, "..", "..", "chroma_data")


# paraphrase-multilingual-MiniLM-L12-v2'den (384 boyut) EmbeddingGemma-
# 300M'e (768 boyut) gecildi - retrieval/RAG icin ozel egitilmis, cok
# daha uzun context penceresi (2048 token) olan daha guclu bir model.
# Vektor boyutu DEGISTI, bu yuzden Chroma'daki eski koleksiyonlar
# uyumsuz - gecis migrate_embeddinggemma.py ile yapildi (eski
# koleksiyonlar silinip tum veri yeniden embed edildi).
#
# EmbeddingGemma, dogru embed kalitesi icin metnin GOREVINE gore farkli
# prompt onekleri ister (bkz. config_sentence_transformers.json'daki
# "prompts" sozlugu) - asagidaki encode() cagrilarinda prompt_name
# bunun icin veriliyor: "query" (arama sorgusu), "document" (aranacak
# icerik), "STS" (iki kisa metnin ANLAMCA ayni sey olup olmadigini
# kontrol etme - kavram/konu ismi eslestirme).
_model = SentenceTransformer("google/embeddinggemma-300m", local_files_only=True)

# Chroma istemcisini olustur 
_chroma_client = chromadb.PersistentClient(path=CHROMA_VERI_YOLU)

# metadata={"hnsw:space": "cosine"} -> Chroma varsayilan olarak L2
# (Oklid) mesafesi kullanir, biz ise KOZINUS mesafesi istiyoruz. Kozinus
# mesafesi 0 ile 1 arasinda oldugu icin "benzerlik = 1 - uzaklik" diye
# yorumlamasi cok daha kolay ve sezgisel. Ayrica all-MiniLM-L6-v2 kendi
# ciktisini zaten birim vektore (unit vector) normalize ediyor - bu
# durumda L2 kare uzakligi ile kozinus uzakligi SIRALAMA olarak
# matematiksel denk (L2kare = 2 - 2*kozinus_benzerlik), ama bunu ACIKCA
# belirtmek, modelin bu normalize ozelligine sessizce guvenmek yerine
# niyetimizi kod icinde net kilar - ileride farkli (normalize etmeyen)
# bir modele gecilirse sessizce yanlis siralama vermez.
_koleksiyon = _chroma_client.get_or_create_collection(
    name="semantic_units",
    metadata={"hnsw:space": "cosine"},
)

# Kavram isimlerini karsilastirmak icin AYRI bir koleksiyon. Neden ayri?
# semantic_units koleksiyonu METIN PARCALARINI (uzun paragraflar) tutuyor,
# bu koleksiyon ise sadece KISA KAVRAM ISIMLERINI (orn. "Kaan Aslan",
# "1NF") tutacak - ikisini karistirmak anlamsiz sonuclar verir.
_kavram_koleksiyonu = _chroma_client.get_or_create_collection(
    name="concept_names",
    metadata={"hnsw:space": "cosine"},
)

def token_sayisi(metin: str) -> int:
    """
    Verilen metnin, embedding modelinin GERCEK tokenizer'iyla kac token
    oldugunu sayar. structural_parser.parcalari_boyuta_gore_bol'a
    "token_sayici" olarak verilmek uzere - o dosya bu modele dogrudan
    bagimli olmak istemedigi icin, gercek sayim burada yasiyor.
    """
    return len(_model.tokenizer.encode(metin))


def parcayi_kaydet(unit_id: int, page_id: int, icerik: str):
    """
    Bir SemanticUnit'in icerigini vektore cevirir ve Chroma'ya kaydeder.

    unit_id: SemanticUnit tablosundaki id (Chroma'da da AYNI id ile
             kaydediyoruz ki ileride SQLite <-> Chroma arasinda
             eslestirme yapabilelim)
    page_id: hangi sayfaya ait oldugu (arama sonuclarinda filtrelemek
             icin ise yarayacak)
    icerik:  vektore cevrilecek asil metin
    """

    # 1) Metni vektore cevir. .encode(), bir string alir, sayilardan
    #    olusan bir liste (vektor) doner. .tolist() ile numpy dizisini
    #    normal Python listesine ceviriyoruz - Chroma bunu bekliyor.
    #    prompt_name="document": bu, ARANACAK icerik tarafi (bkz.
    #    benzer_parcalari_bul'daki "query" tarafi).
    vektor = _model.encode(icerik, prompt_name="document").tolist()

    # 2) Chroma'ya kaydet. upsert = "update or insert" - eger bu id
    #    zaten varsa GUNCELLER, yoksa YENI ekler. Ayni id'yi tekrar
    #    kaydetmeye calistigimizda hata almamak icin add() yerine
    #    upsert() kullaniyoruz.
    _koleksiyon.upsert(
        ids=[str(unit_id)],           # Chroma id'leri STRING bekler
        embeddings=[vektor],
        documents=[icerik],           # asil metni de saklıyoruz, arama
                                        # sonucunda geri okuyabilelim diye
        metadatas=[{"page_id": page_id}],   # filtreleme icin ekstra bilgi
    )
    
    
def parcalari_sil(unit_idler: list[int]):
    """
    Verilen unit_id'lere ait vektorleri Chroma'dan siler.
    Bir sayfa silinirken, o sayfaya ait SemanticUnit'lerin embedding'leri
    de Chroma'da "hayalet" olarak kalmasin diye kullanilir.

    unit_idler: silinecek SemanticUnit id'lerinin listesi
    """
    if not unit_idler:
        return

    # Chroma id'leri STRING bekliyor - kayit ederken de string
    # kullanmistik (bkz. parcayi_kaydet), o yuzden burada da ceviriyoruz.
    _koleksiyon.delete(ids=[str(unit_id) for unit_id in unit_idler])


def kavram_kaydet(node_id: int, isim: str, tip: str):
    """
    Bir ConceptNode'un ismini vektore cevirip concept_names
    koleksiyonuna kaydeder. Yeni bir ConceptNode olusturuldugunda
    cagrilir - boylece ileride baska bir kavram geldiginde, bununla
    ANLAMCA benzer mi diye karsilastirabiliriz.

    node_id: ConceptNode tablosundaki id (Chroma'da da AYNI id ile
             kaydediyoruz - SQLite <-> Chroma eslestirmesi icin)
    isim:    kavramin standart_isim'i (orn. "Kaan Aslan")
    tip:     kavramin tipi (orn. "KISI") - metadata olarak saklaniyor,
             cunku benzerlik aramasi yaparken SADECE AYNI TIPTEKI
             kavramlarla karsilastirma yapacagiz (bir KISI ile bir
             ARAC hicbir zaman "ayni kavram" sayilmamali).
    """
    # prompt_name="STS": kavram isimleri arasinda RETRIEVAL degil,
    # simetrik ANLAMSAL ESLESME kontrolu yapiyoruz (bkz. benzer_kavram_bul).
    vektor = _model.encode(isim, prompt_name="STS").tolist()

    _kavram_koleksiyonu.upsert(
        ids=[str(node_id)],
        embeddings=[vektor],
        documents=[isim],
        metadatas=[{"tip": tip}],
    )


def kavram_sil(node_idler: list[int]):
    """
    Verilen node_id'lere ait vektorleri concept_names koleksiyonundan
    siler. Bir ConceptNode silindiginde (orn. merge sirasinda ya da
    sayfa silinirken) cagrilir.
    """
    if not node_idler:
        return

    _kavram_koleksiyonu.delete(ids=[str(node_id) for node_id in node_idler])


def benzer_kavram_bul(isim: str, tip: str, esik: float) -> dict | None:
    """
    Verilen isimde ve tipte bir kavrama, ANLAMCA en yakin mevcut
    kavrami bulur - EGER benzerlik esigin ustundeyse.

    isim:  aranacak kavramin ismi (orn. "Development Team")
    tip:   sadece bu TIPTEKI kavramlarla karsilastir (orn. "TERIM")
    esik:  0.0 - 1.0 arasi bir deger. Benzerlik bu degerden BUYUK ESIT
           degilse, esles bulunamadi sayilir (None doner).

    Donen deger: None (eslesme yok) ya da
        {"node_id": int, "isim": str, "benzerlik": float}
    """
    # Koleksiyon bombosa Chroma hata firlatir - once kontrol edelim.
    if _kavram_koleksiyonu.count() == 0:
        return None

    vektor = _model.encode(isim, prompt_name="STS").tolist()

    sonuclar = _kavram_koleksiyonu.query(
        query_embeddings=[vektor],
        n_results=5,  # en yakin 5 sonucu al, sonra tip filtresi + esik uygula
        where={"tip": tip},   # SADECE ayni tipteki kavramlarla karsilastir
    )

    # Chroma'nin dondurdugu liste bos olabilir (bu tipte hic kavram yoksa).
    if not sonuclar["ids"][0]:
        return None

    en_yakin_id = sonuclar["ids"][0][0]
    en_yakin_isim = sonuclar["documents"][0][0]
    uzaklik = sonuclar["distances"][0][0]

    # Kozinus mesafesi 0 (ayni) ile 2 (tam zit) arasi degisebilir, ama
    # pratikte metin embedding'lerinde 0-1 araligindadir. Benzerlige
    # cevirmek icin: benzerlik = 1 - uzaklik.
    benzerlik = 1 - uzaklik

    if benzerlik >= esik:
        return {
            "node_id": int(en_yakin_id),
            "isim": en_yakin_isim,
            "benzerlik": benzerlik,
        }

    return None


# en_benzer_konuyu_bul, LLM'in "bu konu, mevcut listedeki X ile ayni"
# dedigi eslesmeyi DOGRULAMAK (bir GUVENLIK AGI olarak) icin kullanilir
# - LLM'in kendi eslestirme kararinin YERINE GECMEK icin degil (bkz.
# classifier.py'deki NEDEN IKI ALAN aciklamasi). Bu yuzden esik BILINCLI
# OLARAK DUSUK/TOLERANSLI secildi: amac sadece capalama-onyargili,
# TAMAMEN ALAKASIZ eslesmeleri (orn. "Gravio" ile "ATLAS", olculen
# benzerlik 0.26) yakalamak - LLM'in kendi dunya bilgisiyle yaptigi,
# kelime bazinda dusuk benzerlikli ama GERCEKTEN dogru esleme
# (orn. "PostgreSQL" ile "Veritabanlari") kararlarina KARISMAMAK.
KATEGORI_DOGRULAMA_ESIGI = 0.40


def en_benzer_konuyu_bul(konu: str, mevcut_konular: list[str], esik: float = KATEGORI_DOGRULAMA_ESIGI) -> str | None:
    """
    Verilen bir konu ismine, mevcut_konular listesinden ANLAMCA en
    yakin olani (esigin ustundeyse) dondurur. Chroma'ya hic ihtiyac
    yok - kisisel bir wiki'deki konu sayisi kucuk oldugu icin (onlarca,
    yuzlerce degil), dogrudan bellekte kozinus benzerligi hesaplamak
    yeterli ve daha basit.
    """
    if not mevcut_konular:
        return None

    konu_vektoru = _model.encode(konu, prompt_name="STS")
    aday_vektorleri = _model.encode(mevcut_konular, prompt_name="STS")

    en_iyi_benzerlik = -1.0
    en_iyi_aday = None
    for aday, aday_vektoru in zip(mevcut_konular, aday_vektorleri):
        # Model ciktisi zaten birim vektor (unit vector) oldugu icin
        # (bkz. embedding_servisi.py'deki cosine yorumu), iki vektorun
        # ic carpimi (dot product) DOGRUDAN kozinus benzerligine esittir.
        benzerlik = float(np.dot(konu_vektoru, aday_vektoru))
        if benzerlik > en_iyi_benzerlik:
            en_iyi_benzerlik = benzerlik
            en_iyi_aday = aday

    if en_iyi_benzerlik >= esik:
        return en_iyi_aday

    return None


def benzer_parcalari_bul(sorgu: str, sonuc_sayisi: int = 5) -> list[dict]:
        """
        Verilen sorgu metnine ANLAMCA en yakin parcalari bulur.

        sorgu: kullanicinin arama metni (orn. "1NF nedir")
        sonuc_sayisi:  kac tane sonuc dondurulecek
        """

        # 1) Sorgu metnini de AYNI modelle vektore cevir - aranan ve
        #    aranilan seyin ayni "dilde" (vektor uzayinda) olmasi sart.
        #    prompt_name="query": parcayi_kaydet'teki "document" tarafiyla
        #    eslesen, retrieval'in sorgu tarafi.
        sorgu_vektoru = _model.encode(sorgu, prompt_name="query").tolist()

        # 2) Chroma'ya "bu vektore en yakin N sonucu getir" diye sor.
        sonuclar = _koleksiyon.query(
            query_embeddings=[sorgu_vektoru],
            n_results=sonuc_sayisi,
        )

        # 3) Chroma'nin dondurdugu format biraz karmasik (liste icinde
        #    liste) - bunu sadelestirip, her sonucu okunabilir bir sozluk
        #    olarak dondurelim.
        bulunan_parcalar = []
        for i in range(len(sonuclar["ids"][0])):
            bulunan_parcalar.append({
                "unit_id": int(sonuclar["ids"][0][i]),
                "icerik": sonuclar["documents"][0][i],
                "page_id": sonuclar["metadatas"][0][i]["page_id"],
                "benzerlik_uzakligi": sonuclar["distances"][0][i],
            })

        return bulunan_parcalar


def cumle_benzerlik_vektorleri(cumleler: list[str]) -> np.ndarray:
    """
    Verilen cumle listesini, ANLAMSAL BENZERLIK (retrieval degil)
    gorevi icin embedding vektorlerine cevirir - chunking_secici.py'deki
    "semantik" bolme yontemi, ardisik cumleler arasindaki kozinus
    uzakligina bakarak konu degisimini tespit etmek icin bunu kullanir.

    prompt_name="STS" (en_benzer_konuyu_bul'daki ile ayni gorev):
    burada bir sorgu/dokuman ayrimi yok, iki metnin ANLAMCA ne kadar
    benzer oldugunu olcuyoruz - EmbeddingGemma'nin bu gorev icin
    onerdigi prompt bu.

    Donen vektorler birim vektor (unit vector) oldugu icin, iki vektor
    arasindaki ic carpim (np.dot) DOGRUDAN kozinus benzerligine esittir
    (bkz. en_benzer_konuyu_bul'daki ayni yorum).
    """
    return _model.encode(cumleler, prompt_name="STS")