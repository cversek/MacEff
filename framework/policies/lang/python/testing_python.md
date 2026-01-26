# Python Testing Guide

**Breadcrumb**: s_agent-84/c_177/g_8d1e86e/p_none/t_1763876414
**Type**: Language-Specific Implementation Guide
**Scope**: Python projects using pytest
**Status**: ACTIVE
**Updated**: 2025-11-23
**Implements**: `base/development/testing.md` universal philosophy

---

## Purpose

This guide provides pytest-specific implementation of MacEff's universal testing standards. It translates language-agnostic principles (4-6 test discipline, progressive verbosity, foundation vs integration rigor) into concrete Python code patterns, pytest commands, and pytest-specific anti-patterns.

**Core Insight**: Universal testing philosophy remains constant across languages. This guide shows HOW to apply those principles using pytest tools, fixtures, parametrization, and CLI flags.

---

## CEP Navigation Guide

**1 pytest Conventions**
- How do I structure pytest tests?
- What are pytest naming conventions?
- How do I organize test files?
- What is conftest.py for?
- How do I use test classes?

**1.1 File and Function Naming**
- What naming patterns does pytest recognize?
- How do I name test files?
- How do I name test functions?
- What about test classes?

**1.2 Directory Structure**
- Where do test files go?
- How do I organize unit vs integration tests?
- What is the tests/ directory pattern?
- How do I mirror source structure?

**1.3 Test Discovery**
- How does pytest find tests?
- What patterns does pytest recognize?
- How do I control test discovery?

**2 Fixture Patterns**
- What are pytest fixtures?
- How do I create fixtures?
- What are fixture scopes?
- When do I use parametrization?
- How do I share fixtures across tests?

**2.1 Basic Fixtures**
- How do I define a fixture?
- How do I use fixtures in tests?
- What is the @pytest.fixture decorator?
- How do I provide test data via fixtures?

**2.2 Fixture Scopes**
- What scopes are available?
- When do I use function scope?
- When do I use module scope?
- When do I use session scope?
- What are scope trade-offs?

**2.3 Parametrization**
- How do I parametrize tests?
- What is @pytest.mark.parametrize?
- How does parametrization implement 4-6 test principle?
- When should I avoid parametrization?

**2.4 conftest.py Pattern**
- What is conftest.py?
- How do I share fixtures?
- Where does conftest.py go?
- What goes in conftest.py?

**3 Implementing Test Running Discipline**
- How do I run tests in summary mode?
- What pytest flags implement progressive verbosity?
- How do I run specific tests?
- How do I generate coverage reports?
- How do I filter tests by marks?

**3.1 Progressive Verbosity with pytest**
- What flags implement Level 0 (Summary)?
- What flags implement Level 1 (Failures)?
- What flags implement Level 2 (Diagnostic)?
- How do I choose appropriate verbosity?

**3.2 Token-Efficient Workflow**
- What is the step-by-step pytest workflow?
- How do I minimize token consumption?
- When do I escalate verbosity?
- How do I target specific tests?

**3.3 Common pytest Flags**
- How do I run specific tests?
- How do I filter by marks?
- How do I stop on first failure?
- How do I generate coverage reports?
- What are the most useful flags?

**3.4 Phase Completion Workflow**
- How do I verify phase completion with pytest?
- What commands do I run?
- How do I document results in roadmaps?
- What output should I capture?

**4 Python-Specific Anti-Patterns**
- What is fixture scope creep?
- What is parametrization explosion?
- What are import-time side effects?
- How do I avoid these patterns?
- What are real examples?

**4.1 Fixture Scope Creep**
- What is the anti-pattern?
- Why is it harmful?
- How do I recognize it?
- How do I fix it?

**4.2 Parametrization Explosion**
- What is parametrization explosion?
- How does it violate 4-6 principle?
- What are warning signs?
- How do I use parametrization correctly?

**4.3 Import-Time Side Effects**
- What are import-time side effects?
- Why do they break tests?
- How do I avoid them?
- What is the fixture solution?

**4.4 Mutable Fixture State**
- What is mutable fixture state?
- How does it create test interdependence?
- How do I ensure isolation?

**5 Integration with Universal Standards**
- How does this implement testing.md?
- Where do I find universal philosophy?
- How do I apply 4-6 test principle in pytest?
- What is foundation vs integration in pytest?

**5.1 4-6 Test Principle in pytest**
- How do test classes help organization?
- How does parametrization relate to test counting?
- What counts as one test?

**5.2 Foundation vs Integration in pytest**
- How do I mark foundation tests?
- How do I mark integration tests?
- How do I run them separately?
- What is the pytest marks pattern?

