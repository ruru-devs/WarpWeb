"""
WarpWeb SQLite Database & Analytics Store
Stores:
- Sites & Crawled Sections
- Query Logs (Total searches, Click-through rates)
- Zero-Result Queries (The core B2B value metric)
- Lead Submissions (Visitor contact info captured on no-match)
- Manual Override Rules
"""
import sqlite3
import json
import time
from typing import List, Dict, Any, Optional
from app.models import SectionNode, OverrideRule, LeadCaptureRequest

DB_PATH = "warpweb.db"

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        site_id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sections (
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS query_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        query TEXT NOT NULL,
        results_count INTEGER,
        is_zero_match INTEGER,
        latency_ms REAL,
        timestamp REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        query TEXT NOT NULL,
        visitor_contact TEXT NOT NULL,
        note TEXT,
        timestamp REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        intent_phrase TEXT NOT NULL,
        target_url TEXT NOT NULL,
        action_label TEXT NOT NULL,
        pinned INTEGER DEFAULT 1
    )
    """)

    conn.commit()
    conn.close()

class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_site(self, site_id: str, domain: str, name: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sites (site_id, domain, name, created_at) VALUES (?, ?, ?, ?)",
                (site_id, domain, name, time.time())
            )

    def save_sections(self, site_id: str, sections: List[SectionNode]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM sections WHERE site_id = ?", (site_id,))
            for s in sections:
                conn.execute("""
                INSERT OR REPLACE INTO sections (id, site_id, url, anchor_id, title, content, action_type, action_label, action_url, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s.id, site_id, s.url, s.anchor_id, s.title, s.content,
                    s.action_type, s.action_label, s.action_url, json.dumps(s.metadata)
                ))

    def get_sections(self, site_id: str) -> List[SectionNode]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM sections WHERE site_id = ?", (site_id,)).fetchall()
            sections = []
            for r in rows:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                sections.append(SectionNode(
                    id=r["id"],
                    url=r["url"],
                    anchor_id=r["anchor_id"],
                    title=r["title"],
                    content=r["content"],
                    action_type=r["action_type"] or "navigate",
                    action_label=r["action_label"],
                    action_url=r["action_url"],
                    metadata=meta
                ))
            return sections

    def log_query(self, site_id: str, query: str, results_count: int, latency_ms: float):
        is_zero = 1 if results_count == 0 else 0
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO query_logs (site_id, query, results_count, is_zero_match, latency_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (site_id, query, results_count, is_zero, latency_ms, time.time()))

    def save_lead(self, lead: LeadCaptureRequest):
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO leads (site_id, query, visitor_contact, note, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """, (lead.site_id, lead.query, lead.visitor_contact, lead.note, time.time()))

    def get_overrides(self, site_id: str) -> List[OverrideRule]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM overrides WHERE site_id = ?", (site_id,)).fetchall()
            return [
                OverrideRule(
                    site_id=r["site_id"],
                    intent_phrase=r["intent_phrase"],
                    target_url=r["target_url"],
                    action_label=r["action_label"],
                    pinned=bool(r["pinned"])
                )
                for r in rows
            ]

    def add_override(self, rule: OverrideRule):
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO overrides (site_id, intent_phrase, target_url, action_label, pinned)
            VALUES (?, ?, ?, ?, ?)
            """, (rule.site_id, rule.intent_phrase, rule.target_url, rule.action_label, 1 if rule.pinned else 0))

    def get_analytics(self, site_id: str) -> Dict[str, Any]:
        with self._get_conn() as conn:
            total_queries = conn.execute("SELECT COUNT(*) FROM query_logs WHERE site_id = ?", (site_id,)).fetchone()[0]
            zero_matches = conn.execute("SELECT COUNT(*) FROM query_logs WHERE site_id = ? AND is_zero_match = 1", (site_id,)).fetchone()[0]
            
            # Top queries
            top_q_rows = conn.execute("""
            SELECT query, COUNT(*) as count 
            FROM query_logs 
            WHERE site_id = ? 
            GROUP BY query 
            ORDER BY count DESC LIMIT 10
            """, (site_id,)).fetchall()
            top_queries = [{"query": r["query"], "count": r["count"]} for r in top_q_rows]

            # Zero match queries (The Findability Report Goldmine)
            zero_q_rows = conn.execute("""
            SELECT query, COUNT(*) as count 
            FROM query_logs 
            WHERE site_id = ? AND is_zero_match = 1 
            GROUP BY query 
            ORDER BY count DESC LIMIT 10
            """, (site_id,)).fetchall()
            lost_queries = [{"query": r["query"], "count": r["count"]} for r in zero_q_rows]

            # Leads
            leads_rows = conn.execute("""
            SELECT * FROM leads WHERE site_id = ? ORDER BY timestamp DESC LIMIT 20
            """, (site_id,)).fetchall()
            leads = [
                {
                    "query": r["query"],
                    "contact": r["visitor_contact"],
                    "note": r["note"],
                    "timestamp": r["timestamp"]
                }
                for r in leads_rows
            ]

            findability_rate = round(((total_queries - zero_matches) / total_queries * 100), 1) if total_queries > 0 else 100.0

            return {
                "total_queries": total_queries,
                "zero_matches": zero_matches,
                "findability_rate": findability_rate,
                "top_queries": top_queries,
                "lost_queries": lost_queries,
                "recent_leads": leads
            }
