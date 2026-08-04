"""
desktop_demo.py

PersonalWiki AI'nin gercek bir masaustu uygulamasi gibi calisabildigini
gostermek icin kucuk bir PyQt6 demo'su. Backend'i (FastAPI) DEGISTIRMEZ -
sadece http://127.0.0.1:8000 uzerinde CALISAN bir sunucuya HTTP
istekleriyle baglanan bir istemci (client) penceresidir.

ONEMLI: Bu uygulamayi calistirmadan ONCE backend'in ayri bir terminalde
calisiyor olmasi gerekir:
    uvicorn main:app --reload

Calistirmak icin (venv aktifken, ayri bir terminalde):
    python desktop_demo.py
"""

import html
import os
import sys

import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QDialog,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFileDialog,
    QMessageBox,
)

BACKEND_URL = "http://127.0.0.1:8000"


def http_hata_mesaji(hata: requests.exceptions.RequestException) -> str:
    """
    requests bir HTTP hatasi (orn. 422, 400, 500) firlattiginda,
    varsayilan hata metni sadece "422 Client Error: Unprocessable
    Entity for url: ..." gibi genel bir ozet veriyor - backend'in
    GERCEK sebep aciklamasini (FastAPI'nin standart {"detail": "..."}
    govdesi) GOSTERMIYOR. Bu fonksiyon, mumkunse o "detail" alanini
    cikarip kullaniciya asil sebebi gosteriyor.
    """
    yanit = getattr(hata, "response", None)
    if yanit is not None:
        try:
            detay = yanit.json().get("detail")
            if detay:
                return str(detay)
        except ValueError:
            pass  # govde JSON degilse, asagida genel hata metnine dusuyoruz
    return str(hata)

# Deniz mavisi tonlarinda bir renk skalasi (acikdan koyuya):
# CAF0F8 - ADE8F4 - 90E0EF - 00B4D8 - 0096C7 - 0077B6 - 023E8A - 03045E
# QSS (Qt Style Sheet), CSS'e cok benziyor - PyQt widget'larina CSS
# yazar gibi stil verebiliyoruz. QApplication'a UYGULANDIGINDA butun
# pencereler/dialoglar bu stili otomatik miras alir.
DENIZ_MAVISI_STIL = """
QMainWindow, QDialog {
    background-color: #CAF0F8;
}
QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #03045E;
}
QLabel {
    color: #023E8A;
    font-weight: 600;
}
QLabel[ipucu="true"] {
    color: #0077B6;
    font-weight: 400;
    font-style: italic;
}
QLineEdit, QTextEdit {
    background-color: white;
    border: 2px solid #0096C7;
    border-radius: 6px;
    padding: 6px;
}
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid #023E8A;
}
QPushButton {
    background-color: #0077B6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #023E8A;
}
QPushButton:pressed {
    background-color: #03045E;
}
QPushButton#silButonu {
    background-color: #D00000;
}
QPushButton#silButonu:hover {
    background-color: #9D0208;
}
QListWidget {
    background-color: white;
    border: 2px solid #90E0EF;
    border-radius: 6px;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #ADE8F4;
}
QListWidget::item:selected {
    background-color: #90E0EF;
    color: #03045E;
}
QTabWidget::pane {
    border: 2px solid #0096C7;
    border-radius: 6px;
    background-color: #E0FBFC;
}
QTabBar::tab {
    background-color: #ADE8F4;
    color: #023E8A;
    padding: 8px 18px;
    font-weight: 600;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #0077B6;
    color: white;
}
"""


