#!/usr/bin/env python3
"""Local Tester Dashboard — offline, no server contact.

Generates ~/.forge/my_dashboard.html from local data:
  - ~/.forge/harness_trend.jsonl (nightly/stress history)
  - ~/.forge/harness_runs/*/summary.json (run summaries)

Opens in default browser. Works completely offline — no telemetry opt-in needed.

Usage:
    python scripts/my_dashboard.py              # generate + open
    python scripts/my_dashboard.py --no-open    # generate only
"""

import argparse
import json
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
FORGE_DIR = HOME / ".forge"
TRENDLINE_FILE = FORGE_DIR / "harness_trend.jsonl"
HARNESS_DIR = FORGE_DIR / "harness_runs"
OUTPUT_FILE = FORGE_DIR / "my_dashboard.html"


def load_trendline() -> list[dict]:
    """Load trendline entries from JSONL file."""
    entries = []
    if TRENDLINE_FILE.exists():
        for line in TRENDLINE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def load_run_summaries() -> list[dict]:
    """Load summary.json from each run directory."""
    summaries = []
    if HARNESS_DIR.exists():
        for run_dir in sorted(HARNESS_DIR.iterdir(), reverse=True):
            summary_file = run_dir / "summary.json"
            if summary_file.exists():
                try:
                    data = json.loads(summary_file.read_text(encoding="utf-8"))
                    data["_run_id"] = run_dir.name
                    summaries.append(data)
                except Exception:
                    pass
    return summaries[:50]  # Last 50 runs


