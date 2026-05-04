"""LLM-assisted entity classification for vendor payees."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from langchain_groq import ChatGroq


EntityContext = Dict[str, Any]
EntityClassification = Dict[str, Any]


class EntityTypeClassifier:
    """Classify payees into entity types using an LLM in batches."""

    def __init__(
        self,
        llm_client: Optional[ChatGroq] = None,
        batch_size: int = 20,
    ) -> None:
        self.llm_client = llm_client or ChatGroq(
            model=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
            api_key=os.getenv("GROQ_KEY"),
            temperature=0,
        )
        self.batch_size = batch_size

    def classify_entities(self, entity_contexts: Dict[str, EntityContext]) -> Dict[str, EntityClassification]:
        """Classify each distinct payee using sampled row context."""
        classifications: Dict[str, EntityClassification] = {}
        names = list(entity_contexts.keys())
        for start in range(0, len(names), self.batch_size):
            batch_names = names[start:start + self.batch_size]
            batch_payload = [
                {
                    "name": name,
                    "sample_major_categories": entity_contexts[name].get("major_categories", [])[:3],
                    "sample_account_descriptions": entity_contexts[name].get("account_descriptions", [])[:3],
                    "sample_agencies": entity_contexts[name].get("agencies", [])[:3],
                }
                for name in batch_names
            ]
            parsed = self._classify_batch(batch_payload)
            for name in batch_names:
                classifications[name] = parsed.get(name, {
                    "canonical_entity_name": name,
                    "entity_type": "unknown",
                    "entity_type_confidence": 0.0,
                    "entity_type_source": "llm_unparsed",
                })
        return classifications

    def _classify_batch(self, batch_payload: List[Dict[str, Any]]) -> Dict[str, EntityClassification]:
        """Classify one batch and return a name-keyed mapping."""
        prompt = f"""Classify each North Carolina payee into an entity type using the provided context.

Allowed entity_type values:
- vendor
- benefit_recipient
- claimant
- grant_recipient
- internal_or_unknown

Instructions:
- Use the payee name plus sample spending context.
- Buckets like employee reimbursements, claimants, benefit recipients, commissioners, and internal government entities should not be classified as vendor.
- If unsure, choose internal_or_unknown rather than vendor.
- canonical_entity_name should be a cleaned version of the payee name, but do not invent a different entity.
- confidence must be a number from 0.0 to 1.0.

Return strict JSON only in this form:
{{
  "classifications": [
    {{
      "name": "...",
      "canonical_entity_name": "...",
      "entity_type": "vendor",
      "entity_type_confidence": 0.91
    }}
  ]
}}

Payload:
{json.dumps(batch_payload, indent=2)}"""

        response = self.llm_client.invoke(prompt)
        parsed = self._extract_json_object(str(response.content))
        results: Dict[str, EntityClassification] = {}
        if not parsed:
            return results

        classifications = parsed.get("classifications", [])
        if not isinstance(classifications, list):
            return results

        for item in classifications:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            confidence = item.get("entity_type_confidence", 0.0)
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (TypeError, ValueError):
                confidence = 0.0
            results[name] = {
                "canonical_entity_name": str(item.get("canonical_entity_name", name)).strip() or name,
                "entity_type": str(item.get("entity_type", "internal_or_unknown")).strip(),
                "entity_type_confidence": confidence,
                "entity_type_source": "llm",
            }
        return results

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object from model output."""
        if not text:
            return None

        text = text.strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
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
