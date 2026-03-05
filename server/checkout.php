<?php
/**
 * Forge Checkout — Creates Stripe Checkout Sessions.
 *
 * Usage: GET checkout.php?tier=pro
 *        GET checkout.php?tier=pro&billing=monthly
 *        Redirects to Stripe-hosted checkout page.
 *
 * On success, Stripe redirects to success.php with session_id.
 * On cancel, Stripe redirects back to cancel_url.
 *
 * Requires: Stripe PHP SDK (or uses cURL fallback below).
 */

$STRIPE_CONFIG = __DIR__ . '/data/stripe_config.json';
$TIERS_FILE    = __DIR__ . '/data/tiers_config.json';

// ── Load config ──

$stripe_ready = true;
$stripe = null;

if (!file_exists($STRIPE_CONFIG)) {
    $stripe_ready = false;
} else {
    $stripe = json_decode(file_get_contents($STRIPE_CONFIG), true);
    if (!$stripe) {
        $stripe_ready = false;
    } else {
        $secret_key = $stripe['secret_key'] ?? '';
        if (!$secret_key || strpos($secret_key, 'REPLACE_ME') !== false) {
            $stripe_ready = false;
        }
    }
}

$tiers = file_exists($TIERS_FILE) ? json_decode(file_get_contents($TIERS_FILE), true) : null;

// ── If Stripe isn't ready, show a branded "Coming Soon" page ──

