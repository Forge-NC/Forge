<?php
/**
 * Forge Telemetry Analyzer
 *
 * Scans uploaded zip bundles and builds fleet intelligence data products.
 * Run via CLI: php analyzer.php
 * Can also be triggered via HTTP (requires auth).
 *
 * Data products created in data/:
 *   profiles/{machine_id}.json       — per-machine usage/hardware profile
 *   profiles/{machine_id}_tests.json — per-machine stress test history
 *   fleet_analytics.json             — fleet-wide rollup
 *   capability_matrix.json           — GPU-tier performance map
 *
 * Uses watermark file to track incremental processing.
 */

// Auth only applies when accessed via HTTP
if (php_sapi_name() !== 'cli') {
    require_once __DIR__ . '/auth.php';
    require_auth();
}

$DATA_DIR = __DIR__ . '/data';
$PROFILES_DIR = $DATA_DIR . '/profiles';
$WATERMARK_FILE = $DATA_DIR . '/analyzer_watermark.json';
$ERROR_LOG = $DATA_DIR . '/analyzer_errors.log';

// ── Ensure directories exist ──

if (!is_dir($PROFILES_DIR)) {
    @mkdir($PROFILES_DIR, 0750, true);
}

// ── Load watermark ──

function load_watermark(string $path): array {
    if (!file_exists($path)) {
        return ['last_processed_date' => '00000000', 'processed_files' => []];
    }
    $data = json_decode(file_get_contents($path), true);
    if (!is_array($data)) {
        return ['last_processed_date' => '00000000', 'processed_files' => []];
    }
    return [
        'last_processed_date' => $data['last_processed_date'] ?? '00000000',
        'processed_files' => $data['processed_files'] ?? [],
    ];
}

function save_watermark(string $path, array $watermark) {
    file_put_contents($path, json_encode($watermark, JSON_PRETTY_PRINT), LOCK_EX);
}

// ── Logging ──

function log_error(string $log_path, string $message) {
    $ts = date('Y-m-d H:i:s');
    file_put_contents($log_path, "[$ts] $message\n", FILE_APPEND | LOCK_EX);
}

function cli_log(string $message) {
    if (php_sapi_name() === 'cli') {
        echo $message . "\n";
    }
}

// ── JSON file I/O with locking ──

function read_json(string $path) {
    if (!file_exists($path)) {
        return null;
    }
    $raw = file_get_contents($path);
    if ($raw === false) {
        return null;
    }
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}

function write_json(string $path, array $data) {
    file_put_contents(
        $path,
        json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
        LOCK_EX
    );
}

// ── Extract data from a single zip bundle ──

function extract_bundle(string $zip_path, string $error_log) {
    $zip = new ZipArchive();
    $flags = defined('ZipArchive::RDONLY') ? ZipArchive::RDONLY : 0;
    $result = $zip->open($zip_path, $flags);
    if ($result !== true) {
        log_error($error_log, "Corrupted zip (open failed code=$result): $zip_path");
        return null;
    }

    $bundle = [];

    // Read manifest.json
    $manifest_raw = $zip->getFromName('manifest.json');
    if ($manifest_raw === false) {
        log_error($error_log, "Missing manifest.json: $zip_path");
        $zip->close();
        return null;
    }
    $bundle['manifest'] = json_decode($manifest_raw, true);
    if (!is_array($bundle['manifest'])) {
        log_error($error_log, "Corrupted manifest.json: $zip_path");
        $zip->close();
        return null;
    }

    // Read audit.json
    $audit_raw = $zip->getFromName('audit.json');
    if ($audit_raw !== false) {
        $bundle['audit'] = json_decode($audit_raw, true);
    }

    // Read stress/trendline.jsonl (optional)
    $trendline_raw = $zip->getFromName('stress/trendline.jsonl');
    if ($trendline_raw !== false) {
        $bundle['trendline'] = [];
        foreach (explode("\n", trim($trendline_raw)) as $line) {
            $line = trim($line);
            if ($line !== '') {
                $entry = json_decode($line, true);
                if (is_array($entry)) {
                    $bundle['trendline'][] = $entry;
                }
            }
        }
    }

    // Read stress/latest_summary.json (optional)
    $summary_raw = $zip->getFromName('stress/latest_summary.json');
    if ($summary_raw !== false) {
        $bundle['stress_summary'] = json_decode($summary_raw, true);
    }

    $zip->close();
    return $bundle;
}

