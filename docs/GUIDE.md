# Agent Gauntlet: Owner's Guide

What every part does, the stack, and how to use it yourself.

---

## 1. The idea

An **AI agent** is an LLM that can call **tools** (look up a customer, search the web). It decides which tool to call, reads the result, maybe calls another, then answers.

Agents look great when everything works. In production a database goes down, an API times out, a search returns nothing, and a bad agent then retries forever, burns money, or invents an answer.

**Agent Gauntlet breaks the agent's tools on purpose (chaos testing) and grades how it copes.** It grades the whole **trajectory** (every tool call), not just the final answer.

## 2. What happens when you click "Run"

```
Browser: "Where is order O-5001?" + fault: get_order = error
   |
FastAPI server (Vercel)
   |
Agent loop -> Brain decides next step -> Groq (real LLM): "call get_order"
   |
Tool runner -> fault injector breaks get_order -> ERROR
   |
Brain again -> "call web_search instead"
   |
Final answer -> Grader scores it -> saved to Postgres (Neon)
   |
Dashboard shows each step live, red/green
```

## 3. Files

### `app/`: the live application
| File | Does |
|---|---|
| `models.py` | Data shapes (Step, Trajectory, FaultSpec) with Pydantic; bad data is rejected automatically |
| `tools.py` | Fake company backend: customers, orders, web search. Fake so every run is repeatable |
| `faults.py` | Chaos injector: `error`, `empty`, `timeout`, `malformed`, `slow` on any tool |
| `brains.py` | Decision makers. Scripted: `resilient` (good), `naive` (gets stuck), `wasteful` (extra calls). `LLMBrain` asks a real model |
| `llm.py` | OpenAI-compatible client (Groq, Ollama, OpenRouter, Gemini). Retries when rate-limited (429) |
| `agent.py` | The loop: ask brain -> run tool (maybe broken) -> feed result back -> repeat (max 10 steps). Counts tokens/cost |
| `api.py` | The web endpoints (URLs) |
| `guard.py` | Per-IP rate limiting so strangers cannot burn your free Groq quota |
| `env.py` | Reads secrets from `.env.local` on your PC |
| `static/dashboard.html` | The web page |

### `gauntlet/`: the evaluation engine
| File | Does |
|---|---|
| `metrics.py` | The grader: 4 scores per case (see section 5) |
| `deepeval_bridge.py` | Converts runs to DeepEval test cases |
| `judge.py` | Optional AI judge for "graceful recovery" |
| `runner.py` | Runs all 20 cases against one agent |
| `db.py`, `store.py` | Save/load runs, compare runs, heatmap |
| `report.py` | HTML report |
| `cli.py` | Terminal commands (`py -m gauntlet ...`) |

### Other
| File | Does |
|---|---|
| `datasets/cases.json` | The 20 test cases: question, fault, expected tool path, expected answer |
| `baselines/baseline.json` | Cases that passed last time; a new failure = regression |
| `alembic/` | Database migrations (versioned table changes, "git for tables") |
| `tests/` | 43 tests, offline, no keys |
| `main.py` | Entry point Vercel looks for |
| `.github/workflows/ci.yml` | Runs tests + regression gate on every push |
| `Dockerfile` | Run anywhere in a container |
| `.env.local` | YOUR SECRETS. Never commit, never paste in chat |

## 4. The stack

- **FastAPI**: Python web framework. You write a function, add `@app.get("/path")`, and it becomes a URL returning JSON. Validates input with Pydantic, auto-generates docs at `/docs`, streams live results (`/run/stream`), async so it serves many users at once.
- **Pydantic**: data validation (e.g. `max_steps` must be 1-10, else rejected).
- **Groq**: runs open models on fast chips with a free tier. Model: `openai/gpt-oss-120b`. The app sends the conversation + tool list; the model replies with which tool to call.
- **DeepEval**: the standard LLM-eval library ("pytest for AI"). Uses `ToolCorrectnessMetric`, a custom `StuckLoopMetric`, and `GEval` (AI judge).
- **PostgreSQL + Neon**: Postgres is the database most companies use; Neon hosts it free (Singapore). Sleeps after 5 min idle, wakes in ~1s; code retries while it wakes.
- **SQLAlchemy + Alembic**: SQLAlchemy = database as Python classes (same code on Postgres and local SQLite). Alembic = migrations.
- **Vercel**: hosts the app 24/7, serverless (runs per request, so free). Secrets live in Vercel settings, not GitHub.
- **pytest**: 43 tests, offline, never touch real DB or keys.
- **GitHub Actions (CI)**: every push runs tests + regression gate; red build if an agent got worse.
- **Rich + Typer**: colourful terminal commands and live tables.
- **Docker**: package the app to run the same anywhere.

