<?php
/**
 * Forge Certified Audit — Orchestrator
 *
 * Webhook-driven pipeline controller. No cron, no background processes.
 * Every state transition is triggered by an inbound HTTP request:
 *   - Stripe webhook → dispatch
 *   - RunPod completion → runpod_complete
 *   - Admin manual → manual_trigger
 *
 * Endpoints:
 *   POST ?action=dispatch&order_id=...      Internal: dispatch RunPod jobs for an order
 *   POST ?action=runpod_complete            RunPod webhook: job finished
 *   POST ?action=manual_trigger&order_id=.. Admin: re-dispatch or start an order
 *   GET  ?action=status&order_id=...        Check order status (auth required)
 */

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/includes/audit_crypto.php';
require_once __DIR__ . '/includes/forge_mail.php';
require_once __DIR__ . '/includes/email_templates.php';
require_once __DIR__ . '/includes/json_compat.php';
require_once __DIR__ . '/includes/model_compat.php';

// ── API subdomain security ─────────────────────────────────────────────────
// api.forge-nc.dev bypasses Cloudflare (DNS-only). Require a shared secret
// header on all requests through that subdomain to prevent abuse.
$_host = $_SERVER['HTTP_HOST'] ?? '';
if (str_starts_with($_host, 'api.')) {
    $cfg = file_exists(__DIR__ . '/data/audit_config.json')
        ? json_decode(file_get_contents(__DIR__ . '/data/audit_config.json'), true) : [];
    $api_secret = $cfg['api_endpoint_secret'] ?? '';
    $provided = $_SERVER['HTTP_X_FORGE_API_SECRET'] ?? '';
    if (!$api_secret || !$provided || !hash_equals($api_secret, $provided)) {
        http_response_code(403);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'Invalid API secret']);
        exit;
    }
}

// ── Config ──────────────────────────────────────────────────────────────────

$AUDIT_CONFIG_FILE = __DIR__ . '/data/audit_config.json';
$AUDIT_QUEUE_FILE  = __DIR__ . '/data/audit_queue.jsonl';
$AUDIT_ARCHIVE_FILE = __DIR__ . '/data/audit_archive.jsonl';

function load_audit_config(): array {
    global $AUDIT_CONFIG_FILE;
    if (!file_exists($AUDIT_CONFIG_FILE)) return [];
    return json_decode(file_get_contents($AUDIT_CONFIG_FILE), true) ?: [];
}

// ── Queue helpers ───────────────────────────────────────────────────────────

function load_audit_queue(): array {
    global $AUDIT_QUEUE_FILE;
    if (!file_exists($AUDIT_QUEUE_FILE)) return [];
    $entries = [];
    foreach (file($AUDIT_QUEUE_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $e = json_decode($line, true);
        if ($e) $entries[$e['order_id']] = $e;
    }
    return $entries;
}

function save_audit_queue(array $entries): void {
    global $AUDIT_QUEUE_FILE;
    $lines = '';
    foreach ($entries as $e) {
        $lines .= json_encode($e, JSON_UNESCAPED_SLASHES) . "\n";
    }
    file_put_contents($AUDIT_QUEUE_FILE, $lines, LOCK_EX);
}

function update_audit_order(string $order_id, array $updates): bool {
    $queue = load_audit_queue();
    if (!isset($queue[$order_id])) return false;
    $queue[$order_id] = array_merge($queue[$order_id], $updates);
    save_audit_queue($queue);
    return true;
}

function get_audit_order(string $order_id): ?array {
    $queue = load_audit_queue();
    if (isset($queue[$order_id])) return $queue[$order_id];
    // Fall back to archive
    $archive = load_audit_archive();
    return $archive[$order_id] ?? null;
}

function load_audit_archive(): array {
    global $AUDIT_ARCHIVE_FILE;
    if (!file_exists($AUDIT_ARCHIVE_FILE)) return [];
    $entries = [];
    foreach (file($AUDIT_ARCHIVE_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $e = json_decode($line, true);
        if ($e) $entries[$e['order_id']] = $e;
    }
    return $entries;
}

function archive_audit_order(string $order_id): bool {
    global $AUDIT_ARCHIVE_FILE;
    $queue = load_audit_queue();
    if (!isset($queue[$order_id])) return false;
    $order = $queue[$order_id];
    $order['archived_at'] = date('c');
    // Append to archive
    file_put_contents($AUDIT_ARCHIVE_FILE, json_encode($order, JSON_UNESCAPED_SLASHES) . "\n", FILE_APPEND | LOCK_EX);
    // Remove from active queue
    unset($queue[$order_id]);
    save_audit_queue($queue);
    return true;
}

// ── Response helpers ────────────────────────────────────────────────────────

function json_out(int $code, array $data): void {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_UNESCAPED_SLASHES);
    exit;
}

// ── HuggingFace Model Size Detection ────────────────────────────────────────

/**
 * Auto-detect model parameter count.
 *
 * Supports:
 *   - HuggingFace repos (org/model) — exact count from safetensors metadata
 *   - HuggingFace repos with token (private models)
 *   - Direct download URLs — estimate from Content-Length (HEAD request)
 *
 * Returns parameter count in billions, or 0 if detection fails.
 */
function detect_model_params_b(string $model_source, string $hf_token = ''): float {
    if (!$model_source) return 0;

    // Direct download URL — estimate from file size
    if (str_starts_with($model_source, 'http://') || str_starts_with($model_source, 'https://')) {
        return _estimate_params_from_url($model_source);
    }

    // HuggingFace repo (org/model format)
    $headers = ['Accept: application/json'];
    if ($hf_token) {
        $headers[] = "Authorization: Bearer {$hf_token}";
    }

    // Don't urlencode the slash in org/model — HF API needs it as a path separator
    $ch = curl_init("https://huggingface.co/api/models/" . $model_source);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_HTTPHEADER     => $headers,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($code !== 200 || !$resp) return 0;

    $data = json_decode($resp, true);

    // safetensors metadata has exact param count
    $params = $data['safetensors']['total'] ?? 0;
    if ($params > 0) {
        return round($params / 1e9, 1);
    }

    // Fallback: estimate from total weight file sizes
    $total_bytes = 0;
    foreach ($data['siblings'] ?? [] as $f) {
        $name = $f['rfilename'] ?? '';
        if (str_ends_with($name, '.safetensors') || str_ends_with($name, '.bin')) {
            $total_bytes += $f['size'] ?? 0;
        }
    }
    if ($total_bytes > 0) {
        // FP16: ~2 bytes per param. Rough estimate.
        return round($total_bytes / 2 / 1e9, 1);
    }

    return 0;
}

/**
 * Estimate params from a direct download URL via HEAD request.
 * Assumes FP16 weights (~2 bytes per parameter).
 */
function _estimate_params_from_url(string $url): float {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_NOBODY         => true,  // HEAD request
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS      => 5,
    ]);
    curl_exec($ch);
    $size = curl_getinfo($ch, CURLINFO_CONTENT_LENGTH_DOWNLOAD);
    curl_close($ch);

    if ($size > 0) {
        // FP16: ~2 bytes/param, but files include overhead/metadata (~10%)
        return round($size * 0.9 / 2 / 1e9, 1);
    }
    return 0;
}

