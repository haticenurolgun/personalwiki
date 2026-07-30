"""
migrate_kategori_ekle.py

TEK SEFERLIK migration scripti. wiki_pages tablosuna yeni bir kategori
sutunu ekler (var olan satirlar icin bos/NULL kalir - classify
endpoint'i cagirilana kadar).

ONEMLI: Bu script sadece BIR KERE calistirilmali. Zaten calistirdiysan
tekrar calistirmana gerek yok ("duplicate column" hatasi alirsin, zarar
vermez ama gereksizdir).

Calistirmak icin (proje kok dizininde, venv aktifken):
    python migrate_kategori_ekle.py
"""

import sqlite3


def migration_yap():
    baglanti = sqlite3.connect("personalwiki.db")
    imlec = baglanti.cursor()

    try:
        imlec.execute("ALTER TABLE wiki_pages ADD COLUMN kategori VARCHAR(50)")
        print("wiki_pages.kategori sutunu eklendi.")
    except sqlite3.OperationalError as hata:
        print(f"wiki_pages.kategori eklenemedi (muhtemelen zaten var): {hata}")

    baglanti.commit()
    baglanti.close()
    print("\nMigration tamamlandi.")


if __name__ == "__main__":
    migration_yap()
