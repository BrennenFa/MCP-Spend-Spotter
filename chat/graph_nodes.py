"""
Graph nodes and state definition for the Claude agent system.
"""
import json
import sys
from typing import Dict, Any, List, TypedDict, Annotated, Literal
from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.graph.message import add_messages
from chat.session_manager import session_manager
from chat.agent_functions.validators import (
    validate_query_results,
    validate_data_grounding,
    validate_context_grounding
)

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
    graph_data: str  # Base64-encoded graph image
    context_data: str  # Results from RAG search
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

    def _call_agent_tool(self, tool_name: str, tool_input: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Call a tool via the unified NC Budget agent."""
        try:
            # Get chat history
            all_history = session_manager.get_messages_dict(session_id)
            chat_history = all_history[-4:]

            agent = self.agent_pool.get_agent("nc_budget")

            # Prepare arguments for tool
            if tool_name == "query_sql":
                arguments = {
                    "query": tool_input["query"],
                    "chat_history": chat_history,
                    "previous_sql": tool_input.get("previous_sql", ""),
                    "sql_warnings": tool_input.get("sql_warnings", [])
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
            
            # Check if result indicates an error (blocked SQL returns dict with explanation)
            if isinstance(result, dict) and "explanation" in result:
                explanation = result.get("explanation", "")
                if "blocked for safety" in explanation.lower():
                    return {"success": False, "error": explanation}
            
            return {"success": True, "result": result}

        except Exception as e:
            return {"success": False, "error": str(e)}


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


    # ========================================================
    # QUERY NODES
    # ========================================================
    def query_sql(self, state: GraphState) -> GraphState:
        """Execute database query."""
        # Increment retry count if this is a retry
        if state.get("sql_query"):
            state["sql_retry_count"] = state.get("sql_retry_count", 0) + 1
            print(f"[NODE] Retrying database query (attempt {state['sql_retry_count']}): {state['user_query']}")
        else:
            print(f"[NODE] Querying database: {state['user_query']}")

        result = self._call_agent_tool(
            "query_sql",
            {
                "query": state["user_query"],
                "previous_sql": state.get("sql_query", ""),
                "sql_warnings": []
            },
            state["session_id"]
        )

        if result.get("success"):
            tool_result = result.get("result", {})
            if isinstance(tool_result, dict):
                state["query_results"] = tool_result.get("results", [])
                state["sql_query"] = tool_result.get("query", "")
                state["query_error"] = ""
                print(f"[NODE] Retrieved {len(state['query_results'])} rows")
        else:
            state["query_error"] = result.get("error", "Unknown query execution error")
            print(f"[NODE] Query failed: {state['query_error']}")

        return state


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

        results = state.get("query_results", [])
        wants_viz = state.get("wants_visualization", False)
        if wants_viz or len(results) > 4:
            return "visualize"
        return "respond"

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

        if result.get("success"):  # Check if agent call succeeded
            tool_result = result.get("result", {})  # Extract already-parsed result
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


    # ========================================================
    # VALIDATE NODES
    # ========================================================

    def validate_query(self, state: GraphState) -> GraphState:
        """Validate query: failures, empty results, result sanity."""
        print(f"[NODE] Validating query results...")

        state["validation_warnings"] = validate_query_results(
            state.get("query_results", []),
            state.get("sql_query", ""),
            state.get("query_error", "")
        )

        print(f"[NODE] Query validation complete ({len(state['validation_warnings'])} warnings)")
        return state



    def validate_answer(self, state: GraphState) -> GraphState:
        """Answer grounding validation: data and context hallucination checks."""
        print(f"[NODE] Validating answer grounding...")

        # Preserve warnings already set by validate_query
        warnings = list(state.get("validation_warnings", []))

        # Data grounding — check answer facts against query results
        if state.get("query_results") and state.get("final_answer"):
            data_warnings = validate_data_grounding(
                state["final_answer"],
                state["query_results"],
                state["sql_query"],
                self.llm
            )
            warnings.extend(data_warnings)

        # Context grounding — check answer facts against RAG context
        if state.get("context_data") and state.get("final_answer"):
            context_warnings = validate_context_grounding(
                state["final_answer"],
                state["context_data"],
                self.llm
            )
            warnings.extend(context_warnings)

        # Print all warnings to stderr
        for warning in warnings:
            print(warning, file=sys.stderr)

        state["validation_warnings"] = warnings
        print(f"[NODE] Answer validation complete ({len(warnings)} warnings)")
        return state

    def handle_general(self, state: GraphState) -> GraphState:
        """Handle general conversation."""
        print(f"[NODE] Handling general conversation")

        response = self.llm.invoke([HumanMessage(content=state["user_query"])])
        state["final_answer"] = response.content

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