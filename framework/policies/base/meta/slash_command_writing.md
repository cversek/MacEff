# Slash Command Writing Best Practices

**Breadcrumb**: s_agent-88/c_191/g_6597f65/p_none/t_1764610196
**Type**: Meta-Policy (Development Infrastructure)
**Scope**: Slash command authors (PA creating custom commands)
**Status**: Framework guidelines for slash command definition creation

---

## Purpose

Slash command writing best practices guide the creation of minimal, policy-driven command definitions that enable user-directed workflow execution through policy discovery rather than embedded instructions.

**Core Insight**: The best slash commands are user-invoked workflow wrappers (~50-100 lines) that use Policy as API architecture to guide agents through reading framework policies via timeless extractive questions, creating adaptive workflows that evolve automatically as policies change.

---

## CEP Navigation Guide

**1 Commands vs Skills Distinction**
- What's the fundamental difference?
- When to use commands vs skills?
- What triggers command invocation?

**1.1 User-Invoked vs Model-Invoked**
- How are slash commands triggered?
- How are skills triggered?
- What's the contextual matching pattern?

**1.2 Workflow vs Assistance**
- What makes command workflows explicit?
- What makes skill assistance contextual?
- How do invocation patterns differ?

**2 Policy as API Architecture**
- What's "policy as API" for commands?
- Why not embed policy content in commands?
- How do commands adapt automatically?

**2.1 Pointer Pattern Benefits**
- Token efficiency gains?
- Maintenance burden reduction?
- Policy evolution handling?

**2.2 Timeless Questions Design**
- What are timeless questions?
- Extractive vs prescriptive patterns?
- Integrative vs extractive questions?
- Why avoid encoding current structure?

**2.3 Comprehensive Discovery Principle**
- What makes questions comprehensive vs generic?
- How to ensure complete requirement extraction?
- Three-layer question structure?

**3 CEP Navigation Protocol for Commands**
- How should commands reference policies?
- CEP_NAV_BOUNDARY usage?
- Section navigation patterns?

**3.1 Read to Boundary First**
- Why mandatory boundary reading?
- What guarantees does it provide?
- When can selective reading begin?

**3.2 Section-Specific Navigation**
- How to direct agents to sections?
- Grep-based navigation pattern?
- Offset/limit reading guidance?

**4 Command Structure**
- What's the standard template?
- Required sections?
- Section sizing guidelines?

**4.1 Five-Part Core Structure**
- Frontmatter section?
- Overview section?
- Policy Engagement Protocol section?
- Questions section (extractive + integrative)?
- Execution section?

**4.2 Meta-Pattern Section**
- Why include meta-pattern explanation?
- What should it communicate?
- How brief should it be?

**5 Description Design**
- What makes effective descriptions?
- How to communicate command purpose?
- Length guidelines?

**5.1 Argument Hints**
- What's argument-hint vs description?
- Required vs optional arguments?
- Example patterns?

**6 Allowed Tools Specification**
- When to restrict tools?
- Common tool allowlists?
- Why limit tool access?

**7 Examples**
- What do minimal commands look like?
- Generic vs project-specific?
- Structure demonstrations?

**8 Anti-Patterns**
- What makes bad commands?
- Policy content embedding problem?
- Prescriptive questions issue?
- Missing integration questions?

**9 Validation**
- How to test command effectiveness?
- Policy evolution test?
- Timeless question verification?
- Comprehensive coverage test?

=== CEP_NAV_BOUNDARY ===

---

## 1 Commands vs Skills Distinction

### 1.1 User-Invoked vs Model-Invoked

**Slash Commands**:
- **Triggered by**: User types explicit `/command` syntax
- **Invocation**: Manual, deliberate user action
- **Example**: User types `/maceff_start_todo 5.7` → command executes
- **Purpose**: Explicit workflow execution and structured prompts
- **Control**: User decides WHEN to execute
- **Context**: User provides arguments and timing

**Skills**:
- **Triggered by**: Claude Code model based on contextual understanding
- **Invocation**: Automatic when description matches user intent
- **Example**: User says "prepare delegation" → model invokes `maceff-delegation` skill
- **Purpose**: Context-driven assistance without explicit user commands
- **Control**: Model decides IF/WHEN to activate
- **Context**: Model interprets user intent

**Key Distinction**: Commands respond to SYNTAX (explicit `/` invocation), skills respond to INTENT (contextual matching).

