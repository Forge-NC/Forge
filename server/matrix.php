<?php
/**
 * The Forge Matrix — 3D Neural Telemetry Visualization
 *
 * Scalable aggregation of /break and /assure telemetry.
 * Designed for 1M+ users: server pre-aggregates per-model stats,
 * sends only summary data (no individual runs). Detail fetched on-demand.
 *
 * Endpoints:
 *   GET  matrix.php              — interactive 3D page
 *   GET  matrix.php?fmt=json     — aggregated model summaries
 *   GET  matrix.php?detail=MODEL — on-demand detail for one model
 */

$DATA_DIR      = __DIR__ . '/data';
$ASSURANCE_IDX = $DATA_DIR . '/assurance/index.json';
$REPORTS_DIR   = $DATA_DIR . '/assurance/reports';
$CACHE_FILE    = $DATA_DIR . '/matrix_cache.json';
$CACHE_TTL     = 300; // 5 minutes

function _load_json(string $path): array {
    if (!file_exists($path)) return [];
    $raw = @file_get_contents($path);
    return $raw ? (json_decode($raw, true) ?? []) : [];
}

/**
 * Build aggregated model summaries — O(entries) single pass.
 * Returns compact per-model stats: NO individual runs in the list response.
 * Runs are only returned via ?detail=MODEL on-demand.
 */
function build_matrix_data(array $entries, string $reports_dir): array {
    $models = [];
    foreach ($entries as $e) {
        $model = $e['model'] ?? 'unknown';
        if (!isset($models[$model])) {
            $models[$model] = [
                'id' => $model, 'best_score' => 0, 'worst_score' => 1,
                'avg_score' => 0, 'run_count' => 0, 'categories' => [],
                'unique_users' => 0, 'break_count' => 0, 'assure_count' => 0,
                'score_histogram' => [0,0,0,0,0],
                'trend' => 0, // recent vs overall avg
                'recent_runs' => [], // only keep last 5
                '_sum' => 0, '_cats' => [], '_users' => [], '_recent_scores' => []
            ];
        }
        $rate = floatval($e['pass_rate'] ?? 0);
        $models[$model]['run_count']++;
        $models[$model]['_sum'] += $rate;
        $models[$model]['avg_score'] = $models[$model]['_sum'] / $models[$model]['run_count'];
        if ($rate > $models[$model]['best_score']) $models[$model]['best_score'] = $rate;
        if ($rate < $models[$model]['worst_score']) $models[$model]['worst_score'] = $rate;

        // Histogram bucket
        $bucket = $rate >= 0.95 ? 4 : ($rate >= 0.85 ? 3 : ($rate >= 0.70 ? 2 : ($rate >= 0.50 ? 1 : 0)));
        $models[$model]['score_histogram'][$bucket]++;

        // Type counting: compliance=true means /assure (has regulatory refs),
        // false or missing means /break or harness run
        $type = !empty($e['compliance']) ? 'assure' : 'break';
        if ($type === 'assure') $models[$model]['assure_count']++;
        else $models[$model]['break_count']++;

        // Unique users (by machine_id or run_id prefix)
        $uid = $e['machine_id'] ?? substr($e['run_id'] ?? '', 0, 8);
        if ($uid && !isset($models[$model]['_users'][$uid])) {
            $models[$model]['_users'][$uid] = true;
        }

        // Category aggregation (running average, no per-run storage)
        $cats = $e['category_pass_rates'] ?? [];
        if (empty($cats) && !empty($e['run_id'])) {
            $rpt = _load_json($reports_dir . '/' . $e['run_id'] . '.json');
            $cats = $rpt['category_pass_rates'] ?? [];
            if (!empty($rpt['compliance'])) $type = 'assure';
        }
        foreach ($cats as $cat => $val) {
            if (!isset($models[$model]['_cats'][$cat])) $models[$model]['_cats'][$cat] = ['s'=>0,'n'=>0];
            $models[$model]['_cats'][$cat]['s'] += $val;
            $models[$model]['_cats'][$cat]['n']++;
        }

        // Keep only 5 most recent runs (sliding window)
        $at = intval($e['generated_at'] ?? 0);
        $models[$model]['_recent_scores'][] = $rate;
        $run_entry = [
            'run_id' => $e['run_id'] ?? '', 'score' => $rate,
            'at' => $at, 'type' => $type
        ];
        $models[$model]['recent_runs'][] = $run_entry;
        if (count($models[$model]['recent_runs']) > 5) {
            array_shift($models[$model]['recent_runs']);
        }
    }

    // Finalize aggregates
    foreach ($models as &$m) {
        // Category averages
        $avg = [];
        foreach ($m['_cats'] as $c => $d) $avg[$c] = round($d['s'] / $d['n'], 3);
        $m['categories'] = $avg;

        // Unique user count
        $m['unique_users'] = count($m['_users']);

        // Trend: last 20 runs avg vs overall avg
        $recent = array_slice($m['_recent_scores'], -20);
        $recent_avg = count($recent) > 0 ? array_sum($recent) / count($recent) : $m['avg_score'];
        $m['trend'] = round($recent_avg - $m['avg_score'], 4);

        // Clean up internal fields
        unset($m['_sum'], $m['_cats'], $m['_users'], $m['_recent_scores']);
    }

    uasort($models, function($a, $b) { return $b['avg_score'] <=> $a['avg_score']; });
    return array_values($models);
}

