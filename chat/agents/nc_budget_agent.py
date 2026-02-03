#!/usr/bin/env python3
"""
NC Budget Agent - Unified MCP Server for SQL, Graph, and RAG tools.
Combines database queries, visualizations, and RAG search into one agent.
"""

import json
import sys
import threading
import os
import logging
from pathlib import Path
from typing import Any, Dict, List
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

# Add parent directory to path to import tools
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chat.tools import (
    SQL_TOOLS,
    GRAPH_TOOLS,
    RAG_TOOLS
)
from chat.tools.handlers import (
    handle_query_vendor_payments,
    handle_query_budget,
    handle_create_graph,
    handle_query_budget_context,
    handle_query_sql
)

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# AGENT STATE - Manages lazy-loaded models and clients
# ============================================================================

class AgentState:
    """Manages lazy-loaded models and clients for SQL, Graph, and RAG."""

    def __init__(self):
        """Initialize all clients"""
        # SQL - eager init, as soon as initialized
        print("[NC_BUDGET] Initializing SQL clients...", file=sys.stderr)
        self.llm_client = ChatGroq(
            model=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
            api_key=os.getenv("GROQ_KEY"),
            temperature=0.1
        )
        print("[NC_BUDGET] SQL clients ready", file=sys.stderr)

        # RAG: Initialize state variables first
        self._embedding_model = None
        self._reranker = None
        self._chroma_client = None
        self._llm_for_rag = None
        # semaphore for when RAG models (above) are ready
        self._rag_ready = threading.Event()

        # init RAG models in background with threading
        print("[NC_BUDGET] Starting RAG model loading in background...", file=sys.stderr)
        threading.Thread(target=self._load_rag_models, daemon=True).start()
        print("[NC_BUDGET] Agent ready! (RAG models loading in background)", file=sys.stderr)


    def _load_rag_models(self) -> None:
        """Load RAG models in background thread and signal when ready."""
        print("[NC_BUDGET] [RAG] Loading models (3GB+)...", file=sys.stderr)

        # Load models
        print("[NC_BUDGET] [RAG] Loading embedding model (1/3)...", file=sys.stderr)
        self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        print("[NC_BUDGET] [RAG] Loading reranker model (2/3)...", file=sys.stderr)
        self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        print("[NC_BUDGET] [RAG] Loading ChromaDB (3/3)...", file=sys.stderr)
        db_path = Path(__file__).parent.parent.parent / "db"
        self._chroma_client = chromadb.PersistentClient(path=str(db_path))

        # Create separate LLM client for RAG
        self._llm_for_rag = ChatGroq(
            model=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
            api_key=os.getenv("GROQ_KEY"),
            temperature=0.3
        )

        # Signal that models are ready
        self._rag_ready.set()
        print("[NC_BUDGET] [RAG] Models loaded successfully!", file=sys.stderr)


# Global agent state instance
_agent_state = AgentState()


# ============================================================================
# MCP PROTOCOL FUNCTIONS
# ============================================================================

def send_json(response: Dict[str, Any]) -> None:
    """Send a JSON response to stdout."""
    print(json.dumps(response), flush=True)


def handle_tools_list() -> Dict[str, Any]:
    """Handle tools/list request - return all 9 tools."""
    all_tools = SQL_TOOLS + GRAPH_TOOLS + RAG_TOOLS
    return {"tools": all_tools}


def handle_tools_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/call request - direct dispatch to handler functions."""
    try:
        # Route to appropriate handler based on tool name
        if tool_name == "query_vendor_payments":
            return handle_query_vendor_payments(arguments)
        elif tool_name == "query_budget":
            return handle_query_budget(arguments)
        elif tool_name == "create_graph":
            return handle_create_graph(arguments)
        elif tool_name == "query_sql":
            return handle_query_sql(arguments, _agent_state)
        elif tool_name == "query_budget_context":
            return handle_query_budget_context(arguments, _agent_state)
        else:
            # Unknown tool
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True
            }

    except Exception as e:
        logger.error(f"[NC_BUDGET] Error in handle_tools_call for {tool_name}: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "isError": True
        }


# ============================================================================
# MAIN MCP SERVER LOOP
# ============================================================================

def run_nc_budget_agent():
    """Run the unified NC Budget Agent MCP server loop."""
    # Send server info on startup
    send_json({
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "nc-budget-agent",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }
    })

    # Main request loop
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            request = json.loads(line)

            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id")

            if method == "tools/list":
                response = handle_tools_list()
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                response = handle_tools_call(tool_name, arguments)
            else:
                response = {
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            # Send response
            send_json({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response
            })

        except Exception as e:
            send_json({
                "jsonrpc": "2.0",
                "id": request.get("id") if 'request' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": f"[NC_BUDGET] Internal error: {str(e)}"
                }
            })


if __name__ == "__main__":
    run_nc_budget_agent()