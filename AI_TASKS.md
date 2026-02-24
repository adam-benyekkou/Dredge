# AI Execution Tasks

This document translates the Dredge finalization plan into granular, atomic tasks designed for AI agents. Each task is self-contained with clear objectives, required files, and verification steps.

**Legend:** ✅ Done · ⚠️ Partial · ❌ Pending

---

## 🌩️ Phase 1: Robust Cloud Provider Integrations

### Task 1.1 ✅ — Implement AWS ECR Authentication & Retrieval
**Context:** Dredge needs to reliably connect to AWS Elastic Container Registry to list repositories and images.
**Action:**
- [x] Add `boto3` to requirements if not present.
- [x] Implement the `AWSRegistryClient` class using IAM credentials (access key, secret key, region).
- [x] Implement pagination for `get_repositories` and `get_images`.
**Verification:** Write a mock test for ECR retrieval. The client must successfully yield a list of `ImageArtifact` objects.

---

### Task 1.2 ✅ — Implement AWS ECR Manifest Deletion
**Context:** Dredge needs to delete images from AWS ECR.
**Action:**
- [x] Implement `delete_image` in `AWSRegistryClient`.
- [x] Use the `batch_delete_image` boto3 API.
- [x] Ensure correct handling of image digests vs tags.
**Verification:** The function must correctly format the API payload and return a boolean success status.

---

### Task 1.3 ✅ — Implement Google Artifact Registry (GAR) Auth & Retrieval
**Context:** Connect to GCP GAR using Service Account JSON.
**Action:**
- [x] Add `google-auth` and `google-api-python-client` to requirements.
- [x] Implement `GARRegistryClient` parsing the provided JSON credentials.
- [x] Map the GAR API response to Dredge's `ImageArtifact` schema.
**Verification:** The client successfully authenticates and parses GAR JSON responses into internal models.

---

### Task 1.4 ✅ — Implement Google Artifact Registry (GAR) Deletion
**Context:** Dredge needs to delete images from GAR.
**Action:**
- [x] Implement `delete_image` in `GARRegistryClient`.
- [x] Use the appropriate Google Cloud API to delete the package/version by digest (`delete_version`).
**Verification:** The function must correctly issue a DELETE request to the GAR endpoint.

---

### Task 1.5 ✅ — Implement Azure Container Registry (ACR) Auth & Retrieval
**Context:** Connect to Azure ACR.
**Action:**
- [x] Implement `ACRRegistryClient` using Admin user credentials (username + password).
- [x] Handle ACR's OAuth2 token exchange flow (`POST /oauth2/token` with `grant_type=password`); fall back to HTTP Basic auth if token exchange fails.
- [x] Implement pagination via Docker V2 API (`/v2/_catalog`, `/v2/{repo}/tags/list`) with Link-header following.
**Verification:** The client successfully retrieves a token and lists repositories/tags (covered by `tests/test_acr_registry.py`).

---

### Task 1.6 ✅ — Implement Azure Container Registry (ACR) Deletion
**Context:** Dredge needs to delete images from ACR.
**Action:**
- [x] Implement `delete_image` in `ACRRegistryClient`.
- [x] Resolve `repo:tag` to manifest digest via `HEAD /v2/{repo}/manifests/{tag}`.
- [x] Issue `DELETE /v2/{repo}/manifests/{digest}` targeting the digest directly.
- [x] Audit log written on success; DB record preserved on failure.
**Verification:** Tests in `tests/test_acr_registry.py` verify correct HEAD + DELETE call sequence and error handling.

---

### Task 1.7 ✅ — Refactor Registry Health Checks
**Context:** A simple network ping is insufficient to verify credentials.
**Action:**
- [x] Modify the background health check task (`ping_registries` in `app/core/scheduler.py`).
- [x] Make it perform a lightweight **authenticated** request via `client.test_connection()` (each provider implements a real API call: `describe_repositories` for ECR, `GET /v2/` for ACR, etc.).
- [x] Differentiate between `AUTH_ERROR` and `NETWORK_ERROR` in `test_connection()` return values; `ping_registries` auto-disables the registry on `AUTH_ERROR`.
**Verification:** A registry with a bad password immediately fails the health check with an auth error.

---

## 🛡️ Phase 2: Remote Lifecycle Policies & Quarantine

### Task 2.1 ✅ — Verify Remote Policy Evaluation (Keep Count & Max Age)
**Context:** Policies must correctly evaluate images living on remote registries.
**Action:**
- [x] Review the core policy engine (`app/core/policies.py`).
- [x] Ensure it groups remote images by `(source, repository_name)` before applying `keep_count` — implemented as `f"{img.source}|{repo_name}"` key in `_apply_policy`.
- [x] Ensure it correctly parses ISO8601 creation dates from remote manifests for `max_age_days` (timezone-aware datetimes are normalised to naive before comparison).
**Verification:** A test case where a mock remote repository with 5 images correctly flags 2 for quarantine under a `keep_count=3` rule.

---

### Task 2.2 ✅ — Ensure End-to-End Purge Execution
**Context:** When a quarantined image expires or a user clicks "Purge", it must be deleted from the cloud.
**Action:**
- [x] `DELETE /images/{digest}` route exists in `app/web/routes.py` (line 1289) and handles registry client resolution.
- [x] Resolves registry via `image.source`, instantiates the correct client (AWS, GAR, ACR, etc.), and calls `client.delete_image()`.
- [x] Robust error handling: If remote deletion fails, the local DB record is **NOT** deleted, session is rolled back, and error is returned to UI.
**Verification:** Route tested in `tests/test_e2e.py::test_purge_image_endpoint`.

---

## 🔔 Phase 3: Notifications System

