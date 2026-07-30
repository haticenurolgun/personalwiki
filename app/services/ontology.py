# Projenin KAVRAM ve ILISKI tiplerini tanimlayan tek merkezi yer.
# concept_extractor.py, LLM'e "sadece bu tiplerden birini kullan" derken
# buradaki listeleri kullanacak.


# 


# 1) KAVRAM(Varlık Tipleri):

KAVRAM_TIPLERI = [
    "KONU",         # genel bir bilgi alani/baslik
    "TERIM",        # teknik bir terim/tanim
    "DOSYA",        # yuklenen bir dosyanin kendisi
    "KISI",         # bahsedilen bir kisi
    "PROJE",        # bir proje adi
    "ARAC",         # kullanilan bir yazilim/arac/teknoloji
    "TARIH_OLAYI",  # belirli bir tarihe bagli olay
    "KURUM",        # sirket/okul/organizasyon
    "KAYNAK",       # dis bir referans (makale, kitap, web sitesi)
    "GOREV",        # yapilacak bir is/gorev
]

# 2) İlişki tipleri: iki kavram arasindaki baglanti, bu tiplerden birine
# ait olmali.yazdım



ILISKI_TIPLERI = [
    "ILGILI",       # genel iliski, baska hicbiri uymuyorsa
    "ICERIR",       # bir kavram digerini kapsiyor
    "ONKOSUL",      # biri digerinin onkosulu
    "BAHSEDER",     # bir dosya/kaynak, bir kavramdan bahsediyor
    "KULLANIR",     # bir proje/gorev, bir araci kullaniyor
    "AITTIR",       # bir sey birine/bir kuruma ait
    "PARCASI",      # biri digerinin bir parcasi
    "KAYNAKLANIR",  # bir bilgi bir kaynaktan geliyor
]

