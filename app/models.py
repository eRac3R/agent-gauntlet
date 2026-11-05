from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class FaultKind(str, Enum):
    none = "none"
    error = "error"
    empty = "empty"
    timeout = "timeout"
    malformed = "malformed"
    slow = "slow"


class FaultSpec(BaseModel):
    tool: str | None = None
    kind: FaultKind = FaultKind.none

    @property
    def active(self) -> bool:
        return self.tool is not None and self.kind != FaultKind.none


StepStatus = Literal["ok", "error", "empty", "timeout", "malformed"]


class Step(BaseModel):
    index: int
    tool: str
    args: dict[str, Any]
    status: StepStatus
    output: str
    latency_ms: int = 0


class Trajectory(BaseModel):
    agent: str
    query: str
    fault: FaultSpec = Field(default_factory=FaultSpec)
    steps: list[Step]
    answer: str
    success: bool
    stopped_reason: Literal["final", "max_steps"]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    @property
    def path(self) -> list[str]:
        return [s.tool for s in self.steps]


class RunRequest(BaseModel):
    query: str
    agent: str = "resilient"
    fault: FaultSpec = Field(default_factory=FaultSpec)
    max_steps: int = Field(default=8, ge=1, le=10)


class EvalRequest(BaseModel):
    agent: str = "resilient"
    case_ids: list[str] | None = None
