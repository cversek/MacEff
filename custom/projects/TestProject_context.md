# TestProject Project Context

**Project**: Named Agents v0.3 Smoke Test
**Domain**: Framework infrastructure validation
**Repositories**: None (smoke test only)

## Repository Structure

- No repositories for smoke test
- Workspace validates symlink creation
- Directory structure testing only

## Domain Knowledge

**Named Agents v0.3**: Architecture replacing numerical agents (PA001, SA001) with named agents (pa_test, pa_manny)

**Key Components**:
- Three-layer context (System/Identity/Project)
- PA_PREAMBLE.md for Primary Agent consciousness
- SA_PREAMBLE.md appended to SubAgent definitions
- Dual artifact pattern (CCP + reflection)

## Technical Stack

**Languages**: Python, Bash, YAML
**Frameworks**: MacEff v0.3.0, MACF Tools 0.1.0
**Tools**: Docker, SSH, Git
**Infrastructure**: Ubuntu 24.04 container

## Workflows

**Smoke Test Validation**:
1. Verify container builds successfully
2. Check PA user created with correct username
3. Validate directory structure (agent/private, agent/public, agent/subagents)
4. Verify three-layer context installation
5. Test subagent workspace creation
6. Validate symlinks and permissions

## Collaboration Guidelines

- Document all validation steps
- Report failures with specific error messages
- Verify against architecture specifications
- Clear pass/fail criteria for each component