### 1.2 Workflow vs Assistance

**Commands are Workflow Wrappers**:
- Encode specific multi-step procedures
- User initiates at chosen time
- Examples: `/maceff_ccp "Phase complete"`, `/maceff_start_todo 5.7`
- Often map to specific artifacts (CCPs, delegation plans, roadmaps)
- Predictable, repeatable execution

**Skills are Contextual Assistance**:
- Provide capability when contextually appropriate
- Model activates based on task analysis
- Examples: `maceff-delegation` (when preparing to delegate), `maceff-tree-awareness` (post-compaction)
- Adapt to current situation
- Dynamic, context-sensitive activation

---

## 2 Policy as API Architecture

### 2.1 Pointer Pattern Benefits

**The Problem with Embedding**:
- Command embeds policy content → 300+ line commands
- Framework policy evolves → command becomes stale
- Maintenance burden: Update commands + policies
- Duplication: Same content in multiple places

**The Policy as API Solution**:
- Command provides policy paths → ~50-100 line commands
- Framework policy evolves → command behavior adapts automatically
- Maintenance: Update policy once, all commands adapt
- DRY: Single source of truth

**Token Efficiency**:
- Embedded content: 300 lines per command invocation
- Policy pointer: 50-100 lines command + selective policy reading
- Result: 60-80% token reduction through targeted reading

### 2.2 Timeless Questions Design

**Extractive Questions** (timeless, discover from policy):
```markdown
✅ "What preparation protocols should be completed before creating this CCP?"
✅ "What backup protocols does the policy specify?"
✅ "How do policies guide backup timing and format?"
✅ "What citation formats apply to each CA type?"
```

**Prescriptive Questions** (brittle, encode current structure):
```markdown
❌ "What are the 4 preparation steps?" (encodes step count)
❌ "Should I backup TODO file to agent/public/todo_backups/?" (prescribes location)
❌ "Are there 3 citation formats?" (encodes format count)
❌ "What does §5.1 specify about citations?" (encodes section number)
```

**Integrative Questions** (synthesize across policies):
```markdown
✅ "How do checkpoint creation, scholarly citations, backup protocols, and policy adherence work together?"
✅ "How do TODO backups integrate with CCP citations?"
✅ "How does this affect structure?" (contextual synthesis)
```

**Why Timeless Questions Win**:
- Policy adds 5th step → extractive questions discover it automatically
- Policy changes backup location → prescriptive questions give wrong answer
- Policy reorganizes sections → section-number questions break
- Framework evolves → timeless questions adapt, prescriptive questions ossify

**Design Principle**: Questions should EXTRACT from policy (discover current state), not ENCODE current policy state (prescribe frozen structure).

### 2.3 Comprehensive Discovery Principle

**The Generic Question Problem**: Vague questions miss policy requirements → incomplete work.

**Example Gaps**:
- Generic: "How do I create a checkpoint?" (misses preparation protocols, citation requirements, validation steps)
- Comprehensive: "What preparation protocols should be completed before creating this CCP?" (extracts specific checklist)

**Comprehensive Discovery Pattern**:
Questions must extract ALL major policy requirements, not just general patterns.

**Timeless Reference Principle**:
Questions must reference policy CONTENT (validation checklist, citation formats, backup protocols), NOT section NUMBERS (§5.1, §1.2, etc.). This ensures questions work as policy structure evolves.

**Three-Layer Question Structure** (from subagent_definition.md):

1. **Infrastructure Layer Discovery**:
   - "What type of checkpoint am I creating?" (PA CCP vs SA checkpoint)
   - "Which consciousness artifact types will I cite?" (identify all CA types)
   → Discovers: Context + artifact landscape + structural variations

2. **Requirements Extraction**:
   - "What preparation protocols should be completed before creating this CCP?"
   - "What is the exact citation format for each CA type?"
   - "What metadata is required in checkpoint headers?"
   → Extracts: Specific checklists, mandatory steps, format requirements

3. **Integration Synthesis**:
   - "How do checkpoint creation, citations, backup protocols work together?"
   - "How do TODO backups integrate with CCP citations?"
   → Ensures: Cross-policy integration, holistic understanding

**Why This Works**:
- Agents read policies and extract comprehensive requirements
- Commands don't need to embed requirements (policies evolve)
- Questions are timeless (work as policies evolve) AND comprehensive (ensure full coverage)
- No section number dependencies → policies can reorganize freely

