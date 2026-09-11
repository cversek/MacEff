---
name: maceff-role-focus
description: USE when the agent should hold one standing position as its working scope ("focus on the TA role", "put the librarian down"), or when a hook names a due duty in an unfocused role. Focus and unfocus per the roles policy, including the honest escape.
allowed-tools: Bash, Read
---

Focus a role, or put it down, understanding what focus does to the hooks.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate roles
```

Read the sections on servicing, pointers and focus; display; and focus as prioritized auto-scoping.

---

## Questions to Extract from Policy Reading

1. **What focus is** - How is focus stored, how many roles may be focused, and how does it relate to the work mode?
2. **What changes in the tree** - What does a focused role show that an unfocused one does not, and what is never truncated?
3. **The gate** - What does the Stop hook do for a focused role, what bounds it, and how does it differ between AUTO_MODE and MANUAL_MODE?
4. **Servicing** - What counts as a service, and which duties does a service clear from the gate's bound?
5. **The escape** - What does the policy say unfocus records, what is the named anti-pattern, and what does an honest escape look like?
6. **The nag** - What does the framework do when a duty in an unfocused role becomes due, and what acknowledges it?

---

## Execution

- To focus: `macf_tools role focus <id-or-title-prefix>`; read what it reports as due now and unserviced; then `macf_tools task tree` to see the expanded stanza.
- To put a role down: service or defer what is due first where honest (`macf_tools role duty note|done|defer`), then `macf_tools role unfocus --note "<why>"`.
- To see the current focus: `macf_tools role focus`.

---

## Critical Meta-Pattern

**Policy as API**: the gate's bound, the nag's schedule and the escape's audit trail are the policy's; this skill points at them.
