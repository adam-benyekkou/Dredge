# Dredge Enhancement Tasks

## Task Group 1: Audit Log Template Fixes

### Task 1.1: Update Audit Log Template to Show New Action Types

**Priority**: High  
**Effort**: 1 hour  
**File**: `templates/logs.html`

**Current Problem**:
- Template only shows "DRY RUN" or "PURGED" (lines 37-41)
- Doesn't display new action types: `QUARANTINE`, `UNQUARANTINE`, `PURGE`, `DELETE`
- Missing `source` column from display

**Changes Required**:

1. **Replace action display logic** (lines 36-42):
   ```html
   <!-- OLD CODE (lines 36-42) -->
   <td>
       {% if log.dry_run %}
           <span style="color: var(--accent); font-weight: 600;">DRY RUN</span>
       {% else %}
           <span style="color: var(--danger); font-weight: 600;">PURGED</span>
       {% endif %}
   </td>
   
   <!-- NEW CODE -->
   <td>
       {% if log.action == "QUARANTINE" %}
           <span class="badge badge-warning">QUARANTINE</span>
       {% elif log.action == "UNQUARANTINE" %}
           <span class="badge badge-success">UNQUARANTINE</span>
       {% elif log.action == "PURGE" %}
           <span class="badge badge-danger">PURGE</span>
       {% elif log.action == "DELETE" %}
           <span class="badge badge-danger">DELETE</span>
       {% else %}
           <span class="badge badge-muted">{{ log.action }}</span>
       {% endif %}
       {% if log.dry_run %}
           <span class="badge badge-info" style="margin-left: 0.5rem;">DRY RUN</span>
       {% endif %}
   </td>
   ```

2. **Add source column** to table header (line 24):
   ```html
   <!-- AFTER line 27 -->
   <th>Source</th>
   ```

3. **Add source column** to table body (after line 46):
   ```html
   <!-- AFTER line 46 -->
   <td>
       <span class="badge badge-secondary">{{ log.source }}</span>
   </td>
   ```

4. **Update empty state colspan** (line 53):
   ```html
   <!-- Change from colspan="5" to colspan="6" -->
   <td colspan="6" style="text-align: center;">
   ```

5. **Add badge CSS** to `static/css/theme.css`:
   ```css
   .badge {
       display: inline-block;
       padding: 0.25rem 0.5rem;
       font-size: 0.75rem;
       font-weight: 600;
       border-radius: 4px;
   }
   
   .badge-warning {
       background: #f59e0b;
       color: #000;
   }
   
   .badge-success {
       background: #10b981;
       color: #fff;
   }
   
   .badge-danger {
       background: #ef4444;
       color: #fff;
   }
   
   .badge-info {
       background: #3b82f6;
       color: #fff;
   }
   
   .badge-secondary {
       background: #6b7280;
       color: #fff;
   }
   
   .badge-muted {
       background: #374151;
       color: #9ca3af;
   }
   ```

**Acceptance Criteria**:
- [ ] QUARANTINE actions show orange "QUARANTINE" badge
- [ ] UNQUARANTINE actions show green "UNQUARANTINE" badge
- [ ] PURGE actions show red "PURGE" badge
- [ ] DELETE actions show red "DELETE" badge
- [ ] DRY RUN badge appears alongside action badge when applicable
- [ ] Source column displays registry name
- [ ] Empty state colspan updated to 6

---

## Task Group 2: Pagination & Filters for Audit Log

### Task 2.1: Add Backend Pagination Support

**Priority**: High  
**Effort**: 2 hours  
**File**: `app/web/routes.py`

**Current Problem**:
- Hard limit of 50 logs (line 230)
- No pagination controls
- No way to view older logs

**Changes Required**:

