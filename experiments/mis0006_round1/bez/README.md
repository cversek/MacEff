# MIS-0006 round 1, Bez's bundle (E15, E16, E17): the kit

Scripts behind the results posted on #1149 (E15 7173704552, E16 7173782059, E17 7173849002). They read one seat's own Claude Code transcript and print figures only; no transcript text, audio or derived table is in this branch.

- `kit.py TRANSCRIPT.jsonl OUT_DIR`: one pass over the transcript. Each turn that opened a drive is classed by its source, read with `macf.utils.input_origin` (origin record first, else the opening tag, MIS-0002-R121): typed, dictated (voice channel), dictated over the session socket, Telegram, peer agent, background notice, Stop hook, daemon notice, framework keystrokes (from the event log's `keys_sent`, plus the framework's fixed openings). It also collects the tool calls with the items each one opened. The resulting `drives.json` holds text, so keep it off any repository.
- `e15.py DRIVES_JSON`: the dictated share of operator-originated drives, by day, with a day-resampled interval (seed 20261123).
- `e16.py DRIVES_JSON PRIVATE_DIR`: the fixed tail flag and trim, prevalence by day, the typed-prompt false-positive check, and the samples for the blind and miss readings (written privately).
- `e17.py DRIVES_JSON PRIVATE_DIR`: the back-reference rate per thousand words on cleaned text, the precision sample, the query set and lexical recall@10 as description.

A seat without voice can run `kit.py` and `e15.py` for the typed side only. The scripts expect a MacEff checkout at `~/gitwork/cversek/MacEff-bez`; change the `sys.path` line in `kit.py` to point at yours.
