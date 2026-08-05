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
    SayfaIliskisi,
    WikiPage
)
from sqlalchemy import select, delete, and_

async def global_graf_yeniden_hesapla(db: AsyncSession) -> tuple[int, int]:
    """
    Tum SayfaBaglantisi VE SayfaIliskisi kayitlarini siler, sonra
    ikisini de SIFIRDAN yeniden kurar:
    - SayfaBaglantisi: ayni kavrami paylasan HER SAYFA CIFTI (yonsuz,
      tipsiz - "bu iki sayfa X kavramindan geciyor").
    - SayfaIliskisi: ConceptRelation'a dayali, YONLU ve TIPLI sayfa
      baglantilari - "A sayfasindaki bir kavram, B sayfasindaki bir
      kavramin ONKOSULU" gibi. Boylece global graf artik sadece
      "ortak kavram" degil, kavramlar ARASINDAKI iliskiyi de sayfa
      seviyesine tasiyor.

    Donen deger: (olusturulan_baglanti_sayisi, olusturulan_iliski_sayisi).
    """

    # 1) Once eski tablolari tamamen temizle - kismi guncelleme yok,
    #    her seferinde sifirdan kuruyoruz.
    await db.execute(delete(SayfaBaglantisi))
    await db.execute(delete(SayfaIliskisi))

    # 2) Butun ConceptNode'lari tek tek geziyoruz. Her kavram icin,
    #    o kavramin gorulduğu unit'ler uzerinden HANGI SAYFALARDA
    #    goruldugunu buluyoruz - bu harita, hem SayfaBaglantisi hem
    #    SayfaIliskisi hesabinda TEKRAR kullaniliyor.
    node_sonucu = await db.execute(select(ConceptNode))
    nodelar = node_sonucu.scalars().all()

    node_id_to_sayfalar: dict[int, list[int]] = {}
    node_id_to_isim: dict[int, str] = {}

    for node in nodelar:
        node_id_to_isim[node.id] = node.standart_isim

        gorulme_sonucu = await db.execute(
            select(KavramGorulme.unit_id).where(
                KavramGorulme.concept_node_id == node.id
            )
        )
        unit_idler = [row[0] for row in gorulme_sonucu.all()]

        if not unit_idler:
            node_id_to_sayfalar[node.id] = []
            continue

        sayfa_sonucu = await db.execute(
            select(SemanticUnit.page_id)
            .where(SemanticUnit.id.in_(unit_idler))
            .distinct()
        )
        node_id_to_sayfalar[node.id] = sorted(set(row[0] for row in sayfa_sonucu.all()))

    # 3) SayfaBaglantisi: ayni kavrami paylasan sayfa ciftleri (mevcut mantik)
    toplam_baglanti = 0

    for node in nodelar:
        sayfa_idleri = node_id_to_sayfalar[node.id]

        # Bu kavram sadece TEK bir sayfada gorulmusse, "sayfalar
        # arasi" bir baglanti kurulamaz - atla.
        if len(sayfa_idleri) < 2:
            continue

        # Bu kavrami paylasan sayfalarin HER IKILISI icin bir
        # SayfaBaglantisi satiri olustur. combinations kullanarak
        # (1,2), (1,3), (2,3) gibi tekrarsiz ciftler uretiyoruz -
        # (2,1) gibi ayna ciftleri TEKRAR eklemek istemiyoruz.
        for sayfa_id_1, sayfa_id_2 in combinations(sayfa_idleri, 2):
            db.add(SayfaBaglantisi(
                sayfa_id_1=sayfa_id_1,
                sayfa_id_2=sayfa_id_2,
                ortak_kavram_ismi=node.standart_isim,
            ))
            toplam_baglanti += 1

    # 4) SayfaIliskisi: ConceptRelation'a dayali YONLU/TIPLI sayfa
    #    baglantilari. Her iliski icin, kaynak kavramin GOZUKTUGU her
    #    sayfadan, hedef kavramin GOZUKTUGU her sayfaya bir baglanti
    #    kuruyoruz - iki kavram FARKLI sayfalarda gorulduyse bu, o
    #    sayfalarin da (iliskinin yonunde) baglantili oldugu anlamina
    #    gelir.
    iliski_sonucu = await db.execute(select(ConceptRelation))
    iliskiler = iliski_sonucu.scalars().all()

    toplam_sayfa_iliskisi = 0

    # Ayni (kaynak_sayfa, hedef_sayfa, iliski_tipi) uc'lusunu birden
    # fazla kez EKLEMEMEK icin - farkli kavram ciftleri ayni sayfa
    # ciftine dusebilir (orn. iki sayfa birden fazla ONKOSUL iliskisi
    # paylasabilir), boyle tekrarlari tek bir satirda birlestiriyoruz.
    eklenen_ucluler: set[tuple[int, int, str]] = set()

    for iliski in iliskiler:
        kaynak_sayfalari = node_id_to_sayfalar.get(iliski.kaynak_id, [])
        hedef_sayfalari = node_id_to_sayfalar.get(iliski.hedef_id, [])

        for kaynak_sayfa_id in kaynak_sayfalari:
            for hedef_sayfa_id in hedef_sayfalari:
                if kaynak_sayfa_id == hedef_sayfa_id:
                    continue  # ayni sayfa icindeki iliski, sayfalar-arasi degil

                anahtar = (kaynak_sayfa_id, hedef_sayfa_id, iliski.iliski_tipi)
                if anahtar in eklenen_ucluler:
                    continue
                eklenen_ucluler.add(anahtar)

                db.add(SayfaIliskisi(
                    kaynak_sayfa_id=kaynak_sayfa_id,
                    hedef_sayfa_id=hedef_sayfa_id,
                    iliski_tipi=iliski.iliski_tipi,
                    kaynak_kavram_ismi=node_id_to_isim.get(iliski.kaynak_id, "?"),
                    hedef_kavram_ismi=node_id_to_isim.get(iliski.hedef_id, "?"),
                ))
                toplam_sayfa_iliskisi += 1

    await db.commit()

    return toplam_baglanti, toplam_sayfa_iliskisi



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


