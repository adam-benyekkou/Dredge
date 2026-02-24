# AI Execution Tasks

This document translates the Dredge finalization plan into granular, atomic tasks designed for AI agents. Each task is self-contained with clear objectives, required files, and verification steps.

---

## 🌩️ Phase 1: Robust Cloud Provider Integrations

### Task 1.1: Implement AWS ECR Authentication & Retrieval
**Context:** Dredge needs to reliably connect to AWS Elastic Container Registry to list repositories and images.
**Action:** 
- Add `boto3` to requirements if not present.
- Implement the `AWSRegistryClient` class using IAM credentials (access key, secret key, region).
- Implement pagination for `get_repositories` and `get_images`.
**Verification:** Write a mock test for ECR retrieval. The client must successfully yield a list of `ImageArtifact` objects.

### Task 1.2: Implement AWS ECR Manifest Deletion
**Context:** Dredge needs to delete images from AWS ECR.
**Action:**
- Implement `delete_image` in `AWSRegistryClient`.
- Use the `batch_delete_image` boto3 API.
- Ensure correct handling of image digests vs tags.
**Verification:** The function must correctly format the API payload and return a boolean success status.

### Task 1.3: Implement Google Artifact Registry (GAR) Auth & Retrieval
**Context:** Connect to GCP GAR using Service Account JSON.
**Action:**
- Add `google-auth` and `google-api-python-client` to requirements.
- Implement `GARRegistryClient` parsing the provided JSON credentials.
- Map the GAR API response to Dredge's `ImageArtifact` schema.
**Verification:** The client successfully authenticates and parses GAR JSON responses into internal models.

### Task 1.4: Implement Google Artifact Registry (GAR) Deletion
**Context:** Dredge needs to delete images from GAR.
**Action:**
- Implement `delete_image` in `GARRegistryClient`.
- Use the appropriate Google Cloud API to delete the package/version by digest.
**Verification:** The function must correctly issue a DELETE request to the GAR endpoint.

### Task 1.5: Implement Azure Container Registry (ACR) Auth & Retrieval
**Context:** Connect to Azure ACR.
**Action:**
- Implement `ACRRegistryClient` using Admin user credentials (or Service Principal).
- Handle ACR's specific OAuth2 token exchange flow if using the Docker V2 API directly, or use Azure SDK.
- Implement pagination for the catalog and tags.
**Verification:** The client successfully retrieves a token and lists repositories/tags.

### Task 1.6: Implement Azure Container Registry (ACR) Deletion
**Context:** Dredge needs to delete images from ACR.
**Action:**
- Implement `delete_image` in `ACRRegistryClient`.
- Ensure the deletion targets the manifest digest directly via the Registry API.
**Verification:** The function must issue the correct DELETE request with the necessary authorization headers.

### Task 1.7: Refactor Registry Health Checks
**Context:** A simple network ping is insufficient to verify credentials.
**Action:**
- Modify the background health check task (`ping_registry`).
- Make it perform a lightweight authenticated request (e.g., `GET /v2/_catalog` with limit=1 or equivalent provider API).
- Update the UI status badges to differentiate between "Network Timeout" and "Auth Failed".
**Verification:** A registry with a bad password should immediately fail the health check with an auth error.

---

## 🛡️ Phase 2: Remote Lifecycle Policies & Quarantine

### Task 2.1: Verify Remote Policy Evaluation (Keep Count & Max Age)
**Context:** Policies must correctly evaluate images living on remote registries.
**Action:**
- Review the core policy engine (`app/core/policy.py`).
- Ensure it groups remote images by `(registry_id, repository_name)` before applying `keep_count`.
- Ensure it correctly parses ISO8601 creation dates from remote manifests for `max_age_days`.
**Verification:** A test case where a mock remote repository with 5 images correctly flags 2 for quarantine under a `keep_count=3` rule.

### Task 2.2: Ensure End-to-End Purge Execution
**Context:** When a quarantined image expires or a user clicks "Purge", it must be deleted from the cloud.
**Action:**
- Trace the `purge` route/function.
- Ensure it correctly resolves the `registry_id`, instantiates the correct client (AWS, GAR, etc.), and calls `client.delete_image()`.
- Add robust error handling: If remote deletion fails, the local DB record should NOT be deleted, and an error should be logged/returned.
**Verification:** Attempting to purge an image from a disconnected registry leaves the image in the DB and returns a 500/400 error.

