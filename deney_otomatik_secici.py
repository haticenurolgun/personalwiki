"""
deney_otomatik_secici.py

Sayfa icerigine bakip HANGI chunking yontemi kullanilmasi gerektigine
UCUZ (embedding cagrisi OLMADAN) yapisal sinyallerle karar veren
kural-bazli secici. deney_metrik_karsilastirma.py'nin 8 test sayfasi
uzerindeki ICC/DCC/BI/SC sonuclarindan gozlemlenen kaliplara dayanir:

- Tek bolumu COK UZUN (zayif basliklandirilmis, orn. PDF) sayfalarda
  overlap_recursive acik ara en iyi sonucu veriyordu.
- Satirlarinin BUYUK COGUNLUGU liste maddesi olan sayfalarda
  genellestirilmis_merge, mevcut'tan belirgin daha iyiydi - mevcut'un
  urettigi minik, SC'yi basaramayan parcalar sorunluydu (bkz. Sayfa 27:
  mevcut ort=0.441, genellestirilmis_merge ort=0.681).
- Kismen liste ICEREN ama COGUNLUGU duz metin olan "karisik" sayfalarda
  semantik en iyi sonucu veriyordu (bkz. Sayfa 33: semantik ort=0.855,
  digerleri 0.76-0.84).
- Duz, temiz basliklandirilmis notlarda HICBIR yontem digerinden
  anlamli farkli degildi - bu durumda en basit/ucuz secenek (mevcut)
  yeterli.

NOT: Bu, makaledeki "Adaptive Chunking"in KENDI yaklasimi (metrikleri
GERCEKTEN hesaplayip en iyisini secme) DEGIL - o, coklu aday yontemi
calistirip birden fazla embedding cagrisi gerektirdigi icin pahali.
Bu secici, o deneyin SONUCLARINI kurala donusturmus, UCUZ bir
yaklasim - garantili degil (8 sayfalik gozleme dayanir), ama
indexleme anini embedding-agirlikli bir metrik hesabiyla yavaslatmiyor.

Calistirmak icin (venv aktifken, proje kok dizininde):
    python deney_otomatik_secici.py
"""

from app.services.structural_parser import (
    MetinParcasi,
    markdown_bol,
    bos_parcalari_temizle,
    _madde_satiri_mi,
)
from app.embeddings.embedding_servisi import token_sayisi

from test_chunking_yont import (
    mevcut_yontem,
    yontem_genellestirilmis_merge,
    yontem_semantik,
    yontem_overlap_recursive,
)

# En uzun bolumun bu token sayisini asmasi, sayfanin "yapisiz/PDF-tipi"
# oldugunun isareti - test sayfalarimizda temiz notlarin en uzun bolumu
# bile 83 token'i gecmiyordu, PDF'ler ise 2247-4131 token'a variyordu -
# aralarinda COK buyuk bir bosluk var, esik o boslugun ortasinda.
BUYUK_BOLUM_ESIGI = 500

# Satirlarin bu orandan FAZLASI liste maddesiyse "liste agirlikli"
# sayilir - test sayfalarimizda liste-agirlikli sayfalar 0.50/0.83,
# "karisik" sayilan sayfa 0.33 idi - esik ikisinin ortasinda.
LISTE_AGIRLIKLI_ESIGI = 0.4

YONTEMLER_BY_ISIM = {
    "mevcut": mevcut_yontem,
    "genellestirilmis_merge": yontem_genellestirilmis_merge,
    "semantik": yontem_semantik,
    "overlap_recursive": yontem_overlap_recursive,
}

TUR_TO_YONTEM = {
    "pdf_yapisiz": "overlap_recursive",
    "liste_agirlikli": "genellestirilmis_merge",
    "karisik": "semantik",
    "duz_metin": "mevcut",
}


def _sayfa_turunu_belirle(content: str) -> str:
    """
    Sayfa icerigine SADECE ucuz, embedding-siz sinyallere bakarak bir
    "tur" etiketi verir - asil karar mantigi burada, yontem_sec bunu
    sadece isimden fonksiyona cevirir. Kontrol sirasi ONEMLI: once en
    "belirgin" sinyal (asiri uzun tek bolum) kontrol ediliyor, cunku
    bir PDF sayfasinda tesadufen birkac liste satiri da olabilir - o
    durumda bile asil sorun yapisizlik, liste orani degil.
    """
    bolumler = bos_parcalari_temizle(markdown_bol(content))
    en_uzun_bolum = max((token_sayisi(b.icerik) for b in bolumler), default=0)

    satirlar = [s for s in content.split("\n") if s.strip()]
    madde_satirlari = [s for s in satirlar if _madde_satiri_mi(s)]
    liste_orani = len(madde_satirlari) / len(satirlar) if satirlar else 0.0

    if en_uzun_bolum > BUYUK_BOLUM_ESIGI:
        return "pdf_yapisiz"
    if liste_orani >= LISTE_AGIRLIKLI_ESIGI:
        return "liste_agirlikli"
    if liste_orani > 0:
        return "karisik"
    return "duz_metin"


def yontem_sec(content: str) -> tuple[str, list[MetinParcasi]]:
    """
    Sayfa icerigine bakip en uygun chunking yontemini SECER, calistirir
    ve (secilen yontemin ismi, sonuc parcalari) dondurur - hem hangi
    kararin verildigini gorebilmek hem de sonucu dogrudan kullanabilmek
    icin.
    """
    tur = _sayfa_turunu_belirle(content)
    yontem_adi = TUR_TO_YONTEM[tur]
    yontem_fonksiyonu = YONTEMLER_BY_ISIM[yontem_adi]
    return yontem_adi, yontem_fonksiyonu(content)


if __name__ == "__main__":
    import asyncio
    from run_test_chunk import SAYFA_IDLERI, sayfalari_getir

    async def _demo():
        sayfalar = await sayfalari_getir(SAYFA_IDLERI)
        for sayfa in sayfalar:
            tur = _sayfa_turunu_belirle(sayfa.content)
            yontem_adi, parcalar = yontem_sec(sayfa.content)
            print(f"Sayfa {sayfa.id:3d} ({sayfa.title:30s}) | tur={tur:16s} | secilen={yontem_adi:24s} | parca={len(parcalar)}")

    asyncio.run(_demo())
