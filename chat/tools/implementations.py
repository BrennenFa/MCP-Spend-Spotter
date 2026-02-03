#!/usr/bin/env python3
"""Tool implementation functions."""

import sqlite3
import json
from pathlib import Path
from typing import Any, List, Dict
from chat.agent_functions.graph_generator import generate_graph
import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer, CrossEncoder
from chat.agent_functions.rag.retriever import HybridRetriever
from chat.agent_functions.rag.keyword_extractor import KeywordExtractor
from chat.agent_functions.rag.synthesizer import RAGSynthesizer

# Database paths
SCRIPT_DIR = Path(__file__).parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_DIR = PROJECT_ROOT / "db"

VENDOR_DB = DB_DIR / "vendor.db"
BUDGET_DB = DB_DIR / "budget.db"

# RAG components (lazy initialization)
_rag_retriever = None
_keyword_extractor = None
_rag_synthesizer = None


def get_rag_components():
    """Lazy initialization of RAG components."""
    global _rag_retriever, _keyword_extractor, _rag_synthesizer

    if _rag_retriever is None:

        # Load models once
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        # Initialize ChromaDB
        db_path = Path(__file__).parent.parent.parent / "db"
        chroma_client = chromadb.PersistentClient(path=str(db_path))
        collection = chroma_client.get_collection("budget_documents")

        _rag_retriever = HybridRetriever(collection, embedding_model, reranker)
        _keyword_extractor = KeywordExtractor()
        _rag_synthesizer = RAGSynthesizer()

    return _rag_retriever, _keyword_extractor, _rag_synthesizer


# Database query functions
def execute_vendor_query(query: str) -> list[dict]:
    """Execute a SELECT query on vendor database."""
    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    conn = sqlite3.connect(VENDOR_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        return results
    finally:
        conn.close()


def execute_budget_query(query: str) -> list[dict]:
    """Execute a SELECT query on budget database."""
    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    conn = sqlite3.connect(BUDGET_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        return results
    finally:
        conn.close()


def create_graph_from_results(results: List[Dict], query: str, title: str = None) -> Dict[str, Any]:
    """
    Create a graph from query results.

    Args:
        results: Query results as list of dicts
        query: SQL query that generated the results
        title: Optional custom title

    Returns:
        Dict with base64 image and metadata
    """
    if not results:
        return {
            "graph": None
        }

    try:
        # Generate the graph
        image_base64 = generate_graph(results, query=query, graph_type="auto", title=title)

        if not image_base64:
            return {
                "graph": None
            }

        return {
            "graph": image_base64,
            "format": "png",
            "encoding": "base64",
            "row_count": len(results)
        }
    except Exception as e:
        return {
            "graph": None
        }


def query_budget_context(query: str, chat_history: list = None) -> Dict[str, Any]:
    """
    Hybrid search + reranking + LLM synthesis for budget clarification questions.

    Args:
        query: User's question about budget concepts, policies, or terminology
        chat_history: List of previous messages for context (optional)

    Returns:
        {
            "answer": str,           # Synthesized explanation with citations
            "chunks_used": int,      # Number of chunks retrieved
            "keywords_found": dict,  # Extracted keywords by category
            "sources": List[str]     # Section headers cited
        }
    """
    retriever, extractor, synthesizer = get_rag_components()

    try:
        # Use chat_history passed from claude_main (or empty list)
        if chat_history is None:
            chat_history = []

        # 1. Extract keywords from query
        keywords = extractor.extract(query)

        # 2. Retrieve chunks with hybrid search + reranking
        chunks = retriever.retrieve(query, extracted_keywords=keywords, top_k=5)

        # 3. Synthesize answer with LLM
        answer, tokens = synthesizer.synthesize(query, chunks, chat_history)

        # 6. Extract sources from chunks
        sources = []
        for chunk in chunks:
            section = chunk['metadata'].get('Section', 'Unknown')
            subsection = chunk['metadata'].get('SubSection', '')
            source = section
            if subsection:
                source += f" > {subsection}"
            sources.append(source)

        return {
            "answer": answer,
            "chunks_used": len(chunks),
            "keywords_found": keywords,
            "sources": sources
        }

    except Exception as e:
        return {
            "answer": f"Error retrieving budget context: {str(e)}",
            "chunks_used": 0,
            "keywords_found": {},
            "sources": [],
            "error": str(e)
        }