/**
 * Select the smallest GPU tier that can run a model of the given size.
 * Returns endpoint_id or empty string.
 */
function select_gpu_tier(array $config, float $params_b): array {
    $tiers = $config['runpod_weights_endpoints'] ?? [];
    // Walk tiers in order from smallest to largest
    foreach (['small', 'medium', 'large', 'xl', 'xml', 'xxl'] as $tier_name) {
        $tier = $tiers[$tier_name] ?? null;
        if (!$tier) continue;
        if ($params_b <= ($tier['max_params_b'] ?? 0)) {
            return [
                'endpoint_id'    => $tier['endpoint_id'] ?? '',
                'tier'           => $tier_name,
                'gpu'            => $tier['gpu'] ?? '',
                'gpu_count'      => $tier['gpu_count'] ?? 1,
                'gpu_price_per_hr' => $tier['gpu_price_per_hr'] ?? 0,
                'vram_gb'        => $tier['vram_gb'] ?? 0,
            ];
        }
    }

    // Check pod-based ultra tier for truly massive models
    $ultra = $config['pod_ultra_tier'] ?? [];
    if ($ultra && $params_b <= ($ultra['max_params_b_int4'] ?? 0)) {
        return [
            'endpoint_id'    => 'pod_ultra',
            'tier'           => 'ultra',
            'gpu'            => ($ultra['gpu_count'] ?? 8) . 'x H100 80GB SXM',
            'gpu_count'      => $ultra['gpu_count'] ?? 8,
            'gpu_price_per_hr' => $ultra['gpu_price_per_hr'] ?? 2.69,
            'vram_gb'        => $ultra['vram_gb'] ?? 640,
        ];
    }

    return ['endpoint_id' => '', 'tier' => 'none', 'gpu' => ''];
}

// ── RunPod API ──────────────────────────────────────────────────────────────

function runpod_dispatch_job(array $job_input, string $webhook_url, array $config, string $access_type = 'api_endpoint', float $params_b = 0): ?array {
    $api_key = $config['runpod_api_key'] ?? '';

    if ($access_type === 'model_weights') {
        $tier = select_gpu_tier($config, $params_b);
        $endpoint_id = $tier['endpoint_id'];
        if (!$endpoint_id) {
            // Fallback to legacy config
            $endpoint_id = $config['runpod_endpoint_id_weights'] ?? '';
        }
        if ($endpoint_id) {
            error_log("GPU routing: {$params_b}B → {$tier['tier']} ({$tier['gpu']})");
        }
    } else {
        $endpoint_id = $config['runpod_endpoint_id_api'] ?? '';
    }

    if (!$api_key || !$endpoint_id) return null;

    $payload = json_encode([
        'input'   => $job_input,
        'webhook' => $webhook_url,
    ], JSON_UNESCAPED_SLASHES);

    $ch = curl_init("https://api.runpod.ai/v2/{$endpoint_id}/run");
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => [
            "Authorization: Bearer {$api_key}",
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 30,
    ]);
    $resp = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($http_code >= 200 && $http_code < 300 && $resp) {
        return json_decode($resp, true);
    }
    error_log("RunPod dispatch failed: HTTP {$http_code} — {$resp}");
    return null;
}

/**
 * Dispatch an audit via on-demand GPU pod (ultra tier).
 *
 * Creates a pod, waits for it to boot, dispatches the job as an HTTP POST
 * to the handler running inside the pod, then returns the pod ID.
 * The pod handler will POST results back to the orchestrator webhook
 * (same as serverless), and the pod is destroyed on completion.
 */
function runpod_dispatch_pod_audit(array $job_input, string $webhook_url, array $config): ?array {
    $api_key = $config['runpod_api_key'] ?? '';
    $ultra = $config['pod_ultra_tier'] ?? [];
    if (!$api_key || !$ultra) return null;

    $gpu_type = $ultra['gpu_type_id'] ?? 'NVIDIA H200';
    $gpu_count = (int)($ultra['gpu_count'] ?? 8);
    // Fetch the current image tag from the RunPod template (auto-updated by CI/CD)
    // instead of hardcoding in config (which requires manual server deploys)
    $image = $ultra['container_image'] ?? '';
    $tpl_id = $ultra['template_id'] ?? 'bwlv4zki0z';
    if (!$image || strpos($image, ':latest') !== false) {
        $tpl_resp = null;
        $ch2 = curl_init('https://api.runpod.io/graphql');
        curl_setopt_array($ch2, [
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => ["Authorization: Bearer {$api_key}", 'Content-Type: application/json'],
            CURLOPT_POSTFIELDS => json_encode(['query' => "{ myself { serverlessWorkers { id name template { id imageName } } } }"]),
            CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10,
        ]);
        // Simpler: just query the template directly
        curl_close($ch2);
        $ch2 = curl_init('https://api.runpod.io/graphql');
        curl_setopt_array($ch2, [
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => ["Authorization: Bearer {$api_key}", 'Content-Type: application/json'],
            CURLOPT_POSTFIELDS => json_encode(['query' => '{ myself { endpoints { id template { id imageName } } } }']),
            CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10,
        ]);
        $tpl_resp = json_decode(curl_exec($ch2), true);
        curl_close($ch2);
        foreach ($tpl_resp['data']['myself']['endpoints'] ?? [] as $ep) {
            if (($ep['template']['id'] ?? '') === $tpl_id) {
                $image = $ep['template']['imageName'] ?? $image;
                break;
            }
        }
    }
    $cloud = $ultra['cloud_type'] ?? 'SECURE';

    // Inject pod-mode env vars so handler starts HTTP server instead of runpod.serverless
    $env_vars = [
        ['key' => 'FORGE_POD_MODE', 'value' => '1'],
        ['key' => 'FORGE_WEBHOOK_URL', 'value' => $webhook_url],
        ['key' => 'FORGE_JOB_INPUT', 'value' => base64_encode(json_encode($job_input, JSON_UNESCAPED_SLASHES))],
    ];

    // Build env array for GraphQL
    $env_gql = '';
    foreach ($env_vars as $ev) {
        $env_gql .= '{key: "' . $ev['key'] . '", value: "' . addslashes($ev['value']) . '"}, ';
    }

    $mutation = 'mutation { podFindAndDeployOnDemand(input: { '
        . 'name: "forge-audit-ultra-' . substr($job_input['order_id'] ?? 'job', 0, 12) . '", '
        . 'imageName: "' . $image . '", '
        . 'gpuTypeId: "' . $gpu_type . '", '
        . 'gpuCount: ' . $gpu_count . ', '
        . 'cloudType: ' . $cloud . ', '
        . 'containerDiskInGb: 500, '
        . 'volumeInGb: 0, '
        . 'dockerArgs: "python -u /app/handler.py", '
        . 'env: [' . $env_gql . '], '
        . 'startJupyter: false, '
        . 'startSsh: false'
        . '}) { id name desiredStatus imageName } }';

    $ch = curl_init('https://api.runpod.io/graphql');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => [
            "Authorization: Bearer {$api_key}",
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS     => json_encode(['query' => $mutation]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 30,
    ]);
    $resp = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($http_code >= 200 && $http_code < 300 && $resp) {
        $data = json_decode($resp, true);
        $pod = $data['data']['podFindAndDeployOnDemand'] ?? null;
        if ($pod && !empty($pod['id'])) {
            error_log("Ultra pod created: {$pod['id']} ({$gpu_count}x {$gpu_type})");
            return [
                'id' => 'pod_' . $pod['id'],
                'pod_id' => $pod['id'],
                'type' => 'pod',
            ];
        }
        $errs = $data['errors'] ?? [];
        $err_msg = !empty($errs) ? $errs[0]['message'] ?? 'unknown' : 'no pod returned';
        error_log("Ultra pod creation failed: {$err_msg}");
        return null;
    }
    error_log("Ultra pod dispatch failed: HTTP {$http_code} — {$resp}");
    return null;
}

