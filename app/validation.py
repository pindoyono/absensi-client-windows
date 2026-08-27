"""
Input validation utilities (REQ-SEC-004).

Mencegah injection attacks, malformed data, dan buffer overflow
pada semua input yang masuk ke sistem absensi.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Regex patterns
NIS_PATTERN = re.compile(r"^[0-9]{7,15}$")
NAMA_PATTERN = re.compile(r"^[A-Za-zÀ-ÿ\s\.\-']{1,100}$")
KELAS_PATTERN = re.compile(r"^[A-Z0-9\s]{1,10}$")
TANGGAL_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{32,128}$")

# Max lengths
MAX_NAMA_LENGTH = 100
MAX_KELAS_LENGTH = 20
MAX_RECORD_LENGTH = 10000  # bytes


class ValidationError(Exception):
    """Raised ketika input tidak valid."""
    pass


def validate_nis(nis: str) -> str:
    """Validasi NIS — hanya angka, 7-15 digit."""
    if not nis or not isinstance(nis, str):
        raise ValidationError("NIS tidak boleh kosong")
    if not NIS_PATTERN.match(nis):
        raise ValidationError(f"NIS tidak valid: harus 7-15 digit angka")
    return nis


def validate_nama(nama: str) -> str:
    """Validasi nama siswa — huruf, spasi, titik, strip, apostrof."""
    if not nama or not isinstance(nama, str):
        raise ValidationError("Nama tidak boleh kosong")
    nama = nama.strip()
    if len(nama) > MAX_NAMA_LENGTH:
        raise ValidationError(f"Nama terlalu panjang (max {MAX_NAMA_LENGTH} karakter)")
    if not NAMA_PATTERN.match(nama):
        raise ValidationError("Nama mengandung karakter tidak valid")
    return nama


def validate_kelas(kelas: str) -> str:
    """Validasi format kelas — contoh: 'XI', 'XII TKJ', 'X IPS'."""
    if not kelas or not isinstance(kelas, str):
        raise ValidationError("Kelas tidak boleh kosong")
    kelas = kelas.strip()
    if len(kelas) > MAX_KELAS_LENGTH:
        raise ValidationError(f"Kelas terlalu panjang (max {MAX_KELAS_LENGTH} karakter)")
    if not KELAS_PATTERN.match(kelas):
        raise ValidationError(f"Format kelas tidak valid: {kelas}")
    return kelas


def validate_tanggal(tanggal: str) -> str:
    """Validasi format tanggal ISO 8601 (YYYY-MM-DD)."""
    if not tanggal or not isinstance(tanggal, str):
        raise ValidationError("Tanggal tidak boleh kosong")
    if not TANGGAL_PATTERN.match(tanggal):
        raise ValidationError(f"Format tanggal tidak valid: {tanggal} (harus YYYY-MM-DD)")
    # Validate actual date
    from datetime import datetime
    try:
        datetime.strptime(tanggal, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"Tanggal tidak valid: {tanggal}")
    return tanggal


def validate_device_id(device_id: str) -> str:
    """Validasi device ID — alfanumerik, underscore, strip."""
    if not device_id or not isinstance(device_id, str):
        raise ValidationError("Device ID tidak boleh kosong")
    if not DEVICE_ID_PATTERN.match(device_id):
        raise ValidationError(f"Device ID tidak valid: {device_id}")
    return device_id


def validate_api_key(api_key: str) -> str:
    """Validasi API key — panjang dan karakter."""
    if not api_key or not isinstance(api_key, str):
        raise ValidationError("API key tidak boleh kosong")
    if not API_KEY_PATTERN.match(api_key):
        raise ValidationError("API key tidak valid: harus 32-128 karakter alfanumerik")
    return api_key


def validate_timestamp(timestamp: str) -> str:
    """Validasi timestamp Unix — hanya angka, 10 digit."""
    if not timestamp or not isinstance(timestamp, str):
        raise ValidationError("Timestamp tidak boleh kosong")
    if not timestamp.isdigit() or len(timestamp) != 10:
        raise ValidationError(f"Timestamp tidak valid: {timestamp}")
    return timestamp


def validate_signature(signature: str) -> str:
    """Validasi HMAC signature — hex string 64 karakter."""
    if not signature or not isinstance(signature, str):
        raise ValidationError("Signature tidak boleh kosong")
    if len(signature) != 64 or not re.match(r"^[0-9a-f]{64}$", signature):
        raise ValidationError("Signature tidak valid: harus hex string 64 karakter")
    return signature


def validate_record_size(data: bytes) -> bytes:
    """Validasi ukuran payload — cegah oversized request."""
    if len(data) > MAX_RECORD_LENGTH:
        raise ValidationError(f"Payload terlalu besar: {len(data)} bytes (max {MAX_RECORD_LENGTH})")
    return data


def sanitize_string(value: str, max_length: int = 255) -> str:
    """Sanitize string — hapus karakter berbahaya, batasi panjang."""
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)
    # Remove null bytes and control characters
    value = re.sub(r"[\x00-\x1f\x7f]", "", value)
    # Limit length
    if len(value) > max_length:
        value = value[:max_length]
    return value.strip()