1. **Update `/logs` route** (lines 226-241):
   ```python
   @router.get("/logs", response_class=HTMLResponse)
   async def logs_view(
       request: Request,
       session: Session = Depends(get_session),
       page: int = 1,
       limit: int = 50
   ):
       """Render the logs view with pagination"""
       # Calculate offset
       offset = (page - 1) * limit
       
       # Get total count
       total_count = session.exec(select(func.count(AuditLog.id))).one()
       
       # Fetch paginated logs
       statement = (
           select(AuditLog)
           .order_by(col(AuditLog.timestamp).desc())
           .limit(limit)
           .offset(offset)
       )
       logs = session.exec(statement).all()
       
       # Calculate pagination metadata
       total_pages = (total_count + limit - 1) // limit
       has_prev = page > 1
       has_next = page < total_pages
       
       settings = session.get(AppSettings, 1)
       
       return templates.TemplateResponse(
           request,
           "logs.html",
           {
               "logs": logs,
               "settings": settings,
               "page": page,
               "limit": limit,
               "total_count": total_count,
               "total_pages": total_pages,
               "has_prev": has_prev,
               "has_next": has_next,
           }
       )
   ```

2. **Add imports** at top of file:
   ```python
   from sqlalchemy import func
   ```

**Acceptance Criteria**:
- [ ] Route accepts `page` and `limit` query parameters
- [ ] Default page=1, limit=50
- [ ] Returns pagination metadata to template
- [ ] Offset calculation correct: (page - 1) * limit

---

### Task 2.2: Add Frontend Pagination Controls

**Priority**: High  
**Effort**: 1.5 hours  
**File**: `templates/logs.html`

**Changes Required**:

1. **Add pagination controls** after `</table>` (after line 59):
   ```html
   {% if total_pages > 1 %}
   <nav aria-label="Audit log pagination" style="margin-top: 2rem; display: flex; justify-content: center; align-items: center; gap: 1rem;">
       <!-- Previous button -->
       {% if has_prev %}
           <a href="/logs?page={{ page - 1 }}&limit={{ limit }}" 
              class="btn btn-secondary"
              style="padding: 0.5rem 1rem;">
               <i data-lucide="chevron-left" style="width: 16px; height: 16px;"></i>
               Previous
           </a>
       {% else %}
           <button class="btn btn-secondary" disabled style="padding: 0.5rem 1rem; opacity: 0.5;">
               <i data-lucide="chevron-left" style="width: 16px; height: 16px;"></i>
               Previous
           </button>
       {% endif %}
       
       <!-- Page info -->
       <span style="color: var(--text-muted);">
           Page {{ page }} of {{ total_pages }} ({{ total_count }} total)
       </span>
       
       <!-- Next button -->
       {% if has_next %}
           <a href="/logs?page={{ page + 1 }}&limit={{ limit }}"
              class="btn btn-secondary"
              style="padding: 0.5rem 1rem;">
               Next
               <i data-lucide="chevron-right" style="width: 16px; height: 16px;"></i>
           </a>
       {% else %}
           <button class="btn btn-secondary" disabled style="padding: 0.5rem 1rem; opacity: 0.5;">
               Next
               <i data-lucide="chevron-right" style="width: 16px; height: 16px;"></i>
           </button>
       {% endif %}
   </nav>
   
   <!-- Page size selector -->
   <div style="margin-top: 1rem; text-align: center;">
       <label style="color: var(--text-muted); font-size: 0.9rem;">
           Items per page:
           <select onchange="window.location.href='/logs?page=1&limit=' + this.value"
                   style="margin-left: 0.5rem; padding: 0.25rem;">
               <option value="25" {% if limit == 25 %}selected{% endif %}>25</option>
               <option value="50" {% if limit == 50 %}selected{% endif %}>50</option>
               <option value="100" {% if limit == 100 %}selected{% endif %}>100</option>
               <option value="200" {% if limit == 200 %}selected{% endif %}>200</option>
           </select>
       </label>
   </div>
   {% endif %}
   ```

2. **Update Lucide icons call** (line 76):
   ```javascript
   // Add after line 75
   lucide.createIcons();
   ```

**Acceptance Criteria**:
- [ ] Pagination controls appear when total_pages > 1
- [ ] Previous/Next buttons work correctly
- [ ] Previous button disabled on page 1
- [ ] Next button disabled on last page
- [ ] Page info displays current page, total pages, total count
- [ ] Page size selector changes items per page
- [ ] Selecting new page size resets to page 1

---

### Task 2.3: Add Filter Backend Support

**Priority**: Medium  
**Effort**: 2 hours  
**File**: `app/web/routes.py`

**Changes Required**:

1. **Update `/logs` route** to accept filter parameters:
   ```python
   @router.get("/logs", response_class=HTMLResponse)
   async def logs_view(
       request: Request,
       session: Session = Depends(get_session),
       page: int = 1,
       limit: int = 50,
       action_filter: Optional[str] = None,
       source_filter: Optional[str] = None,
       date_from: Optional[str] = None,
       date_to: Optional[str] = None
   ):
       """Render the logs view with pagination and filters"""
       # Build base query
       statement = select(AuditLog)
       
       # Apply action filter
       if action_filter and action_filter != "ALL":
           statement = statement.where(AuditLog.action == action_filter)
       
       # Apply source filter
       if source_filter and source_filter != "ALL":
           statement = statement.where(AuditLog.source == source_filter)
       
       # Apply date range filter
       if date_from:
           try:
               from_date = datetime.strptime(date_from, "%Y-%m-%d")
               statement = statement.where(AuditLog.timestamp >= from_date)
           except ValueError:
               pass
       
       if date_to:
           try:
               to_date = datetime.strptime(date_to, "%Y-%m-%d")
               # Add 1 day to include the entire end date
               to_date = to_date + timedelta(days=1)
               statement = statement.where(AuditLog.timestamp < to_date)
           except ValueError:
               pass
       
       # Get total count with filters applied
       count_statement = select(func.count()).select_from(statement.alias())
       total_count = session.exec(count_statement).one()
       
       # Calculate offset
       offset = (page - 1) * limit
       
       # Fetch paginated logs
       statement = statement.order_by(col(AuditLog.timestamp).desc()).limit(limit).offset(offset)
       logs = session.exec(statement).all()
       
       # Calculate pagination metadata
       total_pages = max(1, (total_count + limit - 1) // limit)
       has_prev = page > 1
       has_next = page < total_pages
       
       # Get unique actions and sources for filter dropdowns
       unique_actions = session.exec(
           select(AuditLog.action).distinct().order_by(AuditLog.action)
       ).all()
       unique_sources = session.exec(
           select(AuditLog.source).distinct().order_by(AuditLog.source)
       ).all()
       
       settings = session.get(AppSettings, 1)
       
       return templates.TemplateResponse(
           request,
           "logs.html",
           {
               "logs": logs,
               "settings": settings,
               "page": page,
               "limit": limit,
               "total_count": total_count,
               "total_pages": total_pages,
               "has_prev": has_prev,
               "has_next": has_next,
               "action_filter": action_filter or "ALL",
               "source_filter": source_filter or "ALL",
               "date_from": date_from or "",
               "date_to": date_to or "",
               "unique_actions": unique_actions,
               "unique_sources": unique_sources,
           }
       )
   ```

2. **Add imports**:
   ```python
   from typing import Optional
   from datetime import timedelta
   ```

**Acceptance Criteria**:
- [ ] Route accepts action_filter, source_filter, date_from, date_to
- [ ] Filters are optional (default to showing all)
- [ ] Date parsing handles invalid formats gracefully
- [ ] Total count reflects filtered results
- [ ] Returns unique actions and sources for dropdowns

---

### Task 2.4: Add Filter Frontend Controls

**Priority**: Medium  
**Effort**: 2 hours  
**File**: `templates/logs.html`

**Changes Required**:

1. **Add filter form** before table (after line 19):
   ```html
   <form method="get" action="/logs" style="margin-bottom: 2rem; padding: 1.5rem; background: var(--surface-2); border-radius: 8px;">
       <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
           <!-- Action filter -->
           <div>
               <label for="action-filter" style="display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem;">
                   Action
               </label>
               <select name="action_filter" id="action-filter" style="width: 100%;">
                   <option value="ALL" {% if action_filter == "ALL" %}selected{% endif %}>All Actions</option>
                   {% for action in unique_actions %}
                   <option value="{{ action }}" {% if action_filter == action %}selected{% endif %}>
                       {{ action }}
                   </option>
                   {% endfor %}
               </select>
           </div>
           
           <!-- Source filter -->
           <div>
               <label for="source-filter" style="display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem;">
                   Source
               </label>
               <select name="source_filter" id="source-filter" style="width: 100%;">
                   <option value="ALL" {% if source_filter == "ALL" %}selected{% endif %}>All Sources</option>
                   {% for source in unique_sources %}
                   <option value="{{ source }}" {% if source_filter == source %}selected{% endif %}>
                       {{ source }}
                   </option>
                   {% endfor %}
               </select>
           </div>
           
           <!-- Date from -->
           <div>
               <label for="date-from" style="display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem;">
                   From Date
               </label>
               <input type="date" name="date_from" id="date-from" value="{{ date_from }}" style="width: 100%;">
           </div>
           
           <!-- Date to -->
           <div>
               <label for="date-to" style="display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem;">
                   To Date
               </label>
               <input type="date" name="date_to" id="date-to" value="{{ date_to }}" style="width: 100%;">
           </div>
       </div>
       
       <div style="margin-top: 1rem; display: flex; gap: 1rem;">
           <button type="submit" class="btn btn-primary" style="padding: 0.5rem 1.5rem;">
               <i data-lucide="filter" style="width: 14px; height: 14px; margin-right: 0.5rem; vertical-align: middle;"></i>
               Apply Filters
           </button>
           <a href="/logs" class="btn btn-secondary" style="padding: 0.5rem 1.5rem; text-decoration: none;">
               <i data-lucide="x" style="width: 14px; height: 14px; margin-right: 0.5rem; vertical-align: middle;"></i>
               Clear Filters
           </a>
       </div>
       
       <!-- Hidden fields to preserve pagination when filtering -->
       <input type="hidden" name="page" value="1">
       <input type="hidden" name="limit" value="{{ limit }}">
   </form>
   ```

2. **Update pagination links** to preserve filters:
   ```html
   <!-- Update Previous button href (around line 66) -->
   <a href="/logs?page={{ page - 1 }}&limit={{ limit }}&action_filter={{ action_filter }}&source_filter={{ source_filter }}&date_from={{ date_from }}&date_to={{ date_to }}"
   
   <!-- Update Next button href -->
   <a href="/logs?page={{ page + 1 }}&limit={{ limit }}&action_filter={{ action_filter }}&source_filter={{ source_filter }}&date_from={{ date_from }}&date_to={{ date_to }}"
   
   <!-- Update page size selector -->
   <select onchange="updatePageSize(this.value)">
   
   <!-- Add JavaScript helper -->
   <script>
   function updatePageSize(newLimit) {
       const params = new URLSearchParams(window.location.search);
       params.set('limit', newLimit);
       params.set('page', '1');
       window.location.href = '/logs?' + params.toString();
   }
   </script>
   ```

**Acceptance Criteria**:
- [ ] Filter form appears above table
- [ ] Action dropdown populated with unique actions from database
- [ ] Source dropdown populated with unique sources
- [ ] Date pickers allow selecting date ranges
- [ ] Apply Filters button submits form
- [ ] Clear Filters button resets to /logs with no params
- [ ] Pagination preserves active filters
- [ ] Page size selector preserves active filters
- [ ] Filtering resets to page 1

---

### Task 2.5: Update CSV Export to Respect Filters

**Priority**: Low  
**Effort**: 1 hour  
**File**: `templates/logs.html`

**Changes Required**:

1. **Update exportLogs function** (lines 63-75):
   ```javascript
   function exportLogs() {
       // Get current filters from URL
       const params = new URLSearchParams(window.location.search);
       
       // Build export URL with filters
       const exportUrl = '/logs/export?' + params.toString();
       
       // Trigger download
       window.location.href = exportUrl;
   }
   ```

