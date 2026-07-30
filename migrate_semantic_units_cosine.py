"""
migrate_semantic_units_cosine.py

TEK SEFERLIK migration scripti. "semantic_units" Chroma koleksiyonu L2
(varsayilan) mesafesiyle olusturulmustu, artik kodda cosine olarak
tanimli (embedding_servisi.py). Chroma'da hnsw:space bir koleksiyon
olusturulduktan SONRA degistirilemiyor - bu yuzden:

1) Eski "semantic_units" koleksiyonunu SIL (icindeki vektorler gider,
   ama bu veri kaybi DEGIL - vektorler SQLite'daki SemanticUnit.icerik
   sutunundan YENIDEN hesaplanabilir)
2) embedding_servisi import edildiginde, kod artik cosine ile YENIDEN
   olusturur (get_or_create_collection)
3) SQLite'daki TUM SemanticUnit satirlarini oku, her birini yeniden
   embed edip yeni (cosine) koleksiyona yaz

ONEMLI: Bu script sadece BIR KERE calistirilmali.

Calistirmak icin (proje kok dizininde, venv aktifken):
    python migrate_semantic_units_cosine.py
"""

import asyncio

import chromadb

from app.database import SessionYerel
from sqlalchemy import select
from app.models.db_models import SemanticUnit


CHROMA_VERI_YOLU = "chroma_data"


def eski_koleksiyonu_sil():
    client = chromadb.PersistentClient(path=CHROMA_VERI_YOLU)
    try:
        client.delete_collection(name="semantic_units")
        print("Eski 'semantic_units' koleksiyonu silindi.")
    except Exception as hata:
        print(f"Silinemedi (muhtemelen zaten yok): {hata}")


async def tum_unitleri_yeniden_embed_et():
    # Import BURADA yapiliyor - eski koleksiyon silindikten SONRA import
    # edilirse, embedding_servisi.py'deki get_or_create_collection artik
    # YENI (cosine) koleksiyonu olusturur.
    from app.embeddings.embedding_servisi import parcayi_kaydet

    async with SessionYerel() as db:
        sonuc = await db.execute(select(SemanticUnit.id, SemanticUnit.page_id, SemanticUnit.icerik))
        unitler = sonuc.all()

    print(f"{len(unitler)} adet SemanticUnit yeniden embed edilecek...")

    for i, (unit_id, page_id, icerik) in enumerate(unitler, start=1):
        parcayi_kaydet(unit_id, page_id, icerik)
        if i % 50 == 0:
            print(f"  {i}/{len(unitler)} tamamlandi...")

    print(f"Tamamlandi: {len(unitler)} unit yeniden embed edildi.")


if __name__ == "__main__":
    eski_koleksiyonu_sil()
    asyncio.run(tum_unitleri_yeniden_embed_et())
    print("\nMigration tamamlandi.")
