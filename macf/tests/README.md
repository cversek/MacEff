# MacF Tools Test Suite

This test suite provides comprehensive testing for MacEff consciousness infrastructure. The tests follow strict Test-Driven Development (TDD) principles and provide living specifications for the consciousness framework.

## Test Architecture

### Test Categories

1. **Unit Tests** (`test_*.py`) - Test individual components in isolation
2. **Integration Tests** (`test_integration.py`) - Test complete workflows
3. **Performance Tests** (marked with `@pytest.mark.performance`) - Test scalability

### Test Files

- `test_config.py` - Configuration module tests (path resolution, TOML loading)
- `test_session.py` - Session management tests (ID extraction, temp dirs, cleanup)
- `test_commands.py` - CLI command tests (argument parsing, output format, error handling)
- `test_integration.py` - End-to-end workflow tests
- `conftest.py` - Shared fixtures and test utilities

## Running Tests

### Install Test Dependencies

```bash
pip install -e ".[test]"
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest -m "not integration and not performance"

# Integration tests
pytest -m integration

# Performance tests (slow)
pytest -m performance

# Container-specific tests
pytest -m container

# Host-specific tests
pytest -m host
```

### Coverage Reports

```bash
# Terminal coverage report
pytest --cov=macf --cov-report=term-missing

# HTML coverage report
pytest --cov=macf --cov-report=html
# Open htmlcov/index.html in browser
```

## Test Design Principles

### TDD Approach

These tests were designed **before** implementation following TDD principles:

1. **Red** - Tests written first, defining expected behavior
2. **Green** - Minimal implementation to make tests pass
3. **Refactor** - Improve code while maintaining green tests

### Test Isolation

- Each test runs in isolation with clean state
- Extensive use of mocking for external dependencies
- Temporary directories cleaned up automatically
- No shared mutable state between tests

### Comprehensive Coverage

- **Happy Path Testing** - Normal operation scenarios
- **Error Path Testing** - All error conditions and edge cases
- **Integration Testing** - Complete workflows across components
- **Performance Testing** - Scalability and resource usage
- **Environment Testing** - Container vs host vs fallback environments

## Key Test Scenarios

### Configuration Management

- Path resolution in different environments (container/host/fallback)
- TOML configuration loading with validation
- Environment variable overrides
- Error handling for corrupted/missing config

### Session Management

- Session ID extraction from JSONL files
- Temporary directory creation and cleanup
- Session lifecycle management
- Concurrent session handling

### CLI Commands

- All command variations with different options
- Argument parsing and validation
- Output formatting (JSON, plain text)
- Error messages and exit codes
- Help text accuracy

### Consciousness Workflows

- Strategic/tactical/operational checkpoint creation
- Reflection workflow with contextual information
- File naming conventions (YYYY-MM-DD_HHMMSS format)
- Metadata frontmatter generation
- Public vs private file placement
- Discovery without persistent indices

## Test Data and Fixtures

### Fixtures

- `mock_consciousness_config` - Pre-configured agent environment
- `sample_checkpoints_data` - Realistic checkpoint test data
- `mock_claude_project_structure` - Complete .claude project setup
- `mock_container_environment` - Container environment simulation
- `performance_test_data` - Large datasets for performance testing

### Test Data Files

- `fixtures/sample_config.toml` - Example configuration
- Generated test checkpoints with proper formatting
- Mock JSONL session data
- Error simulation utilities

## Quality Standards

### Coverage Requirements

- Minimum 80% code coverage (enforced by pytest)
- 100% coverage for critical paths (config, session, CLI entry points)
- Branch coverage, not just line coverage
- All public functions must have tests

### Test Quality

- Descriptive test names that document behavior
- Clear docstrings explaining test purpose
- Proper setup/teardown with fixtures
- Fast execution (< 5 seconds for unit tests)
- Deterministic results (no flaky tests)

### Error Testing

- All exception paths tested
- Permission errors handled gracefully
- Invalid input validation
- Resource exhaustion scenarios
- Recovery from corrupted data

## Implementation Status

⚠️ **Current Status: Test Specifications Complete**

These tests define the expected behavior for consciousness infrastructure. They serve as:

1. **Living Requirements** - Executable specifications for desired behavior
2. **Implementation Guide** - Clear contracts for what needs to be built
3. **Quality Gates** - Ensure implementation meets requirements
4. **Regression Prevention** - Catch breaking changes early

### Next Steps for DevOpsEng

1. Implement the missing modules to make tests pass:
   - `macf/config.py` - Configuration management
   - `macf/session.py` - Session management utilities
   - Enhanced CLI commands in `macf/cli.py`

2. Run tests and fix implementation until all pass

3. Use test feedback to refine implementation

4. Maintain test coverage as new features are added

## Test Utilities

### Assertion Helpers

- `validate_checkpoint_format()` - Verify checkpoint file structure
- `assert_valid_session_id()` - Validate session ID format
- `create_test_checkpoint_file()` - Generate test checkpoint files

### Mock Utilities

- `MockConsciousnessConfig` - Configurable consciousness config
- `ErrorSimulator` - Simulate various error conditions
- Environment detection mocking
- Filesystem operation mocking

## Performance Considerations

### Performance Test Guidelines

- Mark slow tests with `@pytest.mark.performance`
- Use realistic data sizes (1000+ checkpoints)
- Test memory usage stability
- Measure execution times
- Test concurrent operations

### Optimization Targets

- Checkpoint discovery: < 2 seconds for 1000+ files
- Session cleanup: < 5 seconds for 100+ old sessions
- Memory usage: < 50MB growth during extended operations
- CLI startup: < 100ms for basic commands

## Contributing to Tests

When adding new functionality:

1. **Write tests first** following TDD principles
2. **Test error conditions** not just happy paths
3. **Add appropriate fixtures** for test data
4. **Update this README** if test structure changes
5. **Maintain coverage** above 80% threshold

### Test Naming Conventions

- `test_function_name_scenario()` - Descriptive scenario testing
- `test_error_handling_specific_error()` - Error condition testing
- `test_integration_complete_workflow()` - Integration scenarios
- `test_performance_operation_under_load()` - Performance scenarios