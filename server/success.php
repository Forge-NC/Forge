<?php
/**
 * Forge Purchase Success — Post-purchase landing page.
 *
 * Shows passport download and activation instructions after
 * successful Stripe checkout.
 */

$STRIPE_CONFIG = __DIR__ . '/data/stripe_config.json';
$MASTERS_DIR   = __DIR__ . '/data/masters';

$session_id = $_GET['session_id'] ?? '';

// ── Look up master by Stripe session ID ──

$master = null;
$passport = null;
$account_id = null;

if ($session_id) {
    foreach (glob("$MASTERS_DIR/*.json") as $file) {
        $data = json_decode(file_get_contents($file), true);
        if ($data && ($data['stripe_session'] ?? '') === $session_id) {
            $master = $data;
            $passport = $data['passport'] ?? [];
            $account_id = $passport['account_id'] ?? basename($file, '.json');
            break;
        }
    }
}

$found = $master !== null;
$tier_label = $passport['tier'] ?? '';
$seats = $passport['seat_count'] ?? 1;
$label = $passport['customer_label'] ?? '';

?><!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forge — Purchase Complete</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: #0a0e17;
            color: #c8d6e5;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            max-width: 640px;
            width: 90%;
            background: #141a2a;
            border: 1px solid #1e2a3a;
            border-radius: 12px;
            padding: 40px;
        }
        .logo {
            font-size: 2em;
            font-weight: 700;
            color: #00d4ff;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #6b7f99;
            margin-bottom: 32px;
        }
        .success-badge {
            display: inline-block;
            background: #0a2e1a;
            color: #34d399;
            border: 1px solid #166534;
            padding: 6px 16px;
            border-radius: 20px;
            font-weight: 600;
            margin-bottom: 24px;
        }
        .error-badge {
            display: inline-block;
            background: #2e0a0a;
            color: #f87171;
            border: 1px solid #7f1d1d;
            padding: 6px 16px;
            border-radius: 20px;
            font-weight: 600;
            margin-bottom: 24px;
        }
        .info-grid {
            display: grid;
            grid-template-columns: 120px 1fr;
            gap: 8px;
            margin-bottom: 28px;
        }
        .info-label { color: #6b7f99; }
        .info-value { color: #e2e8f0; font-weight: 500; }
        .download-btn {
            display: inline-block;
            background: #00d4ff;
            color: #0a0e17;
            padding: 12px 28px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 700;
            font-size: 1.05em;
            transition: background 0.2s;
            margin-bottom: 28px;
        }
        .download-btn:hover { background: #00b8e6; }
        .steps {
            background: #0d1320;
            border: 1px solid #1e2a3a;
            border-radius: 8px;
            padding: 20px;
        }
        .steps h3 {
            color: #00d4ff;
            margin-bottom: 12px;
        }
        .steps ol {
            padding-left: 20px;
            line-height: 1.8;
        }
        .steps code {
            background: #1a2332;
            padding: 2px 8px;
            border-radius: 4px;
            color: #34d399;
            font-size: 0.95em;
        }
        .note {
            margin-top: 20px;
            color: #6b7f99;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Forge</div>
        <div class="subtitle">Local AI Coding Assistant</div>

        <?php if ($found): ?>
            <div class="success-badge">Purchase Complete</div>

            <div class="info-grid">
                <span class="info-label">Name</span>
                <span class="info-value"><?= htmlspecialchars($label) ?></span>

                <span class="info-label">Tier</span>
                <span class="info-value"><?= htmlspecialchars(ucfirst($tier_label)) ?></span>

                <span class="info-label">Seats</span>
                <span class="info-value"><?= (int)$seats ?> (1 master + <?= max(0, (int)$seats - 1) ?> puppets)</span>

                <span class="info-label">Account ID</span>
                <span class="info-value" style="font-family: monospace; font-size: 0.9em;">
                    <?= htmlspecialchars($account_id) ?>
                </span>
            </div>

            <a href="passport_download.php?id=<?= urlencode($account_id) ?>&session=<?= urlencode($session_id) ?>"
               class="download-btn">
                Download Passport File
            </a>

            <div class="steps">
                <h3>Activation Steps</h3>
                <ol>
                    <li>Download your passport file above</li>
                    <li>Open Forge on your machine</li>
                    <li>Run <code>/puppet activate passport.json</code></li>
                    <li>Forge validates with our server and activates your Master license</li>
                    <li>Use <code>/puppet generate DevBox</code> to create puppet licenses for your other machines</li>
                </ol>
            </div>

            <p class="note">
                Your passport file contains your license credentials. Keep it safe.
                You can re-download it from the link in your confirmation email.
            </p>

        <?php else: ?>
            <div class="error-badge">Session Not Found</div>
            <p>Could not find a purchase matching this session. This may happen if:</p>
            <ul style="padding-left: 20px; margin-top: 12px; line-height: 1.8;">
                <li>The payment is still processing (wait a moment and refresh)</li>
                <li>The session link has expired</li>
                <li>There was a payment issue</li>
            </ul>
            <p class="note">
                If you completed payment but see this message, contact support with your
                Stripe receipt email.
            </p>
        <?php endif; ?>
    </div>
</body>
</html>
