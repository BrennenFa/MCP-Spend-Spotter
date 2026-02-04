#!/usr/bin/env python3
"""
Claude-based main interface - LangGraph version with explicit workflow control.
Uses LangGraph StateGraph for deterministic routing and enforced visualization rules.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, TypedDict, Annotated, Literal
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from chat.agents.agent_client import AgentPool
from chat.session_manager import session_manager
from chat.graph_nodes import GraphNodes, GraphState

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


# ============================================================================
# CLAUDE AGENT SYSTEM WITH LANGGRAPH
# ============================================================================

class ClaudeAgentSystem:
    """Claude-powered agent system"""

    def __init__(self):
        """Initialize LangGraph workflow and agent pool."""

        # Check for Anthropic API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env\n")

        # Initialize ChatAnthropic model
        self.llm = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            api_key=api_key,
            max_tokens=2500,
            temperature=0
        )

        self.agent_pool = AgentPool()
        self._start_agent()

        # Initialize nodes
        self.nodes = GraphNodes(self.llm, self.agent_pool)

        # Build the LangGraph workflow
        self.graph = self._build_graph()

    def _start_agent(self):
        """Start all agent subprocesses."""
        print("[SYSTEM] Starting agent...")
        try:
            self.agent_pool.register_agent("nc_budget", "nc_budget_agent.py")
            print("[SYSTEM] NC Budget Agent started (SQL + Graph + RAG)")
        except Exception as e:
            print(f"[SYSTEM] Failed to start agents: {e}")
            raise

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""

        workflow = StateGraph(GraphState)

        # add nodes
        workflow.add_node("route_question", self.nodes.route_question)
        workflow.add_node("query_sql", self.nodes.query_sql)
        workflow.add_node("validate_query", self.nodes.validate_query)
        workflow.add_node("route_visualization", lambda state: state)  # Pass-through node for routing
        workflow.add_node("create_graph", self.nodes.create_graph)
        workflow.add_node("query_budget_context", self.nodes.query_budget_context)
        workflow.add_node("generate_response", self.nodes.generate_response)
        workflow.add_node("validate_answer", self.nodes.validate_answer)
        workflow.add_node("handle_general", self.nodes.handle_general)

        # Set entry point
        workflow.set_entry_point("route_question")

        # Add conditional routing from route_question
        workflow.add_conditional_edges(
            "route_question",
            # check query_type in state - inline function
            lambda state: state["query_type"],
            {
                "database": "query_sql",
                "context": "query_budget_context",
                "general": "handle_general"
            }
        )

        # query_sql -> validate_query -> decide if query needs retry or continue
        workflow.add_edge("query_sql", "validate_query")
        workflow.add_conditional_edges(
            "validate_query",
            self.nodes.query_validate_route,
            {
                "retry_query": "query_sql",
                "continue": "route_visualization"
            }
        )
        
        # After validation, route to visualization or response
        workflow.add_conditional_edges(
            "route_visualization",
            self.nodes.route_after_gate,
            {
                "blocked": END,
                "visualize": "create_graph",
                "respond": "generate_response"
            }
        )

        # Visualization -> response
        workflow.add_edge("create_graph", "generate_response")

        # Context search -> response
        workflow.add_edge("query_budget_context", "generate_response")

        # General (no real thing the llm can do with data) → END
        workflow.add_edge("handle_general", END)

        # Response -> validate_answer -> (self-fix loop or END)
        workflow.add_edge("generate_response", "validate_answer")
        workflow.add_conditional_edges(
            "validate_answer",
            self.nodes.should_retry,
            {
                "retry": "generate_response",
                "done": END
            }
        )

        return workflow.compile()

    # ========================================================================
    # PUBLIC INTERFACE
    # ========================================================================

    def process_message(self, user_message: str, session_id: str = "default") -> Dict[str, Any]:
        """Process user message through LangGraph workflow.

        Returns:
            Dict containing:
                - answer: Final text response
                - data: Query result data (if any)
                - graph: Base64-encoded graph (if any)
                - sql_query: SQL query executed (if any)
        """
        print(f"\n[USER] {user_message}\n")

        # Initialize state
        initial_state: GraphState = {
            "messages": [],
            "user_query": user_message,
            "query_type": "",
            "wants_visualization": False,
            "query_results": [],
            "sql_query": "",
            "graph_data": "",
            "context_data": "",
            "final_answer": "",
            "validation_warnings": [],
            "retry_count": 0,
            "sql_retry_count": 0,
            "query_error": "",
            "session_id": session_id
        }

        # Run the graph
        try:
            final_state = self.graph.invoke(initial_state)

            # Build response from final graph state
            # Extract all data accumulated during graph execution
            response_data = {
                "answer": final_state.get("final_answer", ""),  # LLM-generated response text
                "data": final_state.get("query_results"),  # SQL query results (list of dicts)
                "graph": final_state.get("graph_data"),  # Base64-encoded PNG image (optional)
                "sql_query": final_state.get("sql_query"),  # Executed SQL query string (optional)
                "validation_warnings": final_state.get("validation_warnings", [])  # Answer validation warnings
            }

            # Save to session
            session_manager.add_exchange(session_id, user_message, response_data["answer"])

            print(f"\n[CLAUDE] {response_data['answer']}\n")
            return response_data

        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            print(f"[ERROR] {e}")

            response_data = {
                "answer": error_msg,
                "data": None,
                "graph": None,
                "sql_query": None,
                "validation_warnings": []
            }

            session_manager.add_exchange(session_id, user_message, error_msg)
            return response_data

    def shutdown(self):
        """Shutdown all agents."""
        print("\n[SYSTEM] Shutting down...")
        self.agent_pool.shutdown_all()
        print("[SYSTEM] Agents shut down. Goodbye!")
