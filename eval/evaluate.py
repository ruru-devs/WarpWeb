"""
WarpWeb Search Evaluation Harness
Evaluates search retrieval quality across demo sites and query categories:
- Top-1 Accuracy (Exact Section & Page-Level)
- Recall@5 (Exact Section & Page-Level)
- MRR (Mean Reciprocal Rank)
- Zero-Result Rate (Positive vs Overall)
- False-Positive Rate (on queries that should return nothing)
- p50 and p95 Search Latency (ms)
"""
import sys
import os
import json
import time
import argparse
from typing import List, Dict, Any, Tuple
import numpy as np

# Ensure backend directory is in path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.db.storage import DatabaseManager
from app.indexer.hybrid_search import HybridIndex

def is_match(result: Any, expected_url: str, expected_anchor: str = None, exact: bool = True) -> bool:
    """Checks whether a SearchResultItem matches the expected ground truth."""
    if not expected_url:
        return False

    res_url = getattr(result, "url", "") or ""
    res_anchor = getattr(result, "anchor_id", "") or ""
    res_target = getattr(result, "target_url", "") or ""

    # Page level match
    # Strip protocol and domain for flexible matching
    def normalize_page(u: str) -> str:
        u_clean = u.split("#")[0].split("?")[0].rstrip("/")
        # Keep path portion after domain
        if "://" in u_clean:
            u_clean = u_clean.split("://", 1)[1]
            if "/" in u_clean:
                u_clean = "/" + u_clean.split("/", 1)[1]
        return u_clean

    page_matched = normalize_page(res_url) == normalize_page(expected_url) or \
                   normalize_page(res_target) == normalize_page(expected_url)

    if not exact:
        return page_matched

    if not page_matched:
        return False

    # If an expected anchor is specified, check anchor match
    if expected_anchor:
        anchor_matched = (res_anchor == expected_anchor) or (f"#{expected_anchor}" in res_target)
        return anchor_matched

    return True