## 5. Grading

| Score | Weight | Question |
|---|---|---|
| Answer | 40% | Correct, or honest about what failed? |
| Path | 20% | Right tools in roughly the right order? |
| Efficiency | 20% | Best possible steps / steps taken |
| Loop | 20% | Same call 3+ times in a row = instant fail |

Pass = answer right AND not stuck AND total >= 0.90.
Design choices: rule-based checks first (free, repeatable); AI judge only for fuzzy things. One retry after a timeout is allowed; eight is a bug.

## 6. Interview talking points

1. "`naive` passes every normal test. Only breaking its tools exposes it, so output-only evals are not enough."
2. "My first real-model run scored 40%. The grader was wrong, not the model (a special space character and the model's own wording). After fixing it: 95%. Check the grader before blaming the model."
3. "Deployed with a real model for $0, provider-neutral, rate-limited, regression gate in CI."

---

# HOW TO USE IT YOURSELF

## A. The live website (no setup, works from any device)

Open **https://agent-gauntlet-nine.vercel.app**

1. Pick an **agent**: `llm` (real AI), or `naive` / `resilient` / `wasteful` (scripted).
2. Type a **question**, e.g. `Where is order O-5001?` (other IDs: customers `C-1001`, `C-1002`; `C-9999` does not exist).
3. Pick a **fault**: which tool to break and how (or a preset like "DB down").
4. Click **Run live** and watch each step appear: green = ok, red = broken.
5. Run the **full suite** for an agent to get its pass rate, then look at the **heatmap** and **compare** two runs.

Limits on the live site: 30 runs/minute per person, 10 real-model runs/minute, 1 full real-model suite per minute.

Interactive API docs: **https://agent-gauntlet-nine.vercel.app/docs**. Click an endpoint -> "Try it out" -> "Execute".

## B. On your PC (open a terminal in `agent-gauntlet`)

Use the project's Python: `.\.venv\Scripts\python` (below shortened to `py`; if `py` complains about missing packages, use `.\.venv\Scripts\python` instead).

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python -m gauntlet demo` | The showpiece: all scripted agents through the chaos suite with a live table, then builds the HTML report |
| `.\.venv\Scripts\python -m gauntlet run --agent llm` | Run the 20 cases with the real model (uses your Groq key) |
| `.\.venv\Scripts\python -m gauntlet run --agent naive` | Run with a scripted agent (free, instant) |
| `.\.venv\Scripts\python -m gauntlet compare --baseline resilient --candidate naive` | Which cases got worse between two agents |
| `.\.venv\Scripts\python -m gauntlet serve` | Start the dashboard locally at http://127.0.0.1:8000 |
| `.\.venv\Scripts\python -m gauntlet report` | Rebuild the HTML report (in `reports/`) |
| `.\.venv\Scripts\python -m gauntlet gate` | CI check: fails if a case that used to pass now fails |
| `.\.venv\Scripts\python -m pytest` | Run the 43 tests |

Note: on your PC the commands read `.env.local`, so runs are saved to the **same live Neon database** and show up on the website. To keep a test run private, add `--no-persist` to `run`.

## C. Change things

- **Switch model**: edit `GAUNTLET_LLM_MODEL` in `.env.local` (local) and in Vercel (`vercel env rm GAUNTLET_LLM_MODEL production`, then `vercel env add GAUNTLET_LLM_MODEL production`, then `vercel deploy --prod`). List Groq's current models at console.groq.com.
- **Add a test case**: copy one block in `datasets/cases.json`, give it a new `id`, change the question/fault/expected path/answer. Then update `test_dataset_has_twenty_unique_cases` in `tests/test_agent_and_metrics.py` to the new count.
- **Deploy your changes**: `git add -A`, `git commit -m "..."`, `git push`, then `vercel deploy --prod`.

## D. If something breaks

| Symptom | Fix |
|---|---|
| Real model errors with 401 | Groq key wrong/revoked: make a new one, update `.env.local` and Vercel |
| Real model errors with 404 | Groq retired the model: pick a new one (section C) |
| Slow first load | Neon was asleep; wait a few seconds |
| "Too many requests" | You hit the rate limit; wait a minute |
| Check server errors | `vercel logs --since 10m --query level:error` |
