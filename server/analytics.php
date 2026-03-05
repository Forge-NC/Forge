<?php
/**
 * Forge Fleet Analytics Dashboard
 *
 * Enterprise-grade fleet telemetry & master management console.
 * Self-contained PHP page with Chart.js visualizations.
 * Reads JSON data products created by analyzer.php.
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

// Role-based view detection
$auth_role = $auth['role'] ?? 'tester';
$is_owner = ($auth_role === 'owner');
$is_master = ($auth_role === 'captain' || $auth_role === 'master');

if (isset($_GET['view']) && $_GET['view'] === 'fleet') {
    $view_mode = 'fleet';
} elseif (isset($_GET['view']) && $_GET['view'] === 'fleet_admin' && $is_owner) {
    $view_mode = 'fleet_admin';
} elseif (isset($_GET['view']) && $_GET['view'] === 'my_fleet' && ($is_master || $is_owner)) {
    $view_mode = 'my_fleet';
} elseif (isset($_GET['mine']) && $_GET['mine'] !== '') {
    $view_mode = 'mine';
    $mine_ids = array_map('trim', explode(',', $_GET['mine']));
    $mine_ids = array_filter($mine_ids, function ($id) {
        return preg_match('/^[a-f0-9]{8,16}$/i', $id);
    });
} elseif (isset($_GET['compare']) && $_GET['compare'] !== '') {
    $view_mode = 'compare';
    $compare_id = preg_replace('/[^a-f0-9]/i', '', $_GET['compare']);
    if (strlen($compare_id) < 8) $compare_id = null;
} elseif ($is_owner) {
    $view_mode = 'fleet_admin';
} elseif ($is_master) {
    $view_mode = 'my_fleet';
}

// Privacy: token-scoped users can only see their own machines + fleet averages
$is_token_user = ($auth['method'] === 'token');

// Load master/passport data for fleet admin views
$masters_data = [];
$puppet_registry = [];
$revocations = [];
$tiers_config = [];

if ($is_owner || $is_master) {
    $MASTERS_DIR = __DIR__ . '/data/masters';
    $PUPPET_REG = __DIR__ . '/data/puppet_registry.json';
    $REVOC_FILE = __DIR__ . '/data/revocations.json';
    $TIERS_FILE = __DIR__ . '/data/tiers_config.json';

    $tiers_config = load_json($TIERS_FILE) ?? [];
    $revocations = load_json($REVOC_FILE) ?? [];
    $puppet_registry = load_json($PUPPET_REG) ?? [];

    if ($is_owner && is_dir($MASTERS_DIR)) {
        foreach (glob("$MASTERS_DIR/*.json") as $cf) {
            $cd = load_json($cf);
            if ($cd) $masters_data[] = $cd;
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
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

function tier_color(string $tier): string {
    $colors = ['community' => '#3fb950', 'pro' => '#58a6ff', 'power' => '#bc8cff'];
    return $colors[$tier] ?? '#8b949e';
}

// ---------------------------------------------------------------------------
// Prepare chart data
// ---------------------------------------------------------------------------

$gpu_distribution = [];
$vram_distribution = [];
$os_distribution = [];
foreach ($profiles as $p) {
    $gpu = $p['gpu_model'] ?? $p['gpu'] ?? 'Unknown';
    $gpu_distribution[$gpu] = ($gpu_distribution[$gpu] ?? 0) + 1;

    $vram = ($p['vram'] ?? $p['vram_gb'] ?? 0);
    if ($vram > 0) {
        $vram_label = $vram . ' GB';
        $vram_distribution[$vram_label] = ($vram_distribution[$vram_label] ?? 0) + 1;
    }

    $os = $p['os'] ?? $p['platform'] ?? 'Unknown';
    if (stripos($os, 'win') !== false) $os = 'Windows';
    elseif (stripos($os, 'linux') !== false || stripos($os, 'ubuntu') !== false) $os = 'Linux';
    elseif (stripos($os, 'mac') !== false || stripos($os, 'darwin') !== false) $os = 'macOS';
    $os_distribution[$os] = ($os_distribution[$os] ?? 0) + 1;
}
arsort($gpu_distribution);
arsort($vram_distribution);

$scenario_health = $fleet['scenario_health'] ?? $fleet['scenarios'] ?? [];
$failure_trend = $fleet['failure_trend'] ?? $fleet['weekly_failures'] ?? [];
$leaderboard = $capability['leaderboard'] ?? $capability['gpu_tiers'] ?? [];
$heatmap = $capability['heatmap'] ?? $fleet['heatmap'] ?? [];

$gpu_tiers = $capability['gpu_tiers'] ?? [];
$tier_names = [];
if (is_array($gpu_tiers)) {
    foreach ($gpu_tiers as $tier) {
        $name = is_array($tier) ? ($tier['tier'] ?? $tier['name'] ?? 'unknown') : $tier;
        if (!in_array($name, $tier_names)) $tier_names[] = $name;
    }
}
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

// Performance percentiles
$all_tok_s = [];
$all_reliability = [];
$all_sessions_list = [];
foreach ($profiles as $p) {
    $ts = $p['avg_tok_s'] ?? $p['tok_s'] ?? 0;
    if ($ts > 0) $all_tok_s[] = $ts;
    $rel = $p['reliability'] ?? $p['reliability_score'] ?? 0;
    if ($rel > 0) $all_reliability[] = $rel;
    $sess = (int)($p['sessions'] ?? $p['session_count'] ?? 0);
    $all_sessions_list[] = $sess;
}
sort($all_tok_s);
sort($all_reliability);

$avg_tok_s = count($all_tok_s) > 0 ? array_sum($all_tok_s) / count($all_tok_s) : 0;
$median_tok_s = 0;
if (count($all_tok_s) > 0) {
    $mid = floor(count($all_tok_s) / 2);
    $median_tok_s = count($all_tok_s) % 2 === 0
        ? ($all_tok_s[$mid - 1] + $all_tok_s[$mid]) / 2
        : $all_tok_s[$mid];
}
$p95_tok_s = count($all_tok_s) >= 2 ? $all_tok_s[(int)(count($all_tok_s) * 0.95)] ?? end($all_tok_s) : $avg_tok_s;
$avg_reliability = count($all_reliability) > 0 ? array_sum($all_reliability) / count($all_reliability) : 0;
$total_sessions_all = array_sum($all_sessions_list);

// Fleet averages for compare mode
$fleet_avg = $fleet['averages'] ?? [
    'tok_s' => fleet_val($fleet, 'avg_tok_s', $avg_tok_s),
    'reliability' => fleet_val($fleet, 'avg_reliability', $avg_reliability),
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
// JSON-encode for JS (privacy-safe)
// ---------------------------------------------------------------------------

$js_profiles = $profiles;
if ($is_token_user && $view_mode === 'fleet') {
    $js_profiles = [];
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge Fleet Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
    :root {
        --bg-primary: #0a0e17;
        --bg-secondary: #111827;
        --bg-card: #161b22;
        --bg-card-hover: #1c2333;
        --border-primary: #30363d;
        --border-accent: rgba(88, 166, 255, 0.2);
        --text-primary: #f0f6fc;
        --text-secondary: #d1d9e0;
        --text-muted: #a8b3c0;
        --text-faint: #6e7a88;
        --accent-blue: #58a6ff;
        --accent-green: #3fb950;
        --accent-yellow: #d29922;
        --accent-red: #f85149;
        --accent-purple: #bc8cff;
        --accent-orange: #f78166;
        --gradient-blue: linear-gradient(135deg, rgba(88,166,255,0.1), rgba(188,140,255,0.05));
        --gradient-green: linear-gradient(135deg, rgba(63,185,80,0.1), rgba(88,166,255,0.05));
        --gradient-purple: linear-gradient(135deg, rgba(188,140,255,0.1), rgba(88,166,255,0.05));
        --shadow-card: 0 2px 8px rgba(0,0,0,0.3);
        --shadow-glow: 0 0 20px rgba(88,166,255,0.08);
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
        background: var(--bg-primary);
        color: var(--text-secondary);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        line-height: 1.6;
        padding: 24px;
        min-height: 100vh;
    }

    h1 {
        font-size: 1.75rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.02em;
    }

    h1 span {
        background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    h2 {
        font-size: 1.15rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 6px;
    }

    .section-desc {
        font-size: 0.82rem;
        color: var(--text-secondary);
        margin-bottom: 16px;
        line-height: 1.4;
        opacity: 0.85;
    }

    /* ---- Header ---- */
    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 28px;
        padding-bottom: 20px;
        border-bottom: 1px solid var(--border-primary);
    }

    .header-meta {
        font-size: 0.82rem;
        color: var(--text-muted);
        margin-top: 4px;
    }

    .header-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-right: 6px;
    }

    /* ---- Navigation ---- */
    .nav-links {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }

    .nav-links a {
        color: var(--text-muted);
        text-decoration: none;
        font-size: 0.82rem;
        font-weight: 500;
        padding: 6px 16px;
        border: 1px solid var(--border-primary);
        border-radius: 8px;
        transition: all 0.2s ease;
        background: var(--bg-secondary);
    }

    .nav-links a:hover {
        border-color: var(--accent-blue);
        color: var(--accent-blue);
        background: rgba(88,166,255,0.05);
    }

    .nav-links a.active {
        background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
        color: #fff;
        border-color: transparent;
        box-shadow: 0 2px 12px rgba(88,166,255,0.3);
    }

    /* ---- Grid Layouts ---- */
    .grid-4 {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 28px;
    }

    .grid-3 {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 28px;
    }

    .grid-2 {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
        margin-bottom: 28px;
    }

    .grid-auto {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 16px;
        margin-bottom: 28px;
    }

    /* ---- Cards ---- */
    .card {
        background: var(--bg-card);
        border: 1px solid var(--border-primary);
        border-radius: 10px;
        padding: 20px;
        box-shadow: var(--shadow-card);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .card:hover {
        border-color: var(--border-accent);
        box-shadow: var(--shadow-glow);
    }

    .card-full {
        background: var(--bg-card);
        border: 1px solid var(--border-primary);
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 28px;
        box-shadow: var(--shadow-card);
    }

    /* ---- Stat Cards ---- */
    .stat-card {
        text-align: center;
        padding: 20px 16px;
        position: relative;
        overflow: hidden;
    }

    .stat-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
        opacity: 0.6;
    }

    .stat-card .stat-icon {
        font-size: 1.5rem;
        margin-bottom: 4px;
        display: block;
        opacity: 0.7;
    }

    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        color: var(--accent-blue);
        display: block;
        margin: 6px 0 4px;
        letter-spacing: -0.02em;
    }

    .stat-label {
        font-size: 0.78rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
    }

    .stat-hint {
        display: block;
        font-size: 0.7rem;
        color: var(--text-muted);
        margin-top: 4px;
        line-height: 1.3;
    }

    .stat-sub {
        font-size: 0.82rem;
        margin-top: 4px;
    }

    /* ---- Charts ---- */
    .chart-wrap {
        position: relative;
        width: 100%;
    }

    .chart-sm { max-height: 200px; }
    .chart-md { max-height: 280px; }
    .chart-lg { max-height: 350px; }

    /* ---- Tables ---- */
    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }

    th {
        text-align: left;
        padding: 10px 12px;
        border-bottom: 2px solid var(--border-primary);
        color: var(--text-muted);
        font-weight: 600;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        white-space: nowrap;
    }

    td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(48,54,61,0.5);
        color: var(--text-primary);
    }

    tr:hover td {
        background: rgba(88, 166, 255, 0.03);
    }

    /* ---- Search/Filter ---- */
    .table-search {
        width: 100%;
        max-width: 320px;
        padding: 8px 14px;
        margin-bottom: 14px;
        background: var(--bg-primary);
        border: 1px solid var(--border-primary);
        border-radius: 8px;
        color: var(--text-secondary);
        font-size: 0.85rem;
        outline: none;
        transition: border-color 0.2s;
    }

    .table-search:focus {
        border-color: var(--accent-blue);
    }

    .table-search::placeholder {
        color: var(--text-faint);
    }

    /* ---- Badges ---- */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }

    .badge-green { background: rgba(63,185,80,0.15); color: var(--accent-green); }
    .badge-yellow { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }
    .badge-red { background: rgba(248,81,73,0.15); color: var(--accent-red); }
    .badge-blue { background: rgba(88,166,255,0.15); color: var(--accent-blue); }
    .badge-purple { background: rgba(188,140,255,0.15); color: var(--accent-purple); }

    /* ---- Heatmap ---- */
    .heatmap-cell {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
        text-align: center;
        min-width: 64px;
        color: var(--bg-primary);
    }

    /* ---- Compare Bars ---- */
    .compare-row {
        padding: 16px 0;
        border-bottom: 1px solid rgba(48,54,61,0.3);
    }

    .compare-row:last-child { border-bottom: none; }

    .compare-label {
        font-size: 0.78rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        margin-bottom: 6px;
    }

    .compare-value {
        font-size: 1.4rem;
        font-weight: 700;
    }

    .compare-bar {
        height: 8px;
        border-radius: 4px;
        background: rgba(48,54,61,0.5);
        margin-top: 6px;
        overflow: hidden;
    }

    .compare-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.6s ease;
    }

    /* ---- Progress Ring (tier utilization) ---- */
    .tier-ring {
        position: relative;
        width: 80px;
        height: 80px;
        margin: 0 auto 8px;
    }

    .tier-ring svg {
        transform: rotate(-90deg);
        width: 80px;
        height: 80px;
    }

    .tier-ring .ring-bg {
        fill: none;
        stroke: var(--border-primary);
        stroke-width: 6;
    }

    .tier-ring .ring-fill {
        fill: none;
        stroke-width: 6;
        stroke-linecap: round;
        transition: stroke-dashoffset 0.8s ease;
    }

    .tier-ring .ring-text {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-size: 0.9rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    /* ---- Empty State ---- */
    .empty-state {
        text-align: center;
        padding: 40px 24px;
        color: var(--text-muted);
    }

    .empty-state p { margin-top: 8px; font-size: 0.85rem; }

    /* ---- Utility ---- */
    .mono { font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
    .text-green { color: var(--accent-green); }
    .text-red { color: var(--accent-red); }
    .text-yellow { color: var(--accent-yellow); }
    .text-blue { color: var(--accent-blue); }
    .text-purple { color: var(--accent-purple); }
    .text-muted { color: var(--text-muted); }

    .flex-between {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .mb-0 { margin-bottom: 0; }
    .mb-8 { margin-bottom: 8px; }
    .mb-16 { margin-bottom: 16px; }
    .mb-24 { margin-bottom: 24px; }
    .mt-8 { margin-top: 8px; }
    .mt-16 { margin-top: 16px; }

    /* ---- Divider ---- */
    .section-divider {
        border: none;
        border-top: 1px solid var(--border-primary);
        margin: 32px 0;
    }

    /* ---- Responsive ---- */
    @media (max-width: 1024px) {
        .grid-4 { grid-template-columns: repeat(2, 1fr); }
        .grid-3 { grid-template-columns: repeat(2, 1fr); }
    }

    @media (max-width: 768px) {
        body { padding: 14px; }
        .grid-4 { grid-template-columns: 1fr; }
        .grid-3 { grid-template-columns: 1fr; }
        .grid-2 { grid-template-columns: 1fr; }
        .header { flex-direction: column; gap: 12px; align-items: flex-start; }
        h1 { font-size: 1.35rem; }
        .stat-value { font-size: 1.6rem; }
        .nav-links { width: 100%; }
    }
</style>
</head>
<body>

<!-- ================================================================== -->
<!-- Header & Navigation                                                 -->
<!-- ================================================================== -->
<div class="header">
    <div>
        <h1><span>Forge</span> Fleet Analytics</h1>
        <div class="header-meta">
            <?php if ($view_mode === 'fleet_admin'): ?>
                <span class="header-badge" style="background:rgba(188,140,255,0.15);color:var(--accent-purple)">Owner</span>
                Fleet Administration &mdash; Master &amp; revenue management
            <?php elseif ($view_mode === 'my_fleet'): ?>
                <span class="header-badge" style="background:rgba(88,166,255,0.15);color:var(--accent-blue)">Master</span>
                Fleet seat &amp; puppet management
            <?php elseif ($view_mode === 'mine'): ?>
                <span class="header-badge" style="background:rgba(63,185,80,0.15);color:var(--accent-green)">Scoped</span>
                Viewing <?= count($filtered_profiles) ?> machine(s)
            <?php elseif ($view_mode === 'compare'): ?>
                <span class="header-badge" style="background:rgba(210,153,34,0.15);color:var(--accent-yellow)">Compare</span>
                Machine vs fleet benchmarks
            <?php else: ?>
                <span class="header-badge" style="background:rgba(88,166,255,0.15);color:var(--accent-blue)">Telemetry</span>
                <?= $active_machines ?> machine(s) reporting
            <?php endif; ?>
            &bull; <?= date('Y-m-d H:i T') ?>
        </div>
    </div>
    <div class="nav-links">
        <?php if ($is_owner): ?>
        <a href="admin.php<?= $key_param ?>" style="border-color:var(--accent-purple)">Admin Panel</a>
        <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>view=fleet_admin"
           class="<?= $view_mode === 'fleet_admin' ? 'active' : '' ?>">Fleet Admin</a>
        <?php endif; ?>
        <?php if ($is_master || $is_owner): ?>
        <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>view=my_fleet"
           class="<?= $view_mode === 'my_fleet' ? 'active' : '' ?>">My Fleet</a>
        <?php endif; ?>
        <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>view=fleet"
           class="<?= $view_mode === 'fleet' ? 'active' : '' ?>">Telemetry</a>
        <a href="/Forge/" style="border-color:var(--text-faint)">Main Site</a>
    </div>
</div>


<?php // ================================================================== ?>
<?php // FLEET ADMIN VIEW                                                   ?>
<?php // ================================================================== ?>
<?php if ($view_mode === 'fleet_admin'): ?>

<?php
    $total_masters = count($masters_data);
    $active_masters = 0;
    $total_seats_sold = 0;
    $total_puppets = 0;
    $total_revenue = 0;
    $revenue_by_tier = [];
    $masters_by_tier = [];
    $recent_activations = 0;
    $revoked_count = 0;

    foreach ($masters_data as $cd) {
        $pp = $cd['passport'] ?? [];
        $acct = $pp['account_id'] ?? '';
        $pp_id = $pp['passport_id'] ?? '';
        $is_revoked = isset($revocations[$pp_id]);

        if ($is_revoked) { $revoked_count++; }
        if ($cd['activated'] && !$is_revoked) $active_masters++;

        $seats = $pp['seat_count'] ?? 1;
        $total_seats_sold += $seats;

        $puppets = $puppet_registry[$acct] ?? [];
        $active_puppet_count = count(array_filter($puppets,
            function($p) { return ($p['status'] ?? '') === 'active'; }));
        $total_puppets += $active_puppet_count;

        $tier = $pp['tier'] ?? 'community';
        $tc = $tiers_config[$tier] ?? [];
        $tier_rev = ($tc['price_cents'] ?? 0) / 100;
        $total_revenue += $tier_rev;
        $revenue_by_tier[$tier] = ($revenue_by_tier[$tier] ?? 0) + $tier_rev;
        $masters_by_tier[$tier] = ($masters_by_tier[$tier] ?? 0) + 1;

        // Count activations in last 7 days
        if ($cd['activated_at']) {
            $act_ts = strtotime($cd['activated_at']);
            if ($act_ts && (time() - $act_ts) < 604800) $recent_activations++;
        }
    }

    $avg_seats = $total_masters > 0 ? round($total_seats_sold / $total_masters, 1) : 0;
    $seat_utilization = $total_seats_sold > 0 ? round(($total_puppets / max(1, $total_seats_sold - $total_masters)) * 100, 1) : 0;
    $churn_rate = $total_masters > 0 ? round(($revoked_count / $total_masters) * 100, 1) : 0;
    $arpu = $active_masters > 0 ? round($total_revenue / $active_masters, 2) : 0;
?>

<h2>Revenue Overview</h2>
<p class="section-desc">Aggregate revenue, seat utilization, and master lifecycle metrics across paid tiers.</p>

<div class="grid-4">
    <div class="card stat-card" title="Monthly recurring revenue from all active masters">
        <span class="stat-label">Monthly Revenue</span>
        <span class="stat-value text-green">$<?= number_format($total_revenue, 0) ?></span>
        <span class="stat-hint">Total MRR across all tiers</span>
    </div>
    <div class="card stat-card" title="Average revenue per active master">
        <span class="stat-label">ARPU</span>
        <span class="stat-value">$<?= number_format($arpu, 2) ?></span>
        <span class="stat-hint">Revenue per active master</span>
    </div>
    <div class="card stat-card" title="Masters who activated in the last 7 days">
        <span class="stat-label">New (7d)</span>
        <span class="stat-value"><?= $recent_activations ?></span>
        <span class="stat-hint">Activations this week</span>
    </div>
    <div class="card stat-card" title="Percentage of masters whose passports have been revoked">
        <span class="stat-label">Churn Rate</span>
        <span class="stat-value" style="color:<?= $churn_rate > 10 ? 'var(--accent-red)' : ($churn_rate > 5 ? 'var(--accent-yellow)' : 'var(--accent-green)') ?>">
            <?= $churn_rate ?>%
        </span>
        <span class="stat-hint"><?= $revoked_count ?> revoked / <?= $total_masters ?> total</span>
    </div>
</div>

<div class="grid-4">
    <div class="card stat-card" title="Total registered masters (paid passport holders)">
        <span class="stat-label">Total Masters</span>
        <span class="stat-value"><?= $total_masters ?></span>
        <span class="stat-sub text-green"><?= $active_masters ?> active</span>
        <span class="stat-hint">Pro &amp; Power passport holders</span>
    </div>
    <div class="card stat-card" title="Total seat licenses sold across all masters">
        <span class="stat-label">Seats Sold</span>
        <span class="stat-value"><?= $total_seats_sold ?></span>
        <span class="stat-sub text-muted"><?= $avg_seats ?> avg per master</span>
        <span class="stat-hint">Includes master's own seat</span>
    </div>
    <div class="card stat-card" title="Puppet machines actively registered under master accounts">
        <span class="stat-label">Active Puppets</span>
        <span class="stat-value"><?= $total_puppets ?></span>
        <span class="stat-hint">Machines linked to master seats</span>
    </div>
    <div class="card stat-card" title="Percentage of puppet seat slots that have active puppets registered">
        <span class="stat-label">Seat Utilization</span>
        <span class="stat-value" style="color:<?= $seat_utilization >= 80 ? 'var(--accent-green)' : ($seat_utilization >= 50 ? 'var(--accent-yellow)' : 'var(--accent-red)') ?>">
            <?= $seat_utilization ?>%
        </span>
        <span class="stat-hint">Puppet slots filled</span>
    </div>
</div>

<hr class="section-divider">

<!-- Tier Breakdown + Revenue Chart -->
<div class="grid-2">
    <div>
        <h2>Tier Distribution</h2>
        <p class="section-desc">Master count and revenue contribution by paid tier.</p>
        <div class="grid-auto mb-0">
        <?php foreach (['pro', 'power'] as $t):
            $tc = tier_color($t);
            $count = $masters_by_tier[$t] ?? 0;
            $rev = $revenue_by_tier[$t] ?? 0;
            $pct = $total_masters > 0 ? round(($count / $total_masters) * 100) : 0;
        ?>
            <div class="card" style="border-left:3px solid <?= $tc ?>">
                <div class="flex-between mb-8">
                    <span style="color:<?= $tc ?>;font-weight:700;text-transform:uppercase;font-size:0.85rem"><?= ucfirst($t) ?></span>
                    <span class="badge" style="background:<?= $tc ?>20;color:<?= $tc ?>"><?= $pct ?>%</span>
                </div>
                <div style="font-size:1.5rem;font-weight:700;color:var(--text-primary)"><?= $count ?></div>
                <div class="text-muted" style="font-size:0.82rem">masters &bull; $<?= number_format($rev, 0) ?>/mo</div>
            </div>
        <?php endforeach; ?>
        </div>
    </div>

    <?php if (!empty($revenue_by_tier)): ?>
    <div>
        <h2>Revenue by Tier</h2>
        <p class="section-desc">Monthly revenue distribution across subscription tiers.</p>
        <div class="card">
            <div class="chart-wrap chart-sm">
                <canvas id="revChart"></canvas>
            </div>
        </div>
    </div>
    <?php endif; ?>
</div>

<hr class="section-divider">

<!-- Master Directory -->
<h2>Master Directory</h2>
<p class="section-desc">All registered passport holders with status, seat usage, and last activity. Click "View" to inspect a master's puppet fleet.</p>

<?php if (empty($masters_data)): ?>
    <div class="card-full empty-state">
        <p>No masters registered yet. Passports are generated via Stripe checkout or the admin panel.</p>
    </div>
<?php else: ?>
<div class="card-full">
    <input type="text" class="table-search" placeholder="Search masters..." onkeyup="filterTable(this, 'master-table')">
    <div style="overflow-x:auto">
    <table id="master-table">
        <thead>
            <tr>
                <th>Label</th>
                <th>Tier</th>
                <th>Seats</th>
                <th>Puppets</th>
                <th>Status</th>
                <th>Activated</th>
                <th>Last Seen</th>
                <th>Account</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
        <?php foreach ($masters_data as $cd):
            $pp = $cd['passport'] ?? [];
            $acct = $pp['account_id'] ?? '';
            $pp_id = $pp['passport_id'] ?? '';
            $is_revoked = isset($revocations[$pp_id]);
            $puppets = $puppet_registry[$acct] ?? [];
            $active_pups = count(array_filter($puppets,
                function($p) { return ($p['status'] ?? '') === 'active'; }));
            $seats = $pp['seat_count'] ?? 1;
            $tier = $pp['tier'] ?? 'community';
            $tc = tier_color($tier);
        ?>
            <tr style="<?= $is_revoked ? 'opacity:0.45;' : '' ?>">
                <td style="font-weight:500"><?= htmlspecialchars($pp['customer_label'] ?? '(unlabeled)') ?></td>
                <td><span style="color:<?= $tc ?>;font-weight:600"><?= ucfirst($tier) ?></span></td>
                <td><?= $active_pups ?>/<?= max(0, $seats - 1) ?></td>
                <td><?= count($puppets) ?></td>
                <td>
                    <?php if ($is_revoked): ?>
                        <span class="badge badge-red">Revoked</span>
                    <?php elseif ($cd['activated']): ?>
                        <span class="badge badge-green">Active</span>
                    <?php else: ?>
                        <span class="badge badge-yellow">Pending</span>
                    <?php endif; ?>
                </td>
                <td><?= $cd['activated_at'] ? time_ago($cd['activated_at']) : '<span class="text-muted">--</span>' ?></td>
                <td><?= $cd['last_seen'] ? time_ago($cd['last_seen']) : '<span class="text-muted">--</span>' ?></td>
                <td class="mono" style="font-size:0.78rem;color:var(--text-muted)"><?= htmlspecialchars(substr($acct, 0, 12)) ?></td>
                <td>
                    <?php if (!$is_revoked): ?>
                    <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>view=my_fleet&account_id=<?= urlencode($acct) ?>"
                       style="color:var(--accent-blue);text-decoration:none;font-size:0.82rem;font-weight:500">View</a>
                    <?php else: ?>
                    <span class="text-muted">--</span>
                    <?php endif; ?>
                </td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</div>
<?php endif; ?>


<?php // ================================================================== ?>
<?php // MY FLEET VIEW                                                      ?>
<?php // ================================================================== ?>
<?php elseif ($view_mode === 'my_fleet'): ?>

<?php
    $fleet_account = null;
    if ($is_owner && isset($_GET['account_id'])) {
        $fleet_account = preg_replace('/[^a-zA-Z0-9_-]/', '', $_GET['account_id']);
    } elseif ($is_master && isset($auth['token_hash'])) {
        $tokens_data = load_json(__DIR__ . '/data/tokens.json') ?? [];
        $tok_entry = $tokens_data[$auth['token_hash']] ?? [];
        $fleet_account = $tok_entry['account_id'] ?? null;
    }

    $master_info = null;
    $master_puppets = [];

    if ($fleet_account) {
        $cf = __DIR__ . "/data/masters/$fleet_account.json";
        $master_info = load_json($cf);
        $master_puppets = $puppet_registry[$fleet_account] ?? [];
    }
?>

<?php if (!$master_info): ?>
    <div class="card-full empty-state">
        <h2>Master Not Found</h2>
        <p>Could not locate master account. Ensure your token is linked to a valid passport.</p>
    </div>
<?php else: ?>
<?php
    $mst_pp = $master_info['passport'] ?? [];
    $mst_tier = $mst_pp['tier'] ?? 'community';
    $mst_seats = $mst_pp['seat_count'] ?? 1;
    $puppet_limit = max(0, $mst_seats - 1);
    $active_pups = count(array_filter($master_puppets,
        function($p) { return ($p['status'] ?? '') === 'active'; }));
    $seat_pct = $puppet_limit > 0 ? round(($active_pups / $puppet_limit) * 100) : 0;
    $revoked_pups = count(array_filter($master_puppets,
        function($p) { return ($p['status'] ?? '') === 'revoked'; }));
    $circumference = 2 * 3.14159 * 32;
    $dash_offset = $circumference - ($circumference * min($seat_pct, 100) / 100);
    $ring_color = tier_color($mst_tier);
?>

<h2>Master Dashboard</h2>
<p class="section-desc">Your fleet overview — seat utilization, puppet status, and account details.</p>

<div class="grid-4">
    <div class="card stat-card" title="Your subscription tier">
        <span class="stat-label">Tier</span>
        <span class="stat-value" style="color:<?= tier_color($mst_tier) ?>"><?= ucfirst($mst_tier) ?></span>
        <span class="stat-hint">Subscription level</span>
    </div>
    <div class="card stat-card" title="How many of your available puppet seats are in use">
        <span class="stat-label">Seat Utilization</span>
        <div class="tier-ring">
            <svg viewBox="0 0 72 72">
                <circle class="ring-bg" cx="36" cy="36" r="32"/>
                <circle class="ring-fill" cx="36" cy="36" r="32"
                    stroke="<?= $ring_color ?>"
                    stroke-dasharray="<?= $circumference ?>"
                    stroke-dashoffset="<?= $dash_offset ?>"/>
            </svg>
            <span class="ring-text"><?= $seat_pct ?>%</span>
        </div>
        <span class="stat-hint"><?= $active_pups ?> of <?= $puppet_limit ?> puppet slots used</span>
    </div>
    <div class="card stat-card" title="Active puppets vs total registered puppets">
        <span class="stat-label">Active Puppets</span>
        <span class="stat-value"><?= $active_pups ?></span>
        <span class="stat-sub text-muted"><?= count($master_puppets) ?> total registered</span>
        <span class="stat-hint">Machines linked to your master seats</span>
    </div>
    <div class="card stat-card" title="Puppets whose access has been revoked">
        <span class="stat-label">Revoked</span>
        <span class="stat-value" style="color:<?= $revoked_pups > 0 ? 'var(--accent-red)' : 'var(--accent-green)' ?>"><?= $revoked_pups ?></span>
        <span class="stat-hint">Deactivated puppet seats</span>
    </div>
</div>

<!-- Account Info -->
<div class="card-full">
    <h2 class="mb-8">Account Details</h2>
    <div style="display:grid;grid-template-columns:120px 1fr;gap:8px 16px;font-size:0.85rem;max-width:500px">
        <span class="text-muted">Label</span>
        <span style="font-weight:500"><?= htmlspecialchars($mst_pp['customer_label'] ?? '') ?></span>
        <span class="text-muted">Account ID</span>
        <span class="mono" style="font-size:0.82rem"><?= htmlspecialchars(substr($fleet_account, 0, 24)) ?></span>
        <span class="text-muted">Passport</span>
        <span class="mono" style="font-size:0.82rem"><?= htmlspecialchars(substr($mst_pp['passport_id'] ?? '', 0, 16)) ?></span>
        <span class="text-muted">Activated</span>
        <span><?= $master_info['activated_at'] ? time_ago($master_info['activated_at']) : '--' ?></span>
        <span class="text-muted">Last Seen</span>
        <span><?= $master_info['last_seen'] ? time_ago($master_info['last_seen']) : '--' ?></span>
    </div>
</div>

<hr class="section-divider">

<!-- Puppet Table -->
<h2>Puppet Directory</h2>
<p class="section-desc">All machines registered as puppets under your master passport. Active puppets consume one seat each.</p>

<?php if (empty($master_puppets)): ?>
    <div class="card-full empty-state">
        <p>No puppets registered. Generate puppet passports in Forge with <code>/puppet generate &lt;name&gt;</code> from your master seat.</p>
    </div>
<?php else: ?>
<div class="card-full">
    <input type="text" class="table-search" placeholder="Search puppets..." onkeyup="filterTable(this, 'puppet-table')">
    <div style="overflow-x:auto">
    <table id="puppet-table">
        <thead>
            <tr>
                <th>Name</th>
                <th>Machine ID</th>
                <th>Seat</th>
                <th>Status</th>
                <th>Registered</th>
                <th>Last Seen</th>
            </tr>
        </thead>
        <tbody>
        <?php foreach ($master_puppets as $pup): ?>
            <tr>
                <td style="font-weight:500"><?= htmlspecialchars($pup['puppet_name'] ?? '') ?></td>
                <td class="mono" style="font-size:0.82rem"><?= htmlspecialchars($pup['puppet_mid'] ?? '') ?></td>
                <td class="mono" style="font-size:0.82rem"><?= htmlspecialchars($pup['seat_id'] ?? '') ?></td>
                <td>
                    <?php
                        $ps = $pup['status'] ?? 'unknown';
                        $pb = $ps === 'active' ? 'badge-green' : ($ps === 'revoked' ? 'badge-red' : 'badge-yellow');
                    ?>
                    <span class="badge <?= $pb ?>"><?= ucfirst($ps) ?></span>
                </td>
                <td><?= isset($pup['registered_at']) ? time_ago($pup['registered_at']) : '--' ?></td>
                <td><?= isset($pup['last_seen']) ? time_ago($pup['last_seen']) : '--' ?></td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</div>
<?php endif; ?>

<?php endif; ?>


<?php // ================================================================== ?>
<?php // MINE VIEW                                                          ?>
<?php // ================================================================== ?>
<?php elseif ($view_mode === 'mine'): ?>

<?php if (empty($filtered_profiles)): ?>
    <div class="card-full empty-state">
        <h2>No Machines Found</h2>
        <p>None of the requested machine IDs matched any profiles in the fleet.</p>
    </div>
<?php else: ?>

    <h2>My Machines</h2>
    <p class="section-desc">Detailed performance and health metrics for your registered machines. Click "Compare" to benchmark against the fleet.</p>

    <div class="grid-auto">
    <?php foreach ($filtered_profiles as $mid => $mp): ?>
        <div class="card" style="position:relative;overflow:hidden">
            <?php
                $rel = $mp['reliability'] ?? $mp['reliability_score'] ?? 0;
                $rel_color = $rel >= 90 ? 'var(--accent-green)' : ($rel >= 70 ? 'var(--accent-yellow)' : 'var(--accent-red)');
            ?>
            <div style="position:absolute;top:0;left:0;right:0;height:3px;background:<?= $rel_color ?>"></div>
            <div class="flex-between mb-16" style="margin-top:4px">
                <span class="mono" style="font-size:0.9rem;color:var(--accent-blue);font-weight:600">
                    <?= htmlspecialchars(substr($mid, 0, 8)) ?>
                </span>
                <span class="badge <?= $rel >= 90 ? 'badge-green' : ($rel >= 70 ? 'badge-yellow' : 'badge-red') ?>">
                    <?= fmt_pct($rel) ?> reliability
                </span>
            </div>
            <div style="display:grid;grid-template-columns:100px 1fr;gap:6px 12px;font-size:0.85rem">
                <span class="text-muted">Label</span>
                <span style="font-weight:500"><?= htmlspecialchars($mp['label'] ?? 'unlabeled') ?></span>
                <span class="text-muted">GPU</span>
                <span><?= htmlspecialchars($mp['gpu_model'] ?? $mp['gpu'] ?? 'N/A') ?></span>
                <span class="text-muted">VRAM</span>
                <span><?= htmlspecialchars($mp['vram'] ?? $mp['vram_gb'] ?? 'N/A') ?> GB</span>
                <span class="text-muted">Sessions</span>
                <span><?= (int)($mp['sessions'] ?? $mp['session_count'] ?? 0) ?></span>
                <span class="text-muted">Avg tok/s</span>
                <span style="font-weight:600;color:var(--accent-blue)"><?= number_format($mp['avg_tok_s'] ?? $mp['tok_s'] ?? 0, 1) ?></span>
                <span class="text-muted">Pass Rate</span>
                <span><?= fmt_pct($mp['pass_rate'] ?? 0) ?></span>
                <span class="text-muted">Last Seen</span>
                <span><?= isset($mp['last_seen']) ? time_ago($mp['last_seen']) : 'N/A' ?></span>
            </div>
            <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border-primary)">
                <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>compare=<?= urlencode($mid) ?>"
                   style="color:var(--accent-blue);font-size:0.82rem;text-decoration:none;font-weight:500">
                    Compare vs fleet &rarr;
                </a>
            </div>
        </div>
    <?php endforeach; ?>
    </div>

    <hr class="section-divider">

    <h2>Fleet Averages</h2>
    <p class="section-desc">Anonymized fleet-wide baselines for comparison. Individual machine data is not exposed.</p>
    <div class="grid-4">
        <div class="card stat-card" title="Average test pass rate across all machines in the fleet">
            <span class="stat-label">Avg Pass Rate</span>
            <span class="stat-value"><?= fmt_pct($fleet_avg['pass_rate'] ?? $fleet_pass_rate) ?></span>
            <span class="stat-hint">Fleet-wide test success</span>
        </div>
        <div class="card stat-card" title="Average tokens per second across all machines">
            <span class="stat-label">Avg tok/s</span>
            <span class="stat-value"><?= number_format($fleet_avg['tok_s'] ?? 0, 1) ?></span>
            <span class="stat-hint">Fleet inference speed</span>
        </div>
        <div class="card stat-card" title="Average session count per machine">
            <span class="stat-label">Avg Sessions</span>
            <span class="stat-value"><?= (int)($fleet_avg['sessions'] ?? 0) ?></span>
            <span class="stat-hint">Per-machine average</span>
        </div>
        <div class="card stat-card" title="Average reliability score across fleet">
            <span class="stat-label">Avg Reliability</span>
            <span class="stat-value"><?= fmt_pct($fleet_avg['reliability'] ?? 0) ?></span>
            <span class="stat-hint">Fleet stability score</span>
        </div>
    </div>

<?php endif; ?>


<?php // ================================================================== ?>
<?php // COMPARE VIEW                                                       ?>
<?php // ================================================================== ?>
<?php elseif ($view_mode === 'compare'): ?>

<?php
    $cm = !empty($filtered_profiles) ? reset($filtered_profiles) : null;
    $cm_id = $cm ? key($filtered_profiles) : null;
    // Reset array pointer for proper key access
    reset($filtered_profiles);
    $cm_id = key($filtered_profiles);
?>

<?php if (!$cm): ?>
    <div class="card-full empty-state">
        <h2>Machine Not Found</h2>
        <p>No profile matches the requested machine ID.</p>
    </div>
<?php else: ?>

    <h2>
        <span class="mono text-blue"><?= htmlspecialchars(substr($cm_id, 0, 8)) ?></span>
        &mdash; <?= htmlspecialchars($cm['label'] ?? 'unlabeled') ?>
    </h2>
    <p class="section-desc">Side-by-side comparison of this machine's performance against fleet-wide averages. Green = above fleet avg, red = below.</p>

    <!-- Machine Info Card -->
    <div class="card-full">
        <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(180px, 1fr));gap:16px">
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">GPU</span>
                <span style="font-weight:500"><?= htmlspecialchars($cm['gpu_model'] ?? $cm['gpu'] ?? 'N/A') ?></span>
            </div>
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">GPU Tier</span>
                <span style="font-weight:500"><?= htmlspecialchars($cm['gpu_tier'] ?? 'N/A') ?></span>
            </div>
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">VRAM</span>
                <span style="font-weight:500"><?= htmlspecialchars($cm['vram'] ?? $cm['vram_gb'] ?? 'N/A') ?> GB</span>
            </div>
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">Sessions</span>
                <span style="font-weight:500"><?= (int)($cm['sessions'] ?? $cm['session_count'] ?? 0) ?></span>
            </div>
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">Test Runs</span>
                <span style="font-weight:500"><?= (int)($cm['test_runs'] ?? 0) ?></span>
            </div>
            <div>
                <span class="text-muted" style="font-size:0.78rem;display:block">Last Seen</span>
                <span style="font-weight:500"><?= isset($cm['last_seen']) ? time_ago($cm['last_seen']) : 'N/A' ?></span>
            </div>
        </div>
    </div>

    <!-- Comparison Metrics -->
    <?php
        $metrics = [
            ['label' => 'Pass Rate', 'desc' => 'Test suite success rate', 'key' => 'pass_rate', 'fleet_key' => 'pass_rate', 'unit' => '%', 'max' => 100, 'color' => 'var(--accent-green)'],
            ['label' => 'Reliability', 'desc' => 'Uptime & crash-free score', 'key' => 'reliability', 'fleet_key' => 'reliability', 'unit' => '%', 'max' => 100, 'color' => 'var(--accent-blue)'],
            ['label' => 'Avg tok/s', 'desc' => 'Inference speed (higher = better)', 'key' => 'avg_tok_s', 'fleet_key' => 'tok_s', 'unit' => '', 'max' => 200, 'color' => 'var(--accent-purple)'],
            ['label' => 'Sessions', 'desc' => 'Total usage sessions', 'key' => 'sessions', 'fleet_key' => 'sessions', 'unit' => '', 'max' => null, 'color' => 'var(--accent-orange)'],
        ];
    ?>

    <div class="grid-2">
    <?php foreach ($metrics as $m):
        $mine_val = $cm[$m['key']] ?? $cm[str_replace('avg_', '', $m['key'])] ?? 0;
        $fleet_v = $fleet_avg[$m['fleet_key']] ?? 0;
        $max = $m['max'] ?? max($mine_val, $fleet_v, 1);
        $mine_pct_bar = min(100, ($mine_val / $max) * 100);
        $fleet_pct_bar = min(100, ($fleet_v / $max) * 100);
        $diff = $mine_val - $fleet_v;
        $diff_color = $diff >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        $diff_prefix = $diff >= 0 ? '+' : '';
    ?>
        <div class="card">
            <div class="compare-label"><?= $m['label'] ?></div>
            <div class="section-desc mb-8" style="margin-bottom:8px"><?= $m['desc'] ?></div>
            <div class="flex-between mb-8">
                <span class="compare-value" style="color:<?= $m['color'] ?>">
                    <?= number_format($mine_val, 1) ?><?= $m['unit'] ?>
                </span>
                <span style="color:<?= $diff_color ?>;font-size:0.85rem;font-weight:700">
                    <?= $diff_prefix ?><?= number_format($diff, 1) ?><?= $m['unit'] ?>
                </span>
            </div>
            <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:3px">This machine</div>
            <div class="compare-bar">
                <div class="compare-fill" style="width:<?= $mine_pct_bar ?>%;background:<?= $m['color'] ?>"></div>
            </div>
            <div style="font-size:0.75rem;color:var(--text-muted);margin-top:8px;margin-bottom:3px">
                Fleet average: <?= number_format($fleet_v, 1) ?><?= $m['unit'] ?>
            </div>
            <div class="compare-bar">
                <div class="compare-fill" style="width:<?= $fleet_pct_bar ?>%;background:var(--text-faint)"></div>
            </div>
        </div>
    <?php endforeach; ?>
    </div>

    <!-- Radar Chart -->
    <div class="card-full">
        <h2>Performance Radar</h2>
        <p class="section-desc">Multi-dimensional comparison: your machine (blue) vs fleet average (gray). Larger area = better overall performance.</p>
        <div class="chart-wrap chart-md" style="max-width:450px;margin:0 auto">
            <canvas id="radarChart"></canvas>
        </div>
    </div>

    <?php
        // Prepare radar data
        $radar_mine = [];
        $radar_fleet = [];
        $radar_labels = [];
        foreach ($metrics as $m) {
            $radar_labels[] = $m['label'];
            $mine_val = $cm[$m['key']] ?? $cm[str_replace('avg_', '', $m['key'])] ?? 0;
            $fleet_v = $fleet_avg[$m['fleet_key']] ?? 0;
            $max = $m['max'] ?? max($mine_val, $fleet_v, 1);
            $radar_mine[] = round(min(100, ($mine_val / $max) * 100), 1);
            $radar_fleet[] = round(min(100, ($fleet_v / $max) * 100), 1);
        }
    ?>

<?php endif; ?>


<?php // ================================================================== ?>
<?php // FLEET TELEMETRY VIEW                                               ?>
<?php // ================================================================== ?>
<?php else: ?>

<!-- Fleet Overview Stats -->
<h2>Fleet Overview</h2>
<p class="section-desc">Real-time fleet health metrics. Active machines are those that reported in the last 7 days.</p>

<div class="grid-4">
    <div class="card stat-card" title="Machines that sent telemetry in the last 7 days">
        <span class="stat-label">Active Machines</span>
        <span class="stat-value"><?= fmt_num($active_machines) ?></span>
        <span class="stat-hint">Reported in last 7 days</span>
    </div>
    <div class="card stat-card" title="Total Forge sessions across all machines">
        <span class="stat-label">Total Sessions</span>
        <span class="stat-value"><?= fmt_num($total_sessions) ?></span>
        <span class="stat-hint">Cumulative usage sessions</span>
    </div>
    <div class="card stat-card" title="Total test suite executions across the fleet">
        <span class="stat-label">Test Runs</span>
        <span class="stat-value"><?= fmt_num($total_test_runs) ?></span>
        <span class="stat-hint">Automated test executions</span>
    </div>
    <div class="card stat-card" title="Percentage of tests that passed across the entire fleet">
        <span class="stat-label">Fleet Pass Rate</span>
        <span class="stat-value" style="color:<?= cell_color($fleet_pass_rate) ?>">
            <?= fmt_pct($fleet_pass_rate) ?>
        </span>
        <span class="stat-hint">Tests passing fleet-wide</span>
    </div>
</div>

<!-- Performance Percentiles -->
<h2>Performance Percentiles</h2>
<p class="section-desc">Token generation speed distribution across the fleet. Helps identify hardware bottlenecks and outliers.</p>

<div class="grid-4">
    <div class="card stat-card" title="Average tokens per second across all machines">
        <span class="stat-label">Mean tok/s</span>
        <span class="stat-value"><?= number_format($avg_tok_s, 1) ?></span>
        <span class="stat-hint">Fleet-wide average speed</span>
    </div>
    <div class="card stat-card" title="Median tokens per second — 50th percentile">
        <span class="stat-label">Median tok/s</span>
        <span class="stat-value"><?= number_format($median_tok_s, 1) ?></span>
        <span class="stat-hint">50th percentile (P50)</span>
    </div>
    <div class="card stat-card" title="95th percentile tokens per second — fastest 5% of machines">
        <span class="stat-label">P95 tok/s</span>
        <span class="stat-value text-green"><?= number_format($p95_tok_s, 1) ?></span>
        <span class="stat-hint">Top 5% machine speed</span>
    </div>
    <div class="card stat-card" title="Average reliability score across all machines">
        <span class="stat-label">Avg Reliability</span>
        <span class="stat-value" style="color:<?= cell_color($avg_reliability) ?>">
            <?= fmt_pct($avg_reliability) ?>
        </span>
        <span class="stat-hint">Fleet stability score</span>
    </div>
</div>

<hr class="section-divider">

<!-- Charts Row 1: GPU + VRAM Distribution -->
<div class="grid-2">
    <div class="card">
        <h2>GPU Distribution</h2>
        <p class="section-desc">Which GPU models are running Forge across the fleet.</p>
        <div class="chart-wrap chart-sm">
            <canvas id="gpuPieChart"></canvas>
        </div>
    </div>

    <div class="card">
        <h2>VRAM Distribution</h2>
        <p class="section-desc">Video memory capacity spread — determines which models each machine can run.</p>
        <div class="chart-wrap chart-sm">
            <canvas id="vramChart"></canvas>
        </div>
    </div>
</div>

<!-- Charts Row 2: Scenario Health + OS Distribution -->
<div class="grid-2">
    <div class="card">
        <h2>Scenario Health</h2>
        <p class="section-desc">Pass rate per test scenario. Green = healthy (95%+), yellow = degraded (80%+), red = failing.</p>
        <div class="chart-wrap chart-md">
            <canvas id="scenarioBarChart"></canvas>
        </div>
    </div>

    <div class="card">
        <h2>Platform Distribution</h2>
        <p class="section-desc">Operating system breakdown across fleet machines.</p>
        <div class="chart-wrap chart-sm">
            <canvas id="osChart"></canvas>
        </div>
    </div>
</div>

<!-- Failure Trend -->
<div class="card-full">
    <h2>Failure Trend</h2>
    <p class="section-desc">Weekly failure count over time. Spikes indicate regressions or infrastructure issues requiring investigation.</p>
    <div class="chart-wrap chart-md">
        <canvas id="failureTrendChart"></canvas>
    </div>
</div>

<hr class="section-divider">

<!-- Hardware Leaderboard -->
<h2>Hardware Leaderboard</h2>
<p class="section-desc">GPU performance rankings by average inference speed. Helps users choose optimal hardware for Forge.</p>

<div class="card-full">
    <?php if (empty($leaderboard)): ?>
        <div class="empty-state"><p>No hardware benchmark data available yet. Data populates as machines report telemetry.</p></div>
    <?php else: ?>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>GPU Model</th>
                    <th>Machines</th>
                    <th>Avg tok/s</th>
                    <th>VRAM</th>
                    <th>Tier</th>
                </tr>
            </thead>
            <tbody>
            <?php $rank = 1; foreach ($leaderboard as $hw): ?>
                <tr>
                    <td style="font-weight:700;color:<?= $rank <= 3 ? 'var(--accent-yellow)' : 'var(--text-muted)' ?>"><?= $rank ?></td>
                    <td style="font-weight:500"><?= htmlspecialchars($hw['gpu_model'] ?? $hw['gpu'] ?? $hw['name'] ?? 'N/A') ?></td>
                    <td><?= (int)($hw['machine_count'] ?? $hw['count'] ?? 0) ?></td>
                    <td>
                        <span style="font-weight:600;color:var(--accent-blue)">
                            <?= number_format($hw['avg_tok_s'] ?? $hw['tok_s'] ?? 0, 1) ?>
                        </span>
                    </td>
                    <td><?= htmlspecialchars($hw['vram'] ?? $hw['vram_gb'] ?? 'N/A') ?> GB</td>
                    <td>
                        <?php
                            $hw_tier = $hw['tier'] ?? $hw['gpu_tier'] ?? '';
                            $tier_badge = 'badge-blue';
                            if (stripos($hw_tier, 'high') !== false || stripos($hw_tier, 'A') !== false) $tier_badge = 'badge-green';
                            elseif (stripos($hw_tier, 'low') !== false || stripos($hw_tier, 'C') !== false) $tier_badge = 'badge-yellow';
                        ?>
                        <span class="badge <?= $tier_badge ?>"><?= htmlspecialchars($hw_tier ?: 'N/A') ?></span>
                    </td>
                </tr>
            <?php $rank++; endforeach; ?>
            </tbody>
        </table>
    </div>
    <?php endif; ?>
</div>

<!-- Failure Heatmap -->
<h2>Capability Heatmap</h2>
<p class="section-desc">Pass rate matrix: test scenarios (rows) vs GPU tiers (columns). Reveals which hardware struggles with which workloads.</p>

<div class="card-full">
    <?php if (empty($heatmap) || empty($tier_names)): ?>
        <div class="empty-state"><p>No heatmap data available yet. Requires multiple GPU tiers and test scenarios.</p></div>
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
                    <td class="mono" style="font-size:0.82rem;font-weight:500"><?= htmlspecialchars($scenario) ?></td>
                    <?php foreach ($tier_names as $tn):
                        $val = $tiers[$tn] ?? null;
                    ?>
                        <td style="text-align:center">
                        <?php if ($val !== null): ?>
                            <span class="heatmap-cell" style="background:<?= cell_color((float)$val) ?>">
                                <?= fmt_pct((float)$val) ?>
                            </span>
                        <?php else: ?>
                            <span class="text-muted">&mdash;</span>
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

<hr class="section-divider">

<!-- Machine List -->
<?php if (!$is_token_user): ?>
<h2>Machine Registry</h2>
<p class="section-desc">All machines reporting fleet telemetry. Click a machine ID to compare its performance against fleet averages.</p>

<div class="card-full">
    <?php if (empty($profiles)): ?>
        <div class="empty-state"><p>No machine profiles available yet. Machines register automatically when they send telemetry.</p></div>
    <?php else: ?>
    <input type="text" class="table-search" placeholder="Search by ID, label, or GPU..." onkeyup="filterTable(this, 'machine-table')">
    <div style="overflow-x:auto">
        <table id="machine-table">
            <thead>
                <tr>
                    <th>Machine ID</th>
                    <th>Label</th>
                    <th>GPU</th>
                    <th>VRAM</th>
                    <th>Sessions</th>
                    <th>Avg tok/s</th>
                    <th>Reliability</th>
                    <th>Last Seen</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($profiles as $mid => $mp):
                $rel = $mp['reliability'] ?? $mp['reliability_score'] ?? 0;
            ?>
                <tr>
                    <td>
                        <a href="analytics.php<?= $key_param ? $key_param . '&' : '?' ?>compare=<?= urlencode($mid) ?>"
                           class="mono" style="color:var(--accent-blue);text-decoration:none;font-size:0.82rem;font-weight:500">
                            <?= htmlspecialchars(substr($mid, 0, 8)) ?>
                        </a>
                    </td>
                    <td style="font-weight:500"><?= htmlspecialchars($mp['label'] ?? 'unlabeled') ?></td>
                    <td><?= htmlspecialchars($mp['gpu_model'] ?? $mp['gpu'] ?? 'N/A') ?></td>
                    <td><?= htmlspecialchars($mp['vram'] ?? $mp['vram_gb'] ?? 'N/A') ?> GB</td>
                    <td><?= (int)($mp['sessions'] ?? $mp['session_count'] ?? 0) ?></td>
                    <td style="font-weight:600;color:var(--accent-blue)"><?= number_format($mp['avg_tok_s'] ?? $mp['tok_s'] ?? 0, 1) ?></td>
                    <td>
                        <span class="badge <?= $rel >= 90 ? 'badge-green' : ($rel >= 70 ? 'badge-yellow' : 'badge-red') ?>">
                            <?= fmt_pct($rel) ?>
                        </span>
                    </td>
                    <td>
                        <?php
                            $ls = $mp['last_seen'] ?? null;
                            echo $ls ? htmlspecialchars(time_ago($ls)) : '<span class="text-muted">--</span>';
                        ?>
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


<!-- ================================================================== -->
<!-- JavaScript                                                          -->
<!-- ================================================================== -->

<script>
// --- Table search/filter ---
function filterTable(input, tableId) {
    var filter = input.value.toLowerCase();
    var table = document.getElementById(tableId);
    if (!table) return;
    var rows = table.querySelectorAll('tbody tr');
    for (var i = 0; i < rows.length; i++) {
        var text = rows[i].textContent.toLowerCase();
        rows[i].style.display = text.indexOf(filter) > -1 ? '' : 'none';
    }
}
</script>

<?php // --- Fleet Admin Charts --- ?>
<?php if ($view_mode === 'fleet_admin' && !empty($revenue_by_tier)): ?>
<script>
(function() {
    Chart.defaults.color = '#c9d1d9';
    Chart.defaults.borderColor = '#30363d';

    new Chart(document.getElementById('revChart'), {
        type: 'doughnut',
        data: {
            labels: <?= json_encode(array_map('ucfirst', array_keys($revenue_by_tier)), JSON_HEX_TAG) ?>,
            datasets: [{
                data: <?= json_encode(array_values($revenue_by_tier), JSON_HEX_TAG) ?>,
                backgroundColor: ['#3fb950', '#58a6ff', '#bc8cff', '#d29922'],
                borderColor: '#161b22',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '60%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { padding: 16, usePointStyle: true, pointStyle: 'circle', font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) { return ctx.label + ': $' + ctx.parsed.toLocaleString() + '/mo'; }
                    }
                }
            }
        }
    });
})();
</script>
<?php endif; ?>


