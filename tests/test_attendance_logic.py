from datetime import datetime, time

from app.business.attendance_logic import proses_absen, HasilAbsen


JAM_MASUK = time(7, 0)
JAM_PULANG = time(15, 0)


def test_absen_pertama_jadi_masuk(repo):
    keputusan = proses_absen(
        repo, siswa_id=1, device_id="dev1",
        jam_masuk_standar=JAM_MASUK, jam_pulang_standar=JAM_PULANG,
        sekarang=datetime(2026, 8, 24, 7, 2),
    )
    assert keputusan.hasil == HasilAbsen.BERHASIL_MASUK
    assert keputusan.rekaman.type == "MASUK"
    assert keputusan.rekaman.status_kehadiran_otomatis == "NORMAL"


def test_absen_kedua_jadi_pulang(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 2))
    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 15, 5),
    )
    assert keputusan.hasil == HasilAbsen.BERHASIL_PULANG
    assert keputusan.rekaman.type == "PULANG"


def test_absen_ketiga_ditolak(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 2))
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 15, 5))

    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 15, 30),
    )
    assert keputusan.hasil == HasilAbsen.DITOLAK_SUDAH_ABSEN
    assert keputusan.rekaman is None

    # Pastikan TIDAK ADA record ke-3 yang tersimpan
    assert len(repo.record_belum_sync()) == 2


def test_masuk_terlambat_terdeteksi(repo):
    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 30),
    )
    assert keputusan.rekaman.status_kehadiran_otomatis == "TERLAMBAT"
    assert "Terlambat" in keputusan.pesan


def test_masuk_dalam_toleransi_tetap_normal(repo):
    # toleransi default 5 menit, jam masuk 07:00 -> 07:04 masih NORMAL
    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, toleransi_menit=5,
        sekarang=datetime(2026, 8, 24, 7, 4),
    )
    assert keputusan.rekaman.status_kehadiran_otomatis == "NORMAL"


def test_pulang_cepat_terdeteksi(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 2))
    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 13, 0),
    )
    assert keputusan.rekaman.status_kehadiran_otomatis == "PULANG_CEPAT"


def test_siswa_berbeda_tidak_saling_pengaruh(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 2))
    keputusan = proses_absen(
        repo, 2, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 3),
    )
    assert keputusan.hasil == HasilAbsen.BERHASIL_MASUK


def test_hari_berbeda_boleh_absen_lagi(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 2))
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 15, 5))

    keputusan = proses_absen(
        repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 25, 7, 2),
    )
    assert keputusan.hasil == HasilAbsen.BERHASIL_MASUK
