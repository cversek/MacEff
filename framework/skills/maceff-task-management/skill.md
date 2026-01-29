---
name: maceff-task-management
description: Use BEFORE significant task operations (creating, updating, completing, archiving). Emphasizes CLI-first workflow with policy as reference. Run proactively when planning task operations.
allowed-tools: Read, Bash, Grep
---

## CLI-First Workflow

**PRIMARY**: Use Task CLI to discover and execute operations
```bash
macf_tools task --help                    # Discover available commands
macf_tools task create --help             # Discover creation options
macf_tools task complete --help           # Discover completion workflow
macf_tools task archive --help            # Discover archiving options
```

**SECONDARY**: Consult policy when CLI doesn't answer your question
```bash
macf_tools policy navigate task_management  # See available sections
macf_tools policy read task_management --section N  # Read specific guidance
```

## Task CLI Discovery Pattern

**Before any task operation:**

1. **Check CLI help first** - Most operations have smart defaults and built-in validation
2. **Let CLI guide you** - Command options reveal what's possible and required
3. **Consult policy only when uncertain** - Policy explains WHY, CLI shows HOW

## Common Operations (CLI-First)

**Creating Tasks:**
```bash
macf_tools task create --help             # See all creation options
macf_tools task create deleg              # Create delegation task
macf_tools task create bug                # Create bug task
macf_tools task create --parent 5         # Create child task
```

**Listing and Inspecting:**
```bash
macf_tools task list                      # Show all tasks
macf_tools task tree                      # Show hierarchy
macf_tools task get 5                     # Get task details
```

**Completing Work:**
```bash
macf_tools task complete --help           # See completion options
macf_tools task complete 5                # Mark task complete with report
```

**Archiving:**
```bash
macf_tools task archive --help            # See archive options
macf_tools task archive 5                 # Archive completed task
```

## When to Read Policy

Consult `task_management` policy when:

- CLI doesn't explain a concept (MTMD schema, dual dependency system)
- You need to understand architectural decisions (why persistence matters)
- You're designing complex workflows (mission pinning, multi-repo archiving)
- You hit anti-patterns and need deeper understanding

## Policy Questions (Reference Only)

**If CLI doesn't answer your question, extract from policy:**

1. What is the MTMD schema structure?
2. What task type markers exist and when should each be used?
3. What is the MacfTaskUpdate pattern for tracking changes?
4. What is the dual dependency system (hierarchy vs blocking)?
5. When must I include CA references in tasks?
6. What is cascade behavior in archiving?
7. What protection system governs dangerous operations?
8. What anti-patterns should I avoid?

## Critical Insight

**The Task System is TOOLED, not just DOCUMENTED:**
- CLI commands have smart defaults (no manual MTMD assembly)
- Validation happens at CLI layer (catch errors early)
- Discovery happens through `--help`, not policy memorization
- Policy explains principles, CLI executes patterns

## Version History

- v1.0 (2026-01-29): Initial creation as Task System successor to maceff-todo-hygiene, emphasizing CLI-first workflow
