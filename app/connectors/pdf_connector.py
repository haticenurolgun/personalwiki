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

OCR (TARANMIS/GORUNTU TABANLI SAYFALAR): pymupdf4llm, gercek metin
bulamadigi sayfalari OTOMATIK olarak OCR'a yollar (use_ocr=True
varsayilan) - ama BUNU YAPABILMESI icin sistemde bir OCR motoru
BULUNMASI gerekir. Biz Tesseract OCR'i kullaniyoruz: sistemde
"tesseract" kurulu DEGILSE, pymupdf4llm sessizce OCR'i devre disi
birakir ve o sayfalar BOS doner (bkz. asagidaki OCR_DILI notu ve
kurulum icin sources.py'deki HTTPException mesaji). Kurulacaksa:
UB-Mannheim Tesseract dagitimi (winget: UB-Mannheim.TesseractOCR)
+ Turkce dil verisi (tur.traineddata, tessdata klasorune).

NEDEN TESSDATA_PREFIX'I BURADA SET EDIYORUZ: pymupdf, Tesseract'in
tessdata klasorunu bulmak icin ONCE TESSDATA_PREFIX ortam
degiskenine, YOKSA "where tesseract" ile PATH'e bakiyor. Ama
UB-Mannheim'in winget kurulumu, kurulum klasorunu PATH'e EKLEMIYOR -
yani Tesseract diskte kurulu olsa bile pymupdf onu goremiyor ve OCR
sessizce hic calismiyordu (gercekten yasandi, bkz. gecmis test).
TESSDATA_PREFIX zaten kullanici tarafindan ayarlanmamissa VE
varsayilan kurulum klasoru diskte varsa, PATH'e dokunmadan (sistem
genelinde bir degisiklik yapmadan) SADECE bu process icin ortam
degiskenini set ediyoruz - boylece kullanicinin PATH'ini elle
duzenlemesine gerek kalmiyor.

