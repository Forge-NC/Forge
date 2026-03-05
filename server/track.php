<?php
/**
 * Forge Site Analytics — Event Collection Endpoint
 *
 * Receives tracking events from tracker.js via POST.
 * Appends to data/site_events.jsonl (one JSON object per line).
 * No auth required. Rate-limited to 30 events/min per IP.
 */

// Only accept POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit;
}

// CORS — restrict to same origin
$allowed_origin = 'https://dirt-star.com';
$request_origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if ($request_origin === $allowed_origin || $request_origin === 'http://dirt-star.com') {
    header('Access-Control-Allow-Origin: ' . $request_origin);
} else {
    header('Access-Control-Allow-Origin: ' . $allowed_origin);
}
header('Access-Control-Allow-Methods: POST');

// ── Rate limiting (30 events/min per IP) ──
$ip_raw = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
$rate_dir = sys_get_temp_dir() . '/forge_rate';
if (!is_dir($rate_dir)) @mkdir($rate_dir, 0755, true);
$rate_file = $rate_dir . '/' . md5($ip_raw) . '.txt';
$now = time();

if (file_exists($rate_file)) {
    $lines = file($rate_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    // Keep only timestamps from last 60 seconds
    $recent = array();
    foreach ($lines as $ts) {
        if (($now - (int)$ts) < 60) $recent[] = $ts;
    }
    if (count($recent) >= 30) {
        http_response_code(429);
        exit;
    }
    $recent[] = $now;
    file_put_contents($rate_file, implode("\n", $recent));
} else {
    file_put_contents($rate_file, $now);
}

// ── Parse request body (8KB max) ──
$body = file_get_contents('php://input', false, null, 0, 8192);
$data = json_decode($body, true);

if (!$data || !is_array($data) || empty($data['event'])) {
    http_response_code(400);
    exit;
}

// ── Whitelist allowed event types ──
$allowed_events = array('pageview', 'cta_click', 'waitlist', 'scroll_depth');
if (!in_array($data['event'], $allowed_events)) {
    http_response_code(400);
    exit;
}

// ── Parse User-Agent ──
$ua = $_SERVER['HTTP_USER_AGENT'] ?? '';

$browser = 'Other';
$browser_ver = '';
if (preg_match('/Edg[e\/](\d+)/i', $ua, $m))         { $browser = 'Edge';    $browser_ver = $m[1]; }
elseif (preg_match('/OPR\/(\d+)/i', $ua, $m))          { $browser = 'Opera';   $browser_ver = $m[1]; }
elseif (preg_match('/Chrome\/(\d+)/i', $ua, $m))        { $browser = 'Chrome';  $browser_ver = $m[1]; }
elseif (preg_match('/Firefox\/(\d+)/i', $ua, $m))       { $browser = 'Firefox'; $browser_ver = $m[1]; }
elseif (preg_match('/Safari\/(\d+)/i', $ua, $m) && strpos($ua, 'Chrome') === false) { $browser = 'Safari'; $browser_ver = $m[1]; }

$os = 'Other';
if (strpos($ua, 'Windows') !== false)       $os = 'Windows';
elseif (strpos($ua, 'Macintosh') !== false) $os = 'macOS';
elseif (strpos($ua, 'Linux') !== false && strpos($ua, 'Android') === false) $os = 'Linux';
elseif (strpos($ua, 'Android') !== false)   $os = 'Android';
elseif (preg_match('/iPhone|iPad|iPod/i', $ua)) $os = 'iOS';

// Device type from viewport width (sent by client)
$vw = isset($data['vw']) ? (int)$data['vw'] : 0;
$device = 'Desktop';
if ($vw > 0 && $vw < 768)       $device = 'Mobile';
elseif ($vw >= 768 && $vw < 1024) $device = 'Tablet';

// ── Sanitize string inputs (strip HTML to prevent stored XSS) ──
$_strip = function($v, $max) { return substr(strip_tags((string)$v), 0, $max); };

// ── Build event record ──
$event = array(
    'event'     => $data['event'],
    'ts'        => date('c'),
    'ts_unix'   => $now,
    'vid'       => isset($data['vid']) ? substr(preg_replace('/[^a-f0-9\-]/', '', $data['vid']), 0, 40) : null,
    'url'       => isset($data['url']) ? $_strip($data['url'], 500) : null,
    'ref'       => isset($data['ref']) ? $_strip($data['ref'], 500) : null,
    'ip_hash'   => substr(hash('sha512', $ip_raw . 'forge_salt_2026'), 0, 16),
    'country'   => isset($_SERVER['HTTP_CF_IPCOUNTRY']) ? strtoupper(substr($_SERVER['HTTP_CF_IPCOUNTRY'], 0, 2)) : null,
    'browser'   => $browser . ($browser_ver ? ' ' . $browser_ver : ''),
    'os'        => $os,
    'device'    => $device,
    'vw'        => $vw > 0 ? $vw : null,
    'sw'        => isset($data['sw']) ? (int)$data['sw'] : null,
    'sh'        => isset($data['sh']) ? (int)$data['sh'] : null,
);

// ── Event-specific fields ──
if ($data['event'] === 'pageview') {
    $event['utm_source']   = isset($data['utm_source'])   ? $_strip($data['utm_source'], 100) : null;
    $event['utm_medium']   = isset($data['utm_medium'])   ? $_strip($data['utm_medium'], 100) : null;
    $event['utm_campaign'] = isset($data['utm_campaign']) ? $_strip($data['utm_campaign'], 100) : null;
    $event['utm_content']  = isset($data['utm_content'])  ? $_strip($data['utm_content'], 100) : null;
    $event['utm_term']     = isset($data['utm_term'])     ? $_strip($data['utm_term'], 100) : null;
}

if ($data['event'] === 'cta_click') {
    $event['btn_text'] = isset($data['btn_text']) ? $_strip($data['btn_text'], 200) : null;
    $event['btn_href'] = isset($data['btn_href']) ? $_strip($data['btn_href'], 500) : null;
    $event['tier']     = isset($data['tier'])     ? $_strip($data['tier'], 20) : null;
    $event['billing']  = isset($data['billing'])  ? $_strip($data['billing'], 20) : null;
    $event['section']  = isset($data['section'])  ? $_strip($data['section'], 100) : null;
}

if ($data['event'] === 'scroll_depth') {
    $event['max_scroll'] = isset($data['max_scroll']) ? min(100, max(0, (int)$data['max_scroll'])) : null;
    $event['time_on_page'] = isset($data['time_on_page']) ? min(86400, max(0, (int)$data['time_on_page'])) : null;
}

if ($data['event'] === 'waitlist') {
    $event['tier'] = isset($data['tier']) ? substr($data['tier'], 0, 20) : null;
}

// ── Remove null values to keep JSONL compact ──
$event = array_filter($event, function($v) { return $v !== null; });

// ── Append to JSONL file ──
$events_file = __DIR__ . '/data/site_events.jsonl';

// File rotation at 5MB
if (file_exists($events_file) && filesize($events_file) > 5 * 1024 * 1024) {
    $archive = __DIR__ . '/data/site_events_' . date('Ymd_His') . '.jsonl';
    rename($events_file, $archive);
}

$line = json_encode($event, JSON_UNESCAPED_SLASHES) . "\n";
file_put_contents($events_file, $line, FILE_APPEND | LOCK_EX);

// ── Respond ──
http_response_code(204);
exit;
