# Architecture

Dredge follows a **Modular Domain-Driven Design (DDD)** architecture, where logic is divided into self-contained feature modules (Images, Settings, etc.).

## System Overview

```mermaid
graph TB
    subgraph "Client Browser"
        UI[Deep Harbor UI<br/>Jinja2 + HTMX]
    end
    
    subgraph "Dredge Container"
        API[FastAPI<br/>Modular Aggregator]
        subgraph "Modules"
            Images[Images Module<br/>DDD Structure]
            Settings[Settings Module<br/>DDD Structure]
        end
        Auth[Auth Service<br/>JWT + PBKDF2]
        Registry[Registry Client<br/>Docker SDK]
        Models[(SQLModel<br/>SQLite)]
    end
    
    subgraph "Host System"
        Docker[Docker Daemon<br/>/var/run/docker.sock]
        Images[Docker Images<br/>Local Storage]
    end
    
    UI -->|HTTP/HTMX| API
    API -->|Query Images| Registry
    API -->|Calculate Costs| FinOps
    Registry -->|Unix Socket| Docker
    Docker -->|List/Inspect| Images
    API -->|Store Metadata| Models
```

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Dashboard
    participant API
    participant DockerClient
    participant FinOps
    participant Docker
    
    User->>Dashboard: Click "Scan Now"
    Dashboard->>API: POST /scan
    API->>DockerClient: list_images()
    DockerClient->>Docker: GET /images/json
    Docker-->>DockerClient: [Image Data]
    DockerClient-->>API: [ImageArtifact[]]
    
    loop For each image
        API->>FinOps: calculate_monthly_cost(size, provider)
        FinOps-->>API: cost_usd
    end
    
    API->>API: Generate HTML Table
    API-->>Dashboard: HTMX Response (HTML)
    Dashboard->>User: Display Results
```
