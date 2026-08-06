"""
paket_baslat.py

TEK exe icinde HEM backend'i (FastAPI/uvicorn) HEM masaustu istemcisini
(PyQt6, desktop_demo.py) baslatan BIRLESIK giris noktasi - dagitim
paketinde artik "once backend.exe'yi, sonra app.exe'yi calistir" iki
adimi degil, TEK bir exe cift tiklamak yeterli.

NASIL CALISIYOR: backend, ARKA PLAN bir thread'de baslatiliyor
(uvicorn kendi asyncio event loop'unu O thread icinde kendi yonetir),
GUI ise ANA thread'de calisiyor - Qt'nin event loop'u ANA thread'de
calismak ZORUNDA (aksi halde pencere acilmaz/donar). Ikisi FARKLI
thread'lerde oldugu icin birbirini BLOKE etmiyor. Backend thread'i
"daemon" olarak baslatiliyor - yani GUI penceresi kapanip ana thread
sona erince, arka plandaki backend thread'i de OTOMATIK sonlaniyor,
ayrica bir "kapat" sinyali gondermeye gerek yok.

main.py ve desktop_demo.py kendi baslarina da (eskisi gibi, ayri ayri)
calistirilabilir durumda kaliyor - bu dosya SADECE tek-exe paketleme
icin ayri, ucuncu bir giris noktasi.
"""

import sys
import threading
import time

import requests
import uvicorn

from main import app
import desktop_demo


def _backend_thread_calistir():
    """
    uvicorn.run(), CAGRILDIGI thread'i BLOKE eden bir fonksiyon - bu
    yuzden ayri bir thread'de calistiriliyor, ana thread'i (GUI)
    bloke etmesin diye. reload=False (varsayilan) - paketlenmis exe'de
    reload zaten anlamsiz (bkz. main.py'deki ayni gerekce).
    """
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def _backend_hazir_mi() -> bool:
    try:
        requests.get("http://127.0.0.1:8000/health", timeout=1)
        return True
    except requests.exceptions.RequestException:
        return False


def _backend_hazir_olana_kadar_bekle(maks_saniye: int = 90):
    """
    Backend'in (ozellikle embedding modelinin ilk yuklenmesi birkac
    saniye surebiliyor) GERCEKTEN istek kabul etmeye basladigini
    /health uzerinden dogrulayana kadar bekler - GUI'yi, backend daha
    hazir olmadan acip "Backend'e baglanilamadi" hatasiyla
    karsilastirmamak icin. maks_saniye'yi asarsa (backend gercekten
    cokmus olabilir) yine de GUI'yi acar - kullanici en azindan "Yenile"
    ile durumu gorebilsin.
    """
    for _ in range(maks_saniye):
        if _backend_hazir_mi():
            return
        time.sleep(1)


if __name__ == "__main__":
    backend_thread = threading.Thread(target=_backend_thread_calistir, daemon=True)
    backend_thread.start()

    _backend_hazir_olana_kadar_bekle()

    # desktop_demo.main() kendi icinde sys.exit(uygulama.exec()) cagirir -
    # yani GUI kapaninca SystemExit firlar, ana thread sonlanir, DAEMON
    # olan backend thread'i de (bkz. yukarida) otomatik olarak beraberinde
    # sonlanir - ayri bir "backend'i kapat" adimina gerek yok.
    desktop_demo.main()
