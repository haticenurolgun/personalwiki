# =============================================================================
# arama_servisi.py
# =============================================================================
# Hibrit arama mantigini (embedding + ontoloji) TEK bir yerde toplar -
# hem search.py hem chat.py bu mantigi kullanir. Once search.py'de
# yazilmisti, sonra /chat'in ayni mantigi kullanmadigi (sadece duz
# embedding aramasi yaptigi) fark edildi - bu tutarsizligi onlemek
# icin buraya tasindi (DRY: iki yerde ayni kod tekrar tekrar yazilmasin).
#
# NOT: bu dosya, services/ klasorunun genel kuralindan (veritabanina
# YAZMAZ) FARKLI olarak veritabanindan OKUMA yapiyor - graph_servisi.py
# ile ayni desen (bir AsyncSession alip sadece select() calistiriyor,
# hicbir db.add/commit yok).
# =============================================================================

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import SemanticUnit, ConceptNode, ConceptRelation, KavramTakmaAdi, KavramGorulme
from app.services.normalize import normalize_et
from app.embeddings.embedding_servisi import benzer_parcalari_bul

# Ontoloji-bazli sonuclar icin GERCEK bir kozinus uzakligi yok (embedding
# aramasi yapilmadi) - bu yuzden sabit, "cok yakin" anlamina gelen yer
# tutucu degerler kullaniyoruz. Dogrudan eslesen kavram, iliskili
# kavramdan daha "kesin" sayildigi icin daha kucuk (daha yakin) bir
# deger aliyor.
DOGRUDAN_KAVRAM_UZAKLIGI = 0.0

# Iliskili kavramlar ARTIK TEK bir sabit degil, ILISKI TIPINE gore
# farkli agirliklar aliyor - onceden tum 8 tip (ONKOSUL de ILGILI de)
# ayni 0.15 degerini kullaniyordu, yani "iliskili mi degil mi" disinda
# hicbir ayrim yapilmiyordu.
#
# KALIBRASYON (gercek veriyle test edilerek yapildi, bkz. proje
# notlari): ilk denemede TUM degerler (0.10-0.30) "tipik embedding
# sonucundan kucuk" varsayimiyla secilmisti, ama gercek sorgularda
# (orn. "FastAPI") bu projenin embedding modelinin GERCEKTEN alakali
# sonuclar icin bile ~0.40'in ALTINA pek inmedigi ortaya cikti. Bu
# yuzden ILK halinde TUM iliski tipleri (en zayifi ILGILI dahil) HER
# ZAMAN butun embedding sonuclarini yeniyordu - orn. "Proje lideri
# Ahmet Yilmaz, XYZ Teknoloji bunyesinde calismaktadir" (BAHSEDER,
# FastAPI'den hic bahsetmeyen bir cumle) FastAPI'nin GERCEK tanimini
# (embedding, 0.427) geride birakiyordu. Duzeltme: BAHSEDER/ILGILI
# artik BILINCLI OLARAK gercek embedding tabaninin (~0.40) UZERINDE -
# boylece sadece GERCEKTEN daha iyi bir embedding sonucu yoksa devreye
# giriyorlar. ONKOSUL/PARCASI/ICERIR ise DUSUK birakildi (BILINCLI
# TERCIH, hata degil) - bunlarin amaci zaten embedding'in
# YAKALAYAMAYACAGI (farkli kelime dagarciciyla ifade edilmis) temel/
# hiyerarsik baglami ONE CIKARMAK, o yuzden embedding sonuclarini
# geride birakmalari ISTENEN davranis.
#   - ONKOSUL/PARCASI/ICERIR: yapisal/hiyerarsik, en guclu sinyal -
#     "2NF" ararken "1NF"nin de cikmasi neredeyse her zaman faydali.
#     BILINCLI OLARAK embedding tabaninin ALTINDA tutuluyor.
#   - AITTIR/KULLANIR/KAYNAKLANIR: anlamli ama daha az hiyerarsik -
#     gercek ornekler (orn. "FastAPI -KAYNAKLANIR-> Python") beklenenden
#     daha faydali ciktigi icin KAYNAKLANIR bu kalibrasyonda
#     BAHSEDER'den ayrilip bu guclu gruba tasindi.
#   - BAHSEDER: referans niteliginde ama gercek veride SIK SIK zayif/
#     totolojik ciktigi gozlemlendi (orn. "randevu al -> randevu") -
#     embedding tabaninin UZERINE cikarildi.
#   - ILGILI: hicbir spesifik tip uymadiginda kullanilan SON CARE
#     etiketi - en zayif sinyal, embedding tabaninin da UZERINDE.
ILISKI_TIPI_UZAKLIGI = {
    "ONKOSUL": 0.10,
    "PARCASI": 0.12,
    "ICERIR": 0.12,
    "KAYNAKLANIR": 0.18,
    "AITTIR": 0.18,
    "KULLANIR": 0.18,
    "BAHSEDER": 0.45,
    "ILGILI": 0.50,
}

