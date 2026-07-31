
# chat.py

# Kullanicinin soru sordugu, RAG akisinin TAMAMININ calistigi endpoint.
# Akis: soru -> hibrit arama (embedding + ontoloji, search.py ile AYNI
# mantik - bkz. arama_servisi.py) -> bulunan parcalar -> LLM'e gonder
# -> LLM'in ürettigi cevap kullaniciya donuyor.
#
# NOT: eskiden bu endpoint SADECE duz embedding aramasi (benzer_
# parcalari_bul) kullaniyordu, /search'e eklenen ontoloji-bazli hibrit
# arama BURAYA hic yansitilmamisti - bu tutarsizlik fark edilip
# arama_servisi.py'ye tasinarak duzeltildi.

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import WikiPage
from app.models.schemas import ChatIstegi, ChatCevabi
from app.services.arama_servisi import hibrit_arama_yap
from app.services.chat_servisi import rag_cevap_uret

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatCevabi)
async def sohbet_et(
    istek: ChatIstegi,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    # 1) Once, soruya en yakin parcalari bul - search.py ile AYNI
    #    hibrit (embedding + ontoloji) mantik.
    sonuclar_by_unit_id = await hibrit_arama_yap(db, istek.soru, istek.limit)

    # 2) Bulunan parcalarin SADECE icerik metnini cikar - chat_servisi
    #    bunu istiyor (bir onceki derste konustugumuz gibi)
    baglam_parcalari = [sonuc["icerik"] for sonuc in sonuclar_by_unit_id.values()]

    # 3) LLM'e gonder, cevap uret (bu da senkron bir cagri - Gemini
    #    API'sinin senkron surumunu kullaniyoruz, o yuzden yine
    #    thread'e gonderiyoruz)
    cevap_metni = await asyncio.to_thread(
        rag_cevap_uret, istek.soru, baglam_parcalari
    )

    # 4) Kullanicinin bilgi icin, hangi sayfalardan yararlanildigini
    #    da gosterelim - search.py'deki gibi page_id -> baslik eslemesi
    page_idler = [sonuc["page_id"] for sonuc in sonuclar_by_unit_id.values()]
    sayfa_sonucu = await db.execute(
        select(WikiPage).where(WikiPage.id.in_(page_idler))
    )
    sayfalar = sayfa_sonucu.scalars().all()
    basliklar = list(set(sayfa.title for sayfa in sayfalar))  # tekrarlari kaldir

    return ChatCevabi(
        cevap=cevap_metni,
        kullanilan_kaynaklar=basliklar,
    )