2. **Create export route** in `app/web/routes.py`:
   ```python
   @router.get("/logs/export")
   async def export_logs(
       request: Request,
       session: Session = Depends(get_session),
       action_filter: Optional[str] = None,
       source_filter: Optional[str] = None,
       date_from: Optional[str] = None,
       date_to: Optional[str] = None
   ):
       """Export audit logs to CSV with filters applied"""
       from fastapi.responses import StreamingResponse
       import csv
       from io import StringIO
       
       # Build query with same filter logic as logs_view
       statement = select(AuditLog)
       
       if action_filter and action_filter != "ALL":
           statement = statement.where(AuditLog.action == action_filter)
       
       if source_filter and source_filter != "ALL":
           statement = statement.where(AuditLog.source == source_filter)
       
       if date_from:
           try:
               from_date = datetime.strptime(date_from, "%Y-%m-%d")
               statement = statement.where(AuditLog.timestamp >= from_date)
           except ValueError:
               pass
       
       if date_to:
           try:
               to_date = datetime.strptime(date_to, "%Y-%m-%d")
               to_date = to_date + timedelta(days=1)
               statement = statement.where(AuditLog.timestamp < to_date)
           except ValueError:
               pass
       
       statement = statement.order_by(col(AuditLog.timestamp).desc())
       logs = session.exec(statement).all()
       
       # Get settings for currency symbol
       settings = session.get(AppSettings, 1)
       symbol = settings.currency_symbol if settings else "$"
       
       # Create CSV
       output = StringIO()
       writer = csv.writer(output)
       
       # Write header
       writer.writerow([
           "Timestamp",
           "Action",
           "Source",
           "Image/Resource",
           "Image ID",
           "Space Freed (GB)",
           f"Monthly Savings ({symbol})",
           "Dry Run"
       ])
       
       # Write data
       for log in logs:
           writer.writerow([
               log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
               log.action,
               log.source,
               log.image_tags[0] if log.image_tags else log.image_id[:20],
               log.image_id,
               round(log.bytes_freed / (1024**3), 2),
               round(log.savings_usd, 2),
               "Yes" if log.dry_run else "No"
           ])
       
       # Return as downloadable file
       output.seek(0)
       filename = f"dredge_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
       
       return StreamingResponse(
           iter([output.getvalue()]),
           media_type="text/csv",
           headers={"Content-Disposition": f"attachment; filename={filename}"}
       )
   ```

**Acceptance Criteria**:
- [ ] Export button respects active filters
- [ ] CSV includes all columns with proper headers
- [ ] Filename includes timestamp
- [ ] Export route applies same filters as main view
- [ ] No pagination limit on export (exports all matching logs)

---

## Task Group 3: Policy Automation

### Task 3.1: Add Scheduler Dependencies

**Priority**: High  
**Effort**: 30 minutes  
**File**: `requirements.txt`

**Changes Required**:

1. **Add APScheduler**:
   ```txt
   apscheduler==3.10.4
   ```

2. **Install dependencies**:
   ```bash
   pip install apscheduler==3.10.4
   ```

**Acceptance Criteria**:
- [ ] APScheduler added to requirements.txt
- [ ] Dependencies installed successfully
- [ ] No version conflicts

---

### Task 3.2: Extend CleanupPolicy Model

**Priority**: High  
**Effort**: 1 hour  
**File**: `app/models.py`

**Changes Required**:

1. **Add scheduling fields** to CleanupPolicy (lines 99-120):
   ```python
   class CleanupPolicy(SQLModel, table=True):
       """Cleanup policy for automated image lifecycle management."""
       
       id: Optional[int] = Field(default=None, primary_key=True)
       name: str = Field(max_length=255)
       keep_count: int = Field(default=3, ge=0)
       max_age_days: int = Field(default=30, ge=0)
       regex_whitelist: str = Field(default="", max_length=500)
       enabled: bool = Field(default=True)
       created_at: datetime = Field(default_factory=datetime.utcnow)
       
       # NEW FIELDS
       schedule_enabled: bool = Field(default=False)  # Whether to run on schedule
       schedule_cron: Optional[str] = Field(default=None, max_length=100)  # Cron expression
       next_run: Optional[datetime] = Field(default=None)  # Next scheduled run time
       last_run: Optional[datetime] = Field(default=None)  # Last execution time
       run_count: int = Field(default=0)  # Total number of executions
   ```

2. **Create database migration**:
   ```bash
   # Manual SQL migration or Alembic
   ALTER TABLE cleanuppolicy ADD COLUMN schedule_enabled BOOLEAN DEFAULT FALSE;
   ALTER TABLE cleanuppolicy ADD COLUMN schedule_cron VARCHAR(100);
   ALTER TABLE cleanuppolicy ADD COLUMN next_run TIMESTAMP;
   ALTER TABLE cleanuppolicy ADD COLUMN last_run TIMESTAMP;
   ALTER TABLE cleanuppolicy ADD COLUMN run_count INTEGER DEFAULT 0;
   ```

**Acceptance Criteria**:
- [ ] New fields added to model
- [ ] Database schema updated
- [ ] Existing policies have schedule_enabled=False by default
- [ ] No data loss during migration

---

### Task 3.3: Create Policy Scheduler Service

