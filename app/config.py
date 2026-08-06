
# config.py

# .env dosyasindaki ayarlari okuyan dosya.

from pydantic_settings import BaseSettings

from app.uygulama_yollari import yol


class Ayarlar(BaseSettings):
    """
    .env dosyasindaki degiskenleri otomatik okur. Alan adi (GEMINI_API_KEY)
    .env dosyasindaki isimle AYNI olmali - pydantic-settings bunu otomatik
    eslestiriyor.
    """
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.5-flash"   # varsayilan deger

    class Config:
        # yol(".env"): CWD'ye degil, uygulamanin TABAN dizinine gore
        # (bkz. uygulama_yollari.py) - PyInstaller ile paketlenmis exe
        # nereden calistirilirsa calistirilsin AYNI .env'i bulsun diye.
        env_file = yol(".env")
        


ayarlar = Ayarlar()