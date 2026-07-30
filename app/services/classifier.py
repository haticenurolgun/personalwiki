# =============================================================================
# classifier.py
# =============================================================================
# LLM kullanarak bir WikiPage'in icerigine bakip, SABIT bir kategori
# listesinden birini secen servis. concept_extractor.py ile AYNI kural:
# bu dosya veritabanina yazmaz, sadece metin alip yapilandirilmis bir
# Python nesnesi dondurur.
# =============================================================================

from dataclasses import dataclass
import json

from google import genai

from app.config import ayarlar

_client = genai.Client(api_key=ayarlar.GEMINI_API_KEY)

# Sayfa siniflandirmasi icin sabit kategori listesi. ontology.py'deki
# KAVRAM_TIPLERI'nden FARKLI bir amaca hizmet ediyor: KAVRAM_TIPLERI bir
# sayfa ICINDEKI tek tek kavramlari tipliyor (orn. "1NF" -> TERIM), bu
# liste ise sayfanin KENDISINI (butun olarak) siniflandiriyor.
SAYFA_KATEGORILERI = [
    "DERS_NOTU",         # bir teknik/akademik konuyu anlatan ogrenme notu
    "SINAV_HAZIRLIK",    # sinav/mulakat icin ozet, tekrar, soru-cevap notu
    "PROJE_DOKUMANI",    # bir proje ile ilgili planlama/teknik belge
    "TOPLANTI_NOTU",     # toplanti tutanagi, alinan kararlar
    "GOREV_LISTESI",     # yapilacaklar/TODO tarzi bir liste
    "FIKIR",             # beyin firtinasi, taslak/olgunlasmamis fikirler
    "SUREC_DOKUMANI",    # "nasil yapilir" rehberi, ic prosedur (orn. "deploy nasil yapilir")
    "REFERANS",          # bir dis kaynagin (makale, kitap, web sitesi) ozeti
    "KISISEL",           # aile, gunluk, kisisel bilgiler
    "DIGER",             # hicbiri uymuyorsa
]


@dataclass
class SiniflandirmaSonucu:
    kategori: str


def sayfa_siniflandir(icerik: str) -> SiniflandirmaSonucu:
    """
    Verilen sayfa icerigine bakip, SAYFA_KATEGORILERI listesinden
    birini secer. LLM listede olmayan bir sey donerse (ya da JSON
    bozuksa), guvenli varsayilan olarak "DIGER" kullanilir - concept_
    extractor.py'deki "ontoloji disi tip -> OnerilenTur" mantiginin
    aksine, burada MVP icin ayri bir onay tablosu yok, direkt DIGER'e
    dusuyor.
    """

    kategori_metni = ", ".join(SAYFA_KATEGORILERI)

    prompt = f"""Asagidaki metin, kullanicinin kisisel wiki'sindeki bir
    sayfadir. Bu sayfayi SADECE su kategorilerden birine ata:
    {kategori_metni}

    - DERS_NOTU: bir teknik/akademik konuyu anlatan ogrenme notu
    - SINAV_HAZIRLIK: sinav/mulakat icin ozet, tekrar, soru-cevap notu
      (DERS_NOTU'ndan farki: bu SIKISTIRILMIS/pratik amaclidir, derinlemesine anlatmaz)
    - PROJE_DOKUMANI: bir proje ile ilgili planlama/teknik belge
    - TOPLANTI_NOTU: bir toplantinin tutanagi, orada alinan kararlar
    - GOREV_LISTESI: yapilacaklar/TODO tarzi, SOMUT eylem iceren bir liste
    - FIKIR: beyin firtinasi, henuz somut eyleme donusmemis taslak fikirler
    - SUREC_DOKUMANI: "bir sey nasil yapilir" rehberi, ic prosedur
      (orn. "deploy nasil yapilir") - REFERANS'tan farki DIS bir kaynagi
      degil, KENDI/sirket ici bir sureci anlatir
    - REFERANS: bir dis kaynagin (makale, kitap, web sitesi) ozeti
    - KISISEL: aile, gunluk, kisisel bilgiler
    - DIGER: yukaridakilerden hicbiri uymuyorsa

    Metin:
    {icerik}

    Cevabi asagidaki JSON semasina birebir uyacak sekilde ver:
    {{"kategori": "..."}}"""

    yanit = _client.models.generate_content(
        model=ayarlar.GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    try:
        veri = json.loads(yanit.text)
    except json.JSONDecodeError:
        return SiniflandirmaSonucu(kategori="DIGER")

    kategori = veri.get("kategori", "DIGER")

    if kategori not in SAYFA_KATEGORILERI:
        kategori = "DIGER"

    return SiniflandirmaSonucu(kategori=kategori)
