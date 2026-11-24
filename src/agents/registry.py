"""The agents ("districts"). Each one has its own instructions and only the tools it needs.

To add an agent, add an Agent(...) to AGENTS.
"""
from dataclasses import dataclass

from src.agents.tools import TOOLS, Tool


@dataclass
class Agent:
    name: str
    description: str
    system_prompt: str
    tool_names: list[str]

    @property
    def tools(self) -> dict[str, Tool]:
        # Tools that are switched off (e.g. run_command) are skipped.
        return {name: TOOLS[name] for name in self.tool_names if name in TOOLS}


AGENTS: dict[str, Agent] = {
    "ops": Agent(
        name="ops",
        description="Checks websites and servers and finds out why something is down.",
        system_prompt=(
            "You are the ops agent. You check whether websites and servers work and find "
            "the cause when they don't. Use your tools to get facts before you answer; "
            "never guess a status. Keep the final answer short: what is wrong, the "
            "evidence, and what to do next. If a tool needs approval and the user rejects "
            "it, do not try the same action again."
        ),
        tool_names=["current_time", "check_website", "run_command"],
    ),
}
