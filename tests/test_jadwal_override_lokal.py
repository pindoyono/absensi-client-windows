"""Test override jadwal lokal (offline-first, Opsi C):
- CRUD override lokal
- Prioritas: lokal menang atas server
- Kadaluarsa otomatis (tanggal lewat dihapus)
- Push ke server (tandai terkirim)
"""
from datetime import date, timedelta

from app.database.repository import AbsensiRepository


def test_simpan_dan_baca_override_lokal(repo):
    oid = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00",
        kelas="XI", alasan="Ujian sekolah",
    )
    assert oid
    rows = repo.jadwal_override_lokal_semua()
    assert len(rows) == 1
    assert rows[0]["tanggal"] == "2026-08-29"
    assert rows[0]["kelas"] == "XI"
    assert rows[0]["terkirim"] == 0
    assert rows[0]["status_push"] == "pending"


def test_override_lokal_menang_atas_server(repo):
    # Server punya jadwal standar 07:00-15:00
    repo.replace_jadwal_cache([
        {"kelas": None, "hari": "SENIN", "jam_masuk": "07:00:00",
         "jam_pulang": "15:00:00", "sumber": "standar"},
    ])
    # Admin buat override lokal 09:00-13:00 untuk hari ini
    hari_ini = date.today().isoformat()
    repo.simpan_jadwal_override_lokal(
        tanggal=hari_ini, jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    hasil = repo.jadwal_untuk_kelas("XI", hari_ini)
    assert hasil["jam_masuk"] == "09:00:00"
    assert hasil["jam_pulang"] == "13:00:00"
    # Baris lokal punya kolom 'id' (penanda untuk badge kiosk)
    assert "id" in hasil.keys()


def test_override_lokal_umum_dipakai_kelas_lain(repo):
    hari_ini = date.today().isoformat()
    repo.simpan_jadwal_override_lokal(
        tanggal=hari_ini, jam_masuk="10:00:00", jam_pulang="14:00:00", kelas=None,
    )
    hasil = repo.jadwal_untuk_kelas("XII", hari_ini)
    assert hasil["jam_masuk"] == "10:00:00"


def test_override_lokal_kadaluarsa_otomatis(repo):
    kemarin = (date.today() - timedelta(days=1)).isoformat()
    besok = (date.today() + timedelta(days=1)).isoformat()
    repo.simpan_jadwal_override_lokal(
        tanggal=kemarin, jam_masuk="08:00:00", jam_pulang="12:00:00", kelas="XI",
    )
    repo.simpan_jadwal_override_lokal(
        tanggal=besok, jam_masuk="08:00:00", jam_pulang="12:00:00", kelas="XI",
    )
    dibuang = repo.buang_jadwal_override_lokal_kadaluarsa()
    assert dibuang == 1
    sisa = repo.jadwal_override_lokal_semua()
    assert len(sisa) == 1
    assert sisa[0]["tanggal"] == besok


def test_override_lokal_tandai_terkirim(repo):
    oid = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    assert repo.jadwal_override_lokal_belum_terkirim()
    repo.tandai_jadwal_override_terkirim(oid)
    assert repo.jadwal_override_lokal_belum_terkirim() == []
    rows = repo.jadwal_override_lokal_semua()
    assert rows[0]["terkirim"] == 1
    assert rows[0]["status_push"] == "ok"


def test_hapus_override_lokal(repo):
    oid = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    repo.hapus_jadwal_override_lokal(oid)
    assert repo.jadwal_override_lokal_semua() == []


def test_override_ditolak_server_tidak_retry(repo):
    oid = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    repo.tandai_jadwal_override_terkirim(oid, status="ditolak", pesan="HTTP 403")
    # Tidak di-push ulang (terkirim=1) tapi status jujur 'ditolak'
    assert repo.jadwal_override_lokal_belum_terkirim() == []
    rows = repo.jadwal_override_lokal_semua()
    assert rows[0]["status_push"] == "ditolak"
    assert rows[0]["pesan_push"] == "HTTP 403"


def test_reset_status_push_ditolak_jadi_pending(repo):
    oid_ditolak = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    oid_ok = repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-30", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    repo.tandai_jadwal_override_terkirim(oid_ditolak, status="ditolak", pesan="HTTP 403")
    repo.tandai_jadwal_override_terkirim(oid_ok, status="ok")

    n = repo.reset_jadwal_override_ditolak()
    assert n == 1  # hanya yang 'ditolak' yang direset

    rows = {r["id"]: r for r in repo.jadwal_override_lokal_semua()}
    assert rows[oid_ditolak]["terkirim"] == 0
    assert rows[oid_ditolak]["status_push"] == "pending"
    assert rows[oid_ditolak]["pesan_push"] is None
    # yang sudah ok tidak boleh ikut direset
    assert rows[oid_ok]["terkirim"] == 1
    assert rows[oid_ok]["status_push"] == "ok"
    # masuk lagi ke antrian push
    assert [o["id"] for o in repo.jadwal_override_lokal_belum_terkirim()] == [oid_ditolak]

def test_reset_status_push_tidak_ada_yang_ditolak(repo):
    repo.simpan_jadwal_override_lokal(
        tanggal="2026-08-29", jam_masuk="09:00:00", jam_pulang="13:00:00", kelas="XI",
    )
    assert repo.reset_jadwal_override_ditolak() == 0

def test_server_override_menang_kalau_tidak_ada_lokal(repo):
    hari_ini = date.today().isoformat()
    repo.replace_jadwal_cache([
        {"kelas": "XI", "tanggal": hari_ini, "jam_masuk": "08:00:00",
         "jam_pulang": "12:00:00", "sumber": "override"},
    ])
    hasil = repo.jadwal_untuk_kelas("XI", hari_ini)
    assert hasil["jam_masuk"] == "08:00:00"
    assert "id" not in hasil.keys()
