from unittest.mock import MagicMock

from app.api.client import HasilSyncItem, KoneksiGagal
from app.database.repository import RekamanAbsensi
from app.sync.service import SyncService


def _rekaman(record_id="rid-1", siswa_id=1, tanggal="2026-08-24"):
    return RekamanAbsensi(record_id, siswa_id, tanggal, "MASUK", "2026-08-24T07:00:00", "NORMAL", None, "dev1", False, None)


def test_siklus_sync_offline_tidak_coba_push():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = False

    hasil = SyncService(repo, api).siklus_sync()

    assert hasil.online is False
    api.sync_absensi.assert_not_called()
    repo.record_belum_sync.assert_not_called()


def test_siklus_sync_push_sukses_menandai_repo():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = [_rekaman("rid-1"), _rekaman("rid-2", tanggal="2026-08-23")]
    repo.get_metadata.return_value = None
    api.sync_absensi.return_value = [
        HasilSyncItem("rid-1", "disimpan"),
        HasilSyncItem("rid-2", "duplikat_diabaikan"),
    ]
    api.tarik_embedding.return_value = {"server_time": "t", "jumlah": 0, "data": []}

    hasil = SyncService(repo, api).siklus_sync()

    assert hasil.dikirim == 2
    assert hasil.disimpan == 1
    assert hasil.duplikat == 1
    repo.tandai_hasil_sync.assert_any_call("rid-1", "disimpan")
    repo.tandai_hasil_sync.assert_any_call("rid-2", "duplikat_diabaikan")


def test_siklus_sync_koneksi_putus_saat_push_tidak_crash():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = [_rekaman()]
    api.sync_absensi.side_effect = KoneksiGagal("timeout")

    hasil = SyncService(repo, api).siklus_sync()

    assert hasil.pesan_error is not None
    assert hasil.online is True  # koneksi awalnya ada, putus di tengah


def test_siklus_sync_tanpa_record_tetap_tarik_embedding():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = []
    repo.get_metadata.return_value = "2026-08-23T00:00:00"
    api.tarik_embedding.return_value = {
        "server_time": "2026-08-24T10:00:00", "jumlah": 1,
        "data": [{"siswa_id": 1, "nis": "A1", "nama": "X", "kelas": "XI",
                  "embedding_encrypted": "aabb", "model_version": "v1", "diperbarui_pada": "t"}],
    }

    hasil = SyncService(repo, api).siklus_sync()

    assert hasil.embedding_diperbarui == 1
    api.tarik_embedding.assert_called_with(diperbarui_sejak="2026-08-23T00:00:00")
    repo.set_metadata.assert_called_with("embedding_diperbarui_sejak", "2026-08-24T10:00:00")

def test_siklus_sync_hapus_siswa_nonaktif_dari_server():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = []
    repo.get_metadata.return_value = None
    repo.hapus_siswa_dan_embedding.return_value = True
    api.tarik_embedding.return_value = {
        "server_time": "2026-08-24T10:00:00", "jumlah": 2,
        "data": [
            {"siswa_id": 1, "nis": "A1", "nama": "X", "kelas": "XI",
             "embedding_encrypted": "aabb", "model_version": "v1", "diperbarui_pada": "t",
             "aktif": True},
            {"siswa_id": 2, "nis": "A2", "nama": "Y", "kelas": "XII",
             "embedding_encrypted": "ccdd", "model_version": "v1", "diperbarui_pada": "t",
             "aktif": False},
        ],
    }

    hasil = SyncService(repo, api).siklus_sync()

    # Siswa nonaktif dihapus, tidak di-upsert
    repo.hapus_siswa_dan_embedding.assert_called_once_with(2)
    repo.upsert_siswa.assert_called_once_with(1, "A1", "X", "XI")
    repo.upsert_embedding.assert_called_once()
    assert hasil.embedding_diperbarui == 2


def test_siklus_sync_menarik_jadwal_untuk_kelas_yang_ada():
    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = []
    repo.get_metadata.return_value = None
    repo.daftar_kelas.return_value = ["XI Elektronika"]
    api.tarik_embedding.return_value = {"server_time": "t", "jumlah": 0, "data": []}
    api.tarik_jadwal_efektif.return_value = {"sumber": "standar", "jam_masuk": "07:00:00", "jam_pulang": "15:00:00"}

    hasil = SyncService(repo, api).siklus_sync()

    assert hasil.jadwal_diperbarui == 1
    api.tarik_jadwal_efektif.assert_called_with("XI Elektronika")
    repo.replace_jadwal_cache.assert_called_once()


def test_siklus_sync_jadwal_fetch_failure_tidak_dianggap_error():
    import requests.exceptions

    repo, api = MagicMock(), MagicMock()
    api.cek_koneksi.return_value = True
    repo.record_belum_sync.return_value = []
    repo.get_metadata.return_value = None
    repo.daftar_kelas.return_value = ["XI"]
    api.tarik_embedding.return_value = {"server_time": "t", "jumlah": 0, "data": []}
    api.tarik_jadwal_efektif.side_effect = requests.exceptions.ConnectionError("server down")

    hasil = SyncService(repo, api).siklus_sync()

    # Sinkronisasi tetap selesai, tetapi kegagalan jadwal dilaporkan.
    assert "Koneksi terputus saat tarik jadwal" in hasil.pesan_error
    assert hasil.jadwal_diperbarui == 0
