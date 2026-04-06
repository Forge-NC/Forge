<?php
/**
 * Drop-in snippet for the Forge server.
 *
 * Call forge_notify_discord() after an audit report is verified/certified.
 * This sends a signed POST to the Discord bot's webhook listener.
 *
 * Add to assurance_verify.php after a successful submit or certify action:
 *     require_once __DIR__ . '/discord_notify.php';  // or inline this
 *     forge_notify_discord($report_data);
 */

define('DISCORD_BOT_WEBHOOK_URL', 'http://YOUR_BOT_HOST:8443/webhook/audit-complete');
define('DISCORD_WEBHOOK_SECRET', 'generate-a-random-secret-here');  // must match .env

function forge_notify_discord(array $report): void {
    $payload = json_encode([
        'run_id'              => $report['run_id'] ?? '',
        'model'               => $report['model'] ?? 'Unknown',
        'pass_rate'           => $report['pass_rate'] ?? 0,
        'scenarios_run'       => $report['scenarios_run'] ?? 0,
        'category_pass_rates' => $report['category_pass_rates'] ?? [],
        'verified_at'         => time(),
    ]);

    $signature = hash_hmac('sha256', $payload, DISCORD_WEBHOOK_SECRET);

    $ch = curl_init(DISCORD_BOT_WEBHOOK_URL);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            'X-Forge-Signature: ' . $signature,
        ],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 5,
        CURLOPT_CONNECTTIMEOUT => 3,
    ]);
    $result = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($code !== 200) {
        error_log("Discord webhook failed (HTTP $code): $result");
    }
}
