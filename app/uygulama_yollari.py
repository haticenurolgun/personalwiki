"""
uygulama_yollari.py

Uygulamanin dosya yollarini (personalwiki.db, chroma_data/, .env,
app/uploads/) COZERKEN, calisma dizinine (CWD) ya da modul dosyasinin
konumuna (__file__) degil, TABAN DIZINE gore MUTLAK yollar uretir.

NEDEN GEREKLI: PyInstaller ile PAKETLENMIS (frozen) bir exe, nereden
calistirilirsa calistirilsin (masaustune cift tiklanarak, bir
kisayoldan, farkli bir CWD'den terminalden) HEP AYNI personalwiki.db/
chroma_data/.env/app.uploads klasorlerini bulmali - "./personalwiki.db"
gibi CWD'ye gore bir yol, exe baska bir klasorden calistirilinca YANLIS
(ya da BOS/yeni) bir dosyaya isaret eder. Bu yuzden frozen halde
sys.executable'in (exe dosyasinin KENDISININ) bulundugu klasor taban
aliniyor. Normal (paketlenmemis) Python calismasinda davranis
DEGISMEZ - proje kok dizinine gore calismaya devam eder.
"""

import os
import sys


def taban_dizini() -> str:
    """
    PyInstaller ile paketlenmis halde exe'nin bulundugu klasoru,
    normal Python calismasinda proje kok dizinini dondurur.

    getattr(sys, "frozen", False): PyInstaller'in frozen exe'lere
    otomatik ekledigi bir bayrak - sadece paketlenmis halde True olur,
    normal "python main.py" calistirmasinda bu ozellik hic YOK
    (getattr varsayilan olarak False donduruyor).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    # Bu dosya app/uygulama_yollari.py'de yasiyor - bir ust dizin
    # (app/'nin ebeveyni) proje kok dizinidir.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def yol(*parcalar: str) -> str:
    """taban_dizini()'ne gore MUTLAK bir dosya/klasor yolu olusturur."""
    return os.path.join(taban_dizini(), *parcalar)
