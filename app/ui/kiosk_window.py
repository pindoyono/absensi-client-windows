"""
Window kiosk utama — implementasi dari mockup yang sudah disetujui
sebelumnya (foto besar, nama+kelas, kartu status warna, badge jaringan).
Alur: timer kamera -> FaceEngine -> matcher -> business logic -> tampilkan
hasil beberapa detik -> kembali ke idle.
"""
from __future__ import annotations

from datetime import datetime, time as dtime

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QPushButton,
)

from app.business.attendance_logic import proses_absen, HasilAbsen
from app.database.repository import AbsensiRepository
from app.device.setup import load_config_lokal, save_config_lokal
from app.face.engine_base import FaceEngine
from app.face.matcher import cari_siswa_cocok
from app.ui.styles import WARNA, STYLESHEET_DASAR

DURASI_TAMPIL_HASIL_MS = 3500
INTERVAL_KAMERA_MS = 200


class KioskWindow(QWidget):
    def __init__(
        self, repo: AbsensiRepository, engine: FaceEngine,
        device_id: str, face_encryption_key: str,
        jam_masuk_standar: dtime, jam_pulang_standar: dtime,
        gunakan_kamera: bool = True, parent=None,
    ):
        super().__init__(parent)
        self.repo = repo
        self.engine = engine
        self.device_id = device_id
        self.face_encryption_key = face_encryption_key
        self.jam_masuk_standar = jam_masuk_standar
        self.jam_pulang_standar = jam_pulang_standar

        self._status_online = True
        self._menampilkan_hasil = False
        self._cap: cv2.VideoCapture | None = None

        # State login admin
        self._admin_logged_in = False
        self._admin_nama = ""
        self._admin_role = ""
        self._admin_window: "QMainWindow | None" = None

        self.setWindowTitle("Absensi SMK — Kiosk")
        self.setStyleSheet(STYLESHEET_DASAR)
        self._bangun_ui()

        self._timer_reset = QTimer(self)
        self._timer_reset.setSingleShot(True)
        self._timer_reset.timeout.connect(self._kembali_ke_idle)

        if gunakan_kamera:
            # Windows: pakai DSHOW backend untuk hindari error MSMF
            self._cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                # Fallback ke default backend
                self._cap = cv2.VideoCapture(0)
            if not self._cap.isOpened():
                self._cap = None
                self.label_hasil.setText("❌ Kamera tidak tersedia")
                self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['bahaya_teks']};")
            else:
                self._timer_kamera = QTimer(self)
                self._timer_kamera.timeout.connect(self._tick_kamera)
                self._timer_kamera.start(INTERVAL_KAMERA_MS)

        self._timer_jam = QTimer(self)
        self._timer_jam.timeout.connect(self._update_jam)
        self._timer_jam.start(1000)
        self._update_jam()

        # Update login state saat inisialisasi
        self._update_login_state()

    # ---------- UI ----------

    def _bangun_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: status jaringan + jam di kiri, tombol login di kanan
        header = QHBoxLayout()
        header.setContentsMargins(24, 16, 24, 0)
        header.setSpacing(16)

        self.label_status_jaringan = QLabel("● Online · tersinkron")
        self.label_status_jaringan.setStyleSheet(f"color: {WARNA['sukses_teks']}; font-size: 13px;")

        self.label_jam = QLabel("--:--")
        self.label_jam.setObjectName("jamTampilan")
        self.label_jam.setStyleSheet(f"color: {WARNA['teks_utama']}; font-size: 13px; font-weight: 600;")

        header.addWidget(self.label_status_jaringan)
        header.addStretch()
        header.addWidget(self.label_jam)

        # Container untuk login/logout tombol + username label
        self.header_right = QHBoxLayout()
        self.header_right.setSpacing(8)

        self.lbl_user = QLabel("")
        self.lbl_user.setStyleSheet(f"color: {WARNA['teks_sekunder']}; font-size: 12px;")
        self.lbl_user.setVisible(False)

        self.btn_admin = QPushButton("🔐 Login Admin")
        self.btn_admin.setCursor(Qt.PointingHandCursor)
        self.btn_admin.setMinimumHeight(32)
        self.btn_admin.setStyleSheet(
            f"QPushButton {{ background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; "
            f"border: 1px solid {WARNA['border']}; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {WARNA['border']}; }}"
        )
        self.btn_admin.clicked.connect(self._on_btn_admin_clicked)

        self.header_right.addWidget(self.lbl_user)
        self.header_right.addWidget(self.btn_admin)

        header.addLayout(self.header_right)
        layout.addLayout(header)

        # Kartu utama di tengah
        kartu = QFrame(objectName="kartu")
        kartu.setStyleSheet(
            f"#kartu {{ background-color: {WARNA['surface']}; border-radius: 12px; "
            f"border: 1px solid {WARNA['border']}; }}"
        )
        kartu.setMinimumWidth(550)
        kartu_layout = QVBoxLayout(kartu)
        kartu_layout.setContentsMargins(0, 0, 0, 0)
        kartu_layout.setSpacing(0)

        # -- Body: foto + status --
        body = QVBoxLayout()
        body.setContentsMargins(20, 20, 20, 16)
        body.setAlignment(Qt.AlignHCenter)

        self.label_foto = QLabel()
        self.label_foto.setFixedSize(420, 420)
        self.label_foto.setAlignment(Qt.AlignCenter)
        self.label_foto.setStyleSheet(
            f"background-color: {WARNA['surface_2']}; border-radius: 12px; "
            f"border: 2px solid {WARNA['border']};"
        )
        self.label_foto.setText("👤")
        self.label_foto.setStyleSheet(self.label_foto.styleSheet() + "font-size: 96px;")
        body.addWidget(self.label_foto, alignment=Qt.AlignHCenter)
        body.addSpacing(16)

        self.label_hasil = QLabel("Arahkan wajah ke kamera")
        self.label_hasil.setAlignment(Qt.AlignHCenter)
        self.label_hasil.setStyleSheet(f"font-size: 18px; color: {WARNA['teks_sekunder']};")
        body.addWidget(self.label_hasil)

        self.label_nama = QLabel("")
        self.label_nama.setObjectName("namaSiswa")
        self.label_nama.setAlignment(Qt.AlignHCenter)
        self.label_nama.setStyleSheet("font-size: 28px; font-weight: 600;")
        body.addWidget(self.label_nama)

        self.label_kelas = QLabel("")
        self.label_kelas.setObjectName("kelasSiswa")
        self.label_kelas.setAlignment(Qt.AlignHCenter)
        self.label_kelas.setStyleSheet("font-size: 16px;")
        body.addWidget(self.label_kelas)

        body.addSpacing(12)

        self.kartu_status = QFrame()
        self.kartu_status.setMinimumWidth(420)
        status_layout = QHBoxLayout(self.kartu_status)
        status_layout.setAlignment(Qt.AlignCenter)
        self.label_status_detail = QLabel("")
        self.label_status_detail.setAlignment(Qt.AlignCenter)
        self.label_status_detail.setStyleSheet("font-size: 14px;")
        status_layout.addWidget(self.label_status_detail)
        self.kartu_status.setVisible(False)
        body.addWidget(self.kartu_status, alignment=Qt.AlignHCenter)

        kartu_layout.addLayout(body)

        footer = QLabel("Arahkan wajah ke kamera untuk siswa berikutnya")
        footer.setAlignment(Qt.AlignHCenter)
        footer.setStyleSheet(f"color: {WARNA['teks_muted']}; font-size: 14px; padding: 10px;")
        kartu_layout.addWidget(footer)

        outer = QHBoxLayout()
        outer.addStretch()
        outer.addWidget(kartu)
        outer.addStretch()
        layout.addStretch()
        layout.addLayout(outer)
        layout.addStretch()

    def _update_jam(self) -> None:
        self.label_jam.setText(datetime.now().strftime("%H:%M"))

    def set_status_online(self, online: bool) -> None:
        self._status_online = online
        if online:
            self.label_status_jaringan.setText("● Online · tersinkron")
            self.label_status_jaringan.setStyleSheet(f"color: {WARNA['sukses_teks']}; font-size: 13px;")
        else:
            self.label_status_jaringan.setText("● Offline · disimpan lokal")
            self.label_status_jaringan.setStyleSheet(f"color: {WARNA['teks_muted']}; font-size: 13px;")

    # ---------- Alur kamera ----------

    def _tick_kamera(self) -> None:
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok:
            return

        # Update pratinjau kamera live ke UI jika sedang tidak menampilkan hasil absensi
        if not self._menampilkan_hasil:
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            # Format BGR ke RGB untuk Qt
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            # Crop center/scaled ke ukuran 420x420
            pixmap = QPixmap.fromImage(q_img).scaled(420, 420, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.label_foto.setPixmap(pixmap)

            self._proses_frame(frame)

    def _proses_frame(self, frame_bgr: np.ndarray) -> None:
        hasil_deteksi = self.engine.proses_frame(frame_bgr)
        if not hasil_deteksi.wajah_terdeteksi:
            return

        if not hasil_deteksi.lolos_liveness:
            alasan = (hasil_deteksi.alasan_gagal or "").lower()
            if "spoof" in alasan:
                self._tampilkan_hasil_spoofing(hasil_deteksi.alasan_gagal or "Terdeteksi spoofing")
            return

        match = cari_siswa_cocok(hasil_deteksi.embedding, self.repo, self.engine, self.face_encryption_key)
        if not match.ditemukan:
            self._tampilkan_hasil_wajah_tidak_dikenali()
            return

        jadwal = self.repo.jadwal_untuk_kelas(match.kelas)
        jam_masuk = self._parse_jam(jadwal["jam_masuk"]) if jadwal else self.jam_masuk_standar
        jam_pulang = self._parse_jam(jadwal["jam_pulang"]) if jadwal else self.jam_pulang_standar

        keputusan = proses_absen(
            self.repo, match.siswa_id, self.device_id, jam_masuk, jam_pulang,
        )
        self._tampilkan_keputusan(match.nama, match.kelas, keputusan)

    @staticmethod
    def _parse_jam(teks: str) -> dtime:
        jam, menit = teks.split(":")[:2]
        return dtime(hour=int(jam), minute=int(menit))

    # ---------- Tampilan hasil ----------

    def _tampilkan_keputusan(self, nama: str, kelas: str, keputusan) -> None:
        self._menampilkan_hasil = True
        self.label_nama.setText(nama)
        self.label_kelas.setText(kelas)

        if keputusan.hasil == HasilAbsen.DITOLAK_SUDAH_ABSEN:
            self._set_kartu_status(keputusan.pesan, WARNA["bahaya_teks"], WARNA["bahaya_bg"])
            self.label_hasil.setText("Sudah absen")
            self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['bahaya_teks']};")
        elif keputusan.hasil in (HasilAbsen.DITOLAK_BELUM_WAKTUNYA_MASUK, HasilAbsen.DITOLAK_BELUM_WAKTUNYA_PULANG):
            self._set_kartu_status(keputusan.pesan, WARNA["warning_teks"], WARNA["warning_bg"])
            self.label_hasil.setText("Belum waktunya")
            self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['warning_teks']};")
        else:
            aksi = "masuk" if keputusan.hasil == HasilAbsen.BERHASIL_MASUK else "pulang"
            status = keputusan.rekaman.status_kehadiran_otomatis
            warna_teks = WARNA["sukses_teks"] if status == "NORMAL" else WARNA["warning_teks"]
            warna_bg = WARNA["sukses_bg"] if status == "NORMAL" else WARNA["warning_bg"]
            self.label_hasil.setText(f"Absen {aksi} berhasil")
            self.label_hasil.setStyleSheet(f"font-size: 15px; color: {warna_teks};")
            self._set_kartu_status(keputusan.pesan, warna_teks, warna_bg)

        self._timer_reset.start(DURASI_TAMPIL_HASIL_MS)

    def _tampilkan_hasil_wajah_tidak_dikenali(self) -> None:
        self._menampilkan_hasil = True
        self.label_nama.setText("")
        self.label_kelas.setText("")
        self.label_hasil.setText("Wajah tidak dikenali")
        self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['teks_muted']};")
        self._set_kartu_status("Pastikan sudah terdaftar / coba lagi", WARNA["teks_muted"], WARNA["netral_bg"])
        self._timer_reset.start(DURASI_TAMPIL_HASIL_MS)

    def _tampilkan_hasil_spoofing(self, detail: str) -> None:
        self._menampilkan_hasil = True
        self.label_nama.setText("")
        self.label_kelas.setText("")
        self.label_hasil.setText("Akses ditolak")
        self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['bahaya_teks']};")
        self._set_kartu_status(
            "Wajah terdeteksi sebagai foto/video. Silakan gunakan wajah asli di depan kamera",
            WARNA["bahaya_teks"], WARNA["bahaya_bg"],
        )
        self._timer_reset.start(DURASI_TAMPIL_HASIL_MS)

    def _set_kartu_status(self, teks: str, warna_teks: str, warna_bg: str) -> None:
        self.kartu_status.setStyleSheet(f"background-color: {warna_bg}; border-radius: 8px; padding: 8px;")
        self.label_status_detail.setText(teks)
        self.label_status_detail.setStyleSheet(f"color: {warna_teks}; font-size: 13px;")
        self.kartu_status.setVisible(True)

    def _kembali_ke_idle(self) -> None:
        self._menampilkan_hasil = False
        self.label_nama.setText("")
        self.label_kelas.setText("")
        self.label_hasil.setText("Arahkan wajah ke kamera")
        self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['teks_sekunder']};")
        self.kartu_status.setVisible(False)

    def _buka_admin(self, event=None):
        """Buka jendela Admin/Guru Piket untuk login, enrollment, jadwal, dll."""
        from app.ui.admin_window import AdminWindow

        # Tutup jika masih terbuka
        if self._admin_window:
            self._admin_window.close()

        # Pause kamera kiosk — admin window butuh akses kamera juga
        self._pause_kamera()

        self._admin_window = AdminWindow(
            engine=self.engine,
            repo=self.repo,
            server_url="https://absen.smkn2malinau.sch.id",
            face_encryption_key=self.face_encryption_key,
            device_id=self.device_id,
        )
        self._admin_window.logout_admin.connect(self._on_admin_logout)
        self._admin_window.login_sukses_signal.connect(self._update_login_state)
        # Resume kamera saat admin window ditutup
        self._admin_window.window_closed.connect(self._resume_kamera)
        self._admin_window.show()
        self._admin_window.activateWindow()

    def _pause_kamera(self) -> None:
        """Hentikan timer & release kamera agar admin window bisa pakai."""
        if hasattr(self, "_timer_kamera") and self._timer_kamera:
            self._timer_kamera.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _resume_kamera(self) -> None:
        """Aktifkan kembali kamera setelah admin window ditutup."""
        if self._cap is not None:
            return  # Sudah aktif
        self._cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            self._cap = None
            self.label_hasil.setText("❌ Kamera tidak tersedia")
            self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['bahaya_teks']};")
        else:
            if not hasattr(self, "_timer_kamera") or self._timer_kamera is None:
                self._timer_kamera = QTimer(self)
                self._timer_kamera.timeout.connect(self._tick_kamera)
            self._timer_kamera.start(INTERVAL_KAMERA_MS)

    def _on_admin_logout(self):
        """Handle logout dari admin window."""
        self._admin_logged_in = False
        self._admin_role = ""
        self._admin_nama = ""
        self.btn_admin.setText("🔐 Login Admin")
        self.lbl_user.setText("")
        self.lbl_user.setVisible(False)
        self._update_login_state()

    def _on_btn_admin_clicked(self):
        # Jika sudah login, tombol ini berfungsi sebagai Logout
        if self._admin_logged_in:
            from app.ui.admin_window import AdminWindow
            # Kita bisa panggil _proses_logout dari AdminWindow secara dummy atau langsung hapus config
            config = load_config_lokal()
            config.pop("role", None)
            config.pop("admin_nama", None)
            config.pop("jwt_token", None) # Hapus token juga agar benar-benar logout
            save_config_lokal(config)
            self._on_admin_logout()
            return

        # Jika belum login, buka admin window untuk login
        self._buka_admin()

    def _update_login_state(self):
        """Update tombol login/logout + username label berdasarkan config."""
        config = load_config_lokal()
        jwt_token = config.get("jwt_token", "")
        sudah_login = bool(jwt_token) and self._cek_jwt_valid(jwt_token)

        if sudah_login:
            nama = config.get("admin_nama", "User")
            role = config.get("role", "")
            self._admin_logged_in = True
            self._admin_nama = nama
            self._admin_role = role
            self.lbl_user.setText(f"👤 {nama} ({role})")
            self.lbl_user.setVisible(True)
            self.btn_admin.setText("🚪 Logout")
        else:
            self._admin_logged_in = False
            self.lbl_user.setText("")
            self.lbl_user.setVisible(False)
            self.btn_admin.setText("🔐 Login Admin")

    @staticmethod
    def _cek_jwt_valid(jwt_token: str) -> bool:
        """Cek apakah JWT masih valid (belum expired)."""
        if not jwt_token:
            return False
        try:
            import jwt, time
            payload = jwt.decode(jwt_token, options={"verify_signature": False})
            return payload.get("exp", 0) > time.time()
        except Exception:
            return False

    def closeEvent(self, event) -> None:  # noqa: N802 — override Qt
        if self._cap is not None:
            self._cap.release()
        super().closeEvent(event)
