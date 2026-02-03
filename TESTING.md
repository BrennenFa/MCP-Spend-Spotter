# Testing Guide - NC Budget Project

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests (from project root)
cd tests && pytest

# Run with coverage (coverage is enabled by default)
cd tests && pytest

# View coverage report
open tests/htmlcov/index.html
```

**Note:** All test files and configuration are in the `tests/` directory to keep the project root clean.

## Current Status

✅ **50 passing tests** (3 skipped integration tests)
✅ **22% code coverage** (meets 20% minimum threshold)
✅ **CI/CD ready** with GitHub Actions

## Test Coverage by Module

| Module | Coverage | Status |
|--------|----------|--------|
| query_planner.py | 89% | ✅ Excellent |
| nc_budget_agent.py | 65% | ✅ Good |
| handlers.py | 52% | ⚠️ Decent |
| implementations.py | 35% | ⚠️ Needs work |
| graph_generator.py | 11% | ❌ Low |
| RAG modules | 0-20% | ❌ Low |

## What's Tested

### ✅ Fully Tested (80%+ coverage)
- **SQL Query Planner** (`test_query_planner.py`)
  - SQL sanitization & security (prevents DROP, DELETE, injection)
  - Tool selection based on table names
  - LLM-based SQL generation
  - Query explanation generation

### ✅ Well Tested (50%+ coverage)
- **NC Budget Agent** (`test_agent.py`)
  - MCP protocol handlers (tools/list, tools/call)
  - Natural language query processing
  - RAG query handling
  - Two-tier tool dispatch system
  - Error handling

### ✅ Partially Tested (30%+ coverage)
- **Tool Handlers** (`test_tools.py`)
  - Vendor payments queries
  - Budget queries
  - Database schema retrieval
  - Error handling

## Pre-Railway Deployment Checklist

Before deploying to Railway:

- [x] Tests pass: `pytest`
- [x] Coverage meets minimum: `pytest --cov=chat`
- [x] Security tests pass (SQL injection prevention)
- [x] MCP protocol works correctly
- [ ] GitHub Actions CI is green (push to trigger)
- [ ] Environment variables configured in Railway

## Running Tests Before Deployment

```bash
# Full pre-deploy test suite (from project root)
cd tests && pytest

# Or from tests directory
pytest

# If all tests pass, you're ready to deploy!
```

## GitHub Actions CI

Tests run automatically on:
- Push to `main` or `develop`
- Pull requests

Workflow: `.github/workflows/test.yml`

## Test Categories

```bash
# Run only unit tests (fast)
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

## Improving Coverage

To increase coverage to 50%+, focus on:

1. **Graph Generator** (currently 11%)
   - Add tests for graph creation
   - Test different chart types
   - Mock matplotlib

2. **RAG System** (currently 0-20%)
   - Mock embedding models
   - Test retrieval logic
   - Test reranking

3. **Tool Implementations** (currently 35%)
   - Add tests for summary functions
   - Test agency spending calculations

## Known Limitations

- RAG model loading is skipped in tests (mocked)
- Some integration tests are marked as skipped (require real DB)
- Coverage threshold set to 20% (increase gradually to 50%+)

## For Interviewers

This test suite demonstrates:
- ✅ Modern testing practices (pytest, fixtures, mocks)
- ✅ Security testing (SQL injection prevention)
- ✅ CI/CD automation (GitHub Actions)
- ✅ Code coverage tracking
- ✅ Pre-deployment validation
- ✅ Production-ready error handling

**Next Steps**: Increase coverage to 70%+ and add performance benchmarks.
