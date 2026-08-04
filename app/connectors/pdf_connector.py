"""
pdf_connector.py

Yuklenen bir PDF dosyasindan METIN cikaran servis. pymupdf4llm
kutuphanesini kullaniyoruz - bu kutuphane PDF'i font boyutu/kalinlik
gibi GORSEL ipuclarina bakarak GERCEK basliklara (#, ##) ayirmis
markdown'a cevirir. Bu islem TAMAMEN YEREL calisir, hicbir LLM/API
cagrisi GEREKTIRMEZ.

NEDEN SADECE BASLIK YAPISI YETERLI: projenin hedefi PDF'in birebir
kopyasini (tablolar, gorseller dahil) tutmak degil, ANA FIKIR ve
KAVRAMLARI yakalamak. Bu yuzden pymupdf4llm'in tablo/gorsel
donusumundeki kalite sinirlamalari bizi ilgilendirmiyor - sadece
baslik hiyerarsisini dogru cikarmasi yeterli, ki bu onun EN GUCLU
oldugu nokta.

NEDEN SAYFA BAZLI BOLMEDEN VAZGECTIK: eskiden her PDF sayfasini ayri
bir SemanticUnit yapiyorduk, ama "sayfa" fiziksel bir sinir, ANLAMSAL
bir sinir degil. Projenin hedefi PDF'in birebir kopyasini tutmak
degil, ana fikir/kavramlari yakalamak oldugu icin, GERCEK baslik/
bolum sinirlarina gore bolmek cok daha dogru bir yaklasim.

NEDEN BURADA HIC BOLME YOK (markdown_bol BURADA CAGRILMIYOR): bu
dosya sadece HAM markdown METNINI dondurur - PDF'i nasil parcalara
bolecegini (hangi chunking yontemunu kullanacagini) chunking_secici.py
karar veriyor. Boylece PDF'ten gelen ve elle yazilmis markdown'dan
gelen icerik AYNI, TEK secim pipeline'indan geciyor - PDF'e ozel
ayri bir bolme mantigi olmuyor.

ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz. Sadece bir
dosya yolu alir, ham markdown metni dondurur.
"""

from collections import Counter

import pymupdf4llm

# Bir satirin "tekrar eden header/footer" sayilmasi icin, PDF'teki
# SAYFALARIN en az bu ORANI kadarinda (birebir ayni sekilde) gecmesi
# gerekir. pymupdf4llm cogu header/footer'i zaten ayikliyor, ama bu
# YEDEK bir guvenlik katmani - kacan tekrarlari yakalamak icin.
TEKRAR_ESIGI_ORANI = 0.5


def _tekrar_eden_satirlari_bul(sayfa_metinleri: list[str]) -> set[str]:
    """
    Sayfa bazli metinlerdeki TEKRAR EDEN satirlari (yazar adi, kurum
    adi gibi HER sayfada gecen metadata) tespit eder. Bir satirin,
    sayfalarin BUYUK COGUNLUGUNDA (TEKRAR_ESIGI_ORANI kadar) birebir
    ayni sekilde gecmesi gerekir - boylece normal, tek seferlik
    tekrarlar (orn. bir kod ornegindeki "return 0;") yanlislikla
    silinmez.
    """
    if not sayfa_metinleri:
        return set()

    satir_sayaci = Counter()

    for sayfa_metni in sayfa_metinleri:
        # Bir sayfa icinde ayni satir birden fazla kez gecse bile,
        # bu sayfa icin SADECE BIR KEZ sayiyoruz (set kullanarak) -
        # yoksa bir sayfadaki tekrar, cok-sayfali tekrari yanlislikla
        # taklit edebilir.
        benzersiz_satirlar = set(
            satir.strip() for satir in sayfa_metni.split("\n") if satir.strip()
        )
        for satir in benzersiz_satirlar:
            satir_sayaci[satir] += 1

    esik_sayfa_sayisi = len(sayfa_metinleri) * TEKRAR_ESIGI_ORANI

    # "sayi >= 2" sarti ONEMLI: "sayi >= esik_sayfa_sayisi" tek basina
    # az sayfali PDF'lerde (1-2 sayfa) yanlis calisiyordu. Ornek: 1
    # sayfalik bir PDF'te esik_sayfa_sayisi = 1*0.5 = 0.5 olur, ve
    # SADECE BIR KEZ gecen (yani hic tekrar etmeyen) her satir bile
    # "1 >= 0.5" oldugu icin yanlislikla "tekrar eden" sayilip
    # siliniyordu - bu da TUM sayfanin icerigini bosaltip PDF'ten hic
    # metin cikarilamamis gibi gorunmesine sebep oluyordu (gercekten
    # yasandi, bkz. gecmis test). Bir satirin "tekrar eden" sayilmasi
    # icin MANTIKEN en az 2 kez gecmesi sarttir - oran ne olursa olsun.
    return {
        satir for satir, sayi in satir_sayaci.items()
        if sayi >= esik_sayfa_sayisi and sayi >= 2
    }


def pdf_metnini_cikar(dosya_yolu: str) -> str:
    """
    PDF'i pymupdf4llm ile GERCEK basliklara ayrilmis markdown METNINE
    cevirir (henuz PARCALARA BOLMEDEN - bkz. dosyanin en ustundeki
    "NEDEN BURADA HIC BOLME YOK" notu). Tablo/gorsel dogrulugu
    ONEMSENMIYOR - sadece baslik yapisi cikarmak yeterli.

    ADIMLAR:
    1) Sayfa bazli ham metni al (SADECE header/footer tespiti icin)
    2) Tum PDF'i BIRLESIK markdown olarak al (baslik hiyerarsisiyle)
    3) Tekrar eden (header/footer) satirlari birlesik markdown'dan temizle

    dosya_yolu: PDF dosyasinin sunucudaki fiziksel yolu

    Donen deger: ham markdown metni. PDF'ten hic metin cikarilamazsa
                 (orn. taranmis/goruntu tabanli PDF) BOS string doner.
    """

    # 1) Sayfa bazli ham metni al - SADECE header/footer tespiti icin
    sayfa_parcalari = pymupdf4llm.to_markdown(dosya_yolu, page_chunks=True)
    ham_sayfa_metinleri = [parca["text"] for parca in sayfa_parcalari]

    tekrar_eden_satirlar = _tekrar_eden_satirlari_bul(ham_sayfa_metinleri)

    # 2) Tum PDF'i BIRLESIK markdown olarak al (baslik hiyerarsisiyle)
    tam_markdown = pymupdf4llm.to_markdown(dosya_yolu)

    # 3) Tekrar eden satirlari temizle
    if tekrar_eden_satirlar:
        temiz_satirlar = [
            satir for satir in tam_markdown.split("\n")
            if satir.strip() not in tekrar_eden_satirlar
        ]
        tam_markdown = "\n".join(temiz_satirlar)

    if not tam_markdown.strip():
        return ""

    return tam_markdown