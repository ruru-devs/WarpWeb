"""
WarpWeb Main FastAPI Application
Endpoints:
- POST /api/search (sub-100ms intent search)
- POST /api/ingest (HTML or site crawling)
- GET  /api/analytics/{site_id} (Findability reports & lost queries)
- POST /api/leads (Lead fallback capture)
- GET/POST /api/overrides (Intent pinning rules)
- GET  /warpweb.js (Serves the client widget script)
"""
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from typing import Dict, List, Optional
from pydantic import BaseModel
import os

from app.models import (
    SearchQuery, SearchResponse, SearchResultItem, 
    OverrideRule, LeadCaptureRequest, SectionNode
)
from app.crawler.sectionizer import HTMLSectionizer
from app.indexer.hybrid_search import HybridIndex
from app.db.storage import DatabaseManager

app = FastAPI(title="WarpWeb Intent & Navigation Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
    site_id: str
    domain: str
    name: str
    html_content: str
    page_url: Optional[str] = None

@app.post("/api/ingest")
async def ingest_site_html(req: IngestRequest):
    """Parses raw HTML from target site, splits into semantic sections, indexes it."""
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

    return {
        "status": "success",
        "site_id": req.site_id,
        "indexed_sections": len(sections)
    }

@app.post("/api/search", response_model=SearchResponse)
async def search_intent(req: SearchQuery):
    """Sub-150ms Hybrid intent-to-URL search endpoint."""
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
async def get_site_analytics(site_id: str):
    """Fetches the Findability Report & Zero-Match search insights for site owners."""
    return db.get_analytics(site_id)

@app.post("/api/leads")
async def capture_lead(lead: LeadCaptureRequest):
    """Visitor lead capture when user searches for something not found or requests contact."""
    db.save_lead(lead)
    return {"status": "success", "message": "Lead received"}

@app.get("/api/overrides/{site_id}")
async def get_overrides(site_id: str):
    return db.get_overrides(site_id)

@app.post("/api/overrides")
async def add_override(rule: OverrideRule):
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
