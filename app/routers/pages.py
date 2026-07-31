"""
sayfa okuma + sayfayı "aranabilir" hale getirme

Var olan WikiPage kayitlarini OKUMA ve INDEXLEME islemlerini yapan router.
sources.py'den farki: sources.py yeni icerik EKLER, bu dosya var olani
GETIRIR/LISTELER/INDEXLER.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schemas import WikipageCevap, IndexCevabi, SayfaGrafiCevabi, GraphKavram, GraphIliski, SiniflandirmaCevabi, KategoriGuncelle
from app.services.graph_servisi import sayfa_grafini_hesapla
from app.services.classifier import sayfa_siniflandir
from app.database import veritabani_oturumu_getir
from app.models.db_models import (
    WikiPage,
    SemanticUnit,
    ConceptNode,
    ConceptRelation,
    KavramGorulme
)
from app.services.structural_parser import markdown_bol, parcalari_boyuta_gore_bol, liste_maddelerine_gore_bol, bos_parcalari_temizle
from app.embeddings.embedding_servisi import (
    parcayi_kaydet,
    parcalari_sil,
    kavram_sil,
    token_sayisi,
    en_benzer_konuyu_bul,
)

router = APIRouter(prefix="/pages", tags=["Sayfalar"])


@router.get("", response_model=list[WikipageCevap])
async def sayfalari_listele(db: AsyncSession = Depends(veritabani_oturumu_getir)):
    """
    Veritabanindaki tum sayfalari listeler.
    """
    sonuc = await db.execute(select(WikiPage))
    sayfalar = sonuc.scalars().all()
    return sayfalar


@router.get("/{sayfa_id}", response_model=WikipageCevap)
async def sayfa_getir(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Belirli BIR sayfayi id'sine gore getirir.
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    return sayfa


@router.post("/{sayfa_id}/index", response_model=IndexCevabi)
async def sayfayi_indexle(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Bir WikiPage'in icerigini parcalara boler ve her parcayi
    SemanticUnit olarak veritabanina kaydeder.

    Sayfa ZATEN indexliyse (var olan SemanticUnit'leri varsa) 409 doner -
    tekrar cagirmak, WikiPage.content'in (basliklari icermeyen, duz
    birlestirilmis metin) tekrar bolunmesine yol acar; bu da TUM
    icerigin tek bir dev "Giris" parcasina dusmesine sebep olur (PDF/
    markdown kaynaklarinda zaten upload sirasinda otomatik indexleniyor).
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    var_olan_sonuc = await db.execute(
        select(SemanticUnit.id).where(SemanticUnit.page_id == sayfa_id).limit(1)
    )
    if var_olan_sonuc.scalars().first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Bu sayfa zaten indexlenmis - tekrar indexlemek yinelenen/bozuk parcalar olusturur"
        )

    parcalar = markdown_bol(sayfa.content)

    # Icerigi BOS olan parcalari ele.
    parcalar = bos_parcalari_temizle(parcalar)

    # Bir bolum TAMAMEN bagimsiz liste maddelerinden olusuyorsa, her
    # maddeyi ayri parca yap - yoksa embedding birden fazla bagimsiz
    # gercegi "sulandirir".
    parcalar = liste_maddelerine_gore_bol(parcalar)

    # Bir baslik altindaki metin embedding modelinin token sinirini
    # asarsa sessizce kirpilir - asan parcalari kucuk alt-parcalara bol.
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi)

    yeni_unitler = []
    for sira, parca in enumerate(parcalar):
        yeni_unit = SemanticUnit(
            page_id=sayfa.id,
            baslik=parca.baslik,
            icerik=parca.icerik,
            seviye=parca.seviye,
            sira=sira,
        )
        db.add(yeni_unit)
        yeni_unitler.append(yeni_unit)

    await db.commit()

    for unit in yeni_unitler:
        await db.refresh(unit)

    await asyncio.gather(*[
        asyncio.to_thread(parcayi_kaydet, unit.id, unit.page_id, unit.icerik)
        for unit in yeni_unitler
    ])

    return IndexCevabi(
        sayfa_id=sayfa.id,
        olusturulan_parca_sayisi=len(parcalar),
    )

@router.get("/{sayfa_id}/graph", response_model=SayfaGrafiCevabi)
async def sayfa_grafini_getir(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Katman 1 (sayfa ici kavram grafigi) - bir sayfaya ait TUM
    ConceptNode'lari ve aralarindaki ConceptRelation'lari doner.
    Asil is mantigi graph_servisi.sayfa_grafini_hesapla icinde -
    bu endpoint sadece sayfanin var oldugunu dogrulayip sonucu
    API semasina (SayfaGrafiCevabi) uygun hale getiriyor.
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    nodelar, iliskiler = await sayfa_grafini_hesapla(db, sayfa_id)

    return SayfaGrafiCevabi(
        sayfa_id=sayfa_id,
        kavramlar=[
            GraphKavram(id=node.id, standart_isim=node.standart_isim, tip=node.tip)
            for node in nodelar
        ],
        iliskiler=[
            GraphIliski(
                kaynak_id=iliski.kaynak_id,
                hedef_id=iliski.hedef_id,
                iliski_tipi=iliski.iliski_tipi,
            )
            for iliski in iliskiler
        ],
    )

@router.post("/{sayfa_id}/classify", response_model=SiniflandirmaCevabi)
async def sayfayi_siniflandir(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Bir WikiPage'in icerigine bakip, hangi KONUYA/DERSE/PROJEYE ait
    oldugunu belirler ve WikiPage.kategori sutununa kaydeder. Sabit
    bir liste YOK - sistemde onceden var olan konular LLM'e gosterilir
    (tutarli isimlendirme icin), LLM ya birine eslesir ya da yeni bir
    konu onerir. LLM'in eslestirme karari, embedding benzerligiyle bir
    GUVENLIK AGI olarak dogrulanir - bkz. classifier.py ve
    en_benzer_konuyu_bul docstring'leri, LLM'in TEK BASINA capalama
    onyargisi yasadigi (listede alakasiz tek bir secenek olsa bile ona
    yapismasi) test edilerek bulundu. extract-concepts gibi MANUEL
    tetiklenir - sayfa eklenirken otomatik calismaz.
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    # Sistemde DAHA ONCE olusturulmus tum konu isimlerini topla - hem
    # LLM'e tutarli isimlendirme icin gostermek hem de LLM'in
    # eslestirme kararini dogrulamak icin. Su anki sayfayi (henuz
    # kategorisiz olabilir) ve bos degerleri disarida birakiyoruz.
    mevcut_sonuc = await db.execute(
        select(WikiPage.kategori)
        .where(WikiPage.kategori.isnot(None), WikiPage.id != sayfa_id)
        .distinct()
    )
    mevcut_konular = [satir[0] for satir in mevcut_sonuc.all()]

    # LLM cagrisi senkron calisiyor, thread'e gonderiyoruz ki event
    # loop bloklanmasin (concept_extractor.kavram_cikar ile ayni desen).
    sonuc_siniflandirma = await asyncio.to_thread(sayfa_siniflandir, sayfa.content, mevcut_konular)

    if sonuc_siniflandirma.kategori == sonuc_siniflandirma.bagimsiz_konu:
        # LLM listeden birini SECMEDI, yeni bir konu onerdi - dogrulamaya
        # gerek yok, dogrudan kullan.
        kategori = sonuc_siniflandirma.kategori
    else:
        # LLM listeden birini SECTI - bu karari, kendi bagimsiz kararina
        # (embedding benzerligiyle, TOLERANSLI bir esikle) kiyaslayarak
        # DOGRULUYORUZ. Dogrulama gecerse LLM'in secimine (mevcut
        # konunun tam yazimina) guveniyoruz; gecmezse (orn. "Gravio"
        # ile "ATLAS" gibi capalama onyargisi durumunda) LLM'in kendi
        # bagimsiz kararina donuyoruz.
        dogrulanan = await asyncio.to_thread(
            en_benzer_konuyu_bul, sonuc_siniflandirma.bagimsiz_konu, [sonuc_siniflandirma.kategori]
        )
        kategori = sonuc_siniflandirma.kategori if dogrulanan is not None else sonuc_siniflandirma.bagimsiz_konu

    sayfa.kategori = kategori
    await db.commit()

    return SiniflandirmaCevabi(sayfa_id=sayfa_id, kategori=kategori)


@router.put("/{sayfa_id}/kategori", response_model=WikipageCevap)
async def kategoriyi_guncelle(
    sayfa_id: int,
    istek: KategoriGuncelle,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Kullanicinin KENDI yazdigi bir kategoriyi dogrudan kaydeder -
    classifier.py'deki SAYFA_KATEGORILERI listesiyle SINIRLI DEGIL,
    herhangi bir metin olabilir. sayfayi_siniflandir (LLM, sabit liste)
    ile AYNI sutunu (WikiPage.kategori) gunceller ama LLM'e hic
    danismadan - kullanici LLM'in secimini ISTEDIGI GIBI ezebilir.
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    sayfa.kategori = istek.kategori
    await db.commit()
    await db.refresh(sayfa)

    return sayfa


@router.delete("/{sayfa_id}")
async def sayfayi_sil(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Bir WikiPage'i VE ona bagli tum verileri siler:
    - Source ve SemanticUnit'ler otomatik gider (db_models.py'deki
      cascade="all, delete-orphan" sayesinde, WikiPage silinince).
    - Chroma'daki embedding'ler elle silinir (cascade Chroma'yi kapsamiyor).
    - ConceptNode'lar icin ozel bir kural var: eger bir kavram SADECE bu
      sayfada gorulmusse (baska hicbir sayfada gorulmemisse) o kavram da
      tamamen silinir. Ama baska bir sayfada da goruluyorsa (orn. birden
      fazla dosyada gecen "Kaan Aslan" gibi), ConceptNode KALIR - sadece
      bu sayfayla ilgili KavramGorulme kaydi silinir.
    """
    sonuc = await db.execute(select(WikiPage).where(WikiPage.id == sayfa_id))
    sayfa = sonuc.scalars().first()

    if sayfa is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadi")

    # 1) Bu sayfaya ait SemanticUnit id'lerini topla - hem Chroma
    #    silme islemi hem de KavramGorulme sorgusu icin lazim.
    unit_sonucu = await db.execute(
        select(SemanticUnit.id).where(SemanticUnit.page_id == sayfa_id)
    )
    unit_idler = [satir[0] for satir in unit_sonucu.all()]

    if unit_idler:
        # 2) Bu unit'lerde GORULEN tum ConceptNode id'lerini bul (tekrarsiz).
        gorulme_sonucu = await db.execute(
            select(KavramGorulme.concept_node_id)
            .where(KavramGorulme.unit_id.in_(unit_idler))
            .distinct()
        )
        etkilenen_node_idler = [satir[0] for satir in gorulme_sonucu.all()]

        # Komple silinen ConceptNode'larin id'lerini topluyoruz - asagida
        # Chroma'daki concept_names koleksiyonundan da silmek icin lazim.
        silinen_node_idler = []

        for node_id in etkilenen_node_idler:
            # 3) Bu kavram, silinecek unit'ler DISINDA baska bir unit'te
            #    de goruluyor mu? Yani baska bir sayfada da geciyor mu?
            baska_gorulme_sonucu = await db.execute(
                select(KavramGorulme).where(
                    KavramGorulme.concept_node_id == node_id,
                    KavramGorulme.unit_id.notin_(unit_idler),
                )
            )
            baska_yerde_de_var = baska_gorulme_sonucu.scalars().first()

            if baska_yerde_de_var is None:
                # Sadece bu sayfada gorulmus - ConceptNode'u komple sil.
                # Once ona bagli ConceptRelation'lari silmemiz lazim,
                # yoksa foreign key hatasi aliriz (kaynak_id/hedef_id
                # bu node'a isaret ediyor olabilir).
                iliski_sonucu = await db.execute(
                    select(ConceptRelation).where(
                        (ConceptRelation.kaynak_id == node_id) |
                        (ConceptRelation.hedef_id == node_id)
                    )
                )
                for iliski in iliski_sonucu.scalars().all():
                    await db.delete(iliski)

                # KavramGorulme kayitlarini sil (zaten hepsi bu sayfaya ait,
                # cunku "baska yerde yok" demek biraz once dogruladik).
                tum_gorulme_sonucu = await db.execute(
                    select(KavramGorulme).where(KavramGorulme.concept_node_id == node_id)
                )
                for gorulme in tum_gorulme_sonucu.scalars().all():
                    await db.delete(gorulme)

                # ConceptNode'un kendisini sil - cascade sayesinde
                # KavramTakmaAdi kayitlari da otomatik gidecek.
                node_sonucu = await db.execute(
                    select(ConceptNode).where(ConceptNode.id == node_id)
                )
                node = node_sonucu.scalars().first()
                if node is not None:
                    await db.delete(node)
                    silinen_node_idler.append(node_id)
            else:
                # Baska sayfada da goruluyor - sadece BU sayfaya ait
                # KavramGorulme kayitlarini sil, node'a dokunma.
                bu_sayfadaki_gorulme_sonucu = await db.execute(
                    select(KavramGorulme).where(
                        KavramGorulme.concept_node_id == node_id,
                        KavramGorulme.unit_id.in_(unit_idler),
                    )
                )
                for gorulme in bu_sayfadaki_gorulme_sonucu.scalars().all():
                    await db.delete(gorulme)

        # 4) Chroma'daki vektorleri sil (senkron cagri, thread'e atiyoruz).
        await asyncio.to_thread(parcalari_sil, unit_idler)

        # 5) Komple silinen ConceptNode'larin Chroma'daki concept_names
        #    kaydini da sil - yoksa artik SQLde olmayan bir node, embedding
        #    aramasinda hala "eslesme" olarak cikmaya devam eder (hayalet kayit).
        if silinen_node_idler:
            await asyncio.to_thread(kavram_sil, silinen_node_idler)

    # 5) Son olarak WikiPage'i sil - cascade sayesinde Source ve
    #    SemanticUnit satirlari otomatik silinecek.
    await db.delete(sayfa)
    await db.commit()

    return {"silindi": True, "sayfa_id": sayfa_id}