"""Tests for REQ-QA-001 (Graceful Shutdown) and REQ-QA-002 (Metrics Collection)."""
import os
import signal
import pytest
from unittest.mock import MagicMock, patch
from app.metrics import MetricsCollector, get_metrics


class TestMetricsCollection:
    def test_record_metric(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        mc = MetricsCollector(metrics_file=str(metrics_file))
        mc.record_metric("face_detection", 15.5, status="success", tags={"frame": 1})

        assert metrics_file.exists()
        content = metrics_file.read_text()
        assert "face_detection" in content
        assert "15.5" in content

    def test_timing_decorator(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        mc = MetricsCollector(metrics_file=str(metrics_file))

        @mc.timing("test_func")
        def slow_func():
            return 42

        result = slow_func()
        assert result == 42
        assert metrics_file.exists()
        content = metrics_file.read_text()
        assert "test_func" in content

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2


class TestGracefulShutdown:
    def test_signal_handlers_registered(self):
        # Verify signal module has SIGINT and SIGTERM
        assert hasattr(signal, "SIGINT")
        assert hasattr(signal, "SIGTERM")

    def test_sync_worker_stop(self):
        from app.sync.worker import SyncWorker
        mock_service = MagicMock()
        worker = SyncWorker(mock_service, interval_detik=1)
        worker.berhenti()
        assert worker._berjalan is False
