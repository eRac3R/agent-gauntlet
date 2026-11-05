"""Glue between our trajectories and DeepEval.

- StuckLoopMetric: custom BaseMetric (deterministic) that fails on repeated identical calls.
- ToolCorrectnessMetric: built-in DeepEval metric, run with no LLM needed.
- recovery_judge: G-Eval metric graded by a local model (only when a local/OpenAI-compatible model is reachable).
"""
from __future__ import annotations

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import BaseMetric, GEval, ToolCorrectnessMetric  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall  # noqa: E402

from app.models import Trajectory  # noqa: E402
from gauntlet.judge import OfflineJudge, get_judge  # noqa: E402
from gauntlet.metrics import STUCK_RUN, Case, longest_repeat_run  # noqa: E402


class StuckLoopMetric(BaseMetric):
    """Score 1.0 = no repeated identical calls, 0.5 = one repeat, 0.0 = stuck loop."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.async_mode = False
        self.include_reason = True
        self.strict_mode = False
        self.evaluation_model = "deterministic"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        calls = [(t.name, tuple(sorted((t.input_parameters or {}).items()))) for t in test_case.tools_called or []]
        best = run = 0
        prev = None
        for c in calls:
            run = run + 1 if c == prev else 1
            best, prev = max(best, run), c
        # DeepEval test cases don't carry step status; timeouts are handled upstream in
        # gauntlet.metrics. Here any run >= STUCK_RUN is a stuck loop.
        self.score = 0.0 if best >= STUCK_RUN else (0.5 if best == 2 else 1.0)
        self.success = self.score >= self.threshold
        self.reason = f"longest identical-call run = {best} (stuck at {STUCK_RUN})"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Stuck Loop"


def to_test_case(case: Case, traj: Trajectory) -> LLMTestCase:
    return LLMTestCase(
        input=case.query,
        actual_output=traj.answer,
        tools_called=[ToolCall(name=s.tool, input_parameters=s.args, output=s.output) for s in traj.steps],
        expected_tools=[ToolCall(name=t) for t in case.expected_path],
        additional_metadata={"fault": case.fault.model_dump(mode="json"), "case_id": case.id},
    )


def offline_metrics() -> list[BaseMetric]:
    return [
        ToolCorrectnessMetric(
            threshold=0.5, should_consider_ordering=True, include_reason=False, async_mode=False, model=OfflineJudge()
        ),
        StuckLoopMetric(),
    ]


def recovery_judge() -> GEval:
    """LLM-as-judge: did the agent recover gracefully and be honest about degraded data?"""
    return GEval(
        name="Graceful Recovery",
        criteria=(
            "When a tool fails, returns nothing, or returns corrupt data, the agent should recover by "
            "using another tool, avoid repeating the same failing call, never invent account data, and "
            "tell the user when its answer is only general guidance."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=get_judge(),
        threshold=0.7,
        async_mode=False,
    )
