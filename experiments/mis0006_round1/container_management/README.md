# MIS-0006 round 1: the container-management maintainer's kit (E14, E10 and E3, E7)

The scripts behind the container-management maintainer's round 1 results on #1149. Each experiment's rules were posted there before any data was read. Another seat runs the same folder unchanged on its own record and posts its own figures; only figures leave a host.

| Folder | Experiment | Runs on | Rules | Result |
|---|---|---|---|---|
| `e14/` | Does a failing index get noticed? | any host with `macf` and the search service's dependencies | comment 7091101712 | comment 7174375191 |
| `e10_e3/` | A static-embedding tier (E10), and reranking (E3) | any seat, on its own corpus | the plan and amendments 1 to 3 | comment 7174521376 |
| `e7/` | Hub correction by replay | **only a seat that ran the Oct 20 push trial** | the plan and amendments 1 to 4 | comments 7174288461 and 7174399730 |

Every script writes under its own folder (`out/`, `cache/`, index copies). `.gitignore` keeps all of it out of git, because it holds the seat's private text.

## E14: does a failing index get noticed?

```
cd e14
python3 run_e14.py            # about 31 minutes; the last line of out/run.log is RESULTS_WRITTEN
```

- Builds four copies of a policy index from `E14_POLICIES_DIR` (default: this checkout's `framework/policies`) and starts one search-service instance on each, on ports 9011 to 9014: F0, the control; F1, a source file changed after the build; F2, the full-text index removed; F3, the tables emptied.
- `instance.py` is a service instance whose hybrid call is corrected. The shipped call passes the query vector where the store expects text, so it raises and falls back to vector search on every query. Without the correction the control wouldn't be hybrid at all.
- It picks the known answers on F0 before planting any fault. It then sends ordinary queries every 3 s and the canary every 60 s, for 30 minutes.
- **Decide H14.1** from `out/ordinary.json` (client warnings, stderr, exceptions), from the seat's own event log over the run's window, and from the instances' exit codes in `out/run.log`. **Decide H14.2** from `out/canary_events.jsonl`. The canary fails on fewer than 5 known-answer hits, on a mode other than hybrid, or on an error. Index-older-than-source is the secondary criterion.
- **Cost:** the wall time above, and no model calls beyond the service's own embedder. Record the instances' resident memory while it runs, which the first run didn't.

## E10 and E3: a static tier, and reranking

```
cd e10_e3
HF_HUB_OFFLINE=1 python3 run_e10_e3.py audit   # the leak audit: refuses if a ranker can read its answer
HF_HUB_OFFLINE=1 python3 run_e10_e3.py dev     # chooses the static model and the reranker; writes choices.json
HF_HUB_OFFLINE=1 python3 run_e10_e3.py held    # ONCE: the sealed split, recorded in the event log
CUDA_VISIBLE_DEVICES= python3 cost_e10.py       # CPU only, cache warm, median of 10 cold starts
```

- **Models:** all-MiniLM-L6-v2, Qwen3-Embedding-0.6B, `sentence-transformers/static-retrieval-mrl-en-v1`, `minishlab/potion-retrieval-32M`, `cross-encoder/ms-marco-MiniLM-L-6-v2` and `BAAI/bge-reranker-v2-m3`. Fetch them before running offline.
- **The split** is made from a fresh seed (`E10_SEED`, default `e10-e3-2026-11-25`; set your own) and sealed before `dev`.
- **Every ranker reads cleaned text.** Links, file stems, citation brackets and the Cross-References and Wiki-Links sections are removed, because the leak audit refused full text when 29% of cross-reference pairs named their target in prose.
- **Freeze the corpus between the seal and the held run.** The held run takes a fresh snapshot. On the first run, artifacts written in between added two queries to the held set. The seal records it, but it is better avoided.
- **Apply the rules as amended:**
  - **H10:** the margin is 10% of the MiniLM hybrid's MRR, and it is counted only on label sources where that hybrid beats full text alone with an interval excluding zero. The chosen static model must also meet the cost rule: 400 MB or less, a cold start of 1 s or less, and p95 of 50 ms or less.
  - **H3.1:** cross-references only.
  - **The harm rule:** on citations and same-subject, reranked minus plain must stay above -10% of plain.
- **Not in this kit:** the conversation-store part (the 18 operator questions, and H3.2). It runs on a seat's private conversation store with that store's own harness. A seat with an Experiment 020-style store reruns its schemes there.

## E7: hub correction by replay

```
export E7_TRANSCRIPT=<the trial session's transcript .jsonl>
export E7_PUSH_TRIAL_DIR=<the push trial's own folder: push_service.py and its kit/>
cd e7
python3 prep.py                                  # reads the record once into cache/
python3 a0.py && python3 arms.py && python3 score.py && python3 report.py      # development days
python3 a0.py --sealed && python3 arms.py --sealed && python3 score.py --sealed # ONCE
python3 decide.py sealed                         # the hypotheses and the E9 gate, by the amended rules
```

- **It runs only on a seat that ran the push trial.** A0, the harness check, replays the trial's own service against its own log. Only the container-management seat ran it. Another seat can read the scripts for the method, run A1 to A6 on its own log with `a0.py` adapted, or skip E7.
- **Days alternate** between development and sealed, starting Oct 21 on development. Every interval resamples days with seed 20261125.
- **The development-day H7.3 half-width must be posted before any sealed day is read** (second amendment).
- **A novel consult counts read-type calls only.** The before-window is per item, the larger of 10 and twice the median gap between that item's mentions (fourth amendment).
- **A0 must reproduce at least 180 of the 200 seeded logged pushes**, or nothing else is read.

## Wiki-Links

[[measurement]] [[experiments]] [[knowledge_web]]
