#!/usr/bin/env python3
"""MCP Agent Client - Manages communication with MCP agent servers via JSON-RPC."""

import subprocess
import json
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import sys


class MCPAgentClient:
    """Client for communicating with MCP agent servers as subprocesses."""

    def __init__(self, agent_name: str, script_path: str):
        """
        Initialize MCP Agent Client.

        Args:
            agent_name: Name of the agent (for logging)
            script_path: Path to the agent's Python script
        """
        self.agent_name = agent_name
        self.script_path = script_path
        # agent process
        self.agent_process: Optional[subprocess.Popen] = None
        # self._pending_requests: Dict[str, asyncio.Future] = {}

    def start(self):
        """Launch the agent subprocess."""

        # already running
        if self.agent_process:
            print(f"[{self.agent_name}] Already running")
            return

        print(f"[{self.agent_name}] Launching subprocess: {self.script_path}")

        # Launch agent
        try:
            # init subprocess
            self.agent_process = subprocess.Popen(
                [sys.executable, self.script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # Let stderr pass through to parent -- useful for logging
                stderr=None,  
                text=True,
                bufsize=1
            )
            print(f"[{self.agent_name}] Process spawned (PID: {self.agent_process.pid})")
        except Exception as e:
            print(f"[{self.agent_name}] Failed to spawn process: {e}")
            raise

        # handhsake between agent and client
        try:
            print(f"[{self.agent_name}] Reading init message...")
            # wait for agent message
            init_line = self.agent_process.stdout.readline()
            if not init_line:
                if self.agent_process.stderr:
                    stderr_output = self.agent_process.stderr.read()
                else:
                    stderr_output = "(stderr passed through)"
                raise RuntimeError(f"No init message from agent. Stderr: {stderr_output}")

            init_msg = json.loads(init_line)
            print(f"[{self.agent_name}] Started: {init_msg.get('result', {}).get('serverInfo', {})}")
        except Exception as e:
            stderr_output = self.agent_process.stderr.read() if self.agent_process.stderr else "N/A"
            print(f"[{self.agent_name}] Error reading init: {e}")
            print(f"[{self.agent_name}] Stderr: {stderr_output}")
            self.agent_process.terminate()
            self.agent_process = None
            raise

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the agent and get response.

        Args:
            request: JSON-RPC request dict

        Returns:
            Response dict
        """
        if not self.agent_process:
            raise RuntimeError(f"Agent {self.agent_name} not started")

        # Write request to stdin
        request_json = json.dumps(request) + "\n"
        self.agent_process.stdin.write(request_json)
        self.agent_process.stdin.flush()

        # Read response from agent stdout
        response_line = self.agent_process.stdout.readline()
        if not response_line:
            raise RuntimeError(f"Agent {self.agent_name} died (no response)")

        response = json.loads(response_line)

        # Check for errors
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"Agent {self.agent_name} error: {error.get('message', 'Unknown error')}")

        return response.get("result", {})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on the agent.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result (parsed from JSON)
        """
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        result = self._send_request(request)

        # Extract content from MCP response format
        if "content" in result:
            content_items = result["content"]
            if content_items and len(content_items) > 0:
                text = content_items[0].get("text", "{}")
                # Parse the JSON string content
                return json.loads(text)

        return result


    def shutdown(self):
        """Terminate the agent subprocess."""
        if self.agent_process:
            self.agent_process.terminate()
            try:
                self.agent_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.agent_process.kill()
            self.agent_process = None
            print(f"[{self.agent_name}] Shut down")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()


class AgentPool:
    """Manages a pool of MCP agents."""

    def __init__(self):
        """Initialize agent pool."""
        self.agents: Dict[str, MCPAgentClient] = {}
        self.agents_dir = Path(__file__).parent

    def register_agent(self, agent_name: str, script_name: str) -> MCPAgentClient:
        """
        Register and start an agent.

        Args:
            agent_name: Name identifier for the agent
            script_name: Filename of the agent script (e.g., "sql_agent.py")

        Returns:
            MCPAgentClient instance
        """
        # find and pass script path
        script_path = self.agents_dir / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"Agent script not found: {script_path}")

        client = MCPAgentClient(agent_name, str(script_path))
        client.start()
        self.agents[agent_name] = client
        return client

    def get_agent(self, agent_name: str) -> MCPAgentClient:
        """Get an agent by name."""
        if agent_name not in self.agents:
            raise KeyError(f"Agent '{agent_name}' not registered")
        return self.agents[agent_name]

    def shutdown_all(self):
        """Shutdown all agents in the pool."""
        for agent in self.agents.values():
            agent.shutdown()
        self.agents.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown_all()