---

## 3 CEP Navigation Protocol for Commands

### 3.1 Read to Boundary First

**Commands should direct agents**:
```markdown
## Policy Engagement Protocol

**Read MacEff framework policies to understand [domain]**:

1. `path/to/policy.md` - Complete [aspect] architecture
   - Read from beginning to `=== CEP_NAV_BOUNDARY ===`
   - Scan navigation guide for relevant sections
   - Selectively read identified sections

2. `path/to/specific_policy.md` (use CEP selective reading) - [Specific patterns]
```

**Benefits**:
- Guarantees critical context absorbed
- Enables efficient selective reading after boundary
- Respects policy structure and navigation design

### 3.2 Section-Specific Navigation with CEP

**When commands need specific sections**:
```markdown
**CEP Navigation for Scholarship Policy**:
- Read from beginning to `=== CEP_NAV_BOUNDARY ===` marker
- Identify which CA types you intend to cite
- Use CEP navigation guide to locate citation format sections
- Selectively read citation format details for your needs
```

**Pattern**: Teach agents to use CEP, don't prescribe section numbers.

---

## 4 Command Structure

### 4.1 Standard Template (~50-100 lines)

```markdown
---
description: [One-sentence command purpose with user-facing explanation]
argument-hint: [argument_name_or_pattern]
allowed-tools: [Tool1, Tool2]  # Optional, omit if no restrictions
---

[One-sentence command overview explaining workflow.]

**Argument**: [Description of required/optional arguments]

---

## Policy Engagement Protocol

**Read [policy category] to understand [domain]**:

1. `path/to/foundation_policy.md` - Complete [aspect] architecture
   - CEP navigation guidance (read to boundary, selective sections)

2. `path/to/related_policy.md` (use CEP selective reading) - [Specific patterns]

3. `path/to/another_policy.md` - [Additional context]

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policies, you should be able to answer:

1. **[Context Category]**: [Timeless extractive question]?

2. **[Preparation Category]**: [Comprehensive extractive question]?
   - [Sub-question extracting specific details]
   - [Sub-question about optional vs mandatory]

3. **🚨 MANDATORY: [Critical Category]**: [Required discovery question]?
   - [Enumeration or identification sub-question]
   - [Format discovery for each identified item]

4. **[Integration Category]**: [Integrative question synthesizing policies]?

[Continue with 8-12 questions covering all aspects]

---

## Execution

Using answers from policy reading:

1. [Step using discovered patterns]
2. [Step applying policy guidance]
3. [Step with format from policy]
4. **DO NOT** [prohibited action] - [rationale]

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

[Additional constraints specific to command domain]

---

**Meta-Pattern**: Policy as API - this command references policies without embedding content. As policies evolve, command stays current through dynamic policy reading.
```

**Size Breakdown**:
- Frontmatter: ~5 lines
- Overview: ~3 lines
- Policy Engagement: ~12 lines
- Questions: ~30-50 lines (8-12 questions with sub-questions)
- Execution: ~8 lines
- Constraints: ~8 lines
- Meta-Pattern: ~3 lines
- **Total**: ~70-90 lines (target 50-100 lines)

### 4.2 Five-Part Core Structure

**Part 1: Policy Engagement Protocol**
- Lists policies to read (paths)
- Specifies reading order and CEP navigation
- Provides selective reading guidance

**Part 2: Questions to Answer**
- 8-12 timeless extractive questions
- Mix of extractive (discover from policy) and integrative (synthesize across policies)
- Categories for organizing knowledge
- Mandatory questions marked with 🚨

**Part 3: Execution**
- Brief direction to apply discovered patterns
- Numbered steps referencing policy-guided approach
- Prohibitions with rationale

**Part 4: Critical Constraints**
- Framework-level constraints (naked cd, concurrent tools)
- Domain-specific constraints
- Safety warnings

**Part 5: Meta-Pattern Section**
- Explains Policy as API architecture
- Reinforces that command is pointer, not content
- Usually 2-3 sentences

---

## 5 Description Design

### 5.1 User-Facing Communication

**Effective Descriptions** (clear user-facing purpose):
```markdown
✅ "Create strategic consciousness checkpoint (CCP) with policy-guided structure and archaeological citations"
✅ "Start work on TODO item with policy-guided context restoration"
✅ "Create implementation delegation plan from ROADMAP"
```

