"""
deney_metrikleri.py

Adaptive Chunking makalesindeki 4 icsel kalite metrigini (ICC, DCC, BI,
SC) projemizin verisiyle hesaplayan SAF fonksiyonlar - veritabanina/
Chroma'ya DOKUNMAZ, sadece Parca listeleri alip sayisal skor
dondurur.

NOT: Makaledeki 5. metrik olan References Completeness (RC) BILINCLI
OLARAK ATLANDI - Ingilizce'ye ozel bir coreference cozumleme modeli
(Maverick) gerektiriyor, Turkce icerigimiz icin uygulanamaz (makalenin
kendisi de "Language and Domain Coverage" sinirlamasinda ayni sorunu
belirtiyor - bkz. bolum 6 "Limitations").
"""

import numpy as np

from app.embeddings.embedding_servisi import token_sayisi, _model
from app.services.structural_parser import Parca, _madde_mi

from test_chunking_yont import _cumlelere_ayir


def hesapla_icc(parcalar: list[Parca]) -> float:
    """
    Intrachunk Cohesion (bkz. makale 2.3.3): her parcanin KENDI
    cumleleri ile TAM PARCA embedding'i arasindaki ortalama kozinus
    benzerligi - parca TEK BIR konuda mi kaliyor, yoksa birbiriyle
    alakasiz cumleleri mi bir araya getiriyor?

    2'den AZ cumlesi olan parcalar HESABA KATILMAZ (cohesion anlamli
    hesaplanamaz - makaledeki "n_k >= 2" sarti). Negatif skorlar 0'a
    kirpilir (makaledeki "max{0, Cohesion(c_k)}").

    NEDEN STANZA DEGIL, _cumlelere_ayir (regex) KULLANILIYOR: ilk
    denemede Stanza kullanmistik, ama bunun ciddi bir yan etkisi
    oldugunu gorduk - Stanza, tek `\\n` ile ayrilmis (orn. noktalama
    tasimayan bir yapilacaklar listesi) satirlari TEK bir "cumle"
    sayabiliyor, bu da ICC'yi yontemin gercek davranisindan bagimsiz,
    SADECE metnin nasil birlestirildigine bagli olarak yapay bicimde
    0'a dusurebiliyordu (bkz. Sayfa 27 gozlemi). _cumlelere_ayir,
    HER satiri once kendi basina bir aday cumle saydigi icin (sonra
    icindeki noktalamaya gore ayrica bolen) bu duruma karsi cok daha
    dayanikli - ayrica Stanza'nin parca-basina cagrilma maliyetini de
    ortadan kaldirip performans sorununu (bazi buyuk sayfalarda
    timeout) da cozuyor.
    """
    skorlar = []
    for parca in parcalar:
        cumleler = _cumlelere_ayir(parca.icerik)
        if len(cumleler) < 2:
            continue

        cumle_vektorleri = _model.encode(cumleler, prompt_name="STS")
        parca_vektoru = _model.encode(parca.icerik, prompt_name="STS")

        benzerlikler = [float(np.dot(v, parca_vektoru)) for v in cumle_vektorleri]
        skorlar.append(max(0.0, float(np.mean(benzerlikler))))

    return float(np.mean(skorlar)) if skorlar else 0.0


# Makaledeki AYNI deger (3000 token) - kisa sayfalarimizda pencere zaten
# "tum sayfa" ile ayni sonuca dusuyor, PDF gibi uzun sayfalarda gercek
# bir kayan pencere etkisi gosteriyor.
DCC_PENCERE_TOKEN_BUDGET = 3000


def hesapla_dcc(parcalar: list[Parca]) -> float:
    """
    Document Contextual Coherence (bkz. makale 2.3.4): her chunk, KENDI
    CEVRESINDEKI genis baglam penceresiyle ne kadar tutarli?

    Ardisik chunk'lardan, toplam token'i DCC_PENCERE_TOKEN_BUDGET'i
    asmayacak (en az 2 chunk iceren) kayan pencereler kurulur - pencere
    baslangici 1 chunk kaydirilarak ilerler. Her pencere icin, pencerenin
    TAM metninin embedding'i ile PENCEREDEKI HER CHUNK'IN embedding'i
    arasindaki ortalama benzerlik o pencerenin "coherence"i - DCC, tum
    pencerelerin coherence ortalamasi (negatifse 0'a kirpilir).

    NOT: makale, pencere metnini onceki pencereyle CAKISMAYAN
    kuyruklardan kurup hesap tasarrufu yapiyor - biz basitlik icin
    pencereyi DOGRUDAN o penceredeki chunk'larin TAM metinlerinin
    birlesimi olarak kuruyoruz; ortaya cikan METIN ayni, sadece insa
    yontemi daha basit (bizim olcegimizde performans farki onemsiz).
    """
    if len(parcalar) < 2:
        return 0.0

    token_sayilari = [token_sayisi(p.icerik) for p in parcalar]
    chunk_vektorleri = _model.encode([p.icerik for p in parcalar], prompt_name="STS")

    pencere_skorlari = []
    for baslangic in range(len(parcalar)):
        toplam = 0
        bitis = baslangic
        while bitis < len(parcalar):
            aday_toplam = toplam + token_sayilari[bitis]
            if bitis > baslangic and aday_toplam > DCC_PENCERE_TOKEN_BUDGET:
                break
            toplam = aday_toplam
            bitis += 1

        if bitis - baslangic < 2:
            continue  # makaledeki sart: pencere en az 2 chunk icermeli

        pencere_metni = "\n\n".join(p.icerik for p in parcalar[baslangic:bitis])
        pencere_vektoru = _model.encode(pencere_metni, prompt_name="STS")

        benzerlikler = [
            float(np.dot(pencere_vektoru, chunk_vektorleri[i]))
            for i in range(baslangic, bitis)
        ]
        pencere_skorlari.append(float(np.mean(benzerlikler)))

    if not pencere_skorlari:
        return 0.0
    return max(0.0, float(np.mean(pencere_skorlari)))