/**
 * Get detailed data for a single model (on-demand, fetched when user clicks a hub).
 */
function get_model_detail(string $model_id, array $entries, string $reports_dir) {
    $runs = [];
    $fp_agg = []; // fingerprint probe aggregation
    $cal_scores = [];

    foreach ($entries as $e) {
        if (($e['model'] ?? '') !== $model_id) continue;

        $rate = floatval($e['pass_rate'] ?? 0);
        $run_id = $e['run_id'] ?? '';
        $type = !empty($e['compliance']) ? 'assure' : 'break';
        $cats = $e['category_pass_rates'] ?? [];
        $latency = $e['latency_ms'] ?? null;

        if ($run_id) {
            $rpt = _load_json($reports_dir . '/' . $run_id . '.json');
            if (empty($cats)) $cats = $rpt['category_pass_rates'] ?? [];
            if (!empty($rpt['compliance'])) $type = 'assure';

            // Aggregate fingerprint probes
            if (!empty($rpt['fingerprint'])) {
                foreach ($rpt['fingerprint'] as $probe => $val) {
                    if (!isset($fp_agg[$probe])) $fp_agg[$probe] = ['s'=>0,'n'=>0];
                    $fp_agg[$probe]['s'] += $val;
                    $fp_agg[$probe]['n']++;
                }
            }
            // Calibration
            if (isset($rpt['calibration_score']) && $rpt['calibration_score'] >= 0) {
                $cal_scores[] = $rpt['calibration_score'];
            }
        }

        $runs[] = [
            'run_id' => $run_id, 'score' => $rate,
            'at' => intval($e['generated_at'] ?? 0), 'type' => $type,
            'categories' => $cats,
            'latency_ms' => $latency,
        ];
    }

    if (empty($runs)) return null;

    // Average fingerprint
    $fp = [];
    foreach ($fp_agg as $probe => $d) $fp[$probe] = round($d['s'] / $d['n'], 3);

    // Average calibration
    $cal = count($cal_scores) > 0 ? round(array_sum($cal_scores) / count($cal_scores), 3) : -1;

    // Only return last 50 runs for the detail panel
    usort($runs, function($a, $b) { return $b['at'] <=> $a['at']; });
    $runs = array_slice($runs, 0, 50);

    return [
        'model' => $model_id,
        'runs' => $runs,
        'fingerprint' => $fp,
        'calibration_score' => $cal,
    ];
}

// ── JSON API ──
$wants_json = (($_GET['fmt'] ?? '') === 'json')
           || (strpos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false);
$detail_model = $_GET['detail'] ?? '';

// Force demo mode via ?demo=1
$force_demo = !empty($_GET['demo']);

/**
 * Extract entries from index.json regardless of format.
 * assurance_verify.php stores {run_id: {...}, ...} at top level.
 * Handle both that and a hypothetical {entries: [...]} format.
 */
function _extract_entries(array $idx) {
    if (isset($idx['entries']) && is_array($idx['entries'])) return $idx['entries'];
    // Top-level keyed format: every value is an entry with 'run_id'
    $entries = [];
    foreach ($idx as $k => $v) {
        if (is_array($v) && isset($v['run_id'])) $entries[] = $v;
    }
    return $entries;
}

if ($detail_model && !$force_demo) {
    // On-demand detail for a single model
    $idx     = _load_json($ASSURANCE_IDX);
    $entries = _extract_entries($idx);
    $detail  = get_model_detail($detail_model, $entries, $REPORTS_DIR);
    header('Content-Type: application/json');
    echo json_encode($detail ? $detail : array('error' => 'Model not found'), JSON_UNESCAPED_SLASHES);
    exit;
}

if ($wants_json) {
    // Demo mode — skip real data
    if ($force_demo) {
        header('Content-Type: application/json');
        header('X-Matrix-Source: demo');
        echo json_encode(array('models' => array(), 'total_runs' => 0, 'total_models' => 0, 'demo' => true), JSON_UNESCAPED_SLASHES);
        exit;
    }

    // Check cache first
    if (file_exists($CACHE_FILE) && (time() - filemtime($CACHE_FILE)) < $CACHE_TTL) {
        header('Content-Type: application/json');
        header('X-Matrix-Cache: HIT');
        readfile($CACHE_FILE);
        exit;
    }

    $idx     = _load_json($ASSURANCE_IDX);
    $entries = _extract_entries($idx);
    $models  = build_matrix_data($entries, $REPORTS_DIR);
    $payload = json_encode([
        'models'       => $models,
        'total_runs'   => count($entries),
        'total_models' => count($models),
        'cached_at'    => time(),
    ], JSON_UNESCAPED_SLASHES);

    // Write cache (atomic)
    $tmp = $CACHE_FILE . '.tmp';
    if (@file_put_contents($tmp, $payload)) @rename($tmp, $CACHE_FILE);

    header('Content-Type: application/json');
    header('X-Matrix-Cache: MISS');
    echo $payload;
    exit;
}

