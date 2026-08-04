""" chunking yöntemlerini karşılaştırmak için test dosyası """

import re

import numpy as np
import stanza
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.structural_parser import (
    MetinParcasi,
    markdown_bol,
    liste_maddelerine_gore_bol,
    parcalari_boyuta_gore_bol,
    bos_parcalari_temizle,
    _kucuk_artiklari_birlestir,
)

from app.embeddings.embedding_servisi import token_sayisi, _model

def mevcut_yontem(content:str) -> list[MetinParcasi]:

    """     Su an /sources/markdown ve /pages/{id}/index'te GERCEKTEN kullanilan
    pipeline - deneyin BASELINE'i budur, diger tum yontemler buna karsi
    kiyaslanacak.
    """

    parcalar = markdown_bol(content)
    parcalar = liste_maddelerine_gore_bol(parcalar)
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi, maks_token=1800)
    parcalar = bos_parcalari_temizle(parcalar)
    return parcalar


def yontem_genellestirilmis_merge(content: str) -> list[MetinParcasi]:
    """
    mevcut_yontem ile AYNI 4 adim, artı bir 5. adim: _kucuk_artiklari_
    birlestir.

    FARK: production'da (ve mevcut_yontem'de) bu birlestirme fonksiyonu
    SADECE parcalari_boyuta_gore_bol'un kendi icinde, TEK bir bolumden
    uretilen alt-parcalar arasinda calisiyor - yani BASTAN kucuk olan
    (hic bolunmemis) bir bolum (orn. 15 token'lik kisa bir baslik) asla
    komsu bolumle birlesmiyor, kucuk kalmaya devam ediyor.

    Burada AYNI fonksiyonu, sayfanin TUM nihai parca listesine
    (farkli basliklardan/liste maddelerinden gelen parcalar dahil)
    uyguluyoruz - Adaptive Chunking makalesindeki "Tiny-chunk merging"
    post-processing adimiyla ayni fikir (bkz. makale bolum 2.2).

    ONEMLI DAVRANIS FARKI: _kucuk_artiklari_birlestir, birlesen parcanin
    baslik/seviye bilgisini HEP ONCEKI parcadan alıyor - yani kucuk bir
    parca FARKLI bir basligin altindaki parcayla birlesirse, olusan
    parcanin "baslik" metadatasi artik icerigin TAMAMINI dogru
    yansitmayabilir. Bu, gozlemlerken dikkat etmemiz gereken bir
    trade-off.
    """
    parcalar = markdown_bol(content)
    parcalar = liste_maddelerine_gore_bol(parcalar)
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi, maks_token=1800)
    parcalar = bos_parcalari_temizle(parcalar)
    parcalar = _kucuk_artiklari_birlestir(parcalar, token_sayisi)
    return parcalar


def _cumlelere_ayir(metin: str) -> list[str]:
    """
    Hafif, regex-tabanli bir cumle ayirici - projede agir bir NLP
    kutuphanesi (nltk/spaCy/stanza) yok, deney icin bu yeterli.

    Once SATIRLARA boluyoruz (bir sinav takvimi maddesi gibi noktasiz
    biten satirlar da en azindan kendi "cumlesi" sayilsin diye), sonra
    her satiri KENDI ICINDE noktalama isaretinden (. ! ?) sonra gelen
    bosluktan bolerek gercek cumlelere ayiriyoruz. Kisaltmalar (orn.
    "vb.", "Dr.") icin mukemmel degil, ama deney amacli yeterli.
    """
    cumleler: list[str] = []
    for satir in metin.split("\n"):
        satir = satir.strip()
        if not satir:
            continue
        for parca in re.split(r"(?<=[.!?])\s+", satir):
            parca = parca.strip()
            if parca:
                cumleler.append(parca)
    return cumleler