def _madde_metnini_temizle(satir: str) -> str:
    """
    structural_parser.py'deki liste_maddelerine_gore_bol icinde YAPILAN
    AYNI temizleme mantigi - "- ", "* " ya da "1. " gibi madde
    isaretlerini kaldirir. Gercek chunking yontemleri (mevcut_yontem,
    yontem_genellestirilmis_merge) bu temizlemeyi UYGULUYOR - altin
    bloklarin da AYNI temizlenmis haliyle olusturulmasi gerekiyor,
    yoksa "- [ ] X" (altin blok) ile "[ ] X" (gercek chunk) ASLA
    eslesmez ve BI yapay olarak dusuk cikar (bkz. Sayfa 27 gozlemi -
    ICC=0, BI=0, SC=0 ucu de aslinda "olculemedi", "kotu" degil).
    """
    temiz = satir.strip().lstrip("-*").strip()
    if temiz and temiz[0].isdigit():
        nokta_index = temiz.find(". ")
        if nokta_index > 0 and temiz[:nokta_index].isdigit():
            temiz = temiz[nokta_index + 2:].strip()
    return temiz


def _altin_bloklari_cikar(sayfa_icerigi: str) -> list[str]:
    """
    Sayfanin HAM icerigindeki "altin" (ground truth) yapisal bloklari
    cikarir - PARAGRAFLAR (bos satirla ayrilmis) ve LISTE MADDELERI (bir
    "paragraf" tamamen madde isaretli satirlardan olusuyorsa, her satir
    kendi basina, madde isareti TEMIZLENMIS haliyle bir blok sayilir -
    bkz. _madde_metnini_temizle). Baslik satirlari ("#" ile baslayan)
    ATLANIR - onlar yapisal isaretci, korunmasi gereken "icerik" degil.

    Bu bloklar HANGI chunking yontemi kullanilirsa kullanilsin AYNI
    kalan, bagimsiz bir referans - Block Integrity (BI), bu bloklarin
    bir chunking sonucunda ORTASINDAN BOLUNUP BOLUNMEDIGINI olcer (bkz.
    makale 2.3.2).
    """
    bloklar = []
    for paragraf in sayfa_icerigi.split("\n\n"):
        satirlar = [s for s in paragraf.split("\n") if s.strip()]
        satirlar = [s for s in satirlar if not s.strip().startswith("#")]
        if not satirlar:
            continue

        madde_satirlari = [s for s in satirlar if _madde_mi(s)]
        if len(satirlar) >= 2 and len(madde_satirlari) == len(satirlar):
            bloklar.extend(_madde_metnini_temizle(s) for s in madde_satirlari)
        else:
            bloklar.append("\n".join(satirlar))

    return [b.strip() for b in bloklar if b.strip()]


def _normalize_bosluk(metin: str) -> str:
    return " ".join(metin.split())


def hesapla_bi(sayfa_icerigi: str, parcalar: list[Parca]) -> float:
    """
    Block Integrity (bkz. makale 2.3.2): altin bloklarin KACI, TEK BIR
    chunk'in icinde BUTUN halde kaliyor?

    Makale karakter-ofset bazli calisiyor (parser'in blok sinirlarini
    bilerek); biz bircok yontemde metnin cumle/kelime birlesimiyle
    YENIDEN kuruldugu icin (orijinal karakterle BIREBIR eslesmeyebilir,
    orn. " ".join ile birlesen cumleler arasinda orijinal satir
    sonlari kaybolur) BOSLUK-NORMALLESTIRILMIS ICERME kontrolu
    kullaniyoruz: bir altin blok, normallesmis hali herhangi bir
    chunk'in normallesmis icinde GECIYORSA "saglam" sayilir.
    """
    altin_bloklar = _altin_bloklari_cikar(sayfa_icerigi)
    if not altin_bloklar:
        return 1.0

    normal_parcalar = [_normalize_bosluk(p.icerik) for p in parcalar]

    saglam_sayisi = 0
    for blok in altin_bloklar:
        normal_blok = _normalize_bosluk(blok)
        if any(normal_blok in np for np in normal_parcalar):
            saglam_sayisi += 1

    return saglam_sayisi / len(altin_bloklar)


# Butun yontemleri AYNI (projeye ozgu) sinirlarla olcuyoruz - her
# yontemin KENDI hedef boyutuyla degil, ki karsilastirma adil olsun
# (makale de ayni prensibi uyguluyor: tum satirlari sabit m=100/M=1100
# ile olcuyor). SC_MIN_TOKEN, structural_parser.py'deki MIN_PARCA_TOKEN
# ile ayni; SC_MAX_TOKEN, deneyde coklukla kullandigimiz ortak guvenlik
# sinirinin (maks_token=1800) aynisi.
SC_MIN_TOKEN = 20
SC_MAX_TOKEN = 1800


def hesapla_sc(parcalar: list[Parca], min_token: int = SC_MIN_TOKEN, max_token: int = SC_MAX_TOKEN) -> float:
    """Size Compliance (bkz. makale 2.3.5): parcalarin kacta kaci [min_token, max_token] araliginda?"""
    if not parcalar:
        return 0.0
    uygun = sum(1 for p in parcalar if min_token <= token_sayisi(p.icerik) <= max_token)
    return uygun / len(parcalar)
