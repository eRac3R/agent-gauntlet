"""Gauntlet CLI:  py -m gauntlet <command>"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from app.brains import SCRIPTED_AGENTS
from gauntlet import store
from gauntlet.metrics import load_cases
from gauntlet.report import build_report
from gauntlet.runner import run_case, run_suite
from app.brains import make_brain

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

cli = typer.Typer(add_completion=False, help="Chaos-test and grade AI agents.")
console = Console()
ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "baselines" / "baseline.json"
REPORT = ROOT / "reports" / "report.html"


def _cell(r: dict | None) -> str:
    if r is None:
        return "[dim]...[/]"
    s = r["score"]
    if s["stuck"]:
        return "[bold red]LOOP[/]"
    return f"[green]PASS {s['overall']:.2f}[/]" if s["passed"] else f"[red]FAIL {s['overall']:.2f}[/]"


@cli.command()
def run(agent: str = "resilient", persist: bool = True):
    """Run the 20-case suite against one agent."""
    out = run_suite(agent, persist=persist)
    t = Table(title=f"{agent}: {out['pass_rate']:.0%} passed")
    for col in ("case", "fault", "path", "score", "result", "notes"):
        t.add_column(col)
    for r in out["results"]:
        s = r["score"]
        t.add_row(r["case"]["id"], r["case"]["fault"]["kind"], " > ".join(x["tool"] for x in r["traj"]["steps"]),
                  f"{s['overall']:.2f}", "[green]PASS[/]" if s["passed"] else "[red]FAIL[/]", s["notes"])
    console.print(t)
    console.print(f"{out['tokens']:,} tokens (est.), ${out['cost_usd']:.4f} (est.), run id {out['run_id']}")


@cli.command()
def demo(delay: float = 0.04, agents: str = ",".join(SCRIPTED_AGENTS)):
    """The showpiece: run every agent through the chaos suite live, then build the report."""
    names = agents.split(",")
    cases = load_cases()
    results: dict[tuple[str, str], dict] = {}

    def table() -> Table:
        t = Table(title="[bold]AGENT GAUNTLET[/]  chaos suite", header_style="bold cyan")
        t.add_column("case")
        t.add_column("fault")
        for n in names:
            t.add_column(n, justify="center")
        for c in cases:
            t.add_row(c.id, c.fault.kind.value, *[_cell(results.get((n, c.id))) for n in names])
        done = [[results.get((n, c.id)) for c in cases] for n in names]
        t.add_section()
        t.add_row("pass rate", "", *[
            f"[bold]{sum(r['score']['passed'] for r in col if r) / len(cases):.0%}[/]" for col in done
        ])
        return t

    summaries = {}
    with Live(table(), console=console, refresh_per_second=20) as live:
        for n in names:
            brain = make_brain(n)
            batch = []
            for c in cases:
                r = run_case(n, c, brain)
                results[(n, c.id)] = r
                batch.append(r)
                live.update(table())
                time.sleep(delay)
            summaries[n] = (store.save_run(n, batch), batch)

    base, cand = ("resilient" if "resilient" in names else names[0]), names[-1]
    for n in names:
        if n != base:
            cmp = store.compare_runs(summaries[base][0], summaries[n][0])
            console.print(Panel(
                f"[bold]{base}[/] -> [bold]{n}[/]: [red]{len(cmp['regressions'])} regressions[/], "
                f"[green]{len(cmp['fixes'])} fixes[/]\n"
                + ", ".join(r["case_id"] for r in cmp["regressions"][:12]),
                title="regression diff", border_style="red" if cmp["regressions"] else "green"))
    path = build_report(REPORT, candidate=cand)
    console.print(f"\n[bold green]Report:[/] {path}")
    console.print("[bold]Live dashboard:[/] py -m gauntlet serve  ->  http://127.0.0.1:8000")


@cli.command()
def compare(baseline: str = "resilient", candidate: str = "naive"):
    """Run two agents and show which cases regressed."""
    a, b = run_suite(baseline), run_suite(candidate)
    cmp = store.compare_runs(a["run_id"], b["run_id"])
    console.print_json(json.dumps(cmp))


@cli.command()
def report(candidate: str = "naive"):
    """Rebuild the HTML report from the database."""
    console.print(build_report(REPORT, candidate=candidate))


@cli.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the FastAPI app and live dashboard."""
    import uvicorn

    uvicorn.run("app.api:app", host=host, port=port)


@cli.command()
def baseline(agent: str = "resilient"):
    """Record which cases pass today as the CI baseline."""
    out = run_suite(agent, persist=False)
    passed = sorted(r["case"]["id"] for r in out["results"] if r["score"]["passed"])
    BASELINE.parent.mkdir(exist_ok=True)
    BASELINE.write_text(json.dumps({"agent": agent, "passed": passed}, indent=2), encoding="utf-8")
    console.print(f"baseline saved: {len(passed)}/{out['n']} cases pass")


@cli.command()
def gate(agent: str = "resilient"):
    """CI gate: exit 1 if any baseline-passing case now fails."""
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    out = run_suite(agent, persist=False)
    now = {r["case"]["id"] for r in out["results"] if r["score"]["passed"]}
    regressed = sorted(set(base["passed"]) - now)
    if regressed:
        console.print(f"[bold red]GATE FAILED[/]: {len(regressed)} regressions vs baseline: {', '.join(regressed)}")
        raise typer.Exit(1)
    console.print(f"[bold green]GATE PASSED[/]: no regressions across {len(base['passed'])} baseline cases")


@cli.command()
def calibrate(labels: Path = ROOT / "datasets" / "human_labels.json", agent: str = "resilient"):
    """Compare our automated pass/fail verdicts against human labels (judge calibration)."""
    rows = json.loads(Path(labels).read_text(encoding="utf-8"))
    if not rows:
        console.print("[yellow]No labels yet.[/] Add entries like "
                      '{"case_id": "error-01", "agent": "naive", "human_pass": false} to '
                      f"{labels} then re-run.")
        raise typer.Exit(0)
    by_agent: dict[str, dict] = {}
    agree = 0
    for row in rows:
        res = by_agent.setdefault(row["agent"], {r["case"]["id"]: r for r in run_suite(row["agent"], persist=False)["results"]})
        verdict = res[row["case_id"]]["score"]["passed"]
        agree += verdict == row["human_pass"]
    console.print(f"Metric/human agreement: {agree}/{len(rows)} = {agree / len(rows):.0%}")


if __name__ == "__main__":
    cli()
