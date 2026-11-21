"""
WarpWeb Hybrid Search Engine
Combines:
1. Exact & Substring Overrides (Highest priority, pinned)
2. BM25 Lexical Ranking (Exact keyword/token scoring)
3. Precomputed Dense Sentence Embeddings (Cosine similarity on CPU)
4. Per-Site Intent Aliases / Synonyms Expansion
5. Calibrated Confidence Thresholding (Eliminating junk/false positives)
6. Truthful Match Labeling ('override', 'hybrid', 'semantic', 'lexical')
"""
import re
import os
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from rank_bm25 import BM25Plus

from app.models import SectionNode, SearchResultItem, OverrideRule, SynonymRule
from app.indexer.embeddings import EmbeddingService

# Tunable scoring weights
DEFAULT_BM25_WEIGHT = float(os.getenv("WARPWEB_BM25_WEIGHT", "0.40"))
DEFAULT_SEMANTIC_WEIGHT = float(os.getenv("WARPWEB_SEMANTIC_WEIGHT", "0.45"))
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("WARPWEB_CONFIDENCE_THRESHOLD", "0.30"))

class HybridIndex:
    def __init__(self, site_id: str):
        self.site_id = site_id
        self.sections: List[SectionNode] = []
        self.section_map: Dict[str, SectionNode] = {}
        self.bm25: Optional[BM25Plus] = None
        self.corpus_tokens: List[List[str]] = []
        self.overrides: List[OverrideRule] = []
        self.synonyms: List[SynonymRule] = []

        # Vector embeddings matrix: shape (N, D)
        self.doc_embeddings: Optional[np.ndarray] = None
        self.embedding_model_name = os.getenv("WARPWEB_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    def set_overrides(self, rules: List[OverrideRule]):
        self.overrides = rules

    def set_synonyms(self, synonyms: List[SynonymRule]):
        self.synonyms = synonyms

    def index_sections(
        self,
        sections: List[SectionNode],
        cached_embeddings: Optional[Dict[str, np.ndarray]] = None,
        db_manager: Optional[Any] = None
    ):
        self.sections = sections
        self.section_map = {s.id: s for s in sections}
        
        # 1. Tokenize sections for BM25
        self.corpus_tokens = []
        texts_to_embed = []
        doc_embs_list = []
        missing_indices = []

        for idx, s in enumerate(sections):
            full_text = f"{s.title} {' '.join(s.heading_path)} {s.content} {' '.join(s.keywords)}"
            tokens = self._tokenize(full_text)
            self.corpus_tokens.append(tokens)

            # Check if embedding is already cached
            if cached_embeddings and s.id in cached_embeddings:
                doc_embs_list.append(cached_embeddings[s.id])
            else:
                doc_embs_list.append(None)
                missing_indices.append(idx)
                # Text for embedding representation
                embed_text = f"{s.title}. {' '.join(s.heading_path)}. {s.content[:400]}"
                texts_to_embed.append(embed_text)

        if self.corpus_tokens:
            self.bm25 = BM25Plus(self.corpus_tokens)

        # 2. Compute missing embeddings in batch
        if missing_indices and texts_to_embed:
            new_embs = EmbeddingService.embed_documents(texts_to_embed, self.embedding_model_name)
            new_cache_to_persist = {}
            for list_idx, orig_idx in enumerate(missing_indices):
                emb = new_embs[list_idx]
                doc_embs_list[orig_idx] = emb
                s = sections[orig_idx]
                new_cache_to_persist[s.id] = emb

            if db_manager and new_cache_to_persist:
                db_manager.save_section_embeddings(self.site_id, new_cache_to_persist)

        if doc_embs_list and all(e is not None for e in doc_embs_list):
            self.doc_embeddings = np.array(doc_embs_list, dtype=np.float32)
        else:
            self.doc_embeddings = None

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b[a-zA-Z0-9_-]{2,}\b', text.lower())

    def _expand_query_with_synonyms(self, raw_query: str) -> Tuple[str, List[str]]:
        """Expands query with site-specific intent aliases/synonyms."""
        q_lower = raw_query.lower()
        expanded_terms = []
        for syn in self.synonyms:
            if syn.phrase.lower() in q_lower:
                expanded_terms.append(syn.canonical)

        if expanded_terms:
            expanded_query = f"{raw_query} {' '.join(expanded_terms)}"
        else:
            expanded_query = raw_query

        return expanded_query, expanded_terms

    def search(
        self,
        query: str,
        top_k: int = 5,
        bm25_weight: float = DEFAULT_BM25_WEIGHT,
        semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    ) -> List[SearchResultItem]:
        q_clean = query.strip()
        if not q_clean or not self.sections:
            return []

        q_lower = q_clean.lower()

        # 1. Check Manual Overrides first (Highest Priority)
        for rule in self.overrides:
            if rule.pinned and (rule.intent_phrase.lower() in q_lower or q_lower in rule.intent_phrase.lower()):
                return [SearchResultItem(
                    id=f"override_{rule.intent_phrase}",
                    title=rule.action_label,
                    url=rule.target_url,
                    target_url=rule.target_url,
                    snippet=f"Direct match for: {rule.intent_phrase}",
                    score=999.0,
                    match_type="override",
                    action_label=rule.action_label,
                    action_type="navigate"
                )]

        # 2. Apply Synonym / Intent-Alias Expansion
        expanded_query, added_terms = self._expand_query_with_synonyms(q_clean)
        q_tokens = self._tokenize(expanded_query)

        # 3. BM25 Lexical Scores
        bm25_raw = self.bm25.get_scores(q_tokens) if self.bm25 and q_tokens else np.zeros(len(self.sections))
        # Ensure non-negative
        bm25_raw = np.maximum(bm25_raw, 0.0)
        max_bm25 = float(np.max(bm25_raw)) if len(bm25_raw) > 0 else 0.0
        bm25_norm = (bm25_raw / max_bm25) if max_bm25 > 0.0 else np.zeros(len(self.sections))

        # 4. Dense Semantic Cosine Similarity
        if self.doc_embeddings is not None and len(self.doc_embeddings) == len(self.sections):
            query_emb = EmbeddingService.embed_query(expanded_query, self.embedding_model_name)
            dense_scores = EmbeddingService.cosine_similarity(query_emb, self.doc_embeddings)
            # Clip cosine similarity to [0.0, 1.0] for scoring
            dense_norm = np.clip(dense_scores, 0.0, 1.0)
        else:
            dense_norm = np.zeros(len(self.sections))

        # 5. Hybrid Combination & Calibrated Thresholding
        scored_candidates: List[Tuple[float, SectionNode, str]] = []

        orig_tokens = self._tokenize(q_lower)

        for idx, sec in enumerate(self.sections):
            b_norm = float(bm25_norm[idx])
            d_norm = float(dense_norm[idx])

            # Calculate Title and Intent Boosts
            title_lower = sec.title.lower()
            content_lower = sec.content.lower()

            boost = 0.0
            # Title exact substring match
            if q_lower in title_lower:
                boost += 0.25
            # Token matches in title (including expanded synonym tokens)
            elif any(tok in title_lower for tok in q_tokens):
                boost += 0.14

            # Keyword match boost
            sec_keywords_lower = [k.lower() for k in sec.keywords]
            if any(tok in sec_keywords_lower for tok in q_tokens):
                boost += 0.10

            # Action/Intent keywords
            if any(act in q_lower for act in ["book", "appointment", "price", "cost", "fee", "timings", "hours", "return", "warranty", "specs"]):
                if sec.action_type in ["book", "purchase"] or "price" in sec.metadata or "timings" in sec.metadata or sec.anchor_id in ["return-policy", "warranty-terms"]:
                    boost += 0.06

            # Combined Score with balanced modality scaling
            if b_norm > 0.0 and d_norm > 0.0:
                combined_score = (bm25_weight * b_norm) + (semantic_weight * d_norm) + boost
            elif b_norm > 0.0:
                combined_score = (0.75 * b_norm) + boost
            else:
                combined_score = (0.85 * d_norm) + boost

            # Truthful Match Label Assignment
            if b_norm >= 0.35 and d_norm >= 0.35:
                match_type = "hybrid"
            elif d_norm >= 0.38:
                match_type = "semantic"
            elif b_norm >= 0.25:
                match_type = "lexical"
            else:
                match_type = "hybrid" if combined_score >= confidence_threshold else "low_confidence"

            # Confidence Threshold: Reject low confidence noise
            # If semantic embedding indicates the domain is completely unrelated (cosine < 0.20)
            # and there is no strong title match, treat as noise/false-positive
            if d_norm < 0.20 and (q_lower not in title_lower) and b_norm < 0.70:
                continue

            has_sufficient_grounding = (d_norm >= 0.35) or (b_norm >= 0.25) or (boost >= 0.12 and (b_norm > 0 or d_norm > 0.22))

            if combined_score >= confidence_threshold and has_sufficient_grounding:
                scored_candidates.append((combined_score, sec, match_type))

        # Sort descending by combined score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        results: List[SearchResultItem] = []
        for score, sec, match_type in scored_candidates[:top_k]:
            target_url = sec.url
            if sec.anchor_id:
                target_url = f"{sec.url}#{sec.anchor_id}"

            snippet = sec.content[:160] + "..." if len(sec.content) > 160 else sec.content

            results.append(SearchResultItem(
                id=sec.id,
                title=sec.title,
                url=sec.url,
                anchor_id=sec.anchor_id,
                target_url=target_url,
                snippet=snippet,
                score=round(score, 3),
                match_type=match_type,
                action_label=sec.action_label or "Jump to section",
                action_type=sec.action_type,
                metadata=sec.metadata
            ))

        return results