// ── HTML page ──
$page_title = 'The Forge Matrix';
$page_id    = 'matrix';
require_once __DIR__ . '/includes/header.php';
?>

<style>
/* ── Matrix: full-viewport 3D scene ─────────────────────────────────── */
body.pg-matrix { margin:0; overflow:hidden; background:#060a12; }
body.pg-matrix .nav { background:rgba(6,10,18,0.6); backdrop-filter:blur(8px); border-bottom:1px solid rgba(88,166,255,0.08); }
body.pg-matrix footer, body.pg-matrix .footer { display:none; }

#matrix-canvas { position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:0; }

/* Scan lines */
#matrix-scanlines {
    position:fixed; top:0; left:0; right:0; bottom:0; pointer-events:none; z-index:1;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,200,255,0.008) 2px, rgba(0,200,255,0.008) 4px);
    animation: scanShift 10s linear infinite;
}
@keyframes scanShift { to { transform:translateY(4px); } }

/* Title overlay */
#matrix-title {
    position:fixed; top:70px; left:0; right:0; text-align:center; z-index:5; pointer-events:none;
}
#matrix-title h1 {
    font-family:'Segoe UI',system-ui,sans-serif; font-size:1.6rem; font-weight:300;
    letter-spacing:0.35em; text-transform:uppercase;
    color:rgba(0,212,255,0.7); margin:0;
    text-shadow:0 0 30px rgba(0,212,255,0.3), 0 0 60px rgba(0,212,255,0.1);
}
#matrix-title .subtitle {
    font-size:0.7rem; letter-spacing:0.5em; color:rgba(100,212,255,0.5);
    margin-top:4px; text-transform:uppercase; text-shadow:0 0 10px rgba(0,180,255,0.15);
}

/* Stats overlay */
#matrix-stats {
    position:fixed; bottom:24px; left:24px; z-index:5;
    font-family:'Consolas','Fira Code',monospace; font-size:0.72rem;
    color:rgba(140,210,240,0.75); line-height:1.8; pointer-events:none;
    text-shadow:0 0 6px rgba(0,180,255,0.15);
}
#matrix-stats .val { color:rgba(100,220,255,0.95); font-weight:700; text-shadow:0 0 8px rgba(0,200,255,0.25); }

/* Tooltip */
#matrix-tooltip {
    display:none; position:fixed; z-index:10; pointer-events:none;
    padding:5px 10px; border-radius:4px;
    background:rgba(6,10,18,0.85); border:1px solid rgba(0,212,255,0.25);
    color:#b0bec5; font-family:'Consolas',monospace; font-size:0.75rem;
    backdrop-filter:blur(6px); white-space:nowrap;
}

/* Info panel — compact, no scroll hell */
#matrix-info {
    position:fixed; top:100px; right:-300px; width:260px; z-index:10;
    background:rgba(6,10,18,0.88); border-left:1px solid rgba(0,212,255,0.08);
    border-bottom:1px solid rgba(0,212,255,0.06); border-radius:0 0 0 8px;
    backdrop-filter:blur(10px); padding:20px 14px 14px;
    font-family:'Segoe UI',system-ui,sans-serif; color:#b0bec5;
    max-height:calc(100vh - 120px); overflow-y:auto;
    transition:right 0.35s cubic-bezier(0.4,0,0.2,1);
}
#matrix-info::-webkit-scrollbar { width:3px; }
#matrix-info::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.15); border-radius:2px; }
#matrix-info.open { right:0; }

#matrix-info .mi-close {
    position:sticky; top:0; right:0; cursor:pointer; z-index:2;
    font-size:1.8rem; font-weight:700; color:rgba(255,60,60,0.8); line-height:1;
    width:100%; height:32px; text-align:right; padding-right:10px;
    background:rgba(6,10,18,0.95);
}
#matrix-info .mi-close:hover { color:#ff2222; }

