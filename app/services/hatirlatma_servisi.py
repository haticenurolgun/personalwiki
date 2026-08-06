"""
hatirlatma_servisi.py

WikiPage.hatirlatma_tarihi'ni PERIYODIK olarak tarayip zamani gelen
(gecmis VE henuz bildirilmemis) hatirlatmalar icin Windows masaustu
bildirimi (toast) gonderen arka plan servisi.

NEDEN AYRI BIR ARKA PLAN DONGUSU (HTTP istegi degil): hatirlatmalar,
kullanici uygulamayla ETKILESIME GECMEDEN de (orn. uygulama acik,
kullanici baska bir seyle ugrasirken) zamani gelince bildirilmeli.
Bu yuzden main.py, uygulama basladiginda bu donguyu bir arka plan
GOREVI (asyncio task) olarak baslatiyor - HTTP endpoint'lerinden
BAGIMSIZ calisir.

ONEMLI SINIRLAMA: bildirim SADECE uygulama/sunucu ACIKKEN calisirken
tetiklenir - sunucu kapaliyken zamani gelen bir hatirlatma, sunucu
tekrar acildiginda (bir SONRAKI tarama turunda) bildirilir, gecmis
degil.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from winotify import Notification

from app.database import SessionYerel
from app.models.db_models import WikiPage

# Kac saniyede bir yeni hatirlatma taramasi yapilacak. 60 saniye,
# "bildirim zamani geldikten en fazla 1 dakika sonra bildirilir"
# demek - bir hatirlatma icin pratikte yeterince yakin, sunucuyu
# gereksiz yere yormayacak kadar da seyrek.
TARAMA_ARALIGI_SANIYE = 60


async def _hatirlatmalari_kontrol_et() -> None:
    """Zamani gelmis, henuz bildirilmemis hatirlatmalari bulup bildirir."""
    async with SessionYerel() as db:
        simdi = datetime.now(timezone.utc)
        sonuc = await db.execute(
            select(WikiPage).where(
                WikiPage.hatirlatma_tarihi.is_not(None),
                WikiPage.hatirlatma_tarihi <= simdi,
                WikiPage.hatirlatma_bildirildi_mi.is_(False),
            )
        )
        zamani_gelen_sayfalar = sonuc.scalars().all()

        for sayfa in zamani_gelen_sayfalar:
            # winotify senkron/bloklayici calisiyor (Windows COM
            # cagrisi) - to_thread'e atmiyoruz cunku bu zaten arka
            # plan gorevinin KENDI dongusu, event loop'u HTTP
            # isteklerinden ayri bir yerde bloklamasi sorun degil;
            # ama yine de kisa surmesi (<1sn) beklenir.
            Notification(
                app_id="PersonalWiki",
                title="Hatirlatma",
                msg=sayfa.title,
            ).show()

            sayfa.hatirlatma_bildirildi_mi = True

        if zamani_gelen_sayfalar:
            await db.commit()


async def hatirlatma_dongusunu_calistir() -> None:
    """
    main.py'nin startup'inda asyncio.create_task ile baslatilan
    SONSUZ dongu - her TARAMA_ARALIGI_SANIYE'de bir kontrol yapar.
    Uygulama kapanirken main.py bu task'i iptal eder (asyncio.
    CancelledError burada YAKALANMIYOR - iptali normal sekilde
    yukari firlatip donguden temiz cikmasina izin veriyoruz).
    """
    while True:
        await _hatirlatmalari_kontrol_et()
        await asyncio.sleep(TARAMA_ARALIGI_SANIYE)
