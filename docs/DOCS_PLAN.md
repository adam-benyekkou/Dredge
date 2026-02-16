# Documentation Plan

This document outlines the plan for creating comprehensive documentation for Dredge using VitePress.

## 1. Structure

The documentation will be organized into the following sections:

- **Guide**: General usage, installation, and configuration.
- **Registry Providers**: Detailed instructions for setting up each supported registry.
- **Architecture**: Technical design and implementation details.
- **Reference**: API reference and CLI commands.

## 2. Content Plan

### Guide
- `guide/introduction.md`: What is Dredge? Key features.
- `guide/getting-started.md`: Installation (Docker, Local), running the app.
- `guide/configuration.md`: AppSettings, Database, Environment Variables.

### Registry Providers (The Focus)
- `registry/overview.md`: How the Registry Authentication System works (Strategy Pattern).
- `registry/basic-auth.md`: **Tier 1**. How to configure username/password or PAT for standard registries (Docker Hub, GHCR).
- `registry/aws-ecr.md`: **Tier 3**. Setting up AWS ECR.
    - Prerequisites (IAM permissions).
    - Authentication logic (`boto3` auto-auth).
    - Troubleshooting `401 Unauthorized`.
- `registry/gcp-gar.md`: **Tier 3**. Setting up GCP Artifact Registry.
    - Prerequisites (Service Account, APIs).
    - Authentication logic (`google-auth`).
    - Token lifecycle (1 hour expiry).

### Architecture
- `architecture/design.md`: High-level design (from `DESIGN.md`).
- `architecture/authentication.md`: Deep dive into `app/core/auth.py` and `app/tasks/refresh.py`.
    - Explaining the `RegistryAuthenticator` ABC.
    - Explaining the `AuthFactory`.
    - Explaining the `refresh_registry_credentials` task.

## 3. Implementation Steps

1.  [x] Initialize VitePress.
2.  [x] Set up `config.mts` with sidebar structure.
3.  [x] Create landing page (`index.md`).
4.  [ ] Create placeholder files for all sections.
5.  [ ] Migrate content from `DESIGN.md` to `architecture/design.md`.
6.  [ ] Write `registry/*.md` guides (Priority).
7.  [ ] Write `guide/*.md` content.

## 4. Next Actions

Start by creating the `registry/` folder and populating the provider guides, as this is the most critical part for users setting up the new authentication system.
