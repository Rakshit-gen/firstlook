"""What the agent concludes, in a fixed shape."""

from typing import Literal

from pydantic import BaseModel, Field

Cause = Literal[
    "deploy", "config", "capacity", "dependency", "certificate", "disk", "traffic", "unknown"
]
ActionKind = Literal["rollback", "restart", "scale_up", "rate_limit", "escalate", "none"]


class Action(BaseModel):
    kind: ActionKind = Field(
        description="rollback a deploy, restart, scale_up, rate_limit incoming traffic,"
        " escalate to a person (for fixes no tool can do), or none"
    )
    service: str = Field(description="the service to act on")
    detail: str = Field(default="", description="e.g. the version to roll back to")


class Finding(BaseModel):
    service: str = Field(description="the service where the problem starts")
    cause: Cause
    summary: str = Field(description="what happened, in two or three plain sentences")
    evidence: list[str] = Field(
        description="short exact quotes from tool answers that support this, e.g. a log"
        " message, a deploy line, or a metric change"
    )
    confidence: Literal["low", "medium", "high"]
    action: Action
