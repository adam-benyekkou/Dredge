# Quarantine Management

The Quarantine page is a dedicated interface for managing images that have been flagged by cleanup policies. It provides a safe, reviewable workflow before permanent deletion.

## Overview

When cleanup policies run, matching images are not deleted immediately. Instead, they are moved to a **QUARANTINED** state where you can review, restore, or permanently purge them.

### Key Benefits

*   **Safety**: Review policy decisions before permanent deletion
*   **Flexibility**: Restore images if they were quarantined by mistake
*   **Efficiency**: Bulk operations for managing multiple images at once
*   **Transparency**: Clear visibility into what will be deleted and when

## Accessing the Quarantine Page

Navigate to **Quarantine** from the sidebar (icon: alert-triangle). The page displays:

*   **Total Quarantined Count**: Large counter showing the number of quarantined images
*   **Image Table**: List of all quarantined images with details
*   **Bulk Actions Bar**: Appears when images are selected

## Image Information

Each quarantined image displays:

*   **Tag/Digest**: Image tag (or digest if untagged)
*   **Source**: Registry source (Local, Docker Hub, GHCR, etc.)
*   **Created Date**: When the image was originally created
*   **Size**: Image size in MB/GB
*   **Expires At**: When the 24-hour quarantine period expires
*   **Actions**: Individual restore or purge buttons

## Operations

### Individual Actions

**Unquarantine (Restore)**
*   Click the **"Unquarantine"** button next to an image
*   Image status changes from `QUARANTINED` to `ACTIVE`
*   Expiration timer is removed
*   Image remains in Dredge's database
*   Row disappears from quarantine view
*   Quarantine count updates immediately

**Purge (Delete)**
*   Click the red **"Purge"** button (trash icon)
*   Confirm the action in the browser dialog
*   Image is permanently removed from Dredge's database
*   Row disappears from quarantine view
*   Quarantine count updates immediately
*   **Note**: This only removes the image record from Dredge. To delete from the actual registry, use the Images page.

### Bulk Actions

**Selecting Images**
1.  Click individual checkboxes to select specific images
2.  Use the **"Select All"** checkbox in the table header to select all visible images
3.  The bulk actions bar appears when one or more images are selected
4.  Selected count is displayed (e.g., "3 selected")

**Unquarantine Selected**
*   Click **"Unquarantine Selected"** in the bulk actions bar
*   All selected images are restored to active status
*   Success notification shows how many images were restored
*   Rows disappear from the quarantine view
*   Quarantine count updates by the number of restored images

**Purge Selected**
*   Click the red **"Purge Selected"** button (trash icon)
*   Confirm the destructive action
*   All selected images are permanently deleted from the database
*   Success notification shows how many images were purged
*   Rows disappear from the quarantine view
*   Quarantine count updates by the number of purged images

**Clear Selection**
*   Click **"Clear Selection"** to deselect all images
*   Bulk actions bar disappears

## Real-time Updates

The Quarantine page features real-time updates without requiring page reloads:

*   Quarantine count decreases immediately when images are unquarantined or purged
*   Rows disappear from the table as soon as operations complete
*   Page automatically reloads if the last quarantined image is removed
*   Toast notifications confirm successful operations

## Workflow Example

**Typical quarantine workflow:**

1.  **Run Policy**: Navigate to Policies page → Click "Run Policy Now"
2.  **Preview**: Review the modal showing which images will be quarantined
3.  **Confirm**: Click "Confirm & Quarantine" to proceed
4.  **Review**: Navigate to Quarantine page to see quarantined images
5.  **Decide**:
    *   If images were quarantined correctly → wait for expiration or purge manually
    *   If images were quarantined by mistake → restore them to active status
6.  **Bulk Management**: Select multiple images for efficient processing
7.  **Monitor**: Watch the quarantine count to track your cleanup progress

## Best Practices

**Review Before Purging**
*   Always review quarantined images before purging
*   Check that critical images (like production tags) weren't accidentally quarantined
*   Use the 24-hour grace period to verify with your team

**Use Bulk Operations**
*   When managing multiple images, use bulk selection for efficiency
*   Restore entire batches if a policy was too aggressive
*   Purge entire batches when confident in the cleanup

**Regular Monitoring**
*   Check the Quarantine page periodically
*   Don't let the quarantine list grow too large
*   Make decisions within the 24-hour window

**Policy Tuning**
*   If you frequently restore images, your policies may be too aggressive
*   Adjust `keep_count` or `max_age_days` in the Policies page
*   Use the preview feature to test policy changes before confirming

## Technical Details

### Quarantine Status

*   Images marked as `QUARANTINED` remain in Dredge's SQLite database
*   The `expires_at` field is set to 24 hours from quarantine time
*   Images are NOT automatically purged after expiration (manual action required)
*   Unquarantining sets status to `ACTIVE` and clears `expires_at`

### Cache Invalidation

*   Unquarantine and purge operations clear Dredge's image cache
*   Next scan will reflect the updated image states
*   This ensures consistency across the application

### Database vs Registry

**Important distinction:**
*   **Quarantine**: Changes the image status in Dredge's database only
*   **Purge**: Removes the image record from Dredge's database only
*   **Delete** (from Images page): Actually removes the image from the Docker registry

To fully remove an image:
1.  Unquarantine it (if quarantined)
2.  Navigate to the Images page
3.  Use the "Delete" action to remove from the registry
