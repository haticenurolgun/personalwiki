"""
kalibrasyon.py

Mevcut ConceptNode'lar arasinda, embedding benzerligi FARKLI esik
degerlerinde ne kadar "ayni kavram" eslesmesi cikardigini gosteren
TEK SEFERLIK bir analiz scripti. Veritabanina HICBIR SEY YAZMAZ,
sadece okur ve ekrana rapor basar.

Calistirmak icin (proje kok dizininde, venv aktifken):
    python kalibrasyon.py
"""

import asyncio
from itertools import combinations

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from app.database import SessionYerel
from app.models.db_models import ConceptNode


# Denenecek esik degerleri - gercek veriyle her birinde kac eslesme
# ciktigini gorup, kacinin MANTIKLI kacinin YANLIS oldugunu gozle
# degerlendirecegiz.
DENENECEK_ESIKLER = [0.70, 0.75, 0.80, 0.85, 0.90]


async def kavramlari_getir():
    """Veritabanindaki tum ConceptNode'lari (id, isim, tip) olarak getirir."""
    async with SessionYerel() as db:
        sonuc = await db.execute(select(ConceptNode))
        return sonuc.scalars().all()


def kozinus_benzerligi(vektor_a, vektor_b):
    """Iki vektor arasindaki kozinus benzerligini hesaplar (0-1 arasi)."""
    import numpy as np
    a = np.array(vektor_a)
    b = np.array(vektor_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


async def ana_akis():
    print("Kavramlar veritabanindan okunuyor...")
    kavramlar = await kavramlari_getir()
    print(f"Toplam {len(kavramlar)} kavram bulundu.\n")

    print("Embedding modeli yukleniyor...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Kavramlari TIPE gore grupla - sadece ayni tipteki kavramlari
    # birbiriyle karsilastiracagiz (bir KISI ile bir ARAC karsilastirilmaz).
    tipe_gore = {}
    for kavram in kavramlar:
        tipe_gore.setdefault(kavram.tip, []).append(kavram)

    # Her kavramin ismini vektore cevir (bir kere hesaplayip cache'liyoruz,
    # her cift icin tekrar tekrar hesaplamayalim).
    print("Isimler vektore cevriliyor...")
    id_to_vektor = {}
    for kavram in kavramlar:
        id_to_vektor[kavram.id] = model.encode(kavram.standart_isim)

    # Her esik icin, kac cift esleser diye sayacagiz.
    esik_sonuclari = {esik: [] for esik in DENENECEK_ESIKLER}

    print("Ayni tipteki kavram ciftleri karsilastiriliyor...\n")
    for tip, ayni_tipteki_kavramlar in tipe_gore.items():
        # itertools.combinations, bir listeden TEKRARSIZ ikili
        # kombinasyonlar uretir (A-B ile B-A ayni sayilir, bir kere gelir).
        for kavram_a, kavram_b in combinations(ayni_tipteki_kavramlar, 2):
            benzerlik = kozinus_benzerligi(
                id_to_vektor[kavram_a.id],
                id_to_vektor[kavram_b.id],
            )

            for esik in DENENECEK_ESIKLER:
                if benzerlik >= esik:
                    esik_sonuclari[esik].append((kavram_a.standart_isim, kavram_b.standart_isim, tip, benzerlik))

    # Rapor
    print("=" * 70)
    print("ESIK BAZLI SONUCLAR")
    print("=" * 70)
    for esik in DENENECEK_ESIKLER:
        eslesmeler = esik_sonuclari[esik]
        print(f"\nEsik >= {esik}: {len(eslesmeler)} eslesme bulundu")

    # En yuksek esikten en dusuge, ORNEK eslesmeleri goster - boylece
    # hangi esikte "mantikli" hangi esikte "yanlis" eslesmeler ciktigini
    # gozle gorebilirsin.
    for esik in DENENECEK_ESIKLER:
        eslesmeler = sorted(esik_sonuclari[esik], key=lambda x: -x[3])
        print("\n" + "=" * 70)
        print(f"ESIK >= {esik} - ORNEK ESLESMELER (ilk 20)")
        print("=" * 70)
        for isim_a, isim_b, tip, benzerlik in eslesmeler[:20]:
            print(f"  [{tip}] '{isim_a}' <-> '{isim_b}'  (benzerlik: {benzerlik:.3f})")


if __name__ == "__main__":
    asyncio.run(ana_akis())