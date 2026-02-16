# GitHub Container Registry (GHCR) Setup

Dredge can scan images stored in GitHub Packages (GHCR).

## Prerequisites

- A GitHub Account.
- A Personal Access Token (PAT) with `read:packages` scope.

## Generating a Token

1.  Go to **Settings > Developer settings > Personal access tokens (Classic)**.
2.  Click **Generate new token (classic)**.
3.  **Scopes Required**:
    *   `read:packages` (Required for Scanning)
    *   `write:packages` (Required for Deletion)
    *   `delete:packages` (Required for Deletion)
4.  (Optional) If scanning private repos, ensure the user has access to them.
5.  Copy the token.

## Configuration Steps

1.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `GitHub Packages`
    *   **Provider**: `GHCR`
    *   **Endpoint**: `ghcr.io` (Optional, default is handled)
    *   **Username**: Your GitHub username.
    *   **Password**: Your PAT.
    *   Click **"Test Connection"** to verify access.
    *   Click **Save**.

## Features & Capabilities

| Feature | Supported | Notes |
| :--- | :---: | :--- |
| **Scan Images** | ✅ | Lists containers from your personal account (`ghcr.io/username/...`). |
| **Cost Estimation** | ⚠️ | Limited. GitHub API often returns 0 for package size. |
| **Delete Images** | 🚧 | **In Progress**. Currently scan-only. |

## Troubleshooting

- **"Manifest Unknown"**: Ensure your PAT has access to the specific organization or repository packages.
- **SSO**: If your organization enforces SAML SSO, you must authorize the PAT for that organization.
- **Empty List**: Currently, Dredge scans packages owned by the *authenticated user*. If your packages are in an Organization, you might not see them yet (feature coming soon).
