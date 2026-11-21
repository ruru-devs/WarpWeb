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
from fastapi import FastAPI, HTTPException, Request, Header, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.models import (
    SearchQuery, SearchResponse, SearchResultItem, 
    OverrideRule, SynonymRule, LeadCaptureRequest, SectionNode,
    ClickEventRequest, FeedbackRequest, RetentionCleanupRequest
)
from app.crawler.sectionizer import HTMLSectionizer
from app.crawler.live_crawler import LiveCrawler
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
from app.security.ssrf import (
    is_safe_domain,
    resolve_and_validate_url
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
        synonyms = db.get_synonyms(site_id)
        cached_embeddings = db.get_section_embeddings(site_id)
        index.set_overrides(overrides)
        index.set_synonyms(synonyms)
        index.index_sections(sections, cached_embeddings=cached_embeddings, db_manager=db)
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
    # Log query event for the Findability Report & CTR
    query_id = db.log_query(req.site_id, req.query, len(results), latency_ms)

    quick_actions = [
        {"label": "Book Appointment", "url": "#book"},
        {"label": "Doctor Timings", "url": "#timings"},
        {"label": "Chat on WhatsApp", "url": "https://wa.me/?text=Hello"}
    ]

    return SearchResponse(
        query_id=query_id,
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

@app.get("/api/suggestions/{site_id}")
async def get_site_suggestions(site_id: str, request: Request):
    """Returns dynamic suggestions for the search widget modal."""
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")

    validate_public_origin(request, site["domain"])

    sections = db.get_sections(site_id)
    suggestions = []
    seen_titles = set()
    for s in sections:
        if s.title and s.title not in seen_titles and len(s.title) < 50:
            suggestions.append({
                "label": s.title,
                "query": s.title
            })
            seen_titles.add(s.title)
        if len(suggestions) >= 6:
            break

    if not suggestions:
        suggestions = [{"label": f"Explore {site['name']}", "query": site["name"]}]

    return {"site_id": site_id, "suggestions": suggestions}

@app.post("/api/clicks")
async def track_click(click: ClickEventRequest, request: Request):
    """Tracks search result click-through events for CTR calculation."""
    site = db.get_site(click.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{click.site_id}' not found.")

    validate_public_origin(request, site["domain"])
    click_id = db.log_click(
        site_id=click.site_id,
        result_id=click.result_id,
        rank=click.rank,
        target_url=click.target_url,
        query_id=click.query_id,
        query=click.query
    )
    return {"status": "success", "click_id": click_id}

@app.post("/api/feedback")
async def track_feedback(fb: FeedbackRequest, request: Request):
    """Tracks visitor result satisfaction feedback (thumbs up / down)."""
    site = db.get_site(fb.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{fb.site_id}' not found.")

    validate_public_origin(request, site["domain"])
    fb_id = db.save_feedback(
        site_id=fb.site_id,
        is_positive=fb.is_positive,
        query=fb.query
    )
    return {"status": "success", "feedback_id": fb_id}

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

@app.get("/api/synonyms/{site_id}")
async def get_site_synonyms(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Fetches intent aliases/synonyms for site owners (Auth protected)."""
    require_site_auth(site_id, x_api_key, authorization)
    return db.get_synonyms(site_id)

@app.post("/api/synonyms")
async def add_site_synonym(
    rule: SynonymRule,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Adds intent alias/synonym (Auth protected)."""
    require_site_auth(rule.site_id, x_api_key, authorization)
    site = db.get_site(rule.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{rule.site_id}' not found.")
    syn_id = db.add_synonym(rule)
    if rule.site_id in active_indices:
        active_indices[rule.site_id].set_synonyms(db.get_synonyms(rule.site_id))
    return {"status": "success", "id": syn_id}

@app.delete("/api/synonyms/{site_id}/{synonym_id}")
async def delete_site_synonym(
    site_id: str,
    synonym_id: int,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Deletes intent alias/synonym (Auth protected)."""
    require_site_auth(site_id, x_api_key, authorization)
    deleted = db.delete_synonym(site_id, synonym_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Synonym not found.")
    if site_id in active_indices:
        active_indices[site_id].set_synonyms(db.get_synonyms(site_id))
    return {"status": "success"}

class CrawlTriggerRequest(BaseModel):
    start_url: Optional[str] = Field(None, max_length=1000)
    max_pages: int = Field(50, ge=1, le=500)
    max_depth: int = Field(3, ge=1, le=10)
    use_playwright: bool = False
    index_pdfs: bool = True

@app.post("/api/crawl/{site_id}")
async def trigger_site_crawl(
    site_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[CrawlTriggerRequest] = None,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Triggers background live-domain crawler with robots.txt compliance and delta hashing."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")

    if payload and payload.start_url:
        candidate_url = payload.start_url.strip()
        if not is_safe_domain(candidate_url, site["domain"]):
            raise HTTPException(
                status_code=400,
                detail=f"start_url '{candidate_url}' does not belong to registered domain '{site['domain']}'."
            )
        is_safe, resolved_ip, err = resolve_and_validate_url(candidate_url, allowed_domain=site["domain"])
        if not is_safe:
            raise HTTPException(
                status_code=400,
                detail=f"start_url failed SSRF validation: {err}"
            )
        start_url = candidate_url
    else:
        start_url = f"https://{site['domain']}"
    max_pages = payload.max_pages if payload else 50
    max_depth = payload.max_depth if payload else 3
    use_playwright = payload.use_playwright if payload else False
    index_pdfs = payload.index_pdfs if payload else True

    crawler = LiveCrawler(
        site_id=site_id,
        start_url=start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        use_playwright=use_playwright,
        index_pdfs=index_pdfs
    )

    def run_crawl_job():
        crawler.crawl_and_index()
        # Invalidate in-memory cache so fresh index is picked up
        active_indices.pop(site_id, None)

    background_tasks.add_task(run_crawl_job)
    return {
        "status": "started",
        "site_id": site_id,
        "start_url": start_url,
        "message": "Crawl job running in background"
    }

@app.get("/api/crawl/status/{site_id}")
async def get_crawl_status(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Checks the status of the background crawl job."""
    require_site_auth(site_id, x_api_key, authorization)
    job = db.get_crawl_job(site_id)
    if not job:
        return {"site_id": site_id, "status": "idle", "pages_crawled": 0, "sections_indexed": 0}
    return job

@app.get("/api/export/{site_id}")
async def export_site_data(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Exports all site telemetry, leads, rules, and configurations (owner auth required)."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    return db.export_site_data(site_id)

@app.delete("/api/leads/{site_id}/{lead_id}")
async def delete_site_lead(
    site_id: str,
    lead_id: int,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Deletes an individual lead record for GDPR / compliance (owner auth required)."""
    require_site_auth(site_id, x_api_key, authorization)
    deleted = db.delete_lead(site_id, lead_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return {"status": "deleted", "site_id": site_id, "lead_id": lead_id}

@app.delete("/api/site-data/{site_id}")
async def purge_site_data(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Purges all indexed sections, logs, leads, and rules for a site (owner auth required)."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    db.delete_site_data(site_id)
    active_indices.pop(site_id, None)
    return {"status": "purged", "site_id": site_id}

@app.post("/api/cleanup/{site_id}")
async def cleanup_retention_data(
    site_id: str,
    payload: Optional[RetentionCleanupRequest] = None,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Purges historical logs, clicks, feedback, and leads older than retention threshold."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    days = payload.days if payload else 90
    purged_stats = db.cleanup_old_data(site_id, days=days)
    return {
        "status": "success",
        "site_id": site_id,
        "retention_days": days,
        "purged": purged_stats
    }

@app.post("/api/keys/rotate/{site_id}")
async def rotate_api_key(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Rotates site API key. Requires authentication with current valid key."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    new_key = generate_api_key()
    success = db.rotate_site_api_key(site_id, new_key)
    if not success:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    return {
        "status": "success",
        "site_id": site_id,
        "api_key": new_key,
        "message": "API key rotated successfully. Store this new key safely."
    }

@app.post("/api/keys/revoke/{site_id}")
async def revoke_api_key(
    site_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """Revokes site API key. Requires authentication with current valid key."""
    require_site_auth(site_id, x_api_key, authorization)
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    success = db.revoke_site_api_key(site_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
    return {
        "status": "success",
        "site_id": site_id,
        "message": "API key revoked. Owner/admin access is disabled until a new key is provisioned."
    }

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
