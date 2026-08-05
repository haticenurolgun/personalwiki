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
import webbrowser

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
    (siniflandirma bazen yanilabiliyor - bkz. proje notlari) izin
    verir.

    NOT: siniflandirma ve kavram cikarma artik sayfa yuklenirken
    OTOMATIK calisiyor (bkz. sources.py) - burada ayri "Siniflandir"/
    "Kavram Cikar" butonlari YOK. "Yeniden Isle" butonu, ikisini de
    (siniflandirma + kavram cikarma) tekrar tetikleyen tek bir
    yedek/duzeltme mekanizmasi - otomatik calisma basarisiz olduysa
    ya da icerik guncellendikten sonra tazelemek icin.

    Ilgili endpoint'ler: GET /pages/{id}, PUT /pages/{id}/kategori,
    POST /pages/{id}/classify, POST /pages/{id}/extract-concepts.
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

        # ARTIK DUZENLENEBILIR (eskiden salt-okunurdu) - kullanici
        # icerigi burada dogrudan degistirip "Icerigi Kaydet" ile
        # PUT /pages/{id}/content'e gonderebilir.
        self.icerik_kutusu = QTextEdit()

        self.icerik_kaydet_butonu = QPushButton("Icerigi Kaydet (Yeniden Parcala + Isle)")
        self.icerik_kaydet_butonu.clicked.connect(self.icerigi_kaydet)

        self.yeniden_isle_butonu = QPushButton("Yeniden Isle (Siniflandir + Kavram Cikar)")
        self.yeniden_isle_butonu.clicked.connect(self.yeniden_isle)

        # Sayfa ici kavram grafigi (Katman 1) - GET /pages/{id}/graph.
        # Kavram Cikar butonuyla dogrudan iliskili: cikarim yapildiktan
        # SONRA burasi otomatik yenilenir, ama daha once cikarim yapilmis
        # bir sayfa acildiginda da (self.sayfayi_yukle ile birlikte)
        # dolu gelsin diye ayri bir "Yenile" butonu da var.
        self.grafik_yenile_butonu = QPushButton("Grafigi Yenile")
        self.grafik_yenile_butonu.clicked.connect(self.grafigi_yukle)

        # graph.html'deki gorsel (renkli, etkilesimli) graf goruntuleyiciyi
        # sistemin varsayilan tarayicisinda, DOGRUDAN bu sayfanin Katman 1
        # goruntusune ac - grafik_listesi'ndeki duz metin listesinin
        # gorsel karsiligi.
        self.gorsel_graf_butonu = QPushButton("Gorsel Grafigi Ac (Tarayicida)")
        self.gorsel_graf_butonu.clicked.connect(self.gorsel_grafigi_ac)

        grafik_buton_satiri = QHBoxLayout()
        grafik_buton_satiri.addWidget(self.grafik_yenile_butonu)
        grafik_buton_satiri.addWidget(self.gorsel_graf_butonu)

        self.grafik_listesi = QListWidget()

        self.durum_etiketi = QLabel("")
        self.durum_etiketi.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(self.baslik_etiketi)
        layout.addWidget(self.tarih_etiketi)
        layout.addLayout(kategori_satiri)
        layout.addWidget(QLabel("Icerik:"))
        layout.addWidget(self.icerik_kutusu)
        layout.addWidget(self.icerik_kaydet_butonu)
        layout.addWidget(self.yeniden_isle_butonu)
        layout.addWidget(QLabel("Kavram Grafigi:"))
        layout.addWidget(self.grafik_listesi)
        layout.addLayout(grafik_buton_satiri)
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

    def icerigi_kaydet(self):
        """
        PUT /pages/{id}/content - sayfanin icerigini icerik_kutusu'ndaki
        GUNCEL metinle degistirir. Bu, TUM eski parcalari/kavramlari
        silip yeni icerigi SIFIRDAN yeniden isler (bkz. pages.py
        icerigi_guncelle docstring'i) - yani mevcut kavram baglantilari
        kaybolur ve LLM cagrilari (siniflandirma + kavram cikarma)
        tekrar tetiklenir. Bu yuzden onceden ONAY istiyoruz - sayfayi_
        sil'deki ayni "geri alinamaz islem" desenini takip ediyor.
        """
        yeni_icerik = self.icerik_kutusu.toPlainText()
        if not yeni_icerik.strip():
            self.durum_etiketi.setText("Icerik bos olamaz")
            return

        onay = QMessageBox.question(
            self,
            "Icerigi Kaydet",
            "Icerigi kaydetmek, bu sayfanin TUM parcalarini ve kavram "
            "baglantilarini SIFIRDAN yeniden olusturacak (mevcut kavram "
            "grafigi kaybolur, siniflandirma + kavram cikarma tekrar "
            "calisir - LLM cagrisi icerir, biraz surebilir).\n\nDevam edilsin mi?",
        )
        if onay != QMessageBox.StandardButton.Yes:
            return

        self.icerik_kaydet_butonu.setEnabled(False)
        self.durum_etiketi.setText("Kaydediliyor (yeniden parcalaniyor + isleniyor, biraz surebilir)...")
        QApplication.processEvents()

        try:
            yanit = requests.put(
                f"{BACKEND_URL}/pages/{self.sayfa_id}/content",
                json={"content": yeni_icerik},
                # Chunking + embed + siniflandirma + kavram cikarma TEK
                # istekte - PDF yukleme ile ayni buyuklukte bir islem
                # (bkz. sources.py pdf_ekle timeout'u), o yuzden ayni
                # guvenlik payi.
                timeout=300,
            )
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            self.icerik_kaydet_butonu.setEnabled(True)
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            self.icerik_kaydet_butonu.setEnabled(True)
            return

        self.icerik_kaydet_butonu.setEnabled(True)
        self.durum_etiketi.setText("Icerik kaydedildi, yeniden islendi")

        # Kategori (otomatik siniflandirma) ve kavram grafigi degismis
        # olabilir - ikisini de tazeleyelim.
        self.sayfayi_yukle()
        self.grafigi_yukle()

    def yeniden_isle(self):
        """
        Siniflandirma VE kavram cikarma normalde sayfa yuklenirken
        OTOMATIK calisiyor (bkz. sources.py) - bu buton, ikisini
        MANUEL olarak yeniden tetikleyen bir yedek/duzeltme
        mekanizmasi. Once /classify, sonra /extract-concepts cagirir -
        kategori kutusunu ve kavram grafigini gunceller.
        """
        self.durum_etiketi.setText("Siniflandiriliyor (LLM cagrisi, biraz surebilir)...")
        QApplication.processEvents()

        try:
            siniflandirma_yaniti = requests.post(
                f"{BACKEND_URL}/pages/{self.sayfa_id}/classify", timeout=90
            )
            siniflandirma_yaniti.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Siniflandirma hatasi: {http_hata_mesaji(hata)}")
            return

        yeni_kategori = siniflandirma_yaniti.json()["kategori"]
        self.kategori_kutusu.setText(yeni_kategori)

        self.durum_etiketi.setText("Kavramlar cikariliyor (LLM cagrisi, biraz surebilir)...")
        QApplication.processEvents()

        try:
            kavram_yaniti = requests.post(
                # Buyuk sayfalarda (cok sayida SemanticUnit) TUM unit'ler
                # TEK bir Gemini cagrisinda islendigi icin (bkz.
                # concepts.py::kavramlari_uygula) bu cagri uzun surebilir -
                # 120s bircok gercek PDF icin yetersiz kaliyordu.
                f"{BACKEND_URL}/pages/{self.sayfa_id}/extract-concepts", timeout=300
            )
            kavram_yaniti.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Kavram cikarma hatasi: {http_hata_mesaji(hata)}")
            return

        sonuc = kavram_yaniti.json()
        self.durum_etiketi.setText(
            f"Kategori: {yeni_kategori} | {sonuc['olusturulan_kavram_sayisi']} kavram, "
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

    def gorsel_grafigi_ac(self):
        """
        graph.html'i (renkli, etkilesimli vis-network goruntuleyici) bu
        sayfanin Katman 1 grafigine DOGRUDAN acilacak sekilde sistemin
        varsayilan tarayicisinda acar - URL parametreleri (mod, sayfa_id)
        graph.html'in kendi baslangic-durumu okuma mantigi tarafindan
        okunuyor.
        """
        webbrowser.open(f"{BACKEND_URL}/static/graph.html?mod=sayfa&sayfa_id={self.sayfa_id}")


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
    (yeni sayfa, PDF yukleme, silme, detay goruntuleme). Siniflandirma
    ve kavram cikarma artik burada AYRI birer buton DEGIL - sayfa
    yuklenirken otomatik calisiyor (bkz. sources.py), gerekirse
    SayfaDetayDialogu'ndaki "Yeniden Isle" ile MANUEL tekrar
    tetiklenebilir.

    Ilgili endpoint'ler: GET /pages, POST /sources/pdf, DELETE /pages/{id}.
    Bir sayfaya CIFT TIKLAYINCA (ya da "Detay Ac" ile) SayfaDetayDialogu
    acilir - orada PUT /pages/{id}/kategori, POST /pages/{id}/classify
    ve POST /pages/{id}/extract-concepts var.
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
                    # Bu tek istek; parcalama + embed + siniflandirma +
                    # kavram cikarmayi (buyuk PDF'lerde TEK dev Gemini
                    # cagrisi) hepsini kapsiyor - 120s buyuk PDF'lerde
                    # yetersiz kaliyordu (bkz. extract-concepts timeout'u).
                    timeout=300,
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


class KategorilerSekmesi(QWidget):
    """
    "Kategoriler" sekmesi: sayfalari WikiPage.kategori'ye gore gruplayip
    gosterir - solda kategori listesi (kac sayfa icerdigiyle birlikte),
    saginda secili kategorideki sayfalar. Ayri bir backend endpoint'i
    GEREKMEZ - GET /pages zaten her sayfanin kategorisini donduruyor,
    gruplama burada (istemci tarafinda) yapiliyor. Kategorisi olmayan
    sayfalar "Kategorisiz" kovasina dusuyor.

    Bir sayfaya cift tiklayinca (ya da "Detay Ac" ile) SayfalarSekmesi'nde
    de kullanilan AYNI SayfaDetayDialogu acilir - kategori orada da
    duzeltilebilir.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.yenile_butonu = QPushButton("Yenile")
        self.yenile_butonu.clicked.connect(self.kategorileri_yukle)

        self.kategori_listesi = QListWidget()
        self.kategori_listesi.currentItemChanged.connect(self.kategori_secildi)

        self.sayfa_listesi = QListWidget()
        self.sayfa_listesi.itemDoubleClicked.connect(self.sayfa_detayini_ac)

        self.detay_butonu = QPushButton("Detay Ac")
        self.detay_butonu.clicked.connect(self.secili_sayfa_detayini_ac)

        self.durum_etiketi = QLabel("Kategorileri gormek icin 'Yenile'ye bas")

        # Iki sutunlu duzen: solda kategori listesi, saginda o
        # kategorinin sayfalari - bir kategoriye tiklayinca sag taraf
        # guncelleniyor.
        sutunlar = QHBoxLayout()

        sol_sutun = QVBoxLayout()
        sol_sutun.addWidget(QLabel("Kategoriler:"))
        sol_sutun.addWidget(self.kategori_listesi)

        sag_sutun = QVBoxLayout()
        sag_sutun.addWidget(QLabel("Sayfalar:"))
        sag_sutun.addWidget(self.sayfa_listesi)
        sag_sutun.addWidget(self.detay_butonu)

        sutunlar.addLayout(sol_sutun, 1)
        sutunlar.addLayout(sag_sutun, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.yenile_butonu)
        layout.addLayout(sutunlar)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

        # kategori adi -> o kategorideki sayfalarin (id, title, ...)
        # sozlukleri - kategori_secildi'de tekrar API cagirmadan
        # kullanilacak.
        self._kategori_to_sayfalar: dict[str, list[dict]] = {}

    def kategorileri_yukle(self):
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

        # Sayfalari kategoriye gore grupla - kategorisi olmayanlar
        # (None/bos) "Kategorisiz" kovasina dusuyor.
        self._kategori_to_sayfalar = {}
        for sayfa in sayfalar:
            kategori = sayfa.get("kategori") or "Kategorisiz"
            self._kategori_to_sayfalar.setdefault(kategori, []).append(sayfa)

        self.kategori_listesi.clear()
        self.sayfa_listesi.clear()

        # Kategorileri sayfa sayisina gore AZALAN sirada goster - en
        # kalabalik kategori en ustte, gozden kacmasin.
        for kategori, bu_kategorideki_sayfalar in sorted(
            self._kategori_to_sayfalar.items(), key=lambda kv: -len(kv[1])
        ):
            metin = f"{kategori} ({len(bu_kategorideki_sayfalar)})"
            oge = QListWidgetItem(metin)
            oge.setData(Qt.ItemDataRole.UserRole, kategori)
            self.kategori_listesi.addItem(oge)

        self.durum_etiketi.setText(
            f"{len(self._kategori_to_sayfalar)} kategori, {len(sayfalar)} sayfa"
        )

    def kategori_secildi(self, oge: QListWidgetItem, _onceki_oge: QListWidgetItem = None):
        """
        kategori_listesi.currentItemChanged sinyaline baglanmis - bir
        kategoriye tiklaninca (ya da ok tuslariyla secim degisince) sag
        taraftaki sayfa listesini gunceller.
        """
        self.sayfa_listesi.clear()

        if oge is None:
            return

        kategori = oge.data(Qt.ItemDataRole.UserRole)
        bu_kategorideki_sayfalar = self._kategori_to_sayfalar.get(kategori, [])

        for sayfa in bu_kategorideki_sayfalar:
            metin = f"#{sayfa['id']} - {sayfa['title']}"
            yeni_oge = QListWidgetItem(metin)
            yeni_oge.setData(Qt.ItemDataRole.UserRole, sayfa["id"])
            self.sayfa_listesi.addItem(yeni_oge)

    def sayfa_detayini_ac(self, oge: QListWidgetItem):
        sayfa_id = oge.data(Qt.ItemDataRole.UserRole)
        dialog = SayfaDetayDialogu(sayfa_id, self)
        dialog.exec()
        # Kategori dialogda degismis olabilir (Kategoriyi Guncelle ile) -
        # listeyi yenileyip sayfanin GUNCEL kategorisi altinda gorunmesini
        # sagliyoruz.
        self.kategorileri_yukle()

    def secili_sayfa_detayini_ac(self):
        oge = self.sayfa_listesi.currentItem()
        if oge is None:
            self.durum_etiketi.setText("Once listeden bir sayfa sec")
            return
        self.sayfa_detayini_ac(oge)


class KavramlarSekmesi(QWidget):
    """
    "Kavramlar" sekmesi: KAVRAM-merkezli gezinme - GET /concepts ve
    GET /concepts/{id}. KategorilerSekmesi'nden FARKLI: o sayfa
    (WikiPage) merkezli gruplama yapar, bu sekme ise dogrudan
    ConceptNode'lari gezmeyi saglar.

    Sol tarafta TUM kavramlarin aranabilir listesi. Bir kavram
    secilince sagda: tip/takma adlar, GORULDUGU sayfalar (cift
    tiklayinca SayfaDetayDialogu acilir) ve ConceptRelation uzerinden
    ILISKILI kavramlar (cift tiklayinca O kavrama ATLANIR - boylece
    kavramdan kavrama, graf uzerinde gezer gibi, metin ile gezinilebilir).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.yenile_butonu = QPushButton("Yenile")
        self.yenile_butonu.clicked.connect(self.kavramlari_yukle)

        self.arama_kutusu = QLineEdit()
        self.arama_kutusu.setPlaceholderText("Kavram ara...")
        self.arama_kutusu.textChanged.connect(self.listeyi_filtrele)

        self.kavram_listesi = QListWidget()
        self.kavram_listesi.currentItemChanged.connect(self.kavram_secildi)

        self.detay_etiketi = QLabel("Bir kavram sec")
        self.detay_etiketi.setWordWrap(True)

        self.iliskili_listesi = QListWidget()
        self.iliskili_listesi.itemDoubleClicked.connect(self.iliskili_kavrama_git)

        self.sayfa_listesi = QListWidget()
        self.sayfa_listesi.itemDoubleClicked.connect(self.sayfa_detayini_ac)

        self.durum_etiketi = QLabel("Kavramlari gormek icin 'Yenile'ye bas")

        sol_sutun = QVBoxLayout()
        sol_sutun.addWidget(self.arama_kutusu)
        sol_sutun.addWidget(self.kavram_listesi)

        sag_sutun = QVBoxLayout()
        sag_sutun.addWidget(self.detay_etiketi)
        sag_sutun.addWidget(QLabel("Iliskili Kavramlar (cift tikla -> git):"))
        sag_sutun.addWidget(self.iliskili_listesi)
        sag_sutun.addWidget(QLabel("Goruldugu Sayfalar (cift tikla -> detay ac):"))
        sag_sutun.addWidget(self.sayfa_listesi)

        sutunlar = QHBoxLayout()
        sutunlar.addLayout(sol_sutun, 1)
        sutunlar.addLayout(sag_sutun, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.yenile_butonu)
        layout.addLayout(sutunlar)
        layout.addWidget(self.durum_etiketi)
        self.setLayout(layout)

        # Filtrelemede tekrar API cagirmamak icin TUM kavramlari burada
        # sakliyoruz - GET /concepts sadece "Yenile"de bir kere cagrilir.
        self._tum_kavramlar = []

    def kavramlari_yukle(self):
        self.durum_etiketi.setText("Yukleniyor...")
        QApplication.processEvents()

        try:
            yanit = requests.get(f"{BACKEND_URL}/concepts", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        self._tum_kavramlar = yanit.json()
        self._kavram_listesini_doldur(self._tum_kavramlar)
        self.durum_etiketi.setText(f"{len(self._tum_kavramlar)} kavram")

    def _kavram_listesini_doldur(self, kavramlar):
        self.kavram_listesi.clear()
        for kavram in kavramlar:
            oge = QListWidgetItem(f"{kavram['standart_isim']} ({kavram['tip']})")
            oge.setData(Qt.ItemDataRole.UserRole, kavram["id"])
            self.kavram_listesi.addItem(oge)

    def listeyi_filtrele(self, metin):
        """
        Arama kutusuna yazildikca (her tus vurusunda) listeyi YENIDEN
        API'ye sormadan, bellekteki self._tum_kavramlar uzerinden
        filtreler - kucuk/buyuk harf ve Turkce karakter farki
        gozetmeden basit bir ICERME kontrolu yeterli (tam bir arama
        motoru degil, sadece hizli filtreleme).
        """
        metin_kucuk = metin.strip().lower()
        if not metin_kucuk:
            self._kavram_listesini_doldur(self._tum_kavramlar)
            return
        filtrelenmis = [
            k for k in self._tum_kavramlar if metin_kucuk in k["standart_isim"].lower()
        ]
        self._kavram_listesini_doldur(filtrelenmis)

    def kavram_secildi(self, oge: QListWidgetItem, _onceki_oge: QListWidgetItem = None):
        if oge is None:
            return
        kavram_id = oge.data(Qt.ItemDataRole.UserRole)
        self._kavram_detayini_goster(kavram_id)

    def _kavram_detayini_goster(self, kavram_id):
        try:
            yanit = requests.get(f"{BACKEND_URL}/concepts/{kavram_id}", timeout=10)
            yanit.raise_for_status()
        except requests.exceptions.ConnectionError:
            self.durum_etiketi.setText("Backend'e baglanilamadi")
            return
        except requests.exceptions.RequestException as hata:
            self.durum_etiketi.setText(f"Hata: {http_hata_mesaji(hata)}")
            return

        detay = yanit.json()

        takma_adlar_metni = ", ".join(detay["takma_adlar"]) if detay["takma_adlar"] else "yok"
        self.detay_etiketi.setText(
            f"<b>{detay['standart_isim']}</b>  ({detay['tip']})<br>Takma adlar: {takma_adlar_metni}"
        )

        self.iliskili_listesi.clear()
        for iliskili in detay["iliskili_kavramlar"]:
            ok = "→" if iliskili["yon"] == "giden" else "←"
            metin = f"{ok} [{iliskili['iliski_tipi']}] {iliskili['standart_isim']} ({iliskili['tip']})"
            oge = QListWidgetItem(metin)
            oge.setData(Qt.ItemDataRole.UserRole, iliskili["concept_id"])
            self.iliskili_listesi.addItem(oge)

        self.sayfa_listesi.clear()
        for sayfa in detay["goruldugu_sayfalar"]:
            kisa_icerik = sayfa["icerik"].strip().replace("\n", " ")[:80]
            metin = f"#{sayfa['page_id']} - {sayfa['sayfa_basligi']}: {kisa_icerik}"
            oge = QListWidgetItem(metin)
            oge.setData(Qt.ItemDataRole.UserRole, sayfa["page_id"])
            self.sayfa_listesi.addItem(oge)

    def iliskili_kavrama_git(self, oge: QListWidgetItem):
        """
        Iliskili kavramlar listesinde cift tiklaninca, o kavrama
        ATLAR - once sol listede (goruntudeyse) secili hale getirir ki
        kullanici nerede oldugunu kaybetmesin; sol listede yoksa (orn.
        arama kutusuyla filtrelenmisti) dogrudan detayini gosterir.
        """
        kavram_id = oge.data(Qt.ItemDataRole.UserRole)

        for i in range(self.kavram_listesi.count()):
            liste_ogesi = self.kavram_listesi.item(i)
            if liste_ogesi.data(Qt.ItemDataRole.UserRole) == kavram_id:
                self.kavram_listesi.setCurrentItem(liste_ogesi)
                return

        self._kavram_detayini_goster(kavram_id)

    def sayfa_detayini_ac(self, oge: QListWidgetItem):
        sayfa_id = oge.data(Qt.ItemDataRole.UserRole)
        dialog = SayfaDetayDialogu(sayfa_id, self)
        dialog.exec()


class GlobalGrafSekmesi(QWidget):
    """
    "Global Graf" sekmesi: sayfalar arasi baglanti haritasi (Katman 2) -
    GET /graph/global. Bu, SayfaDetayDialogu'ndaki sayfa ICI grafikten
    (Katman 1) farkli - orada tek bir sayfanin kavramlari/iliskileri
    var, burada FARKLI sayfalarin birbirine baglanmasi var. Iki tur
    baglanti gosterir:
    - Yonsuz "ortak kavram" baglantilari (SayfaBaglantisi) - iki sayfa
      AYNI kavramdan geciyor.
    - Yonlu/tipli iliskiler (SayfaIliskisi) - iki sayfa, ConceptRelation
      uzerinden BAGLI (orn. ONKOSUL) FARKLI kavramlar iceriyor.

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

        # graph.html'deki gorsel (renkli, etkilesimli) graf goruntuleyiciyi
        # sistemin varsayilan tarayicisinda, DOGRUDAN Katman 2 (global)
        # goruntusune ac - baglanti_listesi'ndeki duz metin listesinin
        # gorsel karsiligi.
        self.gorsel_graf_butonu = QPushButton("Gorsel Grafigi Ac (Tarayicida)")
        self.gorsel_graf_butonu.clicked.connect(self.gorsel_grafigi_ac)

        self.baglanti_listesi = QListWidget()

        self.durum_etiketi = QLabel("Baglantilari gormek icin 'Yenile'ye bas")

        ust_satir = QHBoxLayout()
        ust_satir.addWidget(self.yenile_butonu)
        ust_satir.addWidget(self.yeniden_hesapla_butonu)
        ust_satir.addWidget(self.gorsel_graf_butonu)

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

        if not graf["baglantilar"] and not graf["sayfa_iliskileri"]:
            self.baglanti_listesi.addItem(QListWidgetItem("Henuz baglanti yok - 'Yeniden Hesapla'yi dene"))
            self.durum_etiketi.setText("0 baglanti, 0 iliski")
            return

        # Once yonsuz "ortak kavram" baglantilari (SayfaBaglantisi)...
        for baglanti in graf["baglantilar"]:
            baslik_1 = id_to_baslik.get(baglanti["sayfa_id_1"], f"#{baglanti['sayfa_id_1']}")
            baslik_2 = id_to_baslik.get(baglanti["sayfa_id_2"], f"#{baglanti['sayfa_id_2']}")
            metin = f"{baslik_1}  ↔  {baslik_2}   (ortak kavram: {baglanti['ortak_kavram_ismi']})"
            self.baglanti_listesi.addItem(QListWidgetItem(metin))

        # ...sonra YONLU/TIPLI iliskiler (SayfaIliskisi) - ConceptRelation'a
        # dayali, hangi kavram ciftinin bu baglantiya sebep oldugunu da
        # gosteriyor.
        for iliski in graf["sayfa_iliskileri"]:
            baslik_kaynak = id_to_baslik.get(iliski["kaynak_sayfa_id"], f"#{iliski['kaynak_sayfa_id']}")
            baslik_hedef = id_to_baslik.get(iliski["hedef_sayfa_id"], f"#{iliski['hedef_sayfa_id']}")
            metin = (
                f"{baslik_kaynak}  -[{iliski['iliski_tipi']}]->  {baslik_hedef}   "
                f"({iliski['kaynak_kavram_ismi']} -> {iliski['hedef_kavram_ismi']})"
            )
            self.baglanti_listesi.addItem(QListWidgetItem(metin))

        self.durum_etiketi.setText(
            f"{len(graf['baglantilar'])} baglanti, {len(graf['sayfa_iliskileri'])} iliski, "
            f"{len(graf['sayfalar'])} sayfa"
        )

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

    def gorsel_grafigi_ac(self):
        """
        graph.html'i (renkli, etkilesimli vis-network goruntuleyici)
        DOGRUDAN Katman 2 (global) goruntusune acilacak sekilde
        sistemin varsayilan tarayicisinda acar.
        """
        webbrowser.open(f"{BACKEND_URL}/static/graph.html?mod=global")


class AnaPencere(QMainWindow):
    """
    Uygulamanin ANA penceresi. Icerigi bir QTabWidget (sekmeler) -
    "Sohbet", "Ara", "Sayfalar", "Kategoriler", "Kavramlar" ve
    "Global Graf" - olusturuyor, her sekme kendi widget class'inda
    (SohbetSekmesi, AramaSekmesi, SayfalarSekmesi, KategorilerSekmesi,
    KavramlarSekmesi, GlobalGrafSekmesi) yasiyor.
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
        sekmeler.addTab(KategorilerSekmesi(), "Kategoriler")
        sekmeler.addTab(KavramlarSekmesi(), "Kavramlar")
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
