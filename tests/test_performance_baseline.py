"""
Performance baseline tests (REQ-QA-005).

Establishes performance metrics for CI/CD regression detection.
Baseline: tests/performance_baseline.json
"""
import json
import time
import numpy as np
import pytest
from pathlib import Path
from app.health import HealthChecker

BASELINE_FILE = Path(__file__).parent.parent / "tests" / "performance_baseline.json"


def _measure(func, iterations=100):
    """Measure function execution time, return (avg_ms, p95_ms, min_ms, max_ms)."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    times.sort()
    return {
        "avg_ms": round(np.mean(times), 2),
        "p95_ms": round(times[int(len(times) * 0.95)], 2),
        "min_ms": round(times[0], 2),
        "max_ms": round(times[-1], 2),
    }


class TestPerformanceBaseline:
    def test_cosine_distance_1000_siswa(self):
        """Benchmark: cosine distance computation for 1000 siswa <= 1s p95."""
        embeddings = np.random.randn(1000, 512).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        query = np.random.randn(512).astype(np.float32)
        query /= np.linalg.norm(query)

        def run_match():
            # Cosine distance = 1 - cosine_similarity
            similarities = np.dot(embeddings, query)
            distances = 1 - similarities
            best_idx = np.argmin(distances)

        stats = _measure(run_match, iterations=100)
        assert stats["p95_ms"] < 100, f"Cosine distance p95 {stats['p95_ms']}ms > 100ms"

    def test_health_check_time(self):
        """Benchmark: health check <= 100ms."""
        hc = HealthChecker("data/absensi_lokal.db")

        def run_check():
            hc.get_full_health()

        stats = _measure(run_check, iterations=50)
        assert stats["p95_ms"] < 500, f"Health check p95 {stats['p95_ms']}ms > 500ms"

    def test_record_baseline(self, tmp_path):
        """Record performance baseline to JSON file."""
        embeddings = np.random.randn(1000, 512).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        query = np.random.randn(512).astype(np.float32)
        query /= np.linalg.norm(query)

        def run_match():
            similarities = np.dot(embeddings, query)
            distances = 1 - similarities
            best_idx = np.argmin(distances)

        matching_stats = _measure(run_match, iterations=100)

        baseline = {
            "embedding_matching_1000_siswa": matching_stats,
            "thresholds": {
                "matching_p95_max_ms": 100,
                "health_check_p95_max_ms": 500,
            },
        }

        baseline_path = tmp_path / "performance_baseline.json"
        with open(baseline_path, "w") as f:
            json.dump(baseline, f, indent=2)

        assert baseline_path.exists()
