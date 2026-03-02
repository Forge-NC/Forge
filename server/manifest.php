<?php
/**
 * Forge Manifest Generator
 *
 * Returns per-machine test assignments calibrated to hardware capability.
 *
 * Endpoint: GET /Forge/manifest.php?machine_id=XXXX[&budget=60]
 *
 * Security: Server SUGGESTS, client DECIDES.
 *   - Manifest is data, not instructions
 *   - Client validates all values against local hardcoded caps
 *   - Client reduce-only rule prevents server from expanding scope
 *
 * Deploy to: dirt-star.com/Forge/manifest.php
 */

require_once __DIR__ . '/auth.php';

header('Content-Type: application/json');

// -- Auth --
$auth = require_auth();

// -- Validate request --
if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

$machine_id = preg_replace('/[^a-f0-9]/', '', strtolower($_GET['machine_id'] ?? ''));
if (strlen($machine_id) < 8 || strlen($machine_id) > 16) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid machine_id']);
    exit;
}

$budget_m = max(5, min(480, intval($_GET['budget'] ?? 60)));

// -- Data paths --
$DATA_DIR = __DIR__ . '/data';
$PROFILES_DIR = $DATA_DIR . '/profiles';
$FLEET_FILE = $DATA_DIR . '/fleet_analytics.json';
$CAPABILITY_FILE = $DATA_DIR . '/capability_matrix.json';

// -- Load data (graceful on missing) --
$profile = _load_json("$PROFILES_DIR/{$machine_id}.json");
$test_history = _load_json("$PROFILES_DIR/{$machine_id}_tests.json");
$fleet = _load_json($FLEET_FILE);
$capability = _load_json($CAPABILITY_FILE);

// -- Live-compatible scenarios (client hardcodes these too) --
$LIVE_SCENARIOS = [
    ['name' => 'endurance',       'test_file' => 'test_endurance.py',      'default_turns' => 50, 'default_ctx' => 4000, 'default_timeout' => 1800],
    ['name' => 'context_storm',   'test_file' => 'test_context_storm.py',  'default_turns' => 20, 'default_ctx' => 1200, 'default_timeout' => 600],
    ['name' => 'crash_recovery',  'test_file' => 'test_crash_recovery.py', 'default_turns' => 10, 'default_ctx' => 4000, 'default_timeout' => 600],
    ['name' => 'malicious_repo',  'test_file' => 'test_malicious_repo.py', 'default_turns' => 5,  'default_ctx' => 4000, 'default_timeout' => 300],
    ['name' => 'repair_loop',     'test_file' => 'test_repair_loop.py',    'default_turns' => 10, 'default_ctx' => 4000, 'default_timeout' => 300],
];

// -- Determine machine's VRAM tier --
$vram_mb = 0;
if ($profile) {
    $hw = $profile['hardware'] ?? [];
    $vram_mb = $hw['vram_total_mb'] ?? 0;
}
$tier = _vram_to_tier($vram_mb);

// -- Score each scenario --
$scored = [];
foreach ($LIVE_SCENARIOS as $s) {
    $name = $s['name'];
    $score = _score_scenario($name, $test_history, $fleet);

    // Calibrate from capability matrix
    $cap_data = _get_capability($capability, $tier, $name);
    $turns = $cap_data['max_safe_turns'] ?? $s['default_turns'];
    $ctx = $s['default_ctx'];
    $timeout = intval(($cap_data['avg_duration_s'] ?? $s['default_timeout'] * 0.6)
                      * ($cap_data['timeout_multiplier'] ?? 1.5) * 1.5);
    $timeout = max($timeout, 120); // minimum 2 min

    $scored[] = [
        'name' => $name,
        'test_file' => $s['test_file'],
        'turns' => $turns,
        'ctx_tokens' => $ctx,
        'timeout_s' => $timeout,
        'score' => $score,
        'priority' => 0,
        'reason' => _build_reason($name, $test_history, $fleet),
        'estimated_duration_s' => $cap_data['avg_duration_s'] ?? ($timeout * 0.4),
    ];
}

// Sort by score descending
usort($scored, function($a, $b) { return $b['score'] <=> $a['score']; });

// Assign priorities
foreach ($scored as $i => &$s) {
    $s['priority'] = $i + 1;
}
unset($s);

// -- Apply time budget --
$budget_s = $budget_m * 60;
$selected = [];
$estimated_total = 0;

foreach ($scored as $s) {
    $est = $s['estimated_duration_s'];
    if ($estimated_total + $est > $budget_s && count($selected) > 0) {
        break;
    }
    $estimated_total += $est;
    // Strip internal fields
    unset($s['score'], $s['estimated_duration_s']);
    $selected[] = $s;
}

// -- New machine fallback (no profile) --
if (!$profile && empty($selected)) {
    $selected = [
        ['name' => 'crash_recovery',  'test_file' => 'test_crash_recovery.py',
         'turns' => 5, 'ctx_tokens' => 4000, 'timeout_s' => 300, 'priority' => 1,
         'reason' => 'New machine — lightweight smoke test'],
        ['name' => 'malicious_repo',  'test_file' => 'test_malicious_repo.py',
         'turns' => 5, 'ctx_tokens' => 4000, 'timeout_s' => 300, 'priority' => 2,
         'reason' => 'New machine — lightweight smoke test'],
        ['name' => 'repair_loop',     'test_file' => 'test_repair_loop.py',
         'turns' => 5, 'ctx_tokens' => 4000, 'timeout_s' => 300, 'priority' => 3,
         'reason' => 'New machine — lightweight smoke test'],
    ];
    $estimated_total = 900;
}

