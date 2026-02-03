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
from chat.agent_functions.validators.answer_validator import (
    validate_query_results,
    validate_data_grounding,
    validate_context_grounding
)

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from chat.agents.agent_client import AgentPool
from chat.session_manager import session_manager

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

MAX_RETRIES = 2  # Max self-correction loops when hallucinations detected


# ============================================================================
# STATE SCHEMA
# ============================================================================

class GraphState(TypedDict):
    """State schema for LangGraph workflow."""
    messages: Annotated[List[BaseMessage], add_messages]  # Chat history
    user_query: str  # Current user question
    query_type: str  # "database", "context", "general"
    wants_visualization: bool  # Whether user explicitly wants a graph
    query_results: List[Dict]  # Results from database query
    sql_query: str  # SQL query executed
    graph_data: str  # Base64-encoded graph image
    context_data: str  # Results from RAG search
    final_answer: str  # Final response to user
    validation_warnings: List[str]  # Validation warnings from answer validator
    retry_count: int  # Self-fix attempt counter
    session_id: str  # Session identifier


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

    def _call_agent_tool(self, tool_name: str, tool_input: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Call a tool via the unified NC Budget agent."""

        try:
            # Get chat history
            all_history = session_manager.get_messages_dict(session_id)
            chat_history = all_history[-4:]

            agent = self.agent_pool.get_agent("nc_budget")

            # Prepare arguments
            if tool_name == "query_sql":
                arguments = {
                    "query": tool_input["query"],
                    "chat_history": chat_history
                }
            elif tool_name == "create_graph":
                arguments = {
                    "results": tool_input.get("data", []),
                    "query": tool_input.get("sql_query", ""),
                    "title": tool_input.get("title"),
                    "chat_history": chat_history
                }
            elif tool_name == "query_budget_context":
                arguments = {
                    "query": tool_input["query"],
                    "chat_history": chat_history
                }
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

            result = agent.call_tool(tool_name, arguments)
            return {"success": True, "result": result}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # GRAPH NODES
    # ========================================================================

    def route_question(self, state: GraphState) -> GraphState:
        """Analyze question and determine which tool to use."""
        query = state["user_query"]

        # Use LLM to classify query type AND detect visualization intent
        prompt = f"""Analyze this user question and respond with TWO pieces of information:

1. Category (one of: database, context, general):
   - "database": Questions about spending, payments, vendors, agencies, budgets, amounts
   - "context": Questions asking to explain concepts, terminology, or "what is" questions
   - "general": General conversation or greetings

2. Visualization intent (yes/no):
   - "yes" if user explicitly wants a graph, chart, visualization, or plot
   - "no" otherwise

Question: {query}

Respond in this exact format:
category: <database/context/general>
visualization: <yes/no>"""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = response.content.strip().lower()

        # Parse response
        query_type = "general"
        wants_viz = False

        for line in response_text.split('\n'):
            if 'category:' in line:
                query_type = line.split(':')[1].strip()
            elif 'visualization:' in line:
                wants_viz = 'yes' in line.split(':')[1].strip()

        state["query_type"] = query_type
        # state whether or not they want visualization
        state["wants_visualization"] = wants_viz

        print(f"[ROUTE] Query classified as: {query_type}, wants_visualization: {wants_viz}")

        return state

    def query_sql(self, state: GraphState) -> GraphState:
        """Execute database query."""
        print(f"[NODE] Querying database: {state['user_query']}")

        result = self._call_agent_tool(
            "query_sql",
            {"query": state["user_query"]},
            state["session_id"]
        )

        # Parse result - agent.call_tool() already parsed the JSON
        # Response structure: {success: bool, result: {results: [...], query: "...", explanation: "..."}}
        if result.get("success"):  # Check if agent call succeeded
            tool_result = result.get("result", {})  # Extract already-parsed result object
            if isinstance(tool_result, dict):
                state["query_results"] = tool_result.get("results", [])  # Extract query result rows
                state["sql_query"] = tool_result.get("query", "")  # Extract SQL query string
                print(f"[NODE] Retrieved {len(state['query_results'])} rows")
        return state

    def create_graph(self, state: GraphState) -> GraphState:
        """Create visualization from query results."""
        print(f"[NODE] Creating visualization for {len(state['query_results'])} rows")

        result = self._call_agent_tool(
            "create_graph",
            {
                "data": state["query_results"],
                "sql_query": state["sql_query"],
                "title": None
            },
            state["session_id"]
        )

        # Parse graph result - agent.call_tool() already parsed the JSON
        # Response structure: {success: bool, result: {graph: "base64-encoded-png-string"}}
        if result.get("success"):  # Check if agent call succeeded
            tool_result = result.get("result", {})  # Extract already-parsed result object
            if isinstance(tool_result, dict):
                state["graph_data"] = tool_result.get("graph")  # Extract base64 PNG data
                print(f"[NODE] Graph created successfully")

        return state

    def query_budget_context(self, state: GraphState) -> GraphState:
        """Search budget context documents."""
        print(f"[NODE] Searching context: {state['user_query']}")

        result = self._call_agent_tool(
            "query_budget_context",
            {"query": state["user_query"]},
            state["session_id"]
        )

        # Parse RAG context result - agent.call_tool() already parsed the JSON
        # Response structure: {success: bool, result: <context_text_or_dict>}
        if result.get("success"):  # Check if agent call succeeded
            tool_result = result.get("result", {})  # Extract already-parsed result
            # RAG returns either a string or dict - handle both
            if isinstance(tool_result, str):
                state["context_data"] = tool_result
            elif isinstance(tool_result, dict):
                state["context_data"] = json.dumps(tool_result)
            print(f"[NODE] Context retrieved")

        return state



    def generate_response(self, state: GraphState) -> GraphState:
        """Generate final answer based on gathered data. On retry, folds in validator feedback."""

        # Self-fix: if previous validation flagged grounding issues, build correction prompt
        correction_prompt = ""
        if state.get("validation_warnings"):
            state["retry_count"] = state.get("retry_count", 0) + 1
            grounding_issues = [w for w in state["validation_warnings"]
                                if "[DATA_GROUNDING]" in w or "[CONTEXT_GROUNDING]" in w]
            if grounding_issues:
                correction_prompt = "\n\nYour previous answer contained these errors — correct them:\n"
                for issue in grounding_issues:
                    correction_prompt += f"- {issue}\n"
                correction_prompt += "\nStick strictly to the facts in the data above. Do not invent values.\n"
            # Clear warnings so next validation pass starts fresh
            state["validation_warnings"] = []

        print(f"[NODE] Generating response (attempt {state.get('retry_count', 0) + 1})")

        # Build context for LLM from state accumulated during graph execution
        context_parts = []

        # check for sql results
        if state.get("query_results"):
            context_parts.append(f"Query Results ({len(state['query_results'])} rows):")
            # json format
            context_parts.append(json.dumps(state["query_results"], indent=2))
            # Include SQL query
            context_parts.append(f"\nSQL Query: {state.get('sql_query', 'N/A')}")

        # check for graph results
        if state.get("graph_data"):
            context_parts.append("\n[A visualization has been created for this data]")

        # check for rag context data
        if state.get("context_data"):
            context_parts.append(f"\nContext Information:\n{state['context_data']}")

        # combine all parts
        context = "\n\n".join(context_parts)

        # Generate answer
        prompt = f"""Based on the following data, answer the user's question concisely and clearly.

User Question: {state['user_query']}

Data:
{context}

Instructions:
- Provide a clear, direct answer
- Reference specific numbers/facts from the data
- If a visualization was created, mention it briefly
- Keep the answer concise (2-4 sentences)
{correction_prompt}"""

        # invoke an llm response
        response = self.llm.invoke([HumanMessage(content=prompt)])
        state["final_answer"] = response.content

        print(f"[NODE] Response generated")
        return state

    def validate_answer(self, state: GraphState) -> GraphState:
        """Unified validation: result quality + answer grounding."""
        print(f"[NODE] Validating results and answer...")

        warnings = []

        # Validate query results quality
        if state.get("query_results"):
            result_warnings = validate_query_results(
                state["query_results"],
                state["sql_query"]
            )
            warnings.extend(result_warnings)

        # Validate query
        if state.get("query_results") and state.get("final_answer"):
            data_warnings = validate_data_grounding(
                state["final_answer"],
                state["query_results"],
                state["sql_query"],
                self.llm
            )
            warnings.extend(data_warnings)

        # Validate context
        if state.get("context_data") and state.get("final_answer"):
            context_warnings = validate_context_grounding(
                state["final_answer"],
                state["context_data"],
                self.llm
            )
            warnings.extend(context_warnings)

        # print all warnings (non-blocking)
        for warning in warnings:
            print(warning, file=sys.stderr)

        state["validation_warnings"] = warnings
        print(f"[NODE] Validation complete ({len(warnings)} warnings)")
        return state

    def handle_general(self, state: GraphState) -> GraphState:
        """Handle general conversation."""
        print(f"[NODE] Handling general conversation")

        response = self.llm.invoke([HumanMessage(content=state["user_query"])])
        state["final_answer"] = response.content

        return state

    # ========================================================================
    # CONDITIONAL EDGES
    # ========================================================================

    def should_visualize(self, state: GraphState) -> Literal["visualize", "respond"]:
        """Determine if visualization should be created."""

        # sql query results
        results = state.get("query_results", [])
        wants_viz = state.get("wants_visualization", False)

        # Visualize if: user explicitly requested OR more than 4 rows
        if wants_viz or len(results) > 4:
            reason = "user requested" if wants_viz else f"{len(results)} rows"
            return "visualize" 
        else:
            return "respond" 

    def route_by_type(self, state: GraphState) -> Literal["database", "context", "general"]:
        """Route to appropriate node based on query type."""
        return state["query_type"]

    def should_retry(self, state: GraphState) -> Literal["retry", "done"]:
        """Route back to generate_response if grounding issues remain and retries available."""
        warnings = state.get("validation_warnings", [])
        grounding_issues = [w for w in warnings if "[DATA_GROUNDING]" in w or "[CONTEXT_GROUNDING]" in w]

        if grounding_issues and state.get("retry_count", 0) < MAX_RETRIES:
            print(f"[SELF-FIX] Issues detected, retrying ({state.get('retry_count', 0) + 1}/{MAX_RETRIES})")
            return "retry"

        if grounding_issues:
            print(f"[SELF-FIX] Max retries reached — {len(grounding_issues)} issue(s) remain")
        return "done"

    # ========================================================================
    # GRAPH CONSTRUCTION
    # ========================================================================

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""

        workflow = StateGraph(GraphState)

        # add nodes
        workflow.add_node("route_question", self.route_question)
        workflow.add_node("query_sql", self.query_sql)
        workflow.add_node("create_graph", self.create_graph)
        workflow.add_node("query_budget_context", self.query_budget_context)
        workflow.add_node("generate_response", self.generate_response)
        workflow.add_node("validate_answer", self.validate_answer)
        workflow.add_node("handle_general", self.handle_general)

        # Set entry point
        workflow.set_entry_point("route_question")

        # Add conditional routing from route_question
        workflow.add_conditional_edges(
            "route_question",
            self.route_by_type,
            {
                "database": "query_sql",
                "context": "query_budget_context",
                "general": "handle_general"
            }
        )

        # Add conditional edge for visualization
        workflow.add_conditional_edges(
            "query_sql",
            self.should_visualize,
            {
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

        # Response -> Validation -> (self-fix loop or END)
        workflow.add_edge("generate_response", "validate_answer")
        workflow.add_conditional_edges(
            "validate_answer",
            self.should_retry,
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
