# Baseline Search Evaluation (Pre-Embedding / BM25)

*Generated: 2026-11-22 00:24:30*

This document records the baseline retrieval performance of WarpWeb's current BM25 lexical engine, keyword boosts, and SQLite index persistence **before** introducing sentence embeddings and semantic hybrid ranking.

## Overall Metrics

| Metric | Baseline Value | Description |
|---|---|---|
| **Total Queries** | `119` | Full evaluation dataset size |
| **Positive Queries** | `99` | Queries with a targeted ground truth answer |
| **Negative Queries** | `20` | Out-of-domain queries expected to yield 0 results |
| **Top-1 Accuracy (Exact)** | **`61.62%`** | Targeted section/anchor ranked rank #1 |
| **Top-1 Accuracy (Page)** | `74.75%` | Correct target page ranked #1 |
| **Recall@5 (Exact)** | **`87.88%`** | Targeted section/anchor present in top 5 results |
| **Recall@5 (Page)** | `92.93%` | Correct page present in top 5 results |
| **MRR (Exact)** | **`0.72`** | Mean Reciprocal Rank (exact section) |
| **MRR (Page)** | `0.8261` | Mean Reciprocal Rank (page level) |
| **Zero-Result Rate (Positive)** | `5.05%` | Relevant queries returning zero results |
| **False Positive Rate (Negative)** | `15.0%` | Irrelevant queries returning spurious results |
| **Latency p50** | `0.227 ms` | Median search query execution time |
| **Latency p95** | `0.367 ms` | 95th percentile search latency |
| **Latency p99** | `0.418 ms` | 99th percentile search latency |

## Breakdown by Site

| Site ID | Positive Queries | Top-1 Accuracy (Exact) | Recall@5 (Exact) | MRR (Exact) | Negative FP Rate |
|---|---|---|---|---|---|
| `apexcare-clinic` | 59 | **79.7%** | **89.8%** | 0.838 | 20.0% |
| `shoppulse-commerce` | 40 | **35.0%** | **85.0%** | 0.547 | 10.0% |

## Breakdown by Query Category

| Category | Count | Top-1 Accuracy (Exact) | Recall@5 (Exact) | MRR (Exact) | Analysis |
|---|---|---|---|---|---|
| `exact` | 44 | **79.5%** | **100.0%** | 0.886 | Exact keyword & phrase matches perform strongly in BM25 |
| `synonym` | 29 | **44.8%** | **82.8%** | 0.599 | Synonyms & paraphrases frequently fail in pure lexical BM25 |
| `hinglish` | 26 | **50.0%** | **73.1%** | 0.574 | Transliterated Hindi/Hinglish queries struggle without semantic embeddings |

## Analysis and Key Findings

1. **Exact queries**: BM25 excels when exact keywords from the title/content match the query words.
2. **Synonym gap**: Queries like 'urgent care hospital helpline' or 'knee replacement surgery clinic' have lower recall because words like 'urgent' or 'knee' do not appear verbatim in sections titled 'Orthopedics' or 'Trauma & Emergency'.
3. **Hinglish vocabulary mismatch**: Hinglish queries ('dil ki bimari', 'haddi ka hospital', 'paani me kharab na hone wale earbuds') have near-zero lexical overlap with English web content, resulting in high zero-match rates.
4. **False positives on negative queries**: Thresholding currently keeps false positives low, but without confidence scoring some spurious lexical matches may trigger.
5. **Sub-millisecond CPU speed**: Baseline BM25 runs in ~0.05 - 0.2ms on CPU, providing ample budget to add embedding similarity and still comfortably beat the 150ms budget in Phase 2.

