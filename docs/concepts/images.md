# Images Lifecycle

Dredge manages images through distinct states:

1.  **Active**: The image is present and presumably in use.
2.  **Quarantined**: The image is marked for deletion. It enters a 24-hour "grace period" before permanent removal.
3.  **Deleted**: The image has been removed from the registry.

You can manually restore quarantined images before the grace period expires.
