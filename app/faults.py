"""Fault injector: wraps tool execution and breaks it on demand."""
from __future__ import annotations

import json
from typing import Any

from app.models import FaultKind, FaultSpec, StepStatus
from app.tools import BASE_LATENCY_MS, TOOLS, ToolError, ToolTimeout

SLOW_EXTRA_MS = 4000
TIMEOUT_MS = 5000


def execute(tool: str, args: dict[str, Any], fault: FaultSpec) -> tuple[StepStatus, str, int]:
    """Run a tool, applying the fault if it targets this tool.

    Returns (status, output_text, simulated_latency_ms). Latency is simulated so
    the whole suite stays fast and deterministic.
    """
    latency = BASE_LATENCY_MS.get(tool, 100)
    targeted = fault.active and fault.tool == tool

    if targeted:
        if fault.kind == FaultKind.error:
            return "error", "ToolError: upstream service unavailable (503)", latency
        if fault.kind == FaultKind.timeout:
            return "timeout", "ToolTimeout: no response after 5000ms", TIMEOUT_MS
        if fault.kind == FaultKind.empty:
            return "empty", "[]", latency
        if fault.kind == FaultKind.malformed:
            return "malformed", "<<<corrupt payload 0x7f3a>>>", latency
        if fault.kind == FaultKind.slow:
            latency += SLOW_EXTRA_MS

    try:
        result = TOOLS[tool](**args)
    except ToolTimeout as exc:
        return "timeout", f"ToolTimeout: {exc}", TIMEOUT_MS
    except ToolError as exc:
        return "error", f"ToolError: {exc}", latency
    except TypeError as exc:
        return "error", f"BadArguments: {exc}", latency

    if result in (None, [], {}):
        return "empty", "[]", latency
    return "ok", json.dumps(result), latency
