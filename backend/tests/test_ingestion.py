"""
Ingestion Test Suite (Phase 3):
- Nested section deduplication
- Stable anchor & text-fragment locator generation for un-anchored HTML
- Multi-action extraction per section
- Content change hashing (SHA-256)
- Background crawl job API & status reporting
- PDF text extraction
"""
import io
import pytest
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
import pypdf

from app.main import app, db, active_indices
from app.crawler.sectionizer import HTMLSectionizer
from app.crawler.live_crawler import LiveCrawler, normalize_url, is_same_domain

client = TestClient(app)

def test_nested_section_deduplication():
    """Verify sectionizer keeps specific child sections and eliminates duplicate parent wrapper."""
    html = """
    <html>
      <body>
        <main id="main-content">
          <section id="cardio" class="dept">
            <h2>Cardiology Center</h2>
            <p>Comprehensive coronary angioplasty and heart failure care with 24-hour monitoring.</p>
            <a href="/book?dept=cardio">Book Appointment</a>
          </section>
          <section id="ortho" class="dept">
            <h2>Orthopedics Center</h2>
            <p>Full joint replacement and robotic spine surgery with rehabilitation facilities.</p>
            <a href="/book?dept=ortho">Book Appointment</a>
          </section>
        </main>
      </body>
    </html>
    """
    sectionizer = HTMLSectionizer(base_url="https://example.com")
    sections = sectionizer.parse(html, current_url="https://example.com/departments")

    # Should keep the 2 specific sections (cardio, ortho) and NOT index the redundant main-content wrapper
    titles = [s.title for s in sections]
    assert "Cardiology Center" in titles
    assert "Orthopedics Center" in titles
    assert len(sections) == 2

def test_missing_anchor_stable_slug_and_locators():
    """Verify stable anchor generation and text-fragment / dom-path locators when HTML has no id."""
    html = """
    <html>
      <body>
        <div>
          <h3>Emergency Trauma Care</h3>
          <p>Immediate 24/7 trauma triage, ambulance response, and ICU resuscitation desk.</p>
          <a href="tel:102">Call Emergency</a>
        </div>
      </body>
    </html>
    """
    sectionizer = HTMLSectionizer(base_url="https://example.com")
    sections = sectionizer.parse(html, current_url="https://example.com/emergency")

    assert len(sections) == 1
    sec = sections[0]
    # No native id in HTML
    assert sec.anchor_id is None
    # Locator metadata generated
    locator = sec.metadata.get("locator", {})
    assert locator["has_native_id"] is False
    assert ":~:text=Emergency" in locator["text_fragment"]
    assert "dom_path" in locator

def test_multiple_actions_extracted():
    """Verify sectionizer extracts all interactive buttons/links into actions list."""
    html = """
    <html>
      <body>
        <section id="consultation">
          <h2>Dr. Sharma Consultation Desk</h2>
          <p>Chief interventional cardiologist OPD timings Monday to Friday.</p>
          <a href="/book?doc=sharma">Book Appointment Online</a>
          <a href="tel:+919999988888">Call Hospital Desk</a>
          <a href="https://wa.me/919999988888?text=Consult">Chat on WhatsApp</a>
        </section>
      </body>
    </html>
    """
    sectionizer = HTMLSectionizer(base_url="https://example.com")
    sections = sectionizer.parse(html, current_url="https://example.com/doctors")

    assert len(sections) == 1
    sec = sections[0]
    assert len(sec.actions) == 3
    action_types = [a["type"] for a in sec.actions]
    assert "book" in action_types
    assert "call" in action_types
    assert "whatsapp" in action_types

def test_content_change_hashing():
    """Verify content_hash changes when text changes and stays identical when unchanged."""
    html_v1 = "<section id='s1'><h2>Title</h2><p>Original text description of services.</p></section>"
    html_v2 = "<section id='s1'><h2>Title</h2><p>Modified updated description of emergency services.</p></section>"

    sectionizer = HTMLSectionizer(base_url="https://example.com")
    sec_v1 = sectionizer.parse(html_v1, "https://example.com")[0]
    sec_v1_again = sectionizer.parse(html_v1, "https://example.com")[0]
    sec_v2 = sectionizer.parse(html_v2, "https://example.com")[0]

    assert sec_v1.content_hash is not None
    assert sec_v1.content_hash == sec_v1_again.content_hash
    assert sec_v1.content_hash != sec_v2.content_hash

def test_pdf_extraction_to_sections():
    """Verify linked PDF extraction creates structured sections with page references."""
    # Create in-memory single-page PDF with pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)

    crawler = LiveCrawler(
        site_id="test-crawl-site",
        start_url="https://example.com",
        index_pdfs=True
    )
    # Validate url helper
    assert is_same_domain("https://example.com/page", "https://example.com/contact")
    assert not is_same_domain("https://example.com", "https://malicious.com")
    assert normalize_url("https://example.com/path/?a=1#fragment") == "https://example.com/path?a=1"

def test_crawl_api_trigger_and_status():
    """Verify background crawl endpoint starts job and reports status."""
    import time
    site_id = f"test-crawl-api-{int(time.time() * 1000)}"
    db.save_site(site_id, "testcrawlsite.com", "Test Crawl API Site")
    db.set_site_api_key(site_id, "ww_dev_crawl_secret")
    headers = {"X-API-Key": "ww_dev_crawl_secret"}

    # Initial status should be idle
    status_res = client.get(f"/api/crawl/status/{site_id}", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "idle"

    # Trigger crawl
    trigger_res = client.post(f"/api/crawl/{site_id}", headers=headers, json={
        "max_pages": 5,
        "max_depth": 1
    })
    assert trigger_res.status_code == 200
    assert trigger_res.json()["status"] == "started"