class YeniSayfaDialogu(QDialog):
    """
    "+ Yeni Sayfa" butonuna basinca acilan KUCUK PENCERE (dialog).
    Baslik + markdown icerik alir, backend'in POST /sources/markdown
    endpoint'ine gonderir.

    QDialog, QMainWindow'dan FARKLI - ana pencerenin USTUNE acilan,
    kendi basina calisan gecici bir pencere icin kullanilir (formlar,
    onay kutulari gibi).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Wiki Sayfasi Olustur")
        self.resize(450, 420)

        self.baslik_kutusu = QLineEdit()
        self.baslik_kutusu.setPlaceholderText("Sayfa basligi")

        self.icerik_kutusu = QTextEdit()
        self.icerik_kutusu.setPlaceholderText("Buraya notunu yaz...")

        # Kullaniciya format hakkinda kisa bir yardim notu - "markdown
        # bilmiyorum, JSON formati nedir" tarzi kafa karisikligini
        # onlemek icin. ONEMLI VURGU: hicbir ozel format ZORUNLU DEGIL,
        # duz metin de yazilabilir - bolumlere ayirmak ISTERSE "#" ile
        # baslik atabilir.
        ipucu_etiketi = QLabel(
            "İpucu: Normal bir not gibi yaz, özel bir format şart değil.\n"
            "Bölümlere ayırmak istersen '# Bölüm Adı' yaz - # işaretinden\n"
            "sonra MUTLAKA boşluk bırak, yoksa başlık olarak algılanmaz."
        )
        ipucu_etiketi.setProperty("ipucu", "true")
        ipucu_etiketi.setWordWrap(True)

        self.kaydet_butonu = QPushButton("Kaydet")
        self.kaydet_butonu.clicked.connect(self.kaydet)

        self.durum_etiketi = QLabel("")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Baslik:"))
        layout.addWidget(self.baslik_kutusu)
        layout.addWidget(QLabel("Icerik:"))
        layout.addWidget(ipucu_etiketi)
        layout.addWidget(self.icerik_kutusu)
        layout.addWidget(self.kaydet_butonu)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

    def kaydet(self):
        """
        Formdaki bilgileri POST /sources/markdown'a gonderir. Basarili
        olursa dialogu KAPATIR (self.accept()) - bu, dialogu acan
        pencereye "islem basariyla tamamlandi" sinyalini gonderir
        (bkz. cagiran taraftaki "if dialog.exec():").
        """
        baslik = self.baslik_kutusu.text().strip()
        icerik = self.icerik_kutusu.toPlainText().strip()

        if not baslik or not icerik:
            self.durum_etiketi.setText("Baslik ve icerik bos olamaz")
            return

        self.durum_etiketi.setText("Kaydediliyor...")
        QApplication.processEvents()

        try:
            yanit = requests.post(
                f"{BACKEND_URL}/sources/markdown",
                json={"title": baslik, "content": icerik},
                timeout=15,
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self.accept()


class SayfaDetayDialogu(QDialog):
    """
    Sayfalar listesindeki bir sayfaya CIFT TIKLAYINCA acilan detay
    penceresi. Tam icerigi gosterir, kategoriyi ELLE duzeltmeye
    (siniflandirma bazen yanilabiliyor - bkz. proje notlari) ve
    sayfadan kavram/iliski cikarmaya izin verir.

    Ilgili endpoint'ler: GET /pages/{id}, PUT /pages/{id}/kategori,
    POST /pages/{id}/extract-concepts.
    """

    def __init__(self, sayfa_id: int, parent=None):
        super().__init__(parent)
        self.sayfa_id = sayfa_id
        self.setWindowTitle(f"Sayfa #{sayfa_id}")
        self.resize(600, 550)

        self.baslik_etiketi = QLabel("Yukleniyor...")
        self.baslik_etiketi.setStyleSheet("font-size: 16px; font-weight: 700; color: #03045E;")

        self.tarih_etiketi = QLabel("")

        self.kategori_kutusu = QLineEdit()
        self.kategori_guncelle_butonu = QPushButton("Kategoriyi Guncelle")
        self.kategori_guncelle_butonu.clicked.connect(self.kategoriyi_guncelle)

        kategori_satiri = QHBoxLayout()
        kategori_satiri.addWidget(QLabel("Kategori:"))
        kategori_satiri.addWidget(self.kategori_kutusu)
        kategori_satiri.addWidget(self.kategori_guncelle_butonu)

        self.icerik_kutusu = QTextEdit()
        self.icerik_kutusu.setReadOnly(True)

        self.kavram_cikar_butonu = QPushButton("Kavram Cikar")
        self.kavram_cikar_butonu.clicked.connect(self.kavram_cikar)

        # Sayfa ici kavram grafigi (Katman 1) - GET /pages/{id}/graph.
        # Kavram Cikar butonuyla dogrudan iliskili: cikarim yapildiktan
        # SONRA burasi otomatik yenilenir, ama daha once cikarim yapilmis
        # bir sayfa acildiginda da (self.sayfayi_yukle ile birlikte)
        # dolu gelsin diye ayri bir "Yenile" butonu da var.
        self.grafik_yenile_butonu = QPushButton("Grafigi Yenile")
        self.grafik_yenile_butonu.clicked.connect(self.grafigi_yukle)

        self.grafik_listesi = QListWidget()

        self.durum_etiketi = QLabel("")
        self.durum_etiketi.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(self.baslik_etiketi)
        layout.addWidget(self.tarih_etiketi)
        layout.addLayout(kategori_satiri)
        layout.addWidget(QLabel("Icerik:"))
        layout.addWidget(self.icerik_kutusu)
        layout.addWidget(self.kavram_cikar_butonu)
        layout.addWidget(QLabel("Kavram Grafigi:"))
        layout.addWidget(self.grafik_listesi)
        layout.addWidget(self.grafik_yenile_butonu)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

        self.sayfayi_yukle()
        self.grafigi_yukle()

    def sayfayi_yukle(self):
        try:
            yanit = requests.get(f"{BACKEND_URL}/pages/{self.sayfa_id}", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        sayfa = yanit.json()
        self.baslik_etiketi.setText(sayfa["title"])
        self.tarih_etiketi.setText(f"Olusturulma: {sayfa['created_at']}")
        self.kategori_kutusu.setText(sayfa.get("kategori") or "")
        self.icerik_kutusu.setPlainText(sayfa["content"])

    def kategoriyi_guncelle(self):
        """
        PUT /pages/{id}/kategori - otomatik siniflandirmanin (LLM)
        aksine, kullanicinin YAZDIGI HERHANGI BIR METNI dogrudan
        kaydeder, hicbir dogrulama/eslestirme yapmadan (bkz. pages.py
        kategoriyi_guncelle endpoint'i) - kullanici LLM'in kararini
        ISTEDIGI GIBI ezebilir.
        """
        yeni_kategori = self.kategori_kutusu.text().strip()
        if not yeni_kategori:
            self.durum_etiketi.setText("Kategori bos olamaz")
            return

        try:
            yanit = requests.put(
                f"{BACKEND_URL}/pages/{self.sayfa_id}/kategori",
                json={"kategori": yeni_kategori},
                timeout=10,
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self.durum_etiketi.setText("Kategori guncellendi")

    def kavram_cikar(self):
        self.durum_etiketi.setText("Kavramlar cikariliyor (LLM cagrisi, biraz surebilir)...")
        QApplication.processEvents()

        try:
            yanit = requests.post(
                f"{BACKEND_URL}/pages/{self.sayfa_id}/extract-concepts", timeout=120
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        sonuc = yanit.json()
        self.durum_etiketi.setText(
            f"{sonuc['olusturulan_kavram_sayisi']} kavram, "
            f"{sonuc['olusturulan_iliski_sayisi']} iliski cikarildi "
            f"({sonuc['onerilen_yeni_tip_sayisi']} yeni tip onerisi)"
        )
        self.grafigi_yukle()

    def grafigi_yukle(self):
        """
        GET /pages/{id}/graph - bu sayfaya ait ConceptNode'lari ve
        aralarindaki ConceptRelation'lari getirir. Once kavramlari,
        sonra iliskileri listeler - iliski satirlarinda node id'leri
        degil isimleri gostermek icin once bir id->isim eslemesi kuruyoruz.
        """
        try:
            yanit = requests.get(f"{BACKEND_URL}/pages/{self.sayfa_id}/graph", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        graf = yanit.json()
        self.grafik_listesi.clear()

        id_to_isim = {kavram["id"]: kavram["standart_isim"] for kavram in graf["kavramlar"]}

        if not graf["kavramlar"]:
            self.grafik_listesi.addItem(QListWidgetItem("Henuz kavram cikarilmamis"))
            return

        for kavram in graf["kavramlar"]:
            self.grafik_listesi.addItem(QListWidgetItem(f"🏷 {kavram['standart_isim']} ({kavram['tip']})"))

        for iliski in graf["iliskiler"]:
            kaynak_isim = id_to_isim.get(iliski["kaynak_id"], f"#{iliski['kaynak_id']}")
            hedef_isim = id_to_isim.get(iliski["hedef_id"], f"#{iliski['hedef_id']}")
            self.grafik_listesi.addItem(
                QListWidgetItem(f"   {kaynak_isim} —[{iliski['iliski_tipi']}]→ {hedef_isim}")
            )


class SohbetSekmesi(QWidget):
    """
    "Sohbet" sekmesi: kullanicinin KENDI notlarina soru sordugu RAG
    (Retrieval-Augmented Generation) arayuzu. POST /chat'e baglanir -
    backend, soruyla en alakali parcalari bulup (embedding + ontoloji
    bazli hibrit arama), LLM'e "SADECE bu parcalari kullanarak cevap
    ver" talimatiyla gonderiyor (bkz. chat_servisi.py) - boylece LLM
    kendi genel bilgisini "uydurmuyor" (halusinasyon onleniyor).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Konusma GECMISINI gostermek icin salt-okunur bir QTextEdit
        # kullaniyoruz - HTML icerik ekleyebildigi icin (append ile),
        # kalin/italik yazarak "Sen:" / "PersonalWiki AI:" ayrimini
        # kolayca gosterebiliyoruz.
        self.gecmis_kutusu = QTextEdit()
        self.gecmis_kutusu.setReadOnly(True)

        self.soru_kutusu = QLineEdit()
        self.soru_kutusu.setPlaceholderText("Notlarina bir soru sor... (orn. 'event loop nedir')")
        self.soru_kutusu.returnPressed.connect(self.soru_sor)

        self.gonder_butonu = QPushButton("Gonder")
        self.gonder_butonu.clicked.connect(self.soru_sor)

        self.durum_etiketi = QLabel("Hazir")

        soru_satiri = QHBoxLayout()
        soru_satiri.addWidget(self.soru_kutusu)
        soru_satiri.addWidget(self.gonder_butonu)

        layout = QVBoxLayout()
        layout.addWidget(self.gecmis_kutusu)
        layout.addLayout(soru_satiri)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

    def soru_sor(self):
        """
        NOT: Bu cagri SENKRON (requests.post bloklar). AramaSekmesi'nde
        bu "localhost'a giden istek zaten hizli" diye basit tutulmustu,
        ama /chat bir LLM cagrisi ICERDIGI icin (embedding aramasindan
        cok daha yavas) birkac saniye surebilir - bu yuzden "Dusunuyor..."
        durum yazisi ve kutulari GECICI OLARAK devre disi birakma
        (kullanici ikinci bir soruyu ustune bindirmesin diye) burada
        daha onemli.
        """
        soru = self.soru_kutusu.text().strip()
        if not soru:
            return

        self.soru_kutusu.setEnabled(False)
        self.gonder_butonu.setEnabled(False)
        self.durum_etiketi.setText("Dusunuyor... (LLM cagrisi, birkac saniye surebilir)")
        QApplication.processEvents()

        try:
            yanit = requests.post(
                f"{BACKEND_URL}/chat",
                json={"soru": soru, "limit": 5},
                timeout=60,
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText(
                "Backend'e baglanilamadi - 'uvicorn main:app --reload' calisiyor mu?"
            )
            self.soru_kutusu.setEnabled(True)
            self.gonder_butonu.setEnabled(True)
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            self.soru_kutusu.setEnabled(True)
            self.gonder_butonu.setEnabled(True)
            return

        sonuc = yanit.json()
        kaynaklar = ", ".join(sonuc["kullanilan_kaynaklar"]) or "yok"

        # html.escape: soru/cevap metninde "<" gibi karakterler gecerse
        # (orn. kod ornegi iceren bir cevap), bunlar HTML etiketi
        # SANILMASIN diye kacis (escape) yapiyoruz - yoksa gecmis
        # kutusundaki gorunum bozulabilir.
        self.gecmis_kutusu.append(f"<p><b>Sen:</b> {html.escape(soru)}</p>")
        self.gecmis_kutusu.append(f"<p><b>PersonalWiki AI:</b> {html.escape(sonuc['cevap'])}</p>")
        self.gecmis_kutusu.append(f"<p><i>Kaynaklar: {html.escape(kaynaklar)}</i></p><hr>")

        self.soru_kutusu.clear()
        self.durum_etiketi.setText("Hazir")
        self.soru_kutusu.setEnabled(True)
        self.gonder_butonu.setEnabled(True)
        self.soru_kutusu.setFocus()


class AramaSekmesi(QWidget):
    """
    "Ara" sekmesi: arama kutusu + sonuc listesi. GET /search'e baglanir.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.arama_kutusu = QLineEdit()
        self.arama_kutusu.setPlaceholderText("Ne aramak istiyorsun? (orn. 'event loop nedir')")
        self.arama_kutusu.returnPressed.connect(self.arama_yap)

        self.ara_butonu = QPushButton("Ara")
        self.ara_butonu.clicked.connect(self.arama_yap)

        self.sonuc_listesi = QListWidget()

        self.durum_etiketi = QLabel(
            "Hazir - backend'in calistigindan emin ol (uvicorn main:app --reload)"
        )

        arama_satiri = QHBoxLayout()
        arama_satiri.addWidget(self.arama_kutusu)
        arama_satiri.addWidget(self.ara_butonu)

        layout = QVBoxLayout()
        layout.addLayout(arama_satiri)
        layout.addWidget(self.sonuc_listesi)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

    def arama_yap(self):
        """
        NOT: Bu cagri SENKRON (requests.get bloklar) - istek surerken
        pencere kisa bir sure "donmus" gorunur. Gercek/buyuk bir
        uygulamada bu QThread ile arka planda yapilirdi ki arayuz hic
        kilitlenmesin. Burada localhost'a giden istek zaten cok hizli
        oldugu icin bu basitlik bilincli bir tercih.
        """
        sorgu = self.arama_kutusu.text().strip()
        if not sorgu:
            return

        self.sonuc_listesi.clear()
        self.durum_etiketi.setText("Araniyor...")
        QApplication.processEvents()

        try:
            yanit = requests.get(
                f"{BACKEND_URL}/search",
                params={"query": sorgu, "limit": 5},
                timeout=5,
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText(
                "Backend'e baglanilamadi - 'uvicorn main:app --reload' calisiyor mu?"
            )
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        sonuclar = yanit.json()

        if not sonuclar:
            self.durum_etiketi.setText("Sonuc bulunamadi")
            return

        for sonuc in sonuclar:
            baslik = sonuc["sayfa_basligi"]
            icerik = sonuc["icerik"].strip().replace("\n", " ")
            kisa_icerik = icerik[:150] + ("..." if len(icerik) > 150 else "")
            bulunma = sonuc["bulunma_sekli"]

            metin = f"[{bulunma}] {baslik}\n{kisa_icerik}"
            self.sonuc_listesi.addItem(QListWidgetItem(metin))

        self.durum_etiketi.setText(f"{len(sonuclar)} sonuc bulundu")


class SayfalarSekmesi(QWidget):
    """
    "Sayfalar" sekmesi: var olan sayfalarin listesi + yonetim islemleri
    (yeni sayfa, PDF yukleme, siniflandirma, silme, detay goruntuleme).
    Ilgili endpoint'ler: GET /pages, POST /sources/pdf,
    POST /pages/{id}/classify, DELETE /pages/{id}. Bir sayfaya CIFT
    TIKLAYINCA (ya da "Detay Ac" ile) SayfaDetayDialogu acilir - orada
    da PUT /pages/{id}/kategori ve POST /pages/{id}/extract-concepts var.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.sayfa_listesi = QListWidget()
        # Cift tiklama ile de detay penceresi acilsin - "Detay Ac"
        # butonuna basmak zorunda kalmadan.
        self.sayfa_listesi.itemDoubleClicked.connect(self.sayfa_detayini_ac)

        self.yenile_butonu = QPushButton("Yenile")
        self.yenile_butonu.clicked.connect(self.sayfalari_yukle)

        self.yeni_sayfa_butonu = QPushButton("+ Yeni Sayfa")
        self.yeni_sayfa_butonu.clicked.connect(self.yeni_sayfa_ac)

        self.pdf_yukle_butonu = QPushButton("PDF Yukle")
        self.pdf_yukle_butonu.clicked.connect(self.pdf_yukle)

        self.detay_butonu = QPushButton("Detay Ac")
        self.detay_butonu.clicked.connect(self.secili_sayfa_detayini_ac)

        self.siniflandir_butonu = QPushButton("Siniflandir")
        self.siniflandir_butonu.clicked.connect(self.secili_sayfayi_siniflandir)

        self.sil_butonu = QPushButton("Sil")
        self.sil_butonu.setObjectName("silButonu")  # QSS'te kirmizi renk icin
        self.sil_butonu.clicked.connect(self.secili_sayfayi_sil)

        self.durum_etiketi = QLabel("Sayfalari gormek icin 'Yenile'ye bas")

        ust_satir = QHBoxLayout()
        ust_satir.addWidget(self.yenile_butonu)
        ust_satir.addWidget(self.yeni_sayfa_butonu)
        ust_satir.addWidget(self.pdf_yukle_butonu)

        alt_satir = QHBoxLayout()
        alt_satir.addWidget(self.detay_butonu)
        alt_satir.addWidget(self.siniflandir_butonu)
        alt_satir.addWidget(self.sil_butonu)

        layout = QVBoxLayout()
        layout.addLayout(ust_satir)
        layout.addWidget(self.sayfa_listesi)
        layout.addLayout(alt_satir)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

    def sayfalari_yukle(self):
        self.durum_etiketi.setText("Yukleniyor...")
        QApplication.processEvents()

        try:
            yanit = requests.get(f"{BACKEND_URL}/pages", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        sayfalar = yanit.json()
        self.sayfa_listesi.clear()

        for sayfa in sayfalar:
            kategori = sayfa.get("kategori") or "kategorisiz"
            metin = f"#{sayfa['id']} - {sayfa['title']}  [{kategori}]"
            oge = QListWidgetItem(metin)
            # Gercek sayfa id'sini ogenin ICINE gomuyoruz (UserRole) -
            # liste metnindeki "#id" yazisini geri PARSE etmek yerine,
            # dogrudan veriden okumak cok daha guvenilir bir yontem.
            oge.setData(Qt.ItemDataRole.UserRole, sayfa["id"])
            self.sayfa_listesi.addItem(oge)

        self.durum_etiketi.setText(f"{len(sayfalar)} sayfa yuklendi")

    def _secili_sayfa_id(self):
        oge = self.sayfa_listesi.currentItem()
        if oge is None:
            self.durum_etiketi.setText("Once listeden bir sayfa sec")
            return None
        return oge.data(Qt.ItemDataRole.UserRole)

    def sayfa_detayini_ac(self, oge: QListWidgetItem):
        """
        QListWidget.itemDoubleClicked sinyali, tiklanan OGEYI parametre
        olarak veriyor - _secili_sayfa_id'nin aksine burada ekstra bir
        "hangi satir secili" kontrolune gerek yok, cift tiklanan oge
        zaten belli.
        """
        sayfa_id = oge.data(Qt.ItemDataRole.UserRole)
        dialog = SayfaDetayDialogu(sayfa_id, self)
        dialog.exec()
        # Kategori dialogda degismis olabilir (Kategoriyi Guncelle ile) -
        # listeyi yenileyip guncel halini gosterelim.
        self.sayfalari_yukle()

    def secili_sayfa_detayini_ac(self):
        oge = self.sayfa_listesi.currentItem()
        if oge is None:
            self.durum_etiketi.setText("Once listeden bir sayfa sec")
            return
        self.sayfa_detayini_ac(oge)

    def secili_sayfayi_siniflandir(self):
        sayfa_id = self._secili_sayfa_id()
        if sayfa_id is None:
            return

        self.durum_etiketi.setText("Siniflandiriliyor (LLM cagrisi, birkac saniye surebilir)...")
        QApplication.processEvents()

        try:
            yanit = requests.post(f"{BACKEND_URL}/pages/{sayfa_id}/classify", timeout=30)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        sonuc = yanit.json()
        self.durum_etiketi.setText(f"Siniflandirildi: {sonuc['kategori']}")
        self.sayfalari_yukle()  # listeyi yenile ki yeni kategori gorulsun

    def secili_sayfayi_sil(self):
        sayfa_id = self._secili_sayfa_id()
        if sayfa_id is None:
            return

        # QMessageBox.question: kullaniciya "Evet/Hayir" sorusu soran
        # hazir bir onay penceresi - GERI ALINAMAZ islemlerden once
        # (silme gibi) kullanici onayı almak iyi bir pratik.
        onay = QMessageBox.question(
            self,
            "Sayfayi Sil",
            f"#{sayfa_id} numarali sayfayi silmek istedigine emin misin?\nBu islem geri alinamaz.",
        )
        if onay != QMessageBox.StandardButton.Yes:
            return

        try:
            yanit = requests.delete(f"{BACKEND_URL}/pages/{sayfa_id}", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self.durum_etiketi.setText(f"#{sayfa_id} silindi")
        self.sayfalari_yukle()

    def yeni_sayfa_ac(self):
        dialog = YeniSayfaDialogu(self)
        if dialog.exec():
            self.durum_etiketi.setText(f"'{dialog.baslik_kutusu.text()}' olusturuldu")
            self.sayfalari_yukle()

    def pdf_yukle(self):
        """
        QFileDialog.getOpenFileName: isletim sisteminin KENDI dosya
        secme penceresini acar (Windows Gezgini gibi). Kullanici bir
        PDF secince, dosyayi POST /sources/pdf'e MULTIPART FORM olarak
        (dosya icerigiyle birlikte) yolluyoruz.
        """
        dosya_yolu, _ = QFileDialog.getOpenFileName(self, "PDF Sec", "", "PDF Dosyalari (*.pdf)")
        if not dosya_yolu:
            return  # kullanici pencereyi iptal etti

        self.durum_etiketi.setText("Yukleniyor (buyuk PDF'lerde biraz surebilir)...")
        QApplication.processEvents()

        try:
            with open(dosya_yolu, "rb") as dosya:
                dosya_adi = os.path.basename(dosya_yolu)
                yanit = requests.post(
                    f"{BACKEND_URL}/sources/pdf",
                    files={"dosya": (dosya_adi, dosya, "application/pdf")},
                    timeout=120,
                )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self.durum_etiketi.setText("PDF basariyla yuklendi")
        self.sayfalari_yukle()


class GlobalGrafSekmesi(QWidget):
    """
    "Global Graf" sekmesi: sayfalar arasi, ORTAK KAVRAMLAR uzerinden
    kurulan baglanti haritasi (Katman 2) - GET /graph/global. Bu,
    SayfaDetayDialogu'ndaki sayfa ICI grafikten (Katman 1) farkli -
    orada tek bir sayfanin kavramlari/iliskileri var, burada FARKLI
    sayfalarin ayni kavramdan gectigi icin birbirine baglanmasi var.

    Onceden hesaplanmis veriyi gosterir - yeni kavram cikarimi
    yapildiktan sonra "Yeniden Hesapla"ya (POST /graph/global/yeniden-
    hesapla) basilmadan guncel gelmeyebilir (bkz. graph.py docstring'i).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.yenile_butonu = QPushButton("Yenile")
        self.yenile_butonu.clicked.connect(self.grafigi_yukle)

        self.yeniden_hesapla_butonu = QPushButton("Yeniden Hesapla")
        self.yeniden_hesapla_butonu.clicked.connect(self.yeniden_hesapla)

        self.baglanti_listesi = QListWidget()

        self.durum_etiketi = QLabel("Baglantilari gormek icin 'Yenile'ye bas")

        ust_satir = QHBoxLayout()
        ust_satir.addWidget(self.yenile_butonu)
        ust_satir.addWidget(self.yeniden_hesapla_butonu)

        layout = QVBoxLayout()
        layout.addLayout(ust_satir)
        layout.addWidget(self.baglanti_listesi)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

    def grafigi_yukle(self):
        self.durum_etiketi.setText("Yukleniyor...")
        QApplication.processEvents()

        try:
            yanit = requests.get(f"{BACKEND_URL}/graph/global", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        graf = yanit.json()
        self.baglanti_listesi.clear()

        # Baglantilar sadece sayfa ID'si tasiyor - okunabilir olmasi
        # icin once id->baslik eslemesi kuruyoruz.
        id_to_baslik = {sayfa["id"]: sayfa["title"] for sayfa in graf["sayfalar"]}

        if not graf["baglantilar"]:
            self.baglanti_listesi.addItem(QListWidgetItem("Henuz baglanti yok - 'Yeniden Hesapla'yi dene"))
            self.durum_etiketi.setText("0 baglanti")
            return

        for baglanti in graf["baglantilar"]:
            baslik_1 = id_to_baslik.get(baglanti["sayfa_id_1"], f"#{baglanti['sayfa_id_1']}")
            baslik_2 = id_to_baslik.get(baglanti["sayfa_id_2"], f"#{baglanti['sayfa_id_2']}")
            metin = f"{baslik_1}  ↔  {baslik_2}   (ortak kavram: {baglanti['ortak_kavram_ismi']})"
            self.baglanti_listesi.addItem(QListWidgetItem(metin))

        self.durum_etiketi.setText(f"{len(graf['baglantilar'])} baglanti, {len(graf['sayfalar'])} sayfa")

    def yeniden_hesapla(self):
        """
        POST /graph/global/yeniden-hesapla - SayfaBaglantisi tablosunu
        sifirdan yeniden kurar (bkz. graph.py). Bu bir LLM cagrisi degil,
        sadece veritabani islemi - ama sayfa/kavram sayisi arttikca
        yine de biraz surebilir.
        """
        self.durum_etiketi.setText("Yeniden hesaplaniyor...")
        QApplication.processEvents()

        try:
            yanit = requests.post(f"{BACKEND_URL}/graph/global/yeniden-hesapla", timeout=30)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self.grafigi_yukle()


class AnaPencere(QMainWindow):
    """
    Uygulamanin ANA penceresi. Icerigi bir QTabWidget (sekmeler) -
    "Sohbet", "Ara" ve "Sayfalar" - olusturuyor, her sekme kendi widget
    class'inda (SohbetSekmesi, AramaSekmesi, SayfalarSekmesi) yasiyor.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PersonalWiki AI - Masaustu Demo")
        self.resize(750, 600)

        baslik_etiketi = QLabel("PersonalWiki AI")
        baslik_etiketi.setStyleSheet("font-size: 20px; font-weight: 700; color: #03045E;")

        sekmeler = QTabWidget()
        sekmeler.addTab(SohbetSekmesi(), "Sohbet")
        sekmeler.addTab(AramaSekmesi(), "Ara")
        sekmeler.addTab(SayfalarSekmesi(), "Sayfalar")
        sekmeler.addTab(GlobalGrafSekmesi(), "Global Graf")

        ana_layout = QVBoxLayout()
        ana_layout.addWidget(baslik_etiketi)
        ana_layout.addWidget(sekmeler)

        # QMainWindow'a DOGRUDAN layout eklenemez - once bir QWidget'a
        # sarmalayip, o widget'i "merkez widget" olarak atamamiz gerekir.
        merkez_widget = QWidget()
        merkez_widget.setLayout(ana_layout)
        self.setCentralWidget(merkez_widget)


def main():
    uygulama = QApplication(sys.argv)
    uygulama.setStyleSheet(DENIZ_MAVISI_STIL)
    pencere = AnaPencere()
    pencere.show()
    sys.exit(uygulama.exec())


if __name__ == "__main__":
    main()