def _anlamsal_sinirlari_bul(cumleler: list[str], esik_yuzdelik: float = 90) -> set[int]:
    """
    Ardisik cumleler arasindaki kozinus UZAKLIGINI (1 - benzerlik) hesaplar,
    bu uzakliklarin esik_yuzdelik'inci YUZDELIK DILIMINI (percentile) esik
    olarak alir - bu esigi ASAN noktalar "konu degisimi" (breakpoint)
    sayilir. LangChain'in semantic chunker'inin varsayilan "percentile"
    yontemiyle ayni fikir (makaledeki "gradient thresholding" degil,
    ama ayni aile - daha basit ve aciklanabilir bir esik secimi).

    NEDEN PERCENTILE: sabit bir uzaklik esigi (orn. "0.3'ten buyukse
    bol") her sayfada AYNI olcude anlamli olmayabilir - bazi sayfalar
    dogal olarak daha "sicak/soguk" gecisli olabilir. Percentile,
    esigi HER SAYFAYA GORE kendi ic dagilimina uyarliyor.

    Donen deger: hangi cumleden SONRA yeni chunk baslamasi gerektigini
    gosteren indeks kumesi. Cok az cumle varsa (percentile istatistiksel
    olarak anlamsizlasir) bos kume doner - hicbir yerde bolme yapilmaz.
    """
    if len(cumleler) < 3:
        return set()

    # prompt_name="STS": burada retrieval yapmiyoruz, iki cumlenin
    # ANLAMCA ne kadar benzer oldugunu (sentence similarity) olcuyoruz -
    # EmbeddingGemma'nin bunun icin onerdigi gorev bu.
    vektorler = _model.encode(cumleler, prompt_name="STS")

    uzakliklar = []
    for i in range(len(vektorler) - 1):
        # Model ciktisi birim vektor oldugu icin (bkz. embedding_servisi.
        # py'deki en_benzer_konuyu_bul yorumu), ic carpim = kozinus benzerligi.
        kozinus_benzerlik = float(np.dot(vektorler[i], vektorler[i + 1]))
        uzakliklar.append(1 - kozinus_benzerlik)

    esik = np.percentile(uzakliklar, esik_yuzdelik)
    return {i for i, uzaklik in enumerate(uzakliklar) if uzaklik > esik}


def _anlamsal_bol(content: str, cumle_ayirici_fonksiyon) -> list[MetinParcasi]:
    """
    yontem_semantik VE yontem_semantik_stanza'nin PAYLASTIGI ortak mantik.
    Ikisinin arasindaki TEK fark hangi cumle ayirici fonksiyonu
    kullandiklari (regex mi, Stanza mi) - bu yuzden asil algoritmayi
    (anlamsal sinir bulma + guvenlik aglari) burada TEK YERDE yaziyoruz,
    cumle ayiricisini disaridan parametre olarak aliyoruz. Boylece "iki
    yontem arasindaki fark SADECE cumle ayirici" garantisi kod
    seviyesinde de dogru kalir - yanlislikla birbirinden sapamazlar.

    markdown_bol ile basliklara boler (basliklar kullanicinin kendi
    belirttigi NET sinirlar - onlari atmiyoruz), ama HER basligin
    ICERIGINI bolmek icin liste_maddelerine_gore_bol'un yerine, cumleler
    arasi ANLAMSAL uzakliga bakarak "konu degisimi" olan yerlerden
    boluyor - Adaptive Chunking makalesindeki "semantic chunker"
    baseline'iyla ayni fikir (bkz. makale bolum 2.2).

    NEDEN HALA parcalari_boyuta_gore_bol VAR (guvenlik agi olarak):
    anlamsal sinirlar bazen COK uzun bir "tek konulu" blok birakabilir
    (orn. konu hic degismeyen 1500 token'lik bir PDF bolumu) - bu durumda
    hala embedding modelinin token sinirini asabilir. Diger yontemlerle
    ADIL karsilastirma icin de aynı guvenlik agi (maks_token=1800)
    kullaniliyor.

    NEDEN SONUNDA _kucuk_artiklari_birlestir DE VAR: gercek veriyle test
    ederken (Sayfa 37) bu yontemin 4-8 token'lik "yetim" parcalar
    urettigini gorduk - PDF'teki "<!-- Start of picture text -->" gibi
    kisa gurultu satirlari, cevresinde buyuk bir anlamsal sicrama
    oldugu icin kendi basina "ayri konu" sayilip izole kaliyordu.
    parcalari_boyuta_gore_bol SADECE COK BUYUK parcalari boluyor, kucuk
    olanlara dokunmuyor - bu yuzden ayrica kucuk-birlestirme adimi
    gerekiyor (bkz. yontem_genellestirilmis_merge'deki ayni fikir).

    NEDEN "\\n".join (bosluk DEGIL): cumleleri birlestirirken orijinal
    satir sonlarini KORUYORUZ - baslangicta " ".join kullanmistik, ama
    deney_metrikleri.py'deki ICC olcumunde bunun ciddi bir yan etkisi
    oldugunu gorduk: noktalama isareti tasimayan liste maddeleri (orn.
    yapilacaklar listesi) boslukla birlesince TEK bir "cumle" gibi
    algilaniyor, bu da ICC'yi yapay olarak 0'a dusurebiliyor. Satir
    sonlarini korumak, split_then_merge/overlap_recursive gibi metni
    hic yeniden birlestirmeyen yontemlerle de TUTARLI bir davranis.
    """
    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[MetinParcasi] = []
    for parca in basliklara_gore:
        cumleler = cumle_ayirici_fonksiyon(parca.icerik)

        if len(cumleler) <= 1:
            sonuc.append(parca)
            continue

        sinirlar = _anlamsal_sinirlari_bul(cumleler)

        biriken: list[str] = []
        for i, cumle in enumerate(cumleler):
            biriken.append(cumle)
            if i in sinirlar:
                sonuc.append(MetinParcasi(baslik=parca.baslik, icerik="\n".join(biriken), seviye=parca.seviye))
                biriken = []
        if biriken:
            sonuc.append(MetinParcasi(baslik=parca.baslik, icerik="\n".join(biriken), seviye=parca.seviye))

    sonuc = parcalari_boyuta_gore_bol(sonuc, token_sayisi, maks_token=1800)
    sonuc = _kucuk_artiklari_birlestir(sonuc, token_sayisi)
    return sonuc


