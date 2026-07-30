"""
graph_servisi.py

Katman 2 (global graph) icin : iki WikiPage'in ORTAK bir
kavrami paylastigini tespit edip SayfaBaglantisi tablosuna kaydeder.

ONEMLI KURAL: bu fonksiyon anlik hesaplama yapmaz, DELETE + yeniden
INSERT mantigiyla calisir - cagrildiginda SayfaBaglantisi tablosunu
tamamen temizleyip sifirdan yeniden kurar. Boylece kismi guncelleme
mantiginin (hangi baglanti eklendi, hangisi silinmeli, race condition
riski var mi) getirdigi karmasiklikdan kaciniyoruz.
"""

from itertools import combinations

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    ConceptNode,
    ConceptRelation,
    KavramGorulme,
    SemanticUnit,
    SayfaBaglantisi,
    WikiPage
)
from sqlalchemy import select, delete, and_

async def global_graf_yeniden_hesapla(db: AsyncSession) -> int:
    """
    Tum SayfaBaglantisi kayitlarini siler, sonra her ConceptNode icin
    "bu kavram hangi sayfalarda gorulmus" bilgisini cikarip, ayni
    kavrami paylasan HER SAYFA CIFTI icin yeni bir SayfaBaglantisi
    satiri olusturur.

    Donen deger: olusturulan yeni baglanti sayisi.
    """

    # 1) Once eski tabloyu tamamen temizle - kismi guncelleme yok,
    #    her seferinde sifirdan kuruyoruz.
    await db.execute(delete(SayfaBaglantisi))

    # 2) Butun ConceptNode'lari tek tek geziyoruz. Her kavram icin,
    #    o kavramin gorulduğu unit'ler uzerinden HANGI SAYFALARDA
    #    goruldugunu buluyoruz.
    node_sonucu = await db.execute(select(ConceptNode))
    nodelar = node_sonucu.scalars().all()

    toplam_baglanti = 0

    for node in nodelar:
        # Bu kavramin goruldugu unit_id'leri bul (KavramGorulme
        #     uzerinden).
        gorulme_sonucu = await db.execute(
            select(KavramGorulme.unit_id).where(
                KavramGorulme.concept_node_id == node.id
            )
        )
        unit_idler = [row[0] for row in gorulme_sonucu.all()]

        if not unit_idler:
            continue

        # Bu unit'lerin HANGI page_id'lere ait oldugunu bul -
        #     tekrarsiz sayfa id kumesi olusturuyoruz cunku ayni
        #     sayfadan birden fazla unit ayni kavrami gormus olabilir.
        sayfa_sonucu = await db.execute(
            select(SemanticUnit.page_id)
            .where(SemanticUnit.id.in_(unit_idler))
            .distinct()
        )
        sayfa_idleri = sorted(set(row[0] for row in sayfa_sonucu.all()))

        # Bu kavram sadece TEK bir sayfada gorulmusse, "sayfalar
        #     arasi" bir baglanti kurulamaz - atla.
        if len(sayfa_idleri) < 2:
            continue

        # Bu kavrami paylasan sayfalarin HER IKILISI icin bir
        #     SayfaBaglantisi satiri olustur. combinations kullanarak
        #     (1,2), (1,3), (2,3) gibi tekrarsiz ciftler uretiyoruz -
        #     (2,1) gibi ayna ciftleri TEKRAR eklemek istemiyoruz.
        for sayfa_id_1, sayfa_id_2 in combinations(sayfa_idleri, 2):
            db.add(SayfaBaglantisi(
                sayfa_id_1=sayfa_id_1,
                sayfa_id_2=sayfa_id_2,
                ortak_kavram_ismi=node.standart_isim,
            ))
            toplam_baglanti += 1

    await db.commit()

    return toplam_baglanti



async def sayfa_grafini_hesapla(db: AsyncSession, sayfa_id: int) -> tuple[list[ConceptNode], list[ConceptRelation]]:
    """
    Katman 1 (sayfa ici) graph icin is mantigi: bir sayfaya ait
    ConceptNode ve ConceptRelation'lari bulur.

    ConceptNode ve ConceptRelation'in dogrudan page_id kolonu yok -
    baglanti SemanticUnit -> KavramGorulme -> ConceptNode zinciri
    uzerinden kuruluyor. Bu yuzden once bu sayfaya ait unit id'lerini,
    sonra o unit'lerde gorulen kavram id'lerini buluyoruz.

    Donen deger: (nodelar, iliskiler) tuple'i - sayfa var ama hic
    kavram yoksa ikisi de bos liste doner.
    """

    # 1) Bu sayfaya ait SemanticUnit id'lerini bul
    unit_sonucu = await db.execute(
        select(SemanticUnit.id).where(SemanticUnit.page_id == sayfa_id)
    )
    unit_idler = [row[0] for row in unit_sonucu.all()]

    if not unit_idler:
        return [], []

    # 2) Bu unit'lerde GORULEN ConceptNode id'lerini bul (tekrarsiz)
    gorulme_sonucu = await db.execute(
        select(KavramGorulme.concept_node_id)
        .where(KavramGorulme.unit_id.in_(unit_idler))
        .distinct()
    )
    kavram_idler = [row[0] for row in gorulme_sonucu.all()]

    if not kavram_idler:
        return [], []

    # 3) Bu id'lere sahip ConceptNode'lari getir
    node_sonucu = await db.execute(
        select(ConceptNode).where(ConceptNode.id.in_(kavram_idler))
    )
    nodelar = node_sonucu.scalars().all()

    # 4) Iliskileri getir - HEM kaynak HEM hedef bu sayfanin
    #    kavramlari arasinda olmali (disari sarkan iliskileri dahil etme)
    iliski_sonucu = await db.execute(
        select(ConceptRelation).where(
            and_(
                ConceptRelation.kaynak_id.in_(kavram_idler),
                ConceptRelation.hedef_id.in_(kavram_idler),
            )
        )
    )
    iliskiler = iliski_sonucu.scalars().all()

    return nodelar, iliskiler


async def global_grafi_getir(db: AsyncSession) -> tuple[list[WikiPage], list[SayfaBaglantisi]]:
    """
    Katman 2 (global graph) icin kayitli veriyi okur. Anlik hesaplama
    yapmaz - sadece SayfaBaglantisi tablosunda onceden hesaplanmis
    (global_graf_yeniden_hesapla ile kurulmus) veriyi getirir.

    Donen deger: (sayfalar, baglantilar) tuple'i.
    """

    # 1) Tum baglantilari getir
    baglanti_sonucu = await db.execute(select(SayfaBaglantisi))
    baglantilar = baglanti_sonucu.scalars().all()

    if not baglantilar:
        return [], []

    # 2) Baglantilarda gecen TUM sayfa id'lerini topla (tekrarsiz) -
    #    sayfa_id_1 ve sayfa_id_2 sutunlarinin ikisinden de.
    sayfa_idleri = set()
    for baglanti in baglantilar:
        sayfa_idleri.add(baglanti.sayfa_id_1)
        sayfa_idleri.add(baglanti.sayfa_id_2)

    # 3) Bu id'lere sahip WikiPage'leri tek sorguyla getir
    sayfa_sonucu = await db.execute(
        select(WikiPage).where(WikiPage.id.in_(sayfa_idleri))
    )
    sayfalar = sayfa_sonucu.scalars().all()

    return sayfalar, baglantilar