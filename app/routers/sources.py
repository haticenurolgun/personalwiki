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
from app.embeddings.embedding_servisi import parcayi_kaydet
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.connectors.pdf_connector import pdf_metnini_cikar
from app.connectors.markdown_connector import markdown_metnini_cikar
from app.services.chunking_secici import yontem_sec
from app.routers.pages import siniflandirmayi_uygula
from app.routers.concepts import kavramlari_uygula
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

    # 1) Ham metni al, sonra ICERIK TURUNE (duz metin/liste agirlikli/
    #    zayif basliklandirilmis/karisik) gore EN UYGUN chunking
    #    yontemini SEC ve calistir - bkz. chunking_secici.py. Secim
    #    "semantik" yontemi secerse embedding cagrisi icerebilir, bu
    #    yuzden thread'e gonderiyoruz ki event loop bloklanmasin.
    ham_metin = markdown_metnini_cikar(istek.content)
    yontem_adi, parcalar = await asyncio.to_thread(yontem_sec, ham_metin)

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

    # 6) Siniflandirma VE kavram cikarma artik MANUEL butonlar degil,
    #    yukleme aninda OTOMATIK calisiyor - siniflandirmayi_uygula
    #    (pages.py) ve kavramlari_uygula (concepts.py) ile AYNI
    #    fonksiyonlar, manuel /classify ve /extract-concepts route'lari
    #    da bunlari kullaniyor. Ikisi de commit ETMIYOR, tek seferde
    #    asagida commit ediyoruz.
    await siniflandirmayi_uygula(db, yeni_sayfa)
    await kavramlari_uygula(db, yeni_unitler)
    await db.commit()

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
    Kullanicinin yukledigi bir PDF dosyasini diske kaydeder, metnini
    cikarir ve TEK ADIMDA hem WikiPage + Source (type="pdf") olusturur
    HEM DE en uygun chunking yontemiyle parcalayip her parcayi bir
    SemanticUnit olarak kaydedip embedding'e yollar - markdown_ekle
    ile AYNI mantik, index adimi ayri bir cagri gerektirmez.

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

    # 4) PDF'i ham markdown metnine cevir (pymupdf4llm senkron
    #    calisiyor, thread'e gonderiyoruz ki event loop bloklanmasin)
    ham_metin = await asyncio.to_thread(pdf_metnini_cikar, dosya_yolu)

    if not ham_metin:
        raise HTTPException(
            status_code=422,
            detail="PDF'ten metin cikarilamadi - dosya bos veya sadece goruntuden olusuyor olabilir (OCR gerektirebilir)"
        )

    # 5) ICERIK TURUNE gore EN UYGUN chunking yontemini SEC ve
    #    calistir - bkz. chunking_secici.py. PDF'ler genelde zayif
    #    basliklandirilmis oldugu icin cogunlukla overlap_recursive
    #    secilir, ama karar HER ZAMAN icerige bakarak veriliyor.
    yontem_adi, parcalar = await asyncio.to_thread(yontem_sec, ham_metin)

    # 6) WikiPage.content icin PDF'in ham markdown metnini saklıyoruz -
    #    boylece sayfa hala "tam metnine" sahip oluyor, sadece
    #    SemanticUnit'lere bolunme sekli farkli.
    yeni_sayfa = WikiPage(title=dosya.filename, content=ham_metin, tags=None)
    db.add(yeni_sayfa)
    await db.flush()
    await db.refresh(yeni_sayfa)

    # 7) Source kaydi - bu sayfanin bir PDF'ten geldigini ve fiziksel
    #    dosya yolunu iz olarak tutuyoruz.
    yeni_kaynak = Source(
        page_id=yeni_sayfa.id,
        type="pdf",
        file_path=dosya_yolu,
    )
    db.add(yeni_kaynak)

    # 8) Her parcayi bir SemanticUnit olarak kaydet - pages.py'deki
    #    sayfayi_indexle ile AYNI mantik, sadece parcalar buradan gelir.
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

    # 9) Her unit'i embedding'e gonder - pages.py'deki index adimindaki
    #    ayni paralel calisma mantigi (asyncio.gather + to_thread)
    await asyncio.gather(*[
        asyncio.to_thread(parcayi_kaydet, unit.id, unit.page_id, unit.icerik)
        for unit in yeni_unitler
    ])

    # 10) Siniflandirma VE kavram cikarma artik MANUEL butonlar degil,
    #     yukleme aninda OTOMATIK calisiyor - bkz. markdown_ekle'deki
    #     ayni adimin aciklamasi.
    await siniflandirmayi_uygula(db, yeni_sayfa)
    await kavramlari_uygula(db, yeni_unitler)
    await db.commit()

    await db.refresh(yeni_sayfa)

    return yeni_sayfa
