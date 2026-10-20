"""The live trace and its two domains (operator, 13:52 Oct 17): what the trace is COMPUTED over
(every event up to t, the in-context turns included, decaying over history) and what it RETRIEVES
over (the historical record outside the context window at t, never anything inside it).

  moments()       the trigger moments T1 to T5 (protocol, "Trigger moments")
  context_start() the in-context boundary at t: the last compaction before t, or the stream start
  allowed()       a candidate may be retrieved at t only if it existed before the boundary and was
                  not consulted since it (both mean it is already in context)
  l1_targets()    behavioral labels: what the agent consulted from the record after t
  Integrator      Tier A: per-source leaky integrators with depth-gated gain; a null increment
                  (depth 0) leaves every state exactly as it was
"""
import bisect
import re

import numpy as np

NULL_SEEDS = ["continue", "ok", "yes", "go", "go ahead", "proceed", "done", "thanks", "1", "2"]   # fixed 14:15
CA_PATH = re.compile(r"agent/(?:private|public)/(?:learnings|reflections|checkpoints|observations|experiments|reports|roadmaps)/[^\s\"']+")
IDEA = re.compile(r"idea get (\d+)")
TASK = re.compile(r"task get #?(\d+)")


def boundaries(events):
    return [e["t"] for e in events if e["kind"] == "boundary"]


def context_start(t, bounds, stream_start=0.0):
    i = bisect.bisect_left(bounds, t)
    return bounds[i - 1] if i else stream_start


def moments(events, n_tool=20):
    """T1 operator or Telegram prompt; T2 every n_tool-th tool call since the last such prompt;
    T3 the first such prompt after a compaction; T4 a task start; T5 the call that writes an
    artifact (the trace is computed over the events strictly before it)."""
    out, since_prompt, after_boundary = [], 0, False
    for i, e in enumerate(events):
        if e["kind"] == "boundary":
            after_boundary = True
        elif e["kind"] == "prompt" and e["origin"] in ("operator", "telegram"):
            out.append({"kind": "T1", "i": i, "t": e["t"]})
            if after_boundary:
                out.append({"kind": "T3", "i": i, "t": e["t"]})
                after_boundary = False
            since_prompt = 0
        elif e["kind"] == "tool":
            since_prompt += 1
            if since_prompt % n_tool == 0:
                out.append({"kind": "T2", "i": i, "t": e["t"], "n": since_prompt})
            if e.get("writes_ca"):
                out.append({"kind": "T5", "i": i, "t": e["t"]})
        elif e["kind"] == "task_start":
            out.append({"kind": "T4", "i": i, "t": e["t"]})
    return out


def consult_keys(event):
    """Normalized targets a tool call consults: ('kg_path', path) | ('idea', n) | ('task', n)."""
    keys = set()
    for c in event.get("consults") or []:
        for p in CA_PATH.findall(c):
            keys.add(("kg_path", p.rstrip(".,;)")))
        for n in IDEA.findall(c):
            keys.add(("idea", n))
        for n in TASK.findall(c):
            keys.add(("task", n))
    return keys


def l1_targets(events, i, window=20):
    """What the agent consulted in the `window` tool calls strictly after event i."""
    keys, seen = set(), 0
    for e in events[i + 1:]:
        if e["kind"] == "tool":
            seen += 1
            keys |= consult_keys(e)
            if seen >= window:
                break
        elif e["kind"] == "boundary":
            break
    return keys


def allowed(cand, t, ctx_start, consulted_in_context):
    """Retrievable at t: existed before the in-context boundary, and not consulted since it."""
    return cand["t"] < ctx_start and cand.get("key") not in consulted_in_context


class Integrator:
    """s(t) = (1 - a*d) * s(t-1) + a*d * x, per source; one integrator per (source, flavor)."""

    def __init__(self, dim, a):
        self.s = np.zeros(dim, dtype=np.float32)
        self.a = a

    def update(self, x, d):
        g = self.a * float(d)
        self.s = (1.0 - g) * self.s + g * np.asarray(x, dtype=np.float32)
        return self.s


def null_direction(embed_fn):
    v = np.asarray(embed_fn(NULL_SEEDS), dtype=np.float32).mean(axis=0)
    return v / np.linalg.norm(v)


def depth_null_residual(x, null_dir):
    """1 minus cosine to the centroid of contentless prompts, clipped to [0, 1]."""
    x = np.asarray(x, dtype=np.float32)
    return float(np.clip(1.0 - x @ null_dir / (np.linalg.norm(x) or 1.0), 0.0, 1.0))


def null_radius(seed_vecs, null_dir):
    """The residual of the least central seed: a prompt at least as near the null as every seed is null."""
    return max(depth_null_residual(v, null_dir) for v in seed_vecs)


def gate_depth(residual, r0):
    """The integrator's depth: the residual rescaled so the seeds sit at 0 and a prompt orthogonal to
    the null at 1. The raw residual never reaches 0 (found 14:58: 'go' is 0.27, since each seed is
    only about 0.7 cosine from their centroid), so a 'continue' gated by it would still move the trace."""
    return np.clip((np.asarray(residual, dtype=np.float32) - r0) / (1.0 - r0), 0.0, 1.0)
