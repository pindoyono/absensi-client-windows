"""
Performance metrics collection untuk OPS-005 requirement.

Instrument key performance metrics:
- Embedding matching time
- Sync cycle duration
- Database query time
- Face detection + liveness time

Metrics di-log ke JSON file untuk analysis + monitoring.
"""
import json
import time
import logging
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized performance metrics collection."""
    
    def __init__(self, metrics_file: str = "data/performance_metrics.jsonl"):
        """
        Initialize MetricsCollector.
        
        Args:
            metrics_file: Path ke JSON lines file untuk store metrics
        """
        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
    
    def record_metric(
        self,
        name: str,
        duration_ms: float,
        status: str = "success",
        tags: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a performance metric.
        
        Args:
            name: Metric name (e.g., "embedding_matching", "sync_cycle")
            duration_ms: Duration dalam milliseconds
            status: 'success' atau 'failed'
            tags: Extra tags untuk filtering (e.g., {"siswa_count": 1000})
        """
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "metric": name,
                "duration_ms": duration_ms,
                "status": status,
                "tags": tags or {},
            }
            
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        
        except Exception as e:
            logger.error(f"Failed to record metric {name}: {e}", exc_info=True)
    
    def timing(
        self, name: str, tags: Optional[Dict[str, Any]] = None
    ) -> Callable:
        """
        Decorator to measure function execution time.
        
        Args:
            name: Metric name
            tags: Extra tags untuk konteks
        
        Returns:
            Decorated function that measures execution time
        
        Example:
            @metrics.timing("embedding_matching", tags={"siswa_count": 1000})
            def match_face(...):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.time() - start) * 1000
                    self.record_metric(name, duration_ms, "success", tags)
            
            return wrapper
        
        return decorator
    
    def get_statistics(self, metric_name: str, minutes: int = 60) -> Dict[str, Any]:
        """
        Get statistics for a metric in the last N minutes.
        
        Args:
            metric_name: Name of metric to analyze
            minutes: Time window in minutes
        
        Returns:
            Dict with min, max, avg, median, p95, p99
        """
        try:
            cutoff_time = datetime.fromisoformat(
                (datetime.now() - timedelta(minutes=minutes)).isoformat()
            )
            
            durations = []
            with open(self.metrics_file, "r") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry["metric"] == metric_name:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if ts > cutoff_time:
                            durations.append(entry["duration_ms"])
            
            if not durations:
                return {"count": 0, "message": f"No metrics for {metric_name} in last {minutes} minutes"}
            
            import numpy as np
            
            durations = np.array(durations)
            return {
                "count": len(durations),
                "min_ms": float(np.min(durations)),
                "max_ms": float(np.max(durations)),
                "avg_ms": float(np.mean(durations)),
                "median_ms": float(np.median(durations)),
                "p95_ms": float(np.percentile(durations, 95)),
                "p99_ms": float(np.percentile(durations, 99)),
            }
        
        except Exception as e:
            logger.error(f"Error computing statistics for {metric_name}: {e}", exc_info=True)
            return {"error": str(e)}


# Global metrics instance
_metrics_instance: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