// ── Classify failure patterns from failure_tail text ──

function classify_failure(string $failure_tail): string {
    $lower = strtolower($failure_tail);
    if (strpos($lower, 'timeout') !== false) {
        return 'timeout';
    }
    if (strpos($lower, 'outofmemory') !== false || strpos($lower, 'out of memory') !== false
        || strpos($lower, 'cuda out of') !== false || strpos($lower, 'oom') !== false) {
        return 'oom';
    }
    if (strpos($lower, 'assertionerror') !== false || strpos($lower, 'assert') !== false) {
        return 'assertion';
    }
    if (strpos($lower, 'connectionerror') !== false || strpos($lower, 'connection refused') !== false
        || strpos($lower, 'network') !== false) {
        return 'network';
    }
    if (strpos($lower, 'invariant') !== false) {
        return 'invariant_violation';
    }
    if (strpos($lower, 'runtimeerror') !== false) {
        return 'runtime_error';
    }
    if (strpos($lower, 'typeerror') !== false || strpos($lower, 'attributeerror') !== false) {
        return 'type_error';
    }
    return 'unknown';
}

// ── Determine VRAM tier for capability matrix ──

function get_vram_tier(int $vram_mb): string {
    if ($vram_mb <= 0) return 'unknown';
    if ($vram_mb <= 6144) return 'tier_4gb';
    if ($vram_mb <= 10240) return 'tier_8gb';
    if ($vram_mb <= 14336) return 'tier_12gb';
    if ($vram_mb <= 18432) return 'tier_16gb';
    if ($vram_mb <= 26624) return 'tier_24gb';
    return 'tier_48gb';
}

// ── Update per-machine profile ──

