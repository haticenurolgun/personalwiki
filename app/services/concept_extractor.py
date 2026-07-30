# =============================================================================
# concept_extractor.py
# =============================================================================
# LLM kullanarak bir metin parcasindan KAVRAM ve ILISKI cikaran servis.
# ONEMLI KURAL: bu dosya veritabanina yazmaz, sadece metin alip
# yapilandirilmis Python nesneleri dondurur (Wikontic mantiginin
# "aday cikarim" asamasi).
# =============================================================================

from dataclasses import dataclass
from google import genai
from google.genai.errors import ServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json
from app.config import ayarlar
from app.services.ontology import KAVRAM_TIPLERI, ILISKI_TIPLERI

_client = genai.Client(api_key=ayarlar.GEMINI_API_KEY)


@dataclass
class CikarilanKavram:
    isim: str
    tip: str   # KAVRAM_TIPLERI'nden biri OLMAYABILIR de - kontrolu ayri yapacagiz
    takma_adlar: list[str]   # LLM'in onerdigi alternatif isimler/kisaltmalar

@dataclass
class CikarilanIliski:
    kaynak_isim: str
    hedef_isim: str
    iliski_tipi: str   # ILISKI_TIPLERI'nden biri OLMAYABILIR de


@dataclass
class CikarimSonucu:
    kavramlar: list[CikarilanKavram]
    iliskiler: list[CikarilanIliski]


@dataclass
class BatchCikarimSonucu:
    """
    Bir batch'teki HER unit_id icin ayri CikarimSonucu tutan sozluk
    yapisi - hangi unit'in hangi kavram/iliskileri urettigini
    ayirt edebilmemiz icin.
    """
    unit_sonuclari: dict[int, CikarimSonucu]



