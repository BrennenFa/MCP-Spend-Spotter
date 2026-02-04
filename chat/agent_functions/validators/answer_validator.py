"""Answer grounding validators for LangGraph workflow."""

import json
import logging
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


def validate_data_grounding(
    final_answer: str,
    query_results: List[Dict],
    sql_query: str,
    llm
) -> List[str]:
    """
    Check if answer facts exist in query_results.

    Uses LLM to extract claims from answer and verify against data:
    - Dollar amounts mentioned
    - Vendor/agency names
    - Numerical facts (counts, rankings, etc.)

    Args:
        final_answer: The LLM-generated response text
        query_results: Actual database records returned
        sql_query: SQL query that was executed
        llm: LLM client for fact extraction

    Returns:
        List of warnings for hallucinated data (empty if valid)
    """
    warnings = []

    if not final_answer or not query_results:
        return warnings

    try:
        # Build fact-checking prompt
        fact_check_prompt = f"""You are a fact-checker. Compare the answer against the source data and identify any hallucinations.

ANSWER:
{final_answer}

SOURCE DATA (from database query):
{json.dumps(query_results[:20], indent=2)}  # Limit to first 20 rows for context

TASK:
Identify any specific factual claims in the answer that DO NOT appear in the source data.
Focus on:
- Vendor names, agency names, or other proper nouns
- Dollar amounts or numerical values
- Rankings, counts, or aggregates (e.g., "top 10", "total of X")
- Dates or fiscal years

RULES:
- Allow reasonable rounding (e.g., $1,234,567.89 → "$1.2 million" is OK)
- Allow abbreviations (e.g., "Department of Health" → "Health Dept" is OK)
- Only flag CLEAR hallucinations where data doesn't exist in source

OUTPUT FORMAT:
If all facts are accurate: Respond with exactly "VALID"
If hallucinations found: List each one on a new line as:
HALLUCINATION: <wrong claim> | CORRECT: <what the source data actually shows>

Your response:"""

        # Call LLM to fact-check
        response = llm.invoke([HumanMessage(content=fact_check_prompt)])
        fact_check_result = response.content.strip()

        # Parse result
        if fact_check_result.upper() != "VALID":
            # Extract hallucination lines
            for line in fact_check_result.split('\n'):
                if line.strip().startswith('HALLUCINATION:'):
                    hallucination = line.replace('HALLUCINATION:', '').strip()
                    warnings.append(f"[DATA_GROUNDING] WARNING: {hallucination}")

    except Exception as e:
        logger.error(f"[DATA_GROUNDING] Error during validation: {e}")
        warnings.append(f"[DATA_GROUNDING] WARNING: Validation failed due to error: {str(e)}")

    return warnings


def validate_context_grounding(
    final_answer: str,
    context_data: str,
    llm
) -> List[str]:
    """
    Check if RAG answer only uses context_data.

    Uses LLM to verify:
    - Budget concepts mentioned exist in context
    - Citations reference actual chunks
    - No invented terminology or policies

    Args:
        final_answer: The LLM-generated response text
        context_data: Retrieved context from RAG (budget documents)
        llm: LLM client for context verification

    Returns:
        List of warnings for hallucinated concepts (empty if valid)
    """
    warnings = []

    if not final_answer or not context_data:
        return warnings

    try:
        # Build context grounding prompt
        context_check_prompt = f"""You are a fact-checker for budget documentation answers. Verify that all claims in the answer are supported by the context.

ANSWER:
{final_answer}

CONTEXT (from budget documents):
{context_data[:4000]}  # Limit context to avoid token limits

TASK:
Identify any budget concepts, terminology, or facts in the answer that are NOT found in the context.
Focus on:
- Budget terminology (e.g., "net appropriation", "gross expenditure")
- Policy explanations or processes
- Specific budget figures or allocations
- Agency or committee names
- Citations (e.g., "[Chunk 2]") - verify they reference real chunks

RULES:
- Allow paraphrasing if the meaning is preserved
- Only flag concepts that are COMPLETELY ABSENT from context
- If answer says "I couldn't find..." or acknowledges limitations, that's OK

OUTPUT FORMAT:
If all claims are grounded in context: Respond with exactly "VALID"
If unsupported claims found: List each one on a new line as:
HALLUCINATION: <wrong claim> | SOURCE: <what the context actually says, or "not mentioned" if absent>

Your response:"""

        # Call LLM to check context grounding
        response = llm.invoke([HumanMessage(content=context_check_prompt)])
        context_check_result = response.content.strip()

        # Parse result
        if context_check_result.upper() != "VALID":
            # Extract hallucination lines
            for line in context_check_result.split('\n'):
                if line.strip().startswith('HALLUCINATION:'):
                    # hallucination formating
                    hallucination = line.replace('HALLUCINATION:', '').strip()
                    warnings.append(f"[CONTEXT_GROUNDING] WARNING: {hallucination}")

    except Exception as e:
        logger.error(f"[CONTEXT_GROUNDING] Error during validation: {e}")
        warnings.append(f"[CONTEXT_GROUNDING] WARNING: Validation failed due to error: {str(e)}")

    return warnings
