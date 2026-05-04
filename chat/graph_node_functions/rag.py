"""RAG and response-related GraphNodes helper functions."""

import json
import sys
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from chat.agent_functions.validators import validate_context_grounding, validate_data_grounding
from chat.graph_node_functions.sql import call_agent_tool


def extract_rag_citations(state) -> List[Dict[str, Any]]:
    """Extract citations from RAG context payload if present."""
    citations: List[Dict[str, Any]] = []
    context_data = state.get("context_data", "")
    if not context_data:
        return citations
    try:
        parsed = json.loads(context_data)
    except json.JSONDecodeError:
        return citations

    raw_citations = parsed.get("citations", [])
    if not isinstance(raw_citations, list):
        return citations

    for citation in raw_citations:
        if not isinstance(citation, dict):
            continue
        citations.append({
            "id": 0,
            "kind": "rag",
            "title": citation.get("title", "Budget Document"),
            "detail": citation.get("detail", ""),
        })
    return citations


def build_citations(state) -> List[Dict[str, Any]]:
    """Compose and re-index citations for final response."""
    combined = extract_rag_citations(state)
    for idx, citation in enumerate(combined, 1):
        citation["id"] = idx
    return combined


def query_budget_context(nodes, state):
    """Search budget context documents."""
    print(f"[NODE] Searching context: {state['user_query']}")

    result = call_agent_tool(
        nodes,
        "query_budget_context",
        {"query": state["user_query"]},
        state["session_id"],
    )

    if result.get("success"):
        tool_result = result.get("result", {})
        if isinstance(tool_result, str):
            state["context_data"] = tool_result
            state["citations"] = []
        elif isinstance(tool_result, dict):
            state["context_data"] = json.dumps(tool_result)
            state["citations"] = extract_rag_citations(state)
        print("[NODE] Context retrieved")

    return state


def generate_response(nodes, state):
    """Generate final answer based on gathered data. On retry, folds in validator feedback."""
    correction_prompt = ""
    if state.get("validation_warnings"):
        state["retry_count"] = state.get("retry_count", 0) + 1
        grounding_issues = [
            w for w in state["validation_warnings"]
            if "[DATA_GROUNDING]" in w or "[CONTEXT_GROUNDING]" in w
        ]
        if grounding_issues:
            correction_prompt = "\n\nYour previous answer contained these errors — correct them:\n"
            for issue in grounding_issues:
                correction_prompt += f"- {issue}\n"
            correction_prompt += "\nStick strictly to the facts in the data above. Do not invent values.\n"
        state["validation_warnings"] = []

    print(f"[NODE] Generating response (attempt {state.get('retry_count', 0) + 1})")

    context_parts = []

    if state.get("query_results"):
        context_parts.append(f"Query Results ({len(state['query_results'])} rows):")
        context_parts.append(json.dumps(state["query_results"], indent=2))
        context_parts.append(f"\nSQL Query: {state.get('sql_query', 'N/A')}")
        if state.get("query_explanation"):
            context_parts.append(f"\nResult Notes:\n{state['query_explanation']}")

    if state.get("context_data"):
        context_parts.append(f"\nContext Information:\n{state['context_data']}")

    context = "\n\n".join(context_parts)
    citations = build_citations(state)
    state["citations"] = citations
    citation_map = "\n".join([f"[{c['id']}] {c['title']} — {c['detail']}" for c in citations]) if citations else "None"

    prompt = f"""Based on the following data, answer the user's question concisely and clearly.

User Question: {state['user_query']}

Data:
{context}

Available Citations:
{citation_map}

Instructions:
- Provide a clear, direct answer
- Reference specific numbers/facts from the data
- Incorporate any result notes about fiscal-year scope or structural caveats when they matter
- Do not state whether a visualization was created
- Add inline citation markers like [1], [2] for factual claims when citations are available
- Keep the answer concise (2-4 sentences)
{correction_prompt}"""

    response = nodes.llm.invoke([HumanMessage(content=prompt)])
    state["final_answer"] = response.content

    decision = state.get("visualization_decision", {})
    if (
        state.get("wants_visualization", False)
        and not decision.get("should_visualize")
        and decision.get("no_graph_explanation")
    ):
        state["final_answer"] = f"{state['final_answer']} {decision['no_graph_explanation']}".strip()

    session_id = state.get("session_id", "default")
    graph_future = None
    with nodes._graph_lock:
        graph_future = nodes._graph_futures.pop(session_id, None)

    if graph_future is not None:
        try:
            graph_data = graph_future.result()
            if graph_data:
                state["graph_data"] = graph_data
                print("[NODE] Graph created successfully")
        except Exception as e:
            print(f"[NODE] Graph generation failed: {e}", file=sys.stderr)

    if (
        state.get("wants_visualization", False)
        and not state.get("graph_data")
        and not decision.get("no_graph_explanation")
    ):
        state["final_answer"] = (
            f"{state['final_answer']} "
            "I couldn't produce a graph that matched these results cleanly without risking a misleading chart."
        ).strip()

    state["visualization_status"] = "created" if state.get("graph_data") else "not_created"

    print("[NODE] Response generated")
    return state


def validate_answer(nodes, state):
    """Answer grounding validation: data and context hallucination checks."""
    print("[NODE] Validating answer grounding...")

    warnings = list(state.get("validation_warnings", []))

    if state.get("query_results") and state.get("final_answer"):
        data_warnings = validate_data_grounding(
            state["final_answer"],
            state["query_results"],
            state["sql_query"],
            nodes.llm,
        )
        warnings.extend(data_warnings)

    if state.get("context_data") and state.get("final_answer"):
        context_warnings = validate_context_grounding(
            state["final_answer"],
            state["context_data"],
            nodes.llm,
        )
        warnings.extend(context_warnings)

    for warning in warnings:
        print(warning, file=sys.stderr)

    state["validation_warnings"] = warnings
    print(f"[NODE] Answer validation complete ({len(warnings)} warnings)")
    return state
