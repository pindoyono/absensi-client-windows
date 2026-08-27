"""
Tests for REQ-OPS-004 (database backup & restore) and REQ-OPS-007 (health check).
"""
import os
import tempfile
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from app.database.backup import DatabaseBackup
from app.health import HealthChecker


class TestDatabaseBackup:
    def test_create_backup(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"test database content")
        
        key = Fernet.generate_key().decode()
        backup = DatabaseBackup(str(db_file), str(tmp_path / "backups"))
        backup_path = backup.create_backup(key)
        
        assert os.path.exists(backup_path)
        assert backup_path.endswith(".db.enc")
    
    def test_restore_backup(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"original content")
        
        key = Fernet.generate_key().decode()
        backup = DatabaseBackup(str(db_file), str(tmp_path / "backups"))
        backup_path = backup.create_backup(key)
        
        # Overwrite original
        db_file.write_bytes(b"corrupted content")
        
        # Restore
        backup.restore_backup(backup_path, key)
        assert db_file.read_bytes() == b"original content"
    
    def test_cleanup_old_backups(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        # Create backup file with old timestamp
        old_file = backup_dir / "absensi_lokal_2020-01-01_000000.db.enc"
        old_file.write_bytes(b"old backup")
        os.utime(old_file, (0, 0))  # Set to epoch
        
        backup = DatabaseBackup(str(tmp_path / "dummy.db"), str(backup_dir))
        backup.cleanup_old_backups(days_retention=30)
        
        assert not old_file.exists()


class TestHealthChecker:
    def test_get_full_health(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"test content")
        
        hc = HealthChecker(str(db_file))
        health = hc.get_full_health()
        
        assert "status" in health
        assert "disk" in health
        assert "database" in health
        assert health["status"] in ("healthy", "warning", "error")
    
    def test_database_size_check(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"test content")
        
        hc = HealthChecker(str(db_file))
        db_health = hc.check_database_size()
        
        assert db_health["status"] == "healthy"
        assert "size_mb" in db_health
    
    def test_database_not_found(self, tmp_path):
        hc = HealthChecker(str(tmp_path / "nonexistent.db"))
        db_health = hc.check_database_size()
        
        assert db_health["status"] == "error"
