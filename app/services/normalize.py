# =============================================================================
#normalize.py
# =============================================================================
# Metin karsilastirma icin kucuk yardimci fonksiyonlar. Su an sadece
# Turkce karakter normalizasyonu var, ama ileride baska metin islemleri
# de (orn. bosluk temizleme, noktalama kaldirma) buraya eklenebilir.
# ONEMLI KURAL: bu dosya veritabanina HICBIR SEY yazmaz, sadece metin
# alip metin dondurur - tek basina test edilebilir.
# =============================================================================


# Turkce'ye ozgu karakterlerin ASCII karsiliklarina eslemesi. Bu, iki
# ismin SADECE Turkce karakter/buyuk-kucuk harf farkiyla ayni olup
# olmadigini anlamak icin kullanilir.
#
# NEDEN GEREKLI? Python'in kendi .lower() metodu Turkce karakterlerde
# HATALI sonuc verir:
#   "YILMAZ".lower()  -> "yilmaz"  (noktasiz i)
#   "Yılmaz".lower()  -> "yılmaz"  (noktali i / ı harfi)
# Bu ikisi FARKLI karakterler oldugu icin, sadece .lower() kullanirsak
# "YILMAZ" ile "Yılmaz" hala FARKLI string sayilir - oysa bunlar ayni
# isim, sadece yazim farkli. Bu yuzden ONCE Turkce karakterleri ASCII'ye
# ceviriyoruz, SONRA .lower() uyguluyoruz.
_TURKCE_KARAKTER_ESLEMESI = {
    "İ": "i", "I": "i", "ı": "i",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ş": "s", "ş": "s",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
}


def normalize_et(metin: str) -> str:
    """
    Bir metni, Turkce karakter ve buyuk/kucuk harf farklarini yok
    sayacak sekilde normalize eder. Iki farkli yazilmis ama ASLINDA
    ayni olan ismi karsilastirmak icin kullanilir.

    Ornek:
        normalize_et("Kaan ASLAN") == normalize_et("Kaan Aslan")  -> True
        normalize_et("Mühendislik") == normalize_et("Muhendislik") -> True
        normalize_et("YILMAZ") == normalize_et("Yılmaz")           -> True

    metin: normalize edilecek ham metin (orn. bir kavram ismi)
    Donen deger: normalize edilmis, kucuk harfli, ASCII Turkce
                 karakterli metin.
    """
    sonuc = metin

    # Once Turkce'ye ozgu karakterleri ASCII karsiliklarina cevir.
    # NOT: sirali calismasi onemli degil burada, cunku her karakter
    # tek tek ve birbirinden bagimsiz degistiriliyor.
    for turkce_karakter, ascii_karsiligi in _TURKCE_KARAKTER_ESLEMESI.items():
        sonuc = sonuc.replace(turkce_karakter, ascii_karsiligi)

    # Son olarak, geriye kalan (Turkce'ye ozgu olmayan) harfleri de
    # standart Python .lower() ile kucuk harfe cevir.
    return sonuc.lower()