"""Keyword extraction using keywords.json string matching (aligned with ingestion)."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


class KeywordExtractor:
    """Extract budget-related entities from user queries using string matching."""

    def __init__(self):
        """Initialize keyword extractor by loading keywords.json."""
        # Path logic aligned with your directory structure
        keywords_path = Path(__file__).parent.parent.parent.parent / "keywords" / "keywords.json"
        try:
            with open(keywords_path, 'r') as f:
                self.keywords_data = json.load(f)
        except Exception as e:
            print(f"[NC_BUDGET] [RAG] Error loading keywords.json: {e}", file=sys.stderr)
            self.keywords_data = {}

    def extract(self, query: str, *args, **kwargs) -> Dict[str, List[str]]:
        """
        Extract keywords from query matching categories in keywords.json.
        Matches the logic used in the ingestion pipeline.
        
        The *args and **kwargs handle the 'llm' object being passed by the 
        agent without crashing the function.
        """
        if not isinstance(query, str):
            return {}

        query_lower = query.lower()
        extracted = {}

        for category, keywords in self.keywords_data.items():
            # Use substring matching identical to process_chunk_keywords
            # (But improved to catch keywords regardless of surrounding spaces)
            found = [
                kw for kw in keywords
                if kw.lower() in query_lower
            ]

            if found:
                extracted[category] = found

        return extracted