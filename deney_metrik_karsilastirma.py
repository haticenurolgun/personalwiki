"""
deney_metrik_karsilastirma.py

run_test_chunk.py'deki AYNI SAYFA_IDLERI ve YONTEMLER icin ICC/DCC/BI/SC
metriklerini (deney_metrikleri.py) hesaplar, sayfa-bazli sonuclari
yontem-bazli ORTALAMAYA indirger (Adaptive Chunking makalesinin
Tablo 3'undeki formatla ayni fikir) ve hem ekrana hem CSV'ye yazar.
Uretim veritabanina/koleksiyonlarina DOKUNMAZ, sadece OKUR.

NEDEN HER KOMBINASYON AYRI BIR PROCESS'TE (subprocess) CALISTIRILIYOR:
tum (yontem, sayfa) kombinasyonlarini TEK process icinde sirayla
calistirdigimizda, embedding modeli + Stanza'yi COK sayida ardisik
cagirinca calisma bir noktada sessizce (CPU kullanmadan) TAKILIYORDU -
kesin sebep belirlenemedi. Her kombinasyonu deney_metrik_worker.py
uzerinden AYRI, TEMIZ bir process'te calistirmak sorunu ortadan
kaldirdi - bir kombinasyon takilsa/yavaslasa bile (timeout ile) sadece
o kombinasyon atlanir, digerleri etkilenmez.

Calistirmak icin (venv aktifken, proje kok dizininde):
    python deney_metrik_karsilastirma.py
"""

import csv
import json
import statistics
import subprocess
import sys

from run_test_chunk import SAYFA_IDLERI, YONTEMLER

CSV_DOSYA_ADI = "deney_metrikleri.csv"

# Tek bir (yontem, sayfa) kombinasyonu icin azami bekleme suresi -
# bu sureyi asan bir kombinasyon "takildi" sayilip ATLANIR, geri kalan
# kombinasyonlarin calismasini engellemez.
KOMBINASYON_TIMEOUT_SANIYE = 120


def kombinasyonu_calistir(yontem_adi: str, sayfa_id: int) -> dict | None:
    try:
        sonuc = subprocess.run(
            [sys.executable, "deney_metrik_worker.py", yontem_adi, str(sayfa_id)],
            capture_output=True,
            text=True,
            timeout=KOMBINASYON_TIMEOUT_SANIYE,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        print(f"ATLANDI (timeout): {yontem_adi} / sayfa {sayfa_id}")
        return None

    if sonuc.returncode != 0:
        print(f"HATA: {yontem_adi} / sayfa {sayfa_id}: {sonuc.stderr[-500:]}")
        return None

    # worker'in stdout'unda "Loading weights" progress bar'i ve
    # transformers uyarilari da karisiyor - sadece "SONUC:" onekiyle
    # baslayan satiri ariyoruz.
    for satir in sonuc.stdout.splitlines():
        if satir.startswith("SONUC:"):
            return json.loads(satir[len("SONUC:"):])

    print(f"HATA: {yontem_adi} / sayfa {sayfa_id}: SONUC satiri bulunamadi")
    return None


def calistir():
    satirlar = []
    for yontem_adi in YONTEMLER:
        for sayfa_id in SAYFA_IDLERI:
            veri = kombinasyonu_calistir(yontem_adi, sayfa_id)
            if veri is None:
                continue
            satirlar.append(veri)
            print(
                f"{veri['yontem']:24s} | Sayfa {veri['sayfa_id']:3d} | parca={veri['parca_sayisi']:3d} | "
                f"ICC={veri['ICC']:.3f} DCC={veri['DCC']:.3f} BI={veri['BI']:.3f} SC={veri['SC']:.3f} "
                f"ort={veri['ortalama']:.3f}"
            )

    if not satirlar:
        print("Hicbir kombinasyon basariyla tamamlanmadi.")
        return

    with open(CSV_DOSYA_ADI, "w", newline="", encoding="utf-8-sig") as f:
        yazici = csv.DictWriter(f, fieldnames=satirlar[0].keys())
        yazici.writeheader()
        yazici.writerows(satirlar)

    print("\n\n=== YONTEM BAZLI ORTALAMA (tum sayfalar) ===")
    print(f"{'Yontem':24s} {'ICC':>7s} {'DCC':>7s} {'BI':>7s} {'SC':>7s} {'Ort':>7s}")
    ozet_satirlari = []
    for yontem_adi in YONTEMLER:
        ilgili = [s for s in satirlar if s["yontem"] == yontem_adi]
        if not ilgili:
            continue
        icc_ort = statistics.mean(s["ICC"] for s in ilgili)
        dcc_ort = statistics.mean(s["DCC"] for s in ilgili)
        bi_ort = statistics.mean(s["BI"] for s in ilgili)
        sc_ort = statistics.mean(s["SC"] for s in ilgili)
        genel_ort = statistics.mean([icc_ort, dcc_ort, bi_ort, sc_ort])
        ozet_satirlari.append((yontem_adi, icc_ort, dcc_ort, bi_ort, sc_ort, genel_ort))
        print(f"{yontem_adi:24s} {icc_ort:7.3f} {dcc_ort:7.3f} {bi_ort:7.3f} {sc_ort:7.3f} {genel_ort:7.3f}")

    en_iyi = max(ozet_satirlari, key=lambda x: x[-1])
    print(f"\nEn yuksek genel ortalama: {en_iyi[0]} ({en_iyi[-1]:.3f})")
    print(f"Detayli sonuclar: {CSV_DOSYA_ADI}")


if __name__ == "__main__":
    calistir()
