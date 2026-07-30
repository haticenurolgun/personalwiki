import sqlite3

baglanti = sqlite3.connect("personalwiki.db")
imlec = baglanti.cursor()

imlec.execute("ALTER TABLE concept_nodes RENAME COLUMN kanonik_isim TO standart_isim;")
baglanti.commit()

# Kontrol
imlec.execute("PRAGMA table_info(concept_nodes);")
for satir in imlec.fetchall():
    print(satir)

baglanti.close()