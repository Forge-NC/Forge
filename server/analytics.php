<?php
/**
 * Forge Fleet Analytics Dashboard
 *
 * Self-contained PHP page that renders server-side HTML with Chart.js.
 * Reads JSON data products created by analyzer.php and displays them
 * as an interactive dark-themed dashboard.
 *
 * Query params:
 *   ?key=TOKEN           — browser auth
 *   ?mine=ID1,ID2        — scoped view for specific machines
 *   ?compare=MACHINE_ID  — compare one machine against fleet averages
 */

require_once __DIR__ . '/auth.php';
$auth = require_auth();

header('Content-Type: text/html; charset=UTF-8');

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

$DATA_DIR = __DIR__ . '/data';

function load_json(string $path) {
    if (!file_exists($path)) return null;
    $raw = file_get_contents($path);
    if ($raw === false) return null;
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
}

$fleet = load_json($DATA_DIR . '/fleet_analytics.json') ?? [];
$capability = load_json($DATA_DIR . '/capability_matrix.json') ?? [];

// Load all machine profiles
$profiles = [];
$profile_glob = glob($DATA_DIR . '/profiles/*.json');
if (is_array($profile_glob)) {
    foreach ($profile_glob as $pf) {
        $data = load_json($pf);
        if ($data && isset($data['machine_id'])) {
            $profiles[$data['machine_id']] = $data;
        }
    }
}

// ---------------------------------------------------------------------------
// View mode detection
// ---------------------------------------------------------------------------

$view_mode = 'fleet'; // default
$mine_ids = [];
$compare_id = null;

if (isset($_GET['mine']) && $_GET['mine'] !== '') {
    $view_mode = 'mine';
    $mine_ids = array_map('trim', explode(',', $_GET['mine']));
    // Sanitize: hex only, 8-16 chars
    $mine_ids = array_filter($mine_ids, function ($id) {
        return preg_match('/^[a-f0-9]{8,16}$/i', $id);
    });
} elseif (isset($_GET['compare']) && $_GET['compare'] !== '') {
    $view_mode = 'compare';
    $compare_id = preg_replace('/[^a-f0-9]/i', '', $_GET['compare']);
    if (strlen($compare_id) < 8) $compare_id = null;
}

// Privacy: token-scoped users can only see their own machines + fleet averages
$is_token_user = ($auth['method'] === 'token');

// ---------------------------------------------------------------------------
// Helper: safe values from nested arrays
// ---------------------------------------------------------------------------

function fleet_val(array $fleet, string $key, $default = 0) {
    return $fleet[$key] ?? $default;
}

function fmt_pct(float $val): string {
    return number_format($val, 1) . '%';
}

function fmt_num(int $val): string {
    if ($val >= 1000000) return number_format($val / 1000000, 1) . 'M';
    if ($val >= 1000) return number_format($val / 1000, 1) . 'K';
    return (string)$val;
}

function time_ago(string $iso): string {
    $ts = strtotime($iso);
    if (!$ts) return 'unknown';
    $diff = time() - $ts;
    if ($diff < 60) return $diff . 's ago';
    if ($diff < 3600) return floor($diff / 60) . 'm ago';
    if ($diff < 86400) return floor($diff / 3600) . 'h ago';
    return floor($diff / 86400) . 'd ago';
}

function cell_color(float $pct): string {
    if ($pct >= 95) return '#3fb950';
    if ($pct >= 80) return '#d29922';
    return '#f85149';
}

// ---------------------------------------------------------------------------
// Prepare chart data
// ---------------------------------------------------------------------------

// GPU distribution (from capability matrix or profiles)
$gpu_distribution = [];
foreach ($profiles as $p) {
    $gpu = $p['gpu_model'] ?? $p['gpu'] ?? 'Unknown';
    $tier = $p['gpu_tier'] ?? 'unknown';
    $gpu_distribution[$gpu] = ($gpu_distribution[$gpu] ?? 0) + 1;
}

// Scenario health (from fleet analytics)
$scenario_health = $fleet['scenario_health'] ?? $fleet['scenarios'] ?? [];

// Failure trend (weekly)
$failure_trend = $fleet['failure_trend'] ?? $fleet['weekly_failures'] ?? [];

// Hardware leaderboard (from capability matrix)
$leaderboard = $capability['leaderboard'] ?? $capability['gpu_tiers'] ?? [];

