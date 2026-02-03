"""
Pytest configuration and fixtures for NC Budget project tests.
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_llm_client():
    """Mock ChatGroq LLM client for query planning."""
    mock_llm = Mock()
    mock_response = Mock()
    mock_response.content = '{"tool": "query_vendor_payments", "sql": "SELECT * FROM vendor_payments LIMIT 10", "arguments": {"sql": "SELECT * FROM vendor_payments LIMIT 10"}}'
    mock_llm.invoke.return_value = mock_response
    return mock_llm


@pytest.fixture
def sample_vendor_payment_data():
    """Sample vendor payment records for testing."""
    return [
        {
            'fiscal_year': '2023',
            'payment': '$1,234.56',
            'vendor_recipient': 'Test Vendor Inc',
            'account_description': 'Office Supplies',
            'agency_description': 'Department of Transportation'
        },
        {
            'fiscal_year': '2023',
            'payment': '$5,678.90',
            'vendor_recipient': 'Another Vendor LLC',
            'account_description': 'Consulting Services',
            'agency_description': 'Department of Transportation'
        }
    ]


@pytest.fixture
def sample_budget_data():
    """Sample budget records for testing."""
    return [
        {
            'committee': 'Transportation',
            'agency': 'Department of Transportation',
            'account_group': 'Operations',
            'expenditures': '$1000000',
            'receipts': '$50000',
            'fiscal_year': '2023'
        }
    ]


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv('GROQ_KEY', 'test-groq-key-123')
    monkeypatch.setenv('MODEL_NAME', 'llama-3.1-8b-instant')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-anthropic-key-123')
