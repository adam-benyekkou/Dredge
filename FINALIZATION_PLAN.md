# Dredge Finalization Plan

This document outlines the final milestones required to bring Dredge to completion, ensuring robust integration with major cloud providers, reliable lifecycle policies, and functional notifications.

## Phase 1: Robust Cloud Provider Integrations
**Goal:** Ensure Dredge can authentically connect, retrieve, and delete images across all major container registries.

- [ ] **AWS Elastic Container Registry (ECR)**
  - Implement/verify `boto3` or REST API authentication using IAM credentials.
  - Implement pagination for retrieving repositories and images.
  - Implement manifest deletion API calls.
- [ ] **Google Artifact Registry (GAR)**
  - Implement/verify authentication using Service Account JSON (`google-auth`).
  - Map GAR's API structure to Dredge's internal models.
  - Implement manifest deletion API calls.
- [ ] **Azure Container Registry (ACR)**
  - Implement/verify authentication using Service Principal or Admin user credentials.
  - Implement pagination for retrieving repositories and tags.
  - Implement manifest deletion API calls.
- [ ] **Docker Hub & GHCR**
  - Verify existing PAT (Personal Access Token) authentication.
  - Ensure rate limits are respected.
- [ ] **Registry Status & Health Checks**
  - Upgrade the current ping mechanism. The status check must perform a real, lightweight authenticated API call (e.g., `GET /v2/_catalog`) to guarantee credentials are valid.
  - Update UI to clearly reflect authentication failures vs. network timeouts.

## Phase 2: Remote Lifecycle Policies & Quarantine
**Goal:** Guarantee that retention policies are accurately applied to remote registries and that destructive actions succeed.

- [ ] **Remote Policy Evaluation**
  - Ensure the policy engine correctly groups remote images by repository.
  - Verify that `keep_count` and `max_age_days` rules accurately parse remote creation dates and tags.
- [ ] **Quarantine Workflow Validation**
  - Verify that matching remote images are correctly marked as `QUARANTINED` in the local SQLite database.
  - Ensure the 24-hour expiration timer tracks correctly.
- [ ] **End-to-End Deletion Execution**
  - Link the "Purge" (from Quarantine) and "Delete" (from Images page) actions to the actual provider-specific deletion APIs.
  - Handle multi-architecture manifest deletions safely (e.g., deleting a tag vs. deleting a manifest digest).
  - Implement rollback or error logging if the remote deletion fails but the local DB record was altered.

## Phase 3: Notifications System
**Goal:** Deliver reliable alerts to users via Slack, Discord, and other channels using Apprise.

- [ ] **Apprise Integration**
  - Add `apprise` to project dependencies.
  - Create a centralized notification service/manager in the backend.
- [ ] **Configuration UI**
  - Allow users to input Apprise-compatible URLs (e.g., `slack://...`, `discord://...`) in the Settings panel.
- [ ] **Notification Triggers**
  - **FinOps Alerts:** Trigger when the monthly cost exceeds the configured budget threshold.
  - **Policy Summaries:** Trigger a summary alert when an automated policy run finishes (e.g., "5 images quarantined").
  - **System Errors:** (Optional) Alert if a registry connection consistently fails.
- [ ] **Async Delivery**
  - Ensure notifications are sent via background tasks to prevent blocking API responses or UI interactions.

## Phase 4: Testing & Final Polish
**Goal:** Validate all critical paths before the v1.0 release.

- [ ] **Integration Testing:** Write tests that mock cloud provider APIs to ensure deletion logic works without incurring cloud costs.
- [ ] **Dry-Run Validation:** Ensure that running policies in "Dry Run" mode strictly prevents any remote API deletion calls.
- [ ] **Documentation Sync:** Final review of the documentation to ensure all registry configuration steps (IAM, Service Accounts) are accurately detailed.
