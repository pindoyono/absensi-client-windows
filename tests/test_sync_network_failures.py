"""
Test untuk sync service dengan network failures (QA-003).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.sync.service import SyncService
from app.database.repository import AbsensiRepository
from app.api.client import ApiClient, HasilSyncItem
import requests


class TestSyncNetworkFailures:
    """Test sync behavior under network stress."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        repo = Mock(spec=AbsensiRepository)
        repo.record_belum_sync.return_value = [{"record_id": "test-1", "siswa_id": 1, "tanggal": "2026-08-24", "type": "MASUK", "jam_aktual": "07:00:00", "status_kehadiran_otomatis": "NORMAL", "catatan": None, "device_id": "dev1", "synced": False, "sync_status": None}]
        repo.daftar_kelas.return_value = ["XI Elektronika"]
        return repo

    @pytest.fixture
    def mock_api(self):
        """Create mock API client."""
        api = Mock(spec=ApiClient)
        api.cek_koneksi.return_value = True
        api.tarik_embedding.return_value = {"jumlah": 0, "data": [], "server_time": "2026-08-24T00:00:00"}
        api.tarik_jadwal_efektif.return_value = {}
        api.tarik_dispensasi_hari_ini.return_value = []
        return api

    def test_sync_with_timeout(self, mock_repo, mock_api):
        """Test sync handling when request times out."""
        mock_api.sync_absensi.side_effect = requests.exceptions.Timeout()
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.siklus_sync()
        
        # Should handle gracefully, not crash
        assert result is not None
        assert result.online is True  # connectivity check passed
        assert result.pesan_error is not None  # but push failed

    def test_sync_with_connection_error(self, mock_repo, mock_api):
        """Test sync handling when connection fails."""
        mock_api.sync_absensi.side_effect = requests.exceptions.ConnectionError()
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.siklus_sync()
        
        assert result.online is True  # connectivity check passed
        assert result.pesan_error is not None  # but push failed

    def test_sync_with_server_error(self, mock_repo, mock_api):
        """Test sync handling on server 5xx error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_api.sync_absensi.side_effect = requests.exceptions.HTTPError(response=mock_response)
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.siklus_sync()
        
        assert result.online is True  # connectivity check passed
        assert result.pesan_error is not None  # but push failed

    def test_partial_sync_success(self, mock_repo, mock_api):
        """Test sync with partial success (some records fail)."""
        mock_api.sync_absensi.return_value = [
            HasilSyncItem(record_id="1", status="disimpan"),
            HasilSyncItem(record_id="2", status="disimpan"),
            HasilSyncItem(record_id="3", status="gagal"),
        ]
        
        sync = SyncService(mock_repo, mock_api)
        result = sync.siklus_sync()
        
        # Should handle partial success
        assert result.online is True
        assert result.disimpan == 2
        assert result.gagal == 1


class TestSyncJadwalFailover:
    """Test sync jadwal fallback when server unreachable."""

    def test_jadwal_fetch_with_server_error(self):
        """Test jadwal fetch when server returns error."""
        mock_repo = Mock(spec=AbsensiRepository)
        mock_repo.record_belum_sync.return_value = []
        mock_repo.daftar_kelas.return_value = ["XI Elektronika"]
        mock_api = Mock(spec=ApiClient)
        mock_api.cek_koneksi.return_value = True
        mock_api.tarik_embedding.return_value = {"jumlah": 0, "data": [], "server_time": "2026-08-24T00:00:00"}
        mock_api.tarik_dispensasi_hari_ini.return_value = []
        
        # Simulate connection error on jadwal fetch
        mock_api.tarik_jadwal_efektif.side_effect = requests.exceptions.ConnectionError()
        
        sync = SyncService(mock_repo, mock_api)
        
        # Should gracefully handle, use cached jadwal
        result = sync.siklus_sync()
        assert result is not None
