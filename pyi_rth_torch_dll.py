"""
pyi_rth_torch_dll.py

PyInstaller RUNTIME HOOK - paketlenmis exe her baslarken, kullanicinin
kodu (main.py/paket_baslat.py) calismadan HEMEN ONCE otomatik calisir.

NEDEN GEREKLI: torch'un DLL'leri (shm.dll, torch_cpu.dll, vb.)
paketlenmis exe icinde "_internal/torch/lib/" ALT KLASORUNDE duruyor.
Windows, bir DLL'in BAGIMLILIKLARINI ararken varsayilan olarak SADECE
o DLL'in kendi klasorunu + ana exe'nin klasorunu tarar - "_internal/"
klasorunun kendisi (torch/lib'in bir UST klasoru) bu aramaya dahil
DEGIL. Sonuc: shm.dll dosyasi fiziksel olarak PAKETTE VAR olsa bile,
bagimli oldugu baska bir DLL "_internal/"de FLAT durursa Windows onu
bulamiyor ve "WinError 126: Belirtilen modul bulunamadi" hatasi
veriyor (gercekten yasandi - dev makinesinde calisiyordu ama baska
bir bilgisayarda bu hatayla cokuyordu).

COZUM: os.add_dll_directory(), Windows'un DLL arama yoluna ISTEDIGIMIZ
klasorleri ACIKCA ekleyebilecegimiz bir Python 3.8+ API'si. Burada hem
"_internal/" (kokteki flat DLL'ler) HEM "_internal/torch/lib/" (torch'a
ozel DLL'ler) klasorlerini ekliyoruz - boylece hangi DLL hangi
klasorde olursa olsun, birbirini bulabiliyor.

Normal (paketlenmemis) Python calismasinda bu dosya HIC calismiyor -
sadece PyInstaller'in build surecinde runtime_hooks olarak dahil
edildigi icin, SADECE frozen exe icinde devreye giriyor.
"""

import os
import sys

if getattr(sys, "frozen", False) and sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    _meipass = sys._MEIPASS
    for _alt_klasor in (
        _meipass,
        os.path.join(_meipass, "torch", "lib"),
    ):
        if os.path.isdir(_alt_klasor):
            try:
                os.add_dll_directory(_alt_klasor)
            except OSError:
                # Klasor zaten eklenmisse ya da baska bir sebeple
                # reddedilirse, uygulamanin acilisini ENGELLEMESIN -
                # bu sadece bir GUVENLIK AGI, olmazsa eski davranisa
                # (potansiyel DLL hatasi) geri doner, ama en azindan
                # uygulama baslama denemesi YAPAR.
                pass