**5.3 Cross-References**
- Where is universal testing policy?
- Where are other Python policies?
- Where are delegation guidelines?

=== CEP_NAV_BOUNDARY ===

---

## 1 pytest Conventions

### 1.1 File and Function Naming

**pytest Discovery Patterns**:

pytest automatically discovers tests using these naming conventions:

**Test Files**:
```python
# pytest recognizes these patterns:
test_*.py          # Preferred: test_feature.py
*_test.py          # Alternative: feature_test.py
```

**Test Functions**:
```python
# pytest recognizes functions starting with test_
def test_feature_behavior():
    """Descriptive docstring explaining what this tests."""
    assert feature() == expected_result

def test_error_handling_invalid_input():
    """Tests error handling for invalid input."""
    with pytest.raises(ValueError):
        feature(invalid_input)
```

**Test Classes** (optional organization):
```python
# Class names must start with Test (no __init__ method)
class TestBreadcrumbParsing:
    """Group related tests for breadcrumb parsing."""

    def test_parse_valid_format(self):
        """Valid breadcrumb parsed correctly."""
        result = parse_breadcrumb("s_abc/c_1/g_def/p_ghi/t_123")
        assert result.session == "abc"

    def test_parse_invalid_format_raises_error(self):
        """Invalid format raises ValueError."""
        with pytest.raises(ValueError):
            parse_breadcrumb("invalid_format")
```

**Naming Best Practices**:
- Use descriptive names: `test_feature_scenario()` not `test_1()`
- Document behavior: `test_returns_none_when_file_missing()`
- Include expected outcome: `test_raises_error_on_invalid_input()`

### 1.2 Directory Structure

**Standard Python Test Organization**:

```
project/
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── module.py
│       └── utils.py
└── tests/
    ├── __init__.py          # Make tests a package
    ├── conftest.py          # Shared fixtures
    ├── test_module.py       # Mirror source structure
    ├── test_utils.py
    └── integration/
        ├── conftest.py      # Integration-specific fixtures
        └── test_workflow.py
```

**What Goes Where**:

| Test Type | Location | Purpose |
|-----------|----------|---------|
| Unit tests | `tests/test_*.py` | Test individual functions/classes |
| Integration tests | `tests/integration/` | Test complete workflows |
| Fixtures | `tests/conftest.py` | Shared test data and setup |
| Test utilities | `tests/helpers.py` | Custom assertion helpers |

**Real Example** (from MacEff):
```
MacEff/
├── tools/src/macf/
│   ├── utils.py
│   └── hooks/
│       └── handle_session_start.py
└── tests/
    ├── conftest.py
    ├── test_temporal_utils.py    # Tests macf/utils.py
    ├── test_auto_mode.py
    └── integration/
        └── test_hook_workflows.py
```

### 1.3 Test Discovery

**How pytest Finds Tests**:

```bash
# pytest scans current directory and subdirectories for:
# 1. Files: test_*.py or *_test.py
# 2. Functions: def test_*()
# 3. Classes: class Test* (no __init__)
# 4. Methods: def test_*() inside Test* classes

# Run discovery (shows what pytest found):
pytest --collect-only
```

**Control Discovery**:

```bash
# Test specific file
pytest tests/test_module.py

# Test specific function
pytest tests/test_module.py::test_specific_function

# Test specific class
pytest tests/test_module.py::TestClassName

# Test specific method in class
pytest tests/test_module.py::TestClassName::test_method
```

---

## 2 Fixture Patterns

### 2.1 Basic Fixtures

**What Are Fixtures**: Fixtures provide test data, setup, and teardown in reusable form.

**Basic Fixture Pattern**:

```python
import pytest

@pytest.fixture
def sample_config():
    """Provide sample configuration for tests."""
    return {"timeout": 30, "retries": 3, "debug": False}

def test_uses_config(sample_config):
    """Test function receives fixture as argument."""
    assert sample_config["timeout"] == 30
    assert sample_config["retries"] == 3
```

**Fixture with Setup/Teardown**:

```python
@pytest.fixture
def temp_file(tmp_path):
    """Create temporary file for testing."""
    # Setup
    test_file = tmp_path / "test.txt"
    test_file.write_text("test data")

    # Provide to test
    yield test_file

    # Teardown (runs after test completes)
    # tmp_path automatically cleaned up by pytest
```

**Real Example** (from MacEff tests):

```python
@pytest.fixture
def mock_consciousness_config():
    """Pre-configured agent environment for testing."""
    return {
        "agent_id": "test_agent",
        "session_id": "test-session-123",
        "agent_root": "/tmp/test_agent"
    }

def test_session_management(mock_consciousness_config):
    """Session management uses configuration."""
    config = mock_consciousness_config
    assert config["agent_id"] == "test_agent"
```

