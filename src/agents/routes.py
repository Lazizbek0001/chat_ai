from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.registry import AGENTS
from src.agents.runner import run_task
from src.ai_ollama import AGENT_MODEL
from src.auth import current_active_user
from src.db import User, get_async_session
from src.models.task import AgentTask

router = APIRouter(tags=["Agents"])


class TaskCreate(BaseModel):
    prompt: str = Field(min_length=1)
    agent: str = "ops"
    model: str | None = None


def _summary(task: AgentTask) -> dict:
    return {
        "id": str(task.id),
        "agent": task.agent,
        "status": task.status,
        "prompt": task.prompt,
        "result": task.result,
        "error": task.error,
        "waiting_for": task.pending_calls[0]["function"] if task.pending_calls else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


async def _get_task(task_id: UUID, user: User, session: AsyncSession) -> AgentTask:
    task = await session.get(AgentTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/agents")
async def list_agents(user: User = Depends(current_active_user)):
    return [
        {
            "name": agent.name,
            "description": agent.description,
            "tools": [{"name": t.name, "needs_approval": t.needs_approval} for t in agent.tools.values()],
        }
        for agent in AGENTS.values()
    ]


@router.post("/tasks", status_code=202)
async def create_task(
    data: TaskCreate,
    background: BackgroundTasks,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Gives a job to an agent. It runs in the background: poll GET /tasks/{id}."""
    agent = AGENTS.get(data.agent)
    if agent is None:
        raise HTTPException(status_code=400, detail=f"Unknown agent. Available: {', '.join(AGENTS)}")

    task = AgentTask(
        user_id=user.id,
        agent=agent.name,
        model=data.model or AGENT_MODEL,
        prompt=data.prompt,
        status="queued",
        messages=[
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": data.prompt},
        ],
    )
    session.add(task)
    await session.commit()
    background.add_task(run_task, task.id)
    return _summary(task)


@router.get("/tasks")
async def list_tasks(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(AgentTask).where(AgentTask.user_id == user.id).order_by(AgentTask.created_at.desc()).limit(100)
    )
    return [_summary(task) for task in result.scalars().all()]


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """The task with every step: model replies, tool calls and tool outputs."""
    task = await _get_task(task_id, user, session)
    return {**_summary(task), "model": task.model, "steps": task.messages[1:]}


async def _answer(task_id: UUID, approved: bool, background: BackgroundTasks, user: User, session: AsyncSession):
    await _get_task(task_id, user, session)
    # Only one approve/reject can win, even if two arrive at the same time.
    result = await session.execute(
        update(AgentTask)
        .where(AgentTask.id == task_id, AgentTask.status == "waiting_approval")
        .values(status="queued")
    )
    await session.commit()
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="This task is not waiting for approval.")
    background.add_task(run_task, task_id, approved)
    return {"id": str(task_id), "status": "queued", "approved": approved}


@router.post("/tasks/{task_id}/approve")
async def approve_task(
    task_id: UUID,
    background: BackgroundTasks,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Runs the tool call the task is waiting on, then the agent continues."""
    return await _answer(task_id, True, background, user, session)


@router.post("/tasks/{task_id}/reject")
async def reject_task(
    task_id: UUID,
    background: BackgroundTasks,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Skips the tool call the task is waiting on and tells the agent it was rejected."""
    return await _answer(task_id, False, background, user, session)
