"""
migrate_normalize_isim.py

TEK SEFERLIK migration scripti. concept_nodes ve kavram_takma_adlari
tablolarina yeni sutunlar ekler (normalize_isim, normalize_takma_ad)
ve VAR OLAN satirlar icin bu sutunlari otomatik doldurur.

ONEMLI: Bu script sadece BIR KERE calistirilmali. Zaten calistirdiysan
tekrar calistirmana gerek yok (calistirirsan "duplicate column" hatasi
alirsin - bu, sutunun zaten eklendigini gosterir, zarar vermez ama
gereksizdir).

Calistirmak icin (proje kok dizininde, venv aktifken):
    python migrate_normalize_isim.py
"""

import sqlite3

# Turkce karakter normalizasyonu - metin_yardimcilari.py ile AYNI mantik.
# Burada ayrica tanimliyoruz cunku bu script FastAPI uygulamasindan
# BAGIMSIZ, duz bir sqlite3 baglantisiyla calisiyor.
_TURKCE_KARAKTER_ESLEMESI = {
    "İ": "i", "I": "i", "ı": "i",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ş": "s", "ş": "s",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
}


def normalize_et(metin: str) -> str:
    sonuc = metin
    for turkce_karakter, ascii_karsiligi in _TURKCE_KARAKTER_ESLEMESI.items():
        sonuc = sonuc.replace(turkce_karakter, ascii_karsiligi)
    return sonuc.lower()


def migration_yap():
    baglanti = sqlite3.connect("personalwiki.db")
    imlec = baglanti.cursor()

    # 1) concept_nodes tablosuna normalize_isim sutunu ekle
    try:
        imlec.execute("ALTER TABLE concept_nodes ADD COLUMN normalize_isim VARCHAR(300)")
        print("concept_nodes.normalize_isim sutunu eklendi.")
    except sqlite3.OperationalError as hata:
        print(f"concept_nodes.normalize_isim eklenemedi (muhtemelen zaten var): {hata}")

    # 2) kavram_takma_adlari tablosuna normalize_takma_ad sutunu ekle
    try:
        imlec.execute("ALTER TABLE kavram_takma_adlari ADD COLUMN normalize_takma_ad VARCHAR(300)")
        print("kavram_takma_adlari.normalize_takma_ad sutunu eklendi.")
    except sqlite3.OperationalError as hata:
        print(f"kavram_takma_adlari.normalize_takma_ad eklenemedi (muhtemelen zaten var): {hata}")

    baglanti.commit()

    # 3) VAR OLAN concept_nodes satirlarini oku, her biri icin
    #    normalize_isim degerini hesapla, geri yaz.
    imlec.execute("SELECT id, standart_isim FROM concept_nodes")
    kavramlar = imlec.fetchall()

    guncellenen_kavram = 0
    for kavram_id, standart_isim in kavramlar:
        normalize_edilmis = normalize_et(standart_isim)
        imlec.execute(
            "UPDATE concept_nodes SET normalize_isim = ? WHERE id = ?",
            (normalize_edilmis, kavram_id),
        )
        guncellenen_kavram += 1

    print(f"{guncellenen_kavram} adet ConceptNode icin normalize_isim dolduruldu.")

    # 4) VAR OLAN kavram_takma_adlari satirlarini da doldur.
    imlec.execute("SELECT id, takma_ad FROM kavram_takma_adlari")
    takma_adlar = imlec.fetchall()

    guncellenen_takma_ad = 0
    for takma_ad_id, takma_ad in takma_adlar:
        normalize_edilmis = normalize_et(takma_ad)
        imlec.execute(
            "UPDATE kavram_takma_adlari SET normalize_takma_ad = ? WHERE id = ?",
            (normalize_edilmis, takma_ad_id),
        )
        guncellenen_takma_ad += 1

    print(f"{guncellenen_takma_ad} adet KavramTakmaAdi icin normalize_takma_ad dolduruldu.")

    baglanti.commit()
    baglanti.close()
    print("\nMigration tamamlandi.")


if __name__ == "__main__":
    migration_yap()