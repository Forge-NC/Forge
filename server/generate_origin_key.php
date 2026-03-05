<?php
/**
 * One-time script: Generate the Origin Ed25519 signing keypair.
 *
 * SECURITY: CLI-only. Web requests get 403. Self-deletes after success.
 *
 * After running, copy the printed public key into forge/passport.py:
 *   _ORIGIN_PUBLIC_KEY_B64 = "<public_key_b64>"
 *
 * Then re-issue any previously signed passports using tools/passport_issuer.py:
 *   python tools/passport_issuer.py issue --key ~/.forge/forge_origin.key ...
 *
 * Usage (SSH into server):
 *   cd /home/dirtsta1/public_html/Forge
 *   php generate_origin_key.php
 *
 * Requires: PHP 7.2+ with the sodium extension (standard in most hosts).
 */

// ── BLOCK ALL WEB ACCESS ──
if (php_sapi_name() !== 'cli') {
    http_response_code(403);
    die('Forbidden');
}

// ── Check sodium is available ──
if (!function_exists('sodium_crypto_sign_keypair')) {
    echo "ERROR: PHP sodium extension not available.\n";
    echo "Install with: apt-get install php-sodium  (or enable extension=sodium in php.ini)\n";
    exit(1);
}

$key_file = __DIR__ . '/data/origin_key.json';

if (file_exists($key_file)) {
    echo "ERROR: Origin key already exists at $key_file\n";
    echo "Delete it manually if you want to regenerate.\n";
    echo "WARNING: Regenerating invalidates ALL existing passports.\n";
    exit(1);
}

// ── Generate Ed25519 keypair ──
$keypair    = sodium_crypto_sign_keypair();
$secret_key = sodium_crypto_sign_secretkey($keypair);  // 64 bytes
$public_key = sodium_crypto_sign_publickey($keypair);  // 32 bytes

$secret_b64 = base64_encode($secret_key);
$public_b64 = base64_encode($public_key);

// The Python passport_issuer.py needs only the first 32 bytes (raw private scalar)
$private_scalar_b64 = base64_encode(substr($secret_key, 0, 32));

$data = [
    'algorithm'      => 'ed25519',
    'secret_key_b64' => $secret_b64,          // 64-byte sodium secret key (private+public)
    'public_key_b64' => $public_b64,           // 32-byte public key
    'created_at'     => date('c'),
    'warning'        => 'NEVER share secret_key_b64. Regenerating invalidates all passports.',
];

if (!is_dir(__DIR__ . '/data')) {
    mkdir(__DIR__ . '/data', 0755, true);
}

file_put_contents($key_file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
chmod($key_file, 0600);

echo "=== Forge Origin Ed25519 Keypair Generated ===\n\n";
echo "Key file:   $key_file\n";
echo "Algorithm:  Ed25519 (via libsodium)\n";
echo "Created:    " . date('c') . "\n\n";

echo "--- ACTION REQUIRED ---\n\n";
echo "1. Embed this public key in forge/passport.py:\n";
echo "   _ORIGIN_PUBLIC_KEY_B64 = \"$public_b64\"\n\n";

echo "2. Save this private key to ~/.forge/forge_origin.key on your local machine\n";
echo "   (for use with tools/passport_issuer.py):\n";
echo "   $private_scalar_b64\n\n";

echo "3. Re-sign your Origin passport if you had one from a previous key:\n";
echo "   python tools/passport_issuer.py issue --key ~/.forge/forge_origin.key \\\n";
echo "       --account origin-theup --tier origin --role origin \\\n";
echo "       --machine c8294b9c6588 --seats 9999 --out origin.passport.json\n\n";

echo "The secret key in $key_file is chmod 0600 (owner read-only).\n";
echo "Back it up offline. If it leaks, you must regenerate and re-issue all passports.\n\n";

// ── SELF-DESTRUCT ──
$self = __FILE__;
if (unlink($self)) {
    echo "Self-destructed: $self has been deleted.\n";
} else {
    echo "WARNING: Could not self-delete $self. DELETE IT MANUALLY NOW.\n";
}
