# Agent Gauntlet

**Chaos engineering for AI agents.** Break an agent's tools on purpose, watch how it copes, and grade the whole trajectory, not just the final answer.

> Most agent demos only show the happy path. This one shows what happens at 3 a.m. when the database is down.

<!-- TODO (author, at the end): add screenshot/GIF after recording the demo by hand -->

## Why this exists

An agent that answers correctly can still be a production liability: it may call the wrong tool, burn tokens retrying the same failing call forever, or invent data when a backend returns nothing. Output-only evals miss all of that. Agent Gauntlet evaluates the **trajectory** (the sequence of tool calls) under injected faults.

## What is different from a basic trajectory test

| | Typical tutorial | Agent Gauntlet |
|---|---|---|
| Faults | one hand-coded failure | injectable fault matrix: `error`, `empty`, `timeout`, `malformed`, `slow` on any tool |
| Metrics | LLM judge only | **deterministic first** (free, reproducible), LLM judge only for subjective recovery quality |
| Retry logic | any repeat = bad | one retry after a timeout is allowed; endless retries are a stuck loop |
| Regressions | none | run history in SQLite, `compare` diff, CI gate that fails the build |
| Cost | needs a paid API key | full suite runs offline for $0 with scripted agents; real-model mode uses free local/OpenAI-compatible endpoints |

## Stack

FastAPI (async, SSE streaming) · Pydantic v2 · **DeepEval** (`ToolCorrectnessMetric`, custom `BaseMetric`, `GEval` judge) · pytest · SQLite · Rich + Typer · Docker · GitHub Actions · any OpenAI-compatible LLM (local Ollama by default)

**No vendor lock-in and no paid account needed.** The whole suite runs offline for free. For a real model, point it at a local Ollama server (free forever) or any free-tier OpenAI-compatible API:

```powershell
# optional: real model, 100% local and free
ollama pull llama3.2
$env:GAUNTLET_LLM_BASE_URL = "http://localhost:11434/v1"   # default
$env:GAUNTLET_LLM_MODEL    = "llama3.2"                    # default
py -m gauntlet run --agent llm
```

## Quick start (Windows)

```powershell
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m gauntlet demo      # live leaderboard + HTML report
.\.venv\Scripts\python -m gauntlet serve     # dashboard at http://127.0.0.1:8000
.\.venv\Scripts\python -m pytest             # 35 tests
```

## The three agents under test

| Agent | Behaviour | Result |
|---|---|---|
| `resilient` | retries a timeout once, then falls back to web search | 20/20 |
| `naive` | retries the same failing call forever (looks perfect on happy paths!) | 9/20, 11 regressions |
| `wasteful` | always web-searches first, then does the real work | extra steps and tokens |
| `llm` | a real model via any OpenAI-compatible endpoint (Ollama by default) | needs a running endpoint |

`naive` passes every happy-path case. Only fault injection exposes it. That is the point.

## How scoring works

Each case gets four sub-scores (`gauntlet/metrics.py`):

- **answer** (40%): correct content and a successful finish
- **path** (20%): ordered similarity (LCS) to the expected tool sequence
- **efficiency** (20%): optimal steps / actual steps
- **loop** (20%): 1.0 clean, 0.5 one repeat, 0.0 stuck (3+ identical calls)

A case passes only if the answer is right, it is not stuck, and the total is at least 0.90.

DeepEval layer (`gauntlet/deepeval_bridge.py`, `tests/test_evals.py`): each trajectory becomes an `LLMTestCase` and is checked with the built-in `ToolCorrectnessMetric` plus a custom `StuckLoopMetric`. A `GEval` "Graceful Recovery" judge (any local or free model as judge) runs when an endpoint is reachable.

## Regression gate

```powershell
py -m gauntlet baseline --agent resilient   # record what passes today
py -m gauntlet gate --agent naive           # GATE FAILED: 11 regressions ... (exit code 1)
```

CI (`.github/workflows/ci.yml`) runs tests, the gate and uploads the HTML report on every push.

## API

| Endpoint | Purpose |
|---|---|
| `POST /run` | run one query with an optional fault, returns the structured trajectory |
| `GET /run/stream` | same, streamed live as server-sent events |
| `POST /eval` | run the 20-case suite for an agent and store the run |
| `GET /compare?baseline=&candidate=` | regressions and fixes between two runs |
| `GET /heatmap` | pass rate by fault type and agent |
| `GET /docs` | interactive OpenAPI docs |

## Limitations (honest)

- The mock tools and scripted agents are deterministic stand-ins. The real-model path (`llm` agent, `LocalJudge`) is tested only against a fake OpenAI-compatible server in `tests/test_llm_brain.py`, not yet against a real model. Small local models can be flaky at tool calling.
- Token figures are **estimates** (chars/4) unless the endpoint reports usage. Dollar cost is a placeholder-price estimate in `app/agent.py` and is $0 for local models.
- Judge calibration (`py -m gauntlet calibrate`) needs human labels in `datasets/human_labels.json`; none are shipped, so the metric/human agreement number is not claimed.
- Dockerfile and compose are provided but were not built in the dev environment.

## YouTube demo script (about 90 seconds)

1. **Hook (0:00):** "This AI agent got every test right. Watch me break its database." Show `naive` passing happy paths.
2. **Chaos (0:15):** run `py -m gauntlet demo`. The table fills in live; the `naive` column turns red with `LOOP`.
3. **Why it matters (0:40):** open the dashboard, pick preset "DB down", agent `naive`, click Run live. Steps stack up: same call, same error, 8 times. Point at the token counter.
4. **Fix (0:60):** switch to `resilient`: error, then web search, answered in 2 steps.
5. **Close (0:75):** show `gate` failing the build and the HTML report heatmap. "Trajectory evals, as a CI check."
