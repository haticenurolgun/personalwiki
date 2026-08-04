"""
chunking_secici.py

Sayfa icerigine (kaynagi PDF ya da elle yazilmis markdown fark etmez)
bakip, HANGI chunking yontemunun en uygun oldugunu SECEN ve calistiran
katman. /sources/markdown, /sources/pdf ve /pages/{id}/index
endpoint'lerinin ucu BURAYA cikiyor - hepsi ayni secim mantigini
kullanir.

ARKA PLAN: Bu secim kurallari, "Adaptive Chunking: Optimizing
Chunking-Method Selection for RAG" (Ekimetrics) makalesindeki
yontemleri projenin kendi test sayfalari uzerinde ICC/DCC/BI/SC
metrikleriyle karsilastiran bir deneyden cikti (bkz.
chunking-yontem-deneyi branch'i) - deneydeki 4 kural, sayfa turune
gore hangi yontemin en iyi skoru aldigini GOZLEMLEYEREK belirlendi:

- Tek bolumu COK UZUN (zayif basliklandirilmis, orn. cogu PDF)
  sayfalarda overlap_recursive acik ara en iyi sonucu veriyordu.
- Satirlarinin BUYUK COGUNLUGU liste maddesi olan sayfalarda
  genellestirilmis_merge, mevcut yontemden belirgin daha iyiydi -
  mevcut'un urettigi asiri kucuk, boyut siniri basaramayan parcalar
  sorunluydu.
- Kismen liste ICEREN ama COGUNLUGU duz metin olan "karisik"
  sayfalarda semantik en iyi sonucu veriyordu.
- Duz, temiz basliklandirilmis notlarda hicbir yontem digerinden
  anlamli farkli degildi - bu durumda en basit/ucuz secenek (mevcut)
  yeterli.

NOT: Bu, makaledeki "Adaptive Chunking"in KENDI yaklasimi (birden
fazla aday yontemi GERCEKTEN calistirip metriklerini olcerek en
iyisini secme) DEGIL - o, indexleme anini yavaslatacak kadar coklu
embedding cagrisi gerektiriyor. Bu secici, o deneyin SONUCLARINI
kural haline getirilmis, UCUZ (yapisal sinyallerle, ekstra embedding
cagrisi olmadan calisan) bir yaklasim.
"""

import re

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.structural_parser import (
    Parca,
    markdown_bol,
    liste_maddelerine_gore_bol,
    parcalari_boyuta_gore_bol,
    bos_parcalari_temizle,
    _kucuk_parcalari_birlestir,
    _madde_mi,
)
from app.embeddings.embedding_servisi import token_sayisi, cumle_benzerlik_vektorleri

# Diger tum yontemlerle ayni guvenlik sinirini kullaniyoruz -
# EmbeddingGemma-300M'in gercek sinirindan (2048 token) pay birakiyor.
MAKS_TOKEN = 1800


def _mevcut_yontem(content: str) -> list[Parca]:
    """
    Projenin ilk gunden beri kullandigi pipeline - en ucuz secenek.
    Duz, temiz basliklandirilmis sayfalarda ek bir isleme gerek
    olmadigini deney gosterdi, bu yuzden bu tur sayfalar icin secici
    hala bunu kullaniyor.
    """
    parcalar = markdown_bol(content)
    parcalar = liste_maddelerine_gore_bol(parcalar)
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi, maks_token=MAKS_TOKEN)
    parcalar = bos_parcalari_temizle(parcalar)
    return parcalar


def _genellestirilmis_merge_yontemi(content: str) -> list[Parca]:
    """
    _mevcut_yontem + sayfanin TUM nihai parca listesine (farkli
    basliklardan/liste maddelerinden gelenler dahil) uygulanan bir
    kucuk-parca birlestirme adimi. Liste agirlikli sayfalarda
    _mevcut_yontem'in urettigi asiri kucuk parcalari (orn. tek
    satirlik bir gorev maddesi) komsusuyla birlestirir.
    """
    parcalar = markdown_bol(content)
    parcalar = liste_maddelerine_gore_bol(parcalar)
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi, maks_token=MAKS_TOKEN)
    parcalar = bos_parcalari_temizle(parcalar)
    parcalar = _kucuk_parcalari_birlestir(parcalar, token_sayisi)
    return parcalar


