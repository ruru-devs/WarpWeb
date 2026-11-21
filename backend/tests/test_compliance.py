"""
Test Suite for Phase 5: Compliance, Lead Consent, Retention Cleanup & Data Export
"""
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app, db
from app.models import SectionNode, LeadCaptureRequest
from app.security.rate_limiter import lead_ip_limiter, lead_site_limiter

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_compliance_test():
    lead_ip_limiter.reset()
    lead_site_limiter.reset()

    site_id = "test-comp-site"
    db.save_site(site_id, "compliance-demo.org", "Compliance Demo Site")
    db.set_site_api_key(site_id, "ww_secret_comp_key")

    # Add a section
    db.save_sections(site_id, [
        SectionNode(
            id="sec_comp_1",
            url="https://compliance-demo.org/privacy",
            anchor_id="privacy-policy",
            title="Privacy and Consent Policy",
            content="We adhere to strict data retention and user consent procedures."
        )
    ])

def test_lead_capture_with_consent():
    """Verify lead capture accepts and records consent flag, text, and timestamp."""
    site_id = "test-comp-site"
    t_now = time.time()
    res = client.post("/api/leads", json={
        "site_id": site_id,
        "query": "how to delete my account",
        "visitor_contact": "+1-555-0199",
        "note": "Please call tomorrow morning",
        "consent": True,
        "consent_text": "I consent to being contacted by site operators regarding this inquiry.",
        "consent_timestamp": t_now
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify via analytics
    headers = {"X-API-Key": "ww_secret_comp_key"}
    analytics_res = client.get(f"/api/analytics/{site_id}", headers=headers)
    assert analytics_res.status_code == 200
    leads = analytics_res.json()["recent_leads"]
    assert len(leads) >= 1
    latest_lead = leads[0]
    assert latest_lead["contact"] == "+1-555-0199"
    assert latest_lead["consent"] is True
    assert "I consent to being contacted" in latest_lead["consent_text"]
    assert latest_lead["consent_timestamp"] == pytest.approx(t_now, rel=1e-2)

def test_export_site_data():
    """Verify owner-facing export endpoint is auth-protected and returns full site telemetry & leads."""
    site_id = "test-comp-site"

    # Unauthorized
    unauth = client.get(f"/api/export/{site_id}")
    assert unauth.status_code == 401

    # Authorized
    headers = {"X-API-Key": "ww_secret_comp_key"}
    res = client.get(f"/api/export/{site_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["site"]["site_id"] == site_id
    assert "leads" in data
    assert "query_logs" in data
    assert "click_events" in data
    assert "feedback" in data
    assert "overrides" in data
    assert "synonyms" in data

def test_delete_individual_lead():
    """Verify owner can delete an individual lead record for compliance/GDPR."""
    site_id = "test-comp-site"
    lead_req = LeadCaptureRequest(
        site_id=site_id,
        query="delete me",
        visitor_contact="user@example.com",
        consent=True,
        consent_text="I consent.",
        consent_timestamp=time.time()
    )
    db.save_lead(lead_req)

    headers = {"X-API-Key": "ww_secret_comp_key"}
    analytics = client.get(f"/api/analytics/{site_id}", headers=headers).json()
    lead_id = analytics["recent_leads"][0]["id"]

    # Unauthorized attempt
    unauth = client.delete(f"/api/leads/{site_id}/{lead_id}")
    assert unauth.status_code == 401

    # Authorized delete
    del_res = client.delete(f"/api/leads/{site_id}/{lead_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify lead is gone
    analytics_after = client.get(f"/api/analytics/{site_id}", headers=headers).json()
    lead_ids_after = [l["id"] for l in analytics_after["recent_leads"]]
    assert lead_id not in lead_ids_after

def test_retention_cleanup():
    """Verify retention cleanup job purges old records while keeping fresh ones."""
    site_id = "test-comp-site"
    headers = {"X-API-Key": "ww_secret_comp_key"}

    # Seed an old lead (120 days ago) and fresh lead (today)
    old_time = time.time() - (120 * 86400)
    lead_old = LeadCaptureRequest(
        site_id=site_id,
        query="old query",
        visitor_contact="old@example.com",
        consent=True,
        consent_text="I consent.",
        consent_timestamp=old_time,
        created_at=old_time
    )
    db.save_lead(lead_old)

    lead_fresh = LeadCaptureRequest(
        site_id=site_id,
        query="fresh query",
        visitor_contact="fresh@example.com",
        consent=True,
        consent_text="I consent.",
        consent_timestamp=time.time(),
        created_at=time.time()
    )
    db.save_lead(lead_fresh)

    # Trigger cleanup with 90 days retention
    cleanup_res = client.post(f"/api/cleanup/{site_id}", json={"days": 90}, headers=headers)
    assert cleanup_res.status_code == 200
    purged = cleanup_res.json()["purged"]
    assert purged["leads_purged"] >= 1

    # Verify only fresh lead remains
    analytics = client.get(f"/api/analytics/{site_id}", headers=headers).json()
    contacts = [l["contact"] for l in analytics["recent_leads"]]
    assert "fresh@example.com" in contacts
    assert "old@example.com" not in contacts

def test_purge_site_data():
    """Verify owner can completely purge a site's records."""
    site_id = "test-comp-site"
    headers = {"X-API-Key": "ww_secret_comp_key"}

    purge_res = client.delete(f"/api/site-data/{site_id}", headers=headers)
    assert purge_res.status_code == 200
    assert purge_res.json()["status"] == "purged"

    sections = db.get_sections(site_id)
    assert len(sections) == 0
