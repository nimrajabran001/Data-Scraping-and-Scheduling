"""
Configurable search parameters for Stage 4.

Kept separate from rag_api/config.py (which likely holds infra config like
WEAVIATE_URL, LLM_MODEL, EMBEDDING_MODEL) so these tunable ranking knobs are
easy to find, override via env vars, and reproduce for the Section 6
evaluation.

All values can be overridden via environment variables so the eval script
(eval/run_eval.py) can sweep them without editing code, e.g.:

    FUSION_METHOD=rrf RRF_K=60 python eval/run_eval.py
    FUSION_METHOD=weighted VECTOR_WEIGHT=0.7 BM25_WEIGHT=0.3 python eval/run_eval.py
"""

import os

# ---------------------------------------------------------------------
# Fusion strategy for hybrid search
# ---------------------------------------------------------------------
# "rrf"      -> Reciprocal Rank Fusion (rank-based, no score normalization needed)
# "weighted" -> normalize both score lists to [0,1] then weighted sum
FUSION_METHOD = os.getenv("FUSION_METHOD", "rrf")

# RRF constant. Standard default is 60 (from Cormack et al., 2009).
# Higher k flattens the influence of rank differences; lower k makes rank 1
# dominate more heavily.
RRF_K = int(os.getenv("RRF_K", "60"))

# Weighted-sum fusion weights (only used when FUSION_METHOD == "weighted").
# Must sum to 1.0 for interpretable scores, but not enforced.
VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.6"))
BM25_WEIGHT = float(os.getenv("BM25_WEIGHT", "0.4"))

# Whether hybrid search applies the CrossEncoder reranker as a final pass
# on top of the fused list (in addition to fusion, not instead of it).
# Keep this OFF by default for the strategy comparison in Section 6/7 so
# "hybrid" measures fusion alone; the reranker can be evaluated as a
# separate ablation.
RERANK_AFTER_FUSION = os.getenv("RERANK_AFTER_FUSION", "false").lower() == "true"

# ---------------------------------------------------------------------
# Candidate pool sizes (how many results each strategy pulls before
# truncating to top_k)
# ---------------------------------------------------------------------
CANDIDATE_POOL_SIZE = int(os.getenv("CANDIDATE_POOL_SIZE", "20"))

# ---------------------------------------------------------------------
# Query classifier thresholds
# ---------------------------------------------------------------------
# Embedding-similarity threshold below which a query is considered
# "irrelevant" to the corpus (see rag_api/query_classifier.py).
# Tuned empirically against the eval set — see DECISIONS.md for the sweep.
IRRELEVANCE_SIMILARITY_THRESHOLD = float(
    os.getenv("IRRELEVANCE_SIMILARITY_THRESHOLD", "0.35")
)

# Below this (but above the irrelevance threshold), a query is "ambiguous"
# rather than confidently relevant.
AMBIGUOUS_SIMILARITY_THRESHOLD = float(
    os.getenv("AMBIGUOUS_SIMILARITY_THRESHOLD", "0.45")
)

# ---------------------------------------------------------------------
# Default top_k for the search_judgments tool
# ---------------------------------------------------------------------
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
