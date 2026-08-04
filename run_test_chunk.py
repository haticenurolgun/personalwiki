"""Secilen birkac sayfa uzerinde, deney_chunking_yontemleri.py'deki HER
yontemi ayri ayri calistirir, sonuclari AYRI bir Chroma koleksiyonuna
(chroma_data_deney/ klasorunde) yazar ve temel istatistikleri ekrana
basar. Uretim veritabanina/koleksiyonlarina DOKUNMAZ."""

import asyncio
import statistics

import chromadb
from sqlalchemy import select

from app.database import SessionYerel
from app.models.db_models import WikiPage
from app.embeddings.embedding_servisi import token_sayisi, _model
from test_chunking_yont import (
    mevcut_yontem,
    yontem_genellestirilmis_merge,
    yontem_semantik,
    yontem_cumle_bazli,
    yontem_semantik_stanza,
    yontem_overlap_recursive,
    yontem_split_then_merge_1100,
    yontem_split_then_merge_600,
)

test_chroma_path= "chroma_data_test"

SAYFA_IDLERI = [1, 22, 26, 27,30,33,34,37] ## Karsilastirmak istedigimiz sayfalarin id'lerini buraya yaziyoruz. (WikiPage.id)

YONTEMLER = {
    "mevcut": mevcut_yontem,
    "genellestirilmis_merge": yontem_genellestirilmis_merge,
    "semantik": yontem_semantik,
    "cumle_bazli": yontem_cumle_bazli,
    "semantik_stanza": yontem_semantik_stanza,
    "overlap_recursive": yontem_overlap_recursive,
    "split_then_merge_1100": yontem_split_then_merge_1100,
    "split_then_merge_600": yontem_split_then_merge_600,
    # yeni yontemler eklendikce buraya da eklenecek
}


async def sayfalari_getir(sayfa_idleri: list[int]) -> list[WikiPage]:
    
    """Verilen id listesindeki WikiPage kayıtlarını veritabanından çeker ve döndürür."""
    
    async with SessionYerel() as db:
        sonuc = await db.execute(select(WikiPage).where(WikiPage.id.in_(sayfa_idleri)))
        return sonuc.scalars().all()
    
    
def sonuclari_yazdir(yontem_adi:str,sayfa:WikiPage,parcalar):
    
    """Her parçanın gerçek token sayısını (token_sayisi — EmbeddingGemma'nın gerçek tokenizer'ı, tahmin değil) hesaplayıp min/max/ortalama/medyan basıyor. 
    Bu sayılar bize şunu gösterir: yöntem çok mu küçük parçalar üretiyor (bilgi sulanır), çok mu büyük (birden fazla konu tek vektöre sıkışır), yoksa dengeli mi?
    İlk 3 parçanın önizlemesini basıyor. Bu sayede parçaların mantıklı olup olmadığını gözle kontrol edebiliriz."""
    
    token_sayilari=[token_sayisi(parca.icerik) for parca in parcalar]
    
    print(f"\n\nYontem: {yontem_adi} | Sayfa: {sayfa.id} - {sayfa.title}")
    print(f"Parca sayisi: {len(parcalar)}")
    if token_sayilari:
        print(f"Token sayilari: {token_sayilari}")
        print(f"Token sayisi ortalamasi: {statistics.mean(token_sayilari)}")
        print(f"Token sayisi medyani: {statistics.median(token_sayilari)}")
        
    for i, parca in enumerate(parcalar[:3]):
        onizleme = parca.icerik.strip().replace("\n", " ")[:80]
        print(f"  [{i}] ({parca.baslik}) {onizleme}...")
        
        
        
def koleksiyona_kaydet(client, koleksiyon_adi: str, sayfa_id: int, parcalar):
    """
    Verilen parçaları Chroma koleksiyonuna kaydeder. 
    Her parçanın embedding'ini alır ve koleksiyona ekler.
    """
    koleksiyon = client.get_or_create_collection(
        name=koleksiyon_adi,
        metadata={"hnsw:space": "cosine"},
    )
    if not parcalar:
        return
    vektorler = [_model.encode(p.icerik, prompt_name="document").tolist() for p in parcalar]
    koleksiyon.upsert(
        ids=[f"{sayfa_id}_{i}" for i in range(len(parcalar))],
        embeddings=vektorler,
        documents=[p.icerik for p in parcalar],
        metadatas=[{"sayfa_id": sayfa_id, "baslik": p.baslik} for p in parcalar],
    )


async def calistir():
    
    """YONTEMLER sözlüğündeki her yöntemi her sayfa üzerinde çalıştırır, istatistiklerini basar, sonuçlarını kendi koleksiyonuna kaydeder."""
    
    sayfalar = await sayfalari_getir(SAYFA_IDLERI)
    client = chromadb.PersistentClient(path=test_chroma_path)

    for yontem_adi, yontem_fonksiyonu in YONTEMLER.items():
        koleksiyon_adi = f"deney_{yontem_adi}"
        for sayfa in sayfalar:
            parcalar = yontem_fonksiyonu(sayfa.content)
            sonuclari_yazdir(yontem_adi, sayfa, parcalar)
            koleksiyona_kaydet(client, koleksiyon_adi, sayfa.id, parcalar)


if __name__ == "__main__":
    asyncio.run(calistir())