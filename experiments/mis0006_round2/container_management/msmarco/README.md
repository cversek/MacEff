# MIS-0006 round 2: ms-marco reranking on topical queries

The rule is posted on MacEff #1149, comment 7231398098, before any round 2 data was read. This folder runs it, for the container-management maintainer's record and, unchanged, for the host-side maintainer's second record.

```
R1_SNAPSHOT=<your round 1 snapshot.json> python3 run_r2_msmarco.py seal   # fresh queries, sealed; ranks nothing
python3 run_r2_msmarco.py run    # checks the seal, ranks, decides
python3 run_r2_msmarco.py cost   # added latency and memory
```

1. **Seal.** `seal` picks the queries: every same-subject query, and every cross-reference query for the guard, that your round 1 snapshot didn't label. If fewer than 60 are fresh, it fills from round 1's queries in the order a fixed seed gives, and says how many. It writes `seal.json` and prints a hash. Post the hash before running `run`.
2. **Run.** `run` refuses if the snapshot or a query list changed since the seal. It runs the leak audit, then both arms, and applies the posted rule:
   - **H3.3** validates if the paired 95% bootstrap lower bound (10,000 resamples) of reranked minus plain MRR on same-subject queries is above 10% of plain's MRR.
   - **The guard** holds if that lower bound on cross-references is not below minus 10% of plain's MRR.
3. **Cost.** `cost` reports p50 and p95 added latency, resident memory added, and the median of 10 cold starts. The crossing gate is p95 added latency at most 1 s.

The arms, the cleaning and the 400-word cut are round 1's (`../../../mis0006_round1/container_management/e10_e3/`). As a check, against round 1's snapshot this code reports the same share of candidates cut at 400 words as round 1 did (994 of 2,463). `R2_DEVICE` picks the reranker's device (default `cpu`). H3.4, the prose questions, needs a conversation store and isn't in this kit.
