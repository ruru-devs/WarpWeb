"""
Tests for Data Integrity:
1. SectionNode keywords and heading_path persistence and round-trip fidelity.
2. Migration path for legacy SQLite databases missing new columns.
"""
import os
import sqlite3
import tempfile
import pytest
from app.models import SectionNode
from app.db.storage import DatabaseManager, init_db

def test_section_keywords_and_heading_path_roundtrip():
    """Verify SectionNode saves and loads keywords and heading_path without loss."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db_path = tf.name

    try:
        db = DatabaseManager(temp_db_path)
        site_id = "test-site-roundtrip"
        db.save_site(site_id, "testsite.com", "Test Site")

        original_sections = [
            SectionNode(
                id="sec_cardiology",
                url="https://testsite.com/doctors",
                anchor_id="cardio-head",
                title="Cardiology & Heart OPD",
                heading_path=["Departments", "Super-Specialty", "Cardiology"],
                content="Consult Dr. Sharma for interventional cardiology and ECG tests.",
                keywords=["cardiology", "sharma", "ecg", "heart", "angioplasty"],
                action_type="book",
                action_label="Book Appointment",
                action_url="https://testsite.com/book?dept=cardio",
                metadata={"fee": "800", "timings": "10am-2pm"}
            ),
            SectionNode(
                id="sec_emergency",
                url="https://testsite.com/emergency",
                anchor_id="trauma",
                title="24/7 Trauma and Emergency Care",
                heading_path=["Services", "Emergency"],
                content="Immediate triage, ambulance service, and trauma resuscitation.",
                keywords=["emergency", "ambulance", "triage", "24/7"],
                action_type="call",
                action_label="Call Helpline",
                action_url="tel:+911234567890",
                metadata={"open": "24/7"}
            )
        ]

        db.save_sections(site_id, original_sections)

        # Reload from fresh DB manager instance
        db_reloaded = DatabaseManager(temp_db_path)
        loaded_sections = db_reloaded.get_sections(site_id)

        assert len(loaded_sections) == 2

        sec_map = {s.id: s for s in loaded_sections}

        sec1 = sec_map["sec_cardiology"]
        assert sec1.title == "Cardiology & Heart OPD"
        assert sec1.heading_path == ["Departments", "Super-Specialty", "Cardiology"]
        assert sec1.keywords == ["cardiology", "sharma", "ecg", "heart", "angioplasty"]
        assert sec1.metadata["fee"] == "800"

        sec2 = sec_map["sec_emergency"]
        assert sec2.heading_path == ["Services", "Emergency"]
        assert sec2.keywords == ["emergency", "ambulance", "triage", "24/7"]
        assert sec2.action_type == "call"
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

def test_migration_from_legacy_schema():
    """Verify init_db cleanly migrates legacy SQLite tables lacking new columns."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        legacy_db_path = tf.name

    try:
        # Create legacy schema without heading_path_json and keywords_json
        conn = sqlite3.connect(legacy_db_path)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE sites (
            site_id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at REAL
        )
        """)
        cur.execute("""
        CREATE TABLE sections (
            id TEXT PRIMARY KEY,
            site_id TEXT NOT NULL,
            url TEXT NOT NULL,
            anchor_id TEXT,
            title TEXT,
            content TEXT,
            action_type TEXT,
            action_label TEXT,
            action_url TEXT,
            metadata_json TEXT
        )
        """)
        # Insert a legacy row
        cur.execute("""
        INSERT INTO sections (id, site_id, url, anchor_id, title, content, action_type, action_label, action_url, metadata_json)
        VALUES ('legacy_1', 'legacy-site', 'https://legacy.com', 'sec1', 'Legacy Title', 'Content', 'navigate', 'View', '', '{}')
        """)
        conn.commit()
        conn.close()

        # Run init_db / DatabaseManager which triggers migration
        db = DatabaseManager(legacy_db_path)

        # Check that table info now contains heading_path_json and keywords_json
        conn = sqlite3.connect(legacy_db_path)
        cur = conn.cursor()
        cols = [c[1] for c in cur.execute("PRAGMA table_info(sections)").fetchall()]
        conn.close()

        assert "heading_path_json" in cols
        assert "keywords_json" in cols

        # Legacy row loads with default empty lists
        loaded = db.get_sections("legacy-site")
        assert len(loaded) == 1
        assert loaded[0].heading_path == []
        assert loaded[0].keywords == []

        # Saving new sections with keywords works
        db.save_sections("legacy-site", [
            SectionNode(
                id="new_1",
                url="https://legacy.com/new",
                title="New Section",
                heading_path=["Path", "To"],
                content="Some text",
                keywords=["migrated", "success"]
            )
        ])

        reloaded = db.get_sections("legacy-site")
        assert len(reloaded) == 1
        assert reloaded[0].keywords == ["migrated", "success"]
        assert reloaded[0].heading_path == ["Path", "To"]
    finally:
        if os.path.exists(legacy_db_path):
            os.remove(legacy_db_path)
