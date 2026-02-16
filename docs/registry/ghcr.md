# GitHub Container Registry (GHCR) Setup

Dredge can scan images stored in GitHub Packages (GHCR).

## Prerequisites

- A GitHub Account.
- A Personal Access Token (PAT) with `read:packages` scope.

## Generating a Token

1.  Go to **Settings > Developer settings > Personal access tokens (Classic)**.
2.  Generate new token.
3.  Select scope `read:packages`.
4.  (Optional) If scanning private repos, ensure the user has access to them.
5.  Copy the token.

## Configuration Steps

1.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `GitHub Packages`
    *   **Provider**: `GHCR`
    *   **Endpoint**: `ghcr.io`
    *   **Username**: Your GitHub username.
    *   **Password**: Your PAT.
    *   Click **Save**.

## Troubleshooting

- **"Manifest Unknown"**: Ensure your PAT has access to the specific organization or repository packages.
- **SSO**: If your organization enforces SAML SSO, you must authorize the PAT for that organization.
