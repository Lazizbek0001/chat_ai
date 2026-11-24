"""Tools the agents can use.

To add a tool: write an async function that returns a string, then add a Tool(...) to
TOOLS. Set needs_approval=True for anything that changes something (deploys, deletes,
sending messages); the task then waits until you approve it.
"""
import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

MAX_OUTPUT = 4000


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., Awaitable[str]]
    needs_approval: bool = False

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def run(self, arguments: dict) -> str:
        try:
            output = await self.func(**arguments)
        except TypeError as e:
            return f"Bad arguments for {self.name}: {e}"
        except Exception as e:  # The model sees the error and can try something else.
            return f"{self.name} failed: {type(e).__name__}: {e}"
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[cut]"
        return output


async def current_time() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_website(url: str) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        return "Only http:// and https:// URLs can be checked."
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as e:
        return f"DOWN: {type(e).__name__}: {e}"
    ms = (time.perf_counter() - start) * 1000
    return f"HTTP {response.status_code} in {ms:.0f} ms (final URL: {response.url})"


async def run_command(command: str) -> str:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    except asyncio.TimeoutError:
        process.kill()
        return "Timed out after 60 seconds."
    return f"exit code {process.returncode}\n{stdout.decode(errors='replace')}"


TOOLS: dict[str, Tool] = {
    "current_time": Tool(
        name="current_time",
        description="Get the current date and time (UTC).",
        parameters={"type": "object", "properties": {}},
        func=current_time,
    ),
    "check_website": Tool(
        name="check_website",
        description="Open a URL and report whether it is up, its HTTP status and response time.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL, e.g. https://example.com"}},
            "required": ["url"],
        },
        func=check_website,
    ),
}

# Runs shell commands on the machine this API runs on. Off unless ENABLE_SHELL_TOOL=true,
# and every command waits for your approval.
if os.getenv("ENABLE_SHELL_TOOL", "false").lower() == "true":
    TOOLS["run_command"] = Tool(
        name="run_command",
        description="Run a shell command on the server and return its output. Needs the user's approval.",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The shell command"}},
            "required": ["command"],
        },
        func=run_command,
        needs_approval=True,
    )
