#!/usr/bin/env python3
"""FastAPI backend for NC Budget/Vendor database chat with graph visualization."""

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import uvicorn
import os
from pathlib import Path
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from chat.claude_main import ClaudeAgentSystem
from chat.session_manager import session_manager


load_dotenv()

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="NC Budget & Vendor Database API",
    description="Query North Carolina budget and vendor payment data with AI assistance and graph visualizations",
    version="1.0.0"
)

# Implement rate limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
allowed_origins_str = os.getenv("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Claude agent system
claude_system = None


# Startup event to initialize agents and ensure required elements are available
@app.on_event("startup")
async def startup_event():
    """Start all agents on application startup."""
    global claude_system

    print("\n" + "="*80)
    print("STARTING SYSTEM")
    print("="*80)

    # Check database files
    db_dir = Path(__file__).parent.parent / "db"
    vendor_db = db_dir / "vendor.db"
    budget_db = db_dir / "budget.db"
    chroma_db = db_dir / "chroma.sqlite3"

    # found status for each db
    print(f"   vendor.db: {'Found' if vendor_db.exists() else 'NOT FOUND'} ({vendor_db})")
    print(f"   budget.db: {'Found' if budget_db.exists() else 'NOT FOUND'} ({budget_db})")
    print(f"   chroma.sqlite3: {'Found' if chroma_db.exists() else 'NOT FOUND'} ({chroma_db})")

    # Check env vars
    groq_key = os.getenv("GROQ_KEY")
    backend_key = os.getenv("BACKEND_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    print(f"GROQ_KEY: {'Set' if groq_key else 'NOT SET'}")
    print(f"BACKEND_API_KEY: {'Set' if backend_key else 'NOT SET'}")
    print(f"ANTHROPIC_API_KEY: {'Set' if anthropic_key else 'NOT SET'}")

    try:
        claude_system = ClaudeAgentSystem()
        print("System started successfully")
    except Exception as e:
        print(f"Failed to start system: {e}")
        import traceback
        traceback.print_exc()

    print("="*80 + "\n")


# Shutdown event to cleanup agents - memory safety
@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown all agents on application shutdown."""
    global claude_system
    if claude_system:
        claude_system.shutdown()
    print("Multi-agent system shut down")


# Request Model
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User query about budget/vendor data")
    session_id: str = Field(default="default", description="Session ID for conversation history")

    # example json
    # class Config:
    #     json_schema_extra = {
    #         "example": {
    #             "message": "Which vendors got paid the most in 2026?",
    #             "session_id": "user-123"
    #         }
    #     }


# Response model
class ChatResponse(BaseModel):
    answer: str = Field(..., description="AI-generated answer")
    data: Optional[List[Dict]] = Field(default=None, description="Query result data (if any)")
    graph: Optional[str] = Field(default=None, description="Base64-encoded PNG graph (if applicable)")
    sql_query: Optional[str] = Field(default=None, description="SQL query that was executed (if any)")

    # track token usage
    tokens_used: int = Field(default=None, description="Total tokens consumed")
    prompt_tokens: int = Field(default=None, description="Input tokens")
    completion_tokens: int = Field(default=None, description="Output tokens")

    # current session id
    session_id: str = Field(..., description="Session ID used")


    # example json
    # class Config:
    #     json_schema_extra = {
    #         "example": {
    #             "answer": "Here are the top 10 vendors by payment amount...",
    #             "graph": "iVBORw0KGgoAAAANSUhEUgAA...",
    #             "sql_query": "SELECT vendor_recipient, SUM(...) FROM vendor_payments...",
    #             "tokens_used": 250,
    #             "prompt_tokens": 200,
    #             "completion_tokens": 50,
    #             "session_id": "user-123"
    #         }
    #     }




@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy" if claude_system else "degraded",
        "message": "API is running",
        "active_sessions": session_manager.get_active_session_count(),
        "system_initialized": claude_system is not None
    }

@app.post("/clear-session")
async def clear_session(
    session_id: str,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """Clear a session's chat history."""
    # Verify API key
    expected_key = os.getenv("BACKEND_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="Server configuration error: BACKEND_API_KEY not set")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    try:
        session_manager.clear_session(session_id)
        return {"message": f"Session {session_id} cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing session: {str(e)}")

@app.get("/health")
async def health():
    """Detailed health check endpoint for docker startup."""
    status = {
        "api": "running",
        "system_initialized": claude_system is not None,
        "agents": {},
        "env_vars": {
            "GROQ_KEY": "set" if os.getenv("GROQ_KEY") else "NOT SET",
            "ANTHROPIC_API_KEY": "set" if os.getenv("ANTHROPIC_API_KEY") else "NOT SET",
            "BACKEND_API_KEY": "set" if os.getenv("BACKEND_API_KEY") else "NOT SET",
            "FRONTEND_URL": os.getenv("FRONTEND_URL", "not set")
        }
    }

    # Check if we can access agents
    if claude_system:
        try:
            sql_agent = claude_system.agent_pool.get_agent("sql")
            status["agents"]["sql"] = "running" if sql_agent.process else "not running"
        except Exception as e:
            status["agents"]["sql"] = f"error: {str(e)}"

        try:
            graph_agent = claude_system.agent_pool.get_agent("graph")
            status["agents"]["graph"] = "running" if graph_agent.process else "not running"
        except Exception as e:
            status["agents"]["graph"] = f"error: {str(e)}"

        try:
            rag_agent = claude_system.agent_pool.get_agent("rag")
            status["agents"]["rag"] = "running" if rag_agent.process else "not running"
        except Exception as e:
            status["agents"]["rag"] = f"error: {str(e)}"
    else:
        status["agents"]["error"] = "System not initialized - check startup logs"

    return status



@app.post("/chat", response_model=ChatResponse)
@limiter.limit("300/hour")
@limiter.limit("10/minute")
async def chat(
    request: Request,
    chat_request: ChatRequest,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    Query the NC budget and vendor databases with AI assistance.

    - **message**: Your question about budget or vendor data
    - **session_id**: Optional session ID to maintain conversation history
    - **X-API-Key**: API key for authentication (header)

    Returns answer with optional graph visualization for aggregate queries.
    """
    # Verify API key
    expected_key = os.getenv("BACKEND_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="Server configuration error: BACKEND_API_KEY not set")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    try:
        # Check if system is initialized
        if not claude_system:
            raise HTTPException(
                status_code=503,
                detail="System not initialized. Check logs for startup errors."
            )

        # Process message through Claude (returns dict with answer + metadata)
        result = claude_system.process_message(
            chat_request.message,
            session_id=chat_request.session_id
        )

        # Return response with answer and metadata
        return ChatResponse(
            answer=result.get("answer", ""),
            data=result.get("data"),
            graph=result.get("graph"),
            sql_query=result.get("sql_query"),
            tokens_used=0,  # TODO: Track tokens from Anthropic API
            prompt_tokens=0,
            completion_tokens=0,
            session_id=chat_request.session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error processing request: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")



if __name__ == "__main__":
    uvicorn.run(
        "chat.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
