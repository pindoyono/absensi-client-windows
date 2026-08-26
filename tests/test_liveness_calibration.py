"""
Test untuk liveness detection calibration (LIVENESS-001, LIVENESS-002).
"""
import numpy as np
import pytest
from app.face.minifasnet_engine import (
    evaluasi_liveness,
    AMBANG_LIVENESS,
    INDEKS_KELAS_LIVE,
    CALIBRATION_TPR,
    CALIBRATION_FRR,
)


class TestLivenessEvaluation:
    """Test liveness evaluation function (pure function test)."""

    def test_real_face_high_score(self):
        """Test detection of real face with high liveness score."""
        # Simulated output: high score at live index
        output = np.array([[0.1, 0.2, 0.95, 0.1]])  # live score at index 2
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is True
        assert score == pytest.approx(0.95)

    def test_spoofed_face_low_score(self):
        """Test detection of spoofed face with low liveness score."""
        # Simulated output: low score at live index
        output = np.array([[0.9, 0.05, 0.04, 0.01]])  # live score at index 2
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is False
        assert score == pytest.approx(0.04)

    def test_score_at_threshold_boundary(self):
        """Test score exactly at threshold (should be False, not inclusive)."""
        output = np.array([[0.1, 0.2, 0.75, 0.1]])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is False  # boundary, not inclusive
        assert score == pytest.approx(0.75)

    def test_score_just_above_threshold(self):
        """Test score just above threshold."""
        output = np.array([[0.1, 0.2, 0.751, 0.1]])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is True
        assert score == pytest.approx(0.751)

    def test_1d_output_shape(self):
        """Test handling 1D output array."""
        output = np.array([0.1, 0.2, 0.85, 0.1])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is True
        assert score == pytest.approx(0.85)

    def test_nan_values_handled(self):
        """Test handling of NaN values."""
        output = np.array([[0.1, np.nan, 0.85, 0.1]])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert is_real is False  # NaN treated as failed

    def test_inf_values_handled(self):
        """Test handling of Inf values."""
        output = np.array([[0.1, np.inf, 0.85, 0.1]])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        # Inf will be clamped to 1.0
        assert is_real is True

    def test_score_clamped_to_range(self):
        """Test score clamping to [0, 1] range."""
        # Score > 1 should be clamped
        output = np.array([[0.1, 0.2, 1.5, 0.1]])
        is_real, score = evaluasi_liveness(output, ambang=0.75)
        assert score == pytest.approx(1.0)  # clamped
        assert is_real is True

    def test_custom_threshold(self):
        """Test with custom threshold."""
        output = np.array([[0.1, 0.2, 0.6, 0.1]])
        
        # With ambang=0.5, score 0.6 should pass
        is_real, score = evaluasi_liveness(output, ambang=0.5)
        assert is_real is True
        
        # With ambang=0.7, score 0.6 should fail
        is_real, score = evaluasi_liveness(output, ambang=0.7)
        assert is_real is False

    def test_custom_live_index(self):
        """Test with custom live class index."""
        output = np.array([[0.85, 0.1, 0.05, 0.0]])  # live score at index 0
        is_real, score = evaluasi_liveness(output, ambang=0.75, indeks_live=0)
        assert is_real is True
        assert score == pytest.approx(0.85)


class TestCalibrationMetrics:
    """Test that calibration metrics are within expected range."""

    def test_ambang_liveness_in_reasonable_range(self):
        """Test that threshold is in reasonable range [0.5, 0.9]."""
        assert 0.5 <= AMBANG_LIVENESS <= 0.9, \
            f"AMBANG_LIVENESS {AMBANG_LIVENESS} out of reasonable range"

    def test_calibration_tpr_acceptable(self):
        """Test that TPR (true positive rate) is >= 0.98."""
        assert CALIBRATION_TPR >= 0.98, \
            f"CALIBRATION_TPR {CALIBRATION_TPR} should be >= 0.98 (detect 98%+ live faces)"

    def test_calibration_fpr_acceptable(self):
        """Test that FPR (false positive rate) is <= 0.005."""
        assert CALIBRATION_FPR <= 0.005, \
            f"CALIBRATION_FPR {CALIBRATION_FPR} should be <= 0.005 (block 99.5%+ spoofing)"


class TestLivenessLogging:
    """Test liveness check logging."""

    def test_liveness_log_schema(self):
        """Test that liveness_log table has correct schema."""
        from app.database.db import get_connection
        conn = get_connection()
        
        # Check table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='liveness_log'"
        ).fetchall()
        assert len(tables) == 1, "liveness_log table should exist"
        
        # Check columns
        columns = conn.execute("PRAGMA table_info(liveness_log)").fetchall()
        column_names = [col[1] for col in columns]
        
        expected_columns = [
            "log_id",
            "timestamp",
            "frame_id",
            "wajah_terdeteksi",
            "is_real",
            "liveness_score",
            "ambang_saat_itu",
            "alasan_gagal",
            "siswa_id",
            "device_id",
            "created_at",
        ]
        
        for col in expected_columns:
            assert col in column_names, f"Column {col} missing in liveness_log"
        
        conn.close()
