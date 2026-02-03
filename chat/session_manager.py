"""Session and memory management."""

import time
import threading
from typing import Dict, List, Any


class SessionManager:
    """Manages chat sessions with conversation history."""

    def __init__(self, ttl_seconds: int = 1800, window_size: int = 2):
        """
        Initialize session manager.

        Args:
            ttl_seconds: Session TTL in seconds (default 30 min)
            window_size: Number of conversation exchanges to keep (default 2)
        """
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
        self.window_size = window_size
        self.lock = threading.Lock()

        # Start garbage collection thread
        self._start_gc_thread()

    def _truncate_content(self, content: str, max_chars: int = 2000) -> str:
        """
        Truncate long content to prevent context bloat.

        Args:
            content: Content to potentially truncate
            max_chars: Maximum characters to keep

        Returns:
            Truncated content with indicator if truncated
        """
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + f"\n\n[... truncated {len(content) - max_chars} characters for memory efficiency]"

    def add_exchange(self, session_id: str, user_message: str, ai_response: str):
        """
        Add user-AI exchange to session memory.
        Truncates long responses to prevent context explosion.

        Args:
            session_id: Session identifier
            user_message: User's message
            ai_response: AI's response
        """
        with self.lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = {
                    "messages": [],
                    "last_accessed": time.time()
                }

            session = self.sessions[session_id]

            # Truncate long responses to prevent context bloat
            truncated_response = self._truncate_content(ai_response, max_chars=2000)

            session["messages"].append({"role": "user", "content": user_message})
            session["messages"].append({"role": "assistant", "content": truncated_response})

            # Keep only last window_size exchanges (2 messages per exchange)
            if len(session["messages"]) > self.window_size * 2:
                session["messages"] = session["messages"][-(self.window_size * 2):]

            session["last_accessed"] = time.time()

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get messages for a session.

        Returns:
            List of {"role": "user"|"assistant", "content": "..."} dicts
        """
        with self.lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = {
                    "messages": [],
                    "last_accessed": time.time()
                }

            session = self.sessions[session_id]
            session["last_accessed"] = time.time()
            return session["messages"].copy()

    def get_messages_dict(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get messages as dictionaries (alias for get_messages for backwards compatibility).

        Returns:
            List of {"role": "user"|"assistant", "content": "..."} dicts
        """
        return self.get_messages(session_id)

    def clear_session(self, session_id: str):
        """Clear/delete a specific session."""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]

    def get_active_session_count(self) -> int:
        """Get number of active sessions."""
        with self.lock:
            return len(self.sessions)

    def _garbage_collect(self):
        """Remove expired sessions based on TTL."""
        now = time.time()

        with self.lock:
            expired = [
                sid for sid, data in self.sessions.items()
                if now - data["last_accessed"] > self.ttl_seconds
            ]

            for sid in expired:
                del self.sessions[sid]

            if expired:
                print(f"[SessionManager] GC removed {len(expired)} expired sessions")

    def _start_gc_thread(self):
        """Start background daemon thread for garbage collection."""
        def gc_loop():
            while True:
                # run every 5 minutes
                time.sleep(300)
                self._garbage_collect()

        gc_thread = threading.Thread(target=gc_loop, daemon=True)
        gc_thread.start()


# global singleton instance - keep only last 2 exchanges to prevent context bloat
session_manager = SessionManager(ttl_seconds=1800, window_size=2)
