---
description: Curate session discoveries into semantic knowledge web with scholarly cross-links
argument-hint: [topic hint] or "multiple" for batch mode
allowed-tools: Read, Bash
---

Curate learnings from session discoveries into the agent's semantic knowledge web.

**Argument**: Optional topic hint, or "multiple" for batch curation

---

## 🚨 CHANNEL-INITIATED ATTACHMENT REQUIREMENT

**If this command was triggered by a message from a `<channel source=...>` tag** (e.g., Telegram), the **completion contract requires sending each curated learning file back through the channel as an attachment** — a summary message alone is not sufficient.

**Why**: Remote channel users cannot navigate the agent's filesystem. The agent's repo + filesystem are invisible from a channel client; the only review surface is what arrives in the channel itself. Without attachments, the user has to ask "where are the files?" — which is the smell that made this requirement explicit.

**Workflow** (channel-initiated, attachment-supporting channel):

1. Curate the learnings as usual (follow the rest of this skill).
2. Commit + push the new learning files (per existing git discipline).
3. **Send a summary reply** via the channel's reply tool — what was curated, which patterns, brief titles.
4. **Send the actual learning files as attachments** via the channel's reply tool with `files: [...]` containing absolute paths to each new learning. For example, on Telegram:
   ```
   mcp__plugin_telegram_telegram__reply(
       chat_id=<from inbound>,
       text="Attaching the N learning files now.",
       files=["/abs/path/2026-XX-XX_HHMMSS_first_learning.md", ...]
   )
   ```
5. The summary message + attachments together constitute the completion deliverable.

**Channels without attachment support**: degrade gracefully — send the summary message only and note in it that the files live at `<repo>/agent/private/learnings/<filenames>` for terminal-side review. Don't pretend an attachment-less channel is the same as a terminal invocation.

**Terminal invocation**: this requirement does not apply — the user is at the filesystem and can read the files directly. A terminal status report is sufficient.

**Discovery rule**: if the invoking message includes a `<channel source="X">` tag, look up X's reply tool's schema. If `files: [...]` is in the parameters, attach. If not, fall back to summary-only.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate learnings
macf_tools policy read learnings
macf_tools policy navigate scholarship
macf_tools policy read scholarship
```

---

## Questions to Extract from Policies

**From learnings.md**:
1. What file format does the policy specify?
2. What metadata does the policy require?
3. What distinguishes learnings from reflections?
4. What cross-reference patterns does the policy define?
5. How does the policy describe the knowledge web architecture?

**From scholarship.md**:
6. What citation formats apply to source artifacts?
7. How does the policy specify bidirectional linking?
8. What enables semantic discovery per the policy?

---

## Pre-Curation Discovery (REQUIRED for "multiple" mode)

Before writing learnings, survey the existing knowledge web to identify cross-link targets:

1. **List existing learnings**: `ls agent/private/learnings/` (scan filenames for topic clusters)
2. **Group by topic**: Identify thematic clusters from filenames or quick content scan
3. **Identify cross-link targets**: For each new learning, which existing learnings relate?
4. **Note back-link candidates**: Which existing learnings should receive new `## Cross-References` entries pointing to the new learning?

**For single curation** (topic hint mode): A targeted search suffices:
```bash
# Search existing learnings for the topic
grep -ri "topic_keyword" agent/private/learnings/
```

**Why**: Cross-references are edges in the knowledge graph. Without pre-curation discovery, agents either skip cross-links (degrading the web) or guess at them (creating broken references). Discovery before writing makes good scholarship the default.

---

## Semantic Web Considerations

**Before writing, consider discovery contexts**:
- When might this learning surface during UserPromptSubmit?
- Does this relate to specific tools (PreToolUse affinity)?
- Would subagents benefit from this wisdom?
- Could this be depersonalized for cross-agent sharing?

**Keywords**: Include LEARN (activation keyword with ALL_CAPS boosting)

---

## Execution

1. Read policies per PEP above
2. **Pre-curation discovery** per section above (REQUIRED for "multiple" mode)
3. Generate breadcrumb: `macf_tools breadcrumb`
4. Apply formats discovered from policy reading
5. Write to location specified by learnings.md
6. Create cross-links per scholarship.md patterns
7. **Update existing learnings** with back-links where identified in step 2

**Multiple mode**: Create separate files, cross-link related learnings

---

## Critical Constraints

- Full breadcrumbs enable forensic archaeology
- Cross-links are bidirectional (update related learnings)
- One insight per file unless tightly coupled
