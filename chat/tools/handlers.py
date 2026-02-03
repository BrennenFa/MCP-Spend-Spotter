#!/usr/bin/env python3
"""MCP-compliant tool handlers."""

import json
import sys
import logging
from typing import Any, Dict
from .implementations import (
    execute_vendor_query,
    execute_budget_query,
    create_graph_from_results,
    query_budget_context
)

# Import SQL query planner functions
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from chat.agent_functions.sql.query_planner import plan_query, explain_query_results

logger = logging.getLogger(__name__)


def handle_query_vendor_payments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle vendor payment queries."""
    try:
        query = arguments["query"]
        results = execute_vendor_query(query)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(results, indent=2)
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error executing query: {str(e)}"
                }
            ],
            "isError": True
        }


def handle_query_budget(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle budget queries."""
    try:
        query = arguments["query"]
        results = execute_budget_query(query)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(results, indent=2)
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error executing query: {str(e)}"
                }
            ],
            "isError": True
        }


def handle_create_graph(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP request to create a graph."""
    try:
        results = arguments["results"]
        query = arguments["query"]
        title = arguments.get("title")

        graph_result = create_graph_from_results(results, query, title)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(graph_result, indent=2)
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error creating graph: {str(e)}"
                }
            ],
            "isError": True
        }


def handle_query_budget_context(arguments: Dict[str, Any], agent_state) -> Dict[str, Any]:
    """Handle query_budget_context tool - RAG search over budget documents."""
    try:
        query = arguments.get("query", "")
        chat_history = arguments.get("chat_history", [])

        if not query:
            return {
                "content": [{"type": "text", "text": "No query provided"}],
                "isError": True
            }

        # Wait for RAG models to be ready (blocks if background thread still loading)
        agent_state._rag_ready.wait()

        # Call the agent_functions RAG query handler
        print(f"[NC_BUDGET] [RAG] Processing query: {query}", file=sys.stderr)
        result = query_budget_context(
            query=query,
            chat_history=chat_history,
            embedding_model=agent_state._embedding_model,
            reranker=agent_state._reranker,
            chroma_client=agent_state._chroma_client,
            llm=agent_state._llm_for_rag
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result)
                }
            ]
        }

    except Exception as e:
        logger.error(f"[NC_BUDGET] [RAG] Error in query_budget_context: {e}")
        import traceback
        traceback.print_exc()
        return {
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
            "isError": True
        }


def handle_query_sql(arguments: Dict[str, Any], agent_state) -> Dict[str, Any]:
    """Handle query_sql tool - natural language query by converting to SQL and executing."""
    try:
        user_query = arguments.get("query", "")
        if not user_query:
            return {
                "content": [{"type": "text", "text": "No query provided"}],
                "isError": True
            }

        # Plan/write the query using the query_planner module
        query_plan = plan_query(user_query, agent_state.llm_client)
        logger.info(f"[NC_BUDGET] [SQL] Query plan: {query_plan['tool']} - {query_plan['sql']}")

        # Log SQL validation warnings
        sql_warnings = query_plan.get('warnings', [])
        for warning in sql_warnings:
            logger.warning(warning)

        # Execute using the selected tool
        if query_plan['tool'] == 'query_vendor_payments':
            result = handle_query_vendor_payments(query_plan['arguments'])
        elif query_plan['tool'] == 'query_budget':
            result = handle_query_budget(query_plan['arguments'])
        else:
            return {
                "content": [{"type": "text", "text": f"Tool not found: {query_plan['tool']}"}],
                "isError": True
            }

        # Extract results from the handler response
        results = []
        if isinstance(result, dict) and 'content' in result:
            for content in result.get('content', []):
                if content.get('type') == 'text':
                    # Try to parse JSON results
                    try:
                        results = json.loads(content.get('text', '[]'))
                    except:
                        results = content.get('text', '')

        # Generate explanation using the query_planner module
        explanation = explain_query_results(user_query, query_plan['sql'], results if isinstance(results, list) else [], query_plan['tool'])

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "explanation": explanation,
                        "query": query_plan['sql'],
                        "results": results,
                        "tool_used": query_plan['tool'],
                        "warnings": sql_warnings  # SQL warnings only (result validation moved to LangGraph)
                    })
                }
            ]
        }

    except Exception as e:
        logger.error(f"[NC_BUDGET] [SQL] Error in query_sql: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "isError": True
        }
