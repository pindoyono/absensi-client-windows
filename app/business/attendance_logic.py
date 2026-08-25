"""
Business logic absensi — HARUS identik secara aturan dengan yang di
server (lihat app/routers/absensi.py di absensi-server), supaya
keputusan yang dibuat offline tidak pernah bertentangan dengan yang
akan divalidasi server saat sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time
from enum import Enum
from typing import Optional

from app.database.repository import AbsensiRepository, RekamanAbsensi


class HasilAbsen(Enum):
    BERHASIL_MASUK = "berhasil_masuk"
    BERHASIL_PULANG = "berhasil_pulang"
    DITOLAK_SUDAH_ABSEN = "ditolak_sudah_absen"


@dataclass
class KeputusanAbsen:
    hasil: HasilAbsen
    rekaman: Optional[RekamanAbsensi] = None
    pesan: str = ""


def _hitung_status_otomatis(
    jam_aktual: datetime, type_: str, jam_masuk_standar: time, jam_pulang_standar: time,
    toleransi_menit: int,
) -> str:
    """NORMAL | TERLAMBAT | PULANG_CEPAT — logika ini harus sama persis
    dengan yang dipakai server (app/routers/jadwal.py, bagian 8.1
    dokumen arsitektur), supaya status yang dihitung offline konsisten
    dengan yang akan diverifikasi guru piket."""
    waktu = jam_aktual.time()

    if type_ == "MASUK":
        batas = _tambah_menit(jam_masuk_standar, toleransi_menit)
        return "TERLAMBAT" if waktu > batas else "NORMAL"

    if type_ == "PULANG":
        return "PULANG_CEPAT" if waktu < jam_pulang_standar else "NORMAL"

    return "NORMAL"


def _tambah_menit(t: time, menit: int) -> time:
    total_menit = t.hour * 60 + t.minute + menit
    return time(hour=(total_menit // 60) % 24, minute=total_menit % 60)


def proses_absen(
    repo: AbsensiRepository,
    siswa_id: int,
    device_id: str,
    jam_masuk_standar: time,
    jam_pulang_standar: time,
    toleransi_menit: int = 5,
    sekarang: Optional[datetime] = None,
) -> KeputusanAbsen:
    """
    Fungsi inti — dipanggil tiap kali wajah berhasil dikenali & lolos
    liveness check. Implementasi PERSIS state machine di bagian 4.1
    dokumen arsitektur:

        BELUM_ABSEN -> simpan sebagai MASUK
        SUDAH_MASUK -> simpan sebagai PULANG
        SELESAI     -> TOLAK, jangan buat record baru
    """
    sekarang = sekarang or datetime.now()
    tanggal = sekarang.date().isoformat()

    status = repo.status_hari_ini(siswa_id, tanggal)

    if status == "SELESAI":
        return KeputusanAbsen(
            hasil=HasilAbsen.DITOLAK_SUDAH_ABSEN,
            pesan="Masuk & pulang sudah tercatat hari ini",
        )

    type_ = "MASUK" if status == "BELUM_ABSEN" else "PULANG"

    status_otomatis = _hitung_status_otomatis(
        sekarang, type_, jam_masuk_standar, jam_pulang_standar, toleransi_menit,
    )

    rekaman = repo.simpan_absensi(
        siswa_id=siswa_id, type_=type_, status_kehadiran_otomatis=status_otomatis,
        device_id=device_id, tanggal=tanggal, jam_aktual=sekarang,
    )

    hasil = HasilAbsen.BERHASIL_MASUK if type_ == "MASUK" else HasilAbsen.BERHASIL_PULANG
    pesan = {
        "NORMAL": "Tepat waktu",
        "TERLAMBAT": f"Terlambat · masuk {sekarang.strftime('%H:%M')}",
        "PULANG_CEPAT": f"Pulang cepat · keluar {sekarang.strftime('%H:%M')}",
    }[status_otomatis]

    return KeputusanAbsen(hasil=hasil, rekaman=rekaman, pesan=pesan)
