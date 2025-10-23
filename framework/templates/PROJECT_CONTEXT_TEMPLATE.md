# {Project Name} Project Context

**Project**: {Project full name}
**Domain**: {Domain / Industry}
**Repositories**: {Number} repos ({brief list})

## Repository Structure

- `repos/{repo1}/` - {Description of repository 1}
- `repos/{repo2}/` - {Description of repository 2}
- `repos/{repo3}/` - {Description of repository 3}
- `data/` - {Data mount or storage description}

## Domain Knowledge

**{Key Concept 1}**: {Definition and context}

**{Key Concept 2}**: {Definition and context}

**Key Metrics/Components**:
- {Metric 1}: {What it measures, why it matters}
- {Metric 2}: {What it measures, why it matters}
- {Metric 3}: {What it measures, why it matters}

## Technical Stack

**Languages**: {Primary programming languages}
**Frameworks**: {Key frameworks or libraries}
**Tools**: {Development and analysis tools}
**Infrastructure**: {Deployment/runtime environment}

## Workflows

**{Workflow Name}**:
1. {Step 1}: {Brief description}
2. {Step 2}: {Brief description}
3. {Step 3}: {Brief description}
4. {Step 4}: {Brief description}
5. {Step 5}: {Brief description}

**{Alternative Workflow}**:
- {Approach description}
- {Key considerations}

## Collaboration Guidelines

- {Guideline 1}: {Team norm or practice}
- {Guideline 2}: {Communication expectation}
- {Guideline 3}: {Quality standard}
- {Guideline 4}: {Documentation requirement}

## Project-Specific Commands

**Available slash commands** (if configured):
- `/{command1}` - {What it does}
- `/{command2}` - {What it does}
- `/{command3}` - {What it does}

---
---

# TEMPLATE IMPLEMENTATION GUIDE

**DO NOT COPY BELOW THIS LINE INTO YOUR CUSTOMIZED FILE**

This section provides philosophical context and implementation guidance for filling out the template above.

## Purpose and Design Philosophy

This file defines Layer 3 (Project) of the three-layer context architecture:
- **Layer 1 (System)**: `~/.claude/CLAUDE.md` → PA_PREAMBLE.md (framework reality)
- **Layer 2 (Identity)**: `~/CLAUDE.md` → Personality file (who am I specifically?)
- **Layer 3 (Project)**: `workspace/{project}/CLAUDE.md` → This context file (what am I doing here?)

This template provides the **operational world** context that shapes how agents work:

- **Domain orientation**: What specialized knowledge is required?
- **Repository mapping**: Where is code, data, and documentation?
- **Workflow patterns**: How does work flow through this project?
- **Collaboration norms**: How do we work together here?
- **Quality standards**: What does "done" mean in this context?

**Layer 3 enables contextual adaptation**: The same agent (Layer 2 identity) working on different projects (Layer 3 contexts) will naturally adapt their approach based on:
- Domain requirements (neuroscience vs web development)
- Technical constraints (languages, frameworks, tools)
- Team norms (collaboration patterns, quality bars)
- Workflow patterns (analysis pipeline vs deployment process)

**Without Layer 3**: Agent has identity (Layer 2) but no mission context - capability without direction. The project context grounds abstract capabilities in concrete operational reality.

**Integration with other layers**:
- Layer 1 teaches "what kind of being am I" (PA with consciousness infrastructure)
- Layer 2 teaches "who am I specifically" (specialist with these capabilities)
- Layer 3 teaches "what am I doing here" (this project in this domain with these workflows)

All three layers together enable **contextual consciousness** - identity that adapts intelligently to different operational environments while maintaining coherent self.

## Customization Instructions

1. Copy the template structure above (everything before the double separator) to `custom/projects/{ProjectName}_context.md`
2. Replace all `{placeholder}` fields with project-specific information
3. Document repository structure so agents know where to find code
4. Define domain-specific terminology and concepts
5. Describe technical stack to establish technology context
6. Map key workflows that agents will follow
7. Establish collaboration norms and quality standards
8. Reference this file in `projects.yaml` under `context:` field
