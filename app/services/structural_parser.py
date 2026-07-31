# =============================================================================
# structural_parser.py
# =============================================================================
# Markdown metnini BASLIKLARA gore parcalara boler.
# ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz. Sadece metin
# alir, parcalanmis metin listesi dondurur. Boylece veritabani hic
# kurulu olmadan bile bu fonksiyonu tek basina test edebiliriz.
# =============================================================================

from dataclasses import dataclass


@dataclass
class MetinParcasi:
    """
    Bolme isleminden cikan TEK BIR parcayi temsil eder.
    dataclass, bize otomatik olarak __init__ (kurucu fonksiyon) ve
    okunabilir bir __repr__ ureten bir Python kisayolu - normal bir
    class yazsaydik bunlari elle yazmamiz gerekirdi.
    """
    baslik: str      # bu parcanin ait oldugu baslik (orn. "1NF")
    icerik: str      # bu basligin altindaki metin
    seviye: int       # baslik seviyesi (1 = #, 2 = ##, 3 = ###)


def markdown_bol(content: str) -> list[MetinParcasi]:
    """
    Markdown metnini # basliklarina gore parcalara boler.

    Ornek:
        "# Baslik\nmetin\n## Alt baslik\nmetin2"
        -> [MetinParcasi(baslik="Baslik", icerik="metin", seviye=1),
            MetinParcasi(baslik="Alt baslik", icerik="metin2", seviye=2)]
    """
    parcalar: list[MetinParcasi] = []
    satirlar = content.split("\n")

    su_anki_baslik = "Giris"   # hic baslik yoksa varsayilan bolum adi
    su_anki_seviye = 0
    su_anki_icerik: list[str] = []   # su an topladigimiz ham satirlar

    for satir in satirlar:
        if satir.startswith("#"):
            # 1) Yeni bir basliga geciyoruz. Ama once, bir onceki
            #    baslik altinda biriktirdigimiz icerik varsa, onu
            #    KAYBETMEDEN bir MetinParcasi olarak kaydedelim.
            if su_anki_icerik:
                parcalar.append(MetinParcasi(
                    baslik=su_anki_baslik,
                    icerik="\n".join(su_anki_icerik),
                    seviye=su_anki_seviye,
                ))

            # 2) Yeni basligin seviyesini say (kac tane # var).
            #    "## 1NF" -> len("## 1NF")=6, len(" 1NF")=4, fark=2
            su_anki_seviye = len(satir) - len(satir.lstrip("#"))

            # 3) Yeni basligin metnini cikar (# isaretlerini ve
            #    bosluklari temizleyerek).
            su_anki_baslik = satir.lstrip("#").strip()

            # 4) Yeni bolum icin icerik listesini sifirla.
            su_anki_icerik = []
        else:
            # Baslik degil, normal bir metin satiri -> biriktir.
            su_anki_icerik.append(satir)

    # Dongu bitti. Ama metnin EN SON bolumu hala kaydedilmedi, cunku
    # kaydetme islemi sadece "yeni bir baslik gorunce" tetikleniyordu.
    # Son bolumun ardindan yeni bir baslik gelmedigi icin, bunu
    # dongu disinda bir kere daha elle yapmamiz lazim.
    if su_anki_icerik:
        parcalar.append(MetinParcasi(
            baslik=su_anki_baslik,
            icerik="\n".join(su_anki_icerik),
            seviye=su_anki_seviye,
        ))

    return parcalar


