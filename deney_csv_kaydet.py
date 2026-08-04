"""
deney_csv_kaydet.py

run_test_chunk.py'deki AYNI SAYFA_IDLERI ve YONTEMLER sozlugunu kullanarak
(oradan ITHAL ederek, tekrar TANIMLAMADAN - boylece iki dosya birbirinden
asla geride kalmaz), sonuclari TEK bir CSV dosyasina yazar. Her satirda
"yontem" sutunu hangi yonteme ait oldugunu belirtir - boylece Excel/
Sheets'te filtreleyip/pivotlayip yan yana karsilastirabilirsiniz.
Uretim veritabanina/koleksiyonlarina DOKUNMAZ, sadece OKUR.

Calistirmak icin (venv aktifken, proje kok dizininde):
    python deney_csv_kaydet.py
"""

import asyncio
import csv

from sqlalchemy import select

from app.database import SessionYerel
from app.models.db_models import WikiPage
from app.embeddings.embedding_servisi import token_sayisi

from run_test_chunk import SAYFA_IDLERI, YONTEMLER

CSV_DOSYA_ADI = "deney_sonuclari.csv"


async def sayfalari_getir(sayfa_idleri: list[int]) -> list[WikiPage]:
    async with SessionYerel() as db:
        sonuc = await db.execute(select(WikiPage).where(WikiPage.id.in_(sayfa_idleri)))
        return sonuc.scalars().all()


async def calistir():
    sayfalar = await sayfalari_getir(SAYFA_IDLERI)

    # utf-8-sig: basindaki BOM sayesinde Excel, Turkce karakterleri
    # (ı, ş, ğ, vb.) bozmadan dogru acar - duz utf-8 ile Excel bazen
    # bunlari yanlis kodlamayla gosterir.
    with open(CSV_DOSYA_ADI, "w", newline="", encoding="utf-8-sig") as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow([
            "yontem", "sayfa_id", "sayfa_basligi", "parca_sira",
            "parca_basligi", "token_sayisi", "karakter_sayisi", "icerik",
        ])

        for yontem_adi, yontem_fonksiyonu in YONTEMLER.items():
            for sayfa in sayfalar:
                parcalar = yontem_fonksiyonu(sayfa.content)
                for sira, parca in enumerate(parcalar):
                    yazici.writerow([
                        yontem_adi,
                        sayfa.id,
                        sayfa.title,
                        sira,
                        parca.baslik,
                        token_sayisi(parca.icerik),
                        len(parca.icerik),
                        parca.icerik,
                    ])

    print(f"Yazildi: {CSV_DOSYA_ADI}")


if __name__ == "__main__":
    asyncio.run(calistir())
