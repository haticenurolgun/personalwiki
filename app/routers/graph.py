"""
graph.py

Global graph (Katman 2) ile ilgili endpoint'leri toplayan router.
Sayfa ici graph (Katman 1) icin pages.py'deki /pages/{id}/graph
endpoint'ine bak - bu dosya SADECE sayfalar arasi baglantilarla
ilgileniyor.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.schemas import (
    GlobalGrafYenidenHesaplaCevabi,
    GlobalGrafCevabi,
    GlobalGrafSayfa,
    GlobalGrafBaglanti,
)
from app.services.graph_servisi import global_graf_yeniden_hesapla, global_grafi_getir

router = APIRouter(prefix="/graph", tags=["Global Graph"])


@router.post("/global/yeniden-hesapla", response_model=GlobalGrafYenidenHesaplaCevabi)
async def global_grafi_yeniden_hesapla_endpoint(
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    SayfaBaglantisi tablosunu tamamen siler ve mevcut ConceptNode/
    KavramGorulme verisine gore sifirdan yeniden kurar. Bu, yeni
    kavram cikarimi yapildiktan sonra (POST /pages/{id}/extract-concepts)
    veya manuel olarak cagirilabilir.
    """
    olusturulan_sayi = await global_graf_yeniden_hesapla(db)

    return GlobalGrafYenidenHesaplaCevabi(
        olusturulan_baglanti_sayisi=olusturulan_sayi
    )
    
    
@router.get("/global", response_model=GlobalGrafCevabi)
async def global_grafi_getir_endpoint(
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Onceden hesaplanmis global graph'i (Katman 2) doner. Anlik
    hesaplama YAPMAZ - eger veri guncel degilse once
    POST /graph/global/yeniden-hesapla cagrilmali.
    """
    sayfalar, baglantilar = await global_grafi_getir(db)

    sayfa_listesi = [
        GlobalGrafSayfa(id=sayfa.id, title=sayfa.title)
        for sayfa in sayfalar
    ]

    baglanti_listesi = [
        GlobalGrafBaglanti(
            sayfa_id_1=baglanti.sayfa_id_1,
            sayfa_id_2=baglanti.sayfa_id_2,
            ortak_kavram_ismi=baglanti.ortak_kavram_ismi,
        )
        for baglanti in baglantilar
    ]

    return GlobalGrafCevabi(
        sayfalar=sayfa_listesi,
        baglantilar=baglanti_listesi,
    )