#matrix-info h3 {
    font-size:1.1rem; color:#58a6ff; margin:0 0 4px; font-weight:600;
    font-family:'Consolas',monospace; padding-right:30px;
}
.mi-score {
    font-size:1.8rem; font-weight:200; color:#00d4ff; margin:2px 0 4px;
    text-shadow:0 0 15px rgba(0,212,255,0.2);
}
.mi-meta { font-size:0.75rem; color:rgba(190,205,215,0.75); margin-bottom:16px; }
.mi-section {
    font-size:0.65rem; text-transform:uppercase; letter-spacing:0.15em;
    color:rgba(100,212,255,0.6); margin:18px 0 8px; font-weight:700;
    border-top:1px solid rgba(0,212,255,0.08); padding-top:10px;
    text-shadow:0 0 6px rgba(0,180,255,0.1);
}
.mi-cat { display:flex; align-items:center; gap:6px; margin-bottom:5px; font-size:0.72rem; }
.mi-cat-name { width:55px; text-align:right; color:rgba(176,190,197,0.7); flex-shrink:0; font-size:0.6rem; }
.mi-bar { flex:1; height:6px; background:rgba(255,255,255,0.06); border-radius:3px; overflow:hidden; }
.mi-bar-fill { height:100%; border-radius:3px; transition:width 0.5s ease; }
.mi-cat-pct { width:32px; text-align:right; font-family:'Consolas',monospace; font-size:0.68rem; color:rgba(176,190,197,0.5); }
.mi-run {
    font-family:'Consolas',monospace; font-size:0.7rem;
    color:rgba(176,190,197,0.5); padding:3px 0;
    border-bottom:1px solid rgba(255,255,255,0.03);
}
.mi-dim { color:rgba(176,190,197,0.3); font-size:0.72rem; font-style:italic; }

/* Scrollable fingerprint section */
.mi-fp-scroll {
    max-height:180px; overflow-y:auto; padding-right:3px;
}
.mi-fp-scroll::-webkit-scrollbar { width:3px; }
.mi-fp-scroll::-webkit-scrollbar-track { background:transparent; }
.mi-fp-scroll::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.12); border-radius:2px; }

/* Legend / Guide */
#matrix-legend {
    position:fixed; bottom:24px; right:24px; z-index:5; pointer-events:auto;
    font-family:'Consolas',monospace; font-size:0.65rem; color:rgba(190,210,220,0.7);
    text-align:right; line-height:2; max-width:220px;
    background:rgba(4,8,16,0.88); padding:10px 14px; border-radius:6px;
    border:1px solid rgba(0,212,255,0.12);
}
#matrix-legend .legend-close { position:absolute; top:4px; right:6px; cursor:pointer; color:rgba(255,60,60,0.7); font-size:1.4rem; font-weight:700; line-height:1; width:24px; height:24px; text-align:center; }
#matrix-legend .legend-close:hover { color:#ff2222; }
#matrix-legend .legend-header {
    font-size:0.55rem; text-transform:uppercase; letter-spacing:0.15em;
    color:rgba(100,212,255,0.6); margin-bottom:4px; padding-right:20px; font-weight:700;
}
.legend-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:4px; vertical-align:middle; }
.legend-row { display:flex; justify-content:space-between; align-items:center; line-height:1.8; }
.legend-dim { color:rgba(176,190,197,0.45); font-size:0.55rem; margin-top:6px; font-style:italic; }

/* Leaderboards */
#matrix-leaderboards {
    position:fixed; top:70px; left:20px; z-index:5;
    font-family:'Consolas',monospace; font-size:0.6rem;
    max-height:calc(100vh - 180px); overflow-y:auto;
    display:flex; flex-wrap:wrap; gap:6px; max-width:520px;
    pointer-events:auto;
}
#matrix-leaderboards::-webkit-scrollbar { width:10px; }
#matrix-leaderboards::-webkit-scrollbar-track { background:rgba(0,212,255,0.04); border-radius:5px; }
#matrix-leaderboards::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.25); border-radius:5px; min-height:30px; }
#matrix-leaderboards::-webkit-scrollbar-thumb:hover { background:rgba(0,212,255,0.4); }
.lb-sector {
    background:rgba(4,8,16,0.5); border:1px solid rgba(0,212,255,0.06);
    border-radius:5px; padding:6px 8px; min-width:200px; flex:1 1 200px;
}
.lb-title {
    font-size:0.5rem; text-transform:uppercase; letter-spacing:0.12em;
    margin-bottom:4px; opacity:0.7;
}
.lb-row { display:flex; align-items:center; gap:4px; line-height:1.6; }
.lb-rank { color:rgba(100,212,255,0.7); width:18px; font-weight:700; }
.lb-name { flex:1; color:rgba(210,225,235,0.95); white-space:nowrap; font-size:0.58rem; }
.lb-pct { font-weight:700; opacity:0.85; }

/* Demo notice */
#matrix-demo-notice {
    display:none; position:fixed; top:120px; left:50%; transform:translateX(-50%); z-index:8;
    padding:10px 22px; border-radius:6px; max-width:520px; text-align:center;
    background:rgba(6,10,18,0.88); border:1px solid rgba(255,171,0,0.2);
    backdrop-filter:blur(8px);
    font-family:'Consolas',monospace; font-size:0.7rem; line-height:1.6;
    color:rgba(255,171,0,0.6);
    animation: noticePulse 3s ease-in-out infinite;
}
#matrix-demo-notice code { color:rgba(0,212,255,0.7); font-size:0.68rem; }
#matrix-demo-notice .notice-tag {
    display:inline-block; padding:1px 7px; border-radius:3px; margin-right:6px;
    background:rgba(255,171,0,0.12); color:rgba(255,171,0,0.8);
    font-weight:700; font-size:0.62rem; letter-spacing:0.12em; vertical-align:middle;
}
@keyframes noticePulse {
    0%,100% { border-color:rgba(255,171,0,0.2); }
    50% { border-color:rgba(255,171,0,0.35); }
}

