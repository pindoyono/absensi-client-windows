"""
Test untuk embedding matching calibration (EMBEDDING-001, EMBEDDING-002, EMBEDDING-003).
"""
import numpy as np
import pytest
from app.face.matcher import (
    AMBANG_BATAS_JARAK,
    CALIBRATION_FAR,
    CALIBRATION_FRR,
    _validate_embedding,
    HasilMatching,
)


class TestEmbeddingValidation:
    """Test embedding validation function."""

    def test_valid_normalized_embedding(self):
        """Test valid normalized embedding (L2 norm ~1.0)."""
        embedding = np.random.randn(512).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)  # L2 normalize
        assert _validate_embedding(embedding) is True

    def test_none_embedding(self):
        """Test None embedding is rejected."""
        assert _validate_embedding(None) is False

    def test_wrong_size_embedding(self):
        """Test embedding with wrong size is rejected."""
        embedding = np.random.randn(256).astype(np.float32)  # Should be 512
        assert _validate_embedding(embedding) is False

    def test_denormalized_embedding(self):
        """Test denormalized embedding is rejected."""
        embedding = np.random.randn(512).astype(np.float32)  # Not normalized
        assert _validate_embedding(embedding) is False

    def test_embedding_with_nan(self):
        """Test embedding with NaN is rejected."""
        embedding = np.random.randn(512).astype(np.float32)
        embedding[0] = np.nan
        assert _validate_embedding(embedding) is False

    def test_embedding_with_inf(self):
        """Test embedding with Inf is rejected."""
        embedding = np.random.randn(512).astype(np.float32)
        embedding[0] = np.inf
        assert _validate_embedding(embedding) is False

    def test_non_ndarray_embedding(self):
        """Test non-ndarray embedding is rejected."""
        embedding = [0.1, 0.2, 0.3]  # List, not ndarray
        assert _validate_embedding(embedding) is False


class TestMatchingResult:
    """Test matching result data structure."""

    def test_match_found(self):
        """Test result when match is found."""
        result = HasilMatching(
            ditemukan=True,
            siswa_id=1,
            nama="Ahmad Fauzan",
            kelas="XI Elektronika",
            jarak=0.25,
        )
        assert result.ditemukan is True
        assert result.siswa_id == 1
        assert result.nama == "Ahmad Fauzan"
        assert result.jarak == pytest.approx(0.25)

    def test_no_match_found(self):
        """Test result when no match is found."""
        result = HasilMatching(
            ditemukan=False,
            siswa_id=None,
            jarak=0.8,  # High distance, no match
        )
        assert result.ditemukan is False
        assert result.siswa_id is None


class TestCalibrationMetrics:
    """Test calibration metrics are within expected range."""

    def test_ambang_batas_jarak_in_range(self):
        """Test threshold is in reasonable range [0.25, 0.5]."""
        assert 0.25 <= AMBANG_BATAS_JARAK <= 0.5, \
            f"AMBANG_BATAS_JARAK {AMBANG_BATAS_JARAK} out of reasonable range"

    def test_calibration_far_acceptable(self):
        """Test FAR (false accept rate) is <= 0.01 (1%)."""
        assert CALIBRATION_FAR <= 0.01, \
            f"CALIBRATION_FAR {CALIBRATION_FAR} should be <= 0.01 (accept only 1% false positives)"

    def test_calibration_frr_acceptable(self):
        """Test FRR (false reject rate) is <= 0.03 (3%)."""
        assert CALIBRATION_FRR <= 0.03, \
            f"CALIBRATION_FRR {CALIBRATION_FRR} should be <= 0.03 (reject max 3% valid matches)"


class TestEmbeddingDistanceMetrics:
    """Test embedding distance calculation metrics."""

    def test_calibration_dataset_size_sufficient(self):
        """Test that calibration used sufficient dataset."""
        from app.face.matcher import CALIBRATION_DATASET_SIZE, CALIBRATION_SAMPLES_PER_STUDENT
        assert CALIBRATION_DATASET_SIZE >= 20, \
            f"Calibration dataset {CALIBRATION_DATASET_SIZE} should have >= 20 students"
        assert CALIBRATION_SAMPLES_PER_STUDENT >= 3, \
            f"Samples per student {CALIBRATION_SAMPLES_PER_STUDENT} should be >= 3"
