"""SQL Query Planner - LLM-based SQL generation from natural language."""

import logging
from typing import Dict, Any, List
from langchain_groq import ChatGroq

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
            "arguments": {"query": "SELECT ..."}
        }
    """
    try:
        # Generate SQL using LLM with full database context
        sql = generate_sql_with_llm(user_query, llm_client)
        logger.info(f"[SQL_PLANNER] Generated SQL: {sql}")


        # Determine which tool to use based on table
        tool = select_tool(sql)
        logger.info(f"[SQL_PLANNER] Selected tool: {tool}")

        return {
            "tool": tool,
            "sql": sql,
            "arguments": {"query": sql},
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
    vendor_years = _get_available_fiscal_years_for_surface("vendor")
    budget_years = _get_available_fiscal_years_for_surface("budget")
    latest_vendor_year = vendor_years[-1] if vendor_years else "2026"
    latest_budget_year = budget_years[-1] if budget_years else "2025"

    prompt = f"""You are a SQL expert for North Carolina government data.

DATABASE SCHEMA:

vendor DB curated views:

vendor_only_payments view:
- fiscal_year (TEXT)
- payment_amount (REAL)
- canonical_entity_name (TEXT): Normalized external vendor/entity name
- parent_agency (TEXT)
- canonical_agency (TEXT)
- spending_type (TEXT)
- major_category (TEXT)
- account_description (TEXT)
- entity_type is always 'vendor'

vendor_payments_normalized view:
- fiscal_year (TEXT)
- payment_amount (REAL)
- raw_vendor_recipient (TEXT)
- canonical_entity_name (TEXT)
- entity_type (TEXT): vendor | benefit_recipient | claimant | grant_recipient | internal_or_unknown
- entity_type_confidence (REAL)
- canonical_agency (TEXT)
- parent_agency (TEXT)
- sub_agency (TEXT)
- spending_type (TEXT)
- major_category (TEXT)
- account_description (TEXT)

agency_rollup_payments view:
- fiscal_year (TEXT)
- parent_agency (TEXT)
- canonical_agency (TEXT)
- sub_agency (TEXT)
- entity_type (TEXT)
- spending_type (TEXT)
- major_category (TEXT)
- payment_amount (REAL)
- canonical_entity_name (TEXT)
- raw_vendor_recipient (TEXT)
- account_description (TEXT)

budget table:
- fiscal_year (TEXT): "{latest_budget_year}"
- committee (TEXT)
- agency (TEXT)
- expenditures_amount (REAL)
- receipts_amount (REAL)
- net_appropriations_amount (REAL)
- budget_type (TEXT)
- fund_type (TEXT)
- account_group (TEXT)

CRITICAL RULES:
1. Prefer curated vendor views over raw vendor tables.
2. payment_amount / expenditures_amount / receipts_amount / net_appropriations_amount are already numeric. Use them directly.
3. Column names are lowercase with underscores.
4. Only generate SELECT queries (no INSERT, UPDATE, DELETE, DROP, ALTER).
5. For "How many..." questions, use COUNT.
6. For "What's the total..." or "sum of..." questions, use SUM.
7. For "What's the maximum..." or "largest..." questions, use MAX.
8. For "What's the minimum..." or "smallest..." questions, use MIN.
9. Respect user-specified limits: "top 5" = LIMIT 5, "top 10" = LIMIT 10.

CRITICAL RULES ABOUT WHERE CLAUSES:
1. ONLY add WHERE clauses for filters the user explicitly mentions, except for the default fiscal-year rule below.
2. For ranking/comparison questions without a fiscal year, default to the latest available fiscal year for that data surface.
3. Use {latest_vendor_year} as the default latest vendor year and {latest_budget_year} as the default latest budget year.
4. If the user asks for cumulative totals across all years, do not add a fiscal_year filter.
5. For vendor rankings, use vendor_only_payments unless the user explicitly asks for all payees or benefits/grants.
6. For agency comparisons, use agency_rollup_payments and compare parent_agency unless the user explicitly asks for divisions or sub-agencies.
7. All data is from North Carolina - never filter by state or region.
8. Use canonical fields before raw substring matching when possible.

EXAMPLES - Pay attention to when NOT to add WHERE clauses:

User: "How many total payments were made?"
SQL: SELECT COUNT(*) FROM vendor_payments_normalized
(NOTE: Count-style totals can span all years unless the user asks otherwise.)

