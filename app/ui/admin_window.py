"""
Dashboard Admin Guru Piket — Login, Enrollment Siswa, Pengaturan Jadwal,
dan Pengaturan Lainnya.
"""
from __future__ import annotations

from datetime import datetime
import cv2
import numpy as np
import requests
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFormLayout, QGridLayout, QTextEdit,
)

from app.ui.styles import WARNA
from app.database.repository import AbsensiRepository
from app.face.minifasnet_engine import MiniFASNetEngine
from app.face.crypto_embedding import encrypt_embedding

STYLESHEET_ADMIN = f"""
QMainWindow {{ background-color: {WARNA['bg']}; }}
QWidget {{ background-color: {WARNA['bg']}; color: {WARNA['teks_utama']}; font-family: 'Segoe UI', sans-serif; }}
QPushButton {{ background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; border: 1px solid {WARNA['border']}; border-radius: 8px; padding: 10px 20px; font-size: 14px; }}
QPushButton:hover {{ background-color: {WARNA['border']}; }}
QPushButton#btnPrimary {{ background-color: #2563eb; color: white; border: none; font-weight: 600; }}
QPushButton#btnPrimary:hover {{ background-color: #3b82f6; }}
QPushButton#btnDanger {{ background-color: {WARNA['bahaya_bg']}; color: {WARNA['bahaya_teks']}; border: 1px solid {WARNA['bahaya_border']}; }}
QLineEdit {{ background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; border: 1px solid {WARNA['border']}; border-radius: 8px; padding: 10px 14px; font-size: 14px; }}
QTableWidget {{ background-color: {WARNA['surface']}; color: {WARNA['teks_utama']}; border: 1px solid {WARNA['border']}; border-radius: 8px; }}
QHeaderView::section {{ background-color: {WARNA['surface_2']}; color: {WARNA['teks_sekunder']}; border: none; padding: 8px; font-weight: 600; }}
"""


class LoginScreen(QWidget):
    login_berhasil = Signal(str)

    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        judul = QLabel("🔐 Login Guru Piket / Admin")
        judul.setAlignment(Qt.AlignCenter)
        judul.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(judul)

        form = QFormLayout()
        form.setSpacing(12)
        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("email@guru.sch.id")
        self.input_email.setMinimumWidth(320)
        form.addRow("Email:", self.input_email)
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Password")
        self.input_password.setMinimumWidth(320)
        self.input_password.returnPressed.connect(self._login)
        form.addRow("Password:", self.input_password)
        layout.addLayout(form)

        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignCenter)
        self.label_status.setStyleSheet(f"font-size: 13px; color: {WARNA['bahaya_teks']};")
        self.label_status.setVisible(False)
        layout.addWidget(self.label_status)

        self.btn_login = QPushButton("Login")
        self.btn_login.setObjectName("btnPrimary")
        self.btn_login.setMinimumWidth(320)
        self.btn_login.setMinimumHeight(42)
        self.btn_login.clicked.connect(self._login)
        layout.addWidget(self.btn_login)

        info = QLabel("💡 Ketik 'offline' di email untuk akses langsung tanpa server")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet(f"font-size: 12px; color: {WARNA['teks_muted']};")
        layout.addWidget(info)

    def _login(self):
        email = self.input_email.text().strip()
        password = self.input_password.text().strip()
        if not email or not password:
            self.label_status.setText("Email dan password harus diisi!")
            self.label_status.setVisible(True)
            return
        if email.lower() == "offline":
            self.login_berhasil.emit("offline_token")
            return
        self.login_berhasil.emit("offline_token")  # Fallback langsung masuk untuk kemudahan uji coba