# Ontology.py'deki ILISKI_TIPLERI listesinde OLMAYAN (normalde hic
# olusmamasi gereken - concepts.py::kavramlari_uygula, ontoloji disi
# tipler icin zaten ConceptRelation OLUSTURMUYOR, bkz. OnerilenTur -
# ama savunmaci kod olarak) bir tip gelirse kullanilacak varsayilan
# agirlik. Kalibrasyon sonrasi iki net grup olustugu icin (guclu grup
# 0.10-0.18, zayif grup 0.45-0.50) TAM ortasi anlamli degil - bilinmeyen
# bir tipe KORKAK davranip zayif gruba yakin, ama embedding tabaninin
# (~0.40) biraz altinda kalacak temkinli bir deger secildi.
ILISKI_TIPI_VARSAYILAN_UZAKLIK = 0.30


def _iliski_agirligi(iliski_tipi: str) -> float:
    return ILISKI_TIPI_UZAKLIGI.get(iliski_tipi, ILISKI_TIPI_VARSAYILAN_UZAKLIK)

# Bir iliskili kavram, arama sonuclarina dahil edilmeden once en fazla
# bu kadar FARKLI sayfada gorulmus olmali. NEDEN: "Thread" gibi cok
# genel bir kavram, birbiriyle hicbir ilgisi olmayan sayfalarda
# gecebilir - boyle bir kavramla "iliskili" sayilan sonuc genelde
# GERCEKTEN alakali olmuyor, sadece isim eslesmesinden geliyor.
ILISKILI_KAVRAM_MAX_SAYFA = 2


async def _sorgudaki_kavrami_bul(db: AsyncSession, query: str) -> ConceptNode | None:
    """
    Sorgu metninde GECEN bir kavram var mi diye bakar - LLM cagirmadan,
    sadece yerel string ICERME kontroluyle. Hem standart isimler hem
    takma adlar arasinda, normalize edilmis haliyle karsilastirir.
    """
    normalize_sorgu = normalize_et(query)

    node_sonucu = await db.execute(select(ConceptNode))
    for node in node_sonucu.scalars().all():
        if node.normalize_isim and node.normalize_isim in normalize_sorgu:
            return node

    takma_sonucu = await db.execute(select(KavramTakmaAdi))
    for takma in takma_sonucu.scalars().all():
        if takma.normalize_takma_ad and takma.normalize_takma_ad in normalize_sorgu:
            node_sonucu = await db.execute(
                select(ConceptNode).where(ConceptNode.id == takma.concept_node_id)
            )
            return node_sonucu.scalars().first()

    return None


async def _kavram_kac_sayfada_goruluyor(db: AsyncSession, concept_node_id: int) -> int:
    """Verilen kavramin KAC FARKLI WikiPage'de goruldugunu sayar."""
    sonuc = await db.execute(
        select(SemanticUnit.page_id)
        .join(KavramGorulme, KavramGorulme.unit_id == SemanticUnit.id)
        .where(KavramGorulme.concept_node_id == concept_node_id)
        .distinct()
    )
    return len(sonuc.all())


async def _iliskili_kavramlari_bul(db: AsyncSession, node_id: int) -> list[tuple[ConceptNode, str]]:
    """
    Verilen kavrama ConceptRelation uzerinden (yon fark etmeksizin)
    BAGLI olan diger kavramlari, HANGI ILISKI TIPIYLE baglandiklarıyla
    birlikte getirir - cagiran taraf bu tipi _iliski_agirligi ile bir
    mesafeye cevirebilsin diye. ILISKILI_KAVRAM_MAX_SAYFA'dan fazla
    sayfada gorulen, cok genel/yaygin kavramlar HARIC tutulur.
    """
    iliski_sonucu = await db.execute(
        select(ConceptRelation).where(
            (ConceptRelation.kaynak_id == node_id) | (ConceptRelation.hedef_id == node_id)
        )
    )

    # Bir komsu kavrama BIRDEN FAZLA iliski turunden ulasilabilir (orn.
    # hem ONKOSUL hem ILGILI iliskisi olabilir) - bu durumda EN GUCLU
    # (en dusuk agirlikli) tipi tutuyoruz, arama sonucunda en iyi
    # sinyali kullanmak icin.
    komsu_id_to_en_guclu_tip: dict[int, str] = {}
    for iliski in iliski_sonucu.scalars().all():
        komsu_id = iliski.hedef_id if iliski.kaynak_id == node_id else iliski.kaynak_id
        mevcut_tip = komsu_id_to_en_guclu_tip.get(komsu_id)
        if mevcut_tip is None or _iliski_agirligi(iliski.iliski_tipi) < _iliski_agirligi(mevcut_tip):
            komsu_id_to_en_guclu_tip[komsu_id] = iliski.iliski_tipi

    if not komsu_id_to_en_guclu_tip:
        return []

    node_sonucu = await db.execute(select(ConceptNode).where(ConceptNode.id.in_(komsu_id_to_en_guclu_tip)))
    adaylar = node_sonucu.scalars().all()

    sonuc = []
    for aday in adaylar:
        sayfa_sayisi = await _kavram_kac_sayfada_goruluyor(db, aday.id)
        if sayfa_sayisi <= ILISKILI_KAVRAM_MAX_SAYFA:
            sonuc.append((aday, komsu_id_to_en_guclu_tip[aday.id]))

    return sonuc


