"""Thin async wrapper around the FastMCP client: starts the server and talks to it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = ROOT / "server" / "server.py"


class JobTrackerClient:
    """Use as:  async with JobTrackerClient() as api: ..."""

    def __init__(self) -> None:
        transport = StdioTransport(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
            cwd=str(ROOT),
            env={"FASTMCP_LOG_LEVEL": "ERROR"},  # keep the terminal quiet
        )
        self._client = Client(transport)

    async def __aenter__(self) -> "JobTrackerClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    # ---- tools
    async def call(self, tool: str, **arguments) -> dict:
        """Call a tool and always return a dict ({'ok': False, 'error': ...} on failure)."""
        try:
            result = await self._client.call_tool(tool, arguments)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if isinstance(result.structured_content, dict):
            return result.structured_content
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"ok": False, "error": text}
        return {"ok": False, "error": "Empty response from server."}

    # ---- resources
    async def pipeline(self) -> dict:
        contents = await self._client.read_resource("applications://pipeline")
        return json.loads(contents[0].text)

    async def master_profile(self) -> str:
        contents = await self._client.read_resource("resume://master-profile")
        return contents[0].text

    # ---- prompts
    async def prompt(self, name: str, **arguments: str) -> str:
        result = await self._client.get_prompt(name, arguments)
        return "\n".join(m.content.text for m in result.messages if hasattr(m.content, "text"))

    # ---- discovery
    async def capabilities(self) -> dict:
        tools = await self._client.list_tools()
        resources = await self._client.list_resources()
        prompts = await self._client.list_prompts()
        return {"tools": len(tools), "resources": len(resources), "prompts": len(prompts)}