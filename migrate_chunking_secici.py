"""
migrate_chunking_secici.py

TEK SEFERLIK migration scripti. Production, elle yazilmis 4 adimlik
chunking pipeline'indan, belge-turune gore otomatik yontem SECEN
chunking_secici.yontem_sec()'e gecti (bkz. DEVAM_NOTU.md ve
app/services/chunking_secici.py). Bu script, veritabanindaki TUM
sayfalari YENI seciciyle yeniden parcalar.

KAPSAM (kullanici onayli, bkz. DEVAM_NOTU.md "Sirdaki adim"): SADECE
TURETILMIS veri silinip yeniden uretiliyor:
    SemanticUnit, ConceptNode, ConceptRelation, KavramGorulme,
    KavramTakmaAdi, KavramBirlesmesi, OnerilenTur, SayfaBaglantisi
Chroma'daki "semantic_units" ve "concept_names" koleksiyonlari da
silinip yeniden kuruluyor (embedding icerigi degisiyor).

WikiPage ve Source KORUNUYOR - hicbir sayfa yeniden yuklenmiyor,
sadece WikiPage.content yeni seciciyle yeniden parcalaniyor.

ONEMLI, KULLANICI ONAYI ALINDI: bu migration eski kavram grafigi ile
yeni parcalar arasindaki baglantiyi TAMAMEN SIFIRLIYOR - her sayfa
icin otomatik siniflandirma + kavram cikarma SIFIRDAN calisiyor
(sayfa sayisi kadar LLM cagrisi - sure/maliyet göz onunde
bulunduruldu, bkz. DEVAM_NOTU.md).

Guvenlik agi: calistirmadan once personalwiki.db ve chroma_data/,
zaman damgali bir yedek klasorune kopyalanir (asagida BACKUP_KOKU).

Calistirmak icin (proje kok dizininde, venv aktifken, backend KAPALIYKEN):
    python migrate_chunking_secici.py
"""

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import chromadb
from sqlalchemy import delete, select

from app.database import SessionYerel
from app.models.db_models import (
    WikiPage,
    SemanticUnit,
    ConceptNode,
    ConceptRelation,
    KavramGorulme,
    KavramTakmaAdi,
    KavramBirlesmesi,
    OnerilenTur,
    SayfaBaglantisi,
)

CHROMA_VERI_YOLU = "chroma_data"
VERITABANI_DOSYASI = "personalwiki.db"
BACKUP_KOKU = Path("migration_yedekleri") / datetime.now().strftime("%Y%m%d_%H%M%S")


def yedek_al():
    """
    personalwiki.db ve chroma_data/'yi migration_yedekleri/<zaman damgasi>/
    altina kopyalar - migration'in geri alinamaz olmasi (kavram grafiginin
    sifirlanmasi) nedeniyle bir guvenlik agi.
    """
    BACKUP_KOKU.mkdir(parents=True, exist_ok=True)

    if Path(VERITABANI_DOSYASI).exists():
        shutil.copy2(VERITABANI_DOSYASI, BACKUP_KOKU / VERITABANI_DOSYASI)
        print(f"Yedek alindi: {BACKUP_KOKU / VERITABANI_DOSYASI}")

    if Path(CHROMA_VERI_YOLU).exists():
        shutil.copytree(CHROMA_VERI_YOLU, BACKUP_KOKU / CHROMA_VERI_YOLU)
        print(f"Yedek alindi: {BACKUP_KOKU / CHROMA_VERI_YOLU}")


def eski_koleksiyonlari_sil():
    client = chromadb.PersistentClient(path=CHROMA_VERI_YOLU)
    for isim in ["semantic_units", "concept_names"]:
        try:
            client.delete_collection(name=isim)
            print(f"Eski '{isim}' koleksiyonu silindi.")
        except Exception as hata:
            print(f"'{isim}' silinemedi (muhtemelen zaten yok): {hata}")


async def turetilmis_veriyi_temizle():
    """
    KAPSAM'da listelenen tablolari, foreign key sirasina uygun sekilde
    (once ConceptNode'a REFERANS VEREN tablolar, sonra ConceptNode'un
    kendisi) siler. WikiPage ve Source'a HIC dokunmaz.
    """
    async with SessionYerel() as db:
        await db.execute(delete(KavramGorulme))
        await db.execute(delete(ConceptRelation))
        await db.execute(delete(KavramTakmaAdi))
        await db.execute(delete(KavramBirlesmesi))
        await db.execute(delete(OnerilenTur))
        await db.execute(delete(ConceptNode))
        await db.execute(delete(SemanticUnit))
        await db.execute(delete(SayfaBaglantisi))
        await db.commit()

    print(
        "Eski turetilmis veri silindi: SemanticUnit, ConceptNode, "
        "ConceptRelation, KavramGorulme, KavramTakmaAdi, KavramBirlesmesi, "
        "OnerilenTur, SayfaBaglantisi. (WikiPage/Source korundu.)"
    )


