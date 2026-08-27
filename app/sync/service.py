"""
Logika sync dipisah dari QThread (lihat worker.py) supaya bisa diuji
dengan mock ApiClient/Repository tanpa perlu event loop Qt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date as date_cls

import requests

from app.api.client import ApiClient, KoneksiGagal, LayananJadwalBelumSiap
from app.database.repository import AbsensiRepository

logger = logging.getLogger(__name__)


@dataclass
class RingkasanSiklus:
    online: bool
    dikirim: int = 0
    disimpan: int = 0
    duplikat: int = 0
    gagal: int = 0
    embedding_diperbarui: int = 0
    jadwal_diperbarui: int = 0
    dispensasi_diperbarui: int = 0
    pesan_error: str | None = None


class SyncService:
    def __init__(self, repo: AbsensiRepository, api: ApiClient, batas_batch: int = 100, audit_logger=None):
        self.repo = repo
        self.api = api
        self.batas_batch = batas_batch
        self.audit_logger = audit_logger

    def siklus_sync(self) -> RingkasanSiklus:
        """Satu siklus sync lengkap: cek koneksi -> push absensi belum
        sync -> tarik update embedding. Dipanggil berkala oleh worker
        (lihat app/sync/worker.py) — AMAN dipanggil berkali-kali,
        termasuk saat offline (langsung return online=False tanpa error)."""

        if not self.api.cek_koneksi():
            return RingkasanSiklus(online=False)

        ringkasan = RingkasanSiklus(online=True)

        # --- Push absensi ---
        belum_sync = self.repo.record_belum_sync(batas=self.batas_batch)
        if belum_sync:
            try:
                hasil_list = self.api.sync_absensi(belum_sync)
                ringkasan.dikirim = len(hasil_list)
                for hasil in hasil_list:
                    self.repo.tandai_hasil_sync(hasil.record_id, hasil.status)
                    if hasil.status == "disimpan":
                        ringkasan.disimpan += 1
                    elif hasil.status == "duplikat_diabaikan":
                        ringkasan.duplikat += 1
                    else:
                        ringkasan.gagal += 1
                        logger.warning("Sync gagal untuk record %s: %s", hasil.record_id, hasil.pesan)
            except (KoneksiGagal, requests.exceptions.RequestException) as e:
                # Koneksi putus di TENGAH proses push — record tetap
                # synced=0, akan dicoba lagi siklus berikutnya. Bukan error
                # fatal, ini skenario offline-first yang memang diantisipasi.
                ringkasan.pesan_error = f"Koneksi terputus saat push: {e}"
                return ringkasan

        # --- Tarik update embedding ---
        try:
            sejak = self.repo.get_metadata("embedding_diperbarui_sejak")
            resp = self.api.tarik_embedding(diperbarui_sejak=sejak)
            for item in resp["data"]:
                self.repo.upsert_siswa(item["siswa_id"], item["nis"], item["nama"], item["kelas"])
                self.repo.upsert_embedding(
                    item["siswa_id"], bytes.fromhex(item["embedding_encrypted"]),
                    item["model_version"], item["diperbarui_pada"],
                )
            ringkasan.embedding_diperbarui = resp["jumlah"]
            self.repo.set_metadata("embedding_diperbarui_sejak", resp["server_time"])
        except KoneksiGagal as e:
            ringkasan.pesan_error = f"Koneksi terputus saat tarik embedding: {e}"

        # --- Tarik jadwal efektif per kelas yang relevan ---
        try:
            entries = []
            for kelas in self.repo.daftar_kelas():
                data = self.api.tarik_jadwal_efektif(kelas)
                if data.get("jam_masuk") and data.get("jam_pulang"):
                    entries.append({
                        "kelas": kelas, "jam_masuk": data["jam_masuk"],
                        "jam_pulang": data["jam_pulang"], "sumber": data["sumber"],
                    })
            if entries:
                self.repo.replace_jadwal_cache(entries)
                ringkasan.jadwal_diperbarui = len(entries)
        except LayananJadwalBelumSiap as e:
            # Bukan error jaringan — cukup dicatat, kiosk tetap jalan
            # pakai jam default/cache terakhir (lihat main.py)
            logger.info("Jadwal tidak di-refresh: %s", e)
        except (KoneksiGagal, requests.exceptions.RequestException) as e:
            ringkasan.pesan_error = (ringkasan.pesan_error or "") + f" | Koneksi terputus saat tarik jadwal: {e}"

        # --- Tarik dispensasi aktif hari ini ---
        try:
            hari_ini = date_cls.today().isoformat()
            entries = self.api.tarik_dispensasi_hari_ini(hari_ini)
            self.repo.replace_dispensasi_cache(hari_ini, entries)
            ringkasan.dispensasi_diperbarui = len(entries)
        except LayananJadwalBelumSiap as e:
            logger.info("Dispensasi tidak di-refresh: %s", e)
        except (KoneksiGagal, requests.exceptions.RequestException) as e:
            ringkasan.pesan_error = (ringkasan.pesan_error or "") + f" | Koneksi terputus saat tarik dispensasi: {e}"

        return ringkasan
