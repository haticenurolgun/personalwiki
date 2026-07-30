"""
markdown_connector.py

Kullanicinin DOGRUDAN yapistirdigi (bir dosyadan degil) markdown
metnini parcalara ayirir. pdf_connector.py'nin markdown karsiligi -
ikisi de ayni sekle uyuyor: bir "kaynak turu"nden MetinParcasi listesi
uretiyorlar, veritabanina hicbir sey yazmiyorlar.

NEDEN BU DOSYA NEREDEYSE BOS: pasted markdown icin bugun ekstra bir
on-isleme gerekmiyor, structural_parser.markdown_bol zaten yeterli.
Ama sources.py router'inin PDF'te oldugu gibi "icerik -> connector ->
parcalar" akisini izlemesi ve ileride pasted metne ozel bir on-isleme
(orn. YAML front-matter temizleme) eklenmek istenirse buraya
eklenebilmesi icin, dogrudan markdown_bol cagirmak yerine adlandirilmis
bir fonksiyon burada tutuluyor.

ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz.
"""

from app.services.structural_parser import MetinParcasi, markdown_bol


def markdown_metnini_cikar(icerik: str) -> list[MetinParcasi]:
    """
    Verilen markdown metnini baslik/bolum bazinda MetinParcasi
    listesine cevirir. pdf_metnini_cikar'in dosyasiz karsiligi.
    """
    return markdown_bol(icerik)
