""" 
sources.py:
Yeni icerik EKLEME islemlerini yapan router.
"""
import os
import uuid
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import veritabani_oturumu_getir
from app.models.db_models import WikiPage,Source,SemanticUnit
from app.models.schemas import MarkdownEkle, WikipageCevap
from app.embeddings.embedding_servisi import parcayi_kaydet, token_sayisi
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.connectors.pdf_connector import pdf_metnini_cikar
from app.connectors.markdown_connector import markdown_metnini_cikar
from app.services.structural_parser import parcalari_boyuta_gore_bol, liste_maddelerine_gore_bol, bos_parcalari_temizle
# prefix="/sources" -> bu router'daki her endpoint otomatik olarak
# /sources ile baslar. tags=[...] ise sadece /docs sayfasinda
# endpoint'lerin hangi baslik altinda gruplanacagini belirler.

router = APIRouter(prefix="/sources", tags=["Kaynaklar"])

@router.post("/markdown",response_model=WikipageCevap)
async def markdown_ekle(istek: MarkdownEkle, db :AsyncSession = Depends(veritabani_oturumu_getir)):
    """
    Kullanicinin dogrudan yazdigi markdown metnini yeni bir wiki page
    olarak kaydeder. pdf_ekle ile AYNI mantik: TEK ADIMDA hem WikiPage +
    Source (type="markdown") olusturur HEM DE her parcayi bir
    SemanticUnit olarak kaydedip embedding'e yollar - ayri bir /index
    cagrisi gerekmez.
    """

    # 1) Icerigi baslik/bolum bazinda parcalara ayir - pdf_ekle'deki
    #    pdf_metnini_cikar'in dosyasiz karsiligi.
    parcalar = markdown_metnini_cikar(istek.content)

    # 1.35) Icerigi BOS olan parcalari ele - orn. bir baslik hemen
    #    ardindan baska bir baslik geliyorsa (aralarinda govde metni
    #    yoksa) olusan bos parcalar. Bos metnin embedding'i anlamsizdir.
    parcalar = bos_parcalari_temizle(parcalar)

    # 1.4) Bir bolum TAMAMEN bagimsiz liste maddelerinden olusuyorsa
    #    (orn. bir sinav takvimi), her maddeyi ayri parca yap - yoksa
    #    embedding birden fazla bagimsiz gercegi "sulandirir".
    parcalar = liste_maddelerine_gore_bol(parcalar)

    # 1.5) Bir baslik altindaki metin embedding modelinin token sinirini
    #    asarsa sessizce kirpilir - asan parcalari kucuk alt-parcalara bol.
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi)

    # 2) WikiPage'i olustur.
    yeni_sayfa = WikiPage(title=istek.title, content=istek.content, tags=istek.tags)
    db.add(yeni_sayfa)
    await db.flush()
    await db.refresh(yeni_sayfa)

    # 3) Source kaydi - bu sayfanin dogrudan yapistirilmis markdown
    #    metninden geldigini iz olarak tutuyoruz. url/file_path yok,
    #    cunku bir dosya/web sayfasi degil.
    yeni_kaynak = Source(
        page_id=yeni_sayfa.id,
        type="markdown",
    )
    db.add(yeni_kaynak)

    # 4) Her parcayi bir SemanticUnit olarak kaydet.
    yeni_unitler = []
    for sira, parca in enumerate(parcalar):
        yeni_unit = SemanticUnit(
            page_id=yeni_sayfa.id,
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

    # 5) Her unit'i embedding'e gonder - pdf_ekle ile ayni paralel
    #    calisma mantigi (asyncio.gather + to_thread).
    await asyncio.gather(*[
        asyncio.to_thread(parcayi_kaydet, unit.id, unit.page_id, unit.icerik)
        for unit in yeni_unitler
    ])

    await db.refresh(yeni_sayfa)

    return yeni_sayfa

# PDF dosyalarinin fiziksel olarak saklanacagi klasor
YUKLEME_KLASORU = "app/uploads"


@router.post("/pdf", response_model=WikipageCevap)
async def pdf_ekle(
    dosya: UploadFile = File(...),
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Kullanicinin yukledigi bir PDF dosyasini diske kaydeder, sayfa
    sayfa metnini cikarir ve TEK ADIMDA hem WikiPage + Source
    (type="pdf") olusturur HEM DE her PDF sayfasini bir SemanticUnit
    olarak kaydedip embedding'e yollar - markdown_ekle ile AYNI mantik,
    index adimi ayri bir cagri gerektirmez.

    Simdilik title, dosyanin ADI olarak kullaniliyor.
    """

    # 1) Sadece .pdf uzantili dosyalara izin ver
    if not dosya.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece .pdf dosyalari kabul edilir")

    # 2) Klasor yoksa olustur
    os.makedirs(YUKLEME_KLASORU, exist_ok=True)

    # 3) Dosyayi benzersiz bir isimle diske kaydet - iki kullanici
    #    ayni isimde dosya yukleyince CAKISMASIN diye uuid kullaniyoruz.
    benzersiz_dosya_adi = f"{uuid.uuid4().hex}.pdf"
    dosya_yolu = os.path.join(YUKLEME_KLASORU, benzersiz_dosya_adi)

    icerik_baytlari = await dosya.read()
    with open(dosya_yolu, "wb") as hedef_dosya:
        hedef_dosya.write(icerik_baytlari)

    # 4) PDF'i SAYFA SAYFA parcala (pdfplumber senkron calisiyor,
    #    thread'e gonderiyoruz ki event loop bloklanmasin)
    parcalar = await asyncio.to_thread(pdf_metnini_cikar, dosya_yolu)

    if not parcalar:
        raise HTTPException(
            status_code=422,
            detail="PDF'ten metin cikarilamadi - dosya bos veya sadece goruntuden olusuyor olabilir (OCR gerektirebilir)"
        )

    # 4.35) Icerigi BOS olan parcalari ele - bkz. markdown_ekle'deki
    #    ayni adim, PDF'lerde de (basliklar arasi bosluk) yasaniyor.
    parcalar = bos_parcalari_temizle(parcalar)

    # 4.4) Bir bolum TAMAMEN bagimsiz liste maddelerinden olusuyorsa,
    #    her maddeyi ayri parca yap - yoksa embedding birden fazla
    #    bagimsiz gercegi "sulandirir".
    parcalar = liste_maddelerine_gore_bol(parcalar)

    # 4.5) Bir baslik altindaki metin embedding modelinin token sinirini
    #    asarsa sessizce kirpilir - asan parcalari kucuk alt-parcalara bol.
    parcalar = parcalari_boyuta_gore_bol(parcalar, token_sayisi)

    # 5) WikiPage.content icin TUM sayfalarin metnini birlestiriyoruz -
    #    boylece sayfa hala "tam metnine" sahip oluyor, sadece
    #    SemanticUnit'lere bolunme sekli farkli.
    tam_metin = "\n\n".join(parca.icerik for parca in parcalar)

    yeni_sayfa = WikiPage(title=dosya.filename, content=tam_metin, tags=None)
    db.add(yeni_sayfa)
    await db.flush()
    await db.refresh(yeni_sayfa)

    # 6) Source kaydi - bu sayfanin bir PDF'ten geldigini ve fiziksel
    #    dosya yolunu iz olarak tutuyoruz.
    yeni_kaynak = Source(
        page_id=yeni_sayfa.id,
        type="pdf",
        file_path=dosya_yolu,
    )
    db.add(yeni_kaynak)

    # 7) Her PDF sayfasini bir SemanticUnit olarak kaydet - pages.py'deki
    #    sayfayi_indexle ile AYNI mantik, sadece parcalar buradan geliyor.
    yeni_unitler = []
    for sira, parca in enumerate(parcalar):
        yeni_unit = SemanticUnit(
            page_id=yeni_sayfa.id,
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

    # 8) Her unit'i embedding'e gonder - pages.py'deki index adimindaki
    #    ayni paralel calisma mantigi (asyncio.gather + to_thread)
    await asyncio.gather(*[
        asyncio.to_thread(parcayi_kaydet, unit.id, unit.page_id, unit.icerik)
        for unit in yeni_unitler
    ])

    await db.refresh(yeni_sayfa)

    return yeni_sayfa