def yontem_semantik(content: str) -> list[MetinParcasi]:
    """Anlamsal sinir bulma + regex cumle ayirici (_cumlelere_ayir). Bkz. _anlamsal_bol."""
    return _anlamsal_bol(content, _cumlelere_ayir)


# Stanza pipeline'ini modul seviyesinde BIR KERE kuruyoruz (tipki
# embedding_servisi.py'deki _model gibi) - her cagrida yeniden
# yuklemek gereksiz maliyet olurdu. Sadece "tokenize" (cumle/kelime
# bolme) processor'unu istiyoruz - POS/NER/depparse gibi bu deney
# icin gereksiz agir islemleri YUKLEMIYORUZ, hem indirme hem calisma
# suresi kisalsin diye.
_stanza_pipeline = stanza.Pipeline("tr", processors="tokenize", verbose=False)

# Makaledeki "sentence-based chunking" tanimiyla AYNI: sabit sayida
# cumleyi bir araya getirip bir chunk yapiyoruz (makalede 5 cumle
# kullanilmis, bkz. bolum 2.2 "Baseline methods").
CUMLE_BASINA_GRUP = 5


def _stanza_cumlelere_ayir(metin: str) -> list[str]:
    """
    yontem_semantik'teki _cumlelere_ayir'in (regex tahmini) aksine,
    burada GERCEK bir istatistiksel model (Stanza, Turkce IMST
    treebank'i uzerinde egitilmis) cumle sinirlarini buluyor - noktalama
    isaretinin HER ZAMAN cumle sonu olmadigini (orn. "1.5 kg", "Dr.")
    biliyor. Mukemmel degil (test ederken "Dr. Ahmet" gibi bazi
    kisaltmalari hala yanlis boldugunu gorduk) ama regex'ten daha
    guvenilir.
    """
    belge = _stanza_pipeline(metin)
    return [cumle.text for cumle in belge.sentences]


def yontem_cumle_bazli(content: str) -> list[MetinParcasi]:
    """
    Adaptive Chunking makalesindeki "sentence-based chunking" baseline'i
    (bkz. bolum 2.2): basliklara bol (markdown_bol), her basligin
    icerigini STANZA ile gercek cumlelere ayir, sonra sabit sayida
    (CUMLE_BASINA_GRUP=5) cumleyi bir araya getirerek chunk olustur.

    yontem_semantik'ten FARKI: o, cumleler arasi ANLAMSAL uzakliga
    bakip DEGISKEN boyutlu, "konu bazli" siniirlar buluyordu. Bu yontem
    ise KOR - anlam hic hesaba katilmiyor, sadece "her 5 cumlede bir
    bol" deniyor. Amac: anlamsal bolmenin GERCEKTEN bir fark yaratip
    yaratmadigini, bu "aptal ama ucuz" alternatife karsi olcmek.
    """
    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[MetinParcasi] = []
    for parca in basliklara_gore:
        cumleler = _stanza_cumlelere_ayir(parca.icerik)

        if len(cumleler) <= 1:
            sonuc.append(parca)
            continue

        for i in range(0, len(cumleler), CUMLE_BASINA_GRUP):
            grup = cumleler[i:i + CUMLE_BASINA_GRUP]
            sonuc.append(MetinParcasi(baslik=parca.baslik, icerik="\n".join(grup), seviye=parca.seviye))

    sonuc = parcalari_boyuta_gore_bol(sonuc, token_sayisi, maks_token=1800)
    return sonuc


