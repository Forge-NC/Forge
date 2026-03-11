<?php
/**
 * Forge Passport API — Origin → Master → Puppet licensing.
 *
 * Actions:
 *   POST ?action=generate_master    (owner only)  Generate a Master passport
 *   POST ?action=validate           (any auth)    Validate a passport
 *   POST ?action=activate           (self-auth)   Activate as Master
 *   POST ?action=register_puppet    (master)      Register a Puppet under Master
 *   POST ?action=revoke             (owner only)  Revoke Master (cascades)
 *   GET  ?action=list_masters       (owner only)  List all Masters
 *   GET  ?action=my_fleet           (master)      Master's own puppets
 *   GET  ?action=tiers              (public)      Tier definitions
 *   POST ?action=genome_push        (auth)        Push genome to team aggregate
 *   GET  ?action=genome_pull        (auth)        Pull team aggregate genome
 */

require_once __DIR__ . '/auth.php';

// ── Rate limiting (per-IP, 60 requests/minute) ──
$RATE_DIR = __DIR__ . '/rate_limits';
if (!is_dir($RATE_DIR)) @mkdir($RATE_DIR, 0755, true);

$client_ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
$rate_file = $RATE_DIR . '/passport_' . md5($client_ip) . '.json';
$rate_data = file_exists($rate_file) ? json_decode(file_get_contents($rate_file), true) : null;
$now = time();

if ($rate_data && ($now - ($rate_data['window_start'] ?? 0)) < 60) {
    $rate_data['count'] = ($rate_data['count'] ?? 0) + 1;
    if ($rate_data['count'] > 60) {
        http_response_code(429);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'Rate limit exceeded. Try again in a minute.']);
        exit;
    }
} else {
    $rate_data = ['window_start' => $now, 'count' => 1];
}
file_put_contents($rate_file, json_encode($rate_data));

// ── Input size limit (reject payloads > 64KB) ──
$raw_input = file_get_contents('php://input');
if (strlen($raw_input ?: '') > 65536) {
    http_response_code(413);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Payload too large']);
    exit;
}

$ORIGIN_KEY_FILE     = __DIR__ . '/data/origin_key.json';
$TIERS_FILE          = __DIR__ . '/data/tiers_config.json';
$MASTERS_DIR         = __DIR__ . '/data/masters';
$PUPPET_REGISTRY     = __DIR__ . '/data/puppet_registry.json';
$REVOCATIONS_FILE    = __DIR__ . '/data/revocations.json';
$TOKEN_FILE_PASSAPI  = __DIR__ . '/data/tokens.json';

header('Content-Type: application/json');
// Prevent caching of API responses
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');

// ── Utility functions ──

function load_json(string $path) {
    if (!file_exists($path)) return null;
    $data = json_decode(file_get_contents($path), true);
    return is_array($data) ? $data : null;
}

function save_json(string $path, array $data): bool {
    $dir = dirname($path);
    if (!is_dir($dir)) mkdir($dir, 0755, true);
    $tmp = $path . '.tmp.' . getmypid();
    if (file_put_contents($tmp, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) === false) {
        @unlink($tmp);
        return false;
    }
    return rename($tmp, $path);
}

/**
 * Load the Ed25519 secret key (64-byte sodium format) from origin_key.json.
 * Returns raw binary secret key on success, null on failure.
 */
function load_origin_key(): ?string {
    global $ORIGIN_KEY_FILE;
    $data = load_json($ORIGIN_KEY_FILE);
    if (!$data) return null;

    // New Ed25519 format
    if (isset($data['secret_key_b64'])) {
        $key = base64_decode($data['secret_key_b64'], true);
        if ($key !== false && strlen($key) === SODIUM_CRYPTO_SIGN_SECRETKEYBYTES) {
            return $key;
        }
        return null;
    }

    // Old HMAC format — no longer supported
    return null;
}

/**
 * Load the Ed25519 public key (32-byte raw) from origin_key.json.
 * Returns raw binary public key on success, null on failure.
 */
function load_origin_pubkey(): ?string {
    global $ORIGIN_KEY_FILE;
    $data = load_json($ORIGIN_KEY_FILE);
    if (!$data) return null;

    if (isset($data['public_key_b64'])) {
        $key = base64_decode($data['public_key_b64'], true);
        if ($key !== false && strlen($key) === SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
            return $key;
        }
    }
    return null;
}

