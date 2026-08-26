"""
Test untuk sync service dengan network failures (QA-003).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.sync.service import SyncService
from app.database.repository import AbsensiRepository
from app.api.client import ApiClient
import requests


class TestSyncNetworkFailures:
    """Test sync behavior under network stress."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        repo = Mock(spec=AbsensiRepository)
        repo.record_belum_sync.return_value = []
        return repo

    @pytest.fixture
    def mock_api(self):
        """Create mock API client."""
        api = Mock(spec=ApiClient)
        api.cek_koneksi.return_value = True
        return api

    def test_sync_with_timeout(self, mock_repo, mock_api):
        """Test sync handling when request times out."""
        mock_api.sync_absensi.side_effect = requests.exceptions.Timeout()
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.sinkron()
        
        # Should handle gracefully, not crash
        assert result is not None
        assert result.online is False

    def test_sync_with_connection_error(self, mock_repo, mock_api):
        """Test sync handling when connection fails."""
        mock_api.sync_absensi.side_effect = requests.exceptions.ConnectionError()
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.sinkron()
        
        assert result.online is False

    def test_sync_with_server_error(self, mock_repo, mock_api):
        """Test sync handling on server 5xx error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_api.sync_absensi.side_effect = requests.exceptions.HTTPError(response=mock_response)
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.sinkron()
        
        assert result.online is False

    def test_partial_sync_success(self, mock_repo, mock_api):
        """Test sync with partial success (some records fail)."""
        mock_api.sync_absensi.return_value = {
            "total": 3,
            "disimpan": 2,
            "duplikat": 0,
            "gagal": 1,
            "hasil": [
                {"record_id": "1", "status": "disimpan"},
                {"record_id": "2", "status": "disimpan"},
                {"record_id": "3", "status": "gagal"},
            ],
        }
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.sinkron()
        
        # Should handle partial success
        assert result.online is True


class TestSyncJadwalFailover:
    """Test sync jadwal fallback when JWT refresh fails."""

    def test_jadwal_fetch_with_expired_jwt(self):
        """Test jadwal fetch when JWT is expired (401)."""
        mock_repo = Mock(spec=AbsensiRepository)
        mock_api = Mock(spec=ApiClient)
        
        # Simulate 401 on jadwal fetch
        mock_response = Mock()
        mock_response.status_code = 401
        mock_api.fetch_jadwal.side_effect = requests.exceptions.HTTPError(response=mock_response)
        
        sync = SyncService(mock_repo, mock_api)
        
        # Should gracefully handle, use cached jadwal
        # (implementation detail: graceful degradation)
        result = sync.sinkron()
        assert result is not None
