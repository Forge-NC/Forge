<?php
/**
 * Forge — Waitlist
 *
 * Collects email signups. Data is AES-256-GCM encrypted at rest.
 * Attempts email notification to admin if mail() is available.
 */

$waitlist_file = __DIR__ . '/data/waitlist.enc';
$key_file = __DIR__ . '/data/waitlist_key.bin';
$success = false;
$error = '';
$already = false;
$count = 0;

// ── CSRF token ──
session_start();
if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}
$csrf_token = $_SESSION['csrf_token'];

// ── Rate limiting (10 submissions per IP per 10 min) ──
$_wl_rate_dir = __DIR__ . '/rate_limits';
if (!is_dir($_wl_rate_dir)) @mkdir($_wl_rate_dir, 0755, true);
$_wl_ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
$_wl_rate_file = $_wl_rate_dir . '/wl_' . md5($_wl_ip) . '.json';
$_wl_now = time();

// ── Encryption helpers (AES-256-GCM) ──

function wl_get_key($key_file) {
    if (file_exists($key_file)) {
        return file_get_contents($key_file);
    }
    // Generate a new 256-bit key on first use
    $key = random_bytes(32);
    $dir = dirname($key_file);
    if (!is_dir($dir)) mkdir($dir, 0755, true);
    file_put_contents($key_file, $key);
    chmod($key_file, 0600);
    return $key;
}

function wl_encrypt($plaintext, $key) {
    $iv = random_bytes(12); // 96-bit nonce for GCM
    $tag = '';
    $cipher = openssl_encrypt($plaintext, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag, '', 16);
    if ($cipher === false) return false;
    // Format: iv (12) + tag (16) + ciphertext
    return base64_encode($iv . $tag . $cipher);
}

function wl_decrypt($encoded, $key) {
    $raw = base64_decode($encoded);
    if ($raw === false || strlen($raw) < 28) return false;
    $iv = substr($raw, 0, 12);
    $tag = substr($raw, 12, 16);
    $cipher = substr($raw, 28);
    $plain = openssl_decrypt($cipher, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
    return $plain;
}

function wl_load($waitlist_file, $key) {
    if (!file_exists($waitlist_file)) return array();
    $encoded = file_get_contents($waitlist_file);
    if (empty($encoded)) return array();
    $json = wl_decrypt(trim($encoded), $key);
    if ($json === false) return array();
    $data = json_decode($json, true);
    return is_array($data) ? $data : array();
}

function wl_save($waitlist_file, $data, $key) {
    $json = json_encode($data, JSON_PRETTY_PRINT);
    $encrypted = wl_encrypt($json, $key);
    if ($encrypted === false) return false;
    $dir = dirname($waitlist_file);
    if (!is_dir($dir)) mkdir($dir, 0755, true);
    return file_put_contents($waitlist_file, $encrypted, LOCK_EX);
}

// ── Load existing waitlist ──

$enc_key = wl_get_key($key_file);
$waitlist = wl_load($waitlist_file, $enc_key);
$count = count($waitlist);

// ── Handle form submission ──

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['email'])) {
    // CSRF check
    $submitted_csrf = $_POST['_csrf'] ?? '';
    if (!hash_equals($csrf_token, $submitted_csrf)) {
        $error = 'Session expired. Please try again.';
    }

    // Rate limit check
    if (!$error) {
        $_wl_rate = file_exists($_wl_rate_file) ? json_decode(file_get_contents($_wl_rate_file), true) : null;
        if ($_wl_rate && ($_wl_now - ($_wl_rate['window_start'] ?? 0)) < 600) {
            $_wl_rate['count'] = ($_wl_rate['count'] ?? 0) + 1;
            if ($_wl_rate['count'] > 10) {
                $error = 'Too many submissions. Please try again later.';
            }
        } else {
            $_wl_rate = ['window_start' => $_wl_now, 'count' => 1];
        }
        file_put_contents($_wl_rate_file, json_encode($_wl_rate));
    }

    $email = trim($_POST['email']);

    if (!$error && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $error = 'Please enter a valid email address.';
    }

    if (!$error) {
        // Check for duplicates
        $found = false;
        foreach ($waitlist as $entry) {
            if (strtolower($entry['email']) === strtolower($email)) {
                $found = true;
                break;
            }
        }

        if ($found) {
            $already = true;
        } else {
            $waitlist[] = array(
                'email' => $email,
                'date'  => date('Y-m-d H:i:s'),
                'ip_hash' => substr(hash('sha512', ($_SERVER['REMOTE_ADDR'] ?? '') . 'forge_wl_salt'), 0, 16),
            );

            // Save encrypted with file locking
            wl_save($waitlist_file, $waitlist, $enc_key);

            $count = count($waitlist);
            $success = true;

            // Try to notify admin (best-effort, don't fail if mail is broken)
            @mail(
                'admin@dirt-star.com',
                'Forge Waitlist Signup #' . $count,
                "New waitlist signup:\n\nDate: " . date('Y-m-d H:i:s') . "\nTotal signups: {$count}\n",
                "From: noreply@dirt-star.com\r\nContent-Type: text/plain; charset=UTF-8"
            );
        }
    }
}

