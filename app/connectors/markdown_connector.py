"""
markdown_connector.py

Kullanicinin DOGRUDAN yapistirdigi (bir dosyadan degil) markdown
metnini isler. pdf_connector.py'nin markdown karsiligi - ikisi de ayni
sekle uyuyor: bir "kaynak turu"nden HAM metin uretiyorlar, veritabanina
hicbir sey yazmiyorlar, PARCALARA BOLMUYORLAR (bunu chunking_secici.py
yapiyor - bkz. o dosyadaki "NEDEN BURADA HIC BOLME YOK" notu).

NEDEN BU DOSYA NEREDEYSE BOS: pasted markdown icin bugun ekstra bir
on-isleme gerekmiyor. Ama sources.py router'inin PDF'te oldugu gibi
"icerik -> connector -> ham metin" akisini izlemesi ve ileride pasted
metne ozel bir on-isleme (orn. YAML front-matter temizleme) eklenmek
istenirse buraya eklenebilmesi icin, icerigi oldugu gibi dondurmek
yerine adlandirilmis bir fonksiyon burada tutuluyor.

ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz.
"""


def markdown_metnini_cikar(icerik: str) -> str:
    """
    Verilen markdown metnini (su an icin) oldugu gibi dondurur -
    pdf_metnini_cikar'in dosyasiz karsiligi.
    """
    return icerik