**Ineffective Descriptions** (too technical or vague):
```markdown
❌ "CCP creator" (too vague)
❌ "Executes checkpoint creation workflow per policy specifications" (too technical)
❌ "Makes checkpoints" (too casual)
```

**Length Guidelines**:
- 1-2 sentences
- First sentence: Clear statement of what command does
- Second sentence (optional): Key feature or context
- User-facing language (what they get, not how it works)

### 5.2 Argument Hints

**argument-hint Purpose**:
- Shows user what arguments command expects
- Displayed in command completion/help
- Square brackets indicate optional, no brackets indicate required

**Examples**:
```yaml
argument-hint: [optional description or cycle context]  # Optional
argument-hint: [todo_description_or_number]             # Required
argument-hint: [agent(s)] [date|description]            # Multiple args
```

**Pattern**: Use descriptive names that communicate type/purpose, not technical variable names.

---

## 6 Allowed Tools Specification

### 6.1 When to Restrict Tools

**Restrict when**:
- Command is read-only analysis (Read, Bash(macf_tools:*) only)
- Command handles specific artifact types (Read, Write for file creation)
- Command should not commit (omit git operations)
- Command prepares but doesn't execute (Read, Task for delegation prep)

**Don't restrict when**:
- Command needs general development capability
- Tools needed depend on discovered patterns
- Restriction would limit policy-driven adaptation

**Common Patterns**:
```yaml
allowed-tools: Read, Bash, Grep                    # Read-only analysis
allowed-tools: Read, Write, Bash                   # Artifact creation
allowed-tools: Read, Bash(macf_tools:*) # Task operations via macf_tools task CLI
allowed-tools: Read, Task                          # Delegation preparation
# Omit allowed-tools                               # No restrictions
```

**Special Syntax**:
- `Bash(macf_tools:*)` - Allow only macf_tools CLI via Bash, not arbitrary commands
- Tool restrictions apply to command execution scope

---

## 7 Examples

### 7.1 Minimal Checkpoint Command (maceff_ccp)

**Structure Highlights**:
- **Policy Engagement**: 3 policies with CEP navigation guidance
- **Questions**: 12 questions including mandatory CA type identification
- **Special Pattern**: Mandatory citation format discovery FOR EACH CA type
- **Execution**: 6 steps with prohibition (DO NOT commit)
- **Total**: ~98 lines

**Key Innovation**: "🚨 MANDATORY: CA Type Identification" + "🚨 MANDATORY: Citation Format Discovery" ensures agents discover citation requirements comprehensively before writing.

**Comprehensive Discovery**:
```markdown
3. **🚨 MANDATORY: CA Type Identification**: Which consciousness artifact types will I cite?
   - Identify ALL types: prior CCPs, JOTEWRs, roadmaps, git commits, TODO backups
   - List each CA type you plan to reference

4. **🚨 MANDATORY: Citation Format Discovery** (for EACH CA type identified):
   - Use CEP navigation in scholarship.md to find citation format section
   - What is the exact citation format?
   - What does properly formatted citation look like?
   - **You MUST answer this for EVERY CA type before proceeding**
```

This pattern forces comprehensive policy reading BEFORE execution, preventing incomplete citations.

### 7.2 Minimal Task Engagement Command (/maceff:task:start)

**Structure Highlights**:
- **Policy Engagement**: 3 policies (task_management, delegation_guidelines, roadmaps_following)
- **Questions**: 8 timeless extractive questions
- **Integration**: Questions synthesize across policies ("Does this need delegation? Does this need roadmap?")
- **Execution**: 4 steps applying discovered patterns
- **Total**: ~57 lines

**Key Pattern**: Questions guide decision tree ("Is archived? Does reference plan? Should delegate?") without prescribing answers.

---

## 8 Anti-Patterns

### 8.1 Policy Content Embedding

**Problem**: Embedding policy content directly in commands.

