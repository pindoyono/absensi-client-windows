"""
Wrapper HTTP ke absensi-server. Semua request di sini mengikuti
docs/API_CONTRACT.md dari project absensi-server persis — jangan ubah
format tanpa mengecek dokumen itu dulu, server memvalidasi ketat.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from app.database.repository import RekamanAbsensi


class KoneksiGagal(Exception):
    """Dilempar untuk SEMUA kegagalan jaringan (timeout, DNS, refused,
    dst) — ini kondisi OFFLINE NORMAL, bukan error aplikasi. Pemanggil
    (sync worker) menangkap ini dan menganggapnya "belum bisa sync",
    bukan menghentikan aplikasi."""
    pass


class LayananJadwalBelumSiap(Exception):
    """Dilempar kalau GURU_SERVICE_JWT belum dikonfigurasi. BEDA dengan
    KoneksiGagal — ini masalah konfigurasi, bukan jaringan, jadi
    sync worker tidak perlu retry terus-menerus untuk hal ini."""
    pass


@dataclass
class HasilSyncItem:
    record_id: str
    status: str  # 'disimpan' | 'duplikat_diabaikan' | 'gagal'
    pesan: Optional[str] = None


class ApiClient:
    def __init__(
        self, base_url: str, device_id: str, api_key: str,
        service_jwt: str = "", timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.device_id = device_id
        self.api_key = api_key
        self.service_jwt = service_jwt
        self.timeout = timeout

    def _headers_device(self) -> dict:
        return {"X-Device-Api-Key": self.api_key}

    def cek_koneksi(self) -> bool:
        """Cek cepat sebelum sync worker mencoba operasi berat — dipakai
        loop background (app/sync/worker.py)."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            return resp.status_code == 200
        except requests.RequestException as e:
            import logging
            logging.getLogger(__name__).warning("cek_koneksi gagal: %s", e)
            return False

    def sync_absensi(self, records: list[RekamanAbsensi]) -> list[HasilSyncItem]:
        """POST /absensi/sync — kirim batch record yang belum sync."""
        payload = {
            "records": [
                {
                    "record_id": r.record_id,
                    "siswa_id": r.siswa_id,
                    "tanggal": r.tanggal,
                    "type": r.type,
                    "jam_aktual": r.jam_aktual,
                    "status_kehadiran_otomatis": r.status_kehadiran_otomatis,
                    "catatan": r.catatan,
                    "device_id": r.device_id,
                }
                for r in records
            ]
        }
        try:
            resp = requests.post(
                f"{self.base_url}/absensi/sync",
                json=payload, headers=self._headers_device(), timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise KoneksiGagal(str(e)) from e

        data = resp.json()
        return [
            HasilSyncItem(record_id=item["record_id"], status=item["status"], pesan=item.get("pesan"))
            for item in data["hasil"]
        ]

    def tarik_embedding(self, diperbarui_sejak: Optional[str] = None) -> dict:
        """GET /embeddings/sync — cache embedding wajah ke lokal."""
        headers = {"X-Device-Id": self.device_id, **self._headers_device()}
        params = {"diperbarui_sejak": diperbarui_sejak} if diperbarui_sejak else {}
        try:
            resp = requests.get(
                f"{self.base_url}/embeddings/sync",
                headers=headers, params=params, timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise KoneksiGagal(str(e)) from e
        return resp.json()

    def tarik_jadwal_efektif(self, kelas: str) -> dict:
        """
        GET /jadwal/efektif — pakai GURU_SERVICE_JWT (akun layanan
        read-only khusus device, di-generate SEKALI oleh admin lewat
        cara yang sama seperti generate token guru — lihat docs/SETUP.md
        langkah 2b). SENGAJA BUKAN token guru pribadi, supaya device
        tidak menyimpan kredensial milik orang.

        CATATAN ARSITEKTUR: endpoint /jadwal/* di server saat ini hanya
        menerima JWT guru (get_current_guru), tidak ada jalur device
        API key untuk endpoint ini (beda dengan /absensi/sync dan
        /embeddings/sync). Service JWT ini adalah workaround praktis
        di sisi client. Perbaikan jangka panjang yang lebih bersih:
        tambahkan dukungan X-Device-Api-Key di endpoint /jadwal/efektif
        pada absensi-server (endpoint ini read-only & tidak sensitif,
        risikonya rendah untuk dibuka ke device).
        """
        if not self.service_jwt:
            raise LayananJadwalBelumSiap(
                "GURU_SERVICE_JWT belum dikonfigurasi di .env device ini — "
                "jadwal tidak bisa di-refresh, kiosk memakai jam default/cache terakhir"
            )
        headers = {"Authorization": f"Bearer {self.service_jwt}"}
        try:
            resp = requests.get(
                f"{self.base_url}/jadwal/efektif",
                headers=headers, params={"kelas": kelas}, timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise KoneksiGagal(str(e)) from e
        return resp.json()
