"""
Security test suite for WarpWeb backend.
Tests:
- API key authentication and tenant isolation
- Override target URL validation (prevent SSRF/open-redirect/XSS schemes)
- Input bounds and format validation
- Rate limiting on public endpoints
- Anonymous public search & lead accessibility
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app, db, active_indices
from app.security.rate_limiter import (
    search_ip_limiter,
    search_site_limiter,
    lead_ip_limiter,
    lead_site_limiter
)
from app.models import SectionNode

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db_and_limiter():
    """Setup test data and reset rate limiters before each test."""
    search_ip_limiter.reset()
    search_site_limiter.reset()
    lead_ip_limiter.reset()
    lead_site_limiter.reset()
    active_indices.clear()

    # Ensure demo sites exist in DB
    db.save_site("apexcare-clinic", "apexcareclinic.com", "Apex Care Clinic")
    db.set_site_api_key("apexcare-clinic", "ww_dev_apexcare_secret")

    db.save_site("shoppulse-commerce", "pulsetechaudio.com", "PulseTech Audio")
    db.set_site_api_key("shoppulse-commerce", "ww_dev_shoppulse_secret")

    # Add realistic sections for apexcare
    db.save_sections("apexcare-clinic", [
        SectionNode(
            id="sec_1",
            url="https://apexcareclinic.com/doctors",
            title="Dr. Sharma Cardiology",
            content="Dr. Sharma OPD timings are 10am to 2pm Monday to Friday.",
            keywords=["sharma", "cardiology", "timings"]
        ),
        SectionNode(
            id="sec_2",
            url="https://apexcareclinic.com/contact",
            title="Hospital Emergency Contact",
            content="24/7 emergency helpline number and ambulance desk.",
            keywords=["emergency", "contact", "ambulance"]
        ),
        SectionNode(
            id="sec_3",
            url="https://apexcareclinic.com/billing",
            title="Insurance and Billing Desk",
            content="Cashless insurance claims and hospital billing queries.",
            keywords=["insurance", "billing", "claims"]
        )
    ])

def test_public_search_anonymous_access():
    """Anonymous visitors must be able to search without an API key."""
    res = client.post("/api/search", json={
        "site_id": "apexcare-clinic",
        "query": "sharma timings",
        "top_k": 5
    })
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "sharma timings"
    assert len(data["results"]) >= 1

def test_public_search_unknown_site_404():
    """Search on an unregistered site_id must return 404."""
    res = client.post("/api/search", json={
        "site_id": "nonexistent-site-xyz",
        "query": "hello",
        "top_k": 5
    })
    assert res.status_code == 404

def test_public_lead_submission_anonymous_access():
    """Anonymous visitors can submit lead for an existing site."""
    res = client.post("/api/leads", json={
        "site_id": "apexcare-clinic",
        "query": "skin specialist",
        "visitor_contact": "+91 9999988888",
        "note": "Looking for acne consultation"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_owner_analytics_requires_auth():
    """Accessing owner analytics without API key must return 401."""
    res = client.get("/api/analytics/apexcare-clinic")
    assert res.status_code == 401

def test_owner_analytics_invalid_key():
    """Accessing owner analytics with wrong API key must return 403."""
    res = client.get("/api/analytics/apexcare-clinic", headers={"X-API-Key": "wrong-secret-key"})
    assert res.status_code == 403

def test_owner_analytics_valid_key():
    """Accessing owner analytics with valid API key returns 200."""
    res = client.get("/api/analytics/apexcare-clinic", headers={"X-API-Key": "ww_dev_apexcare_secret"})
    assert res.status_code == 200
    assert "total_queries" in res.json()

def test_tenant_isolation_cross_tenant_access_denied():
    """An API key for Site A cannot access or modify Site B."""
    # shoppulse key used on apexcare analytics
    res = client.get("/api/analytics/apexcare-clinic", headers={"X-API-Key": "ww_dev_shoppulse_secret"})
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # shoppulse key used on apexcare overrides
    res = client.get("/api/overrides/apexcare-clinic", headers={"X-API-Key": "ww_dev_shoppulse_secret"})
    assert res.status_code == 403

def test_override_creation_requires_auth():
    """Creating an override without auth must return 401."""
    res = client.post("/api/overrides", json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "dr sharma timings",
        "target_url": "#doc-sharma",
        "action_label": "Reserve Doctor",
        "pinned": True
    })
    assert res.status_code == 401

def test_override_target_url_security():
    """Target URLs with dangerous schemes or external domains must be rejected."""
    headers = {"X-API-Key": "ww_dev_apexcare_secret"}

    # 1. javascript: scheme rejected
    res_js = client.post("/api/overrides", headers=headers, json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "hack",
        "target_url": "javascript:alert(document.cookie)",
        "action_label": "Click me"
    })
    assert res_js.status_code == 400
    assert "Unsupported URL scheme" in res_js.json()["detail"]

    # 2. data: scheme rejected
    res_data = client.post("/api/overrides", headers=headers, json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "phish",
        "target_url": "data:text/html,<script>alert(1)</script>",
        "action_label": "Click me"
    })
    assert res_data.status_code == 400

    # 3. External domain rejected
    res_ext = client.post("/api/overrides", headers=headers, json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "external scam",
        "target_url": "https://attacker-phishing.com/login",
        "action_label": "Login"
    })
    assert res_ext.status_code == 400
    assert "does not match registered site domain" in res_ext.json()["detail"]

    # 4. Valid relative path accepted
    res_rel = client.post("/api/overrides", headers=headers, json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "opd doctors",
        "target_url": "/pages/doctors.html#doc-sharma",
        "action_label": "View Schedule"
    })
    assert res_rel.status_code == 200

    # 5. Valid anchor accepted
    res_anchor = client.post("/api/overrides", headers=headers, json={
        "site_id": "apexcare-clinic",
        "intent_phrase": "book now",
        "target_url": "#appointment",
        "action_label": "Book"
    })
    assert res_anchor.status_code == 200

def test_input_validation():
    """Test input length bounds and regex on query parameters."""
    # Blank query
    res = client.post("/api/search", json={
        "site_id": "apexcare-clinic",
        "query": "   ",
        "top_k": 5
    })
    assert res.status_code == 422

    # Query too long (> 300 chars)
    res = client.post("/api/search", json={
        "site_id": "apexcare-clinic",
        "query": "a" * 301,
        "top_k": 5
    })
    assert res.status_code == 422

    # Invalid site_id with path traversal characters
    res = client.post("/api/search", json={
        "site_id": "../../etc/passwd",
        "query": "test",
        "top_k": 5
    })
    assert res.status_code == 422

    # Invalid contact length
    res = client.post("/api/leads", json={
        "site_id": "apexcare-clinic",
        "query": "test",
        "visitor_contact": "x" # too short
    })
    assert res.status_code == 422

def test_rate_limiting_search():
    """Verify rate limiter triggers 429 when client exceeds search threshold."""
    # Set artificial tight limit on search limiter for test
    search_ip_limiter.default_limit = 3

    for i in range(3):
        res = client.post("/api/search", json={
            "site_id": "apexcare-clinic",
            "query": f"search query {i}",
            "top_k": 5
        })
        assert res.status_code == 200

    # 4th request should exceed limit
    res_exceeded = client.post("/api/search", json={
        "site_id": "apexcare-clinic",
        "query": "search query 4",
        "top_k": 5
    })
    assert res_exceeded.status_code == 429
    assert "Rate limit exceeded" in res_exceeded.json()["detail"]
    assert "Retry-After" in res_exceeded.headers
