"""
Search Quality and Hybrid Ranking Tests (Phase 2):
- Sentence embedding inference & cosine similarity
- Hybrid ranking with normalized BM25 + dense embedding
- Calibrated confidence thresholding (zero results on out-of-domain junk)
- Truthful match_type labeling ('override', 'hybrid', 'semantic', 'lexical')
- Owner-defined intent alias / synonym mechanism & API endpoints
"""
import pytest
from fastapi.testclient import TestClient
import numpy as np

from app.main import app, db, active_indices
from app.models import SectionNode, SynonymRule, OverrideRule
from app.indexer.embeddings import EmbeddingService
from app.indexer.hybrid_search import HybridIndex

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_search_test():
    active_indices.clear()
    site_id = "test-search-site"
    db.save_site(site_id, "testsearch.com", "Test Search Site")
    db.set_site_api_key(site_id, "ww_dev_test_secret")

    sections = [
        SectionNode(
            id="sec_cardio",
            url="https://testsearch.com/departments/cardio",
            anchor_id="cardio-center",
            title="Cardiology & Heart Failure Center",
            heading_path=["Departments", "Cardiology"],
            content="Comprehensive coronary angioplasty, heart failure clinic, and pacemaker implants.",
            keywords=["heart", "cardio", "angioplasty", "pacemaker"],
            action_type="book",
            action_label="Book Appointment"
        ),
        SectionNode(
            id="sec_earbuds",
            url="https://testsearch.com/products/earbuds",
            anchor_id="earbuds-anc",
            title="AeroBuds Pro Active Noise Cancelling",
            heading_path=["Products", "Audio"],
            content="True wireless stereo earbuds with 35 hour battery playback and IPX7 sweatproof design.",
            keywords=["earbuds", "wireless", "battery", "sweatproof"],
            action_type="purchase",
            action_label="Buy Now"
        )
    ]
    db.save_sections(site_id, sections)

    # Precompute and save embeddings
    idx = HybridIndex(site_id)
    idx.index_sections(sections, db_manager=db)

def test_embedding_service_cosine_similarity():
    """Verify EmbeddingService produces valid unit vectors and correct similarity ordering."""
    vec1 = EmbeddingService.embed_query("heart specialist doctor")
    vec2 = EmbeddingService.embed_query("cardiology clinic")
    vec_unrelated = EmbeddingService.embed_query("airline luggage flight delay")

    sim_related = float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))
    sim_unrelated = float(np.dot(vec1, vec_unrelated) / (np.linalg.norm(vec1) * np.linalg.norm(vec_unrelated)))

    assert sim_related > 0.45
    assert sim_unrelated < 0.25
    assert sim_related > sim_unrelated

def test_truthful_match_types():
    """Verify truthful match_type labeling (override, hybrid/semantic/lexical)."""
    site_id = "test-search-site"
    db.add_override(OverrideRule(
        site_id=site_id,
        intent_phrase="vip emergency",
        target_url="https://testsearch.com/departments/cardio#cardio-center",
        action_label="Emergency Jump"
    ))

    # 1. Override match
    res_override = client.post("/api/search", json={
        "site_id": site_id,
        "query": "vip emergency",
        "top_k": 3
    }).json()
    assert len(res_override["results"]) == 1
    assert res_override["results"][0]["match_type"] == "override"

    # 2. Semantic / Hybrid match on paraphrase without exact keywords
    res_semantic = client.post("/api/search", json={
        "site_id": site_id,
        "query": "doctor for cardiac failure",
        "top_k": 3
    }).json()
    assert len(res_semantic["results"]) >= 1
    assert res_semantic["results"][0]["match_type"] in ["hybrid", "semantic"]

def test_confidence_threshold_blocks_junk():
    """Verify out-of-domain queries return zero results instead of junk."""
    site_id = "test-search-site"
    res = client.post("/api/search", json={
        "site_id": site_id,
        "query": "fresh organic vegetable grocery delivery",
        "top_k": 3
    }).json()
    assert res["zero_match"] is True
    assert len(res["results"]) == 0

def test_synonym_intent_alias_api_and_expansion():
    """Verify owner synonym API and automatic query expansion."""
    site_id = "test-search-site"
    headers = {"X-API-Key": "ww_dev_test_secret"}

    # Add synonym for Hinglish phrase
    add_res = client.post("/api/synonyms", headers=headers, json={
        "site_id": site_id,
        "phrase": "dil ki bimari",
        "canonical": "cardiology heart failure"
    })
    assert add_res.status_code == 200
    syn_id = add_res.json()["id"]

    # Verify synonym in list
    list_res = client.get(f"/api/synonyms/{site_id}", headers=headers)
    assert list_res.status_code == 200
    assert any(s["phrase"] == "dil ki bimari" for s in list_res.json())

    # Query with Hinglish synonym
    res = client.post("/api/search", json={
        "site_id": site_id,
        "query": "dil ki bimari treatment",
        "top_k": 3
    }).json()
    assert len(res["results"]) >= 1
    assert "Cardiology" in res["results"][0]["title"]

    # Delete synonym
    del_res = client.delete(f"/api/synonyms/{site_id}/{syn_id}", headers=headers)
    assert del_res.status_code == 200


def test_embedding_failure_graceful_degradation(monkeypatch):
    """
    Verify search pipeline gracefully degrades to BM25+ when embedding model fails:
    - Does not crash or return 500.
    - Sets model_status='degraded_bm25_only' in response and health check.
    - Accurately returns BM25+ results with synonyms and overrides.
    """
    site_id = "test-search-site"
    active_indices.clear()

    # Simulate ONNX runtime / embedding inference failure
    def mock_failing_embed_query(query, model_name=None):
        raise RuntimeError("Simulated ONNX Runtime OOM / GPU incompatibility failure")

    monkeypatch.setattr(EmbeddingService, "embed_query", mock_failing_embed_query)
    EmbeddingService._is_degraded = True

    # 1. Health check reports degradation
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["embedding_model_status"] == "degraded_bm25_only"

    # 2. Search query executes without 500 error
    search_res = client.post("/api/search", json={
        "site_id": site_id,
        "query": "cardiology heart failure",
        "top_k": 3
    })
    assert search_res.status_code == 200
    data = search_res.json()

    # 3. model_status indicates degraded mode
    assert data["model_status"] == "degraded_bm25_only"

    # 4. BM25+ fallback returns relevant match
    assert len(data["results"]) >= 1
    assert "Cardiology" in data["results"][0]["title"]
    assert data["results"][0]["match_type"] == "lexical"

    # Clean up state for subsequent tests
    EmbeddingService.reset_status()