function load_tiers(): array {
    global $TIERS_FILE;
    $data = load_json($TIERS_FILE);
    return $data ?: [];
}

function load_revocations(): array {
    global $REVOCATIONS_FILE;
    return load_json($REVOCATIONS_FILE) ?: [];
}

function save_revocations(array $data): bool {
    global $REVOCATIONS_FILE;
    return save_json($REVOCATIONS_FILE, $data);
}

function load_puppet_registry(): array {
    global $PUPPET_REGISTRY;
    return load_json($PUPPET_REGISTRY) ?: [];
}

function save_puppet_registry(array $data): bool {
    global $PUPPET_REGISTRY;
    return save_json($PUPPET_REGISTRY, $data);
}

// Fields covered by the Ed25519 signature — MUST match BPoS._SIGNED_FIELDS in passport.py
define('SIGNED_FIELDS', [
    'passport_id', 'account_id', 'tier',
    'issued_at', 'expires_at', 'max_activations',
    'role', 'seat_count', 'parent_passport_id',
]);

/**
 * Build the canonical signing payload — identical to Python's BPoS._signing_payload().
 * Only covers immutable grant fields. All numeric values as integers.
 */
function signing_payload(array $passport): string {
    $payload = [];
    foreach (SIGNED_FIELDS as $field) {
        $val = array_key_exists($field, $passport) ? $passport[$field] : '';
        // Normalize: whole-number floats → int (matches Python's int() cast)
        if (is_float($val) && ($val == floor($val))) {
            $val = (int)$val;
        }
        $payload[$field] = $val;
    }
    ksort($payload);
    // JSON_UNESCAPED_SLASHES + JSON_UNESCAPED_UNICODE matches Python json.dumps defaults
    return json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
}

/**
 * Sign a passport with Ed25519. Returns base64-encoded signature string.
 * $secret_key is the raw 64-byte sodium secret key (from load_origin_key()).
 */
function sign_passport(array $passport_data, string $secret_key): string {
    if (strlen($secret_key) !== SODIUM_CRYPTO_SIGN_SECRETKEYBYTES) {
        throw new RuntimeException('Invalid secret key length');
    }
    $payload  = signing_payload($passport_data);
    $sig      = sodium_crypto_sign_detached($payload, $secret_key);
    return base64_encode($sig);
}

/**
 * Verify a passport's Ed25519 origin_signature.
 * $public_key is the raw 32-byte sodium public key (from load_origin_pubkey()).
 * Returns true if valid.
 */
function verify_passport(array $passport_data, string $public_key): bool {
    $sig_b64 = $passport_data['origin_signature'] ?? '';
    if (!$sig_b64) return false;

    $sig = base64_decode($sig_b64, true);
    if ($sig === false || strlen($sig) !== SODIUM_CRYPTO_SIGN_BYTES) return false;

    $payload = signing_payload($passport_data);
    return sodium_crypto_sign_verify_detached($sig, $payload, $public_key);
}

function generate_account_id(): string {
    return 'fg_' . bin2hex(random_bytes(12));
}

function generate_passport_id(): string {
    return 'pp_' . bin2hex(random_bytes(8));
}

function is_revoked(string $passport_id): bool {
    $revocations = load_revocations();
    return isset($revocations[$passport_id]);
}

function json_response(array $data, int $code = 200) {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_SLASHES);
    exit;
}

function json_error(string $msg, int $code = 400) {
    json_response(['error' => $msg], $code);
}

/**
 * Sanitize account_id to prevent path traversal.
 * Only allows alphanumeric, underscore, and hyphen.
 */
function sanitize_account_id(string $id): string {
    return preg_replace('/[^a-zA-Z0-9_-]/', '', $id);
}

function get_post_data(): array {
    global $raw_input;
    $data = json_decode($raw_input ?: '', true);
    return is_array($data) ? $data : [];
}

function require_role(array $auth, string $role) {
    $rank = ['tester' => 0, 'captain' => 1, 'master' => 1, 'admin' => 2, 'owner' => 3];
    $auth_role = $auth['role'] ?? 'tester';
    $auth_rank = $rank[$auth_role] ?? 0;
    $need_rank = $rank[$role] ?? 0;
    if ($auth_rank < $need_rank) {
        json_error("Insufficient permissions (need $role, have $auth_role)", 403);
    }
}

