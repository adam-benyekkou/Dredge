# Quick Start

Get Dredge running in under 60 seconds.

## Docker Compose (Recommended)

```bash
git clone https://github.com/adam-benyekkou/dredge
cd dredge
docker-compose up -d
```

Open [http://localhost:8000](http://localhost:8000) to access the dashboard.

## Local Development

1.  Clone the repository.
2.  Install dependencies: `pip install -e .[dev]`
3.  Run the app: `uvicorn app.main:app --reload`
