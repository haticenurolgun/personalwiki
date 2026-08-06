#bu dosya veritabanına async bağlanmamızı sağlayan altyapıyı kurar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.db_models import Base
from app.uygulama_yollari import yol

# yol("personalwiki.db"): CWD'ye gore "./personalwiki.db" DEGIL,
# uygulamanin TABAN dizinine gore MUTLAK bir yol (bkz.
# uygulama_yollari.py) - PyInstaller ile paketlenmis exe nereden
# calistirilirsa calistirilsin AYNI veritabanini bulsun diye. SQLite
# URL'i icin ters slash'lar (\) ileri slash'a (/) cevriliyor - Windows
# yollari SQLAlchemy'nin URL formatinda ters slash kabul etmiyor.
VERITABANI_URL = f"sqlite+aiosqlite:///{yol('personalwiki.db').replace(chr(92), '/')}"


# create_async_engine: veritabanina giden "baglanti havuzu"nu kurar.
# echo=True, SQLAlchemy calistirdigi HER SQL komutunu terminale
# yazdirir - ilk gelistirme asamasinda hata ayiklamak icin cok faydali,
# kapatabiliriz (echo=False)

engine = create_async_engine(VERITABANI_URL, echo=False)

# async_sessionmaker: her istek geldiginde YENI bir "oturum" (session)
# uretmemizi saglayan bir fabrika. expire_on_commit=False demek: commit
# yaptiktan sonra Python nesnelerimizin verisi "gecersiz" sayilmasin -
# yoksa commit sonrasi ayni nesneye tekrar erismek istedigimizde
# SQLAlchemy veritabanina gereksiz bir sorgu daha atar.
SessionYerel = async_sessionmaker(engine, expire_on_commit=False)


async def veritabanini_hazirla():
    """
    Uygulama ilk acildiginda calisir. db_models.py'de tanimli tum
    tablolarin (WikiPage, Source, vb.) veritabaninda VAR OLDUGUNDAN
    emin olur - yoksa olusturur, varsa hicbir sey yapmaz.
    """
    async with engine.begin() as baglanti:
        await baglanti.run_sync(Base.metadata.create_all)
        #Base.metadata.create_all "veritabanında olmayan tablo varsa oluştur" diyor.

        # create_all SADECE eksik TABLOLARI olusturur, VAR OLAN bir
        # tabloya SONRADAN eklenen SUTUNLARI eklemez. wiki_pages tablosu
        # zaten mevcut kullanicilarda VARDI (hatirlatma ozelligi
        # eklenmeden once) - o yuzden hatirlatma_tarihi/
        # hatirlatma_bildirildi_mi sutunlari yoksa burada ELLE (basit
        # bir ALTER TABLE ile) ekliyoruz. Alembic gibi tam bir migrasyon
        # araci bu projede zaten kullanilmiyor, tek eksik sutun icin
        # boyle bir bagimlilik eklemek yerine bu kucuk kontrol yeterli.
        sutunlar = await baglanti.run_sync(
            lambda sync_baglanti: [
                satir[1] for satir in sync_baglanti.execute(
                    text("PRAGMA table_info(wiki_pages)")
                ).fetchall()
            ]
        )
        if "hatirlatma_tarihi" not in sutunlar:
            await baglanti.execute(
                text("ALTER TABLE wiki_pages ADD COLUMN hatirlatma_tarihi DATETIME")
            )
        if "hatirlatma_bildirildi_mi" not in sutunlar:
            await baglanti.execute(
                text(
                    "ALTER TABLE wiki_pages ADD COLUMN "
                    "hatirlatma_bildirildi_mi BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        
        
async def veritabani_oturumu_getir():
    """
    FastAPI'nin "Depends()" mekanizmasiyla kullanilir. Her HTTP istegi
    geldiginde YENI bir veritabani oturumu acar, endpoint bitince
    OTOMATIK kapatir (async with sayesinde) - boylece oturumlar
    sizdirilmaz (leak olmaz).

    "yield" neden var, "return" degil?
       FastAPI bunu su sekilde kullanir: yield'e kadar olan kodu calistirir
      (session'i acar), session'i endpoint'e verir, endpoint islemini
      bitirince yield'den SONRAKI kodu calistirir (session'i kapatir).
      Yani "once ac, kullandir, sonra kapat" akisini tek fonksiyonda
      yazmamizi sagliyor.
    """
    async with SessionYerel() as oturum:
        yield oturum