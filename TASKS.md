# Dredge FinOps & Bloat Optimization Tasks

## Phase 1: Notification & Budget Foundation (Quick Wins)

### Task 1.1: Notification Testing System
**Priority**: High (UX Blocker)
**Goal**: Allow users to verify Apprise configuration immediately.
- [ ] Add `POST /api/settings/test-notification` endpoint in `routes_settings.py`
- [ ] Implement `send_test_notification()` in `notify.py`
- [ ] Add "Test Connection" button to Settings page next to notification URL input
- [ ] Add frontend feedback (Toast: "Test sent!" or "Error: ...")

### Task 1.2: Monthly Budget Configuration
**Priority**: High (Core FinOps)
**Goal**: Define financial thresholds to trigger alerts.
- [ ] Add `monthly_budget` (float) column to `AppSettings` model (default: 0 = disabled)
- [ ] Update `POST /settings` to accept budget value
- [ ] Add Budget Input field to Settings page (Settings > General)
- [ ] Add migration/schema update logic (if using Alembic, or manual `init_db` handling)

### Task 1.3: Budget Status Widget
**Priority**: High (Visibility)
**Goal**: Show real-time budget consumption on Dashboard.
- [ ] Calculate `budget_percent` in `dashboard` route (`current_cost / monthly_budget * 100`)
- [ ] Add "Budget Health" card to Dashboard:
  - Progress bar (Green < 75%, Yellow < 90%, Red > 100%)
  - Text: "$12.50 / $20.00 (62%)"
  - Warning icon if budget exceeded

### Task 1.4: Budget Alert Logic
**Priority**: Medium (Automation)
**Goal**: Notify users when budget is exceeded.
- [ ] Create `BudgetMonitor` service in `app/core/finops.py`
- [ ] Add check logic: If `current_cost > budget` AND `notification_sent_today` is False -> Notify
- [ ] Hook into `run_scheduled_policy` (or create dedicated daily check job)
- [ ] Send Apprise notification: "⚠️ Budget Exceeded: Current spend $X vs Budget $Y"

## Phase 2: Cost History & Trends (Data)

### Task 2.1: Metric Snapshots
**Priority**: High (Data accumulation)
**Goal**: Track storage/cost usage over time.
- [ ] Create `MetricSnapshot` model:
  - `date` (date)
  - `total_images` (int)
  - `total_gb` (float)
  - `total_cost_usd` (float)
  - `efficiency_score` (int)
- [ ] Create `capture_daily_snapshot()` function in `app/core/analytics.py`
- [ ] Register daily job in `app/core/scheduler.py` (e.g., 23:59 UTC)

### Task 2.2: Trend Visualization
**Priority**: Medium (UI)
**Goal**: Visualize cost trajectory.
- [ ] Add `Chart.js` (lightweight via CDN or static) to `layout.html`
- [ ] Create API `GET /api/metrics/history` returning last 30 snapshots
- [ ] Add Line Chart to Dashboard ("Cost Trend (30 Days)")
- [ ] Add trend indicator (e.g., "⬇️ 5% from last week")

## Phase 3: Bloat Detection (GreenOps)

### Task 3.1: Heuristic Bloat Analyzer
**Priority**: Medium (Optimization)
**Goal**: Identify easy optimization wins without deep scanning.
- [ ] Create `BloatAnalyzer` class in `app/core/bloat.py`
- [ ] Implement heuristics:
  - **Size**: > 500MB (Warning), > 1GB (Critical)
  - **Tag**: Contains `slim`, `alpine`, `distroless` (Good)
  - **OS Family**: Guess based on common patterns (e.g., `python:3.9` vs `python:3.9-slim`)
- [ ] Add `bloat_score` and `optimization_suggestion` to image scan logic

### Task 3.2: Bloat Recommendations UI
**Priority**: Low (Optimization)
**Goal**: Show users what to fix.
- [ ] Add "Optimization Opportunities" table to Dashboard or Images page
- [ ] Show top 5 "Fattest" images with suggestions:
  - "nginx:latest (142MB) → Try nginx:alpine (41MB)"
- [ ] Calculate "Potential Savings" (GB and $) if suggestions applied

## Phase 4: SRE & Reliability Polish (The "SRE" Layer)

### Task 4.1: Structured JSON Logging
**Priority**: High (Observability)
**Goal**: Improve log searchability in production environments.
- [ ] Implement a custom JSON Formatter for the standard `logging` library
- [ ] Replace `logging.basicConfig` with a structured configuration
- [ ] Add contextual metadata (e.g., `registry_id`, `image_digest`) to log records

### Task 4.2: Resilient Registry Clients
**Priority**: High (Reliability)
**Goal**: Handle transient network failures gracefully.
- [ ] Implement exponential backoff retry logic for all Registry API calls (requests)
- [ ] Audit and enforce strict timeouts on all external network requests
- [ ] Add circuit breaker pattern for failing registries (optional/advanced)

### Task 4.3: Transactional Integrity
**Priority**: Medium (Data Integrity)
**Goal**: Prevent orphaned data between Registry and Database.
- [ ] Audit deletion routes to ensure DB transactions wrap both Audit Log creation and Artifact deletion
- [ ] Implement explicit rollback logic in exception handlers for DB sessions
- [ ] Ensure "Delete-from-Registry" and "Delete-from-DB" are logically synchronized

## Phase 5: DevOps & Infrastructure Hardening (The "DevOps" Layer)

### Task 5.1: Production-Grade Dockerfile
**Priority**: Medium (Security)
**Goal**: Minimize attack surface and improve startup reliability.
- [ ] Refactor to a Multi-Stage Docker build (build vs runtime)
- [ ] Add `HEALTHCHECK` instruction using `/health` endpoint
- [ ] Ensure all dependencies are locked and installed via `pyproject.toml`

### Task 5.2: Secure Container Orchestration
**Priority**: High (Security)
**Goal**: Apply least-privilege principles.
- [ ] Fix `docker-compose.yml` to remove `user: root` override
- [ ] Add Resource Limits (CPU/Memory) to prevent container runaway
- [ ] Implement a `docker-compose.prod.yml` without volume mounts for source code

### Task 5.3: Prometheus Metrics
**Priority**: Medium (Observability)
**Goal**: Enable real-time monitoring and alerting.
- [ ] Integrate `prometheus-client` into FastAPI
- [ ] Expose `/metrics` endpoint (protected or internal)
- [ ] Track key SRE metrics: `dredge_space_freed_bytes_total`, `dredge_registry_latency_seconds`, `dredge_active_images_count`

## Phase 6: Testing & Quality Assurance

### Task 6.1: E2E Tests
**Goal**: Verify new features work end-to-end.
- [ ] Test Notification: Mock Apprise, call test endpoint, verify success
- [ ] Test Budget: Set low budget, trigger scan, verify alert triggered (mocked)
- [ ] Test History: Create dummy snapshots, call API, verify JSON structure
