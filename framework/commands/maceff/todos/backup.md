---
description: Backup TODO state following policy-compliant protocol
argument-hint: [mission_description]
allowed-tools: Read, Bash(macf_tools:*), Write
---

Backup current TODO state to disk following MacEff framework policy.

**Argument**: $ARGUMENTS (optional mission description for filename)

---

## Policy Engagement Protocol

**MANDATORY**: Read TODO backup protocol before any backup operation.

```bash
# Navigate to see policy structure
macf_tools policy navigate todo_hygiene
```

**Locate the section**: Scan the CEP Navigation Guide for "TODO Backup Protocol" - it contains questions like:
- What is the TODO backup protocol?
- What is the backup filename format?
- Where do backups go?

Once you identify the section number from navigation, read that section:
```bash
macf_tools policy read todo_hygiene --section N  # Replace N with section from navigation
```

---

## Extract Requirements Through Timeless Questions

1. Where are TODO backups stored?
2. What is the backup filename format?
3. What format should the backup content use?
4. What anti-patterns must be avoided?

---

## Execution

After reading policy and extracting requirements:

1. Generate current breadcrumb: `macf_tools breadcrumb`
2. Extract session short (first 8 chars) and cycle from breadcrumb
3. Determine mission description from argument or active TODO mission
4. Construct filename per policy format
5. Write raw JSON array of current TODO state (NO summarization)
6. Report backup path to user

---

## Critical Constraints

🚨 **Never summarize or collapse** - backup must enable FULL STATE RECONSTRUCTION

🚨 **Raw JSON array** - direct copy of TODO structure, every field preserved

---

**Meta-Pattern**: Policy as API - this command reads policy via CLI tools before executing to ensure compliance with current TODO backup requirements.