def run_evaluation(
    dataset_path: str = "eval/queries.json",
    site_filter: str = None
) -> Dict[str, Any]:
    db = DatabaseManager()

    with open(dataset_path, "r", encoding="utf-8") as f:
        all_queries: List[Dict[str, Any]] = json.load(f)

    if site_filter:
        queries = [q for q in all_queries if q["site_id"] == site_filter]
    else:
        queries = all_queries

    # Preload indices per site
    indices: Dict[str, HybridIndex] = {}
    unique_sites = set(q["site_id"] for q in queries)
    for sid in unique_sites:
        idx = HybridIndex(sid)
        sections = db.get_sections(sid)
        overrides = db.get_overrides(sid)
        idx.set_overrides(overrides)
        idx.index_sections(sections)
        indices[sid] = idx

    pos_queries = [q for q in queries if q.get("should_match", True)]
    neg_queries = [q for q in queries if not q.get("should_match", True)]

    latencies: List[float] = []
    top1_exact_count = 0
    top1_page_count = 0
    recall5_exact_count = 0
    recall5_page_count = 0
    mrr_exact_sum = 0.0
    mrr_page_sum = 0.0

    pos_zero_count = 0
    neg_zero_count = 0
    neg_fp_count = 0

    category_stats: Dict[str, Dict[str, Any]] = {}
    site_stats: Dict[str, Dict[str, Any]] = {}

    for q in queries:
        sid = q["site_id"]
        query_text = q["query"]
        expected_url = q.get("expected_url")
        expected_anchor = q.get("expected_anchor")
        should_match = q.get("should_match", True)
        category = q.get("category", "general")

        index = indices[sid]

        t0 = time.perf_counter()
        results = index.search(query_text, top_k=5)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        # Initialize trackers for category & site breakdown
        for group_dict, key in [(category_stats, category), (site_stats, sid)]:
            if key not in group_dict:
                group_dict[key] = {
                    "total": 0, "pos": 0, "neg": 0,
                    "top1_exact": 0, "top1_page": 0,
                    "recall5_exact": 0, "recall5_page": 0,
                    "mrr_exact": 0.0, "zero": 0, "fp": 0,
                    "latencies": []
                }
            group_dict[key]["total"] += 1
            group_dict[key]["latencies"].append(lat)

        if not should_match:
            # Negative query
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["neg"] += 1

            if len(results) == 0:
                neg_zero_count += 1
            else:
                neg_fp_count += 1
                for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                    group_dict[key]["fp"] += 1
            continue

        # Positive query
        for group_dict, key in [(category_stats, category), (site_stats, sid)]:
            group_dict[key]["pos"] += 1

        if len(results) == 0:
            pos_zero_count += 1
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["zero"] += 1
            continue

        # Top-1 Check
        first = results[0]
        if is_match(first, expected_url, expected_anchor, exact=True):
            top1_exact_count += 1
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["top1_exact"] += 1
        if is_match(first, expected_url, expected_anchor, exact=False):
            top1_page_count += 1
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["top1_page"] += 1

        # Recall@5 and MRR Check
        found_exact_rank = 0
        found_page_rank = 0
        for rank_idx, res in enumerate(results, 1):
            if found_exact_rank == 0 and is_match(res, expected_url, expected_anchor, exact=True):
                found_exact_rank = rank_idx
            if found_page_rank == 0 and is_match(res, expected_url, expected_anchor, exact=False):
                found_page_rank = rank_idx

        if found_exact_rank > 0:
            recall5_exact_count += 1
            mrr_exact_sum += 1.0 / found_exact_rank
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["recall5_exact"] += 1
                group_dict[key]["mrr_exact"] += 1.0 / found_exact_rank

        if found_page_rank > 0:
            recall5_page_count += 1
            mrr_page_sum += 1.0 / found_page_rank
            for group_dict, key in [(category_stats, category), (site_stats, sid)]:
                group_dict[key]["recall5_page"] += 1

    total_pos = len(pos_queries)
    total_neg = len(neg_queries)
    total_all = len(queries)

    overall_metrics = {
        "total_queries": total_all,
        "positive_queries": total_pos,
        "negative_queries": total_neg,
        "top1_exact_accuracy": round((top1_exact_count / total_pos) * 100, 2) if total_pos else 0.0,
        "top1_page_accuracy": round((top1_page_count / total_pos) * 100, 2) if total_pos else 0.0,
        "recall5_exact": round((recall5_exact_count / total_pos) * 100, 2) if total_pos else 0.0,
        "recall5_page": round((recall5_page_count / total_pos) * 100, 2) if total_pos else 0.0,
        "mrr_exact": round(mrr_exact_sum / total_pos, 4) if total_pos else 0.0,
        "mrr_page": round(mrr_page_sum / total_pos, 4) if total_pos else 0.0,
        "zero_result_rate_overall": round(((pos_zero_count + neg_zero_count) / total_all) * 100, 2),
        "zero_result_rate_positive": round((pos_zero_count / total_pos) * 100, 2) if total_pos else 0.0,
        "false_positive_rate_negative": round((neg_fp_count / total_neg) * 100, 2) if total_neg else 0.0,
        "p50_latency_ms": round(float(np.percentile(latencies, 50)), 3) if latencies else 0.0,
        "p95_latency_ms": round(float(np.percentile(latencies, 95)), 3) if latencies else 0.0,
        "p99_latency_ms": round(float(np.percentile(latencies, 99)), 3) if latencies else 0.0,
    }

    return {
        "overall": overall_metrics,
        "by_category": category_stats,
        "by_site": site_stats
    }

