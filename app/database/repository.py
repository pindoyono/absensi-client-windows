"""
Lapisan akses data lokal. Semua query SQLite/SQLCipher lewat sini,
supaya business logic (attendance_logic.py) tidak perlu tahu SQL.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

try:
    import sqlcipher3 as sqlite3
except ImportError:
    import sqlite3


@dataclass
class RekamanAbsensi:
    record_id: str
    siswa_id: int
    tanggal: str
    type: str
    jam_aktual: str
    status_kehadiran_otomatis: str
    catatan: Optional[str]
    device_id: str
    synced: bool
    sync_status: Optional[str]

    def asdict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


class AbsensiRepository:
    def __init__(self, conn: sqlcipher3.Connection):
        self.conn = conn

    # ---------- Siswa & embedding cache ----------

    def upsert_siswa(self, siswa_id: int, nis: str, nama: str, kelas: str) -> None:
        self.conn.execute(
            """INSERT INTO siswa_cache (siswa_id, nis, nama, kelas)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(siswa_id) DO UPDATE SET nis=excluded.nis, nama=excluded.nama, kelas=excluded.kelas""",
            (siswa_id, nis, nama, kelas),
        )
        self.conn.commit()

    def upsert_embedding(self, siswa_id: int, embedding_encrypted: bytes, model_version: str, diperbarui_pada: str) -> None:
        self.conn.execute(
            """INSERT INTO embedding_cache (siswa_id, embedding_encrypted, model_version, diperbarui_pada)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(siswa_id) DO UPDATE SET
                 embedding_encrypted=excluded.embedding_encrypted,
                 model_version=excluded.model_version,
                 diperbarui_pada=excluded.diperbarui_pada""",
            (siswa_id, embedding_encrypted, model_version, diperbarui_pada),
        )
        self.conn.commit()

    def semua_embedding(self) -> list[tuple[int, str, str, bytes]]:
        """Return (siswa_id, nama, kelas, embedding_encrypted) untuk semua
        siswa yang sudah di-cache — dipakai loop matching wajah."""
        rows = self.conn.execute(
            """SELECT s.siswa_id, s.nama, s.kelas, e.embedding_encrypted
               FROM siswa_cache s JOIN embedding_cache e ON e.siswa_id = s.siswa_id"""
        ).fetchall()
        return [(r["siswa_id"], r["nama"], r["kelas"], r["embedding_encrypted"]) for r in rows]

    def get_siswa(self, siswa_id: int) -> Optional[sqlcipher3.Row]:
        return self.conn.execute(
            "SELECT * FROM siswa_cache WHERE siswa_id = ?", (siswa_id,)
        ).fetchone()

    def daftar_kelas(self) -> list[str]:
        """Daftar kelas unik dari siswa yang sudah ter-cache di device
        ini — dipakai sync worker untuk tahu kelas mana saja yang perlu
        di-refresh jadwalnya (device tidak perlu tahu jadwal SEMUA kelas
        di sekolah, cukup kelas yang siswanya lewat device ini)."""
        rows = self.conn.execute("SELECT DISTINCT kelas FROM siswa_cache ORDER BY kelas").fetchall()
        return [r["kelas"] for r in rows]

    # ---------- Jadwal cache ----------

    def replace_jadwal_cache(self, entries: list[dict]) -> None:
        self.conn.execute("DELETE FROM jadwal_cache")
        for e in entries:
            self.conn.execute(
                """INSERT INTO jadwal_cache (kelas, tanggal, hari, jam_masuk, jam_pulang, sumber, ditarik_pada)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (e.get("kelas"), e.get("tanggal"), e.get("hari"), e["jam_masuk"], e["jam_pulang"],
                 e["sumber"], datetime.now().isoformat()),
            )
        self.conn.commit()

    def jadwal_untuk_kelas(self, kelas: str) -> Optional[sqlcipher3.Row]:
        """Ambil jadwal ter-cache untuk kelas tertentu — override menang
        atas standar (lihat urutan ORDER BY)."""
        return self.conn.execute(
            """SELECT * FROM jadwal_cache
               WHERE (kelas = ? OR kelas IS NULL)
               ORDER BY sumber = 'override' DESC, kelas IS NOT NULL DESC
               LIMIT 1""",
            (kelas,),
        ).fetchone()

    # ---------- Absensi lokal (inti offline-first) ----------

    def status_hari_ini(self, siswa_id: int, tanggal: str) -> str:
        """BELUM_ABSEN | SUDAH_MASUK | SELESAI — dicek dari SQLite lokal,
        TIDAK PERNAH menunggu server (lihat bagian 4.1 dokumen arsitektur)."""
        rows = self.conn.execute(
            "SELECT type FROM absensi_lokal WHERE siswa_id = ? AND tanggal = ?",
            (siswa_id, tanggal),
        ).fetchall()
        types = {r["type"] for r in rows}
        if "MASUK" in types and "PULANG" in types:
            return "SELESAI"
        if "MASUK" in types:
            return "SUDAH_MASUK"
        return "BELUM_ABSEN"

    def simpan_absensi(
        self, siswa_id: int, type_: str, status_kehadiran_otomatis: str,
        device_id: str, catatan: Optional[str] = None,
        tanggal: Optional[str] = None, jam_aktual: Optional[datetime] = None,
    ) -> RekamanAbsensi:
        """Simpan record baru. record_id di-generate DI SINI (client),
        bukan menunggu server — inilah yang membuat offline-first bekerja
        dan sync jadi idempotent (lihat docs/API_CONTRACT.md bagian 4)."""
        tanggal = tanggal or date.today().isoformat()
        jam_aktual = jam_aktual or datetime.now()
        record_id = str(uuid.uuid4())

        self.conn.execute(
            """INSERT INTO absensi_lokal
               (record_id, siswa_id, tanggal, type, jam_aktual, status_kehadiran_otomatis,
                catatan, device_id, synced, dibuat_pada)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (record_id, siswa_id, tanggal, type_, jam_aktual.isoformat(),
             status_kehadiran_otomatis, catatan, device_id, datetime.now().isoformat()),
        )
        self.conn.commit()

        return RekamanAbsensi(
            record_id=record_id, siswa_id=siswa_id, tanggal=tanggal, type=type_,
            jam_aktual=jam_aktual.isoformat(), status_kehadiran_otomatis=status_kehadiran_otomatis,
            catatan=catatan, device_id=device_id, synced=False, sync_status=None,
        )

    def record_belum_sync(self, batas: int = 100) -> list[RekamanAbsensi]:
        rows = self.conn.execute(
            "SELECT * FROM absensi_lokal WHERE synced = 0 ORDER BY dibuat_pada LIMIT ?",
            (batas,),
        ).fetchall()
        return [
            RekamanAbsensi(
                record_id=r["record_id"], siswa_id=r["siswa_id"], tanggal=r["tanggal"],
                type=r["type"], jam_aktual=r["jam_aktual"],
                status_kehadiran_otomatis=r["status_kehadiran_otomatis"],
                catatan=r["catatan"], device_id=r["device_id"],
                synced=bool(r["synced"]), sync_status=r["sync_status"],
            )
            for r in rows
        ]

    def tandai_hasil_sync(self, record_id: str, status: str) -> None:
        """status: 'disimpan' | 'duplikat_diabaikan' -> synced=1
                   'gagal' -> synced tetap 0, retry nanti (lihat app/sync/worker.py)"""
        if status in ("disimpan", "duplikat_diabaikan"):
            self.conn.execute(
                "UPDATE absensi_lokal SET synced = 1, sync_status = ? WHERE record_id = ?",
                (status, record_id),
            )
        else:
            self.conn.execute(
                "UPDATE absensi_lokal SET percobaan_sync = percobaan_sync + 1, sync_status = ? WHERE record_id = ?",
                (status, record_id),
            )
        self.conn.commit()

    def bersihkan_data_lama(self, lebih_lama_dari_hari: int = 7) -> int:
        """Retention: hapus record yang SUDAH sync dan lebih lama dari N
        hari. Record yang belum sync TIDAK PERNAH dihapus otomatis,
        berapapun lama umurnya (lihat bagian 8.3 dokumen arsitektur)."""
        cur = self.conn.execute(
            """DELETE FROM absensi_lokal
               WHERE synced = 1 AND date(tanggal) < date('now', ?)""",
            (f"-{lebih_lama_dari_hari} days",),
        )
        self.conn.commit()
        return cur.rowcount

    # ---------- Sync metadata ----------

    def get_metadata(self, kunci: str) -> Optional[str]:
        row = self.conn.execute("SELECT nilai FROM sync_metadata WHERE kunci = ?", (kunci,)).fetchone()
        return row["nilai"] if row else None

    def set_metadata(self, kunci: str, nilai: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_metadata (kunci, nilai) VALUES (?, ?) ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai",
            (kunci, nilai),
        )
        self.conn.commit()

    # ---------- Dispensasi cache ----------
    def replace_dispensasi_cache(self, tanggal: str, entries: list[dict]) -> None:
        """Hapus semua entri dispensasi untuk tanggal tertentu, lalu masukkan yang baru.
        entries berisi dict dengan kunci: siswa_id, tanggal, jenis, kategori, alasan.
        """
        self.conn.execute("DELETE FROM dispensasi_cache WHERE tanggal = ?", (tanggal,))
        for e in entries:
            self.conn.execute(
                "INSERT INTO dispensasi_cache (siswa_id, tanggal, jenis, kategori, alasan) VALUES (?, ?, ?, ?, ?)",
                (e["siswa_id"], e["tanggal"], e["jenis"], e.get("kategori"), e.get("alasan")),
            )
        self.conn.commit()

    def punya_dispensasi_aktif(self, siswa_id: int, tanggal: str, jenis: str = "PULANG_CEPAT") -> Optional[sqlite3.Row]:
        """Kembalikan baris dispensasi jika ada untuk siswa, tanggal, dan jenis.
        """
        return self.conn.execute(
            "SELECT * FROM dispensasi_cache WHERE siswa_id = ? AND tanggal = ? AND jenis = ?",
            (siswa_id, tanggal, jenis),
        ).fetchone()
