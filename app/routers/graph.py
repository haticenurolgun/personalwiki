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
    GlobalGrafIliski,
)
from app.services.graph_servisi import global_graf_yeniden_hesapla, global_grafi_getir

router = APIRouter(prefix="/graph", tags=["Global Graph"])


@router.post("/global/yeniden-hesapla", response_model=GlobalGrafYenidenHesaplaCevabi)
async def global_grafi_yeniden_hesapla_endpoint(
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    SayfaBaglantisi VE SayfaIliskisi tablolarini tamamen siler ve
    mevcut ConceptNode/ConceptRelation/KavramGorulme verisine gore
    sifirdan yeniden kurar. Bu, yeni kavram cikarimi yapildiktan sonra
    (POST /pages/{id}/extract-concepts) veya manuel olarak cagirilabilir.
    """
    olusturulan_baglanti_sayisi, olusturulan_iliski_sayisi = await global_graf_yeniden_hesapla(db)

    return GlobalGrafYenidenHesaplaCevabi(
        olusturulan_baglanti_sayisi=olusturulan_baglanti_sayisi,
        olusturulan_iliski_sayisi=olusturulan_iliski_sayisi,
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
    sayfalar, baglantilar, sayfa_iliskileri = await global_grafi_getir(db)

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

    iliski_listesi = [
        GlobalGrafIliski(
            kaynak_sayfa_id=iliski.kaynak_sayfa_id,
            hedef_sayfa_id=iliski.hedef_sayfa_id,
            iliski_tipi=iliski.iliski_tipi,
            kaynak_kavram_ismi=iliski.kaynak_kavram_ismi,
            hedef_kavram_ismi=iliski.hedef_kavram_ismi,
        )
        for iliski in sayfa_iliskileri
    ]

    return GlobalGrafCevabi(
        sayfalar=sayfa_listesi,
        baglantilar=baglanti_listesi,
        sayfa_iliskileri=iliski_listesi,
    )