User: "Which vendor received the single largest payment?"
SQL: SELECT canonical_entity_name, payment_amount AS amount FROM vendor_only_payments WHERE fiscal_year = '{latest_vendor_year}' ORDER BY amount DESC LIMIT 1
(NOTE: Rankings default to the latest vendor year when no year is specified.)

User: "Top 5 vendors by total payments"
SQL: SELECT canonical_entity_name, SUM(payment_amount) AS total FROM vendor_only_payments WHERE fiscal_year = '{latest_vendor_year}' GROUP BY canonical_entity_name ORDER BY total DESC LIMIT 5
(NOTE: Use vendor_only_payments so payment buckets do not appear as vendors.)

User: "How many vendors were paid in 2026?"
SQL: SELECT COUNT(DISTINCT canonical_entity_name) FROM vendor_only_payments WHERE fiscal_year = '2026'
(NOTE: Use normalized vendor names.)

User: "Total payments to Duke Energy"
SQL: SELECT SUM(payment_amount) AS total FROM vendor_only_payments WHERE canonical_entity_name LIKE '%Duke Energy%'
(NOTE: Filter on canonical entity name.)

User: "Show payments to Transportation department in 2026"
SQL: SELECT * FROM agency_rollup_payments WHERE parent_agency = 'Department Of Transportation' AND fiscal_year = '2026'
(NOTE: Agency comparisons should use normalized parent agencies.)

User: "Compare spending across departments"
SQL: SELECT parent_agency, SUM(payment_amount) AS total FROM agency_rollup_payments WHERE fiscal_year = '{latest_vendor_year}' GROUP BY parent_agency ORDER BY total DESC
(NOTE: Default to the latest year for comparisons.)

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

    if any(name in sql_lower for name in ['vendor_payments', 'vendor_only_payments', 'vendor_payments_normalized', 'agency_rollup_payments']):
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

    # If results look good, provide summary plus scope/caveat notes.
    result_count = len(results)
    message_parts = [f"Found {result_count} result{'s' if result_count != 1 else ''}."]

    year_note = _build_year_scope_note(results)
    if year_note:
        message_parts.append(year_note)

    structural_note = _build_structural_note(user_query, sql, results)
    if structural_note:
        message_parts.append(structural_note)

    return " ".join(message_parts)


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
        from chat.tools.implementations import execute_vendor_query, execute_budget_query

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


def _get_available_fiscal_years_for_surface(surface: str) -> List[str]:
    """Fetch available years directly from the normalized surfaces."""
    try:
        from chat.tools.implementations import execute_vendor_query, execute_budget_query

        if surface == "vendor":
            results = execute_vendor_query("SELECT DISTINCT fiscal_year FROM vendor_payments_normalized ORDER BY fiscal_year")
        elif surface == "budget":
            results = execute_budget_query("SELECT DISTINCT fiscal_year FROM budget ORDER BY fiscal_year")
        else:
            return []
        return [row.get("fiscal_year") for row in results if row.get("fiscal_year")]
    except Exception as e:
        logger.error(f"[SQL_PLANNER] Error getting fiscal years for {surface}: {e}")
        return []


def _build_year_scope_note(results: List[Dict]) -> str:
    """Summarize whether the results cover one or multiple fiscal years."""
    years = sorted({str(row.get("fiscal_year")).strip() for row in results if row.get("fiscal_year")})
    if not years:
        return ""
    if len(years) == 1:
        return f"This result set is scoped to fiscal year {years[0]}."
    return f"This result set spans multiple fiscal years: {', '.join(years)}."


def _build_structural_note(user_query: str, sql: str, results: List[Dict]) -> str:
    """Surface analytical caveats that factual grounding alone will not catch."""
    lowered_query = user_query.lower()
    lowered_sql = sql.lower()

    entity_types = {
        str(row.get("entity_type")).strip()
        for row in results
        if row.get("entity_type")
    }
    if "vendor" in lowered_query and entity_types and entity_types != {"vendor"}:
        non_vendor_types = ", ".join(sorted(entity_type for entity_type in entity_types if entity_type != "vendor"))
        return f"These results include non-vendor payee types ({non_vendor_types}), so they should not be interpreted as a pure vendor ranking."

    if "agency_rollup_payments" in lowered_sql:
        return "Agency results are rolled up to parent agencies for apples-to-apples comparison."

    if any(row.get("parent_agency") and row.get("canonical_agency") and row.get("parent_agency") != row.get("canonical_agency") for row in results):
        return "These results include sub-agencies nested under parent agencies, so detailed units may be grouped or mixed depending on the query."

    return ""