def yontem_semantik_stanza(content: str) -> list[MetinParcasi]:
    """
    yontem_semantik ile TEK farki: cumle ayirici olarak regex tahmini
    (_cumlelere_ayir) yerine gercek Stanza modeli (_stanza_cumlelere_ayir)
    kullaniliyor - algoritmanin geri kalani (_anlamsal_bol) BIREBIR AYNI.

    AMAC: onceki gozlemde "semantik ile cumle_bazli arasindaki farkin
    bir kismi, aslinda hangi cumle ayiriciyi kullandigimizdan
    kaynaklanabilir" notunu dustuk - bu yontem o degiskeni sabitliyor.
    Simdi karsilastirma net: semantik vs semantik_stanza farki SADECE
    cumle ayiriciyi gosterir; semantik_stanza vs cumle_bazli farki ise
    SADECE "anlam-bazli mi, sayi-bazli mi bolme" sorusunu gosterir.
    """
    return _anlamsal_bol(content, _stanza_cumlelere_ayir)


# Makalenin Ek G'sindeki (Figure 4) AYNI ayirici oncelik listesi -
# basliklardan (1-6. seviye) numarali/madde isaretli listelere, bos
# satirlara, cumle sonuna, virgule, bosluga ve en son karaktere kadar.
# RecursiveCharacterTextSplitter bu listeyi SIRAYLA dener: ilk ayirici
# ile bolunen parca hala cok buyukse, bir SONRAKI (daha "kaba") ayiriciyi
# dener - boylece mumkun oldugunca "dogal" bir sinirdan bolmeye calisir.
MAKALE_AYIRICILARI = [
    r"(?<=\n)#{1}\s",
    r"(?<=\n)#{2}\s",
    r"(?<=\n)#{3}\s",
    r"(?<=\n)#{4}\s",
    r"(?<=\n)#{5}\s",
    r"(?<=\n)#{6}\s",
    r"(?<=\n)\s*\(?[A-Za-z0-9]{1,4}[.)]\s+",
    r"(?<=\n)\s*[-*·•●▪◦‣▸▹○◯‒–—]\s+",
    r"\n{2,}",
    r"\n",
    r"[.!?]\s+",
    r",\s+",
    r"\s+",
    "",
]

# Diger tum yontemlerle ADIL karsilastirma icin AYNI boyut sinirini
# (maks_token=1800) kullaniyoruz - makaledeki "s=1100" degil, cunku
# amac makaledeki mutlak sayilari kopyalamak degil, YONTEMLERI kendi
# projemizin verisiyle, ayni kosullar altinda kiyaslamak.
OVERLAP_RECURSIVE_CHUNK_SIZE = 1800

# Komsu chunklar arasinda kac token'lik ORTAK PAY birakilacagi - sinirin
# hemen yanindaki cumlenin/baglamin TAMAMEN kaybolmamasi icin. ~%8'lik
# bir pay (1800'un ~8'i) - yaygin kullanilan bir oran, kesin bir bilim
# degil.
OVERLAP_RECURSIVE_CHUNK_OVERLAP = 150


