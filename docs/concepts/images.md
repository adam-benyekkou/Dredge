# Images Lifecycle

Dredge manages images through distinct states:

1.  **Active**: The image is present and presumably in use.
2.  **Quarantined**: The image is marked for deletion by cleanup policies. It enters a 24-hour "grace period" before automatic purging becomes available.
3.  **Purged**: The image has been permanently removed from Dredge's database.

## Managing Quarantined Images

Quarantined images can be managed through the dedicated **Quarantine** page:

*   **Restore/Unquarantine**: Return images to active status, removing the expiration timer
*   **Purge**: Permanently delete images from Dredge's database

Both operations support bulk actions via checkboxes, allowing you to restore or purge multiple images simultaneously.

**Important**: Quarantined images are stored in Dredge's database with a status flag. Purging an image removes it from Dredge's tracking but does not automatically delete it from the actual Docker registry. Use the **Images** page with the "Delete" action to remove images from registries.