---

## 🔔 Phase 3: Notifications System

### Task 3.1: Integrate Apprise Library
**Context:** Dredge needs a unified way to send messages to Slack, Discord, etc.
**Action:**
- Add `apprise` to `requirements.txt`.
- Create `app/core/notifications.py` wrapping the Apprise library.
- Implement an async `send_notification(title, body)` function.
**Verification:** A simple unit test successfully initializes Apprise and passes validation.

### Task 3.2: Notification Configuration UI
**Context:** Users need a place to input webhook URLs.
**Action:**
- Add an `apprise_urls` text field (or list) to the `AppSettings` database model.
- Update the UI (`Settings > General` or new `Settings > Notifications` tab) to let users save these URLs.
**Verification:** URLs are successfully saved and loaded from the SQLite database.

### Task 3.3: Implement Notification Triggers
**Context:** Alerts should fire on specific events.
**Action:**
- **FinOps:** In `app/core/finops.py`, trigger an alert if the newly calculated monthly cost exceeds the `monthly_budget`.
- **Policies:** At the end of `run_scheduled_policies()`, trigger an alert summarizing the results (e.g., "3 images quarantined").
**Verification:** Running a policy that flags images triggers a call to `send_notification()`.

---

## 🧪 Phase 4: Testing & Final Polish

### Task 4.1: Dry-Run Safety Audit
**Context:** "Dry Run" must be absolutely safe.
**Action:**
- Audit all deletion and quarantine routes.
- Ensure that if a `dry_run=True` flag is passed, NO external API calls that mutate state are fired.
**Verification:** A full text search of the codebase confirms `dry_run` properly short-circuits all `.delete()` or `.purge()` methods.

### Task 4.2: Documentation Sync
**Context:** The docs must match the final implementation.
**Action:**
- Update the Registry Setup docs (`docs/registry/*.md`) with exact instructions on how to generate the required credentials for AWS, GAR, and ACR based on the implementations in Phase 1.
**Verification:** Docs contain clear, step-by-step IAM/Service Account creation guides.
---

## 🎪 Phase 5: Demo Branch Sandbox (DEMO ONLY)

### Task 5.1: Disable Authentication Flow
**Context:** The demo must be instantly accessible without a login wall.
**Action:**
- Remove the `@requires_auth` decorators and JWT validation logic from all routes in `app/web/routes.py`.
- Redirect `/` and `/login` directly to `/dashboard`.
- Remove the "Logout" button from the UI.
**Verification:** Visiting the root URL immediately loads the dashboard.

### Task 5.2: Periodic Database Reset
**Context:** The demo data must stay fresh and prevent permanent clutter from users testing the tool.
**Action:**
- Add a scheduled task (via APScheduler) that runs every 12 hours.
- The task should wipe the SQLite database tables and execute the logic in `scripts/seed_fake_data.py` to restore a clean state.
**Verification:** Manually triggering the reset function cleanly restores the database to the default 50 images and 20 volumes.

### Task 5.3: Sandbox Remote Scanning (Disable Real Docker/API Access)
**Context:** The demo instance must not attempt to connect to the host's Docker socket or real cloud providers.
**Action:**
- Modify the scan endpoint (`/scan-dashboard`, `/scan-registries`) to instantly return without actually invoking `DockerClient` or Remote Registry clients.
- The UI should still show a "Scan complete" toast, but rely entirely on the pre-seeded SQLite data.
**Verification:** Clicking "Scan Now" returns immediately and does not alter the fake DB data or trigger Docker socket errors.

### Task 5.4: Mock Destructive Actions
**Context:** Users should be able to click around without breaking real infrastructure or permanently deleting the fake data (until the 12-hour reset).
**Action:**
- For `Delete`, `Purge`, and `Update Settings` routes: bypass the actual backend logic.
- Instead of deleting records from the DB or calling cloud APIs, simply return an HTMX response with a toast saying "Action simulated in Demo Mode".
- Alternatively, allow local DB deletion (since it resets in 12 hours) but explicitly block the `registry.delete_image()` calls.
**Verification:** Clicking "Delete" on an image shows a success toast but the backend confirms no remote API was called.