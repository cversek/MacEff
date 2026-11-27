"""E10 cost rule: per embedder, on CPU with the GPU hidden and the file cache warm.
Cold = a fresh process from launch to its first answer (load model, load the index matrix, encode one
query, rank); median of 10 starts. Resident memory = the child's VmRSS after its first answer.
Latency = encode one query and rank the whole index, 100 queries, p50 and p95."""
import glob
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMB = {"minilm": "sentence-transformers/all-MiniLM-L6-v2", "qwen3": "Qwen/Qwen3-Embedding-0.6B",
       "static": "sentence-transformers/static-retrieval-mrl-en-v1", "potion": "minishlab/potion-retrieval-32M"}
CHILD = r'''
import sys, time, json, numpy as np
t0 = float(sys.argv[3])
from sentence_transformers import SentenceTransformer
m = SentenceTransformer(sys.argv[1], device="cpu")
M = np.load(sys.argv[2])
v = m.encode(["how do I merge a pull request safely"], normalize_embeddings=True)[0]
order = np.argsort(-(M @ v))[:10]
first = time.time() - t0
rss = [int(l.split()[1]) for l in open("/proc/self/status") if l.startswith("VmRSS")][0] / 1024
qs = [f"query number {i} about policies, checkpoints and merging" for i in range(100)]
lat = []
for q in qs:
    a = time.perf_counter(); v = m.encode([q], normalize_embeddings=True)[0]; np.argsort(-(M @ v))[:10]
    lat.append((time.perf_counter() - a) * 1000)
lat.sort()
print(json.dumps({"first_s": first, "rss_mb": rss, "p50_ms": lat[49], "p95_ms": lat[94]}))
'''


def main():
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1", TOKENIZERS_PARALLELISM="false")
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor())
    mem = [int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal")][0] / 1024 / 1024
    out = {"host": {"cpu": cpu, "cores": os.cpu_count(), "mem_gb": round(mem, 1)}, "models": {}}
    for name, hf in EMB.items():
        mat = sorted(glob.glob(str(HERE / f"emb_{name}_*.npy")))[-1]
        runs = []
        for _ in range(10):
            t0 = time.time()
            r = subprocess.run([sys.executable, "-c", CHILD, hf, mat, str(t0)], capture_output=True, text=True, env=env)
            runs.append(json.loads(r.stdout.strip().splitlines()[-1]))
        out["models"][name] = {"cold_first_answer_s_median": round(statistics.median(x["first_s"] for x in runs), 2),
                               "rss_mb_median": round(statistics.median(x["rss_mb"] for x in runs)),
                               "p50_ms": round(statistics.median(x["p50_ms"] for x in runs), 1),
                               "p95_ms": round(statistics.median(x["p95_ms"] for x in runs), 1)}
        print(name, out["models"][name], flush=True)
    json.dump(out, open(HERE / "cost.json", "w"), indent=1)
    print("COST_DONE", out["host"])


if __name__ == "__main__":
    main()
