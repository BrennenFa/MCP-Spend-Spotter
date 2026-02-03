"""SQL Query Planner - LLM-based SQL generation from natural language."""

import os
import sys
import logging
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from chat.tools import execute_vendor_query, execute_budget_query
from chat.agent_functions.sql.validator import validate_sql_query

logger = logging.getLogger(__name__)


def plan_query(user_query: str, llm_client: ChatGroq) -> Dict[str, Any]:
    """
    Generate SQL from user query using LLM.

    Args:
        user_query: Natural language query from user
        llm_client: ChatGroq client for SQL generation

    Returns:
        {
            "tool": "query_vendor_payments" | "query_budget",
            "sql": "SELECT ...",  # LLM-generated SQL
            "arguments": {"query": "SELECT ..."},
            "warnings": ["warning1", "warning2", ...]  # Validation warnings
        }
    """
    try:
        # Generate SQL using LLM with full database context
        sql = generate_sql_with_llm(user_query, llm_client)
        logger.info(f"[SQL_PLANNER] Generated SQL: {sql}")

        # Validate SQL (warnings only, non-blocking)
        warnings = validate_sql_query(sql)
        for warning in warnings:
            logger.warning(warning)
            print(warning, file=sys.stderr)

        # Determine which tool to use based on table
        tool = select_tool(sql)
        logger.info(f"[SQL_PLANNER] Selected tool: {tool}")

        return {
            "tool": tool,
            "sql": sql,
            "arguments": {"query": sql},
            "warnings": warnings  # Include warnings in response
        }

    except Exception as e:
        logger.error(f"[SQL_PLANNER] Error planning query: {e}")
        raise


def generate_sql_with_llm(user_query: str, llm_client: ChatGroq) -> str:
    """
    Use LLM to generate SQL with complete database context.

    Prompt includes:
    - Database schema (tables, columns, types)
    - Currency conversion requirements
    - Example queries
    - User's question

    Args:
        user_query: Natural language query
        llm_client: ChatGroq client for SQL generation

    Returns:
        SQL query string
    """
    prompt = f"""You are a SQL expert for North Carolina government data.

DATABASE SCHEMA:

vendor_payments table:
- fiscal_year (TEXT): "2026"
- payment (TEXT): "$1,234.56" - CRITICAL: Always use CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL) for math
- vendor_recipient (TEXT): Vendor name
- agency_description (TEXT): Agency name
- account_description (TEXT): What the payment was for
- major_category (TEXT): Spending category
- budget_fund (TEXT): Fund type
- budget_code (TEXT): Budget code

budget table:
- fiscal_year (TEXT): "2025"
- committee (TEXT)
- agency (TEXT)
- expenditures (TEXT): "$1,234.56" - CRITICAL: Always use CAST(REPLACE(REPLACE(expenditures, '$', ''), ',', '') AS REAL) for math
- receipts (TEXT): "$1,234.56" - CRITICAL: Always use CAST(REPLACE(REPLACE(receipts, '$', ''), ',', '') AS REAL) for math
- net_appropriations (TEXT): "$1,234.56" - CRITICAL: Always use CAST(REPLACE(REPLACE(net_appropriations, '$', ''), ',', '') AS REAL) for math
- budget_type (TEXT)
- fund_type (TEXT)
- account_group (TEXT)

CRITICAL RULES:
1. Currency columns are TEXT with $ and commas. Always use: CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL)
2. Column names are lowercase with underscores
3. Use LIKE '%name%' for partial text matching (case-insensitive matching)
4. Only generate SELECT queries (no INSERT, UPDATE, DELETE, DROP, ALTER)
5. For "How many..." questions, use COUNT
6. For "What's the total..." or "sum of..." questions, use SUM
7. For "What's the maximum..." or "largest..." questions, use MAX
8. For "What's the minimum..." or "smallest..." questions, use MIN
9. Respect user-specified limits: "top 5" = LIMIT 5, "top 10" = LIMIT 10

CRITICAL RULES ABOUT WHERE CLAUSES:
1. ONLY add WHERE clauses for filters the user EXPLICITLY mentions
2. If user doesn't mention a fiscal year, DO NOT add fiscal_year filter
3. If user doesn't mention a specific vendor/agency, DO NOT add vendor/agency filter
4. All data is from North Carolina - NEVER filter by state, region, or "North Carolina"
5. When in doubt, use FEWER filters rather than more
6. Better to return too much data than to return 0 rows due to overly restrictive filters

EXAMPLES - Pay attention to when NOT to add WHERE clauses:

User: "How many total payments were made?"
SQL: SELECT COUNT(*) FROM vendor_payments
(NOTE: No fiscal_year filter - user didn't ask for a specific year!)

User: "Which vendor received the single largest payment?"
SQL: SELECT vendor_recipient, CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL) as amount FROM vendor_payments ORDER BY amount DESC LIMIT 1
(NOTE: No fiscal_year filter - user wants THE largest, not largest in a specific year!)

User: "Top 5 vendors by total payments"
SQL: SELECT vendor_recipient, SUM(CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL)) as total FROM vendor_payments GROUP BY vendor_recipient ORDER BY total DESC LIMIT 5
(NOTE: No filters - user wants overall top vendors!)

User: "How many vendors were paid in 2026?"
SQL: SELECT COUNT(DISTINCT vendor_recipient) FROM vendor_payments WHERE fiscal_year = '2026'
(NOTE: NOW we add fiscal_year because user explicitly mentioned "in 2026")

User: "Total payments to Duke Energy"
SQL: SELECT SUM(CAST(REPLACE(REPLACE(payment, '$', ''), ',', '') AS REAL)) as total FROM vendor_payments WHERE vendor_recipient LIKE '%Duke Energy%'
(NOTE: We add vendor filter because user explicitly mentioned "to Duke Energy")

User: "Show payments to Transportation department in 2026"
SQL: SELECT * FROM vendor_payments WHERE agency_description LIKE '%Transportation%' AND fiscal_year = '2026'
(NOTE: Use short keyword 'Transportation' not full name, and only because user specified both filters)

USER QUERY: "{user_query}"

Generate ONLY the SQL query (no explanations, no markdown):"""

    response = llm_client.invoke(prompt)

    sql = response.content.strip()

    # Clean up markdown code blocks if LLM adds them
    if sql.startswith("```"):
        lines = sql.split("\n")
        # Remove first line (```) and last line (```)
        sql = "\n".join(lines[1:-1]) if len(lines) > 2 else sql
        # If first line was ```sql, remove it
        if sql.startswith("sql"):
            sql = sql[3:].strip()

    # Remove any remaining backticks
    sql = sql.replace("```", "").strip()

    return sql


