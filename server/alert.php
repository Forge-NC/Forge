<?php
/**
 * Forge Fleet SLA Alerting
 *
 * Runs after analyzer.php (cron). Checks fleet health metrics against
 * SLA thresholds and sends notifications via configurable webhooks.
 *
 * Checks:
 *   - Fleet pass rate < 90%
 *   - Any machine offline > 3 days
 *   - Any scenario failing on > 50% of machines
 *
 * Supports: Discord webhook, Slack incoming webhook, email via mail()
 *
 * Config: data/alert_config.json
 *   {
 *     "enabled": false,
 *     "webhook_url": "",
 *     "webhook_type": "discord|slack|email",
 *     "email_to": "",
 *     "thresholds": {
 *       "fleet_pass_rate_min": 0.90,
 *       "machine_offline_days": 3,
 *       "scenario_fail_machine_pct": 0.50
 *     }
 *   }
 *
 * Invocation: php alert.php (cron, after analyzer)
 */

// CLI only — block web access
if (php_sapi_name() !== 'cli') {
    http_response_code(403);
    exit;
}

$DATA_DIR = __DIR__ . '/data';
$PROFILES_DIR = $DATA_DIR . '/profiles';
$FLEET_FILE = $DATA_DIR . '/fleet_analytics.json';
$CONFIG_FILE = $DATA_DIR . '/alert_config.json';
$ALERT_LOG = $DATA_DIR . '/alert_log.jsonl';

// -- Load config --
if (!file_exists($CONFIG_FILE)) {
    // Create default config
    $default = [
        'enabled' => false,
        'webhook_url' => '',
        'webhook_type' => 'discord',
        'email_to' => '',
        'thresholds' => [
            'fleet_pass_rate_min' => 0.90,
            'machine_offline_days' => 3,
            'scenario_fail_machine_pct' => 0.50,
        ],
    ];
    file_put_contents($CONFIG_FILE,
        json_encode($default, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
        LOCK_EX);
    echo "Created default config at $CONFIG_FILE\n";
    echo "Set 'enabled: true' and configure webhook to activate.\n";
    exit(0);
}

$config = json_decode(file_get_contents($CONFIG_FILE), true);
if (!$config || empty($config['enabled'])) {
    echo "Alerting disabled. Set 'enabled: true' in $CONFIG_FILE\n";
    exit(0);
}

$thresholds = $config['thresholds'] ?? [];
$alerts = [];

// -- Check fleet pass rate --
if (file_exists($FLEET_FILE)) {
    $fleet = json_decode(file_get_contents($FLEET_FILE), true);
    $pass_rate = $fleet['pass_rate_7d'] ?? null;
    $min_rate = $thresholds['fleet_pass_rate_min'] ?? 0.90;

    if ($pass_rate !== null && $pass_rate < $min_rate) {
        $pct = round($pass_rate * 100, 1);
        $target = round($min_rate * 100, 1);
        $alerts[] = [
            'type' => 'fleet_pass_rate',
            'message' => "Fleet pass rate {$pct}% is below target {$target}%",
            'severity' => 'warning',
        ];
    }

    // -- Check scenario health --
    $scenario_health = $fleet['scenario_health'] ?? [];
    $fail_pct_threshold = $thresholds['scenario_fail_machine_pct'] ?? 0.50;
    foreach ($scenario_health as $name => $health) {
        $rate = $health['pass_rate'] ?? 1.0;
        if ($rate < (1.0 - $fail_pct_threshold)) {
            $pct = round($rate * 100, 1);
            $alerts[] = [
                'type' => 'scenario_failing',
                'message' => "Scenario '{$name}' pass rate: {$pct}% (failing on majority of machines)",
                'severity' => 'critical',
            ];
        }
    }
}

// -- Check machine offline --
$offline_days = $thresholds['machine_offline_days'] ?? 3;
$cutoff = time() - ($offline_days * 86400);

if (is_dir($PROFILES_DIR)) {
    foreach (glob("$PROFILES_DIR/*.json") as $f) {
        if (strpos(basename($f), '_tests') !== false) continue;
        $profile = json_decode(file_get_contents($f), true);
        if (!$profile) continue;

        $last_seen = strtotime($profile['last_seen'] ?? '2000-01-01');
        $machine_id = $profile['machine_id'] ?? basename($f, '.json');
        $label = $profile['machine_label'] ?? '';
        $display = $label ? "$label ($machine_id)" : $machine_id;

        // Only alert if machine was previously active (has > 2 sessions)
        if (($profile['total_sessions'] ?? 0) > 2 && $last_seen < $cutoff) {
            $days_ago = round((time() - $last_seen) / 86400);
            $alerts[] = [
                'type' => 'machine_offline',
                'message' => "Machine '{$display}' offline for {$days_ago} days",
                'severity' => 'info',
            ];
        }
    }
}

// -- Send alerts --
if (empty($alerts)) {
    echo "All clear — no alerts triggered.\n";
    _log_alert('check_passed', 'No alerts triggered');
    exit(0);
}

echo count($alerts) . " alert(s) triggered:\n";
foreach ($alerts as $a) {
    echo "  [{$a['severity']}] {$a['message']}\n";
}

// Build notification payload
$title = "Forge Fleet Alert — " . count($alerts) . " issue(s)";
$body = "";
foreach ($alerts as $a) {
    $icon = $a['severity'] === 'critical' ? '🔴' : ($a['severity'] === 'warning' ? '🟡' : '🔵');
    $body .= "$icon {$a['message']}\n";
}
$body .= "\nGenerated: " . date('Y-m-d H:i:s T');

$webhook_type = $config['webhook_type'] ?? 'discord';
$webhook_url = $config['webhook_url'] ?? '';

if ($webhook_url) {
    $success = _send_webhook($webhook_type, $webhook_url, $title, $body);
    echo $success ? "Webhook sent.\n" : "Webhook failed.\n";
}

if (!empty($config['email_to'])) {
    $sent = @mail($config['email_to'], $title, $body,
        "From: forge-alerts@noreply.local\r\n");
    echo $sent ? "Email sent.\n" : "Email failed.\n";
}

_log_alert('alerts_fired', json_encode($alerts));


// ── Helpers ──

function _send_webhook(string $type, string $url, string $title, string $body): bool {
    if ($type === 'discord') {
        $payload = json_encode([
            'embeds' => [[
                'title' => $title,
                'description' => $body,
                'color' => 16007990,  // red-ish
            ]],
        ]);
    } elseif ($type === 'slack') {
        $payload = json_encode([
            'text' => "*{$title}*\n```\n{$body}\n```",
        ]);
    } else {
        return false;
    }

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $payload,
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    return $code >= 200 && $code < 300;
}

function _log_alert(string $action, string $detail) {
    global $ALERT_LOG;
    $entry = json_encode([
        'timestamp' => date('c'),
        'action' => $action,
        'detail' => $detail,
    ]);
    file_put_contents($ALERT_LOG, $entry . "\n", FILE_APPEND | LOCK_EX);
}