def generate_html(entries: list[dict], summaries: list[dict]) -> str:
    """Generate the dashboard HTML."""
    # Aggregate stats
    total_runs = len(entries)
    total_pass = sum(1 for e in entries if e.get("invariant_pass", False))
    pass_rate = (total_pass / total_runs * 100) if total_runs else 0

    # Per-scenario breakdown
    scenario_stats = defaultdict(lambda: {"pass": 0, "fail": 0, "total": 0})
    for e in entries:
        scenario = e.get("scenario", e.get("mode", "unknown"))
        scenario_stats[scenario]["total"] += 1
        if e.get("invariant_pass", False):
            scenario_stats[scenario]["pass"] += 1
        else:
            scenario_stats[scenario]["fail"] += 1

    # Timeline (last 100 entries)
    timeline_labels = []
    timeline_pass = []
    timeline_fail = []
    for e in entries[-100:]:
        ts = e.get("timestamp", "")[:16]
        timeline_labels.append(ts)
        timeline_pass.append(1 if e.get("invariant_pass") else 0)
        timeline_fail.append(0 if e.get("invariant_pass") else 1)

    # Duration trend
    dur_labels = []
    dur_values = []
    for e in entries[-100:]:
        dur_labels.append(e.get("timestamp", "")[:16])
        dur_values.append(round(e.get("duration_s", 0), 1))

    # Scenario names and pass rates for bar chart
    sc_names = sorted(scenario_stats.keys())
    sc_rates = []
    for name in sc_names:
        st = scenario_stats[name]
        rate = (st["pass"] / st["total"] * 100) if st["total"] else 0
        sc_rates.append(round(rate, 1))

    # Recent runs table
    run_rows = ""
    for s in summaries[:20]:
        summary = s.get("summary", s)
        run_id = s.get("_run_id", "?")
        mode = summary.get("mode", "?")
        total = summary.get("total_iterations", summary.get("total_scenarios", 0))
        passed = summary.get("total_passed", 0)
        failed = summary.get("total_failed", 0)
        time_s = summary.get("total_time_s", 0)
        rate = summary.get("success_rate_pct", 0)
        started = summary.get("started", "")[:19]
        color = "#3fb950" if failed == 0 else "#f85149"
        run_rows += f"""<tr>
            <td>{run_id}</td><td>{mode}</td>
            <td>{passed}/{total}</td>
            <td style="color:{color}">{failed}</td>
            <td>{time_s:.0f}s</td>
            <td>{rate:.0f}%</td>
            <td>{started}</td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge - My Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; padding: 20px; }}
  h1 {{ color: #58a6ff; margin-bottom: 8px; }}
  .subtitle {{ color: #8b949e; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }}
  .card .label {{ color: #8b949e; font-size: 13px; text-transform: uppercase; }}
  .card .value {{ font-size: 28px; font-weight: bold; margin-top: 4px; }}
  .chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
  .chart-box h3 {{ color: #58a6ff; margin-bottom: 12px; font-size: 15px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #21262d; font-size: 13px; }}
  th {{ color: #8b949e; font-weight: 600; }}
  .green {{ color: #3fb950; }}
  .red {{ color: #f85149; }}
  @media (max-width: 800px) {{ .chart-row {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>Forge - My Dashboard</h1>
<p class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {total_runs} total test runs</p>

<div class="cards">
  <div class="card"><div class="label">Total Runs</div><div class="value">{total_runs}</div></div>
  <div class="card"><div class="label">Passed</div><div class="value green">{total_pass}</div></div>
  <div class="card"><div class="label">Failed</div><div class="value red">{total_runs - total_pass}</div></div>
  <div class="card"><div class="label">Pass Rate</div><div class="value" style="color:{'#3fb950' if pass_rate >= 90 else '#d29922' if pass_rate >= 70 else '#f85149'}">{pass_rate:.1f}%</div></div>
</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>Pass/Fail Trend (last 100)</h3>
    <canvas id="trendChart" height="200"></canvas>
  </div>
  <div class="chart-box">
    <h3>Scenario Pass Rates</h3>
    <canvas id="scenarioChart" height="200"></canvas>
  </div>
</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>Duration Trend (seconds)</h3>
    <canvas id="durChart" height="200"></canvas>
  </div>
  <div class="chart-box">
    <h3>Recent Runs</h3>
    <div style="max-height:400px;overflow-y:auto">
    <table>
      <tr><th>Run</th><th>Mode</th><th>Passed</th><th>Failed</th><th>Time</th><th>Rate</th><th>Started</th></tr>
      {run_rows}
    </table>
    </div>
  </div>
</div>

<script>
const tl = {json.dumps(timeline_labels)};
const tp = {json.dumps(timeline_pass)};
const tf = {json.dumps(timeline_fail)};
new Chart(document.getElementById('trendChart'), {{
  type: 'bar',
  data: {{
    labels: tl,
    datasets: [
      {{label:'Pass', data:tp, backgroundColor:'#3fb95080', borderColor:'#3fb950', borderWidth:1}},
      {{label:'Fail', data:tf, backgroundColor:'#f8514980', borderColor:'#f85149', borderWidth:1}}
    ]
  }},
  options: {{
    responsive: true, scales: {{x:{{display:false}}, y:{{stacked:true, ticks:{{color:'#8b949e'}}, grid:{{color:'#21262d'}}}}}},
    plugins: {{legend:{{labels:{{color:'#c9d1d9'}}}}}}
  }}
}});

const sn = {json.dumps(sc_names)};
const sr = {json.dumps(sc_rates)};
new Chart(document.getElementById('scenarioChart'), {{
  type: 'bar',
  data: {{
    labels: sn,
    datasets: [{{label:'Pass %', data:sr, backgroundColor:sr.map(v=>v>=90?'#3fb95080':v>=70?'#d2992280':'#f8514980'),
      borderColor:sr.map(v=>v>=90?'#3fb950':v>=70?'#d29922':'#f85149'), borderWidth:1}}]
  }},
  options: {{
    indexAxis: 'y', responsive: true,
    scales: {{x:{{max:100, ticks:{{color:'#8b949e'}}, grid:{{color:'#21262d'}}}}, y:{{ticks:{{color:'#c9d1d9'}}, grid:{{color:'#21262d'}}}}}},
    plugins: {{legend:{{display:false}}}}
  }}
}});

const dl = {json.dumps(dur_labels)};
const dv = {json.dumps(dur_values)};
new Chart(document.getElementById('durChart'), {{
  type: 'line',
  data: {{
    labels: dl,
    datasets: [{{label:'Duration (s)', data:dv, borderColor:'#58a6ff', backgroundColor:'#58a6ff20', fill:true, tension:0.3, pointRadius:1}}]
  }},
  options: {{
    responsive: true,
    scales: {{x:{{display:false}}, y:{{ticks:{{color:'#8b949e'}}, grid:{{color:'#21262d'}}}}}},
    plugins: {{legend:{{labels:{{color:'#c9d1d9'}}}}}}
  }}
}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Forge Local Dashboard")
    parser.add_argument("--no-open", action="store_true",
                        help="Generate HTML but don't open browser")
    args = parser.parse_args()

    entries = load_trendline()
    summaries = load_run_summaries()

    html = generate_html(entries, summaries)
    FORGE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {OUTPUT_FILE}")

    if not args.no_open:
        webbrowser.open(str(OUTPUT_FILE))


if __name__ == "__main__":
    main()
