"""Benchmark reporting — HTML visualization of model comparison results.

Generates self-contained HTML reports with Chart.js for:
  - Model comparison radar charts
  - Quality distribution histograms
  - Duration/token efficiency trends
  - Pass rate comparison tables
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ModelScore:
    """Aggregate scores for one model across a benchmark suite."""
    model: str
    backend: str = ""
    pass_rate: float = 0.0
    avg_quality: float = 0.0
    avg_duration_s: float = 0.0
    avg_tokens_out: int = 0
    avg_tokens_in: int = 0
    total_scenarios: int = 0
    scenarios_passed: int = 0
    quality_scores: list = field(default_factory=list)
    durations: list = field(default_factory=list)


def build_comparison_report(results: list[dict],
                            title: str = "Forge Benchmark Report",
                            ) -> str:
    """Build self-contained HTML report comparing benchmark results.

    Args:
        results: List of BenchmarkSuiteResult dicts (from save_result)
        title: Report title

    Returns:
        Complete HTML string ready to write to file.
    """
    # Group results by model
    models: dict[str, ModelScore] = {}
    for suite_result in results:
        model = suite_result.get("model", "unknown")
        if model not in models:
            models[model] = ModelScore(model=model)
        ms = models[model]

        for scenario in suite_result.get("results", []):
            ms.total_scenarios += 1
            if scenario.get("passed"):
                ms.scenarios_passed += 1
            ms.durations.append(scenario.get("duration_s", 0))
            q = scenario.get("quality_score", 0)
            if q > 0:
                ms.quality_scores.append(q)

        ms.pass_rate = ms.scenarios_passed / max(1, ms.total_scenarios)
        ms.avg_duration_s = (
            sum(ms.durations) / max(1, len(ms.durations)))
        ms.avg_quality = (
            sum(ms.quality_scores) / max(1, len(ms.quality_scores))
            if ms.quality_scores else 0)

    model_list = sorted(models.values(), key=lambda m: -m.pass_rate)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # Build HTML
    return _render_html(title, timestamp, model_list, results)


def _render_html(title: str, timestamp: str,
                 model_list: list[ModelScore],
                 raw_results: list[dict]) -> str:
    """Render the full HTML report."""

    # Prepare chart data
    model_names = json.dumps([m.model for m in model_list])
    pass_rates = json.dumps([round(m.pass_rate * 100, 1) for m in model_list])
    avg_qualities = json.dumps([round(m.avg_quality * 100, 1) for m in model_list])
    avg_durations = json.dumps([round(m.avg_duration_s, 2) for m in model_list])
    scenario_counts = json.dumps([m.total_scenarios for m in model_list])

    # Build per-model quality distributions for box plot
    quality_data = json.dumps({
        m.model: [round(q * 100, 1) for q in m.quality_scores]
        for m in model_list if m.quality_scores
    })

    # Stats cards
    total_runs = len(raw_results)
    total_scenarios = sum(m.total_scenarios for m in model_list)
    best_model = model_list[0].model if model_list else "N/A"
    best_rate = f"{model_list[0].pass_rate * 100:.0f}%" if model_list else "N/A"

    # Scenario results table
    table_rows = []
    for suite in raw_results:
        model = suite.get("model", "?")
        for sc in suite.get("results", []):
            status = "PASS" if sc.get("passed") else "FAIL"
            color = "#3fb950" if sc.get("passed") else "#f85149"
            table_rows.append(
                f'<tr><td>{model}</td>'
                f'<td>{sc.get("scenario_name", sc.get("scenario_id", "?"))}</td>'
                f'<td style="color:{color}">{status}</td>'
                f'<td>{sc.get("duration_s", 0):.3f}s</td>'
                f'<td>{sc.get("quality_score", 0) * 100:.0f}%</td>'
                f'<td>{sc.get("tokens_out", 0)}</td></tr>'
            )
    table_html = "\n".join(table_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 20px; }}
  h1 {{ color: #58a6ff; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; font-size: 14px; margin-bottom: 20px; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr);
            gap: 12px; margin-bottom: 24px; }}
  .stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 16px; text-align: center; }}
  .stat .value {{ font-size: 28px; font-weight: bold; color: #58a6ff; }}
  .stat .label {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr;
             gap: 16px; margin-bottom: 24px; }}
  .chart-card {{ background: #161b22; border: 1px solid #30363d;
                 border-radius: 8px; padding: 16px; }}
  .chart-card h3 {{ color: #e6edf3; margin-bottom: 12px; font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22;
           border-radius: 8px; overflow: hidden; }}
  th {{ background: #21262d; color: #e6edf3; padding: 10px 12px;
       text-align: left; font-size: 13px; }}
  td {{ padding: 8px 12px; border-top: 1px solid #30363d; font-size: 13px; }}
  tr:hover td {{ background: #1c2128; }}
  .footer {{ text-align: center; color: #484f58; font-size: 12px;
             margin-top: 20px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">Generated {timestamp} — {total_runs} suite runs, {total_scenarios} total scenarios</div>

<div class="stats">
  <div class="stat"><div class="value">{len(model_list)}</div><div class="label">Models Tested</div></div>
  <div class="stat"><div class="value">{total_scenarios}</div><div class="label">Total Scenarios</div></div>
  <div class="stat"><div class="value">{best_model}</div><div class="label">Best Model</div></div>
  <div class="stat"><div class="value">{best_rate}</div><div class="label">Best Pass Rate</div></div>
</div>

<div class="charts">
  <div class="chart-card">
    <h3>Pass Rate by Model</h3>
    <canvas id="passChart" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>Avg Quality Score by Model</h3>
    <canvas id="qualityChart" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>Avg Duration by Model</h3>
    <canvas id="durationChart" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>Radar — Model Comparison</h3>
    <canvas id="radarChart" height="200"></canvas>
  </div>
</div>

<h3 style="color:#e6edf3;margin-bottom:12px">Scenario Results</h3>
<table>
<thead><tr><th>Model</th><th>Scenario</th><th>Status</th><th>Duration</th><th>Quality</th><th>Tokens Out</th></tr></thead>
<tbody>{table_html}</tbody>
</table>

<div class="footer">Forge Benchmark Report — generated by forge/benchmark_report.py</div>

<script>
const labels = {model_names};
const passRates = {pass_rates};
const qualities = {avg_qualities};
const durations = {avg_durations};

const colors = ['#58a6ff','#3fb950','#f0883e','#bc8cff','#f85149','#39d353','#56d4dd','#db61a2'];

new Chart(document.getElementById('passChart'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label: 'Pass Rate %', data: passRates,
    backgroundColor: labels.map((_, i) => colors[i % colors.length] + '88'),
    borderColor: labels.map((_, i) => colors[i % colors.length]),
    borderWidth: 1 }}] }},
  options: {{ scales: {{ y: {{ beginAtZero: true, max: 100,
    ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ display: false }} }} }},
    plugins: {{ legend: {{ display: false }} }} }}
}});

new Chart(document.getElementById('qualityChart'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label: 'Quality %', data: qualities,
    backgroundColor: labels.map((_, i) => colors[i % colors.length] + '88'),
    borderColor: labels.map((_, i) => colors[i % colors.length]),
    borderWidth: 1 }}] }},
  options: {{ scales: {{ y: {{ beginAtZero: true, max: 100,
    ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ display: false }} }} }},
    plugins: {{ legend: {{ display: false }} }} }}
}});

new Chart(document.getElementById('durationChart'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label: 'Avg Duration (s)', data: durations,
    backgroundColor: labels.map((_, i) => colors[i % colors.length] + '88'),
    borderColor: labels.map((_, i) => colors[i % colors.length]),
    borderWidth: 1 }}] }},
  options: {{ scales: {{ y: {{ beginAtZero: true,
    ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
    x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ display: false }} }} }},
    plugins: {{ legend: {{ display: false }} }} }}
}});

// Radar chart — normalize all metrics to 0-100
const maxDur = Math.max(...durations, 1);
new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: ['Pass Rate', 'Quality', 'Speed', 'Scenarios'],
    datasets: labels.map((name, i) => ({{
      label: name,
      data: [
        passRates[i],
        qualities[i],
        Math.max(0, 100 - (durations[i] / maxDur * 100)),
        Math.min(100, {scenario_counts}[i] * 10),
      ],
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length] + '22',
      borderWidth: 2,
    }}))
  }},
  options: {{
    scales: {{ r: {{
      beginAtZero: true, max: 100,
      ticks: {{ color: '#8b949e', backdropColor: 'transparent' }},
      grid: {{ color: '#21262d' }},
      pointLabels: {{ color: '#c9d1d9' }}
    }} }},
    plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
  }}
}});
</script>
</body>
</html>"""


def save_report(html: str, path: Path = None) -> Path:
    """Write HTML report to disk."""
    if path is None:
        path = Path.home() / ".forge" / "benchmark_report.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