### Task 3.1 ✅ — Integrate Apprise Library
**Context:** Dredge needs a unified way to send messages to Slack, Discord, etc.
**Action:**
- [x] Add `apprise` to `requirements.txt` / `pyproject.toml`.
- [x] Create `app/core/notifications.py` (implemented as `app/core/notify.py`) wrapping the Apprise library.
- [x] Implement an async `send_notification(title, body)` function.
**Verification:** A simple unit test successfully initializes Apprise and passes validation.

---

### Task 3.2 ✅ — Notification Configuration UI
**Context:** Users need a place to input webhook URLs.
**Action:**
- [x] Add a `notification_urls` text field to the `AppSettings` database model (`app/models.py` line 227).
- [x] `Settings > Notifications` tab implemented in `templates/partials/settings_notifications.html` with Apprise URLs textarea.
**Verification:** URLs are successfully saved and loaded from the SQLite database.

---

### Task 3.3 ✅ — Implement Notification Triggers
**Context:** Alerts should fire on specific events.
**Action:**
- [x] **FinOps:** In `app/core/finops.py`, `check_budget()` triggers an alert if newly calculated monthly cost exceeds `monthly_budget`.
- [x] **Policies:** At the end of `run_all()` in `PolicyEnforcer`, a notification is triggered summarising quarantined image count.
- [x] **Bug fixed:** `run_all()` now uses `asyncio.run()` with a `RuntimeError` fallback to `loop.create_task()` for when an event loop is already running.
**Verification:** Running a policy that flags images triggers a call to `send_notification()`.

---

## 🧪 Phase 4: Testing & Final Polish

### Task 4.1 ✅ — Dry-Run Safety Audit
**Context:** "Dry Run" must be absolutely safe.
**Action:**
- [x] Audit all deletion and quarantine routes.
- [x] All `delete_image` implementations across `LocalDockerClient`, `DockerRegistryClient`, `AWSRegistryClient`, `GARRegistryClient`, and `ACRRegistryClient` check `if dry_run: return ...` before any external API calls.
**Verification:** A full text search of the codebase confirms `dry_run` properly short-circuits all `.delete()` or `.purge()` methods.

---

### Task 4.2 ✅ — Documentation Sync
**Context:** The docs must match the final implementation.
**Action:**
- [x] Update the Registry Setup docs (`docs/registry/*.md`) with exact instructions on how to generate the required credentials for AWS, GAR, and ACR.
- [x] Files present: `docs/registry/aws-ecr.md`, `docs/registry/azure-acr.md`, `docs/registry/gcp-gar.md`, `docs/registry/ghcr.md`, `docs/registry/docker-hub.md`, `docs/registry/custom.md`, `docs/registry/overview.md`.
**Verification:** Docs contain clear, step-by-step IAM/Service Account creation guides.

---

## 🎪 Phase 5: Demo Branch Sandbox (DEMO ONLY)

> ⚠️ These tasks are intended for a **separate `demo` branch** only. Do **not** implement on `main`.

### Task 5.1 ✅ — Disable Authentication Flow
**Context:** The demo must be instantly accessible without a login wall.
**Action:**
- [x] `GET /auth/login` and `POST /auth/login` both redirect directly to `/` (no login wall).
- [x] `POST /api/v1/auth/login` returns a mock `demo_token` for API clients.
- [x] JWT middleware bypassed — no `@requires_auth` guards active on the demo branch.
**Verification:** `tests/test_demo_mode.py::test_demo_no_login` — GET `/auth/login` returns 302 to `/`.

---

### Task 5.2 ✅ — Periodic Database Reset
**Context:** The demo data must stay fresh and prevent permanent clutter from users testing the tool.
**Action:**
- [x] `run_demo_db_reset()` added to `app/core/scheduler.py`.
- [x] Scheduled via APScheduler cron `0 */12 * * *` (every 12 hours UTC).
- [x] Calls `scripts/seed_fake_data.main()` to restore clean state.
**Verification:** Scheduler registers `demo_db_reset` job on startup when `seed_db_main` is importable.

---

### Task 5.3 ✅ — Sandbox Remote Scanning (Disable Real Docker/API Access)
**Context:** The demo instance must not attempt to connect to the host’s Docker socket or real cloud providers.
**Action:**
- [x] `POST /scan` returns immediately with `"Scan complete (Demo Mode)"` toast — no Docker/registry calls.
- [x] `POST /scan-dashboard` bypasses live scans and reads directly from seeded SQLite data.
**Verification:** `tests/test_demo_mode.py::test_demo_scan_mocked` — `/scan` returns `"Scan complete (Demo Mode)"` in `HX-Trigger`.

---

### Task 5.4 ✅ — Mock Destructive Actions
**Context:** Users should be able to click around without breaking real infrastructure.
**Action:**
- [x] `DELETE /volumes/{name}` — returns `"Action simulated in Demo Mode: Volume purged"` toast.
- [x] `DELETE /volumes/batch` — returns `"Action simulated in Demo Mode: Purged N volumes"`.
- [x] `DELETE /images/{digest}` — returns `"Action simulated in Demo Mode: Image purged"` toast.
- [x] `DELETE /images/batch` — returns `"Action simulated in Demo Mode: Deletion ... started"`.
- [x] `DELETE /registries/{reg_id}` — suppresses delete, returns demo toast.
- [x] `POST /settings` — bypasses save, returns `"Action simulated in Demo Mode: Settings Saved"`.
- [x] `POST /registries/test` — returns `"Connection successful (Demo Mode)"` without real network call.
**Verification:** `tests/test_demo_mode.py::test_demo_destructive_action_mocked` and `test_demo_settings_mocked`.
