---
name: maceff-restart-session
description: Restart the agent's own Claude Code session so it reloads what loads at start (settings, permissions, channels, plugins); the conversation continues. Use when the operator asks for a session restart, resume, refresh, or a reload of settings or permissions (also recognizes the deprecated term "μC").
---

Restart the agent's own session the way the persistent layer says, whatever runs it.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate persistent_layer
macf_tools policy read persistent_layer --section <CEP_MATCH>
macf_tools policy navigate capability_boundaries
macf_tools policy read capability_boundaries --section <CEP_MATCH>
```

`<CEP_MATCH>` is the section whose navigation questions ask how a session is restarted (persistent_layer) and when
`inject exit` refuses (capability_boundaries). For a session that is not its daemon's unit, `agent_harness` says what
supervises it.

---

## Questions to Extract from Policy Reading

1. **What runs this session** - How do I tell whether my session is its daemon's unit, and what confirms it?
2. **My own restart** - How does an agent restart its own session, and who starts it again?
3. **Refusals** - When does that act refuse or stop short, and what does it report instead of an exit?
4. **The operator's route** - How does the operator restart the session, and what happens if I use that route for my
   own session?
5. **No supervisor** - What restarts a session that is not its daemon's unit, and what do I tell the operator when
   nothing does?
6. **After** - Is a restart a resume or a compaction, and what recovery does it call for?

---

## Execution

1. Answer question 1 from `macf_tools env` and the session's own start line, not from memory.
2. Restart by the route the answers give; act on a refusal as it says, never by typing into a dialog.
3. If a channel is attached and the operator is away, tell them a restart was asked and why.
4. Afterwards, carry on as question 6 answers.

---

## Critical Meta-Pattern

**Policy as API**: how a session restarts, what refuses and who starts it again live in the persistent layer and
capability boundaries policies; this skill asks for them.