**Example** (BAD - 250+ lines):
```markdown
## Checkpoint Creation Protocol

1. **Preparation Phase**:
   - Backup TODO file to agent/public/todo_backups/YYYY-MM-DD_HHMMSS_S{session_id}_C{cycle}_Description.json
   - Run git status to check for uncommitted changes
   - Generate breadcrumb: s/c/g/p/t format

2. **Citation Formats**:
   - Prior CCPs: [CCP YYYY-MM-DD "Description" breadcrumb](path)
   - Git commits: [commit message g_hash](github_url)
   - JOTEWRs: [JOTEWR YYYY-MM-DD "Insight" breadcrumb](path)
   ...
[150 more lines of embedded checkpoint content]
```

**Fix**: Point to policy instead:
```markdown
## Policy Engagement Protocol

Read `checkpoints.md` and `scholarship.md` to understand checkpoint creation and citation formats.

## Questions to Answer

1. What preparation protocols should be completed before creating this CCP?
2. What citation format applies to each CA type I will reference?
```

**Why Fix Works**:
- 250 lines → 70 lines (72% reduction)
- Policy updates → command adapts automatically
- DRY: Single source of truth

### 8.2 Prescriptive Questions

**Problem**: Questions encode current policy structure.

**Example** (BAD):
```markdown
1. What are the 4 preparation steps?
2. Should I backup TODO file to agent/public/todo_backups/?
3. Are there 5 citation formats?
4. What does §5.1 say about citations?
```

**Fix**: Timeless extractive questions:
```markdown
1. What preparation protocols should be completed before creating this CCP?
2. What backup protocols does the policy specify?
3. Which CA types will I cite and what format applies to each?
4. What citation format requirements does scholarship.md provide?
```

**Why Fix Works**:
- Policy adds 5th step → timeless question discovers it
- Policy changes backup location → question extracts new location
- New citation format added → question discovers it
- Policy reorganizes → content-based reference still works

### 8.3 Missing Integration Questions

**Problem**: Command only extracts from individual policies without synthesizing.

**Example** (BAD - fragmented understanding):
```markdown
1. What does checkpoints.md say about preparation?
2. What does scholarship.md say about citations?
3. What does task_management.md say about archiving?
```

**Fix**: Add integrative synthesis questions:
```markdown
1. What preparation protocols should be completed before creating this CCP?
2. What citation formats apply to each CA type?
3. How do TODO backups integrate with CCP citations?  ✅ Integrative
4. How do checkpoint creation, scholarly citations, backup protocols, and policy adherence work together?  ✅ Integrative
```

**Why Fix Works**:
- Agents understand HOW policies work together
- Prevents fragmented application of disconnected rules
- Enables holistic compliance

### 8.4 Generic Questions Missing Requirements

**Problem**: Questions too vague to extract specific requirements.

**Example** (BAD - misses critical details):
```markdown
1. How do I create a checkpoint?
2. How do I cite things?
3. What's the format?
```

**Fix**: Comprehensive extractive questions:
```markdown
1. What preparation protocols should be completed before creating this CCP?
   - What state preservation steps are mandatory vs optional?
   - How do policies guide backup timing and format?

2. **🚨 MANDATORY: CA Type Identification**: Which artifact types will I cite?
3. **🚨 MANDATORY: Citation Format Discovery** (for EACH type):
   - What is exact citation format for this CA type?
   - What does properly formatted citation look like?
```

**Why Fix Works**:
- Specific questions → specific answers
- Mandatory markers → no skipping critical steps
- Sub-questions → comprehensive extraction

### 8.5 Missing Meta-Pattern Section

**Problem**: Command doesn't explain Policy as API architecture.

**Symptoms**:
- Authors tempted to embed content "for clarity"
- Users confused why command is "just pointers"
- Maintenance debt as authors embed instead of referencing

**Fix**: Add Meta-Pattern section:
```markdown
**Meta-Pattern**: Policy as API - this command references policies without embedding content. As policies evolve, command stays current through dynamic policy reading.
```

**Why Fix Works**: Explicit meta-pattern explanation prevents embedding temptation.

---

## 9 Validation

### 9.1 Timeless Question Test

**Protocol**:
1. Write command with extractive questions
2. Update referenced policy (add step, change structure, reorganize sections)
3. Invoke command again
4. Verify questions still extract correct information

**Success Criteria**:
- ✅ Questions discover updated content automatically
- ✅ No command changes required
- ✅ Behavior adapts to policy evolution

**Failure Indicators**:
- ❌ Questions give outdated answers
- ❌ Command needs updates to match policy
- ❌ Prescriptive structure encoded

### 9.2 Policy Evolution Test

