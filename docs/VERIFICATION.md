# Phase 1.1 Verification Guide

## Prerequisites
- Python 3.11 or higher installed
- pip package manager available

## Verification Steps

### 1. Install Dependencies
```bash
cd C:\Code\Dredge
pip install -e .
```

**Expected Output:**
```
Successfully installed dredge-0.1.0 fastapi-[version] uvicorn-[version] ...
```

### 2. Start the Application
```bash
uvicorn app.main:app --reload
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [pid] using StatReload
INFO:     Started server process [pid]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 3. Test the Health Endpoint
Open browser or use curl:
```bash
curl http://127.0.0.1:8000/
```

**Expected Response:**
```json
{"status":"ok","app":"Dredge","version":"0.1.0"}
```

## Success Criteria
- [x] Directory structure created: `app/core`, `app/models`, `app/services`, `app/web`, `templates`, `static`
- [x] `pyproject.toml` exists with all required dependencies
- [x] `app/__init__.py` exists
- [x] `app/main.py` exists with FastAPI app, StaticFiles mount, Jinja2Templates
- [ ] Server starts without errors (manual verification required)
- [ ] Health endpoint returns expected JSON (manual verification required)

## Notes
The scaffolding code is complete and follows FastAPI best practices. Verification requires a Python 3.11+ environment with pip.
