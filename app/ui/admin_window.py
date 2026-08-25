"""
Dashboard Admin Guru Piket — Login, Enrollment Siswa, Pengaturan Jadwal,
dan Pengaturan Lainnya.
"""
from __future__ import annotations

from datetime import datetime
import cv2
import numpy as np
import requests
import webbrowser
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
from app.device.setup import (
    proses_login_google_manual, load_config_lokal, simpan_config_lokal,
    update_env_file, CONFIG_PATH,
)

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

    def __init__(self, server_url: str, device_id: str, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.device_id = device_id
        self._oauth_server = None
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        judul = QLabel("🔐 Setup Device — Login Google")
        judul.setAlignment(Qt.AlignCenter)
        judul.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(judul)

        sub = QLabel("Klik tombol di bawah untuk login Google.\nSistem akan otomatis mendaftarkan device ini ke server.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        layout.addWidget(sub)
        layout.addSpacing(12)

        self.input_lokasi = QLineEdit()
        self.input_lokasi.setPlaceholderText("Nama Lokasi (misal: Gerbang Utama)")
        self.input_lokasi.setStyleSheet(
            f"background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; "
            f"border: 1px solid {WARNA['border']}; border-radius: 6px; padding: 8px 12px; font-size: 13px;"
        )
        self.input_lokasi.setMaximumWidth(400)
        layout.addWidget(self.input_lokasi, alignment=Qt.AlignCenter)

        # Tombol utama: Login Google
        self.btn_google = QPushButton("🌐 Login dengan Google Sekolah")
        self.btn_google.setObjectName("btnPrimary")
        self.btn_google.setMinimumWidth(360)
        self.btn_google.setMinimumHeight(48)
        self.btn_google.setStyleSheet(
            "QPushButton { background-color: #4285f4; color: white; border: none; border-radius: 8px; "
            "font-size: 16px; font-weight: 600; }"
            "QPushButton:hover { background-color: #357ae8; }"
            "QPushButton:disabled { background-color: #1a4a8a; color: #93c5fd; }"
        )
        self.btn_google.clicked.connect(self._mulai_login_google)
        layout.addWidget(self.btn_google, alignment=Qt.AlignCenter)

        layout.addSpacing(8)

        # Progress
        self.label_progress = QLabel("")
        self.label_progress.setAlignment(Qt.AlignCenter)
        self.label_progress.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        self.label_progress.setVisible(False)
        layout.addWidget(self.label_progress)

        # Status error/sukses
        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignCenter)
        self.label_status.setWordWrap(True)
        self.label_status.setMaximumWidth(500)
        self.label_status.setVisible(False)
        layout.addWidget(self.label_status)

        layout.addSpacing(16)

        # Fallback: manual token
        fallback = QFrame()
        fallback.setStyleSheet(
            f"background-color: {WARNA['surface']}; border-radius: 8px; border: 1px solid {WARNA['border']}; padding: 12px;"
        )
        fallback_layout = QVBoxLayout(fallback)
        lbl_fallback = QLabel("📋 Atau paste Google ID Token secara manual:")
        lbl_fallback.setStyleSheet(f"font-size: 12px; color: {WARNA['teks_muted']};")
        fallback_layout.addWidget(lbl_fallback)

        token_row = QHBoxLayout()
        self.input_token = QLineEdit()
        self.input_token.setPlaceholderText("Google ID Token (opsional)")
        self.input_token.setStyleSheet(
            f"background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; "
            f"border: 1px solid {WARNA['border']}; border-radius: 6px; padding: 6px 10px; font-size: 12px;"
        )
        token_row.addWidget(self.input_token)
        self.btn_manual = QPushButton("Submit")
        self.btn_manual.clicked.connect(self._manual_token)
        token_row.addWidget(self.btn_manual)
        fallback_layout.addLayout(token_row)
        layout.addWidget(fallback)

        layout.addStretch()

    def _progress(self, msg: str):
        self.label_progress.setText(msg)
        self.label_progress.setVisible(True)
        self.label_status.setVisible(False)

    def _error(self, msg: str):
        self.label_status.setText(msg)
        self.label_status.setStyleSheet(f"font-size: 13px; color: {WARNA['bahaya_teks']};")
        self.label_status.setVisible(True)
        self.label_progress.setVisible(False)

    def _sukses(self, msg: str):
        self.label_status.setText(msg)
        self.label_status.setStyleSheet(f"font-size: 13px; color: {WARNA['sukses_teks']};")
        self.label_status.setVisible(True)

    def _mulai_login_google(self):
        """Mulai flow OAuth Google otomatis."""
        self.btn_google.setEnabled(False)
        self.btn_google.setText("⏳ Menyiapkan...")
        self._progress("Mencari port lokal untuk callback...")

        from app.device.oauth_server import mulai_google_oauth_flow

        try:
            result = mulai_google_oauth_flow(
                server_url=self.server_url,
                device_id=self.device_id,
                nama_lokasi=self.input_lokasi.text().strip() or "Gerbang Utama",
                on_progress=self._progress,
                on_success=self._on_oauth_sukses,
                on_error=self._on_oauth_error,
            )
            if result is None:
                # Flow dimulai di background thread, tunggu callback
                self.btn_google.setText("🌐 Menunggu login Google di browser...")
            else:
                # Error langsung
                self._on_oauth_error(result)
        except Exception as e:
            self._on_oauth_error(str(e))

    def _on_oauth_sukses(self, api_key: str, nama: str):
        """Callback saat OAuth + registrasi berhasil."""
        self._sukses(f"✅ Berhasil! Device terdaftar sebagai '{nama}'")
        self.btn_google.setText("✅ Selesai")
        QTimer.singleShot(1500, lambda: self.login_berhasil.emit("oauth_done"))

    def _on_oauth_error(self, msg: str):
        self._error(msg)
        self.btn_google.setEnabled(True)
        self.btn_google.setText("🌐 Login dengan Google Sekolah")

    def _manual_token(self):
        token = self.input_token.text().strip()
        if not token:
            self._error("Token harus diisi!")
            return
        if token.lower() == "offline":
            from app.device.setup import simpan_config_lokal
            simpan_config_lokal("offline", self.device_id, "offline")
            self.login_berhasil.emit("offline_token")
            return

        self.btn_manual.setEnabled(False)
        self._progress("Memproses token manual...")
        from app.device.setup import proses_login_google_manual
        lokasi = self.input_lokasi.text().strip() or "Gerbang Utama"

        def _run():
            hasil = proses_login_google_manual(self.server_url, token, self.device_id, lokasi)
            QTimer.singleShot(0, lambda: self._selesai_manual(hasil))

        threading.Thread(target=_run, daemon=True).start()

    def _selesai_manual(self, hasil):
        self.btn_manual.setEnabled(True)
        if hasil.success:
            self._sukses(f"✅ Device terdaftar! API Key tersimpan.")
            QTimer.singleShot(1500, lambda: self.login_berhasil.emit(hasil.jwt_token))
        else:
            self._error(hasil.error)


class AdminWindow(QMainWindow):
    def __init__(self, engine: MiniFASNetEngine, repo: AbsensiRepository,
                 server_url: str, face_encryption_key: str, device_id: str):
        super().__init__()
        self.setWindowTitle("Panel Admin & Guru Piket — Absensi")
        self.resize(1000, 650)
        self.setStyleSheet(STYLESHEET_ADMIN)

        # Cek apakah device sudah terdaftar
        config = load_config_lokal()
        sudah_terdaftar = (
            config.get("device_id") == device_id and
            config.get("api_key") and
            config.get("api_key") != "offline"
        )

        if sudah_terdaftar:
            # Langsung ke dashboard
            role = config.get("role", "guru_piket")
            self._build_dashboard_ui(engine, repo, face_encryption_key, role, server_url)
        else:
            # Tampilkan login screen
            self._build_login_flow(engine, repo, server_url, face_encryption_key, device_id)

    def _build_login_flow(self, engine, repo, server_url, face_encryption_key, device_id):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setAlignment(Qt.AlignCenter)

        self.login_screen = LoginScreen(server_url, device_id)
        self.login_screen.login_berhasil.connect(
            lambda token: self._on_login_success(token, engine, repo, server_url, face_encryption_key, device_id)
        )
        main_layout.addWidget(self.login_screen)
        self.setCentralWidget(main_widget)

    def _on_login_success(self, token, engine, repo, server_url, face_encryption_key, device_id):
        """Setelah login berhasil, bangun dashboard admin."""
        # Ambil role dari config
        config = load_config_lokal()
        role = config.get("role", "guru_piket")
        self._build_dashboard_ui(engine, repo, face_encryption_key, role)
        self.setWindowTitle(f"Panel Admin — {device_id} ({role})")

    def _build_dashboard_ui(self, engine, repo, face_encryption_key, role="guru_piket"):
        """Bangun tampilan dashboard admin setelah login."""
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {WARNA['surface']}; border-right: 1px solid {WARNA['border']};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 20, 12, 20)
        side_layout.setSpacing(8)

        # Logo + role badge
        is_admin = role in ("admin", "superadmin")
        lbl_logo = QLabel("🛠️ Panel Admin" if is_admin else "📋 Guru Piket")
        lbl_logo.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 4px;")
        side_layout.addWidget(lbl_logo)

        lbl_role = QLabel(f"Role: {role}")
        lbl_role.setStyleSheet(f"font-size: 11px; color: {WARNA['teks_muted']}; padding-bottom: 12px;")
        side_layout.addWidget(lbl_role)

        # Stack
        self.stack = QStackedWidget()
        idx = 0

        # 1. Enrollment Siswa — semua role bisa
        self.btn_nav_enroll = QPushButton("📸 Enrollment Siswa")
        self.btn_nav_enroll.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        side_layout.addWidget(self.btn_nav_enroll)
        self.enroll_screen = QWidget()
        self._build_enroll_ui(self.enroll_screen, engine, repo, face_encryption_key)
        self.stack.addWidget(self.enroll_screen)
        idx += 1

        # 2. Data Siswa — semua role bisa
        self.btn_nav_data = QPushButton("📋 Data Siswa")
        self.btn_nav_data.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        side_layout.addWidget(self.btn_nav_data)
        self.data_screen = QWidget()
        self._build_data_ui(self.data_screen, repo)
        self.stack.addWidget(self.data_screen)
        idx += 1

        # 3. Pengaturan Jadwal — admin only
        if is_admin:
            self.btn_nav_jadwal = QPushButton("📅 Pengaturan Jadwal")
            self.btn_nav_jadwal.clicked.connect(lambda: self.stack.setCurrentIndex(2))
            side_layout.addWidget(self.btn_nav_jadwal)
            self.jadwal_screen = QWidget()
            self._build_jadwal_ui(self.jadwal_screen, server_url)
            self.stack.addWidget(self.jadwal_screen)
            idx += 1

            # 4. Pengaturan Guru — admin only
            self.btn_nav_guru = QPushButton("👩‍🏫 Data Guru")
            self.btn_nav_guru.clicked.connect(lambda: self.stack.setCurrentIndex(3))
            side_layout.addWidget(self.btn_nav_guru)
            self.guru_screen = QWidget()
            self._build_guru_ui(self.guru_screen, server_url)
            self.stack.addWidget(self.guru_screen)
            idx += 1

            # 5. Laporan — admin only
            self.btn_nav_laporan = QPushButton("📊 Laporan")
            self.btn_nav_laporan.clicked.connect(lambda: self.stack.setCurrentIndex(4))
            side_layout.addWidget(self.btn_nav_laporan)
            self.laporan_screen = QWidget()
            self._build_laporan_ui(self.laporan_screen, server_url)
            self.stack.addWidget(self.laporan_screen)
            idx += 1

            # 6. Sinkronisasi — admin only
            self.btn_nav_sync = QPushButton("🔄 Sinkronisasi Server")
            self.btn_nav_sync.clicked.connect(lambda: self.stack.setCurrentIndex(5))
            side_layout.addWidget(self.btn_nav_sync)
            self.sync_screen = QWidget()
            self._build_sync_ui(self.sync_screen, server_url)
            self.stack.addWidget(self.sync_screen)
            idx += 1

        side_layout.addStretch()

        btn_tutup = QPushButton("❌ Tutup Panel")
        btn_tutup.setObjectName("btnDanger")
        btn_tutup.clicked.connect(self.close)
        side_layout.addWidget(btn_tutup)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)
        self.setCentralWidget(main_widget)

        # Info box
        config = load_config_lokal()
        api_key = config.get("api_key", "N/A")
        device_id = config.get("device_id", "N/A")
        QMessageBox.information(
            self, "Login Berhasil",
            f"Device '{device_id}' terdaftar!\nAPI Key: {api_key[:16]}...\n\nAnda sekarang bisa menggunakan panel admin."
        )

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

    def _build_jadwal_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("📅 Pengaturan Jadwal Sekolah")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        
        info = QLabel("Fitur ini memungkinkan admin mengatur jam masuk, jam pulang, dan hari libur.")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Placeholder for actual implementation
        layout.addStretch()
        btn_web = QPushButton("🌐 Buka Dashboard Web untuk Pengaturan Lengkap")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{server_url}/dashboard/jadwal"))
        layout.addWidget(btn_web)

    def _build_guru_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("👩‍🏫 Manajemen Data Guru & Staf")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        layout.addStretch()
        btn_web = QPushButton("🌐 Kelola Guru di Dashboard Web")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{server_url}/dashboard/guru"))
        layout.addWidget(btn_web)

    def _build_laporan_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("📊 Laporan & Rekap Absensi")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        layout.addStretch()
        btn_web = QPushButton("🌐 Lihat Laporan Lengkap di Web")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{server_url}/dashboard/laporan"))
        layout.addWidget(btn_web)

    def _build_sync_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("🔄 Sinkronisasi Manual")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        
        btn_sync = QPushButton("🚀 Jalankan Sinkronisasi Sekarang")
        btn_sync.setObjectName("btnPrimary")
        layout.addWidget(btn_sync)
        
        self.log_sync = QTextEdit()
        self.log_sync.setReadOnly(True)
        self.log_sync.setPlaceholderText("Log sinkronisasi akan muncul di sini...")
        layout.addWidget(self.log_sync)
        layout.addStretch()
