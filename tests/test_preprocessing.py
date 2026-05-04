"""Tests for preprocessing helpers."""

from preprocessing.agency_normalizer import normalize_agency
from preprocessing.entity_classifier import EntityTypeClassifier


class StubLLM:
    """Return a fixed classification payload."""

    def __init__(self, content: str):
        self.content = content

    def invoke(self, _prompt):
        class Response:
            def __init__(self, content: str):
                self.content = content
        return Response(self.content)


class TestAgencyNormalizer:
    """Test agency normalization behavior."""

    def test_rolls_transportation_to_parent(self):
        normalized = normalize_agency("Department of Transportation")
        assert normalized["parent_agency"] == "Department Of Transportation"

    def test_marks_transportation_subagency(self):
        normalized = normalize_agency("Department of Transportation Rail Division")
        assert normalized["parent_agency"] == "Department Of Transportation"
        assert normalized["sub_agency"] == "Department Of Transportation Rail Division"


class TestEntityClassifier:
    """Test batched LLM parsing."""

    def test_classify_entities_parses_llm_output(self):
        llm = StubLLM(
            """
            {
              "classifications": [
                {
                  "name": "EMPLOYEE REIMBURSEMENT",
                  "canonical_entity_name": "EMPLOYEE REIMBURSEMENT",
                  "entity_type": "internal_or_unknown",
                  "entity_type_confidence": 0.98
                }
              ]
            }
            """
        )
        classifier = EntityTypeClassifier(llm_client=llm, batch_size=10)
        contexts = {
            "EMPLOYEE REIMBURSEMENT": {
                "major_categories": ["OTHER EXPENSES AND ADJUSTMENTS"],
                "account_descriptions": ["TRAVEL REIMBURSEMENT"],
                "agencies": ["Department of Transportation"],
            }
        }

        result = classifier.classify_entities(contexts)

        assert result["EMPLOYEE REIMBURSEMENT"]["entity_type"] == "internal_or_unknown"
        assert result["EMPLOYEE REIMBURSEMENT"]["entity_type_source"] == "llm"