/* Loading */
#matrix-loading {
    position:fixed; top:0; left:0; right:0; bottom:0; z-index:20;
    display:flex; align-items:center; justify-content:center;
    background:#060a12; transition:opacity 0.8s ease;
}
#matrix-loading.fade { opacity:0; pointer-events:none; }
#matrix-loading .spinner {
    width:40px; height:40px; border:2px solid rgba(0,212,255,0.1);
    border-top-color:rgba(0,212,255,0.6); border-radius:50%;
    animation:spin 0.8s linear infinite;
}
@keyframes spin { to { transform:rotate(360deg); } }
#matrix-loading .load-text {
    position:absolute; margin-top:70px;
    font-family:'Consolas',monospace; font-size:0.7rem; color:rgba(0,212,255,0.4);
    letter-spacing:0.1em;
}
/* ── Head-to-Head Compare ────────────────────────────────────────── */
#h2h-overlay {
    display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
    z-index:20; width:min(520px,90vw); max-height:80vh; overflow-y:auto;
    background:rgba(6,10,18,0.95); border:1px solid rgba(0,212,255,0.2);
    border-radius:10px; padding:24px; backdrop-filter:blur(14px);
    font-family:'Segoe UI',system-ui,sans-serif; color:#b0bec5;
}
#h2h-overlay .h2h-close {
    position:absolute; top:8px; right:12px; cursor:pointer;
    font-size:1.6rem; font-weight:700; color:rgba(255,60,60,0.7); line-height:1;
}
#h2h-overlay .h2h-close:hover { color:#ff2222; }
#h2h-overlay h3 { color:#00d4ff; font-family:Consolas,monospace; font-size:0.9rem;
    letter-spacing:0.12em; margin:0 0 12px; text-transform:uppercase; }
.h2h-row { display:flex; align-items:center; gap:6px; margin:4px 0; font-size:0.72rem; }
.h2h-label { width:60px; text-align:right; color:rgba(176,190,197,0.6); font-size:0.6rem; flex-shrink:0; }
.h2h-bar-wrap { flex:1; display:flex; gap:2px; height:10px; }
.h2h-bar { height:100%; border-radius:3px; transition:width 0.6s ease; }
.h2h-pct { width:30px; text-align:right; font-family:Consolas,monospace; font-size:0.6rem; }
.h2h-name { font-family:Consolas,monospace; font-size:0.7rem; font-weight:700; }
.h2h-radar-wrap { display:flex; justify-content:center; margin:12px 0 8px; }

/* ── Sector Drilldown ────────────────────────────────────────────── */
#sector-drilldown {
    display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
    z-index:20; width:min(400px,90vw); max-height:80vh; overflow-y:auto;
    background:rgba(6,10,18,0.95); border:1px solid rgba(0,212,255,0.2);
    border-radius:10px; padding:24px; backdrop-filter:blur(14px);
    font-family:'Segoe UI',system-ui,sans-serif; color:#b0bec5;
}
#sector-drilldown .sd-close {
    position:absolute; top:8px; right:12px; cursor:pointer;
    font-size:1.6rem; font-weight:700; color:rgba(255,60,60,0.7); line-height:1;
}
#sector-drilldown .sd-close:hover { color:#ff2222; }
#sector-drilldown h3 { color:#00d4ff; font-family:Consolas,monospace; font-size:0.9rem;
    letter-spacing:0.12em; margin:0 0 12px; text-transform:uppercase; }
.sd-row { display:flex; align-items:center; gap:6px; margin:3px 0; font-size:0.68rem;
    cursor:pointer; padding:3px 4px; border-radius:3px; transition:background 0.2s; }
