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

## Testing

### Task 4.1: E2E Tests
**Goal**: Verify new features work end-to-end.
- [ ] Test Notification: Mock Apprise, call test endpoint, verify success
- [ ] Test Budget: Set low budget, trigger scan, verify alert triggered (mocked)
- [ ] Test History: Create dummy snapshots, call API, verify JSON structure