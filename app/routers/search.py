# =============================================================================
# search.py
# =============================================================================
# Kullanicinin arama kutusundan sorgu gonderdigi router. Iki kaynaktan
# gelen sonuclari BIRLESTIRIYOR:
#   1) Embedding araması (mevcut, degismedi) - anlamca yakin parcalar
#   2) Ontoloji-bazli arama (YENI) - sorguda GECEN bir kavram varsa,
#      o kavrama VE ona ILISKILI kavramlara bagli parcalar da eklenir
# Boylece "1NF nedir" gibi bir sorguda, embedding'in kacirabilecegi ama
# kavram grafiginde AÇIKÇA bagli olan parcalar da garantiye alinmis olur.
# =============================================================================

import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.database import veritabani_oturumu_getir
from app.models.db_models import (
    WikiPage,
    SemanticUnit,
    ConceptNode,
    ConceptRelation,
    KavramTakmaAdi,
    KavramGorulme,
)
from app.models.schemas import AramaSonucu
from app.embeddings.embedding_servisi import benzer_parcalari_bul
from app.services.normalize import normalize_et

router = APIRouter(prefix="/search", tags=["Arama"])

# Ontoloji-bazli sonuclar icin GERCEK bir kozinus uzakligi yok (embedding
# aramasi yapilmadi) - bu yuzden sabit, "cok yakin" anlamina gelen yer
# tutucu degerler kullaniyoruz. Dogrudan eslesen kavram, iliskili
# kavramdan daha "kesin" sayildigi icin daha kucuk (daha yakin) bir
# deger aliyor.
DOGRUDAN_KAVRAM_UZAKLIGI = 0.0
ILISKILI_KAVRAM_UZAKLIGI = 0.15


async def _sorgudaki_kavrami_bul(db: AsyncSession, query: str) -> ConceptNode | None:
    """
    Sorgu metninde GECEN bir kavram var mi diye bakar - LLM cagirmadan,
    sadece yerel string ICERME kontroluyle. Hem standart isimler hem
    takma adlar arasinda, normalize edilmis haliyle karsilastirir.

    Ornek: query="1NF nedir" -> normalize="1nf nedir". ConceptNode'un
    normalize_isim'i "1nf" bu sorgunun ICINDE geciyorsa, eslesme
    bulunmus sayilir.

    NOT: Veritabanindaki TUM kavram/takma-ad satirlarini teker teker
    kontrol ediyoruz (SQL'de degil, Python'da). Kisisel bir wiki icin
    (yuzlerce kavram) bu performans sorunu yaratmaz - cok daha buyuk
    bir veri setinde SQL LIKE sorgusuna gecmek gerekebilir.
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


# Bir iliskili kavram, arama sonuclarina dahil edilmeden once en fazla
# bu kadar FARKLI sayfada gorulmus olmali. NEDEN: "Thread" gibi cok
# genel bir kavram, birbiriyle hicbir ilgisi olmayan sayfalarda
# (orn. bir async-programlama notu VE alakasiz bir isletim sistemi
# ders notu) gecebilir - boyle bir kavramla "iliskili" sayilan sonuc
# genelde GERCEKTEN alakali olmuyor, sadece isim eslesmesinden geliyor.
# ontology.py'deki HUB_ESIGI ile ayni fikir (asiri baglantili kavramlari
# supheyle karsila), burada "iliski sayisi" yerine "sayfa sayisi"
# uzerinden uygulaniyor - arama icin daha dogrudan bir sinyal.
ILISKILI_KAVRAM_MAX_SAYFA = 2


async def _kavram_kac_sayfada_goruluyor(db: AsyncSession, concept_node_id: int) -> int:
    """Verilen kavramin KAC FARKLI WikiPage'de goruldugunu sayar."""
    sonuc = await db.execute(
        select(SemanticUnit.page_id)
        .join(KavramGorulme, KavramGorulme.unit_id == SemanticUnit.id)
        .where(KavramGorulme.concept_node_id == concept_node_id)
        .distinct()
    )
    return len(sonuc.all())


