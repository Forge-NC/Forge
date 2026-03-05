<?php
/**
 * Forge Authentication Helper
 *
 * Included by all server endpoints. Validates per-user tokens or
 * the legacy shared API key.
 *
 * Token storage: data/tokens.json
 *   {"token_hash": {"created": "...", "revoked": false, "label": "tester-alice"}}
 *
 * Tokens are SHA512-hashed at rest. Client stores plaintext in config.
 * Tokens are NOT bound to machine_id — one token = one person.
 * Revocation kills the token regardless of which machine used it.
 */

// Load legacy key from protected config file (not hardcoded)
$_LEGACY_KEY_FILE = __DIR__ . '/data/legacy_key.json';
$LEGACY_API_KEY = '';
if (file_exists($_LEGACY_KEY_FILE)) {
    $_lk = json_decode(file_get_contents($_LEGACY_KEY_FILE), true);
    $LEGACY_API_KEY = isset($_lk['legacy_api_key']) ? $_lk['legacy_api_key'] : '';
}
$TOKEN_FILE = __DIR__ . '/data/tokens.json';

// Rate limit directory for auth attempts
$_AUTH_RATE_DIR = __DIR__ . '/rate_limits';

/**
 * Validate the current request's authentication.
 *
 * Checks X-Forge-Token header first, then X-Forge-Key (legacy).
 * Also accepts ?key= query param for browser-based dashboard access.
 *
 * Returns ['valid' => true, 'method' => 'token'|'legacy'|'query',
 *          'label' => '...'] on success.
 * Returns ['valid' => false, 'error' => '...'] on failure.
 */
function validate_auth(): array {
    global $LEGACY_API_KEY, $TOKEN_FILE;

    // 1. Per-user token (X-Forge-Token header)
    $token = $_SERVER['HTTP_X_FORGE_TOKEN'] ?? '';
    if ($token !== '') {
        $result = _check_token($token, $TOKEN_FILE);
        if (!$result['valid']) _log_auth_failure('token_header');
        return $result;
    }

    // 2. Legacy shared key (X-Forge-Key header) — constant-time comparison
    $key = $_SERVER['HTTP_X_FORGE_KEY'] ?? '';
    if ($key !== '' && $LEGACY_API_KEY !== '' && hash_equals($LEGACY_API_KEY, $key)) {
        return ['valid' => true, 'method' => 'legacy', 'label' => 'shared_key', 'role' => 'tester'];
    }

    // 3. Query param (for dashboard browser access)
    $query_key = $_GET['key'] ?? '';
    if ($query_key !== '' && $LEGACY_API_KEY !== '' && hash_equals($LEGACY_API_KEY, $query_key)) {
        return ['valid' => true, 'method' => 'query', 'label' => 'shared_key', 'role' => 'tester'];
    }
    if ($query_key !== '') {
        $result = _check_token($query_key, $TOKEN_FILE);
        if (!$result['valid']) _log_auth_failure('query_param');
        return $result;
    }

    // 4. Legacy header check (backward compat with old telemetry_receiver)
    if ($key !== '') {
        _log_auth_failure('legacy_header');
        return ['valid' => false, 'error' => 'Authentication failed'];
    }

    return ['valid' => false, 'error' => 'No authentication provided'];
}

/**
 * Check a token against the token store.
 */
function _check_token(string $token, string $token_file): array {
    if (!file_exists($token_file)) {
        return ['valid' => false, 'error' => 'Authentication failed'];
    }

    $store = json_decode(file_get_contents($token_file), true);
    if (!is_array($store)) {
        return ['valid' => false, 'error' => 'Authentication failed'];
    }

    $hash = hash('sha512', $token);

    // Backward compat: try SHA-512 first, fall back to SHA-256 for pre-migration tokens
    $migrated = false;
    if (!isset($store[$hash])) {
        $fallback_hash = hash('sha256', $token);
        if (isset($store[$fallback_hash])) {
            // Migrate: re-key the entry from SHA-256 to SHA-512
            $store[$hash] = $store[$fallback_hash];
            unset($store[$fallback_hash]);
            $tmp = $token_file . '.tmp.' . getmypid();
            file_put_contents($tmp, json_encode($store, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
            rename($tmp, $token_file);
            $migrated = true;
        } else {
            return ['valid' => false, 'error' => 'Authentication failed'];
        }
    }

    $entry = $store[$hash];
    if (!empty($entry['revoked'])) {
        return ['valid' => false, 'error' => 'Authentication failed'];
    }

    // Determine role — explicit role field only, no label inference
    $role = 'tester';
    if (isset($entry['role']) && in_array($entry['role'], array('owner', 'admin', 'captain', 'master', 'tester'))) {
        $role = $entry['role'];
    }

    return [
        'valid' => true,
        'method' => 'token',
        'label' => isset($entry['label']) ? $entry['label'] : 'unknown',
        'token_hash' => $hash,
        'role' => $role,
    ];
}

/**
 * Log failed authentication attempts for audit trail.
 */
function _log_auth_failure(string $method) {
    global $_AUTH_RATE_DIR;
    $ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    $log_file = __DIR__ . '/data/auth_failures.jsonl';
    $entry = json_encode([
        'ts' => date('c'),
        'ip_hash' => substr(hash('sha512', $ip . 'forge_auth_salt'), 0, 16),
        'method' => $method,
    ]);
    @file_put_contents($log_file, $entry . "\n", FILE_APPEND | LOCK_EX);

    // Rate limit: max 20 failed attempts per IP per 5 minutes
    if (!is_dir($_AUTH_RATE_DIR)) @mkdir($_AUTH_RATE_DIR, 0755, true);
    $rate_file = $_AUTH_RATE_DIR . '/auth_' . md5($ip) . '.json';
    $now = time();
    $rate_data = file_exists($rate_file) ? json_decode(file_get_contents($rate_file), true) : null;
    if ($rate_data && ($now - ($rate_data['window_start'] ?? 0)) < 300) {
        $rate_data['count'] = ($rate_data['count'] ?? 0) + 1;
        if ($rate_data['count'] > 20) {
            http_response_code(429);
            header('Content-Type: application/json');
            echo json_encode(['error' => 'Too many failed attempts. Try again later.']);
            exit;
        }
    } else {
        $rate_data = ['window_start' => $now, 'count' => 1];
    }
    file_put_contents($rate_file, json_encode($rate_data));
}

/**
 * Require valid authentication or return 403 and exit.
 */
function require_auth(): array {
    $auth = validate_auth();
    if (!$auth['valid']) {
        http_response_code(403);
        header('Content-Type: application/json');
        echo json_encode(['error' => $auth['error']]);
        exit;
    }
    return $auth;
}