// Heatmap: scenarios x gpu_tiers
$heatmap = $capability['heatmap'] ?? $fleet['heatmap'] ?? [];

// GPU tiers for heatmap columns
$gpu_tiers = $capability['gpu_tiers'] ?? [];
$tier_names = [];
if (is_array($gpu_tiers)) {
    foreach ($gpu_tiers as $tier) {
        $name = is_array($tier) ? ($tier['tier'] ?? $tier['name'] ?? 'unknown') : $tier;
        if (!in_array($name, $tier_names)) $tier_names[] = $name;
    }
}
// Fallback: extract from heatmap keys
if (empty($tier_names) && !empty($heatmap)) {
    foreach ($heatmap as $scenario => $tiers) {
        foreach (array_keys($tiers) as $t) {
            if (!in_array($t, $tier_names)) $tier_names[] = $t;
        }
    }
}

// Fleet summary stats
$active_machines = fleet_val($fleet, 'active_machines', count($profiles));
$total_sessions = fleet_val($fleet, 'total_sessions', 0);
$total_test_runs = fleet_val($fleet, 'total_test_runs', 0);
$fleet_pass_rate = fleet_val($fleet, 'fleet_pass_rate', 0.0);

// For compare mode: get fleet averages
$fleet_avg = $fleet['averages'] ?? [
    'tok_s' => fleet_val($fleet, 'avg_tok_s', 0),
    'reliability' => fleet_val($fleet, 'avg_reliability', 0),
    'pass_rate' => $fleet_pass_rate,
    'sessions' => $total_sessions > 0 && $active_machines > 0
        ? round($total_sessions / $active_machines) : 0,
];

// Build auth key param for links
$key_param = '';
if (isset($_GET['key'])) {
    $key_param = '?key=' . urlencode($_GET['key']);
}

// ---------------------------------------------------------------------------
// Filtered profiles for scoped views
// ---------------------------------------------------------------------------

$filtered_profiles = [];
if ($view_mode === 'mine') {
    foreach ($mine_ids as $mid) {
        // Match prefix or full id
        foreach ($profiles as $id => $p) {
            if (stripos($id, $mid) === 0 || $id === $mid) {
                $filtered_profiles[$id] = $p;
            }
        }
    }
} elseif ($view_mode === 'compare' && $compare_id) {
    foreach ($profiles as $id => $p) {
        if (stripos($id, $compare_id) === 0 || $id === $compare_id) {
            $filtered_profiles[$id] = $p;
            break;
        }
    }
}

// ---------------------------------------------------------------------------
// JSON-encode data for inline JS (privacy-safe)
// ---------------------------------------------------------------------------

// For token users in fleet mode, anonymize individual machine data
$js_profiles = $profiles;
if ($is_token_user && $view_mode === 'fleet') {
    $js_profiles = []; // Don't expose individual machines to token users
}

$js_gpu_distribution = $gpu_distribution;
$js_scenario_health = $scenario_health;
$js_failure_trend = $failure_trend;

