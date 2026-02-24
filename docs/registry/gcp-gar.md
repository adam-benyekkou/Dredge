# Google Artifact Registry (GAR) Setup

Dredge supports Google Cloud's Artifact Registry. Authentication is handled via Service Account JSON keys or Workload Identity.

## Prerequisites

- A Google Cloud Project.
- Artifact Registry API enabled.
- A Service Account with `Artifact Registry Reader` role.

## Service Account Setup

1.  Go to IAM & Admin > Service Accounts.
2.  Create a new Service Account (e.g., `dredge-scanner`).
3.  Grant the role **Artifact Registry Reader** (`roles/artifactregistry.reader`).
4.  Create and download a JSON key for this account.
5.  Save the key file (e.g., `gcp-key.json`) in your Dredge directory.

## Configuration Steps

1.  **Mount Key File**
    Update your `docker-compose.yml` to mount the key and set the env var:

    ```yaml
    services:
      dredge:
        environment:
          - GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-key.json
        volumes:
          - ./gcp-key.json:/app/gcp-key.json:ro
    ```

2.  **Add Registry in Dredge**
    *   Navigate to **Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `GCP Artifacts`
    *   **Provider**: `GAR`
    *   **Endpoint**: `projects/<project-id>/locations/<region>/repositories/<repo-name>` (Used for resource discovery)
    *   **Username**: Your GCP Project ID.
    *   **Password**: Paste the *contents* of your Service Account JSON key file.
    *   Click **Save**.

## GCR (Container Registry)

For legacy GCR (`gcr.io`), follow the same steps but set the Provider to `GCR` and use `gcr.io` as the endpoint.
