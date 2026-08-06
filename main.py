# giriş noktası. Sadece kurulum yapar:

#FastAPI nesnesini oluşturur. Uygulama açılırken veritabanını hazırlar ,routerrları bağlar

import sys
import os

from app.uygulama_yollari import yol

# ONEMLI: bu satir, embedding_servisi.py'yi (dolayisiyla
# sentence_transformers'i) YUKLEYEN HERHANGI BIR IMPORT'TAN ONCE
# calismali - embedding_servisi.py modul SEVIYESINDE
# SentenceTransformer(..., local_files_only=True) cagiriyor, yani
# HF_HUB_CACHE degiskeni o import gerceklesmeden ONCE ayarlanmis
# olmali. PyInstaller ile paketlenmis (frozen) exe'de model
# dosyalari (~1.3GB) exe'nin ICINE gomulmek yerine, exe'nin
# YANINDAKI "hf_cache" klasorunde tutuluyor (bkz. build notlari) -
# boylece onefile paketleme her calistirmada dev bir modeli tekrar
# tekrar acmak zorunda kalmiyor. Normal (paketlenmemis) Python
# calismasinda bu deger zaten os.environ'da yoksa huggingface_hub
# kendi varsayilanini (~/.cache/huggingface/hub) kullanmaya devam
# eder - bu yuzden setdefault kullaniliyor, VAR OLAN bir HF_HUB_CACHE
# degiskenini EZMIYORUZ.
if getattr(sys, "frozen", False):
    os.environ.setdefault("HF_HUB_CACHE", yol("hf_cache"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import veritabanini_hazirla
from app.routers import sources, pages, search, chat, concepts, graph, ontology, kavramlar


#fastapi oluşturuyoruz

app = FastAPI(title="PersonelWiki",version= "0.1.0")

# Statik dosyalar (graph.html) SALT-OKUNUR, degismeyen paket verisi -
# PyInstaller ile paketlenmis (frozen) halde bunlar --add-data ile
# exe'nin ICINE gomuluyor ve calisma anında sys._MEIPASS (PyInstaller'in
# gecici cikartma klasoru) altinda bulunuyor. Normal Python
# calismasinda (frozen degilken) eskisi gibi proje icindeki
# app/static'e bakiyor. NOT: personalwiki.db/chroma_data/app.uploads
# gibi KALICI/degisen veriler icin bu YAKLASIM KULLANILMAZ - onlar
# uygulama_yollari.py::yol() ile exe'nin YANINDAKI (MEIPASS DEGIL)
# klasore yazilir, yoksa her calistirmada sifirlanirlardi.
if getattr(sys, "frozen", False):
    STATIK_DIZINI = os.path.join(sys._MEIPASS, "app", "static")
else:
    STATIK_DIZINI = "app/static"

app.mount("/static", StaticFiles(directory=STATIK_DIZINI), name="static")

@app.on_event("startup")
async def uygulama_baslarken_calis():
    """FastAPI sunucusu ilk açtığında otomatik çalışır
    görevi: veri tabanındaki tabloların var olduğundan emin olmak"""

    await veritabanini_hazirla()


@app.get("/health")
def health_control():
    """
    Basit bir kontrol adresi. Sunucunun calisip calismadigini anlamak
    icin kullanilir. Tarayicidan /health adresine gidip {"status": "ok"}
    goruyorsan, sunucu duzgun calisiyor demektir.
    """
    return {"status": "ok"}

#include_router(...), o belgeleri ana dosyaya fiziksel olarak dahil etme işlemi.
# sources ve pages'i app'e de ekliyorum.
#include_router olmasaydı tüm endpointleri main içinde tanımlamam gerekirdi

app.include_router(sources.router) 
# simdi app, "/sources/markdown" adresini de biliyor

app.include_router(pages.router)
# simdi app, "/pages" ve "/pages/{sayfa_id}" adreslerini de biliyor

app.include_router(search.router)

app.include_router(chat.router)

app.include_router(concepts.router)

app.include_router(graph.router)

app.include_router(ontology.router)

app.include_router(kavramlar.router)


if __name__ == "__main__":
    # Gelistirmede backend "uvicorn main:app --reload" ile ayri bir
    # terminalden calistiriliyor - bu blok O AKISI DEGISTIRMEZ (uvicorn
    # main.py'yi bir MODUL olarak import ediyor, __name__ hicbir zaman
    # "__main__" olmuyor). Bu blok SADECE main.py DOGRUDAN calistirilinca
    # (orn. "python main.py", ya da PyInstaller ile paketlenip exe
    # olarak cift tiklaninca) devreye giriyor - paketlenmis exe'nin
    # KENDI baslatma yolu, reload OLMADAN (reload, ayri bir alt surec
    # + dosya izleme gerektiriyor, tek-dosyalik bir exe'de anlamsiz).
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)