# Production Guide

When deploying to production, consider:

1.  **Security**: Do not expose Dredge to the public internet without an authentication proxy (e.g., Nginx with Basic Auth, or OAuth2 Proxy).
2.  **Persistence**: Ensure the SQLite database path is mounted to a persistent volume.
3.  **Resources**: Dredge is lightweight but scanning large registries can be memory intensive. Start with 512MB RAM limit.
