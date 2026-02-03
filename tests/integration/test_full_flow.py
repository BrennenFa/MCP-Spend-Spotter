"""
Integration tests - test full workflows with real components.
Mark these as slow since they may involve real database queries.
"""
import pytest


@pytest.mark.integration
@pytest.mark.slow
class TestFullQueryFlow:
    """Test complete query flow from natural language to results."""

    @pytest.mark.skip(reason="Requires real database - enable when DB is available")
    def test_end_to_end_vendor_query(self):
        """Test complete flow: natural language -> SQL -> execution -> results."""
        # This would test the full pipeline with real database
        # Enable this when you want to test against actual data
        pass

    @pytest.mark.skip(reason="Requires real database - enable when DB is available")
    def test_end_to_end_budget_query(self):
        """Test budget query flow with real database."""
        pass


@pytest.mark.integration
@pytest.mark.slow
class TestRAGIntegration:
    """Test RAG system with real models (slow)."""

    @pytest.mark.skip(reason="Requires model loading - enable for full integration tests")
    def test_rag_query_with_real_models(self):
        """Test RAG query with actual embedding models and ChromaDB."""
        # This would test RAG with real models
        # Mark as slow since it loads ~3GB of models
        pass


@pytest.mark.integration
class TestAgentStartup:
    """Test that the agent can start without crashing."""

    def test_agent_state_initialization_without_rag(self):
        """Test that AgentState can initialize SQL components."""
        # You could test basic initialization here
        # Make sure to mock out the expensive RAG loading
        pass
