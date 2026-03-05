<?php
/**
 * Forge Passport Download — Serves passport JSON file for download.
 *
 * Authenticated by either:
 *   - session_id matching the master's Stripe session (post-purchase)
 *   - owner token (admin download for any master)
 */

$MASTERS_DIR = __DIR__ . '/data/masters';

$account_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $_GET['id'] ?? '');
$session_id = $_GET['session'] ?? '';

if (!$account_id) {
    http_response_code(400);
    die('Missing id parameter');
}

$master_file = "$MASTERS_DIR/$account_id.json";
if (!file_exists($master_file)) {
    http_response_code(404);
    die('Passport not found');
}

$master = json_decode(file_get_contents($master_file), true);
if (!$master) {
    http_response_code(500);
    die('Invalid master record');
}

// Authenticate: session_id match OR owner token
$authorized = false;

if ($session_id && ($master['stripe_session'] ?? '') === $session_id) {
    $authorized = true;
}

if (!$authorized) {
    // Check for owner auth
    require_once __DIR__ . '/auth.php';
    $auth = validate_auth();
    if ($auth['valid'] && ($auth['role'] ?? '') === 'owner') {
        $authorized = true;
    }
}

if (!$authorized) {
    http_response_code(403);
    die('Unauthorized. Use the download link from your purchase confirmation.');
}

$passport = $master['passport'] ?? [];
if (!$passport) {
    http_response_code(500);
    die('No passport data in master record');
}

// Serve as downloadable JSON
$filename = "forge_passport_{$account_id}.json";
header('Content-Type: application/json');
header("Content-Disposition: attachment; filename=\"$filename\"");
echo json_encode($passport, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
