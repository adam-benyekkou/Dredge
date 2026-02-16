"""API routes for Dredge"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.registry import LocalDockerClient
from app.core.finops import CostCalculator

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the dashboard"""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "monthly_waste": 0,
            "reclaimable_gb": 0,
            "efficiency": 100,
        }
    )


@router.get("/images", response_class=HTMLResponse)
async def images_view(request: Request):
    """Render the images view"""
    return templates.TemplateResponse(
        "images.html",
        {
            "request": request,
            "images": [],
        }
    )


@router.post("/scan", response_class=HTMLResponse)
async def scan_images(request: Request):
    """Scan Docker images and return HTML table rows"""
    try:
        # Initialize Docker client
        client = LocalDockerClient()
        
        # Get all images
        images = client.list_images()
        
        # Calculate total stats
        total_size_bytes = sum(img.size_bytes for img in images)
        total_cost = CostCalculator.calculate_monthly_cost(total_size_bytes)
        
        # Build HTML response for HTMX
        html_rows = []
        for img in images:
            repo = img.tags[0].split(':')[0] if img.tags else 'N/A'
            tag = img.tags[0].split(':')[1] if ':' in (img.tags[0] if img.tags else '') else 'latest'
            size_gb = img.size_bytes / (1024 ** 3)
            cost = CostCalculator.calculate_monthly_cost(img.size_bytes)
            created = img.created_at.strftime('%Y-%m-%d %H:%M') if img.created_at else 'N/A'
            
            html_rows.append(f"""
                <tr>
                    <td><input type="checkbox" name="image-select" value="{img.digest}"></td>
                    <td>{repo}</td>
                    <td>{tag}</td>
                    <td>{size_gb:.2f} GB</td>
                    <td>{created}</td>
                    <td><span class="badge safe">Safe</span></td>
                    <td>${cost:.2f}/mo</td>
                </tr>
            """)
        
        result_html = f"""
            <div class="images-table">
                <table>
                    <thead>
                        <tr>
                            <th><input type="checkbox" id="select-all"></th>
                            <th>Repository</th>
                            <th>Tag</th>
                            <th>Size</th>
                            <th>Created</th>
                            <th>Status</th>
                            <th>Monthly Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(html_rows)}
                    </tbody>
                </table>
            </div>
            <p style="margin-top: 1rem; color: var(--text-muted);">
                Found {len(images)} images | Total: {total_size_bytes / (1024**3):.2f} GB | Monthly cost: ${total_cost:.2f}
            </p>
        """
        
        return HTMLResponse(content=result_html)
        
    except Exception as e:
        return HTMLResponse(
            content=f'<p style="color: var(--danger);">Error scanning images: {str(e)}</p>',
            status_code=500
        )
