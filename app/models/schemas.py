"""
bu Bu dosya, API'ye GELEN ve API'DEN GIDEN verinin sekillerini tanimlar.
endpoint'e gelen veri nasıl görünecek? tanımlandığı yer
"""

from datetime import datetime

from pydantic import BaseModel


class MarkdownEkle(BaseModel):
    
    """
    POST /sources/markdown endpoint'ine gonderilmesi gereken govde.
    Kullanici bize sadece baslik ve markdown metnini gonderir - id, 
    created_at gibi alanlari GONDERMEZ, onlari veritabani kendisi uretir.
    """
    
    title: str
    content: str
    tags: str | None = None  # opsiyonel alan, gonderilmezse None olur
    
    
class WikipageCevap(BaseModel):
    """
    API'nin GERI DONDURDUGU sayfa bilgisi. Veritabanindaki WikiPage
    nesnesini, disariya gonderilecek JSON'a cevirmek icin kullanilir.
    """
    
    id: int
    title: str
    content: str
    tags: str | None
    kategori: str | None  # classifier.py'nin sectigi sabit kategori, yoksa None
    created_at: datetime  # sayfa ne zaman eklendi - "hatirlama" sorulari icin


    class Config:
        from_attributes= True
        
    # Bu ayar, Pydantic'e "SQLAlchemy nesnelerinden de veri
    # okuyabilirsin" demek. Normalde Pydantic sadece dict/JSON
    # bekler, ama bizim elimizde bir WikiPage NESNESI var (sozluk
    # degil) - bu ayar olmadan Pydantic o nesneyi okuyamaz.
    
    
    
class IndexCevabi(BaseModel):
    """
    POST /pages/{id}/index endpoint'inin donecegi cevap.
    """
    sayfa_id: int
    olusturulan_parca_sayisi: int
    
    
class AramaSonucu(BaseModel):
    """
    Tek bir arama sonucunu temsil eder - hem ICERIK (SemanticUnit)
    hem de HANGI SAYFAYA ait oldugu bilgisini birlikte tasir.
    """
    unit_id: int
    icerik: str
    page_id: int
    sayfa_basligi: str
    benzerlik_uzakligi: float
    # Bu sonuc NASIL bulundu: "embedding" (vektor benzerligi),
    # "dogrudan_kavram" (sorguda gecen bir ConceptNode'a bagli) ya da
    # "iliskili_kavram" (o kavrama ConceptRelation ile bagli baska bir
    # kavrama bagli). embedding disindakiler icin benzerlik_uzakligi
    # GERCEK bir kozinus uzakligi degil, sabit bir yer tutucudur.
    bulunma_sekli: str
    
    
class ChatIstegi(BaseModel):
    """
    POST /chat endpoint'ine gonderilen govde.
    """
    soru: str
    limit: int = 5   # kac tane baglam parcasi kullanilacak

    
class ChatCevabi(BaseModel):
    """
    POST /chat endpoint'inin donecegi cevap.
    """
    cevap: str
    kullanilan_kaynaklar: list[str]   # hangi sayfa basliklarindan yararlandi
    
    
class ExtractConceptsCevabi(BaseModel):
    """
    POST /pages/{id}/extract-concepts endpoint'inin donecegi cevap.
    """
    sayfa_id: int
    olusturulan_kavram_sayisi: int
    olusturulan_iliski_sayisi: int
    onerilen_yeni_tip_sayisi: int


class SiniflandirmaCevabi(BaseModel):
    """
    POST /pages/{id}/classify endpoint'inin donecegi cevap.
    """
    sayfa_id: int
    kategori: str


class KategoriGuncelle(BaseModel):
    """
    PUT /pages/{id}/kategori endpoint'ine gonderilmesi gereken govde.
    Kullanicinin KENDI yazdigi, classifier.py'deki SAYFA_KATEGORILERI
    listesiyle SINIRLI OLMAYAN serbest bir kategori metni.
    """
    kategori: str



class GraphKavram(BaseModel):
    id: int
    standart_isim: str
    tip: str


class GraphIliski(BaseModel):
    kaynak_id: int
    hedef_id: int
    iliski_tipi: str


class SayfaGrafiCevabi(BaseModel):
    sayfa_id: int
    kavramlar: list[GraphKavram]
    iliskiler: list[GraphIliski]
    
    
    
    
class GlobalGrafYenidenHesaplaCevabi(BaseModel):
    olusturulan_baglanti_sayisi: int


class GlobalGrafSayfa(BaseModel):
    id: int
    title: str


class GlobalGrafBaglanti(BaseModel):
    sayfa_id_1: int
    sayfa_id_2: int
    ortak_kavram_ismi: str


class GlobalGrafCevabi(BaseModel):
    sayfalar: list[GlobalGrafSayfa]
    baglantilar: list[GlobalGrafBaglanti]