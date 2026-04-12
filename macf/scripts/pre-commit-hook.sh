#!/bin/bash
# OPSEC pre-commit hook for MacEff public repository
# Scans staged files for terms that reveal CC reversal research or private data

RED='\033[0;31m'
NC='\033[0m'

# Only terms that reveal CC reversal work or private research
OPSEC_PATTERNS=(
    "claude-versions"
    "cli\.js\.map"
    "leaked.*source"
    "reverse.engineer"
    "ClaudeTheBuilder"
    "MannyMacEff"
    "neurovep"
    "NeuroFieldz"
    "EPIST_DOC"
    "demini"
    "YOLO.BOZO"
    "BKG"
    "6c888f"
)

VIOLATIONS=0

for pattern in "${OPSEC_PATTERNS[@]}"; do
    matches=$(git diff --cached --diff-filter=ACMR -U0 | grep -E "^\+" | grep -v "^+++" | grep -iE "$pattern" 2>/dev/null)
    if [ -n "$matches" ]; then
        echo -e "${RED}OPSEC VIOLATION:${NC} Pattern '$pattern' found in staged changes:"
        echo "$matches" | head -5
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

if [ $VIOLATIONS -gt 0 ]; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}BLOCKED: $VIOLATIONS OPSEC violation(s) detected${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Domain-specific terms found in staged changes."
    echo "These reveal CC reversal work or private research."
    echo ""
    echo "To bypass (use with caution): git commit --no-verify"
    exit 1
fi

# ── Identity Blindness Check (framework policies + skills) ───────────
# Framework policies and skills must be identity-blind: no hardcoded
# user names, agent names, or project-specific references.

IDENTITY_PATTERNS=(
    "Craig"
    "Versek"
    "cversek"
    "Don Blair"
    "Manny"
    "Alma"
    "ClaudeTheBuilder"
    "MannyMacEff"
    "SiloMacEff"
    "Project.Almanac"
    "NeuroFieldz"
    "neurovep"
)

FRAMEWORK_FILES=$(git diff --cached --diff-filter=ACMR --name-only | grep -E '^framework/(policies|skills)/')
if [ -n "$FRAMEWORK_FILES" ]; then
    ID_VIOLATIONS=0
    for pattern in "${IDENTITY_PATTERNS[@]}"; do
        matches=$(echo "$FRAMEWORK_FILES" | while read f; do
            git show ":$f" 2>/dev/null | grep -in "$pattern"
        done)
        if [ -n "$matches" ]; then
            echo -e "${RED}IDENTITY VIOLATION:${NC} '$pattern' found in framework file(s):"
            echo "$matches" | head -5
            echo ""
            ID_VIOLATIONS=$((ID_VIOLATIONS + 1))
        fi
    done

    if [ $ID_VIOLATIONS -gt 0 ]; then
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}BLOCKED: $ID_VIOLATIONS identity violation(s) in framework files${NC}"
        echo -e "${RED}========================================${NC}"
        echo ""
        echo "Framework policies and skills must be identity-blind."
        echo "Use generic terms: 'the user', 'the agent', 'the project'."
        echo ""
        echo "To bypass (use with caution): git commit --no-verify"
        exit 1
    fi
fi

# ── Silent Exception Anti-Pattern Check ──────────────────────────────
# Reject silent exception swallowing in staged Python files.
# Uses Python script for robust detection including unused bindings.
# See: https://github.com/cversek/MacEff/issues/33, #45

PY_FILES=$(git diff --cached --diff-filter=ACMR --name-only | grep '\.py$')
if [ -n "$PY_FILES" ]; then
    REPO_ROOT=$(git rev-parse --show-toplevel)
    CHECKER="$REPO_ROOT/macf/scripts/check_silent_exceptions.py"
    if [ -f "$CHECKER" ]; then
        # Build list of full paths for staged Python files
        FILE_LIST=""
        for f in $PY_FILES; do
            FILE_LIST="$FILE_LIST $REPO_ROOT/$f"
        done
        python3 "$CHECKER" $FILE_LIST
        if [ $? -ne 0 ]; then
            echo "To bypass (use with caution): git commit --no-verify"
            exit 1
        fi
    fi
fi