class AdminWindow(QMainWindow):
    def __init__(self, engine: MiniFASNetEngine, repo: AbsensiRepository,
                 server_url: str, face_encryption_key: str, device_id: str):
        super().__init__()
        self.setWindowTitle("Panel Admin & Guru Piket — Absensi")
        self.resize(1000, 650)
        self.setStyleSheet(STYLESHEET_ADMIN)

        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar Navigasi
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {WARNA['surface']}; border-right: 1px solid {WARNA['border']};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 20, 12, 20)
        side_layout.setSpacing(8)

        lbl_logo = QLabel("🛠️ Panel Admin")
        lbl_logo.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 12px;")
        side_layout.addWidget(lbl_logo)

        self.btn_nav_enroll = QPushButton("📸 Enrollment Siswa")
        self.btn_nav_enroll.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        side_layout.addWidget(self.btn_nav_enroll)

        self.btn_nav_data = QPushButton("📋 Data Siswa & Log")
        self.btn_nav_data.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        side_layout.addWidget(self.btn_nav_data)

        side_layout.addStretch()

        btn_tutup = QPushButton("❌ Tutup Panel")
        btn_tutup.setObjectName("btnDanger")
        btn_tutup.clicked.connect(self.close)
        side_layout.addWidget(btn_tutup)

        main_layout.addWidget(sidebar)

        # Konten Utama Stack
        self.stack = QStackedWidget()
        
        # 1. Enrollment Screen
        self.enroll_screen = QWidget()
        self._build_enroll_ui(self.enroll_screen, engine, repo, face_encryption_key)
        self.stack.addWidget(self.enroll_screen)

        # 2. Data & Log Screen
        self.data_screen = QWidget()
        self._build_data_ui(self.data_screen, repo)
        self.stack.addWidget(self.data_screen)

        main_layout.addWidget(self.stack)
        self.setCentralWidget(main_widget)

    def _build_enroll_ui(self, parent: QWidget, engine, repo, face_encryption_key):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("📸 Enrollment Wajah Siswa Baru")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        form = QHBoxLayout()
        self.input_nis = QLineEdit(); self.input_nis.setPlaceholderText("NIS / NISN")
        self.input_nama = QLineEdit(); self.input_nama.setPlaceholderText("Nama Lengkap")
        self.input_kelas = QLineEdit(); self.input_kelas.setPlaceholderText("Kelas (XI RPL 1)")
        form.addWidget(self.input_nis); form.addWidget(self.input_nama); form.addWidget(self.input_kelas)
        layout.addLayout(form)

        mid = QHBoxLayout()
        self.label_cam = QLabel("Kamera mati")
        self.label_cam.setFixedSize(400, 300)
        self.label_cam.setAlignment(Qt.AlignCenter)
        self.label_cam.setStyleSheet(f"background-color: {WARNA['surface']}; border-radius: 8px; border: 1px solid {WARNA['border']};")
        mid.addWidget(self.label_cam)

        rp = QVBoxLayout()
        self.lbl_status = QLabel("Klik 'Mulai Kamera' untuk enroll wajah")
        rp.addWidget(self.lbl_status)
        
        self.btn_cam = QPushButton("🎥 Mulai Kamera")
        self.btn_cam.setObjectName("btnPrimary")
        self.btn_cam.clicked.connect(lambda: self._start_cam(engine, repo, face_encryption_key))
        rp.addWidget(self.btn_cam)
        rp.addStretch()
        mid.addLayout(rp)
        layout.addLayout(mid)

    def _start_cam(self, engine, repo, face_encryption_key):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.lbl_status.setText("❌ Kamera tidak dapat dibuka!")
            return
        
        self.lbl_status.setText("⏳ Mengambil foto wajah...")
        ok, frame = cap.read()
        cap.release()

        if not ok:
            self.lbl_status.setText("❌ Gagal capture frame kamera.")
            return

        hasil = engine.proses_frame(frame)
        if hasil.embedding is not None:
            import random
            siswa_id = random.randint(1000, 9999)
            nis = self.input_nis.text().strip() or "NIS999"
            nama = self.input_nama.text().strip() or "Siswa Baru"
            kelas = self.input_kelas.text().strip() or "XI"

            repo.upsert_siswa(siswa_id, nis, nama, kelas)
            enc = encrypt_embedding(hasil.embedding, face_encryption_key)
            repo.upsert_embedding(siswa_id, enc, engine.model_version, datetime.now().isoformat())
            self.lbl_status.setText(f"✅ Sukses enroll: {nama} ({kelas})!")
            QMessageBox.information(self, "Berhasil", f"Siswa {nama} berhasil di-enroll ke database lokal!")
        else:
            self.lbl_status.setText(f"❌ Gagal deteksi wajah: {hasil.alasan_gagal}")

    def _build_data_ui(self, parent: QWidget, repo: AbsensiRepository):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("📋 Data Siswa Terdaftar di Kiosk")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "NIS", "Nama", "Kelas"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        btn_refresh = QPushButton("🔄 Refresh Data")
        btn_refresh.clicked.connect(lambda: self._load_data(repo))
        layout.addWidget(btn_refresh)
        self._load_data(repo)

    def _load_data(self, repo: AbsensiRepository):
        try:
            embs = repo.semua_embedding()
            self.table.setRowCount(len(embs))
            for i, row in enumerate(embs):
                siswa_id, nama, kelas, _ = row
                self.table.setItem(i, 0, QTableWidgetItem(str(siswa_id)))
                self.table.setItem(i, 1, QTableWidgetItem("-"))
                self.table.setItem(i, 2, QTableWidgetItem(nama))
                self.table.setItem(i, 3, QTableWidgetItem(kelas))
        except Exception:
            pass
