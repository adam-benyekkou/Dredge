# TASKS.md - Dredge Implementation Plan (AI-Optimized)

This document outlines the granular development plan for Dredge. Each task is designed to be atomic and verifiable.

## Phase 1: MVP (Local Only)
**Goal:** Core infrastructure, local Docker socket connection, image listing, and basic cost estimation.

### 1.1 Project Scaffolding
- [ ] **Initialize Python Project**
  - [ ] Create `pyproject.toml` with dependencies: `fastapi`, `uvicorn`, `taskiq`, `sqlmodel`, `jinja2`, `docker`.
  - [ ] Create `app/__init__.py`.
  - [ ] Create directory structure: `app/core`, `app/models`, `app/services`, `app/web`, `templates`, `static`.
- [ ] **Setup FastAPI Entrypoint**
  - [ ] Create `app/main.py`.
  - [ ] Initialize `FastAPI` app.
  - [ ] Mount `static` files.
  - [ ] Configure `Jinja2Templates` pointing to `templates/`.
- [ ] **Verify Scaffolding**
  - [ ] Run `uvicorn app.main:app --reload` and check if it starts without errors.

### 1.2 Domain Models (app/models.py)
- [ ] **Create ImageArtifact Model**
  - [ ] Define `class ImageArtifact(SQLModel, table=True):`.
  - [ ] Fields: `id: Optional[int]`, `tags: List[str]` (use Pydantic JSON or specific SA column), `size_bytes: int`, `created_at: datetime`, `digest: str`.
  - [ ] Add strict type hinting.

### 1.3 Registry Abstraction (app/core/registry.py)
- [ ] **Define Base Interface**
  - [ ] Create `class BaseRegistryClient(ABC):`.
  - [ ] Define abstract method: `list_images() -> List[ImageArtifact]`.
  - [ ] Define abstract method: `get_manifest_size(digest: str) -> int`.
  - [ ] Define abstract method: `delete_image(image_id: str, dry_run: bool = True) -> bool`.
- [ ] **Implement LocalDockerClient**
  - [ ] Create `class LocalDockerClient(BaseRegistryClient):`.
  - [ ] Initialize with `docker.from_env()`.
  - [ ] Implement `list_images()`: Map local images to `ImageArtifact` list.
  - [ ] Implement `get_manifest_size()`: Return size from attrs.
  - [ ] Implement `delete_image()`: Raise `NotImplementedError` for MVP.
  - [ ] **Error Handling**: Wrap docker calls in `try/except` for `docker.errors.APIError`.

### 1.4 FinOps Engine (app/core/finops.py)
- [ ] **Implement CostCalculator**
  - [ ] Create `class CostCalculator:`.
  - [ ] Add constant: `AWS_PRICE_PER_GB = 0.10`.
  - [ ] Add constant: `AZURE_PRICE_PER_GB = 0.13`.
  - [ ] Implement `calculate_monthly_cost(size_bytes: int, provider: str = "AWS") -> float`.
  - [ ] Logic: `(size_bytes / 1024**3) * price`.

### 1.5 Frontend - Layout & MVP Views (See docs/DESIGN.md)
- [ ] **Base Layout (templates/layout.html)**
  - [ ] Import PicoCSS from CDN.
  - [ ] Import HTMX from CDN.
  - [ ] **Define CSS Variables (Deep Harbor Theme)**:
    - [ ] `--pico-background-color: #0D1B2A` (Deep Navy)
    - [ ] `--pico-card-background-color: #1B263B` (Steel Blue)
    - [ ] `--pico-primary: #0077B6` (Cerulean)
    - [ ] `--pico-primary-hover: #0096C7` (Lighter Blue)
    - [ ] `--pico-color: #E0E1DD` (Off-White)
    - [ ] `--danger: #D97D54` (Rusted Orange - for Waste metrics)
    - [ ] `--accent: #48CAE4` (Cyan - for Highlights)
  - [ ] **Sidebar Implementation**:
    - [ ] Fixed width (~250px).
    - [ ] Top: "Abyssal Vortex" Logo + "Dredge" Text.
    - [ ] Nav: Dashboard, Images, Volumes, Policies, Logs.
    - [ ] Bottom: Scope Dropdown (Local/Remote) + Server Status Indicator.
  - [ ] **Main Content Area**: Scrollable container.
