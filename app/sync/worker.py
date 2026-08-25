"""
Wrapper QThread — menjalankan SyncService secara berkala di background,
tidak memblokir UI kiosk saat kirim/tarik data.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.sync.service import SyncService, RingkasanSiklus


class SyncWorker(QThread):
    siklus_selesai = Signal(object)  # emit RingkasanSiklus tiap siklus

    def __init__(self, service: SyncService, interval_detik: int = 45, parent=None):
        super().__init__(parent)
        self.service = service
        self.interval_detik = interval_detik
        self._berjalan = True

    def run(self) -> None:
        while self._berjalan:
            try:
                ringkasan = self.service.siklus_sync()
                self.siklus_selesai.emit(ringkasan)
            except Exception as e:  # noqa: BLE001 — sync worker TIDAK BOLEH mati karena 1 error
                self.siklus_selesai.emit(RingkasanSiklus(online=False, pesan_error=str(e)))

            self.sleep(self.interval_detik)

    def berhenti(self) -> None:
        self._berjalan = False
        self.wait(2000)
