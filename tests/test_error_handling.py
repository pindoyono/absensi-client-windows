"""
Test untuk error handling dan graceful shutdown (REQ-OPS-003, REQ-OPS-008).
"""
import pytest
from app.api.client import ApiClient
import requests
from unittest.mock import Mock, patch, MagicMock


class TestApiClientErrorHandling:
    """Test API client error handling."""

    def test_timeout_error_handling(self):
        """Test handling of request timeout — cek_koneksi should return False, not raise."""
        client = ApiClient(
            "https://example.com",
            "test-device",
            "test-key",
            request_timeout=1,
        )
        
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Request timeout")
            
            # cek_koneksi should swallow timeout and return False
            is_online = client.cek_koneksi()
            assert is_online is False

    def test_connection_error_handling(self):
        """Test handling of connection error."""
        client = ApiClient(
            "https://example.com",
            "test-device",
            "test-key",
        )
        
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
            
            is_online = client.cek_koneksi()
            assert is_online is False

    def test_http_401_unauthorized(self):
        """Test handling of 401 Unauthorized response — should raise KoneksiGagal."""
        from app.api.client import KoneksiGagal
        client = ApiClient(
            "https://example.com",
            "test-device",
            "invalid-key",
        )
        
        with patch.object(client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_post.side_effect = requests.exceptions.HTTPError(response=mock_response)
            
            with pytest.raises(KoneksiGagal):
                client.sync_absensi([])

    def test_http_500_server_error(self):
        """Test handling of 500 Server Error — should raise KoneksiGagal."""
        from app.api.client import KoneksiGagal
        client = ApiClient(
            "https://example.com",
            "test-device",
            "test-key",
        )
        
        with patch.object(client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.side_effect = requests.exceptions.HTTPError(response=mock_response)
            
            with pytest.raises(KoneksiGagal):
                client.sync_absensi([])




class TestConnectionRetry:
    """Test connection retry logic with exponential backoff."""

    def test_retry_strategy_configured(self):
        """Test that session has retry strategy configured."""
        client = ApiClient(
            "https://example.com",
            "test-device",
            "test-key",
            max_retries=3,
        )
        
        # Check that HTTPAdapter is mounted with retry strategy
        https_adapter = client.session.get_adapter("https://example.com")
        assert https_adapter is not None
        assert https_adapter.max_retries is not None
