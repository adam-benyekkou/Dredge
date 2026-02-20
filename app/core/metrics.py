from prometheus_client import Counter, Histogram, Gauge

# SRE Metrics
DREDGE_SPACE_FREED_BYTES = Counter(
    "dredge_space_freed_bytes_total",
    "Total space freed by Dredge in bytes",
    ["source", "action"]
)

DREDGE_REGISTRY_LATENCY = Histogram(
    "dredge_registry_latency_seconds",
    "Latency of registry API calls",
    ["registry", "operation"]
)

DREDGE_ACTIVE_IMAGES = Gauge(
    "dredge_active_images_count",
    "Number of active images detected during last scan",
    ["source"]
)

DREDGE_BUDGET_USAGE_PERCENT = Gauge(
    "dredge_budget_usage_percent",
    "Current budget usage percentage",
    ["currency"]
)