async def _kavrama_bagli_unitleri_ekle(
    db: AsyncSession,
    concept_node_id: int,
    sonuclar_by_unit_id: dict,
    bulunma_sekli: str,
    uzaklik: float,
):
    """
    Verilen kavrama KavramGorulme uzerinden bagli tum SemanticUnit'leri
    bulur ve sonuclar_by_unit_id sozlugune ekler. Bir unit ZATEN
    embedding aramasindan gelmisse (gercek bir uzaklik skoruyla),
    UZERINE YAZMIYORUZ - embedding sonucu daha bilgilendirici.

    uzaklik: cagiran tarafin (hibrit_arama_yap) hesapladigi mesafe -
    dogrudan eslesen kavram icin DOGRUDAN_KAVRAM_UZAKLIGI, iliskili
    kavramlar icin ILISKI TIPINE gore _iliski_agirligi'nden gelen deger.
    """
    gorulme_sonucu = await db.execute(
        select(KavramGorulme.unit_id).where(KavramGorulme.concept_node_id == concept_node_id)
    )
    unit_idler = [satir[0] for satir in gorulme_sonucu.all()]

    if not unit_idler:
        return

    unit_sonucu = await db.execute(select(SemanticUnit).where(SemanticUnit.id.in_(unit_idler)))

    for unit in unit_sonucu.scalars().all():
        if unit.id not in sonuclar_by_unit_id:
            sonuclar_by_unit_id[unit.id] = {
                "unit_id": unit.id,
                "page_id": unit.page_id,
                "icerik": unit.icerik,
                "benzerlik_uzakligi": uzaklik,
                "bulunma_sekli": bulunma_sekli,
            }


async def hibrit_arama_yap(db: AsyncSession, query: str, limit: int) -> dict[int, dict]:
    """
    Embedding aramasini VE ontoloji-bazli aramayi (sorguda gecen kavram
    + ona iliskili kavramlar) BIRLESTIRIR. Hem /search hem /chat bu
    fonksiyonu kullanir - boylece ikisi de AYNI kalitede baglam bulur.

    Donen deger: unit_id -> {unit_id, page_id, icerik, benzerlik_
    uzakligi, bulunma_sekli} sozlugu. Cagiran taraf (search.py/chat.py)
    bunu kendi ihtiyacina gore (AramaSonucu listesi / baglam_parcalari
    listesi) sekillendirir.
    """
    # 1) Embedding araması yap (senkron fonksiyon, thread'e gonderiyoruz)
    ham_sonuclar = await asyncio.to_thread(benzer_parcalari_bul, query, limit)

    # unit_id -> sonuc sozlugu. Hem embedding hem ontoloji sonuclarini
    # AYNI sozlukte biriktiriyoruz ki bir parca iki kaynaktan da
    # gelse TEKRARLANMASIN (dedup).
    sonuclar_by_unit_id: dict[int, dict] = {}
    for sonuc in ham_sonuclar:
        sonuclar_by_unit_id[sonuc["unit_id"]] = {
            "unit_id": sonuc["unit_id"],
            "page_id": sonuc["page_id"],
            "icerik": sonuc["icerik"],
            "benzerlik_uzakligi": sonuc["benzerlik_uzakligi"],
            "bulunma_sekli": "embedding",
        }

    # 2) Ontoloji-bazli arama: sorguda gecen bir kavram var mi?
    dogrudan_kavram = await _sorgudaki_kavrami_bul(db, query)

    if dogrudan_kavram is not None:
        # 2a) Bu kavrama DOGRUDAN bagli parcalar
        await _kavrama_bagli_unitleri_ekle(
            db, dogrudan_kavram.id, sonuclar_by_unit_id,
            bulunma_sekli="dogrudan_kavram", uzaklik=DOGRUDAN_KAVRAM_UZAKLIGI,
        )

        # 2b) Bu kavramla ConceptRelation uzerinden ILISKILI kavramlara
        #     bagli parcalar - mesafe artik ILISKI TIPINE gore degisiyor
        #     (bkz. ILISKI_TIPI_UZAKLIGI), tum tipler icin sabit degil.
        #     bulunma_sekli'ne tipi de ekliyoruz ("iliskili_kavram:ONKOSUL"
        #     gibi) - hem hata ayiklarken hem arayuzde (Ara sekmesi)
        #     NEDEN bu sonucun geldigini gormek icin faydali.
        iliskili_kavramlar = await _iliskili_kavramlari_bul(db, dogrudan_kavram.id)
        for iliskili, iliski_tipi in iliskili_kavramlar:
            await _kavrama_bagli_unitleri_ekle(
                db, iliskili.id, sonuclar_by_unit_id,
                bulunma_sekli=f"iliskili_kavram:{iliski_tipi}",
                uzaklik=_iliski_agirligi(iliski_tipi),
            )

    return sonuclar_by_unit_id
