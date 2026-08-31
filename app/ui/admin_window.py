"""
Dashboard Admin Guru Piket — Login, Enrollment Siswa, Pengaturan Jadwal,
dan Pengaturan Lainnya.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date
import cv2
import numpy as np
import requests
import webbrowser

logger = logging.getLogger(__name__)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QImage, QPixmap, QColor, QAction, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFormLayout, QGridLayout, QTextEdit,
    QListWidget, QListWidgetItem, QProgressBar, QInputDialog, QScrollArea,
    QCheckBox, QComboBox,
)

from app.ui.styles import WARNA
from app.database.repository import AbsensiRepository
from app.face.minifasnet_engine import MiniFASNetEngine
from app.face.crypto_embedding import encrypt_embedding
from app.device.setup import (
    proses_login_google_manual, load_config_lokal, simpan_config_lokal,
    save_config_lokal, update_env_file, CONFIG_PATH,
)
from app.device.camera import daftar_kamera
from app.config import settings

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

        from app.device.oauth_server import mulai_google_oauth_flow_sync

        server_url = self.server_url
        device_id = self.device_id
        nama_lokasi = self.input_lokasi.text().strip() or "Gerbang Utama"

        def _run():
            try:
                hasil = mulai_google_oauth_flow_sync(
                    server_url=server_url,
                    device_id=device_id,
                    nama_lokasi=nama_lokasi,
                )
                logger.info(
                    "OAuth flow selesai: success=%s, error=%s, api_key=%s",
                    hasil.success, hasil.error or "-", bool(hasil.api_key),
                )
            except Exception as e:
                import traceback
                logger.error("OAuth flow gagal: %s\n%s", e, traceback.format_exc())
                hasil = LoginResult()
                hasil.success = False
                hasil.error = f"Login gagal: {e}"
            # Gunakan QMetaObject.invokeMethod agar callback dijalankan di GUI thread
            from PySide6.QtCore import QMetaObject, Q_ARG, Qt as QtConst
            if hasil.success:
                QMetaObject.invokeMethod(
                    self, "_on_oauth_sukses_thread",
                    QtConst.QueuedConnection,
                    Q_ARG(str, hasil.api_key), Q_ARG(str, hasil.nama),
                )
            elif hasil.needs_api_key:
                # Device sudah terdaftar tapi API key hilang — minta user
                # menulis ulang API key manual.
                QMetaObject.invokeMethod(
                    self, "_on_oauth_needs_api_key_thread",
                    QtConst.QueuedConnection,
                    Q_ARG(str, hasil.jwt_token), Q_ARG(str, hasil.nama),
                )
            else:
                QMetaObject.invokeMethod(
                    self, "_on_oauth_error_thread",
                    QtConst.QueuedConnection,
                    Q_ARG(str, hasil.error),
                )

        import threading
        threading.Thread(target=_run, daemon=True).start()
        self.btn_google.setText("🌐 Menunggu login Google di browser...")

    # Decorator agar PySide5/6 bisa memanggil dari QMetaObject.invokeMethod
    from PySide6.QtCore import Slot
    @Slot(str, str)
    def _on_oauth_sukses_thread(self, api_key: str, nama: str):
        logger.debug("_on_oauth_sukses_thread called, api_key=%s...", api_key[:16])
        self._on_oauth_sukses(api_key, nama)

    @Slot(str)
    def _on_oauth_error_thread(self, msg: str):
        self._on_oauth_error(msg)

    @Slot(str, str)
    def _on_oauth_needs_api_key_thread(self, jwt_token: str, nama: str):
        self._on_oauth_needs_api_key(jwt_token, nama)

    def _on_oauth_needs_api_key(self, jwt_token: str, nama: str):
        """Device sudah terdaftar tapi API key hilang — minta user menulis ulang."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        from app.device.setup import simpan_config_lokal

        api_key, ok = QInputDialog.getText(
            self,
            "API Key Diperlukan",
            "Device sudah terdaftar di server, tapi API key tidak ditemukan "
            "di perangkat ini.\n\nMasukkan API key device untuk melanjutkan:",
            QLineEdit.Password,
        )
        if not ok or not api_key.strip():
            self._error("API key tidak diisi. Registrasi dibatalkan.")
            self.btn_google.setEnabled(True)
            self.btn_google.setText("🌐 Login dengan Google Sekolah")
            return

        api_key = api_key.strip()
        try:
            simpan_config_lokal(
                api_key=api_key,
                device_id=self.device_id,
                jwt_token=jwt_token,
                nama=nama,
            )
            self._sukses(f"✅ API key tersimpan! Device '{nama}' siap digunakan.")
            self.btn_google.setText("✅ Selesai")
            QTimer.singleShot(1200, lambda: self.login_berhasil.emit(jwt_token))
        except Exception as e:
            logger.error("Gagal menyimpan API key: %s", e)
            self._error(f"Gagal menyimpan API key: {e}")
            self.btn_google.setEnabled(True)
            self.btn_google.setText("🌐 Login dengan Google Sekolah")

    def _on_oauth_sukses(self, api_key: str, nama: str):
        """Callback saat OAuth + registrasi berhasil."""
        self._sukses(f"✅ Berhasil! Device terdaftar sebagai '{nama}'")
        self.btn_google.setText("✅ Selesai")
        # Ambil token dari config yang baru disimpan
        config = load_config_lokal()
        token = config.get("jwt_token", "oauth_done")
        logger.debug("emitting login_berhasil with token: %s...", token[:10])
        self.login_berhasil.emit(token)

    def _on_oauth_error(self, msg: str):
        self._error(msg)
        self.btn_google.setEnabled(True)
        self.btn_google.setText("🌐 Login dengan Google Sekolah")

    def _manual_token(self):
        token = self.input_token.text().strip()
        if not token:
            self._error("Token harus diisi!")
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
    logout_admin = Signal()
    login_sukses_signal = Signal()
    window_closed = Signal()
    jadwal_refresh_selesai = Signal(object, object, str)

    def __init__(self, engine: MiniFASNetEngine, repo: AbsensiRepository,
                 server_url: str, face_encryption_key: str, device_id: str,
                 bypass_login: bool = False, sync_service=None, dashboard_url: str = ""):
        super().__init__()
        self.setWindowTitle("Panel Admin & Guru Piket — Absensi")
        self.resize(1000, 650)
        self.setStyleSheet(STYLESHEET_ADMIN)

        # Simpan atribut instance untuk dipakai di seluruh method
        self.server_url = server_url
        self.dashboard_url = dashboard_url or server_url
        self.device_id = device_id
        self.face_encryption_key = face_encryption_key
        self.repo = repo
        self.sync_service = sync_service

        # Cek apakah device sudah terdaftar & user sudah login (JWT valid)
        config = load_config_lokal()
        sudah_terdaftar = (
            config.get("device_id") == device_id and
            config.get("api_key") and
            config.get("api_key") != "offline"
        )
        sudah_login = sudah_terdaftar and self._cek_jwt_valid(config.get("jwt_token", ""))

        if bypass_login:
            # Dibuka lewat password panel (⚙️ Panel Admin) — langsung ke
            # dashboard tanpa login Google. jwt_token diambil dari config
            # kalau ada (untuk fitur yang butuh server); kalau kosong,
            # fitur enrollment/jadwal akan minta login terpisah.
            role = config.get("role", "admin")
            self.jwt_token = config.get("jwt_token", "")
            self._build_dashboard_ui(engine, repo, face_encryption_key, role, server_url)
        elif sudah_login:
            # Langsung ke dashboard
            role = config.get("role", "guru_piket")
            self.jwt_token = config.get("jwt_token", "")
            self._build_dashboard_ui(engine, repo, face_encryption_key, role, server_url)
        else:
            # Tampilkan login screen
            self._build_login_flow(engine, repo, server_url, face_encryption_key, device_id)
        
        self.show()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def _cek_jwt_valid(jwt_token: str) -> bool:
        """Cek apakah JWT masih valid (belum expired) dan signature cocok
        dengan secret server. Secret diambil dari config lokal — kalau
        tidak tersedia, token dianggap TIDAK valid (fail-closed)."""
        if not jwt_token:
            return False
        try:
            import jwt, time
            from app.config import settings
            secret = settings.jwt_secret
            if not secret:
                return False
            payload = jwt.decode(
                jwt_token,
                key=secret,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
            return payload.get("exp", 0) > time.time()
        except Exception:
            return False

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
        logger.info("_on_login_success dipanggil, token=%s...", (token or "")[:10])
        try:
            config = load_config_lokal()
            self.jwt_token = config.get("jwt_token", "")
            self.server_url = server_url
            role = config.get("role", "guru_piket")
            self._build_dashboard_ui(engine, repo, face_encryption_key, role, server_url)
            logger.info("Dashboard admin berhasil dibangun (role=%s)", role)
            self.setWindowTitle(f"Panel Admin — {device_id} ({role})")
            self.login_sukses_signal.emit()

            # Kiosk berjalan fullscreen — panel admin harus TETAP di atas
            # window kiosk. Jangan pernah melepas flag StaysOnTop selama
            # panel terbuka, kalau tidak panel jatuh ke belakang kiosk
            # dan terlihat seperti "tidak terbuka".
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.raise_()
            self.activateWindow()

            logger.debug("done")
        except Exception as e:
            import traceback
            logger.error("Gagal membuka dashboard admin: %s\n%s", e, traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Gagal membuka dashboard: {str(e)}")

    def _build_dashboard_ui(self, engine, repo, face_encryption_key, role="guru_piket", server_url=""):
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
            self.btn_nav_jadwal.clicked.connect(self._load_jadwal_data)
            side_layout.addWidget(self.btn_nav_jadwal)
            self.jadwal_screen = QWidget()
            self._build_jadwal_ui(self.jadwal_screen, server_url)
            # Bungkus dalam scroll area supaya tidak numpuk saat fullscreen
            jadwal_scroll = QScrollArea()
            jadwal_scroll.setWidgetResizable(True)
            jadwal_scroll.setWidget(self.jadwal_screen)
            jadwal_scroll.setFrameShape(QFrame.NoFrame)
            self.stack.addWidget(jadwal_scroll)
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

            # 7. Pengaturan (.env) — admin only
            self.btn_nav_settings = QPushButton("⚙️ Pengaturan (.env)")
            self.btn_nav_settings.clicked.connect(lambda: self.stack.setCurrentIndex(6))
            side_layout.addWidget(self.btn_nav_settings)
            self.settings_screen = QWidget()
            self._build_settings_ui(self.settings_screen)
            settings_scroll = QScrollArea()
            settings_scroll.setWidgetResizable(True)
            settings_scroll.setWidget(self.settings_screen)
            settings_scroll.setFrameShape(QFrame.NoFrame)
            self.stack.addWidget(settings_scroll)
            idx += 1

        side_layout.addStretch()

        btn_tutup = QPushButton("🚪 Logout & Tutup")
        btn_tutup.setObjectName("btnDanger")
        btn_tutup.clicked.connect(self._proses_logout)
        side_layout.addWidget(btn_tutup)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)
        self.setCentralWidget(main_widget)
        self.stack.setCurrentIndex(0) # Pastikan halaman pertama (Enrollment) tampil
        self.update() # Paksa refresh UI

        # Info box - gunakan QTimer agar tidak memblokir rendering dashboard
        config = load_config_lokal()
        api_key = config.get("api_key", "N/A")
        device_id = config.get("device_id", "N/A")
        
        def _show_info():
            QMessageBox.information(
                self, "Login Berhasil",
                f"Device '{device_id}' terdaftar!\nAPI Key: {api_key[:16]}...\n\nAnda sekarang bisa menggunakan panel admin."
            )
        QTimer.singleShot(500, _show_info)

    def _proses_logout(self):
        """Logout: hapus role dari config, emit signal, tutup window."""
        config = load_config_lokal()
        config.pop("role", None)
        config.pop("admin_nama", None)
        save_config_lokal(config)
        self.logout_admin.emit()
        self.close()

    def _build_enroll_ui(self, parent: QWidget, engine, repo, face_encryption_key):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("📸 Enrollment Wajah Siswa Baru")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        # --- Pencarian siswa dari server (pilih berdasarkan NISN atau nama) ---
        box_cari = QFrame()
        box_cari.setStyleSheet(f"background-color: {WARNA['surface']}; border: 1px solid {WARNA['border']}; border-radius: 8px;")
        lay_cari = QVBoxLayout(box_cari)
        lay_cari.setContentsMargins(16, 12, 16, 12)
        lay_cari.setSpacing(8)

        lbl_cari = QLabel("🔎 Cari siswa dari server (NISN / Nama)")
        lbl_cari.setStyleSheet("font-size: 13px; font-weight: 600;")
        lay_cari.addWidget(lbl_cari)

        row_cari = QHBoxLayout()
        self.input_cari = QLineEdit()
        self.input_cari.setPlaceholderText("Ketik NISN atau nama siswa…")
        self.input_cari.textChanged.connect(self._filter_daftar_siswa)
        row_cari.addWidget(self.input_cari, 1)

        self.btn_muat_siswa = QPushButton("🔄 Muat dari Server")
        self.btn_muat_siswa.clicked.connect(self._muat_daftar_siswa)
        row_cari.addWidget(self.btn_muat_siswa)
        lay_cari.addLayout(row_cari)

        self.list_siswa = QListWidget()
        self.list_siswa.setMaximumHeight(140)
        self.list_siswa.itemClicked.connect(self._pilih_siswa_dari_list)
        lay_cari.addWidget(self.list_siswa)

        self.lbl_hasil_cari = QLabel("")
        self.lbl_hasil_cari.setStyleSheet(f"font-size: 12px; color: {WARNA['teks_sekunder']};")
        lay_cari.addWidget(self.lbl_hasil_cari)
        layout.addWidget(box_cari)

        form = QHBoxLayout()
        self.input_nis = QLineEdit(); self.input_nis.setPlaceholderText("NISN")
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
        self.btn_cam.clicked.connect(lambda: self._mulai_preview_kamera(engine, repo, face_encryption_key))
        rp.addWidget(self.btn_cam)

        self.btn_capture = QPushButton("📸 Ambil Foto & Enroll")
        self.btn_capture.setObjectName("btnPrimary")
        self.btn_capture.setEnabled(False)
        self.btn_capture.clicked.connect(lambda: self._capture_enroll(engine, repo, face_encryption_key))
        rp.addWidget(self.btn_capture)

        rp.addStretch()
        mid.addLayout(rp)
        layout.addLayout(mid)

    def _muat_daftar_siswa(self):
        """Muat daftar siswa dari server (GET /siswa) untuk dipilih saat enroll."""
        if not self.jwt_token:
            self.lbl_hasil_cari.setText("❌ Sesi login tidak valid, silakan login ulang.")
            return
        self.btn_muat_siswa.setEnabled(False)
        self.lbl_hasil_cari.setText("⏳ Memuat daftar siswa dari server…")
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            resp = requests.get(f"{self.server_url}/siswa", headers=headers, timeout=15)
            resp.raise_for_status()
            self._daftar_siswa_server = resp.json()
            self._filter_daftar_siswa()
            self.lbl_hasil_cari.setText(f"✅ {len(self._daftar_siswa_server)} siswa dimuat dari server.")
        except requests.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text[:200]}"
            logger.warning("Gagal memuat daftar siswa: %s", err_msg)
            self.lbl_hasil_cari.setText(f"❌ Gagal memuat siswa: {err_msg}")
        finally:
            self.btn_muat_siswa.setEnabled(True)

    def _filter_daftar_siswa(self):
        """Filter daftar siswa berdasarkan teks pencarian (NISN atau nama)."""
        if not hasattr(self, "_daftar_siswa_server"):
            return
        q = self.input_cari.text().strip().lower()
        self.list_siswa.clear()
        if not q:
            self.lbl_hasil_cari.setText(f"{len(self._daftar_siswa_server)} siswa tersedia. Ketik NISN/nama untuk memfilter.")
            return
        cocok = [
            s for s in self._daftar_siswa_server
            if q in s.get("nis", "").lower() or q in s.get("nama", "").lower()
        ]
        for s in cocok[:50]:
            status = "✅" if s.get("enrolled") else "⬜"
            item = QListWidgetItem(f"{status} {s.get('nis', '')} — {s.get('nama', '')} ({s.get('kelas', '')})")
            item.setData(Qt.UserRole, s)
            self.list_siswa.addItem(item)
        self.lbl_hasil_cari.setText(f"{len(cocok)} siswa cocok." if cocok else "Tidak ada siswa yang cocok.")

    def _pilih_siswa_dari_list(self, item: QListWidgetItem):
        """Isi form enroll dari siswa yang dipilih di daftar."""
        s = item.data(Qt.UserRole)
        self.input_nis.setText(s.get("nis", ""))
        self.input_nama.setText(s.get("nama", ""))
        self.input_kelas.setText(s.get("kelas", ""))
        self.lbl_hasil_cari.setText(f"Dipilih: {s.get('nama', '')} ({s.get('kelas', '')}) — klik 'Ambil Foto & Enroll'.")

    def _mulai_preview_kamera(self, engine, repo, face_encryption_key):
        """Mulai live preview kamera di label_cam."""
        if hasattr(self, "_cap_enroll") and self._cap_enroll is not None:
            return  # Sudah jalan

        cap = cv2.VideoCapture(settings.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(settings.camera_index)
        if not cap.isOpened():
            self.lbl_status.setText("❌ Kamera tidak dapat dibuka!")
            return

        self._cap_enroll = cap
        self._timer_enroll = QTimer(self)
        self._timer_enroll.timeout.connect(lambda: self._update_preview_kamera())
        self._timer_enroll.start(50)  # 20 fps

        self.btn_cam.setEnabled(False)
        self.btn_capture.setEnabled(True)
        self.lbl_status.setText("✅ Kamera aktif. Arahkan wajah ke kamera, lalu klik 'Ambil Foto'.")

    def _update_preview_kamera(self):
        """Update frame kamera ke label_cam."""
        if not hasattr(self, "_cap_enroll") or self._cap_enroll is None:
            return
        ok, frame = self._cap_enroll.read()
        if not ok:
            return
        # Simpan frame terakhir untuk capture
        self._last_frame = frame.copy()
        # Convert BGR ke RGB untuk QLabel
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        from PySide6.QtGui import QImage
        img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.label_cam.setPixmap(QPixmap.fromImage(img).scaled(
            self.label_cam.width(), self.label_cam.height(), Qt.KeepAspectRatio
        ))

    def _capture_enroll(self, engine, repo, face_encryption_key):
        """Capture frame terakhir dan enroll ke server."""
        if not hasattr(self, "_last_frame") or self._last_frame is None:
            self.lbl_status.setText("❌ Belum ada frame kamera. Klik 'Mulai Kamera' dulu.")
            return

        frame = self._last_frame
        # Stop preview
        if hasattr(self, "_timer_enroll"):
            self._timer_enroll.stop()
        if hasattr(self, "_cap_enroll") and self._cap_enroll is not None:
            self._cap_enroll.release()
            self._cap_enroll = None

        self.btn_cam.setEnabled(True)
        self.btn_capture.setEnabled(False)

        hasil = engine.proses_frame(frame, skip_liveness=True)
        if hasil.embedding is None:
            self.lbl_status.setText(f"❌ Gagal deteksi wajah: {hasil.alasan_gagal}")
            return

        nis = self.input_nis.text().strip()
        nama = self.input_nama.text().strip()
        kelas = self.input_kelas.text().strip()
        if not nis or not nama or not kelas:
            self.lbl_status.setText("❌ NISN, nama, dan kelas wajib diisi.")
            return

        if not self.jwt_token:
            self.lbl_status.setText("❌ Sesi login tidak valid, silakan login ulang.")
            return

        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        self.lbl_status.setText("⏳ Mendaftarkan siswa ke server...")

        try:
            # 1. Cari siswa yang sudah ada berdasarkan NIS, atau buat baru
            resp_list = requests.get(f"{self.server_url}/siswa", headers=headers, timeout=15)
            resp_list.raise_for_status()
            existing = next((s for s in resp_list.json() if s["nis"] == nis), None)

            if existing:
                siswa_id = existing["id"]
            else:
                resp_create = requests.post(
                    f"{self.server_url}/siswa", headers=headers,
                    json={"nis": nis, "nama": nama, "kelas": kelas}, timeout=15,
                )
                resp_create.raise_for_status()
                siswa_id = resp_create.json()["id"]

            # 2. Kirim embedding ke server
            self.lbl_status.setText("⏳ Mengirim data wajah ke server...")
            payload = {
                "embedding": hasil.embedding.tolist(),
                "model_version": engine.model_version,
            }
            logger.debug("Enroll payload: %d dim, model=%s", len(payload["embedding"]), payload["model_version"])
            resp_enroll = requests.post(
                f"{self.server_url}/siswa/{siswa_id}/enroll", headers=headers,
                json=payload, timeout=30,
            )
            logger.debug("Enroll response: %s %s", resp_enroll.status_code, resp_enroll.text[:200])
            resp_enroll.raise_for_status()

        except requests.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text[:300]}"
            logger.warning("Enrollment gagal ke server: %s", err_msg)
            self.lbl_status.setText(f"❌ Enrollment gagal: {err_msg}")
            QMessageBox.critical(
                self, "Enrollment Gagal",
                f"Tidak bisa mendaftarkan siswa ke server.\n\n{err_msg}\n\n"
                "Enrollment butuh koneksi ke server (ID siswa berasal dari "
                "server). Coba lagi setelah koneksi tersedia.",
            )
            return   # <-- KUNCI PERBAIKAN: hentikan di sini, jangan lanjut

        # Titik ini HANYA tercapai kalau proses ke server berhasil penuh
        repo.upsert_siswa(siswa_id, nis, nama, kelas)
        enc = encrypt_embedding(hasil.embedding, face_encryption_key)
        repo.upsert_embedding(siswa_id, enc, engine.model_version, datetime.now().isoformat())

        self.lbl_status.setText(f"✅ {nama} berhasil di-enroll!")
        QMessageBox.information(self, "Berhasil", f"Siswa {nama} berhasil di-enroll ke server.")

    def _build_data_ui(self, parent: QWidget, repo: AbsensiRepository):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("📋 Data Siswa Terdaftar di Kiosk")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "NISN", "Nama", "Kelas"])
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

        # Header baris
        header_row = QHBoxLayout()
        judul = QLabel("📅 Pengaturan Jadwal Sekolah")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        header_row.addWidget(judul)
        header_row.addStretch()

        self.btn_refresh_jadwal = QPushButton("🔄 Refresh")
        self.btn_refresh_jadwal.setObjectName("btnPrimary")
        self.btn_refresh_jadwal.clicked.connect(self._load_jadwal_data)
        header_row.addWidget(self.btn_refresh_jadwal)
        layout.addLayout(header_row)

        # Status label
        self.label_jadwal_status = QLabel("")
        self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['teks_sekunder']};")
        layout.addWidget(self.label_jadwal_status)
        self.jadwal_refresh_selesai.connect(self._selesai_refresh_jadwal)
        layout.addSpacing(8)

        # --- Tabel Jadwal Standar ---
        lbl_standar = QLabel("📋 Jadwal Standar (per Hari)")
        lbl_standar.setStyleSheet("font-size: 15px; font-weight: 600; padding-bottom: 4px;")
        layout.addWidget(lbl_standar)

        self.table_jadwal_standar = QTableWidget()
        self.table_jadwal_standar.setColumnCount(5)
        self.table_jadwal_standar.setHorizontalHeaderLabels(
            ["Hari", "Jam Masuk", "Jam Pulang", "Jam Efektif (Durasi)", "Aksi"]
        )
        self.table_jadwal_standar.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_jadwal_standar.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_jadwal_standar.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_jadwal_standar.verticalHeader().setVisible(False)
        self.table_jadwal_standar.setAlternatingRowColors(True)
        self.table_jadwal_standar.setMinimumHeight(230)
        layout.addWidget(self.table_jadwal_standar)

        layout.addSpacing(16)

        # --- Tabel Jadwal Override ---
        lbl_override = QLabel("🔧 Override Jadwal (Perubahan Tanggal Tertentu)")
        lbl_override.setStyleSheet("font-size: 15px; font-weight: 600; padding-bottom: 4px;")
        layout.addWidget(lbl_override)

        self.table_jadwal_override = QTableWidget()
        self.table_jadwal_override.setColumnCount(5)
        self.table_jadwal_override.setHorizontalHeaderLabels(["Tanggal", "Kelas", "Jam Masuk", "Jam Pulang", "Alasan"])
        self.table_jadwal_override.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_jadwal_override.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_jadwal_override.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_jadwal_override.verticalHeader().setVisible(False)
        self.table_jadwal_override.setAlternatingRowColors(True)
        self.table_jadwal_override.setMinimumHeight(230)
        layout.addWidget(self.table_jadwal_override)

        layout.addSpacing(16)

        # --- Override Lokal (offline-first, Opsi C) ---
        lbl_lokal = QLabel("🔄 Override Jadwal Lokal (Dibuat di Device — Berlaku Offline)")
        lbl_lokal.setStyleSheet("font-size: 15px; font-weight: 600; padding-bottom: 4px;")
        layout.addWidget(lbl_lokal)

        self.table_jadwal_lokal = QTableWidget()
        self.table_jadwal_lokal.setColumnCount(6)
        self.table_jadwal_lokal.setHorizontalHeaderLabels(
            ["Tanggal", "Kelas", "Jam Masuk", "Jam Pulang", "Status", "Aksi"]
        )
        self.table_jadwal_lokal.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_jadwal_lokal.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_jadwal_lokal.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_jadwal_lokal.verticalHeader().setVisible(False)
        self.table_jadwal_lokal.setAlternatingRowColors(True)
        self.table_jadwal_lokal.setMinimumHeight(150)
        layout.addWidget(self.table_jadwal_lokal)

        btn_tambah_lokal = QPushButton("➕ Tambah Override Lokal (Offline)")
        btn_tambah_lokal.clicked.connect(self._tambah_override_lokal_dialog)
        layout.addWidget(btn_tambah_lokal)

        btn_reset_push = QPushButton("🔁 Reset Status Push (Coba Ulang yang Ditolak)")
        btn_reset_push.setToolTip(
            "Reset override yang statusnya '✗ server menolak' menjadi '⏳ menunggu sync' "
            "supaya dicoba push ulang di siklus sync berikutnya. "
            "Pakai setelah server di-patch endpoint POST /jadwal/override untuk device."
        )
        btn_reset_push.clicked.connect(self._reset_status_push)
        layout.addWidget(btn_reset_push)

        layout.addStretch()

        # Link ke web dashboard
        btn_web = QPushButton("🌐 Buka Dashboard Web untuk Pengaturan Lengkap")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{self.dashboard_url}/dashboard/jadwal"))
        layout.addWidget(btn_web)

    def _load_jadwal_data(self):
        """Tampilkan jadwal server; cache hanya dipakai sebagai fallback offline."""
        import logging
        _log = logging.getLogger(__name__)

        self.btn_refresh_jadwal.setEnabled(False)
        self.btn_refresh_jadwal.setText("⏳ Memuat...")
        self.label_jadwal_status.setText("⏳ Mengambil jadwal standar dan override dari server...")
        self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['warning_teks']};")

        # Langsung baca cache lokal (cepat, di main thread)
        standar = []
        override = []
        try:
            rows = self.repo.conn.execute(
                "SELECT kelas, tanggal, hari, jam_masuk, jam_pulang, sumber "
                "FROM jadwal_cache ORDER BY sumber, kelas"
            ).fetchall()
            for r in rows:
                entry = {"kelas": r["kelas"] or "Semua", "jam_masuk": r["jam_masuk"], "jam_pulang": r["jam_pulang"]}
                if r["sumber"] == "standar":
                    entry["hari"] = r["hari"] or ""
                    standar.append(entry)
                else:
                    entry["tanggal"] = r["tanggal"] or ""
                    override.append(entry)
        except Exception as e:
            _log.warning("Gagal baca jadwal_cache: %s", e)

        self._isi_tabel_jadwal([], [])
        self._jadwal_cache_standar = standar
        self._jadwal_cache_override = override

        # Background: fetch jadwal dari server (bukan siklus sync penuh)
        import threading

        # Pastikan jwt_token ada, fallback baca dari config lokal
        jwt_token = getattr(self, "jwt_token", "") or load_config_lokal().get("jwt_token", "")

        def _refresh(token):
            err = None
            try:
                if not token:
                    raise Exception("JWT token tidak ditemukan. Silakan login ulang.")
                headers = {"Authorization": f"Bearer {token}"}
                # Panel menampilkan konfigurasi server, bukan jadwal efektif
                # hari ini yang tidak memiliki field hari.
                resp_standar = requests.get(
                    f"{self.server_url}/jadwal/standar",
                    headers=headers, timeout=15,
                )
                resp_standar.raise_for_status()
                resp_override = requests.get(
                    f"{self.server_url}/jadwal/override",
                    headers=headers, timeout=15,
                )
                resp_override.raise_for_status()

                standar_server = self._normalisasi_jadwal_standar(resp_standar.json())
                override_server = self._normalisasi_jadwal_override(resp_override.json())
                _log.info(
                    "Jadwal server dimuat: %d standar, %d override",
                    len(standar_server), len(override_server),
                )
            except Exception as e:
                err = str(e)
                _log.warning("Refresh jadwal server gagal: %s", e)
                standar_server = []
                override_server = []
            self.jadwal_refresh_selesai.emit(standar_server, override_server, err or "")

        threading.Thread(target=_refresh, args=(jwt_token,), daemon=True).start()

    def _selesai_refresh_jadwal(self, standar_server, override_server, err):
        """Terima hasil thread refresh pada event loop main window."""
        if err:
            standar2 = self._jadwal_cache_standar
            override2 = self._jadwal_cache_override
        else:
            standar2 = standar_server or []
            override2 = override_server or []
        self._isi_tabel_jadwal(standar2, override2)

        total = len(standar2) + len(override2)
        if total == 0:
            msg = "📭 Belum ada jadwal. Pastikan siswa ter-cache dan server aktif."
            self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['warning_teks']};")
        else:
            sumber = "server" if not err else "cache lokal"
            msg = f"✅ {len(standar2)} jadwal standar, {len(override2)} override ({sumber})"
            if err:
                msg += f" ⚠️ {err}"
            warna = WARNA['sukses_teks'] if not err else WARNA['warning_teks']
            self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {warna};")
        self.label_jadwal_status.setText(msg)
        self.btn_refresh_jadwal.setEnabled(True)
        self.btn_refresh_jadwal.setText("🔄 Refresh")

    @staticmethod
    def _normalisasi_jadwal_standar(data):
        """Normalisasi response GET /jadwal/standar untuk tabel per hari."""
        if not isinstance(data, list):
            return []
        urutan_hari = {"SENIN": 0, "SELASA": 1, "RABU": 2, "KAMIS": 3, "JUMAT": 4, "SABTU": 5, "MINGGU": 6}
        hasil = []
        for item in data:
            if not isinstance(item, dict):
                continue
            hasil.append({
                "hari": str(item.get("hari") or "-"),
                "jam_masuk": str(item.get("jam_masuk") or "-"),
                "jam_pulang": str(item.get("jam_pulang") or "-"),
            })
        return sorted(hasil, key=lambda item: urutan_hari.get(item["hari"].upper(), 99))

    @staticmethod
    def _durasi_jadwal(jam_masuk: str, jam_pulang: str) -> str:
        """Hitung durasi kerja dari jam server, tanpa mengubah nilai aslinya."""
        try:
            masuk = datetime.strptime(jam_masuk[:8], "%H:%M:%S")
            pulang = datetime.strptime(jam_pulang[:8], "%H:%M:%S")
            menit = int((pulang - masuk).total_seconds() // 60)
            if menit < 0:
                menit += 24 * 60
            return f"{menit // 60} jam {menit % 60} menit" if menit % 60 else f"{menit // 60} jam"
        except (TypeError, ValueError):
            return "-"

    @staticmethod
    def _normalisasi_jadwal_override(data):
        """Pertahankan field override persis dari kontrak API server."""
        if not isinstance(data, list):
            return []
        return [{
            "tanggal": str(item.get("tanggal") or "-"),
            "kelas": str(item.get("kelas") or "Semua kelas"),
            "jam_masuk": str(item.get("jam_masuk") or "-"),
            "jam_pulang": str(item.get("jam_pulang") or "-"),
            "alasan": str(item.get("alasan") or "-"),
        } for item in data if isinstance(item, dict)]

    def _isi_tabel_jadwal(self, standar: list[dict], override: list[dict]):
        """Isi tabel jadwal standar dan override."""
        self.table_jadwal_standar.setRowCount(len(standar))
        for i, j in enumerate(standar):
            self.table_jadwal_standar.setItem(i, 0, QTableWidgetItem(str(j.get("hari", ""))))
            jam_masuk = str(j.get("jam_masuk", ""))
            jam_pulang = str(j.get("jam_pulang", ""))
            self.table_jadwal_standar.setItem(i, 1, QTableWidgetItem(jam_masuk))
            self.table_jadwal_standar.setItem(i, 2, QTableWidgetItem(jam_pulang))
            self.table_jadwal_standar.setItem(i, 3, QTableWidgetItem(self._durasi_jadwal(jam_masuk, jam_pulang)))
            self.table_jadwal_standar.setItem(i, 4, QTableWidgetItem("Edit di Dashboard Web"))

        self.table_jadwal_override.setRowCount(len(override))
        for i, j in enumerate(override):
            self.table_jadwal_override.setItem(i, 0, QTableWidgetItem(str(j.get("tanggal", ""))))
            self.table_jadwal_override.setItem(i, 1, QTableWidgetItem(str(j.get("kelas", "Semua"))))
            self.table_jadwal_override.setItem(i, 2, QTableWidgetItem(str(j.get("jam_masuk", "") or "—")))
            self.table_jadwal_override.setItem(i, 3, QTableWidgetItem(str(j.get("jam_pulang", "") or "—")))
            self.table_jadwal_override.setItem(i, 4, QTableWidgetItem(str(j.get("alasan", "") or "—")))

        # Muat override lokal dari DB
        self._isi_tabel_override_lokal()

    def _isi_tabel_override_lokal(self):
        """Isi tabel override jadwal lokal (offline-first, Opsi C)."""
        try:
            rows = self.repo.jadwal_override_lokal_semua()
        except Exception as e:
            logger.warning("Gagal ambil override lokal: %s", e)
            rows = []
        self.table_jadwal_lokal.setRowCount(len(rows))
        for i, r in enumerate(rows):
            tanggal = str(r.get("tanggal", ""))
            kelas = str(r.get("kelas") or "Semua")
            jam_masuk = str(r.get("jam_masuk", ""))[:5]
            jam_pulang = str(r.get("jam_pulang", ""))[:5]
            terkirim = bool(r.get("terkirim"))
            status_push = str(r.get("status_push") or ("ok" if terkirim else "pending"))
            pesan_push = str(r.get("pesan_push") or "")
            if status_push == "ok":
                status, warna = "✓ di server", WARNA["sukses_teks"]
            elif status_push == "ditolak":
                status, warna = "✗ server menolak", WARNA["bahaya_teks"]
            else:
                status, warna = "⏳ menunggu sync", WARNA["warning_teks"]

            item_tanggal = QTableWidgetItem(tanggal)
            item_kelas = QTableWidgetItem(kelas)
            item_masuk = QTableWidgetItem(jam_masuk)
            item_pulang = QTableWidgetItem(jam_pulang)
            item_status = QTableWidgetItem(status)
            item_status.setForeground(QColor(warna))
            if status_push == "ditolak" and pesan_push:
                item_status.setToolTip(pesan_push)
            for c, item in enumerate([item_tanggal, item_kelas, item_masuk, item_pulang, item_status]):
                self.table_jadwal_lokal.setItem(i, c, item)

            # Kolom aksi: hapus
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            override_id = r.get("id")
            btn_hapus = QPushButton("🗑️")
            btn_hapus.setToolTip("Hapus override lokal ini")
            btn_hapus.clicked.connect(lambda _=False, i=override_id: self._hapus_override_lokal(i))
            lay.addWidget(btn_hapus)
            lay.addStretch()
            self.table_jadwal_lokal.setCellWidget(i, 5, w)

    def _tambah_override_lokal_dialog(self):
        """Dialog tambah override jadwal lokal (berlaku offline)."""
        tanggal, ok1 = self._input_teks("Tanggal (YYYY-MM-DD)", date.today().isoformat())
        if not ok1:
            return
        kelas, ok2 = self._input_teks("Kelas (kosong = semua)", "")
        if not ok2:
            return
        jam_masuk, ok3 = self._input_teks("Jam Masuk (HH:MM)", "07:00")
        if not ok3:
            return
        jam_pulang, ok4 = self._input_teks("Jam Pulang (HH:MM)", "15:00")
        if not ok4:
            return
        alasan, ok5 = self._input_teks("Alasan (opsional)", "")
        if not ok5:
            return
        if not self._validasi_jam(jam_masuk) or not self._validasi_jam(jam_pulang):
            QMessageBox.warning(self, "Input Salah", "Format jam harus HH:MM (contoh 07:00).")
            return
        self.repo.simpan_jadwal_override_lokal(
            tanggal=tanggal, kelas=kelas or None,
            jam_masuk=jam_masuk + ":00", jam_pulang=jam_pulang + ":00",
            alasan=alasan or None,
        )
        self.label_jadwal_status.setText("✅ Override lokal disimpan. Berlaku langsung untuk absensi offline.")
        self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['sukses_teks']};")
        self._isi_tabel_override_lokal()

    def _hapus_override_lokal(self, override_id: str):
        if QMessageBox.question(
            self, "Konfirmasi", "Hapus override lokal ini?", QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self.repo.hapus_jadwal_override_lokal(override_id)
        self.label_jadwal_status.setText("🗑️ Override lokal dihapus.")
        self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['sukses_teks']};")
        self._isi_tabel_override_lokal()

    def _reset_status_push(self):
        """Reset override yang ditolak server menjadi 'pending' supaya
        dicoba push ulang di siklus sync berikutnya."""
        jumlah = self.repo.jadwal_override_lokal_semua()
        jumlah_ditolak = sum(1 for o in jumlah if o["status_push"] == "ditolak")
        if jumlah_ditolak == 0:
            QMessageBox.information(
                self,
                "Reset Status Push",
                "Tidak ada override dengan status '✗ server menolak'.\n"
                "Semua override sudah terkirim atau masih menunggu sync.",
            )
            return
        jawab = QMessageBox.question(
            self,
            "Konfirmasi Reset",
            f"Reset {jumlah_ditolak} override yang ditolak server menjadi 'menunggu sync'?\n\n"
            "Akan dicoba push ulang di siklus sync berikutnya.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if jawab != QMessageBox.Yes:
            return
        n = self.repo.reset_jadwal_override_ditolak()
        self.label_jadwal_status.setText(f"🔁 {n} override direset, menunggu push ulang.")
        self.label_jadwal_status.setStyleSheet(f"font-size: 12px; color: {WARNA['warning_teks']};")
        self._isi_tabel_override_lokal()

    @staticmethod
    def _input_teks(prompt: str, default: str = ""):
        return QInputDialog.getText(None, prompt, f"{prompt}:", text=default)

    @staticmethod
    def _validasi_jam(s: str) -> bool:
        import re
        return bool(re.fullmatch(r"\d{2}:\d{2}", s))

    def _build_guru_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("👩‍🏫 Manajemen Data Guru & Staf")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        layout.addStretch()
        btn_web = QPushButton("🌐 Kelola Guru di Dashboard Web")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{self.dashboard_url}/dashboard/guru"))
        layout.addWidget(btn_web)

    def _build_laporan_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        judul = QLabel("📊 Laporan & Rekap Absensi")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)
        layout.addStretch()
        btn_web = QPushButton("🌐 Lihat Laporan Lengkap di Web")
        btn_web.clicked.connect(lambda: webbrowser.open(f"{self.dashboard_url}/dashboard/laporan"))
        layout.addWidget(btn_web)

    def _build_sync_ui(self, parent: QWidget, server_url: str):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("🔄 Sinkronisasi Server")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        sub = QLabel(
            "Status data lokal vs server. Hijau = sudah tersinkron, "
            "kuning = menunggu, merah = gagal (akan dicoba ulang otomatis)."
        )
        sub.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        layout.addWidget(sub)

        # Kartu ringkasan (4 kolom)
        kartu = QHBoxLayout()
        kartu.setSpacing(12)
        self.sync_kartu = {}
        for kunci, label in [
            ("total_absensi", "Total Absensi"),
            ("sudah_sync", "✓ Tersinkron"),
            ("belum_sync", "⏳ Menunggu"),
            ("gagal_sync", "✗ Gagal / Retry"),
        ]:
            frame = QFrame()
            frame.setStyleSheet(
                f"background-color: {WARNA['surface_2']}; border: 1px solid {WARNA['border']}; "
                "border-radius: 8px; padding: 6px;"
            )
            frame.setMinimumHeight(96)
            frame.setMaximumHeight(104)
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(10, 8, 10, 8)
            fv.setSpacing(2)
            lbl_nilai = QLabel("0")
            lbl_nilai.setObjectName(f"sync_nilai_{kunci}")
            lbl_nilai.setStyleSheet(
                f"font-size: 20px; font-weight: 700; color: {WARNA['teks_utama']};"
            )
            lbl_nilai.setMinimumHeight(30)
            fv.addWidget(lbl_nilai)
            lbl_ket = QLabel(label)
            lbl_ket.setStyleSheet(f"font-size: 11px; color: {WARNA['teks_sekunder']};")
            fv.addWidget(lbl_ket)
            self.sync_kartu[kunci] = (frame, lbl_nilai, lbl_ket)
            kartu.addWidget(frame, 1)
        layout.addLayout(kartu)

        # Progress bar sinkronisasi
        bar_row = QHBoxLayout()
        bar_row.setSpacing(12)
        self.sync_progress = QProgressBar()
        self.sync_progress.setRange(0, 100)
        self.sync_progress.setValue(0)
        self.sync_progress.setFormat("%p% tersinkron")
        self.sync_progress.setTextVisible(True)
        self.sync_progress.setMinimumHeight(28)
        bar_row.addWidget(self.sync_progress, 1)
        self.sync_label_persen = QLabel("0 / 0")
        self.sync_label_persen.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        bar_row.addWidget(self.sync_label_persen)
        layout.addLayout(bar_row)

        # Info data referensi (embedding, jadwal, dispensasi)
        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        self.sync_label_ref = QLabel("")
        self.sync_label_ref.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        info_row.addWidget(self.sync_label_ref, 1)
        self.sync_label_last = QLabel("")
        self.sync_label_last.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        self.sync_label_last.setAlignment(Qt.AlignRight)
        info_row.addWidget(self.sync_label_last)
        layout.addLayout(info_row)

        # Tombol aksi
        aksi = QHBoxLayout()
        aksi.setSpacing(12)
        btn_sync = QPushButton("🚀 Jalankan Sinkronisasi Sekarang")
        btn_sync.setObjectName("btnPrimary")
        btn_sync.clicked.connect(self._jalankan_sync_manual)
        aksi.addWidget(btn_sync)
        btn_refresh = QPushButton("🔄 Muat Ulang Status")
        btn_refresh.clicked.connect(self._muat_status_sync)
        aksi.addWidget(btn_refresh)
        aksi.addStretch()
        layout.addLayout(aksi)

        # Label status proses
        self.sync_label_proses = QLabel("")
        self.sync_label_proses.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        layout.addWidget(self.sync_label_proses)

        # Tabel detail absensi (mana yang sudah / belum sync)
        self.table_sync = QTableWidget(0, 5)
        self.table_sync.setHorizontalHeaderLabels(
            ["Waktu", "Siswa ID", "Tipe", "Status Sync", "Keterangan"]
        )
        self.table_sync.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_sync.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_sync.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_sync.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_sync.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_sync.verticalHeader().setVisible(False)
        layout.addWidget(self.table_sync, 1)

        # Refresh status otomatis tiap 10 detik selama panel terbuka
        self._timer_status_sync = QTimer(self)
        self._timer_status_sync.setInterval(10_000)
        self._timer_status_sync.timeout.connect(self._muat_status_sync)
        self._timer_status_sync.start()

        # Muat status awal
        self._muat_status_sync()

    # ---------- Sinkronisasi: logika tampilan ----------

    def _jalankan_sync_manual(self):
        """Jalankan satu siklus sync di thread background supaya UI tidak
        membeku, lalu muat ulang status."""
        if self.sync_service is None:
            self.sync_label_proses.setText(
                "⚠️ Layanan sync tidak tersedia (aplikasi berjalan tanpa SyncService)."
            )
            return
        from PySide6.QtCore import QThread
        from app.sync.service import SyncService

        self.btn_sync_diproses = True
        self.sync_label_proses.setText("⏳ Sinkronisasi berjalan... mohon tunggu.")
        self.sync_label_proses.setStyleSheet(f"color: {WARNA['warning_teks']};")

        class _SiklusThread(QThread):
            selesai = Signal(object)

            def __init__(self, service: SyncService):
                super().__init__()
                self.service = service

            def run(self):
                ringkasan = self.service.siklus_sync()
                self.selesai.emit(ringkasan)

        self._thread_sync = _SiklusThread(self.sync_service)
        self._thread_sync.selesai.connect(self._selesai_sync_manual)
        self._thread_sync.finished.connect(
            lambda: self.sync_label_proses.setText(
                self.sync_label_proses.text() or "Sinkronisasi selesai."
            )
        )
        self._thread_sync.start()

    def _selesai_sync_manual(self, ringkasan):
        self._muat_status_sync()
        if ringkasan.online:
            teks = (
                f"✅ Sinkronisasi selesai — kirim {ringkasan.dikirim} "
                f"(disimpan {ringkasan.disimpan}, duplikat {ringkasan.duplikat}, "
                f"gagal {ringkasan.gagal}), tarik embedding {ringkasan.embedding_diperbarui}, "
                f"jadwal {ringkasan.jadwal_diperbarui}, dispensasi {ringkasan.dispensasi_diperbarui}."
            )
            self.sync_label_proses.setStyleSheet(f"color: {WARNA['sukses_teks']};")
        else:
            teks = f"⚠️ Server tidak terjangkau. Data tetap aman di perangkat dan akan dikirim otomatis nanti. ({ringkasan.pesan_error or ''})"
            self.sync_label_proses.setStyleSheet(f"color: {WARNA['warning_teks']};")
        self.sync_label_proses.setText(teks)

    def _muat_status_sync(self):
        """Baca statistik dari repository dan tampilkan di dashboard."""
        try:
            st = self.repo.statistik_sync()
        except Exception as e:
            logger.warning("Gagal muat status sync: %s", e)
            self.sync_label_proses.setText(f"❌ Gagal membaca status: {e}")
            self.sync_label_proses.setStyleSheet(f"color: {WARNA['bahaya_teks']};")
            return

        total = st["total_absensi"]
        sudah = st["sudah_sync"]
        belum = st["belum_sync"]
        gagal = st["gagal_sync"]

        # Update kartu
        for kunci, (frame, lbl_nilai, lbl_ket) in self.sync_kartu.items():
            lbl_nilai.setText(str(st.get(kunci, 0)))

        # Warna kartu (padding kecil agar angka tidak terpotong)
        frame_sudah = self.sync_kartu["sudah_sync"][0]
        frame_belum = self.sync_kartu["belum_sync"][0]
        frame_gagal = self.sync_kartu["gagal_sync"][0]
        frame_sudah.setStyleSheet(
            f"background-color: {WARNA['sukses_bg']}; border: 1px solid {WARNA['sukses_border']}; border-radius: 8px; padding: 6px;"
        )
        frame_belum.setStyleSheet(
            f"background-color: {WARNA['warning_bg']}; border: 1px solid {WARNA['warning_border']}; border-radius: 8px; padding: 6px;"
        )
        if gagal > 0:
            frame_gagal.setStyleSheet(
                f"background-color: {WARNA['bahaya_bg']}; border: 1px solid {WARNA['bahaya_border']}; border-radius: 8px; padding: 6px;"
            )
        else:
            frame_gagal.setStyleSheet(
                f"background-color: {WARNA['surface_2']}; border: 1px solid {WARNA['border']}; border-radius: 8px; padding: 6px;"
            )

        # Progress bar
        if total > 0:
            pct = round(sudah / total * 100)
            self.sync_progress.setValue(pct)
            self.sync_label_persen.setText(f"{sudah} / {total} absensi tersinkron")
        else:
            self.sync_progress.setValue(0)
            self.sync_label_persen.setText("Belum ada data absensi")

        # Info referensi
        self.sync_label_ref.setText(
            f"📚 Referensi lokal: {st['embedding_total']} siswa · "
            f"{st['jadwal_total']} jadwal · {st['dispensasi_total']} dispensasi"
        )
        if st.get("last_sync"):
            try:
                from datetime import datetime as _dt
                ts = _dt.fromisoformat(st["last_sync"])
                self.sync_label_last.setText(f"🕒 Sync terakhir: {ts.strftime('%d/%m/%Y %H:%M:%S')}")
            except Exception:
                self.sync_label_last.setText(f"🕒 Sync terakhir: {st['last_sync']}")
        else:
            self.sync_label_last.setText("🕒 Sync terakhir: belum pernah")

        # Tabel detail (20 terbaru)
        self._isi_tabel_sync()

    def _isi_tabel_sync(self):
        """Tampilkan 20 record absensi terbaru dengan warna status."""
        try:
            rows = self.repo.record_sync_terbaru(batas=20)
        except Exception as e:
            logger.warning("Gagal ambil daftar sync: %s", e)
            return
        self.table_sync.setRowCount(0)
        for i, r in enumerate(rows):
            self.table_sync.insertRow(i)
            jam = str(r.get("jam_aktual", "")) or ""
            siswa = str(r.get("siswa_id", ""))
            tipe = str(r.get("type", ""))
            synced = bool(r.get("synced"))
            status = str(r.get("sync_status", "") or "")
            if synced:
                teks_status = "✓ Tersinkron"
                warna = WARNA["sukses_teks"]
            elif status:
                teks_status = "✗ Gagal / retry"
                warna = WARNA["bahaya_teks"]
            else:
                teks_status = "⏳ Menunggu"
                warna = WARNA["warning_teks"]

            item_jam = QTableWidgetItem(jam)
            item_siswa = QTableWidgetItem(siswa)
            item_tipe = QTableWidgetItem(tipe)
            item_status = QTableWidgetItem(teks_status)
            item_status.setForeground(QColor(warna))
            item_ket = QTableWidgetItem(status if status else "—")
            for c, item in enumerate([item_jam, item_siswa, item_tipe, item_status, item_ket]):
                self.table_sync.setItem(i, c, item)

    # ---------- Pengaturan (.env) ----------

    _ENV_SENSITIF = {
        "DEVICE_API_KEY", "FACE_ENCRYPTION_KEY", "DB_ENCRYPTION_KEY",
        "ADMIN_PASSWORD", "JWT_SECRET", "GURU_SERVICE_JWT",
    }

    # Kunci boolean — dirender sebagai toggle (checkbox) alih-alih input teks
    _ENV_BOOL = {
        "ON_SITE_TESTING_SELESAI",
    }

    _TOGGLE_ON = "background-color: #16a34a; border-radius: 9px; padding: 2px;"
    _TOGGLE_OFF = "background-color: #4b5563; border-radius: 9px; padding: 2px;"

    def _env_path(self) -> str:
        """Path file .env yang dibaca aplikasi saat runtime."""
        from app.config import APP_DIR
        return str(APP_DIR / ".env")

    @staticmethod
    def _buat_ikon_mata(terbuka: bool) -> QIcon:
        """Gambar ikon mata (terbuka/tutup) secara programatik — tidak
        bergantung file resource, jadi aman untuk build PyInstaller."""
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#9ca3af"))
        pen.setWidth(2)
        p.setPen(pen)
        # Bentuk mata (elips)
        p.drawEllipse(2, 6, 16, 8)
        if terbuka:
            # Pupil
            p.setBrush(QColor("#9ca3af"))
            p.drawEllipse(8, 8, 4, 4)
        else:
            # Garis coret (mata tertutup)
            p.drawLine(3, 10, 17, 10)
        p.end()
        return QIcon(pm)

    def _baca_env(self) -> list[dict]:
        """Parse file .env menjadi daftar baris terstruktur.

        Setiap entri: {key, value, komentar} — komentar adalah baris
        komentar/blank yang mendahului baris KEY=VALUE, supaya saat
        disimpan ulang komentar & urutan tetap dipertahankan.
        """
        path = self._env_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="cp1252", errors="replace") as f:
                raw = f.read()

        entri = []
        komentar = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                komentar.append(line)
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                entri.append({"key": key, "value": val, "komentar": komentar})
                komentar = []
            else:
                komentar.append(line)
        return entri

    def _build_settings_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        judul = QLabel("⚙️ Pengaturan (.env)")
        judul.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(judul)

        sub = QLabel(
            "Edit semua isian file .env. Perubahan disimpan langsung ke file "
            "dan akan berlaku setelah aplikasi di-restart."
        )
        sub.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.settings_label_path = QLabel(f"📄 {self._env_path()}")
        self.settings_label_path.setStyleSheet(f"font-size: 12px; color: {WARNA['teks_muted']};")
        self.settings_label_path.setWordWrap(True)
        layout.addWidget(self.settings_label_path)

        # Form
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)
        self.settings_widgets: dict[str, QLineEdit | QCheckBox | QComboBox] = {}
        self.settings_entri = self._baca_env()
        # Snapshot nilai awal file .env — dipakai tombol "Reset ke Awal"
        self.settings_awal: dict[str, str] = {
            e["key"]: e["value"] for e in self.settings_entri
        }

        if not self.settings_entri:
            layout.addWidget(QLabel("⚠️ File .env tidak ditemukan atau kosong."))
        else:
            # --- Dropdown kamera (di atas form, supaya menonjol) ---
            if any(e["key"] == "CAMERA_INDEX" for e in self.settings_entri):
                cam_row = QHBoxLayout()
                cam_row.setSpacing(10)
                cam_label = QLabel("📷 Kamera Aktif:")
                cam_label.setStyleSheet("font-size: 14px; font-weight: 600;")
                cam_row.addWidget(cam_label)
                self.combo_camera = QComboBox()
                self.combo_camera.setMinimumWidth(320)
                self._populate_combo_camera()
                cam_row.addWidget(self.combo_camera)
                cam_row.addStretch()
                form.addRow(cam_row)

            for entri in self.settings_entri:
                key = entri["key"]
                val = entri["value"].lower() if entri["value"] else ""

                if key == "CAMERA_INDEX":
                    # Sudah di-handle oleh dropdown di atas — lewati baris ini
                    continue

                if key in self._ENV_BOOL:
                    # --- Toggle boolean (checkbox) ---
                    cb = QCheckBox()
                    cb.setObjectName(f"env_{key}")
                    cb.setChecked(val == "true")
                    cb.setStyleSheet(f"QCheckBox::indicator {{ width: 36px; height: 20px; }}")
                    cb.stateChanged.connect(
                        lambda state, w=cb: w.setStyleSheet(
                            self._TOGGLE_ON if state else self._TOGGLE_OFF
                        )
                    )
                    cb.setStyleSheet(
                        self._TOGGLE_ON if val == "true" else self._TOGGLE_OFF
                    )
                    form.addRow(f"{key}:", cb)
                    self.settings_widgets[key] = cb
                else:
                    # --- Input teks biasa ---
                    inp = QLineEdit(entri["value"])
                    inp.setObjectName(f"env_{key}")
                    if key in self._ENV_SENSITIF:
                        inp.setEchoMode(QLineEdit.Password)
                        inp.setPlaceholderText("•••••••• (tersembunyi)")
                        # Tombol mata: toggle tampil/sembunyi nilai
                        act_toggle = QAction(inp)
                        act_toggle.setCheckable(True)
                        act_toggle.setIcon(self._buat_ikon_mata(False))
                        act_toggle.setToolTip("Tampilkan / sembunyikan nilai")
                        act_toggle.toggled.connect(
                            lambda checked, e=inp, a=act_toggle: (
                                e.setEchoMode(
                                    QLineEdit.Normal if checked else QLineEdit.Password
                                ),
                                a.setIcon(self._buat_ikon_mata(checked)),
                            )
                        )
                        inp.addAction(act_toggle, QLineEdit.TrailingPosition)
                    form.addRow(f"{key}:", inp)
                    self.settings_widgets[key] = inp

        layout.addLayout(form)

        # Tombol aksi
        aksi = QHBoxLayout()
        aksi.setSpacing(12)
        btn_simpan = QPushButton("💾 Simpan Perubahan")
        btn_simpan.setObjectName("btnPrimary")
        btn_simpan.clicked.connect(self._simpan_settings)
        aksi.addWidget(btn_simpan)
        btn_muat = QPushButton("🔄 Muat Ulang")
        btn_muat.clicked.connect(self._muat_ulang_settings)
        aksi.addWidget(btn_muat)
        btn_reset = QPushButton("♻️ Reset ke Awal")
        btn_reset.setObjectName("btnDanger")
        btn_reset.setToolTip("Kembalikan semua nilai ke isian awal file .env")
        btn_reset.clicked.connect(self._reset_settings)
        aksi.addWidget(btn_reset)
        aksi.addStretch()
        layout.addLayout(aksi)

        self.settings_label_status = QLabel("")
        self.settings_label_status.setStyleSheet(f"font-size: 13px; color: {WARNA['teks_sekunder']};")
        self.settings_label_status.setWordWrap(True)
        layout.addWidget(self.settings_label_status)

        layout.addStretch()

    def _populate_combo_camera(self):
        """Isi combo box kamera dengan daftar kamera yang terdeteksi."""
        daftar = daftar_kamera()
        self.combo_camera.clear()
        self.combo_camera.addItem("(Kamera tidak terdeteksi)", -1)
        for cam in daftar:
            self.combo_camera.addItem(
                f"{cam['nama']}  (index {cam['index']})",
                cam['index'],
            )
        # Pilih sesuai CAMERA_INDEX yang sedang aktif
        idx_aktif = int(self.settings_awal.get("CAMERA_INDEX", "0"))
        pos = self.combo_camera.findData(idx_aktif)
        if pos >= 0:
            self.combo_camera.setCurrentIndex(pos)

    def _muat_ulang_settings(self):
        """Muat ulang nilai dari file .env ke form."""
        self.settings_entri = self._baca_env()
        for entri in self.settings_entri:
            w = self.settings_widgets.get(entri["key"])
            if not w: continue
            if isinstance(w, QCheckBox):
                w.setChecked(entri["value"].lower() == "true")
            else:
                w.setText(entri["value"])
        # Muat ulang combo kamera juga
        if hasattr(self, "combo_camera"):
            idx = int(self.settings_awal.get("CAMERA_INDEX", "0"))
            pos = self.combo_camera.findData(idx)
            if pos >= 0:
                self.combo_camera.setCurrentIndex(pos)
        self.settings_label_status.setText("🔄 Nilai dimuat ulang dari file .env.")
        self.settings_label_status.setStyleSheet(f"color: {WARNA['teks_sekunder']};")

    def _reset_settings(self):
        """Kembalikan semua isian form ke nilai awal file .env."""
        if not self.settings_awal:
            self.settings_label_status.setText("⚠️ Tidak ada nilai awal untuk direset.")
            self.settings_label_status.setStyleSheet(f"color: {WARNA['warning_teks']};")
            return
        for key, val in self.settings_awal.items():
            w = self.settings_widgets.get(key)
            if not w: continue
            if isinstance(w, QCheckBox):
                w.setChecked(val.lower() == "true")
            else:
                w.setText(val)
        # Reset combo kamera
        if hasattr(self, "combo_camera"):
            idx = int(self.settings_awal.get("CAMERA_INDEX", "0"))
            pos = self.combo_camera.findData(idx)
            if pos >= 0:
                self.combo_camera.setCurrentIndex(pos)
        self.settings_label_status.setText(
            "♻️ Semua isian dikembalikan ke nilai awal. Klik 'Simpan Perubahan' agar tertulis ke file."
        )
        self.settings_label_status.setStyleSheet(f"color: {WARNA['warning_teks']};")

    def _simpan_settings(self):
        """Tulis ulang file .env dengan nilai dari form, pertahankan
        komentar & urutan baris."""
        path = self._env_path()
        try:
            # Kumpulkan nilai baru dari form
            nilai_baru = {}
            for k, w in self.settings_widgets.items():
                if isinstance(w, QCheckBox):
                    nilai_baru[k] = "true" if w.isChecked() else "false"
                else:
                    nilai_baru[k] = w.text()
            # Sisipkan nilai CAMERA_INDEX dari combo dropdown
            if hasattr(self, "combo_camera"):
                nilai_baru["CAMERA_INDEX"] = str(self.combo_camera.currentData())

            # Bangun ulang isi file
            baris = []
            for entri in self.settings_entri:
                baris.extend(entri["komentar"])
                val = nilai_baru.get(entri["key"], entri["value"])
                baris.append(f"{entri['key']}={val}")
            isi = "\n".join(baris) + "\n"

            with open(path, "w", encoding="utf-8") as f:
                f.write(isi)

            self.settings_label_status.setText(
                f"✅ Perubahan disimpan ke {path}. Restart aplikasi agar berlaku."
            )
            self.settings_label_status.setStyleSheet(f"color: {WARNA['sukses_teks']};")
            logger.info("Pengaturan .env disimpan ke %s", path)
        except Exception as e:
            logger.error("Gagal simpan .env: %s", e)
            self.settings_label_status.setText(f"❌ Gagal menyimpan: {e}")
            self.settings_label_status.setStyleSheet(f"color: {WARNA['bahaya_teks']};")

    def closeEvent(self, event):
        self.logout_admin.emit()
        self.window_closed.emit()
        super().closeEvent(event)
