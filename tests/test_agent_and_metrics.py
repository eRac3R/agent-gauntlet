from app.agent import run_agent
from app.brains import make_brain
from app.models import FaultKind, FaultSpec, Step
from gauntlet.metrics import (
    efficiency_score, load_cases, longest_repeat_run, loop_score, path_score, score_case,
)


def _step(i, tool, status="ok", **args):
    return Step(index=i, tool=tool, args=args, status=status, output="x")


def test_dataset_has_twenty_unique_cases():
    cases = load_cases()
    assert len(cases) == 20
    assert len({c.id for c in cases}) == 20


def test_naive_agent_gets_stuck_when_db_fails():
    fault = FaultSpec(tool="lookup_customer", kind=FaultKind.error)
    traj = run_agent("Which plan is customer C-1005 on?", make_brain("naive"), fault)
    assert traj.stopped_reason == "max_steps" and not traj.success
    assert longest_repeat_run(traj.steps) >= 3


def test_resilient_agent_falls_back_to_web_search():
    fault = FaultSpec(tool="lookup_customer", kind=FaultKind.error)
    traj = run_agent("Which plan is customer C-1005 on?", make_brain("resilient"), fault)
    assert traj.path == ["lookup_customer", "web_search"]
    assert "general guidance" in traj.answer


def test_resilient_retries_a_timeout_exactly_once():
    fault = FaultSpec(tool="get_order", kind=FaultKind.timeout)
    traj = run_agent("Where is order O-5003?", make_brain("resilient"), fault)
    assert traj.path == ["get_order", "get_order", "web_search"]


def test_one_retry_after_timeout_is_not_a_loop():
    steps = [_step(0, "a", "timeout", q=1), _step(1, "a", "timeout", q=1)]
    assert longest_repeat_run(steps) == 1


def test_endless_timeout_retries_are_a_loop():
    steps = [_step(i, "a", "timeout", q=1) for i in range(8)]
    assert loop_score(steps) == 0.0


def test_three_identical_calls_is_a_stuck_loop():
    steps = [_step(i, "a", "error", q=1) for i in range(3)]
    assert loop_score(steps) == 0.0


def test_path_and_efficiency_scores():
    assert path_score(["a", "b"], ["a", "b"]) == 1.0
    assert path_score(["a", "b"], ["a"]) == 0.5
    assert efficiency_score(2, 4) == 0.5
    assert efficiency_score(2, 1) == 1.0


def test_resilient_passes_every_case_and_naive_regresses():
    cases = load_cases()
    resilient = [score_case(c, run_agent(c.query, make_brain("resilient"), c.fault)).passed for c in cases]
    naive = [score_case(c, run_agent(c.query, make_brain("naive"), c.fault)).passed for c in cases]
    assert all(resilient)
    assert sum(naive) < sum(resilient)
