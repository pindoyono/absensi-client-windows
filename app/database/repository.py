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

import logging

logger = logging.getLogger(__name__)


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
        # Lock untuk serialisasi akses lintas thread (SyncWorker QThread
        # background + thread sync manual dari panel admin + main thread
        # kiosk). Semua metode repository adalah operasi DB murni (HTTP
        # ada di ApiClient), jadi membungkusnya dengan lock tidak akan
        # menahan request jaringan. RLock = reentrant, aman untuk pemanggilan
        # bersarang dalam satu thread.
        import threading
        self._lock = threading.RLock()
        self._wrap_metode_dengan_lock()

    def _wrap_metode_dengan_lock(self) -> None:
        """Bungkus semua metode publik instance dengan self._lock supaya
        akses SQLite dari beberapa thread ter-serialisasi."""
        import functools
        for nama in dir(type(self)):
            if nama.startswith("_"):
                continue
            attr = getattr(type(self), nama, None)
            if callable(attr):
                setattr(self, nama, self._kunci(attr))

    def _kunci(self, fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with self._lock:
                return fn(self, *args, **kwargs)

        return wrapper

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

    def hapus_embedding_tidak_sesuai_kunci(self, face_encryption_key: str) -> int:
        """Hapus semua embedding yang TIDAK BISA didekripsi dengan kunci
        FACE_ENCRYPTION_KEY saat ini (mis. kunci baru dipasang di .env,
        embedding lama dienkripsi kunci lama). Return jumlah baris dihapus.

        Embedding yang gagal dekripsi tidak berguna untuk matching —
        matcher melewati mereka tiap frame (buang CPU) dan log penuh
        error. Setelah dihapus, reset metadata 'embedding_diperbarui_sejak'
        supaya siklus sync berikutnya menarik ulang SEMUA embedding dari
        server (yang dienkripsi kunci baru)."""
        from app.face.crypto_embedding import decrypt_embedding, KunciEnkripsiSalah

        rows = self.conn.execute(
            "SELECT siswa_id, embedding_encrypted FROM embedding_cache"
        ).fetchall()
        rusak = []
        for r in rows:
            try:
                decrypt_embedding(r["embedding_encrypted"], face_encryption_key)
            except KunciEnkripsiSalah:
                rusak.append(r["siswa_id"])
        if not rusak:
            return 0
        cur = self.conn.execute(
            f"DELETE FROM embedding_cache WHERE siswa_id IN ({','.join('?' * len(rusak))})",
            rusak,
        )
        self.conn.commit()
        return cur.rowcount

    def reset_metadata_tarik_embedding(self) -> None:
        """Reset watermark 'embedding_diperbarui_sejak' supaya siklus sync
        berikutnya menarik ulang SEMUA embedding dari server (bukan hanya
        yang berubah sejak terakhir sync)."""
        self.conn.execute(
            "DELETE FROM sync_metadata WHERE kunci = 'embedding_diperbarui_sejak'"
        )
        self.conn.commit()

    def get_siswa(self, siswa_id: int) -> Optional[sqlcipher3.Row]:
        return self.conn.execute(
            "SELECT * FROM siswa_cache WHERE siswa_id = ?", (siswa_id,)
        ).fetchone()

    def hapus_siswa_dan_embedding(self, siswa_id: int) -> bool:
        """Hapus siswa + embedding-nya dari cache lokal (dipakai saat
        server menandai siswa nonaktif/hapus via sync embedding)."""
        cur = self.conn.execute(
            "DELETE FROM embedding_cache WHERE siswa_id = ?", (siswa_id,)
        )
        cur2 = self.conn.execute(
            "DELETE FROM siswa_cache WHERE siswa_id = ?", (siswa_id,)
        )
        self.conn.commit()
        return cur2.rowcount > 0

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

    # ---------- Override jadwal lokal (offline-first, Opsi C) ----------

    def jadwal_override_lokal_belum_terkirim(self) -> list[dict]:
        """Override jadwal lokal yang belum di-push ke server."""
        rows = self.conn.execute(
            "SELECT id, tanggal, kelas, jam_masuk, jam_pulang, alasan, dibuat_pada "
            "FROM jadwal_override_lokal WHERE terkirim = 0 ORDER BY dibuat_pada"
        ).fetchall()
        return [dict(r) for r in rows]

    def jadwal_override_lokal_semua(self) -> list[dict]:
        """Semua override jadwal lokal (untuk tabel admin)."""
        rows = self.conn.execute(
            "SELECT id, tanggal, kelas, jam_masuk, jam_pulang, alasan, dibuat_pada, "
            "terkirim, status_push, pesan_push "
            "FROM jadwal_override_lokal ORDER BY tanggal DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def simpan_jadwal_override_lokal(
        self, tanggal: str, jam_masuk: str, jam_pulang: str,
        kelas: Optional[str] = None, alasan: Optional[str] = None,
    ) -> str:
        """Simpan override jadwal lokal. return id (UUID) untuk push."""
        import uuid
        override_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO jadwal_override_lokal
               (id, tanggal, kelas, jam_masuk, jam_pulang, alasan, dibuat_pada, terkirim, status_push)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending')""",
            (override_id, tanggal, kelas, jam_masuk, jam_pulang, alasan,
             datetime.now().isoformat()),
        )
        self.conn.commit()
        return override_id

    def tandai_jadwal_override_terkirim(
        self, override_id: str, status: str = "ok", pesan: Optional[str] = None
    ) -> None:
        """Tandai override lokal sudah di-push ke server.

        status: 'ok' (server terima) | 'ditolak' (403/404, jangan retry).
        Keduanya set terkirim=1 supaya tidak di-push ulang tiap siklus.
        """
        self.conn.execute(
            "UPDATE jadwal_override_lokal SET terkirim = 1, status_push = ?, pesan_push = ? WHERE id = ?",
            (status, pesan, override_id),
        )
        self.conn.commit()

    def hapus_jadwal_override_lokal(self, override_id: str) -> None:
        self.conn.execute(
            "DELETE FROM jadwal_override_lokal WHERE id = ?", (override_id,)
        )
        self.conn.commit()

    def buang_jadwal_override_lokal_kadaluarsa(self) -> int:
        """Hapus override lokal yang tanggalnya sudah lewat (kadaluarsa
        otomatis). Return jumlah baris yang dihapus."""
        hari_ini = date.today().isoformat()
        cur = self.conn.execute(
            "DELETE FROM jadwal_override_lokal WHERE tanggal < ?", (hari_ini,)
        )
        self.conn.commit()
        return cur.rowcount

    def reset_jadwal_override_ditolak(self) -> int:
        """Reset override yang sebelumnya ditolak server (status='ditolak')
        supaya dicoba push ulang di siklus sync berikutnya. Return jumlah
        baris yang direset."""
        cur = self.conn.execute(
            """UPDATE jadwal_override_lokal
               SET terkirim = 0,
                   status_push = 'pending',
                   pesan_push = NULL
               WHERE status_push = 'ditolak'"""
        )
        self.conn.commit()
        return cur.rowcount

    def jadwal_override_lokal_jadwal_aktif(self, kelas: str, tanggal: str) -> Optional[sqlcipher3.Row]:
        """Ambil override lokal yang berlaku untuk kelas+hari ini.
        Prioritas: kelas spesifik > kelas NULL (umum)."""
        return self.conn.execute(
            """SELECT * FROM jadwal_override_lokal
               WHERE tanggal = ? AND (kelas = ? OR kelas IS NULL)
               ORDER BY kelas IS NOT NULL DESC
               LIMIT 1""",
            (tanggal, kelas),
        ).fetchone()

    def jadwal_untuk_kelas(self, kelas: str, tanggal: Optional[str] = None) -> Optional[sqlcipher3.Row]:
        """Ambil jadwal ter-cache untuk kelas tertentu.

        Saat tanggal=None (legacy/tanpa tanggal): pakai prioritas lama —
        override server bertanggal (apapun) menang atas standar umum.

        Saat tanggal diberi (pemakaian kiosk): prioritas offline-first —
        1. Override LOKAL untuk kelas ini (dibuat di device, Opsi C)
        2. Override LOKAL umum (kelas NULL)
        3. Override SERVER untuk tanggal+kelas ini
        4. Override SERVER umum di tanggal itu
        5. Standar SERVER umum (kelas NULL) — berlaku semua hari
        """
        if tanggal is None:
            # Perilaku lama: override server (tanpa filter tanggal) menang
            override = self.conn.execute(
                """SELECT * FROM jadwal_cache
                   WHERE (kelas = ? OR kelas IS NULL) AND sumber = 'override'
                   ORDER BY kelas IS NOT NULL DESC
                   LIMIT 1""",
                (kelas,),
            ).fetchone()
            if override:
                return override
            return self.conn.execute(
                """SELECT * FROM jadwal_cache
                   WHERE (kelas = ? OR kelas IS NULL) AND sumber = 'standar'
                   ORDER BY kelas IS NOT NULL DESC
                   LIMIT 1""",
                (kelas,),
            ).fetchone()

        # 1 & 2: override lokal (Opsi C — menang di device)
        lokal = self.jadwal_override_lokal_jadwal_aktif(kelas, tanggal)
        if lokal:
            return lokal

        # 3-5: jadwal server — perilaku asli: override bertanggal menang,
        # lalu standar yang berlaku di tanggal itu (tanggal NULL/umum atau
        # persis tanggal tsb).
        return self.conn.execute(
            """SELECT * FROM jadwal_cache
               WHERE (kelas = ? OR kelas IS NULL)
                 AND (
                   (sumber = 'override' AND tanggal = ?)
                   OR (sumber = 'standar' AND (tanggal IS NULL OR tanggal = ?))
                 )
               ORDER BY sumber = 'override' DESC, kelas IS NOT NULL DESC
               LIMIT 1""",
            (kelas, tanggal, tanggal),
        ).fetchone()

    def jadwal_pertama_tersedia(self, tanggal: Optional[str] = None) -> Optional[sqlcipher3.Row]:
        """Ambil jadwal apa pun yang tersedia di cache (untuk tampilan header
        kiosk saat idle, ketika tidak ada jadwal umum kelas NULL). Prioritas:
        override lokal aktif → override server bertanggal → standar umum.
        Dipakai supaya label 'Masuk/Pulang' tidak kosong padahal data ada."""
        if tanggal:
            # Override lokal aktif dulu (Opsi C)
            lokal = self.jadwal_override_lokal_jadwal_aktif("", tanggal)
            if lokal:
                return lokal
        return self.conn.execute(
            """SELECT * FROM jadwal_cache
               ORDER BY sumber = 'override' DESC, kelas IS NOT NULL DESC
               LIMIT 1"""
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

    def record_sync_terbaru(self, batas: int = 20) -> list[dict]:
        """Ambil N record absensi terbaru (berdasarkan waktu dibuat) untuk
        ditampilkan di tabel status sinkronisasi panel admin."""
        rows = self.conn.execute(
            """SELECT record_id, siswa_id, tanggal, type, jam_aktual,
                      status_kehadiran_otomatis, synced, sync_status
               FROM absensi_lokal
               ORDER BY dibuat_pada DESC LIMIT ?""",
            (batas,),
        ).fetchall()
        return [dict(r) for r in rows]

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

    def statistik_sync(self) -> dict:
        """Hitung ringkasan status sinkronisasi untuk dashboard visualisasi.

        Returns:
            dict dengan kunci:
            - total_absensi: int
            - sudah_sync: int (synced=1)
            - belum_sync: int (synced=0)
            - gagal_sync: int (synced=0 tapi pernah gagal)
            - embedding_total: int (jumlah siswa di cache)
            - jadwal_total: int (jumlah baris jadwal_cache)
            - dispensasi_total: int (jumlah baris dispensasi_cache)
            - last_sync: str | None (ISO timestamp sync terakhir)
        """
        try:
            row = self.conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN synced = 1 THEN 1 ELSE 0 END) AS sudah,
                       SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) AS belum,
                       SUM(CASE WHEN synced = 0 AND percobaan_sync > 0 THEN 1 ELSE 0 END) AS gagal
                   FROM absensi_lokal"""
            ).fetchone()
            total = row["total"] or 0
            sudah = row["sudah"] or 0
            belum = row["belum"] or 0
            gagal = row["gagal"] or 0

            embedding = self.conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
            jadwal = self.conn.execute("SELECT COUNT(*) FROM jadwal_cache").fetchone()[0]
            dispensasi = self.conn.execute("SELECT COUNT(*) FROM dispensasi_cache").fetchone()[0]
            last_sync = self.get_metadata("sync_terakhir")

            return {
                "total_absensi": total,
                "sudah_sync": sudah,
                "belum_sync": belum,
                "gagal_sync": gagal,
                "embedding_total": embedding,
                "jadwal_total": jadwal,
                "dispensasi_total": dispensasi,
                "last_sync": last_sync,
            }
        except Exception as e:
            logger.warning("Gagal hitung statistik sync: %s", e)
            return {
                "total_absensi": 0, "sudah_sync": 0, "belum_sync": 0,
                "gagal_sync": 0, "embedding_total": 0, "jadwal_total": 0,
                "dispensasi_total": 0, "last_sync": None,
            }

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

    def status_kesegaran_data(self) -> dict:
        """Return {'jadwal_jam_lalu': ..., 'dispensasi_jam_lalu': ...}
        -- None kalau belum pernah sync sama sekali."""
        now = datetime.now()
        hasil = {}

        # Jadwal
        jadwal_terakhir = self.conn.execute(
            "SELECT MAX(ditarik_pada) as t FROM jadwal_cache"
        ).fetchone()["t"]
        hasil["jadwal_jam_lalu"] = (
            (now - datetime.fromisoformat(jadwal_terakhir)).total_seconds() / 3600
            if jadwal_terakhir else None
        )

        # Dispensasi
        disp_terakhir = self.get_metadata("dispensasi_terakhir_sync")
        hasil["dispensasi_jam_lalu"] = (
            (now - datetime.fromisoformat(disp_terakhir)).total_seconds() / 3600
            if disp_terakhir else None
        )

        # Embedding
        emb_terakhir = self.get_metadata("embedding_diperbarui_sejak")
        hasil["embedding_hari_lalu"] = (
            (now - datetime.fromisoformat(emb_terakhir)).days
            if emb_terakhir else None
        )
        return hasil

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

    # ---------- Liveness log (LIVENESS-004) ----------

    def log_liveness(
        self,
        wajah_terdeteksi: bool,
        is_real: Optional[bool],
        liveness_score: Optional[float],
        ambang_saat_itu: float,
        alasan_gagal: Optional[str] = None,
        siswa_id: Optional[int] = None,
        device_id: str = "",
    ) -> None:
        """Catat satu hasil liveness check ke tabel liveness_log."""
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                """INSERT INTO liveness_log
                   (timestamp, wajah_terdeteksi, is_real, liveness_score,
                    ambang_saat_itu, alasan_gagal, siswa_id, device_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now,
                    1 if wajah_terdeteksi else 0,
                    (1 if is_real else 0) if is_real is not None else None,
                    liveness_score,
                    ambang_saat_itu,
                    alasan_gagal,
                    siswa_id,
                    device_id,
                    now,
                ),
            )
            self.conn.commit()
        except Exception:
            # Logging liveness tidak boleh mengganggu alur absen utama.
            pass
