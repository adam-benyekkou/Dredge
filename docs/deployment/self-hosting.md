# Self-Hosting Dredge

Dredge is designed to be self-hosted via Docker. It's a single container application with minimal dependencies.

## Deployment with Docker Compose

This is the recommended way to run Dredge in production.

1.  **Create a `docker-compose.yml` file:**

```yaml
version: '3.8'

services:
  dredge:
    image: ghcr.io/adam-benyekkou/dredge:latest
    container_name: dredge
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock # Required for local scanning
      - dredge_data:/app/data                   # Persistent database
    environment:
      - LOG_LEVEL=INFO
      - ALLOWED_HOSTS=*

volumes:
  dredge_data:
```

2.  **Start the service:**

```bash
docker-compose up -d
```

3.  **Access the dashboard:**
    Open `http://localhost:8000`.

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Application port |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Path to Docker socket |
| `AWS_PRICE_PER_GB` | `0.10` | Default cost factor for AWS |
| `AZURE_PRICE_PER_GB` | `0.13` | Default cost factor for Azure |
| `GCP_PRICE_PER_GB` | `0.10` | Default cost factor for GCP |

## Persistence

Dredge uses SQLite for storing image metadata, policies, and registry configurations. By mounting a volume to `/app/data` (or wherever the DB is configured to reside), you ensure configuration survives container restarts.
