<?php
/**
 * Forge Reliability Report Viewer
 *
 * Public endpoint for viewing shared assurance/break reports.
 *
 * Endpoints:
 *   GET  ?id=<run_id>      — view a specific report
 *   GET  ?action=list      — list recent public reports (leaderboard)
 *
 * Reports are fetched from the assurance index (populated by assurance_verify.php).
 * Only verified, signed reports are displayed.
 *
 * Deploy to: dirt-star.com/Forge/report_view.php
 */

$DATA_DIR      = __DIR__ . '/data';
$REPORTS_DIR   = $DATA_DIR . '/assurance/reports';
$ASSURANCE_IDX = $DATA_DIR . '/assurance/index.json';

// ── Helpers ───────────────────────────────────────────────────────────────────

function load_json(string $path): array {
    if (!file_exists($path)) return [];
    $raw = @file_get_contents($path);
    return $raw ? (json_decode($raw, true) ?? []) : [];
}

function json_response(int $code, $data): void {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

function html_head(string $title): void {
    global $page_title, $page_id, $hide_nav, $auth;
    $page_title = $title . ' — Forge Reliability';
    $page_id    = 'scoreboard';
    require __DIR__ . '/includes/header.php';
    echo '<style>
  .rpt-body  { font-family: monospace; max-width: 860px; margin: 32px auto; padding: 0 20px; }
  .rpt-body h1 { color: #58a6ff; margin-bottom: 12px; }
  .rpt-body h2 { color: #79c0ff; border-bottom: 1px solid #30363d; padding-bottom: 6px; margin: 24px 0 12px; }
  .pass    { color: #3fb950; }
  .fail    { color: #f85149; }
  .partial { color: #d29922; }
  .rpt-body table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
  .rpt-body th, .rpt-body td { padding: 6px 10px; border: 1px solid #30363d; text-align: left; }
  .rpt-body th { background: #161b22; color: #58a6ff; }
  .rpt-score { font-size: 2em; font-weight: bold; margin: 8px 0; }
  .rpt-meta  { color: #8b949e; font-size: 0.85em; margin: 4px 0; }
  .rpt-body pre { background: #161b22; padding: 12px; overflow-x: auto; font-size: 0.85em; border-radius: 4px; }
  .rpt-body a { color: #58a6ff; }
</style><div class="rpt-body">';
}

function html_foot(): void {
    echo "<p class='rpt-meta' style='margin-top:32px'>Forge Reliability Infrastructure &mdash; Reports are Ed25519-signed and tamper-evident.</p>";
    echo '</div><!-- /rpt-body -->';
    require __DIR__ . '/includes/footer.php';
}

// ── Dispatch ──────────────────────────────────────────────────────────────────

$action = $_GET['action'] ?? '';
$run_id = $_GET['id'] ?? '';

// Accept JSON requests
$wants_json = (strpos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false)
           || ($_GET['fmt'] ?? '') === 'json';

// ── View single report ────────────────────────────────────────────────────────

if ($run_id) {
    // Sanitise run_id — hex string only
    $safe_id = preg_replace('/[^a-f0-9]/', '', strtolower($run_id));
    if (strlen($safe_id) < 8) {
        http_response_code(400);
        echo 'Invalid report ID.';
        exit;
    }

    $report_path = $REPORTS_DIR . '/' . $safe_id . '.json';
    if (!file_exists($report_path)) {
        http_response_code(404);
        echo "Report '{$safe_id}' not found.";
        exit;
    }

    $report = load_json($report_path);

    if ($wants_json) {
        json_response(200, $report);
    }

    // HTML view
    $pct      = round($report['pass_rate'] * 100, 1);
    $model    = htmlspecialchars($report['model'] ?? 'unknown');
    $run_id_s = htmlspecialchars($report['run_id'] ?? $safe_id);
    $verdict  = $report['pass_rate'] >= 0.95 ? 'PASS'
              : ($report['pass_rate'] >= 0.75 ? 'PARTIAL PASS' : 'FAIL');
    $v_class  = $report['pass_rate'] >= 0.95 ? 'pass'
              : ($report['pass_rate'] >= 0.75 ? 'partial' : 'fail');

    html_head("Report {$run_id_s}");
    echo "<h1>Forge Reliability Report</h1>";
    echo "<p class='rpt-meta'>Run ID: <code>{$run_id_s}</code> &nbsp;|&nbsp; Model: <strong>{$model}</strong> &nbsp;|&nbsp; Forge v" . htmlspecialchars($report['forge_version'] ?? '?') . "</p>";
    echo "<p class='rpt-score {$v_class}'>{$pct}% &mdash; {$verdict}</p>";
    echo "<p class='rpt-meta'>{$report['scenarios_passed']}/{$report['scenarios_run']} scenarios passed &nbsp;|&nbsp; Duration: {$report['duration_s']}s</p>";

    // Category table
    echo "<h2>Category Results</h2><table><tr><th>Category</th><th>Pass Rate</th></tr>";
    foreach ($report['category_pass_rates'] ?? [] as $cat => $rate) {
        $cpct = round($rate * 100, 1);
        $cls  = $rate >= 1.0 ? 'pass' : ($rate > 0 ? 'partial' : 'fail');
        echo "<tr><td>" . htmlspecialchars($cat) . "</td><td class='{$cls}'>{$cpct}%</td></tr>";
    }
    echo "</table>";

    // Scenario results
    echo "<h2>Scenario Results</h2><table><tr><th>Scenario</th><th>Category</th><th>Result</th><th>Reason</th></tr>";
    foreach ($report['results'] ?? [] as $r) {
        $cls    = $r['passed'] ? 'pass' : 'fail';
        $label  = $r['passed'] ? 'PASS' : 'FAIL';
        $sid    = htmlspecialchars($r['scenario_id']);
        $cat    = htmlspecialchars($r['category']);
        $reason = htmlspecialchars($r['reason']);
        echo "<tr><td><code>{$sid}</code></td><td>{$cat}</td><td class='{$cls}'>{$label}</td><td>{$reason}</td></tr>";
    }
    echo "</table>";

    // Signature
    echo "<h2>Signature</h2><pre>";
    echo "Public key (Ed25519): " . htmlspecialchars($report['pub_key_b64'] ?? 'N/A') . "\n";
    $sig = htmlspecialchars(substr($report['signature'] ?? '', 0, 64));
    echo "Signature (first 64): {$sig}...";
    echo "</pre>";

    html_foot();
    exit;
}

// ── Leaderboard / list ────────────────────────────────────────────────────────

$index = load_json($ASSURANCE_IDX);
$entries = $index['entries'] ?? [];

// Sort by generated_at descending
usort($entries, function($a, $b) { return ($b['generated_at'] ?? 0) <=> ($a['generated_at'] ?? 0); });
$entries = array_slice($entries, 0, 50);

if ($wants_json || $action === 'list') {
    json_response(200, ['reports' => $entries]);
}

html_head('Forge Reliability Leaderboard');
echo "<h1>Forge Reliability Leaderboard</h1>";
echo "<p class='rpt-meta'>Community-generated, cryptographically signed model reliability benchmarks.</p>";

if (empty($entries)) {
    echo "<p>No verified reports yet. Run <code>forge break --share</code> to submit the first.</p>";
} else {
    echo "<table><tr><th>Model</th><th>Score</th><th>Scenarios</th><th>Report</th></tr>";
    foreach ($entries as $e) {
        $pct   = round(($e['pass_rate'] ?? 0) * 100, 1);
        $model = htmlspecialchars($e['model'] ?? 'unknown');
        $rid   = htmlspecialchars($e['run_id'] ?? '');
        $cls   = ($e['pass_rate'] ?? 0) >= 0.95 ? 'pass'
               : (($e['pass_rate'] ?? 0) >= 0.75 ? 'partial' : 'fail');
        echo "<tr><td>{$model}</td><td class='{$cls}'>{$pct}%</td><td>{$e['scenarios_passed']}/{$e['scenarios_run']}</td><td><a href='?id={$rid}'>{$rid}</a></td></tr>";
    }
    echo "</table>";
}

html_foot();
