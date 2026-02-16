# Registry Overview

Dredge acts as a centralized FinOps dashboard for all your container registries. By configuring remote sources, you can visualize costs and manage lifecycles across your entire infrastructure.

## Supported Providers

Dredge supports the following providers out of the box:

| Provider | Key | Authentication |
| :--- | :--- | :--- |
| **Docker Hub** | `DOCKERHUB` | Username + PAT |
| **AWS ECR** | `ECR` | IAM Role / Access Keys |
| **Google Artifact Registry** | `GAR` | Service Account JSON |
| **Azure Container Registry** | `ACR` | Admin User / Service Principal |
| **GitHub Container Registry** | `GHCR` | Username + PAT |
| **Google Container Registry** | `GCR` | Service Account JSON |
| **Custom / Self-Hosted** | `CUSTOM` | Basic Auth |

## How Scanning Works

When you trigger a scan:
1.  Dredge iterates through all enabled registries.
2.  It authenticates using the stored credentials.
3.  It fetches the catalog (`_catalog`) and tags (`/tags/list`).
4.  It retrieves image manifest headers to determine compressed size.
5.  **Note:** Dredge does *not* pull the full image layers. Scanning is lightweight and fast.

## Security Note

Credentials stored in Dredge are currently saved in the local SQLite database. Ensure your Dredge instance is not exposed to the public internet without proper authentication and SSL.
