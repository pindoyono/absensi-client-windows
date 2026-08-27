"""
E2E Attendance Flow Tests (REQ-QA-002).
"""
import pytest
from unittest.mock import MagicMock
from datetime import time as dtime, datetime
from app.business.attendance_logic import (
    proses_absen,
    HasilAbsen,
    KeputusanAbsen,
)
from app.database.repository import AbsensiRepository, RekamanAbsensi


class TestE2EAttendanceFlow:
    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock(spec=AbsensiRepository)
        repo.status_hari_ini.return_value = "BELUM_ABSEN"
        def _dynamic_simpan(**kw):
            return RekamanAbsensi(
                record_id="test-123",
                siswa_id=kw.get("siswa_id", 1),
                tanggal=kw.get("tanggal", "2025-01-15"),
                type=kw.get("type_", "MASUK"),
                jam_aktual=str(kw.get("jam_aktual", "06:45:00")),
                status_kehadiran_otomatis=kw.get("status_kehadiran_otomatis", "NORMAL"),
                catatan=kw.get("catatan"),
                device_id=kw.get("device_id", "DEV-001"),
                synced=False,
                sync_status=None,
            )
        repo.simpan_absensi.side_effect = lambda **kw: _dynamic_simpan(**kw)
        return repo

    def test_e2e_normal_masuk_flow(self, mock_repo):
        # 1. Scan masuk tepat waktu
        hasil = proses_absen(
            repo=mock_repo,
            siswa_id=1,
            device_id="DEV-001",
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            toleransi_menit=5,
            sekarang=datetime(2025, 1, 15, 6, 45),
        )
        assert hasil.hasil == HasilAbsen.BERHASIL_MASUK
        assert hasil.rekaman is not None
        assert hasil.rekaman.type == "MASUK"

    def test_e2e_terlambat_masuk_flow(self, mock_repo):
        # 2. Scan masuk terlambat
        hasil = proses_absen(
            repo=mock_repo,
            siswa_id=1,
            device_id="DEV-001",
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            toleransi_menit=5,
            sekarang=datetime(2025, 1, 15, 7, 15),
        )
        assert hasil.hasil == HasilAbsen.BERHASIL_MASUK
        assert hasil.rekaman.status_kehadiran_otomatis == "TERLAMBAT"

    def test_e2e_sudah_absen_flow(self, mock_repo):
        # 3. Scan ketika sudah absen masuk + pulang
        mock_repo.status_hari_ini.return_value = "SELESAI"
        hasil = proses_absen(
            repo=mock_repo,
            siswa_id=1,
            device_id="DEV-001",
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            toleransi_menit=5,
            sekarang=datetime(2025, 1, 15, 10, 0),
        )
        assert hasil.hasil == HasilAbsen.DITOLAK_SUDAH_ABSEN

    def test_e2e_belum_waktunya_pulang_flow(self, mock_repo):
        # 4. Scan pulang sebelum jam pulang, tidak ada dispensasi
        mock_repo.status_hari_ini.return_value = "SUDAH_MASUK"
        mock_repo.punya_dispensasi_aktif.return_value = None
        hasil = proses_absen(
            repo=mock_repo,
            siswa_id=1,
            device_id="DEV-001",
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            toleransi_menit=5,
            sekarang=datetime(2025, 1, 15, 12, 0),
        )
        assert hasil.hasil == HasilAbsen.DITOLAK_BELUM_WAKTUNYA_PULANG

    def test_e2e_pulang_cepat_dengan_dispensasi_flow(self, mock_repo):
        # 5. Scan pulang sebelum jam pulang, ada dispensasi
        mock_repo.status_hari_ini.return_value = "SUDAH_MASUK"
        mock_repo.punya_dispensasi_aktif.return_value = {
            "kategori": "IZIN",
            "alasan": "Lomba",
        }
        hasil = proses_absen(
            repo=mock_repo,
            siswa_id=1,
            device_id="DEV-001",
            jam_masuk_standar=dtime(7, 0),
            jam_pulang_standar=dtime(15, 0),
            toleransi_menit=5,
            sekarang=datetime(2025, 1, 15, 12, 0),
        )
        assert hasil.hasil == HasilAbsen.BERHASIL_PULANG
        assert hasil.rekaman.type == "PULANG"
        assert hasil.rekaman.status_kehadiran_otomatis == "IZIN"
