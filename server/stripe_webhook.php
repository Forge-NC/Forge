<?php
/**
 * Forge Stripe Webhook — Handles payment success events.
 *
 * Stripe sends POST to this endpoint after successful checkout.
 * Verifies webhook signature, then auto-generates a Master passport.
 *
 * Setup in Stripe Dashboard:
 *   Webhook URL: https://dirt-star.com/Forge/stripe_webhook.php
 *   Events: checkout.session.completed
 */

$STRIPE_CONFIG   = __DIR__ . '/data/stripe_config.json';
$TIERS_FILE      = __DIR__ . '/data/tiers_config.json';
$ORIGIN_KEY_FILE = __DIR__ . '/data/origin_key.json';
$MASTERS_DIR     = __DIR__ . '/data/masters';
$WEBHOOK_LOG     = __DIR__ . '/data/webhook_log.jsonl';

// ── Load config ──

$stripe_config = json_decode(file_get_contents($STRIPE_CONFIG), true);
$webhook_secret = $stripe_config['webhook_secret'] ?? '';

if (!$webhook_secret || strpos($webhook_secret, 'REPLACE_ME') !== false) {
    http_response_code(500);
    die('Webhook secret not configured');
}

// ── Verify Stripe signature ──

$payload   = file_get_contents('php://input');
$sig_header = $_SERVER['HTTP_STRIPE_SIGNATURE'] ?? '';

if (!$sig_header) {
    http_response_code(400);
    die('Missing Stripe-Signature header');
}

$verified = verify_stripe_signature($payload, $sig_header, $webhook_secret);
if (!$verified) {
    http_response_code(400);
    log_webhook('signature_failed', ['sig' => substr($sig_header, 0, 20)]);
    die('Invalid signature');
}

// ── Parse event ──

$event = json_decode($payload, true);
if (!$event) {
    http_response_code(400);
    die('Invalid JSON payload');
}

$event_type = $event['type'] ?? '';
log_webhook($event_type, ['event_id' => $event['id'] ?? '']);

// Only handle checkout completion
if ($event_type !== 'checkout.session.completed') {
    http_response_code(200);
    echo json_encode(['ok' => true, 'ignored' => true]);
    exit;
}

// ── Process checkout.session.completed ──

$session  = $event['data']['object'] ?? [];
$metadata = $session['metadata'] ?? [];
$tier     = $metadata['forge_tier'] ?? '';
$email    = $session['customer_email'] ?? $session['customer_details']['email'] ?? '';
$name     = $session['customer_details']['name'] ?? '';
$stripe_customer = $session['customer'] ?? '';

if (!$tier) {
    log_webhook('error', ['msg' => 'No forge_tier in metadata', 'session_id' => $session['id'] ?? '']);
    http_response_code(200);
    echo json_encode(['ok' => false, 'error' => 'No tier in metadata']);
    exit;
}

// ── Load tier config and origin key ──

$tiers = json_decode(file_get_contents($TIERS_FILE), true);
if (!isset($tiers[$tier])) {
    log_webhook('error', ['msg' => "Unknown tier: $tier"]);
    http_response_code(200);
    echo json_encode(['ok' => false, 'error' => "Unknown tier: $tier"]);
    exit;
}

$origin_data = json_decode(file_get_contents($ORIGIN_KEY_FILE), true);
$origin_key  = $origin_data['origin_key'] ?? '';
if (!$origin_key) {
    log_webhook('error', ['msg' => 'Origin key missing']);
    http_response_code(500);
    die('Origin key not configured');
}

// ── Generate Master passport ──

$tier_config = $tiers[$tier];
$account_id  = 'fg_' . bin2hex(random_bytes(12));
$passport_id = 'pp_' . bin2hex(random_bytes(8));
$customer_label = $name ?: $email ?: "stripe_$stripe_customer";

$passport = [
    'passport_id'    => $passport_id,
    'account_id'     => $account_id,
    'role'           => 'master',
    'tier'           => $tier,
    'customer_label' => $customer_label,
    'email'          => $email,
    'seat_count'     => $tier_config['seats'],
    'issued_at'      => time(),
    'issued_date'    => date('c'),
    'expires_at'     => 0,
    'stripe_session' => $session['id'] ?? '',
    'stripe_customer'=> $stripe_customer,
];

// Sign with Origin key
$clean = $passport;
unset($clean['origin_signature']);
ksort($clean);
$canonical = json_encode($clean, JSON_UNESCAPED_SLASHES);
$passport['origin_signature'] = hash_hmac('sha512', $canonical, $origin_key);

// Store master record
$master_record = [
    'passport'        => $passport,
    'activated'       => false,
    'master_mid'      => null,
    'activated_at'    => null,
    'last_seen'       => null,
    'telemetry_token' => null,
    'stripe_session'  => $session['id'] ?? '',
    'payment_status'  => $session['payment_status'] ?? '',
    'amount_paid'     => $session['amount_total'] ?? 0,
];

if (!is_dir($MASTERS_DIR)) mkdir($MASTERS_DIR, 0755, true);
$master_file = "$MASTERS_DIR/$account_id.json";
file_put_contents($master_file, json_encode($master_record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

log_webhook('master_created', [
    'account_id'  => $account_id,
    'passport_id' => $passport_id,
    'tier'        => $tier,
    'email'       => $email,
    'seats'       => $tier_config['seats'],
]);

// Return success
http_response_code(200);
echo json_encode([
    'ok'          => true,
    'account_id'  => $account_id,
    'passport_id' => $passport_id,
]);


// ── Helper functions ──

function verify_stripe_signature(string $payload, string $sig_header, string $secret): bool {
    // Parse Stripe-Signature header: t=timestamp,v1=signature
    $parts = [];
    foreach (explode(',', $sig_header) as $part) {
        $kv = explode('=', $part, 2);
        if (count($kv) === 2) {
            $parts[$kv[0]] = $kv[1];
        }
    }

    $timestamp = $parts['t'] ?? '';
    $signature = $parts['v1'] ?? '';

    if (!$timestamp || !$signature) return false;

    // Check timestamp freshness (5 min tolerance)
    if (abs(time() - (int)$timestamp) > 300) return false;

    // Compute expected signature
    $signed_payload = $timestamp . '.' . $payload;
    $expected = hash_hmac('sha256', $signed_payload, $secret);

    return hash_equals($expected, $signature);
}

function log_webhook(string $event, array $data = []) {
    global $WEBHOOK_LOG;
    $entry = array_merge([
        'timestamp' => date('c'),
        'event'     => $event,
    ], $data);
    file_put_contents($WEBHOOK_LOG, json_encode($entry) . "\n", FILE_APPEND | LOCK_EX);
}
