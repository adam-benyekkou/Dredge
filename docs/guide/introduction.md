# Introduction

**Dredge** is a FinOps and lifecycle management tool for Docker images. It brings clarity to the often opaque costs of container storage and helps DevOps teams keep their registries clean.

## The Problem

Container registries are "write-only" by default. CI/CD pipelines push gigabytes of data daily—feature branches, nightly builds, and old releases—which accumulate indefinitely. Cloud providers charge for this storage (e.g., AWS ECR costs $0.10/GB/month), leading to "silent bill creep."

## The Solution

Dredge provides:
1.  **Visibility**: A unified dashboard showing exactly what images exist across all your registries and how much they cost.
2.  **Analysis**: Automated identification of "waste" (untagged images, old development builds).
3.  **Action**: Tools to safely clean up artifacts, including a preview-before-action policy system with a dedicated quarantine management interface.

## Key Features

*   **Multi-Registry Support**: Manage AWS ECR, Azure ACR, Google GAR, Docker Hub, GHCR, and more from one place.
*   **Cost Estimation**: Real-time calculation of monthly storage costs.
*   **Safe Cleanup**: Preview policies before execution, quarantine images with 24-hour grace period, and manage quarantined images with bulk operations.
*   **Quarantine Management**: Dedicated page for reviewing, restoring, or purging quarantined images with checkbox-based bulk actions.
*   **Nautical Theme**: Because managing containers should at least look cool.