def yontem_overlap_recursive(content: str) -> list[MetinParcasi]:
    """
    Adaptive Chunking makalesindeki LangChain RecursiveCharacterTextSplitter
    baseline'i (bkz. bolum 2.2, Ek G) - makale bu yontemi KENDI YAZMAMIS,
    dogrudan LangChain kutuphanesini kullanmis, biz de ayni sekilde
    kutuphaneyi kullaniyoruz (yeniden yazip farkli davranma riski almak
    yerine).

    DIGER TUM YONTEMLERDEN EN BUYUK FARKI: bu, projedeki TEK yontem
    - chunk'lar arasinda OVERLAP (ortak pay) biraktiran. Digerlerinin
    hepsinde (mevcut_yontem dahil) chunk'lar TAMAMEN AYRIK - bir sinirin
    hemen yanindaki cumle sadece BIR chunk'a giriyor. Burada ise her
    chunk, bir onceki chunk'in son ~150 token'ini de icinde tasiyor -
    boylece "sinirin tam ortasindan gecen" bir bilginin HER IKI
    chunk'ta da (kismen) bulunma sansi var.

    NEDEN markdown_bol ile ONCE BASLIKLARA BOLUYORUZ (digerleriyle ayni
    desen): baslikari kaybetmek istemedik ki "hangi baslik altinda"
    metadata'si (parca.baslik) diger yontemlerle karsilastirilabilir
    kalsin. Splitter'in kendisi zaten MAKALE_AYIRICILARI listesinde
    baslik ayiricilarini da iceriyor - yani ayni sinirlari IKI KERE
    bulmus oluyoruz ama zararsiz (markdown_bol zaten hallettigi icin
    splitter icin bunlar nadiren tetiklenir).

    NEDEN ekstra bir guvenlik agi (parcalari_boyuta_gore_bol,
    _kucuk_artiklari_birlestir) YOK: RecursiveCharacterTextSplitter'in
    kendi ICINDE zaten hem boyut siniri (chunk_size) hem kucuk parcalari
    komsusuyla birlestirme mantigi var - digerlerinin aksine bu yonteme
    ekstra bir sey eklemeye gerek yok, kutuphanenin kendi davranisini
    SAF haliyle gozlemlemek istiyoruz.
    """
    splitter = RecursiveCharacterTextSplitter(
        separators=MAKALE_AYIRICILARI,
        is_separator_regex=True,
        chunk_size=OVERLAP_RECURSIVE_CHUNK_SIZE,
        chunk_overlap=OVERLAP_RECURSIVE_CHUNK_OVERLAP,
        length_function=token_sayisi,
    )

    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[MetinParcasi] = []
    for parca in basliklara_gore:
        for alt_metin in splitter.split_text(parca.icerik):
            sonuc.append(MetinParcasi(baslik=parca.baslik, icerik=alt_metin, seviye=parca.seviye))

    return sonuc


def _recursif_kucult(metin: str, ayiricilar: list[str], hedef_boyut: int) -> list[str]:
    """
    Split-then-merge yontemin 1. GECISI (PASS): metni, MAKALE_AYIRICILARI
    listesindeki oncelik sirasina gore recursive olarak kucultur - her
    parca hedef_boyut'un ALTINA dusene kadar bir SONRAKI (daha ince)
    ayiriciyi dener. Bu asamada MERGE (birlestirme) YOK - sadece "kucult,
    kucult, hedefe kadar kucult" (bkz. makale bolum 2.2, "In the first
    pass, the text is recursively split... until each segment is <= S").

    yontem_overlap_recursive'ten (RecursiveCharacterTextSplitter) FARKI:
    o kutuphane split+merge'u TEK bir ic mantikta birlikte yapiyordu - biz
    burada bilerek IKI ayri, GORULEBILIR asamaya bolduk (bu fonksiyon +
    _acgozlu_birlestir), tam olarak makalenin anlattigi gibi.
    """
    if not metin.strip():
        return []
    if token_sayisi(metin) <= hedef_boyut:
        return [metin]
    if not ayiricilar:
        # Ayirici listesi tukendi (en son "" karakter-bazli ayirici bile
        # denendi) - normalde buraya hic gelinmemesi beklenir, ama
        # olursa metni oldugu gibi don, sonsuz donguye girme.
        return [metin]

    ayirici, kalan_ayiricilar = ayiricilar[0], ayiricilar[1:]

    if ayirici == "":
        # Son care: tek tek karaktere bol.
        alt_parcalar = list(metin)
    else:
        alt_parcalar = [p for p in re.split(ayirici, metin) if p.strip()]

    if len(alt_parcalar) <= 1:
        # Bu ayirici metinde hic gecmiyor (boldugu bir sey yok) - bir
        # sonraki (daha ince) ayiriciyi dene.
        return _recursif_kucult(metin, kalan_ayiricilar, hedef_boyut)

    sonuc: list[str] = []
    for alt_parca in alt_parcalar:
        sonuc.extend(_recursif_kucult(alt_parca, kalan_ayiricilar, hedef_boyut))
    return sonuc


def _son_n_token_metni(metin: str, n: int) -> str:
    """
    Verilen metnin SON n token'ina denk gelen metni dondurur -
    backtracking ile overlap eklerken kullanilir. Karakter/kelime
    bazli bir tahmin degil, GERCEK tokenizer ile encode edip son n
    token id'sini tekrar decode ediyoruz - boylece "son n token" tam
    olarak dogru.
    """
    if n <= 0:
        return ""
    token_idleri = _model.tokenizer.encode(metin)
    son_idler = token_idleri[-n:]
    return _model.tokenizer.decode(son_idler)


