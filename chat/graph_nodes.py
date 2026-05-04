"""Graph nodes and state definition for the Claude agent system."""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, TypedDict, Annotated, Literal

from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.graph.message import add_messages

from chat.graph_node_functions.rag import generate_response, query_budget_context, validate_answer
from chat.graph_node_functions.sql import query_sql, validate_query
from chat.graph_node_functions.viz import assess_visualization, create_graph

MAX_RETRIES = 2
MAX_SQL_RETRIES = 2

class GraphState(TypedDict):
    """State schema for LangGraph workflow."""
    messages: Annotated[List[BaseMessage], add_messages]  # Chat history
    user_query: str  # Current user question
    query_type: str  # "database", "context", "general"
    wants_visualization: bool  # Whether user explicitly wants a graph
    query_results: List[Dict]  # Results from database query
    sql_query: str  # SQL query executed
    query_explanation: str  # Planner summary / caveats for the SQL results
    graph_data: str  # Base64-encoded graph image
    visualization_status: str  # "created" | "not_created"
    visualization_decision: Dict[str, Any]  # Post-query visualization decision/chart spec
    context_data: str  # Results from RAG search
    citations: List[Dict[str, Any]]  # Structured citation objects for final response
    final_answer: str  # Final response to user


    # error handling
    validation_warnings: List[str]  # Validation warnings from answer validator
    retry_count: int  # Self-fix attempt counter for response grounding
    sql_retry_count: int  # Self-fix attempt counter for SQL quality
    query_error: str  # Error message from failed agent call (empty if ok)
    session_id: str  # Session identifier

class GraphNodes:
    """Encapsulates the nodes and logic for the LangGraph workflow."""

    def __init__(self, llm, agent_pool):
        self.llm = llm
        self.agent_pool = agent_pool
        self._graph_executor = ThreadPoolExecutor(max_workers=4)
        self._graph_futures: Dict[str, Any] = {}
        self._graph_lock = threading.Lock()


    def route_question(self, state: GraphState) -> GraphState:
        """Analyze question and determine which tool to use."""
        query = state["user_query"]

        # Use LLM to classify query type + detect visualization intent
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
        return query_sql(self, state)


    def query_validate_route(self, state: GraphState) -> Literal["retry_query", "continue"]:
        """After validate_query: decide if query should be retried or continue based on the state."""
        warnings = state.get("validation_warnings", [])
        
        # Check for query failures - these can't be retried
        query_failures = [w for w in warnings if "[QUERY_FAILED]" in w]
        if query_failures:
            print(f"[ROUTE] Query failed — cannot retry: {query_failures[0]}")
            return "continue"  # Continue to show error to user
        
        # Check for empty results - retry if we haven't exceeded max retries
        empty_result_issues = [w for w in warnings if "[EMPTY_RESULTS]" in w]
        if empty_result_issues and state.get("sql_retry_count", 0) < MAX_SQL_RETRIES:
            print(f"[ROUTE] Empty results detected, retrying query ({state.get('sql_retry_count', 0) + 1}/{MAX_SQL_RETRIES})")
            return "retry_query"
        
        # If we've exceeded retries or no issues, continue
        if empty_result_issues:
            print(f"[ROUTE] Max SQL retries reached — continuing with empty results")
        
        return "continue"

    # ========================================================
    # ROUTE NODES
    # ========================================================

    def route_after_gate(self, state: GraphState) -> Literal["blocked", "visualize", "respond"]:
        """After query validation: END if blocked, otherwise decide whether to visualize."""
        if state.get("query_error"):
            return "blocked"

        decision = state.get("visualization_decision", {})
        if decision.get("should_visualize"):
            return "visualize"
        return "respond"

    def assess_visualization(self, state: GraphState) -> GraphState:
        """Grounded post-query visualization decision."""
        return assess_visualization(self, state)

    def create_graph(self, state: GraphState) -> GraphState:
        """Kick off visualization creation in background for overlap with answer generation."""
        return create_graph(self, state)

    def query_budget_context(self, state: GraphState) -> GraphState:
        """Search budget context documents."""
        return query_budget_context(self, state)

    def generate_response(self, state: GraphState) -> GraphState:
        """Generate final answer based on gathered data. On retry, folds in validator feedback."""
        return generate_response(self, state)


    # ========================================================
    # VALIDATE NODES
    # ========================================================

    def validate_query(self, state: GraphState) -> GraphState:
        """Validate query: failures, empty results, result sanity."""
        return validate_query(state)

    def validate_answer(self, state: GraphState) -> GraphState:
        """Answer grounding validation: data and context hallucination checks."""
        return validate_answer(self, state)

    def handle_general(self, state: GraphState) -> GraphState:
        """Handle general conversation."""
        print(f"[NODE] Handling general conversation")

        response = self.llm.invoke([HumanMessage(content=state["user_query"])])
        state["final_answer"] = response.content
        state["citations"] = []

        return state

    def should_retry(self, state: GraphState) -> Literal["retry", "done"]:
        """Route based on validation issues: retry response or end.
        SQL retries are handled earlier by query_validate_route."""
        warnings = state.get("validation_warnings", [])

        # Query failures are not retryable and should have been handled already
        query_failures = [w for w in warnings if "[QUERY_FAILED]" in w]
        if query_failures:
            print(f"[SELF-FIX] Query failed — cannot auto-retry: {query_failures[0]}")

        # Check grounding issues (answer was wrong, but data was fine)
        grounding_issues = [w for w in warnings if "[DATA_GROUNDING]" in w or "[CONTEXT_GROUNDING]" in w]
        if grounding_issues and state.get("retry_count", 0) < MAX_RETRIES:
            print(f"[SELF-FIX] Grounding issues, retrying response ({state.get('retry_count', 0) + 1}/{MAX_RETRIES})")
            return "retry"

        if grounding_issues:
            print(f"[SELF-FIX] Max retries reached — {len(grounding_issues)} issue(s) remain")
        return "done"