async def global_grafi_getir(db: AsyncSession) -> tuple[list[WikiPage], list[SayfaBaglantisi], list[SayfaIliskisi]]:
    """
    Katman 2 (global graph) icin kayitli veriyi okur. Anlik hesaplama
    yapmaz - sadece SayfaBaglantisi VE SayfaIliskisi tablolarinda
    onceden hesaplanmis (global_graf_yeniden_hesapla ile kurulmus)
    veriyi getirir.

    Donen deger: (sayfalar, baglantilar, iliskiler) tuple'i.
    """

    # 1) Tum baglantilari VE iliskileri getir
    baglanti_sonucu = await db.execute(select(SayfaBaglantisi))
    baglantilar = baglanti_sonucu.scalars().all()

    iliski_sonucu = await db.execute(select(SayfaIliskisi))
    iliskiler = iliski_sonucu.scalars().all()

    if not baglantilar and not iliskiler:
        return [], [], []

    # 2) Baglanti ve iliskilerde gecen TUM sayfa id'lerini topla
    #    (tekrarsiz).
    sayfa_idleri = set()
    for baglanti in baglantilar:
        sayfa_idleri.add(baglanti.sayfa_id_1)
        sayfa_idleri.add(baglanti.sayfa_id_2)
    for iliski in iliskiler:
        sayfa_idleri.add(iliski.kaynak_sayfa_id)
        sayfa_idleri.add(iliski.hedef_sayfa_id)

    # 3) Bu id'lere sahip WikiPage'leri tek sorguyla getir
    sayfa_sonucu = await db.execute(
        select(WikiPage).where(WikiPage.id.in_(sayfa_idleri))
    )
    sayfalar = sayfa_sonucu.scalars().all()

    return sayfalar, baglantilar, iliskiler