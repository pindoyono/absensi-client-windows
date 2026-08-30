"""
Konfigurasi client Windows. Nilai diambil dari file .env di folder yang
sama dengan executable — supaya bisa diganti per device tanpa build ulang.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.device.credentials import CredentialManager

# .env dicari di folder tempat aplikasi dijalankan (bukan hardcode path
# development), supaya installer bisa taruh .env di sebelah .exe
APP_DIR = Path(os.environ.get("ABSENSI_APP_DIR", Path.cwd()))
load_dotenv(APP_DIR / ".env")


@dataclass
class Settings:
    # URL server absensi. Fail-closed: default kosong → startup gagal kalau
    # SERVER_URL tidak diset di .env (tidak ada default hardcoded ke server
    # produksi tertentu, supaya aman dipakai lintas sekolah / open-source).
    server_url: str = os.environ.get("SERVER_URL", "")

    # URL dashboard web (frontend). Kalau DASHBOARD_URL kosong, turunkan dari
    # server_url dengan mengganti subdomain absen. → front. (mis. server
    # absen.smkn2malinau.sch.id → dashboard front.smkn2malinau.sch.id).
    dashboard_url: str = os.environ.get("DASHBOARD_URL", "")
    device_id: str = os.environ.get("DEVICE_ID", "")
    device_api_key: str = os.environ.get("DEVICE_API_KEY", "")

    # Key dekripsi embedding wajah — HARUS SAMA dengan FACE_ENCRYPTION_KEY
    # di server (lihat docs/API_CONTRACT.md bagian 7, Opsi A). Didistribusikan
    # manual oleh admin saat setup device, BUKAN ditarik lewat API.
    face_encryption_key: str = os.environ.get("FACE_ENCRYPTION_KEY", "")

    # Database lokal terenkripsi (SQLCipher)
    db_path: str = os.environ.get("DB_PATH", str(APP_DIR / "data" / "absensi_lokal.db"))
    db_encryption_key: str = os.environ.get("DB_ENCRYPTION_KEY", "")

    # Interval background sync (detik)
    sync_interval_seconds: int = int(os.environ.get("SYNC_INTERVAL_SECONDS", "45"))

    # Password admin untuk panel
    # Fail-closed: default kosong → akses panel admin DITOLAK kalau
    # ADMIN_PASSWORD tidak diset di .env. Admin wajib set password kuat.
    admin_password: str = os.environ.get("ADMIN_PASSWORD", "")

    # Secret JWT server — dipakai untuk verifikasi signature token lokal.
    # HARUS SAMA dengan JWT_SECRET di server. Kalau kosong, verifikasi
    # signature dilewati (fail-closed: token dianggap tidak valid).
    jwt_secret: str = os.environ.get("JWT_SECRET", "")

    # Toleransi keterlambatan (menit) sebelum dianggap TERLAMBAT — di luar
    # ini murni untuk buffer kecil (siswa antre di gerbang, bukan telat asli)
    toleransi_terlambat_menit: int = int(os.environ.get("TOLERANSI_TERLAMBAT_MENIT", "5"))

    # --- Ambang batas kesegaran data (PRD observabilitas degradasi) ---
    # Kalau data cache lokal lebih basi dari ambang ini, tampilkan badge
    # peringatan di kiosk (bukan cuma tercatat di log).
    batas_stale_jadwal_jam: int = int(os.environ.get("BATAS_STALE_JADWAL_JAM", "6"))
    batas_stale_dispensasi_jam: int = int(os.environ.get("BATAS_STALE_DISPENSASI_JAM", "2"))
    batas_stale_embedding_hari: int = int(os.environ.get("BATAS_STALE_EMBEDDING_HARI", "3"))

    # --- On-site testing gate (REQ-TEST-001) ---
    # Set 'true' setelah on-site testing selesai & lolos.
    # Aplikasi tidak akan masuk mode reguler (scan wajah aktif)
    # sampai flag ini diaktifkan.
    on_site_testing_selesai: bool = os.environ.get("ON_SITE_TESTING_SELESAI", "false").lower() == "true"

    def validasi(self) -> list[str]:
        """Kembalikan daftar masalah konfigurasi — dipakai saat startup
        supaya device dengan setup salah ketahuan cepat, bukan gagal
        diam-diam di tengah hari sekolah."""
        masalah = []
        if not self.server_url:
            masalah.append("SERVER_URL belum diisi di .env")
        if not self.device_id:
            masalah.append("DEVICE_ID belum diisi di .env")
        if not self.device_api_key:
            masalah.append("DEVICE_API_KEY belum diisi di .env")
        if not self.face_encryption_key:
            masalah.append("FACE_ENCRYPTION_KEY belum diisi di .env — minta ke admin server")
        if not self.db_encryption_key:
            masalah.append("DB_ENCRYPTION_KEY belum diisi di .env")
        return masalah

    def __post_init__(self):
        """Fallback ke Windows Credential Manager bila .env kosong (REQ-CRED-002)."""
        if not self.dashboard_url and self.server_url:
            # Turunkan URL dashboard dari server_url: absen.xxx → front.xxx
            object.__setattr__(
                self, "dashboard_url",
                self.server_url.replace("absen.", "front.", 1),
            )
        if not self.device_api_key and CredentialManager.is_available():
            cred = CredentialManager.get_credential("device_api_key")
            if cred:
                object.__setattr__(self, "device_api_key", cred)
        if not self.face_encryption_key and CredentialManager.is_available():
            cred = CredentialManager.get_credential("face_encryption_key")
            if cred:
                object.__setattr__(self, "face_encryption_key", cred)
        if not self.db_encryption_key and CredentialManager.is_available():
            cred = CredentialManager.get_credential("db_encryption_key")
            if cred:
                object.__setattr__(self, "db_encryption_key", cred)


settings = Settings()
