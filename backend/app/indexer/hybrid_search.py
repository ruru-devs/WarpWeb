"""
WarpWeb In-Memory / SQLite Hybrid Search Index
Supports:
1. Exact & Substring Overrides (instant pin matching)
2. BM25 Lexical Search (instant exact word/phrase scoring)
3. Normalized TF-IDF / Substring Intent Scoring (instant fallback with zero latency)
"""
import math
import re
from typing import List, Dict, Tuple, Optional
from rank_bm25 import BM25Okapi
from app.models import SectionNode, SearchResultItem, OverrideRule

class HybridIndex:
    def __init__(self, site_id: str):
        self.site_id = site_id
        self.sections: List[SectionNode] = []
        self.section_map: Dict[str, SectionNode] = {}
        self.bm25: Optional[BM25Okapi] = None
        self.corpus_tokens: List[List[str]] = []
        self.overrides: List[OverrideRule] = []

    def set_overrides(self, rules: List[OverrideRule]):
        self.overrides = rules

    def index_sections(self, sections: List[SectionNode]):
        self.sections = sections
        self.section_map = {s.id: s for s in sections}
        
        # Tokenize sections for BM25
        self.corpus_tokens = []
        for s in sections:
            full_text = f"{s.title} {' '.join(s.heading_path)} {s.content} {' '.join(s.keywords)}"
            tokens = self._tokenize(full_text)
            self.corpus_tokens.append(tokens)

        if self.corpus_tokens:
            self.bm25 = BM25Okapi(self.corpus_tokens)

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b[a-zA-Z0-9_-]{2,}\b', text.lower())

    def search(self, query: str, top_k: int = 5) -> List[SearchResultItem]:
        q_clean = query.strip().lower()
        if not q_clean or not self.sections:
            return []

        results: List[SearchResultItem] = []

        # 1. Check Manual Overrides first (Highest Priority)
        for rule in self.overrides:
            if rule.pinned and (rule.intent_phrase.lower() in q_clean or q_clean in rule.intent_phrase.lower()):
                results.append(SearchResultItem(
                    id=f"override_{rule.intent_phrase}",
                    title=rule.action_label,
                    url=rule.target_url,
                    target_url=rule.target_url,
                    snippet=f"Direct match for: {rule.intent_phrase}",
                    score=999.0,
                    match_type="override",
                    action_label=rule.action_label,
                    action_type="navigate"
                ))
                return results

        # 2. BM25 Lexical Ranking
        q_tokens = self._tokenize(q_clean)
        if not q_tokens:
            return []

        bm25_scores = self.bm25.get_scores(q_tokens) if self.bm25 else [0.0] * len(self.sections)

        # 3. Combine with Title/Keyword Intent Boost
        scored_candidates: List[Tuple[float, SectionNode, str]] = []
        for idx, sec in enumerate(self.sections):
            base_score = float(bm25_scores[idx]) if idx < len(bm25_scores) else 0.0

            # Only boost if there is already a positive lexical match from BM25
            if base_score > 0.0:
                title_lower = sec.title.lower()
                if any(tok in title_lower for tok in q_tokens):
                    base_score += 4.0
                if q_clean in title_lower:
                    base_score += 8.0 # exact substring match in title

                # Boost if section contains key actions requested
                if any(intent in q_clean for intent in ["book", "appointment", "reserve", "timings", "hours", "fee", "price", "cost", "buy"]):
                    if sec.action_type in ["book", "purchase"] or "price" in sec.metadata or "timings" in sec.metadata:
                        base_score += 3.5

            # Require a meaningful score threshold (avoid false positives on unrelated queries)
            if base_score >= 1.0:
                match_type = "exact_keyword" if base_score >= 4.0 else "semantic"
                scored_candidates.append((base_score, sec, match_type))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        for score, sec, match_type in scored_candidates[:top_k]:
            target_url = sec.url
            if sec.anchor_id:
                target_url = f"{sec.url}#{sec.anchor_id}"

            # Format concise readable snippet
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
