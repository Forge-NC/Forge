<?php
/**
 * Forge Token Administration
 *
 * Admin-only endpoint for registering and revoking telemetry tokens.
 * Only tokens with "admin" in their label can access this endpoint.
 *
 * GET  — list all tokens (hash prefix + label + status)
 * POST — register or revoke tokens
 *
 * Invocation: HTTP from admin panel or curl
 */

require_once __DIR__ . '/auth.php';

header('Content-Type: application/json');

// -- Authenticate and require admin --
$auth = require_auth();
$label = isset($auth['label']) ? $auth['label'] : '';
if (strpos($label, 'admin') === false) {
    http_response_code(403);
    echo json_encode(['error' => 'Admin access required']);
    exit;
}

$TOKEN_FILE = __DIR__ . '/data/tokens.json';
$method = $_SERVER['REQUEST_METHOD'];

// -- Route by method --
if ($method === 'GET') {
    echo json_encode(list_tokens($TOKEN_FILE));
    exit;
}

if ($method !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// -- Parse POST body --
$body = json_decode(file_get_contents('php://input'), true);
if (!is_array($body)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON body']);
    exit;
}

$action = isset($body['action']) ? $body['action'] : '';

if ($action === 'list') {
    echo json_encode(list_tokens($TOKEN_FILE));
    exit;
}

if ($action === 'register') {
    handle_register($body, $TOKEN_FILE);
} elseif ($action === 'revoke') {
    handle_revoke($body, $TOKEN_FILE);
} else {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown action: ' . $action]);
    exit;
}

// -----------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------

function load_tokens($path) {
    if (!file_exists($path)) {
        return array();
    }
    $data = json_decode(file_get_contents($path), true);
    return is_array($data) ? $data : array();
}

function save_tokens($path, array $tokens) {
    $dir = dirname($path);
    if (!is_dir($dir)) {
        @mkdir($dir, 0750, true);
    }
    file_put_contents($path, json_encode($tokens, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
}

function list_tokens($path) {
    $tokens = load_tokens($path);
    $result = array();
    foreach ($tokens as $hash => $entry) {
        $result[] = array(
            'hash_prefix' => substr($hash, 0, 12) . '...',
            'label'       => isset($entry['label']) ? $entry['label'] : 'unknown',
            'created'     => isset($entry['created']) ? $entry['created'] : null,
            'revoked'     => !empty($entry['revoked']),
        );
    }
    return $result;
}

function handle_register(array $body, $path) {
    $hash  = isset($body['token_hash']) ? $body['token_hash'] : '';
    $label = isset($body['label']) ? $body['label'] : '';

    // Validate hash: exactly 64 hex characters
    if (!preg_match('/^[a-f0-9]{64}$/i', $hash)) {
        http_response_code(400);
        echo json_encode(['error' => 'token_hash must be exactly 64 hex characters']);
        exit;
    }

    // Sanitize label to alphanumeric, dash, underscore
    $label = preg_replace('/[^a-zA-Z0-9_-]/', '', $label);
    if ($label === '') {
        http_response_code(400);
        echo json_encode(['error' => 'label is required (alphanumeric, dash, underscore)']);
        exit;
    }

    $hash = strtolower($hash);
    $tokens = load_tokens($path);

    if (isset($tokens[$hash])) {
        http_response_code(409);
        echo json_encode(['error' => 'Token already exists']);
        exit;
    }

    $tokens[$hash] = array(
        'created' => gmdate('Y-m-d\TH:i:s\Z'),
        'revoked' => false,
        'label'   => $label,
    );
    save_tokens($path, $tokens);

    echo json_encode(array('status' => 'ok', 'label' => $label));
    exit;
}

function handle_revoke(array $body, $path) {
    $hash_input = isset($body['token_hash']) ? $body['token_hash'] : '';
    if ($hash_input === '') {
        http_response_code(400);
        echo json_encode(['error' => 'token_hash is required']);
        exit;
    }

    $hash_input = strtolower($hash_input);
    $tokens = load_tokens($path);

    // Exact match first
    if (isset($tokens[$hash_input])) {
        $tokens[$hash_input]['revoked'] = true;
        save_tokens($path, $tokens);
        echo json_encode(array('status' => 'ok', 'revoked' => $tokens[$hash_input]['label']));
        exit;
    }

    // Prefix match
    $match_key = null;
    foreach ($tokens as $hash => $entry) {
        if (strpos($hash, $hash_input) === 0) {
            $match_key = $hash;
            break;
        }
    }

    if ($match_key === null) {
        http_response_code(404);
        echo json_encode(['error' => 'Token not found']);
        exit;
    }

    $tokens[$match_key]['revoked'] = true;
    save_tokens($path, $tokens);
    echo json_encode(array('status' => 'ok', 'revoked' => $tokens[$match_key]['label']));
    exit;
}
