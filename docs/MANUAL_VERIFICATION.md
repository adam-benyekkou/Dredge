# Manual Verification Guide

**CRITICAL**: This guide MUST be executed before considering Phase 1 complete.

---

## Prerequisites

- Docker installed and running
- Python 3.11+ with pip
- Git

---

## 1. Run E2E Tests

```bash
cd C:\Code\Dredge

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Expected output:
# tests/test_e2e.py::test_health_check PASSED
# tests/test_e2e.py::test_dashboard_renders PASSED
# tests/test_e2e.py::test_images_page_renders PASSED
# tests/test_e2e.py::test_scan_endpoint PASSED
# ========================== 4 passed in X.XXs ==========================
```

**Success Criteria**: All 4 tests pass.

---

## 2. Verify Docker Build

```bash
# Build the image
docker-compose build

# Expected output (no errors):
# Successfully built <hash>
# Successfully tagged dredge:latest
```

**Success Criteria**: Build completes without errors.

---

## 3. Verify Docker Startup

```bash
# Start the container
docker-compose up

# Expected output:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete.
```

**Success Criteria**: Container starts, logs show "Application startup complete".

---

## 4. Verify Health Endpoint

```bash
# In another terminal
curl http://localhost:8000/health

# Expected output:
# {"status":"ok","app":"Dredge","version":"0.1.0"}
```

**Success Criteria**: 200 OK response with JSON.

---

## 5. Verify Dashboard Renders

Open browser: `http://localhost:8000/`

**Expected**:
- Dark "Deep Harbor" theme visible
- Sidebar with navigation
- KPI cards showing "Monthly Waste", "Reclaimable Space", "Efficiency"
- "Scan Now" button present

**Success Criteria**: All UI elements render correctly.

---

## 6. Verify Image Scanning (CRITICAL)

1. **Ensure Docker has images**:
   ```bash
   docker pull alpine:latest
   docker pull nginx:latest
   ```

2. **Click "Scan Now" button** in dashboard

3. **Expected Result**:
   - Table appears with 2+ rows
   - Columns: Repository, Tag, Size, Created, Status, Monthly Cost
   - Data shows actual Docker images
   - Cost calculations displayed

**Success Criteria**: Real Docker images displayed with calculated costs.

---

## 7. Security Verification

### 7.1 XSS Protection Test

Create a malicious image tag:
```bash
docker tag alpine:latest '<script>alert("XSS")</script>:test'
```

**Scan the images via dashboard.**

**Expected**: The `<script>` tag should be HTML-escaped (displayed as text, NOT executed).

**Success Criteria**: No JavaScript alert appears. Tag is displayed as literal text.

---

### 7.2 Error Disclosure Test

Stop Docker daemon:
```bash
# Windows: Stop Docker Desktop
# Linux: sudo systemctl stop docker
```

**Click "Scan Now"**

**Expected Output**:
```
Scan failed. Please check Docker daemon connection.
```

**NOT Expected** (information disclosure):
```
Error: ConnectionError at /var/run/docker.sock line 42 ...
```

**Success Criteria**: Generic error message shown. No stack traces.

---

## 8. Security Scanner

### 8.1 Bandit (Python Security Linter)

```bash
pip install bandit
bandit -r app/

# Review output for HIGH/MEDIUM severity issues
```

**Success Criteria**: No HIGH severity issues. MEDIUM issues reviewed and accepted/fixed.

---

### 8.2 Safety (Dependency Vulnerabilities)

```bash
pip install safety
safety check

# Review output for known CVEs
```

**Success Criteria**: No critical vulnerabilities in dependencies.

---

## 9. Performance Baseline

### 9.1 Response Time Test

```bash
# Install httpie
pip install httpie

# Test health endpoint
time http http://localhost:8000/health

# Expected: < 100ms response time
```

### 9.2 Scan Endpoint Load

```bash
# Pull 10+ images
for i in {1..10}; do docker pull alpine:latest; done

# Click "Scan Now"
# Measure time to render
```

**Success Criteria**: Scans complete in < 3 seconds for 10 images.

---

## 10. Docker Socket Access Verification

```bash
# Inside running container
docker-compose exec dredge bash

# Try to list host images
docker images

# Expected: Should see host's Docker images
```

**Success Criteria**: Container can access host Docker daemon.

---

## 11. Logs Review

```bash
# Check container logs
docker-compose logs dredge

# Look for:
# - No Python exceptions
# - INFO level logs for startup
# - ERROR logs only for expected failures
```

**Success Criteria**: Clean logs, no unexpected exceptions.

---

## 12. Code Quality

### 12.1 Type Checking

```bash
pip install mypy
mypy app/
```

**Success Criteria**: No type errors.

---

### 12.2 Linting

```bash
pip install ruff
ruff check app/
```

**Success Criteria**: No critical linting errors.

---

## VERIFICATION CHECKLIST

- [ ] All 4 E2E tests pass
- [ ] Docker build succeeds
- [ ] Docker container starts successfully
- [ ] Health endpoint returns 200 OK
- [ ] Dashboard renders with Deep Harbor theme
- [ ] Image scanning works with real Docker images
- [ ] XSS protection verified (malicious tags escaped)
- [ ] Error disclosure prevented (generic messages)
- [ ] Bandit security scan passes (no HIGH issues)
- [ ] Safety dependency check passes
- [ ] Performance baseline met (< 3s for 10 images)
- [ ] Docker socket access works
- [ ] Logs are clean
- [ ] Type checking passes
- [ ] Linting passes

---

## SIGN-OFF

**Tested By**: ___________________  
**Date**: ___________________  
**Status**: [ ] PASS [ ] FAIL  
**Notes**: ___________________

**If ANY item fails, Phase 1 is NOT complete.**
