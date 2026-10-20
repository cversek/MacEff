# Corpus Integrity and the Doctor Family

**Version**: 1.1.0
**Tier**: RECOMMENDED
**Category**: Infrastructure
**Status**: ACTIVE
**Dependencies**: scholarship, core_principles, debugging_and_validation

---

## Purpose

MacEff runs on corpora that describe themselves — a knowledge graph over consciousness artifacts, a policy corpus with search indices, a learnings index with activation hooks. Each is maintained by hand, each drifts from what it describes, and **each drifts silently**: a missing entry produces no error, only questions never asked.

A **doctor** is the instrument that reports that drift for one corpus.

**Core Insight**: the failure these tools address is not that a corpus is incomplete. It is that an incomplete corpus **reports confidence**. A gap detector that says "no gaps detected" while a third of the artifacts it should cover have no edges at all is not merely unhelpful — it actively certifies a condition it never examined.

---

## CEP Navigation Guide

**1 Why Doctors Exist**
- What failure mode does a doctor address that a test does not?
- Why is "reports confidence" worse than "reports nothing"?
- What makes corpus drift structurally invisible?

**2 Specialists, Shared Vocabulary**
- Why is there no single doctor for every corpus?
- What is shared between doctors, and what is not?
- Who owns the shared vocabulary?

**3 The Clinical Vocabulary**
- What do acute, chronic and note mean, and how do they differ from priority?
- What is the chart, and why does it print even when nothing is wrong?
- What is a referral?
- Why must every finding carry a remedy?

**4 Intended Use**
- When is running a doctor worth doing?
- What response does each finding class warrant?
- Why is CI gating NOT the default answer to a noisy checker?
- Are the described uses exhaustive?

**5 Building a New Doctor**
- What must a new doctor ship with?
- What verification does a checker require before it is trusted?

**6 The Relevance Check: `knowledge eval`**
- How do I know whether the knowledge query answers well, rather than whether the corpus is intact?
- Where does the relevance come from, and why not from the query's author?
- Why is the held split spent once read, and how is its use counted?
- What is a leak, and why is it found by content rather than by field name?
- When is running it worth doing?

=== CEP_NAV_BOUNDARY ===

---

## 1 Why Doctors Exist

A test asks whether code behaves correctly. A doctor asks whether a **corpus still describes the thing it claims to describe** — a different question, and one no test suite is positioned to answer, because the corpus is data that accumulates between runs rather than code that is exercised by them.

The failure is structural rather than careless:

- **Registration is manual and multi-site.** Adding an artifact means updating the artifact, the index, and often a keyword map. Omitting any one leaves the artifact readable and unfindable, which is indistinguishable from absent for an agent using the sanctioned discovery flow.
- **Absence produces no signal.** A missing index entry does not raise. It removes a result from a list nobody counted.
- **The instrument often cannot observe the condition.** A detector defined over *relationships* cannot see *absent* relationships. An artifact with no links is skipped before comparison begins — so the tool that exists to find missing connections is exactly the tool that cannot report the artifacts that have none.

That last point is the one worth internalising, because it generalises past corpora: **ask what must be true of an item for a check to consider it at all, then ask what happens to items that fail that precondition.**

---

## 2 Specialists, Shared Vocabulary

**Doctors are specialists.** There is no god-doctor. Each corpus needs domain knowledge the others cannot carry — graph topology, manifest registration, index referential integrity are different problems — and a single checker over all of them would be shallow everywhere or become a dumping ground.

**Their vocabulary is shared.** Specialists reporting in private words are unreadable together: an agent cannot tell that *orphan*, *dangling entry*, *unregistered policy* and *stale index* are the same finding in four dialects.

**Ownership**: the vocabulary belongs to no doctor. Whichever ships first **extracts** it to a shared location rather than keeping it, and later doctors cite rather than re-invent. Discovery order is not ownership — a general mechanism that stays inside the first subsystem to need it becomes invisible to everyone not reading about that subsystem.

---

## 3 The Clinical Vocabulary

The medical register is used **only where it clarifies**. Terms that add ceremony without meaning do not belong.

### 3.1 Severity is about how to read a finding, not how loudly to print it

| severity | meaning |
|---|---|
| **acute** | Something is wrong **now** and will mislead a reader who trusts it. An index reporting coverage it does not have; a node carrying no class, so retrieval cannot tell durable insight from expired state. These produce confident wrong answers. |
| **chronic** | Accumulating degradation. Nothing breaks today; the corpus becomes less trustworthy each cycle. Orphaned artifacts are canonical — each is survivable, the trend is not. |
| **note** | An observation with no implied action. |

