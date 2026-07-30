
# chat_servisi.py
# Arama sonuclarini alip, Gemini'ye "SADECE bu baglami kullanarak
# cevap ver" talimatiyla gonderen servis. RAG'in "generation" (uretim)
# kismi burada.
# !! bu dosya veritabanina yazmaz, sadece metin alip metin dondurur.

from google import genai

from app.config import ayarlar


# Gemini istemcisi
_client = genai.Client(api_key=ayarlar.GEMINI_API_KEY)

def rag_cevap_uret(soru:str,baglam_parcalari:list[str]) -> str :
    
    """
    soru:kullanicinin sordugu soru
    baglam_parcalari: arama sonucunda bulunan ilgili metin parcalari

    Donen deger: LLM'in SADECE verilen baglama dayanarak uretttigi cevap.
    """
    
        # Baglam parcalarini tek bir metinde birlestiriyoruz, aralarina
    # numara koyarak LLM'in hangi parcanin hangisi oldugunu ayirt
    # etmesini kolaylastiriyoruz.
    baglam_metni = "\n\n".join(
        f"[Parca {i+1}]: {parca}"
        for i, parca in enumerate(baglam_parcalari)
    )

    # ONEMLI: bu prompt, "knowledge-base tabanli arama" prensibini
    # uyguluyor - LLM'e SADECE verilen baglami kullanmasini,
    # kendi genel bilgisini KULLANMAMASINI soyluyoruz.
    prompt = f"""Asagida kullanicinin kendi bilgi tabanindan alinmis metin parcalari var.
    SADECE bu parcalardaki bilgiyi kullanarak soruyu cevapla.
    Eger cevap bu parcalarda yoksa, "Bu bilgi yuklediginiz dosyalarda bulunamadi" de.
    Kendi genel bilgini KULLANMA, sadece asagidaki baglama dayan.

    Baglam: {baglam_metni}

    Soru: {soru}

    Cevap:"""

    yanit = _client.models.generate_content(
        model=ayarlar.GEMINI_MODEL,
        contents=prompt,
    )

    return yanit.text