- [ ] **Dashboard View (templates/dashboard.html)**
  - [ ] **KPI Cards**:
    - [ ] Monthly Waste ($): Value in Rusted Orange (`--danger`).
    - [ ] Reclaimable Space (GB): Value in Cyan (`--accent`).
    - [ ] Efficiency Score (%): Value in White.
  - [ ] **Action Bar**:
    - [ ] "Scan Now" Button (`hx-post="/scan"`).
    - [ ] "Dry Run" Toggle Switch.
- [ ] **Images View (templates/images.html)**
  - [ ] Extend `layout.html`.
  - [ ] Create High-Density Table.
  - [ ] Columns: Checkbox, Repository, Tag, Size, Created (Relative time), Status Badge.
  - [ ] **Badging Logic**:
    - [ ] Safe: Green/Cyan background.
    - [ ] Dangling: Rusted Orange background.
    - [ ] Quarantined: Striped/Grey background.

### 1.6 API & Integration (app/web/routes.py)
- [ ] **Create Endpoints**
  - [ ] `GET /`: Render `templates/images.html` with empty list or initial data.
  - [ ] `POST /scan`: Instantiate `LocalDockerClient`, call `list_images()`, return HTML partial (table rows) for HTMX.

---

## Phase 2: Alpha (The Reaper)
**Goal:** Soft delete (quarantine), policies, and manual purge.

### 2.1 Advanced Models (app/models.py)
- [ ] **CleanupPolicy**
  - [ ] Create `class CleanupPolicy(SQLModel, table=True):`.
  - [ ] Fields: `keep_count: int`, `max_age_days: int`, `regex_whitelist: str`.
- [ ] **AuditLog**
  - [ ] Create `class AuditLog(SQLModel, table=True):`.
  - [ ] Fields: `image_id: str`, `bytes_freed: int`, `savings_usd: float`, `timestamp: datetime`.
- [ ] **Update ImageArtifact**
  - [ ] Add field: `status: str` (Enum: ACTIVE, QUARANTINED, DELETED).
  - [ ] Add field: `expires_at: Optional[datetime]`.

### 2.2 Quarantine Logic (app/services/cleaner.py)
- [ ] **Mark for Deletion**
  - [ ] Create function `mark_for_deletion(image_id: str)`.
  - [ ] Logic: Update `ImageArtifact.status` to `QUARANTINED`.
  - [ ] Logic: Set `expires_at` to `now() + timedelta(hours=24)`.

### 2.3 Deletion Logic (app/core/registry.py)
- [ ] **Implement Real Deletion**
  - [ ] Update `LocalDockerClient.delete_image`.
  - [ ] If `dry_run=False`: Call `docker_client.images.remove()`.
  - [ ] Record entry in `AuditLog`.

### 2.4 Frontend Updates
- [ ] **Image Table Actions**
  - [ ] Add "Status" Badge (Green/Orange).
  - [ ] Add "Dry Run" Toggle (UI element only).
  - [ ] Add "Purge" button triggering `hx-delete="/images/{id}"`.

---

## Phase 3: Beta (FinOps)
**Goal:** Remote registry support and visualization.

### 3.1 Remote Adapter (app/core/registry.py)
- [ ] **Implement RemoteRegistryClient**
  - [ ] Inherit from `BaseRegistryClient`.
  - [ ] Implement `list_images` using `requests` to Docker V2 API (`/_catalog`).
  - [ ] Implement auth handling (Basic/Bearer).

### 3.2 Dashboard (templates/dashboard.html)
- [ ] **KPI Cards**
  - [ ] Calculate "Monthly Waste": Sum of cost of all QUARANTINED images.
  - [ ] Calculate "Efficiency": (Active Size / Total Size) * 100.
- [ ] **Charts**
  - [ ] Add placeholder `<div>` for Chart.js.
  - [ ] Create endpoint `/api/stats` to return JSON data for charts.

### 3.3 Reporting (app/services/report.py)
- [ ] **PDF Generation**
  - [ ] Install `reportlab` or similar.
  - [ ] Generate PDF summarizing `AuditLog` entries for the month.