// ── Route dispatch ──

$action = $_GET['action'] ?? $_POST['action'] ?? '';

// Public endpoint — no auth needed
if ($action === 'tiers') {
    json_response(load_tiers());
}

// All other actions require auth (except validate which accepts passport self-auth)
if ($action === 'validate') {
    // validate can be called with or without auth — passport is self-validating
    handle_validate();
}

$auth = require_auth();

switch ($action) {
    case 'generate_master':
        require_role($auth, 'owner');
        handle_generate_master($auth);
        break;

    case 'activate':
        handle_activate($auth);
        break;

    case 'register_puppet':
        handle_register_puppet($auth);
        break;

    case 'revoke':
        require_role($auth, 'owner');
        handle_revoke($auth);
        break;

    case 'list_masters':
        require_role($auth, 'owner');
        handle_list_masters();
        break;

    case 'my_fleet':
        handle_my_fleet($auth);
        break;

    case 'genome_push':
        handle_genome_push($auth);
        break;

    case 'genome_pull':
        handle_genome_pull($auth);
        break;

    default:
        json_error("Unknown action");
}


// ── Action handlers ──

/**
 * POST ?action=generate_master
 * Owner generates a Master passport for a paying customer.
 * Input: {tier, customer_label, email}
 */
function handle_generate_master(array $auth) {
    global $MASTERS_DIR;

    $input = get_post_data();
    $tier = $input['tier'] ?? '';
    $label = $input['customer_label'] ?? $input['label'] ?? '';
    $email = $input['email'] ?? '';

    if (!$tier || !$label) {
        json_error('Missing required fields: tier, customer_label');
    }

    $tiers = load_tiers();
    if (!isset($tiers[$tier])) {
        json_error("Unknown tier: $tier");
    }

    $secret_key = load_origin_key();
    if (!$secret_key) {
        json_error('Origin key not configured — run generate_origin_key.php first', 500);
    }

    $tier_config = $tiers[$tier];
    $account_id = generate_account_id();
    $passport_id = generate_passport_id();

    $passport = [
        'passport_id'        => $passport_id,
        'account_id'         => $account_id,
        'role'               => 'master',
        'tier'               => $tier,
        'customer_label'     => $label,
        'email'              => $email,
        'seat_count'         => (int)$tier_config['seats'],
        'max_activations'    => (int)$tier_config['seats'],
        'issued_at'          => time(),
        'issued_date'        => date('c'),
        'expires_at'         => 0,
        'parent_passport_id' => '',
        'master_id'          => '',
        'origin_signature'   => '',
    ];

    // Sign with Ed25519 Origin key
    $passport['origin_signature'] = sign_passport($passport, $secret_key);

    // Store master record
    $master_record = [
        'passport'       => $passport,
        'activated'      => false,
        'master_mid'     => null,
        'activated_at'   => null,
        'last_seen'      => null,
        'telemetry_token'=> null,
    ];

    if (!is_dir($MASTERS_DIR)) mkdir($MASTERS_DIR, 0755, true);
    save_json("$MASTERS_DIR/$account_id.json", $master_record);

    json_response([
        'ok'          => true,
        'passport_id' => $passport_id,
        'account_id'  => $account_id,
        'passport'    => $passport,
        'download_url'=> "passport_api.php?action=download&id=$account_id",
    ]);
}

/**
 * POST ?action=validate
 * Validate a passport's signature and revocation status.
 * Input: {passport_json} (the passport object)
 */