if (!$stripe_ready) {
    $tier = $_GET['tier'] ?? '';
    $tier_label = '';
    if ($tiers && isset($tiers[$tier])) {
        $tier_label = $tiers[$tier]['label'] ?? ucfirst($tier);
    }

    // ── Waitlist signup handler ──
    $waitlist_msg = '';
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['waitlist_email'])) {
        $email = filter_var(trim($_POST['waitlist_email']), FILTER_VALIDATE_EMAIL);
        if ($email) {
            $waitlist_file = __DIR__ . '/data/waitlist.json';
            $list = file_exists($waitlist_file) ? json_decode(file_get_contents($waitlist_file), true) : [];
            if (!is_array($list)) $list = [];
            // Check for duplicate
            $already = false;
            foreach ($list as $entry) {
                if (isset($entry['email']) && strtolower($entry['email']) === strtolower($email)) {
                    $already = true;
                    break;
                }
            }
            if ($already) {
                $waitlist_msg = 'already';
            } else {
                $list[] = [
                    'email' => $email,
                    'tier'  => $tier ?: null,
                    'date'  => date('Y-m-d H:i:s'),
                ];
                file_put_contents($waitlist_file, json_encode($list, JSON_PRETTY_PRINT), LOCK_EX);
                $waitlist_msg = 'success';
            }
        } else {
            $waitlist_msg = 'invalid';
        }
    }
    ?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forge — Checkout Coming Soon</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            background:#0a0e17;color:#e0e8f0;min-height:100vh;
            display:flex;align-items:center;justify-content:center;
            background-image:radial-gradient(ellipse at 50% 0%,rgba(0,212,255,0.08) 0%,transparent 60%);
        }
        .checkout-card{
            text-align:center;max-width:520px;padding:48px 40px;
            background:rgba(20,28,43,0.85);border:1px solid rgba(0,212,255,0.15);
            border-radius:16px;backdrop-filter:blur(12px);
            box-shadow:0 0 60px rgba(0,212,255,0.06),0 24px 48px rgba(0,0,0,0.4);
        }
        .forge-logo{
            font-size:2.2rem;font-weight:800;letter-spacing:2px;
            background:linear-gradient(135deg,#00d4ff,#00ff88);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            background-clip:text;margin-bottom:8px;
        }
        .checkout-card h2{
            font-size:1.4rem;font-weight:600;margin:20px 0 12px;color:#fff;
        }
        .checkout-card p{
            font-size:1rem;line-height:1.7;color:#8892a4;margin-bottom:16px;
        }
        .tier-badge{
            display:inline-block;padding:6px 18px;border-radius:20px;font-size:0.85rem;
            font-weight:600;letter-spacing:1px;text-transform:uppercase;
            background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.25);
            color:#00d4ff;margin-bottom:24px;
        }
        .email-hint{
            font-size:0.85rem;color:#556;margin-top:24px;
            padding-top:20px;border-top:1px solid rgba(255,255,255,0.06);
        }
        .email-hint a{color:#00d4ff;text-decoration:none}
        .email-hint a:hover{text-decoration:underline}
        .back-link{
            display:inline-block;margin-top:20px;padding:10px 28px;
            border-radius:8px;font-size:0.9rem;font-weight:600;
            color:#00d4ff;border:1px solid rgba(0,212,255,0.3);
            text-decoration:none;transition:all 0.2s;
        }
        .back-link:hover{background:rgba(0,212,255,0.1);border-color:#00d4ff}
        .pulse-dot{
            display:inline-block;width:8px;height:8px;border-radius:50%;
            background:#00ff88;margin-right:8px;vertical-align:middle;
            animation:dotPulse 2s ease-in-out infinite;
        }
        @keyframes dotPulse{
            0%,100%{opacity:1;transform:scale(1)}
            50%{opacity:0.4;transform:scale(0.8)}
        }
        .waitlist-form{
            display:flex;gap:8px;margin:0 auto;max-width:380px;
        }
        .waitlist-form input[type="email"]{
            flex:1;padding:10px 14px;border-radius:8px;border:1px solid rgba(0,212,255,0.25);
            background:rgba(10,14,23,0.6);color:#e0e8f0;font-size:0.9rem;
            outline:none;transition:border-color 0.2s;
        }
        .waitlist-form input[type="email"]:focus{border-color:#00d4ff}
        .waitlist-form input[type="email"]::placeholder{color:#556}
        .waitlist-form button{
            padding:10px 20px;border-radius:8px;border:none;
            background:linear-gradient(135deg,#00d4ff,#00ff88);color:#0a0e17;
            font-weight:700;font-size:0.85rem;cursor:pointer;white-space:nowrap;
            transition:opacity 0.2s;
        }
        .waitlist-form button:hover{opacity:0.85}
        .waitlist-msg{
            font-size:0.85rem;margin-top:10px;
        }
        .waitlist-msg.success{color:#00ff88}
        .waitlist-msg.info{color:#00d4ff}
        .waitlist-msg.error{color:#f87171}
    </style>
</head>
<body>
    <div class="checkout-card">
        <div class="forge-logo">FORGE</div>
        <?php if ($tier_label): ?>
            <span class="tier-badge"><?php echo htmlspecialchars($tier_label); ?> License</span>
        <?php endif; ?>
        <h2><span class="pulse-dot"></span>Payments Launching Soon</h2>
        <p>
            We're putting the finishing touches on our secure payment system.
            Forge licenses will be available for purchase very shortly.
        </p>
        <?php if ($waitlist_msg === 'success'): ?>
            <p class="waitlist-msg success">You're on the list. We'll email you the moment checkout goes live.</p>
        <?php elseif ($waitlist_msg === 'already'): ?>
            <p class="waitlist-msg info">You're already on the waitlist. We'll be in touch soon.</p>
        <?php else: ?>
            <p>Drop your email to get notified the moment checkout goes live &mdash; and lock in early-adopter pricing.</p>
            <form class="waitlist-form" method="POST" action="">
                <input type="email" name="waitlist_email" placeholder="you@example.com" required>
                <?php if ($tier): ?><input type="hidden" name="tier" value="<?php echo htmlspecialchars($tier); ?>"><?php endif; ?>
                <button type="submit">Join Waitlist</button>
            </form>
            <?php if ($waitlist_msg === 'invalid'): ?>
                <p class="waitlist-msg error">Please enter a valid email address.</p>
            <?php endif; ?>
        <?php endif; ?>
        <a href="/Forge/" class="back-link">&larr; Back to Forge</a>
        <div class="email-hint">
            Questions? Reach out at <a href="mailto:admin@dirt-star.com">admin@dirt-star.com</a>
        </div>
    </div>
</body>
</html>
    <?php
    exit;
}

// ── Stripe is configured — proceed with checkout ──

$secret_key  = $stripe['secret_key'];
$success_url = $stripe['success_url'] ?? '';
$cancel_url  = $stripe['cancel_url'] ?? '';

// ── Validate tier + billing ──

$tier = $_GET['tier'] ?? '';
$billing = $_GET['billing'] ?? 'onetime';

if (!$tier || !isset($tiers[$tier])) {
    http_response_code(400);
    die('Invalid tier. Available: ' . implode(', ', array_keys($tiers)));
}

$tier_config = $tiers[$tier];
$is_monthly = ($billing === 'monthly');

// Determine which price to use
if ($is_monthly) {
    $price_id = $tier_config['stripe_price_id_monthly'] ?? null;
    $price_cents = $tier_config['price_monthly_cents'] ?? 0;
    $price_display = $tier_config['price_monthly_display'] ?? '';
} else {
    $price_id = $tier_config['stripe_price_id'] ?? null;
    $price_cents = $tier_config['price_cents'] ?? 0;
    $price_display = $tier_config['price_display'] ?? '';
}

if (empty($price_id) && $price_cents <= 0) {
    http_response_code(400);
    die('This tier is free — no purchase needed.');
}

$stripe_mode = $is_monthly ? 'subscription' : 'payment';

// ── Create Stripe Checkout Session via cURL ──

$line_items = [];

if (!empty($price_id)) {
    // Use pre-configured Stripe Price
    $line_items[] = [
        'price'    => $price_id,
        'quantity' => 1,
    ];
} else {
    // Create ad-hoc price from tier config
    $price_data = [
        'currency'     => 'usd',
        'unit_amount'  => $price_cents,
        'product_data' => [
            'name'        => "Forge {$tier_config['label']} License",
            'description' => "{$tier_config['seats']} seat(s) — {$price_display}",
        ],
    ];
    if ($is_monthly) {
        $price_data['recurring'] = ['interval' => 'month'];
    }
    $line_items[] = [
        'price_data' => $price_data,
        'quantity'   => 1,
    ];
}

$checkout_data = [
    'payment_method_types' => ['card'],
    'line_items'           => $line_items,
    'mode'                 => $stripe_mode,
    'success_url'          => $success_url . '?session_id={CHECKOUT_SESSION_ID}',
    'cancel_url'           => $cancel_url,
    'metadata'             => [
        'forge_tier' => $tier,
        'billing'    => $billing,
        'seats'      => (string)$tier_config['seats'],
    ],
];

$ch = curl_init('https://api.stripe.com/v1/checkout/sessions');
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER     => [
        'Authorization: Bearer ' . $secret_key,
        'Content-Type: application/x-www-form-urlencoded',
    ],
    CURLOPT_POSTFIELDS     => http_build_query_nested($checkout_data),
    CURLOPT_TIMEOUT        => 30,
]);

$response = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($http_code !== 200) {
    $err = json_decode($response, true);
    $msg = $err['error']['message'] ?? 'Unknown Stripe error';
    http_response_code(502);
    die("Payment error: $msg");
}

$session = json_decode($response, true);
$checkout_url = $session['url'] ?? '';

if (!$checkout_url) {
    http_response_code(502);
    die('Failed to create checkout session.');
}

// Redirect to Stripe Checkout
header("Location: $checkout_url");
exit;


// ── Helper: Build nested query string for Stripe API ──

function http_build_query_nested(array $data, string $prefix = ''): string {
    $parts = [];
    foreach ($data as $key => $value) {
        $full_key = $prefix ? "{$prefix}[{$key}]" : $key;
        if (is_array($value)) {
            $parts[] = http_build_query_nested($value, $full_key);
        } else {
            $parts[] = urlencode($full_key) . '=' . urlencode((string)$value);
        }
    }
    return implode('&', $parts);
}
