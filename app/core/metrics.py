try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock classes to prevent crashes when library is missing
    class MockMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
    Counter = Histogram = Gauge = MockMetric

# SRE Metrics
DREDGE_SPACE_FREED_BYTES = Counter(
    "dredge_space_freed_bytes_total",
    "Total space freed by Dredge in bytes",
    labelnames=["source", "action"]
)

DREDGE_REGISTRY_LATENCY = Histogram(
    "dredge_registry_latency_seconds",
    "Latency of registry API calls",
    labelnames=["registry", "operation"]
)

DREDGE_ACTIVE_IMAGES = Gauge(
    "dredge_active_images_count",
    "Number of active images detected during last scan",
    labelnames=["source"]
)

DREDGE_BUDGET_USAGE_PERCENT = Gauge(
    "dredge_budget_usage_percent",
    "Current budget usage percentage",
    labelnames=["currency"]
)