function handle_validate() {
    $input = get_post_data();
    $passport = $input['passport_json'] ?? $input['passport'] ?? null;

    if (!$passport || !is_array($passport)) {
        json_error('Missing passport_json');
    }

    $public_key = load_origin_pubkey();
    if (!$public_key) {
        json_error('Origin key not configured', 500);
    }

    // Verify Ed25519 signature
    if (!verify_passport($passport, $public_key)) {
        json_response([
            'valid'  => false,
            'reason' => 'Invalid origin signature',
        ]);
    }

    // Check revocation
    $passport_id = $passport['passport_id'] ?? '';
    if ($passport_id && is_revoked($passport_id)) {
        json_response([
            'valid'  => false,
            'reason' => 'Passport has been revoked',
        ]);
    }

    // Check if master's passport is revoked (for puppet passports)
    $parent_passport_id = $passport['parent_passport_id'] ?? '';
    if ($parent_passport_id && is_revoked($parent_passport_id)) {
        json_response([
            'valid'  => false,
            'reason' => 'Parent master passport has been revoked',
        ]);
    }

    $tiers = load_tiers();
    $tier = $passport['tier'] ?? 'community';
    $tier_config = $tiers[$tier] ?? $tiers['community'] ?? [];

    // Count seats used
    $account_id = $passport['account_id'] ?? '';
    $registry = load_puppet_registry();
    $puppets = $registry[$account_id] ?? [];
    $seats_used = count($puppets);
    $seats_total = $passport['seat_count'] ?? $tier_config['seats'] ?? 1;

    json_response([
        'valid'           => true,
        'tier'            => $tier,
        'role'            => $passport['role'] ?? 'master',
        'seats_total'     => $seats_total,
        'seats_used'      => $seats_used,
        'seats_remaining' => max(0, $seats_total - $seats_used),
        'account_id'      => $account_id,
    ]);
}

/**
 * POST ?action=activate
 * Master activates their passport on a machine.
 * Input: {passport_json, machine_id}
 */
function handle_activate(array $auth) {
    global $MASTERS_DIR, $TOKEN_FILE_PASSAPI;

    $input = get_post_data();
    $passport = $input['passport_json'] ?? $input['passport'] ?? null;
    $machine_id = $input['machine_id'] ?? '';

    if (!$passport || !is_array($passport) || !$machine_id) {
        json_error('Missing passport_json and/or machine_id');
    }

    $public_key = load_origin_pubkey();
    if (!$public_key) {
        json_error('Origin key not configured', 500);
    }

    // Verify Ed25519 signature
    if (!verify_passport($passport, $public_key)) {
        json_error('Invalid passport signature');
    }

    // Check revocation
    $passport_id = $passport['passport_id'] ?? '';
    if ($passport_id && is_revoked($passport_id)) {
        json_error('Passport has been revoked');
    }

    $account_id = sanitize_account_id($passport['account_id'] ?? '');
    if (!$account_id) {
        json_error('Passport missing account_id');
    }

    // Load or create master record
    $master_file = "$MASTERS_DIR/$account_id.json";
    $master = load_json($master_file);

    if (!$master) {
        // First activation — create record from passport
        $master = [
            'passport'        => $passport,
            'activated'       => false,
            'master_mid'      => null,
            'activated_at'    => null,
            'last_seen'       => null,
            'telemetry_token' => null,
        ];
    }

    // Check if already activated on a different machine
    if ($master['activated'] && $master['master_mid'] && $master['master_mid'] !== $machine_id) {
        json_error("Master passport already activated on another machine. Deactivate first.");
    }

    // Generate telemetry token for this master
    $telemetry_token = 'fg_cap_' . bin2hex(random_bytes(16));
    $token_hash = hash('sha512', $telemetry_token);

    // Store token in tokens.json
    $tokens = load_json($TOKEN_FILE_PASSAPI) ?: [];
    $tokens[$token_hash] = [
        'created'    => date('c'),
        'revoked'    => false,
        'label'      => 'master-' . ($passport['customer_label'] ?? $account_id),
        'role'       => 'master',
        'account_id' => $account_id,
    ];
    save_json($TOKEN_FILE_PASSAPI, $tokens);

    // Update master record
    $master['activated']       = true;
    $master['master_mid']      = $machine_id;
    $master['activated_at']    = date('c');
    $master['last_seen']       = date('c');
    $master['telemetry_token'] = $token_hash;  // Store hash, not plaintext

    save_json($master_file, $master);

    $tiers = load_tiers();
    $tier = $passport['tier'] ?? 'community';
    $tier_config = $tiers[$tier] ?? [];

    json_response([
        'ok'              => true,
        'account_id'      => $account_id,
        'master_id'       => $machine_id,
        'tier'            => $tier,
        'tier_config'     => $tier_config,
        'seat_count'      => $passport['seat_count'] ?? $tier_config['seats'] ?? 1,
        'telemetry_token' => $telemetry_token,  // Plaintext — client stores this
    ]);
}

/**
 * POST ?action=register_puppet
 * Master registers a Puppet under their account.
 * Input: {master_id (account_id), puppet_mid, puppet_name, seat_id}
 */
