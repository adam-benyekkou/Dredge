
import random
from datetime import datetime, timedelta
import json
from sqlmodel import Session, select, delete
from app.core.db import engine, init_db
from app.models import (
    ImageArtifact, VolumeArtifact, AuditLog, RegistryConfig, 
    MetricSnapshot, ImageStatus, VolumeStatus, RegistryType, 
    AppSettings, CleanupPolicy
)

# Map registry source names to price per GB (matches PROVIDER_PRICES in finops.py)
SOURCE_PRICE_MAP = {
    "Local":              0.10,   # Default/ECR
    "Docker Hub Prod":    0.00,   # Docker Hub fair use
    "GHCR CI":            0.25,   # GitHub Packages
    "AWS ECR us-east-1":  0.10,   # AWS ECR
    "Azure ACR":          0.09,   # Azure ACR
}

def clear_data(session: Session):
    print("Clearing existing data...")
    session.exec(delete(ImageArtifact))
    session.exec(delete(VolumeArtifact))
    session.exec(delete(AuditLog))
    session.exec(delete(RegistryConfig))
    session.exec(delete(MetricSnapshot))
    session.commit()

def create_registries(session: Session):
    print("Creating registries...")
    registries = [
        RegistryConfig(name="Docker Hub Prod", type=RegistryType.DOCKERHUB, endpoint="https://registry-1.docker.io", username="dredge_user", is_active=True),
        RegistryConfig(name="GHCR CI", type=RegistryType.GHCR, endpoint="https://ghcr.io", username="dredge_bot", is_active=True),
        RegistryConfig(name="AWS ECR us-east-1", type=RegistryType.ECR, endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com", is_active=True),
        RegistryConfig(name="Azure ACR", type=RegistryType.ACR, endpoint="dredge.azurecr.io", is_active=False),
    ]
    for reg in registries:
        session.add(reg)
    session.commit()
    return registries

def create_images(session: Session, registries):
    print("Creating images...")
    sources = ["Local"] + [r.name for r in registries]
    
    apps = [
        ("nginx", "1.19", 50 * 1024**2),
        ("nginx", "alpine", 20 * 1024**2),
        ("postgres", "14", 150 * 1024**2),
        ("postgres", "14-alpine", 80 * 1024**2),
        ("node", "16", 900 * 1024**2),
        ("node", "16-slim", 200 * 1024**2),
        ("python", "3.9", 950 * 1024**2),
        ("python", "3.9-slim", 120 * 1024**2),
        ("redis", "6", 100 * 1024**2),
        ("ubuntu", "20.04", 70 * 1024**2),
        ("my-app", "latest", 450 * 1024**2),
        ("ml-model", "v1", 2.5 * 1024**3), # Huge
        ("legacy-monolith", "v2021", 1.8 * 1024**3),
    ]
    
    images = []
    base_date = datetime.utcnow() - timedelta(days=60)
    
    for i in range(50):
        app, tag, base_size = random.choice(apps)
        source = random.choice(sources)
        
        # Randomize size slightly
        size = int(base_size * random.uniform(0.9, 1.1))
        
        # Bloat score logic
        bloat_score = 100
        issues = []
        if size > 1000 * 1024**2:
            bloat_score -= 40
            issues.append(f"Huge image size ({size/1024**2:.0f}MB)")
        elif size > 500 * 1024**2:
            bloat_score -= 20
            issues.append(f"Large image size ({size/1024**2:.0f}MB)")
            
        if "alpine" not in tag and "slim" not in tag and size > 200 * 1024**2:
            bloat_score -= 20
            issues.append("Base image appears unoptimized")
            
        bloat_score = max(0, bloat_score)
        
        # Status distribution
        r = random.random()
        status = ImageStatus.ACTIVE
        expires_at = None
        if r > 0.8:
            status = ImageStatus.QUARANTINED
            expires_at = datetime.utcnow() + timedelta(hours=random.randint(1, 23))
        
        # Create
        created_at = base_date + timedelta(days=random.randint(0, 60))
        full_tag = f"{source.lower().replace(' ', '')}/{app}:{tag}" if source != "Local" else f"{app}:{tag}"
        
        img = ImageArtifact(
            tags=[full_tag],
            size_bytes=size,
            created_at=created_at,
            digest=f"sha256:{random.getrandbits(256):064x}",
            source=source,
            status=status,
            expires_at=expires_at,
            bloat_score=bloat_score,
            bloat_issues=json.dumps(issues) if issues else None
        )
        session.add(img)
        images.append(img)
        
    # Deterministic untagged (dangling) images — always show waste in dashboard
    untagged_specs = [
        ("Local",             320 * 1024**2),
        ("Local",             510 * 1024**2),
        ("Docker Hub Prod",   180 * 1024**2),
        ("GHCR CI",           740 * 1024**2),
        ("AWS ECR us-east-1", 260 * 1024**2),
        ("Local",             90  * 1024**2),
        ("GHCR CI",           1.1 * 1024**3),
        ("Local",             430 * 1024**2),
    ]
    for idx, (src, sz) in enumerate(untagged_specs):
        img = ImageArtifact(
            tags=["<none>:<none>"],
            size_bytes=int(sz),
            created_at=base_date + timedelta(days=idx * 7),
            digest=f"sha256:untagged{idx:056d}",
            source=src,
            status=ImageStatus.ACTIVE,
            bloat_score=0,
            bloat_issues=json.dumps(["Untagged dangling image"]),
        )
        session.add(img)
        images.append(img)

    session.commit()
    return images

def create_volumes(session: Session):
    print("Creating volumes...")
    volumes = []
    base_date = datetime.utcnow() - timedelta(days=60)
    
    names = ["pg_data", "redis_data", "app_logs", "prometheus_data", "grafana_storage", "unused_vol_1", "backup_tmp"]
    
    for i in range(20):
        name = f"{random.choice(names)}_{i}"
        status = VolumeStatus.DANGLING if random.random() > 0.7 else VolumeStatus.ACTIVE
        size = random.randint(100, 5000) * 1024**2 # 100MB to 5GB
        
        vol = VolumeArtifact(
            name=name,
            driver="local",
            size_bytes=size,
            created_at=base_date + timedelta(days=random.randint(0, 60)),
            status=status,
            source="Local",
            labels=['com.docker.compose.project=dredge'] if random.random() > 0.5 else []
        )
        session.add(vol)
        volumes.append(vol)
        
    session.commit()

def create_audit_logs(session: Session, images):
    print("Creating audit logs...")
    actions = ["DELETE", "PURGE", "QUARANTINE", "UNQUARANTINE"]
    base_date = datetime.utcnow() - timedelta(days=30)
    
    for i in range(100):
        action = random.choice(actions)
        img = random.choice(images)
        # Calculate realistic savings based on provider pricing
        price_per_gb = SOURCE_PRICE_MAP.get(img.source, 0.10)
        size_gb = img.size_bytes / (1024 ** 3)
        savings = size_gb * price_per_gb if action in ["DELETE", "PURGE"] else 0
        log = AuditLog(
            action=action,
            image_id=img.digest,
            image_tags=img.tags,
            source=img.source,
            bytes_freed=img.size_bytes if action in ["DELETE", "PURGE"] else 0,
            savings_usd=round(savings, 4),
            timestamp=base_date + timedelta(days=random.randint(0, 30), hours=random.randint(0, 23)),
            dry_run=False
        )
        session.add(log)
    session.commit()

def create_metrics_history(session: Session):
    print("Creating metrics history...")
    base_date = datetime.utcnow() - timedelta(days=30)
    base_gb = 120.0
    for i in range(30):
        date = base_date + timedelta(days=i)
        gb = base_gb + (i * 2.0) + random.uniform(-5, 10)
        gb = max(10, gb)
        # Realistic cost: ~60% Local/ECR ($0.10), 20% GHCR ($0.25), 20% Docker Hub ($0.00)
        avg_price_per_gb = 0.60 * 0.10 + 0.20 * 0.25 + 0.20 * 0.00  # ~$0.11/GB
        cost = gb * avg_price_per_gb + random.uniform(-0.5, 1.0)
        snapshot = MetricSnapshot(
            date=date,
            total_images=50 + int(i/2),
            total_volumes=12 + int(i/5),
            total_gb=gb,
            total_cost_usd=max(0.5, round(cost, 2)),
            efficiency_score=int(80 - (i * 0.5))
        )
        session.add(snapshot)
    session.commit()

def main():
    print("Initializing DB...")
    init_db()
    
    with Session(engine) as session:
        clear_data(session)
        registries = create_registries(session)
        images = create_images(session, registries)
        create_volumes(session)
        
        # Update AppSettings with real provider pricing
        settings = session.get(AppSettings, 1)
        if not settings:
            settings = AppSettings(id=1)
        settings.custom_price_per_gb = 0.10
        settings.dockerhub_price_per_gb = 0.00
        settings.ghcr_price_per_gb = 0.25
        settings.github_hrc_price_per_gb = 0.07
        settings.provider_name = "AWS"
        session.add(settings)
        session.commit()
        print("Updated AppSettings with provider pricing.")
        create_audit_logs(session, images)
        create_metrics_history(session)
        
    print("Seeding complete! 🚀")

if __name__ == "__main__":
    main()