The distinction is not priority. A single acute finding can matter less than fifty chronic ones in aggregate; what differs is **how a reader should treat the corpus in the meantime**. Acute means do not trust this surface until it is fixed. Chronic means the surface is usable and getting worse.

### 3.2 The chart prints even when nothing is wrong

The **chart** records what was examined and the baseline measurements taken — files examined, node counts, scope.

It is not decoration. A doctor that prints only problems cannot be distinguished from one that failed to run, examined nothing, or silently skipped the directory containing every defect. **A clean result is meaningful only alongside evidence of what was looked at**, which is precisely the distinction this whole family exists to make. Reporting the scope alongside the verdict is the same discipline as stating the corpus a search covered.

### 3.3 Every finding carries a remedy

A finding an agent cannot act on is noise, and noise trains readers to skim the whole report — which is the failure that makes a checker worse than none, because an ignored report still looks like coverage.

If a remedy cannot be stated, the check is not ready to ship.

### 3.4 Referral

When a finding is real but its remedy lives in another corpus, the doctor **refers** rather than reaching across. A knowledge-web doctor that finds a node whose class its CA-type policy never defined reports it and names the policy that owns the fix; it does not amend the policy itself.

---

## 4 Intended Use

This section exists because `--help` gives syntax and **intention is not discoverable from syntax**. What an agent cannot learn from a flag list is when running the thing is worth doing, what a finding means, and what response it warrants.

### 4.1 When to run

- **During corpus curation** — the housekeeping workflow is already asking "what is missing", which is the moment a finding is actionable in the same sitting.
- **After bulk changes** to a corpus: a batch of new artifacts, a migration, a restored deletion.
- **Before trusting a corpus-wide claim.** If you are about to report that something is absent from a corpus, run the doctor for that corpus first — absence is exactly the claim these instruments exist to qualify.
- **When a corpus-derived answer surprises you.** A query returning less than expected is the symptom; drift is a common cause.

### 4.2 What each finding class warrants

- **acute** → fix before relying on the surface, or record explicitly why it is being left.
- **chronic** → schedule. Chronic findings are for curation workflows, not for interrupting current work. Fixing them one at a time as they are noticed is how they stay ahead of accumulation.
- **note** → read; act only if it changes something you were going to do.

### 4.3 Noise is solved by discoverable intent, not by stronger enforcement

The instinct on seeing a noisy checker is to gate it in CI so its findings cannot be ignored. **That is the wrong shape**, and it is worth stating plainly because the instinct is strong.

A checker that fires on every push trains people to ignore it, and **an ignored gate is worse than no gate, because it looks like coverage.** The remedy is not enforcement frequency. It is policy stating when running the thing is worth doing, invoked from the workflow where its findings are actionable.

Gating remains available where a specific finding genuinely must block — but that is a per-check decision requiring its own justification, never the default answer to "people are not reading the output".

### 4.4 The described uses are a floor, not a ceiling

Novel uses are encouraged; that is how a system learns what a tool is for. This section constrains nothing. It exists so an agent meeting a doctor for the first time has somewhere to learn what it is *for*, rather than inferring purpose from flags.

---

## 5 Building a New Doctor

A new doctor **ships with its policy**, per the constitutional requirement that policy ships with the capability. A checker whose intended use is undiscoverable produces either disuse or ritual use, and both are failures.

Required before a doctor is trusted:

1. **A negative control per check.** Plant the defect, confirm **that specific finding** fires, restore. A checker never observed failing is not a checker.
2. **The opposite control.** Confirm it goes **quiet** once the defect is fixed. A checker that flags everything passes the first control and is useless.
3. **A remedy for every finding class** (§3.3).
4. **A chart** naming what was examined (§3.2).
5. **Vocabulary cited, not re-invented** (§2).

### 5.1 Findings must be locatable

A finding names an artifact a reader has to find. When a corpus nests artifacts inside directories whose *directory* carries the identifying name, the filename alone is not an identifier — several findings reading `analysis.md` name the same thing as far as a reader can tell. **A finding you cannot locate is not actionable**, which by §3.3 makes it noise.

---

## 6 The Relevance Check: `knowledge eval`

A doctor asks whether a corpus still describes what it claims to. A different instrument is needed to ask whether the **query over it answers well**. The query's author can't settle that by reading results: a ranking that looks sensible to the person who wrote it has been judged by the party least able to see its faults. `macf_tools knowledge eval` asks someone else, the agent's own earlier artifacts.

### 6.1 Where the relevance comes from

Each label source is something a past self wrote about what an artifact bears on, which the query never reads:

| source | an artifact is relevant to the query when |
|---|---|
| `xref` | the query learning names it in its Cross-References section |
| `citations` | a reflection or checkpoint cites it with an enhanced citation, resolved by the citation's date and title |
| `same_subject` | both are learnings filed under one cluster of the learnings index |

