"""
WarpWeb Data Models
Generalized schema supporting healthcare, commerce, and arbitrary business websites.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time

class SectionNode(BaseModel):
    id: str
    url: str
    anchor_id: Optional[str] = None
    title: str
    heading_path: List[str] = Field(default_factory=list) # e.g. ["Departments", "Cardiology", "OPD Timings"]
    content: str
    keywords: List[str] = Field(default_factory=list)
    action_type: str = "navigate" # navigate, book, call, whatsapp, purchase
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict) # prices, hours, availability, doctor/product tags

class SiteProfile(BaseModel):
    site_id: str
    domain: str
    name: str
    created_at: float = Field(default_factory=time.time)
    sections_count: int = 0
    quick_actions: List[Dict[str, str]] = Field(default_factory=list)

class SearchQuery(BaseModel):
    site_id: str
    query: str
    top_k: int = 5

class SearchResultItem(BaseModel):
    id: str
    title: str
    url: str
    anchor_id: Optional[str] = None
    target_url: str
    snippet: str
    score: float
    match_type: str # 'override', 'exact_keyword', 'semantic'
    action_label: Optional[str] = None
    action_type: str = "navigate"
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]
    latency_ms: float
    zero_match: bool = False
    suggested_quick_actions: List[Dict[str, str]] = Field(default_factory=list)

class OverrideRule(BaseModel):
    site_id: str
    intent_phrase: str # e.g. "dr sharma timings", "return policy", "emergency contact"
    target_url: str
    action_label: str
    pinned: bool = True

class LeadCaptureRequest(BaseModel):
    site_id: str
    query: str
    visitor_contact: str # phone / email / whatsapp
    note: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
