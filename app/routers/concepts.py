"""
Bir sayfadan KAVRAM ve ILISKI cikarma islemlerini yapan router.
LLM ile cikarim yapar (concept_extractor.py), sonra ontoloji kontrolu
ve deduplication (kavram_bul_veya_olustur) uygulayarak veritabanina
kaydeder.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import (
    SemanticUnit,
    ConceptNode,
    ConceptRelation,
    KavramTakmaAdi,
    OnerilenTur,
    KavramGorulme,
    KavramBirlesmesi,
)
from app.models.schemas import ExtractConceptsCevabi
from app.services.concept_extractor import kavram_cikar_batch, BatchCikarimSonucu, CikarimSonucu
from app.services.ontology import KAVRAM_TIPLERI, ILISKI_TIPLERI
from app.services.normalize import normalize_et
from app.embeddings.embedding_servisi import kavram_kaydet, benzer_kavram_bul, token_sayisi

router = APIRouter(prefix="/pages", tags=["Kavramlar"])

# Yeni bir kavram, mevcut hicbir kavrama ISIM olarak (normalize edilmis
# haliyle) tam uymuyorsa, embedding benzerligine bakiyoruz. Benzerlik
# bu esigin USTUNDEYSE (>=), iki kavram AYNI sayilip otomatik
# birlestiriliyor. Bu deger, kalibrasyon.py scripti ile gercek verilerle
# test edilerek 0.85 olarak belirlendi - bkz. proje notlari.
BENZERLIK_ESIGI = 0.85

# Buyuk sayfalarda (cok sayida SemanticUnit) TUM unit'leri TEK bir
# Gemini cagrisinda batch'lemek - gercek kullanimda 84 unit'lik bir
# PDF'te tek cagri 2+ dakika surdu, masaustu uygulamasinin (ve
# migrate_chunking_secici.py'nin) timeout'unu asti. Bu yuzden unit'leri
# bu TOKEN sinirini asmayacak ardisik gruplara ayirip HER GRUBU AYRI
# (ama PARALEL) bir Gemini cagrisinda isliyoruz - batch'lemenin
# faydasini (tek tek cagirmaktan cok daha az round-trip) korurken, tek
# bir cagrinin suresiz buyumesini onluyor.
KAVRAM_CIKARMA_GRUP_MAKS_TOKEN = 6000


def _unitleri_gruplara_ayir(unitler: list[SemanticUnit]) -> list[list[SemanticUnit]]:
    """
    Unit'leri, HER GRUBUN toplam icerik token'i KAVRAM_CIKARMA_GRUP_
    MAKS_TOKEN'i asmayacak sekilde ardisik (sirali) gruplara ayirir.
    Tek basina siniri asan bir unit (nadir ama olasi) KENDI grubuna
    yalniz konur - bolme/atlama yapilmiyor, sadece o unit tek basina
    gonderiliyor.
    """
    gruplar: list[list[SemanticUnit]] = []
    mevcut_grup: list[SemanticUnit] = []
    mevcut_grup_token = 0

    for unit in unitler:
        unit_token = token_sayisi(unit.icerik)

        if mevcut_grup and mevcut_grup_token + unit_token > KAVRAM_CIKARMA_GRUP_MAKS_TOKEN:
            gruplar.append(mevcut_grup)
            mevcut_grup = []
            mevcut_grup_token = 0

        mevcut_grup.append(unit)
        mevcut_grup_token += unit_token

    if mevcut_grup:
        gruplar.append(mevcut_grup)

    return gruplar


async def grubu_isle(grup: list[SemanticUnit]) -> BatchCikarimSonucu:
    """
    Bir unit grubunu kavram_cikar_batch ile isler. kavram_cikar_batch
    3 denemeden sonra hala basarisizsa (bkz. kendi @retry aciklamasi)
    hatayi BURAYA firlatir - biz de bu grubu bos gecip (o gruptaki
    unit'ler icin bos CikarimSonucu ile) TUM islemi cokertmeden devam
    ediyoruz. Boylece 10 gruptan biri Gemini'nin gecici yogunlugu
    yuzunden kalici basarisiz olsa bile, diger 9 grubun kavramlari
    kaybolmuyor.
    """
    try:
        return await asyncio.to_thread(kavram_cikar_batch, {u.id: u.icerik for u in grup})
    except Exception:
        return BatchCikarimSonucu(unit_sonuclari={
            u.id: CikarimSonucu(kavramlar=[], iliskiler=[])
            for u in grup
        })


async def kavram_bul_veya_olustur(
    db: AsyncSession,
    isim: str,
    tip: str,
    unit_id: int,
    takma_adlar: list[str],
) -> tuple[ConceptNode, bool]:
    """
    Verilen isimde bir kavram VAR MI diye kontrol eder, varsa onu
    kullanir, yoksa yenisini olusturur. Her durumda, bu kavramin bu
    unit_id'de GORULDUGUNU KavramGorulme tablosuna kaydeder - boylece
    ayni kavram birden fazla unit'te (ve dolayisiyla birden fazla
    sayfada) gorulebilir.
    """

    node = None

    # Aranacak ismin normalize edilmis hali - Turkce karakter ve
    # buyuk/kucuk harf farklarini yok sayarak karsilastirma yapmak icin.
    # Bkz. metin_yardimcilari.py normalize_et fonksiyonu.
    normalize_edilmis_isim = normalize_et(isim)

    # 1) Takma ad olarak var mi?
    # normalize_takma_ad sutunu sayesinde, "Kaan Aslan" ile "Kaan ASLAN"
    # gibi buyuk/kucuk harf farkli VE "Mühendislik" ile "Muhendislik"
    # gibi Turkce karakter farkli isimler de AYNI sayiliyor - cunku her
    # ikisinin de normalize_takma_ad degeri ayni ("kaan aslan", "muhendislik").
    takma_ad_sonucu = await db.execute(
        select(KavramTakmaAdi).where(KavramTakmaAdi.normalize_takma_ad == normalize_edilmis_isim)
    )
    takma_ad = takma_ad_sonucu.scalars().first()

    if takma_ad is not None:
        node_sonucu = await db.execute(
            select(ConceptNode).where(ConceptNode.id == takma_ad.concept_node_id)
        )
        node = node_sonucu.scalars().first()

    # 2) Takma ad olarak bulunamadiysa, standart isim olarak var mi?
    # Ayni mantik: normalize_isim sutunu uzerinden karsilastiriyoruz.
    if node is None:
        standart_sonuc = await db.execute(
            select(ConceptNode).where(ConceptNode.normalize_isim == normalize_edilmis_isim)
        )
        node = standart_sonuc.scalars().first()

    # 2.5) Hala bulunamadiysa - yani normalize edilmis ISIM eslesmesi de
    # yoksa - embedding benzerligine bakiyoruz. Bu, "Development Team"
    # ile "Development Takimi" gibi FARKLI KELIMELERLE yazilmis ama
    # ANLAMCA ayni olan kavramlari yakalamak icin (normalize_et sadece
    # yazim farklarini kapatir, kelime farklarini degil). Sadece AYNI
    # TIPTEKI kavramlarla karsilastiriyoruz (benzer_kavram_bul icinde
    # "tip" filtresi zaten uygulaniyor).
    if node is None:
        benzer_sonuc = benzer_kavram_bul(isim, tip, BENZERLIK_ESIGI)
        if benzer_sonuc is not None:
            node_sonucu = await db.execute(
                select(ConceptNode).where(ConceptNode.id == benzer_sonuc["node_id"])
            )
            node = node_sonucu.scalars().first()

            # Bu ismi (orn. "Development Takimi"), eslesilen node'a YENI
            # bir takma ad olarak kaydediyoruz. 1. ve 2. adimlar bu ismi
            # (normalize_edilmis_isim) ne takma addda ne standart isimde
            # bulamadi - yani burada zaten var olma ihtimali yok, tekrar
            # kontrol etmeye gerek yok. Boylece bir dahaki sefere bu isim
            # tekrar gecerse, pahali embedding aramasina gerek kalmadan
            # 1. adimdaki ucuz tam eslesmeyle bulunur.
            if node is not None:
                db.add(KavramTakmaAdi(
                    concept_node_id=node.id,
                    takma_ad=isim,
                    normalize_takma_ad=normalize_edilmis_isim,
                ))
                await db.flush()

    yeni_mi = False

    # 3) Hicbiri yoksa, yeni ConceptNode olustur
    if node is None:
        node = ConceptNode(
            standart_isim=isim,
            normalize_isim=normalize_edilmis_isim,
            tip=tip,
        )
        db.add(node)
        await db.flush()
        await db.refresh(node)
        yeni_mi = True

        # Yeni node'u Chroma'daki concept_names koleksiyonuna da ekle -
        # yoksa bir sonraki benzer kavram geldiginde bu node'la
        # karsilastirilamaz (embedding'i hic kaydedilmemis olur).
        kavram_kaydet(node.id, isim, tip)

        for takma_ad_ismi in takma_adlar:
            normalize_edilmis_takma_ad = normalize_et(takma_ad_ismi)
            var_mi_sonucu = await db.execute(
                select(KavramTakmaAdi).where(KavramTakmaAdi.normalize_takma_ad == normalize_edilmis_takma_ad)
            )
            zaten_var = var_mi_sonucu.scalars().first()

            if zaten_var is None:
                db.add(KavramTakmaAdi(
                    concept_node_id=node.id,
                    takma_ad=takma_ad_ismi,
                    normalize_takma_ad=normalize_edilmis_takma_ad,
                ))
                await db.flush()

    # 4) HER DURUMDA, bu kavramin bu unit'te GORULDUGUNU kaydet
    gorulme_sonucu = await db.execute(
        select(KavramGorulme).where(
            KavramGorulme.concept_node_id == node.id,
            KavramGorulme.unit_id == unit_id,
        )
    )
    var_olan_gorulme = gorulme_sonucu.scalars().first()

    if var_olan_gorulme is None:
        db.add(KavramGorulme(concept_node_id=node.id, unit_id=unit_id))

    return node, yeni_mi


async def kavramlari_uygula(db: AsyncSession, unitler: list[SemanticUnit]) -> tuple[int, int, int]:
    """
    Verilen unit'lerden LLM ile kavram ve iliski cikarir, ontoloji
    kontrolu + deduplication uygulayarak veritabanina EKLER - ama
    COMMIT ETMEZ, cagiran taraf kendi commit zamanlamasina karar verir
    (orn. sources.py'de baska islemlerle AYNI transaction'da commit
    edilebilsin diye).

    kavramlari_cikar route'u (manuel "Kavram Cikar" butonu) VE
    sources.py'deki otomatik yukleme akisi (PDF/markdown eklenince)
    BU FONKSIYONU PAYLASIR - ikisi de AYNI mantigi calistirir.

    Donen deger: (olusturulan_kavram_sayisi, olusturulan_iliski_sayisi, onerilen_yeni_tip_sayisi)
    """
    toplam_kavram = 0
    toplam_iliski = 0
    toplam_onerilen_tip = 0

    # Her unit icin ayri ayri LLM cagirmak yerine, TOKEN sinirina gore
    # gruplara ayirip HER GRUBU AYRI (ama PARALEL) bir batch cagrisinda
    # isliyoruz - bkz. KAVRAM_CIKARMA_GRUP_MAKS_TOKEN ve grubu_isle.
    # Boylece hem batch'lemenin faydasi (network round-trip azaltma)
    # korunuyor, hem buyuk sayfalarda (cok unit) TEK bir dev cagriya
    # donusmuyor, hem de bir grubun kalici basarisiz olmasi diger
    # gruplarin sonuclarini etkilemiyor.
    gruplar = _unitleri_gruplara_ayir(unitler)

    grup_sonuclari = await asyncio.gather(*[grubu_isle(grup) for grup in gruplar])

    batch_unit_sonuclari: dict[int, CikarimSonucu] = {}
    for grup_sonuc in grup_sonuclari:
        batch_unit_sonuclari.update(grup_sonuc.unit_sonuclari)

    for unit in unitler:
        cikarim = batch_unit_sonuclari[unit.id]

        isim_to_node = {}

        for kavram in cikarim.kavramlar:
            if kavram.tip not in KAVRAM_TIPLERI:
                onerilen_sonucu = await db.execute(
                    select(OnerilenTur).where(
                        OnerilenTur.kategori == "kavram",
                        OnerilenTur.onerilen_tip == kavram.tip,
                    )
                )
                var_olan_oneri = onerilen_sonucu.scalars().first()

                if var_olan_oneri is not None:
                    var_olan_oneri.kac_kere_onerildi += 1
                else:
                    db.add(OnerilenTur(
                        kategori="kavram",
                        onerilen_tip=kavram.tip,
                        ornek_kavram=kavram.isim,
                    ))
                    toplam_onerilen_tip += 1
                continue

            node, yeni_mi = await kavram_bul_veya_olustur(
                db, kavram.isim, kavram.tip, unit.id, kavram.takma_adlar
            )
            isim_to_node[kavram.isim] = node

            if yeni_mi:
                toplam_kavram += 1

        for iliski in cikarim.iliskiler:
            if iliski.iliski_tipi not in ILISKI_TIPLERI:
                onerilen_sonucu = await db.execute(
                    select(OnerilenTur).where(
                        OnerilenTur.kategori == "iliski",
                        OnerilenTur.onerilen_tip == iliski.iliski_tipi,
                    )
                )
                var_olan_oneri = onerilen_sonucu.scalars().first()

                if var_olan_oneri is not None:
                    var_olan_oneri.kac_kere_onerildi += 1
                else:
                    db.add(OnerilenTur(
                        kategori="iliski",
                        onerilen_tip=iliski.iliski_tipi,
                        ornek_kavram=f"{iliski.kaynak_isim} -> {iliski.hedef_isim}",
                    ))
                    toplam_onerilen_tip += 1
                continue

            kaynak_node = isim_to_node.get(iliski.kaynak_isim)
            hedef_node = isim_to_node.get(iliski.hedef_isim)

            if kaynak_node is None or hedef_node is None:
                continue

            db.add(ConceptRelation(
                kaynak_id=kaynak_node.id,
                hedef_id=hedef_node.id,
                iliski_tipi=iliski.iliski_tipi,
            ))
            toplam_iliski += 1

    return toplam_kavram, toplam_iliski, toplam_onerilen_tip


@router.post("/{sayfa_id}/extract-concepts", response_model=ExtractConceptsCevabi)
async def kavramlari_cikar(
    sayfa_id: int,
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Bir sayfanin tum SemanticUnit'lerinden LLM ile kavram ve iliski
    cikarir, ontoloji kontrolu + deduplication uygulayarak kaydeder.
    Asil is mantigi kavramlari_uygula'da - bu route sadece unit'leri
    cekip sonucu API semasina uygun hale getiriyor (PDF/markdown
    yuklerken OTOMATIK calisan akis da AYNI kavramlari_uygula'yi
    kullaniyor, bkz. sources.py).
    """
    sonuc = await db.execute(
        select(SemanticUnit).where(SemanticUnit.page_id == sayfa_id)
    )
    unitler = sonuc.scalars().all()

    if not unitler:
        raise HTTPException(
            status_code=404,
            detail="Bu sayfaya ait SemanticUnit bulunamadi - once /index cagirmalisin"
        )

    toplam_kavram, toplam_iliski, toplam_onerilen_tip = await kavramlari_uygula(db, unitler)
    await db.commit()

    return ExtractConceptsCevabi(
        sayfa_id=sayfa_id,
        olusturulan_kavram_sayisi=toplam_kavram,
        olusturulan_iliski_sayisi=toplam_iliski,
        onerilen_yeni_tip_sayisi=toplam_onerilen_tip,
    )