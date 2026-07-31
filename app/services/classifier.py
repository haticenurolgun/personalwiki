# =============================================================================
# classifier.py
# =============================================================================
# LLM kullanarak bir WikiPage'in ICERIGININ hangi KONUYA/DERSE/PROJEYE
# ait oldugunu belirleyen servis. Sabit bir liste YOK (ontology.py'deki
# KAVRAM_TIPLERI gibi degil) - sistemde daha once olusturulmus konu
# isimleri LLM'e gosteriliyor (tutarli isimlendirme icin: ayni ders
# icin hep AYNI ismi kullansin), LLM ya birine eslesir ya da yeni bir
# konu ismi onerir. Nihai eslesme karari TEK BASINA LLM'e birakilmiyor
# (bkz. asagidaki NEDEN IKI ALAN aciklamasi) - pages.py'de embedding
# benzerligiyle bir GUVENLIK AGI olarak dogrulaniyor.
#
# concept_extractor.py ile AYNI kural: bu dosya veritabanina yazmaz.
# =============================================================================

from dataclasses import dataclass
import json

from google import genai

from app.config import ayarlar

_client = genai.Client(api_key=ayarlar.GEMINI_API_KEY)


@dataclass
class SiniflandirmaSonucu:
    kategori: str          # LLM'in NIHAI karari (listeden biri ya da yeni)
    bagimsiz_konu: str      # LLM'in listeye BAKMADAN verdigi bagimsiz karar


def sayfa_siniflandir(icerik: str, mevcut_konular: list[str]) -> SiniflandirmaSonucu:
    """
    Verilen sayfa icerigine bakip, hangi KONUYA/DERSE/PROJEYE ait
    oldugunu belirler.

    mevcut_konular: sistemde DAHA ONCE olusturulmus konu/klasor
    isimleri (orn. ["Calculus", "Elektronik"]). LLM'e gosterilmesinin
    amaci TUTARLI ISIMLENDIRME - ayni derse ait yeni bir sayfa
    geldiginde, LLM'in dunya bilgisiyle "bu da ayni ders" diye
    tanıyip AYNI ismi kullanmasini saglamak (bir embedding modelinin
    yakalayamayacagi kadar ince bir eslestirme olabilir, orn.
    "PostgreSQL" ile "Veritabani Normalizasyonu" konusu).

    NEDEN IKI ALAN (kategori + bagimsiz_konu) DONUYOR: LLM'in "listeden
    birine uydur ya da yeni oner" karari TEK BASINA guvenilir degil -
    test ederek bulundu: listede TEK bir ALAKASIZ secenek bile olsa
    ("ATLAS" gibi), LLM ona "yapisiyordu" (capalama onyargisi) -
    tamamen alakasiz bir "Gravio" sirket profili yanlislikla "ATLAS"
    olarak etiketlendi. bagimsiz_konu alani, LLM'in listeye HIC
    BAKMADAN verdigi kararı ayrica tutuyor - pages.py bu ikisini
    KARSILASTIRIP (embedding benzerligiyle) LLM'in eslestirme
    kararinin makul olup olmadigini DOGRULUYOR, kor kor guvenmiyor.

    LLM'den anlamli bir cevap alinamazsa (JSON bozuksa ya da bos
    donerse), guvenli varsayilan olarak "Diger" kullanilir.
    """

    if mevcut_konular:
        konu_listesi_metni = ", ".join(mevcut_konular)
        liste_talimati = f"""2) SONRA, bu bagimsiz kararini asagidaki
        mevcut konu/klasor listesiyle KARSILASTIR:
        {konu_listesi_metni}

        Eger 1. adimda bulduğun konu, bu listedeki bir konuyla
        GERCEKTEN AYNI SPESIFIK ders/proje/kurumsa (sadece ayni GENIS
        ALANDA olmalari YETERLI DEGIL, GERCEKTEN AYNI konu/proje/kurum
        olmalilar), o konunun ismini BIREBIR AYNEN kullan. Degilse,
        1. adimdaki KENDI bagimsiz kararini kullan - listede bir
        secenek var diye ona ZORLA uydurma, EMIN OLMADIGIN durumda
        YENI konuyu tercih et."""
    else:
        liste_talimati = (
            "2) Henuz sistemde kayitli bir konu yok, bu yuzden "
            "1. adimdaki bagimsiz kararini dogrudan kullan."
        )

    prompt = f"""Asagidaki metin, kullanicinin kisisel wiki'sindeki bir
    sayfadir. Iki asamada karar ver:

    1) ONCE, BASKA HICBIR SEYE BAKMADAN, SADECE metnin ICERIGINE
    bakarak bu sayfanin ASIL konusunu belirle - MUMKUN OLDUGUNCA
    SPESIFIK bir ders/kurs/proje/kurum ismiyle (orn. "Calculus",
    "Elektronik", "Sistem Programlama", "Gravio"). "Yazilim",
    "Programlama", "Ders Notlari", "Teknoloji" gibi COK GENIS/SEMSIYE
    isimlerden KACIN. Metnin icinde GECEN ama metnin ASIL konusu
    OLMAYAN bir kelime/terimi (orn. aile hakkindaki bir metinde arada
    gecen "veritabani kuruyor" cumlesi) konu olarak SECME.

    {liste_talimati}

    Metin:
    {icerik}

    Cevabi asagidaki JSON semasina birebir uyacak sekilde ver:
    {{"bagimsiz_konu": "1. adimda buldugun konu", "kategori": "nihai karar (2. adim sonrasi)"}}"""

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
        return SiniflandirmaSonucu(kategori="Diger", bagimsiz_konu="Diger")

    bagimsiz_konu = veri.get("bagimsiz_konu", "").strip() or "Diger"
    kategori = veri.get("kategori", "").strip() or bagimsiz_konu

    return SiniflandirmaSonucu(kategori=kategori, bagimsiz_konu=bagimsiz_konu)
