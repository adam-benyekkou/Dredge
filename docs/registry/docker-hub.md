# Docker Hub Setup

Dredge supports scanning private repositories on Docker Hub. This guide explains how to configure access using your Docker credentials.

## Prerequisites

- A Docker Hub account
- A Personal Access Token (PAT) (Recommended over password)

## Configuration Steps

1.  **Generate a Token**
    *   Go to [Docker Hub Settings > Security](https://hub.docker.com/settings/security).
    *   Click "New Access Token".
    *   Give it a description (e.g., "Dredge Scanner").
    *   Set Access permissions to **Read-only**.
    *   Copy the generated token.

2.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries** in the Dredge dashboard.
    *   Click **"Add Registry"**.
    *   **Name**: `Docker Hub` (or any custom name)
    *   **Provider**: `DOCKERHUB`
    *   **Username**: Your Docker Hub username.
    *   **Password**: Paste your Personal Access Token (PAT).
    *   Click **Save**.

## Verification

Once added, go to the **Images** page and select "Docker Hub" from the source dropdown. Click "Scan Now". If configured correctly, your private repository images should appear in the list.
