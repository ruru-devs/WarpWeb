"""
WarpWeb SQLite Database & Analytics Store
Stores:
- Sites & Crawled Sections (with owner api_key_hash)
- Query Logs (Total searches, Click-through rates)
- Zero-Result Queries (The core B2B value metric)
- Lead Submissions (Visitor contact info captured on no-match)
- Manual Override Rules
"""
import sqlite3
import json
import time
import hashlib
from typing import List, Dict, Any, Optional
import numpy as np
from app.models import SectionNode, OverrideRule, LeadCaptureRequest, SynonymRule

DB_PATH = "warpweb.db"

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        site_id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at REAL,
        api_key_hash TEXT
    )
    """)

    # Check and run migration if api_key_hash column is missing
    site_cols = [c[1] for c in cur.execute("PRAGMA table_info(sites)").fetchall()]
    if "api_key_hash" not in site_cols:
        cur.execute("ALTER TABLE sites ADD COLUMN api_key_hash TEXT")

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
        metadata_json TEXT,
        heading_path_json TEXT,
        keywords_json TEXT,
        embedding_blob BLOB,
        actions_json TEXT,
        content_hash TEXT
    )
    """)

    # Check and run migration if columns are missing
    section_cols = [c[1] for c in cur.execute("PRAGMA table_info(sections)").fetchall()]
    if "heading_path_json" not in section_cols:
        cur.execute("ALTER TABLE sections ADD COLUMN heading_path_json TEXT")
    if "keywords_json" not in section_cols:
        cur.execute("ALTER TABLE sections ADD COLUMN keywords_json TEXT")
    if "embedding_blob" not in section_cols:
        cur.execute("ALTER TABLE sections ADD COLUMN embedding_blob BLOB")
    if "actions_json" not in section_cols:
        cur.execute("ALTER TABLE sections ADD COLUMN actions_json TEXT")
    if "content_hash" not in section_cols:
        cur.execute("ALTER TABLE sections ADD COLUMN content_hash TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS crawl_jobs (
        site_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        pages_crawled INTEGER DEFAULT 0,
        sections_indexed INTEGER DEFAULT 0,
        error_message TEXT,
        started_at REAL,
        finished_at REAL
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
    CREATE TABLE IF NOT EXISTS click_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        query_id INTEGER,
        query TEXT,
        result_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        target_url TEXT NOT NULL,
        timestamp REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS search_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        query TEXT,
        is_positive INTEGER NOT NULL,
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
        consent INTEGER DEFAULT 1,
        consent_text TEXT,
        consent_timestamp REAL,
        timestamp REAL
    )
    """)

    lead_cols = [c[1] for c in cur.execute("PRAGMA table_info(leads)").fetchall()]
    if "consent" not in lead_cols:
        cur.execute("ALTER TABLE leads ADD COLUMN consent INTEGER DEFAULT 1")
    if "consent_text" not in lead_cols:
        cur.execute("ALTER TABLE leads ADD COLUMN consent_text TEXT")
    if "consent_timestamp" not in lead_cols:
        cur.execute("ALTER TABLE leads ADD COLUMN consent_timestamp REAL")

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS synonyms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id TEXT NOT NULL,
        phrase TEXT NOT NULL,
        canonical TEXT NOT NULL
    )
    """)

    # Seed demo synonyms if table is empty
    existing_syn_count = cur.execute("SELECT COUNT(*) FROM synonyms").fetchone()[0]
    if existing_syn_count == 0:
        demo_synonyms = [
            # ApexCare Demo
            ("apexcare-clinic", "dil ki bimari", "cardiology heart failure"),
            ("apexcare-clinic", "dil ke doctor", "cardiologist Dr Sharma"),
            ("apexcare-clinic", "haddi ka hospital", "orthopedics robotic spine surgery"),
            ("apexcare-clinic", "haddi ke doctor", "orthopedic Dr Patel"),
            ("apexcare-clinic", "charm rog", "dermatology skin clinic"),
            ("apexcare-clinic", "charm rog vibhag", "dermatology"),
            ("apexcare-clinic", "skin doctor", "dermatologist Dr Mehta"),
            ("apexcare-clinic", "ambulance bulana hai", "ambulance trauma emergency"),
            ("apexcare-clinic", "emergency number", "trauma ambulance emergency 24/7"),
            ("apexcare-clinic", "urgent care", "emergency trauma"),
            ("apexcare-clinic", "knee replacement", "orthopedics joint reconstruction"),
            # PulseTech Demo
            ("shoppulse-commerce", "earbuds ka backup", "battery life earbuds playback"),
            ("shoppulse-commerce", "battery backup", "battery life playback"),
            ("shoppulse-commerce", "paise wapas", "30-day money-back guarantee return policy"),
            ("shoppulse-commerce", "paani me", "IPX7 waterproof sweatproof earbuds"),
            ("shoppulse-commerce", "halka headphone", "lightweight commuter headphone"),
            ("shoppulse-commerce", "sabse accha", "flagship reference"),
            ("shoppulse-commerce", "warranty claim", "2-year manufacturer warranty terms"),
            ("shoppulse-commerce", "delivery kitne din", "express shipping delivery timelines"),
            ("shoppulse-commerce", "running", "gym workout IPX7 sweatproof")
        ]
        cur.executemany("INSERT INTO synonyms (site_id, phrase, canonical) VALUES (?, ?, ?)", demo_synonyms)

    # Seed demo keys if sites exist without api_key_hash
    demo_keys = {
        "apexcare-clinic": "ww_dev_apexcare_secret",
        "shoppulse-commerce": "ww_dev_shoppulse_secret"
    }
    for sid, k in demo_keys.items():
        k_hash = hashlib.sha256(k.encode("utf-8")).hexdigest()
        cur.execute(
            "UPDATE sites SET api_key_hash = ? WHERE site_id = ? AND (api_key_hash IS NULL OR api_key_hash = '')",
            (k_hash, sid)
        )

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

    def save_site(self, site_id: str, domain: str, name: str, api_key_hash: Optional[str] = None):
        with self._get_conn() as conn:
            # Preserve existing api_key_hash if not provided
            existing = conn.execute("SELECT api_key_hash FROM sites WHERE site_id = ?", (site_id,)).fetchone()
            final_hash = api_key_hash if api_key_hash is not None else (existing["api_key_hash"] if existing else None)

            conn.execute(
                """
                INSERT OR REPLACE INTO sites (site_id, domain, name, created_at, api_key_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (site_id, domain, name, time.time(), final_hash)
            )

    def get_site(self, site_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM sites WHERE site_id = ?", (site_id,)).fetchone()
            if not row:
                return None
            return {
                "site_id": row["site_id"],
                "domain": row["domain"],
                "name": row["name"],
                "created_at": row["created_at"],
                "api_key_hash": row["api_key_hash"]
            }

    def set_site_api_key(self, site_id: str, raw_key: str):
        k_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with self._get_conn() as conn:
            conn.execute("UPDATE sites SET api_key_hash = ? WHERE site_id = ?", (k_hash, site_id))

    def save_sections(self, site_id: str, sections: List[SectionNode]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM sections WHERE site_id = ?", (site_id,))
            for s in sections:
                conn.execute("""
                INSERT OR REPLACE INTO sections (
                    id, site_id, url, anchor_id, title, content,
                    action_type, action_label, action_url, metadata_json,
                    heading_path_json, keywords_json, actions_json, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s.id, site_id, s.url, s.anchor_id, s.title, s.content,
                    s.action_type, s.action_label, s.action_url, json.dumps(s.metadata),
                    json.dumps(s.heading_path), json.dumps(s.keywords),
                    json.dumps(s.actions), s.content_hash
                ))

    def get_sections(self, site_id: str) -> List[SectionNode]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM sections WHERE site_id = ?", (site_id,)).fetchall()
            sections = []
            for r in rows:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                heading_path = []
                if "heading_path_json" in r.keys() and r["heading_path_json"]:
                    try:
                        heading_path = json.loads(r["heading_path_json"])
                    except Exception:
                        heading_path = []
                keywords = []
                if "keywords_json" in r.keys() and r["keywords_json"]:
                    try:
                        keywords = json.loads(r["keywords_json"])
                    except Exception:
                        keywords = []
                actions = []
                if "actions_json" in r.keys() and r["actions_json"]:
                    try:
                        actions = json.loads(r["actions_json"])
                    except Exception:
                        actions = []
                content_hash = r["content_hash"] if "content_hash" in r.keys() else None

                sections.append(SectionNode(
                    id=r["id"],
                    url=r["url"],
                    anchor_id=r["anchor_id"],
                    title=r["title"],
                    heading_path=heading_path,
                    content=r["content"],
                    keywords=keywords,
                    action_type=r["action_type"] or "navigate",
                    action_label=r["action_label"],
                    action_url=r["action_url"],
                    actions=actions,
                    content_hash=content_hash,
                    metadata=meta
                ))
            return sections

    def log_query(self, site_id: str, query: str, results_count: int, latency_ms: float) -> int:
        is_zero = 1 if results_count == 0 else 0
        with self._get_conn() as conn:
            cur = conn.execute("""
            INSERT INTO query_logs (site_id, query, results_count, is_zero_match, latency_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (site_id, query, results_count, is_zero, latency_ms, time.time()))
            return cur.lastrowid

    def log_click(
        self,
        site_id: str,
        result_id: str,
        rank: int,
        target_url: str,
        query_id: Optional[int] = None,
        query: Optional[str] = None
    ) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
            INSERT INTO click_events (site_id, query_id, query, result_id, rank, target_url, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (site_id, query_id, query, result_id, rank, target_url, time.time()))
            return cur.lastrowid

    def save_feedback(self, site_id: str, is_positive: bool, query: Optional[str] = None) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
            INSERT INTO search_feedback (site_id, query, is_positive, timestamp)
            VALUES (?, ?, ?, ?)
            """, (site_id, query, 1 if is_positive else 0, time.time()))
            return cur.lastrowid

    def save_lead(self, lead: LeadCaptureRequest):
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO leads (site_id, query, visitor_contact, note, consent, consent_text, consent_timestamp, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.site_id,
                lead.query,
                lead.visitor_contact,
                lead.note,
                1 if lead.consent else 0,
                lead.consent_text,
                lead.consent_timestamp or time.time(),
                lead.created_at or time.time()
            ))

    def delete_lead(self, site_id: str, lead_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM leads WHERE site_id = ? AND id = ?", (site_id, lead_id))
            return cur.rowcount > 0

    def export_site_data(self, site_id: str) -> Dict[str, Any]:
        with self._get_conn() as conn:
            site = conn.execute("SELECT site_id, domain, name, created_at FROM sites WHERE site_id = ?", (site_id,)).fetchone()
            if not site:
                return {}

            leads = [
                dict(r) for r in conn.execute(
                    "SELECT id, query, visitor_contact, note, consent, consent_text, consent_timestamp, timestamp FROM leads WHERE site_id = ? ORDER BY timestamp DESC",
                    (site_id,)
                ).fetchall()
            ]

            queries = [
                dict(r) for r in conn.execute(
                    "SELECT id, query, results_count, is_zero_match, latency_ms, timestamp FROM query_logs WHERE site_id = ? ORDER BY timestamp DESC",
                    (site_id,)
                ).fetchall()
            ]

            clicks = [
                dict(r) for r in conn.execute(
                    "SELECT id, query_id, query, result_id, rank, target_url, timestamp FROM click_events WHERE site_id = ? ORDER BY timestamp DESC",
                    (site_id,)
                ).fetchall()
            ]

            feedback = [
                dict(r) for r in conn.execute(
                    "SELECT id, query, is_positive, timestamp FROM search_feedback WHERE site_id = ? ORDER BY timestamp DESC",
                    (site_id,)
                ).fetchall()
            ]

            overrides = [
                dict(r) for r in conn.execute(
                    "SELECT id, intent_phrase, target_url, action_label, pinned FROM overrides WHERE site_id = ?",
                    (site_id,)
                ).fetchall()
            ]

            synonyms = [
                dict(r) for r in conn.execute(
                    "SELECT id, phrase, canonical FROM synonyms WHERE site_id = ?",
                    (site_id,)
                ).fetchall()
            ]

            return {
                "site": dict(site),
                "leads": leads,
                "query_logs": queries,
                "click_events": clicks,
                "feedback": feedback,
                "overrides": overrides,
                "synonyms": synonyms,
                "exported_at": time.time()
            }

    def delete_site_data(self, site_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM leads WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM query_logs WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM click_events WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM search_feedback WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM overrides WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM synonyms WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM sections WHERE site_id = ?", (site_id,))
            conn.execute("DELETE FROM crawl_jobs WHERE site_id = ?", (site_id,))
            return True

    def cleanup_old_data(self, site_id: str, days: int = 90) -> Dict[str, int]:
        cutoff = time.time() - (days * 86400)
        with self._get_conn() as conn:
            leads_del = conn.execute("DELETE FROM leads WHERE site_id = ? AND timestamp < ?", (site_id, cutoff)).rowcount
            queries_del = conn.execute("DELETE FROM query_logs WHERE site_id = ? AND timestamp < ?", (site_id, cutoff)).rowcount
            clicks_del = conn.execute("DELETE FROM click_events WHERE site_id = ? AND timestamp < ?", (site_id, cutoff)).rowcount
            feedback_del = conn.execute("DELETE FROM search_feedback WHERE site_id = ? AND timestamp < ?", (site_id, cutoff)).rowcount
            return {
                "leads_purged": leads_del,
                "queries_purged": queries_del,
                "clicks_purged": clicks_del,
                "feedback_purged": feedback_del
            }

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

    def save_section_embeddings(self, site_id: str, embeddings: Dict[str, np.ndarray]):
        with self._get_conn() as conn:
            for sec_id, emb in embeddings.items():
                blob = emb.astype(np.float32).tobytes()
                conn.execute(
                    "UPDATE sections SET embedding_blob = ? WHERE id = ? AND site_id = ?",
                    (blob, sec_id, site_id)
                )

    def get_section_embeddings(self, site_id: str) -> Dict[str, np.ndarray]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, embedding_blob FROM sections WHERE site_id = ? AND embedding_blob IS NOT NULL",
                (site_id,)
            ).fetchall()
            result = {}
            for r in rows:
                if r["embedding_blob"]:
                    result[r["id"]] = np.frombuffer(r["embedding_blob"], dtype=np.float32)
            return result

    def get_synonyms(self, site_id: str) -> List[SynonymRule]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM synonyms WHERE site_id = ?", (site_id,)).fetchall()
            return [
                SynonymRule(
                    id=r["id"],
                    site_id=r["site_id"],
                    phrase=r["phrase"],
                    canonical=r["canonical"]
                )
                for r in rows
            ]

    def add_synonym(self, rule: SynonymRule) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO synonyms (site_id, phrase, canonical) VALUES (?, ?, ?)",
                (rule.site_id, rule.phrase, rule.canonical)
            )
            return cur.lastrowid

    def delete_synonym(self, site_id: str, synonym_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM synonyms WHERE site_id = ? AND id = ?", (site_id, synonym_id))
            return cur.rowcount > 0

    def update_crawl_job(
        self,
        site_id: str,
        status: str,
        pages_crawled: int = 0,
        sections_indexed: int = 0,
        error_message: Optional[str] = None
    ):
        with self._get_conn() as conn:
            now = time.time()
            existing = conn.execute("SELECT started_at FROM crawl_jobs WHERE site_id = ?", (site_id,)).fetchone()
            started_at = existing["started_at"] if existing else now
            finished_at = now if status in ["completed", "failed"] else None
            conn.execute("""
            INSERT OR REPLACE INTO crawl_jobs (site_id, status, pages_crawled, sections_indexed, error_message, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (site_id, status, pages_crawled, sections_indexed, error_message, started_at, finished_at))

    def get_crawl_job(self, site_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM crawl_jobs WHERE site_id = ?", (site_id,)).fetchone()
            if not row:
                return None
            return {
                "site_id": row["site_id"],
                "status": row["status"],
                "pages_crawled": row["pages_crawled"],
                "sections_indexed": row["sections_indexed"],
                "error_message": row["error_message"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"]
            }

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
                    "id": r["id"],
                    "query": r["query"],
                    "contact": r["visitor_contact"],
                    "note": r["note"],
                    "consent": bool(r["consent"]) if "consent" in r.keys() else True,
                    "consent_text": r["consent_text"] if "consent_text" in r.keys() else None,
                    "consent_timestamp": r["consent_timestamp"] if "consent_timestamp" in r.keys() else None,
                    "timestamp": r["timestamp"]
                }
                for r in leads_rows
            ]

            findability_rate = round(((total_queries - zero_matches) / total_queries * 100), 1) if total_queries > 0 else 100.0

            total_clicks = conn.execute("SELECT COUNT(*) FROM click_events WHERE site_id = ?", (site_id,)).fetchone()[0]
            ctr = round((total_clicks / total_queries * 100), 1) if total_queries > 0 else 0.0

            pos_feedback = conn.execute("SELECT COUNT(*) FROM search_feedback WHERE site_id = ? AND is_positive = 1", (site_id,)).fetchone()[0]
            neg_feedback = conn.execute("SELECT COUNT(*) FROM search_feedback WHERE site_id = ? AND is_positive = 0", (site_id,)).fetchone()[0]

            return {
                "total_queries": total_queries,
                "zero_matches": zero_matches,
                "findability_rate": findability_rate,
                "total_clicks": total_clicks,
                "click_through_rate": ctr,
                "positive_feedback": pos_feedback,
                "negative_feedback": neg_feedback,
                "top_queries": top_queries,
                "lost_queries": lost_queries,
                "recent_leads": leads
            }
