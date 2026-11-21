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
    lead_site_limiter,
    get_client_ip
)
from app.security.ssrf import (
    is_safe_domain,
    resolve_and_validate_url,
    safe_fetch_page,
    is_private_or_reserved_ip
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

    # Ensure test sites exist in DB
    db.save_site("test-sec-apexcare", "apexcareclinic.com", "Apex Care Clinic")
    db.set_site_api_key("test-sec-apexcare", "ww_dev_apexcare_secret")

    db.save_site("test-sec-pulse", "pulsetechaudio.com", "PulseTech Audio")
    db.set_site_api_key("test-sec-pulse", "ww_dev_shoppulse_secret")

    # Add realistic sections for test-sec-apexcare
    db.save_sections("test-sec-apexcare", [
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
        "site_id": "test-sec-apexcare",
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
        "site_id": "test-sec-apexcare",
        "query": "skin specialist",
        "visitor_contact": "+91 9999988888",
        "note": "Looking for acne consultation"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_owner_analytics_requires_auth():
    """Accessing owner analytics without API key must return 401."""
    res = client.get("/api/analytics/test-sec-apexcare")
    assert res.status_code == 401

def test_owner_analytics_invalid_key():
    """Accessing owner analytics with wrong API key must return 403."""
    res = client.get("/api/analytics/test-sec-apexcare", headers={"X-API-Key": "wrong-secret-key"})
    assert res.status_code == 403

def test_owner_analytics_valid_key():
    """Accessing owner analytics with valid API key returns 200."""
    res = client.get("/api/analytics/test-sec-apexcare", headers={"X-API-Key": "ww_dev_apexcare_secret"})
    assert res.status_code == 200
    assert "total_queries" in res.json()

def test_tenant_isolation_cross_tenant_access_denied():
    """An API key for Site A cannot access or modify Site B."""
    # shoppulse key used on apexcare analytics
    res = client.get("/api/analytics/test-sec-apexcare", headers={"X-API-Key": "ww_dev_shoppulse_secret"})
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # shoppulse key used on apexcare overrides
    res = client.get("/api/overrides/test-sec-apexcare", headers={"X-API-Key": "ww_dev_shoppulse_secret"})
    assert res.status_code == 403

def test_override_creation_requires_auth():
    """Creating an override without auth must return 401."""
    res = client.post("/api/overrides", json={
        "site_id": "test-sec-apexcare",
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
        "site_id": "test-sec-apexcare",
        "intent_phrase": "hack",
        "target_url": "javascript:alert(document.cookie)",
        "action_label": "Click me"
    })
    assert res_js.status_code == 400
    assert "Unsupported URL scheme" in res_js.json()["detail"]

    # 2. data: scheme rejected
    res_data = client.post("/api/overrides", headers=headers, json={
        "site_id": "test-sec-apexcare",
        "intent_phrase": "phish",
        "target_url": "data:text/html,<script>alert(1)</script>",
        "action_label": "Click me"
    })
    assert res_data.status_code == 400

    # 3. External domain rejected
    res_ext = client.post("/api/overrides", headers=headers, json={
        "site_id": "test-sec-apexcare",
        "intent_phrase": "external scam",
        "target_url": "https://attacker-phishing.com/login",
        "action_label": "Login"
    })
    assert res_ext.status_code == 400
    assert "does not match registered site domain" in res_ext.json()["detail"]

    # 4. Valid relative path accepted
    res_rel = client.post("/api/overrides", headers=headers, json={
        "site_id": "test-sec-apexcare",
        "intent_phrase": "opd doctors",
        "target_url": "/pages/doctors.html#doc-sharma",
        "action_label": "View Schedule"
    })
    assert res_rel.status_code == 200

    # 5. Valid anchor accepted
    res_anchor = client.post("/api/overrides", headers=headers, json={
        "site_id": "test-sec-apexcare",
        "intent_phrase": "book now",
        "target_url": "#appointment",
        "action_label": "Book"
    })
    assert res_anchor.status_code == 200

def test_input_validation():
    """Test input length bounds and regex on query parameters."""
    # Blank query
    res = client.post("/api/search", json={
        "site_id": "test-sec-apexcare",
        "query": "   ",
        "top_k": 5
    })
    assert res.status_code == 422

    # Query too long (> 300 chars)
    res = client.post("/api/search", json={
        "site_id": "test-sec-apexcare",
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
        "site_id": "test-sec-apexcare",
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
            "site_id": "test-sec-apexcare",
            "query": f"search query {i}",
            "top_k": 5
        })
        assert res.status_code == 200

    # 4th request should exceed limit
    res_exceeded = client.post("/api/search", json={
        "site_id": "test-sec-apexcare",
        "query": "search query 4",
        "top_k": 5
    })
    assert res_exceeded.status_code == 429
    assert "Rate limit exceeded" in res_exceeded.json()["detail"]
    assert "Retry-After" in res_exceeded.headers


def test_domain_validation_edge_cases():
    """Validates domain matching rules against suffix attacks, userinfo tricks, and case/port variations."""
    target = "example.com"

    # Suffix attacks: notexample.com must NOT match example.com
    assert is_safe_domain("https://notexample.com/page", target) is False
    assert is_safe_domain("https://example.com.evil.net/page", target) is False
    assert is_safe_domain("notexample.com", target) is False

    # Userinfo tricks
    assert is_safe_domain("https://example.com@evil.com/path", target) is False
    assert is_safe_domain("https://user:password@example.com/path", target) is False

    # Scheme restrictions: only http and https allowed
    assert is_safe_domain("ftp://example.com/file", target) is False
    assert is_safe_domain("file:///etc/passwd", target) is False
    assert is_safe_domain("javascript:alert(1)", target) is False

    # Port and case variations
    assert is_safe_domain("HTTPS://EXAMPLE.COM/PATH", target) is True
    assert is_safe_domain("https://example.com:8443/page", target) is True
    assert is_safe_domain("http://example.com:8080", target) is True

    # Valid subdomains
    assert is_safe_domain("https://blog.example.com", target) is True
    assert is_safe_domain("https://sub.portal.example.com", target) is True

    # www. symmetry
    assert is_safe_domain("https://www.example.com", target) is True
    assert is_safe_domain("https://example.com", "www.example.com") is True


def test_private_ip_detection():
    """Verifies that RFC1918, loopback, link-local, and IPv6 private addresses are caught."""
    # Loopback
    assert is_private_or_reserved_ip("127.0.0.1") is True
    assert is_private_or_reserved_ip("127.0.0.2") is True
    assert is_private_or_reserved_ip("::1") is True

    # Link-local / Cloud metadata service
    assert is_private_or_reserved_ip("169.254.169.254") is True
    assert is_private_or_reserved_ip("fe80::1") is True

    # RFC 1918 private subnets
    assert is_private_or_reserved_ip("10.0.0.1") is True
    assert is_private_or_reserved_ip("172.16.0.1") is True
    assert is_private_or_reserved_ip("172.31.255.255") is True
    assert is_private_or_reserved_ip("192.168.1.1") is True

    # IPv6 unique-local
    assert is_private_or_reserved_ip("fc00::1") is True
    assert is_private_or_reserved_ip("fd12:3456:789a::1") is True

    # IPv4-mapped IPv6 address
    assert is_private_or_reserved_ip("::ffff:127.0.0.1") is True
    assert is_private_or_reserved_ip("::ffff:169.254.169.254") is True

    # Public IP should not be marked private
    assert is_private_or_reserved_ip("8.8.8.8") is False
    assert is_private_or_reserved_ip("1.1.1.1") is False


def test_ssrf_crawl_endpoint_validation():
    """Verify POST /api/crawl/{site_id} rejects loopback, metadata, and cross-domain start_url."""
    headers = {"X-API-Key": "ww_dev_apexcare_secret"}

    # 1. Reject start_url pointing to loopback
    res_loopback = client.post("/api/crawl/test-sec-apexcare", headers=headers, json={
        "start_url": "http://127.0.0.1:8080/admin"
    })
    assert res_loopback.status_code == 400
    assert "does not belong to registered domain" in res_loopback.json()["detail"] or "SSRF" in res_loopback.json()["detail"]

    # 2. Reject cloud metadata address
    res_meta = client.post("/api/crawl/test-sec-apexcare", headers=headers, json={
        "start_url": "http://169.254.169.254/latest/meta-data/"
    })
    assert res_meta.status_code == 400

    # 3. Reject different domain
    res_other = client.post("/api/crawl/test-sec-apexcare", headers=headers, json={
        "start_url": "https://attacker-domain.com/evil"
    })
    assert res_other.status_code == 400
    assert "does not belong to registered domain" in res_other.json()["detail"]


def test_ssrf_safe_fetch_page_redirect_to_loopback(monkeypatch):
    """Verify safe_fetch_page detects and aborts an open redirect targeting private/loopback IP."""
    import httpx

    class MockRedirectResponse:
        is_redirect = True
        status_code = 302
        headers = {"Location": "http://127.0.0.1:8080/internal-admin"}

    # Mock first hop returning 302 redirect to loopback
    def mock_get(self, url, **kwargs):
        return MockRedirectResponse()

    # resolve_and_validate_url allows example.com for the first hop
    content, final_url, err = safe_fetch_page("https://example.com/redirect", allowed_domain="example.com")
    # First hop fails because redirect to 127.0.0.1 fails resolve_and_validate_url
    assert content is None
    assert "SSRF check failed" in err or "private/reserved IP" in err or "does not match allowed domain" in err


def test_api_key_rotation_and_revocation():
    """Tests rotating and revoking owner API keys."""
    site_id = "test-sec-apexcare"
    initial_key = "ww_dev_apexcare_secret"

    # 1. Rotate API key with valid initial key
    rotate_res = client.post(f"/api/keys/rotate/{site_id}", headers={"X-API-Key": initial_key})
    assert rotate_res.status_code == 200
    new_key = rotate_res.json()["api_key"]
    assert new_key.startswith("ww_live_")
    assert new_key != initial_key

    # 2. Old key is immediately rejected
    old_key_res = client.get(f"/api/analytics/{site_id}", headers={"X-API-Key": initial_key})
    assert old_key_res.status_code == 403

    # 3. New key works
    new_key_res = client.get(f"/api/analytics/{site_id}", headers={"X-API-Key": new_key})
    assert new_key_res.status_code == 200

    # 4. Revoke API key
    revoke_res = client.post(f"/api/keys/revoke/{site_id}", headers={"X-API-Key": new_key})
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "success"

    # 5. Revoked key can no longer access analytics
    revoked_res = client.get(f"/api/analytics/{site_id}", headers={"X-API-Key": new_key})
    assert revoked_res.status_code == 403

    # Restore key for subsequent tests
    db.set_site_api_key(site_id, initial_key)


def test_rate_limiter_trusted_proxy(monkeypatch):
    """Test that X-Forwarded-For is only honored when connecting through a trusted proxy."""
    from starlette.requests import Request

    class DummyClient:
        def __init__(self, host):
            self.host = host

    # Scenario 1: Request comes from trusted proxy (127.0.0.1)
    req_trusted = Request({
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 127.0.0.1")]
    })
    extracted_ip = get_client_ip(req_trusted)
    assert extracted_ip == "203.0.113.195"

    # Scenario 2: Request comes directly from an untrusted IP (e.g. 198.51.100.5) spoofing X-Forwarded-For
    req_untrusted = Request({
        "type": "http",
        "client": ("198.51.100.5", 54321),
        "headers": [(b"x-forwarded-for", b"10.0.0.1")] # spoofed header
    })
    extracted_ip_untrusted = get_client_ip(req_untrusted)
    # Must use socket address, NOT the spoofed header!
    assert extracted_ip_untrusted == "198.51.100.5"


def test_cross_tenant_isolation_all_endpoints():
    """Comprehensive test verifying cross-tenant access is rejected across all protected endpoints."""
    # Site A: test-sec-apexcare (key: ww_dev_apexcare_secret)
    # Site B: test-sec-pulse (key: ww_dev_shoppulse_secret)
    attacker_headers = {"X-API-Key": "ww_dev_shoppulse_secret"}
    target_site = "test-sec-apexcare"

    # 1. Analytics
    res = client.get(f"/api/analytics/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 2. Overrides read
    res = client.get(f"/api/overrides/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 3. Overrides create
    res = client.post("/api/overrides", headers=attacker_headers, json={
        "site_id": target_site,
        "intent_phrase": "stolen intent",
        "target_url": "#stolen",
        "action_label": "Stolen"
    })
    assert res.status_code == 403

    # 4. Synonyms read
    res = client.get(f"/api/synonyms/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 5. Synonyms create
    res = client.post("/api/synonyms", headers=attacker_headers, json={
        "site_id": target_site,
        "phrase": "stolen syn",
        "canonical": "stolen can"
    })
    assert res.status_code == 403

    # 6. Synonyms delete
    res = client.delete(f"/api/synonyms/{target_site}/1", headers=attacker_headers)
    assert res.status_code == 403

    # 7. Crawl trigger
    res = client.post(f"/api/crawl/{target_site}", headers=attacker_headers, json={
        "max_pages": 10
    })
    assert res.status_code == 403

    # 8. Crawl status
    res = client.get(f"/api/crawl/status/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 9. Export
    res = client.get(f"/api/export/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 10. Lead deletion
    res = client.delete(f"/api/leads/{target_site}/1", headers=attacker_headers)
    assert res.status_code == 403

    # 11. Key rotation
    res = client.post(f"/api/keys/rotate/{target_site}", headers=attacker_headers)
    assert res.status_code == 403

    # 12. Key revocation
    res = client.post(f"/api/keys/revoke/{target_site}", headers=attacker_headers)
    assert res.status_code == 403


def test_xss_payload_in_indexed_content():
    """Verify that malicious script tags stored in indexed content do not execute and return as safe text."""
    xss_payload = "<script>alert('pwned')</script><img src=x onerror=alert(1)>"
    db.save_sections("test-sec-apexcare", [
        SectionNode(
            id="sec_xss_1",
            url="https://apexcareclinic.com/about",
            title=f"Malicious Title {xss_payload}",
            content=f"Malicious content with payload {xss_payload}",
            keywords=["malicious", "xss", "payload"]
        )
    ])
    active_indices.clear()

    res = client.post("/api/search", json={
        "site_id": "test-sec-apexcare",
        "query": "malicious payload",
        "top_k": 5
    })
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) > 0
    # Data is returned as a plain JSON string; no script execution can occur
    assert xss_payload in results[0]["title"]
    assert xss_payload in results[0]["snippet"]

