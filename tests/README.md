# NC Budget Project - Test Suite

## Overview

This test suite provides comprehensive coverage for the NC Budget Agent project, including unit tests, integration tests, and CI/CD automation.

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── test_agent.py            # MCP protocol and agent handler tests
├── test_query_planner.py    # SQL generation and sanitization tests
├── test_tools.py            # Tool handler tests
└── integration/             # Integration tests (optional)
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements.txt
```

### Run All Tests

From project root:
```bash
cd tests && pytest
```

Or from tests directory:
```bash
pytest
```

### Run with Coverage Report

From tests directory:
```bash
pytest  # Coverage is enabled by default
```

Then open `tests/htmlcov/index.html` in your browser to see detailed coverage.

**Note:** All test configuration and generated files (pytest.ini, .coverage, htmlcov/) are in the `tests/` folder to keep the project root clean.

### Run Specific Test Files

```bash
# Test only the agent
pytest test_agent.py -v

# Test only query planner
pytest test_query_planner.py -v

# Test only tool handlers
pytest test_tools.py -v
```

### Run Tests by Category

```bash
# Run only fast unit tests
pytest -m unit

# Skip slow tests (like RAG model loading)
pytest -m "not slow"

# Run only integration tests
pytest -m integration
```

## Test Categories

- **Unit Tests**: Fast, isolated tests with mocked dependencies
- **Integration Tests**: Tests that use real databases (slower)
- **Slow Tests**: Tests involving model loading or heavy operations

## Coverage Goals

- **Current Target**: 50% minimum coverage (enforced in pytest.ini)
- **Recommended Goal**: 70%+ for critical paths
- **Critical Areas**:
  - MCP protocol handlers (test_agent.py)
  - SQL generation and sanitization (test_query_planner.py)
  - Tool handlers (test_tools.py)

## CI/CD

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

GitHub Actions workflow: `.github/workflows/test.yml`

## Pre-Railway Deployment Checklist

Before deploying to Railway, ensure:

1. ✅ All tests pass: `pytest`
2. ✅ Coverage meets minimum: `pytest --cov=chat`
3. ✅ No security issues: Check SQL injection tests pass
4. ✅ CI is green: Check GitHub Actions status

## Writing New Tests

### Example Unit Test

```python
def test_my_function():
    """Test description."""
    result = my_function("input")
    assert result == "expected_output"
```

### Example Test with Mock

```python
from unittest.mock import Mock, patch

@patch('chat.module.external_api')
def test_with_mock(mock_api):
    mock_api.return_value = {"data": "test"}
    result = function_that_calls_api()
    assert result is not None
```

### Using Fixtures

```python
def test_with_fixture(mock_llm_client, sample_data):
    """Fixtures from conftest.py are automatically available."""
    result = process_data(sample_data, mock_llm_client)
    assert len(result) > 0
```

## Troubleshooting

### Tests Failing Locally

1. Check environment variables are set:
   ```bash
   export GROQ_KEY=your-key
   export ANTHROPIC_API_KEY=your-key
   ```

2. Ensure databases exist:
   ```bash
   ls db/*.db
   ```

3. Clear pytest cache:
   ```bash
   pytest --cache-clear
   ```

### Import Errors

If you get import errors, ensure project root is in PYTHONPATH:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest
```

## Mocking Strategy

- **LLM Clients**: Always mocked in unit tests to avoid API costs
- **Databases**: Mocked in unit tests, real in integration tests
- **File I/O**: Mocked unless testing actual file operations
- **External APIs**: Always mocked

## Performance

- **Unit tests**: Should run in < 1 second each
- **Integration tests**: May take several seconds
- **Full suite**: Should complete in < 30 seconds (excluding slow tests)

## Contributing

When adding new features:
1. Write tests first (TDD approach)
2. Ensure coverage doesn't decrease
3. Add integration tests for new tools
4. Update this README if test structure changes
