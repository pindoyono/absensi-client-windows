"""Tests for REQ-SEC-003 (rate limiting) and REQ-SEC-005 (security audit logging)."""
import time
import pytest
from unittest.mock import MagicMock, patch
from app.api.client import RateLimiter, ApiClient


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=1)
        for _ in range(5):
            assert rl.allow() is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=10)
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False  # 4th should be blocked

    def test_window_resets(self):
        rl = RateLimiter(max_requests=2, window_seconds=1)
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False
        time.sleep(1.1)
        assert rl.allow() is True  # Window reset

    def test_default_limits(self):
        rl = RateLimiter()
        assert rl.max_requests == 60
        assert rl.window_seconds == 60


class TestAuditLoggerSecurityMethods:
    def test_log_security_event(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_security_event(
            event_type="AUTH_FAILURE",
            action="Test auth failure",
            status="failed",
            actor="test_user",
            error_message="Bad credentials",
        )
        mock_repo.conn.execute.assert_called()
        mock_repo.conn.commit.assert_called()

    def test_log_auth_success(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_auth_success("user@example.com", "device_api_key")
        mock_repo.conn.execute.assert_called()

    def test_log_auth_failure(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_auth_failure("attacker", "Invalid API key")
        mock_repo.conn.execute.assert_called()

    def test_log_cert_pinning_failure(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_cert_pinning_failure("AAAAAAA...", "BBBBBBB...")
        mock_repo.conn.execute.assert_called()

    def test_log_rate_limit_blocked(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_rate_limit_blocked("/absensi/sync")
        mock_repo.conn.execute.assert_called()

    def test_log_token_refresh(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_token_refresh()
        mock_repo.conn.execute.assert_called()

    def test_log_token_expiry(self):
        from app.audit import AuditLogger
        mock_repo = MagicMock()
        mock_repo.conn.execute.return_value = MagicMock()
        logger = AuditLogger(mock_repo, "DEVICE-001")
        logger.log_token_expiry()
        mock_repo.conn.execute.assert_called()


class TestApiClientAuditIntegration:
    def test_api_client_has_audit_logger(self):
        client = ApiClient(
            server_url="https://example.com",
            device_id="DEV-001",
            device_api_key="test-key-12345678901234567890123456789012",
        )
        assert client.audit_logger is None  # Default
        mock_al = MagicMock()
        client2 = ApiClient(
            server_url="https://example.com",
            device_id="DEV-001",
            device_api_key="test-key-12345678901234567890123456789012",
            audit_logger=mock_al,
        )
        assert client2.audit_logger is mock_al
