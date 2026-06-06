<?php
/**
 * Oracle parity test runner — reads JSON cases from stdin, scores each via
 * forge_oracle_score_scenario(), writes JSON results to stdout. Driven by
 * tests/test_oracle_parity.py — not a standalone tool.
 */
declare(strict_types=1);
require_once __DIR__ . '/../server/includes/external_runner_scoring.php';

$payload = stream_get_contents(STDIN);
$cases = json_decode($payload, true);
if (!is_array($cases)) {
    fwrite(STDERR, "bad json on stdin\n");
    exit(2);
}

$out = [];
foreach ($cases as $c) {
    $verdict = forge_oracle_score_scenario(
        $c['scenario'] ?? [],
        (string)($c['response'] ?? '')
    );
    $out[] = [
        'name'   => $c['name'] ?? '',
        'passed' => $verdict['passed'],
        'reason' => $verdict['reason'],
    ];
}
echo json_encode($out, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
