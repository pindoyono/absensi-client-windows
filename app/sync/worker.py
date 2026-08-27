"""
Wrapper QThread — menjalankan SyncService secara berkala di background,
tidak memblokir UI kiosk saat kirim/tarik data.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.sync.service import SyncService, RingkasanSiklus


class SyncWorker(QThread):
    siklus_selesai = Signal(object)  # emit RingkasanSiklus tiap siklus
    sync_status_changed = Signal(str)  # emit sync status string untuk UI badge

    def __init__(self, service: SyncService, interval_detik: int = 45, parent=None):
        super().__init__(parent)
        self.service = service
        self.interval_detik = interval_detik
        self._berjalan = True

    def run(self) -> None:
        while self._berjalan and not self.isInterruptionRequested():
            try:
                ringkasan = self.service.siklus_sync()
                self.siklus_selesai.emit(ringkasan)
                # Emit status string untuk UI badge (REQ-OPS-002)
                if not ringkasan.online:
                    self.sync_status_changed.emit("OFFLINE")
                elif ringkasan.pesan_error:
                    self.sync_status_changed.emit("ERROR")
                elif ringkasan.gagal > 0:
                    self.sync_status_changed.emit("PARTIAL")
                else:
                    self.sync_status_changed.emit("OK")
            except Exception as e:  # noqa: BLE001 — sync worker TIDAK BOLEH mati karena 1 error
                self.siklus_selesai.emit(RingkasanSiklus(online=False, pesan_error=str(e)))
                self.sync_status_changed.emit("ERROR")

            # Tidur bertahap supaya thread bisa berhenti cepat saat app ditutup.
            for _ in range(self.interval_detik):
                if not self._berjalan or self.isInterruptionRequested():
                    break
                self.sleep(1)

    def berhenti(self) -> None:
        self._berjalan = False
        self.requestInterruption()
        self.wait(5000)