### 2.2 Fixture Scopes

**Available Scopes**:

| Scope | Lifetime | Use When |
|-------|----------|----------|
| `function` | Per test function (default) | Test needs fresh data |
| `class` | Per test class | Tests share immutable data |
| `module` | Per test file | Expensive setup (database) |
| `session` | Entire test run | Very expensive (server start) |

**Function Scope** (default, safest):

```python
@pytest.fixture  # Same as scope="function"
def fresh_data():
    """Each test gets fresh data."""
    return {"counter": 0}

def test_increment(fresh_data):
    fresh_data["counter"] += 1
    assert fresh_data["counter"] == 1

def test_independent(fresh_data):
    # Gets new fresh_data, not modified version
    assert fresh_data["counter"] == 0  # Still 0!
```

**Module Scope** (shared across file):

```python
@pytest.fixture(scope="module")
def database_connection():
    """Module-scoped: created once per test file."""
    # Expensive setup
    conn = connect_to_db()
    yield conn
    # Teardown once at end of module
    conn.close()
```

**Session Scope** (shared across all tests):

```python
@pytest.fixture(scope="session")
def test_server():
    """Session-scoped: created once for entire test run."""
    server = start_test_server()
    yield server
    server.shutdown()
```

**Scope Trade-offs**:
- **Function scope**: Safest (test isolation), slower (repeated setup)
- **Module/Session scope**: Faster (shared setup), riskier (shared state)

### 2.3 Parametrization

**Purpose**: Run same test with multiple inputs (implements 4-6 test principle).

**Basic Parametrization**:

```python
@pytest.mark.parametrize("input,expected", [
    ("valid", True),
    ("invalid", False),
    ("", False),
    (None, False)
])
def test_validation(input, expected):
    """4 parameter sets = ONE test function (not 4 tests)."""
    assert validate(input) == expected
```

**Multiple Parameters**:

```python
@pytest.mark.parametrize("hour,expected", [
    (0, "Late night / Early morning"),
    (6, "Morning"),
    (12, "Afternoon"),
    (18, "Evening"),
    (23, "Late night / Early morning")
])
def test_time_of_day_detection(hour, expected):
    """5 parameter sets test time classification."""
    assert get_time_of_day(hour) == expected
```

**Real Example** (from MacEff test_auto_mode.py):

```python
def test_confidence_scores_in_valid_range(monkeypatch):
    """Confidence scores are in 0.0-1.0 range."""
    scenarios = [
        ("true", "env", 0.9),
        ("false", "env", 0.9),
        ("", "default", 0.0),
    ]

    for env_value, expected_source, expected_confidence in scenarios:
        if env_value:
            monkeypatch.setenv("MACF_AUTO_MODE", env_value)
        else:
            monkeypatch.delenv("MACF_AUTO_MODE", raising=False)

        enabled, source, confidence = detect_auto_mode("test-session")
        assert 0.0 <= confidence <= 1.0
        assert source == expected_source
```

