# Introduction

**Dredge** is a FinOps and lifecycle management tool for Docker images. It brings clarity to the often opaque costs of container storage and helps DevOps teams keep their registries clean.

## The Problem

Container registries are "write-only" by default. CI/CD pipelines push gigabytes of data daily—feature branches, nightly builds, and old releases—which accumulate indefinitely. Cloud providers charge for this storage (e.g., AWS ECR costs $0.10/GB/month), leading to "silent bill creep."

## The Solution

Dredge provides:
1.  **Visibility**: A unified dashboard showing exactly what images exist across all your registries and how much they cost.
2.  **Analysis**: Automated identification of "waste" (untagged images, old development builds).
3.  **Action**: Tools to safely clean up artifacts, including a preview-before-action policy system with a dedicated quarantine management interface.

## Detailed Features

- **Cost Visibility** - Real-time calculation of monthly storage costs with provider-specific pricing (Docker Hub, GHCR, etc.)
- **Multi-Registry Support** - Real API integration for scanning and deleting images from Local Docker, Docker Hub, and GHCR.
- **FinOps Dashboard** - Track waste, efficiency scores, and reclaimable space with lazy-loaded, high-performance views.
- **Cost Trends** - Visualize spending patterns with interactive line charts anchored to real costs.
- **Bloat Detection** - Automatically identify oversized images and unoptimized base layers.
- **Smart Alerts** - Receive notifications via Slack/Discord when monthly budget thresholds are exceeded.
- **Mass Cleanup** - Batch delete images across multiple registries with asynchronous background processing.
- **Lifecycle Policies** - Automated quarantine logic based on image age and count per repository.
- **Quarantine Management** - Dedicated interface for reviewing, restoring, or purging quarantined images.
- **Health Monitoring** - Automated registry health checks with proactive 5-minute pings.
- **Deep Harbor UI** - Beautiful dark nautical theme with real-time HTMX-powered interactions.

## Tech Stack

Dredge is built for performance and simplicity:

- **Backend:** Python 3.11 • FastAPI • SQLModel • Docker SDK
- **Frontend:** HTMX • Jinja2 • Custom CSS (Deep Harbor theme)
- **Infrastructure:** Docker • Docker Compose • SQLite
- **Auth:** JWT (python-jose) • PBKDF2-SHA256 hashing
