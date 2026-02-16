# Custom Registry Setup

For self-hosted registries (like Harbor, Nexus, or plain `registry:2`), use the Custom provider.

## Prerequisites

- A V2-compatible Docker Registry API.
- Basic Auth credentials (if authentication is enabled).
- HTTPS access (Dredge generally requires SSL, though insecure registries can be configured via Docker daemon settings).

## Configuration Steps

1.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `My Private Harbor`
    *   **Provider**: `CUSTOM`
    *   **Endpoint**: `https://registry.example.com` (Include protocol).
    *   **Username**: Registry username.
    *   **Password**: Registry password.
    *   Click **Save**.

## Insecure Registries (HTTP)

If your registry is exposed over HTTP (not recommended), ensure the Docker daemon running Dredge is configured to allow it:

1.  Edit `/etc/docker/daemon.json` on the host:
    ```json
    {
      "insecure-registries" : ["registry.example.com:5000"]
    }
    ```
2.  Restart Docker daemon.
