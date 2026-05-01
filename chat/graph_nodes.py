"""
Graph nodes and state definition for the Claude agent system.
"""
import json
import sys
import threading
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, TypedDict, Annotated, Literal, Optional
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
                    "chart_spec": tool_input.get("chart_spec"),
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

    def _build_sql_citations(self, state: GraphState) -> List[Dict[str, Any]]:
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
                "detail": "data/vendor_data.csv; data/Key value - Payment 1y.csv; data/Key value - Payment 1ya.csv"
            })
        elif " budget" in sql_lower or "from budget" in sql_lower:
            citations.append({
                "id": 0,
                "kind": "sql",
                "title": "Budget CSV Sources",
                "detail": "data/budget_data.csv; data/budget2024.csv"
            })
        else:
            citations.append({
                "id": 0,
                "kind": "sql",
                "title": "Database Source",
                "detail": "SQLite tables populated from project CSV files in data/"
            })

        return citations

    def _extract_rag_citations(self, state: GraphState) -> List[Dict[str, Any]]:
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
                "detail": citation.get("detail", "")
            })
        return citations

    def _build_citations(self, state: GraphState) -> List[Dict[str, Any]]:
        """Compose and re-index citations for final response."""
        # RAG-only citations for now. SQL/source-provenance mapping will be added later.
        combined = self._extract_rag_citations(state)
        for idx, citation in enumerate(combined, 1):
            citation["id"] = idx
        return combined

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
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

    def _default_visualization_decision(self, state: GraphState, requested: bool = False) -> Dict[str, Any]:
        """Fallback visualization decision."""
        decision: Dict[str, Any] = {
            "should_visualize": False,
            "chart_type": "",
            "x_field": "",
            "y_field": "",
            "analysis_goal": "",
            "title": "",
            "no_graph_explanation": ""
        }
        if requested:
            decision["no_graph_explanation"] = (
                "I couldn't identify a graph that would clarify these results without being misleading or redundant."
            )
        return decision

    def _normalize_visualization_decision(self, raw: Dict[str, Any], requested: bool) -> Dict[str, Any]:
        """Normalize LLM decision output to the internal schema."""
        decision = self._default_visualization_decision({}, requested=requested)

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
                return self._default_visualization_decision({}, requested=requested)
            return decision

        if requested and not decision["no_graph_explanation"]:
            decision["no_graph_explanation"] = (
                "I couldn't identify a graph that would clarify these results without being misleading or redundant."
            )
        return decision


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

        decision = state.get("visualization_decision", {})
        if decision.get("should_visualize"):
            return "visualize"
        return "respond"

    def assess_visualization(self, state: GraphState) -> GraphState:
        """Grounded post-query visualization decision."""
        if state.get("query_error"):
            state["visualization_decision"] = self._default_visualization_decision(
                state,
                requested=state.get("wants_visualization", False)
            )
            return state

        results = state.get("query_results", [])
        requested = state.get("wants_visualization", False)
        if not results:
            state["visualization_decision"] = self._default_visualization_decision(
                state,
                requested=requested
            )
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

        response = self.llm.invoke([HumanMessage(content=prompt)])
        parsed = self._extract_json_object(str(response.content))
        if parsed is None:
            state["visualization_decision"] = self._default_visualization_decision(state, requested=requested)
        else:
            state["visualization_decision"] = self._normalize_visualization_decision(parsed, requested=requested)

        print(f"[NODE] Visualization decision: {state['visualization_decision']}")
        return state

    def create_graph(self, state: GraphState) -> GraphState:
        """Kick off visualization creation in background for overlap with answer generation."""
        print(f"[NODE] Creating visualization for {len(state['query_results'])} rows")
        session_id = state.get("session_id", "default")
        graph_state = deepcopy(state)

        def _graph_job() -> str:
            result = self._call_agent_tool(
                "create_graph",
                {
                    "data": graph_state.get("query_results", []),
                    "sql_query": graph_state.get("sql_query", ""),
                    "chart_spec": graph_state.get("visualization_decision", {}),
                    "title": graph_state.get("visualization_decision", {}).get("title")
                },
                graph_state.get("session_id", "default")
            )

            if result.get("success"):
                tool_result = result.get("result", {})
                if isinstance(tool_result, dict):
                    return tool_result.get("graph") or ""
            return ""

        with self._graph_lock:
            previous = self._graph_futures.pop(session_id, None)
            if previous and not previous.done():
                previous.cancel()
            self._graph_futures[session_id] = self._graph_executor.submit(_graph_job)

        print(f"[NODE] Graph generation started in background")

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
                state["citations"] = []
            elif isinstance(tool_result, dict):
                state["context_data"] = json.dumps(tool_result)
                state["citations"] = self._extract_rag_citations(state)
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

        # check for rag context data
        if state.get("context_data"):
            context_parts.append(f"\nContext Information:\n{state['context_data']}")

        # combine all parts
        context = "\n\n".join(context_parts)
        citations = self._build_citations(state)
        state["citations"] = citations
        citation_map = "\n".join([f"[{c['id']}] {c['title']} — {c['detail']}" for c in citations]) if citations else "None"

        # Generate answer
        prompt = f"""Based on the following data, answer the user's question concisely and clearly.

User Question: {state['user_query']}

Data:
{context}

Available Citations:
{citation_map}

Instructions:
- Provide a clear, direct answer
- Reference specific numbers/facts from the data
- Do not state whether a visualization was created
- Add inline citation markers like [1], [2] for factual claims when citations are available
- Keep the answer concise (2-4 sentences)
{correction_prompt}"""

        # invoke an llm response
        response = self.llm.invoke([HumanMessage(content=prompt)])
        state["final_answer"] = response.content

        decision = state.get("visualization_decision", {})
        if (
            state.get("wants_visualization", False)
            and not decision.get("should_visualize")
            and decision.get("no_graph_explanation")
        ):
            state["final_answer"] = f"{state['final_answer']} {decision['no_graph_explanation']}".strip()

        # If a background graph job exists for this session, resolve it now.
        session_id = state.get("session_id", "default")
        graph_future = None
        with self._graph_lock:
            graph_future = self._graph_futures.pop(session_id, None)

        if graph_future is not None:
            try:
                graph_data = graph_future.result()
                if graph_data:
                    state["graph_data"] = graph_data
                    print(f"[NODE] Graph created successfully")
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