<?php // --- Compare Radar Chart --- ?>
<?php if ($view_mode === 'compare' && $cm): ?>
<script>
(function() {
    Chart.defaults.color = '#c9d1d9';
    Chart.defaults.borderColor = '#30363d';

    var labels = <?= json_encode($radar_labels, JSON_HEX_TAG) ?>;
    var mine = <?= json_encode($radar_mine, JSON_HEX_TAG) ?>;
    var fleet = <?= json_encode($radar_fleet, JSON_HEX_TAG) ?>;

    new Chart(document.getElementById('radarChart'), {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'This Machine',
                    data: mine,
                    borderColor: '#58a6ff',
                    backgroundColor: 'rgba(88,166,255,0.15)',
                    borderWidth: 2,
                    pointBackgroundColor: '#58a6ff',
                    pointRadius: 4
                },
                {
                    label: 'Fleet Average',
                    data: fleet,
                    borderColor: '#484f58',
                    backgroundColor: 'rgba(72,79,88,0.1)',
                    borderWidth: 2,
                    pointBackgroundColor: '#484f58',
                    pointRadius: 3,
                    borderDash: [4, 4]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: '#21262d' },
                    angleLines: { color: '#21262d' },
                    pointLabels: { font: { size: 12, weight: '600' } },
                    ticks: { display: false }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { padding: 16, usePointStyle: true, pointStyle: 'circle' }
                }
            }
        }
    });
})();
</script>
<?php endif; ?>


