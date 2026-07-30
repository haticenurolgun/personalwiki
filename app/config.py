
# config.py

# .env dosyasindaki ayarlari okuyan dosya.

from pydantic_settings import BaseSettings


class Ayarlar(BaseSettings):
    """
    .env dosyasindaki degiskenleri otomatik okur. Alan adi (GEMINI_API_KEY)
    .env dosyasindaki isimle AYNI olmali - pydantic-settings bunu otomatik
    eslestiriyor.
    """
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.5-flash"   # varsayilan deger

    class Config:
        env_file = ".env" #değerleri bu dosyadan çek demek.
        


ayarlar = Ayarlar()