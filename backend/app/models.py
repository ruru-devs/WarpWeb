"""
WarpWeb Data Models
Generalized schema supporting healthcare, commerce, and arbitrary business websites.
With strict validation and bounds.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import time

class SectionNode(BaseModel):
    id: str = Field(..., min_length=1, max_length=150)
    url: str = Field(..., min_length=1, max_length=1000)
    anchor_id: Optional[str] = Field(None, max_length=150)
    title: str = Field(..., min_length=1, max_length=300)
    heading_path: List[str] = Field(default_factory=list) # e.g. ["Departments", "Cardiology", "OPD Timings"]
    content: str = Field(..., max_length=50000)
    keywords: List[str] = Field(default_factory=list)
    action_type: str = Field("navigate", max_length=50) # navigate, book, call, whatsapp, purchase
    action_label: Optional[str] = Field(None, max_length=100)
    action_url: Optional[str] = Field(None, max_length=1000)
    metadata: Dict[str, Any] = Field(default_factory=dict) # prices, hours, availability, doctor/product tags

class SiteProfile(BaseModel):
    site_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    domain: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    created_at: float = Field(default_factory=time.time)
    sections_count: int = 0
    quick_actions: List[Dict[str, str]] = Field(default_factory=list)

class SearchQuery(BaseModel):
    site_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    query: str = Field(..., min_length=1, max_length=300)
    top_k: int = Field(5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def strip_and_clean_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be blank or whitespace only")
        return cleaned

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
    site_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    intent_phrase: str = Field(..., min_length=1, max_length=150)
    target_url: str = Field(..., min_length=1, max_length=1000)
    action_label: str = Field(..., min_length=1, max_length=100)
    pinned: bool = True

    @field_validator("intent_phrase", "action_label", "target_url")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only")
        return cleaned

class LeadCaptureRequest(BaseModel):
    site_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    query: str = Field(..., max_length=300)
    visitor_contact: str = Field(..., min_length=3, max_length=150)
    note: Optional[str] = Field(None, max_length=1000)
    created_at: float = Field(default_factory=time.time)

    @field_validator("visitor_contact")
    @classmethod
    def clean_contact(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Visitor contact must be at least 3 characters")
        return cleaned