.sd-row:hover { background:rgba(0,212,255,0.08); }
.sd-rank { color:rgba(0,212,255,0.5); width:24px; font-weight:600; font-family:Consolas,monospace; }
.sd-name { flex:1; color:rgba(200,215,225,0.85); font-family:Consolas,monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.sd-score { font-weight:700; font-family:Consolas,monospace; }

/* ── Heatmap / History / Data Source — positioned by JS, hover-only CSS ── */
#heatmap-btn:hover, #history-btn:hover { color:#40e8ff!important; border-color:rgba(0,212,255,0.5)!important; text-shadow:0 0 10px rgba(0,200,255,0.3)!important; }
#datasrc-btn:hover { color:#ffcc44!important; border-color:rgba(255,171,0,0.5)!important; text-shadow:0 0 10px rgba(255,171,0,0.3)!important; }
#matrix-history::-webkit-scrollbar { width:3px; height:3px; }
#matrix-history::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.15); border-radius:2px; }

/* ── Embed mode ──────────────────────────────────────────────────── */
body.pg-matrix.embed-mode .nav,
body.pg-matrix.embed-mode #matrix-stats,
body.pg-matrix.embed-mode #matrix-legend,
body.pg-matrix.embed-mode #matrix-leaderboards,
body.pg-matrix.embed-mode #tour-btn,
body.pg-matrix.embed-mode #polarity-btn,
body.pg-matrix.embed-mode #family-btn,
body.pg-matrix.embed-mode #heatmap-btn,
body.pg-matrix.embed-mode #datasrc-btn,
body.pg-matrix.embed-mode #history-btn,
body.pg-matrix.embed-mode #model-search,
body.pg-matrix.embed-mode #matrix-demo-notice,
body.pg-matrix.embed-mode #matrix-compass { display:none!important; }
body.pg-matrix.embed-mode #matrix-title h1 { font-size:1rem; }
body.pg-matrix.embed-mode #matrix-title .subtitle { display:none; }

/* ── Model Search ─────────────────────────────────────────────────── */
#model-search {
    position:fixed; bottom:16px; left:50%; transform:translateX(-50%); z-index:6;
    display:flex; flex-direction:column; align-items:center; pointer-events:auto;
}
#model-search input {
    width:260px; padding:7px 12px; border-radius:4px;
    background:rgba(4,8,16,0.85); border:1px solid rgba(0,212,255,0.15);
    color:rgba(200,215,225,0.9); font-family:'Consolas',monospace; font-size:0.72rem;
    outline:none; backdrop-filter:blur(8px); letter-spacing:0.03em;
}
#model-search input:focus { border-color:rgba(0,212,255,0.4); }
#model-search input::placeholder { color:rgba(0,212,255,0.25); }
#model-search-results {
    order:-1; width:260px; max-height:240px; overflow-y:auto; margin-bottom:2px;
    background:rgba(4,8,16,0.92); border:1px solid rgba(0,212,255,0.12);
    border-radius:4px 4px 0 0; display:none; backdrop-filter:blur(10px);
}
#model-search-results::-webkit-scrollbar { width:4px; }
#model-search-results::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.2); border-radius:2px; }
.search-result {
    padding:5px 12px; cursor:pointer; font-family:'Consolas',monospace; font-size:0.68rem;
    color:rgba(200,215,225,0.7); display:flex; justify-content:space-between; align-items:center;
    border-bottom:1px solid rgba(0,212,255,0.04);
}
.search-result:hover { background:rgba(0,212,255,0.08); color:#fff; }
.search-result .sr-score { font-size:0.6rem; font-weight:700; }

/* ── Compass ──────────────────────────────────────────────────────── */
#matrix-compass {
    position:fixed; bottom:24px; right:270px; z-index:12;
    width:160px; height:160px;
    pointer-events:none;
    background:rgba(4,8,16,0.9); border:2px solid rgba(0,212,255,0.35);
    border-radius:50%;
}

/* ── Tour ─────────────────────────────────────────────────────────── */
#tour-btn {
    position:fixed; top:72px; right:180px; z-index:6; cursor:pointer;
    font-family:'Consolas',monospace; font-size:0.65rem; letter-spacing:0.15em;
    color:rgba(120,220,255,0.8); background:rgba(4,8,16,0.75);
    border:1px solid rgba(0,212,255,0.25); border-radius:4px;
    padding:6px 14px; text-transform:uppercase; pointer-events:auto;
    transition:all 0.3s; font-weight:600; text-shadow:0 0 6px rgba(0,180,255,0.15);
}
#tour-btn:hover { color:#00d4ff; border-color:rgba(0,212,255,0.5); background:rgba(4,8,16,0.9); text-shadow:0 0 10px rgba(0,200,255,0.3); }
#tour-modal {
    display:none; position:fixed; z-index:15; pointer-events:none;
    max-width:340px; padding:18px 22px; border-radius:8px;
    background:rgba(4,8,16,0.92); border:1px solid rgba(0,212,255,0.2);
    backdrop-filter:blur(12px);
    font-family:'Segoe UI',system-ui,sans-serif; color:#b0bec5; font-size:0.78rem; line-height:1.6;
    animation: tourFadeIn 0.6s ease-out;
}
@keyframes tourFadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
@keyframes tourPulseBtn { 0%,100% { border-color:#ffab00; box-shadow:0 0 8px rgba(255,171,0,0.3); } 50% { border-color:#ffe082; box-shadow:0 0 20px rgba(255,171,0,0.6); } }
@keyframes tourBounceDown { 0%,100% { transform:translateY(0); opacity:0.6; } 50% { transform:translateY(10px); opacity:1; } }
#tour-modal h3 {
    font-family:'Consolas',monospace; font-size:0.9rem; color:#00d4ff; margin:0 0 8px;
    letter-spacing:0.08em; text-transform:uppercase;
}
#tour-modal .tour-sub { font-size:0.62rem; color:rgba(0,212,255,0.35); letter-spacing:0.1em; text-transform:uppercase; margin-bottom:6px; }
#tour-modal .tour-highlight { color:#58a6ff; font-weight:600; }
#tour-modal .tour-step-indicator {
    margin-top:10px; font-family:'Consolas',monospace; font-size:0.55rem;
    color:rgba(0,212,255,0.3); letter-spacing:0.2em; text-transform:uppercase;
}
#tour-modal .tour-btns {
    display:flex; gap:10px; margin-top:14px; pointer-events:auto;
}
#tour-modal .tour-continue {
    flex:1; padding:10px 0; border:none; border-radius:5px; cursor:pointer;
    font-family:'Consolas',monospace; font-size:0.8rem; font-weight:700;
    letter-spacing:0.12em; text-transform:uppercase;
    background:linear-gradient(135deg,#ffab00,#ffd740); color:#0a0e14;
    box-shadow:0 0 20px rgba(255,171,0,0.25);
    transition:all 0.2s;
}
#tour-modal .tour-continue:hover { background:linear-gradient(135deg,#ffc107,#ffe082); box-shadow:0 0 30px rgba(255,171,0,0.4); }
#tour-modal .tour-exit {
    padding:10px 14px; border:1px solid rgba(255,255,255,0.12); border-radius:5px; cursor:pointer;
    font-family:'Consolas',monospace; font-size:0.65rem; letter-spacing:0.1em; text-transform:uppercase;
    background:rgba(255,255,255,0.04); color:rgba(255,255,255,0.4);
    transition:all 0.2s;
}
#tour-modal .tour-exit:hover { border-color:rgba(255,80,80,0.4); color:rgba(255,80,80,0.7); }

