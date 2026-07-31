# =============================================================================
# classifier.py
# =============================================================================
# LLM kullanarak bir WikiPage'in ICERIGININ hangi KONUYA/DERSE ait
# oldugunu belirleyen servis. Sabit bir liste YOK (ontology.py'deki
# KAVRAM_TIPLERI gibi degil) - bunun yerine, sistemde DAHA ONCE
# olusturulmus konu isimleri LLM'e gosteriliyor: ya BIRINE uyduruluyor
# (ayni klasore dusuyor) ya da YENI bir konu ismi oneriliyor (orn.
# "Calculus", "Elektronik"). Boylece kullanici dosya yukledikce, ayni
# derse ait notlar otomatik olarak AYNI klasorde birikiyor - yeni bir
# konu gelirse de kendiliginden yeni bir klasor acilmis olur.
#
# concept_extractor.py ile AYNI kural: bu dosya veritabanina yazmaz,
# sadece metin (+ mevcut konu listesi) alip yapilandirilmis bir Python
# nesnesi dondurur. Mevcut konulari VERITABANINDAN cekmek ve isim
# eslesmesindeki yazim farklarini (buyuk/kucuk harf, Turkce karakter)
# normalize etmek CAGIRAN tarafin (pages.py) sorumlulugunda.
# =============================================================================

from dataclasses import dataclass
import json

from google import genai

from app.config import ayarlar

_client = genai.Client(api_key=ayarlar.GEMINI_API_KEY)


@dataclass
class SiniflandirmaSonucu:
    kategori: str


def sayfa_siniflandir(icerik: str, mevcut_konular: list[str]) -> SiniflandirmaSonucu:
    """
    Verilen sayfa icerigine bakip, hangi KONUYA/DERSE ait oldugunu
    belirler.

    mevcut_konular: sistemde DAHA ONCE olusturulmus konu/klasor
    isimlerinin listesi (orn. ["Calculus", "Elektronik"]). LLM'e bu
    liste veriliyor ki, ayni konudaki YENI bir sayfa geldiginde var
    olan klasore duzgunce eslesebilsin - her seferinde farkli isimli
    yeni bir klasor acmak yerine.

    LLM'den anlamli bir cevap alinamazsa (JSON bozuksa, ya da bos
    donerse), guvenli varsayilan olarak "Diger" kullanilir.
    """

    if mevcut_konular:
        konu_listesi_metni = ", ".join(mevcut_konular)
        baglam = f"""Sistemde su an bu konu/klasor isimleri kayitli:
        {konu_listesi_metni}

        Bu, kullanicinin KISISEL wiki'si - aile notlari, ders notlari,
        is/proje notlari gibi BIRBIRINDEN TAMAMEN FARKLI konular ayni
        sistemde bir arada bulunabilir. Bu yuzden ONEMLI: bir konuyu
        SADECE metnin icinde o konuyla ilgili TEK BIR KELIME/TERIM
        gectigi icin secme - metnin GENELININ, BUTUN OLARAK o konu
        hakkinda olmasi gerekir. Ornegin metin esas olarak aile
        bilgilerinden bahsediyorsa ama arada "veritabani kuruyor" gibi
        TEK bir cumle geciyorsa, bu metni "Veritabanlari" konusuna
        DAHIL ETME - bu durumda metnin ASIL konusuna gore yeni bir
        etiket sec (orn. "Kisisel").

        Eger metnin GENELI, listedeki konulardan BIRIYLE GERCEKTEN
        ayniysa, o konunun ismini BIREBIR AYNEN kullan (yeni bir isim
        uydurma, kucuk yazim farkli bir versiyonunu da uretme). Emin
        degilsen, yanlis eslestirmektense YENI bir konu onermeyi
        TERCIH ET. Hicbiri uymuyorsa, metnin konusunu KISA (1-3
        kelime), GENEL bir konu/ders ismiyle etiketle (orn. "Calculus",
        "Elektronik", "Veritabanlari", "Kisisel")."""
    else:
        baglam = """Henuz hicbir konu kaydedilmemis. Metnin konusunu
        KISA (1-3 kelime), GENEL bir konu/ders ismiyle etiketle (orn.
        "Calculus", "Elektronik", "Veritabanlari")."""

    prompt = f"""Asagidaki metin, kullanicinin kisisel wiki'sindeki bir
    sayfadir. Bu sayfanin hangi KONUYA/DERSE ait oldugunu belirle.

    {baglam}

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
        return SiniflandirmaSonucu(kategori="Diger")

    kategori = veri.get("kategori", "").strip()
    if not kategori:
        kategori = "Diger"

    return SiniflandirmaSonucu(kategori=kategori)
