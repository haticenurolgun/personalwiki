# giriş noktası. Sadece kurulum yapar:

#FastAPI nesnesini oluşturur. Uygulama açılırken veritabanını hazırlar ,routerrları bağlar

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import veritabanini_hazirla
from app.routers import sources, pages, search, chat, concepts, graph, ontology, kavramlar
from app.services.hatirlatma_servisi import hatirlatma_dongusunu_calistir
import asyncio


#fastapi oluşturuyoruz

app = FastAPI(title="PersonelWiki",version= "0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
async def uygulama_baslarken_calis():
    """FastAPI sunucusu ilk açtığında otomatik çalışır
    görevi: veri tabanındaki tabloların var olduğundan emin olmak,
    ve hatirlatma_servisi.py'nin arka plan taramasini baslatmak -
    bkz. o dosyadaki notlar."""

    await veritabanini_hazirla()
    app.state.hatirlatma_gorevi = asyncio.create_task(hatirlatma_dongusunu_calistir())


@app.on_event("shutdown")
async def uygulama_kapanirken_calis():
    """Arka plan hatirlatma taramasini TEMIZ sekilde durdurur - yoksa
    sunucu kapanirken 'Task was destroyed but it is pending' gibi bir
    uyari birakir (zararsiz ama gurultulu)."""

    app.state.hatirlatma_gorevi.cancel()


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