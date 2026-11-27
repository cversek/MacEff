"""E14: one instance of today's search service, from the same code, on its own port and index copy.

python3 instance.py <port> <index_path>

The only change from the shipped service: PolicySearch.hybrid_search is given the call lancedb 0.36
accepts (vector and text both supplied). The shipped call passes a vector as the text query, raises
ValueError on every query, and falls back to vector search; so without this patch there is no healthy
hybrid baseline to plant a fault into. The fallback and everything else is unchanged.
"""
import sys
import time
from pathlib import Path

from macf.hybrid_search import policy_search as PS
from macf.utils import recommend as R
from macf.search_service.daemon import SearchService
from macf.search_service.retrievers.policy_retriever import PolicyRetriever


def hybrid_search(self, query, limit=5):
    start = time.time()
    emb = self.model.encode(query)
    try:
        rows = self.documents_table.search(query_type="hybrid").vector(emb).text(query).limit(limit).to_list()
        mode = "hybrid"
    except Exception:  # noqa: BLE001 - the shipped fallback, kept as it is
        rows = self.documents_table.search(emb).limit(limit).to_list()
        mode = "semantic"
    out = []
    for r in rows:
        d = r.get("_distance")
        if d is None:
            d = 1.0 - float(r.get("_relevance_score") or 0.0)
        out.append({"policy_name": r["policy_name"], "distance": d, "similarity": 1 - d,
                    "tier": r.get("tier", ""), "category": r.get("category", "")})
    return {"query": query, "search_type": mode, "results": out, "latency_ms": (time.time() - start) * 1000}


PS.PolicySearch.hybrid_search = hybrid_search
R.DB_PATH = Path(sys.argv[2])
svc = SearchService(host="127.0.0.1", port=int(sys.argv[1]))
svc.register(PolicyRetriever())
svc.start(daemonize=False)
