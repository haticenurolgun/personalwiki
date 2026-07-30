"""
ontology.py

Ontoloji ve kavram grafigi verisinin SAGLIK durumunu kontrol eden
GECICI/TESHIS amacli endpoint'leri barindirir. Bu router, kalici bir
kullanici ozelligi degil - hibrit arama gibi kavram grafigine bagimli
yeni ozellikler eklemeden ONCE, mevcut verinin ne durumda oldugunu
gormek icin kullanilir.
"""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import veritabani_oturumu_getir
from app.models.db_models import ConceptNode, ConceptRelation, OnerilenTur

router = APIRouter(prefix="/ontology", tags=["Ontoloji"])

# Bir kavramin "asiri baglantili hub" sayilmasi icin gereken minimum
# iliski sayisi - bu esigin uzerindeki kavramlar, muhtemelen dedup/
# prompt sorunundan kaynaklanan "sahte merkez" olabilir (orn. her
# sayfada tekrar eden bir yazar/kaynak adi gibi).
HUB_ESIGI = 15


@router.get("/saglik-kontrolu")
async def saglik_kontrolu(
    db: AsyncSession = Depends(veritabani_oturumu_getir),
):
    """
    Kavram grafiginin genel saglik durumunu ozetler:
    1) En sik tekrar eden standart_isim'ler (potansiyel duplicate/dedup sorunu)
    2) Hic iliskisi olmayan (izole) ConceptNode sayisi
    3) Ontoloji disi onerilen tiplerin listesi (OnerilenTur)
    4) ASIRI baglantili "hub" kavramlar (muhtemelen yanlis/anlamsiz
       tekrar eden iliskiler yuzunden olusmus sahte merkezler)
    """

    # ------------------------------------------------------------
    # 1) AYNI ISIMDE BIRDEN FAZLA ConceptNode var mi?
    # ------------------------------------------------------------
    tekrar_eden_isimler_sonucu = await db.execute(
        select(ConceptNode.standart_isim, func.count(ConceptNode.id).label("adet"))
        .group_by(ConceptNode.standart_isim)
        .having(func.count(ConceptNode.id) > 1)
        .order_by(func.count(ConceptNode.id).desc())
    )
    tekrar_eden_isimler = [
        {"isim": isim, "adet": adet}
        for isim, adet in tekrar_eden_isimler_sonucu.all()
    ]

    # ------------------------------------------------------------
    # 2) IZOLE (hic iliskisi olmayan) ConceptNode sayisi
    # ------------------------------------------------------------
    tum_node_sonucu = await db.execute(
        select(ConceptNode.id, ConceptNode.standart_isim, ConceptNode.tip)
    )
    tum_nodelar = tum_node_sonucu.all()
    tum_node_idleri = set(row[0] for row in tum_nodelar)

    # ------------------------------------------------------------
    # Butun iliskileri TEK SEFERDE cekiyoruz - hem izole kontrolu
    # hem hub kontrolu icin ayni veriyi kullanacagiz.
    # ------------------------------------------------------------
    iliski_sonucu = await db.execute(
        select(ConceptRelation.kaynak_id, ConceptRelation.hedef_id)
    )
    tum_iliskiler = iliski_sonucu.all()

    # Her node'un KAC iliskiye dahil oldugunu sayan bir Counter -
    # hem kaynak hem hedef tarafinda gecmis olmasi sayiliyor.
    node_iliski_sayaci = Counter()
    iliskili_node_idleri = set()

    for kaynak_id, hedef_id in tum_iliskiler:
        node_iliski_sayaci[kaynak_id] += 1
        node_iliski_sayaci[hedef_id] += 1
        iliskili_node_idleri.add(kaynak_id)
        iliskili_node_idleri.add(hedef_id)

    izole_node_idleri = tum_node_idleri - iliskili_node_idleri

    node_id_to_detay = {
        node_id: {"id": node_id, "isim": isim, "tip": tip}
        for node_id, isim, tip in tum_nodelar
    }

    izole_node_detaylari = [
        node_id_to_detay[node_id]
        for node_id in izole_node_idleri
        if node_id in node_id_to_detay
    ]

    # ------------------------------------------------------------
    # 3) Ontoloji disi onerilen tipler
    # ------------------------------------------------------------
    onerilen_sonucu = await db.execute(
        select(OnerilenTur).order_by(OnerilenTur.kac_kere_onerildi.desc())
    )
    onerilen_turler = onerilen_sonucu.scalars().all()
    onerilen_tur_listesi = [
        {
            "kategori": oneri.kategori,
            "onerilen_tip": oneri.onerilen_tip,
            "ornek_kavram": oneri.ornek_kavram,
            "kac_kere_onerildi": oneri.kac_kere_onerildi,
        }
        for oneri in onerilen_turler
    ]

    # ------------------------------------------------------------
    # 4) ASIRI BAGLANTILI "HUB" kavramlar
    # ------------------------------------------------------------
    # HUB_ESIGI'nin uzerinde iliskiye sahip kavramlari bul - bunlar
    # muhtemelen "her sayfada tekrar eden bir yazar/kaynak adi" gibi
    # organik olmayan, sahte merkez kavramlardir.
    hub_kavramlar = []
    for node_id, iliski_sayisi in node_iliski_sayaci.most_common():
        if iliski_sayisi < HUB_ESIGI:
            break   # most_common() zaten azalan sirada, esigin altina inince dur
        if node_id in node_id_to_detay:
            hub_kavramlar.append({
                **node_id_to_detay[node_id],
                "iliski_sayisi": iliski_sayisi,
            })

    # ------------------------------------------------------------
    # Ozet sayilar
    # ------------------------------------------------------------
    return {
        "ozet": {
            "toplam_kavram_sayisi": len(tum_node_idleri),
            "toplam_iliski_sayisi": len(tum_iliskiler),
            "tekrar_eden_isim_grubu_sayisi": len(tekrar_eden_isimler),
            "izole_kavram_sayisi": len(izole_node_idleri),
            "onerilen_yeni_tip_sayisi": len(onerilen_tur_listesi),
            "hub_kavram_sayisi": len(hub_kavramlar),
        },
        "tekrar_eden_isimler": tekrar_eden_isimler,
        "izole_kavramlar": izole_node_detaylari,
        "onerilen_turler": onerilen_tur_listesi,
        "hub_kavramlar": hub_kavramlar,
    }