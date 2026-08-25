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
from app.face.opencv_engine import OpenCVPlaceholderEngine
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

    # PENTING: OpenCVPlaceholderEngine BUKAN untuk produksi (lihat
    # app/face/engine_base.py). Ganti dengan adapter MiniFASNet di sini
    # sebelum pilot dengan siswa asli.
    from app.ui.kiosk_window import KioskWindow
    from app.ui.admin_window import AdminWindow
    from app.face.minifasnet_engine import MiniFASNetEngine
    engine = MiniFASNetEngine(
        path_model_liveness="models/minifasnet.onnx",
    )
    logger.info(
        "Memakai %s — siap untuk produksi.",
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
