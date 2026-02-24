"""Policy scheduler for automated policy execution"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from sqlmodel import Session, select

from app.core.db import engine
from app.core.policies import PolicyEnforcer
from app.models import CleanupPolicy
from app.core.finops import check_budget
from app.core.analytics import capture_daily_snapshot

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance"""
    global scheduler
    
    if scheduler is None:
        jobstores = {
            'default': MemoryJobStore()
        }
        
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone='UTC'
        )
    
    return scheduler


async def run_scheduled_policy(policy_id: int):
    """Execute a policy on schedule"""
    logger.info(f"Executing scheduled policy ID={policy_id}")
    
    try:
        with Session(engine) as session:
            # Also run budget check when policies run (as it's a good time to check)
            await check_budget(session)
            
            policy = session.get(CleanupPolicy, policy_id)
            
            if not policy:
                logger.error(f"Policy {policy_id} not found")
                return
            
            if not policy.enabled:
                logger.info(f"Policy {policy_id} is disabled, skipping")
                return
            
            # Run policy
            enforcer = PolicyEnforcer(session)
            # ignore_enabled=False because we only want to run ENABLED policies if scheduled
            # but wait, if it's scheduled it should probably run.
            # Task 3.3 says ignore_enabled=False.
            result = enforcer.run_all(dry_run=False, ignore_enabled=False)
            
            # Update policy metadata
            policy.last_run = datetime.utcnow()
            policy.run_count += 1
            session.add(policy)
            session.commit()
            
            logger.info(
                f"Policy {policy.name} executed: "
                f"quarantined={result['quarantined']}, errors={result['errors']}"
            )
            
    except Exception as e:
        logger.error(f"Failed to execute scheduled policy {policy_id}: {e}", exc_info=True)


def schedule_policy(policy: CleanupPolicy):
    """Add or update a policy in the scheduler"""
    sched = get_scheduler()
    job_id = f"policy_{policy.id}"
    
    # Remove existing job if it exists
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    
    # Only schedule if enabled and has cron expression
    if policy.schedule_enabled and policy.schedule_cron:
        try:
            trigger = CronTrigger.from_crontab(policy.schedule_cron, timezone='UTC')
            
            sched.add_job(
                run_scheduled_policy,
                trigger=trigger,
                args=[policy.id],
                id=job_id,
                name=f"Policy: {policy.name}",
                replace_existing=True
            )
            
            # Calculate next run time
            next_run = trigger.get_next_fire_time(None, datetime.utcnow())
            
            # Update policy with next run time
            with Session(engine) as session:
                db_policy = session.get(CleanupPolicy, policy.id)
                if db_policy:
                    db_policy.next_run = next_run
                    session.add(db_policy)
                    session.commit()
            
            logger.info(f"Scheduled policy '{policy.name}' with cron '{policy.schedule_cron}'")
            
        except Exception as e:
            logger.error(f"Failed to schedule policy {policy.id}: {e}", exc_info=True)


def unschedule_policy(policy_id: int):
    """Remove a policy from the scheduler"""
    sched = get_scheduler()
    job_id = f"policy_{policy_id}"
    
    if sched.get_job(job_id):
        sched.remove_job(job_id)
        logger.info(f"Unscheduled policy ID={policy_id}")


def load_all_policies():
    """Load all scheduled policies from database on startup"""
    logger.info("Loading scheduled policies from database")
    
    with Session(engine) as session:
        statement = select(CleanupPolicy).where(
            CleanupPolicy.schedule_enabled == True
        )
        policies = session.exec(statement).all()
        
        for policy in policies:
            schedule_policy(policy)
        
        logger.info(f"Loaded {len(policies)} scheduled policies")


def start_scheduler():
    """Start the scheduler (call on app startup)"""
    sched = get_scheduler()
    
    if not sched.running:
        sched.start()
        logger.info("Policy scheduler started")
        
        # Load existing policies
        load_all_policies()
        
        # Add daily budget check (9am UTC)
        sched.add_job(
            run_daily_budget_check,
            trigger=CronTrigger.from_crontab('0 9 * * *', timezone='UTC'),
            id='daily_budget_check',
            replace_existing=True
        )
        
        # Add daily metric snapshot (23:59 UTC)
        sched.add_job(
            run_daily_snapshot,
            trigger=CronTrigger.from_crontab('59 23 * * *', timezone='UTC'),
            id='daily_metric_snapshot',
            replace_existing=True
        )
        # Add daily metric snapshot (23:59 UTC)
        sched.add_job(
            ping_registries,
            trigger=CronTrigger.from_crontab('*/5 * * * *'), # Every 5 minutes
            id='ping_registries',
            replace_existing=True
        )

async def run_daily_budget_check():
    """Execute daily budget check"""
    try:
        with Session(engine) as session:
            await check_budget(session)
            logger.info("Executed daily budget check")
    except Exception as e:
        logger.error(f"Failed to execute budget check: {e}", exc_info=True)

async def ping_registries():
    """Background health check for all active registries"""
    from app.core.registry import RegistryClientFactory
    try:
        with Session(engine) as session:
            statement = select(RegistryConfig).where(RegistryConfig.is_active == True)
            registries = session.exec(statement).all()
            
            for registry in registries:
                try:
                    client = RegistryClientFactory.get_client(registry)
                    result = client.test_connection()
                    
                    if not result["success"]:
                        logger.warning(f"Health check failed for {registry.name}: {result['message']}")
                        # We don't auto-disable for network errors, only for clear Auth failures
                        if result.get("type") == "AUTH_ERROR":
                            logger.error(f"AUTHENTICATION FAILURE for {registry.name}. Disabling registry.")
                            registry.is_active = False
                            session.add(registry)
                except Exception as e:
                    logger.error(f"Error checking health for {registry.name}: {e}")
            
            session.commit()
    except Exception as e:
        logger.error(f"ping_registries task failed: {e}")

async def run_daily_snapshot():
    """Capture daily metrics snapshot"""
    try:
        with Session(engine) as session:
            await capture_daily_snapshot(session)
    except Exception as e:
        logger.error(f"Failed to capture daily snapshot: {e}", exc_info=True)


def shutdown_scheduler():
    """Shutdown the scheduler (call on app shutdown)"""
    sched = get_scheduler()
    
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("Policy scheduler stopped")
