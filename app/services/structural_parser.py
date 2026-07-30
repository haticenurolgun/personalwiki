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