function update_profile(string $profiles_dir, string $machine_id, array $bundle) {
    $path = $profiles_dir . '/' . $machine_id . '.json';
    $profile = read_json($path);

    if ($profile === null) {
        $profile = [
            'machine_id' => $machine_id,
            'hardware' => [],
            'usage' => [
                'models_used' => [],
                'avg_tokens_per_session' => 0,
                'avg_turn_duration_s' => 0,
                'avg_tok_per_sec' => 0,
                'total_sessions' => 0,
                'last_seen' => '',
                '_token_sum' => 0,
                '_duration_sum' => 0,
                '_turn_sum' => 0,
                '_tok_per_sec_sum' => 0,
                '_tok_per_sec_count' => 0,
            ],
            'failure_patterns' => [],
            'reliability_scores' => [],
        ];
    }

    $manifest = $bundle['manifest'] ?? [];
    $audit = $bundle['audit'] ?? [];
    $session = $audit['session'] ?? [];

    // Hardware — always overwrite with latest
    $hw = $manifest['hardware'] ?? [];
    if (!empty($hw)) {
        $profile['hardware'] = [
            'gpu_name' => $hw['gpu_name'] ?? ($profile['hardware']['gpu_name'] ?? 'unknown'),
            'vram_total_mb' => $hw['vram_total_mb'] ?? ($profile['hardware']['vram_total_mb'] ?? 0),
            'driver_version' => $hw['driver_version'] ?? ($profile['hardware']['driver_version'] ?? ''),
            'cuda_version' => $hw['cuda_version'] ?? ($profile['hardware']['cuda_version'] ?? ''),
            'cpu' => $hw['cpu'] ?? ($profile['hardware']['cpu'] ?? ''),
            'ram_mb' => $hw['ram_mb'] ?? ($profile['hardware']['ram_mb'] ?? 0),
            'os_version' => $hw['os_version'] ?? ($profile['hardware']['os_version'] ?? ''),
        ];
    }

    // Fleet metadata — role + master association
    $fleet_meta = $manifest['fleet'] ?? $audit['fleet'] ?? [];
    if (!empty($fleet_meta)) {
        $profile['fleet_role'] = $fleet_meta['role'] ?? ($profile['fleet_role'] ?? 'standalone');
        $profile['master_id'] = $fleet_meta['master_id'] ?? ($profile['master_id'] ?? null);
        $profile['account_id'] = $fleet_meta['account_id'] ?? ($profile['account_id'] ?? null);
        $profile['seat_id'] = $fleet_meta['seat_id'] ?? ($profile['seat_id'] ?? null);
    }

    // Usage — incremental merge
    $usage = &$profile['usage'];
    $usage['total_sessions'] = ($usage['total_sessions'] ?? 0) + 1;
    $usage['last_seen'] = $manifest['export_timestamp'] ?? date('c');

    // Model tracking
    $model = $session['model'] ?? ($manifest['model'] ?? '');
    if ($model !== '' && !in_array($model, $usage['models_used'] ?? [], true)) {
        $usage['models_used'][] = $model;
    }

    // Token/duration accumulation
    $session_tokens = ($session['tokens_in'] ?? 0) + ($session['tokens_out'] ?? 0);
    $session_duration = $session['duration_s'] ?? 0;
    $session_turns = $session['turns'] ?? 0;

    $usage['_token_sum'] = ($usage['_token_sum'] ?? 0) + $session_tokens;
    $usage['_duration_sum'] = ($usage['_duration_sum'] ?? 0) + $session_duration;
    $usage['_turn_sum'] = ($usage['_turn_sum'] ?? 0) + $session_turns;

    $total = $usage['total_sessions'];
    $usage['avg_tokens_per_session'] = $total > 0
        ? round($usage['_token_sum'] / $total, 1) : 0;
    $usage['avg_turn_duration_s'] = ($usage['_turn_sum'] > 0)
        ? round($usage['_duration_sum'] / $usage['_turn_sum'], 2) : 0;

    // tok/sec from stats subsystem
    $stats = $audit['stats'] ?? [];
    $tok_per_sec = $stats['avg_tok_per_sec'] ?? 0;
    if ($tok_per_sec > 0) {
        $usage['_tok_per_sec_sum'] = ($usage['_tok_per_sec_sum'] ?? 0) + $tok_per_sec;
        $usage['_tok_per_sec_count'] = ($usage['_tok_per_sec_count'] ?? 0) + 1;
        $usage['avg_tok_per_sec'] = round(
            $usage['_tok_per_sec_sum'] / $usage['_tok_per_sec_count'], 2
        );
    }

    // Reliability scores (keep last 30)
    $reliability = $audit['reliability'] ?? [];
    $rel_score = $reliability['score'] ?? null;
    if ($rel_score !== null) {
        $profile['reliability_scores'][] = round($rel_score, 1);
        $profile['reliability_scores'] = array_slice(
            $profile['reliability_scores'], -30
        );
    }

    // Failure patterns — extract from stress summary runs
    $stress_summary = $bundle['stress_summary'] ?? [];
    $runs = $stress_summary['runs'] ?? [];
    foreach ($runs as $run) {
        if (($run['success'] ?? true) === false && isset($run['failure_tail'])) {
            $type = classify_failure($run['failure_tail']);
            $now_ts = $run['timestamp'] ?? date('c');
            $found = false;
            foreach ($profile['failure_patterns'] as &$fp) {
                if ($fp['type'] === $type) {
                    $fp['count'] = ($fp['count'] ?? 0) + 1;
                    $fp['last_seen'] = $now_ts;
                    $found = true;
                    break;
                }
            }
            unset($fp);
            if (!$found) {
                $profile['failure_patterns'][] = [
                    'type' => $type,
                    'count' => 1,
                    'last_seen' => $now_ts,
                ];
            }
        }
    }

    write_json($path, $profile);
}

