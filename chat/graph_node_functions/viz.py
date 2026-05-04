"""Visualization-related GraphNodes helper functions."""

import json
from copy import deepcopy
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from chat.graph_node_functions.sql import call_agent_tool


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from an LLM response."""
    if not text:
        return None

    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def default_visualization_decision(requested: bool = False) -> Dict[str, Any]:
    """Fallback visualization decision."""
    decision: Dict[str, Any] = {
        "should_visualize": False,
        "chart_type": "",
        "x_field": "",
        "y_field": "",
        "analysis_goal": "",
        "title": "",
        "no_graph_explanation": "",
    }
    if requested:
        decision["no_graph_explanation"] = (
            "I couldn't identify a graph that would clarify these results without being misleading or redundant."
        )
    return decision


def normalize_visualization_decision(raw: Dict[str, Any], requested: bool) -> Dict[str, Any]:
    """Normalize LLM decision output to the internal schema."""
    decision = default_visualization_decision(requested=requested)

    should_visualize = raw.get("should_visualize", False)
    if isinstance(should_visualize, str):
        should_visualize = should_visualize.strip().lower() == "true"
    decision["should_visualize"] = bool(should_visualize)

    for key in ("chart_type", "x_field", "y_field", "analysis_goal", "title", "no_graph_explanation"):
        value = raw.get(key, "")
        decision[key] = value.strip() if isinstance(value, str) else ""

    if decision["analysis_goal"] == "" and isinstance(raw.get("aggregation_intent"), str):
        decision["analysis_goal"] = raw["aggregation_intent"].strip()

    if decision["should_visualize"]:
        required = ("chart_type", "x_field", "y_field", "analysis_goal")
        if not all(decision.get(key) for key in required):
            return default_visualization_decision(requested=requested)
        return decision

    if requested and not decision["no_graph_explanation"]:
        decision["no_graph_explanation"] = (
            "I couldn't identify a graph that would clarify these results without being misleading or redundant."
        )
    return decision


def assess_visualization(nodes, state):
    """Grounded post-query visualization decision."""
    if state.get("query_error"):
        state["visualization_decision"] = default_visualization_decision(
            requested=state.get("wants_visualization", False)
        )
        return state

    results = state.get("query_results", [])
    requested = state.get("wants_visualization", False)
    if not results:
        state["visualization_decision"] = default_visualization_decision(requested=requested)
        return state

    print(f"[NODE] Assessing visualization need for {len(results)} rows")
    result_sample = json.dumps(results[:15], indent=2)
    prompt = f"""You are deciding whether a chart should be included for a SQL answer.

User question:
{state["user_query"]}

User explicitly requested a visualization:
{"yes" if requested else "no"}

SQL query:
{state.get("sql_query", "")}

Result sample:
{result_sample}

Rules:
- Decide based on the actual result set and whether a chart would materially improve the answer.
- If the user explicitly requested a visualization, default to should_visualize=true unless no coherent, useful chart can be justified.
- If the user did not explicitly request a visualization, only set should_visualize=true when the chart adds clear value beyond a short textual answer.
- Never force a chart from detail rows, noisy records, or semantically weak axes.
- If should_visualize=true, choose one chart type and exact x/y fields from the result keys.
- Allowed chart_type values: "bar", "line".
- y_field must be numeric or numeric-like in the results.
- x_field must be a real key from the results that makes semantic sense for the question.
- analysis_goal should be a short phrase like "compare top vendors" or "show year-over-year trend".
- If should_visualize=false and the user explicitly requested a chart, provide a single-sentence no_graph_explanation.
- If should_visualize=false and the user did not request a chart, no_graph_explanation should be empty.

Return strict JSON only with this schema:
{{
  "should_visualize": true or false,
  "chart_type": "bar" or "line" or "",
  "x_field": "<field>" or "",
  "y_field": "<field>" or "",
  "analysis_goal": "<short phrase>" or "",
  "title": "<optional title>" or "",
  "no_graph_explanation": "<single sentence or empty string>"
}}"""

    response = nodes.llm.invoke([HumanMessage(content=prompt)])
    parsed = extract_json_object(str(response.content))
    if parsed is None:
        state["visualization_decision"] = default_visualization_decision(requested=requested)
    else:
        state["visualization_decision"] = normalize_visualization_decision(parsed, requested=requested)

    print(f"[NODE] Visualization decision: {state['visualization_decision']}")
    return state


def create_graph(nodes, state):
    """Kick off visualization creation in background for overlap with answer generation."""
    print(f"[NODE] Creating visualization for {len(state['query_results'])} rows")
    session_id = state.get("session_id", "default")
    graph_state = deepcopy(state)

    def _graph_job() -> str:
        result = call_agent_tool(
            nodes,
            "create_graph",
            {
                "data": graph_state.get("query_results", []),
                "sql_query": graph_state.get("sql_query", ""),
                "chart_spec": graph_state.get("visualization_decision", {}),
                "title": graph_state.get("visualization_decision", {}).get("title"),
            },
            graph_state.get("session_id", "default"),
        )

        if result.get("success"):
            tool_result = result.get("result", {})
            if isinstance(tool_result, dict):
                return tool_result.get("graph") or ""
        return ""

    with nodes._graph_lock:
        previous = nodes._graph_futures.pop(session_id, None)
        if previous and not previous.done():
            previous.cancel()
        nodes._graph_futures[session_id] = nodes._graph_executor.submit(_graph_job)

    print("[NODE] Graph generation started in background")
    return state