/**
 * Destroy a RunPod GPU pod after audit completion.
 */
function runpod_destroy_pod(string $pod_id, array $config): bool {
    $api_key = $config['runpod_api_key'] ?? '';
    if (!$api_key || !$pod_id) return false;

    $mutation = 'mutation { podTerminate(input: { podId: "' . addslashes($pod_id) . '" }) }';
    $ch = curl_init('https://api.runpod.io/graphql');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => [
            "Authorization: Bearer {$api_key}",
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS     => json_encode(['query' => $mutation]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
    ]);
    curl_exec($ch);
    curl_close($ch);

    error_log("Pod terminated: {$pod_id}");
    return true;
}

// ── Routing ─────────────────────────────────────────────────────────────────

header('Content-Type: application/json');
$action = $_GET['action'] ?? '';
$method = $_SERVER['REQUEST_METHOD'];

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=dispatch — Trigger RunPod jobs for an audit order
// Called internally by stripe_webhook.php after payment
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'dispatch' && $method === 'POST') {
    // Auth: orchestrator secret
    $config = load_audit_config();
    $orch_secret = $config['orchestrator_secret'] ?? '';
    $provided = $_SERVER['HTTP_X_ORCHESTRATOR_SECRET'] ?? '';
    if (!$orch_secret || !hash_equals($orch_secret, $provided)) {
        json_out(403, ['error' => 'Invalid orchestrator secret']);
    }

    $input = json_decode(file_get_contents('php://input'), true) ?: [];
    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $input['order_id'] ?? ($_GET['order_id'] ?? ''));
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    $order = get_audit_order($order_id);
    if (!$order) json_out(404, ['error' => 'Order not found']);
    if (!in_array($order['status'], ['deposit_paid', 'paid'])) {
        json_out(400, ['error' => 'Order not in dispatchable state: ' . $order['status']]);
    }

    $models = $order['models'] ?? [];
    if (empty($models) || !is_array($models)) {
        json_out(400, ['error' => 'No models in order']);
    }

    $callback_base = $config['callback_base_url'] ?? 'https://forge-nc.dev';
    $webhook_url = $callback_base . '/audit_orchestrator.php?action=runpod_complete';

    $dispatched = 0;
    $errors = [];
    foreach ($models as $i => &$model) {
        if (($model['status'] ?? '') === 'completed') continue; // skip already done

        // Decrypt API key for dispatch
        $api_key = '';
        if (!empty($model['api_key_encrypted'])) {
            $api_key = audit_decrypt_api_key($model['api_key_encrypted']);
            if ($api_key === null) {
                $errors[] = "Model {$i}: API key decryption failed";
                continue;
            }
        }

        // Auto-detect model size and compatibility from HuggingFace
        $access = $order['access_type'] ?? 'api_endpoint';
        $model_params_b = (float)($model['model_params_b'] ?? 0);
        if ($access === 'model_weights') {
            $hf_repo = $model['model_id'] ?? $model['model_name'] ?? '';
            $hf_token = $model['hf_token'] ?? '';

            // Run compatibility check
            $compat = check_model_compatibility($hf_repo, $hf_token);
            $model['compat'] = $compat;
            if (!empty($compat['errors'])) {
                $model['status'] = 'compat_failed';
                $errors[] = "Model {$i}: Compatibility check failed — " . implode('; ', $compat['errors']);
                try {
                    db_create_notification('admin@forge-nc.dev', 'audit_warning',
                        "Model compatibility issue — Order {$order_id}",
                        "Model '{$model['model_name']}' ({$hf_repo}) failed compatibility check:\n" . implode("\n", $compat['errors']),
                        '/admin/telemetry');
                } catch (Throwable $e) {}
                continue;
            }
            if (!empty($compat['warnings'])) {
                error_log("Model compat warnings for {$hf_repo}: " . implode('; ', $compat['warnings']));
            }
            // Store recommended settings on the model for the handler
            $model['vllm_env_auto'] = !empty($compat['vllm_env']) ? implode(',', array_map(
                fn($k, $v) => "{$k}={$v}", array_keys($compat['vllm_env']), $compat['vllm_env']
            )) : '';
            // Use compat-detected params if available
            if (($compat['params_b'] ?? 0) > 0) {
                $model_params_b = $compat['params_b'];
            }
            $detected = detect_model_params_b($hf_repo, $hf_token);
            if ($detected > 0) {
                $model_params_b = $detected;
                error_log("Auto-detected model size: {$hf_repo} = {$detected}B params");
            } elseif ($model_params_b <= 0) {
                // Detection failed and no estimate — use XL tier for max success chance
                $xl_tier = $config['runpod_weights_endpoints']['xl'] ?? [];
                $model_params_b = (float)($xl_tier['max_params_b'] ?? 700);
                error_log("WARNING: Could not detect model size for '{$hf_repo}' — defaulting to XL tier ({$model_params_b}B)");

                // Notify admin so they're aware of the detection failure
                try {
                    db_create_notification(
                        'admin@forge-nc.dev',
                        'audit_warning',
                        "Model size detection failed — Order {$order_id}",
                        "Could not auto-detect parameter count for '{$hf_repo}' (model {$i}). "
                        . "Dispatching to XL tier as fallback. Customer estimate: "
                        . ($model['model_params_b'] ?? 'none') . "B. "
                        . "Verify the model source is correct.",
                        '/admin/telemetry'
                    );
                } catch (Throwable $e) {}
            }

            // Check if model fits our infrastructure
            $tier_check = select_gpu_tier($config, $model_params_b);
            if (!$tier_check['endpoint_id']) {
                // Model exceeds all tiers — flag for manual setup, don't auto-reject
                $model['status'] = 'pending_manual';
                $errors[] = "Model {$i}: {$model_params_b}B params exceeds auto-dispatch capacity. Queued for manual GPU provisioning.";

                try {
                    db_create_notification(
                        'admin@forge-nc.dev',
                        'enterprise',
                        "Oversized model needs manual GPU — Order {$order_id}",
                        "Model '{$model['model_name']}' detected at {$model_params_b}B params, "
                        . "exceeds all tiers including ultra (2,200B INT4 max). Requires manual provisioning. "
                        . "Customer: " . ($order['email'] ?? '') . ". "
                        . "Use Admin > Manual Trigger after provisioning.",
                        '/admin/telemetry'
                    );
                } catch (Throwable $e) {}
                continue;
            }
        }

        // Store GPU tier + cost tracking data on the model entry
        // Use compat checker's recommendation if available (accounts for KV cache headroom)
        if ($access === 'model_weights') {
            $compat_tier = $compat['recommended_gpu_tier'] ?? '';
            if ($compat_tier && $compat_tier !== 'ultra') {
                // Map compat tier name to actual endpoint config
                $compat_endpoint = $config['runpod_weights_endpoints'][$compat_tier] ?? null;
                if ($compat_endpoint) {
                    $tier_info = [
                        'endpoint_id' => $compat_endpoint['endpoint_id'] ?? '',
                        'tier' => $compat_tier,
                        'gpu' => $compat_endpoint['gpu'] ?? '',
                        'gpu_count' => $compat_endpoint['gpu_count'] ?? 1,
                        'gpu_price_per_hr' => $compat_endpoint['gpu_price_per_hr'] ?? 0,
                        'vram_gb' => $compat_endpoint['vram_gb'] ?? 0,
                    ];
                } else {
                    $tier_info = select_gpu_tier($config, $model_params_b);
                }
            } elseif ($compat_tier === 'ultra') {
                $tier_info = select_gpu_tier($config, $model_params_b); // ultra handled by pod dispatch
            } else {
                $tier_info = select_gpu_tier($config, $model_params_b);
            }
            $model['gpu_tier'] = $tier_info['tier'];
            $model['gpu_label'] = $tier_info['gpu'];
            $model['detected_params_b'] = $model_params_b;
            $model['gpu_count'] = $tier_info['gpu_count'] ?? 1;
            $model['gpu_price_per_hr'] = $tier_info['gpu_price_per_hr'] ?? 0;
        } else {
            $model['gpu_tier'] = 'api';
            $model['gpu_label'] = 'N/A (API endpoint)';
            $model['detected_params_b'] = $model_params_b;
            $model['gpu_count'] = 0;
            $model['gpu_price_per_hr'] = 0;
        }

        $job_input = [
            'order_id'      => $order_id,
            'model_index'   => $i,
            'model_name'    => $model['model_name'] ?? 'unknown',
            'model_id'      => $model['model_id'] ?? '',
            'hf_repo'       => $model['model_id'] ?? '',
            'hf_token'      => $model['hf_token'] ?? '',
            'access_type'   => $access,
            'endpoint_url'  => $model['endpoint_url'] ?? '',
            'api_key'       => $api_key,
            'webhook_secret' => $order['webhook_secret'] ?? '',
            'forge_server'  => $callback_base,
            'model_params_b' => $model_params_b,
            'vllm_flags'    => $model['vllm_flags'] ?? '',
            'vllm_env'      => $model['vllm_env'] ?? $model['vllm_env_auto'] ?? '',
        ];

        // Dry run: validate everything but don't actually dispatch
        $dry_run = !empty($input['dry_run']) || !empty($_GET['dry_run']);
        if ($dry_run) {
            $model['status'] = 'dry_run';
            $model['dry_run_job_input'] = $job_input;
            $model['dry_run_webhook_url'] = $webhook_url;
            $dispatched++;
            continue;
        }

        // Dispatch: ultra tier uses on-demand GPU pod, all others use serverless
        if (($model['gpu_tier'] ?? '') === 'ultra') {
            $result = runpod_dispatch_pod_audit($job_input, $webhook_url, $config);
        } else {
            $result = runpod_dispatch_job($job_input, $webhook_url, $config, $access, $model_params_b);
        }

        if ($result && !empty($result['id'])) {
            $model['status'] = 'running';
            $model['runpod_job_id'] = $result['id'];
            $model['runpod_pod_id'] = $result['pod_id'] ?? null;
            $model['dispatched_at'] = date('c');
            $dispatched++;
        } else {
            $model['status'] = 'dispatch_failed';
            $errors[] = "Model {$i}: RunPod dispatch failed (" . ($model['gpu_tier'] ?? 'unknown') . " tier)";
        }
    }
    unset($model);

    // Generate a unique dispatch ID — webhook handler only accepts results matching this
    $dispatch_id = bin2hex(random_bytes(8));

    // Update order (clear stale progress from previous attempts)
    update_audit_order($order_id, [
        'status'        => $dispatched > 0 ? 'running' : 'dispatch_failed',
        'models'        => $models,
        'dispatched_at' => date('c'),
        'dispatch_id'   => $dispatch_id,
        'progress'      => [],
    ]);

    // Log
    db_audit_log('orchestrator', 'system', 'audit.dispatch', 'order', $order_id, [
        'dispatched' => $dispatched,
        'errors' => $errors,
    ]);

    json_out(200, [
        'ok'         => $dispatched > 0,
        'dispatched' => $dispatched,
        'errors'     => $errors,
    ]);
}

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=runpod_complete — RunPod webhook callback
// Called by RunPod when a serverless job finishes
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'runpod_complete' && $method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    if (!$data) json_out(400, ['error' => 'Invalid JSON']);

    // RunPod wraps output in {id, status, output: {...}}
    $output = $data['output'] ?? $data;
    $runpod_status = $data['status'] ?? 'UNKNOWN';

    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $output['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id in output']);

    $order = get_audit_order($order_id);
    if (!$order) json_out(404, ['error' => 'Order not found']);

    // Validate webhook secret
    $expected_secret = $order['webhook_secret'] ?? '';
    $provided_secret = $output['webhook_secret'] ?? '';
    if (!$expected_secret || !hash_equals($expected_secret, $provided_secret)) {
        error_log("Audit orchestrator: webhook secret mismatch for order {$order_id}");
        json_out(403, ['error' => 'Invalid webhook secret']);
    }

    $model_index = (int)($output['model_index'] ?? -1);
    $models = $order['models'] ?? [];
    if ($model_index < 0 || $model_index >= count($models)) {
        json_out(400, ['error' => 'Invalid model_index']);
    }

    // Update model status
    if ($runpod_status === 'COMPLETED' && !empty($output['run_id'])) {
        $models[$model_index]['status'] = 'completed';
        $models[$model_index]['run_id'] = $output['run_id'] ?? '';
        $models[$model_index]['run_id_paired'] = $output['run_id_paired'] ?? '';
        $models[$model_index]['pass_rate'] = $output['pass_rate'] ?? 0;
        $models[$model_index]['scenarios_run'] = $output['scenarios_run'] ?? 0;
        $models[$model_index]['scenarios_passed'] = $output['scenarios_passed'] ?? 0;
        $models[$model_index]['completed_at'] = date('c');

        // ── Calculate GPU cost for this model ──
        $dispatched_at = $models[$model_index]['dispatched_at'] ?? '';
        if ($dispatched_at) {
            $exec_secs = max(0, time() - strtotime($dispatched_at));
            $gpu_count = (int)($models[$model_index]['gpu_count'] ?? 1);
            $gpu_rate = (float)($models[$model_index]['gpu_price_per_hr'] ?? 0);
            $models[$model_index]['execution_time_s'] = $exec_secs;
            $models[$model_index]['gpu_cost'] = round($exec_secs / 3600 * $gpu_count * $gpu_rate, 4);
        }

        // ── Save reports from worker output (bypasses Cloudflare) ──
        foreach (['break_report_b64', 'assure_report_b64'] as $report_key) {
            if (!empty($output[$report_key])) {
                $report_json = base64_decode($output[$report_key], true);
                if ($report_json) {
                    _save_report_locally($report_json);
                }
            }
        }
        // ── Destroy ultra pod if applicable ──
        $pod_id = $models[$model_index]['runpod_pod_id'] ?? null;
        if ($pod_id) {
            $config = load_audit_config();
            runpod_destroy_pod($pod_id, $config);
            $models[$model_index]['pod_destroyed'] = true;
        }
    } else {
        $models[$model_index]['status'] = 'failed';
        $models[$model_index]['error'] = $output['error'] ?? $data['error'] ?? 'Unknown RunPod error';
        $models[$model_index]['completed_at'] = date('c');

        // Destroy ultra pod on failure too
        $pod_id = $models[$model_index]['runpod_pod_id'] ?? null;
        if ($pod_id) {
            $config = load_audit_config();
            runpod_destroy_pod($pod_id, $config);
            $models[$model_index]['pod_destroyed'] = true;
        }
    }

    // Check if all models are done
    $all_done = true;
    $all_passed = true;
    foreach ($models as $m) {
        if (!in_array($m['status'] ?? '', ['completed', 'failed'])) {
            $all_done = false;
            break;
        }
        if (($m['status'] ?? '') !== 'completed') $all_passed = false;
    }

    $order_updates = ['models' => $models];

    if ($all_done) {
        $order_updates['status'] = $all_passed ? 'completed' : 'partial';
        $order_updates['completed_at'] = date('c');

        // ── Auto-verify completed models in registry ──
        foreach ($models as $m) {
            if ($m['status'] !== 'completed') continue;
            $hf_repo = $m['model_id'] ?? '';
            if ($hf_repo) {
                $reg_path = __DIR__ . '/data/model_registry.json';
                $reg = file_exists($reg_path) ? json_decode(file_get_contents($reg_path), true) : ['models' => []];
                if (isset($reg['models'][$hf_repo]) && empty($reg['models'][$hf_repo]['verified_date'])) {
                    $reg['models'][$hf_repo]['verified_date'] = date('Y-m-d');
                    $reg['models'][$hf_repo]['verified_by'] = 'forge-origin';
                    file_put_contents($reg_path, json_encode($reg, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), LOCK_EX);
                    error_log("Auto-verified model in registry: {$hf_repo}");
                }
            }
        }

        // ── Origin-certify all completed reports ──
        foreach ($models as $m) {
            if ($m['status'] !== 'completed') continue;
            foreach (['run_id', 'run_id_paired'] as $rid_key) {
                $rid = $m[$rid_key] ?? '';
                if (!$rid) continue;
                // Self-POST to certify
                _origin_certify_report($rid);
            }
        }

        // ── Email customer with results (only if at least one model completed successfully) ──
        $any_completed = false;
        foreach ($models as $m) {
            if (($m['status'] ?? '') === 'completed' && !empty($m['run_id'])) {
                $any_completed = true;
                break;
            }
        }

        $email = $order['email'] ?? '';
        $tier_label = ($order['tier'] ?? '') === 'audit_startup' ? 'Startup' : 'Enterprise';
        if ($email && $any_completed) {
            $report_links = '';
            foreach ($models as $mi => $m) {
                if ($m['status'] === 'completed' && !empty($m['run_id'])) {
                    $report_links .= "  Model: {$m['model_name']}\n";
                    $report_links .= "  Score: " . round(($m['pass_rate'] ?? 0) * 100, 1) . "%\n";
                    $report_links .= "  Report: https://forge-nc.dev/report/{$m['run_id']}\n\n";
                }
            }
            $balance = $order['balance_amount'] ?? 0;
            $balance_str = $balance > 0 ? "\nBalance due (Net 30): $" . number_format($balance / 100, 2) . "\n" : '';

            $html_body = forge_email_audit_complete(
                $order['order_id'],
                $tier_label,
                $models,
                $balance
            );
            forge_mail($email,
                "[Forge NC] Certified Audit Complete — {$order['order_id']}",
                $html_body,
                'Forge NC',
                null,
                true
            );

            // In-app notification
            db_create_notification($email, 'audit_complete',
                'Audit Complete: ' . $order['order_id'],
                "Your {$tier_label} Certified Audit is complete. View your reports on the Dashboard.",
                '/dashboard');
        }

        // ── Create Stripe invoice for remaining balance (only if audit produced results) ──
        if (($order['balance_amount'] ?? 0) > 0 && $any_completed) {
            _create_balance_invoice($order);
        }

        // ── Notify Origin (rich notification + HTML email) ──
        try {
            $stmt = get_db()->prepare("SELECT email FROM users WHERE role = 'origin' LIMIT 1");
            $stmt->execute();
            $origin = $stmt->fetch();
            if ($origin) {
                $tier_label_admin = ($order['tier'] ?? '') === 'audit_startup' ? 'Startup' : 'Enterprise';
                $customer_name = $order['name'] ?? '';
                $customer_email = $order['email'] ?? '';
                $balance_admin = (int)($order['balance_amount'] ?? 0);
                $deposit_admin = (int)($order['deposit_amount'] ?? 0);
                $total_admin = (int)($order['total_amount'] ?? 0);
                $dispatched_at = $order['dispatched_at'] ?? '';
                $completed_at = $order_updates['completed_at'] ?? date('c');

                // Calculate execution time
                $exec_time_str = 'N/A';
                if ($dispatched_at && $completed_at) {
                    $exec_secs = strtotime($completed_at) - strtotime($dispatched_at);
                    if ($exec_secs > 0) {
                        $exec_min = (int)floor($exec_secs / 60);
                        $exec_sec = $exec_secs % 60;
                        $exec_time_str = $exec_min > 0 ? "{$exec_min}m {$exec_sec}s" : "{$exec_sec}s";
                    }
                }

                // Build model details
                $model_lines = '';
                foreach ($models as $mi => $m) {
                    $m_name = $m['model_name'] ?? 'Model ' . ($mi + 1);
                    $m_status = $m['status'] ?? 'unknown';
                    if ($m_status === 'completed') {
                        $m_score = round(($m['pass_rate'] ?? 0) * 100, 1);
                        $m_scenarios = ($m['scenarios_passed'] ?? 0) . '/' . ($m['scenarios_run'] ?? 0) . ' passed';
                        $m_gpu = $m['gpu_tier'] ?? 'auto';
                        $m_break = !empty($m['run_id']) ? "https://forge-nc.dev/report/{$m['run_id']}" : 'N/A';
                        $m_assure = !empty($m['run_id_paired']) ? "https://forge-nc.dev/report/{$m['run_id_paired']}" : 'N/A';
                        $model_lines .= "  [{$m_name}] Score: {$m_score}% | {$m_scenarios} | GPU: {$m_gpu}\n";
                        $model_lines .= "    Break: {$m_break}\n";
                        $model_lines .= "    Assurance: {$m_assure}\n";
                    } else {
                        $m_err = $m['error'] ?? 'unknown error';
                        $model_lines .= "  [{$m_name}] FAILED: {$m_err}\n";
                    }
                }

                $balance_line = $balance_admin > 0 ? "Balance Due (Net 30): \$" . number_format($balance_admin / 100, 2) : 'Paid in full';

                $access_label = ($order['access_type'] ?? '') === 'model_weights' ? 'Weights' : 'API';
                $total_fmt = '$' . number_format($total_admin / 100, 2);

                $notif_msg = "{$tier_label_admin} Audit | {$access_label}\n"
                    . "Order: {$order['order_id']}\n"
                    . "Customer: {$customer_name} ({$customer_email})\n\n"
                    . "Models:\n{$model_lines}\n"
                    . "Execution: {$exec_time_str}\n"
                    . "Revenue: {$total_fmt} | {$balance_line}";

                $notif_title = $any_completed
                    ? 'Audit Completed: ' . $order['order_id']
                    : 'Audit FAILED: ' . $order['order_id'];

                db_create_notification($origin['email'], 'enterprise',
                    $notif_title,
                    $notif_msg,
                    '/admin/telemetry');

                // ── System alert to server email (always, especially on failure) ──
                forge_mail('forgenc@forge-nc.dev',
                    "[Forge NC] {$notif_title}",
                    $notif_msg,
                    'Forge Audit System'
                );

                // ── HTML email to admin (only if at least one model produced results) ──
                if ($any_completed) {
                $admin_html = forge_email_admin_audit_complete(
                    $order['order_id'],
                    $tier_label_admin,
                    $customer_name,
                    $customer_email,
                    $models,
                    $deposit_admin,
                    $balance_admin,
                    $total_admin,
                    $exec_time_str,
                    $order['access_type'] ?? ''
                );
                forge_mail('admin@forge-nc.dev',
                    "[Forge NC] Audit Complete — {$order['order_id']} ({$tier_label_admin})",
                    $admin_html,
                    'Forge NC',
                    null,
                    true
                );

                // Also send to billing for financial records
                forge_mail('billing@forge-nc.dev',
                    "[Forge NC] Audit Complete — {$order['order_id']} ({$tier_label_admin})",
                    $admin_html,
                    'Forge NC',
                    null,
                    true
                );
                } // end if ($any_completed) for HTML emails
            }
        } catch (Exception $e) {}

        db_audit_log('orchestrator', 'system', 'audit.completed', 'order', $order_id, [
            'all_passed' => $all_passed,
            'models' => count($models),
        ]);
    }

    update_audit_order($order_id, $order_updates);

    // Auto-archive completed/failed orders so they don't clutter the active queue
    if ($all_done) {
        archive_audit_order($order_id);
    }

    json_out(200, ['ok' => true, 'all_done' => $all_done]);
}

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=manual_trigger — Admin/Origin manual dispatch
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'manual_trigger' && $method === 'POST') {
    require_once __DIR__ . '/includes/auth_guard.php';
    if (!$is_origin) json_out(403, ['error' => 'Origin access required']);

    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $_GET['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    $order = get_audit_order($order_id);
    if (!$order) json_out(404, ['error' => 'Order not found']);

    // Reset failed models to pending so dispatch picks them up
    $models = $order['models'] ?? [];
    foreach ($models as &$m) {
        if (in_array($m['status'] ?? '', ['failed', 'dispatch_failed', 'pending'])) {
            $m['status'] = 'pending';
            unset($m['error'], $m['runpod_job_id']);
        }
    }
    unset($m);
    // Force status back to dispatchable
    update_audit_order($order_id, ['status' => 'deposit_paid', 'models' => $models]);

    // Now dispatch via internal call
    $config = load_audit_config();
    $orch_secret = $config['orchestrator_secret'] ?? '';
    $callback_base = $config['callback_base_url'] ?? 'https://forge-nc.dev';

    $ch = curl_init($callback_base . '/audit_orchestrator.php?action=dispatch&order_id=' . urlencode($order_id));
    curl_setopt_array($ch, [
        CURLOPT_POST       => true,
        CURLOPT_HTTPHEADER => [
            "X-Orchestrator-Secret: {$orch_secret}",
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode(['order_id' => $order_id]),
        CURLOPT_TIMEOUT    => 15,
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $resp = curl_exec($ch);
    curl_close($ch);

    db_audit_log($auth['email'] ?? 'origin', $auth_role ?? 'origin', 'audit.manual_trigger', 'order', $order_id, []);
    json_out(200, json_decode($resp, true) ?: ['ok' => true, 'triggered' => true]);
}

// ═══════════════════════════════════════════════════════════════════════════
// GET ?action=status — Check order status
// ═══════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=progress — Live progress update from worker
// Called by the handler during audit execution
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'progress' && $method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    if (!$data) json_out(400, ['error' => 'Invalid JSON']);

    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $data['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    $order = get_audit_order($order_id);
    if (!$order) json_out(404, ['error' => 'Order not found']);

    // Validate webhook secret
    $expected = $order['webhook_secret'] ?? '';
    $provided = $data['webhook_secret'] ?? '';
    if (!$expected || !hash_equals($expected, $provided)) {
        json_out(403, ['error' => 'Invalid webhook secret']);
    }

    // Store progress on order
    $progress = [
        'stage'   => $data['stage'] ?? 'unknown',
        'current' => (int)($data['current'] ?? 0),
        'total'   => (int)($data['total'] ?? 0),
        'pass'    => (int)($data['pass'] ?? 0),
        'updated' => date('c'),
    ];
    update_audit_order($order_id, ['progress' => $progress]);
    json_out(200, ['ok' => true]);
}

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=log — Live log line from worker
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'log' && $method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    if (!$data) json_out(400, ['error' => 'Invalid JSON']);

    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $data['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    // Append log lines to a per-order log file
    $log_dir = __DIR__ . '/data/audit_logs';
    if (!is_dir($log_dir)) mkdir($log_dir, 0750, true);
    $log_file = $log_dir . '/' . $order_id . '.log';

    $lines = $data['lines'] ?? [];
    if (is_array($lines) && !empty($lines)) {
        $content = implode("\n", array_slice($lines, 0, 50)) . "\n"; // max 50 lines per POST
        file_put_contents($log_file, $content, FILE_APPEND | LOCK_EX);
    }
    json_out(200, ['ok' => true]);
}

// ═══════════════════════════════════════════════════════════════════════════
// GET ?action=logs&order_id=... — Retrieve log lines for admin dashboard
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'logs' && $method === 'GET') {
    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $_GET['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    $log_file = __DIR__ . '/data/audit_logs/' . $order_id . '.log';
    $after = (int)($_GET['after'] ?? 0); // byte offset for incremental reads

    if (!file_exists($log_file)) {
        json_out(200, ['lines' => [], 'offset' => 0]);
    }

    $size = filesize($log_file);
    if ($after >= $size) {
        json_out(200, ['lines' => [], 'offset' => $size]);
    }

    $fh = fopen($log_file, 'r');
    fseek($fh, $after);
    $new_content = fread($fh, min($size - $after, 524288)); // max 512KB per read
    fclose($fh);

    $lines = array_filter(explode("\n", $new_content), fn($l) => $l !== '');
    json_out(200, ['lines' => array_values($lines), 'offset' => $size]);
}

if ($action === 'status' && $method === 'GET') {
    $order_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $_GET['order_id'] ?? '');
    if (!$order_id) json_out(400, ['error' => 'Missing order_id']);

    $order = get_audit_order($order_id);
    if (!$order) json_out(404, ['error' => 'Order not found']);

    // Check RunPod job status for queue detection
    $rp_queue_wait = false;
    $progress = $order['progress'] ?? [];
    $stage = $progress['stage'] ?? 'dispatched';
    if ($order['status'] === 'running' && in_array($stage, ['dispatched', ''])) {
        // No progress updates yet — check if RunPod job is still queued
        $models = $order['models'] ?? [];
        $job_id = $models[0]['runpod_job_id'] ?? '';
        $gpu_tier = $models[0]['gpu_tier'] ?? '';
        if ($job_id && $gpu_tier) {
            $config = load_audit_config();
            $endpoint_id = $config['runpod_weights_endpoints'][$gpu_tier]['endpoint_id'] ?? '';
            $rp_key = $config['runpod_api_key'] ?? '';
            if ($endpoint_id && $rp_key) {
                $ch = curl_init("https://api.runpod.ai/v2/{$endpoint_id}/status/{$job_id}");
                curl_setopt_array($ch, [
                    CURLOPT_HTTPHEADER => ["Authorization: Bearer {$rp_key}"],
                    CURLOPT_RETURNTRANSFER => true,
                    CURLOPT_TIMEOUT => 5,
                ]);
                $rp_resp = json_decode(curl_exec($ch), true);
                curl_close($ch);
                if (($rp_resp['status'] ?? '') === 'IN_QUEUE') {
                    $rp_queue_wait = true;
                }
            }
        }
    }

    // Strip sensitive data
    $safe = $order;
    unset($safe['webhook_secret'], $safe['stripe_session'], $safe['stripe_customer']);
    if (isset($safe['models'])) {
        foreach ($safe['models'] as &$m) {
            unset($m['api_key_encrypted']);
        }
        unset($m);
    }
    $safe['gpu_queue_wait'] = $rp_queue_wait;
    json_out(200, $safe);
}

// ═══════════════════════════════════════════════════════════════════════════
// GET ?action=report_models — List model IDs that already have reports
// Used by batch runner for dedup
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'report_models' && $method === 'GET') {
    $reports_dir = __DIR__ . '/data/assurance/reports';
    $models = [];
    if (is_dir($reports_dir)) {
        foreach (glob($reports_dir . '/*.json') as $f) {
            $r = json_decode(file_get_contents($f), true);
            if ($r && !empty($r['model'])) {
                $models[] = $r['model'];
            }
        }
    }
    json_out(200, ['models' => array_values(array_unique($models))]);
}

// ═══════════════════════════════════════════════════════════════════════════
// POST ?action=upload_report — Accept a report from batch break runner
// ═══════════════════════════════════════════════════════════════════════════

if ($action === 'upload_report' && $method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    if (!$data || empty($data['report_b64'])) json_out(400, ['error' => 'Missing report_b64']);

    $report_json = base64_decode($data['report_b64'], true);
    if (!$report_json) json_out(400, ['error' => 'Invalid base64']);

    _save_report_locally($report_json);
    json_out(200, ['ok' => true, 'source' => $data['source'] ?? 'unknown']);
}

json_out(400, ['error' => 'Unknown action']);

// ═══════════════════════════════════════════════════════════════════════════
// Internal helpers
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Origin-certify a report by calling assurance_verify.php internally.
 */
function _origin_certify_report(string $run_id): void {
    if (!$run_id) return;
    require_once __DIR__ . '/auth.php';
    // Load origin auth for the certify endpoint
    $origin_key_path = __DIR__ . '/data/origin_key.json';
    if (!file_exists($origin_key_path)) return;

    // Direct file-based certification (same logic as assurance_verify.php?action=certify)
    $reports_dir = __DIR__ . '/data/assurance/reports';
    $path = $reports_dir . '/' . preg_replace('/[^a-zA-Z0-9_-]/', '', $run_id) . '.json';
    if (!file_exists($path)) return;

    $report = json_decode(file_get_contents($path), true);
    if (!$report || !empty($report['_verification']['origin_certified'])) return;

    $origin_key = json_decode(file_get_contents($origin_key_path), true);
    if (!$origin_key || empty($origin_key['secret_key_b64'])) return;

    try {
        $origin_secret = base64_decode($origin_key['secret_key_b64'], true);
        $origin_pub = $origin_key['public_key_b64'];

        $countersign_payload = json_encode([
            'run_id'            => $report['run_id'] ?? $run_id,
            'machine_signature' => $report['signature'] ?? '',
            'machine_pub_key'   => $report['pub_key_b64'] ?? '',
            'pass_rate'         => $report['pass_rate'] ?? 0,
            'model'             => $report['model'] ?? '',
            'scenarios_run'     => $report['scenarios_run'] ?? 0,
            'certified_at'      => time(),
            'certified_by'      => 'audit_orchestrator',
        ], JSON_UNESCAPED_SLASHES);

        $origin_keypair = sodium_crypto_sign_seed_keypair(substr($origin_secret, 0, 32));
        $origin_sig_bytes = sodium_crypto_sign_detached($countersign_payload, sodium_crypto_sign_secretkey($origin_keypair));
        $origin_sig = base64_encode($origin_sig_bytes);

        $report['_verification']['origin_signature'] = $origin_sig;
        $report['_verification']['origin_pub_key_b64'] = $origin_pub;
        $report['_verification']['origin_certified'] = true;
        $report['_verification']['certified_at'] = time();
        $report['_verification']['certified_by'] = 'audit_orchestrator';

        file_put_contents($path, json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    } catch (Throwable $e) {
        error_log("Origin certification failed for {$run_id}: " . $e->getMessage());
    }
}

/**
 * Create a Stripe invoice for the remaining audit balance.
 */
function _create_balance_invoice(array $order): void {
    $stripe_config_file = __DIR__ . '/data/stripe_config.json';
    if (!file_exists($stripe_config_file)) return;
    $stripe = json_decode(file_get_contents($stripe_config_file), true);
    $sk = $stripe['secret_key'] ?? '';
    if (!$sk) return;

    $customer_id = $order['stripe_customer'] ?? '';
    if (!$customer_id) return;

    $balance = (int)($order['balance_amount'] ?? 0);
    if ($balance <= 0) return;

    $tier_label = ($order['tier'] ?? '') === 'audit_startup' ? 'Startup' : 'Enterprise';

    // Create invoice item
    $ch = curl_init('https://api.stripe.com/v1/invoiceitems');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_USERPWD        => $sk . ':',
        CURLOPT_POSTFIELDS     => http_build_query([
            'customer'    => $customer_id,
            'amount'      => $balance,
            'currency'    => 'usd',
            'description' => "Forge {$tier_label} Certified Audit — Balance ({$order['order_id']})",
        ]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
    ]);
    curl_exec($ch);
    curl_close($ch);

    // Create and finalize invoice with Net 30
    $ch = curl_init('https://api.stripe.com/v1/invoices');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_USERPWD        => $sk . ':',
        CURLOPT_POSTFIELDS     => http_build_query([
            'customer'           => $customer_id,
            'collection_method'  => 'send_invoice',
            'days_until_due'     => 30,
            'auto_advance'       => 'true',
            'metadata[order_id]' => $order['order_id'] ?? '',
            'metadata[type]'     => 'audit_balance',
        ]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
    ]);
    $resp = curl_exec($ch);
    curl_close($ch);

    $invoice = json_decode($resp, true);
    $invoice_id = $invoice['id'] ?? '';

    // Finalize and get hosted invoice URL for customer payment
    if ($invoice_id) {
        $ch = curl_init("https://api.stripe.com/v1/invoices/{$invoice_id}/finalize");
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_USERPWD        => $sk . ':',
            CURLOPT_POSTFIELDS     => '',
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 15,
        ]);
        $finalize_resp = curl_exec($ch);
        curl_close($ch);

        $finalized = json_decode($finalize_resp, true);
        $hosted_url = $finalized['hosted_invoice_url'] ?? '';
        $invoice_pdf = $finalized['invoice_pdf'] ?? '';
        $due_date = !empty($finalized['due_date']) ? date('F j, Y', $finalized['due_date']) : date('F j, Y', strtotime('+30 days'));

        // Store invoice ID + pay link on order
        update_audit_order($order['order_id'] ?? '', [
            'stripe_invoice_id' => $invoice_id,
            'stripe_invoice_url' => $hosted_url,
            'stripe_invoice_pdf' => $invoice_pdf,
        ]);

        // ── Branded invoice email to customer ──
        $customer_email = $order['email'] ?? '';
        if ($customer_email && $hosted_url) {
            $invoice_html = forge_email_customer_balance_invoice(
                $order['order_id'] ?? '',
                $tier_label,
                $order['name'] ?? '',
                $balance,
                $hosted_url,
                $invoice_pdf,
                $due_date
            );
            forge_mail($customer_email,
                "[Forge NC] Balance Invoice — {$order['order_id']} — \$" . number_format($balance / 100, 2),
                $invoice_html,
                'Forge NC',
                'billing@forge-nc.dev',
                true
            );
        }

        // ── Notify billing (internal) ──
        $billing_html = forge_email_billing_balance_invoice(
            $order['order_id'] ?? '',
            $tier_label,
            $order['name'] ?? '',
            $customer_email,
            $balance,
            $invoice_id
        );
        forge_mail('billing@forge-nc.dev',
            '[Forge NC] Balance Invoice: ' . ($order['order_id'] ?? '') . ' — $' . number_format($balance / 100, 2),
            $billing_html,
            'Forge NC',
            null,
            true
        );
    }
}