// ── Update per-machine test history ──

function update_test_history(string $profiles_dir, string $machine_id, array $bundle) {
    $path = $profiles_dir . '/' . $machine_id . '_tests.json';
    $history = read_json($path);
    if ($history === null) {
        $history = ['machine_id' => $machine_id, 'test_runs' => []];
    }

    $manifest = $bundle['manifest'] ?? [];
    $model = $manifest['model'] ?? '';

    // Extract from stress/latest_summary.json
    $stress_summary = $bundle['stress_summary'] ?? [];
    $runs = $stress_summary['runs'] ?? [];
    $summary_meta = $stress_summary['summary'] ?? [];
    $mode = $summary_meta['mode'] ?? 'unknown';

    foreach ($runs as $run) {
        $error_cats = [];
        $failures = $run['failures'] ?? [];
        foreach ($failures as $fail) {
            $scenario_name = $fail['scenario'] ?? 'unknown';
            $error_cats[] = $scenario_name;
        }
        if (isset($run['failure_tail'])) {
            $error_cats[] = classify_failure($run['failure_tail']);
        }

        $history['test_runs'][] = [
            'scenario' => $summary_meta['mode'] ?? 'unknown',
            'timestamp' => $run['timestamp'] ?? '',
            'passed' => $run['passed'] ?? 0,
            'failed' => $run['failed'] ?? 0,
            'duration_s' => $run['elapsed_s'] ?? 0,
            'turns' => ($run['passed'] ?? 0) + ($run['failed'] ?? 0) + ($run['skipped'] ?? 0),
            'invariant_pass' => $run['invariant_pass'] ?? false,
            'mode' => $mode,
            'model' => $summary_meta['model'] ?? $model,
            'error_categories' => array_unique($error_cats),
        ];
    }

    // Also extract from trendline entries
    $trendline = $bundle['trendline'] ?? [];
    foreach ($trendline as $entry) {
        $error_cats = [];
        $inv_failures = $entry['invariant_failures'] ?? [];
        foreach ($inv_failures as $fail) {
            if (isset($fail['scenario'])) {
                $error_cats[] = $fail['scenario'];
            }
        }

        $history['test_runs'][] = [
            'scenario' => $entry['mode'] ?? 'unknown',
            'timestamp' => $entry['timestamp'] ?? '',
            'passed' => $entry['passed'] ?? 0,
            'failed' => $entry['failed'] ?? 0,
            'duration_s' => $entry['duration_s'] ?? 0,
            'turns' => $entry['test_count'] ?? 0,
            'invariant_pass' => $entry['invariant_pass'] ?? false,
            'mode' => $entry['mode'] ?? 'unknown',
            'model' => $entry['model'] ?? $model,
            'error_categories' => array_unique($error_cats),
        ];
    }

    // Deduplicate by timestamp (trendline + summary may overlap)
    $seen = [];
    $deduped = [];
    foreach ($history['test_runs'] as $run) {
        $key = ($run['timestamp'] ?? '') . '|' . ($run['passed'] ?? 0) . '|' . ($run['failed'] ?? 0);
        if (!isset($seen[$key])) {
            $seen[$key] = true;
            $deduped[] = $run;
        }
    }
    $history['test_runs'] = $deduped;

    write_json($path, $history);
}

// ── Build fleet analytics from all profiles ──

