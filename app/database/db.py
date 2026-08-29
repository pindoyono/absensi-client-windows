"""
Koneksi ke database lokal terenkripsi (SQLCipher) — data 1000 siswa
+ embedding wajah ada di device ini, dan device bisa hilang/dicuri,
jadi WAJIB terenkripsi at-rest (lihat bagian 9.2 dokumen arsitektur).
"""
import os
from pathlib import Path

try:
    import sqlcipher3
    _USE_CIPHER = True
except ImportError:
    import sqlite3 as sqlcipher3
    _USE_CIPHER = False

from app.config import settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlcipher3.Connection:
    """Buka koneksi ke database lokal, set key enkripsi, dan pastikan
    skema sudah ada (idempotent — aman dipanggil setiap startup)."""
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False: koneksi ini dipakai lintas thread
    # (SyncWorker QThread background + thread sync manual dari panel admin).
    # Akses diserialisasi lewat _lock di repository (lihat repository.py).
    conn = sqlcipher3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlcipher3.Row

    if settings.db_encryption_key:
        # PRAGMA key harus statement PERTAMA sebelum operasi lain apapun.
        # Escape kutip tunggal untuk jaga-jaga key mengandung karakter tsb.
        key_escaped = settings.db_encryption_key.replace("'", "''")
        conn.execute(f"PRAGMA key = '{key_escaped}'")

    conn.execute("PRAGMA foreign_keys = ON")

    with open(_SCHEMA_PATH) as f:
        conn.executescript(f.read())

    # Migrasi idempotent: kolom status push untuk override jadwal lokal
    # (DB lama punya tabel tanpa kolom ini).
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jadwal_override_lokal)").fetchall()]
        if cols and "status_push" not in cols:
            conn.execute("ALTER TABLE jadwal_override_lokal ADD COLUMN status_push TEXT NOT NULL DEFAULT 'pending'")
        if cols and "pesan_push" not in cols:
            conn.execute("ALTER TABLE jadwal_override_lokal ADD COLUMN pesan_push TEXT")
    except Exception:
        pass  # tabel belum ada di DB sangat lama — aman diabaikan

    conn.commit()

    return conn