NEDEN OCR'I SADECE "GERCEKTEN TARANMIS" BELGELERDE ACIYORUZ (belgenin
GENELINDE native metin varsa OCR HIC calistirmiyoruz): pymupdf4llm'in
sayfa-bazli "bu sayfada OCR gerekli mi" karari (needs_ocr), hem GERCEK
metin HEM fotograf/gorsel barindiran KARMA sayfalarda (orn. dergi
reklam sayfalari - metin var ama sayfada gorsel agirlikli) YANLIS
pozitif verebiliyor. Boyle bir sayfada OCR yanlislikla tetiklenirse,
pymupdf4llm'in Tesseract entegrasyonu sayfadaki TUM metni siler ve
SADECE OCR'in bulabildigiyle degistirir - eger OCR o sayfayi (spans
zaten "legible" sayildigi icin OCR'a gonderilen goruntude kor
birakilarak) BOS/bozuk okursa, GERCEK VE DOGRU olan orijinal metin
GERI DONDURULEMEZ SEKILDE KAYBOLUR (gercekten yasandi, bkz. gecmis
test - "Dergi-Tarama-Ornek.pdf": her sayfada 500-7000+ karakter native
metin olmasina ragmen 5 sayfada OCR yanlislikla tetiklendi ve o
sayfalarin gercek metni bozuk OCR ciktisiyla degisti). Bu riski
ONLEMEK icin: OCR'i SADECE belgenin GENELINDE ciddi miktarda native
metin YOKSA (yani belge GERCEKTEN taranmis/goruntu tabanliysa) actik -
bkz. asagidaki _taranmis_pdf_mi(). Zaten native metni olan belgelerde
OCR hic devreye girmiyor, bu yuzden bu veri kaybi riski OLUSMUYOR.

ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz. Sadece bir
dosya yolu alir, ham markdown metni dondurur.
"""

import os
from collections import Counter

import pymupdf
import pymupdf4llm

# Bir satirin "tekrar eden header/footer" sayilmasi icin, PDF'teki
# SAYFALARIN en az bu ORANI kadarinda (birebir ayni sekilde) gecmesi
# gerekir. pymupdf4llm cogu header/footer'i zaten ayikliyor, ama bu
# YEDEK bir guvenlik katmani - kacan tekrarlari yakalamak icin.
TEKRAR_ESIGI_ORANI = 0.5

# Tesseract'a OCR sirasinda hangi dil(ler)i taniyacagini soyluyoruz.
# "tur+eng" ile HEM Turkce HEM Ingilizce karakterleri/kelimeleri
# tanimaya calisir (cogu PDF'te en az biri gecer, ikisi ayni anda
# denenmesi ekstra maliyetsiz - Tesseract ikisini birlikte kullanir).
OCR_DILI = "tur+eng"

# UB-Mannheim Tesseract kurulumunun VARSAYILAN klasoru - bkz. dosyanin
# en ustundeki "NEDEN TESSDATA_PREFIX'I BURADA SET EDIYORUZ" notu.
_VARSAYILAN_TESSERACT_TESSDATA = r"C:\Program Files\Tesseract-OCR\tessdata"

if not os.getenv("TESSDATA_PREFIX") and os.path.isdir(_VARSAYILAN_TESSERACT_TESSDATA):
    os.environ["TESSDATA_PREFIX"] = _VARSAYILAN_TESSERACT_TESSDATA

# Bir belgenin "gercekten taranmis" sayilmasi icin, sayfa basina
# ORTALAMA native (OCR'siz, dogrudan pymupdf'in bulabildigi) metin
# miktarinin bu karakter sayisinin ALTINDA olmasi gerekir. Gercekten
# taranmis bir sayfada bu deger pratikte 0'dir (sayfa TAMAMEN goruntu);
# gercek bir dijital belgede ise (sayfa basi onlarca-binlerce karakter)
# bu esigi COK asar - bkz. dosyanin en ustundeki "NEDEN OCR'I SADECE
# GERCEKTEN TARANMIS BELGELERDE ACIYORUZ" notu.
NATIVE_METIN_ESIGI_SAYFA_BASINA = 50


def _taranmis_pdf_mi(belge: pymupdf.Document) -> bool:
    """Belgenin GENELINDE ciddi miktarda native metin olup olmadigina
    bakarak, OCR'in GUVENLE acilip acilamayacagina karar verir."""
    if belge.page_count == 0:
        return False
    toplam_native_metin = sum(len(sayfa.get_text().strip()) for sayfa in belge)
    return (toplam_native_metin / belge.page_count) < NATIVE_METIN_ESIGI_SAYFA_BASINA


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

    Belge GENELINDE ciddi miktarda native metin YOKSA (yani belge
    GERCEKTEN taranmis/goruntu tabanliysa) her iki adimda da OCR
    otomatik devreye girer - bkz. dosyanin en ustundeki "NEDEN OCR'I
    SADECE GERCEKTEN TARANMIS BELGELERDE ACIYORUZ" notu. Belgenin
    zaten native metni VARSA (dijital uretilmis bir PDF, karma
    metin+gorsel sayfalari OLSA BILE) OCR HIC calistirilmiyor - veri
    kaybi riskine hic girilmiyor.

    dosya_yolu: PDF dosyasinin sunucudaki fiziksel yolu

    Donen deger: ham markdown metni. PDF'ten hic metin cikarilamazsa
                 (orn. taranmis bir PDF VE sistemde Tesseract kurulu
                 DEGILSE) BOS string doner.
    """

    # PDF'i TEK SEFER aciyoruz ve ayni Document nesnesini asagidaki
    # iki to_markdown cagrisina da veriyoruz (dosya yolu yerine).
    # NEDEN: OCR, taranan sayfaya GERCEK metni kalici olarak GOMER -
    # ayni nesne 2. cagriya da verilince, pymupdf4llm o sayfada artik
    # metin oldugunu gorup TEKRAR OCR YAPMAZ. Eger her cagrida dosya
    # yolu verseydik, pymupdf4llm her seferinde dosyayi SIFIRDAN acar
    # ve HER SAYFAYI IKI KEZ OCR'lardi - Tesseract OCR yavas oldugu
    # icin bu, PDF isleme suresini gereksiz yere ikiye katlardi.
    belge = pymupdf.open(dosya_yolu)

    ocr_ayarlari = (
        {"ocr_language": OCR_DILI} if _taranmis_pdf_mi(belge) else {"use_ocr": False}
    )

    # 1) Sayfa bazli ham metni al - SADECE header/footer tespiti icin
    sayfa_parcalari = pymupdf4llm.to_markdown(
        belge, page_chunks=True, **ocr_ayarlari
    )
    ham_sayfa_metinleri = [parca["text"] for parca in sayfa_parcalari]

    tekrar_eden_satirlar = _tekrar_eden_satirlari_bul(ham_sayfa_metinleri)

    # 2) Tum PDF'i BIRLESIK markdown olarak al (baslik hiyerarsisiyle) -
    #    ayni 'belge' nesnesi kullanildigi icin 1. adimda OCR'lanmis
    #    sayfalar burada TEKRAR OCR'lanmaz.
    tam_markdown = pymupdf4llm.to_markdown(belge, **ocr_ayarlari)

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