def _cumlelere_ayir(metin: str) -> list[str]:
    """
    Hafif, regex-tabanli bir cumle ayirici. Once SATIRLARA boluyoruz
    (noktasiz biten liste maddeleri de en azindan kendi "cumlesi"
    sayilsin diye), sonra her satiri KENDI ICINDE noktalama
    isaretinden (. ! ?) sonra gelen bosluktan bolerek gercek
    cumlelere ayiriyoruz.
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


# Ardisik cumleler arasindaki kozinus uzakliginin bu YUZDELIK DILIMI
# (percentile), "konu degisimi" (breakpoint) sayilacagi esik - sayfaya
# ozgu, her sayfanin kendi ic dagilimina gore uyarlaniyor.
_ANLAMSAL_ESIK_YUZDELIK = 90


def _anlamsal_sinirlari_bul(cumleler: list[str]) -> set[int]:
    """
    Ardisik cumleler arasindaki kozinus UZAKLIGINI (1 - benzerlik)
    hesaplar, _ANLAMSAL_ESIK_YUZDELIK'inci yuzdelik dilimi esik olarak
    alir - bu esigi ASAN noktalar "konu degisimi" sayilir. Cok az
    cumle varsa (percentile istatistiksel olarak anlamsizlasir) bos
    kume doner - hicbir yerde bolme yapilmaz.
    """
    if len(cumleler) < 3:
        return set()

    vektorler = cumle_benzerlik_vektorleri(cumleler)

    uzakliklar = []
    for i in range(len(vektorler) - 1):
        kozinus_benzerlik = float(np.dot(vektorler[i], vektorler[i + 1]))
        uzakliklar.append(1 - kozinus_benzerlik)

    esik = np.percentile(uzakliklar, _ANLAMSAL_ESIK_YUZDELIK)
    return {i for i, uzaklik in enumerate(uzakliklar) if uzaklik > esik}


def _semantik_yontem(content: str) -> list[Parca]:
    """
    Basliklara boler (basliklar kullanicinin kendi belirttigi NET
    sinirlar), ama HER basligin ICERIGINI bolmek icin liste_
    maddelerine_gore_bol yerine, cumleler arasi ANLAMSAL uzakliga
    bakarak "konu degisimi" olan yerlerden boler. Hem duz metin hem
    liste iceren "karisik" sayfalarda en iyi sonucu veriyor.
    """
    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[Parca] = []
    for parca in basliklara_gore:
        cumleler = _cumlelere_ayir(parca.icerik)

        if len(cumleler) <= 1:
            sonuc.append(parca)
            continue

        sinirlar = _anlamsal_sinirlari_bul(cumleler)

        biriken: list[str] = []
        for i, cumle in enumerate(cumleler):
            biriken.append(cumle)
            if i in sinirlar:
                sonuc.append(Parca(baslik=parca.baslik, icerik="\n".join(biriken), seviye=parca.seviye))
                biriken = []
        if biriken:
            sonuc.append(Parca(baslik=parca.baslik, icerik="\n".join(biriken), seviye=parca.seviye))

    sonuc = parcalari_boyuta_gore_bol(sonuc, token_sayisi, maks_token=MAKS_TOKEN)
    sonuc = _kucuk_parcalari_birlestir(sonuc, token_sayisi)
    return sonuc


# "Adaptive Chunking" makalesinin Ek G'sindeki (Figure 4) AYNI ayirici
# oncelik listesi - basliklardan (1-6. seviye) numarali/madde isaretli
# listelere, bos satirlara, cumle sonuna, virgule, bosluga ve en son
# karaktere kadar.
_OVERLAP_RECURSIVE_AYIRICILARI = [
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

# Komsu chunklar arasinda kac token'lik ortak pay birakilacagi -
# sinirin hemen yanindaki baglamin tamamen kaybolmamasi icin.
_OVERLAP_RECURSIVE_CHUNK_OVERLAP = 150


def _overlap_recursive_yontem(content: str) -> list[Parca]:
    """
    LangChain'in RecursiveCharacterTextSplitter'i - ayirici oncelik
    listesiyle (basliktan karaktere) boler, chunk'lar arasinda overlap
    birakir. Zayif basliklandirilmis (orn. cogu PDF) sayfalarda en iyi
    sonucu veriyor - boyle sayfalarda markdown_bol tek bir dev bolum
    uretiyor, bu yontem onu overlap'li, dengeli parcalara bolebiliyor.
    """
    splitter = RecursiveCharacterTextSplitter(
        separators=_OVERLAP_RECURSIVE_AYIRICILARI,
        is_separator_regex=True,
        chunk_size=MAKS_TOKEN,
        chunk_overlap=_OVERLAP_RECURSIVE_CHUNK_OVERLAP,
        length_function=token_sayisi,
    )

    basliklara_gore = markdown_bol(content)
    basliklara_gore = bos_parcalari_temizle(basliklara_gore)

    sonuc: list[Parca] = []
    for parca in basliklara_gore:
        for alt_metin in splitter.split_text(parca.icerik):
            sonuc.append(Parca(baslik=parca.baslik, icerik=alt_metin, seviye=parca.seviye))

    return sonuc


_YONTEMLER = {
    "mevcut": _mevcut_yontem,
    "genellestirilmis_merge": _genellestirilmis_merge_yontemi,
    "semantik": _semantik_yontem,
    "overlap_recursive": _overlap_recursive_yontem,
}

# En uzun bolumun bu token sayisini asmasi, sayfanin "yapisiz/PDF-tipi"
# oldugunun isareti - temiz notlarda en uzun bolum bile nadiren birkac
# yuz token'i geciyor, zayif basliklandirilmis PDF'lerde ise tek bolum
# binlerce token'a varabiliyor.
_BUYUK_BOLUM_ESIGI = 500

# Satirlarin bu orandan FAZLASI liste maddesiyse "liste agirlikli"
# sayilir.
_LISTE_AGIRLIKLI_ESIGI = 0.4

_TUR_TO_YONTEM = {
    "pdf_yapisiz": "overlap_recursive",
    "liste_agirlikli": "genellestirilmis_merge",
    "karisik": "semantik",
    "duz_metin": "mevcut",
}


def _sayfa_turunu_belirle(content: str) -> str:
    """
    Sayfa icerigine SADECE ucuz, embedding-siz sinyallere bakarak bir
    "tur" etiketi verir. Kontrol sirasi ONEMLI: once en "belirgin"
    sinyal (asiri uzun tek bolum) kontrol ediliyor - bir PDF sayfasinda
    tesadufen birkac liste satiri da olabilir, o durumda bile asil
    sorun yapisizlik, liste orani degil.
    """
    bolumler = bos_parcalari_temizle(markdown_bol(content))
    en_uzun_bolum = max((token_sayisi(b.icerik) for b in bolumler), default=0)

    satirlar = [s for s in content.split("\n") if s.strip()]
    madde_satirlari = [s for s in satirlar if _madde_mi(s)]
    liste_orani = len(madde_satirlari) / len(satirlar) if satirlar else 0.0

    if en_uzun_bolum > _BUYUK_BOLUM_ESIGI:
        return "pdf_yapisiz"
    if liste_orani >= _LISTE_AGIRLIKLI_ESIGI:
        return "liste_agirlikli"
    if liste_orani > 0:
        return "karisik"
    return "duz_metin"


def yontem_sec(content: str) -> tuple[str, list[Parca]]:
    """
    Sayfa icerigine bakip en uygun chunking yontemini SECER, calistirir
    ve (secilen yontemin ismi, sonuc parcalari) dondurur.

    yontem_adi'nin de dondurulmesi bilincli: cagiran taraf (router)
    isterse loglayabilir - "bu sayfa neden bu sekilde parcalandi"
    sorusu ileride hata ayiklarken islevsel olur.
    """
    tur = _sayfa_turunu_belirle(content)
    yontem_adi = _TUR_TO_YONTEM[tur]
    yontem_fonksiyonu = _YONTEMLER[yontem_adi]
    return yontem_adi, yontem_fonksiyonu(content)
