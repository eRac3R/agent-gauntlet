"""The agent loop: ask the brain what to do, run the tool through the fault injector, repeat."""
from __future__ import annotations

from typing import Iterator

from app.brains import Brain
from app.faults import execute
from app.models import FaultSpec, Step, Trajectory

# Placeholder $/million-token prices used for *estimated* cost. Verify against current pricing.
PRICE_IN_PER_MTOK = 1.0
PRICE_OUT_PER_MTOK = 5.0


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def iter_agent(
    query: str, brain: Brain, fault: FaultSpec | None = None, max_steps: int = 8
) -> Iterator[tuple[str, Step | Trajectory]]:
    """Yield ("step", Step) per tool call, then ("done", Trajectory)."""
    fault = fault or FaultSpec()
    steps: list[Step] = []
    tokens_in = tokens_out = 0
    answer, success, reason = "Stopped: step budget exhausted.", False, "max_steps"

    for i in range(max_steps):
        action = brain.decide(query, steps)
        if action.usage:
            tokens_in += action.usage[0]
            tokens_out += action.usage[1]
        else:  # estimate: the model re-reads the whole transcript every turn
            tokens_in += _est_tokens(query) + sum(_est_tokens(s.output) + 20 for s in steps)
            tokens_out += 25
        if action.final is not None:
            answer, success, reason = action.final, action.success, "final"
            break
        status, output, latency = execute(action.tool, action.args, fault)
        step = Step(index=i, tool=action.tool, args=action.args, status=status, output=output, latency_ms=latency)
        steps.append(step)
        yield "step", step

    cost = tokens_in / 1e6 * PRICE_IN_PER_MTOK + tokens_out / 1e6 * PRICE_OUT_PER_MTOK
    yield "done", Trajectory(
        agent=brain.name, query=query, fault=fault, steps=steps, answer=answer, success=success,
        stopped_reason=reason, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=round(cost, 6),
    )


def run_agent(query: str, brain: Brain, fault: FaultSpec | None = None, max_steps: int = 8) -> Trajectory:
    for kind, payload in iter_agent(query, brain, fault, max_steps):
        if kind == "done":
            return payload  # type: ignore[return-value]
    raise RuntimeError("agent produced no result")