$page_title = 'Forge — Join the Waitlist';
$page_id = 'waitlist';
require_once __DIR__ . '/includes/header.php';
?>

<section class="section" style="min-height: calc(100vh - var(--nav-height) - 200px); display: flex; align-items: center;">
    <div class="container-narrow">
        <div class="section-header" style="margin-bottom: 32px;">
            <span class="badge-label">Early Access</span>
            <h1 style="font-size: 2.6em; margin-bottom: 16px;">Get In <span class="text-gradient">Early.</span></h1>
            <p style="font-size: 1.15em; max-width: 540px; margin: 0 auto;">
                Forge is a local AI coding assistant that runs entirely on your hardware.
                Join the waitlist to get notified when we launch.
            </p>
        </div>

        <div class="card card-glow" style="max-width: 520px; margin: 0 auto; padding: 36px;">

            <?php if ($success): ?>
                <div style="text-align: center; padding: 20px 0;">
                    <div style="font-size: 2.4em; margin-bottom: 12px;">&#9889;</div>
                    <h3 style="margin-bottom: 8px;">You're on the list.</h3>
                    <p class="text-dim">We'll reach out when it's your turn. You're <strong class="text-accent">#<?php echo $count; ?></strong> in line.</p>
                </div>

            <?php elseif ($already): ?>
                <div style="text-align: center; padding: 20px 0;">
                    <div style="font-size: 2.4em; margin-bottom: 12px;">&#128077;</div>
                    <h3 style="margin-bottom: 8px;">You're already signed up.</h3>
                    <p class="text-dim">We've got your email. Hang tight.</p>
                </div>

            <?php else: ?>
                <form method="POST" action="waitlist.php" autocomplete="on">
                    <input type="hidden" name="_csrf" value="<?php echo htmlspecialchars($csrf_token); ?>">
                    <div class="form-group">
                        <label class="form-label" for="email">Email Address</label>
                        <input type="email" id="email" name="email" class="form-input" placeholder="you@example.com"
                               required autofocus style="font-size: 1.05em; padding: 14px 16px;"
                               value="<?php echo isset($_POST['email']) ? htmlspecialchars($_POST['email']) : ''; ?>">
                    </div>

                    <?php if ($error): ?>
                        <p style="color: var(--red); font-size: 0.9em; margin-bottom: 12px;"><?php echo htmlspecialchars($error); ?></p>
                    <?php endif; ?>

                    <button type="submit" class="btn btn-primary btn-block btn-lg" style="margin-top: 8px;">
                        Join the Waitlist
                    </button>
                </form>

                <?php if ($count > 0): ?>
                    <p class="text-dim text-center" style="margin-top: 16px; font-size: 0.88em;">
                        <strong class="text-accent"><?php echo number_format($count); ?></strong> people already signed up
                    </p>
                <?php endif; ?>
            <?php endif; ?>
        </div>

        <!-- Specs / What You'll Get -->
        <div class="grid-3" style="margin-top: 48px; gap: 16px;">
            <div class="stat-card">
                <span class="stat-icon">&#128187;</span>
                <span class="stat-value">100%</span>
                <span class="stat-label">Runs on Your GPU</span>
            </div>
            <div class="stat-card">
                <span class="stat-icon">&#128274;</span>
                <span class="stat-value">$0</span>
                <span class="stat-label">Cloud API Costs</span>
            </div>
            <div class="stat-card">
                <span class="stat-icon">&#9889;</span>
                <span class="stat-value">14B+</span>
                <span class="stat-label">Parameter Models</span>
            </div>
        </div>

        <div style="max-width: 640px; margin: 40px auto 0; text-align: center;">
            <p class="text-dim" style="font-size: 0.95em; line-height: 1.7;">
                Forge supports everything from lightweight 7B models on modest hardware up to
                massive 70B+ parameter models on high-end rigs. Whatever GPU you've got, there's a
                model in the catalog that fits.
            </p>
            <p style="margin-top: 24px;">
                <a href="/Forge/" class="btn btn-secondary">Learn More</a>
            </p>
        </div>
    </div>
</section>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
