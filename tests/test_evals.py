"""DeepEval-powered evals. The resilient agent is the production baseline: every case must pass.

Run:  py -m pytest tests/test_evals.py
The LLM-judge test is skipped unless a local OpenAI-compatible endpoint (e.g. Ollama) is reachable.
"""
import pytest
from deepeval import assert_test

from app.agent import run_agent
from app.brains import make_brain
from gauntlet.deepeval_bridge import offline_metrics, recovery_judge, to_test_case
from gauntlet.judge import judge_available
from gauntlet.metrics import load_cases

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_resilient_agent_trajectory(case):
    traj = run_agent(case.query, make_brain("resilient"), case.fault)
    assert_test(to_test_case(case, traj), offline_metrics(), run_async=False)


def test_deepeval_catches_the_naive_agent_stuck_loop():
    case = next(c for c in CASES if c.id == "error-01")
    traj = run_agent(case.query, make_brain("naive"), case.fault)
    with pytest.raises(AssertionError):
        assert_test(to_test_case(case, traj), offline_metrics(), run_async=False)


@pytest.mark.skipif(not judge_available(), reason="needs a reachable local LLM endpoint (e.g. Ollama) for the judge")
def test_llm_judge_scores_recovery():
    case = next(c for c in CASES if c.id == "error-01")
    traj = run_agent(case.query, make_brain("resilient"), case.fault)
    assert_test(to_test_case(case, traj), [recovery_judge()], run_async=False)
