# Introduction

**Dredge** is a FinOps and lifecycle management tool for Docker images. It brings clarity to the often opaque costs of container storage and helps DevOps teams keep their registries clean.

## The Problem

Container registries are "write-only" by default. CI/CD pipelines push gigabytes of data daily—feature branches, nightly builds, and old releases—which accumulate indefinitely. Cloud providers charge for this storage (e.g., AWS ECR costs $0.10/GB/month), leading to "silent bill creep."

## The Solution

Dredge provides:
1.  **Visibility**: A unified dashboard showing exactly what images exist across all your registries and how much they cost.
2.  **Analysis**: Automated identification of "waste" (untagged images, old development builds).
3.  **Action**: Tools to safely clean up artifacts, including a "Quarantine" mode (soft delete) and automated policies.

## Key Features

*   **Multi-Registry Support**: Manage AWS ECR, Azure ACR, Google GAR, Docker Hub, and more from one place.
*   **Cost Estimation**: Real-time calculation of monthly storage costs.
*   **Safe Cleanup**: "Quarantine" first, delete later. Set policies like "Keep last 5 images" or "Delete images older than 30 days."
*   **Nautical Theme**: Because managing containers should at least look cool.
