"""
Database backup & restore module (REQ-OPS-004).

Backup database lokal ke file terenkripsi dan restore jika diperlukan.
"""
import shutil
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class DatabaseBackup:
    def __init__(self, db_path: str, backup_dir: str):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(self, encryption_key: str) -> str:
        """Create encrypted backup."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_name = f"absensi_lokal_{timestamp}.db.enc"
        backup_path = self.backup_dir / backup_name
        
        # Copy DB file
        shutil.copy(self.db_path, backup_path)
        
        # Encrypt backup
        with open(backup_path, 'rb') as f:
            data = f.read()
        cipher = Fernet(encryption_key.encode())
        encrypted = cipher.encrypt(data)
        with open(backup_path, 'wb') as f:
            f.write(encrypted)
        
        logger.info(f"Backup created: {backup_path}")
        return str(backup_path)
    
    def cleanup_old_backups(self, days_retention: int = 30):
        """Delete backups older than retention period."""
        cutoff = datetime.now() - timedelta(days=days_retention)
        for backup_file in self.backup_dir.glob("absensi_lokal_*.db.enc"):
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if mtime < cutoff:
                backup_file.unlink()
                logger.info(f"Deleted old backup: {backup_file}")
    
    def restore_backup(self, backup_path: str, encryption_key: str):
        """Restore database from encrypted backup."""
        with open(backup_path, 'rb') as f:
            encrypted = f.read()
        cipher = Fernet(encryption_key.encode())
        decrypted = cipher.decrypt(encrypted)
        with open(self.db_path, 'wb') as f:
            f.write(decrypted)
        logger.info(f"Database restored from: {backup_path}")
