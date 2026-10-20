# MIS-0006: A knowledge index that ranks, and a push that knows when to stay quiet

**Number**: 0006
**Type**: Standards
**Status**: Draft
**Authors**: the host-side maintainer, from two experiments run on its own record, with directions the operator gave while planning them
**Secretary**: none
**Deliberation**: pending
**Created**: 2026-10-20
**Updates**: none
**Supersedes**: none
**Lands-in**: planned: the knowledge query and a knowledge index in `macf` (replacing the policy recommender's index); a push behind an off-by-default switch; policy text in scholarship, corpus_integrity, search_service and policy_awareness; framework/glossary.md
**Resolution**: none

<!--
A FIRST DRAFT. Every requirement below is a proposal for the deliberation to keep, change or drop.
Nothing here is settled until the operator ratifies it (mis section 6). Where the evidence behind a
proposal is thin, it is an open question, not a requirement. The replications in section 2.4 are
pending, and the draft is revised when they arrive.
-->

---

## 1 Summary

Agents ask `macf_tools knowledge query` what they already know, before they write, decide or recover from a compaction. Today it doesn't rank: for two of the three relations measured, its order is worse than random. And nothing brings the knowledge web to an agent at the moments it would help, since MacEff removed its one push, the per-prompt policy recommendation, for good reasons.

This MIS proposes two things:
- **A knowledge index** over every artifact and policy section, searched by meaning and by the web's own vocabulary, kept fresh by content hash, with every hit saying where it came from and why it matched.
- **A push** that draws on that index at a few measured moments, abstains everywhere else, is off until the operator turns it on, and records every push, abstention and failure, so a push that stops working can't go unnoticed.

It concerns every agent that uses the knowledge web, and the operator, who decides whether a push runs at all.

## 2 Motivation

### 2.1 The query doesn't rank

**Measured, sealed split** (Experiment 010, run on one agent's corpus of about 2,200 artifacts; its figures are reproduced by `macf_tools knowledge eval`, the measuring instrument this MIS's ranking changes answer to, in pull request #750).

Labels came from the agent's own earlier artifacts: learning cross-references ("bears on"), enhanced citations ("continues"), and learnings-index clusters ("same subject"). Against them, today's query scored MRR 0.055, 0.018 and 0.033, where a random order scores 0.016, 0.005 and 0.099. Ordering the same matches by how rare their shared concepts are scored 0.162, 0.437 and 0.247.

The same experiment found what ranks better still:
- **Hybrid search** (vector and full text fused) over clean artifact text, with the web's concepts in the keyword slot, was the best single method for "bears on" (0.334) and on the agents' real query workload, graded by a model judge and by two maintainers (nDCG@10 0.817, 0.881, 0.884).
- **Full text over the body**, with breadcrumb lineage, was best for "continues" (0.737). The best method for one relation is near the worst for another.

### 2.2 The recommender reports a search it doesn't run

**Reproduced.** The policy recommender's hybrid call always fails and falls back to vector search, and it reports "semantic" either way, in a field nothing reads. Its index on the host where this was found was months old. The knowledge index this MIS proposes replaces it, and its first requirements answer exactly these two defects.

### 2.3 MacEff had a push, and removed it

**Recorded** (GH#211, closed). The per-prompt policy recommendation was retired for four reasons:
1. push floods, and what floods gets skimmed;
2. it recommended against a stale index;
3. on one host it silently produced nothing, and nobody noticed;
4. it cost about 4 s on every prompt.

`policy_awareness` section 2.5 has said "pull, not push" since. Any push this MIS proposes has to answer each reason, and section 7 does, one by one.

### 2.4 When a push would help, measured

**Measured, sealed split, one agent's record; replication by the other maintainers is pending** (Experiment 014). Labels were behavioral: what the agent itself consulted in the 20 tool calls after each moment, among what was outside its context then. A query built from a decaying trace of recent work (the task tree, the knowledge web the agent touched, the conversation) was compared with the prompt alone:

| Moment | Trace minus prompt, MRR [95% interval] |
|---|---|
| All moments | +0.114 [0.067, 0.160] |
| A shallow operator prompt ("go ahead") | +0.079 [0.017, 0.180] |
| A deep operator prompt | +0.029 [−0.035, 0.123] |
| Every 20th tool call in a stretch of autonomous work | +0.103 [0.030, 0.185] |
| The tool call that writes an artifact | +0.265 [0.127, 0.399] |
| A task start | +0.028 [0.0, 0.083] |
| The first prompt after a compaction | +0.024 [0.0, 0.071] |

A trace from a shuffled stream did much worse (+0.099 for the real trace over it), so the gain is the record's, not a popularity prior. And 44% of the "prompts" in the record came from machines: notifications, schedules, mail clocks, peers.

**Exploratory, judged, with the operator's grades as the anchor:** no score threshold separated useful items from noise. Precision of pushed items stayed at 26 to 29% whether the bar sat at the 50th or the 95th percentile. By moment, the trace's top item was useful 9 times in 10 before an artifact write, 5 in 8 on a shallow prompt, and 2 in 10 or fewer mid-work, at a task start and after a compaction.

The other maintainers are invited to run the same steps on their own records (a replication kit on the branch `replication/exp014-kit`). Each proposal below that rests on this section says so, and the draft is revised when their figures arrive.

## 3 Goals and Non-Goals

**Goals**
- `knowledge query` ranks, answers prose, and searches every artifact and policy section, with each hit explained.
- One knowledge index serves the query, the policy recommender and the push.
- An operator can turn a push on, see everything it did and did not do, and turn it off, in one command each.
- Every one of GH#211's four reasons has an answer that a trial can show working.

**Non-goals**
- **Changing how agents write wiki-links.** The concepts stay; they earn their place as vocabulary and filter.
- **Indexing outside the agent's own home,** or moving private text into a repository.
- **A repository-carried index for code** (an idea for a later MIS).
- **Larger embedding models.** A model change is a later decision with its own evaluation.

## 4 Guide-Level Explanation

An agent about to write a learning on notification delivery runs:

```
macf_tools knowledge query "a delivery claim judged by the sender's view of the receiver"
```

It gets ten ranked hits. Each shows its class, title, date and breadcrumb, its score, and whether the match came from meaning, from words or from shared concepts. `--like <artifact>` asks what bears on an artifact, and `--mode lineage` asks what continues it.

With the push turned on, the same agent, a moment before it writes that learning, sees one item in its context: a learning from three weeks earlier on the same failure, with its breadcrumb and a line saying it was pushed because an artifact write is a push moment and the trace matched it. On a "go ahead" from the operator, it may see one item drawn from learnings, policy sections and ideas. On a scheduled check-in, it sees nothing: machine turns never push. Mid-task, it sees nothing unless the operator enabled pushes during autonomous work.

The operator runs `macf_tools knowledge push status` and sees, for the last day, every push, every abstention with its reason, and every failure.

## 5 Terms

- **knowledge index**: the searchable store of every knowledge-web artifact and policy section, with a vector view, a full-text view and the concepts of each entry.
- **trace**: a query built from a decaying record of the session's recent events, weighted by source: the task tree, the knowledge web the agent touched, and the conversation.
- **push**: an item from the knowledge index placed into an agent's context without the agent asking.
- **push moment**: a point in a session at which a push may happen: a shallow operator prompt, an artifact write, or every Nth tool call of autonomous work.
- **machine turn**: a prompt that a process sent, not the operator: a notification, a scheduled job, a mail clock, a wake or a peer.
- **abstention**: a push moment at which the push decided to place nothing, with its reason.

## 6 Specification

### 6.1 The knowledge index

- **R01** [MUST · decidable: macf/tests/test_knowledge_index.py::test_every_artifact_class_and_policy_section_is_indexed (planned)] The knowledge index MUST hold every knowledge-web artifact, orphans included, and each policy section, except a class the operator excludes. (index_MUST_hold_every_artifact)
- **R02** [MUST · decidable: macf/tests/test_knowledge_index.py::test_a_rebuild_reembeds_only_what_changed (planned)] When an artifact's content hash changes, the knowledge index MUST embed that artifact again, and no unchanged one. (index_MUST_reembed_changed_only)
- **R03** [MUST · decidable: macf/tests/test_knowledge_index.py::test_a_stale_index_says_so (planned)] If the knowledge index is older than one of its sources, then each query MUST report the stale classes beside its results. (stale_index_MUST_be_reported)
- **R04** [MUST NOT · decidable: macf/tests/test_knowledge_index.py::test_a_fallback_is_reported_as_a_fallback (planned)] A search MUST NOT report a hybrid search when it ran a vector search alone. (search_MUST-NOT_misreport_its_mode)
- **R05** [MUST · decidable: macf/tests/test_knowledge_index.py::test_each_hit_says_where_it_came_from (planned)] Each hit MUST carry its class, date, breadcrumb where one exists, and the share of its score from each part of the query. (hit_MUST_be_interpretable)
- **R06** [MUST · decidable: macf/tests/test_knowledge_index.py::test_the_index_is_owner_only (planned)] The knowledge index MUST be readable by the agent's account only. (index_MUST_be_owner_only)
- **R07** [SHOULD · judgment: the operator, at review of the landing pull request] The knowledge index SHOULD hold task notes by default, and transcript spans only when the operator turns them on. (spans_SHOULD_need_operator_flag)
- **R08** [MUST · decidable: macf/tests/test_knowledge_index.py::test_the_recommender_reads_the_knowledge_index (planned)] The policy recommender MUST search the knowledge index, and no index of its own. (recommender_MUST_use_knowledge_index)

### 6.2 The knowledge query

- **R09** [MUST · decidable: macf/tests/test_knowledge_query.py::test_results_are_ranked_and_scored (planned)] The knowledge query MUST return its results ranked, each with its score, in an order two runs reproduce. (query_MUST_rank)
- **R10** [MUST · decidable: macf/tests/test_knowledge_query.py::test_prose_and_like_use_the_hybrid_search (planned)] When a query is prose or names an artifact, the knowledge query MUST answer it with hybrid search, the concepts in the keyword slot. (prose_query_MUST_use_hybrid)
- **R11** [SHOULD · decidable: macf/tests/test_knowledge_query.py::test_lineage_mode_ranks_continuations (planned)] The knowledge query SHOULD offer a lineage mode, full text over the body with breadcrumb lineage, beside the default topical mode. (query_SHOULD_offer_lineage_mode)
- **R12** [MUST · judgment: the head maintainer, at review of each landing pull request] Each change to how the knowledge query ranks MUST report its `knowledge eval` figures on the held split, with intervals. (ranking_change_MUST_report_eval)

### 6.3 The push

- **R13** [MUST · decidable: macf/tests/test_knowledge_push.py::test_the_push_is_off_until_turned_on (planned)] The push MUST stay off for an agent until the operator turns it on for that agent. (push_MUST_default_off)
- **R14** [MAY · decidable: macf/tests/test_knowledge_push.py::test_one_command_turns_it_on_and_off (planned)] The operator MAY turn the push on or off, and each push moment on or off, with one command. (operator_MAY_toggle_push)
- **R15** [MUST · decidable: macf/tests/test_knowledge_push.py::test_origin_comes_from_the_record_first (planned)] The push MUST classify each turn's origin from the record's own origin fields before it reads the turn's text. (push_MUST_classify_origin_from_record)
- **R16** [MUST NOT · decidable: macf/tests/test_knowledge_push.py::test_a_machine_turn_never_pushes (planned)] The push MUST NOT place an item on a machine turn. (push_MUST-NOT_act_on_machine_turn)
- **R17** [MUST · decidable: macf/tests/test_knowledge_push.py::test_it_pushes_only_at_enabled_moments (planned)] The push MUST place items only at a push moment the operator has turned on. (push_MUST_act_only_at_enabled_moments)
- **R18** [MUST NOT · decidable: macf/tests/test_knowledge_push.py::test_nothing_in_context_is_pushed (planned)] The push MUST NOT place an item that the session read since its context began. (push_MUST-NOT_repeat_what_is_in_context)
- **R19** [MUST · decidable: macf/tests/test_knowledge_push.py::test_a_push_holds_three_items_at_most (planned)] Each push MUST hold three items or fewer. (push_MUST_hold_three_items_max)
- **R20** [MUST · decidable: macf/tests/test_knowledge_push.py::test_each_item_says_why (planned)] Each pushed item MUST name its push moment and the share of its score from each trace source. (pushed_item_MUST_say_why)
- **R21** [MUST · decidable: macf/tests/test_knowledge_push.py::test_every_outcome_is_an_event (planned)] Each push, abstention and failure MUST be an event in the agent's event log, with its reason. (push_outcome_MUST_be_event)
- **R22** [MUST · decidable: macf/tests/test_knowledge_push.py::test_past_the_budget_it_abstains (planned)] If the push can't answer within its time budget, then it MUST abstain and record the abstention. (push_MUST_abstain_past_budget)
- **R23** [MUST · decidable: macf/tests/test_knowledge_push.py::test_status_shows_pushes_abstentions_and_failures (planned)] The push status command MUST show the pushes, abstentions and failures of a period, with their counts. (push_status_MUST_show_outcomes)
- **R24** [MUST · decidable: macf/tests/test_knowledge_push.py::test_a_stale_or_missing_index_degrades_loudly (planned)] If the knowledge index is stale or missing, then the push MUST abstain and record that reason. (push_MUST_refuse_stale_index)
- **R25** [SHOULD · judgment: the operator, at the verdict on the host trial] While the agent works autonomously, the push SHOULD weight the task tree above the trace's other sources. (autonomous_push_SHOULD_favor_task_tree)

## 7 Rationale and Rejected Alternatives

### The index

- **R01**: the web's concepts reach only linked artifacts, and an orphan is invisible to a concept query. A search over text reaches it. Policy sections, not whole policies, because a push that names the specific section is one an agent can act on (the operator, Oct 17: "a match to an idea, a learning, and a policy section").
- **R02**: a full rebuild on every change is what made the old index too slow to keep fresh.
- **R03**: answers GH#211's second reason. A stale index is the ordinary state after any write, so it is reported, not hidden.
- **R04**: the recommender's defect, written as a rule: a degraded search that reports itself as the full one is the failure GH#211's third reason describes, at the level of one call.
- **R05**: a hit an agent can't trace is a hit it can't judge. The share of the score from each query part showed, in Experiment 014, when the trace was carrying a contentless prompt.
- **R06**: the index holds private artifacts' text.
- **R07**: the operator's direction on Oct 17 (20:45): task notes by default, transcript spans by flag. Spans hold the most private text and the least distilled knowledge.
- **R08**: two indexes of one corpus drift apart. One index, kept fresh, serves three readers.

### The query

- **R09**: Experiment 010's first finding: a result in string order is a defect, not a mode.
- **R10**: the measured best for "bears on" and for the real workload.
- **R11**: the measured best for "continues" is near the worst for "bears on", so it is a second mode rather than a blend. A SHOULD, because its evidence (14 sealed queries) is thin.
- **R12**: the instrument outside the author. A ranking judged by its author's reading is judged by the party least able to see its faults.

### The push, and GH#211's four reasons

| GH#211's reason | The answer |
|---|---|
| Push floods, and what floods gets skimmed | R16, R17 and R19: no push on machine turns (44% of prompts), only at enabled moments, at most three items, and never what is already in context (R18) |
| It recommended against a stale index | R02, R03 and R24: fresh by content hash, stale classes reported, and the push abstains on a stale index |
| It silently produced nothing, and nobody noticed | R21, R23 and R24: every push, abstention and failure is an event, the status command shows them, and a missing index degrades loudly |
| About 4 s on every prompt | R22: a time budget, past which the push abstains and says so |

- **R13**: the operator's direction (Oct 17, 12:44): "Add a push option but can be toggle using the CLI." Off by default, because the case for a push rests on one agent's record until the replications arrive.
- **R14**: the same direction, and the operator's need to turn off one moment that proves noisy without losing the rest.
- **R15**: in Experiment 014, machines posed as the operator: a check-in typed into the pane reads as human. The record's own origin fields are the more reliable witness.
- **R16**: a push on a notification or a schedule serves nobody, and machine turns were 44% of the record.
- **R17**: the moments are the evidence's (section 2.4) and the operator's choice (Oct 17, 20:25, quoted in Q02). The rule fixes that pushes happen only where enabled, and leaves which moments to the operator.
- **R18**: an item already in context costs attention and adds nothing. Experiment 014's whole retrieval domain was built on this split, at the operator's instruction (Oct 17, 13:52).
- **R19**: the judges rated about a quarter of pooled items useful. More items is more noise, not more help.
- **R20**: a push that can't say why it came trains an agent to skim it.
- **R21, R23**: GH#211's third reason. A push nobody can see working is indistinguishable from one that stopped.
- **R22**: GH#211's fourth reason. The prompt hook runs before every turn.
- **R24**: the second and third reasons together: a push that degrades must say so where the operator looks.
- **R25**: the operator's direction (Oct 17, 20:25): "auto_mode mid work draws from task tree with greater weight". Experiment 014 found the task tree the strongest single trace source. A SHOULD, judged at the trial's verdict, because the weight is tuned there.

**Rejected**
- **A score threshold as the salience bar.** Measured: precision stayed at 26 to 29% at every threshold. The bar is the moment (R17), not the score.
- **A push on every prompt.** That is what GH#211 removed.
- **Pushing at task starts and after compactions.** Measured: the task's own text did as well as any trace at a task start, and after a compaction the trace mostly re-found the recovery reading list. They remain moments an operator can enable, off by default (Q02).
- **PageRank and question anchoring.** One added nothing, and the other cut "bears on" to 0.049.
- **Fusing every method into one ranker.** Not better than the best single method on the sealed split.

## 8 Prior Art

- **Inside MacEff:** the policy recommender and its `hybrid_search` package, whose machinery the knowledge index reuses with its two defects fixed; GH#211, the push it retired; `policy_awareness` section 2.5; `knowledge eval` and `corpus_integrity` section 6, the measuring instrument this MIS's ranking changes answer to; Experiments 010 and 014.
- **Outside:** retrieval-augmented generation pushes retrieved passages into every prompt. This MIS refuses that default: it pushes at measured moments and abstains elsewhere. Reciprocal rank fusion (Cormack et al., 2009) is the hybrid's fusion.

## 9 Compatibility and Deployment

- **The knowledge query's output changes:** ranked, scored, with new fields. Under the development-phase rule there is no compatibility mode for the old order.
- **The policy recommender's index is replaced.** A deployment rebuilds once with `macf_tools knowledge index`.
- **The push changes nothing until the operator turns it on,** per agent.
- **Dependencies:** the index uses the embedding model and vector store the recommender already uses; both stay optional. Without them the query falls back to concept ranking and says so (R04), and the push abstains (R24).

## 10 Security and Safety

- **Prompt injection.** A push places stored text into an agent's context. Most of that text is the agent's own, but a learning or a span may quote an outsider. A pushed item is labeled as a push (R20), and an agent treats it as its own earlier note, never as an instruction or the operator's word, as the MacEff channel's notices already are. Transcript spans, which hold the most quoted outside text, are off by default (R07).
- **Private text.** The index is owner-only (R06), lives in the agent's home, and never enters a repository. The replication kit that tests this MIS's evidence publishes figures only.
- **Attention as a resource.** A push that floods is a denial of the agent's attention. R16, R17, R19 and R22 bound it, and R21 and R23 make it auditable.
- **Silent failure.** Answered by R03, R04, R21, R23 and R24.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | macf/tests/test_knowledge_index.py::test_every_artifact_class_and_policy_section_is_indexed | planned |
| R02 | decidable | macf/tests/test_knowledge_index.py::test_a_rebuild_reembeds_only_what_changed | planned |
| R03 | decidable | macf/tests/test_knowledge_index.py::test_a_stale_index_says_so | planned |
| R04 | decidable | macf/tests/test_knowledge_index.py::test_a_fallback_is_reported_as_a_fallback | planned |
| R05 | decidable | macf/tests/test_knowledge_index.py::test_each_hit_says_where_it_came_from | planned |
| R06 | decidable | macf/tests/test_knowledge_index.py::test_the_index_is_owner_only | planned |
| R07 | judgment | the operator, at review of the landing pull request | pending |
| R08 | decidable | macf/tests/test_knowledge_index.py::test_the_recommender_reads_the_knowledge_index | planned |
| R09 | decidable | macf/tests/test_knowledge_query.py::test_results_are_ranked_and_scored | planned |
| R10 | decidable | macf/tests/test_knowledge_query.py::test_prose_and_like_use_the_hybrid_search | planned |
| R11 | decidable | macf/tests/test_knowledge_query.py::test_lineage_mode_ranks_continuations | planned |
| R12 | judgment | the head maintainer, at review of each landing pull request | standing |
| R13 | decidable | macf/tests/test_knowledge_push.py::test_the_push_is_off_until_turned_on | planned |
| R14 | decidable | macf/tests/test_knowledge_push.py::test_one_command_turns_it_on_and_off | planned |
| R15 | decidable | macf/tests/test_knowledge_push.py::test_origin_comes_from_the_record_first | planned |
| R16 | decidable | macf/tests/test_knowledge_push.py::test_a_machine_turn_never_pushes | planned |
| R17 | decidable | macf/tests/test_knowledge_push.py::test_it_pushes_only_at_enabled_moments | planned |
| R18 | decidable | macf/tests/test_knowledge_push.py::test_nothing_in_context_is_pushed | planned |
| R19 | decidable | macf/tests/test_knowledge_push.py::test_a_push_holds_three_items_at_most | planned |
| R20 | decidable | macf/tests/test_knowledge_push.py::test_each_item_says_why | planned |
| R21 | decidable | macf/tests/test_knowledge_push.py::test_every_outcome_is_an_event | planned |
| R22 | decidable | macf/tests/test_knowledge_push.py::test_past_the_budget_it_abstains | planned |
| R23 | decidable | macf/tests/test_knowledge_push.py::test_status_shows_pushes_abstentions_and_failures | planned |
| R24 | decidable | macf/tests/test_knowledge_push.py::test_a_stale_or_missing_index_degrades_loudly | planned |
| R25 | judgment | the operator, at the verdict on the host trial | pending |

**Cold-reader trial**: not yet held.

**Use trial**: not yet held. Before Final, the capabilities the Motivation names are shown in use (MIS-0001's revision of 2026-10-20): an agent finds a prior artifact by prose, and a push on one host is judged by the operator.

## 12 Landing Plan

Planned, and re-planned from whatever the deliberation accepts:
1. **The knowledge index and the query** (R01 to R12), replacing the recommender's index, with the scholarship and search_service text.
2. **A host trial of the push,** outside MacEff's hooks, as evidence for this deliberation, on the author's host only, by the operator's direction (Oct 17, 20:45). Its conclusion is posted here as evidence, not as a decision.
3. **The push in MacEff, off by default** (R13 to R25), with policy_awareness section 2.5 changed as accepted (Q01).
4. **The seats,** at their next rebuild, in the operator's window.

Each landing pull request carries its normative text with its capability, and each landed rule cites its requirement by number, ID and slug.

## 13 Open Questions

- **Q01** How should policy_awareness section 2.5 read once a push exists: "pull, with a gated push at measured moments", or unchanged until the trial's verdict? The operator decides after the host trial. (pull_rule_after_a_push)
- **Q02** Which push moments start on when the operator turns the push on? The operator's direction (Oct 17, 20:25) was "1 + auto_mode mid work draws from task tree with greater weight": shallow operator prompts and artifact writes, and every 20th tool call in AUTO_MODE. The replications may move this. The operator decides. (default_push_moments)
- **Q03** Do the other maintainers' records replicate section 2.4's findings? The deliberation weighs their figures, side by side with these. (do_the_findings_replicate)
- **Q04** Should the work mode choose which classes a push draws from: policy sections by default, ideas in creative modes, learnings and observations in investigating ones? The operator proposed it (Oct 17, 19:14 to 19:16), and Experiment 014's curated-domain result points that way, on few moments. The operator decides whether it belongs here or in a later MIS. (work_mode_SHOULD_choose_classes)
- **Q05** What time budget should the push have on the prompt hook? The host trial measures it. (push_time_budget)
- **Q06** Should breadcrumb lineage become the knowledge graph's first typed edge in this MIS, or in one of its own? It helped "same subject" (+0.145) and didn't reach significance elsewhere. (lineage_as_typed_edge)
- **Q07** Should each push class be judged by its own goal (compliance, problem solving, creativity), each with its own rubric, rather than one "useful now" scale? The operator raised it (Oct 17, 19:13); the experiment's one rubric favored procedure. (one_rubric_per_goal)

## 14 Deliberation Record

None yet.

## 15 Revision History

- 2026-10-20: first draft.

## Wiki-Links

[[knowledge_web]] [[discoverability]] [[attention]] [[measurement]]
