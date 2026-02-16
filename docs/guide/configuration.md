# Configuration

Dredge is configured via environment variables and the in-app settings dashboard.

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `LOG_LEVEL` | Application logging level | `INFO` |
| `DOCKER_SOCKET` | Path to Docker socket | `/var/run/docker.sock` |

## In-App Settings

Navigate to **Configure > Settings** to customize the FinOps engine:

*   **Default Price per GB**: The monthly cost used for Local Docker and generic registries.
*   **Docker Hub Price per GB**: Specific pricing for Docker Hub images.
*   **GitHub Packages Price per GB**: Specific pricing for GHCR images.
*   **Currency**: Select your preferred currency symbol ($, €, £).

See [Deployment](/deployment/self-hosting) for more details.
