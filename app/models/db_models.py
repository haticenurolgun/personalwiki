# Bu dosya, veritabanimizdaki TABLOLARI Python class'lari olarak tanimlar.
# SQLAlchemy bu class'lari okuyup arka planda gercek SQL komutlarina cevirir.

#toplam 10 tablo var

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey,Boolean, Float

from sqlalchemy.orm import declarative_base ,relationship


# Base, TUM tablo class'larimizin ortak atasi

Base = declarative_base() #bundan sonra yazılan her class X(Base):, otomatik olarak "bu bir tablo" diye SQLAlchemy'nin kayıt defterine giriyor

def su_anki_zaman():
    """
    Su anki tarih ve saati UTC (dunya standart saati) olarak dondurur.
    """
    return datetime.now(timezone.utc)


class WikiPage(Base):
    """
    Kullanicinin eklediği her bilgi kaynaginin (web sayfasi, PDF, not)
    dönüştüğü "wiki sayfasi". Projenin en temel tablosu.
    """
    
    __tablename__ = "wiki_pages"  # Veritabanindaki gercek tablo adi
    
    # id: her sayfanin benzersiz numarasi. primary_key=True -> bu sutun,
    # tablodaki satirlari ayirt eden "anahtar".
    id =Column(Integer, primary_key=True,index=True)
    
    # title: sayfanin basligi. nullable=False -> bu alan BOS OLAMAZ.
    title = Column(String(300), nullable=False)
    
    
    # content: sayfanin tam metni (markdown).
    content = Column(Text, nullable=False)
    
        # tags: etiketler, virgulle ayrilmis tek bir metin olarak (basitlik icin).
    # nullable=True -> bu alan BOS KALABILIR.
    tags = Column(Text, nullable=True)

    # kategori: classifier.py::sayfa_siniflandir'in sabit SAYFA_KATEGORILERI
    # listesinden sectigi deger (orn. "DERS_NOTU"). nullable=True - sayfa
    # eklendiginde otomatik dolmaz, POST /pages/{id}/classify ile ayrica
    # doldurulur. tags'tan FARKLI: tags kullanicinin kendi etiketleri,
    # kategori sistemin sabit listeden urettigi siniflandirma.
    kategori = Column(String(50), nullable=True)

      # Bir WikiPage'in birden fazla Source'u olabilir (1:N iliski).
    # cascade="all, delete-orphan" demek: bu sayfa silinirse, ona bagli
    # Source satirlari da OTOMATIK silinsin
    sources = relationship("Source", back_populates="page", cascade="all, delete-orphan")
    
    semantic_units = relationship("SemanticUnit", back_populates="page", cascade="all, delete-orphan")
    
    created_at = Column(DateTime, default=su_anki_zaman, nullable=False)
    updated_at = Column(DateTime, default=su_anki_zaman, onupdate=su_anki_zaman, nullable=False)

    def __repr__(self):
        # Bu fonksiyon sadece hata ayiklarken (debug) print ettigimizde
        # ekranda okunabilir bir cikti gormemizi sagliyor.
        return f"<WikiPage id={self.id} title={self.title}>"
    
    
class  Source(Base):
        
    """
    Bir WikiPage'in nereden geldigini tutan tablo.
    Ornek: "bu sayfa bir web sitesinden geldi", "bu sayfa bir PDF'ten geldi".
    """
    
    __tablename__ = "sources"
    
    id = Column(Integer, primary_key=True,index=True)
    
        # page_id: bu kaynagin HANGI WikiPage'e ait oldugunu gosteren
    # "yabanci anahtar" (foreign key). ForeignKey("wiki_pages.id") demek:
    # bu sutundaki deger, wiki_pages tablosundaki bir id ile ESLESMEK
    # ZORUNDA - rastgele bir sayi yazamayiz, gercekten var olan bir
    # sayfanin id'si olmali.
    
    page_id= Column(Integer, ForeignKey("wiki_pages.id"),nullable=False)
        
        # type: kaynagin turu. Su an 3 secenek olacak: "web", "pdf", "markdown"
    type=Column(String(50),nullable=False)
        
        # url: kaynak bir web sayfasiysa adresi burada tutulur, degilse bos kalir.
    url = Column(String(1000), nullable=True)
        
        # file_path: kaynak bir PDF'ten geldiyse dosya yolu burada tutulur.
    file_path = Column(String(1000), nullable=True)
        
    added_at = Column(DateTime, default=su_anki_zaman, nullable=False)

        # Bu Source'un ait oldugu WikiPage'e Python tarafindan erisebilmek icin:
        # kaynak.page -> o kaynagin bagli oldugu WikiPage nesnesini verir.
    page = relationship("WikiPage", back_populates="sources")

