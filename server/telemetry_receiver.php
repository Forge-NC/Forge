<?php
/**
 * Forge Telemetry Receiver
 *
 * Accepts POST with:
 *   - File upload: "bundle" (zip)
 *   - Header: X-Forge-Key (shared API key)
 *   - POST field: machine_id (12-char hex)
 *
 * Saves to: data/YYYYMMDD/forge_{machine_id}_{timestamp}.zip
 * Rate limit: max 10 uploads per machine_id per hour (file-based).
 *
 * Deploy to: dirt-star.com/Forge/telemetry_receiver.php
 */

// -- Configuration --
$API_KEY = 'fg_tel_2026_e7eb55900b70bd84eaeb62f7cd0153e7';
$DATA_DIR = __DIR__ . '/data';
$RATE_LIMIT_DIR = __DIR__ . '/rate_limits';
$MAX_ZIP_SIZE = 512 * 1024;  // 512KB
$RATE_LIMIT_MAX = 10;        // per machine per hour

// -- CORS headers for preflight --
header('Content-Type: application/json');

// -- Validate request method --
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// -- Check API key --
$key = $_SERVER['HTTP_X_FORGE_KEY'] ?? '';
if ($key !== $API_KEY) {
    http_response_code(403);
    echo json_encode(['error' => 'Invalid API key']);
    exit;
}

// -- Check file upload --
if (!isset($_FILES['bundle']) || $_FILES['bundle']['error'] !== UPLOAD_ERR_OK) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing or invalid bundle upload']);
    exit;
}

$file = $_FILES['bundle'];
if ($file['size'] > $MAX_ZIP_SIZE) {
    http_response_code(413);
    echo json_encode(['error' => 'Bundle too large']);
    exit;
}

// -- Validate machine_id (hex chars only) --
$machine_id = preg_replace('/[^a-f0-9]/', '', strtolower($_POST['machine_id'] ?? ''));
if (strlen($machine_id) < 8 || strlen($machine_id) > 16) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid machine_id']);
    exit;
}

// -- Rate limiting (file-based, no external deps) --
if (!is_dir($RATE_LIMIT_DIR)) {
    @mkdir($RATE_LIMIT_DIR, 0750, true);
}
$rate_file = $RATE_LIMIT_DIR . '/' . $machine_id . '.txt';
$now = time();
$window_start = $now - 3600;
$entries = [];

if (file_exists($rate_file)) {
    $lines = file($rate_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $ts = (int)$line;
        if ($ts > $window_start) {
            $entries[] = $ts;
        }
    }
}

if (count($entries) >= $RATE_LIMIT_MAX) {
    http_response_code(429);
    echo json_encode(['error' => 'Rate limited', 'retry_after' => 3600]);
    exit;
}

$entries[] = $now;
file_put_contents($rate_file, implode("\n", $entries) . "\n", LOCK_EX);

// -- Validate zip contents --
$zip = new ZipArchive();
$open_result = $zip->open($file['tmp_name']);
if ($open_result !== true) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid zip file']);
    exit;
}

$has_manifest = ($zip->locateName('manifest.json') !== false);
$has_audit = ($zip->locateName('audit.json') !== false);
$zip->close();

if (!$has_manifest || !$has_audit) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing required files in bundle']);
    exit;
}

// -- Save to date-partitioned directory --
$date_dir = $DATA_DIR . '/' . date('Ymd');
if (!is_dir($date_dir)) {
    @mkdir($date_dir, 0750, true);
}

$timestamp = date('His');
$dest = $date_dir . '/forge_' . $machine_id . '_' . $timestamp . '.zip';

if (!move_uploaded_file($file['tmp_name'], $dest)) {
    http_response_code(500);
    echo json_encode(['error' => 'Failed to save bundle']);
    exit;
}

// -- Success --
http_response_code(200);
echo json_encode([
    'status' => 'ok',
    'stored' => basename($dest),
    'size' => filesize($dest),
]);
