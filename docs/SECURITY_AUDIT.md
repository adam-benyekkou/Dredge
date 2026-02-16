# Security & Optimization Audit Report

**Date**: 2026-02-16  
**Phase**: 1 (MVP)  
**Status**: 🔴 CRITICAL ISSUES FOUND

---

## 🚨 CRITICAL SECURITY VULNERABILITIES

### 1. **XSS (Cross-Site Scripting) in `/scan` Endpoint**
**Severity**: HIGH  
**Location**: `app/web/routes.py:55-75`

**Issue**:
```python
html_rows.append(f"""
    <tr>
        <td>{repo}</td>  # ← UNSANITIZED USER DATA
        <td>{tag}</td>   # ← UNSANITIZED USER DATA
```

**Risk**: Docker image tags/repositories are directly injected into HTML without escaping. Malicious image names like `<script>alert('XSS')</script>` would execute in user browsers.

**Fix Required**:
```python
from html import escape

html_rows.append(f"""
    <tr>
        <td>{escape(repo)}</td>
        <td>{escape(tag)}</td>
```

**Priority**: IMMEDIATE

---

### 2. **Docker Socket Exposure (Privileged Access)**
**Severity**: CRITICAL  
**Location**: `docker-compose.yml:9`

**Issue**:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

**Risk**: The container has FULL control over the host Docker daemon. A compromised container can:
- Delete ALL host containers
- Read sensitive data from other containers
- Escalate to root on the host

**Mitigation** (for production):
1. Use Docker-in-Docker (DinD) instead
2. Implement strict authentication
3. Run container in read-only mode with limited capabilities
4. Use Docker API over TCP with TLS

**Current Status**: ACCEPTABLE for local development ONLY. MUST NOT deploy to production without mitigation.

---

### 3. **No Input Validation**
**Severity**: MEDIUM  
**Location**: `app/core/registry.py:67`

**Issue**:
```python
def get_manifest_size(self, digest: str) -> int:
    img = self.client.images.get(digest)  # ← No validation
```

**Risk**: Arbitrary digest strings accepted. Could cause Docker API errors or information disclosure.

**Fix Required**:
```python
import re

def get_manifest_size(self, digest: str) -> int:
    if not re.match(r'^sha256:[a-f0-9]{64}$', digest):
        raise ValueError("Invalid digest format")
    img = self.client.images.get(digest)
```

---

### 4. **Error Information Disclosure**
**Severity**: LOW  
**Location**: `app/web/routes.py:91`

**Issue**:
```python
except Exception as e:
    return HTMLResponse(
        content=f'<p>Error scanning images: {str(e)}</p>',  # ← Exposes stack traces
```

**Risk**: Internal error details (file paths, library versions) exposed to users.

**Fix Required**:
```python
except Exception as e:
    # Log full error internally
    logger.error(f"Scan failed: {e}")
    # Return generic message
    return HTMLResponse(
        content='<p>Scan failed. Please try again.</p>',
        status_code=500
    )
```

---

### 5. **No Rate Limiting**
**Severity**: MEDIUM  
**Location**: `app/web/routes.py:40`

**Issue**: `/scan` endpoint has no rate limiting. Attackers can spam scans to cause DoS.

**Fix Required**: Add FastAPI rate limiting middleware (e.g., `slowapi`).

---

## ⚡ OPTIMIZATION ISSUES

### 1. **Docker Client Created Per Request**
**Location**: `app/web/routes.py:43`

```python
@router.post("/scan")
async def scan_images(request: Request):
    client = LocalDockerClient()  # ← NEW CLIENT EVERY REQUEST
```

**Impact**: High latency. Docker client initialization is expensive.

**Fix**:
```python
# In app/main.py
from app.core.registry import LocalDockerClient

@app.on_event("startup")
async def startup():
    app.state.docker_client = LocalDockerClient()

# In routes.py
@router.post("/scan")
async def scan_images(request: Request):
    client = request.app.state.docker_client
```

---

### 2. **String Concatenation in HTML Building**
**Location**: `app/web/routes.py:55`

```python
html_rows.append(f"""...""")  # String concat in loop
result_html = f"""...{''.join(html_rows)}..."""
```

**Impact**: O(n²) complexity for large lists. Slow for 100+ images.

**Fix**: Use Jinja2 templates (already available):
```python
return templates.TemplateResponse(
    "scan_results.html",
    {"request": request, "images": images, "total_cost": total_cost}
)
```

---

### 3. **No Caching**
**Location**: `app/core/registry.py:41`

**Issue**: Every scan re-fetches ALL images from Docker API.

**Fix**: Implement TTL cache (5-60 seconds):
```python
from functools import lru_cache
from time import time

@lru_cache(maxsize=1)
def _list_images_cached(timestamp: int):
    return self.client.images.list()

def list_images(self):
    current_minute = int(time() // 60)
    return _list_images_cached(current_minute)
```

---

### 4. **Missing Database Connection Pool**
**Location**: Not implemented yet

**Issue**: SQLModel/SQLite not configured with proper connection pooling.

**Fix Required** (for Phase 2):
```python
from sqlmodel import create_engine
engine = create_engine(
    "sqlite:///dredge.db",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)
```

---

### 5. **No Async for Docker Operations**
**Location**: `app/core/registry.py:41`

**Issue**: Blocking I/O in async endpoint. Docker SDK calls are synchronous.

**Fix**: Use `asyncio.to_thread()`:
```python
import asyncio

async def list_images_async(self):
    return await asyncio.to_thread(self._list_images_sync)

def _list_images_sync(self):
    # Current implementation
```

---

## 📋 MISSING FEATURES (Security)

### 1. **No Authentication/Authorization**
- Anyone can access `/scan` endpoint
- No user management
- No API keys

### 2. **No HTTPS/TLS**
- Credentials/data transmitted in plaintext

### 3. **No CORS Configuration**
- Cross-origin attacks possible

### 4. **No Security Headers**
```python
# Add to main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 5. **No Logging/Audit Trail**
- No record of who scanned what
- No detection of suspicious activity

---

## ✅ VERIFICATION CHECKLIST (NOT COMPLETED)

- [ ] **E2E Tests**: NOT RUN (Python env not available)
- [ ] **Docker Build**: NOT VERIFIED
- [ ] **Security Scan**: NOT RUN (no `bandit` or `safety` check)
- [ ] **Performance Test**: NOT RUN
- [ ] **Load Test**: NOT RUN

---

## 🔧 IMMEDIATE ACTION REQUIRED

### Before ANY production use:

1. **Fix XSS vulnerability** (15 min)
2. **Add input validation** (30 min)
3. **Implement rate limiting** (1 hour)
4. **Move Docker client to app state** (15 min)
5. **Add proper error logging** (30 min)
6. **Run security scanner**: `pip install bandit && bandit -r app/`
7. **Run dependency check**: `pip install safety && safety check`

### For Production Deployment:

1. Implement authentication (OAuth2/JWT)
2. Add HTTPS/TLS termination (nginx/Traefik)
3. Isolate Docker socket access (API gateway pattern)
4. Add comprehensive logging (structured logs to ELK/Datadog)
5. Implement monitoring (Prometheus/Grafana)

---

## 📊 SEVERITY SUMMARY

| Severity | Count | Items |
|----------|-------|-------|
| CRITICAL | 1 | Docker socket exposure |
| HIGH | 1 | XSS vulnerability |
| MEDIUM | 3 | Input validation, rate limiting, error disclosure |
| LOW | 0 | - |

**RECOMMENDATION**: DO NOT deploy to production without addressing CRITICAL and HIGH issues.
