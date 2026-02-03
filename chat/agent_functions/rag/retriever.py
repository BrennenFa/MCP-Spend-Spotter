"""Hybrid retriever with keyword filtering and cross-encoder reranking."""

import sys
from typing import List, Dict, Any


class HybridRetriever:
    """hybrid retriever with reranking."""

    def __init__(self, collection, embedding_model, reranker):
        """
        Initialize retriever with pre-loaded models.

        Args:
            collection: ChromaDB collection
            embedding_model: SentenceTransformer model
            reranker: CrossEncoder model
        """
        self.collection = collection
        self.embedding_model = embedding_model
        self.reranker = reranker

    def retrieve(
        self,
        query: str,
        extracted_keywords: Dict[str, List[str]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval: filtered + unfiltered semantic search + reranking.

        Follows Epstein model:
        1. Filtered search (if keywords found): semantic + metadata filter
        2. Unfiltered search: pure semantic
        3. Merge and deduplicate
        4. Rerank with cross-encoder
        5. Return top K

        Args:
            query: User query
            extracted_keywords: Dict of {category: [keywords]} from keyword extractor
            top_k: Final number of chunks to return after reranking

        Returns:
            List of {text, metadata, rerank_score} dicts
        """
        # Encode query
        query_embedding = self.embedding_model.encode(query).tolist()

        # Filtered search (if keywords found)
        filtered_results = {}
        if extracted_keywords:
            where_filter = self._build_where_filter(extracted_keywords)
            try:
                filtered_results = self.collection.query(
                    query_embeddings=[query_embedding],
                    where=where_filter,
                    n_results=5
                )
            except Exception as e:
                print(f"[Retriever] Warning: Filtered search failed: {e}", file=sys.stderr)
                filtered_results = {}

        # Unfiltered search (pure semantic)
        unfiltered_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )

        # Combine and deduplicate
        combined_chunks = self._merge_results(
            filtered_results,
            unfiltered_results
        )

        if not combined_chunks:
            return []

        # Rerank with cross-encoder
        reranked = self._rerank(query, combined_chunks, top_k)

        return reranked

    def _build_where_filter(
        self,
        extracted_keywords: Dict[str, List[str]]
    ) -> Dict:
        """
        Build ChromaDB where filter for keyword matching.

        Handles comma-separated metadata strings with $contains operator.

        Example:
            extracted_keywords = {
                "agencies": ["department of labor", "dhhs"],
                "committees": ["education"]
            }

        Returns:
            {
                "$or": [
                    {"agencies": {"$contains": "department of labor"}},
                    {"agencies": {"$contains": "dhhs"}},
                    {"committees": {"$contains": "education"}}
                ]
            }
        """
        conditions = []
        for category, keywords in extracted_keywords.items():
            for keyword in keywords:
                conditions.append({
                    category: {"$contains": keyword.lower()}
                })

        if len(conditions) == 1:
            return conditions[0]
        return {"$or": conditions}

    def _merge_results(
        self,
        filtered: Dict,
        unfiltered: Dict
    ) -> List[Dict[str, Any]]:
        """
        Merge and deduplicate results from filtered and unfiltered searches.

        Args:
            filtered: ChromaDB query results from filtered search
            unfiltered: ChromaDB query results from unfiltered search

        Returns:
            List of unique chunks with text, metadata, distance
        """
        merged = {}

        # Add filtered results
        if filtered and 'ids' in filtered and filtered['ids']:
            for i, doc_id in enumerate(filtered['ids'][0]):
                merged[doc_id] = {
                    'text': filtered['documents'][0][i],
                    'metadata': filtered['metadatas'][0][i],
                    'distance': filtered['distances'][0][i]
                }

        # Add unfiltered results (skip duplicates)
        for i, doc_id in enumerate(unfiltered['ids'][0]):
            if doc_id not in merged:
                merged[doc_id] = {
                    'text': unfiltered['documents'][0][i],
                    'metadata': unfiltered['metadatas'][0][i],
                    'distance': unfiltered['distances'][0][i]
                }

        return list(merged.values())

    def _rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Rerank chunks using cross-encoder for improved relevance.

        Args:
            query: User query
            chunks: List of chunks from semantic search
            top_k: Number of top chunks to return

        Returns:
            Top K chunks sorted by rerank_score (descending)
        """
        if not chunks:
            return []

        # Prepare pairs for cross-encoder
        pairs = [[query, chunk['text']] for chunk in chunks]

        # Get scores
        scores = self.reranker.predict(pairs)

        # Add scores and sort
        for chunk, score in zip(chunks, scores):
            chunk['rerank_score'] = float(score)

        ranked = sorted(chunks, key=lambda x: x['rerank_score'], reverse=True)

        return ranked[:top_k]
