
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
        
        log = AuditLog(
            action=action,
            image_id=img.digest,
            image_tags=img.tags,
            source=img.source,
            bytes_freed=img.size_bytes if action in ["DELETE", "PURGE"] else 0,
            savings_usd=random.uniform(0.01, 2.50) if action in ["DELETE", "PURGE"] else 0,
            timestamp=base_date + timedelta(days=random.randint(0, 30), hours=random.randint(0, 23)),
            dry_run=False
        )
        session.add(log)
    session.commit()

def create_metrics_history(session: Session):
    print("Creating metrics history...")
    base_date = datetime.utcnow() - timedelta(days=30)
    base_cost = 45.0
    base_gb = 120.0
    
    for i in range(30):
        date = base_date + timedelta(days=i)
        # Add some trends (increasing over time)
        cost = base_cost + (i * 0.8) + random.uniform(-2, 5)
        gb = base_gb + (i * 2.0) + random.uniform(-5, 10)
        
        snapshot = MetricSnapshot(
            date=date,
            total_images=50 + int(i/2),
            total_volumes=12 + int(i/5),
            total_gb=max(10, gb),
            total_cost_usd=max(5, cost),
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
        create_audit_logs(session, images)
        create_metrics_history(session)
        
    print("Seeding complete! 🚀")

if __name__ == "__main__":
    main()