function build_fleet_analytics(string $profiles_dir, string $data_dir) {
    $fleet = [
        'generated_at' => date('c'),
        'scenario_health' => [],
        'gpu_distribution' => [],
        'model_throughput' => [],
        'forge_version_distribution' => [],
        'time_of_day_histogram' => array_fill(0, 24, 0),
        'failure_heatmap' => [],
    ];

    // Scan all profile files
    $profile_files = glob($profiles_dir . '/*.json');
    $all_test_runs = [];

    foreach ($profile_files as $pf) {
        $basename = basename($pf, '.json');

        // Skip test history files
        if (substr($basename, -6) === '_tests') {
            // Load test history for fleet rollup
            $test_data = read_json($pf);
            if (is_array($test_data) && isset($test_data['test_runs'])) {
                foreach ($test_data['test_runs'] as $run) {
                    $run['_machine'] = substr($basename, 0, -6);
                    $all_test_runs[] = $run;
                }
            }
            continue;
        }

        $profile = read_json($pf);
        if (!is_array($profile)) {
            continue;
        }

        $hw = $profile['hardware'] ?? [];
        $usage = $profile['usage'] ?? [];

        // GPU distribution
        $gpu_name = $hw['gpu_name'] ?? 'unknown';
        if ($gpu_name !== 'unknown') {
            if (!isset($fleet['gpu_distribution'][$gpu_name])) {
                $fleet['gpu_distribution'][$gpu_name] = [
                    'count' => 0,
                    'avg_tok_per_sec' => 0,
                    'avg_vram_mb' => 0,
                    '_tok_sum' => 0,
                    '_vram_sum' => 0,
                ];
            }
            $fleet['gpu_distribution'][$gpu_name]['count']++;
            $tok = $usage['avg_tok_per_sec'] ?? 0;
            $vram = $hw['vram_total_mb'] ?? 0;
            $fleet['gpu_distribution'][$gpu_name]['_tok_sum'] += $tok;
            $fleet['gpu_distribution'][$gpu_name]['_vram_sum'] += $vram;
        }

        // Model throughput
        $models = $usage['models_used'] ?? [];
        foreach ($models as $m) {
            if (!isset($fleet['model_throughput'][$m])) {
                $fleet['model_throughput'][$m] = [
                    'avg_tok_per_sec' => 0,
                    'sessions' => 0,
                    '_tok_sum' => 0,
                ];
            }
            $fleet['model_throughput'][$m]['sessions'] += $usage['total_sessions'] ?? 0;
            $fleet['model_throughput'][$m]['_tok_sum'] += $usage['avg_tok_per_sec'] ?? 0;
        }

        // Time-of-day from last_seen
        $last_seen = $usage['last_seen'] ?? '';
        if ($last_seen !== '') {
            $hour = (int)date('G', strtotime($last_seen));
            if ($hour >= 0 && $hour < 24) {
                $fleet['time_of_day_histogram'][$hour] += ($usage['total_sessions'] ?? 1);
            }
        }
    }

    // Finalize GPU distribution averages
    foreach ($fleet['gpu_distribution'] as $gpu => &$gdata) {
        $c = $gdata['count'];
        if ($c > 0) {
            $gdata['avg_tok_per_sec'] = round($gdata['_tok_sum'] / $c, 2);
            $gdata['avg_vram_mb'] = round($gdata['_vram_sum'] / $c);
        }
        unset($gdata['_tok_sum'], $gdata['_vram_sum']);
    }
    unset($gdata);

    // Finalize model throughput averages
    foreach ($fleet['model_throughput'] as $m => &$mdata) {
        // _tok_sum is sum of per-machine avg_tok_per_sec; count = distinct machines using model
        // We approximate: number of entries contributing
        $entries = 0;
        foreach ($profile_files as $pf) {
            if (substr(basename($pf, '.json'), -6) === '_tests') continue;
            $p = read_json($pf);
            if (is_array($p) && in_array($m, $p['usage']['models_used'] ?? [], true)) {
                $entries++;
            }
        }
        $mdata['avg_tok_per_sec'] = $entries > 0
            ? round($mdata['_tok_sum'] / $entries, 2) : 0;
        unset($mdata['_tok_sum']);
    }
    unset($mdata);

    // Forge version distribution (from scanning date dirs for manifests)
    // We already have it in profiles — scan all zips is expensive, so use manifest data
    // collected during processing. For now, build from recent zips.
    $version_counts = [];
    $date_dirs = glob($data_dir . '/[0-9]*', GLOB_ONLYDIR);
    foreach ($date_dirs as $dd) {
        $zips = glob($dd . '/forge_*.zip');
        foreach (array_slice($zips, 0, 50) as $zp) {  // Sample to avoid slowness
            $z = new ZipArchive();
            $_zflags = defined('ZipArchive::RDONLY') ? ZipArchive::RDONLY : 0;
            if ($z->open($zp, $_zflags) === true) {
                $mraw = $z->getFromName('manifest.json');
                if ($mraw !== false) {
                    $mj = json_decode($mraw, true);
                    $ver = $mj['forge_version'] ?? 'unknown';
                    $version_counts[$ver] = ($version_counts[$ver] ?? 0) + 1;
                }
                $z->close();
            }
        }
    }
    $fleet['forge_version_distribution'] = $version_counts;

    // Scenario health from test runs
    $scenario_stats = [];
    foreach ($all_test_runs as $run) {
        $mode = $run['mode'] ?? 'unknown';
        if (!isset($scenario_stats[$mode])) {
            $scenario_stats[$mode] = [
                'total_runs' => 0,
                'total_pass' => 0,
                'pass_rate' => 0,
                'last_failure' => null,
            ];
        }
        $scenario_stats[$mode]['total_runs']++;
        if ($run['invariant_pass'] ?? false) {
            $scenario_stats[$mode]['total_pass']++;
        } else {
            $scenario_stats[$mode]['last_failure'] = $run['timestamp'] ?? null;
        }
    }
    foreach ($scenario_stats as $mode => &$ss) {
        $ss['pass_rate'] = $ss['total_runs'] > 0
            ? round($ss['total_pass'] / $ss['total_runs'], 4) : 0;
    }
    unset($ss);
    $fleet['scenario_health'] = $scenario_stats;

    // Failure heatmap: scenario x GPU tier -> pass rate
    $heatmap = [];
    foreach ($all_test_runs as $run) {
        $machine = $run['_machine'] ?? '';
        $mode = $run['mode'] ?? 'unknown';
        if ($machine === '') continue;

        // Look up GPU tier for this machine
        $mp = read_json($profiles_dir . '/' . $machine . '.json');
        $vram = ($mp['hardware']['vram_total_mb'] ?? 0);
        $tier = get_vram_tier((int)$vram);

        $key = $mode . '|' . $tier;
        if (!isset($heatmap[$key])) {
            $heatmap[$key] = ['scenario' => $mode, 'gpu_tier' => $tier,
                              'total' => 0, 'passed' => 0];
        }
        $heatmap[$key]['total']++;
        if ($run['invariant_pass'] ?? false) {
            $heatmap[$key]['passed']++;
        }
    }
    $fleet['failure_heatmap'] = [];
    foreach ($heatmap as $cell) {
        $cell['pass_rate'] = $cell['total'] > 0
            ? round($cell['passed'] / $cell['total'], 4) : 0;
        $fleet['failure_heatmap'][] = $cell;
    }

    write_json($data_dir . '/fleet_analytics.json', $fleet);
}