Every artifact with labels is a query. A ranker sees the query artifact, never its labels, and orders the web's other nodes. The chart reports each source's queries, pairs and unresolved references **before** any score, so a thin source reads as thin, not as a result.

The sources measure different relations, and a ranker can be best on one and near the worst on another. Read each source on its own; never average them into one number.

### 6.2 The held split is spent once read

A fifth of each source's queries is held out by a stable hash of the query's id, so a query keeps its side as the corpus grows. Run the `dev` split as often as you like. **A `held` run is recorded** in the agent's event log (`knowledge_eval_held_run`, with its seed, snapshot and rankers), and a seed is sealed on its first use the same way (`knowledge_eval_sealed`). Every report prints how many held runs came before it, counted from the log, so deleting a file can't reset it, and a gap in the log shows.

The reason is the one experiments give for a sealed split: a configuration chosen by looking at the figures that judge it measures the choosing. The count doesn't stop anyone. It makes the spending visible, so a reader can tell a first held run from a tenth.

- Tune on `dev`. Run `held` once, when the change is finished, and report that run.
- A new `--split-seed` is a new seal. Changing the seed to get a fresh held split is the same as tuning on the old one, unless the old one's figures were never read.
- Pin the corpus with `--save-snapshot` and score it later with `--snapshot`, so two configurations are compared on the same state. A pinned snapshot holds the agent's private text and is written owner-only; it never goes into a repository.

### 6.3 What a leak is, and why it is found by content

A ranker that reads an artifact's text can be handed the answer: a learning's Cross-References section names exactly the learnings the `xref` labels say are relevant. Such a ranker scores well by copying, not by finding.

Before scoring a ranker that reads text, the eval checks each query's input **by content**: does it contain a target's file stem or title? Above 5% of the pairs it can audit it refuses to score, and names the ranker and some of the leaking pairs. A target whose file stem and title are both too short to search for can't be audited: it is counted apart and reported, never counted as clean, so it can't pull the share under the limit. The remedy is to remove the field that names the answer from what the ranker reads, then run it again.

A leak can't be found reliably by field name. Experiment 010 found a `Related` line that named the answers in about a third of its pairs, a field nobody had listed as a label. Ask whether the answer is in the question.

### 6.4 When to run it

- **Before and after a change to how the knowledge query ranks or searches**, on one pinned snapshot, with `--compare OLD NEW` for the paired interval of the difference.
- **To check a claim about the query** ("it ranks", "it finds what I cite"), before stating it.
- **After a large curation pass**, to see whether new wiki-links changed what the query finds.

The `today` ranker is the shipping query, run on each of the query artifact's concepts in turn. `random` is the floor, and a metric that doesn't separate a ranker from it isn't measuring ranking. `idf` is a reference: nodes that share a concept, ordered by how rare the shared concepts are.

---

## Integration with Other Policies

- `scholarship.md` — node classes, provenance, and emergent participation in the knowledge web
- `core_principles.md` — Policy Ships With the Capability
- `debugging_and_validation.md` — evidence standards a doctor's own verification must meet
- `learnings.md` — the index a learnings doctor would examine, and one of the relevance check's label sources
- `experiments.md` and `empiricism.md` — the sealed-split discipline the relevance check applies to the query

## Anti-Patterns

**God-doctor.** One checker over every corpus. Shallow everywhere, or a dumping ground.

**Silent scope.** Reporting findings without reporting what was examined, so a clean run and a run that examined nothing look identical.

**Remedy-free findings.** "Something is wrong" with no next step. Trains skimming.

**Gate-first.** Reaching for CI enforcement before writing down when the check is worth running.

**Judging the query by reading its results.** The author of a ranking is the reader least able to see its faults. Score it with `knowledge eval` against labels the query never read.

**Tuning on the held split.** Choosing a configuration by its held figures, then reporting those figures as a test. Tune on dev; run held once.

**Vocabulary hoarding.** The first doctor keeping the shared terms inside its own module, so the second invents its own and the two become unreadable together.

## Evolution & Feedback

This policy was written alongside the first doctor in the family. It generalises from one instrument and should be expected to be wrong in places only a second and third will reveal. If a new doctor finds the vocabulary does not fit its corpus, that is evidence about the vocabulary rather than about the corpus — say so.

---

## Wiki-Links

<!-- NORMATIVE node (see scholarship on node classes and provenance): this artifact
     states what MUST be done, not what was found or what was true at a moment. It is
     also INHERITED — it ships with the framework rather than being produced by any one
     agent, which is what makes the vocabulary below shared across deployments.
     Link what this policy GOVERNS, never what it merely mentions. -->

[[silent_failure]] [[verification]] [[knowledge_web]]
