# Security Audit Report - Phase 2

**Date**: 2026-02-16
**Version**: 2.0
**Status**: 🟠 IMPROVED BUT NOT PRODUCTION READY

---

## 1. Executive Summary

Since the Phase 1 audit, several critical vulnerabilities have been addressed, specifically **XSS injection** points and **Error Information Disclosure**. However, the application remains **unsuitable for production** in its current state due to the lack of authentication, plaintext secret storage, and privileged Docker access.

This report outlines the current security posture and provides a roadmap for production readiness.

## 2. Status of Phase 1 Findings

| ID | Issue | Severity | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **S1** | **XSS in `/scan`** | HIGH | ✅ **FIXED** | `html.escape()` is now applied to all user-controlled data. |
| **S2** | **Docker Socket Exposure** | CRITICAL | 🔴 **OPEN** | `/var/run/docker.sock` is still mounted. Required for core functionality but risky. |
| **S3** | **Input Validation** | MEDIUM | ✅ **FIXED** | Regex validation added to `get_manifest_size` and `delete_image`. |
| **S4** | **Error Disclosure** | LOW | ✅ **FIXED** | Generic error messages returned to UI; full stack traces logged internally. |
| **S5** | **No Rate Limiting** | MEDIUM | 🔴 **OPEN** | Endpoints are vulnerable to DoS. |
| **O1** | **Docker Client Re-init** | LOW | 🟡 **PARTIAL** | Factory pattern used, but client not cached in App State. |

---

## 3. New Findings (Phase 2)

### 🚨 Critical Vulnerabilities (P0)

#### 3.1. Missing Authentication & Authorization
**Location**: `app/web/routes.py`
**Risk**: Anyone with network access to the Dredge port (8000) has full administrative control. They can:
*   Delete any Docker image.
*   Delete Docker volumes.
*   Read audit logs.
*   Configure remote registries (potentially extracting credentials).

**Recommendation**:
*   Implement a login system (Basic Auth or OAuth2).
*   Add `@login_required` dependencies to all non-public routes.

#### 3.2. Plaintext Secrets Storage
**Location**: `app/models.py` (`RegistryConfig.password`)
**Risk**: Registry credentials (PATs, AWS Keys, Service Account JSONs) are stored in plain text in the SQLite database (`dredge.db`).
*   If the database file is leaked (e.g., via backup or container compromise), all remote registry access is compromised.

**Recommendation**:
*   Encrypt sensitive fields using `cryptography.fernet` before storage.
*   Store the encryption key in an environment variable (`ENCRYPTION_KEY`), *never* in the database.

#### 3.3. Lack of CSRF Protection
**Location**: Global
**Risk**: The application relies on HTMX `POST` and `DELETE` requests but does not implement Anti-CSRF tokens.
*   If an authenticated user (assuming auth is added) visits a malicious site, it could trigger image deletions in the background.

**Recommendation**:
*   Implement `CSRFMiddleware`.
*   Inject CSRF tokens into templates and HTMX headers.

---

### ⚠️ High/Medium Risks (P1/P2)

#### 3.4. Privileged Container User
**Location**: `Dockerfile`
**Risk**: The application runs as `root` inside the container. Combined with the Docker socket mount, this makes container escape trivial if an RCE vulnerability is found.

**Recommendation**:
*   Create a non-root user (`useradd -m dredge`) in the Dockerfile.
*   Switch to `USER dredge` before the `CMD` instruction.
*   **Note**: This complicates access to `/var/run/docker.sock`. The socket permissions must allow the `dredge` user to read/write (usually via `docker` group).

#### 3.5. HTTP Only (No TLS)
**Location**: `app/main.py`
**Risk**: Credentials and data are transmitted in cleartext.

**Recommendation**:
*   **Do not implement TLS in Python**.
*   Use a reverse proxy (Nginx, Traefik, Caddy) to handle HTTPS termination in production.

---

## 4. Production Readiness Roadmap

To make Dredge "Prod Usable", the following plan must be executed:

### Step 1: Security Hardening (Immediate)
- [ ] **Implement Authentication**: Add a simple Login page and session management.
- [ ] **Encrypt Secrets**: Add transparent encryption for `RegistryConfig` passwords.
- [ ] **CSRF Protection**: secure state-changing endpoints.

### Step 2: Infrastructure (Deployment)
- [ ] **Non-Root Docker Image**: Update Dockerfile.
- [ ] **Reverse Proxy Example**: Provide a `docker-compose.prod.yml` with Nginx/Caddy.
- [ ] **Database Persistence**: Ensure docs clearly state volume mounting requirements.

### Step 3: Advanced Security (Optional)
- [ ] **Docker Socket Proxy**: Instead of mounting the raw socket, use a sidecar proxy (e.g., `tecnativa/docker-socket-proxy`) that only allows `GET /images` and specific `DELETE` calls, blocking dangerous APIs like `container run`.

---

## 5. Conclusion

Dredge has made significant progress in code quality and safety features (Audit Logs, Quarantine). However, it currently operates on a "Zero Trust" assumption that does not exist. **It must strictly be run in isolated, local environments** until authentication and secret encryption are implemented.
