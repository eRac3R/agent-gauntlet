"""Deterministic trajectory metrics. Free, fast, and reproducible: no LLM involved."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.models import FaultSpec, Step, Trajectory

DATASET = Path(__file__).resolve().parent.parent / "datasets" / "cases.json"
PASS_THRESHOLD = 0.9
STUCK_RUN = 3  # this many identical calls in a row = stuck


@dataclass
class Case:
    id: str
    category: str
    query: str
    fault: FaultSpec
    expected_path: list[str]
    optimal_steps: int
    answer_contains: list[str]


@dataclass
class CaseScore:
    answer_ok: bool
    path: float
    efficiency: float
    loop: float
    overall: float
    passed: bool
    stuck: bool
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_cases(path: Path = DATASET) -> list[Case]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Case(**{**r, "fault": FaultSpec(**r["fault"])}) for r in raw]


def lcs_len(a: list[str], b: list[str]) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            dp[i + 1][j + 1] = dp[i][j] + 1 if x == y else max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]


def path_score(expected: list[str], actual: list[str]) -> float:
    """Ordered similarity: LCS length over the longer of the two paths."""
    if not expected and not actual:
        return 1.0
    return lcs_len(expected, actual) / max(len(expected), len(actual))


def efficiency_score(optimal: int, actual: int) -> float:
    return 1.0 if actual == 0 and optimal == 0 else min(1.0, optimal / max(actual, 1))


def longest_repeat_run(steps: list[Step]) -> int:
    """Longest run of identical (tool, args) calls. One retry after a timeout is
    legitimate and is forgiven; anything beyond that counts."""
    best = run = 0
    prev: Step | None = None
    forgiven = 0
    for s in steps:
        if prev and (prev.tool, prev.args) == (s.tool, s.args):
            run += 1
        else:
            run, forgiven = 1, 1 if s.status == "timeout" else 0
        best = max(best, run - forgiven)
        prev = s
    return max(best, 1) if steps else 0


def loop_score(steps: list[Step]) -> float:
    run = longest_repeat_run(steps)
    if run >= STUCK_RUN:
        return 0.0
    return 0.5 if run == 2 else 1.0


def score_case(case: Case, traj: Trajectory) -> CaseScore:
    answer_ok = traj.success and any(s.lower() in traj.answer.lower() for s in case.answer_contains)
    path = path_score(case.expected_path, traj.path)
    eff = efficiency_score(case.optimal_steps, len(traj.steps))
    loop = loop_score(traj.steps)
    overall = 0.4 * answer_ok + 0.2 * path + 0.2 * eff + 0.2 * loop
    stuck = loop == 0.0
    overall = round(overall, 3)
    passed = answer_ok and not stuck and overall >= PASS_THRESHOLD

    notes = []
    if stuck:
        notes.append(f"STUCK LOOP x{longest_repeat_run(traj.steps)}")
    if not answer_ok:
        notes.append("wrong/failed answer")
    if path < 1.0 and not stuck:
        notes.append("off expected path")
    if eff < 1.0 and not stuck:
        notes.append(f"{len(traj.steps)} steps vs {case.optimal_steps} optimal")
    return CaseScore(answer_ok, round(path, 3), round(eff, 3), loop, round(overall, 3), passed, stuck, "; ".join(notes))
