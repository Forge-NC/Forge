<?php
/**
 * Forge Fleet Consensus Engine
 *
 * Aggregates signed Proof of Inference results across nodes to produce
 * a decentralised, mathematically-defended capability matrix.
 *
 * Endpoints:
 *   GET  ?action=consensus&scenario=…            → consensus for a scenario
 *   GET  ?action=leaderboard                     → all scenarios, sorted by confidence
 *   GET  ?action=node_stats&machine_id=…         → per-node contribution summary
 *   POST ?action=recalculate                     → force full consensus recalculation
 *                                                   (admin-only, X-Forge-Admin token)
 *
 * Consensus algorithm:
 *   - Per (scenario) across all contributing nodes:
 *     1. Compute weighted mean (weight = 1 / max(1, outlier_count) per node)
 *     2. Identify outliers (score more than 2σ from mean)
 *     3. Compute confidence = 1 − (stddev / max_possible_stddev)
 *     4. Flag outlier nodes (don't discard — they're the most interesting data)
 *   - Minimum 2 nodes for a "verified" consensus entry
 *   - Single-node entries are marked "provisional"
 *
 * Data files:
 *   data/capability_matrix.json      — raw aggregated values (written by challenge_server.php)
 *   data/consensus/                  — per-scenario consensus records
 *   data/consensus/leaderboard.json  — cached leaderboard (rebuilt on recalculate)
 *
 * Deploy to: dirt-star.com/Forge/consensus_engine.php
 */

// ── Config ────────────────────────────────────────────────────────────────────
$DATA_DIR        = __DIR__ . '/data';
$CONSENSUS_DIR   = $DATA_DIR . '/consensus';
$CAP_MATRIX_FILE = $DATA_DIR . '/capability_matrix.json';
$LEADERBOARD     = $CONSENSUS_DIR . '/leaderboard.json';
$ADMIN_TOKEN_ENV = 'FORGE_ADMIN_TOKEN';  // set in server environment

$MIN_NODES_VERIFIED = 2;     // minimum nodes for "verified" status
$OUTLIER_Z_THRESHOLD = 2.0;  // z-score beyond which a node is flagged as outlier

// ── Helpers ───────────────────────────────────────────────────────────────────

function ensure_dir(string $dir): void {
    if (!is_dir($dir)) mkdir($dir, 0750, true);
}

