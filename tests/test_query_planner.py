"""
Tests for query_planner.py - SQL generation and validation.
"""
import pytest
from unittest.mock import Mock
from chat.agent_functions.sql.query_planner import (
    plan_query,
    generate_sql_with_llm,
    select_tool,
    explain_query_results
)
from chat.agent_functions.validators.sql_validator import sql_validator
from chat.agent_functions.validators.answer_validator import validate_query_results


class TestValidateSQLQuery:
    """Test SQL validation and blocking."""

    def test_validate_valid_select(self):
        """Test that valid SELECT query passes."""
        sql = "SELECT * FROM vendor_payments WHERE fiscal_year = '2023' LIMIT 10"
        is_safe, warnings = sql_validator(sql)
        assert is_safe is True
        assert len(warnings) == 0

    def test_validate_blocks_drop(self):
        """Test that DROP statements are blocked."""
        is_safe, warnings = sql_validator("DROP TABLE vendor_payments")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("DROP" in w for w in warnings)

    def test_validate_blocks_delete(self):
        """Test that DELETE statements are blocked."""
        is_safe, warnings = sql_validator("DELETE FROM vendor_payments WHERE id = 1")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("DELETE" in w for w in warnings)

    def test_validate_blocks_update(self):
        """Test that UPDATE statements are blocked."""
        is_safe, warnings = sql_validator("UPDATE vendor_payments SET payment = '0'")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("UPDATE" in w for w in warnings)

    def test_validate_blocks_insert(self):
        """Test that INSERT statements are blocked."""
        is_safe, warnings = sql_validator("INSERT INTO vendor_payments VALUES (1, 'test')")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("INSERT" in w for w in warnings)

    def test_validate_blocks_multiple_statements(self):
        """Test that multiple statements are blocked."""
        is_safe, warnings = sql_validator("SELECT * FROM vendor_payments; SELECT * FROM budget;")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("Multiple SQL statements" in w for w in warnings)

    def test_validate_allows_trailing_semicolon(self):
        """Test that trailing semicolon is allowed."""
        sql = "SELECT * FROM vendor_payments;"
        is_safe, warnings = sql_validator(sql)
        assert is_safe is True
        # Should not block for trailing semicolon
        assert not any("Multiple SQL statements" in w for w in warnings)

    def test_validate_case_insensitive(self):
        """Test that validation is case-insensitive."""
        is_safe, warnings = sql_validator("drop table users")
        assert is_safe is False
        assert len(warnings) > 0
        assert any("DROP" in w for w in warnings)


class TestSelectTool:
    """Test tool selection based on SQL."""

    def test_select_tool_vendor_payments(self):
        """Test that vendor_payments table selects correct tool."""
        sql = "SELECT * FROM vendor_payments WHERE fiscal_year = '2023'"
        tool = select_tool(sql)
        assert tool == "query_vendor_payments"

    def test_select_tool_budget(self):
        """Test that budget table selects correct tool."""
        sql = "SELECT * FROM budget WHERE committee = 'Education'"
        tool = select_tool(sql)
        assert tool == "query_budget"

    def test_select_tool_case_insensitive(self):
        """Test that tool selection is case-insensitive."""
        sql = "SELECT * FROM VENDOR_PAYMENTS"
        tool = select_tool(sql)
        assert tool == "query_vendor_payments"

    def test_select_tool_default(self):
        """Test that unknown table defaults to vendor_payments."""
        sql = "SELECT * FROM unknown_table"
        tool = select_tool(sql)
        assert tool == "query_vendor_payments"


class TestGenerateSQLWithLLM:
    """Test LLM-based SQL generation."""

    def test_generate_sql_basic(self, mock_llm_client):
        """Test basic SQL generation."""
        mock_llm_client.invoke.return_value.content = "SELECT * FROM vendor_payments LIMIT 10"

        sql = generate_sql_with_llm("show me vendor payments", mock_llm_client)

        assert sql == "SELECT * FROM vendor_payments LIMIT 10"
        mock_llm_client.invoke.assert_called_once()

    def test_generate_sql_strips_markdown(self, mock_llm_client):
        """Test that markdown code blocks are removed."""
        mock_llm_client.invoke.return_value.content = "```sql\nSELECT * FROM vendor_payments\n```"

        sql = generate_sql_with_llm("show vendors", mock_llm_client)

        assert sql == "SELECT * FROM vendor_payments"
        assert "```" not in sql

    def test_generate_sql_strips_backticks(self, mock_llm_client):
        """Test that backticks in code blocks are removed."""
        mock_llm_client.invoke.return_value.content = "```\nSELECT * FROM vendor_payments\n```"

        sql = generate_sql_with_llm("show vendors", mock_llm_client)

        assert sql == "SELECT * FROM vendor_payments"
        assert "```" not in sql

    def test_generate_sql_prompt_includes_user_query(self, mock_llm_client):
        """Test that user query is included in prompt."""
        mock_llm_client.invoke.return_value.content = "SELECT * FROM vendor_payments"

        user_query = "show transportation spending in 2023"
        generate_sql_with_llm(user_query, mock_llm_client)

        # Check that the prompt passed to LLM contains the user query
        call_args = mock_llm_client.invoke.call_args[0][0]
        assert user_query in call_args


