"""
Entry point aplikasi kiosk. Jalankan: python main.py
(atau .exe hasil build PyInstaller — lihat docs/BUILD_INSTALLER.md)

Improvements (Phase 2.1):
- Graceful shutdown dengan signal handlers (REQ-OPS-008)
- Resource cleanup guarantee dengan try-finally (REQ-OPS-003)
- Audit logging integration (REQ-OPS-001)
- Liveness logging (LIVENESS-004)
- Metrics collection (OPS-005)
"""
import logging
import logging.handlers
import signal
import sys
from datetime import time as dtime
from pathlib import Path

# Konfigurasi BLAS/threading WAJIB sebelum NumPy pertama kali di-load,
# supaya cosine distance & matmul berjalan multi-threaded di Windows.
import app.blas_config  # noqa: F401

from PySide6.QtWidgets import QApplication, QMessageBox

from app.api.client import ApiClient
from app.audit import AuditLogger
from app.config import settings
from app.database.db import get_connection
from app.database.repository import AbsensiRepository
from app.metrics import get_metrics
from app.sync.service import SyncService
from app.sync.worker import SyncWorker
from app.ui.kiosk_window import KioskWindow

# ============================================================
# Logging Setup (OPS-006: Centralized Logging)
# ============================================================
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def _setup_logging() -> logging.Logger:
    """Setup logging dengan file rotation dan console output."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler dengan rotation (max 10MB, keep 30 days)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "application.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=30,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


logger = _setup_logging()


def main() -> int:
    """Main application entry point.
    
    Returns:
        Exit code (0 = success, 1 = error)
    """
    app = QApplication(sys.argv)
    
    # Setup signal handlers untuk graceful shutdown (REQ-OPS-008)
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        app.quit()
    
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    
    # Validate configuration
    masalah_config = settings.validasi()
    if masalah_config:
        logger.error(f"Configuration validation failed: {masalah_config}")
        QMessageBox.critical(
            None,
            "Konfigurasi Belum Lengkap",
            "Device belum dikonfigurasi dengan benar:\n\n"
            + "\n".join(f"• {m}" for m in masalah_config)
            + "\n\nHubungi admin untuk mendapatkan file .env yang benar.",
        )
        return 1
    
    conn = None
    sync_worker = None
    
    try:
        # Initialize database
        logger.info("Initializing database connection...")
        conn = get_connection()
        repo = AbsensiRepository(conn)
        
        # Initialize audit logger (OPS-001)
        audit_logger = AuditLogger(repo, settings.device_id)
        audit_logger.log_event(
            event_type="SYSTEM_START",
            action="Application started",
            status="success",
        )
        
        # Initialize metrics (OPS-005)
        metrics = get_metrics()
        logger.info(f"Metrics will be collected to: data/performance_metrics.jsonl")
        
        # Load face engine
        logger.info("Loading MiniFASNet engine...")
        from app.face.minifasnet_engine import MiniFASNetEngine
        engine = MiniFASNetEngine(
            path_model_liveness="models/minifasnet.onnx",
        )
        logger.warning(
            f"Using {engine.model_version} — liveness AKTIF tapi ambang batas "
            "BELUM divalidasi dengan uji spoofing foto/video sungguhan. Jangan pilot dulu."
        )
        
        # Initialize API client
        logger.info("Initializing API client...")
        api = ApiClient(
            settings.server_url,
            settings.device_id,
            settings.device_api_key,
            audit_logger=audit_logger,
        )

        # Setup sync service (dibutuhkan oleh kiosk window & admin panel)
        logger.info("Initializing sync service...")
        sync_service = SyncService(repo, api, audit_logger=audit_logger)

        # Bersihkan embedding lama yang tidak cocok FACE_ENCRYPTION_KEY baru.
        # Kalau kunci di .env diganti, embedding terenkripsi kunci lama tidak
        # bisa didekripsi → matcher buang CPU + penuh error tiap frame. Hapus,
        # lalu reset watermark tarik-ulang supaya sync berikutnya ambil ulang
        # SEMUA embedding dari server (dienkripsi kunci baru).
        if settings.face_encryption_key:
            try:
                n_rusak = repo.hapus_embedding_tidak_sesuai_kunci(settings.face_encryption_key)
                if n_rusak:
                    repo.reset_metadata_tarik_embedding()
                    logger.warning(
                        "FACE_ENCRYPTION_KEY baru: %d embedding lama dihapus, "
                        "akan ditarik ulang dari server di siklus sync berikutnya.", n_rusak
                    )
            except Exception as e:
                logger.warning("Gagal bersihkan embedding tidak sesuai kunci: %s", e)

        # Create kiosk window
        logger.info("Creating kiosk window...")
        window = KioskWindow(
            repo=repo,
            engine=engine,
            device_id=settings.device_id,
            face_encryption_key=settings.face_encryption_key,
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            gunakan_kamera=True,
            audit_logger=audit_logger,
            sync_service=sync_service,
        )
        window.resize(1024, 768)
        
        # Check connectivity before showing window
        logger.info("Checking server connectivity...")
        is_online = api.cek_koneksi()
        window.set_status_online(is_online)
        
        # Show window
        logger.info("Showing kiosk window...")
        window.showFullScreen()  # kiosk mode — ganti window.show() saat development
        
        # Setup sync worker
        logger.info(f"Starting sync worker (interval: {settings.sync_interval_seconds}s)...")
        sync_worker = SyncWorker(
            sync_service,
            interval_detik=settings.sync_interval_seconds,
        )
        sync_worker.siklus_selesai.connect(
            lambda ringkasan: window.set_status_online(ringkasan.online)
        )
        sync_worker.siklus_selesai.connect(
            lambda ringkasan: window.set_sync_status(ringkasan)
        )
        sync_worker.start()
        
        logger.info("Application ready")
        
        # Run application
        exit_code = app.exec()
        
        logger.info(f"Application exiting with code {exit_code}")
        return exit_code
    
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    
    except Exception as e:
        logger.exception(f"Unexpected error during application execution: {e}")
        QMessageBox.critical(
            None,
            "Error",
            f"Unexpected error:\n{str(e)}\n\nLihat log file untuk detail.",
        )
        return 1
    
    finally:
        # Graceful shutdown (REQ-OPS-008)
        logger.info("Performing graceful shutdown...")
        
        if sync_worker:
            try:
                logger.info("Stopping sync worker...")
                sync_worker.berhenti()
            except Exception as e:
                logger.error(f"Error stopping sync worker: {e}", exc_info=True)
        
        if conn:
            try:
                logger.info("Closing database connection...")
                conn.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}", exc_info=True)
        
        logger.info("Shutdown complete")


if __name__ == "__main__":
    sys.exit(main())
