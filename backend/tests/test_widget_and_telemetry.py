"""
Test Suite for Widget & Dashboard Telemetry (Phase 4):
- Dynamic suggestions endpoint (/api/suggestions/{site_id})
- Click-through tracking (/api/clicks) and CTR metrics
- Result quality feedback (/api/feedback)
- Owner analytics CTR & satisfaction reporting
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app, db
from app.models import SectionNode
from app.security.rate_limiter import (
    search_ip_limiter, search_site_limiter, lead_ip_limiter, lead_site_limiter
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_telemetry():
    search_ip_limiter.reset()
    search_site_limiter.reset()
    lead_ip_limiter.reset()
    lead_site_limiter.reset()

    site_id = "test-widget-site"
    db.save_site(site_id, "testwidget.com", "Test Widget Site")
    db.set_site_api_key(site_id, "ww_dev_telemetry_key")

    db.save_sections(site_id, [
        SectionNode(
            id="sec_test_1",
            url="https://testwidget.com/products/anc",
            anchor_id="anc-feature",
            title="Active Noise Cancellation Features",
            content="Hybrid ANC with 45 hour battery.",
            keywords=["anc", "battery", "noise"]
        ),
        SectionNode(
            id="sec_test_2",
            url="https://testwidget.com/support/returns",
            anchor_id="returns-faq",
            title="30-Day Money Back Returns",
            content="Easy return pickup and bank refund timeline.",
            keywords=["return", "refund", "timeline"]
        )
    ])

def test_dynamic_suggestions_endpoint():
    """Verify backend serves dynamic suggestions derived from site sections."""
    site_id = "test-widget-site"
    res = client.get(f"/api/suggestions/{site_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["site_id"] == site_id
    suggestions = data["suggestions"]
    assert len(suggestions) >= 2
    labels = [s["label"] for s in suggestions]
    assert "Active Noise Cancellation Features" in labels

def test_click_tracking_and_ctr_analytics():
    """Verify click logging records events and updates CTR in analytics."""
    site_id = "test-widget-site"
    headers = {"X-API-Key": "ww_dev_telemetry_key"}

    # Issue search query to generate query_id
    search_res = client.post("/api/search", json={
        "site_id": site_id,
        "query": "noise cancellation",
        "top_k": 3
    })
    assert search_res.status_code == 200
    query_id = search_res.json()["query_id"]
    assert query_id is not None

    # Log click on rank 1
    click_res = client.post("/api/clicks", json={
        "site_id": site_id,
        "query_id": query_id,
        "query": "noise cancellation",
        "result_id": "sec_test_1",
        "rank": 1,
        "target_url": "https://testwidget.com/products/anc#anc-feature"
    })
    assert click_res.status_code == 200
    assert click_res.json()["status"] == "success"

    # Check analytics reflects click and CTR
    analytics_res = client.get(f"/api/analytics/{site_id}", headers=headers)
    assert analytics_res.status_code == 200
    data = analytics_res.json()
    assert data["total_clicks"] >= 1
    assert data["click_through_rate"] > 0.0

def test_result_feedback_tracking():
    """Verify visitor thumbs-up / down feedback is tracked and reflected in analytics."""
    site_id = "test-widget-site"
    headers = {"X-API-Key": "ww_dev_telemetry_key"}

    # Send positive feedback
    fb1 = client.post("/api/feedback", json={
        "site_id": site_id,
        "query": "returns",
        "is_positive": True
    })
    assert fb1.status_code == 200

    # Send negative feedback
    fb2 = client.post("/api/feedback", json={
        "site_id": site_id,
        "query": "unknown topic",
        "is_positive": False
    })
    assert fb2.status_code == 200

    analytics_res = client.get(f"/api/analytics/{site_id}", headers=headers)
    assert analytics_res.status_code == 200
    data = analytics_res.json()
    assert data["positive_feedback"] >= 1
    assert data["negative_feedback"] >= 1