**Priority**: High  
**Effort**: 3 hours  
**File**: `app/core/scheduler.py` (new file)

**Changes Required**:

1. **Create scheduler service**:
   ```python
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
               policy = session.get(CleanupPolicy, policy_id)
               
               if not policy:
                   logger.error(f"Policy {policy_id} not found")
                   return
               
               if not policy.enabled:
                   logger.info(f"Policy {policy_id} is disabled, skipping")
                   return
               
               # Run policy
               enforcer = PolicyEnforcer(session)
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
   
   
   def shutdown_scheduler():
       """Shutdown the scheduler (call on app shutdown)"""
       sched = get_scheduler()
       
       if sched.running:
           sched.shutdown(wait=False)
           logger.info("Policy scheduler stopped")
   ```

**Acceptance Criteria**:
- [ ] Scheduler service created
- [ ] Uses AsyncIOScheduler for FastAPI compatibility
- [ ] Cron triggers parsed correctly
- [ ] Policies execute on schedule
- [ ] Policy metadata (last_run, run_count, next_run) updated
- [ ] Error handling for invalid cron expressions
- [ ] Logging for all scheduler operations

---

### Task 3.4: Integrate Scheduler with FastAPI Lifecycle

**Priority**: High  
**Effort**: 30 minutes  
**File**: `app/main.py`

**Changes Required**:

1. **Update startup event** (lines 184-189):
   ```python
   @app.on_event("startup")
   async def startup_event():
       """Application startup tasks"""
       logging.info("Dredge application starting...")
       init_db()
       logging.info("Database initialized.")
       
       # Start policy scheduler
       from app.core.scheduler import start_scheduler
       start_scheduler()
       logging.info("Policy scheduler initialized.")
   ```

2. **Update shutdown event** (lines 192-194):
   ```python
   @app.on_event("shutdown")
   async def shutdown_event():
       """Application shutdown tasks"""
       logging.info("Dredge application shutting down...")
       
       # Shutdown scheduler gracefully
       from app.core.scheduler import shutdown_scheduler
       shutdown_scheduler()
   ```

**Acceptance Criteria**:
- [ ] Scheduler starts on app startup
- [ ] Scheduler stops on app shutdown
- [ ] No errors in logs during startup/shutdown
- [ ] Scheduled jobs persist across restarts (reload from DB)

---

### Task 3.5: Update Policy Routes to Manage Scheduling

**Priority**: High  
**Effort**: 2 hours  
**File**: `app/web/routes.py`

**Changes Required**:

1. **Update policy creation/update routes** to schedule/unschedule:
   ```python
   # Add import at top
   from app.core.scheduler import schedule_policy, unschedule_policy
   
   # Update POST /policies route (around line 203)
   @router.post("/policies", response_class=HTMLResponse)
   async def create_or_update_policy(request: Request, session: Session = Depends(get_session)):
       """Create or update a cleanup policy"""
       try:
           form_data = await request.form()
           
           # ... existing form parsing ...
           
           # NEW: Get schedule fields
           schedule_enabled = form_data.get("schedule_enabled") == "on"
           schedule_cron = form_data.get("schedule_cron", "").strip()
           
           policy_id = form_data.get("policy_id")
           
           if policy_id:
               # Update existing
               policy = session.get(CleanupPolicy, int(policy_id))
               policy.name = name
               policy.keep_count = int(keep_count)
               policy.max_age_days = int(max_age_days)
               policy.regex_whitelist = whitelist
               policy.enabled = enabled
               policy.schedule_enabled = schedule_enabled
               policy.schedule_cron = schedule_cron if schedule_cron else None
           else:
               # Create new
               policy = CleanupPolicy(
                   name=name,
                   keep_count=int(keep_count),
                   max_age_days=int(max_age_days),
                   regex_whitelist=whitelist,
                   enabled=enabled,
                   schedule_enabled=schedule_enabled,
                   schedule_cron=schedule_cron if schedule_cron else None
               )
           
           session.add(policy)
           session.commit()
           session.refresh(policy)
           
           # Schedule or unschedule based on settings
           if policy.schedule_enabled and policy.schedule_cron:
               schedule_policy(policy)
           else:
               unschedule_policy(policy.id)
           
           # ... rest of route ...
   ```

