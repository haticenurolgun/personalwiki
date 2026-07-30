
# chat.py

# Kullanicinin soru sordugu, RAG akisinin TAMAMININ calistigi endpoint.
# Akis: soru -> embedding aramasi -> bulunan parcalar -> LLM'e gonder
#       -> LLM'in ürettigi cevap kullaniciya donuyor.

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import WikiPage
from app.models.schemas import ChatIstegi, ChatCevabi
from app.embeddings.embedding_servisi import benzer_parcalari_bul
from app.services.chat_servisi import rag_cevap_uret

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatCevabi)
async def sohbet_et(
    istek: ChatIstegi,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    # 1) Once, soruya en yakin parcalari bul (search.py'deki mantigin
    #    ayni siyle) - senkron fonksiyon oldugu icin thread'e gonderiyoruz
    ham_sonuclar = await asyncio.to_thread(
        benzer_parcalari_bul, istek.soru, istek.limit
    )

    # 2) Bulunan parcalarin SADECE icerik metnini cikar - chat_servisi
    #    bunu istiyor (bir onceki derste konustugumuz gibi)
    baglam_parcalari = [sonuc["icerik"] for sonuc in ham_sonuclar]

    # 3) LLM'e gonder, cevap uret (bu da senkron bir cagri - Gemini
    #    API'sinin senkron surumunu kullaniyoruz, o yuzden yine
    #    thread'e gonderiyoruz)
    cevap_metni = await asyncio.to_thread(
        rag_cevap_uret, istek.soru, baglam_parcalari
    )

    # 4) Kullanicinin bilgi icin, hangi sayfalardan yararlanildigini
    #    da gosterelim - search.py'deki gibi page_id -> baslik eslemesi
    page_idler = [sonuc["page_id"] for sonuc in ham_sonuclar]
    sayfa_sonucu = await db.execute(
        select(WikiPage).where(WikiPage.id.in_(page_idler))
    )
    sayfalar = sayfa_sonucu.scalars().all()
    basliklar = list(set(sayfa.title for sayfa in sayfalar))  # tekrarlari kaldir

    return ChatCevabi(
        cevap=cevap_metni,
        kullanilan_kaynaklar=basliklar,
    )