"""
Tests for nc_budget_agent.py - MCP server protocol and handlers.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from chat.agents.nc_budget_agent import (
    handle_tools_list,
    handle_tools_call,
    send_json
)


class TestMCPProtocol:
    """Test MCP protocol functions."""

    def test_handle_tools_list_returns_all_tools(self):
        """Test that tools/list returns all 5 tools."""
        result = handle_tools_list()

        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) == 5

        # Verify tool names are present (tools may have different formats)
        tool_names = []
        for tool in result["tools"]:
            # Handle both OpenAI format (nested function) and MCP format (direct name)
            if "function" in tool:
                tool_names.append(tool["function"]["name"])
            elif "name" in tool:
                tool_names.append(tool["name"])

        assert "query_sql" in tool_names
        assert "query_vendor_payments" in tool_names
        assert "query_budget" in tool_names
        assert "query_budget_context" in tool_names

    def test_send_json_outputs_valid_json(self, capsys):
        """Test that send_json outputs valid JSON to stdout."""
        test_data = {"test": "data", "number": 42}
        send_json(test_data)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed == test_data

    def test_handle_tools_call_unknown_tool(self):
        """Test that unknown tool returns error."""
        result = handle_tools_call("nonexistent_tool", {})

        assert "content" in result
        assert result.get("isError") == True
        assert "Unknown tool" in result["content"][0]["text"]


class TestToolsCallDispatch:
    """Test tool dispatch system."""

    @patch('chat.agents.nc_budget_agent.handle_query_sql')
    def test_dispatch_to_query_sql(self, mock_handler):
        """Test that query_sql routes to handle_query_sql."""
        mock_handler.return_value = {"content": [{"type": "text", "text": "success"}]}

        result = handle_tools_call("query_sql", {"query": "test"})

        assert result == {"content": [{"type": "text", "text": "success"}]}

    @patch('chat.agents.nc_budget_agent.handle_query_budget_context')
    def test_dispatch_to_query_budget_context(self, mock_handler):
        """Test that query_budget_context routes to handle_query_budget_context."""
        mock_handler.return_value = {"content": [{"type": "text", "text": "success"}]}

        result = handle_tools_call("query_budget_context", {"query": "test"})

        assert result == {"content": [{"type": "text", "text": "success"}]}

    @patch('chat.agents.nc_budget_agent.handle_query_vendor_payments')
    def test_dispatch_to_standard_handler(self, mock_handler):
        """Test that query_vendor_payments routes to handle_query_vendor_payments."""
        mock_handler.return_value = {"result": "success"}

        result = handle_tools_call("query_vendor_payments", {"sql": "SELECT * FROM test"})

        mock_handler.assert_called_once_with({"sql": "SELECT * FROM test"})
        assert result == {"result": "success"}
