"""LLM synthesis with chat history for budget explanations."""

from typing import List, Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import os


class RAGSynthesizer:
    """Synthesize answers from retrieved context with chat history."""

    def __init__(self):
        """Initialize ChatGroq client."""
        self.llm_client = ChatGroq(
            model=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
            api_key=os.getenv("GROQ_KEY"),
            temperature=0.3
        )

    def synthesize(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        chat_history: List[Dict[str, str]] = None
    ) -> str:
        """
        Generate answer from retrieved chunks with chat history.

        Args:
            query: User question
            chunks: Retrieved chunks with 'text' and 'metadata' keys
            chat_history: Optional list of {role, content} messages

        Returns:
            Synthesized answer with citations
        """
        if not chunks:
            return "I couldn't find relevant information in the budget documents to answer your question. Could you rephrase or ask something more specific?"

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):

            context_parts.append(f"\n{chunk['text']}\n")

        context = "\n".join(context_parts)

        # Build system prompt
        system_prompt = f"""You are an expert on North Carolina's Governor's Budget documents.
Your role is to explain budget concepts, policies, and appropriations clearly and accurately
based ONLY on the provided context.

RULES:
1. ONLY use information from the context chunks below
2. Cite sections when referencing information (e.g., "According to [Chunk 2]...")
3. If context doesn't fully answer the question, acknowledge the limitation
4. Explain budget terminology clearly (gross vs net expenditures, fund types, receipts, etc.)
5. Be concise but thorough - aim for 2-4 paragraphs
6. Maintain conversation continuity using chat history

CONTEXT CHUNKS:
{context}
"""

        # Build messages using LangChain message types
        messages = [SystemMessage(content=system_prompt)]

        # Add chat history (last 4 messages)
        if chat_history:
            for msg in chat_history[-4:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Add current query
        messages.append(HumanMessage(content=query))

        # Generate response
        try:
            response = self.llm_client.invoke(messages)
            answer = response.content

            # Extract token usage from response metadata
            usage_metadata = response.response_metadata.get("token_usage", {})
            tokens = {
                "prompt_tokens": usage_metadata.get("prompt_tokens", 0),
                "completion_tokens": usage_metadata.get("completion_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0)
            }

            return answer, tokens

        except Exception as e:
            return f"Error generating answer: {str(e)}", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
