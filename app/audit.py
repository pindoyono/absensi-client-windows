"""
Audit logging module untuk OPS-001 requirement.

Track semua actions di device untuk compliance + debugging:
- LOGIN/LOGOUT events
- ENROLLMENT events
- SYNC_START/SYNC_COMPLETE/SYNC_FAIL events
- ATTENDANCE_RECORD events
- CONFIG_CHANGE events
- ERROR events

Semua events di-log ke database (device_audit_log table) dan backup JSON file.
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from app.database.repository import AbsensiRepository

logger = logging.getLogger(__name__)


class AuditLogger:
    """Centralized audit logging untuk device."""
    
    def __init__(self, repo: AbsensiRepository, device_id: str):
        """
        Initialize AuditLogger.
        
        Args:
            repo: Database repository untuk menyimpan audit logs
            device_id: Device ID untuk konteks logging
        """
        self.repo = repo
        self.device_id = device_id
    
    def log_event(
        self,
        event_type: str,
        action: str,
        status: str = "success",
        actor: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log event ke database audit log.
        
        Args:
            event_type: Type of event (LOGIN, LOGOUT, ENROLLMENT, SYNC_START, etc.)
            action: Deskripsi singkat action (e.g., "User logged in via Google OAuth")
            status: 'success' atau 'failed'
            actor: Email atau identifier akun yang melakukan action (None untuk 'system')
            details: Extra details sebagai JSON dict
            error_message: Error message jika status='failed'
        """
        try:
            timestamp = datetime.now().isoformat()
            details_json = json.dumps(details) if details else None
            
            # Insert ke database
            self.repo.conn.execute(
                """INSERT INTO device_audit_log 
                   (timestamp, event_type, actor, action, details, status, error_message, device_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    timestamp,
                    event_type,
                    actor or "system",
                    action,
                    details_json,
                    status,
                    error_message,
                    self.device_id,
                    timestamp,
                ),
            )
            self.repo.conn.commit()
            
            # Also log to Python logger
            level = logging.ERROR if status == "failed" else logging.INFO
            msg = f"[AUDIT] {event_type}: {action} (actor={actor or 'system'}, status={status})"
            if error_message:
                msg += f" | Error: {error_message}"
            logger.log(level, msg)
        
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}", exc_info=True)
    
    def log_login(self, email: str, method: str = "google_oauth") -> None:
        """Log admin/guru piket login."""
        self.log_event(
            event_type="LOGIN",
            action=f"Admin/Guru logged in via {method}",
            actor=email,
            status="success",
            details={"method": method},
        )
    
    def log_logout(self, email: str) -> None:
        """Log admin/guru piket logout."""
        self.log_event(
            event_type="LOGOUT",
            action="Admin/Guru logged out",
            actor=email,
            status="success",
        )
    
    def log_enrollment(self, siswa_id: int, siswa_nama: str, actor: str) -> None:
        """Log student enrollment."""
        self.log_event(
            event_type="ENROLLMENT",
            action=f"Student enrolled: {siswa_nama}",
            actor=actor,
            status="success",
            details={"siswa_id": siswa_id, "siswa_nama": siswa_nama},
        )
    
    def log_attendance_record(
        self, siswa_id: int, siswa_nama: str, type_: str, status_kehadiran: str
    ) -> None:
        """Log attendance record creation."""
        self.log_event(
            event_type="ATTENDANCE_RECORD",
            action=f"{type_} recorded: {siswa_nama} ({status_kehadiran})",
            status="success",
            details={
                "siswa_id": siswa_id,
                "siswa_nama": siswa_nama,
                "type": type_,
                "status_kehadiran": status_kehadiran,
            },
        )
    
    def log_sync_start(self, batch_count: int) -> None:
        """Log sync cycle start."""
        self.log_event(
            event_type="SYNC_START",
            action=f"Sync cycle started with {batch_count} pending records",
            status="success",
            details={"batch_count": batch_count},
        )
    
    def log_sync_complete(self, duration_ms: int, success_count: int, fail_count: int) -> None:
        """Log sync cycle complete."""
        self.log_event(
            event_type="SYNC_COMPLETE",
            action=f"Sync cycle complete: {success_count} synced, {fail_count} failed",
            status="success",
            details={
                "duration_ms": duration_ms,
                "success_count": success_count,
                "fail_count": fail_count,
            },
        )
    
    def log_sync_fail(self, error_message: str) -> None:
        """Log sync cycle failure."""
        self.log_event(
            event_type="SYNC_FAIL",
            action="Sync cycle failed",
            status="failed",
            error_message=error_message,
        )
    
    def log_config_change(self, config_key: str, old_value: str, new_value: str, actor: str) -> None:
        """Log configuration change."""
        self.log_event(
            event_type="CONFIG_CHANGE",
            action=f"Config changed: {config_key}",
            actor=actor,
            status="success",
            details={
                "config_key": config_key,
                "old_value": old_value,
                "new_value": new_value,
            },
        )
    
    def log_error(self, error_type: str, error_message: str) -> None:
        """Log device error."""
        self.log_event(
            event_type="ERROR",
            action=f"Device error: {error_type}",
            status="failed",
            error_message=error_message,
        )
    
    def log_security_event(
        self,
        event_type: str,
        action: str,
        status: str = "success",
        actor: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Log security-related event (REQ-SEC-005).
        
        Event types:
        - AUTH_SUCCESS: Successful authentication
        - AUTH_FAILURE: Failed authentication attempt
        - CERT_PINNING_FAILURE: SSL certificate pinning mismatch
        - RATE_LIMIT_BLOCKED: Request blocked by rate limiter
        - HMAC_VERIFICATION_FAILURE: Server rejected HMAC signature
        - TOKEN_REFRESH: JWT token refresh event
        - TOKEN_EXPIRY: JWT token expired
        """
        self.log_event(
            event_type=event_type,
            action=action,
            status=status,
            actor=actor,
            details=details,
            error_message=error_message,
        )
    
    def log_auth_success(self, actor: str, method: str = "device_api_key") -> None:
        """Log successful authentication."""
        self.log_security_event(
            event_type="AUTH_SUCCESS",
            action=f"Authentication successful via {method}",
            actor=actor,
            details={"method": method},
        )
    
    def log_auth_failure(self, actor: str, reason: str, method: str = "device_api_key") -> None:
        """Log failed authentication attempt."""
        self.log_security_event(
            event_type="AUTH_FAILURE",
            action=f"Authentication failed via {method}",
            status="failed",
            actor=actor,
            error_message=reason,
            details={"method": method},
        )
    
    def log_cert_pinning_failure(self, expected: str, actual: str) -> None:
        """Log SSL certificate pinning failure."""
        self.log_security_event(
            event_type="CERT_PINNING_FAILURE",
            action="SSL certificate pinning verification failed",
            status="failed",
            error_message=f"Expected fingerprint: {expected[:16]}..., Got: {actual[:16]}...",
            details={"expected": expected[:32], "actual": actual[:32]},
        )
    
    def log_rate_limit_blocked(self, endpoint: str) -> None:
        """Log rate limit block."""
        self.log_security_event(
            event_type="RATE_LIMIT_BLOCKED",
            action=f"Request blocked by rate limiter: {endpoint}",
            status="failed",
            details={"endpoint": endpoint},
        )
    
    def log_hmac_failure(self, endpoint: str, reason: str) -> None:
        """Log HMAC signature verification failure."""
        self.log_security_event(
            event_type="HMAC_VERIFICATION_FAILURE",
            action=f"HMAC signature rejected by server: {endpoint}",
            status="failed",
            error_message=reason,
            details={"endpoint": endpoint},
        )
    
    def log_token_refresh(self, actor: str = "system") -> None:
        """Log JWT token refresh."""
        self.log_security_event(
            event_type="TOKEN_REFRESH",
            action="JWT service token refreshed",
            actor=actor,
        )
    
    def log_token_expiry(self, actor: str = "system") -> None:
        """Log JWT token expiry."""
        self.log_security_event(
            event_type="TOKEN_EXPIRY",
            action="JWT service token expired",
            status="failed",
            actor=actor,
        )
    
    def get_recent_logs(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        """Get recent audit logs.
        
        Args:
            event_type: Filter by event type (None = all)
            limit: Max number of logs to return
        
        Returns:
            List of audit log records
        """
        try:
            if event_type:
                rows = self.repo.conn.execute(
                    "SELECT * FROM device_audit_log WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
            else:
                rows = self.repo.conn.execute(
                    "SELECT * FROM device_audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving audit logs: {e}", exc_info=True)
            return []
