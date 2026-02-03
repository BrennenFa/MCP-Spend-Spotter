"""RAG query orchestration - handles the full RAG pipeline."""

import logging
import json
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


def query_budget_context(
    query: str,
    chat_history: List[Dict],
    embedding_model,
    reranker,
    chroma_client,
    llm
) -> Dict[str, Any]:
    """
    Execute full RAG pipeline: keyword extraction -> retrieval -> synthesis.

    Args:
        query: User's question about budget concepts
        chat_history: Previous conversation context
        embedding_model: SentenceTransformer model for embeddings
        reranker: CrossEncoder model for reranking
        chroma_client: ChromaDB client
        llm: ChatGroq LLM client

    Returns:
        Dict with answer and metadata
    """
    try:
        # Import RAG components
        from .retriever import HybridRetriever
        from .synthesizer import RAGSynthesizer
        from .keyword_extractor import KeywordExtractor

        # Extract keywords from query
        logger.info(f"[RAG] Extracting keywords from: {query}")
        extractor = KeywordExtractor()
        keywords = extractor.extract(query, llm)

        # Retrieve relevant chunks
        logger.info(f"[RAG] Retrieving context...")
        collection = chroma_client.get_collection("budget_documents")
        retriever = HybridRetriever(collection, embedding_model, reranker)
        chunks = retriever.retrieve(
            query=query,
            extracted_keywords=keywords,
            top_k=5
        )

        # Synthesize answer
        logger.info(f"[RAG] Synthesizing answer...")
        synthesizer = RAGSynthesizer()
        answer, tokens = synthesizer.synthesize(
            query=query,
            chunks=chunks,
            chat_history=chat_history
        )

        return {
            "answer": answer,
            "chunks_used": len(chunks),
            "keywords": keywords
        }

    except Exception as e:
        logger.error(f"[RAG] Error in query_budget_context: {e}")
        import traceback
        traceback.print_exc()
        raise