2. **Add policy delete route** to unschedule:
   ```python
   @router.delete("/policies/{policy_id}")
   async def delete_policy(policy_id: int, session: Session = Depends(get_session)):
       """Delete a cleanup policy"""
       try:
           policy = session.get(CleanupPolicy, policy_id)
           
           if not policy:
               return HTMLResponse(content="Policy not found", status_code=404)
           
           # Unschedule before deleting
           unschedule_policy(policy_id)
           
           session.delete(policy)
           session.commit()
           
           return HTMLResponse(
               content="",
               headers={"HX-Trigger": '{"showMessage": {"message": "Policy deleted", "type": "success"}}'}
           )
       except Exception as e:
           logger.error(f"Failed to delete policy: {e}", exc_info=True)
           return HTMLResponse(
               content="",
               status_code=500,
               headers={"HX-Trigger": f'{{"showMessage": {{"message": "Error: {str(e)}", "type": "error"}}}}'}
           )
   ```

**Acceptance Criteria**:
- [ ] Creating policy schedules it if schedule_enabled=True
- [ ] Updating policy reschedules it with new cron
- [ ] Disabling schedule_enabled unschedules job
- [ ] Deleting policy removes scheduled job
- [ ] Invalid cron expressions handled gracefully

---

### Task 3.6: Update Policy Template with Schedule Controls

**Priority**: High  
**Effort**: 2 hours  
**File**: `templates/policies.html`

**Changes Required**:

1. **Add schedule controls to policy form**:
   ```html
   <!-- Add after the "enabled" checkbox section -->
   <div class="form-group">
       <label class="checkbox-label" style="cursor: pointer; display: flex; align-items: center;">
           <input type="checkbox" name="schedule_enabled" id="schedule-enabled"
                  onchange="toggleScheduleFields()"
                  {% if policy and policy.schedule_enabled %}checked{% endif %}>
           <span style="margin-left: 0.5rem;">Enable Scheduled Execution</span>
       </label>
       <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.5rem;">
           Automatically run this policy on a schedule
       </p>
   </div>
   
   <div id="schedule-fields" style="display: {% if policy and policy.schedule_enabled %}block{% else %}none{% endif %}; margin-top: 1rem; padding: 1rem; background: var(--surface-2); border-radius: 4px;">
       <div class="form-group">
           <label for="schedule-cron">Schedule (Cron Expression)</label>
           <input type="text" 
                  name="schedule_cron" 
                  id="schedule-cron" 
                  value="{{ policy.schedule_cron if policy else '' }}"
                  placeholder="0 2 * * *"
                  style="font-family: monospace;">
           <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.5rem;">
               <strong>Examples:</strong><br>
               <code>0 2 * * *</code> - Daily at 2:00 AM<br>
               <code>0 0 * * 0</code> - Weekly on Sunday at midnight<br>
               <code>0 0 1 * *</code> - Monthly on the 1st at midnight<br>
               <code>*/30 * * * *</code> - Every 30 minutes
           </p>
       </div>
       
       <div class="form-group">
           <label>Quick Presets</label>
           <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
               <button type="button" class="btn btn-secondary" onclick="setSchedule('0 2 * * *')" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                   Daily 2am
               </button>
               <button type="button" class="btn btn-secondary" onclick="setSchedule('0 0 * * 0')" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                   Weekly Sunday
               </button>
               <button type="button" class="btn btn-secondary" onclick="setSchedule('0 0 1 * *')" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                   Monthly 1st
               </button>
               <button type="button" class="btn btn-secondary" onclick="setSchedule('0 */6 * * *')" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                   Every 6 hours
               </button>
           </div>
       </div>
       
       {% if policy and policy.next_run %}
       <div style="margin-top: 1rem; padding: 0.75rem; background: var(--bg); border-left: 3px solid var(--accent); border-radius: 4px;">
           <p style="margin: 0; font-size: 0.9rem;">
               <strong>Next Run:</strong> {{ policy.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') }}
           </p>
           {% if policy.last_run %}
           <p style="margin: 0.5rem 0 0 0; font-size: 0.85rem; color: var(--text-muted);">
               Last Run: {{ policy.last_run.strftime('%Y-%m-%d %H:%M:%S UTC') }} ({{ policy.run_count }} total runs)
           </p>
           {% endif %}
       </div>
       {% endif %}
   </div>
   
   <script>
   function toggleScheduleFields() {
       const checkbox = document.getElementById('schedule-enabled');
       const fields = document.getElementById('schedule-fields');
       fields.style.display = checkbox.checked ? 'block' : 'none';
   }
   
   function setSchedule(cron) {
       document.getElementById('schedule-cron').value = cron;
   }
   </script>
   ```

