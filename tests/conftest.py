import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Konfigurasi BLAS/threading sebelum NumPy di-load di test
import app.blas_config  # noqa: F401


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_absensi.db")


@pytest.fixture()
def repo(db_path, monkeypatch):
    """Repository dengan database SQLCipher sementara, key tetap untuk
    reproducibility test."""
    try:
        import sqlcipher3
    except ImportError:
        import sqlite3 as sqlcipher3
    from app.database.repository import AbsensiRepository
    from pathlib import Path

    schema_path = Path(__file__).parent.parent / "app" / "database" / "schema.sql"

    conn = sqlcipher3.connect(db_path)
    conn.row_factory = sqlcipher3.Row
    try:
        conn.execute("PRAGMA key = 'test-fixture-key'")
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys = ON")
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()

    yield AbsensiRepository(conn)
    conn.close()
