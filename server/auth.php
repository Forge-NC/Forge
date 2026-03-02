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
 * Tokens are SHA256-hashed at rest. Client stores plaintext in config.
 * Tokens are NOT bound to machine_id — one token = one person.
 * Revocation kills the token regardless of which machine used it.
 *
 * The legacy shared key (fg_tel_2026_...) continues to work as a
 * fallback until all clients upgrade to per-user tokens.
 */

$LEGACY_API_KEY = 'fg_tel_2026_e7eb55900b70bd84eaeb62f7cd0153e7';
$TOKEN_FILE = __DIR__ . '/data/tokens.json';

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
        return _check_token($token, $TOKEN_FILE);
    }

    // 2. Legacy shared key (X-Forge-Key header)
    $key = $_SERVER['HTTP_X_FORGE_KEY'] ?? '';
    if ($key === $LEGACY_API_KEY) {
        return ['valid' => true, 'method' => 'legacy', 'label' => 'shared_key'];
    }

    // 3. Query param (for dashboard browser access)
    $query_key = $_GET['key'] ?? '';
    if ($query_key === $LEGACY_API_KEY) {
        return ['valid' => true, 'method' => 'query', 'label' => 'shared_key'];
    }
    if ($query_key !== '') {
        return _check_token($query_key, $TOKEN_FILE);
    }

    // 4. Legacy header check (backward compat with old telemetry_receiver)
    if ($key !== '' && $key !== $LEGACY_API_KEY) {
        return ['valid' => false, 'error' => 'Invalid API key'];
    }

    return ['valid' => false, 'error' => 'No authentication provided'];
}

/**
 * Check a token against the token store.
 */
function _check_token(string $token, string $token_file): array {
    if (!file_exists($token_file)) {
        return ['valid' => false, 'error' => 'Token store not found'];
    }

    $store = json_decode(file_get_contents($token_file), true);
    if (!is_array($store)) {
        return ['valid' => false, 'error' => 'Token store corrupted'];
    }

    $hash = hash('sha256', $token);

    if (!isset($store[$hash])) {
        return ['valid' => false, 'error' => 'Unknown token'];
    }

    $entry = $store[$hash];
    if (!empty($entry['revoked'])) {
        return ['valid' => false, 'error' => 'Token has been revoked'];
    }

    return [
        'valid' => true,
        'method' => 'token',
        'label' => $entry['label'] ?? 'unknown',
        'token_hash' => $hash,
    ];
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