function handle_register_puppet(array $auth) {
    global $MASTERS_DIR;

    $input = get_post_data();
    $account_id  = sanitize_account_id($input['master_id'] ?? $input['account_id'] ?? '');
    $puppet_mid  = $input['puppet_mid'] ?? '';
    $puppet_name = $input['puppet_name'] ?? '';
    $seat_id     = $input['seat_id'] ?? '';

    if (!$account_id || !$puppet_mid) {
        json_error('Missing master_id and/or puppet_mid');
    }

    // Verify this master exists and is active
    $master_file = "$MASTERS_DIR/$account_id.json";
    $master = load_json($master_file);
    if (!$master || !$master['activated']) {
        json_error('Master not found or not activated');
    }

    // Check auth — must be the master or owner
    $auth_role = $auth['role'] ?? 'tester';
    $auth_account = $auth['account_id'] ?? null;

    // Master can only register puppets for themselves
    if (($auth_role === 'captain' || $auth_role === 'master') && $auth_account !== $account_id) {
        json_error('Cannot register puppets for another master', 403);
    }

    // Check seat availability
    $passport = $master['passport'] ?? [];
    $seat_count = $passport['seat_count'] ?? 1;
    $registry = load_puppet_registry();
    $existing = $registry[$account_id] ?? [];

    // Seat count includes the master's own machine — puppets get (seats - 1)
    $puppet_limit = max(0, $seat_count - 1);
    if (count($existing) >= $puppet_limit) {
        json_error("Seat limit reached ($puppet_limit puppet seats). Upgrade tier for more.");
    }

    // Check if puppet_mid already registered
    foreach ($existing as $p) {
        if ($p['puppet_mid'] === $puppet_mid) {
            json_error("Machine $puppet_mid is already registered as a puppet");
        }
    }

    // Register
    $puppet_entry = [
        'puppet_mid'  => $puppet_mid,
        'puppet_name' => $puppet_name,
        'seat_id'     => $seat_id ?: 'seat_' . (count($existing) + 1),
        'registered_at' => date('c'),
        'last_seen'   => null,
        'status'      => 'active',
    ];

    $existing[] = $puppet_entry;
    $registry[$account_id] = $existing;
    save_puppet_registry($registry);

    json_response([
        'ok'        => true,
        'seat_id'   => $puppet_entry['seat_id'],
        'seats_used'=> count($existing),
        'seats_max' => $puppet_limit,
    ]);
}

/**
 * POST ?action=revoke
 * Owner revokes a Master passport. Cascades to all their puppets.
 * Input: {account_id} or {passport_id}
 */
function handle_revoke(array $auth) {
    global $MASTERS_DIR;

    $input = get_post_data();
    $account_id  = sanitize_account_id($input['account_id'] ?? '');
    $passport_id = $input['passport_id'] ?? '';

    // Find master by account_id or passport_id
    if ($account_id) {
        $master_file = "$MASTERS_DIR/$account_id.json";
        $master = load_json($master_file);
    } elseif ($passport_id) {
        // Search masters for this passport_id
        $master = null;
        $account_id = null;
        foreach (glob("$MASTERS_DIR/*.json") as $file) {
            $c = load_json($file);
            if ($c && ($c['passport']['passport_id'] ?? '') === $passport_id) {
                $master = $c;
                $account_id = $c['passport']['account_id'] ?? basename($file, '.json');
                $master_file = $file;
                break;
            }
        }
    } else {
        json_error('Missing account_id or passport_id');
    }

    if (!$master) {
        json_error('Master not found');
    }

    $pp_id = $master['passport']['passport_id'] ?? '';

    // Add to revocations
    $revocations = load_revocations();
    $revocations[$pp_id] = [
        'revoked_at' => date('c'),
        'revoked_by' => $auth['label'] ?? 'owner',
        'reason'     => $input['reason'] ?? 'Revoked by owner',
        'account_id' => $account_id,
    ];
    save_revocations($revocations);

    // Revoke telemetry token
    if ($master['telemetry_token']) {
        global $TOKEN_FILE_PASSAPI;
        $tokens = load_json($TOKEN_FILE_PASSAPI) ?: [];
        if (isset($tokens[$master['telemetry_token']])) {
            $tokens[$master['telemetry_token']]['revoked'] = true;
            save_json($TOKEN_FILE_PASSAPI, $tokens);
        }
    }

    // Count puppets that are now invalid
    $registry = load_puppet_registry();
    $puppets = $registry[$account_id] ?? [];
    $puppet_count = count($puppets);

    // Mark all puppets as revoked in registry
    foreach ($puppets as &$p) {
        $p['status'] = 'revoked';
    }
    unset($p);
    $registry[$account_id] = $puppets;
    save_puppet_registry($registry);

    // Update master file
    $master['activated'] = false;
    save_json($master_file, $master);

    json_response([
        'ok'              => true,
        'passport_id'     => $pp_id,
        'account_id'      => $account_id,
        'puppets_revoked' => $puppet_count,
    ]);
}

