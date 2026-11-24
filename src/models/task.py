import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text

from src.db import GUID, Base


def _now():
    return datetime.now(timezone.utc)


class AgentTask(Base):
    """One job given to an agent.

    status: queued -> running -> done | failed, or running -> waiting_approval when the
    agent wants to use a tool that needs your OK. Approving or rejecting puts it back in
    the queue.
    """

    __tablename__ = "agent_tasks"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID, ForeignKey("user.id"), nullable=False, index=True)
    agent = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    # The full conversation with the model, including tool calls and tool outputs.
    messages = Column(JSON, nullable=False, default=list)
    # Tool calls waiting for approval (the first one) and the ones after it.
    pending_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
