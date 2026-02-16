"""Policy Enforcement Logic"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict
from sqlmodel import Session, select

from app.models import ImageArtifact, ImageStatus, CleanupPolicy, RegistryConfig
from app.core.registry import RegistryClientFactory

logger = logging.getLogger(__name__)

class PolicyEnforcer:
    """Enforces cleanup policies on images."""
    
    def __init__(self, session: Session):
        self.session = session
        
    def run_all(self) -> Dict[str, int]:
        """Run all active policies."""
        policies = self.session.exec(select(CleanupPolicy).where(CleanupPolicy.enabled == True)).all()
        results = {"quarantined": 0, "errors": 0}
        
        # 1. Sync latest state from registries (essential before applying policies)
        # In a real background job, we might skip this or do it separately.
        # For manual trigger, we rely on what's in the DB? 
        # Actually, Dredge currently doesn't store ALL images in DB persistently, 
        # it fetches them live for the view.
        # BUT for policies to work, we need persistent tracking OR we filter the live list.
        
        # Strategy:
        # 1. Fetch live images (Local + Remote)
        # 2. Apply rules in memory
        # 3. If rule matches -> Import to DB (if not exists) AND set status=QUARANTINED
        
        try:
            # Fetch all images
            all_images = self._fetch_all_images()
            
            for policy in policies:
                count = self._apply_policy(policy, all_images)
                results["quarantined"] += count
                
        except Exception as e:
            logger.error(f"Policy run failed: {e}")
            results["errors"] += 1
            
        return results

    def _fetch_all_images(self) -> List[ImageArtifact]:
        """Fetch unified list of images from all sources."""
        images = []
        
        # Local
        try:
            local = RegistryClientFactory.get_client().list_images()
            images.extend(local)
        except Exception: 
            pass
            
        # Remote
        remote_configs = self.session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for conf in remote_configs:
            try:
                client = RegistryClientFactory.get_client(conf)
                images.extend(client.list_images())
            except Exception:
                pass
                
        return images

    def _apply_policy(self, policy: CleanupPolicy, images: List[ImageArtifact]) -> int:
        """Apply a single policy to the image list."""
        quarantined_count = 0
        
        # Group by Repository (we clean up per repo)
        # Key: "source/repo_name"
        repos: Dict[str, List[ImageArtifact]] = {}
        
        for img in images:
            if not img.tags: continue
            
            # Parse repo name from first tag
            # tag format: "repo:tag" or "host/repo:tag"
            full_tag = img.tags[0]
            repo_name = full_tag.split(":")[0]
            key = f"{img.source}|{repo_name}"
            
            if key not in repos:
                repos[key] = []
            repos[key].append(img)
            
        # Analyze each repo
        for repo_key, artifacts in repos.items():
            # Sort by creation date (newest first)
            # Handle missing dates
            artifacts.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
            
            # Whitelist Check
            if policy.regex_whitelist:
                try:
                    pattern = re.compile(policy.regex_whitelist)
                    artifacts = [a for a in artifacts if not any(pattern.match(t) for t in a.tags)]
                except re.error:
                    logger.error(f"Invalid regex in policy {policy.name}")
                    continue

            # Rule 1: Keep Count
            # If we have 10 images, and keep_count is 3, we process the remaining 7
            candidates = artifacts[policy.keep_count:]
            
            for img in candidates:
                should_quarantine = False
                
                # Rule 2: Max Age
                if policy.max_age_days > 0:
                    age = datetime.utcnow() - (img.created_at or datetime.utcnow())
                    if age.days > policy.max_age_days:
                        should_quarantine = True
                
                # If only keep_count is set (max_age=0), implies "delete everything else"?
                # Usually policies imply "Delete if Older Than X OR (Count > Y AND Older than Z)"
                # Simple logic: If it falls out of "Keep Count", AND exceeds "Max Age" (if set)
                # If Max Age is 0, we might assume purely count-based cleanup?
                # Let's assume strict intersection: Must be outside keep list AND older than max_age (if > 0)
                
                if policy.max_age_days == 0:
                    # Pure count based
                    should_quarantine = True
                
                if should_quarantine:
                    self._quarantine_image(img, policy)
                    quarantined_count += 1
                    
        return quarantined_count

    def _quarantine_image(self, image: ImageArtifact, policy: CleanupPolicy):
        """Mark image as quarantined in DB."""
        # Check if already in DB
        db_image = self.session.exec(select(ImageArtifact).where(ImageArtifact.digest == image.digest)).first()
        
        if not db_image:
            # Create new record
            db_image = ImageArtifact(
                tags=image.tags,
                size_bytes=image.size_bytes,
                created_at=image.created_at,
                digest=image.digest,
                source=image.source,
                status=ImageStatus.QUARANTINED
            )
        else:
            db_image.status = ImageStatus.QUARANTINED
            
        # Set expiry (e.g., 24h from now)
        db_image.expires_at = datetime.utcnow() + timedelta(hours=24)
        self.session.add(db_image)
        self.session.commit()
        logger.info(f"Quarantined image {image.tags} due to policy {policy.name}")