def _acgozlu_birlestir(parcalar: list[str], hedef_boyut: int, overlap: int) -> list[str]:
    """
    Split-then-merge yontemin 2. GECISI (PASS): _recursif_kucult'un
    urettigi (hepsi hedef_boyut'un ALTINDA olan) kucuk parcalari, ardisik
    sirayla, hedef_boyut'u ASMAYACAK sekilde ACGOZLU (greedy) bicimde
    birlestirir. Bir sonraki parca eklenince siniri asacaksa, mevcut
    chunk'i kapatir - ama yeni chunk'i SIFIRDAN degil, kapanan chunk'in
    SON `overlap` token'iyla ("backtracking") baslatir, boylece sinirin
    hemen yanindaki baglam HER IKI chunk'ta da (kismen) bulunur (bkz.
    makale: "backtracking when necessary to maintain overlap").

    NEDEN GUVENLIK AGI YOK BURADA: girdi zaten _recursif_kucult'tan
    gectigi icin HER TEK parca hedef_boyut'un altinda - birlestirme
    ADIMI kontrollu oldugu icin (hicbir zaman siniri asacak bir ekleme
    yapilmiyor) sonuc da hep hedef_boyut'un altinda kalir. Yine de
    cagiran fonksiyon (yontem_split_then_merge) son bir kontrol icin
    parcalari_boyuta_gore_bol'u guvenlik agi olarak calistiriyor -
    "re-splitting oversized parts" (makale) ihtimaline karsi.
    """
    if not parcalar:
        return []

    sonuc: list[str] = []
    mevcut = parcalar[0]

    for sonraki in parcalar[1:]:
        aday = mevcut + "\n\n" + sonraki
        if token_sayisi(aday) <= hedef_boyut:
            mevcut = aday
        else:
            sonuc.append(mevcut)
            kuyruk = _son_n_token_metni(mevcut, overlap)
            mevcut = (kuyruk + "\n\n" + sonraki) if kuyruk else sonraki

    sonuc.append(mevcut)
    return sonuc


# Makalenin kendi split-then-merge splitter'inda test ettigi IKI hedef
# boyut (bkz. Tablo 2/3: "ourrecursive(s=1100)" ve "ourrecursive(s=600)") -
# 1100 makalede EN YUKSEK ortalama skoru alan varyanttı. Biz de projemizin
# verisiyle ikisini de deniyoruz.
SPLIT_MERGE_HEDEF_1100 = 1100
SPLIT_MERGE_HEDEF_600 = 600
SPLIT_MERGE_OVERLAP = 100


def _split_then_merge_bol(content: str, hedef_boyut: int) -> list[MetinParcasi]:
    """
    yontem_split_then_merge_1100 ve _600'un PAYLASTIGI ortak mantik -
    tek fark hedef_boyut. markdown_bol ile basliklara boler (digerleriyle
    ayni desen), her basligin icerigini once _recursif_kucult (PASS 1),
    sonra _acgozlu_birlestir (PASS 2) ile isler, sonunda guvenlik agi
    olarak parcalari_boyuta_gore_bol + _kucuk_artiklari_birlestir
    calistirir (makaledeki "final regularization" post-processing
    adimlariyla ayni fikir - bkz. mevcut_yontem/yontem_genellestirilmis_
    merge'deki ayni araclar).
    """
    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[MetinParcasi] = []
    for parca in basliklara_gore:
        kucultulmus = _recursif_kucult(parca.icerik, MAKALE_AYIRICILARI, hedef_boyut)
        birlestirilmis = _acgozlu_birlestir(kucultulmus, hedef_boyut, SPLIT_MERGE_OVERLAP)
        for alt_metin in birlestirilmis:
            sonuc.append(MetinParcasi(baslik=parca.baslik, icerik=alt_metin, seviye=parca.seviye))

    sonuc = parcalari_boyuta_gore_bol(sonuc, token_sayisi, maks_token=hedef_boyut)
    sonuc = _kucuk_artiklari_birlestir(sonuc, token_sayisi)
    return sonuc


def yontem_split_then_merge_1100(content: str) -> list[MetinParcasi]:
    """Split-then-merge recursive splitter, hedef boyut=1100 token (makaledeki en iyi varyant). Bkz. _split_then_merge_bol."""
    return _split_then_merge_bol(content, SPLIT_MERGE_HEDEF_1100)


def yontem_split_then_merge_600(content: str) -> list[MetinParcasi]:
    """Split-then-merge recursive splitter, hedef boyut=600 token. Bkz. _split_then_merge_bol."""
    return _split_then_merge_bol(content, SPLIT_MERGE_HEDEF_600)
