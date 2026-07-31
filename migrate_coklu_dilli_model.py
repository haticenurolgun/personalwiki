"""
migrate_coklu_dilli_model.py

TEK SEFERLIK migration scripti. Embedding modeli all-MiniLM-L6-v2'den
paraphrase-multilingual-MiniLM-L12-v2'ye degistirildi (Turkce
tokenizasyon kalitesi icin, bkz. embedding_servisi.py'deki yorum).

Iki modelin vektorleri AYNI BOYUTTA (384) olsa da, birbirleriyle
KIYASLANAMAZ - farkli modellerin vektor uzaylari farkli. Bu yuzden HEM
"semantic_units" HEM "concept_names" Chroma koleksiyonlarinin SILINIP
YENI modelle YENIDEN olusturulmasi gerekiyor.

Calistirmak icin (proje kok dizininde, venv aktifken, backend KAPALIYKEN):
    python migrate_coklu_dilli_model.py
"""

import asyncio

import chromadb

from app.database import SessionYerel
from sqlalchemy import select
from app.models.db_models import SemanticUnit, ConceptNode


CHROMA_VERI_YOLU = "chroma_data"


def eski_koleksiyonlari_sil():
    client = chromadb.PersistentClient(path=CHROMA_VERI_YOLU)
    for isim in ["semantic_units", "concept_names"]:
        try:
            client.delete_collection(name=isim)
            print(f"Eski '{isim}' koleksiyonu silindi.")
        except Exception as hata:
            print(f"'{isim}' silinemedi (muhtemelen zaten yok): {hata}")


async def tum_verileri_yeniden_embed_et():
    # Import BURADA yapiliyor - eski koleksiyonlar silindikten SONRA
    # import edilirse, get_or_create_collection artik YENI (bos)
    # koleksiyonlari YENI modelle olusturur.
    from app.embeddings.embedding_servisi import parcayi_kaydet, kavram_kaydet

    async with SessionYerel() as db:
        sonuc = await db.execute(select(SemanticUnit.id, SemanticUnit.page_id, SemanticUnit.icerik))
        unitler = sonuc.all()

        sonuc2 = await db.execute(select(ConceptNode.id, ConceptNode.standart_isim, ConceptNode.tip))
        kavramlar = sonuc2.all()

    print(f"{len(unitler)} adet SemanticUnit yeniden embed edilecek...")
    for i, (unit_id, page_id, icerik) in enumerate(unitler, start=1):
        parcayi_kaydet(unit_id, page_id, icerik)
        if i % 50 == 0:
            print(f"  {i}/{len(unitler)} tamamlandi...")
    print(f"Tamamlandi: {len(unitler)} unit yeniden embed edildi.")

    print(f"\n{len(kavramlar)} adet ConceptNode yeniden embed edilecek...")
    for i, (node_id, isim, tip) in enumerate(kavramlar, start=1):
        kavram_kaydet(node_id, isim, tip)
        if i % 50 == 0:
            print(f"  {i}/{len(kavramlar)} tamamlandi...")
    print(f"Tamamlandi: {len(kavramlar)} kavram yeniden embed edildi.")


if __name__ == "__main__":
    eski_koleksiyonlari_sil()
    asyncio.run(tum_verileri_yeniden_embed_et())
    print("\nMigration tamamlandi.")