**Parametrization and 4-6 Principle**:
- Parameter sets count as variations within ONE test
- Test function count is what matters for 4-6 principle
- 5 parameter sets ≠ 5 tests (it's 1 test with 5 cases)

### 2.4 conftest.py Pattern

**What is conftest.py**: Special file for sharing fixtures across test files.

**Location Rules**:
- `tests/conftest.py` - Available to all tests in tests/
- `tests/integration/conftest.py` - Available only to integration tests

**Example conftest.py**:

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def temp_agent_root(tmp_path):
    """Create temporary agent root directory."""
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    (agent_root / "private").mkdir()
    (agent_root / "public").mkdir()
    return agent_root

@pytest.fixture
def mock_session_id():
    """Provide consistent test session ID."""
    return "test-session-abc123"

# All test files in tests/ can now use these fixtures
```

**Using Shared Fixtures**:

```python
# tests/test_checkpoints.py
def test_checkpoint_creation(temp_agent_root, mock_session_id):
    """Uses fixtures from conftest.py without importing."""
    # Fixtures automatically available
    checkpoint_path = create_checkpoint(temp_agent_root, mock_session_id)
    assert checkpoint_path.exists()
```

---

## 3 Implementing Test Running Discipline

### 3.1 Progressive Verbosity with pytest

**Implements**: `testing.md §3.2` progressive verbosity protocol using pytest flags.

**Level 0: Summary Mode** (100-500 tokens):

```bash
# Minimal output, just pass/fail counts
pytest --tb=no -q

# Example output:
# .....F...F  [23 passed, 2 failed in 0.8s]
```

**Level 1: Failures Only** (1k-2k tokens):

```bash
# Show failed test details, suppress passing tests
pytest --tb=short

# Example output:
# test_module.py::test_compaction_detection FAILED
# AssertionError: Expected True, got False
```

**Level 2: Full Diagnostic** (5k+ tokens):

```bash
# Verbose output with full tracebacks
pytest -v --tb=long

# Shows:
# - All test names
# - Complete stack traces
# - Local variable dumps
# - Full error context
```

**Progressive Workflow**:

```bash
# Step 1: Phase completion check (minimal tokens)
pytest --tb=no -q

# If all pass → Document and proceed
# If failures → Step 2

# Step 2: Investigate specific module
pytest tests/test_failing_module.py --tb=short

# If cause clear → Fix and return to Step 1
# If cause unclear → Step 3

# Step 3: Deep diagnostic on specific test
pytest tests/test_module.py::test_failing_function -v --tb=long
```

### 3.2 Token-Efficient Workflow

**The Economics**:
- Full verbose: 10,000+ tokens
- Summary mode: 100-500 tokens
- Efficiency gain: 20-100x reduction

**Example Workflow**:

```bash
# GOOD (token-efficient):
# Run 1: Summary (200 tokens)
pytest --tb=no -q
# Output: ......................FF [23 tests, 2 failed]

# Run 2: Failures only on specific module (500 tokens)
pytest tests/test_hooks.py --tb=short
# Shows only 2 failing tests

# Run 3: Verify fix (200 tokens)
pytest --tb=no -q
# Output: ........................ [23 passed in 0.8s]
# Total: 900 tokens

# BAD (token-wasteful):
# Run 1: Full verbose (12,000 tokens)
pytest -v --tb=long
# Run 2: Full verbose (12,000 tokens)
pytest -v --tb=long
# Total: 24,000 tokens (27x more expensive!)
```

### 3.3 Common pytest Flags

**Running Specific Tests**:

```bash
# Run specific test file
pytest tests/test_module.py

# Run specific test function
pytest tests/test_module.py::test_function

# Run tests matching pattern
pytest -k "test_parse"  # Runs all tests with "parse" in name
```

**Filtering by Marks**:

```python
# Mark tests in code:
@pytest.mark.integration
def test_complete_workflow():
    """Integration test for complete workflow."""
    pass

@pytest.mark.slow
def test_performance_under_load():
    """Slow performance test."""
    pass
```

```bash
# Run only integration tests
pytest -m integration

# Exclude slow tests
pytest -m "not slow"

# Exclude integration and performance
pytest -m "not integration and not performance"
```

**Coverage Reports**:

```bash
# Terminal coverage report
pytest --cov=mypackage --cov-report=term-missing

# HTML coverage report (detailed)
pytest --cov=mypackage --cov-report=html
# Open htmlcov/index.html in browser

# Show missing lines
pytest --cov=mypackage --cov-report=term-missing
```

**Other Useful Flags**:

```bash
# Stop on first failure
pytest -x

# Show 3 slowest tests
pytest --durations=3

# Show print statements (for debugging)
pytest -s

# Rerun only failed tests from last run
pytest --lf  # "last failed"

# Run failed tests first, then others
pytest --ff  # "failed first"
```

### 3.4 Phase Completion Workflow

**Implements**: `testing.md §3.5` roadmap integration.

**Standard Phase Completion**:

```bash
# Step 1: Run test suite in summary mode
pytest --tb=no -q

# Example output to document:
# ................................. [19 passed in 0.03s]
```

**Document in Roadmap**:

```markdown
## Phase 1A Complete

**Implementation**: 5 utility functions (150 lines)
**Tests**: 19/19 passed in 0.03s (summary mode)
**Coverage**: 95% (pytest --cov=macf --cov-report=term-missing)
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

**Test Output**:
```
pytest --tb=no -q
................................. [19 passed in 0.03s]
```
```

**With Coverage Documentation**:

```bash
# Run with coverage
pytest --cov=macf --cov-report=term-missing --tb=no -q

# Document results
# Coverage: 95% (macf/utils.py: 147/150 lines covered)
# Tests: 19/19 passed in 0.03s
```

---

## 4 Python-Specific Anti-Patterns

### 4.1 Fixture Scope Creep

**The Anti-Pattern**: Using broader fixture scope than necessary, creating shared mutable state.

**BAD - Session-scoped mutable fixture**:

```python
@pytest.fixture(scope="session")
def shared_counter():
    """Session-scoped fixture with mutable state."""
    return {"count": 0}  # Shared across ALL tests!

def test_increment(shared_counter):
    shared_counter["count"] += 1
    assert shared_counter["count"] == 1  # Passes first time

def test_independent(shared_counter):
    # Gets SAME shared_counter, not fresh one!
    assert shared_counter["count"] == 0  # FAILS! count is 1
```

**GOOD - Function-scoped or immutable**:

```python
# Option 1: Function scope (default)
@pytest.fixture
def fresh_counter():
    """Each test gets fresh counter."""
    return {"count": 0}

# Option 2: Use deepcopy for shared data
from copy import deepcopy

@pytest.fixture(scope="session")
def base_config():
    """Immutable base configuration."""
    return {"timeout": 30, "retries": 3}

@pytest.fixture
def test_config(base_config):
    """Each test gets independent copy."""
    return deepcopy(base_config)
```

**How to Recognize**:
- Fixtures with scope broader than `function`
- Fixtures returning mutable data (lists, dicts)
- Tests failing when run in different orders
- Tests passing alone but failing in suite

**Fix**: Use function scope by default, only broaden when performance requires AND data is immutable.

### 4.2 Parametrization Explosion

**The Anti-Pattern**: Using parametrization to create exhaustive permutations, violating 4-6 test principle.

**BAD - Cartesian product explosion**:

```python
# Creates 10,000 test runs (100 x 100)!
@pytest.mark.parametrize("x", range(100))
@pytest.mark.parametrize("y", range(100))
def test_addition(x, y):
    """10,000 test runs violates 4-6 principle!"""
    assert add(x, y) == x + y
```

**BAD - Testing every theoretical value**:

```python
# 1000 test runs for simple validation
@pytest.mark.parametrize("cycle", range(1000))
def test_cycle_validation(cycle):
    """Tests every cycle 0-999 (exhaustive permutation trap)."""
    assert is_valid_cycle(cycle)
```

**GOOD - Representative samples (4-6 principle)**:

```python
# 4 focused parameter sets
@pytest.mark.parametrize("x,y,expected", [
    (0, 0, 0),      # Zero case
    (1, 1, 2),      # Positive case
    (-1, -1, -2),   # Negative case
    (100, 200, 300) # Larger values
])
def test_addition_representative_cases(x, y, expected):
    """4 parameter sets test key scenarios."""
    assert add(x, y) == expected
```

**GOOD - Boundary testing**:

```python
# 6 focused boundary tests
@pytest.mark.parametrize("cycle,expected", [
    (0, True),       # Minimum boundary
    (1, True),       # Just above minimum
    (999, True),     # Just below maximum
    (1000, True),    # Maximum boundary
    (-1, False),     # Below minimum (error)
    (1001, False)    # Above maximum (error)
])
def test_cycle_boundaries(cycle, expected):
    """6 boundary cases sufficient."""
    assert is_valid_cycle(cycle) == expected
```

**How to Recognize**:
- Multiple `@pytest.mark.parametrize` decorators (Cartesian product)
- `range(100)` or similar large ranges
- Test count exceeds 20 for single function
- Parameter sets test theoretical space, not real usage

**Fix**: Select 4-6 representative cases covering boundaries and likely failures.

### 4.3 Import-Time Side Effects

**The Anti-Pattern**: Code that executes during module import, breaking test isolation.

**BAD - Import-time execution**:

```python
# test_module.py
import os

# This runs when file imported!
setup_database()  # Side effect at import time
os.environ["TEST_MODE"] = "true"  # Pollutes environment

def test_feature():
    """Test runs with polluted state."""
    pass
```

**BAD - Module-level state**:

```python
# Shared mutable state at module level
_test_counter = 0

def test_increment():
    global _test_counter
    _test_counter += 1
    assert _test_counter == 1  # Fails if run after other tests
```

**GOOD - Use fixtures for setup**:

```python
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Runs before each test automatically."""
    # Setup
    original_env = os.environ.copy()
    setup_database()

    yield  # Test runs here

    # Teardown
    cleanup_database()
    os.environ.clear()
    os.environ.update(original_env)

def test_feature():
    """Test runs with clean isolated state."""
    pass
```

**GOOD - Module-level constants only**:

```python
# Constants are safe (immutable)
TEST_DATA_PATH = Path(__file__).parent / "fixtures"
DEFAULT_TIMEOUT = 30

# Use fixtures for mutable state
@pytest.fixture
def test_counter():
    """Fresh counter per test."""
    return 0
```

**How to Recognize**:
- Code executing outside functions/classes
- Global variables modified at module level
- Tests fail when run in different orders
- Tests pass in isolation but fail in suite

**Fix**: Move all setup into fixtures, use module-level constants only.

### 4.4 Mutable Fixture State

**The Anti-Pattern**: Fixtures that return mutable objects shared across tests.

**BAD - Shared mutable list**:

```python
@pytest.fixture(scope="module")
def shared_list():
    """Module-scoped fixture with mutable list."""
    return []  # Same list shared across tests!

def test_append(shared_list):
    shared_list.append("item1")
    assert len(shared_list) == 1

def test_independent(shared_list):
    # Gets SAME list with "item1" already in it!
    assert len(shared_list) == 0  # FAILS!
```

**GOOD - Fresh mutable objects**:

```python
@pytest.fixture
def fresh_list():
    """Function-scoped fixture with fresh list."""
    return []  # New list per test

def test_append(fresh_list):
    fresh_list.append("item1")
    assert len(fresh_list) == 1

def test_independent(fresh_list):
    # Gets NEW fresh list
    assert len(fresh_list) == 0  # PASSES
```

**How to Recognize**:
- Fixtures with scope broader than `function` returning mutable types
- Tests modifying fixture data
- Test failures depending on execution order

**Fix**: Use function scope for mutable fixtures, or return immutable data.

---

## 5 Integration with Universal Standards

### 5.1 4-6 Test Principle in pytest

**From**: `base/development/testing.md §1.1`

**How pytest Implements**:

**Test Organization with Classes**:

```python
# One test class per feature = organized 4-6 tests
class TestBreadcrumbParsing:
    """6 focused tests for breadcrumb parsing."""

    def test_parse_valid_format(self):
        """Happy path."""
        pass

    def test_parse_invalid_format_raises_error(self):
        """Error handling."""
        pass

    def test_parse_missing_components(self):
        """Edge case."""
        pass

    def test_parse_preserves_order(self):
        """Integration point."""
        pass

    def test_parse_malformed_timestamp(self):
        """Likely failure."""
        pass

    def test_parse_unicode_components(self):
        """Real-world edge case."""
        pass
```

**Test Counting**:
- Class with 6 methods = 6 tests ✅
- One function with 6 parameter sets = 1 test ✅
- Loop with 6 iterations = 1 test (not 6) ✅

**Real Example** (from MacEff test_temporal_utils.py):

```python
class TestGetTemporalContext:
    """Test temporal context generation."""

    def test_returns_dict_with_required_keys(self):
        """Context dict has all required keys."""
        # 4 tests in this class = 4-6 principle satisfied

    def test_timestamp_formatted_has_correct_format(self):
        """Timestamp follows expected format."""
        pass

    def test_time_of_day_classification_is_reasonable(self):
        """Time of day classification valid."""
        pass

    def test_timezone_is_non_empty_string(self):
        """Timezone is populated."""
        pass
```

### 5.2 Foundation vs Integration in pytest

**From**: `base/development/testing.md §4`

**Using pytest Marks for Rigor Levels**:

```python
# Foundation tests (strict TDD, always run)
def test_parse_breadcrumb_valid_format():
    """Foundation: core utility function."""
    pass

# Integration tests (pragmatic TDD, run separately)
@pytest.mark.integration
def test_session_start_hook_workflow():
    """Integration: complete hook workflow."""
    pass

# Slow tests (skip during development)
@pytest.mark.slow
def test_performance_under_load():
    """Performance test with realistic data."""
    pass
```

**Running by Rigor Level**:

```bash
# Foundation tests only (fast, strict)
pytest -m "not integration and not slow"

# All tests including integration
pytest

# Integration tests only
pytest -m integration

# Everything including slow performance tests
pytest -m "slow or integration or not slow"
```

**Directory Organization by Rigor**:

```
tests/
├── test_utils.py           # Foundation (strict TDD)
├── test_parsing.py         # Foundation
└── integration/
    ├── test_workflows.py   # Integration (pragmatic)
    └── test_end_to_end.py  # Integration
```

### 5.3 Cross-References

**Universal Testing Philosophy**:
- `base/development/testing.md` - Language-agnostic principles
- 4-6 test principle (§1.1)
- Progressive verbosity (§3.2)
- Foundation vs integration rigor (§4)

**Related Python Policies**:
- `lang/python/workspace_python.md` - Where test files go (future)
- `lang/python/style_python.md` - Python code style (future)

**Delegation**:
- `base/delegation/delegation_guidelines.md` - TestEng specialist
- Delegation pattern for pytest test creation
- Anti-pattern warnings for subagents

**Roadmaps**:
- `base/consciousness/roadmaps_following.md` - Phase completion criteria
- Test results documentation in roadmaps
- §3.4 integration pattern (this guide)

---

## 6 Examples and Patterns

### 6.1 Well-Designed pytest Test Suite

**Foundation Layer Example** (6 focused tests):

```python
"""Test breadcrumb parsing (foundation utility)."""
import pytest
from mypackage.utils import parse_breadcrumb, BreadcrumbError


class TestBreadcrumbParsing:
    """Foundation testing: strict TDD, comprehensive coverage."""

    def test_parse_valid_breadcrumb_returns_all_components(self):
        """Happy path: valid format works."""
        result = parse_breadcrumb("s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890")

        assert result.session == "abc12345"
        assert result.cycle == 42
        assert result.git == "def6789"
        assert result.prompt == "ghi01234"
        assert result.timestamp == 1234567890

    def test_parse_invalid_format_raises_error(self):
        """Error handling: malformed input rejected."""
        with pytest.raises(BreadcrumbError, match="Invalid format"):
            parse_breadcrumb("invalid_breadcrumb_format")

    def test_parse_missing_components_returns_partial(self):
        """Edge case: abbreviated breadcrumbs."""
        result = parse_breadcrumb("s_abc12345/c_42/t_1234567890")

        assert result.session == "abc12345"
        assert result.cycle == 42
        assert result.git is None
        assert result.prompt is None
        assert result.timestamp == 1234567890

    def test_parse_preserves_component_order(self):
        """Integration: component ordering matters."""
        result = parse_breadcrumb("s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890")
        components = result.to_list()

        assert components == ["abc12345", 42, "def6789", "ghi01234", 1234567890]

    def test_parse_malformed_timestamp_raises_error(self):
        """Edge case: invalid timestamp format."""
        with pytest.raises(BreadcrumbError, match="timestamp"):
            parse_breadcrumb("s_abc12345/c_42/g_def6789/p_ghi01234/t_invalid")

    def test_parse_validates_ascii_only_components(self):
        """Reality check: ensure ASCII-only validation."""
        with pytest.raises(BreadcrumbError, match="ASCII"):
            parse_breadcrumb("s_abc™2345/c_42/g_def6789/p_ghi01234/t_1234567890")
```

**Integration Layer Example** (4 focused tests):

```python
"""Test SessionStart hook integration."""
import pytest
from macf.hooks.handle_session_start import run


@pytest.mark.integration
class TestSessionStartHook:
    """Integration testing: pragmatic TDD, builds on foundation."""

    def test_hook_generates_valid_breadcrumb(self, mock_session_input):
        """Happy path: hook produces valid breadcrumb."""
        output = run(mock_session_input, testing=True)

        assert output["breadcrumb"] is not None
        assert "s_" in output["breadcrumb"]
        assert "c_" in output["breadcrumb"]

    def test_hook_detects_compaction(self, mock_compaction_input):
        """Integration: compaction detection workflow."""
        output = run(mock_compaction_input, testing=True)

        assert output["compaction_detected"] is True
        assert "ULTRATHINK" in output["additionalContext"]

    def test_hook_includes_artifact_paths_when_found(self, mock_session_with_artifacts):
        """Integration: artifact discovery workflow."""
        output = run(mock_session_with_artifacts, testing=True)

        assert "latest_checkpoint" in output["additionalContext"]
        assert "latest_reflection" in output["additionalContext"]

    def test_hook_graceful_when_artifacts_missing(self, mock_session_no_artifacts):
        """Edge case: no artifacts available."""
        output = run(mock_session_no_artifacts, testing=True)

        assert "Not found" in output["additionalContext"]
        # Hook succeeds despite missing artifacts
```

### 6.2 Common pytest Mistakes

**Mistake 1: Testing Implementation Details**:

```python
# BAD - Coupled to implementation
def test_parser_uses_regex_pattern():
    """Tests internal implementation."""
    parser = BreadcrumbParser()
    assert parser._regex_pattern == "^s_[a-f0-9]{8}.*"
    # Breaks when refactoring to different parsing approach

# GOOD - Tests behavior
def test_parser_accepts_valid_format():
    """Tests observable behavior."""
    result = parse_breadcrumb("s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890")
    assert result.is_valid is True
    # Works regardless of parsing implementation
```

**Mistake 2: Unclear Test Names**:

```python
# BAD - Meaningless names
def test_case_1():
    pass

def test_edge_case():
    pass

def test_function_works():
    pass

# GOOD - Self-documenting names
def test_parse_valid_breadcrumb_returns_components():
    pass

def test_parse_missing_session_raises_error():
    pass

def test_parse_preserves_component_order():
    pass
```

**Mistake 3: No Error Testing**:

```python
# BAD - Only happy path
def test_feature():
    result = do_feature(valid_input)
    assert result == expected

# GOOD - Tests success and failure
def test_feature_succeeds_with_valid_input():
    result = do_feature(valid_input)
    assert result == expected

def test_feature_raises_error_with_invalid_input():
    with pytest.raises(ValueError):
        do_feature(invalid_input)

def test_feature_handles_missing_data_gracefully():
    result = do_feature(None)
    assert result is None  # Graceful degradation
```

---

## 7 Quick Reference

### 7.1 Essential pytest Commands

```bash
# Progressive verbosity (token-efficient)
pytest --tb=no -q              # Level 0: Summary (100-500 tokens)
pytest --tb=short              # Level 1: Failures (1k-2k tokens)
pytest -v --tb=long            # Level 2: Diagnostic (5k+ tokens)

# Running specific tests
pytest tests/test_module.py                    # Specific file
pytest tests/test_module.py::test_function     # Specific function
pytest -k "parse"                              # Pattern matching

# Filtering by marks
pytest -m integration                          # Only integration
pytest -m "not slow"                           # Exclude slow tests

# Coverage
pytest --cov=mypackage --cov-report=term-missing  # Terminal
pytest --cov=mypackage --cov-report=html          # HTML report

# Useful flags
pytest -x                      # Stop on first failure
pytest --lf                    # Rerun last failed
pytest --durations=3           # Show 3 slowest tests
```

### 7.2 Common Fixture Patterns

```python
# Basic fixture
@pytest.fixture
def sample_data():
    return {"key": "value"}

# Setup/teardown
@pytest.fixture
def resource():
    res = acquire()
    yield res
    res.release()

# Parametrization
@pytest.mark.parametrize("input,expected", [
    (val1, exp1),
    (val2, exp2)
])
def test_feature(input, expected):
    assert process(input) == expected

# Scopes
@pytest.fixture(scope="function")  # Default, safest
@pytest.fixture(scope="module")    # Per test file
@pytest.fixture(scope="session")   # Entire test run
```

### 7.3 Phase Completion Checklist

```markdown
## Phase Completion

- [ ] Implementation complete
- [ ] Test suite passing: `pytest --tb=no -q`
- [ ] Coverage acceptable: `pytest --cov=mypackage --cov-report=term-missing`
- [ ] Results documented in roadmap
- [ ] Changes committed

**Test Output**:
```bash
pytest --tb=no -q
................................. [19 passed in 0.03s]
```

**Coverage**:
```bash
pytest --cov=macf --cov-report=term-missing
Coverage: 95% (147/150 lines)
```
```

---

## 8 Anti-Patterns Summary

**Python/pytest-Specific Anti-Patterns**:

1. **Fixture Scope Creep**:
   - ❌ Session-scoped mutable fixtures
   - ✅ Function-scoped or immutable data

2. **Parametrization Explosion**:
   - ❌ Cartesian products creating 10,000 test runs
   - ✅ 4-6 representative parameter sets

3. **Import-Time Side Effects**:
   - ❌ Code executing during module import
   - ✅ All setup in fixtures

4. **Mutable Fixture State**:
   - ❌ Shared mutable objects across tests
   - ✅ Fresh fixtures per test

**Universal Anti-Patterns** (apply to all languages):
- Test suite bloat (see `testing.md §5.1`)
- Loop iterations counted as tests (see `testing.md §5.2`)
- Exhaustive permutations (see `testing.md §5.3`)

---

## 9 Evolution & Feedback

This guide evolves through:
- **pytest ecosystem changes**: New fixtures, plugins, best practices
- **Real-world effectiveness**: Do patterns work in practice?
- **Community feedback**: What helps vs hinders pytest users?
- **Integration discoveries**: Better ways to implement universal principles

**Principle**: pytest-specific patterns should enable universal testing philosophy, not override it. If pytest patterns conflict with 4-6 principle or progressive verbosity → refine the patterns.

**Feedback Channels**:
- Report pytest-specific anti-patterns encountered
- Suggest better fixture patterns
- Document pytest plugin integrations
- Share pytest performance optimizations

---

**Policy Established**: Python testing guide implements MacEff's universal testing standards using pytest tools, fixtures, parametrization, and CLI flags. Provides concrete Python code examples while referencing `base/development/testing.md` for philosophy.

**Core Wisdom**: "pytest implements universal principles. 4-6 tests via parametrization discipline. Progressive verbosity via --tb flags. Foundation rigor via marks. Test reality using Python."

**Remember**: This guide shows HOW to apply universal testing philosophy in Python. For WHY these principles matter, see `base/development/testing.md`. Together they enable pragmatic quality assurance for all Python projects in MacEff framework.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
