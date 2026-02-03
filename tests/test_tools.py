"""
Tests for tool handlers - SQL queries, summaries, and utility functions.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from chat.tools.handlers import (
    handle_query_vendor_payments,
    handle_query_budget
)


class TestQueryVendorPayments:
    """Test vendor payments query handler."""

    @patch('chat.tools.handlers.execute_vendor_query')
    def test_handle_query_vendor_payments_success(self, mock_execute):
        """Test successful vendor payments query."""
        # Mock data
        mock_execute.return_value = [
            {'vendor': 'Test Vendor', 'payment': '$1000'},
            {'vendor': 'Another Vendor', 'payment': '$2000'}
        ]

        result = handle_query_vendor_payments({
            'query': 'SELECT * FROM vendor_payments LIMIT 2'
        })

        assert 'content' in result
        assert len(result['content']) == 1
        assert result['content'][0]['type'] == 'text'

        # Should return JSON array
        import json
        data = json.loads(result['content'][0]['text'])
        assert len(data) == 2
        assert data[0]['vendor'] == 'Test Vendor'

    @patch('chat.tools.handlers.execute_vendor_query')
    def test_handle_query_vendor_payments_empty_results(self, mock_execute):
        """Test query with no results."""
        mock_execute.return_value = []

        result = handle_query_vendor_payments({
            'query': 'SELECT * FROM vendor_payments WHERE vendor = "NonExistent"'
        })

        assert 'content' in result
        import json
        data = json.loads(result['content'][0]['text'])
        assert data == []

    @patch('chat.tools.handlers.execute_vendor_query')
    def test_handle_query_vendor_payments_error(self, mock_execute):
        """Test error handling in vendor payments query."""
        mock_execute.side_effect = Exception("Database error")

        result = handle_query_vendor_payments({
            'query': 'SELECT * FROM vendor_payments'
        })

        assert 'content' in result
        assert result.get('isError') == True
        assert 'error' in result['content'][0]['text'].lower()

    def test_handle_query_vendor_payments_missing_query(self):
        """Test error when query parameter is missing."""
        result = handle_query_vendor_payments({})

        assert 'content' in result
        assert result.get('isError') == True


class TestQueryBudget:
    """Test budget query handler."""

    @patch('chat.tools.handlers.execute_budget_query')
    def test_handle_query_budget_success(self, mock_execute):
        """Test successful budget query."""
        mock_execute.return_value = [
            {'committee': 'Transportation', 'expenditures': '$1000000'},
            {'committee': 'Education', 'expenditures': '$2000000'}
        ]

        result = handle_query_budget({
            'query': 'SELECT * FROM budget LIMIT 2'
        })

        assert 'content' in result
        import json
        data = json.loads(result['content'][0]['text'])
        assert len(data) == 2
        assert data[0]['committee'] == 'Transportation'

    @patch('chat.tools.handlers.execute_budget_query')
    def test_handle_query_budget_error(self, mock_execute):
        """Test error handling in budget query."""
        mock_execute.side_effect = Exception("Database error")

        result = handle_query_budget({
            'query': 'SELECT * FROM budget'
        })

        assert 'content' in result
        assert result.get('isError') == True


class TestToolErrorHandling:
    """Test error handling across different tool handlers."""

    @patch('chat.tools.handlers.execute_vendor_query')
    def test_sql_injection_attempt(self, mock_execute):
        """Test that malicious SQL is handled safely."""
        # This should be caught by sanitization before reaching the handler,
        # but test that handler doesn't crash
        malicious_query = "SELECT * FROM vendor_payments; DROP TABLE users;"

        # Even if it reaches the handler, it should handle errors gracefully
        mock_execute.side_effect = Exception("SQL error")

        result = handle_query_vendor_payments({'query': malicious_query})

        assert 'content' in result
        # Should return error, not crash
        assert result.get('isError') == True

