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

// -- Authenticate and require admin/owner role --
$auth = require_auth();
$caller_role = isset($auth['role']) ? $auth['role'] : 'tester';
// Backward compat fallback
if ($caller_role === 'tester') {
    $label_check = isset($auth['label']) ? $auth['label'] : '';
    if (strpos($label_check, 'admin') !== false) {
        $caller_role = 'admin';
    }
}
if (!in_array($caller_role, array('owner', 'admin'))) {
    http_response_code(403);
    header('Content-Type: application/json');
    echo json_encode(array('error' => 'Admin or owner access required'));
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
    handle_register($body, $TOKEN_FILE, $caller_role);
} elseif ($action === 'revoke') {
    handle_revoke($body, $TOKEN_FILE, $caller_role);
} elseif ($action === 'set_role') {
    handle_role_change($body, $TOKEN_FILE, $caller_role);
} else {
    http_response_code(400);
    echo json_encode(array('error' => 'Unknown action: ' . $action));
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

function role_rank($role) {
    $ranks = array('tester' => 0, 'admin' => 1, 'owner' => 2);
    return isset($ranks[$role]) ? $ranks[$role] : 0;
}

function list_tokens($path) {
    $tokens = load_tokens($path);
    $result = array();
    foreach ($tokens as $hash => $entry) {
        // Determine role with 3-tier fallback
        $role = 'tester';
        if (isset($entry['role']) && in_array($entry['role'], array('owner', 'admin', 'tester'))) {
            $role = $entry['role'];
        } elseif (isset($entry['label']) && strpos($entry['label'], 'admin') !== false) {
            $role = 'admin';
        }

        $result[] = array(
            'hash_prefix' => substr($hash, 0, 12) . '...',
            'label'       => isset($entry['label']) ? $entry['label'] : 'unknown',
            'created'     => isset($entry['created']) ? $entry['created'] : null,
            'revoked'     => !empty($entry['revoked']),
            'role'        => $role,
        );
    }
    return $result;
}

function handle_register(array $body, $path, $caller_role) {
    $hash  = isset($body['token_hash']) ? $body['token_hash'] : '';
    $label = isset($body['label']) ? $body['label'] : '';

    // Validate hash: exactly 64 hex characters
    if (!preg_match('/^[a-f0-9]{64}$/i', $hash)) {
        http_response_code(400);
        echo json_encode(array('error' => 'token_hash must be exactly 64 hex characters'));
        exit;
    }

    // Sanitize label to alphanumeric, dash, underscore
    $label = preg_replace('/[^a-zA-Z0-9_-]/', '', $label);
    if ($label === '') {
        http_response_code(400);
        echo json_encode(array('error' => 'label is required (alphanumeric, dash, underscore)'));
        exit;
    }

    // Determine role for new token
    $new_role = isset($body['role']) ? $body['role'] : 'tester';
    if (!in_array($new_role, array('owner', 'admin', 'tester'))) {
        http_response_code(400);
        echo json_encode(array('error' => 'Invalid role. Must be owner, admin, or tester'));
        exit;
    }

    // Only owner can create admin/owner tokens
    if ($new_role !== 'tester' && $caller_role !== 'owner') {
        http_response_code(403);
        echo json_encode(array('error' => 'Only owner can create admin or owner tokens'));
        exit;
    }

    $hash = strtolower($hash);
    $tokens = load_tokens($path);

    if (isset($tokens[$hash])) {
        http_response_code(409);
        echo json_encode(array('error' => 'Token already exists'));
        exit;
    }

    $tokens[$hash] = array(
        'created' => gmdate('Y-m-d\TH:i:s\Z'),
        'revoked' => false,
        'label'   => $label,
        'role'    => $new_role,
    );
    save_tokens($path, $tokens);

    echo json_encode(array('status' => 'ok', 'label' => $label, 'role' => $new_role));
    exit;
}

function handle_revoke(array $body, $path, $caller_role) {
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

function handle_role_change(array $body, $path, $caller_role) {
    if ($caller_role !== 'owner') {
        http_response_code(403);
        echo json_encode(array('error' => 'Only owner can change roles'));
        exit;
    }

    $target_label = isset($body['label']) ? $body['label'] : '';
    $new_role = isset($body['role']) ? $body['role'] : '';

    if ($target_label === '') {
        http_response_code(400);
        echo json_encode(array('error' => 'label is required'));
        exit;
    }

    if (!in_array($new_role, array('owner', 'admin', 'tester'))) {
        http_response_code(400);
        echo json_encode(array('error' => 'Invalid role. Must be owner, admin, or tester'));
        exit;
    }

    $tokens = load_tokens($path);
    $found_key = null;
    foreach ($tokens as $hash => $entry) {
        $entry_label = isset($entry['label']) ? $entry['label'] : '';
        if ($entry_label === $target_label) {
            $found_key = $hash;
            break;
        }
    }

    if ($found_key === null) {
        http_response_code(404);
        echo json_encode(array('error' => 'Token with label not found'));
        exit;
    }

    $tokens[$found_key]['role'] = $new_role;
    save_tokens($path, $tokens);

    echo json_encode(array('status' => 'ok', 'label' => $target_label, 'role' => $new_role));
    exit;
}
