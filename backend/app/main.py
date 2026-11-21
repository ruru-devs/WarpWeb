"""
WarpWeb Main FastAPI Application
Endpoints:
- POST /api/search (sub-100ms intent search)
- POST /api/ingest (HTML or site crawling)
- GET  /api/analytics/{site_id} (Findability reports & lost queries - Auth protected)
- POST /api/leads (Lead fallback capture)
- GET/POST /api/overrides (Intent pinning rules - Auth protected)
- GET  /warpweb.js (Serves the client widget script)
"""
import time
import os
import urllib.parse
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.models import (
    SearchQuery, SearchResponse, SearchResultItem, 
    OverrideRule, LeadCaptureRequest, SectionNode
)
from app.crawler.sectionizer import HTMLSectionizer
from app.indexer.hybrid_search import HybridIndex
from app.db.storage import DatabaseManager
from app.security.auth import (
    require_site_auth,
    extract_api_key,
    generate_api_key,
    hash_api_key,
    validate_override_url
)
from app.security.rate_limiter import (
    rate_limit_search,
    rate_limit_leads
)

app = FastAPI(title="WarpWeb Intent & Navigation Engine", version="1.0.0")

# CORS Configuration: Configurable origins, avoid wildcard with credentials
raw_origins = os.getenv(
    "WARPWEB_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
)
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

db = DatabaseManager()

# In-memory index cache per site_id
active_indices: Dict[str, HybridIndex] = {}

def get_or_load_index(site_id: str) -> HybridIndex:
    if site_id not in active_indices:
        index = HybridIndex(site_id)
        sections = db.get_sections(site_id)
        overrides = db.get_overrides(site_id)
        index.set_overrides(overrides)
        index.index_sections(sections)
        active_indices[site_id] = index
    return active_indices[site_id]

class IngestRequest(BaseModel):
    site_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    domain: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    html_content: str = Field(..., min_length=1, max_length=10_000_000)
    page_url: Optional[str] = Field(None, max_length=1000)

@app.post("/api/ingest")
async def ingest_site_html(
    req: IngestRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """
    Parses raw HTML from target site, splits into semantic sections, indexes it.
    If site already exists, enforces owner authentication.
    If new site, registers it and returns a new API key.
    """
    existing_site = db.get_site(req.site_id)
    new_api_key = None

    if existing_site:
        require_site_auth(req.site_id, x_api_key, authorization)
    else:
        # Generate API key for new site
        new_api_key = generate_api_key()
        k_hash = hash_api_key(new_api_key)
        db.save_site(req.site_id, req.domain, req.name, api_key_hash=k_hash)

    sectionizer = HTMLSectionizer(base_url=req.page_url or f"https://{req.domain}")
    sections = sectionizer.parse(req.html_content, current_url=req.page_url)
    
    db.save_site(req.site_id, req.domain, req.name)
    db.save_sections(req.site_id, sections)

    # Re-index
    index = HybridIndex(req.site_id)
    overrides = db.get_overrides(req.site_id)
    index.set_overrides(overrides)
    index.index_sections(sections)
    active_indices[req.site_id] = index

    resp = {
        "status": "success",
        "site_id": req.site_id,
        "indexed_sections": len(sections)
    }
    if new_api_key:
        resp["api_key"] = new_api_key
        resp["message"] = "Save this API key. You will need it for analytics and admin endpoints."

    return resp

def validate_public_origin(request: Request, site_domain: str):
    """Restricts public widget requests to registered site domain or allowed dev origins."""
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        parsed = urllib.parse.urlparse(origin)
        hostname = (parsed.hostname or "").lower()
        site_domain_lower = site_domain.lower()
        if hostname in ("localhost", "127.0.0.1"):
            return
        if hostname == site_domain_lower or hostname.endswith(f".{site_domain_lower}"):
            return
        raise HTTPException(
            status_code=403,
            detail=f"Origin '{origin}' is not authorized for this site."
        )
    except HTTPException:
        raise
    except Exception:
        pass

@app.post("/api/search", response_model=SearchResponse)
async def search_intent(req: SearchQuery, request: Request):
    """Sub-150ms Hybrid intent-to-URL search endpoint with rate limiting."""
    site = db.get_site(req.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{req.site_id}' not found.")

    # Apply rate limiting (per IP and per site)
    rate_limit_search(request, req.site_id)

    # Validate origin if provided
    validate_public_origin(request, site["domain"])

    t0 = time.time()
    index = get_or_load_index(req.site_id)
    results = index.search(req.query, top_k=req.top_k)
    latency_ms = round((time.time() - t0) * 1000, 2)

    is_zero = len(results) == 0
    # Log query event for the Findability Report
    db.log_query(req.site_id, req.query, len(results), latency_ms)

    quick_actions = [
        {"label": "Book Appointment", "url": "#book"},
        {"label": "Doctor Timings", "url": "#timings"},
        {"label": "Chat on WhatsApp", "url": "https://wa.me/?text=Hello"}
    ]

    return SearchResponse(
        query=req.query,
        results=results,
        latency_ms=latency_ms,
        zero_match=is_zero,
        suggested_quick_actions=quick_actions
    )

@app.get("/api/analytics/{site_id}")
async def get_site_analytics(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Fetches the Findability Report & Zero-Match search insights for site owners (Auth protected)."""
    require_site_auth(site_id, x_api_key, authorization)
    return db.get_analytics(site_id)

@app.post("/api/leads")
async def capture_lead(lead: LeadCaptureRequest, request: Request):
    """Visitor lead capture when user searches for something not found or requests contact."""
    site = db.get_site(lead.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{lead.site_id}' not found.")

    # Rate limiting on lead submissions
    rate_limit_leads(request, lead.site_id)

    validate_public_origin(request, site["domain"])

    db.save_lead(lead)
    return {"status": "success", "message": "Lead received"}

@app.get("/api/overrides/{site_id}")
async def get_overrides(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Fetches intent overrides for site owners (Auth protected)."""
    require_site_auth(site_id, x_api_key, authorization)
    return db.get_overrides(site_id)

@app.post("/api/overrides")
async def add_override(
    rule: OverrideRule,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Adds intent override (Auth protected, target URL domain validated)."""
    require_site_auth(rule.site_id, x_api_key, authorization)

    site = db.get_site(rule.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{rule.site_id}' not found.")

    # Validate target URL against site domain
    validate_override_url(rule.target_url, site["domain"])

    db.add_override(rule)
    # Refresh index overrides
    if rule.site_id in active_indices:
        active_indices[rule.site_id].set_overrides(db.get_overrides(rule.site_id))
    return {"status": "success"}

@app.get("/warpweb.js")
async def serve_widget():
    """Serves the embeddable client widget."""
    widget_path = os.path.join(os.path.dirname(__file__), "..", "..", "widget", "dist", "warpweb.js")
    if os.path.exists(widget_path):
        return FileResponse(widget_path, media_type="application/javascript")
    return Response(
        content="/* WarpWeb widget is compiling... */", 
        media_type="application/javascript"
    )

@app.get("/health")
def health():
    return {"status": "ok", "app": "WarpWeb"}
