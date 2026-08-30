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
    QLineEdit, QInputDialog, QMessageBox,
)

from app.business.attendance_logic import proses_absen, HasilAbsen
from app.config import settings
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
        gunakan_kamera: bool = True, parent=None, audit_logger=None,
        sync_service=None, mode_testing: bool = False,
    ):
        super().__init__(parent)
        self.repo = repo
        self.engine = engine
        self.audit_logger = audit_logger
        self.device_id = device_id
        self.face_encryption_key = face_encryption_key
        self.jam_masuk_standar = jam_masuk_standar
        self.jam_pulang_standar = jam_pulang_standar
        self.sync_service = sync_service
        self.mode_testing = mode_testing

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

        # Isi label jadwal header saat startup
        self._update_jadwal_waktu()
        # Evaluasi badge kesegaran data saat startup — kalau cache sudah
        # basi (mis. device baru nyala setelah lama offline), badge langsung
        # tampil tanpa menunggu siklus sync pertama selesai.
        self._update_badge_kesegaran()

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

        self.label_status_sync = QLabel("")
        self.label_status_sync.setStyleSheet(f"color: {WARNA['teks_sekunder']}; font-size: 12px;")

        # Badge jadwal lokal (offline override) — muncul kalau ada override
        # jadwal yang dibuat di device dan berlaku hari ini (Opsi C).
        self.label_jadwal_lokal = QLabel("🔄 Jadwal Lokal")
        self.label_jadwal_lokal.setStyleSheet(
            f"background-color: {WARNA['warning_bg']}; color: {WARNA['warning_teks']}; "
            f"border: 1px solid {WARNA['warning_border']}; border-radius: 6px; "
            "padding: 2px 8px; font-size: 12px; font-weight: 600;"
        )
        self.label_jadwal_lokal.setVisible(False)
        self.label_jadwal_lokal.setToolTip(
            "Absensi hari ini memakai jadwal override yang dibuat di device ini "
            "(offline). Akan dikirim ke server saat online."
        )

        self.label_jam = QLabel("--:--")
        self.label_jam.setObjectName("jamTampilan")
        self.label_jam.setStyleSheet(f"color: {WARNA['teks_utama']}; font-size: 13px; font-weight: 600;")

        # Badge kesegaran data (PRD observabilitas degradasi) — tampil HANYA
        # kalau jadwal/dispensasi/embedding cache lokal sudah basi melewati
        # ambang batas. Tidak menambah noise saat semua normal.
        self.label_kesegaran = QLabel("")
        self.label_kesegaran.setStyleSheet(
            f"background-color: {WARNA['warning_bg']}; color: {WARNA['warning_teks']}; "
            f"border: 1px solid {WARNA['warning_border']}; border-radius: 6px; "
            "padding: 2px 8px; font-size: 12px; font-weight: 600;"
        )
        self.label_kesegaran.setVisible(False)
        self.label_kesegaran.setToolTip(
            "Data cache lokal (jadwal/dispensasi/embedding) sudah lama tidak "
            "diperbarui dari server. Hubungi admin untuk cek koneksi device."
        )

        header.addWidget(self.label_status_jaringan)
        header.addWidget(self.label_status_sync)
        header.addWidget(self.label_jadwal_lokal)
        header.addWidget(self.label_kesegaran)
        header.addStretch()
        header.addWidget(self.label_jam)

        # Label jadwal hari ini — SELALU tampil di header supaya siswa tahu
        # kapan harus absen masuk & pulang. Ukuran besar & kontras.
        self.label_jadwal_header = QLabel("Masuk: --:--  Pulang: --:--")
        self.label_jadwal_header.setStyleSheet(
            f"background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; "
            f"border: 1px solid {WARNA['border']}; border-radius: 6px; "
            "padding: 4px 12px; font-size: 15px; font-weight: 700;"
        )
        header.addWidget(self.label_jadwal_header)

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

        # Tombol admin: buka panel admin, verifikasi password dari .env
        self.btn_admin_panel = QPushButton("⚙️ Panel Admin")
        self.btn_admin_panel.setCursor(Qt.PointingHandCursor)
        self.btn_admin_panel.setMinimumHeight(32)
        self.btn_admin_panel.setStyleSheet(
            f"QPushButton {{ background-color: {WARNA['surface_2']}; color: {WARNA['teks_utama']}; "
            f"border: 1px solid {WARNA['border']}; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {WARNA['border']}; }}"
        )
        self.btn_admin_panel.clicked.connect(self._on_btn_admin_panel_clicked)

        self.header_right.addWidget(self.lbl_user)
        self.header_right.addWidget(self.btn_admin)
        self.header_right.addWidget(self.btn_admin_panel)

        header.addLayout(self.header_right)
        layout.addLayout(header)

        # Banner MODE TESTING — tampil saat on-site testing belum selesai.
        # Mengingatkan operator bahwa device belum boleh dipakai reguler.
        if self.mode_testing:
            self.label_mode_testing = QLabel(
                "🧪 MODE TESTING — hasil absen TIDAK disimpan. "
                "Selesaikan on-site testing lalu set ON_SITE_TESTING_SELESAI=true di .env"
            )
            self.label_mode_testing.setAlignment(Qt.AlignCenter)
            self.label_mode_testing.setStyleSheet(
                f"background-color: {WARNA['warning_bg']}; color: {WARNA['warning_teks']}; "
                f"border: 1px solid {WARNA['warning_border']}; "
                "padding: 6px 12px; font-size: 13px; font-weight: 700;"
            )
            layout.addWidget(self.label_mode_testing)

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

    def set_sync_status(self, ringkasan) -> None:
        """Perbarui label status sync dengan waktu terakhir dan jumlah data."""
        try:
            # Waktu terakhir sync dari metadata
            terakhir = self.repo.get_metadata("sync_terakhir")
            if not terakhir:
                terakhir = "belum pernah"
            else:
                try:
                    from datetime import datetime as _dt
                    terakhir = _dt.fromisoformat(terakhir).strftime("%d/%m %H:%M")
                except Exception:
                    pass

            # Jumlah data yang disinkronkan
            if ringkasan is not None:
                detail = f" · {ringkasan.dikirim} kirim, {ringkasan.embedding_diperbarui} wajah, {ringkasan.jadwal_diperbarui} jadwal"
            else:
                detail = ""

            self.label_status_sync.setText(f"Sync: {terakhir}{detail}")
            self.label_status_sync.setStyleSheet(f"color: {WARNA['teks_sekunder']}; font-size: 12px;")
        except Exception:
            pass
        # Refresh jadwal header setiap siklus sync — jadwal cache bisa baru
        # terisi/berubah setelah tarik jadwal dari server.
        self._update_jadwal_waktu()
        self._update_badge_kesegaran(ringkasan)

    def _update_badge_kesegaran(self, ringkasan=None) -> None:
        """Tampilkan badge status data cache lokal. Selalu tampil:
        - Hijau → data segar (jadwal, dispensasi, embedding masih valid)
        - Kuning → ada data yang basi, perlu hubungi admin
        - Kosong/skip kalau cache masih kosong total (belum pernah sync)."""
        try:
            from app.config import settings
            status = self.repo.status_kesegaran_data()

            # Kalau belum ada data sama sekali (belum pernah sync), sembunyikan
            if (status["jadwal_jam_lalu"] is None
                    and status["dispensasi_jam_lalu"] is None
                    and status["embedding_hari_lalu"] is None):
                self.label_kesegaran.setVisible(False)
                return

            masalah = []
            if status["jadwal_jam_lalu"] is None or status["jadwal_jam_lalu"] > settings.batas_stale_jadwal_jam:
                masalah.append("Jadwal")
            if status["dispensasi_jam_lalu"] is None or status["dispensasi_jam_lalu"] > settings.batas_stale_dispensasi_jam:
                masalah.append("Dispensasi")
            if status["embedding_hari_lalu"] is None or status["embedding_hari_lalu"] > settings.batas_stale_embedding_hari:
                masalah.append("Embedding")

            if masalah:
                self.label_kesegaran.setText(f"⚠️ {' & '.join(masalah)} basi")
                self.label_kesegaran.setStyleSheet(
                    f"background-color: {WARNA['warning_bg']}; color: {WARNA['warning_teks']}; "
                    f"border: 1px solid {WARNA['warning_border']}; border-radius: 6px; "
                    "padding: 2px 8px; font-size: 12px; font-weight: 600;"
                )
            else:
                self.label_kesegaran.setText("✓ Data segar")
                self.label_kesegaran.setStyleSheet(
                    f"background-color: {WARNA['sukses_bg']}; color: {WARNA['sukses_teks']}; "
                    f"border: 1px solid {WARNA['sukses_border']}; border-radius: 6px; "
                    "padding: 2px 8px; font-size: 12px; font-weight: 600;"
                )
            self.label_kesegaran.setVisible(True)
        except Exception:
            self.label_kesegaran.setVisible(False)

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
                self.repo.log_liveness(
                    wajah_terdeteksi=True,
                    is_real=False,
                    liveness_score=hasil_deteksi.skor_liveness,
                    ambang_saat_itu=0.0,
                    alasan_gagal=hasil_deteksi.alasan_gagal,
                    device_id=self.device_id,
                )
                self._tampilkan_hasil_spoofing(hasil_deteksi.alasan_gagal or "Terdeteksi spoofing")
            return

        match = cari_siswa_cocok(hasil_deteksi.embedding, self.repo, self.engine, self.face_encryption_key)
        if not match.ditemukan:
            self._tampilkan_hasil_wajah_tidak_dikenali()
            return

        self.repo.log_liveness(
            wajah_terdeteksi=True,
            is_real=True,
            liveness_score=hasil_deteksi.skor_liveness,
            ambang_saat_itu=0.0,
            siswa_id=match.siswa_id,
            device_id=self.device_id,
        )

        jadwal = self.repo.jadwal_untuk_kelas(match.kelas, datetime.now().date().isoformat())
        jam_masuk = self._parse_jam(jadwal["jam_masuk"]) if jadwal else self.jam_masuk_standar
        jam_pulang = self._parse_jam(jadwal["jam_pulang"]) if jadwal else self.jam_pulang_standar

        # Update panel jadwal dengan data kelas yang terdeteksi
        self._update_jadwal_waktu(match.kelas)

        # Badge kiosk: tunjukkan kalau absensi pakai jadwal override lokal
        # (dibuat di device, Opsi C) — bukan jadwal server. Baris override
        # lokal punya kolom 'id' (UUID), baris jadwal_cache server tidak.
        pakai_lokal = bool(jadwal is not None and "id" in jadwal.keys())
        self._set_badge_jadwal_lokal(pakai_lokal)

        # MODE TESTING: wajah dikenali tapi TIDAK disimpan ke DB — hanya
        # simulasi hasil, supaya data testing tidak mencemari absensi resmi.
        if self.mode_testing:
            self._menampilkan_hasil = True
            self.label_nama.setText(match.nama)
            self.label_kelas.setText(match.kelas)
            self.label_hasil.setText("🧪 [TEST] Wajah dikenali")
            self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['warning_teks']};")
            self._set_kartu_status(
                "MODE TESTING — absen tidak disimpan. "
                f"Liveness: {hasil_deteksi.skor_liveness:.3f}",
                WARNA["warning_teks"], WARNA["warning_bg"],
            )
            self._timer_reset.start(DURASI_TAMPIL_HASIL_MS)
            return

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

    def _set_badge_jadwal_lokal(self, aktif: bool) -> None:
        """Tampilkan/sembunyikan badge '🔄 Jadwal Lokal' di header kiosk.
        Aktif saat absensi memakai override jadwal yang dibuat di device
        ini (offline-first, Opsi C). Badge akan hilang saat kembali ke idle
        atau jadwal lokal sudah tidak berlaku."""
        self.label_jadwal_lokal.setVisible(aktif)

    def _kembali_ke_idle(self) -> None:
        self._menampilkan_hasil = False
        self.label_nama.setText("")
        self.label_kelas.setText("")
        self.label_hasil.setText("Arahkan wajah ke kamera")
        self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['teks_sekunder']};")
        self.kartu_status.setVisible(False)
        # Kembalikan panel jadwal ke jadwal umum
        self._update_jadwal_waktu()

    def _update_jadwal_waktu(self, kelas: str | None = None) -> None:
        """Perbarui label jadwal di header. Format: 'Masuk: ..:..  Pulang: ..:..'
        Jika kelas diberikan, cari jadwal spesifik kelas tsb.
        Jika tidak (idle), pakai jadwal umum/standar — dan kalau tidak ada
        jadwal umum, fallback ke jadwal kelas pertama yang tersedia supaya
        label tidak kosong ('--:--') padahal data jadwal ada."""
        try:
            tanggal = datetime.now().date().isoformat()
            jadwal = self.repo.jadwal_untuk_kelas(kelas or "", tanggal)

            # Fallback: saat idle (kelas kosong) tidak ada jadwal umum
            # (kelas NULL), ambil jadwal kelas pertama yang tersedia supaya
            # jam masuk/pulang tetap tampil.
            if not jadwal and not kelas:
                jadwal = self.repo.jadwal_pertama_tersedia(tanggal)

            if jadwal:
                masuk = jadwal["jam_masuk"][:5]  # HH:mm
                pulang = jadwal["jam_pulang"][:5]
                self.label_jadwal_header.setText(f"Masuk: {masuk}  Pulang: {pulang}")
            else:
                # Weekend atau tidak ada jadwal
                self.label_jadwal_header.setText("Masuk: --:--  Pulang: --:--")

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Gagal update label jadwal: %s", e)
            self.label_jadwal_header.setText("Masuk: --:--  Pulang: --:--")

    def _buka_admin(self, bypass_login: bool = False):
        """Buka jendela Admin/Guru Piket untuk login, enrollment, jadwal, dll.

        bypass_login=True hanya untuk jalur ⚙️ Panel Admin (sudah diverifikasi
        password). Tombol 🔐 Login Admin memakai jalur normal: login Google SSO.
        """
        from app.ui.admin_window import AdminWindow

        # Tutup jika masih terbuka
        if self._admin_window:
            self._admin_window.close()

        # Pause kamera kiosk — admin window butuh akses kamera juga
        self._pause_kamera()

        self._admin_window = AdminWindow(
            engine=self.engine,
            repo=self.repo,
            server_url=settings.server_url,
            dashboard_url=settings.dashboard_url,
            face_encryption_key=self.face_encryption_key,
            device_id=self.device_id,
            bypass_login=bypass_login,
            sync_service=self.sync_service,
        )
        self._admin_window.logout_admin.connect(self._on_admin_logout)
        self._admin_window.login_sukses_signal.connect(self._update_login_state)
        # Resume kamera saat admin window ditutup
        self._admin_window.window_closed.connect(self._resume_kamera)
        self._admin_window.window_closed.connect(self._lepas_stays_on_top)
        self._admin_window.show()
        self._admin_window.activateWindow()

    def _lepas_stays_on_top(self):
        """Lepas flag StaysOnTop dari admin window setelah ditutup, supaya
        tidak menimpa window lain (kiosk fullscreen) di masa mendatang."""
        if self._admin_window is not None:
            try:
                self._admin_window.setWindowFlags(
                    self._admin_window.windowFlags() & ~Qt.WindowStaysOnTopHint
                )
            except Exception:
                pass

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

    def _on_btn_admin_panel_clicked(self):
        """Buka panel admin setelah verifikasi password dari konfigurasi (.env)."""
        password, ok = QInputDialog.getText(
            self,
            "Verifikasi Admin",
            "Masukkan password admin:",
            QLineEdit.Password,
        )
        if not ok:
            return
        if not settings.admin_password:
            QMessageBox.critical(
                self, "Konfigurasi Tidak Lengkap",
                "ADMIN_PASSWORD belum diset di .env.\nHubungi admin untuk mengatur password panel.",
            )
            return
        if password != settings.admin_password:
            QMessageBox.warning(self, "Akses Ditolak", "Password salah. Silakan coba lagi.")
            return
        self._buka_admin(bypass_login=True)

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
                # Tanpa secret kita tidak bisa verifikasi signature —
                # fail-closed lebih aman daripada menerima token palsu.
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

    def closeEvent(self, event) -> None:  # noqa: N802 — override Qt
        if self._cap is not None:
            self._cap.release()
        super().closeEvent(event)
