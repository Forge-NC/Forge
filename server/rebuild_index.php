<?php
/**
 * One-time script to rebuild assurance index from report files.
 * DELETE AFTER USE.
 */
$DATA_DIR      = __DIR__ . '/data';
$ASSURANCE_IDX = $DATA_DIR . '/assurance/index.json';
$REPORTS_DIR   = $DATA_DIR . '/assurance/reports';

// Ensure directories exist
if (!is_dir($REPORTS_DIR)) mkdir($REPORTS_DIR, 0755, true);

$index = [];
$count = 0;

foreach (glob($REPORTS_DIR . '/*.json') as $file) {
    $report = json_decode(file_get_contents($file), true);
    if (!$report || !isset($report['run_id'])) continue;

    $run_id = $report['run_id'];

    // Check if any result entry has compliance (assure vs break)
    $has_compliance = false;
    if (isset($report['results']) && is_array($report['results'])) {
        foreach ($report['results'] as $r) {
            if (!empty($r['compliance'])) { $has_compliance = true; break; }
        }
    }

    $index[$run_id] = [
        'run_id'              => $run_id,
        'model'               => isset($report['model']) ? $report['model'] : 'unknown',
        'forge_version'       => isset($report['forge_version']) ? $report['forge_version'] : '',
        'pass_rate'           => isset($report['pass_rate']) ? $report['pass_rate'] : 0.0,
        'scenarios_run'       => isset($report['scenarios_run']) ? $report['scenarios_run'] : 0,
        'scenarios_passed'    => isset($report['scenarios_passed']) ? $report['scenarios_passed'] : 0,
        'machine_id'          => isset($report['machine_id']) ? $report['machine_id'] : '',
        'verified_at'         => time(),
        'generated_at'        => isset($report['generated_at']) ? $report['generated_at'] : 0,
        'started_at'          => isset($report['started_at']) ? $report['started_at'] : 0,
        'duration_s'          => isset($report['duration_s']) ? $report['duration_s'] : 0,
        'category_pass_rates' => isset($report['category_pass_rates']) ? $report['category_pass_rates'] : [],
        'compliance'          => $has_compliance,
        'harness_mode'        => isset($report['harness_mode']) ? $report['harness_mode'] : null,
    ];
    $count++;
}

file_put_contents($ASSURANCE_IDX, json_encode($index, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

// Also clear matrix cache so fresh data is served
$cache = $DATA_DIR . '/matrix_cache.json';
if (file_exists($cache)) unlink($cache);

header('Content-Type: application/json');
echo json_encode(['status' => 'ok', 'reports_indexed' => $count, 'index_entries' => count($index)]);
