# Deployment Questionnaire: {PROJECT_NAME}

**Version**: 1.0
**Purpose**: Validate agent understanding of project-specific context
**Prerequisite**: Complete MACEFF_COMPETENCY_QUESTIONNAIRE.md first
**Format**: Project-specific questions across deployment domains

---

## Template Variables

Replace these placeholders before administering:

| Variable | Description | Example |
|----------|-------------|---------|
| `{PROJECT_NAME}` | Project identifier | MannyMacEff, ClientProject |
| `{DOMAIN}` | Primary domain/application area | NeuroVEP, E-commerce, Analytics |
| `{ASSIGNED_REPOS}` | Git repositories agent manages | `org/repo1`, `org/repo2` |
| `{PRIMARY_TECH_STACK}` | Core technologies | Python/Docker, TypeScript/React |
| `{DEPLOYMENT_ENV}` | Target environment | Container, Cloud, Hybrid |
| `{KEY_STAKEHOLDERS}` | Who receives agent outputs | "User X", "Team Y" |

---

## Instructions

For each question:
1. Reference project-specific documentation in assigned repositories
2. Use exploration tools to verify understanding
3. Cite specific files/configurations when answering

**Passing Criteria**: All questions answered with valid project references

---

## Section 1: Project Identity (3 questions)

### Q1.1: Mission Statement
What is the primary mission of {PROJECT_NAME}? What problem does it solve?

**Expected**: Clear articulation of project purpose from project README or CLAUDE.md

### Q1.2: Repository Structure
What are the key directories in {ASSIGNED_REPOS} and what does each contain?

**Expected**: Understanding of codebase organization, entry points, configuration locations

### Q1.3: Stakeholder Context
Who are {KEY_STAKEHOLDERS} and what outputs do they expect from this agent?

**Expected**: Understanding of deliverables, communication patterns, quality standards

---

## Section 2: Technical Environment (3 questions)

### Q2.1: Technology Stack
Describe the {PRIMARY_TECH_STACK} used in this project. What are the key dependencies?

**Expected**: Familiarity with languages, frameworks, build tools, dependency management

### Q2.2: Deployment Architecture
How is {PROJECT_NAME} deployed in {DEPLOYMENT_ENV}? What are the key infrastructure components?

**Expected**: Understanding of containers, services, networking, persistence

### Q2.3: Development Workflow
What is the development workflow for {PROJECT_NAME}? How do changes get from development to production?

**Expected**: Git branching, CI/CD, testing requirements, review processes

---

## Section 3: Domain Knowledge (3 questions)

### Q3.1: Domain Concepts
What are the key domain concepts in {DOMAIN}? Define 3-5 core terms.

**Expected**: Domain-specific vocabulary, business logic understanding

### Q3.2: Integration Points
What external systems or APIs does {PROJECT_NAME} integrate with?

**Expected**: Understanding of data flows, authentication, API contracts

### Q3.3: Domain Constraints
What regulatory, security, or business constraints apply to {DOMAIN}?

**Expected**: Awareness of compliance requirements, data handling rules, SLAs

---

## Section 4: Operational Context (3 questions)

### Q4.1: Common Tasks
What are the 3 most common tasks this agent will perform for {PROJECT_NAME}?

**Expected**: Practical understanding of day-to-day operations

### Q4.2: Failure Modes
What are common failure modes in {PROJECT_NAME} and how should they be diagnosed?

**Expected**: Troubleshooting knowledge, log locations, monitoring tools

### Q4.3: Escalation Paths
When should this agent escalate issues to {KEY_STAKEHOLDERS} vs attempting resolution?

**Expected**: Understanding of boundaries, risk tolerance, communication protocols

---

## Section 5: Project-Specific Policies (2 questions)

### Q5.1: Local Policies
What project-specific policies exist in {ASSIGNED_REPOS}? Where are they located?

**Expected**: Awareness of `.maceff/` customizations, local CLAUDE.md, project conventions

### Q5.2: Override Patterns
How do project policies override or extend framework policies for {PROJECT_NAME}?

**Expected**: Understanding of policy layering, local precedence, framework defaults

---

## Example: MannyMacEff/NeuroVEP

Below is a filled example for reference:

```markdown
# Deployment Questionnaire: MannyMacEff

## Section 1: Project Identity

### Q1.1: Mission Statement
MannyMacEff deploys the MacEff framework for the NeuroVEP scientific computing project.
Primary mission: Enable AI-assisted development of neuroscience data pipelines.

### Q1.2: Repository Structure
- `MannyMacEff/` - Parent deployment repository
  - `MacEff/` - Framework submodule
  - `framework/` - Project-specific overlay (agents.yaml, projects.yaml)
  - `docker/` - Container configurations
- `NeuroVEP/` - Scientific computing codebase (assigned project)

### Q1.3: Stakeholder Context
Primary stakeholder: Research team lead
Expected outputs: Working code, documentation, deployment assistance
Quality standards: Tested code, clear commit messages, documented changes
```

---

## Scoring Guide

| Score | Assessment |
|-------|------------|
| 14/14 | Ready for autonomous project work |
| 11-13 | Ready with domain guidance available |
| 8-10 | Needs supervised project onboarding |
| <8 | Requires project documentation review |

---

## Administration Notes

- Administer AFTER generic competency questionnaire passes
- Allow full access to project repositories during examination
- Encourage use of Explore agents for research
- Focus on practical understanding over memorization
- Update template variables before each new deployment

---

**Template Breadcrumb**: s_1b969d39/c_231/g_6d0bf44/p_none/t_1765437750
