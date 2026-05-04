"""SQL-related GraphNodes helper functions."""

from typing import Any, Dict, List

from chat.session_manager import session_manager
from chat.agent_functions.validators import validate_query_results


def call_agent_tool(nodes, tool_name: str, tool_input: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """Call a tool via the unified NC Budget agent."""
    try:
        all_history = session_manager.get_messages_dict(session_id)
        chat_history = all_history[-4:]

        agent = nodes.agent_pool.get_agent("nc_budget")

        if tool_name == "query_sql":
            arguments = {
                "query": tool_input["query"],
                "chat_history": chat_history,
                "previous_sql": tool_input.get("previous_sql", ""),
                "sql_warnings": tool_input.get("sql_warnings", []),
            }
        elif tool_name == "create_graph":
            arguments = {
                "results": tool_input.get("data", []),
                "query": tool_input.get("sql_query", ""),
                "chart_spec": tool_input.get("chart_spec"),
                "title": tool_input.get("title"),
                "chat_history": chat_history,
            }
        elif tool_name == "query_budget_context":
            arguments = {
                "query": tool_input["query"],
                "chat_history": chat_history,
            }
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result = agent.call_tool(tool_name, arguments)

        if isinstance(result, dict) and "explanation" in result:
            explanation = result.get("explanation", "")
            if "blocked for safety" in explanation.lower():
                return {"success": False, "error": explanation}

        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_sql_citations(state) -> List[Dict[str, Any]]:
    """Create deterministic SQL citations from source dataset provenance."""
    citations: List[Dict[str, Any]] = []
    sql_query = (state.get("sql_query") or "").strip()

    if not sql_query:
        return citations

    sql_lower = sql_query.lower()
    if "vendor_payments" in sql_lower:
        citations.append({
            "id": 0,
            "kind": "sql",
            "title": "Vendor Payments CSV Sources",
            "detail": "data/vendor_data.csv; data/Key value - Payment 1y.csv; data/Key value - Payment 1ya.csv",
        })
    elif "vendor_only_payments" in sql_lower or "vendor_payments_normalized" in sql_lower or "agency_rollup_payments" in sql_lower:
        citations.append({
            "id": 0,
            "kind": "sql",
            "title": "Vendor Payments CSV Sources",
            "detail": "data/vendor_data.csv; data/Key value - Payment 1y.csv; data/Key value - Payment 1ya.csv",
        })
    elif " budget" in sql_lower or "from budget" in sql_lower:
        citations.append({
            "id": 0,
            "kind": "sql",
            "title": "Budget CSV Sources",
            "detail": "data/budget_data.csv; data/budget2024.csv",
        })
    else:
        citations.append({
            "id": 0,
            "kind": "sql",
            "title": "Database Source",
            "detail": "SQLite tables populated from project CSV files in data/",
        })

    return citations


def query_sql(nodes, state):
    """Execute database query."""
    if state.get("sql_query"):
        state["sql_retry_count"] = state.get("sql_retry_count", 0) + 1
        print(f"[NODE] Retrying database query (attempt {state['sql_retry_count']}): {state['user_query']}")
    else:
        print(f"[NODE] Querying database: {state['user_query']}")

    result = call_agent_tool(
        nodes,
        "query_sql",
        {
            "query": state["user_query"],
            "previous_sql": state.get("sql_query", ""),
            "sql_warnings": [],
        },
        state["session_id"],
    )

    if result.get("success"):
        tool_result = result.get("result", {})
        if isinstance(tool_result, dict):
            state["query_results"] = tool_result.get("results", [])
            state["sql_query"] = tool_result.get("query", "")
            state["query_explanation"] = tool_result.get("explanation", "")
            state["query_error"] = ""
            print(f"[NODE] Retrieved {len(state['query_results'])} rows")
    else:
        state["query_error"] = result.get("error", "Unknown query execution error")
        print(f"[NODE] Query failed: {state['query_error']}")

    return state


def validate_query(state):
    """Validate query: failures, empty results, result sanity."""
    print("[NODE] Validating query results...")

    state["validation_warnings"] = validate_query_results(
        state.get("query_results", []),
        state.get("sql_query", ""),
        state.get("query_error", ""),
    )

    print(f"[NODE] Query validation complete ({len(state['validation_warnings'])} warnings)")
    return state
