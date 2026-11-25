# MIS-0006 round 1, E4: an episodic benchmark from a seat's own record

A kit for the experiment E4 in the MIS-0006 deliberation (#1149). It reads only the running
seat's transcripts, memory files and checkpoints, writes everything it derives owner-only into
a cache directory you name, and prints figures only, never question or episode text.

It needs this branch's `macf.knowledge_eval_text` (bm25, dense, the fusions) on the import path,
and sentence-transformers with all-MiniLM-L6-v2.

```
PROJ=~/.claude/projects/<your project directory>
MEM=$PROJ/memory
CCP=<your agent home>/agent/private/checkpoints
OUT=<an owner-only directory>
PY="python -I"     # with PYTHONPATH pointing at this checkout's macf/src

$PY e4_episodes.py    $PROJ $OUT/episodes.json          # 1. episodes, operator turn to operator turn
$PY e4_questions.py   $OUT/episodes.json $MEM $OUT/questions.json   # 2. Q-decision, Q-current, Q-none
$PY e4_warm.py        $OUT/episodes.json $OUT           # 3. embed the three indexes once (optional)
$PY e4_run.py         $OUT/episodes.json $OUT/questions.json $OUT rrf:10 dev    # 4. H4a-H4d, dev
$PY e4_run.py         $OUT/episodes.json $OUT/questions.json $OUT rrf:10 held   #    and held, once
$PY e4_obligations.py $PROJ $CCP $OUT/obligations.json  # 5. session starts and their obligations
$PY e4_h4e.py         $OUT/obligations.json rrf:10 $OUT # 6. H4e
```

The ranker argument is the E1 winner with its frozen parameter (`cc:A` or `rrf:K`); on the
head maintainer's record it was `rrf:10`. H4c's verdict takes the 10th percentile of the dev
run's `H4c_scores.decision` as the threshold and counts the held run's `none_invocab` below it.
Every construction choice is in each script's docstring and in the head maintainer's
clarification on #1149.
