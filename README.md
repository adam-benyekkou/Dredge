# <img src="static/media/dredge_logo.png" height="32" style="vertical-align: bottom;"> Dredge

<div align="center">

**Docker FinOps & Lifecycle Management Tool**

A powerful, nautical-themed platform for managing Docker infrastructure costs and optimizing image lifecycles.

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[Live Demo](https://dredge-demo.cavydev.com/) • [📖 Documentation](https://adam-benyekkou.github.io/Dredge/) • [Quick Start](#quick-start)

</div>

![Dredge Dashboard](docs/assets/screenshots/dashboard.png)

## What is Dredge?

**Dredge** brings clarity to the murky waters of Docker infrastructure costs. Named after the maritime process of clearing sediment, Dredge helps you identify and remove unused Docker images, optimize storage, and track your cloud registry expenses.

- **Visibility** - Real-time cost tracking across multi-registries (Docker Hub, AWS ECR, GHCR, etc.).
- **Optimization** - Automated cleanup policies, bloat detection, and efficiency scoring.
- **Safety** - Quarantine-first workflow with preview modals and 24-hour grace periods.

## Tech Stack

- **Backend:** Python 3.11 • FastAPI • SQLModel • Docker SDK
- **Frontend:** HTMX • Jinja2 • Custom CSS (Deep Harbor theme)
- **Infrastructure:** Docker • Docker Compose • SQLite
- **Auth:** JWT (python-jose) • PBKDF2-SHA256 hashing

## Quick Start

```bash
git clone https://github.com/adam-benyekkou/Dredge.git
cd Dredge
docker-compose up -d
```

Open [http://localhost:8000](http://localhost:8000) to access the dashboard. (Default: `admin` / `admin`)

## 📖 Learn More

- [Introduction & Features](https://adam-benyekkou.github.io/Dredge/guide/introduction)
- [Architecture & Data Flow](https://adam-benyekkou.github.io/Dredge/concepts/architecture)
- [Security Best Practices](https://adam-benyekkou.github.io/Dredge/guide/security)
- [Deployment Guide](https://adam-benyekkou.github.io/Dredge/deployment/production)