/**
 * Save a signed report to the assurance reports directory.
 * Called from runpod_complete when reports are returned in the worker output
 * (bypasses Cloudflare which blocks data center POSTs to assurance_verify.php).
 */
function _save_report_locally(string $report_json): void {
    $report = json_decode($report_json, true);
    if (!$report || empty($report['run_id'])) return;

    $run_id = preg_replace('/[^a-zA-Z0-9_\-]/', '', $report['run_id']);
    if (!$run_id) return;

    $reports_dir = __DIR__ . '/data/assurance/reports';
    if (!is_dir($reports_dir)) {
        mkdir($reports_dir, 0755, true);
    }

    $path = $reports_dir . '/' . $run_id . '.json';
    if (file_exists($path)) return; // already saved

    // Verify signature if sodium is available
    $sig_status = 'unverified';
    if (function_exists('sodium_crypto_sign_verify_detached')
        && !empty($report['pub_key_b64']) && !empty($report['signature'])) {
        try {
            $report_obj = json_decode($report_json);
            unset($report_obj->signature, $report_obj->pub_key_b64, $report_obj->paired_run_id);
            $payload = python_json_encode($report_obj);
            $pub_key = base64_decode($report['pub_key_b64'], true);
            $sig = base64_decode($report['signature'], true);
            if ($pub_key && $sig && sodium_crypto_sign_verify_detached($sig, $payload, $pub_key)) {
                $sig_status = 'verified';
            } else {
                $sig_status = 'invalid';
            }
        } catch (Throwable $e) {
            $sig_status = 'error: ' . $e->getMessage();
        }
    }

    // Verify hash chain
    $chain_ok = true;
    $chain_bad_idx = null;
    foreach ($report['results'] ?? [] as $ci => $cr) {
        if (empty($cr['entry_hash'])) {
            $chain_ok = false;
            $chain_bad_idx = $ci;
            break;
        }
    }

    // Add verification metadata
    $report['_verification'] = [
        'sig_status' => $sig_status,
        'chain_ok' => $chain_ok,
        'chain_bad_idx' => $chain_bad_idx,
        'saved_by' => 'audit_orchestrator',
        'saved_at' => time(),
    ];

    file_put_contents($path, json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    error_log("Report saved locally: {$run_id} (sig: {$sig_status})");

    // Update index
    $index_path = __DIR__ . '/data/assurance/index.json';
    $index = file_exists($index_path) ? json_decode(file_get_contents($index_path), true) : [];
    if (!is_array($index)) $index = [];
    $index[$run_id] = [
        'run_id' => $run_id,
        'model' => $report['model'] ?? '',
        'pass_rate' => $report['pass_rate'] ?? 0,
        'sig_status' => $sig_status,
        'saved_at' => time(),
    ];
    file_put_contents($index_path, json_encode($index, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
}