/**
 * GET ?action=list_masters
 * Owner view — all masters with summary data.
 */
function handle_list_masters() {
    global $MASTERS_DIR;

    $masters = [];
    $registry = load_puppet_registry();
    $revocations = load_revocations();

    foreach (glob("$MASTERS_DIR/*.json") as $file) {
        $c = load_json($file);
        if (!$c) continue;

        $passport = $c['passport'] ?? [];
        $account_id = $passport['account_id'] ?? basename($file, '.json');
        $pp_id = $passport['passport_id'] ?? '';
        $puppets = $registry[$account_id] ?? [];
        $active_puppets = array_filter($puppets, function($p) { return ($p['status'] ?? '') !== 'revoked'; });

        $masters[] = [
            'account_id'    => $account_id,
            'passport_id'   => $pp_id,
            'label'         => $passport['customer_label'] ?? '',
            'email'         => $passport['email'] ?? '',
            'tier'          => $passport['tier'] ?? 'community',
            'seats_total'   => $passport['seat_count'] ?? 1,
            'seats_used'    => count($active_puppets),
            'puppet_count'  => count($puppets),
            'activated'     => $c['activated'] ?? false,
            'master_mid'    => $c['master_mid'] ?? null,
            'activated_at'  => $c['activated_at'] ?? null,
            'last_seen'     => $c['last_seen'] ?? null,
            'revoked'       => isset($revocations[$pp_id]),
            'issued_date'   => $passport['issued_date'] ?? null,
        ];
    }

    json_response([
        'ok'      => true,
        'count'   => count($masters),
        'masters' => $masters,
    ]);
}

/**
 * GET ?action=my_fleet
 * Master view — their own puppets.
 */
function handle_my_fleet(array $auth) {
    global $MASTERS_DIR;

    // Find master by auth token's account_id
    $auth_account = null;

    // Check if token has account_id
    if (isset($auth['token_hash'])) {
        global $TOKEN_FILE_PASSAPI;
        $tokens = load_json($TOKEN_FILE_PASSAPI) ?: [];
        $token_entry = $tokens[$auth['token_hash']] ?? [];
        $auth_account = $token_entry['account_id'] ?? null;
    }

    // Owner can specify account_id as query param
    $auth_role = $auth['role'] ?? 'tester';
    if ($auth_role === 'owner' && isset($_GET['account_id'])) {
        $auth_account = sanitize_account_id($_GET['account_id']);
    }

    if (!$auth_account) {
        json_error('Cannot determine master account. Use master token or specify account_id.', 403);
    }

    $master_file = "$MASTERS_DIR/$auth_account.json";
    $master = load_json($master_file);
    if (!$master) {
        json_error('Master record not found');
    }

    $passport = $master['passport'] ?? [];
    $registry = load_puppet_registry();
    $puppets = $registry[$auth_account] ?? [];

    $seat_count = $passport['seat_count'] ?? 1;
    $puppet_limit = max(0, $seat_count - 1);

    json_response([
        'ok'            => true,
        'account_id'    => $auth_account,
        'tier'          => $passport['tier'] ?? 'community',
        'label'         => $passport['customer_label'] ?? '',
        'seats_total'   => $seat_count,
        'puppet_limit'  => $puppet_limit,
        'seats_used'    => count(array_filter($puppets, function($p) { return ($p['status'] ?? '') === 'active'; })),
        'puppets'       => $puppets,
    ]);
}


// ── Team Genome Sync ─────────────────────────────────────────────────────────

/**
 * Resolve master account from auth context.
 * Returns account_id string or null.
 */