def __repr__(self):
        return f"<Source id={self.id} type={self.type}>"
    
    
    
    
class SemanticUnit(Base):
    """
    Bir WikiPage'in bolunmus HER BIR parcasini temsil eder.
    structural_parser.py (veya ileride semantic_splitter.py) bir metni
    boldugunde, her parca burada ayri bir satir olarak saklanir.
    """

    __tablename__ = "semantic_units"

    id = Column(Integer, primary_key=True, index=True)

    # Bu parca hangi WikiPage'e ait?
    page_id = Column(Integer, ForeignKey("wiki_pages.id"), nullable=False)

    # structural_parser.py'deki Parca ile birebir eslesen alanlar:
    baslik = Column(String(300), nullable=False)
    icerik = Column(Text, nullable=False)
    seviye = Column(Integer, nullable=False)

    # Bu parcanin sayfa icindeki SIRASINI tutuyoruz - ileride parcalari
    # dogru sirayla gostermek/islemek icin lazim olacak.
    sira = Column(Integer, nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    # WikiPage tarafina Python'dan erismek icin:
    page = relationship("WikiPage", back_populates="semantic_units")
    
    
    
    def __repr__(self):
        return f"<SemanticUnit id={self.id} baslik={self.baslik}>"
    
    
    
class ConceptNode(Base):
    """
    Bir metin parcasindan (SemanticUnit) cikarilan TEK BIR kavrami
    temsil eder. Ontolojideki KAVRAM_TIPLERI listesinden birine
    ait olmali (ornek: "1NF" -> tip="TERIM").
    """

    __tablename__ = "concept_nodes"

    id = Column(Integer, primary_key=True, index=True)


    # Kavramin kendisi (orn. "1NF", "Event Loop")
    standart_isim = Column(String(300), nullable=False)
    
    # standart_isim'in NORMALIZE EDILMIS hali - Turkce karakter ve
    # buyuk/kucuk harf farklarini yok sayarak karsilastirma yapabilmek
    # icin ayri bir sutunda saklaniyor (bkz. metin_yardimcilari.py
    # normalize_et fonksiyonu). Kullaniciya HICBIR ZAMAN gosterilmez,
    # SADECE arama/karsilastirma icin kullanilir.
    normalize_isim = Column(String(300), nullable=False, index=True)
    
    # Ontolojideki KAVRAM_TIPLERI listesinden biri olmali (orn. "TERIM")
    tip = Column(String(50), nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    # SemanticUnit tarafina Python'dan erismek icin

    takma_adlar = relationship("KavramTakmaAdi", back_populates="concept_node", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ConceptNode id={self.id} isim={self.standart_isim} tip={self.tip}>"
    
    
class ConceptRelation(Base):
    """
    Iki ConceptNode arasindaki YONLU iliskiyi temsil eder.
    Ornek: kaynak="1NF", iliski_tipi="ONKOSUL", hedef="2NF"
    -> "1NF, 2NF'nin onkosuludur" anlamina gelir.
    """

    __tablename__ = "concept_relations"

    id = Column(Integer, primary_key=True, index=True)

    # Iki ayri foreign key, AYNI tabloya (concept_nodes) isaret ediyor.
    # Bu yuzden SQLAlchemy'nin hangi foreign key'in hangi relationship'e
    # ait oldugunu anlayabilmesi icin foreign_keys parametresini ELLE
    # belirtmemiz gerekiyor (asagida relationship tanimlarinda gorecegiz).
    kaynak_id = Column(Integer, ForeignKey("concept_nodes.id"), nullable=False) #ilişkinin başladığı kavram
    hedef_id = Column(Integer, ForeignKey("concept_nodes.id"), nullable=False) #

    # Ontolojideki ILISKI_TIPLERI listesinden biri olmali (orn. "ONKOSUL")
    iliski_tipi = Column(String(50), nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    # Iki ayri relationship - biri "kaynak" tarafi, biri "hedef" tarafi.
    # foreign_keys=[kaynak_id] diyerek SQLAlchemy'ye "bu relationship,
    # kaynak_id sutununu kullanarak baglaniyor" diye ACIKCA soyluyoruz -
    # yoksa SQLAlchemy iki foreign key'den hangisini kullanacagini
    # bilemez, hata verir.
    kaynak = relationship("ConceptNode", foreign_keys=[kaynak_id])
    hedef = relationship("ConceptNode", foreign_keys=[hedef_id])

    def __repr__(self):
        return f"<ConceptRelation {self.kaynak_id} -{self.iliski_tipi}-> {self.hedef_id}>"
    
    
    
class OnerilenTur(Base):
    """
    LLM, ontolojide OLMAYAN bir kavram/iliski tipi onerdiginde buraya
    kaydedilir. Otomatik onaylanmaz - proje sahibi elle inceleyip
    ontolojiye eklemeye karar verebilir.
    """

    __tablename__ = "onerilen_turler"

    id = Column(Integer, primary_key=True, index=True)

    # "kavram" veya "iliski" - hangi listeye (KAVRAM_TIPLERI mi
    # ILISKI_TIPLERI mi) onerildigini ayirt etmek icin.
    kategori = Column(String(20), nullable=False)

    # Onerilen yeni tip ismi (orn. "DONANIM")
    onerilen_tip = Column(String(50), nullable=False)

    # Bu tipin onerilmesine sebep olan ornek kavram (orn. "GPU")
    ornek_kavram = Column(String(300), nullable=False)

    # Bu tip kac kere onerildi - ayni tip birden fazla kez onerilirse
    # sayaci artiracagiz, tekrar tekrar satir eklemek yerine.
    kac_kere_onerildi = Column(Integer, default=1, nullable=False)

    ilk_onerilme_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    def __repr__(self):
        return f"<OnerilenTur tip={self.onerilen_tip} sayisi={self.kac_kere_onerildi}>"
    
    
    
class KavramTakmaAdi(Base):
    """
    Bir ConceptNode'un ALTERNATIF isimlerini/kisaltmalarini tutar.
    Ornek: standart_isim="Birinci Normal Form" olan ConceptNode'un
    takma_ad="1NF" olan bir KavramTakmaAdi'si olabilir.
    unique=True sayesinde ayni takma ad İKI FARKLI kavrama
    baglanamaz - veritabani bunu garanti ediyor.
    """

    __tablename__ = "kavram_takma_adlari"

    id = Column(Integer, primary_key=True, index=True)
    concept_node_id = Column(Integer, ForeignKey("concept_nodes.id"), nullable=False)
    takma_ad = Column(String(300), nullable=False, unique=True)
    # takma_ad'in NORMALIZE EDILMIS hali - ConceptNode.normalize_isim
    # ile ayni mantik (bkz. metin_yardimcilari.py normalize_et).
    normalize_takma_ad = Column(String(300), nullable=False, index=True)
    concept_node = relationship("ConceptNode", back_populates="takma_adlar")

    def __repr__(self):
        return f"<KavramTakmaAdi takma_ad={self.takma_ad}>"
    
    
    
class SayfaBaglantisi(Base):
    """
    Katman 2 (global graph) icin: iki WikiPage'in ORTAK bir kavram
    paylastigini gosteren tablo. Anlik hesaplanmaz - global_graf_
    yeniden_hesapla() fonksiyonu cagrildiginda tamamen silinip
    sifirdan yeniden kurulur.
    """

    __tablename__ = "sayfa_baglantilari"

    id = Column(Integer, primary_key=True, index=True)

    sayfa_id_1 = Column(Integer, ForeignKey("wiki_pages.id"), nullable=False)
    sayfa_id_2 = Column(Integer, ForeignKey("wiki_pages.id"), nullable=False)

    # Hangi kavram uzerinden baglandiklarini da saklıyoruz - kullaniciya
    # "bu iki sayfa X kavramindan dolayi baglantili" diye gosterebiliriz
    ortak_kavram_ismi = Column(String(300), nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    def __repr__(self):
        return f"<SayfaBaglantisi {self.sayfa_id_1}-{self.sayfa_id_2} kavram={self.ortak_kavram_ismi}>"
    
    
    
class KavramGorulme(Base):
    """
    Bir ConceptNode'un HANGI SemanticUnit'lerde gorulduğunu tutan
    ARA TABLO (junction table). Coktan-coga iliskiyi mumkun kilar:
    bir kavram birden fazla unit'te gorulebilir, bir unit'te birden
    fazla kavram cikarilabilir.
    """

    __tablename__ = "kavram_gorulmeler"

    id = Column(Integer, primary_key=True, index=True)
    concept_node_id = Column(Integer, ForeignKey("concept_nodes.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("semantic_units.id"), nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    def __repr__(self):
        return f"<KavramGorulme concept_node_id={self.concept_node_id} unit_id={self.unit_id}>"
    
    
class KavramBirlesmesi(Base):
    """
        Otomatik dedup sistemi iki ConceptNode'u AYNI kavram sayip
        birlestirdiginde buraya bir kayit dusuyor. Bu tablo sayesinde
        kullanici, yanlislikla birlestirilen bir kavrami GERI ALABILIR
        (undo).

        Birlestirme mantigi: "silinen_node", "hedef_node"ye eritiliyor -
        yani silinen_node'un tum KavramGorulme/ConceptRelation/KavramTakmaAdi
        kayitlari hedef_node'a tasiniyor, sonra silinen_node veritabanindan
        siliniyor. Bu kayit, silinen_node'un ESKI HALINI (ismi, tipi) sakliyor
        ki undo yapildiginda node'u orijinal bilgileriyle yeniden olusturabilelim.
    """

    __tablename__ = "kavram_birlesmeleri"

    id = Column(Integer, primary_key=True, index=True)

    # Silinen (eritilen) kavramin ESKI id'si - artik veritabaninda
    # bu id'de bir ConceptNode YOK (silindi), ama undo'da referans
    # olarak faydali.
    silinen_node_id = Column(Integer, nullable=False)

    # Silinen kavramin undo icin gereken orijinal bilgileri - bunlar
    # olmadan, node silindikten sonra "eskiden ismi neydi" bilemeyiz.
    silinen_standart_isim = Column(String(300), nullable=False)
    silinen_tip = Column(String(50), nullable=False)

    # Hangi kavrama birlestirildi - bu node HALA veritabaninda var.
    hedef_node_id = Column(Integer, ForeignKey("concept_nodes.id"), nullable=False)

    # Bu iki kavram hangi benzerlik skoruyla eslesti (0.0 - 1.0 arasi).
    # Kalibrasyon ve seffaflik icin - "neden bunlar birlestirildi"
    # sorusuna cevap verir.
    benzerlik_skoru = Column(Float, nullable=False)

    # Bu birlesme geri alindi mi? Alindiysa tekrar undo edilmeye
    # calisilmasin diye.
    geri_alindi_mi = Column(Boolean, default=False, nullable=False)

    olusturulma_tarihi = Column(DateTime, default=su_anki_zaman, nullable=False)

    hedef_node = relationship("ConceptNode")

    def __repr__(self):
        return f"<KavramBirlesmesi silinen={self.silinen_standart_isim} -> hedef_id={self.hedef_node_id}>"