def parcalari_boyuta_gore_bol(
    parcalar: list[MetinParcasi],
    token_sayan_fonksiyon,
    maks_token: int = 128,  # paraphrase-multilingual-MiniLM-L12-v2'nin max_seq_length'i
) -> list[MetinParcasi]:
    """
    markdown_bol basliklara gore boler, ama bir baslik altindaki metin
    yine de COK UZUN olabilir (orn. 3000 token) - embedding modelinin
    bir token siniri var (bkz. embedding_servisi.py), siniri asan kisim
    SESSIZCE kirpiliyor. Bu fonksiyon, siniri asan parcalari PARAGRAF
    sinirlarindan bolerek kucuk alt-parcalara ayirir - boylece hicbir
    icerik embedding'e girmeden kaybolmaz.

    token_sayan_fonksiyon: bir metin alip token sayisini donduren
    fonksiyon. Bu fonksiyonun DISARIDAN parametre olarak verilmesinin
    sebebi: bu dosya (structural_parser.py) veritabani/model gibi agir
    bagimliliklardan TAMAMEN bagimsiz kalsin istiyoruz (dosyanin en
    basindaki kural) - gercek token sayimi (BERT tokenizer) embedding_
    servisi.py'de yasiyor, oraya bagimli olmadan burada test edilebiliriz
    (basit bir "len(metin.split())" ile bile test yazilabilir).

    Donen deger: hicbir parca maks_token'i asmayan YENI bir liste. Alt-
    parcalarin baslik/seviye'si, ait olduklari orijinal parcayla AYNI -
    boylece arama sonucunda hala "hangi baslik altinda" bilgisi kalir.
    """
    sonuc: list[MetinParcasi] = []

    for parca in parcalar:
        if token_sayan_fonksiyon(parca.icerik) <= maks_token:
            sonuc.append(parca)
            continue

        # Bu TEK parcadan uretilen alt-parcalari ONCE AYRI bir listede
        # (parca_sonuclari) topluyoruz, dogrudan sonuc'a eklemiyoruz -
        # boylece asagidaki "cok kucuk artik parcalari birlestir"
        # adimini SADECE bu parcanin kendi alt-parcalari arasinda
        # yapabiliriz. Eger dogrudan sonuc'a eklesek, bu parcanin son
        # (kucuk) alt-parcasi YANLISLIKLA bir SONRAKI, TAMAMEN FARKLI
        # bolumun/liste maddesinin ilk parcasiyla birlesebilirdi.
        parca_sonuclari: list[MetinParcasi] = []

        # Once paragraf sinirlarindan (bos satir) parcala.
        paragraflar = [p for p in parca.icerik.split("\n\n") if p.strip()]

        biriken_paragraflar: list[str] = []

        def alt_parcayi_kaydet():
            if biriken_paragraflar:
                parca_sonuclari.append(MetinParcasi(
                    baslik=parca.baslik,
                    icerik="\n\n".join(biriken_paragraflar),
                    seviye=parca.seviye,
                ))

        for paragraf in paragraflar:
            if token_sayan_fonksiyon(paragraf) > maks_token:
                # Tek bir paragraf bile sinirin uzerinde - once o ana
                # kadar biriken paragraflari kaydet, sonra bu paragrafi
                # kelime kelime, GERCEK token sayisini olcerek zorla
                # parcala. Sabit bir "kac kelime = kac token" tahmini
                # GUVENILMEZ - Turkce'de kimi kelimeler (orn. uzun
                # bilesik/eklemeli kelimeler) BERT tokenizer'da tek
                # basina 3-4 token'a bolunebiliyor, bu yuzden her adimda
                # gercekten olcuyoruz (tahmin etmiyoruz).
                alt_parcayi_kaydet()
                biriken_paragraflar = []

                biriken_kelimeler: list[str] = []
                for kelime in paragraf.split():
                    aday_kelimeler = biriken_kelimeler + [kelime]
                    if token_sayan_fonksiyon(" ".join(aday_kelimeler)) > maks_token:
                        if biriken_kelimeler:
                            parca_sonuclari.append(MetinParcasi(
                                baslik=parca.baslik,
                                icerik=" ".join(biriken_kelimeler),
                                seviye=parca.seviye,
                            ))
                        biriken_kelimeler = [kelime]
                    else:
                        biriken_kelimeler = aday_kelimeler

                if biriken_kelimeler:
                    parca_sonuclari.append(MetinParcasi(
                        baslik=parca.baslik,
                        icerik=" ".join(biriken_kelimeler),
                        seviye=parca.seviye,
                    ))
                continue

            aday = biriken_paragraflar + [paragraf]
            if token_sayan_fonksiyon("\n\n".join(aday)) > maks_token:
                alt_parcayi_kaydet()
                biriken_paragraflar = [paragraf]
            else:
                biriken_paragraflar = aday

        alt_parcayi_kaydet()

        # Cok kucuk kalan artik alt-parcalari (orn. bir paragrafin/
        # kelime dizisinin en sonunda kalan bir kac kelimelik kalinti),
        # hemen ONCEKI alt-parcayla BIRLESTIR - bkz. _kucuk_artiklari_
        # birlestir docstring'i. Sadece bu TEK parcanin alt-parcalari
        # arasinda calisiyor, farkli bolum/liste maddeleriyle karismaz.
        sonuc.extend(_kucuk_artiklari_birlestir(parca_sonuclari, token_sayan_fonksiyon))

    return sonuc


# Bir alt-parca, bu kadar TOKEN'DAN AZ ise "cok kucuk" sayilir ve
# komsu parcayla birlestirilir. NEDEN: tek basina anlamli bir
# embedding uretemeyecek kadar kisa parcalar (orn. bir paragrafin
# sonunda kalan "cozulmelidir.</u>**" gibi bir kac kelimelik cumle
# artigi), aramada "gurultu" gibi davraniyor - anlamsiz oldugu icin
# ALAKASIZ sorgularda bile garip sekilde orta seviye benzerlik skoru
# alip gercek sonuclarin yerini caliyor. Gercek kullanimda test
# edilerek bulundu.
MIN_PARCA_TOKEN = 20


