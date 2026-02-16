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
    *   **Permissions**:
        *   **Read-only**: Sufficient for scanning and cost calculation.
        *   **Read & Write / Delete**: Required if you want to **delete images** via Dredge.
    *   Copy the generated token.

2.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries** in the Dredge dashboard.
    *   Click **"Add Registry"**.
    *   **Name**: `Docker Hub` (or any custom name)
    *   **Provider**: `DOCKERHUB`
    *   **Username**: **REQUIRED** - Your Docker ID (e.g., `adam123`). This is used to locate your repositories.
    *   **Password**: Paste your Personal Access Token (PAT).
    *   Click **"Test Connection"** to verify your credentials before saving.
    *   Click **Save**.

## Features & Capabilities

| Feature | Supported | Notes |
| :--- | :---: | :--- |
| **Scan Images** | ✅ | Lists both public and private repositories for your user. |
| **Cost Estimation** | ✅ | Calculates storage cost based on compressed layer size. |
| **Delete Images** | ✅ | **Permanently deletes** tags from Docker Hub. Requires Write/Delete token scope. |
| **Delete Volumes** | ❌ | Not applicable. Docker Hub does not host volumes. |

## Verification

Once added, go to the **Images** page and select "Docker Hub" from the source dropdown. Click **"Scan Now"**.

*   **Success**: Your private repository images appear in the list with "Docker Hub" source.
*   **Deletion**: Clicking "Delete" on an image will send a request to the Hub API to remove that specific tag.

## Troubleshooting

*   **"Authentication Failed"**: Ensure your Username matches the account that owns the token.
*   **"Connection Failed"**: Check your network connection. Docker Hub API must be reachable from the Dredge container.
*   **Empty List**: 
    *   Ensure you have repositories in your account.
    *   Verify your token has permission to view them.

