# =============================================================================
# search.py
# =============================================================================
# Kullanicinin arama kutusundan sorgu gonderdigi router. Asil hibrit
# arama mantigi (embedding + ontoloji) artik arama_servisi.py'de -
# /chat de AYNI mantigi kullanabilsin diye (bkz. arama_servisi.py
# docstring'i). Bu router sadece hibrit_arama_yap'i cagirip sonucu
# API semasina (AramaSonucu) uygun hale getiriyor.
# =============================================================================

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import WikiPage
from app.models.schemas import AramaSonucu
from app.services.arama_servisi import hibrit_arama_yap

router = APIRouter(prefix="/search", tags=["Arama"])


@router.get("", response_model=list[AramaSonucu])
async def Ara(
    query: str,
    limit: int = 4,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Query: kullanicinin arama metni (query parametresi)\n

    limit: embedding aramasindan kac sonuc alinacak (ontoloji-bazli
    sonuclar bu sayaca dahil degil - bir kavram bulunursa, ona bagli
    TUM parcalar eklenir)
    """
    sonuclar_by_unit_id = await hibrit_arama_yap(db, query, limit)

    # Ilgili TUM sayfalari tek sorguyla getir (sayfa basligi icin).
    page_idler = list({sonuc["page_id"] for sonuc in sonuclar_by_unit_id.values()})
    sayfa_sonucu = await db.execute(select(WikiPage).where(WikiPage.id.in_(page_idler)))
    sayfalar = sayfa_sonucu.scalars().all()
    baslik_sozlugu = {sayfa.id: sayfa.title for sayfa in sayfalar}

    # Sonuclari AramaSonucu semasina uygun hale getir.
    zenginlestirilmis_sonuclar = []
    for sonuc in sonuclar_by_unit_id.values():
        zenginlestirilmis_sonuclar.append(AramaSonucu(
            unit_id=sonuc["unit_id"],
            icerik=sonuc["icerik"],
            page_id=sonuc["page_id"],
            sayfa_basligi=baslik_sozlugu.get(sonuc["page_id"], "Bilinmeyen Sayfa"),
            benzerlik_uzakligi=sonuc["benzerlik_uzakligi"],
            bulunma_sekli=sonuc["bulunma_sekli"],
        ))

    return zenginlestirilmis_sonuclar
