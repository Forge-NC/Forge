<?php
/**
 * Forge Reliability Scoreboard
 *
 * The primary public face of Forge's fleet telemetry.
 * Shows community-generated, cryptographically signed model reliability rankings.
 *
 * Data source: assurance_verify.php writes to data/assurance/index.json
 *              each time a signed report is submitted.
 *
 * Endpoints:
 *   GET  /                 — HTML scoreboard
 *   GET  ?fmt=json         — JSON rankings for embedding / external tools
 *   GET  ?model=<name>     — filter to specific model history
 *
 * Deploy to: dirt-star.com/Forge/scoreboard.php (set as directory index)
 */

$DATA_DIR      = __DIR__ . '/data';
$ASSURANCE_IDX = $DATA_DIR . '/assurance/index.json';
$REPORTS_DIR   = $DATA_DIR . '/assurance/reports';

// ── Data loading ──────────────────────────────────────────────────────────────

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

// Aggregate entries by model: track best score, run count, total_runs
function aggregate_by_model(array $entries): array {
    $models = [];
    foreach ($entries as $e) {
        $model = $e['model'] ?? 'unknown';
        if (!isset($models[$model])) {
            $models[$model] = [
                'model'           => $model,
                'best_score'      => 0.0,
                'avg_score'       => 0.0,
                'run_count'       => 0,
                'scenarios_run'   => $e['scenarios_run'] ?? 0,
                'latest_run_id'   => '',
                'latest_at'       => 0,
                '_score_sum'      => 0.0,
            ];
        }
        $rate = $e['pass_rate'] ?? 0.0;
        $models[$model]['run_count']++;
        $models[$model]['_score_sum'] += $rate;
        $models[$model]['avg_score']   = $models[$model]['_score_sum']
                                       / $models[$model]['run_count'];
        if ($rate > $models[$model]['best_score']) {
            $models[$model]['best_score']    = $rate;
            $models[$model]['scenarios_run'] = $e['scenarios_run'] ?? 0;
        }
        if (($e['generated_at'] ?? 0) > $models[$model]['latest_at']) {
            $models[$model]['latest_at']     = $e['generated_at'] ?? 0;
            $models[$model]['latest_run_id'] = $e['run_id'] ?? '';
        }
    }
    // Clean up internal field
    foreach ($models as &$m) { unset($m['_score_sum']); }
    // Sort by average score desc
    uasort($models, function($a, $b) { return $b['avg_score'] <=> $a['avg_score']; });
    return array_values($models);
}

// ── Load data ─────────────────────────────────────────────────────────────────

$index   = load_json($ASSURANCE_IDX);
$entries = $index['entries'] ?? [];

// Recent runs (newest first)
usort($entries, function($a, $b) { return ($b['generated_at'] ?? 0) <=> ($a['generated_at'] ?? 0); });
$recent  = array_slice($entries, 0, 20);
$ranked  = aggregate_by_model($entries);

$total_runs   = count($entries);
$total_models = count($ranked);

// ── JSON API ──────────────────────────────────────────────────────────────────

$wants_json = (strpos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false)
           || ($_GET['fmt'] ?? '') === 'json';

if ($wants_json) {
    json_response(200, [
        'rankings'     => $ranked,
        'total_runs'   => $total_runs,
        'total_models' => $total_models,
        'recent'       => $recent,
    ]);
}

// ── Model filter ──────────────────────────────────────────────────────────────

$model_filter = $_GET['model'] ?? '';

// ── HTML via site template ─────────────────────────────────────────────────────