def print_report(results: Dict[str, Any]):
    ov = results["overall"]
    print("=" * 70)
    print("WARPWEB SEARCH EVALUATION REPORT")
    print("=" * 70)
    print(f"Total Queries Evaluated: {ov['total_queries']} (Positive: {ov['positive_queries']}, Negative: {ov['negative_queries']})")
    print("-" * 70)
    print(f"Top-1 Accuracy (Exact Section):   {ov['top1_exact_accuracy']}%")
    print(f"Top-1 Accuracy (Page-Level):      {ov['top1_page_accuracy']}%")
    print(f"Recall@5 (Exact Section):         {ov['recall5_exact']}%")
    print(f"Recall@5 (Page-Level):            {ov['recall5_page']}%")
    print(f"MRR (Mean Reciprocal Rank Exact): {ov['mrr_exact']}")
    print(f"MRR (Page-Level):                 {ov['mrr_page']}")
    print(f"Zero-Result Rate (Positive Qs):   {ov['zero_result_rate_positive']}% (missed targets)")
    print(f"False-Positive Rate (Neg Qs):     {ov['false_positive_rate_negative']}% (spurious matches)")
    print("-" * 70)
    print(f"Latency p50:                      {ov['p50_latency_ms']} ms")
    print(f"Latency p95:                      {ov['p95_latency_ms']} ms")
    print(f"Latency p99:                      {ov['p99_latency_ms']} ms")
    print("=" * 70)

    print("\nBREAKDOWN BY SITE:")
    print(f"{'Site ID':<22} | {'Pos':<5} | {'Top-1 Exact':<12} | {'Recall@5':<10} | {'MRR':<6} | {'Neg FP%':<8}")
    print("-" * 70)
    for sid, st in results["by_site"].items():
        pos = st["pos"]
        neg = st["neg"]
        t1 = round((st["top1_exact"] / pos * 100), 1) if pos else 0.0
        r5 = round((st["recall5_exact"] / pos * 100), 1) if pos else 0.0
        mrr = round(st["mrr_exact"] / pos, 3) if pos else 0.0
        fp = round((st["fp"] / neg * 100), 1) if neg else 0.0
        print(f"{sid:<22} | {pos:<5} | {t1:>10}% | {r5:>8}% | {mrr:>6} | {fp:>6}%")

    print("\nBREAKDOWN BY QUERY CATEGORY:")
    print(f"{'Category':<15} | {'Count':<6} | {'Top-1 Exact':<12} | {'Recall@5':<10} | {'MRR':<6}")
    print("-" * 70)
    for cat, st in results["by_category"].items():
        if cat == "negative":
            continue
        pos = st["pos"]
        t1 = round((st["top1_exact"] / pos * 100), 1) if pos else 0.0
        r5 = round((st["recall5_exact"] / pos * 100), 1) if pos else 0.0
        mrr = round(st["mrr_exact"] / pos, 3) if pos else 0.0
        print(f"{cat:<15} | {pos:<6} | {t1:>10}% | {r5:>8}% | {mrr:>6}")
    print("=" * 70)

