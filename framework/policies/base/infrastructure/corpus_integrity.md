# Corpus Integrity and the Doctor Family

**Version**: 1.0.0
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
| **acute** | Something is wrong **now** and will mislead a reader who trusts it. A registry claiming a type that does not exist; an index reporting coverage it does not have. These produce confident wrong answers. |
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

When a finding is real but its remedy lives in another corpus, the doctor **refers** rather than reaching across. A knowledge-web doctor that discovers an undeclared artifact directory reports it and names the registry that owns the fix; it does not edit the manifest.

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

## Integration with Other Policies

- `scholarship.md` — node classes, provenance, and registry authority for the knowledge web
- `core_principles.md` — Policy Ships With the Capability
- `debugging_and_validation.md` — evidence standards a doctor's own verification must meet
- `learnings.md` — the index a learnings doctor would examine

## Anti-Patterns

**God-doctor.** One checker over every corpus. Shallow everywhere, or a dumping ground.

**Silent scope.** Reporting findings without reporting what was examined, so a clean run and a run that examined nothing look identical.

**Remedy-free findings.** "Something is wrong" with no next step. Trains skimming.

**Gate-first.** Reaching for CI enforcement before writing down when the check is worth running.

**Vocabulary hoarding.** The first doctor keeping the shared terms inside its own module, so the second invents its own and the two become unreadable together.

## Evolution & Feedback

This policy was written alongside the first doctor in the family. It generalises from one instrument and should be expected to be wrong in places only a second and third will reveal. If a new doctor finds the vocabulary does not fit its corpus, that is evidence about the vocabulary rather than about the corpus — say so.