?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge Fleet Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
        background: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        line-height: 1.5;
        padding: 24px;
        min-height: 100vh;
    }

    h1 {
        font-size: 1.75rem;
        font-weight: 600;
        color: #58a6ff;
        margin-bottom: 8px;
    }

    h2 {
        font-size: 1.25rem;
        font-weight: 600;
        color: #c9d1d9;
        margin-bottom: 16px;
    }

    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid #30363d;
    }

    .header-meta {
        font-size: 0.85rem;
        color: #8b949e;
    }

    .nav-links {
        display: flex;
        gap: 12px;
        margin-bottom: 24px;
    }

    .nav-links a {
        color: #58a6ff;
        text-decoration: none;
        font-size: 0.85rem;
        padding: 4px 12px;
        border: 1px solid #30363d;
        border-radius: 6px;
        transition: border-color 0.2s;
    }

    .nav-links a:hover { border-color: #58a6ff; }
    .nav-links a.active { background: #58a6ff; color: #0d1117; border-color: #58a6ff; }

    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 16px;
        margin-bottom: 32px;
    }

    .grid-wide {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
        gap: 16px;
        margin-bottom: 32px;
    }

    .card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 20px;
    }

    .card-full {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 32px;
    }

    .stat-card {
        text-align: center;
    }

    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        color: #58a6ff;
        display: block;
        margin: 8px 0 4px;
    }

    .stat-label {
        font-size: 0.85rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .chart-container {
        position: relative;
        width: 100%;
        max-height: 350px;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
    }

    th {
        text-align: left;
        padding: 10px 12px;
        border-bottom: 2px solid #30363d;
        color: #8b949e;
        font-weight: 600;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    td {
        padding: 8px 12px;
        border-bottom: 1px solid #21262d;
    }

    tr:hover td { background: rgba(88, 166, 255, 0.04); }

    .heatmap-cell {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
        text-align: center;
        min-width: 60px;
        color: #0d1117;
    }

    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    .badge-green { background: rgba(63, 185, 80, 0.2); color: #3fb950; }
    .badge-yellow { background: rgba(210, 153, 34, 0.2); color: #d29922; }
    .badge-red { background: rgba(248, 81, 73, 0.2); color: #f85149; }

    .compare-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-bottom: 32px;
    }

    .compare-label {
        font-size: 0.8rem;
        color: #8b949e;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

    .compare-value {
        font-size: 1.5rem;
        font-weight: 700;
    }

    .compare-bar {
        height: 6px;
        border-radius: 3px;
        background: #21262d;
        margin-top: 8px;
        overflow: hidden;
    }

    .compare-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
    }

    .empty-state {
        text-align: center;
        padding: 48px 24px;
        color: #8b949e;
    }

    .empty-state p { margin-top: 8px; font-size: 0.9rem; }

    .mono { font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }

    @media (max-width: 768px) {
        body { padding: 12px; }
        .grid { grid-template-columns: 1fr; }
        .grid-wide { grid-template-columns: 1fr; }
        .compare-grid { grid-template-columns: 1fr; }
        h1 { font-size: 1.35rem; }
    }
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>Forge Fleet Analytics</h1>
        <span class="header-meta">
            <?php if ($view_mode === 'mine'): ?>
                Viewing <?= count($filtered_profiles) ?> machine(s) &mdash; scoped view
            <?php elseif ($view_mode === 'compare'): ?>
                Comparing machine against fleet averages
            <?php else: ?>
                Fleet-wide overview &mdash; <?= $active_machines ?> active machine(s)
            <?php endif; ?>
            &bull; <?= date('Y-m-d H:i T') ?>
        </span>
    </div>
    <div class="nav-links">
        <a href="analytics.php<?= $key_param ?>"
           class="<?= $view_mode === 'fleet' ? 'active' : '' ?>">Fleet</a>
    </div>
</div>

<?php // ================================================================== ?>
<?php // MINE VIEW — Token-scoped side-by-side comparison                   ?>
<?php // ================================================================== ?>
<?php if ($view_mode === 'mine'): ?>

<?php if (empty($filtered_profiles)): ?>
    <div class="card-full empty-state">
        <h2>No Machines Found</h2>
        <p>None of the requested machine IDs matched any profiles.</p>
    </div>
<?php else: ?>

    <h2>My Machines</h2>
    <div class="grid">
    <?php foreach ($filtered_profiles as $mid => $mp): ?>
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <span class="mono" style="font-size:0.9rem;color:#58a6ff">
                    <?= htmlspecialchars(substr($mid, 0, 8)) ?>
                </span>
                <?php
                    $rel = $mp['reliability'] ?? $mp['reliability_score'] ?? 0;
                    $bc = $rel >= 90 ? 'badge-green' : ($rel >= 70 ? 'badge-yellow' : 'badge-red');
                ?>
                <span class="badge <?= $bc ?>"><?= fmt_pct($rel) ?></span>
            </div>
            <table>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">Label</td>
                    <td style="border:none;padding:4px 0"><?= htmlspecialchars($mp['label'] ?? 'unlabeled') ?></td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">GPU</td>
                    <td style="border:none;padding:4px 0"><?= htmlspecialchars($mp['gpu_model'] ?? $mp['gpu'] ?? 'N/A') ?></td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">VRAM</td>
                    <td style="border:none;padding:4px 0"><?= htmlspecialchars($mp['vram'] ?? $mp['vram_gb'] ?? 'N/A') ?> GB</td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">Sessions</td>
                    <td style="border:none;padding:4px 0"><?= (int)($mp['sessions'] ?? $mp['session_count'] ?? 0) ?></td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">Avg tok/s</td>
                    <td style="border:none;padding:4px 0"><?= number_format($mp['avg_tok_s'] ?? $mp['tok_s'] ?? 0, 1) ?></td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">Last Seen</td>
                    <td style="border:none;padding:4px 0"><?= htmlspecialchars($mp['last_seen'] ?? 'N/A') ?></td></tr>
                <tr><td style="color:#8b949e;border:none;padding:4px 0">Pass Rate</td>
                    <td style="border:none;padding:4px 0"><?= fmt_pct($mp['pass_rate'] ?? 0) ?></td></tr>
            </table>
            <div style="margin-top:12px">
                <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>compare=<?= urlencode($mid) ?>"
                   style="color:#58a6ff;font-size:0.85rem;text-decoration:none">
                    Compare vs fleet &rarr;
                </a>
            </div>
        </div>
    <?php endforeach; ?>
    </div>

    <h2>Fleet Averages (anonymized)</h2>
    <div class="grid">
        <div class="card stat-card">
            <span class="stat-label">Avg Pass Rate</span>
            <span class="stat-value"><?= fmt_pct($fleet_avg['pass_rate'] ?? $fleet_pass_rate) ?></span>
        </div>
        <div class="card stat-card">
            <span class="stat-label">Avg tok/s</span>
            <span class="stat-value"><?= number_format($fleet_avg['tok_s'] ?? 0, 1) ?></span>
        </div>
        <div class="card stat-card">
            <span class="stat-label">Avg Sessions</span>
            <span class="stat-value"><?= (int)($fleet_avg['sessions'] ?? 0) ?></span>
        </div>
        <div class="card stat-card">
            <span class="stat-label">Avg Reliability</span>
            <span class="stat-value"><?= fmt_pct($fleet_avg['reliability'] ?? 0) ?></span>
        </div>
    </div>

<?php endif; ?>

<?php // ================================================================== ?>
<?php // COMPARE VIEW — One machine vs fleet averages                       ?>
<?php // ================================================================== ?>
<?php elseif ($view_mode === 'compare'): ?>

<?php
    $cm = !empty($filtered_profiles) ? reset($filtered_profiles) : null;
    $cm_id = $cm ? key($filtered_profiles) : null;
?>

<?php if (!$cm): ?>
    <div class="card-full empty-state">
        <h2>Machine Not Found</h2>
        <p>No profile matches the requested machine ID.</p>
    </div>
<?php else: ?>

    <h2>
        <span class="mono" style="color:#58a6ff"><?= htmlspecialchars(substr($cm_id, 0, 8)) ?></span>
        &mdash; <?= htmlspecialchars($cm['label'] ?? 'unlabeled') ?>
        vs Fleet Average
    </h2>

    <?php
        $metrics = [
            ['label' => 'Pass Rate', 'key' => 'pass_rate', 'fleet_key' => 'pass_rate', 'unit' => '%', 'max' => 100],
            ['label' => 'Reliability', 'key' => 'reliability', 'fleet_key' => 'reliability', 'unit' => '%', 'max' => 100],
            ['label' => 'Avg tok/s', 'key' => 'avg_tok_s', 'fleet_key' => 'tok_s', 'unit' => '', 'max' => 200],
            ['label' => 'Sessions', 'key' => 'sessions', 'fleet_key' => 'sessions', 'unit' => '', 'max' => null],
        ];
    ?>

    <div class="grid">
    <?php foreach ($metrics as $m):
        $mine_val = $cm[$m['key']] ?? $cm[str_replace('avg_', '', $m['key'])] ?? 0;
        $fleet_v = $fleet_avg[$m['fleet_key']] ?? 0;
        $max = $m['max'] ?? max($mine_val, $fleet_v, 1);
        $mine_pct_bar = min(100, ($mine_val / $max) * 100);
        $fleet_pct_bar = min(100, ($fleet_v / $max) * 100);
        $diff = $mine_val - $fleet_v;
        $diff_color = $diff >= 0 ? '#3fb950' : '#f85149';
    ?>
        <div class="card">
            <div class="compare-label"><?= $m['label'] ?></div>
            <div style="display:flex;justify-content:space-between;align-items:baseline">
                <span class="compare-value" style="color:#58a6ff">
                    <?= number_format($mine_val, 1) ?><?= $m['unit'] ?>
                </span>
                <span style="color:<?= $diff_color ?>;font-size:0.85rem;font-weight:600">
                    <?= $diff >= 0 ? '+' : '' ?><?= number_format($diff, 1) ?>
                </span>
            </div>
            <div class="compare-bar">
                <div class="compare-fill" style="width:<?= $mine_pct_bar ?>%;background:#58a6ff"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:0.8rem;color:#8b949e">
                <span>Fleet avg: <?= number_format($fleet_v, 1) ?><?= $m['unit'] ?></span>
            </div>
            <div class="compare-bar">
                <div class="compare-fill" style="width:<?= $fleet_pct_bar ?>%;background:#30363d"></div>
            </div>
        </div>
    <?php endforeach; ?>
    </div>

    <h2>Machine Details</h2>
    <div class="card-full">
        <table>
            <tr><td style="color:#8b949e;width:180px">Machine ID</td>
                <td class="mono"><?= htmlspecialchars(substr($cm_id, 0, 8)) ?></td></tr>
            <tr><td style="color:#8b949e">Label</td>
                <td><?= htmlspecialchars($cm['label'] ?? 'unlabeled') ?></td></tr>
            <tr><td style="color:#8b949e">GPU</td>
                <td><?= htmlspecialchars($cm['gpu_model'] ?? $cm['gpu'] ?? 'N/A') ?></td></tr>
            <tr><td style="color:#8b949e">GPU Tier</td>
                <td><?= htmlspecialchars($cm['gpu_tier'] ?? 'N/A') ?></td></tr>
            <tr><td style="color:#8b949e">VRAM</td>
                <td><?= htmlspecialchars($cm['vram'] ?? $cm['vram_gb'] ?? 'N/A') ?> GB</td></tr>
            <tr><td style="color:#8b949e">Last Seen</td>
                <td><?= htmlspecialchars($cm['last_seen'] ?? 'N/A') ?></td></tr>
            <tr><td style="color:#8b949e">Total Sessions</td>
                <td><?= (int)($cm['sessions'] ?? $cm['session_count'] ?? 0) ?></td></tr>
            <tr><td style="color:#8b949e">Total Test Runs</td>
                <td><?= (int)($cm['test_runs'] ?? 0) ?></td></tr>
        </table>
    </div>

<?php endif; ?>

<?php // ================================================================== ?>
<?php // FLEET VIEW — Full dashboard                                         ?>
<?php // ================================================================== ?>
<?php else: ?>

<?php // ---- Section A: Fleet Overview Stat Cards ---- ?>
<h2>Fleet Overview</h2>
<div class="grid">
    <div class="card stat-card">
        <span class="stat-label">Active Machines (7d)</span>
        <span class="stat-value"><?= fmt_num($active_machines) ?></span>
    </div>
    <div class="card stat-card">
        <span class="stat-label">Total Sessions</span>
        <span class="stat-value"><?= fmt_num($total_sessions) ?></span>
    </div>
    <div class="card stat-card">
        <span class="stat-label">Total Test Runs</span>
        <span class="stat-value"><?= fmt_num($total_test_runs) ?></span>
    </div>
    <div class="card stat-card">
        <span class="stat-label">Fleet Pass Rate</span>
        <span class="stat-value" style="color:<?= cell_color($fleet_pass_rate) ?>">
            <?= fmt_pct($fleet_pass_rate) ?>
        </span>
    </div>
</div>

<?php // ---- Section B & C: Charts (GPU Distribution + Scenario Health) ---- ?>
<div class="grid-wide">

    <?php // ---- Section B: Hardware Distribution (Doughnut) ---- ?>
    <div class="card">
        <h2>Hardware Distribution</h2>
        <div class="chart-container">
            <canvas id="gpuPieChart"></canvas>
        </div>
    </div>

    <?php // ---- Section C: Scenario Health (Horizontal Bar) ---- ?>
    <div class="card">
        <h2>Scenario Health</h2>
        <div class="chart-container">
            <canvas id="scenarioBarChart"></canvas>
        </div>
    </div>

</div>

<?php // ---- Section D: Failure Trend (Line) ---- ?>
<div class="card-full">
    <h2>Failure Trend (Weekly)</h2>
    <div class="chart-container" style="max-height:300px">
        <canvas id="failureTrendChart"></canvas>
    </div>
</div>

<?php // ---- Section E: Hardware Leaderboard ---- ?>
<div class="card-full">
    <h2>Hardware Leaderboard</h2>
    <?php if (empty($leaderboard)): ?>
        <div class="empty-state"><p>No hardware data available yet.</p></div>
    <?php else: ?>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>GPU Model</th>
                    <th>Machine Count</th>
                    <th>Avg tok/s</th>
                    <th>VRAM (GB)</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($leaderboard as $hw): ?>
                <tr>
                    <td><?= htmlspecialchars($hw['gpu_model'] ?? $hw['gpu'] ?? $hw['name'] ?? 'N/A') ?></td>
                    <td><?= (int)($hw['machine_count'] ?? $hw['count'] ?? 0) ?></td>
                    <td><?= number_format($hw['avg_tok_s'] ?? $hw['tok_s'] ?? 0, 1) ?></td>
                    <td><?= htmlspecialchars($hw['vram'] ?? $hw['vram_gb'] ?? 'N/A') ?></td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <?php endif; ?>
</div>

<?php // ---- Section F: Failure Heatmap ---- ?>
<div class="card-full">
    <h2>Failure Heatmap</h2>
    <?php if (empty($heatmap) || empty($tier_names)): ?>
        <div class="empty-state"><p>No heatmap data available yet.</p></div>
    <?php else: ?>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>Scenario</th>
                    <?php foreach ($tier_names as $tn): ?>
                        <th style="text-align:center"><?= htmlspecialchars($tn) ?></th>
                    <?php endforeach; ?>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($heatmap as $scenario => $tiers): ?>
                <tr>
                    <td class="mono" style="font-size:0.85rem"><?= htmlspecialchars($scenario) ?></td>
                    <?php foreach ($tier_names as $tn):
                        $val = $tiers[$tn] ?? null;
                    ?>
                        <td style="text-align:center">
                        <?php if ($val !== null): ?>
                            <span class="heatmap-cell" style="background:<?= cell_color((float)$val) ?>">
                                <?= fmt_pct((float)$val) ?>
                            </span>
                        <?php else: ?>
                            <span style="color:#484f58">&mdash;</span>
                        <?php endif; ?>
                        </td>
                    <?php endforeach; ?>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <?php endif; ?>
</div>

<?php // ---- Section G: Machine List ---- ?>
<?php if (!$is_token_user): // Only show full machine list to admin/legacy auth ?>
<div class="card-full">
    <h2>Machine List</h2>
    <?php if (empty($profiles)): ?>
        <div class="empty-state"><p>No machine profiles available yet.</p></div>
    <?php else: ?>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>Machine ID</th>
                    <th>Label</th>
                    <th>Last Seen</th>
                    <th>GPU</th>
                    <th>Sessions</th>
                    <th>Reliability</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($profiles as $mid => $mp):
                $rel = $mp['reliability'] ?? $mp['reliability_score'] ?? 0;
            ?>
                <tr>
                    <td>
                        <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>compare=<?= urlencode($mid) ?>"
                           class="mono" style="color:#58a6ff;text-decoration:none;font-size:0.85rem">
                            <?= htmlspecialchars(substr($mid, 0, 8)) ?>
                        </a>
                    </td>
                    <td><?= htmlspecialchars($mp['label'] ?? 'unlabeled') ?></td>
                    <td><?php
                        $ls = $mp['last_seen'] ?? null;
                        echo $ls ? htmlspecialchars(time_ago($ls)) : '<span style="color:#484f58">N/A</span>';
                    ?></td>
                    <td><?= htmlspecialchars($mp['gpu_model'] ?? $mp['gpu'] ?? 'N/A') ?></td>
                    <td><?= (int)($mp['sessions'] ?? $mp['session_count'] ?? 0) ?></td>
                    <td>
                        <?php
                            $bc = $rel >= 90 ? 'badge-green' : ($rel >= 70 ? 'badge-yellow' : 'badge-red');
                        ?>
                        <span class="badge <?= $bc ?>"><?= fmt_pct($rel) ?></span>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <?php endif; ?>
</div>
<?php endif; ?>

<?php endif; // end fleet view ?>

<?php // ================================================================== ?>
<?php // Chart.js initialization (only for fleet view)                       ?>
<?php // ================================================================== ?>
<?php if ($view_mode === 'fleet'): ?>
<script>
(function() {
    // --- Injected data ---
    var gpuDist = <?= json_encode($js_gpu_distribution, JSON_UNESCAPED_UNICODE) ?>;
    var scenarioHealth = <?= json_encode($js_scenario_health, JSON_UNESCAPED_UNICODE) ?>;
    var failureTrend = <?= json_encode($js_failure_trend, JSON_UNESCAPED_UNICODE) ?>;

    // --- Chart defaults ---
    Chart.defaults.color = '#c9d1d9';
    Chart.defaults.borderColor = '#30363d';
    Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";

    var palette = [
        '#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff',
        '#f78166', '#79c0ff', '#7ee787', '#e3b341', '#ff7b72',
        '#d2a8ff', '#ffa657'
    ];

    // --- GPU Distribution Doughnut ---
    var gpuLabels = Object.keys(gpuDist);
    var gpuValues = Object.values(gpuDist);

    if (gpuLabels.length > 0) {
        new Chart(document.getElementById('gpuPieChart'), {
            type: 'doughnut',
            data: {
                labels: gpuLabels,
                datasets: [{
                    data: gpuValues,
                    backgroundColor: palette.slice(0, gpuLabels.length),
                    borderColor: '#161b22',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { padding: 16, usePointStyle: true, pointStyle: 'circle' }
                    }
                },
                cutout: '55%'
            }
        });
    }

    // --- Scenario Health Horizontal Bar ---
    var scenarioLabels = [];
    var scenarioValues = [];

    if (Array.isArray(scenarioHealth)) {
        // Array of objects: [{name: "...", pass_rate: N}, ...]
        scenarioHealth.forEach(function(s) {
            scenarioLabels.push(s.name || s.scenario || 'unknown');
            scenarioValues.push(s.pass_rate != null ? s.pass_rate : (s.rate || 0));
        });
    } else if (typeof scenarioHealth === 'object' && scenarioHealth !== null) {
        // Object: {scenario_name: pass_rate, ...}
        for (var k in scenarioHealth) {
            if (scenarioHealth.hasOwnProperty(k)) {
                scenarioLabels.push(k);
                var v = scenarioHealth[k];
                scenarioValues.push(typeof v === 'object' ? (v.pass_rate || v.rate || 0) : v);
            }
        }
    }

    if (scenarioLabels.length > 0) {
        var barColors = scenarioValues.map(function(v) {
            if (v >= 95) return '#3fb950';
            if (v >= 80) return '#d29922';
            return '#f85149';
        });

        new Chart(document.getElementById('scenarioBarChart'), {
            type: 'bar',
            data: {
                labels: scenarioLabels,
                datasets: [{
                    label: 'Pass Rate %',
                    data: scenarioValues,
                    backgroundColor: barColors,
                    borderColor: barColors,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        min: 0, max: 100,
                        grid: { color: '#21262d' },
                        ticks: { callback: function(v) { return v + '%'; } }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { font: { family: "'Cascadia Code', 'Consolas', monospace", size: 11 } }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) { return ctx.parsed.x.toFixed(1) + '%'; }
                        }
                    }
                }
            }
        });
    }

    // --- Failure Trend Line ---
    var trendLabels = [];
    var trendValues = [];

    if (Array.isArray(failureTrend)) {
        failureTrend.forEach(function(entry) {
            trendLabels.push(entry.week || entry.date || entry.label || '');
            trendValues.push(entry.failures != null ? entry.failures : (entry.count || entry.value || 0));
        });
    } else if (typeof failureTrend === 'object' && failureTrend !== null) {
        for (var wk in failureTrend) {
            if (failureTrend.hasOwnProperty(wk)) {
                trendLabels.push(wk);
                var fv = failureTrend[wk];
                trendValues.push(typeof fv === 'object' ? (fv.failures || fv.count || 0) : fv);
            }
        }
    }

    if (trendLabels.length > 0) {
        new Chart(document.getElementById('failureTrendChart'), {
            type: 'line',
            data: {
                labels: trendLabels,
                datasets: [{
                    label: 'Failures',
                    data: trendValues,
                    borderColor: '#f85149',
                    backgroundColor: 'rgba(248, 81, 73, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#f85149',
                    pointBorderColor: '#161b22',
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: '#21262d' } },
                    y: {
                        beginAtZero: true,
                        grid: { color: '#21262d' },
                        ticks: { precision: 0 }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
})();
</script>
<?php endif; ?>

</body>
</html>