async def tum_sayfalari_yeniden_isle():
    # Importlar BURADA yapiliyor - eski Chroma koleksiyonlari silindikten
    # SONRA import edilirse, get_or_create_collection artik YENI (bos)
    # koleksiyonlari kurar (bkz. migrate_embeddinggemma.py ile ayni desen).
    from app.embeddings.embedding_servisi import parcayi_kaydet, parcalari_sil
    from app.services.chunking_secici import yontem_sec
    from app.routers.pages import siniflandirmayi_uygula
    from app.routers.concepts import kavramlari_uygula
    from app.services.graph_servisi import global_graf_yeniden_hesapla

    async with SessionYerel() as db:
        sonuc = await db.execute(select(WikiPage))
        sayfalar = sonuc.scalars().all()

    print(f"\n{len(sayfalar)} sayfa yeniden islenecek...\n")

    basarisiz_sayfalar = []

    for i, sayfa in enumerate(sayfalar, start=1):
        async with SessionYerel() as db:
            yeni_unitler = []
            try:
                # 1) Yeni seciciyle yeniden parcala.
                yontem_adi, parcalar = yontem_sec(sayfa.content)

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

                await db.flush()
                for unit in yeni_unitler:
                    await db.refresh(unit)

                # 2) Her parcayi embed et.
                for unit in yeni_unitler:
                    parcayi_kaydet(unit.id, unit.page_id, unit.icerik)

                # 3) Otomatik siniflandirma + kavram cikarma (production'daki
                #    upload akisiyla AYNI paylasilan fonksiyonlar).
                guncel_sayfa = await db.get(WikiPage, sayfa.id)
                kategori = await siniflandirmayi_uygula(db, guncel_sayfa)
                await kavramlari_uygula(db, yeni_unitler)

                await db.commit()

                print(
                    f"[{i}/{len(sayfalar)}] sayfa_id={sayfa.id} '{sayfa.title}' -> "
                    f"{len(parcalar)} parca ({yontem_adi}), kategori={kategori}"
                )
            except Exception as hata:
                await db.rollback()

                # SQL rollback oldu ama flush edilmis unit'ler icin Chroma'ya
                # yazma zaten gerceklesmis olabilir (embed adimi transaction
                # disinda calisiyor) - bu "hayalet" vektorleri temizle, yoksa
                # SQL'de olmayan bir id Chroma'da kalir (bkz. pages.py'deki
                # sayfa silme docstring'inde ayni sorun).
                flush_edilmis_idler = [u.id for u in yeni_unitler if u.id is not None]
                if flush_edilmis_idler:
                    parcalari_sil(flush_edilmis_idler)

                basarisiz_sayfalar.append((sayfa.id, sayfa.title, str(hata)))
                print(f"[{i}/{len(sayfalar)}] sayfa_id={sayfa.id} '{sayfa.title}' BASARISIZ: {hata}")

    print("\nTum sayfalar islendi. Global graf yeniden hesaplaniyor...")
    async with SessionYerel() as db:
        olusturulan_baglanti = await global_graf_yeniden_hesapla(db)
    print(f"Global graf yeniden kuruldu: {olusturulan_baglanti} baglanti olusturuldu.")

    if basarisiz_sayfalar:
        print(f"\n{len(basarisiz_sayfalar)} sayfa basarisiz oldu:")
        for sayfa_id, title, hata in basarisiz_sayfalar:
            print(f"  - sayfa_id={sayfa_id} '{title}': {hata}")
        print(
            "Bu sayfalar icin masaustu uygulamasindaki 'Yeniden Isle' "
            "butonunu (ya da POST /pages/{id}/index + /classify + "
            "/extract-concepts) manuel calistirarak tamamlayabilirsin."
        )


async def migration_calistir():
    await turetilmis_veriyi_temizle()
    await tum_sayfalari_yeniden_isle()


if __name__ == "__main__":
    yedek_al()
    eski_koleksiyonlari_sil()
    asyncio.run(migration_calistir())
    print("\nMigration tamamlandi.")