/* ── Mobile responsive ────────────────────────────────────────────── */
@media (max-width:768px) {
    #matrix-title h1 { font-size:1.1rem; letter-spacing:0.2em; }
    #matrix-title .subtitle { font-size:0.55rem; letter-spacing:0.3em; }
    #matrix-stats { bottom:12px; left:12px; font-size:0.6rem; }
    #matrix-legend { display:none; bottom:12px; right:12px; max-width:180px; font-size:0.55rem; padding:8px 10px; }
    #matrix-leaderboards {
        top:auto; bottom:60px; left:8px; right:8px; max-width:100%;
        max-height:140px; flex-direction:column; flex-wrap:nowrap; gap:4px;
    }
    #matrix-leaderboards .panel-body { flex-direction:column!important; flex-wrap:nowrap!important; gap:4px!important; }
    .lb-sector { min-width:unset!important; flex:0 0 auto!important; padding:4px 6px; overflow:hidden; margin:0; display:flex; flex-direction:column; gap:0; }
    .lb-sector > * { margin:0!important; }
    .lb-sector .lb-title { font-size:0.45rem; padding:0 0 1px 0; }
    .lb-sector .lb-row { font-size:0.52rem; line-height:1.3; padding:0; }
    .lb-header-bar { flex:0 0 auto; }
    #matrix-info { width:100vw; right:-100vw; border-radius:0; }
    #matrix-info.open { right:0; }
    #matrix-demo-notice { max-width:90vw; font-size:0.62rem; padding:8px 14px; }
    #model-search { bottom:10px; }
    #model-search input { width:180px; font-size:0.6rem; padding:5px 8px; }
    #model-search-results { width:180px; }
    #tour-btn, #polarity-btn, #family-btn, #heatmap-btn, #datasrc-btn, #history-btn {
        top:100px!important; bottom:auto!important; font-size:0.5rem!important; padding:5px 8px!important;
        background:rgba(4,8,16,0.92)!important; border:1px solid rgba(0,212,255,0.5)!important;
        color:#00d4ff!important; font-weight:700!important; right:auto!important;
        box-shadow:none!important; transform:none!important;
    }
    #tour-btn { left:6px!important; }
    #polarity-btn { left:76px!important; }
    #family-btn { left:190px!important; }
    #heatmap-btn { left:290px!important; }
    #datasrc-btn { display:none!important; }
    #history-btn { left:370px!important; }
    #matrix-history { right:8px!important; left:8px!important; bottom:50px!important; max-width:calc(100vw - 16px)!important; }
    #h2h-overlay, #sector-drilldown { width:95vw!important; max-height:85vh!important; padding:14px!important; }
    #matrix-compass { top:130px!important; bottom:auto!important; left:6px!important; right:auto!important;
        width:80px!important; height:80px!important; transform:none!important; border-width:1px!important; }
    #tour-modal { max-width:calc(100vw - 20px); left:10px!important; right:10px; font-size:0.7rem; padding:12px 14px; }
    #tour-modal h3 { font-size:0.8rem; }
    #tour-modal .tour-continue { padding:8px 0; font-size:0.72rem; }
    #tour-modal .tour-exit { padding:8px 10px; font-size:0.58rem; }
    #creator-legend { bottom:auto!important; top:220px!important; right:auto!important; left:6px!important;
        font-size:0.5rem!important; max-width:160px!important; padding:6px 8px!important; }
    #matrix-info { top:0!important; max-height:100vh!important; padding-top:0!important; z-index:1100!important; }
    #matrix-info .mi-close { font-size:2.4rem; height:52px; padding-top:10px; padding-right:14px;
        background:rgba(6,10,18,0.98); border-bottom:1px solid rgba(255,60,60,0.2);
        display:flex; align-items:center; justify-content:flex-end; }
}
@media (max-width:480px) {
    #matrix-title h1 { font-size:0.9rem; }
    #matrix-title .subtitle { display:none; }
    #matrix-stats { font-size:0.52rem; line-height:1.6; }
    #matrix-legend { max-width:150px; font-size:0.5rem; }
    .legend-row { font-size:0.48rem; }
    .legend-dim { display:none; }
    #matrix-leaderboards { max-height:110px; bottom:50px; }
    .lb-sector { padding:3px 5px; }
    .lb-name { font-size:0.5rem; }
}
</style>

