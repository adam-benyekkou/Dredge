# 🌊 Dredge

<div align="center">

**Docker FinOps & Lifecycle Management Tool**

A powerful, nautical-themed platform for managing Docker infrastructure costs and optimizing image lifecycles.

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[📖 Documentation](https://adam-benyekkou.github.io/Dredge/) • [🚀 Quick Start](#-quick-start) • [💻 GitHub](https://github.com/adam-benyekkou/Dredge)

</div>

## 🌊 What is Dredge?

**Dredge** brings clarity to the murky waters of Docker infrastructure costs. Named after the maritime process of clearing sediment, Dredge helps you identify and remove unused Docker images, optimize storage, and track your cloud registry expenses.

### Key Features

- 💰 **Cost Visibility** - Real-time calculation of monthly storage costs across AWS, Azure, and GCP
- 🔍 **Multi-Registry Support** - Scan local Docker and remote registries (Hub, ECR, ACR, GAR)
- 📊 **FinOps Dashboard** - Track waste, efficiency scores, and reclaimable space
- 🗑️ **Safe Cleanup** - Quarantine mode and automated lifecycle policies
- 🎨 **Deep Harbor UI** - Beautiful dark nautical theme for long monitoring sessions

## 🛠️ Tech Stack

**Backend:** Python 3.11 • FastAPI • SQLModel • Docker SDK  
**Frontend:** HTMX • Jinja2 • Custom CSS (Deep Harbor theme)  
**Infrastructure:** Docker • Docker Compose • SQLite

## 🚀 Quick Start

```bash
git clone https://github.com/adam-benyekkou/Dredge.git
cd Dredge
docker-compose up -d
```

Open [http://localhost:8000](http://localhost:8000) to access the dashboard.

**That's it!** 🎉

For detailed installation, configuration, and usage instructions, see the [📖 Documentation](https://adam-benyekkou.github.io/Dredge/).

## 📚 Documentation

For comprehensive guides, API reference, and deployment instructions, visit:

### [📖 https://adam-benyekkou.github.io/Dredge/](https://adam-benyekkou.github.io/Dredge/)

**What's in the docs:**
- 🚀 Getting Started Guide
- 🔧 Configuration & Environment Setup
- 🌐 Registry Provider Setup (AWS ECR, GCP GAR, Docker Hub, etc.)
- 📊 Core Concepts (Images, Volumes, Policies, FinOps)
- 🚢 Production Deployment Guide
- 📖 API Reference

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Made with ❤️ by the Dredge Team**

[⬆ Back to Top](#-dredge)

</div>