$page_title = 'Forge Reliability Scoreboard';
$page_id    = 'scoreboard';
require_once __DIR__ . '/includes/header.php';
?>
<style>
.sb-hero    { padding: 32px 40px; border-bottom: 1px solid #30363d; font-family: 'Courier New', monospace; }
.sb-hero h1 { color: #58a6ff; font-size: 1.6em; letter-spacing: 0.02em; }
.sb-hero p  { color: #8b949e; margin-top: 6px; font-size: 0.9em; }
.sb-tagline { color: #3fb950; font-size: 0.85em; margin-top: 4px; }
.sb-page    { max-width: 1100px; margin: 0 auto; padding: 32px 40px; font-family: 'Courier New', monospace; }
.stats-row  { display: flex; gap: 32px; margin-bottom: 32px; flex-wrap: wrap; }
.stat       { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px 24px; }
.stat-val   { font-size: 2em; color: #58a6ff; font-weight: bold; }
.stat-lbl   { color: #8b949e; font-size: 0.8em; margin-top: 2px; }
.sb-page h2 { color: #79c0ff; margin-bottom: 16px; font-size: 1.1em; border-bottom: 1px solid #21262d; padding-bottom: 8px; margin-top: 32px; }
.sb-page table      { width: 100%; border-collapse: collapse; margin-bottom: 40px; }
.sb-page th, .sb-page td { padding: 10px 14px; border: 1px solid #21262d; text-align: left; }
.sb-page th { background: #161b22; color: #58a6ff; font-size: 0.85em; letter-spacing: 0.05em; }
.sb-page td { font-size: 0.9em; }
.sb-page tr:hover { background: #161b22; }
.score      { font-weight: bold; font-size: 1.05em; }
.pass       { color: #3fb950; }
.partial    { color: #d29922; }
.fail       { color: #f85149; }
.bar        { display: inline-block; background: #21262d; width: 80px; height: 8px; border-radius: 4px; vertical-align: middle; margin-right: 6px; position: relative; overflow: hidden; }
.bar-fill   { height: 100%; border-radius: 4px; }
.rank-num   { color: #58a6ff; font-weight: bold; min-width: 30px; display: inline-block; }
.sb-page a  { color: #58a6ff; text-decoration: none; }
.sb-page a:hover { text-decoration: underline; }
.badge      { background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; border-radius: 3px; padding: 1px 6px; font-size: 0.75em; margin-left: 6px; }
.meta-note  { color: #8b949e; font-size: 0.8em; margin-top: 8px; }
.how-to     { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 20px 24px; margin-top: 32px; }
.how-to pre { color: #3fb950; margin: 10px 0 0; font-size: 0.9em; }
.sb-empty   { color: #8b949e; padding: 32px; text-align: center; }
</style>

<div class="sb-hero">
    <h1>Forge Reliability Scoreboard</h1>
    <p>Community-generated AI reliability benchmarks — cryptographically signed, tamper-evident.</p>
    <p class="sb-tagline">Not a vendor benchmark. Not self-reported. Real inference. Real signatures.</p>
</div>

<div class="sb-page">

<!-- Stats row -->
<div class="stats-row">
    <div class="stat">
        <div class="stat-val"><?= $total_models ?: '—' ?></div>
        <div class="stat-lbl">Models Tested</div>
    </div>
    <div class="stat">
        <div class="stat-val"><?= number_format($total_runs) ?: '—' ?></div>
        <div class="stat-lbl">Signed Runs</div>
    </div>
    <div class="stat">
        <div class="stat-val">5</div>
        <div class="stat-lbl">Scenario Categories</div>
    </div>
    <div class="stat">
        <div class="stat-val">Ed25519</div>
        <div class="stat-lbl">Signature Algorithm</div>
    </div>
</div>

<!-- Rankings table -->
<h2>Reliability Rankings</h2>

<?php if (empty($ranked)): ?>
<div class="sb-empty">
    No signed reports yet.<br>
    Run <code>forge break --share</code> to submit the first result.
</div>
<?php else: ?>
<table>
<thead>
<tr>
    <th>#</th>
    <th>Model</th>
    <th>Avg Score</th>
    <th>Best Score</th>
    <th>Runs</th>
    <th>Scenarios</th>
    <th>Latest Report</th>
</tr>
</thead>
<tbody>
<?php foreach ($ranked as $i => $r):
    $avg_pct  = round($r['avg_score'] * 100, 1);
    $best_pct = round($r['best_score'] * 100, 1);
    $cls      = $r['avg_score'] >= 0.90 ? 'pass' : ($r['avg_score'] >= 0.75 ? 'partial' : 'fail');
    $bar_pct  = (int)$avg_pct;
    $bar_color = $r['avg_score'] >= 0.90 ? '#3fb950' : ($r['avg_score'] >= 0.75 ? '#d29922' : '#f85149');
    $model_safe = htmlspecialchars($r['model']);
    $rid = htmlspecialchars($r['latest_run_id']);
?>
<tr>
    <td><span class="rank-num"><?= $i + 1 ?></span></td>
    <td><?= $model_safe ?></td>
    <td>
        <span class="bar"><span class="bar-fill" style="width:<?= $bar_pct ?>%;background:<?= $bar_color ?>"></span></span>
        <span class="score <?= $cls ?>"><?= $avg_pct ?>%</span>
    </td>
    <td class="<?= $cls ?>"><?= $best_pct ?>%</td>
    <td><?= $r['run_count'] ?></td>
    <td><?= $r['scenarios_run'] ?></td>
    <td><?php if ($rid): ?><a href="report_view.php?id=<?= $rid ?>"><?= substr($rid, 0, 12) ?>…</a><?php else: ?>—<?php endif; ?></td>
</tr>
<?php endforeach; ?>
</tbody>
</table>
<p class="meta-note">Average score is computed across all signed runs for that model. Each run is verified against the submitter's Ed25519 machine key.</p>
<?php endif; ?>

<!-- Recent runs -->
<?php if (!empty($recent)): ?>
<h2>Recent Reports</h2>
<table>
<thead>
<tr><th>Run ID</th><th>Model</th><th>Score</th><th>Submitted</th></tr>
</thead>
<tbody>
<?php foreach ($recent as $e):
    $pct = round(($e['pass_rate'] ?? 0) * 100, 1);
    $cls = ($e['pass_rate'] ?? 0) >= 0.90 ? 'pass' : (($e['pass_rate'] ?? 0) >= 0.75 ? 'partial' : 'fail');
    $rid = htmlspecialchars($e['run_id'] ?? '');
    $ts  = isset($e['generated_at']) ? date('Y-m-d H:i', (int)$e['generated_at']) : '—';
?>
<tr>
    <td><a href="report_view.php?id=<?= $rid ?>"><?= $rid ?></a></td>
    <td><?= htmlspecialchars($e['model'] ?? '?') ?></td>
    <td class="<?= $cls ?>"><?= $pct ?>%</td>
    <td><?= $ts ?></td>
</tr>
<?php endforeach; ?>
</tbody>
</table>
<?php endif; ?>

<!-- How to contribute -->
<div class="how-to">
    <h2>Add your model to the scoreboard</h2>
    <pre>forge break --model qwen3:14b --share</pre>
    <p class="meta-note" style="margin-top:12px">
        Requires a Forge BPoS passport. Results are signed with your machine's Ed25519 key and verified
        server-side before appearing. Forge is model-agnostic — local models, OpenAI, Anthropic,
        and any Ollama-compatible backend are all supported.
    </p>
    <p class="meta-note" style="margin-top:8px">
        <a href="https://github.com/your-repo/forge">GitHub</a> &nbsp;·&nbsp;
        <a href="report_view.php?action=list&fmt=json">JSON API</a>
    </p>
</div>

</div><!-- /sb-page -->

<?php require_once __DIR__ . '/includes/footer.php'; ?>
