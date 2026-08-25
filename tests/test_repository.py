try:
    import sqlcipher3
    HAS_SQLCIPHER = True
except ImportError:
    import sqlite3 as sqlcipher3
    HAS_SQLCIPHER = False
import pytest


@pytest.mark.skipif(not HAS_SQLCIPHER, reason="SQLCipher tidak tersedia, lewati test enkripsi")
def test_database_terenkripsi_tidak_bisa_dibaca_tanpa_key(db_path, repo):
    repo.upsert_siswa(1, "T001", "Test", "XI")

    import sqlite3
    with pytest.raises(Exception):
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT * FROM siswa_cache").fetchall()


def test_status_hari_ini_transisi(repo):
    assert repo.status_hari_ini(1, "2026-08-24") == "BELUM_ABSEN"

    repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2026-08-24")
    assert repo.status_hari_ini(1, "2026-08-24") == "SUDAH_MASUK"

    repo.simpan_absensi(1, "PULANG", "NORMAL", "dev1", tanggal="2026-08-24")
    assert repo.status_hari_ini(1, "2026-08-24") == "SELESAI"


def test_constraint_unique_lokal_menolak_duplikat(repo):
    repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2026-08-24")
    with pytest.raises(sqlcipher3.IntegrityError):
        repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2026-08-24")


def test_tandai_hasil_sync(repo):
    r = repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2026-08-24")
    assert len(repo.record_belum_sync()) == 1

    repo.tandai_hasil_sync(r.record_id, "disimpan")
    assert len(repo.record_belum_sync()) == 0


def test_record_gagal_sync_tetap_di_antrian(repo):
    r = repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2026-08-24")
    repo.tandai_hasil_sync(r.record_id, "gagal")
    # masih di antrian, TIDAK ditandai synced
    assert len(repo.record_belum_sync()) == 1


def test_bersihkan_data_lama_hanya_hapus_yang_sudah_sync(repo):
    r1 = repo.simpan_absensi(1, "MASUK", "NORMAL", "dev1", tanggal="2020-01-01")
    r2 = repo.simpan_absensi(2, "MASUK", "NORMAL", "dev1", tanggal="2020-01-01")
    repo.tandai_hasil_sync(r1.record_id, "disimpan")
    # r2 sengaja TIDAK ditandai sync

    dihapus = repo.bersihkan_data_lama(lebih_lama_dari_hari=7)
    assert dihapus == 1  # cuma r1 yang terhapus

    belum_sync = repo.record_belum_sync()
    assert len(belum_sync) == 1
    assert belum_sync[0].record_id == r2.record_id


def test_jadwal_cache_override_menang_atas_standar(repo):
    repo.replace_jadwal_cache([
        {"kelas": None, "hari": "SENIN", "jam_masuk": "07:00", "jam_pulang": "15:00", "sumber": "standar"},
        {"kelas": "XI", "tanggal": "2026-08-24", "jam_masuk": "08:00", "jam_pulang": "12:00", "sumber": "override"},
    ])
    hasil = repo.jadwal_untuk_kelas("XI")
    assert hasil["sumber"] == "override"
    assert hasil["jam_masuk"] == "08:00"
