# Security

Dredge uses secure practices to protect your infrastructure data and registry credentials.

## Authentication

All access to the Dredge API and UI is protected:
- **JWT Tokens**: Authentication is handled via JSON Web Tokens.
- **Secure Hashing**: User passwords are stored using the **PBKDF2-SHA256** algorithm.
- **Default Credentials**: Initial installation uses `admin` / `admin`. **Change these immediately** in the **Settings > General** tab.

## Data Protection

- **Credential Storage**: External registry credentials (PATs, Access Keys) are encrypted at rest in the SQLite database.
- **Least Privilege**: We recommend using scoped access tokens (e.g., Docker Hub PATs with read/write access) rather than primary account passwords.

## Deployment Security

Dredge is intended for internal use:
- **Exposure**: Do not expose the Dredge container directly to the public internet.
- **Reverse Proxy**: We recommend running Dredge behind a reverse proxy (Nginx, Traefik) with SSL/TLS enabled.
- **Docker Socket**: Dredge requires access to `/var/run/docker.sock` to manage local images. Ensure the container has appropriate permissions.
