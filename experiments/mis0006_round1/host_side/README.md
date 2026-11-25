# MIS-0006 round 1, host-side maintainer's kit: E12, E8, E13

Replays of one agent's own record. The plan, its amendment and the results are on cversek/MacEff#1149. Only figures leave a host; the extracted rows stay where you run this.

Environment:
- `KIT_TRANSCRIPTS` (required): the directory holding the agent's session transcripts (`*.jsonl`).
- `KIT_AGENT_HOME`: the agent's home, with `agent/private` and `agent/public` under it.
- `KIT_MEMORY`: the directory of the agent's memory files.
- `KIT_POLICIES`: the framework's `policies` directory.
- `KIT_DATA`: where the extracted rows and results are written.

Run, in order:
1. `python e0_extract.py`: one row per tool call; a progress line per transcript in `$KIT_DATA/progress.log`.
2. `E13_SINCE=YYYY-MM-DD python e13.py`: real knowledge queries, the shipping query's own output against a fixed five-term grep and BM25.
3. `python e12.py`: breakpoints and the every-20th call against matched controls.
4. `E8_SINCE=YYYY-MM-DD python e8.py`: the frozen trigger registry (`e8_registry.tsv`) replayed.
5. `python e8_blind.py`: shuffled fire and control excerpts for the blind hazard reading (definitions in `e8_hazards.tsv`); the key is written apart.

Two things to edit for another seat: `e8_registry.tsv` names this seat's memory files, so each seat writes its own registry, frozen and hashed before replay; and the consult patterns at the top of `e0_extract.py` assume the MacEff agent tree.