2. **Add schedule info to policy list**:
   ```html
   <!-- In the policy list table, add a "Schedule" column -->
   <th>Schedule</th>
   
   <!-- In the tbody, add: -->
   <td>
       {% if policy.schedule_enabled %}
           <span class="badge badge-success">Scheduled</span>
           <br>
           <small style="color: var(--text-muted); font-family: monospace;">{{ policy.schedule_cron }}</small>
           {% if policy.next_run %}
           <br>
           <small style="color: var(--text-muted);">Next: {{ policy.next_run.strftime('%m/%d %H:%M') }}</small>
           {% endif %}
       {% else %}
           <span class="badge badge-muted">Manual Only</span>
       {% endif %}
   </td>
   ```

**Acceptance Criteria**:
- [ ] Schedule checkbox toggles schedule fields visibility
- [ ] Cron input accepts freeform cron expressions
- [ ] Quick preset buttons populate cron input
- [ ] Next run time displayed when available
- [ ] Last run time and run count displayed
- [ ] Schedule status badge in policy list
- [ ] Helpful examples shown for cron syntax

---

## Testing Checklist

### Audit Log Tests
- [ ] New action types display with correct badges
- [ ] Source column shows registry names
- [ ] Pagination controls appear when > 50 logs
- [ ] Page navigation works correctly
- [ ] Page size selector updates correctly
- [ ] Filters apply correctly (action, source, date range)
- [ ] Pagination preserves filters
- [ ] CSV export respects active filters
- [ ] Empty states handled gracefully

### Policy Automation Tests
- [ ] Policy scheduler starts on app startup
- [ ] Creating scheduled policy adds job
- [ ] Updating cron expression reschedules job
- [ ] Disabling schedule removes job
- [ ] Deleting policy removes job
- [ ] Scheduled policies execute on time
- [ ] Policy metadata updates after execution (last_run, run_count, next_run)
- [ ] Invalid cron expressions handled gracefully
- [ ] Manual "Run Policy Now" still works
- [ ] Scheduler persists across app restarts

---

## Migration Notes

### Database Changes Required

```sql
-- Add schedule fields to CleanupPolicy
ALTER TABLE cleanuppolicy ADD COLUMN schedule_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE cleanuppolicy ADD COLUMN schedule_cron VARCHAR(100);
ALTER TABLE cleanuppolicy ADD COLUMN next_run TIMESTAMP;
ALTER TABLE cleanuppolicy ADD COLUMN last_run TIMESTAMP;
ALTER TABLE cleanuppolicy ADD COLUMN run_count INTEGER DEFAULT 0;
```

### Deployment Steps

1. **Update dependencies**: `pip install -r requirements.txt`
2. **Run database migration**: Execute SQL or use Alembic
3. **Restart application**: Scheduler starts automatically
4. **Configure policies**: Update existing policies with schedules
5. **Monitor logs**: Check scheduler initialization and job execution

---

## Estimated Timeline

| Task Group | Effort | Priority |
|------------|--------|----------|
| Audit Log Template Fixes | 1 hour | High |
| Pagination Backend | 2 hours | High |
| Pagination Frontend | 1.5 hours | High |
| Filter Backend | 2 hours | Medium |
| Filter Frontend | 2 hours | Medium |
| CSV Export Update | 1 hour | Low |
| **Subtotal: Audit Log** | **9.5 hours** | |
| | | |
| Scheduler Dependencies | 0.5 hours | High |
| Extend Policy Model | 1 hour | High |
| Scheduler Service | 3 hours | High |
| FastAPI Integration | 0.5 hours | High |
| Policy Routes Update | 2 hours | High |
| Policy Template Update | 2 hours | High |
| **Subtotal: Policy Automation** | **9 hours** | |
| | | |
| **TOTAL** | **18.5 hours** | |

**Recommended Sprint**: 1 week (2-3 hours/day)
