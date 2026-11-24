"""The agent loop: the model asks for tools, we run them and send back the results,
until it gives a final answer. Tools that need approval pause the task."""
from uuid import UUID

from sqlalchemy import update

from src import ai_ollama
from src.agents.registry import AGENTS, Agent
from src.db import async_session_maker
from src.logging_config import logger
from src.models.task import AgentTask

MAX_STEPS = 10
REJECTED = "The user rejected this action. Do not try it again."


async def _run_calls(agent: Agent, messages: list[dict], calls: list[dict], approved: bool | None) -> list[dict]:
    """Runs tool calls in order. Returns the calls that still wait for approval (empty if none).

    `approved` is the user's answer for the first call, when resuming a paused task.
    """
    tools = agent.tools
    for i, call in enumerate(calls):
        name = call["function"]["name"]
        arguments = call["function"].get("arguments") or {}
        tool = tools.get(name)

        if tool is None:
            output = f"Unknown tool: {name}. Available: {', '.join(tools) or 'none'}."
        elif tool.needs_approval:
            if i == 0 and approved is not None:
                output = await tool.run(arguments) if approved else REJECTED
            else:
                return calls[i:]
        else:
            output = await tool.run(arguments)

        logger.info("Agent %s used %s", agent.name, name)
        messages.append({"role": "tool", "tool_name": name, "content": output})
    return []


async def run_task(task_id: UUID, approved: bool | None = None) -> None:
    async with async_session_maker() as session:
        task = await session.get(AgentTask, task_id)
        if task is None:
            return
        agent = AGENTS.get(task.agent)
        if agent is None:
            task.status, task.error = "failed", f"Unknown agent: {task.agent}"
            await session.commit()
            return

        task.status = "running"
        await session.commit()

        messages = list(task.messages)
        try:
            # Resume after an approval or rejection.
            if task.pending_calls:
                waiting = await _run_calls(agent, messages, task.pending_calls, approved)
                if waiting:
                    task.messages, task.pending_calls, task.status = list(messages), waiting, "waiting_approval"
                    await session.commit()
                    return

            tool_schemas = [tool.schema() for tool in agent.tools.values()]
            for _ in range(MAX_STEPS):
                reply = await ai_ollama.chat_with_tools(messages, task.model, tool_schemas)
                messages.append(reply)

                calls = reply.get("tool_calls")
                if not calls:
                    task.messages, task.pending_calls = list(messages), None
                    task.result, task.status = reply["content"], "done"
                    await session.commit()
                    return

                waiting = await _run_calls(agent, messages, calls, None)
                task.messages = list(messages)
                if waiting:
                    task.pending_calls, task.status = waiting, "waiting_approval"
                    await session.commit()
                    return
                await session.commit()

            task.messages, task.pending_calls = list(messages), None
            task.status, task.error = "failed", f"Stopped after {MAX_STEPS} steps without an answer."
            await session.commit()
        except Exception as e:
            logger.exception("Agent task %s failed", task_id)
            await session.rollback()
            task = await session.get(AgentTask, task_id)
            task.messages, task.status, task.error = list(messages), "failed", f"{type(e).__name__}: {e}"
            await session.commit()


async def fail_interrupted_tasks() -> None:
    """Tasks that were running when the server stopped cannot continue. Called on startup."""
    async with async_session_maker() as session:
        await session.execute(
            update(AgentTask)
            .where(AgentTask.status.in_(["queued", "running"]))
            .values(status="failed", error="The server restarted while this task was running.")
        )
        await session.commit()
