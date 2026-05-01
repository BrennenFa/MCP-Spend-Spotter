"""Tests for post-query visualization gating."""

from types import SimpleNamespace

from chat.graph_nodes import GraphNodes


class StubLLM:
    """Return a fixed response payload for visualization prompts."""

    def __init__(self, content: str):
        self.content = content

    def invoke(self, _messages):
        return SimpleNamespace(content=self.content)


class DummyAgentPool:
    """Placeholder agent pool for GraphNodes tests."""

    def get_agent(self, _name):
        raise AssertionError("Agent access is not expected in these tests")


def make_state(**overrides):
    """Build a minimal graph state for visualization tests."""
    state = {
        "messages": [],
        "user_query": "Show me a graph of top agencies by spending",
        "query_type": "database",
        "wants_visualization": True,
        "query_results": [
            {"agency": "Transportation", "total_amount": 9000000},
            {"agency": "Education", "total_amount": 8000000},
            {"agency": "Health", "total_amount": 7000000},
        ],
        "sql_query": "SELECT agency, total_amount FROM budget",
        "graph_data": "",
        "visualization_status": "not_created",
        "visualization_decision": {},
        "context_data": "",
        "citations": [],
        "final_answer": "",
        "validation_warnings": [],
        "retry_count": 0,
        "sql_retry_count": 0,
        "query_error": "",
        "session_id": "test-session",
    }
    state.update(overrides)
    return state


class TestVisualizationGate:
    """Test post-query visualization decision behavior."""

    def test_assess_visualization_accepts_valid_spec(self):
        llm = StubLLM(
            """
            {
              "should_visualize": true,
              "chart_type": "bar",
              "x_field": "agency",
              "y_field": "total_amount",
              "analysis_goal": "compare agency spending",
              "title": "Agency Spending",
              "no_graph_explanation": ""
            }
            """
        )
        nodes = GraphNodes(llm, DummyAgentPool())
        state = make_state()

        updated = nodes.assess_visualization(state)

        assert updated["visualization_decision"]["should_visualize"] is True
        assert updated["visualization_decision"]["x_field"] == "agency"
        assert updated["visualization_decision"]["y_field"] == "total_amount"

    def test_assess_visualization_returns_explanation_for_ungraphable_explicit_request(self):
        llm = StubLLM(
            """
            {
              "should_visualize": false,
              "chart_type": "",
              "x_field": "",
              "y_field": "",
              "analysis_goal": "",
              "title": "",
              "no_graph_explanation": "These rows are too granular to support a meaningful chart."
            }
            """
        )
        nodes = GraphNodes(llm, DummyAgentPool())
        state = make_state(query_results=[{"vendor": "A", "invoice": "1", "payment": "$10.00"}])

        updated = nodes.assess_visualization(state)

        assert updated["visualization_decision"]["should_visualize"] is False
        assert "meaningful chart" in updated["visualization_decision"]["no_graph_explanation"].lower()

    def test_route_after_gate_uses_visualization_decision(self):
        nodes = GraphNodes(StubLLM("{}"), DummyAgentPool())

        assert nodes.route_after_gate(make_state(visualization_decision={"should_visualize": True})) == "visualize"
        assert nodes.route_after_gate(make_state(visualization_decision={"should_visualize": False})) == "respond"
