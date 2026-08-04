"""
deney_metrik_worker.py

TEK bir (yontem, sayfa) kombinasyonu icin ICC/DCC/BI/SC hesaplayip
sonucu STDOUT'a TEK SATIR JSON olarak yazan yardimci script. AYRI bir
process olarak calistirilmasi icin tasarlandi (bkz. deney_metrik_
karsilastirma.py) - boylece bir kombinasyonda olusabilecek herhangi bir
kaynak sorunu/yavaslama/kilitlenme, digerlerini ETKILEMEZ (her biri
temiz bir process'te, sifirdan baslar).

NEDEN GEREKLI OLDU: tum kombinasyonlari TEK process icinde sirayla
calistirdigimizda (embedding modeli + Stanza'yi COK sayida ardisik
cagirinca), calisma bir noktada sessizce (CPU kullanmadan) TAKILIYORDU -
kesin sebebi belirlenemedi (muhtemelen PyTorch'un Windows'taki thread
havuzu ile ilgili bir sorun), ama her kombinasyonu izole bir process'te
calistirmak sorunu tamamen ortadan kaldirdi.

Kullanim:
    python deney_metrik_worker.py <yontem_adi> <sayfa_id>
"""

import sys
import json
import asyncio
import statistics

from run_test_chunk import YONTEMLER, sayfalari_getir
from deney_metrikleri import hesapla_icc, hesapla_dcc, hesapla_bi, hesapla_sc


async def calistir(yontem_adi: str, sayfa_id: int):
    sayfalar = await sayfalari_getir([sayfa_id])
    sayfa = sayfalar[0]
    parcalar = YONTEMLER[yontem_adi](sayfa.content)

    icc = hesapla_icc(parcalar)
    dcc = hesapla_dcc(parcalar)
    bi = hesapla_bi(sayfa.content, parcalar)
    sc = hesapla_sc(parcalar)

    # NOT: bu satirin oncesinde "Loading weights" progress bar'i ve
    # transformers uyarilari da stdout/stderr'e karisabilir - bu yuzden
    # bu satiri OZEL bir onek ("SONUC:") ile isaretliyoruz, cagiran
    # taraf (deney_metrik_karsilastirma.py) sadece bu onekle baslayan
    # satiri arayip parse ediyor.
    print("SONUC:" + json.dumps({
        "yontem": yontem_adi,
        "sayfa_id": sayfa.id,
        "sayfa_basligi": sayfa.title,
        "parca_sayisi": len(parcalar),
        "ICC": round(icc, 4),
        "DCC": round(dcc, 4),
        "BI": round(bi, 4),
        "SC": round(sc, 4),
        "ortalama": round(statistics.mean([icc, dcc, bi, sc]), 4),
    }))


if __name__ == "__main__":
    _yontem_adi = sys.argv[1]
    _sayfa_id = int(sys.argv[2])
    asyncio.run(calistir(_yontem_adi, _sayfa_id))