function resolve_genome_account(array $auth) {
    global $MASTERS_DIR;

    $auth_account = $auth['account_id'] ?? null;
    $auth_role = $auth['role'] ?? 'tester';

    // Owner can specify account_id explicitly
    if ($auth_role === 'owner' && isset($_GET['account_id'])) {
        $auth_account = sanitize_account_id($_GET['account_id']);
    }

    if (!$auth_account) {
        return null;
    }

    // Verify tier allows genome_sync
    $master_file = "$MASTERS_DIR/$auth_account.json";
    $master = load_json($master_file);
    if (!$master) {
        return null;
    }

    $tier = $master['passport']['tier'] ?? 'community';
    $tiers = load_tiers();
    $tier_config = $tiers[$tier] ?? [];
    if (empty($tier_config['genome_sync'])) {
        json_error('genome_sync not available on tier: ' . $tier, 403);
    }

    return $auth_account;
}

/**
 * POST ?action=genome_push
 * Push local genome metrics to the team aggregate.
 * Input: {genome: {session_count, avg_quality, ...}}
 */
function handle_genome_push(array $auth) {
    $account_id = resolve_genome_account($auth);
    if (!$account_id) {
        json_error('Cannot determine account for genome sync', 403);
    }

    $input = get_post_data();
    $local = $input['genome'] ?? null;
    if (!is_array($local)) {
        json_error('Missing genome data in request body');
    }

    $genome_dir = __DIR__ . '/data/genomes';
    if (!is_dir($genome_dir)) {
        mkdir($genome_dir, 0755, true);
    }
    $genome_file = $genome_dir . '/' . sanitize_account_id($account_id) . '.json';

    // File-locked read-merge-write
    $fp = fopen($genome_file, 'c+');
    if (!$fp) {
        json_error('Failed to open genome file', 500);
    }
    flock($fp, LOCK_EX);

    $existing_raw = stream_get_contents($fp);
    $team = ($existing_raw && strlen($existing_raw) > 2) ? json_decode($existing_raw, true) : [];
    if (!is_array($team)) {
        $team = [];
    }

    // EMA merge: alpha * incoming + (1 - alpha) * existing
    $alpha = 0.3;
    $ema_keys = ['avg_quality', 'reliability_score', 'ami_average_quality'];
    foreach ($ema_keys as $k) {
        if (isset($local[$k])) {
            $old = isset($team[$k]) ? (float)$team[$k] : (float)$local[$k];
            $team[$k] = $alpha * (float)$local[$k] + (1.0 - $alpha) * $old;
        }
    }

    // Counters: max(team, local)
    $counter_keys = ['session_count', 'threat_scans_total', 'ami_failure_catalog_size',
                     'ami_model_profiles', 'total_turns'];
    foreach ($counter_keys as $k) {
        if (isset($local[$k])) {
            $team[$k] = max((int)($team[$k] ?? 0), (int)$local[$k]);
        }
    }

    // Models tested: union
    $team_models = $team['models_tested'] ?? [];
    $local_models = $local['models_tested'] ?? [];
    if (is_array($local_models)) {
        $team['models_tested'] = array_values(array_unique(array_merge(
            is_array($team_models) ? $team_models : [],
            $local_models
        )));
    }

    // Threat patterns: max per category
    $team_threats = $team['threat_pattern_counts'] ?? [];
    $local_threats = $local['threat_pattern_counts'] ?? [];
    if (is_array($local_threats)) {
        foreach ($local_threats as $cat => $count) {
            $team_threats[$cat] = max((int)($team_threats[$cat] ?? 0), (int)$count);
        }
        $team['threat_pattern_counts'] = $team_threats;
    }

    $team['last_push_at'] = time();
    $team['last_push_by'] = $auth['machine_id'] ?? 'unknown';

    // Write back under lock
    ftruncate($fp, 0);
    rewind($fp);
    fwrite($fp, json_encode($team, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    flock($fp, LOCK_UN);
    fclose($fp);

    json_response(['ok' => true, 'message' => 'Genome merged into team aggregate']);
}

/**
 * GET ?action=genome_pull
 * Pull the team aggregate genome for merging into local.
 */
function handle_genome_pull(array $auth) {
    $account_id = resolve_genome_account($auth);
    if (!$account_id) {
        json_error('Cannot determine account for genome sync', 403);
    }

    $genome_file = __DIR__ . '/data/genomes/' . sanitize_account_id($account_id) . '.json';
    $team = load_json($genome_file);
    if (!$team) {
        $team = [];
    }

    json_response(['ok' => true, 'genome' => $team]);
}
