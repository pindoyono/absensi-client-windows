"""
Konfigurasi client Windows. Nilai diambil dari file .env di folder yang
sama dengan executable — supaya bisa diganti per device tanpa build ulang.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# .env dicari di folder tempat aplikasi dijalankan (bukan hardcode path
# development), supaya installer bisa taruh .env di sebelah .exe
APP_DIR = Path(os.environ.get("ABSENSI_APP_DIR", Path.cwd()))
load_dotenv(APP_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    server_url: str = os.environ.get("SERVER_URL", "https://absen.smkn2malinau.sch.id")
    device_id: str = os.environ.get("DEVICE_ID", "")
    device_api_key: str = os.environ.get("DEVICE_API_KEY", "")

    # Token akun layanan read-only khusus device, untuk akses endpoint
    # /jadwal/* (yang di server butuh JWT guru, bukan API key device —
    # lihat catatan di app/api/client.py). Di-generate SEKALI oleh admin,
    # bukan token guru pribadi. Kalau kosong, jadwal tidak ter-refresh
    # otomatis (kiosk tetap jalan pakai jam default/cache terakhir).
    guru_service_jwt: str = os.environ.get("GURU_SERVICE_JWT", "")

    # Key dekripsi embedding wajah — HARUS SAMA dengan FACE_ENCRYPTION_KEY
    # di server (lihat docs/API_CONTRACT.md bagian 7, Opsi A). Didistribusikan
    # manual oleh admin saat setup device, BUKAN ditarik lewat API.
    face_encryption_key: str = os.environ.get("FACE_ENCRYPTION_KEY", "")

    # Database lokal terenkripsi (SQLCipher)
    db_path: str = os.environ.get("DB_PATH", str(APP_DIR / "data" / "absensi_lokal.db"))
    db_encryption_key: str = os.environ.get("DB_ENCRYPTION_KEY", "")

    # Interval background sync (detik)
    sync_interval_seconds: int = int(os.environ.get("SYNC_INTERVAL_SECONDS", "45"))

    # Toleransi keterlambatan (menit) sebelum dianggap TERLAMBAT — di luar
    # ini murni untuk buffer kecil (siswa antre di gerbang, bukan telat asli)
    toleransi_terlambat_menit: int = int(os.environ.get("TOLERANSI_TERLAMBAT_MENIT", "5"))

    def validasi(self) -> list[str]:
        """Kembalikan daftar masalah konfigurasi — dipakai saat startup
        supaya device dengan setup salah ketahuan cepat, bukan gagal
        diam-diam di tengah hari sekolah."""
        masalah = []
        if not self.device_id:
            masalah.append("DEVICE_ID belum diisi di .env")
        if not self.device_api_key:
            masalah.append("DEVICE_API_KEY belum diisi di .env")
        if not self.face_encryption_key:
            masalah.append("FACE_ENCRYPTION_KEY belum diisi di .env — minta ke admin server")
        if not self.db_encryption_key:
            masalah.append("DB_ENCRYPTION_KEY belum diisi di .env")
        return masalah


settings = Settings()
