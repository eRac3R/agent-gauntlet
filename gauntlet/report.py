"""Static, shareable HTML report built from the latest run of each agent."""
from __future__ import annotations

import html
from pathlib import Path

from gauntlet import store

CSS = """
:root{--bg:#0b0f17;--panel:#121826;--line:#1f2a3d;--text:#e6edf7;--muted:#8a9ab5;--ok:#3ddc97;--warn:#ffb454;--bad:#ff5d73;--accent:#6ea8ff}
@media (prefers-color-scheme: light){:root{--bg:#f5f7fb;--panel:#fff;--line:#dfe5f0;--text:#14203a;--muted:#5b6b86}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 16px 64px}h1{margin:0;font-size:30px}h1 span{color:var(--accent)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin:28px 0 12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.big{font-size:34px;font-weight:700}.muted{color:var(--muted);font-size:13px}
.bar{height:8px;border-radius:99px;background:var(--line);overflow:hidden;margin-top:8px}.bar i{display:block;height:100%}
table{border-collapse:collapse;width:100%;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:center;font-size:14px}
th:first-child,td:first-child{text-align:left}
.path{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}
.pill{padding:2px 9px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.pill.ok{color:var(--ok)}.pill.bad{color:var(--bad);border-color:var(--bad)}.pill.warn{color:var(--warn)}
.fail{color:var(--bad);font-weight:600}.pass{color:var(--ok);font-weight:600}
"""


def _color(rate: float) -> str:
    return "var(--ok)" if rate >= 0.9 else ("var(--warn)" if rate >= 0.5 else "var(--bad)")


def _pill(step: dict) -> str:
    cls = "ok" if step["status"] == "ok" else ("warn" if step["status"] in ("empty", "slow") else "bad")
    return f'<span class="pill {cls}">{html.escape(step["tool"])}</span>'


def build_report(out: Path, candidate: str | None = None) -> Path:
    latest = store.latest_by_agent()
    if not latest:
        raise RuntimeError("no runs in the database yet; run `py -m gauntlet demo` first")
    runs = {a: store.get_run(i) for a, i in latest.items()}
    cand = candidate if candidate in runs else sorted(runs)[0]

    cards = "".join(
        f'<div class="card"><div class="muted">{html.escape(a)}</div>'
        f'<div class="big" style="color:{_color(r["pass_rate"])}">{r["pass_rate"]:.0%}</div>'
        f'<div class="bar"><i style="width:{r["pass_rate"]:.0%};background:{_color(r["pass_rate"])}"></i></div>'
        f'<div class="muted">{r["tokens"]:,} tokens (est.) &middot; ${r["cost_usd"]:.4f} (est.)</div></div>'
        for a, r in sorted(runs.items())
    )

    heat = store.heatmap()
    head = "".join(f"<th>{html.escape(a)}</th>" for a in heat["agents"])
    body = ""
    for cat in heat["categories"]:
        cells = ""
        for a in heat["agents"]:
            rate = heat["grid"][cat].get(a)
            cells += "<td>-</td>" if rate is None else f'<td class="{"pass" if rate >= .9 else "fail"}">{rate:.0%}</td>'
        body += f"<tr><td>{html.escape(cat)}</td>{cells}</tr>"

    detail = ""
    for r in runs[cand]["results"]:
        steps = r["trajectory"]["steps"]
        path = "".join(_pill(s) for s in steps) or "-"
        verdict = f'<span class="{"pass" if r["passed"] else "fail"}">{"PASS" if r["passed"] else "FAIL"}</span>'
        detail += (
            f'<tr><td>{r["case_id"]}</td><td>{html.escape(r["fault_kind"])}</td>'
            f'<td><div class="path">{path}</div></td><td>{r["scores"]["overall"]:.2f}</td>'
            f'<td>{verdict}</td><td class="muted">{html.escape(r["scores"]["notes"])}</td></tr>'
        )

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Gauntlet Report</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Agent <span>Gauntlet</span> report</h1><div class="muted">Chaos-test results across {len(runs)} agents</div>
<h2>Pass rate by agent</h2><div class="cards">{cards}</div>
<h2>Pass rate by fault type</h2><table><tr><th>fault</th>{head}</tr>{body}</table>
<h2>Trajectories &middot; {html.escape(cand)}</h2>
<table><tr><th>case</th><th>fault</th><th>tool path</th><th>score</th><th>verdict</th><th>notes</th></tr>{detail}</table>
</div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
