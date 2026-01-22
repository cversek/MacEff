# Search Service Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Infrastructure
**Status**: ACTIVE
**Updated**: 2026-01-21

---

## Policy Statement

The search service provides warm-cached policy recommendations with sub-100ms latency. It pre-loads embedding models at container startup and serves queries via Unix socket, eliminating cold-start delays from hooks.

## Scope

Applies to all MacEff agents operating in containerized environments with policy search capabilities.

---

## CEP Navigation Guide

**1 Architecture Overview**
- What is the search service daemon?
- How does warm caching improve performance?
- What is the socket client pattern?

**2 Automatic Startup**
- When does the search service start?
- What happens during initialization?
- How do I verify it's running?

**3 Hook Integration**
- How do hooks use the search service?
- What is the socket client fallback?
- Why is this faster than direct search?

**4 Manual Operations**
- How do I rebuild the policy index?
- How do I restart the search service?
- How do I check service status?

**5 Troubleshooting**
- What if search returns no results?
- What if the service isn't running?
- How do I diagnose latency issues?

---

## 1 Architecture Overview

### What is the Search Service Daemon?

The search service is a background daemon that:
- Pre-loads the sentence-transformers embedding model (~8s cold start)
- Maintains a warm LanceDB connection to the policy index
- Listens on a Unix socket for search queries
- Returns results in <100ms after warm-up

### How Does Warm Caching Improve Performance?

| Scenario | Latency | Why |
|----------|---------|-----|
| Cold start (no service) | ~8000ms | Model loading + index opening |
| Warm service | <100ms | Model + index already loaded |
| **Speedup** | **~89x** | Eliminates cold start entirely |

### Socket Client Pattern

```
Hook (UserPromptSubmit)
    ↓
Socket Client (try Unix socket first)
    ↓ success?
Search Service Daemon (warm model)
    ↓
Policy Recommendations (<100ms)

    ↓ fallback if socket fails
Direct Search (cold start, ~8s)
```

---

## 2 Automatic Startup

### When Does the Search Service Start?

The service starts automatically during container initialization via `start.py`:

1. Container starts → `start.py` runs
2. `install_macf_tools()` installs dependencies (lancedb, sentence-transformers)
3. `start_search_service_daemon()` launches the daemon as the PA user
4. Daemon pre-loads model and opens index
5. Service ready for queries

### What Happens During Initialization?

```
[start.py] Starting search service daemon as pa_manny...
[daemon] Loading embedding model: all-MiniLM-L6-v2
[daemon] Model loaded in 8.36s
[daemon] Opening LanceDB index...
[daemon] Listening on /tmp/macf_search.sock
[start.py] Search service daemon started successfully
```

### How Do I Verify It's Running?

```bash
# Check if socket exists
ls -la /tmp/macf_search.sock

# Check process
ps aux | grep search_service

# Test with CLI
macf_tools search-service status
```

---

## 3 Hook Integration

### How Do Hooks Use the Search Service?

The `UserPromptSubmit` hook automatically uses the socket client:

```python
# In handle_user_prompt_submit.py
from macf.hybrid_search.search_service.client import SearchServiceClient

client = SearchServiceClient()
if client.is_available():
    results = client.search(prompt)  # <100ms
else:
    results = direct_search(prompt)   # ~8s fallback
```

### Socket Client Fallback

If the search service is unavailable, hooks fall back to direct search:
- First query will be slow (~8s) due to model loading
- Subsequent queries in same process are faster
- Service restart restores full speed

### Why Is This Faster Than Direct Search?

Direct search (no daemon):
1. Import sentence-transformers (~2s)
2. Load model weights (~6s)
3. Open LanceDB index (~0.1s)
4. Execute query (~0.05s)
5. **Total: ~8s**

Socket client (with daemon):
1. Connect to socket (~0.001s)
2. Send query (~0.001s)
3. Receive results (~0.05s)
4. **Total: <100ms**

---

## 4 Manual Operations

### How Do I Rebuild the Policy Index?

```bash
# Rebuild index (updates after policy changes)
macf_tools policy build_index

# Index location
~/.maceff/policy_index.lance
```

### How Do I Restart the Search Service?

```bash
# Stop existing daemon
macf_tools search-service stop

# Start new daemon
macf_tools search-service start

# Or restart container (service auto-starts)
```

### How Do I Check Service Status?

```bash
macf_tools search-service status
```

---

## 5 Troubleshooting

### What If Search Returns No Results?

1. **Check index exists**: `ls ~/.maceff/policy_index.lance`
2. **Rebuild if missing**: `macf_tools policy build_index`
3. **Verify query length**: Minimum 10 characters required

### What If the Service Isn't Running?

1. **Check socket**: `ls /tmp/macf_search.sock`
2. **Check process**: `ps aux | grep search_service`
3. **Start manually**: `macf_tools search-service start`
4. **Check logs**: Container logs show startup status

### How Do I Diagnose Latency Issues?

```bash
# Time a query
time macf_tools policy recommend "How do I backup TODOs?"

# Expected with warm service: <1s total
# If >5s: Service may not be running, falling back to cold start
```

---

## Implementation Notes

**Dependencies**:
- `lancedb>=0.26.0` - Vector database with native hybrid search
- `sentence-transformers>=2.2.0` - Embedding model (all-MiniLM-L6-v2)

**Files**:
- Daemon: `macf/hybrid_search/search_service/daemon.py`
- Client: `macf/hybrid_search/search_service/client.py`
- CLI: `macf_tools search-service {start|stop|status}`

**Socket Path**: `/tmp/macf_search.sock` (Unix domain socket)

---

**End Policy**
