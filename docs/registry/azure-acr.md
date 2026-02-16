# Azure Container Registry (ACR) Setup

Integrate Azure Container Registry (ACR) with Dredge to scan your images hosted on Azure.

## Prerequisites

- An Azure Subscription.
- An Azure Container Registry instance.
- A Service Principal or Admin User enabled.

## Authentication Methods

### Method 1: Admin User (Simplest)
1.  Go to your ACR in the Azure Portal.
2.  Under **Settings > Access keys**, enable **Admin user**.
3.  Copy the **Username** and **password**.

### Method 2: Service Principal (Recommended for Prod)
1.  Create a Service Principal with `AcrPull` permission on the registry scope.
2.  Use the App ID as username and Client Secret as password.

## Configuration Steps

1.  **Add Registry in Dredge**
    *   Navigate to **Settings > Registries**.
    *   Click **"Add Registry"**.
    *   **Name**: `Azure Registry`
    *   **Provider**: `ACR`
    *   **Endpoint**: `myregistry.azurecr.io` (Replace with your login server).
    *   **Username**: Your ACR Username or Service Principal ID.
    *   **Password**: Your ACR Password or Client Secret.
    *   Click **Save**.

## Verification

Select "Azure Registry" from the source dropdown on the dashboard. Scanning should retrieve all repositories and tags.