class TestPlanQuery:
    """Test complete query planning pipeline."""

    def test_plan_query_success(self, mock_llm_client):
        """Test successful query planning."""
        mock_llm_client.invoke.return_value.content = "SELECT * FROM vendor_payments LIMIT 5"

        result = plan_query("show me vendor payments", mock_llm_client)

        assert result["tool"] == "query_vendor_payments"
        assert result["sql"] == "SELECT * FROM vendor_payments LIMIT 5"
        assert result["arguments"]["query"] == "SELECT * FROM vendor_payments LIMIT 5"

    def test_plan_query_selects_correct_tool(self, mock_llm_client):
        """Test that plan_query selects tool based on table."""
        mock_llm_client.invoke.return_value.content = "SELECT * FROM budget WHERE fiscal_year = '2023'"

        result = plan_query("show budget data", mock_llm_client)

        assert result["tool"] == "query_budget"


class TestValidateQueryResults:
    """Test query result validation."""

    def test_validate_results_empty(self):
        """Test that empty results return no warnings."""
        warnings = validate_query_results([], "SELECT * FROM vendor_payments")
        assert len(warnings) == 0

    def test_validate_results_valid_data(self):
        """Test that valid data returns no warnings."""
        results = [
            {"fiscal_year": "2023", "payment": "$1,234.56"},
            {"fiscal_year": "2024", "payment": "$5,678.90"}
        ]
        warnings = validate_query_results(results, "SELECT * FROM vendor_payments")
        assert len(warnings) == 0

    def test_validate_results_negative_payment(self):
        """Test that negative monetary values generate warning."""
        results = [
            {"fiscal_year": "2023", "payment": -1234.56}
        ]
        warnings = validate_query_results(results, "SELECT * FROM vendor_payments")
        assert len(warnings) > 0
        assert any("Negative monetary value" in w for w in warnings)

    def test_validate_results_invalid_fiscal_year(self):
        """Test that invalid fiscal years generate warning."""
        results = [
            {"fiscal_year": "1999", "payment": "$1,234.56"}
        ]
        warnings = validate_query_results(results, "SELECT * FROM vendor_payments")
        assert len(warnings) > 0
        assert any("fiscal year" in w.lower() for w in warnings)

    def test_validate_results_large_result_set(self):
        """Test that large result sets generate warning."""
        # Create 10001 dummy results
        results = [{"id": i} for i in range(10001)]
        warnings = validate_query_results(results, "SELECT * FROM vendor_payments")
        assert len(warnings) > 0
        assert any("Large result set" in w for w in warnings)

    def test_validate_results_negative_expenditures(self):
        """Test that negative expenditures generate warning."""
        results = [
            {"fiscal_year": "2023", "expenditures": -50000}
        ]
        warnings = validate_query_results(results, "SELECT * FROM budget")
        assert len(warnings) > 0
        assert any("Negative monetary value" in w for w in warnings)


class TestExplainQueryResults:
    """Test result explanation generation."""

    def test_explain_query_results_with_data(self):
        """Test explanation when results are found."""
        results = [{"id": 1}, {"id": 2}, {"id": 3}]
        explanation = explain_query_results(
            "show vendors",
            "SELECT * FROM vendor_payments LIMIT 3",
            results,
            "query_vendor_payments"
        )

        assert "3 results" in explanation

    def test_explain_query_results_single_result(self):
        """Test explanation with single result."""
        results = [{"id": 1}]
        explanation = explain_query_results(
            "show vendor",
            "SELECT * FROM vendor_payments LIMIT 1",
            results,
            "query_vendor_payments"
        )

        assert "1 result" in explanation
        assert "results" not in explanation  # Should be singular

    def test_explain_query_results_empty(self):
        """Test explanation when no results found."""
        explanation = explain_query_results(
            "show something",
            "SELECT * FROM vendor_payments WHERE vendor = 'NonExistent'",
            [],
            "query_vendor_payments"
        )

        assert "No" in explanation or "found" in explanation

    def test_explain_query_results_with_fiscal_year_filter(self):
        """Test explanation mentions fiscal year when filter is present."""
        explanation = explain_query_results(
            "show data for 2099",
            "SELECT * FROM vendor_payments WHERE fiscal_year = '2099'",
            [],
            "query_vendor_payments"
        )

        assert "fiscal year" in explanation.lower() or "year" in explanation.lower()

    def test_explain_query_results_with_like_filter(self):
        """Test explanation when LIKE filter is present."""
        explanation = explain_query_results(
            "show payments to XYZ Corp",
            "SELECT * FROM vendor_payments WHERE vendor LIKE '%XYZ%'",
            [],
            "query_vendor_payments"
        )

        assert any(word in explanation.lower() for word in ["match", "name", "keyword", "spelling"])
