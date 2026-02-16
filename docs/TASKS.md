# Dredge Project Roadmap

## Phase 1: MVP (Completed)
- [x] Local Docker Scanning
- [x] Cost Calculator (Basic)
- [x] FinOps Dashboard (KPI Cards)
- [x] Deep Harbor Theme (PicoCSS)
- [x] HTMX Interactivity

## Phase 2: Core Functionality (Completed)
- [x] Quarantine Mode (Soft-delete)
- [x] Cleanup Policies (Model layer)
- [x] Audit Logs (Database & View)
- [x] Manual Purge (Permanent deletion)
- [x] Local Volume Management (Phase 2.5)

## Phase 3: Multi-Source & Remote Registries (Completed)
- [x] Registry Configuration Models
- [x] Registry Management UI (Add/Remove)
- [x] Registry Abstraction Layer (Factory/Clients)
- [x] Support for Docker Hub, ECR, ACR, GCR, GAR, GHCR
- [x] Unified Image/Volume Views with Source Tracking
- [x] Source-based Filtering

## Phase 4: Polish & Quality of Life (The "Product" Feel)
**Goal:** User configuration, safety mechanisms, and visual feedback.

### 4.1 Global Settings (app/models/settings.py & templates/settings.html)
- [ ] **Settings Model**
  - [ ] Create `class AppSettings(SQLModel)` (Singleton row).
  - [ ] Fields: `provider_name` (str), `custom_price_per_gb` (float), `currency_symbol` (str, default='$').
- [ ] **Settings UI**
  - [ ] Create `templates/settings.html`.
  - [ ] Add Form: "FinOps Configuration" (Select Provider, Input Price).
  - [ ] Add Form: "Danger Zone" (Button: "Flush All Logs", Button: "Reset Database").
  - [ ] **HTMX:** Auto-save on change (`hx-trigger="change"`) or "Save" button.

### 4.2 Policy Manager (templates/policies.html)
- [ ] **Policy UI**
  - [ ] Display current `CleanupPolicy`.
  - [ ] **Rule Editor:** Inputs for `keep_count` (e.g., 5) and `max_age_days` (e.g., 30).
  - [ ] **Whitelist Editor:** Textarea for `regex_whitelist` (one per line).
  - [ ] **Test Box:** Input field to type a tag name and see if it passes/fails the current policy (Client-side regex or HTMX).

### 4.3 Notification System (Frontend)
- [ ] **Toast Implementation**
  - [ ] Add a lightweight toast library (e.g., `Toastify.js`) or custom CSS implementation.
  - [ ] **HTMX Integration:** Listen for `HX-Trigger` response headers (e.g., `{"showMessage": "Scan Complete"}`) to show toasts automatically after backend actions.

### 4.4 Audit & Logs View (templates/logs.html)
- [ ] **Audit Table**
  - [ ] Render `AuditLog` entries: Timestamp, Action (Quarantine/Delete), Image ID, Savings ($).
  - [ ] Add "Export CSV" button.
- [ ] **Visuals:** Use the "Rusted Orange" color for Deletions and "Cyan" for Restores.

### 4.5 Safety Features
- [ ] **"Un-Quarantine" Action**
  - [ ] In `images.html`, add a "Restore" button for items with status `QUARANTINED`.
  - [x] Backend: Route `POST /images/{id}/restore` sets status to `ACTIVE`.

## Phase 5: Enterprise (The "God Mode")
**Goal:** Make Dredge communicative and self-deployable.

### 5.1 Multi-Channel Notifications (The "Omni-Notifier")
- [x] **Dependency:** Add `apprise` to `pyproject.toml`.
- [x] **Settings Model:** Add `notification_urls` (str) to `AppSettings`.
- [x] **Core Service:** Create `app/core/notify.py` with an async `send_notification(title, body)` function.
- [x] **Triggers:**
  - [x] Fire on `SCAN_COMPLETED` (if waste > 0).
  - [x] Fire on `PURGE_COMPLETED` (with total savings $).
- [x] **UI:** Add a "Test Notification" button in the Settings page.

## Phase 6: Reporting (Future Ideas)
### 6.1 Reporting (app/services/report.py)
- [ ] **PDF Generation**
  - [ ] Install `reportlab` or similar.
  - [ ] Generate PDF summarizing `AuditLog` entries for the month.
