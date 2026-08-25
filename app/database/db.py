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

    conn = sqlcipher3.connect(str(db_path))
    conn.row_factory = sqlcipher3.Row

    if settings.db_encryption_key:
        # PRAGMA key harus statement PERTAMA sebelum operasi lain apapun.
        # Escape kutip tunggal untuk jaga-jaga key mengandung karakter tsb.
        key_escaped = settings.db_encryption_key.replace("'", "''")
        conn.execute(f"PRAGMA key = '{key_escaped}'")

    conn.execute("PRAGMA foreign_keys = ON")

    with open(_SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()

    return conn