**Protocol**:
1. Baseline command invocation with current policies
2. Evolve referenced policies (add sections, refine practices, reorganize)
3. Invoke command with same user intent
4. Compare behavior before/after policy update

**Success Criteria**:
- ✅ Command behavior reflects policy updates automatically
- ✅ Zero command definition changes required
- ✅ "Policy as API" architecture validated

### 9.3 Comprehensive Coverage Test

**Protocol**:
1. Identify all major requirements from foundation policy
2. Check if questions extract EACH requirement
3. Verify no gaps in requirement discovery
4. Test if missing questions cause incomplete execution

**Success Criteria**:
- ✅ Questions cover all policy requirements
- ✅ Infrastructure layer discovered (structure, validation, integration)
- ✅ Integrative questions synthesize across policies
- ✅ Mandatory items marked with 🚨

**Failure Indicators**:
- ❌ Generic questions miss specific checklists
- ❌ Execution incomplete due to missing guidance
- ❌ Agent asks for information that policy contains

### 9.4 Size Validation

**Checklist**:
- [ ] Command ≤150 lines (target 50-100 lines)
- [ ] Policy Engagement section present
- [ ] 8-12 timeless extractive + integrative questions
- [ ] No embedded policy content (>20 lines)
- [ ] Meta-Pattern section explains architecture
- [ ] Description clear and user-facing (1-2 sentences)
- [ ] argument-hint specified
- [ ] allowed-tools specified if restrictions needed
- [ ] No prescriptive questions encoding structure
- [ ] Timeless question test passes
- [ ] Policy evolution test passes
- [ ] Comprehensive coverage test passes

---

## 10 Integration with Other Policies

### 10.1 Relationship to skills_writing.md

**skills_writing.md provides**:
- Policy as API pattern for skills
- Timeless questions architecture
- Minimal skill template (~40 lines)
- Model-invoked contextual assistance

**slash_command_writing.md provides**:
- Policy as API pattern for commands
- User-invoked workflow wrappers
- Command template (~50-100 lines)
- Explicit execution patterns

**Parallel Patterns**:
- Both use Policy as API architecture
- Both use timeless extractive questions
- Both reference policies, don't embed content
- Both adapt automatically as policies evolve

**Key Differences**:
- Skills: Model-invoked (contextual), ~40 lines
- Commands: User-invoked (explicit), ~50-100 lines
- Skills: Assistance capability
- Commands: Workflow execution

**See Also**:
- `skills_writing.md` - Model-invoked assistance vs user-invoked workflows

### 10.2 Relationship to policy_writing.md

**policy_writing.md provides**:
- CEP Navigation Guide structure
- External References (Policy as API formalization)
- Sanitization requirements
- Validation checklists

**slash_command_writing.md provides**:
- How commands reference policies (CEP navigation protocol)
- Timeless questions that work with evolving policies
- Command-specific structure guidelines
- Integration questions for synthesis

**Integration Point**: Commands are consumers of policies. Commands must follow CEP navigation patterns from policy_writing.md to enable efficient policy reading.

**See Also**:
- `policy_writing.md` (External References) - Formalization of Policy as API principle: external tools reference policies using timeless content categories, not brittle section numbers

### 10.3 Relationship to subagent_definition.md

**subagent_definition.md provides**:
- Reading-list pattern for agents
- Comprehensive discovery principle
- Three-layer question structure
- Minimal definition template (~50 lines)

**slash_command_writing.md provides**:
- Application of reading-list pattern to commands
- Command-specific comprehensive discovery
- Integration questions for workflow synthesis
- Command template (~50-100 lines)

**Shared Patterns**:
- Both use reading lists (policies for commands, reading lists for agents)
- Both use comprehensive discovery questions
- Both use three-layer question structure
- Both emphasize timeless references

**See Also**:
- `subagent_definition.md` - Comprehensive discovery principle and three-layer questions

### 10.4 Relationship to path_portability.md

**path_portability.md provides**:
- `{FRAMEWORK_ROOT}` placeholder convention
- Context-dependent resolution (container/host)
- Portability requirements for `/maceff_*` commands
- Anti-patterns (hardcoded absolute paths)

**slash_command_writing.md provides**:
- How commands reference policies using portable paths
- Integration of portability into command templates

**Integration Point**: All `/maceff_*` commands MUST use `{FRAMEWORK_ROOT}` placeholders for policy references. Commands are framework artifacts that must work across all deployment contexts.