// ── Build capability matrix from test histories and profiles ──

function build_capability_matrix(string $profiles_dir, string $data_dir) {
    $tiers = [
        'tier_4gb' => [], 'tier_8gb' => [], 'tier_12gb' => [],
        'tier_16gb' => [], 'tier_24gb' => [], 'tier_48gb' => [],
    ];

    // Collect successful run durations/turns per tier per scenario
    // Structure: tier -> scenario -> [{turns, duration_s}]
    $tier_scenario_data = [];
    foreach (array_keys($tiers) as $t) {
        $tier_scenario_data[$t] = [];
    }

    $profile_files = glob($profiles_dir . '/*.json');
    foreach ($profile_files as $pf) {
        $basename = basename($pf, '.json');
        if (substr($basename, -6) !== '_tests') {
            continue;
        }
        $machine_id = substr($basename, 0, -6);

        // Get machine's VRAM tier
        $mp = read_json($profiles_dir . '/' . $machine_id . '.json');
        $vram = (int)($mp['hardware']['vram_total_mb'] ?? 0);
        $tier = get_vram_tier($vram);
        if ($tier === 'unknown') {
            continue;
        }

        $test_data = read_json($pf);
        if (!is_array($test_data)) {
            continue;
        }

        foreach ($test_data['test_runs'] ?? [] as $run) {
            $mode = $run['mode'] ?? 'unknown';
            if (!isset($tier_scenario_data[$tier][$mode])) {
                $tier_scenario_data[$tier][$mode] = [];
            }
            $tier_scenario_data[$tier][$mode][] = [
                'passed' => $run['invariant_pass'] ?? false,
                'turns' => $run['turns'] ?? 0,
                'duration_s' => $run['duration_s'] ?? 0,
            ];
        }
    }

    // Build matrix
    $matrix = ['generated_at' => date('c'), 'tiers' => []];

    foreach ($tier_scenario_data as $tier => $scenarios) {
        $matrix['tiers'][$tier] = [];
        foreach ($scenarios as $scenario => $runs) {
            $successful_runs = array_filter($runs, function($r) { return $r['passed']; });
            $successful_turns = array_map(function($r) { return $r['turns']; }, $successful_runs);
            $all_durations = array_map(function($r) { return $r['duration_s']; }, $runs);

            sort($successful_turns);
            sort($all_durations);

            // 25th percentile of successful run turns = max_safe_turns
            $max_safe_turns = 0;
            if (count($successful_turns) > 0) {
                $p25_idx = (int)floor(count($successful_turns) * 0.25);
                $max_safe_turns = $successful_turns[$p25_idx] ?? 0;
            }

            // Average duration
            $avg_duration = count($all_durations) > 0
                ? round(array_sum($all_durations) / count($all_durations), 2) : 0;

            // Timeout multiplier: ratio of P95 duration to median
            $timeout_mult = 1.0;
            if (count($all_durations) >= 3) {
                $median_idx = (int)floor(count($all_durations) * 0.5);
                $p95_idx = (int)floor(count($all_durations) * 0.95);
                $median = $all_durations[$median_idx];
                $p95 = $all_durations[$p95_idx];
                if ($median > 0) {
                    $timeout_mult = round($p95 / $median, 2);
                }
            }

            $matrix['tiers'][$tier][$scenario] = [
                'max_safe_turns' => $max_safe_turns,
                'avg_duration_s' => $avg_duration,
                'timeout_multiplier' => $timeout_mult,
                'sample_size' => count($runs),
                'pass_rate' => count($runs) > 0
                    ? round(count($successful_runs) / count($runs), 4) : 0,
            ];
        }
    }

    // Default tier fallback: weighted average across all tiers
    $default_scenarios = [];
    foreach ($tier_scenario_data as $tier => $scenarios) {
        foreach ($scenarios as $scenario => $runs) {
            if (!isset($default_scenarios[$scenario])) {
                $default_scenarios[$scenario] = ['turns' => [], 'durations' => [], 'total' => 0, 'passed' => 0];
            }
            foreach ($runs as $r) {
                $default_scenarios[$scenario]['total']++;
                if ($r['passed']) {
                    $default_scenarios[$scenario]['passed']++;
                    $default_scenarios[$scenario]['turns'][] = $r['turns'];
                }
                $default_scenarios[$scenario]['durations'][] = $r['duration_s'];
            }
        }
    }

    $matrix['tiers']['default_tier'] = [];
    foreach ($default_scenarios as $scenario => $agg) {
        sort($agg['turns']);
        sort($agg['durations']);
        $max_safe = 0;
        if (count($agg['turns']) > 0) {
            $p25_idx = (int)floor(count($agg['turns']) * 0.25);
            $max_safe = $agg['turns'][$p25_idx] ?? 0;
        }
        $avg_dur = count($agg['durations']) > 0
            ? round(array_sum($agg['durations']) / count($agg['durations']), 2) : 0;

        $matrix['tiers']['default_tier'][$scenario] = [
            'max_safe_turns' => $max_safe,
            'avg_duration_s' => $avg_dur,
            'timeout_multiplier' => 1.5,
            'sample_size' => $agg['total'],
            'pass_rate' => $agg['total'] > 0
                ? round($agg['passed'] / $agg['total'], 4) : 0,
        ];
    }

    write_json($data_dir . '/capability_matrix.json', $matrix);
}