def select_tool(sql: str) -> str:
    """
    Determine which tool to use based on table name in SQL.

    Args:
        sql: SQL query

    Returns:
        Tool name: "query_vendor_payments" or "query_budget"
    """
    sql_lower = sql.lower()

    if 'vendor_payments' in sql_lower:
        return 'query_vendor_payments'
    elif 'budget' in sql_lower:
        return 'query_budget'
    else:
        # Default to vendor_payments
        logger.warning(f"[SQL_PLANNER] No table found in SQL, defaulting to vendor_payments")
        return 'query_vendor_payments'


def explain_query_results(user_query: str, sql: str, results: List[Dict], tool: str) -> str:
    """
    Generate explanation for query results, especially when empty or unexpected.

    Args:
        user_query: Original user query
        sql: SQL query that was executed
        results: Query results (list of dicts)
        tool: Tool that was used

    Returns:
        Natural language explanation of results
    """
    # If results are empty, explain why
    if not results or len(results) == 0:
        explanation = _explain_zero_results(user_query, sql, tool)
        return explanation

    # If results look good, provide simple summary
    result_count = len(results)
    return f"Found {result_count} result{'s' if result_count != 1 else ''}."


def _explain_zero_results(user_query: str, sql: str, tool: str) -> str:
    """
    When query returns 0 results, figure out why and explain it.

    Args:
        user_query: Original user query
        sql: SQL query that was executed
        tool: Tool that was used

    Returns:
        Explanation of why query returned 0 results
    """
    # Check if query has fiscal_year filter
    if "fiscal_year" in sql.lower():
        available_years = _get_available_fiscal_years(tool)
        if available_years:
            years_str = ', '.join(sorted(available_years))
            return f"No data found. You asked for a specific fiscal year, but our dataset contains data from: {years_str}. Try removing the year filter or using one of these years."
        else:
            return "No data found. Unable to determine available fiscal years."

    # Check if query has entity name filter (LIKE clause)
    if "LIKE" in sql.upper():
        return "No exact matches found for that agency/vendor name. Try using a shorter keyword or check spelling. You can also try removing specific name filters to see all available options."

    return "No results found for your query. The filters may be too restrictive."


def _get_available_fiscal_years(tool: str) -> List[str]:
    """
    Query database for available fiscal years. - trust me its needed

    Args:
        tool: Tool name ("query_vendor_payments" or "query_budget")

    Returns:
        List of available fiscal years as strings
    """
    try:
        if tool == 'query_vendor_payments':
            results = execute_vendor_query("SELECT DISTINCT fiscal_year FROM vendor_payments ORDER BY fiscal_year")
        elif tool == 'query_budget':
            results = execute_budget_query("SELECT DISTINCT fiscal_year FROM budget ORDER BY fiscal_year")
        else:
            return []

        # Extract fiscal years from results
        years = [row.get('fiscal_year') for row in results if row.get('fiscal_year')]
        return years

    except Exception as e:
        logger.error(f"[SQL_PLANNER] Error getting fiscal years: {e}")
        return []