function json_response(int $code, $data): void {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

function load_json(string $path): array {
    if (!file_exists($path)) return [];
    $raw = @file_get_contents($path);
    return $raw ? (json_decode($raw, true) ?? []) : [];
}

function save_json(string $path, $data): void {
    file_put_contents($path, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
}

/**
 * Compute consensus statistics for an array of score floats.
 * Returns: [mean, stddev, confidence, outlier_indices]
 */
function compute_consensus(array $scores): array {
    $n = count($scores);
    if ($n === 0) return [null, null, null, []];

    $mean = array_sum($scores) / $n;

    if ($n === 1) {
        return ['mean' => $mean, 'stddev' => 0.0, 'confidence' => 0.5,
                'outlier_indices' => [], 'node_count' => 1];
    }

    // Population stddev
    $sq = array_sum(array_map(fn($s) => ($s - $mean) ** 2, $scores));
    $std = sqrt($sq / $n);

    // Identify outliers by z-score
    global $OUTLIER_Z_THRESHOLD;
    $outliers = [];
    if ($std > 0) {
        foreach ($scores as $i => $s) {
            if (abs($s - $mean) / $std > $OUTLIER_Z_THRESHOLD) {
                $outliers[] = $i;
            }
        }
    }

    // Confidence: 1 − normalised stddev (max possible stddev for binary 0/1 = 0.5)
    $max_std = 0.5;
    $confidence = max(0.0, 1.0 - ($std / $max_std));

    return [
        'mean'            => round($mean, 4),
        'stddev'          => round($std,  4),
        'confidence'      => round($confidence, 4),
        'outlier_indices' => $outliers,
        'node_count'      => $n,
    ];
}

/**
 * Build the full consensus record for one scenario from cap matrix data.
 */
function build_scenario_consensus(string $scenario_id, array $matrix_entry): array {
    global $MIN_NODES_VERIFIED;

    $values  = $matrix_entry['values'] ?? [];
    $scores  = array_column($values, 'score');
    $stats   = compute_consensus($scores);
    $n       = $stats['node_count'] ?? count($scores);
    $verified = $n >= $MIN_NODES_VERIFIED;

    // Build node-level detail (outliers preserved with flag)
    $nodes = [];
    foreach ($values as $i => $v) {
        $nodes[] = [
            'machine_id' => $v['machine_id'] ?? '?',
            'score'      => $v['score'],
            'latency_ms' => $v['latency_ms'] ?? null,
            'ts'         => $v['ts'] ?? null,
            'outlier'    => in_array($i, $stats['outlier_indices'] ?? []),
        ];
    }

    // Sort: non-outliers first, then outliers
    usort($nodes, fn($a, $b) => $a['outlier'] <=> $b['outlier']);

    return [
        'scenario'    => $scenario_id,
        'node_count'  => $n,
        'consensus'   => $stats['mean'],
        'stddev'      => $stats['stddev'],
        'confidence'  => $stats['confidence'],
        'verified'    => $verified,
        'status'      => $verified ? 'verified' : 'provisional',
        'outlier_count' => count($stats['outlier_indices'] ?? []),
        'nodes'       => $nodes,
        'last_updated' => $matrix_entry['last_updated'] ?? null,
    ];
}

/**
 * Rebuild all per-scenario consensus files and the leaderboard cache.
 */
function recalculate_all(): array {
    global $CAP_MATRIX_FILE, $CONSENSUS_DIR, $LEADERBOARD;

    $matrix  = load_json($CAP_MATRIX_FILE);
    $board   = [];
    $rebuilt = 0;

    foreach ($matrix as $scenario_id => $entry) {
        $rec  = build_scenario_consensus($scenario_id, $entry);
        $path = $CONSENSUS_DIR . '/' . preg_replace('/[^a-zA-Z0-9_\-]/', '_', $scenario_id) . '.json';
        save_json($path, $rec);

        $board[] = [
            'scenario'   => $scenario_id,
            'consensus'  => $rec['consensus'],
            'confidence' => $rec['confidence'],
            'node_count' => $rec['node_count'],
            'verified'   => $rec['verified'],
            'status'     => $rec['status'],
        ];
        $rebuilt++;
    }

    // Sort leaderboard: verified first, then by confidence desc
    usort($board, function($a, $b) {
        if ($a['verified'] !== $b['verified']) return $b['verified'] <=> $a['verified'];
        return $b['confidence'] <=> $a['confidence'];
    });

    save_json($LEADERBOARD, ['updated' => time(), 'entries' => $board]);
    return ['rebuilt' => $rebuilt, 'updated' => time()];
}

// ── Routing ───────────────────────────────────────────────────────────────────

header('Content-Type: application/json');
ensure_dir($CONSENSUS_DIR);

$action = $_GET['action'] ?? 'leaderboard';
$method = $_SERVER['REQUEST_METHOD'];

// GET ?action=consensus&scenario=…
if ($action === 'consensus' && $method === 'GET') {
    $scenario = preg_replace('/[^a-zA-Z0-9_\-]/', '_', $_GET['scenario'] ?? '');
    if (!$scenario) json_response(400, ['error' => 'scenario required']);

    $path = $CONSENSUS_DIR . '/' . $scenario . '.json';
    if (file_exists($path)) {
        json_response(200, load_json($path));
    }

    // Not cached — compute on the fly
    $matrix = load_json($CAP_MATRIX_FILE);
    if (!isset($matrix[$_GET['scenario']])) {
        json_response(404, ['error' => 'Scenario not found in capability matrix']);
    }
    $rec = build_scenario_consensus($_GET['scenario'], $matrix[$_GET['scenario']]);
    save_json($path, $rec);
    json_response(200, $rec);
}

// GET ?action=leaderboard
if ($action === 'leaderboard' && $method === 'GET') {
    if (file_exists($LEADERBOARD)) {
        $board = load_json($LEADERBOARD);
        // Auto-refresh if older than 1 hour
        if (time() - ($board['updated'] ?? 0) < 3600) {
            json_response(200, $board);
        }
    }
    $result = recalculate_all();
    json_response(200, array_merge(load_json($LEADERBOARD), ['recalculated' => true]));
}

// GET ?action=node_stats&machine_id=…
if ($action === 'node_stats' && $method === 'GET') {
    $machine_id = preg_replace('/[^a-zA-Z0-9_\-]/', '', $_GET['machine_id'] ?? '');
    if (!$machine_id) json_response(400, ['error' => 'machine_id required']);

    $matrix = load_json($CAP_MATRIX_FILE);
    $contributions = [];
    $outlier_count = 0;
    $total = 0;

    foreach ($matrix as $scenario_id => $entry) {
        $values = $entry['values'] ?? [];
        $scores = array_column($values, 'score');
        $stats  = compute_consensus($scores);

        foreach ($values as $i => $v) {
            if (($v['machine_id'] ?? '') !== $machine_id) continue;
            $is_outlier = in_array($i, $stats['outlier_indices'] ?? []);
            $contributions[] = [
                'scenario'   => $scenario_id,
                'score'      => $v['score'],
                'latency_ms' => $v['latency_ms'] ?? null,
                'ts'         => $v['ts'] ?? null,
                'outlier'    => $is_outlier,
            ];
            if ($is_outlier) $outlier_count++;
            $total++;
        }
    }

    json_response(200, [
        'machine_id'      => $machine_id,
        'total_proofs'    => $total,
        'outlier_count'   => $outlier_count,
        'outlier_rate'    => $total > 0 ? round($outlier_count / $total, 4) : null,
        'contributions'   => $contributions,
    ]);
}

// POST ?action=recalculate  (admin)
if ($action === 'recalculate' && $method === 'POST') {
    $admin_token = getenv($ADMIN_TOKEN_ENV) ?: '';
    $supplied    = $_SERVER['HTTP_X_FORGE_ADMIN'] ?? '';
    if (!$admin_token || !hash_equals($admin_token, $supplied)) {
        json_response(403, ['error' => 'Admin token required']);
    }
    json_response(200, recalculate_all());
}

json_response(400, ['error' => 'Unknown action or method']);
