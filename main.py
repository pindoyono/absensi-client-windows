"""
Entry point aplikasi kiosk. Jalankan: python main.py
(atau .exe hasil build PyInstaller — lihat docs/BUILD_INSTALLER.md)
"""
import logging
import sys
from datetime import time as dtime

from PySide6.QtWidgets import QApplication, QMessageBox

from app.api.client import ApiClient
from app.config import settings
from app.database.db import get_connection
from app.database.repository import AbsensiRepository
from app.sync.service import SyncService
from app.sync.worker import SyncWorker
from app.ui.kiosk_window import KioskWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def main() -> int:
    app = QApplication(sys.argv)

    masalah_config = settings.validasi()
    if masalah_config:
        QMessageBox.critical(
            None, "Konfigurasi Belum Lengkap",
            "Device belum dikonfigurasi dengan benar:\n\n" + "\n".join(f"• {m}" for m in masalah_config)
            + "\n\nHubungi admin untuk mendapatkan file .env yang benar.",
        )
        return 1

    conn = get_connection()
    repo = AbsensiRepository(conn)

    # PENTING: liveness detection sudah aktif (bug hardcode is_real=True
    # sudah diperbaiki), TAPI AMBANG_LIVENESS dan INDEKS_KELAS_LIVE di
    # app/face/minifasnet_engine.py masih nilai awal, BELUM dikalibrasi
    # dengan pengujian foto/video spoofing sungguhan (Skenario 5 & 6 di
    # prompt pengujian webcam). Jangan anggap "siap produksi" sebelum itu.
    from app.face.minifasnet_engine import MiniFASNetEngine
    engine = MiniFASNetEngine(
        path_model_liveness="models/minifasnet.onnx",
    )
    logger.warning(
        "Memakai %s — liveness AKTIF tapi ambang batas BELUM divalidasi "
        "dengan uji spoofing foto/video sungguhan. Jangan pilot dulu.",
        engine.model_version,
    )

    api = ApiClient(
        settings.server_url, settings.device_id, settings.device_api_key,
        service_jwt=settings.guru_service_jwt,
    )

    window = KioskWindow(
        repo=repo, engine=engine, device_id=settings.device_id,
        face_encryption_key=settings.face_encryption_key,
        jam_masuk_standar=dtime(7, 0), jam_pulang_standar=dtime(15, 0),
        gunakan_kamera=True,
    )
    window.resize(500, 640)
    
    # Cek konektivitas sebelum window ditampilkan
    window.set_status_online(api.cek_koneksi())
    
    window.showFullScreen()  # kiosk mode — ganti window.show() saat development

    sync_service = SyncService(repo, api)
    sync_worker = SyncWorker(sync_service, interval_detik=settings.sync_interval_seconds)
    sync_worker.siklus_selesai.connect(
        lambda ringkasan: window.set_status_online(ringkasan.online)
    )
    sync_worker.start()

    exit_code = app.exec()

    sync_worker.berhenti()
    conn.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