def _kucuk_artiklari_birlestir(parcalar: list[MetinParcasi], token_sayan_fonksiyon) -> list[MetinParcasi]:
    """
    Ardisik alt-parcalar arasinda MIN_PARCA_TOKEN'dan kucuk olanlari,
    bir ONCEKI alt-parcayla birlestirir. SADECE parcalari_boyuta_gore_
    bol icinde, TEK bir kaynak bolumden uretilen alt-parcalar
    uzerinde cagrilir - bu yuzden farkli bolumler/liste maddeleri
    ASLA birbirine karismaz (cagiran kod bunu garanti ediyor).

    NOT: birlestirme sonucu maks_token'i BIRAZ asabilir (MIN_PARCA_
    TOKEN kadar) - bu kabul edilebilir bir bedel, cunku alternatifi
    (kucuk, anlamsiz bir "yetim" parca birakmak) arama kalitesi icin
    daha kotu.
    """
    if not parcalar:
        return parcalar

    sonuc = [parcalar[0]]
    for parca in parcalar[1:]:
        if token_sayan_fonksiyon(parca.icerik) < MIN_PARCA_TOKEN:
            onceki = sonuc[-1]
            sonuc[-1] = MetinParcasi(
                baslik=onceki.baslik,
                icerik=onceki.icerik + "\n\n" + parca.icerik,
                seviye=onceki.seviye,
            )
        else:
            sonuc.append(parca)

    return sonuc


def _madde_satiri_mi(satir: str) -> bool:
    """Bir satir "- ", "* " ile ya da "1. " gibi numarayla mi basliyor?"""
    satir = satir.strip()
    if satir.startswith("- ") or satir.startswith("* ") or satir in ("-", "*"):
        return True
    # "1. ", "12. " gibi numarali madde kontrolu.
    nokta_index = satir.find(". ")
    if nokta_index > 0 and satir[:nokta_index].isdigit():
        return True
    return False


def liste_maddelerine_gore_bol(parcalar: list[MetinParcasi]) -> list[MetinParcasi]:
    """
    Bir bolumun ICERIGI TAMAMEN (satir satir hepsi) madde isaretli
    satirlardan olusuyorsa VE en az 2 madde varsa, HER MADDEYI AYRI
    bir MetinParcasi yapar - boylece bir parcanin embedding'i, birden
    fazla BAGIMSIZ gercegi (orn. "15 Ocak - Elektronik Devreler
    sinavi" gibi bir sinav takvimi maddesi) TEK VEKTORDE "sulandirip"
    ortalamaya dusurmez.

    NEDEN GEREKLI: gercek kullanimda test edilerek bulundu - 3 farkli
    dersin sinav tarihini iceren TEK bir bolum, "elektronik devreler
    sinavi" sorgusuna 0.42 kozinus benzerligi verirken, SADECE o
    maddenin (satirin) embedding'i 0.60 benzerlik veriyordu.

    NEDEN SADECE BOLUM TAMAMEN LISTE OLDUGUNDA BOLUYORUZ (duz metinle
    KARISIK degilse ya da tek bir madde varsa BOLMUYORUZ): bir bolumde
    "Faydalari:\n- Hiz\n- Guvenlik" gibi BIRBIRINE BAGLI alt-maddeler
    de olabilir - bunlari ayirmak "Faydalari" baglamini KAYBETTIRIR,
    madde tek basina anlamsiz kalabilir. Bu bir kesin cozum degil,
    bilincli bir denge - cogunlukla dogru tarafta hata yapar (bagimsiz
    gercekleri ayirmak, iliskili alt-maddeleri ayirmaktan daha sik
    karsilasilan ve daha faydali bir durum).
    """
    sonuc: list[MetinParcasi] = []

    for parca in parcalar:
        satirlar = [s for s in parca.icerik.split("\n") if s.strip()]
        madde_satirlari = [s for s in satirlar if _madde_satiri_mi(s)]

        if len(satirlar) >= 2 and len(madde_satirlari) == len(satirlar):
            for madde in madde_satirlari:
                # Basindaki "- ", "* " ya da "1. " isaretini temizle -
                # embedding'e giden metin gereksiz noktalama gurultusu
                # tasimasin.
                temiz_madde = madde.strip().lstrip("-*").strip()
                if temiz_madde and temiz_madde[0].isdigit():
                    nokta_index = temiz_madde.find(". ")
                    if nokta_index > 0 and temiz_madde[:nokta_index].isdigit():
                        temiz_madde = temiz_madde[nokta_index + 2:].strip()

                sonuc.append(MetinParcasi(
                    baslik=parca.baslik,
                    icerik=temiz_madde,
                    seviye=parca.seviye,
                ))
        else:
            sonuc.append(parca)

    return sonuc


def bos_parcalari_temizle(parcalar: list[MetinParcasi]) -> list[MetinParcasi]:
    """
    Icerigi BOS (ya da sadece bosluk) olan parcalari eler.

    NEDEN GEREKLI: bir baslik, hemen ardindan baska bir baslik
    geliyorsa (aralarinda govde metni yoksa - orn. "# Baslik\n##
    Alt Baslik") markdown_bol, "Baslik" icin BOS icerikli bir
    MetinParcasi uretir. Boyle bir parca SemanticUnit olarak
    kaydedilip embed edilirse (BOS bir metnin embedding'i!), LLM'e
    "hicbir bilgi tasimayan" bir "kaynak" olarak sunulur - arama/
    sohbet baglamini gereksiz yere kalabaliklastirir, gercek bilgiyi
    "sulandirir". Gercek kullanimda bulundu: 452 unit'in 51'i (%11)
    bos cikmisti.
    """
    return [parca for parca in parcalar if parca.icerik.strip()]