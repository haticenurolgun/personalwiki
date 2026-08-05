"""
kavramlar.py

Kavram (ConceptNode) MERKEZLI gezinme icin router - "bu kavram nerede
geciyor, neyle iliskili" sorusuna cevap verir. concepts.py'den FARKLI:
o dosya bir SAYFANIN kavram cikarma islemini yonetir (POST /pages/{id}
/extract-concepts), bu dosya ise VAR OLAN kavramlari LISTELEME ve
TEK BIR kavramin DETAYINI getirme ile ilgilenir - hicbir yazma islemi
YAPMAZ.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import (
    ConceptNode,
    ConceptRelation,
    KavramGorulme,
    KavramTakmaAdi,
    SemanticUnit,
    WikiPage,
)
from app.models.schemas import (
    KavramOzet,
    KavramDetayCevabi,
    KavramGorulduguSayfa,
    IliskiliKavram,
)

router = APIRouter(prefix="/concepts", tags=["Kavramlar"])


@router.get("", response_model=list[KavramOzet])
async def kavramlari_listele(db: AsyncSession = Depends(veritabani_oturumu_getir)):
    """
    Veritabanindaki TUM kavramlari (id, standart_isim, tip), isme gore
    alfabetik sirali dondurur - kavram-bazli gezinme ekranindaki
    aranabilir/secilebilir liste icin.
    """
    sonuc = await db.execute(select(ConceptNode).order_by(ConceptNode.standart_isim))
    return sonuc.scalars().all()


@router.get("/{kavram_id}", response_model=KavramDetayCevabi)
async def kavram_detayini_getir(
    kavram_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Bir kavramin TAM detayini getirir: temel bilgisi, takma adlari,
    goruldugu TUM sayfalar/parcalar (KavramGorulme uzerinden), ve
    ConceptRelation uzerinden (hem GIDEN hem GELEN yonde) iliskili
    oldugu diger kavramlar.
    """
    sonuc = await db.execute(select(ConceptNode).where(ConceptNode.id == kavram_id))
    kavram = sonuc.scalars().first()

    if kavram is None:
        raise HTTPException(status_code=404, detail="Kavram bulunamadi")

    takma_sonucu = await db.execute(
        select(KavramTakmaAdi.takma_ad).where(KavramTakmaAdi.concept_node_id == kavram_id)
    )
    takma_adlar = [row[0] for row in takma_sonucu.all()]

    # Bu kavramin goruldugu TUM unit'ler + ait olduklari sayfa basligi -
    # tek sorguda JOIN ile.
    gorulme_sonucu = await db.execute(
        select(SemanticUnit, WikiPage.title)
        .join(KavramGorulme, KavramGorulme.unit_id == SemanticUnit.id)
        .join(WikiPage, WikiPage.id == SemanticUnit.page_id)
        .where(KavramGorulme.concept_node_id == kavram_id)
    )
    goruldugu_sayfalar = [
        KavramGorulduguSayfa(
            unit_id=unit.id,
            page_id=unit.page_id,
            sayfa_basligi=sayfa_basligi,
            icerik=unit.icerik,
        )
        for unit, sayfa_basligi in gorulme_sonucu.all()
    ]

    # Iliskili kavramlar - GIDEN yon (bu kavram -[tip]-> baskasi).
    giden_sonucu = await db.execute(
        select(ConceptRelation.iliski_tipi, ConceptNode)
        .join(ConceptNode, ConceptNode.id == ConceptRelation.hedef_id)
        .where(ConceptRelation.kaynak_id == kavram_id)
    )
    iliskili_kavramlar = [
        IliskiliKavram(
            concept_id=hedef.id,
            standart_isim=hedef.standart_isim,
            tip=hedef.tip,
            iliski_tipi=iliski_tipi,
            yon="giden",
        )
        for iliski_tipi, hedef in giden_sonucu.all()
    ]

    # Iliskili kavramlar - GELEN yon (baskasi -[tip]-> bu kavram).
    gelen_sonucu = await db.execute(
        select(ConceptRelation.iliski_tipi, ConceptNode)
        .join(ConceptNode, ConceptNode.id == ConceptRelation.kaynak_id)
        .where(ConceptRelation.hedef_id == kavram_id)
    )
    iliskili_kavramlar += [
        IliskiliKavram(
            concept_id=kaynak.id,
            standart_isim=kaynak.standart_isim,
            tip=kaynak.tip,
            iliski_tipi=iliski_tipi,
            yon="gelen",
        )
        for iliski_tipi, kaynak in gelen_sonucu.all()
    ]

    return KavramDetayCevabi(
        id=kavram.id,
        standart_isim=kavram.standart_isim,
        tip=kavram.tip,
        takma_adlar=takma_adlar,
        goruldugu_sayfalar=goruldugu_sayfalar,
        iliskili_kavramlar=iliskili_kavramlar,
    )
