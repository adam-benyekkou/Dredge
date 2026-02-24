"""Policy Enforcement Logic"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from sqlmodel import Session, select

from app.models import ImageArtifact, ImageStatus, CleanupPolicy, RegistryConfig
from app.core.registry import RegistryClientFactory

logger = logging.getLogger(__name__)

class PolicyEnforcer:
    """Enforces cleanup policies on images."""
    
    def __init__(self, session: Session):
        self.session = session
        
    def run_all(self, dry_run: bool = False, ignore_enabled: bool = False) -> Dict[str, Any]:
        """Run all active policies.
        
        Args:
            dry_run: If True, don't actually quarantine images, just return candidates
            ignore_enabled: If True, run all policies regardless of enabled status (for manual runs)
        """
        logger.info(f"PolicyEnforcer.run_all called with dry_run={dry_run}, ignore_enabled={ignore_enabled}")
        
        if ignore_enabled:
            # Manual run - use all policies regardless of enabled status
            policies = self.session.exec(select(CleanupPolicy)).all()
        else:
            # Automated run - only use enabled policies
            policies = self.session.exec(select(CleanupPolicy).where(CleanupPolicy.enabled == True)).all()
            
        logger.info(f"PolicyEnforcer: Found {len(list(policies))} {'total' if ignore_enabled else 'enabled'} policies")
        results = {"quarantined": 0, "errors": 0, "candidates": []}
        
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
            logger.info("PolicyEnforcer: Starting _fetch_all_images()")
            all_images = self._fetch_all_images()
            logger.info(f"PolicyEnforcer: Finished _fetch_all_images(), got {len(all_images)} total images")
            
            for policy in policies:
                quarantine_list = self._apply_policy(policy, all_images, dry_run=dry_run)
                results["quarantined"] += len(quarantine_list)
                results["candidates"].extend(quarantine_list)
            
            if not dry_run and results["quarantined"] > 0:
                from app.core.registry import clear_image_cache
                clear_image_cache()
                
        except Exception as e:
            logger.error(f"Policy run failed: {e}")
            results["errors"] += 1
            
        return results

    def _fetch_all_images(self) -> List[ImageArtifact]:
        """Fetch unified list of images (Mocked for Demo: DB only)."""
        # Demo Mode: Only use images already in the DB (seeded)
        return self.session.exec(select(ImageArtifact)).all()

    def _apply_policy(self, policy: CleanupPolicy, images: List[ImageArtifact], dry_run: bool = False) -> List[ImageArtifact]:
        """Apply a single policy to the image list."""
        logger.info(f"PolicyEnforcer._apply_policy: policy={policy.name}, total_images={len(images)}, keep_count={policy.keep_count}, max_age_days={policy.max_age_days}")
        quarantine_list = []
        
        # Group by Repository (we clean up per repo)
        # Key: "source/repo_name"
        repos: Dict[str, List[ImageArtifact]] = {}
        
        images_without_tags = 0
        for img in images:
            if not img.tags:
                images_without_tags += 1
                continue
            
            # Parse repo name from first tag
            # tag format: "repo:tag" or "host/repo:tag"
            full_tag = img.tags[0]
            repo_name = full_tag.split(":")[0]
            key = f"{img.source}|{repo_name}"
            
            if key not in repos:
                repos[key] = []
            repos[key].append(img)
        
        if images_without_tags > 0:
            logger.warning(f"PolicyEnforcer: Skipped {images_without_tags} images without tags")
        logger.info(f"PolicyEnforcer: Grouped images into {len(repos)} repositories")
        
        total_candidates = 0
            
        # Analyze each repo
        for repo_key, artifacts in repos.items():
            logger.info(f"PolicyEnforcer: Processing repo '{repo_key}' with {len(artifacts)} images")
            # Sort by creation date (newest first)
            # Ensure all are naive for sorting to prevent TypeError
            def get_sort_date(x):
                d = x.created_at or datetime.min
                if d.tzinfo is not None:
                    d = d.replace(tzinfo=None)
                return d

            artifacts.sort(key=get_sort_date, reverse=True)
            
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
            logger.info(f"PolicyEnforcer: Repo '{repo_key}' has {len(artifacts)} images, {len(candidates)} candidates after keep_count={policy.keep_count}")
            
            total_candidates += len(candidates)
            
            for img in candidates:
                should_quarantine = False
                
                # Rule 2: Max Age
                if policy.max_age_days > 0:
                    now = datetime.utcnow()
                    created_at = img.created_at or now
                    
                    # Ensure both are naive for comparison
                    if created_at.tzinfo is not None:
                        created_at = created_at.replace(tzinfo=None)
                    
                    age = now - created_at
                    if age.days > policy.max_age_days:
                        should_quarantine = True
                        logger.debug(f"PolicyEnforcer: Image {img.tags[0] if img.tags else img.digest[:12]} is {age.days} days old (> {policy.max_age_days}), marking for quarantine")
                    else:
                        logger.debug(f"PolicyEnforcer: Image {img.tags[0] if img.tags else img.digest[:12]} is {age.days} days old (<= {policy.max_age_days}), skipping")
                
                # If only keep_count is set (max_age=0), implies "delete everything else"?
                # Usually policies imply "Delete if Older Than X OR (Count > Y AND Older than Z)"
                # Simple logic: If it falls out of "Keep Count", AND exceeds "Max Age" (if set)
                # If Max Age is 0, we might assume purely count-based cleanup?
                # Let's assume strict intersection: Must be outside keep list AND older than max_age (if > 0)
                
                if policy.max_age_days == 0:
                    # Pure count based
                    should_quarantine = True
                
                if should_quarantine:
                    if not dry_run:
                        self._quarantine_image(img, policy)
                    quarantine_list.append(img)
        
        logger.info(f"PolicyEnforcer._apply_policy: Total candidates across all repos: {total_candidates}, quarantined: {len(quarantine_list)}")
        return quarantine_list

    def _quarantine_image(self, image: ImageArtifact, policy: CleanupPolicy):
        """Mark image as quarantined in DB."""
        logger.info(f"PolicyEnforcer._quarantine_image called for image: {image.tags[0] if image.tags else image.digest[:12]}")
        
        # Ensure created_at is naive for DB storage if that's the convention
        created_at = image.created_at
        if created_at and created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)

        # Check if already in DB
        db_image = self.session.exec(select(ImageArtifact).where(ImageArtifact.digest == image.digest)).first()
        
        logger.info(f"PolicyEnforcer: Image {'found' if db_image else 'not found'} in database")
        
        if not db_image:
            # Create new record
            db_image = ImageArtifact(
                tags=image.tags,
                size_bytes=image.size_bytes,
                created_at=created_at,
                digest=image.digest,
                source=image.source,
                status=ImageStatus.QUARANTINED
            )
        else:
            db_image.status = ImageStatus.QUARANTINED
            db_image.created_at = created_at # Update in case it was different
            
        # Set expiry (e.g., 24h from now)
        db_image.expires_at = datetime.utcnow() + timedelta(hours=24)
        self.session.add(db_image)
        
        # Audit log
        from app.models import AuditLog
        audit = AuditLog(
            action="QUARANTINE",
            image_id=image.digest,
            image_tags=image.tags,
            source=image.source,
            bytes_freed=0,
            savings_usd=0.0,
            timestamp=datetime.utcnow()
        )
        self.session.add(audit)
        
        self.session.commit()
        self.session.refresh(db_image)
        
        logger.info(f"PolicyEnforcer: Successfully quarantined image ID={db_image.id}, digest={db_image.digest[:12]}, status={db_image.status}")
        
        from app.core.registry import clear_image_cache
        clear_image_cache()
        logger.info(f"Quarantined image {image.tags} due to policy {policy.name}")
