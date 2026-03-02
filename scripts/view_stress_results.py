#!/usr/bin/env python3
"""Generate an HTML dashboard from the stress test trendline.

Reads ~/.forge/harness_trend.jsonl and produces an interactive HTML report
with charts for pass rate, timing, and failure breakdown.

Usage:
    python scripts/view_stress_results.py           # Generate and open
    python scripts/view_stress_results.py --no-open # Generate only
"""

import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

HOME = Path.home()
TRENDLINE_FILE = HOME / ".forge" / "harness_trend.jsonl"
OUTPUT_FILE = HOME / ".forge" / "harness_dashboard.html"


def load_trendline() -> list[dict]:
    """Load all entries from the JSONL trendline."""
    entries = []
    if not TRENDLINE_FILE.exists():
        return entries
    with open(TRENDLINE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def generate_html(entries: list[dict]) -> str:
    """Generate a self-contained HTML dashboard."""
    # Prepare data for charts
    timestamps = []
    durations = []
    passed_counts = []
    failed_counts = []
    modes = []
    success_flags = []

    for e in entries:
        ts = e.get("timestamp", "")
        # Shorten to HH:MM
        try:
            dt = datetime.fromisoformat(ts)
            timestamps.append(dt.strftime("%m/%d %H:%M"))
        except (ValueError, TypeError):
            timestamps.append(ts[:16])

        durations.append(e.get("duration_s", 0))
        passed_counts.append(e.get("passed", 0))
        failed_counts.append(e.get("failed", 0))
        modes.append(e.get("mode", "unknown"))
        success_flags.append(1 if e.get("invariant_pass") else 0)

    # Compute running stats
    total = len(entries)
    total_pass = sum(success_flags)
    total_fail = total - total_pass
    pass_rate = (100 * total_pass / total) if total else 0
    avg_duration = (sum(durations) / total) if total else 0
    total_tests = sum(passed_counts) + sum(failed_counts)

    # Mode breakdown
    mode_counts = {}
    for m in modes:
        mode_counts[m] = mode_counts.get(m, 0) + 1

    # JSON-encode for JS
    ts_json = json.dumps(timestamps)
    dur_json = json.dumps(durations)
    pass_json = json.dumps(passed_counts)
    fail_json = json.dumps(failed_counts)
    success_json = json.dumps(success_flags)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge Stress Test Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', -apple-system, sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    padding: 24px;
  }}
  h1 {{
    font-size: 28px;
    color: #58a6ff;
    margin-bottom: 8px;
  }}
  .subtitle {{
    color: #8b949e;
    margin-bottom: 24px;
    font-size: 14px;
  }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .stat-card {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
  }}
  .stat-value {{
    font-size: 32px;
    font-weight: 700;
    color: #58a6ff;
  }}
  .stat-value.green {{ color: #3fb950; }}
  .stat-value.red {{ color: #f85149; }}
  .stat-value.yellow {{ color: #d29922; }}
  .stat-label {{
    font-size: 12px;
    color: #8b949e;
    text-transform: uppercase;
    margin-top: 4px;
  }}
  .chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
  }}
  .chart-card {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 20px;
  }}
  .chart-card h3 {{
    color: #c9d1d9;
    margin-bottom: 12px;
    font-size: 16px;
  }}
  .chart-card canvas {{
    width: 100% !important;
    max-height: 300px;
  }}
  .full-width {{ grid-column: 1 / -1; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin-top: 12px;
  }}
  th, td {{
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #21262d;
  }}
  th {{ color: #8b949e; font-weight: 600; }}
  .pass {{ color: #3fb950; }}
  .fail {{ color: #f85149; }}
  @media (max-width: 768px) {{
    .chart-row {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<h1>Forge Stress Test Dashboard</h1>
<p class="subtitle">Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {total} iterations | Trendline: ~/.forge/harness_trend.jsonl</p>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value {'green' if pass_rate >= 95 else 'yellow' if pass_rate >= 80 else 'red'}">{pass_rate:.1f}%</div>
    <div class="stat-label">Pass Rate</div>
  </div>
  <div class="stat-card">
    <div class="stat-value green">{total_pass}</div>
    <div class="stat-label">Iterations Passed</div>
  </div>
  <div class="stat-card">
    <div class="stat-value {'red' if total_fail > 0 else 'green'}">{total_fail}</div>
    <div class="stat-label">Iterations Failed</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{avg_duration:.1f}s</div>
    <div class="stat-label">Avg Duration</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{total_tests:,}</div>
    <div class="stat-label">Total Test Runs</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{total}</div>
    <div class="stat-label">Total Iterations</div>
  </div>
</div>

<div class="chart-row">
  <div class="chart-card">
    <h3>Pass / Fail per Iteration</h3>
    <canvas id="passFailChart"></canvas>
  </div>
  <div class="chart-card">
    <h3>Duration per Iteration (seconds)</h3>
    <canvas id="durationChart"></canvas>
  </div>
</div>

<div class="chart-row">
  <div class="chart-card full-width">
    <h3>Cumulative Success Rate</h3>
    <canvas id="successRateChart"></canvas>
  </div>
</div>

<div class="chart-row">
  <div class="chart-card full-width">
    <h3>Run History</h3>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Timestamp</th>
          <th>Mode</th>
          <th>Passed</th>
          <th>Failed</th>
          <th>Duration</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
"""

    # Add table rows (most recent first)
    for i, e in enumerate(reversed(entries)):
        idx = total - i
        ts = timestamps[total - 1 - i] if (total - 1 - i) < len(timestamps) else ""
        p = e.get("passed", 0)
        f = e.get("failed", 0)
        d = e.get("duration_s", 0)
        m = e.get("mode", "?")
        ok = e.get("invariant_pass", False)
        status_cls = "pass" if ok else "fail"
        status_txt = "PASS" if ok else "FAIL"
        html += f'        <tr><td>{idx}</td><td>{ts}</td><td>{m}</td>'
        html += f'<td class="pass">{p}</td><td class="{"fail" if f else ""}">{f}</td>'
        html += f'<td>{d:.1f}s</td><td class="{status_cls}">{status_txt}</td></tr>\n'

    html += f"""      </tbody>
    </table>
  </div>
</div>

<script>
const labels = {ts_json};
const passData = {pass_json};
const failData = {fail_json};
const durData = {dur_json};
const successData = {success_json};

// Pass/Fail stacked bar
new Chart(document.getElementById('passFailChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'Passed', data: passData, backgroundColor: '#3fb950' }},
      {{ label: 'Failed', data: failData, backgroundColor: '#f85149' }},
    ]
  }},
  options: {{
    responsive: true,
    scales: {{
      x: {{ stacked: true, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
      y: {{ stacked: true, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    }},
    plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
  }}
}});

// Duration line
new Chart(document.getElementById('durationChart'), {{
  type: 'line',
  data: {{
    labels: labels,
    datasets: [{{
      label: 'Duration (s)',
      data: durData,
      borderColor: '#58a6ff',
      backgroundColor: 'rgba(88,166,255,0.1)',
      fill: true,
      tension: 0.3,
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    }},
    plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
  }}
}});

// Cumulative success rate
const cumRate = [];
let cumPass = 0;
for (let i = 0; i < successData.length; i++) {{
  cumPass += successData[i];
  cumRate.push(((cumPass / (i + 1)) * 100).toFixed(1));
}}
new Chart(document.getElementById('successRateChart'), {{
  type: 'line',
  data: {{
    labels: labels,
    datasets: [{{
      label: 'Cumulative Pass Rate (%)',
      data: cumRate,
      borderColor: '#3fb950',
      backgroundColor: 'rgba(63,185,80,0.1)',
      fill: true,
      tension: 0.3,
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
      y: {{ min: 0, max: 100, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    }},
    plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
  }}
}});
</script>
</body>
</html>"""

    return html


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate HTML dashboard from stress test trendline")
    parser.add_argument(
        "--no-open", action="store_true",
        help="Generate HTML but don't open in browser")
    args = parser.parse_args()

    entries = load_trendline()
    if not entries:
        print(f"No trendline data found at {TRENDLINE_FILE}")
        print("Run the stress tests first: python scripts/run_live_stress.py")
        sys.exit(1)

    html = generate_html(entries)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {OUTPUT_FILE}")
    print(f"  {len(entries)} data points from trendline")

    if not args.no_open:
        webbrowser.open(str(OUTPUT_FILE))


if __name__ == "__main__":
    main()