def kavram_cikar(metin: str) -> CikarimSonucu:
    """
    Verilen metinden, ontolojiye uygun kavram ve iliskileri LLM ile
    cikarir. TEK BIR metin parcasi icin calisir - birden fazla
    parcayi ayni anda islemek icin kavram_cikar_batch'e bak.
    """

    kavram_tipleri_metni = ", ".join(KAVRAM_TIPLERI)
    iliski_tipleri_metni = ", ".join(ILISKI_TIPLERI)

    prompt = f"""Asagidaki metinden onemli KAVRAMLARI ve aralarindaki
    ILISKILERI cikar.

    Kavram tipleri SADECE su listeden olmali: {kavram_tipleri_metni}
    Iliski tipleri SADECE su listeden olmali: {iliski_tipleri_metni}
    Hicbiri tam uymuyorsa en yakinini sec, ya da listede olmayan yeni
    bir tip onerebilirsin (orn. "DONANIM").

    ONEMLI: Metinde birbiriyle iliskili gecen HER kavram cifti icin
    MUTLAKA bir iliski uret - kavrami iliskisiz birakma.
    "ILGILI" tipini SON CARE olarak kullan, once daha spesifik tipi dene:
    - Kisi/kurum aidiyeti (cocuk, kardes, uye) -> AITTIR
    - Biri digerini kapsiyorsa -> ICERIR / PARCASI
    - Biri digerinin onkosuluysa -> ONKOSUL
    - Dosya/kaynak bir konudan bahsediyorsa -> BAHSEDER
    - Proje/gorev bir arac kullaniyorsa -> KULLANIR
    - Bilgi bir kaynaktan geliyorsa -> KAYNAKLANIR

    Ornekler:
    - "Hatice, Adem'in kizidir" -> {{"kaynak_isim": "Hatice", "hedef_isim": "Adem", "iliski_tipi": "AITTIR"}}
    - "Ayse'nin 6 cocugu vardir" -> {{"kaynak_isim": "Ayse", "hedef_isim": "Cocuklar", "iliski_tipi": "ICERIR"}}
    - "Proje FastAPI kullaniyor" -> {{"kaynak_isim": "Proje", "hedef_isim": "FastAPI", "iliski_tipi": "KULLANIR"}}
    - "1NF, 2NF'nin onkosuludur" -> {{"kaynak_isim": "1NF", "hedef_isim": "2NF", "iliski_tipi": "ONKOSUL"}}

    Her kavram icin, biliniyorsa alternatif isim/kisaltmalarini
    takma_adlar listesinde ver, yoksa bos liste ver.

    Metin:
    {metin}

    Cevabi asagidaki JSON semasina birebir uyacak sekilde ver:
    {{
    "kavramlar": [{{"isim": "...", "tip": "...", "takma_adlar": ["..."]}}],
    "iliskiler": [{{"kaynak_isim": "...", "hedef_isim": "...", "iliski_tipi": "..."}}]
    }}"""
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
        # LLM bazen kusurlu JSON uretebilir - bu durumda bu metin icin
        # bos bir sonuc donuyoruz, tum islemi cokertmek yerine.
        return CikarimSonucu(kavramlar=[], iliskiler=[])

    kavramlar = [
        CikarilanKavram(
            isim=k["isim"],
            tip=k["tip"],
            takma_adlar=k.get("takma_adlar", []),
        )
        for k in veri.get("kavramlar", [])
    ]

    iliskiler = [
        CikarilanIliski(
            kaynak_isim=i["kaynak_isim"],
            hedef_isim=i["hedef_isim"],
            iliski_tipi=i["iliski_tipi"],
        )
        for i in veri.get("iliskiler", [])
    ]

    return CikarimSonucu(kavramlar=kavramlar, iliskiler=iliskiler)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(ServerError),
    reraise=True,
)
def kavram_cikar_batch(metinler: dict[int, str]) -> BatchCikarimSonucu:
    """
    Birden fazla SemanticUnit'in icerigini TEK BIR Gemini cagrisinda
    isler - her biri icin AYRI kavram/iliski listesi doner.

    metinler: {unit_id: icerik} seklinde sozluk - hangi unit_id'nin
              hangi metne ait oldugunu LLM'e numarali olarak
              gonderiyoruz, LLM de cevabini AYNI numaralarla
              etiketleyerek donduruyor.

    NEDEN BATCH: her sayfa icin ayri ayri Gemini cagirmak (400 sayfalik
    bir PDF'te 400 cagri) network round-trip suresini kat kat
    carpiyor. Birden fazla sayfayi tek cagrida birlestirerek cagri
    sayisini azaltiyoruz.

    NEDEN @retry: Gemini bazen gecici olarak 503 (yogunluk) hatasi
    dondurebiliyor. Bu durumda 3 kere, artan bekleme sureleriyle
    (2sn, 4sn, 8sn) tekrar deniyoruz. Uc deneme de basarisiz olursa,
    hata cagiran tarafa (concepts.py'deki grubu_isle) firlatiliyor -
    o da bu grubu bos gecip TUM islemi cokertmeden devam ediyor.
    """

    kavram_tipleri_metni = ", ".join(KAVRAM_TIPLERI)
    iliski_tipleri_metni = ", ".join(ILISKI_TIPLERI)

    # unit_id'leri sirali bir liste olarak sabitliyoruz - prompt'ta
    # ve cevapta AYNI sirayla referans verecegiz.
    unit_id_listesi = list(metinler.keys())

    parcalar_metni = "\n\n".join(
        f"--- METIN {i+1} (unit_id={unit_id}) ---\n{metinler[unit_id]}"
        for i, unit_id in enumerate(unit_id_listesi)
    )

    prompt = f"""Asagida NUMARALANMIS birden fazla metin parcasi var.
    HER metin parcasi icin AYRI AYRI onemli KAVRAMLARI ve aralarindaki
    ILISKILERI cikar. Cevabinda her metnin sonucunu, o metnin
    numarasiyla (METIN 1, METIN 2, ...) esleyecek sekilde ayir.

    Kavram tipleri SADECE su listeden olmali: {kavram_tipleri_metni}
    Iliski tipleri SADECE su listeden olmali: {iliski_tipleri_metni}
    Hicbiri tam uymuyorsa en yakinini sec, ya da listede olmayan yeni
    bir tip onerebilirsin (orn. "DONANIM").

    ONEMLI: Her metinde birbiriyle iliskili gecen HER kavram cifti
    icin MUTLAKA bir iliski uret - kavrami iliskisiz birakma.
    "ILGILI" tipini SON CARE olarak kullan, once daha spesifik tipi dene:
    - Kisi/kurum aidiyeti (cocuk, kardes, uye) -> AITTIR
    - Biri digerini kapsiyorsa -> ICERIR / PARCASI
    - Biri digerinin onkosuluysa -> ONKOSUL
    - Dosya/kaynak bir konudan bahsediyorsa -> BAHSEDER
    - Proje/gorev bir arac kullaniyorsa -> KULLANIR
    - Bilgi bir kaynaktan geliyorsa -> KAYNAKLANIR

    Her kavram icin, biliniyorsa alternatif isim/kisaltmalarini
    takma_adlar listesinde ver, yoksa bos liste ver.

    Metinler:
    {parcalar_metni}

    Cevabi asagidaki JSON semasina birebir uyacak sekilde ver - "metin_no"
    alani, yukaridaki METIN numarasina (1'den baslayarak) karsilik gelmeli:
    {{
    "sonuclar": [
        {{
        "metin_no": 1,
        "kavramlar": [{{"isim": "...", "tip": "...", "takma_adlar": ["..."]}}],
        "iliskiler": [{{"kaynak_isim": "...", "hedef_isim": "...", "iliski_tipi": "..."}}]
        }}
    ]
    }}"""

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
        # Tum batch icin bos sonuc don - hicbir unit'i kaybetmeden,
        # sadece bu batch'in kavramlarini atlamis oluyoruz.
        return BatchCikarimSonucu(unit_sonuclari={
            unit_id: CikarimSonucu(kavramlar=[], iliskiler=[])
            for unit_id in unit_id_listesi
        })

    # metin_no -> unit_id eslemesi (1-indexed metin_no'yu, 0-indexed
    # listedeki karsiligina ceviriyoruz). Once TUM unit'ler icin bos
    # sonuc ile baslatiyoruz - LLM bir metni atlarsa bile bos donsun.
    unit_sonuclari: dict[int, CikarimSonucu] = {
        unit_id: CikarimSonucu(kavramlar=[], iliskiler=[])
        for unit_id in unit_id_listesi
    }

    for sonuc_item in veri.get("sonuclar", []):
        metin_no = sonuc_item.get("metin_no")

        if metin_no is None or not (1 <= metin_no <= len(unit_id_listesi)):
            continue   # LLM gecersiz bir numara uretmis olabilir, atla

        ilgili_unit_id = unit_id_listesi[metin_no - 1]

        kavramlar = [
            CikarilanKavram(
                isim=k["isim"],
                tip=k["tip"],
                takma_adlar=k.get("takma_adlar", []),
            )
            for k in sonuc_item.get("kavramlar", [])
        ]

        iliskiler = [
            CikarilanIliski(
                kaynak_isim=i["kaynak_isim"],
                hedef_isim=i["hedef_isim"],
                iliski_tipi=i["iliski_tipi"],
            )
            for i in sonuc_item.get("iliskiler", [])
        ]

        unit_sonuclari[ilgili_unit_id] = CikarimSonucu(kavramlar=kavramlar, iliskiler=iliskiler)

    return BatchCikarimSonucu(unit_sonuclari=unit_sonuclari)