// ── Extract machine_id from zip filename ──

function extract_machine_id(string $filename): string {
    // Format: forge_{machine_id}_{timestamp}.zip
    if (preg_match('/^forge_([a-f0-9]{8,16})_/', $filename, $m)) {
        return $m[1];
    }
    return '';
}

// ══════════════════════════════════════════════════════════════════════
//  MAIN PROCESSING LOOP
// ══════════════════════════════════════════════════════════════════════

cli_log("Forge Telemetry Analyzer");
cli_log("========================");

$watermark = load_watermark($WATERMARK_FILE);
$min_date = $watermark['last_processed_date'];
$processed = $watermark['processed_files'];

// Scan date directories >= watermark
$date_dirs = glob($DATA_DIR . '/[0-9]*', GLOB_ONLYDIR);
sort($date_dirs);

$new_bundles = 0;
$errors = 0;
$max_date_seen = $min_date;

foreach ($date_dirs as $date_dir) {
    $date_name = basename($date_dir);

    // Skip dates before watermark
    if ($date_name < $min_date) {
        continue;
    }

    $zips = glob($date_dir . '/forge_*.zip');
    $already_processed = $processed[$date_name] ?? [];

    foreach ($zips as $zip_path) {
        $filename = basename($zip_path);

        // Skip already-processed files
        if (in_array($filename, $already_processed, true)) {
            continue;
        }

        $machine_id = extract_machine_id($filename);
        if ($machine_id === '') {
            log_error($ERROR_LOG, "Cannot extract machine_id from: $filename");
            // Mark processed to avoid infinite retry
            $processed[$date_name][] = $filename;
            $errors++;
            continue;
        }

        cli_log("  Processing: $date_name/$filename (machine=$machine_id)");

        $bundle = extract_bundle($zip_path, $ERROR_LOG);
        if ($bundle === null) {
            // Corrupted — mark processed, no infinite retry
            $processed[$date_name][] = $filename;
            $errors++;
            continue;
        }

        // Update per-machine profile
        update_profile($PROFILES_DIR, $machine_id, $bundle);

        // Update per-machine test history (if stress data present)
        if (isset($bundle['trendline']) || isset($bundle['stress_summary'])) {
            update_test_history($PROFILES_DIR, $machine_id, $bundle);
        }

        // Mark processed
        $processed[$date_name][] = $filename;
        $new_bundles++;

        // Track max date
        if ($date_name > $max_date_seen) {
            $max_date_seen = $date_name;
        }
    }
}

// Update watermark
$watermark['last_processed_date'] = $max_date_seen;
$watermark['processed_files'] = $processed;
save_watermark($WATERMARK_FILE, $watermark);

cli_log("");
cli_log("Processed $new_bundles new bundles ($errors errors)");

// Rebuild fleet-wide data products
if ($new_bundles > 0 || !file_exists($DATA_DIR . '/fleet_analytics.json')) {
    cli_log("Building fleet analytics...");
    build_fleet_analytics($PROFILES_DIR, $DATA_DIR);

    cli_log("Building capability matrix...");
    build_capability_matrix($PROFILES_DIR, $DATA_DIR);

    cli_log("Done.");
} else {
    cli_log("No new data — skipping fleet rebuild.");
}

// HTTP response (if not CLI)
if (php_sapi_name() !== 'cli') {
    header('Content-Type: application/json');
    echo json_encode([
        'status' => 'ok',
        'processed' => $new_bundles,
        'errors' => $errors,
    ]);
}
