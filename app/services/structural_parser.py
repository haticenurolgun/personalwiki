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
    maks_token: int = 256,
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

        # Once paragraf sinirlarindan (bos satir) parcala.
        paragraflar = [p for p in parca.icerik.split("\n\n") if p.strip()]

        biriken_paragraflar: list[str] = []

        def alt_parcayi_kaydet():
            if biriken_paragraflar:
                sonuc.append(MetinParcasi(
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
                            sonuc.append(MetinParcasi(
                                baslik=parca.baslik,
                                icerik=" ".join(biriken_kelimeler),
                                seviye=parca.seviye,
                            ))
                        biriken_kelimeler = [kelime]
                    else:
                        biriken_kelimeler = aday_kelimeler

                if biriken_kelimeler:
                    sonuc.append(MetinParcasi(
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

    return sonuc