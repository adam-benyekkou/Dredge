# Cleanup Policies

Dredge allows you to automate image management by defining lifecycle rules. Policies help you maintain a clean registry and keep storage costs under control.

## Rule Types

*   **Keep Count**: Ensure the last $N$ tags are always kept per repository (e.g., keep last 5 deployments).
*   **Max Age**: Mark images as candidates for cleanup if they are older than $X$ days (e.g., older than 30 days).
*   **Regex Whitelist**: Specify patterns to exclude from policies. Any tag matching this regex will **never** be quarantined (e.g., `^prod-.*` or `latest`).

## How Policies Work

Dredge policies follow a **Quarantine First** approach with preview-before-action safety:

1.  **Preview**: When you click "Run Policy Now", Dredge shows a preview modal with all images that will be quarantined.
2.  **Confirmation**: You must explicitly confirm the quarantine action by clicking "Confirm & Quarantine" in the preview modal.
3.  **Enforcement**: After confirmation, Dredge scans your local and remote registries and applies the policies.
4.  **Quarantine**: Images that violate your rules are **not deleted immediately**. Instead, their status is changed to `QUARANTINED` with a 24-hour expiration timer.
5.  **Review**: You can review all quarantined images in the dedicated **Quarantine** page (accessible from the sidebar).
6.  **Unquarantine or Purge**: From the Quarantine page, you can:
    *   **Unquarantine**: Restore images to active status (individually or in bulk)
    *   **Purge**: Permanently delete images from the database (individually or in bulk)

### Per-Repository Policy Application

**Important**: Policies are applied **per repository**, not globally. For example:

*   If you set `keep_count=3` and have 5 repositories with 2 images each (10 total images), **no images will be quarantined** because each repository has fewer than 3 images.
*   The `keep_count` rule means "keep the 3 newest images **in each repository**", not "keep 3 newest images globally".

This design ensures that every repository maintains its own minimum image count, preventing accidental removal of critical images from low-activity repositories.

## Running Policies

Policies can be triggered manually via the **Policies** page:

1.  Configure your rules in the **Configure > Policies** section.
2.  Click **"Run Policy Now"** (the "Enable automated scans" toggle does NOT affect manual runs).
3.  Review the preview modal showing which images will be quarantined.
4.  Click **"Confirm & Quarantine"** to proceed, or **"Cancel"** to abort.
5.  View the results in the real-time notification toast.

## Quarantine Management

The **Quarantine** page provides a dedicated interface for managing quarantined images:

### Features

*   **Bulk Selection**: Select multiple images using checkboxes, or use "Select All" to select all visible images.
*   **Bulk Actions Bar**: When images are selected, a bulk actions bar appears with:
    *   **Unquarantine Selected**: Restore multiple images to active status at once
    *   **Purge Selected**: Permanently delete multiple images from the database
*   **Individual Actions**: Each quarantined image has individual action buttons:
    *   **Unquarantine**: Restore a single image to active status
    *   **Purge**: Permanently delete a single image from the database
*   **Real-time Updates**: The quarantine count updates immediately without page reload when you unquarantine or purge images.
*   **Expiration Display**: Each image shows when it will expire (default: 24 hours from quarantine time).

### Using the Quarantine Page

1.  Navigate to **Quarantine** from the sidebar (icon: alert-triangle).
2.  Review the list of quarantined images with their tags, sources, creation dates, and sizes.
3.  Select images individually or use "Select All".
4.  Choose an action:
    *   **Unquarantine**: Restores images to active status, removing the expiration timer
    *   **Purge**: Permanently deletes images from the database (this action is irreversible)
5.  Confirm destructive actions when prompted.
6.  Watch the quarantine count update in real-time as images are processed.

## Registry Health Monitoring

Dredge proactively monitors the health of your external registry connections to ensure high performance and responsiveness:

*   **Proactive Pings**: Every 5 minutes, a background task attempts to verify connectivity with all active registries.
*   **Automatic Deactivation**: If a registry fails a connection test (e.g., expired credentials or network failure), Dredge automatically marks it as `INACTIVE`.
*   **Lazy Verification**: When listing images, Dredge performs a quick connection check. If the registry is unreachable, it is disabled immediately to prevent UI hanging.
*   **Manual Reactivation**: Once the connection issue is resolved (e.g., by updating credentials in the **Registries** page), you can re-enable the registry for scanning.

