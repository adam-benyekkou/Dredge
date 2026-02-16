# Cleanup Policies

Dredge allows you to automate image management by defining lifecycle rules. Policies help you maintain a clean registry and keep storage costs under control.

## Rule Types

*   **Keep Count**: Ensure the last $N$ tags are always kept per repository (e.g., keep last 5 deployments).
*   **Max Age**: Mark images as candidates for cleanup if they are older than $X$ days (e.g., older than 30 days).
*   **Regex Whitelist**: Specify patterns to exclude from policies. Any tag matching this regex will **never** be quarantined (e.g., `^prod-.*` or `latest`).

## How Policies Work

Dredge policies follow a **Quarantine First** approach:

1.  **Enforcement**: When a policy run is triggered, Dredge scans your local and remote registries.
2.  **Quarantine**: Images that violate your rules are **not deleted immediately**. Instead, their status is changed to `QUARANTINED`.
3.  **Review**: You can review quarantined images in the "Images" view (filter by status).
4.  **Purge**: Once you are satisfied, you can manually "Purge" quarantined images or use the **Mass Delete** feature to remove them from the registry forever.

## Running Policies

Currently, policies can be triggered manually via the **Policies** page.

1.  Configure your rules in the **Configure > Policies** section.
2.  Ensure the "Enable automated scans" toggle is ON.
3.  Click **"Run Policy Now"**.
4.  View the results in the real-time notification toast.

## Registry Health Monitoring

Dredge proactively monitors the health of your external registry connections to ensure high performance and responsiveness:

*   **Proactive Pings**: Every 5 minutes, a background task attempts to verify connectivity with all active registries.
*   **Automatic Deactivation**: If a registry fails a connection test (e.g., expired credentials or network failure), Dredge automatically marks it as `INACTIVE`.
*   **Lazy Verification**: When listing images, Dredge performs a quick connection check. If the registry is unreachable, it is disabled immediately to prevent UI hanging.
*   **Manual Reactivation**: Once the connection issue is resolved (e.g., by updating credentials in the **Registries** page), you can re-enable the registry for scanning.