<div id="matrix-canvas"></div>
<div id="matrix-scanlines"></div>

<div id="matrix-loading">
    <div class="spinner"></div>
    <div class="load-text">INITIALIZING MATRIX</div>
</div>

<div id="matrix-title">
    <h1>The Forge Matrix</h1>
    <div class="subtitle">Decentralized Model Intelligence Network</div>
</div>

<div id="matrix-stats">
    <span class="val" id="stat-models">0</span> models indexed<br>
    <span class="val" id="stat-runs">0</span> test runs<br>
    <span class="val" id="stat-nodes">0</span> unique users
</div>

<div id="matrix-demo-notice">
    <span class="notice-tag">SIMULATION</span>
    Displaying generated sample data. Live nodes appear as users
    run <code>/break --share</code> with <code>telemetry_enabled: true</code> in their config.
    <div style="margin-top:8px"><button onclick="this.parentElement.parentElement.style.display='none'" style="background:rgba(255,171,0,0.12);border:1px solid rgba(255,171,0,0.3);color:rgba(255,171,0,0.8);padding:3px 16px;border-radius:3px;cursor:pointer;font-family:Consolas,monospace;font-size:0.65rem;letter-spacing:0.1em">OK</button></div>
</div>

<div id="model-search">
    <input type="text" id="model-search-input" placeholder="Search models..." autocomplete="off" spellcheck="false">
    <div id="model-search-results"></div>
</div>
<canvas id="matrix-compass" width="160" height="160"></canvas>
<div id="tour-btn" onclick="window._fmTour&&window._fmTour()">GUIDED TOUR</div>
<div id="tour-modal"></div>
<div id="matrix-tooltip"></div>
<div id="matrix-info"></div>

<div id="matrix-leaderboards"></div>
<div id="h2h-overlay"></div>
<div id="sector-drilldown"></div>

<div id="matrix-legend">
    <div class="legend-close" onclick="window._togglePanel(this.parentElement)">&times;</div>
    <div class="legend-header">HOW TO READ THE MATRIX</div>
    <div class="panel-body">
        <div class="legend-row"><span><span class="legend-dot" style="background:#00ffcc"></span>Elite 95%+</span></div>
        <div class="legend-row"><span><span class="legend-dot" style="background:#50ff80"></span>Strong 85%+</span></div>
        <div class="legend-row"><span><span class="legend-dot" style="background:#ffab00"></span>Moderate 70%+</span></div>
        <div class="legend-row"><span><span class="legend-dot" style="background:#ff1744"></span>Weak &lt;70%</span></div>
        <div style="margin:6px 0 2px;border-top:1px solid rgba(0,212,255,0.06);padding-top:6px">
            <div class="legend-row"><span style="color:rgba(0,212,255,0.4)">&#9679;</span>&nbsp; Near core = higher score</div>
            <div class="legend-row"><span style="color:rgba(0,212,255,0.4)">&#8593;</span>&nbsp; Higher Y = improving trend</div>
            <div class="legend-row"><span style="color:rgba(0,212,255,0.4)">&#9711;</span>&nbsp; Larger = more test runs</div>
            <div class="legend-row"><span style="color:rgba(0,212,255,0.4)">&#9481;</span>&nbsp; Ring = score tier boundary</div>
            <div class="legend-row"><span style="color:rgba(0,188,212,0.4)">&#9473;</span>&nbsp; Line = same model family</div>
        </div>
        <div class="legend-dim">Double-click a node to inspect</div>
    </div>
</div>
<script>
window._togglePanel=function(el){
    const body=el.querySelector('.panel-body');
    const btn=el.querySelector('.legend-close,.lb-close-btn');
    if(!body)return;
    const collapsed=body.style.display==='none';
    body.style.display=collapsed?'':'none';
    if(btn)btn.textContent=collapsed?'\u00d7':'+';
};
</script>

<script type="importmap">
{
    "imports": {
        "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"
    }
}
</script>
<script type="module" src="assets/matrix.js?v=<?php echo filemtime(__DIR__ . '/assets/matrix.js'); ?>"></script>

<script>
document.body.classList.add('pg-matrix');
if(new URLSearchParams(location.search).get('embed')==='1')document.body.classList.add('embed-mode');
</script>