<?php // --- Fleet Telemetry Charts --- ?>
<?php if ($view_mode === 'fleet'): ?>
<script>
(function() {
    Chart.defaults.color = '#c9d1d9';
    Chart.defaults.borderColor = '#30363d';
    Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";

    var palette = [
        '#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff',
        '#f78166', '#79c0ff', '#7ee787', '#e3b341', '#ff7b72',
        '#d2a8ff', '#ffa657'
    ];

    // --- GPU Distribution Doughnut ---
    var gpuDist = <?= json_encode($gpu_distribution, JSON_HEX_TAG) ?>;
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
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { padding: 12, usePointStyle: true, pointStyle: 'circle', font: { size: 11 } }
                    }
                }
            }
        });
    }

    // --- VRAM Distribution Bar ---
    var vramDist = <?= json_encode($vram_distribution, JSON_HEX_TAG) ?>;
    var vramLabels = Object.keys(vramDist);
    var vramValues = Object.values(vramDist);

    if (vramLabels.length > 0) {
        new Chart(document.getElementById('vramChart'), {
            type: 'bar',
            data: {
                labels: vramLabels,
                datasets: [{
                    label: 'Machines',
                    data: vramValues,
                    backgroundColor: '#bc8cff',
                    borderColor: '#bc8cff',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, grid: { color: '#21262d' }, ticks: { precision: 0 } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    // --- Scenario Health Horizontal Bar ---
    var scenarioHealth = <?= json_encode($scenario_health, JSON_HEX_TAG) ?>;
    var scenarioLabels = [];
    var scenarioValues = [];

    if (Array.isArray(scenarioHealth)) {
        scenarioHealth.forEach(function(s) {
            scenarioLabels.push(s.name || s.scenario || 'unknown');
            scenarioValues.push(s.pass_rate != null ? s.pass_rate : (s.rate || 0));
        });
    } else if (typeof scenarioHealth === 'object' && scenarioHealth !== null) {
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

    // --- OS Distribution Doughnut ---
    var osDist = <?= json_encode($os_distribution, JSON_HEX_TAG) ?>;
    var osLabels = Object.keys(osDist);
    var osValues = Object.values(osDist);

    if (osLabels.length > 0) {
        new Chart(document.getElementById('osChart'), {
            type: 'doughnut',
            data: {
                labels: osLabels,
                datasets: [{
                    data: osValues,
                    backgroundColor: ['#58a6ff', '#3fb950', '#d29922', '#f85149'],
                    borderColor: '#161b22',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { padding: 12, usePointStyle: true, pointStyle: 'circle', font: { size: 11 } }
                    }
                }
            }
        });
    }

    // --- Failure Trend Line ---
    var failureTrend = <?= json_encode($failure_trend, JSON_HEX_TAG) ?>;
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
                    backgroundColor: 'rgba(248, 81, 73, 0.08)',
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