async def _iliskili_kavramlari_bul(db: AsyncSession, node_id: int) -> list[ConceptNode]:
    """
    Verilen kavrama ConceptRelation uzerinden (yon fark etmeksizin,
    kaynak ya da hedef olarak) BAGLI olan diger kavramlari getirir -
    ama ILISKILI_KAVRAM_MAX_SAYFA'dan fazla sayfada gorulen, yani cok
    genel/yaygin kavramlari HARIC tutar.
    """
    iliski_sonucu = await db.execute(
        select(ConceptRelation).where(
            (ConceptRelation.kaynak_id == node_id) | (ConceptRelation.hedef_id == node_id)
        )
    )
    iliskili_id_ler = set()
    for iliski in iliski_sonucu.scalars().all():
        if iliski.kaynak_id == node_id:
            iliskili_id_ler.add(iliski.hedef_id)
        else:
            iliskili_id_ler.add(iliski.kaynak_id)

    if not iliskili_id_ler:
        return []

    node_sonucu = await db.execute(select(ConceptNode).where(ConceptNode.id.in_(iliskili_id_ler)))
    adaylar = node_sonucu.scalars().all()

    sonuc = []
    for aday in adaylar:
        sayfa_sayisi = await _kavram_kac_sayfada_goruluyor(db, aday.id)
        if sayfa_sayisi <= ILISKILI_KAVRAM_MAX_SAYFA:
            sonuc.append(aday)

    return sonuc


async def _kavrama_bagli_unitleri_ekle(
    db: AsyncSession,
    concept_node_id: int,
    sonuclar_by_unit_id: dict,
    bulunma_sekli: str,
):
    """
    Verilen kavrama KavramGorulme uzerinden bagli tum SemanticUnit'leri
    bulur ve sonuclar_by_unit_id sozlugune ekler. Bir unit ZATEN
    embedding aramasindan gelmisse (gercek bir uzaklik skoruyla),
    UZERINE YAZMIYORUZ - embedding sonucu daha bilgilendirici.
    """
    gorulme_sonucu = await db.execute(
        select(KavramGorulme.unit_id).where(KavramGorulme.concept_node_id == concept_node_id)
    )
    unit_idler = [satir[0] for satir in gorulme_sonucu.all()]

    if not unit_idler:
        return

    unit_sonucu = await db.execute(select(SemanticUnit).where(SemanticUnit.id.in_(unit_idler)))

    uzaklik = DOGRUDAN_KAVRAM_UZAKLIGI if bulunma_sekli == "dogrudan_kavram" else ILISKILI_KAVRAM_UZAKLIGI

    for unit in unit_sonucu.scalars().all():
        if unit.id not in sonuclar_by_unit_id:
            sonuclar_by_unit_id[unit.id] = {
                "unit_id": unit.id,
                "page_id": unit.page_id,
                "icerik": unit.icerik,
                "benzerlik_uzakligi": uzaklik,
                "bulunma_sekli": bulunma_sekli,
            }


@router.get("", response_model=list[AramaSonucu])
async def Ara(
    query: str,
    limit: int = 4,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Query: kullanicinin arama metni (query parametresi)\n

    limit: embedding aramasindan kac sonuc alinacak (ontoloji-bazli
    sonuclar bu sayaca dahil degil - bir kavram bulunursa, ona bagli
    TUM parcalar eklenir)
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
            db, dogrudan_kavram.id, sonuclar_by_unit_id, bulunma_sekli="dogrudan_kavram"
        )

        # 2b) Bu kavramla ConceptRelation uzerinden ILISKILI kavramlara
        #     bagli parcalar
        iliskili_kavramlar = await _iliskili_kavramlari_bul(db, dogrudan_kavram.id)
        for iliskili in iliskili_kavramlar:
            await _kavrama_bagli_unitleri_ekle(
                db, iliskili.id, sonuclar_by_unit_id, bulunma_sekli="iliskili_kavram"
            )

    # 3) Ilgili TUM sayfalari tek sorguyla getir (sayfa basligi icin).
    page_idler = list({sonuc["page_id"] for sonuc in sonuclar_by_unit_id.values()})
    sayfa_sonucu = await db.execute(select(WikiPage).where(WikiPage.id.in_(page_idler)))
    sayfalar = sayfa_sonucu.scalars().all()
    baslik_sozlugu = {sayfa.id: sayfa.title for sayfa in sayfalar}

    # 4) Sonuclari AramaSonucu semasina uygun hale getir.
    zenginlestirilmis_sonuclar = []
    for sonuc in sonuclar_by_unit_id.values():
        zenginlestirilmis_sonuclar.append(AramaSonucu(
            unit_id=sonuc["unit_id"],
            icerik=sonuc["icerik"],
            page_id=sonuc["page_id"],
            sayfa_basligi=baslik_sozlugu.get(sonuc["page_id"], "Bilinmeyen Sayfa"),
            benzerlik_uzakligi=sonuc["benzerlik_uzakligi"],
            bulunma_sekli=sonuc["bulunma_sekli"],
        ))

    return zenginlestirilmis_sonuclar