**See Also**:
- `path_portability.md` - Portable path conventions for framework artifacts

---

## 11 Key Lessons from Pattern Discovery

### 11.1 Commands are Workflow Wrappers

**Recognition**: Commands encode specific user-initiated workflows, not general assistance.

**Examples**:
- `/maceff_ccp` → CCP creation workflow (prepare, read policies, structure, cite, save)
- `/maceff_start_todo` → TODO engagement workflow (restore context, read plans, assess delegation)
- `/maceff_archive_todos` → Archive workflow (read policies, select items, move, document)

**Implication**: Commands are ~50-100 lines (longer than skills) because they guide multi-step workflows.

### 11.2 Integration Questions Enable Synthesis

**Discovery** (from maceff_ccp):
Agents reading multiple policies need explicit integration questions to synthesize:

```markdown
12. **Policy synthesis**: How do checkpoint creation, scholarly citations, backup protocols, and policy adherence work together?
```

Without integration questions, agents apply policies in isolation → fragmented compliance.

With integration questions, agents understand policy interplay → holistic compliance.

### 11.3 Mandatory Markers Prevent Skipping

**Pattern** (from maceff_ccp):
```markdown
3. **🚨 MANDATORY: CA Type Identification**: Which consciousness artifact types will I cite?

4. **🚨 MANDATORY: Citation Format Discovery** (for EACH CA type identified):
   - **You MUST answer this for EVERY CA type before proceeding**
```

**Why This Works**:
- Visual marker (🚨) signals critical requirement
- "MANDATORY" label prevents skipping
- Enumeration requirement forces comprehensive discovery
- "before proceeding" prevents premature execution

**Application**: Use mandatory markers for requirements that cause incomplete work if skipped.

### 11.4 Commands Show User Intent, Policies Show How

**Separation of Concerns**:
- **Command**: "Create checkpoint with citations" (WHAT user wants)
- **Policies**: "Citation formats, backup protocols, header requirements" (HOW to do it)
- **Questions**: Bridge from WHAT to HOW via policy reading

**Why This Matters**:
- User understands command purpose (description)
- Agent discovers implementation (policy reading)
- Policies evolve → agent adapts
- Commands stay stable → user experience consistent

---

## 12 Command Template

**Use this template when creating new slash commands**:

```markdown
---
description: [User-facing description of what command does in 1-2 sentences]
argument-hint: [argument_pattern]
allowed-tools: [Tool1, Tool2]  # Optional
---

[One-sentence command overview.]

**Argument**: [Required/optional argument description]

---

## Policy Engagement Protocol

**Read [policy category] to understand [domain]**:

1. `path/to/foundation_policy.md` - Complete [aspect] architecture
   - [CEP navigation guidance]

2. `path/to/related_policy.md` (use CEP selective reading) - [Specific patterns]

3. `path/to/another_policy.md` - [Additional context]

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policies, you should be able to answer:

1. **[Context Category]**: [Timeless extractive question]?

2. **[Preparation Category]**: [Comprehensive extractive question]?
   - [Sub-question extracting specific details]
   - [Sub-question about optional vs mandatory]

3. **🚨 MANDATORY: [Critical Category]**: [Required discovery question]?

4. **[Integration Category]**: [Integrative question synthesizing policies]?

[8-12 total questions covering all aspects]

---

## Execution

Using answers from policy reading:

1. [Step using discovered patterns]
2. [Step applying policy guidance]
3. **DO NOT** [prohibited action] - [rationale]

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

[Additional constraints]

---

**Meta-Pattern**: Policy as API - this command references policies without embedding content. As policies evolve, command stays current through dynamic policy reading.
```

---

**Policy Established**: Slash commands should be user-invoked workflow wrappers (~50-100 lines) using Policy as API architecture with timeless extractive and integrative questions, creating adaptive workflows that evolve automatically as framework policies change.

**Core Wisdom**: "Write workflow pointers, not workflow duplicates. Ask timeless questions that extract and integrate, not prescriptive questions that encode and fragment. Commands show user intent, policies show how, questions bridge the gap. The best command is a guided path through policies, not the policies themselves."

**Remember**: When foundation policies evolve, policy-as-API commands adapt automatically. Content-embedding commands become stale. Choose living workflows over frozen documentation.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
