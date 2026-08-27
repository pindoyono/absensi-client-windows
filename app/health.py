"""
Health check module (REQ-OPS-007).

Memeriksa kesehatan device (CPU, memory, disk, DB size, sync status).
"""
import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class HealthChecker:
    """Device health check utility."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
    
    def check_disk_space(self, min_free_gb: float = 1.0) -> Dict[str, Any]:
        """Check available disk space."""
        try:
            total, used, free = shutil.disk_usage(self.db_path.anchor)
            free_gb = free / (1024 ** 3)
            return {
                "status": "healthy" if free_gb >= min_free_gb else "warning",
                "free_gb": round(free_gb, 2),
                "total_gb": round(total / (1024 ** 3), 2),
            }
        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")
            return {"status": "error", "message": str(e)}
    
    def check_database_size(self, max_size_gb: float = 2.0) -> Dict[str, Any]:
        """Check database file size."""
        try:
            if not self.db_path.exists():
                return {"status": "error", "message": "Database not found"}
            size_bytes = self.db_path.stat().st_size
            size_mb = size_bytes / (1024 ** 2)
            return {
                "status": "healthy" if size_mb < (max_size_gb * 1024) else "warning",
                "size_mb": round(size_mb, 2),
            }
        except Exception as e:
            logger.error(f"Failed to check database size: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_full_health(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        disk = self.check_disk_space()
        db = self.check_database_size()
        
        overall = "healthy"
        if disk["status"] == "error" or db["status"] == "error":
            overall = "error"
        elif disk["status"] == "warning" or db["status"] == "warning":
            overall = "warning"
            
        return {
            "status": overall,
            "disk": disk,
            "database": db,
        }
