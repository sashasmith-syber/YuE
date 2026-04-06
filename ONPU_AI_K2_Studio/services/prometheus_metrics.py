"""
Prometheus metrics exposure for monitoring.
Optional; enabled via K2_PROMETHEUS_ENABLED.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.config import get_config

logger = logging.getLogger(__name__)

_metrics_registry: Optional[object] = None


def get_metrics_registry():
    """Return Prometheus registry if enabled; else None."""
    global _metrics_registry
    if not get_config().PROMETHEUS_ENABLED:
        return None
    if _metrics_registry is None:
        try:
            from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge
            _metrics_registry = CollectorRegistry()
            _metrics_registry.request_count = Counter(
                "k2_requests_total", "Total generation requests", ["engine"],
                registry=_metrics_registry,
            )
            _metrics_registry.request_latency = Histogram(
                "k2_request_duration_seconds", "Request duration", ["engine"],
                registry=_metrics_registry,
            )
            # Prompt 004 queue metrics
            _metrics_registry.jobs_submitted_total = Counter(
                "jobs_submitted_total", "Total jobs submitted", ["engine"], registry=_metrics_registry,
            )
            _metrics_registry.jobs_completed_total = Counter(
                "jobs_completed_total", "Total jobs completed", ["engine", "status"], registry=_metrics_registry,
            )
            _metrics_registry.jobs_cancelled_total = Counter(
                "jobs_cancelled_total", "Total jobs cancelled", ["engine"], registry=_metrics_registry,
            )
            _metrics_registry.queue_depth = Gauge(
                "queue_depth", "Current queue depth", ["engine", "status"], registry=_metrics_registry,
            )
            _metrics_registry.job_duration_seconds = Histogram(
                "job_duration_seconds", "Job duration", ["engine"],
                buckets=[10, 30, 60, 120, 300, 600], registry=_metrics_registry,
            )
            _metrics_registry.time_in_queue_seconds = Histogram(
                "time_in_queue_seconds", "Time job spent in queue", ["engine"],
                buckets=[1, 5, 10, 30, 60, 300], registry=_metrics_registry,
            )
        except ImportError:
            logger.warning("prometheus_client not installed; metrics disabled")
            _metrics_registry = False
    return _metrics_registry if _metrics_registry is not False else None