def generate_markdown(results: Dict[str, Any], output_path: str = "eval/BASELINE.md"):
    ov = results["overall"]
    md = []
    md.append("# Baseline Search Evaluation (Pre-Embedding / BM25)")
    md.append(f"\n*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n")
    md.append("This document records the baseline retrieval performance of WarpWeb's current BM25 lexical engine, keyword boosts, and SQLite index persistence **before** introducing sentence embeddings and semantic hybrid ranking.\n")
    md.append("## Overall Metrics\n")
    md.append("| Metric | Baseline Value | Description |")
    md.append("|---|---|---|")
    md.append(f"| **Total Queries** | `{ov['total_queries']}` | Full evaluation dataset size |")
    md.append(f"| **Positive Queries** | `{ov['positive_queries']}` | Queries with a targeted ground truth answer |")
    md.append(f"| **Negative Queries** | `{ov['negative_queries']}` | Out-of-domain queries expected to yield 0 results |")
    md.append(f"| **Top-1 Accuracy (Exact)** | **`{ov['top1_exact_accuracy']}%`** | Targeted section/anchor ranked rank #1 |")
    md.append(f"| **Top-1 Accuracy (Page)** | `{ov['top1_page_accuracy']}%` | Correct target page ranked #1 |")
    md.append(f"| **Recall@5 (Exact)** | **`{ov['recall5_exact']}%`** | Targeted section/anchor present in top 5 results |")
    md.append(f"| **Recall@5 (Page)** | `{ov['recall5_page']}%` | Correct page present in top 5 results |")
    md.append(f"| **MRR (Exact)** | **`{ov['mrr_exact']}`** | Mean Reciprocal Rank (exact section) |")
    md.append(f"| **MRR (Page)** | `{ov['mrr_page']}` | Mean Reciprocal Rank (page level) |")
    md.append(f"| **Zero-Result Rate (Positive)** | `{ov['zero_result_rate_positive']}%` | Relevant queries returning zero results |")
    md.append(f"| **False Positive Rate (Negative)** | `{ov['false_positive_rate_negative']}%` | Irrelevant queries returning spurious results |")
    md.append(f"| **Latency p50** | `{ov['p50_latency_ms']} ms` | Median search query execution time |")
    md.append(f"| **Latency p95** | `{ov['p95_latency_ms']} ms` | 95th percentile search latency |")
    md.append(f"| **Latency p99** | `{ov['p99_latency_ms']} ms` | 99th percentile search latency |")

    md.append("\n## Breakdown by Site\n")
    md.append("| Site ID | Positive Queries | Top-1 Accuracy (Exact) | Recall@5 (Exact) | MRR (Exact) | Negative FP Rate |")
    md.append("|---|---|---|---|---|---|")
    for sid, st in results["by_site"].items():
        pos = st["pos"]
        neg = st["neg"]
        t1 = round((st["top1_exact"] / pos * 100), 1) if pos else 0.0
        r5 = round((st["recall5_exact"] / pos * 100), 1) if pos else 0.0
        mrr = round(st["mrr_exact"] / pos, 3) if pos else 0.0
        fp = round((st["fp"] / neg * 100), 1) if neg else 0.0
        md.append(f"| `{sid}` | {pos} | **{t1}%** | **{r5}%** | {mrr} | {fp}% |")

    md.append("\n## Breakdown by Query Category\n")
    md.append("| Category | Count | Top-1 Accuracy (Exact) | Recall@5 (Exact) | MRR (Exact) | Analysis |")
    md.append("|---|---|---|---|---|---|")
    notes_map = {
        "exact": "Exact keyword & phrase matches perform strongly in BM25",
        "synonym": "Synonyms & paraphrases frequently fail in pure lexical BM25",
        "hinglish": "Transliterated Hindi/Hinglish queries struggle without semantic embeddings"
    }
    for cat, st in results["by_category"].items():
        if cat == "negative":
            continue
        pos = st["pos"]
        t1 = round((st["top1_exact"] / pos * 100), 1) if pos else 0.0
        r5 = round((st["recall5_exact"] / pos * 100), 1) if pos else 0.0
        mrr = round(st["mrr_exact"] / pos, 3) if pos else 0.0
        note = notes_map.get(cat, "")
        md.append(f"| `{cat}` | {pos} | **{t1}%** | **{r5}%** | {mrr} | {note} |")

    md.append("\n## Analysis and Key Findings\n")
    md.append("1. **Exact queries**: BM25 excels when exact keywords from the title/content match the query words.")
    md.append("2. **Synonym gap**: Queries like 'urgent care hospital helpline' or 'knee replacement surgery clinic' have lower recall because words like 'urgent' or 'knee' do not appear verbatim in sections titled 'Orthopedics' or 'Trauma & Emergency'.")
    md.append("3. **Hinglish vocabulary mismatch**: Hinglish queries ('dil ki bimari', 'haddi ka hospital', 'paani me kharab na hone wale earbuds') have near-zero lexical overlap with English web content, resulting in high zero-match rates.")
    md.append("4. **False positives on negative queries**: Thresholding currently keeps false positives low, but without confidence scoring some spurious lexical matches may trigger.")
    md.append("5. **Sub-millisecond CPU speed**: Baseline BM25 runs in ~0.05 - 0.2ms on CPU, providing ample budget to add embedding similarity and still comfortably beat the 150ms budget in Phase 2.\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"\nBaseline results written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate WarpWeb search retrieval")
    parser.add_argument("--dataset", default="eval/queries.json", help="Path to evaluation queries JSON")
    parser.add_argument("--site", default=None, help="Filter by specific site_id")
    parser.add_argument("--baseline", action="store_true", help="Generate eval/BASELINE.md")
    parser.add_argument("--output", default="eval/BASELINE.md", help="Output path for markdown report")

    args = parser.parse_args()
    res = run_evaluation(args.dataset, args.site)
    print_report(res)
    if args.baseline:
        generate_markdown(res, args.output)