// -- Fleet status --
$fleet_status = [
    'active_machines' => _count_active_machines($PROFILES_DIR, 7),
    'scenarios_needing_coverage' => _scenarios_needing_coverage($fleet),
    'fleet_pass_rate_7d' => $fleet['pass_rate_7d'] ?? 0,
];

// -- Response --
$response = [
    'schema_version' => 1,
    'machine_id' => $machine_id,
    'generated_at' => gmdate('Y-m-d\TH:i:s\Z'),
    'scenarios' => $selected,
    'estimated_duration_m' => round($estimated_total / 60, 1),
    'max_budget_m' => $budget_m,
    'model_recommendation' => 'qwen2.5-coder:14b',
    'fleet_status' => $fleet_status,
];

echo json_encode($response, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);


// ── Helper functions ──

function _load_json(string $path) {
    if (!file_exists($path)) return null;
    $data = json_decode(file_get_contents($path), true);
    return is_array($data) ? $data : null;
}

function _vram_to_tier(int $vram_mb): string {
    $vram_gb = $vram_mb / 1024;
    if ($vram_gb > 26) return 'tier_48gb';
    if ($vram_gb > 18) return 'tier_24gb';
    if ($vram_gb > 14) return 'tier_16gb';
    if ($vram_gb > 10) return 'tier_12gb';
    if ($vram_gb > 6)  return 'tier_8gb';
    return 'tier_4gb';
}

function _score_scenario(string $name, array $history = null, array $fleet = null): float {
    /*
     * Score(scenario, machine) =
     *   0.30 * recency    (days since last run / 7, capped at 1.0)
     *   0.35 * failure    (1.0 if failed last time, 0.5 if 2 runs ago)
     *   0.20 * fleet_need (1.0 - fleet_pass_rate)
     *   0.15 * coverage   (1.0 if never run, 0.5 if <3 times)
     */
    $recency = 1.0;
    $failure = 0.0;
    $coverage = 1.0;

    if ($history && is_array($history)) {
        $scenario_runs = array_filter($history, function($r) use ($name) {
            return ($r['scenario'] ?? '') === $name;
        });
        $scenario_runs = array_values($scenario_runs);

        if (count($scenario_runs) > 0) {
            // Recency
            $last = end($scenario_runs);
            $last_ts = strtotime($last['timestamp'] ?? '2000-01-01');
            $days_ago = (time() - $last_ts) / 86400;
            $recency = min(1.0, $days_ago / 7.0);

            // Failure
            if (!($last['invariant_pass'] ?? true)) {
                $failure = 1.0;
            } elseif (count($scenario_runs) >= 2) {
                $prev = $scenario_runs[count($scenario_runs) - 2];
                if (!($prev['invariant_pass'] ?? true)) {
                    $failure = 0.5;
                }
            }

            // Coverage
            $run_count = count($scenario_runs);
            if ($run_count >= 3) {
                $coverage = 0.0;
            } else {
                $coverage = 0.5;
            }
        }
    }

    // Fleet need
    $fleet_need = 0.5;
    if ($fleet) {
        $scenario_health = $fleet['scenario_health'][$name] ?? null;
        if ($scenario_health) {
            $pass_rate = $scenario_health['pass_rate'] ?? 1.0;
            $fleet_need = 1.0 - $pass_rate;
        }
    }

    return 0.30 * $recency + 0.35 * $failure + 0.20 * $fleet_need + 0.15 * $coverage;
}

function _build_reason(string $name, array $history = null, array $fleet = null): string {
    $reasons = [];

    if ($history && is_array($history)) {
        $runs = array_filter($history, function($r) use ($name) { return ($r['scenario'] ?? '') === $name; });
        $runs = array_values($runs);
        if (empty($runs)) {
            $reasons[] = 'Never tested on this machine';
        } else {
            $last = end($runs);
            if (!($last['invariant_pass'] ?? true)) {
                $reasons[] = 'Failed last run';
            }
        }
    } else {
        $reasons[] = 'New machine';
    }

    if ($fleet) {
        $health = $fleet['scenario_health'][$name] ?? null;
        if ($health && ($health['pass_rate'] ?? 1) < 0.9) {
            $pct = round(($health['pass_rate'] ?? 0) * 100);
            $reasons[] = "Fleet pass rate: {$pct}%";
        }
    }

    return implode('; ', $reasons) ?: 'Routine coverage';
}

function _get_capability($matrix, string $tier, string $scenario): array {
    if (!$matrix) return [];
    $tier_data = $matrix[$tier] ?? $matrix['default_tier'] ?? [];
    return $tier_data[$scenario] ?? [];
}

function _count_active_machines(string $profiles_dir, int $days): int {
    if (!is_dir($profiles_dir)) return 0;
    $cutoff = time() - ($days * 86400);
    $count = 0;
    foreach (glob("$profiles_dir/*.json") as $f) {
        if (strpos(basename($f), '_tests') !== false) continue;
        $data = json_decode(file_get_contents($f), true);
        if ($data) {
            $last = strtotime($data['last_seen'] ?? '2000-01-01');
            if ($last > $cutoff) $count++;
        }
    }
    return $count;
}

function _scenarios_needing_coverage(array $fleet = null): array {
    if (!$fleet) return [];
    $needing = [];
    foreach (($fleet['scenario_health'] ?? []) as $name => $health) {
        if (($health['pass_rate'] ?? 1) < 0.9) {
            $needing[] = $name;
        }
    }
    return $needing;
}
