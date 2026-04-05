<?php
/**
 * Forge — Admin Dashboard (Owner Only)
 *
 * Master management, token management, revenue overview,
 * webhook log viewer, and system health.
 */
require_once __DIR__ . '/includes/auth_guard.php';

// Admin access (origin + any user with is_admin flag)
if (!$is_authed || !$is_admin) {
    header('Location: /login');
    exit;
}

// ── CSRF token ──
start_forge_session();
if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}
$csrf_token = $_SESSION['csrf_token'];

// ── Settings save handler ──
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_GET['action'] ?? '') === 'save_settings') {
    header('Content-Type: application/json');
    if (($_POST['csrf_token'] ?? '') !== ($_SESSION['csrf_token'] ?? '')) {
        echo json_encode(['error' => 'Invalid CSRF token']);
        exit;
    }
    // Only origin can change settings
    if (!$is_origin) {
        echo json_encode(['error' => 'Origin access required']);
        exit;
    }

    $audit_config_path = __DIR__ . '/data/audit_config.json';
    $audit_cfg = file_exists($audit_config_path) ? json_decode(file_get_contents($audit_config_path), true) : [];

    // Toggle maintenance mode
    if (isset($_POST['audit_maintenance'])) {
        $audit_cfg['audit_maintenance'] = $_POST['audit_maintenance'] === '1';
    }
    if (isset($_POST['audit_maintenance_message']) && trim($_POST['audit_maintenance_message'])) {
        $audit_cfg['audit_maintenance_message'] = trim($_POST['audit_maintenance_message']);
    }

    // Delete audit order (checks both active queue and archive)
    if (!empty($_POST['delete_order_id'])) {
        $del_id = preg_replace('/[^a-zA-Z0-9_-]/', '', $_POST['delete_order_id']);
        foreach ([__DIR__ . '/data/audit_queue.jsonl', __DIR__ . '/data/audit_archive.jsonl'] as $_qf) {
            if (!file_exists($_qf)) continue;
            $lines = file($_qf, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $kept = [];
            foreach ($lines as $line) {
                $o = json_decode($line, true);
                if ($o && ($o['order_id'] ?? '') !== $del_id) {
                    $kept[] = $line;
                }
            }
            file_put_contents($_qf, implode("\n", $kept) . ($kept ? "\n" : ''), LOCK_EX);
        }
        echo json_encode(['ok' => true, 'deleted' => $del_id]);
        exit;
    }

    // Toggle Stripe test/live mode
    if (isset($_POST['stripe_mode'])) {
        $stripe_dir = __DIR__ . '/data';
        $target = $stripe_dir . '/stripe_config.json';
        if ($_POST['stripe_mode'] === 'test') {
            $src = $stripe_dir . '/stripe_config_test.json';
        } else {
            $src = $stripe_dir . '/stripe_config_live.json';
        }
        if (file_exists($src)) {
            copy($src, $target);
        }
        $new_stripe = json_decode(file_get_contents($target), true);
        $mode = (strpos($new_stripe['secret_key'] ?? '', 'test') !== false) ? 'TEST' : 'LIVE';
        file_put_contents($audit_config_path, json_encode($audit_cfg, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
        echo json_encode(['ok' => true, 'stripe_mode' => $mode]);
        exit;
    }

    file_put_contents($audit_config_path, json_encode($audit_cfg, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    echo json_encode(['ok' => true, 'audit_maintenance' => $audit_cfg['audit_maintenance'] ?? false]);
    exit;
}

// ── AJAX handlers (JSON responses, no HTML) ──
if (isset($_GET['ajax'])) {
    // CSV exports return text/csv, not JSON
    if ($_GET['ajax'] === 'export_users' || $_GET['ajax'] === 'export_audit') {
        // CSRF via query param for GET exports
        if (($_GET['_csrf'] ?? '') !== ($_SESSION['csrf_token'] ?? '')) {
            header('Content-Type: application/json');
            echo json_encode(['ok' => false, 'error' => 'Invalid CSRF token']);
            exit;
        }
        if ($_GET['ajax'] === 'export_users') {
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="forge_users_' . date('Y-m-d') . '.csv"');
            $out = fopen('php://output', 'w');
            fputcsv($out, ['Email', 'Label', 'Role', 'Tier', 'Admin', 'Disabled', 'Created']);
            foreach (db_get_all_users() as $u) {
                fputcsv($out, [
                    $u['email'] ?? '',
                    $u['label'] ?? '',
                    $u['role'] ?? 'standalone',
                    $u['tier'] ?? 'community',
                    !empty($u['is_admin']) ? 'yes' : 'no',
                    !empty($u['disabled']) ? 'yes' : 'no',
                    $u['created'] ?? '',
                ]);
            }
            fclose($out);
            exit;
        }
        if ($_GET['ajax'] === 'export_audit') {
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="forge_audit_' . date('Y-m-d') . '.csv"');
            $out = fopen('php://output', 'w');
            fputcsv($out, ['Timestamp', 'Actor', 'Role', 'Action', 'Target Type', 'Target ID', 'Details', 'IP Hash']);
            $a_filters = [];
            if (!empty($_GET['audit_action'])) $a_filters['action'] = $_GET['audit_action'];
            if (!empty($_GET['audit_actor']))  $a_filters['actor'] = $_GET['audit_actor'];
            foreach (db_get_audit_log(5000, $a_filters) as $ae) {
                $details_raw = $ae['details'] ?? null;
                $details_str = is_string($details_raw) ? $details_raw : (is_array($details_raw) ? json_encode($details_raw) : '');
                fputcsv($out, [
                    $ae['timestamp'] ?? '',
                    $ae['actor_email'] ?? '',
                    $ae['actor_role'] ?? '',
                    $ae['action'] ?? '',
                    $ae['target_type'] ?? '',
                    $ae['target_id'] ?? '',
                    $details_str,
                    $ae['ip_hash'] ?? '',
                ]);
            }
            fclose($out);
            exit;
        }
    }

    header('Content-Type: application/json');
    $input = json_decode(file_get_contents('php://input'), true) ?: [];

    // CSRF validation for all POST AJAX handlers
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (($input['_csrf'] ?? '') !== ($_SESSION['csrf_token'] ?? '')) {
            echo json_encode(['ok' => false, 'error' => 'Invalid CSRF token']);
            exit;
        }
    }

    if ($_GET['ajax'] === 'bulk_action' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $emails = $input['emails'] ?? [];
        $action = $input['action'] ?? '';
        if (!is_array($emails) || empty($emails) || !in_array($action, ['disable', 'enable', 'set_tier'])) {
            echo json_encode(['ok' => false, 'error' => 'Invalid bulk action']);
            exit;
        }
        $bulk_tier = $input['tier'] ?? '';
        $count = 0;
        foreach ($emails as $be) {
            $be = strtolower(trim($be));
            if (!$be) continue;
            $bu = db_get_user($be);
            if (!$bu || ($bu['role'] ?? '') === 'origin') continue;
            if ($action === 'disable') {
                if (db_update_user($be, ['disabled' => 1])) $count++;
            } elseif ($action === 'enable') {
                if (db_update_user($be, ['disabled' => 0])) $count++;
            } elseif ($action === 'set_tier' && in_array($bulk_tier, ['community', 'pro', 'power'])) {
                if (db_update_user($be, ['tier' => $bulk_tier])) {
                    $count++;
                    require_once __DIR__ . '/includes/discord_notify.php';
                    discord_sync_tier($be);
                }
            }
        }
        db_audit_log($auth['email'] ?? '', $auth_role, 'user.bulk.' . $action, 'users', implode(',', array_slice($emails, 0, 5)), [
            'action' => $action, 'count' => $count, 'tier' => $bulk_tier ?: null,
        ]);
        echo json_encode(['ok' => true, 'count' => $count]);
        exit;
    }

    if ($_GET['ajax'] === 'update_role' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $email = strtolower(trim($input['email'] ?? ''));
        $new_role = $input['role'] ?? '';
        $valid_roles = ['standalone', 'master', 'puppet', 'admin'];
        if (!$email || !in_array($new_role, $valid_roles)) {
            echo json_encode(['ok' => false, 'error' => 'Invalid email or role']);
            exit;
        }
        $target_user = db_get_user($email);
        $old_role = $target_user['role'] ?? 'standalone';
        $ok = db_update_user($email, ['role' => $new_role]);
        // Also update any tokens for this user
        if ($target_user && !empty($target_user['telemetry_token'])) {
            $tk_hash = hash('sha512', $target_user['telemetry_token']);
            $stmt = get_db()->prepare('UPDATE tokens SET role = ? WHERE token_hash = ?');
            $stmt->execute([$new_role, $tk_hash]);
        }
        if ($ok) {
            db_audit_log($auth['email'] ?? '', $auth_role, 'user.role.change', 'user', $email, [
                'old_role' => $old_role,
                'new_role' => $new_role,
            ]);
            db_create_notification($email, 'role_change', 'Fleet Role Updated', 'Your fleet role has been changed to ' . ucfirst($new_role) . '.', '/dashboard');
        }
        echo json_encode(['ok' => $ok]);
        exit;
    }

    if ($_GET['ajax'] === 'toggle_status' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $email = strtolower(trim($input['email'] ?? ''));
        $disable = !empty($input['disabled']);
        if (!$email) {
            echo json_encode(['ok' => false, 'error' => 'Invalid email']);
            exit;
        }
        $ok = db_update_user($email, ['disabled' => $disable ? 1 : 0]);
        if ($ok) {
            db_audit_log($auth['email'] ?? '', $auth_role, 'user.status.toggle', 'user', $email, [
                'disabled' => $disable,
                'action' => $disable ? 'disabled' : 'enabled',
            ]);
            $status_msg = $disable ? 'Your account has been disabled.' : 'Your account has been re-enabled.';
            db_create_notification($email, 'status_change', 'Account Status Changed', $status_msg, '/dashboard');
        }
        echo json_encode(['ok' => $ok]);
        exit;
    }

    if ($_GET['ajax'] === 'update_tier' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $email = strtolower(trim($input['email'] ?? ''));
        $new_tier = $input['tier'] ?? '';
        if (!$email || !in_array($new_tier, ['community', 'pro', 'power'])) {
            echo json_encode(['ok' => false, 'error' => 'Invalid']);
            exit;
        }

        $target_user = db_get_user($email);
        $old_tier = $target_user['tier'] ?? 'community';
        $passport_action = 'none';

        // Update DB tier
        $ok = db_update_user($email, ['tier' => $new_tier]);

        if ($ok) {
            // Sync Discord role
            require_once __DIR__ . '/includes/discord_notify.php';
            discord_sync_tier($email);
            $MASTERS_DIR_TIER = __DIR__ . '/data/masters';

            // Find existing passport for this user
            $existing_passport_file = null;
            $existing_passport = null;
            if (is_dir($MASTERS_DIR_TIER)) {
                foreach (glob("$MASTERS_DIR_TIER/*.json") as $mf) {
                    $md = json_decode(file_get_contents($mf), true);
                    if ($md && strtolower($md['passport']['email'] ?? '') === $email) {
                        $existing_passport_file = $mf;
                        $existing_passport = $md;
                        break;
                    }
                }
            }

            // Also check via token → account_id
            if (!$existing_passport && $target_user && !empty($target_user['telemetry_token'])) {
                $tk_hash = hash('sha512', $target_user['telemetry_token']);
                $acct_id = db_get_account_id_by_token_hash($tk_hash);
                if ($acct_id) {
                    $mf = "$MASTERS_DIR_TIER/$acct_id.json";
                    if (file_exists($mf)) {
                        $existing_passport_file = $mf;
                        $existing_passport = json_decode(file_get_contents($mf), true);
                    }
                }
            }

            if (in_array($new_tier, ['pro', 'power'])) {
                // Upgrading to Pro/Power
                if ($existing_passport) {
                    // Update existing passport tier
                    $existing_passport['passport']['tier'] = $new_tier;
                    $tiers_cfg = file_exists(__DIR__ . '/data/tiers_config.json')
                        ? json_decode(file_get_contents(__DIR__ . '/data/tiers_config.json'), true) : [];
                    $tier_cfg = $tiers_cfg[$new_tier] ?? [];
                    if (!empty($tier_cfg['seats'])) {
                        $existing_passport['passport']['seat_count'] = (int)$tier_cfg['seats'];
                        $existing_passport['passport']['max_activations'] = (int)$tier_cfg['seats'];
                    }
                    $existing_passport['admin_tier_change'] = [
                        'old_tier' => $old_tier,
                        'new_tier' => $new_tier,
                        'changed_by' => $auth['email'] ?? 'admin',
                        'changed_at' => date('c'),
                    ];
                    // Re-activate passport if it was previously deactivated
                    $existing_passport['activated'] = true;
                    if (empty($existing_passport['activated_at'])) {
                        $existing_passport['activated_at'] = date('c');
                    }
                    unset($existing_passport['admin_downgraded']);
                    file_put_contents($existing_passport_file, json_encode($existing_passport, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
                    // Ensure user role is master
                    db_update_user($email, ['role' => 'master']);
                    // Update token role too
                    if ($target_user && !empty($target_user['telemetry_token'])) {
                        $tk_hash = hash('sha512', $target_user['telemetry_token']);
                        try {
                            $stmt = get_db()->prepare('UPDATE tokens SET role = ?, account_id = ? WHERE token_hash = ?');
                            $stmt->execute(['master', $existing_passport['passport']['account_id'] ?? '', $tk_hash]);
                        } catch (Exception $e) {}
                    }
                    $passport_action = 'updated';
                } else {
                    // Auto-generate passport (same logic as stripe_webhook.php)
                    require_once __DIR__ . '/includes/passport_signing.php';
                    $tiers_cfg = file_exists(__DIR__ . '/data/tiers_config.json')
                        ? json_decode(file_get_contents(__DIR__ . '/data/tiers_config.json'), true) : [];
                    $tier_cfg = $tiers_cfg[$new_tier] ?? ['seats' => ($new_tier === 'power' ? 10 : 3)];
                    $secret_key = load_origin_key();

                    $account_id = 'fg_' . bin2hex(random_bytes(12));
                    $passport_id = 'pp_' . bin2hex(random_bytes(8));

                    $passport = [
                        'passport_id'        => $passport_id,
                        'account_id'         => $account_id,
                        'role'               => 'master',
                        'tier'               => $new_tier,
                        'customer_label'     => $target_user['label'] ?? $email,
                        'email'              => $email,
                        'seat_count'         => (int)($tier_cfg['seats'] ?? 3),
                        'max_activations'    => (int)($tier_cfg['seats'] ?? 3),
                        'issued_at'          => time(),
                        'issued_date'        => date('c'),
                        'expires_at'         => 0,
                        'parent_passport_id' => '',
                        'master_id'          => '',
                        'origin_signature'   => '',
                    ];

                    if ($secret_key) {
                        $passport['origin_signature'] = sign_passport($passport, $secret_key);
                    }

                    $master_record = [
                        'passport'        => $passport,
                        'activated'       => false,
                        'master_mid'      => null,
                        'activated_at'    => null,
                        'last_seen'       => null,
                        'telemetry_token' => null,
                        'admin_generated' => [
                            'generated_by' => $auth['email'] ?? 'admin',
                            'generated_at' => date('c'),
                            'reason' => 'admin_tier_upgrade',
                        ],
                    ];

                    if (!is_dir($MASTERS_DIR_TIER)) mkdir($MASTERS_DIR_TIER, 0755, true);
                    file_put_contents("$MASTERS_DIR_TIER/$account_id.json",
                        json_encode($master_record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

                    // Link token to new account
                    if ($target_user && !empty($target_user['telemetry_token'])) {
                        $tk_hash = hash('sha512', $target_user['telemetry_token']);
                        try {
                            $stmt = get_db()->prepare('UPDATE tokens SET role = ?, account_id = ? WHERE token_hash = ?');
                            $stmt->execute(['master', $account_id, $tk_hash]);
                        } catch (Exception $e) {}
                    }

                    // Also update user role to master
                    db_update_user($email, ['role' => 'master']);

                    $passport_action = 'generated';
                }
            } elseif ($new_tier === 'community') {
                // Downgrading to Community — deactivate passport, reset role
                if ($existing_passport) {
                    $existing_passport['admin_downgraded'] = [
                        'old_tier' => $old_tier,
                        'downgraded_by' => $auth['email'] ?? 'admin',
                        'downgraded_at' => date('c'),
                    ];
                    $existing_passport['passport']['tier'] = 'community';
                    $existing_passport['activated'] = false;
                    file_put_contents($existing_passport_file, json_encode($existing_passport, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
                }
                // Reset fleet role back to standalone
                db_update_user($email, ['role' => 'standalone']);
                // Reset token role too
                if ($target_user && !empty($target_user['telemetry_token'])) {
                    $tk_hash = hash('sha512', $target_user['telemetry_token']);
                    try {
                        $stmt = get_db()->prepare('UPDATE tokens SET role = ? WHERE token_hash = ?');
                        $stmt->execute(['standalone', $tk_hash]);
                    } catch (Exception $e) {}
                }
                $passport_action = 'downgraded';
            }

            db_audit_log($auth['email'] ?? '', $auth_role, 'user.tier.change', 'user', $email, [
                'old_tier' => $old_tier,
                'new_tier' => $new_tier,
                'passport_action' => $passport_action,
            ]);
            if ($new_tier === 'community') {
                $notify_msg = 'Your account has been changed to Community tier. Paid features have been deactivated.';
                $notify_title = 'Tier changed to Community';
            } else {
                $notify_msg = 'Your account has been upgraded to ' . ucfirst($new_tier) . ".\n\n"
                    . "To activate:\n"
                    . "1. Go to your Dashboard and click \"Download Passport File\"\n"
                    . "2. Save the .json file somewhere on your machine\n"
                    . "3. In Forge, run: /license activate /path/to/passport.json\n\n"
                    . "That's it — your " . ucfirst($new_tier) . " features are unlocked once activated.";
                $notify_title = 'You\'ve been upgraded to ' . ucfirst($new_tier);
            }
            db_create_notification($email, 'tier_change', $notify_title, $notify_msg, '/dashboard');
        }
        echo json_encode(['ok' => $ok, 'passport_action' => $passport_action]);
        exit;
    }

    if ($_GET['ajax'] === 'toggle_admin' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $email = strtolower(trim($input['email'] ?? ''));
        $make_admin = !empty($input['is_admin']);
        if (!$email) {
            echo json_encode(['ok' => false, 'error' => 'Invalid']);
            exit;
        }
        $ok = db_update_user($email, ['is_admin' => $make_admin ? 1 : 0]);
        if ($ok) {
            db_audit_log($auth['email'] ?? '', $auth_role, 'user.admin.toggle', 'user', $email, [
                'is_admin' => $make_admin,
                'action' => $make_admin ? 'granted' : 'revoked',
            ]);
            $admin_msg = $make_admin ? 'You have been granted admin access.' : 'Your admin access has been revoked.';
            db_create_notification($email, 'admin_change', 'Admin Access ' . ($make_admin ? 'Granted' : 'Revoked'), $admin_msg, '/dashboard');
        }
        echo json_encode(['ok' => $ok]);
        exit;
    }

    // ── Clear API activity log (Origin only) ──
    if ($_GET['ajax'] === 'clear_api_log' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) {
            echo json_encode(['ok' => false, 'error' => 'Origin access required']);
            exit;
        }
        $api_path = __DIR__ . '/data/api_activity.jsonl';
        if (file_exists($api_path)) unlink($api_path);
        echo json_encode(['ok' => true]);
        exit;
    }

    // ── Clear fraud log (Origin only) ──
    if ($_GET['ajax'] === 'clear_fraud' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) {
            echo json_encode(['ok' => false, 'error' => 'Origin access required']);
            exit;
        }
        $fraud_path = __DIR__ . '/data/fraud_reports.jsonl';
        $count = 0;
        if (file_exists($fraud_path)) {
            $lines = file($fraud_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $count = is_array($lines) ? count($lines) : 0;
            unlink($fraud_path);
        }
        echo json_encode(['ok' => true, 'deleted' => $count]);
        exit;
    }

    // ── Delete audit entry (Origin only) ──
    if ($_GET['ajax'] === 'delete_audit' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) {
            echo json_encode(['ok' => false, 'error' => 'Origin access required']);
            exit;
        }
        $audit_id = (int)($input['id'] ?? 0);
        if (!$audit_id) {
            echo json_encode(['ok' => false, 'error' => 'Invalid audit entry ID']);
            exit;
        }
        $ok = db_delete_audit_entry($audit_id);
        echo json_encode(['ok' => $ok]);
        exit;
    }

    // ── Clear all audit log (Origin only) ──
    if ($_GET['ajax'] === 'clear_audit' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) {
            echo json_encode(['ok' => false, 'error' => 'Origin access required']);
            exit;
        }
        $count = db_clear_audit_log();
        echo json_encode(['ok' => $count >= 0, 'deleted' => $count]);
        exit;
    }

    // ── Delete assurance report (Origin only) ──
    if ($_GET['ajax'] === 'delete_report' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) {
            echo json_encode(['ok' => false, 'error' => 'Origin access required']);
            exit;
        }
        $run_id = preg_replace('/[^a-zA-Z0-9_\-]/', '', $input['run_id'] ?? '');
        if (!$run_id) {
            echo json_encode(['ok' => false, 'error' => 'Invalid run_id']);
            exit;
        }
        $rpt_dir = __DIR__ . '/data/assurance/reports';
        $idx_path = __DIR__ . '/data/assurance/index.json';
        $rpt_path = $rpt_dir . '/' . $run_id . '.json';

        $deleted_files = [];
        $errors = [];

        // Delete report file
        if (file_exists($rpt_path)) {
            if (unlink($rpt_path)) {
                $deleted_files[] = $run_id;
            } else {
                $errors[] = "Failed to delete $run_id";
            }
        }

        // Also delete paired report if requested
        if (!empty($input['delete_pair'])) {
            // Find paired_run_id from the report we just deleted, or from the input
            $pair_id = preg_replace('/[^a-zA-Z0-9_\-]/', '', $input['pair_run_id'] ?? '');
            if ($pair_id) {
                $pair_path = $rpt_dir . '/' . $pair_id . '.json';
                if (file_exists($pair_path)) {
                    if (unlink($pair_path)) {
                        $deleted_files[] = $pair_id;
                    } else {
                        $errors[] = "Failed to delete pair $pair_id";
                    }
                }
            }
        }

        // Remove from index
        if (file_exists($idx_path)) {
            $idx = json_decode(file_get_contents($idx_path), true) ?: [];
            foreach ($deleted_files as $did) {
                unset($idx[$did]);
            }
            file_put_contents($idx_path, json_encode($idx, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
        }

        // Audit log
        db_audit_log($auth['email'] ?? '', $auth_role, 'report.delete', 'report', $run_id, [
            'deleted' => $deleted_files,
            'errors' => $errors,
        ]);

        echo json_encode([
            'ok' => empty($errors),
            'deleted' => $deleted_files,
            'errors' => $errors,
        ]);
        exit;
    }

    // ── Save expense ──
    if ($_GET['ajax'] === 'save_expense' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        $valid_cats = ['R&D', 'Operations', 'Equipment', 'Travel', 'Office', 'Hosting', 'Compute', 'Software'];
        $date = preg_replace('/[^0-9\-]/', '', $input['date'] ?? '');
        $category = $input['category'] ?? '';
        $description = trim($input['description'] ?? '');
        $amount = round(floatval($input['amount'] ?? 0), 2);
        $receipt_url = trim($input['receipt_url'] ?? '');
        if (!$date || !in_array($category, $valid_cats) || !$description || $amount <= 0) {
            echo json_encode(['ok' => false, 'error' => 'Missing or invalid fields']); exit;
        }
        $expense = [
            'id' => 'exp_' . bin2hex(random_bytes(6)),
            'date' => $date, 'category' => $category, 'description' => $description,
            'amount' => $amount, 'receipt_url' => $receipt_url, 'created_at' => date('c'),
        ];
        file_put_contents(__DIR__ . '/data/expenses.jsonl', json_encode($expense, JSON_UNESCAPED_SLASHES) . "\n", FILE_APPEND | LOCK_EX);
        echo json_encode(['ok' => true, 'expense' => $expense]);
        exit;
    }

    // ── Delete expense ──
    if ($_GET['ajax'] === 'delete_expense' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        $del_id = preg_replace('/[^a-zA-Z0-9_]/', '', $input['id'] ?? '');
        $exp_path = __DIR__ . '/data/expenses.jsonl';
        $found = false;
        if ($del_id && file_exists($exp_path)) {
            $lines = file($exp_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $kept = [];
            foreach ($lines as $line) {
                $e = json_decode($line, true);
                if ($e && ($e['id'] ?? '') === $del_id) $found = true;
                else $kept[] = $line;
            }
            file_put_contents($exp_path, $kept ? implode("\n", $kept) . "\n" : '', LOCK_EX);
        }
        echo json_encode(['ok' => $found, 'deleted' => $del_id]);
        exit;
    }

    // ── Export expenses CSV ──
    if ($_GET['ajax'] === 'export_expenses') {
        if (($_GET['_csrf'] ?? '') !== ($_SESSION['csrf_token'] ?? '')) { echo json_encode(['ok' => false, 'error' => 'CSRF']); exit; }
        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="forge_expenses_' . date('Y-m-d') . '.csv"');
        $out = fopen('php://output', 'w');
        fputcsv($out, ['ID', 'Date', 'Category', 'Description', 'Amount', 'Receipt URL', 'Created At']);
        $exp_path = __DIR__ . '/data/expenses.jsonl';
        if (file_exists($exp_path)) {
            foreach (file($exp_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $e = json_decode($line, true);
                if ($e) fputcsv($out, [$e['id']??'', $e['date']??'', $e['category']??'', $e['description']??'', $e['amount']??0, $e['receipt_url']??'', $e['created_at']??'']);
            }
        }
        fclose($out);
        exit;
    }

    // ── Upload receipt image ──
    if ($_GET['ajax'] === 'upload_receipt' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        // CSRF via POST field (multipart form)
        if (($_POST['_csrf'] ?? '') !== ($_SESSION['csrf_token'] ?? '')) {
            echo json_encode(['ok' => false, 'error' => 'Invalid CSRF']); exit;
        }
        if (empty($_FILES['receipt']) || $_FILES['receipt']['error'] !== UPLOAD_ERR_OK) {
            echo json_encode(['ok' => false, 'error' => 'No file uploaded']); exit;
        }
        $file = $_FILES['receipt'];
        $allowed = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
        if (!in_array($file['type'], $allowed)) {
            echo json_encode(['ok' => false, 'error' => 'Allowed: JPG, PNG, WebP, PDF']); exit;
        }
        if ($file['size'] > 10 * 1024 * 1024) {
            echo json_encode(['ok' => false, 'error' => 'Max 10MB']); exit;
        }
        $ext = ['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp','application/pdf'=>'pdf'][$file['type']];
        $receipt_dir = __DIR__ . '/data/receipts';
        if (!is_dir($receipt_dir)) mkdir($receipt_dir, 0750, true);
        $filename = 'rcpt_' . bin2hex(random_bytes(8)) . '.' . $ext;
        move_uploaded_file($file['tmp_name'], $receipt_dir . '/' . $filename);
        echo json_encode(['ok' => true, 'url' => '/receipt.php?f=' . $filename]);
        exit;
    }

    // ── Save recurring expense ──
    if ($_GET['ajax'] === 'save_recurring' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        $rec_path = __DIR__ . '/data/recurring_expenses.json';
        $recurring = file_exists($rec_path) ? json_decode(file_get_contents($rec_path), true) : [];
        if (!is_array($recurring)) $recurring = [];
        $new_rec = [
            'description' => trim($input['description'] ?? ''),
            'category' => $input['category'] ?? 'Operations',
            'amount' => round(floatval($input['amount'] ?? 0), 2),
            'frequency' => in_array($input['frequency'] ?? '', ['monthly', 'quarterly', 'yearly']) ? $input['frequency'] : 'monthly',
        ];
        if (!$new_rec['description'] || $new_rec['amount'] <= 0) {
            echo json_encode(['ok' => false, 'error' => 'Invalid fields']); exit;
        }
        $recurring[] = $new_rec;
        file_put_contents($rec_path, json_encode($recurring, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
        echo json_encode(['ok' => true]);
        exit;
    }

    // ── Delete recurring expense ──
    if ($_GET['ajax'] === 'delete_recurring' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        $rec_path = __DIR__ . '/data/recurring_expenses.json';
        $recurring = file_exists($rec_path) ? json_decode(file_get_contents($rec_path), true) : [];
        $idx = (int)($input['index'] ?? -1);
        if ($idx >= 0 && $idx < count($recurring)) {
            array_splice($recurring, $idx, 1);
            file_put_contents($rec_path, json_encode($recurring, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
            echo json_encode(['ok' => true]);
        } else {
            echo json_encode(['ok' => false, 'error' => 'Invalid index']);
        }
        exit;
    }

    // ── Update expense ──
    if ($_GET['ajax'] === 'update_expense' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_origin) { echo json_encode(['ok' => false, 'error' => 'Origin access required']); exit; }
        $upd_id = preg_replace('/[^a-zA-Z0-9_]/', '', $input['id'] ?? '');
        $exp_path = __DIR__ . '/data/expenses.jsonl';
        $found = false;
        if ($upd_id && file_exists($exp_path)) {
            $lines = file($exp_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $updated = [];
            foreach ($lines as $line) {
                $e = json_decode($line, true);
                if ($e && ($e['id'] ?? '') === $upd_id) {
                    if (isset($input['date'])) $e['date'] = preg_replace('/[^0-9\-]/', '', $input['date']);
                    if (isset($input['category'])) $e['category'] = $input['category'];
                    if (isset($input['description'])) $e['description'] = trim($input['description']);
                    if (isset($input['amount'])) $e['amount'] = round(floatval($input['amount']), 2);
                    if (isset($input['receipt_url'])) $e['receipt_url'] = trim($input['receipt_url']);
                    $found = true;
                }
                $updated[] = json_encode($e, JSON_UNESCAPED_SLASHES);
            }
            if ($found) file_put_contents($exp_path, implode("\n", $updated) . "\n", LOCK_EX);
        }
        echo json_encode(['ok' => $found]);
        exit;
    }

    echo json_encode(['ok' => false, 'error' => 'Unknown action']);
    exit;
}

// ── Load all data server-side ──
$MASTERS_DIR  = __DIR__ . '/data/masters';
$PUPPET_REG    = __DIR__ . '/data/puppet_registry.json';
$TIERS_FILE    = __DIR__ . '/data/tiers_config.json';
$REVOC_FILE    = __DIR__ . '/data/revocations.json';
// Tokens loaded from DB via db_list_tokens()
$WEBHOOK_LOG   = __DIR__ . '/data/webhook_log.jsonl';

$tiers_config = file_exists($TIERS_FILE) ? json_decode(file_get_contents($TIERS_FILE), true) : array();
$puppet_registry = file_exists($PUPPET_REG) ? json_decode(file_get_contents($PUPPET_REG), true) : array();
$revocations = file_exists($REVOC_FILE) ? json_decode(file_get_contents($REVOC_FILE), true) : array();
$tokens_data = db_list_tokens();

// Load masters
$masters = array();
if (is_dir($MASTERS_DIR)) {
    $master_files = glob($MASTERS_DIR . '/*.json');
    if (is_array($master_files)) {
        foreach ($master_files as $cf) {
            $c = json_decode(file_get_contents($cf), true);
            if ($c) {
                $pp = isset($c['passport']) ? $c['passport'] : array();
                $aid = isset($pp['account_id']) ? $pp['account_id'] : basename($cf, '.json');
                $ppid = isset($pp['passport_id']) ? $pp['passport_id'] : '';
                $pups = isset($puppet_registry[$aid]) ? $puppet_registry[$aid] : array();
                $active_pups = 0;
                foreach ($pups as $p) {
                    if (isset($p['status']) && $p['status'] === 'active') $active_pups++;
                }
                $masters[] = array(
                    'account_id' => $aid,
                    'passport_id' => $ppid,
                    'label' => isset($pp['customer_label']) ? $pp['customer_label'] : '',
                    'email' => isset($pp['email']) ? $pp['email'] : '',
                    'tier' => isset($pp['tier']) ? $pp['tier'] : 'community',
                    'seats' => isset($pp['seat_count']) ? (int)$pp['seat_count'] : 1,
                    'puppets_active' => $active_pups,
                    'puppets_total' => count($pups),
                    'activated' => !empty($c['activated']),
                    'activated_at' => isset($c['activated_at']) ? $c['activated_at'] : null,
                    'last_seen' => isset($c['last_seen']) ? $c['last_seen'] : null,
                    'revoked' => isset($revocations[$ppid]),
                    'issued' => isset($pp['issued_date']) ? $pp['issued_date'] : null,
                    'amount_paid' => isset($c['amount_paid']) ? (int)$c['amount_paid'] : 0,
                );
            }
        }
    }
}

// Calculate stats
$total_masters = count($masters);
$active_masters = 0;
$total_seats = 0;
$total_puppets = 0;
$total_revenue = 0;
$paid_customers = 0;
$granted_count = 0;
$tier_breakdown = array();
$grant_breakdown = array();
foreach ($masters as $m) {
    if ($m['activated'] && !$m['revoked']) $active_masters++;
    if ($m['seats'] > 0) $total_seats += $m['seats'];
    $total_puppets += $m['puppets_active'];
    $t = $m['tier'];
    $paid = $m['amount_paid'];
    $is_grant = ($paid <= 0);

    if ($t === 'origin') {
        // Origin — not a customer or grant, skip revenue/grant tracking
    } elseif ($is_grant) {
        // Granted (admin-issued, sponsor)
        $granted_count++;
        if (!isset($grant_breakdown[$t])) {
            $grant_breakdown[$t] = array('count' => 0, 'seats' => 0);
        }
        $grant_breakdown[$t]['count']++;
        if ($m['seats'] > 0) $grant_breakdown[$t]['seats'] += $m['seats'];
    } else {
        // Paid customer
        $paid_customers++;
        if (!isset($tier_breakdown[$t])) {
            $tier_breakdown[$t] = array('count' => 0, 'revenue' => 0, 'seats' => 0);
        }
        $tier_breakdown[$t]['count']++;
        $tier_breakdown[$t]['revenue'] += $paid;
        if ($m['seats'] > 0) $tier_breakdown[$t]['seats'] += $m['seats'];
        $total_revenue += $paid;
    }
}

// Load tokens
$token_list = array();
foreach ($tokens_data as $entry) {
    $hash = isset($entry['token_hash']) ? $entry['token_hash'] : '';
    $role = isset($entry['role']) ? $entry['role'] : 'standalone';
    $user_email = isset($entry['user_email']) ? $entry['user_email'] : '';
    $token_list[] = array(
        'hash' => $hash,
        'hash_prefix' => substr($hash, 0, 12) . '...',
        'label' => isset($entry['label']) ? $entry['label'] : 'unknown',
        'role' => $role,
        'created' => isset($entry['created']) ? $entry['created'] : '',
        'revoked' => !empty($entry['revoked']),
        'account_id' => isset($entry['account_id']) ? $entry['account_id'] : '',
        'user_email' => $user_email,
        'source' => $user_email ? 'registration' : 'admin',
    );
}

// Load webhook log (last 50 lines)
$webhook_entries = array();
if (file_exists($WEBHOOK_LOG)) {
    $lines = file($WEBHOOK_LOG, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (is_array($lines)) {
        $lines = array_slice($lines, -50);
        $lines = array_reverse($lines);
        foreach ($lines as $line) {
            $entry = json_decode($line, true);
            if ($entry) $webhook_entries[] = $entry;
        }
    }
}

// System health
$profile_count = 0;
$profile_dir = __DIR__ . '/data/profiles';
$profiles = [];
if (is_dir($profile_dir)) {
    $pg = glob($profile_dir . '/*.json');
    $profile_count = is_array($pg) ? count($pg) : 0;
    foreach ($pg as $pf) {
        $pd = json_decode(file_get_contents($pf), true);
        if ($pd) {
            $mid = $pd['machine_id'] ?? basename($pf, '.json');
            $profiles[$mid] = $pd;
        }
    }
}
$rate_count = 0;
$rate_dir = __DIR__ . '/rate_limits';
if (is_dir($rate_dir)) {
    $rg = glob($rate_dir . '/*.json');
    $rate_count = is_array($rg) ? count($rg) : 0;
}

// ── Load site analytics data (only when needed) ──
$EVENTS_FILE = __DIR__ . '/data/site_events.jsonl';
$WAITLIST_FILE = __DIR__ . '/data/waitlist.json';
$site_events = array();
$site_range = isset($_GET['range']) ? $_GET['range'] : '7d';

$active_view = isset($_GET['view']) ? $_GET['view'] : 'overview';
$valid_views = array('overview', 'users', 'masters', 'tokens', 'revenue', 'webhooks', 'system', 'site', 'telemetry', 'audit', 'billing', 'expenses', 'settings');
if (!in_array($active_view, $valid_views)) $active_view = 'overview';

if ($active_view === 'site') {
    // Parse time range
    $range_map = array('today' => 0, '7d' => 7, '30d' => 30, 'all' => 99999);
    $range_days = isset($range_map[$site_range]) ? $range_map[$site_range] : 7;
    $range_start = ($site_range === 'today')
        ? strtotime('today midnight')
        : ($site_range === 'all' ? 0 : strtotime("-{$range_days} days midnight"));

    // Load events from JSONL
    if (file_exists($EVENTS_FILE)) {
        $fh = fopen($EVENTS_FILE, 'r');
        if ($fh) {
            while (($line = fgets($fh)) !== false) {
                $evt = json_decode(trim($line), true);
                if ($evt && isset($evt['ts_unix']) && $evt['ts_unix'] >= $range_start) {
                    $site_events[] = $evt;
                }
            }
            fclose($fh);
        }
    }

    // Also load archived files if range > 7d
    if ($range_days > 7) {
        $archives = glob(__DIR__ . '/data/site_events_*.jsonl');
        if (is_array($archives)) {
            foreach ($archives as $af) {
                $fh = fopen($af, 'r');
                if ($fh) {
                    while (($line = fgets($fh)) !== false) {
                        $evt = json_decode(trim($line), true);
                        if ($evt && isset($evt['ts_unix']) && $evt['ts_unix'] >= $range_start) {
                            $site_events[] = $evt;
                        }
                    }
                    fclose($fh);
                }
            }
        }
    }

    // Compute analytics
    $sa_pageviews = array();
    $sa_cta_clicks = array();
    $sa_scroll_events = array();
    $sa_waitlist_events = array();
    $sa_visitors = array();
    $sa_today_visitors = array();
    $sa_daily = array();
    $sa_referrers = array();
    $sa_browsers = array();
    $sa_os = array();
    $sa_devices = array();
    $sa_pages = array();
    $sa_countries = array();
    $sa_cta_detail = array();

    $today_str = date('Y-m-d');

    foreach ($site_events as $evt) {
        $type = isset($evt['event']) ? $evt['event'] : '';
        $vid = isset($evt['vid']) ? $evt['vid'] : '';
        $day = isset($evt['ts']) ? substr($evt['ts'], 0, 10) : date('Y-m-d', $evt['ts_unix']);
        $url = isset($evt['url']) ? $evt['url'] : '';

        if ($vid) $sa_visitors[$vid] = true;
        if ($vid && $day === $today_str) $sa_today_visitors[$vid] = true;

        if ($type === 'pageview') {
            $sa_pageviews[] = $evt;
            if (!isset($sa_daily[$day])) $sa_daily[$day] = array('views' => 0, 'visitors' => array());
            $sa_daily[$day]['views']++;
            if ($vid) $sa_daily[$day]['visitors'][$vid] = true;

            // Referrer
            $ref = isset($evt['ref']) ? $evt['ref'] : '';
            if ($ref) {
                $ref_host = parse_url($ref, PHP_URL_HOST);
                if (!$ref_host) $ref_host = $ref;
                $ref_host = preg_replace('/^www\./', '', $ref_host);
                if (!isset($sa_referrers[$ref_host])) $sa_referrers[$ref_host] = 0;
                $sa_referrers[$ref_host]++;
            } else {
                if (!isset($sa_referrers['Direct'])) $sa_referrers['Direct'] = 0;
                $sa_referrers['Direct']++;
            }

            // Pages
            if (!isset($sa_pages[$url])) $sa_pages[$url] = array('views' => 0, 'visitors' => array(), 'scroll_sum' => 0, 'time_sum' => 0, 'scroll_count' => 0);
            $sa_pages[$url]['views']++;
            if ($vid) $sa_pages[$url]['visitors'][$vid] = true;
        }

        if ($type === 'cta_click') {
            $sa_cta_clicks[] = $evt;
            $btn = isset($evt['btn_text']) ? $evt['btn_text'] : 'Unknown';
            $sa_cta_detail[] = $evt;
        }

        if ($type === 'scroll_depth') {
            $sa_scroll_events[] = $evt;
            if ($url && isset($sa_pages[$url])) {
                $sa_pages[$url]['scroll_sum'] += isset($evt['max_scroll']) ? (int)$evt['max_scroll'] : 0;
                $sa_pages[$url]['time_sum'] += isset($evt['time_on_page']) ? (int)$evt['time_on_page'] : 0;
                $sa_pages[$url]['scroll_count']++;
            }
        }

        if ($type === 'waitlist') {
            $sa_waitlist_events[] = $evt;
        }

        // Browser/OS/Device
        if ($type === 'pageview') {
            $br = isset($evt['browser']) ? $evt['browser'] : 'Other';
            if (!isset($sa_browsers[$br])) $sa_browsers[$br] = 0;
            $sa_browsers[$br]++;

            $os = isset($evt['os']) ? $evt['os'] : 'Other';
            if (!isset($sa_os[$os])) $sa_os[$os] = 0;
            $sa_os[$os]++;

            $dev = isset($evt['device']) ? $evt['device'] : 'Desktop';
            if (!isset($sa_devices[$dev])) $sa_devices[$dev] = 0;
            $sa_devices[$dev]++;

            $country = isset($evt['country']) ? $evt['country'] : null;
            if ($country) {
                if (!isset($sa_countries[$country])) $sa_countries[$country] = 0;
                $sa_countries[$country]++;
            }
        }
    }

    arsort($sa_referrers);
    arsort($sa_browsers);
    arsort($sa_os);
    arsort($sa_devices);
    arsort($sa_countries);
    ksort($sa_daily);

    // CTA funnel counts
    $sa_cta_funnel = array();
    foreach ($sa_cta_clicks as $click) {
        $label = isset($click['btn_text']) ? $click['btn_text'] : 'Unknown';
        if (!isset($sa_cta_funnel[$label])) $sa_cta_funnel[$label] = 0;
        $sa_cta_funnel[$label]++;
    }
    arsort($sa_cta_funnel);

    // Waitlist count from file
    $waitlist_count = 0;
    if (file_exists($WAITLIST_FILE)) {
        $wl = json_decode(file_get_contents($WAITLIST_FILE), true);
        if (is_array($wl)) $waitlist_count = count($wl);
    }

    // ── Advanced metrics ──

    // New vs returning visitors
    $sa_new_visitors = 0;
    $sa_returning_visitors = 0;
    $visitor_first_seen = array();
    foreach ($site_events as $evt) {
        if (isset($evt['event']) && $evt['event'] === 'pageview' && isset($evt['vid'])) {
            $v = $evt['vid'];
            $ts = $evt['ts_unix'];
            if (!isset($visitor_first_seen[$v])) {
                $visitor_first_seen[$v] = $ts;
            } elseif ($ts > $visitor_first_seen[$v] + 1800) {
                // Return visit if > 30 min after first seen
                $sa_returning_visitors++;
            }
        }
    }
    $sa_new_visitors = count($visitor_first_seen) - $sa_returning_visitors;
    if ($sa_new_visitors < 0) $sa_new_visitors = 0;

    // Bounce rate (single-page sessions): visitors with only 1 pageview
    $visitor_page_count = array();
    foreach ($sa_pageviews as $pv) {
        $v = isset($pv['vid']) ? $pv['vid'] : '';
        if ($v) {
            if (!isset($visitor_page_count[$v])) $visitor_page_count[$v] = 0;
            $visitor_page_count[$v]++;
        }
    }
    $bounced = 0;
    foreach ($visitor_page_count as $cnt) {
        if ($cnt <= 1) $bounced++;
    }
    $bounce_rate = count($visitor_page_count) > 0 ? round($bounced / count($visitor_page_count) * 100, 1) : 0;

    // Avg session duration (from scroll_depth time_on_page)
    $session_times = array();
    foreach ($sa_scroll_events as $se) {
        if (isset($se['time_on_page'])) $session_times[] = (int)$se['time_on_page'];
    }
    $avg_session = count($session_times) > 0 ? round(array_sum($session_times) / count($session_times)) : 0;

    // Conversion rate: CTA clicks / unique visitors
    $conversion_rate = count($sa_visitors) > 0 ? round(count($sa_cta_clicks) / count($sa_visitors) * 100, 1) : 0;

    // UTM campaign breakdown
    $sa_utm_campaigns = array();
    foreach ($sa_pageviews as $pv) {
        $src = isset($pv['utm_source']) ? $pv['utm_source'] : '';
        $med = isset($pv['utm_medium']) ? $pv['utm_medium'] : '';
        $camp = isset($pv['utm_campaign']) ? $pv['utm_campaign'] : '';
        if ($src || $camp) {
            $key = ($src ?: 'none') . ' / ' . ($med ?: 'none') . ($camp ? " ({$camp})" : '');
            if (!isset($sa_utm_campaigns[$key])) $sa_utm_campaigns[$key] = array('views' => 0, 'visitors' => array());
            $sa_utm_campaigns[$key]['views']++;
            if (isset($pv['vid'])) $sa_utm_campaigns[$key]['visitors'][$pv['vid']] = true;
        }
    }
    uasort($sa_utm_campaigns, function($a, $b) { return $b['views'] - $a['views']; });

    // Tier interest breakdown (from CTA clicks)
    $sa_tier_interest = array();
    foreach ($sa_cta_clicks as $click) {
        $tier = isset($click['tier']) ? $click['tier'] : 'unknown';
        if (!isset($sa_tier_interest[$tier])) $sa_tier_interest[$tier] = array('clicks' => 0, 'billing' => array());
        $sa_tier_interest[$tier]['clicks']++;
        $billing = isset($click['billing']) ? $click['billing'] : 'onetime';
        if (!isset($sa_tier_interest[$tier]['billing'][$billing])) $sa_tier_interest[$tier]['billing'][$billing] = 0;
        $sa_tier_interest[$tier]['billing'][$billing]++;
    }
    arsort($sa_tier_interest);

    // Hourly distribution
    $sa_hourly = array_fill(0, 24, 0);
    foreach ($sa_pageviews as $pv) {
        $hour = isset($pv['ts']) ? (int)date('G', strtotime($pv['ts'])) : (int)date('G', $pv['ts_unix']);
        $sa_hourly[$hour]++;
    }

    // Real-time: visitors in last 5 minutes
    $sa_realtime = 0;
    $five_min_ago = time() - 300;
    $realtime_vids = array();
    foreach ($site_events as $evt) {
        if (isset($evt['ts_unix']) && $evt['ts_unix'] >= $five_min_ago && isset($evt['vid'])) {
            $realtime_vids[$evt['vid']] = true;
        }
    }
    $sa_realtime = count($realtime_vids);

    // Viewport width distribution
    $sa_viewports = array('< 768px' => 0, '768-1024' => 0, '1024-1440' => 0, '1440-1920' => 0, '> 1920' => 0);
    foreach ($sa_pageviews as $pv) {
        $vw = isset($pv['vw']) ? (int)$pv['vw'] : 0;
        if ($vw > 0) {
            if ($vw < 768) $sa_viewports['< 768px']++;
            elseif ($vw < 1024) $sa_viewports['768-1024']++;
            elseif ($vw < 1440) $sa_viewports['1024-1440']++;
            elseif ($vw < 1920) $sa_viewports['1440-1920']++;
            else $sa_viewports['> 1920']++;
        }
    }
}

// ── Telemetry data (loaded on telemetry + overview views) ──
$telem_reports = [];
$telem_machines = [];
$telem_index = [];
if ($active_view === 'telemetry' || $active_view === 'overview') {
    $REPORTS_DIR = __DIR__ . '/data/assurance/reports';
    $ASSURANCE_IDX = __DIR__ . '/data/assurance/index.json';
    if (file_exists($ASSURANCE_IDX)) {
        $telem_index = json_decode(file_get_contents($ASSURANCE_IDX), true) ?: [];
    }
    if (is_dir($REPORTS_DIR)) {
        $report_files = glob($REPORTS_DIR . '/*.json');
        if (is_array($report_files)) {
            foreach ($report_files as $rf) {
                $rpt = json_decode(file_get_contents($rf), true);
                if (!$rpt) continue;
                $mid = $rpt['machine_id'] ?? '';
                $telem_reports[] = [
                    'run_id'        => $rpt['run_id'] ?? basename($rf, '.json'),
                    'model'         => $rpt['model'] ?? 'unknown',
                    'pass_rate'     => $rpt['pass_rate'] ?? 0,
                    'scenarios_run' => $rpt['scenarios_run'] ?? 0,
                    'scenarios_passed' => $rpt['scenarios_passed'] ?? 0,
                    'machine_id'    => $mid,
                    'passport_id'   => $rpt['passport_id'] ?? '',
                    'forge_version' => $rpt['forge_version'] ?? '',
                    'generated_at'  => $rpt['generated_at'] ?? 0,
                    'duration_s'    => $rpt['duration_s'] ?? 0,
                    'sig_status'    => $rpt['_verification']['sig_status'] ?? 'unknown',
                    'chain_ok'      => $rpt['_verification']['chain_ok'] ?? null,
                    'platform'      => $rpt['platform_info'] ?? [],
                    'paired_run_id' => $rpt['paired_run_id'] ?? ($rpt['_verification']['paired_run_id'] ?? ''),
                    '_verification' => $rpt['_verification'] ?? [],
                ];
                if ($mid !== '') {
                    if (!isset($telem_machines[$mid])) {
                        $telem_machines[$mid] = [
                            'machine_id' => $mid,
                            'runs' => 0,
                            'models' => [],
                            'first_seen' => $rpt['generated_at'] ?? 0,
                            'last_seen' => $rpt['generated_at'] ?? 0,
                            'platform' => $rpt['platform_info'] ?? [],
                            'passport_id' => $rpt['passport_id'] ?? '',
                        ];
                    }
                    $telem_machines[$mid]['runs']++;
                    $telem_machines[$mid]['models'][$rpt['model'] ?? 'unknown'] = true;
                    $gen = $rpt['generated_at'] ?? 0;
                    if ($gen > $telem_machines[$mid]['last_seen'])
                        $telem_machines[$mid]['last_seen'] = $gen;
                    if ($gen < $telem_machines[$mid]['first_seen'] || $telem_machines[$mid]['first_seen'] == 0)
                        $telem_machines[$mid]['first_seen'] = $gen;
                }
            }
        }
    }
    // Sort reports by date descending
    usort($telem_reports, fn($a, $b) => ($b['generated_at'] ?? 0) <=> ($a['generated_at'] ?? 0));
}

$page_title = 'Forge — Admin';
$page_id = 'admin';
require_once __DIR__ . '/includes/header.php';
?>

<style>
/* ── Admin Command Center ──────────────────────────────────────────── */
.admin-wrap { display:flex; min-height:calc(100vh - var(--nav-height)); }
.admin-nav {
    width:240px; min-width:240px; background:var(--bg-surface);
    border-right:1px solid var(--border); padding:24px 0;
    position:sticky; top:var(--nav-height); height:calc(100vh - var(--nav-height));
    overflow-y:auto; z-index:10;
}
.admin-nav-title {
    padding:0 20px; margin:0 0 16px; font-size:0.7rem; font-weight:700;
    text-transform:uppercase; letter-spacing:0.15em; color:var(--text-muted);
}
.admin-nav a {
    display:flex; align-items:center; gap:10px;
    padding:10px 20px; font-size:0.88rem; color:var(--text-dim);
    text-decoration:none; transition:all 0.15s; border-left:3px solid transparent;
}
.admin-nav a:hover { color:var(--text); background:var(--bg-card); }
.admin-nav a.active {
    color:var(--accent); background:var(--accent-bg);
    border-left-color:var(--accent); font-weight:600;
}
.admin-nav a .nav-icon { font-size:1.1em; width:20px; text-align:center; }
.admin-nav .nav-divider { height:1px; background:var(--border); margin:12px 20px; }

.admin-main { flex:1; padding:32px 40px; }
.admin-main h2 {
    font-size:1.5rem; font-weight:700; margin-bottom:8px;
    background:var(--gradient-text); -webkit-background-clip:text;
    -webkit-text-fill-color:transparent; background-clip:text;
}
.admin-main .view-desc { color:var(--text-dim); margin-bottom:28px; font-size:0.9rem; }

/* Enhanced stat cards */
.admin-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:28px; }
.admin-stat {
    background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg);
    padding:20px; transition:border-color 0.2s, box-shadow 0.2s;
}
.admin-stat:hover { border-color:var(--accent); box-shadow:var(--shadow-glow); }
.admin-stat .stat-val { font-size:1.8rem; font-weight:800; line-height:1.1; }
.admin-stat .stat-lbl { font-size:0.78rem; color:var(--text-dim); margin-top:4px; text-transform:uppercase; letter-spacing:0.05em; }
.admin-stat .stat-trend { font-size:0.75rem; margin-top:6px; }
.admin-stat .stat-trend.up { color:var(--green); }
.admin-stat .stat-trend.down { color:var(--red); }

/* Card sections */
.admin-card {
    background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg);
    padding:24px; margin-bottom:20px; transition:border-color 0.2s;
}
.admin-card:hover { border-color:var(--border-light); }
.admin-card h3 { font-size:1.05rem; font-weight:600; margin-bottom:16px; color:var(--text-bright); }
.admin-card .card-row { display:grid; grid-template-columns:1fr 1fr; gap:20px; }

/* Enhanced tables */
.admin-card table, .admin-main .card table { width:100%; border-collapse:collapse; }
.admin-card th, .admin-main .card th {
    text-align:left; padding:10px 12px; font-size:0.75rem; font-weight:600;
    text-transform:uppercase; letter-spacing:0.06em; color:var(--text-muted);
    border-bottom:2px solid var(--border); white-space:nowrap;
}
.admin-card td, .admin-main .card td { padding:10px 12px; border-bottom:1px solid var(--border); font-size:0.88rem; white-space:nowrap; }
.admin-card tr:last-child td, .admin-main .card tr:last-child td { border-bottom:none; }
.admin-card tr:hover td, .admin-main .card tr:hover td { background:var(--accent-bg); }

/* Badge system */
.abadge {
    display:inline-flex; align-items:center; gap:4px; padding:3px 10px;
    border-radius:var(--radius-full); font-size:0.75rem; font-weight:600;
    text-transform:uppercase; letter-spacing:0.04em;
}
.abadge-green { background:rgba(52,211,153,0.12); color:var(--green); border:1px solid rgba(52,211,153,0.2); }
.abadge-red { background:rgba(248,113,113,0.12); color:var(--red); border:1px solid rgba(248,113,113,0.2); }
.abadge-yellow { background:rgba(251,191,36,0.12); color:var(--yellow); border:1px solid rgba(251,191,36,0.2); }
.abadge-blue { background:rgba(88,166,255,0.12); color:var(--blue); border:1px solid rgba(88,166,255,0.2); }
.abadge-purple { background:rgba(188,140,255,0.12); color:var(--purple); border:1px solid rgba(188,140,255,0.2); }
.abadge-accent { background:var(--accent-bg); color:var(--accent); border:1px solid rgba(0,212,255,0.2); }

/* Charts */
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; }
.chart-card { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px; }
.chart-card h4 { font-size:0.88rem; font-weight:600; margin-bottom:12px; color:var(--text-bright); }

/* Audit log specific */
.admin-main input[type="date"] {
    color-scheme: dark;
}
#audit-table td { vertical-align:top; }
#audit-table tr:hover td { background:var(--accent-bg); }

@media(max-width:900px) {
    .admin-wrap { flex-direction:column; }
    .admin-nav { width:100%; min-width:100%; position:relative; top:0; height:auto; display:flex; flex-wrap:wrap; padding:12px; gap:4px; }
    .admin-nav-title { display:none; }
    .admin-nav .nav-divider { display:none; }
    .admin-nav a { padding:8px 14px; border-left:none; border-radius:var(--radius-md); font-size:0.8rem; }
    .admin-main { padding:20px; }
    .chart-grid, .admin-card .card-row { grid-template-columns:1fr; }
}

/* Audit detail expandable rows */
.audit-detail-row td { border-left:3px solid var(--accent); background:var(--bg-surface) !important; }
.audit-detail-row:hover td { background:var(--bg-surface) !important; }
#audit-table tbody tr[data-details]:not(.audit-detail-row) { cursor:pointer; }
#audit-table tbody tr[data-details]:not(.audit-detail-row):hover td { background:var(--accent-bg); }

/* Pagination */
#users-pagination button:disabled { opacity:0.4; cursor:not-allowed; }

/* Bulk action bar */
#bulk-bar { animation: slideDown 0.2s ease; }
@keyframes slideDown { from { opacity:0; transform:translateY(-8px); } to { opacity:1; transform:translateY(0); } }
</style>

<div class="admin-wrap">
    <nav class="admin-nav">
        <div class="admin-nav-title">Command Center</div>
        <a href="/admin/overview"<?php echo $active_view === 'overview' ? ' class="active"' : ''; ?>><span class="nav-icon">&#9632;</span> Overview</a>
        <a href="/admin/users"<?php echo $active_view === 'users' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128100;</span> Users</a>
        <a href="/admin/masters"<?php echo $active_view === 'masters' ? ' class="active"' : ''; ?>><span class="nav-icon">&#9733;</span> Licensing</a>
        <a href="/admin/tokens"<?php echo $active_view === 'tokens' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128273;</span> Tokens</a>
        <div class="nav-divider"></div>
        <a href="/admin/revenue"<?php echo $active_view === 'revenue' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128176;</span> Revenue</a>
        <a href="/admin/telemetry"<?php echo $active_view === 'telemetry' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128300;</span> Intelligence</a>
        <div class="nav-divider"></div>
        <a href="/admin/webhooks"<?php echo $active_view === 'webhooks' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128232;</span> Events</a>
        <a href="/admin/system"<?php echo $active_view === 'system' ? ' class="active"' : ''; ?>><span class="nav-icon">&#9881;</span> System</a>
        <a href="/admin/site"<?php echo $active_view === 'site' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128202;</span> Site Analytics</a>
        <a href="/admin/audit"<?php echo $active_view === 'audit' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128209;</span> Audit Log</a>
        <a href="/admin/billing"<?php echo $active_view === 'billing' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128179;</span> Billing &amp; Costs</a>
        <a href="/admin/expenses"<?php echo $active_view === 'expenses' ? ' class="active"' : ''; ?>><span class="nav-icon">&#128206;</span> Expenses</a>
        <a href="/admin/settings"<?php echo $active_view === 'settings' ? ' class="active"' : ''; ?>><span class="nav-icon">&#9881;</span> Settings</a>
        <div class="nav-divider"></div>
        <a href="/" style="color:var(--text-muted)"><span class="nav-icon">&#8594;</span> View Website</a>
        <a href="/dashboard" style="color:var(--text-muted)"><span class="nav-icon">&#8594;</span> My Dashboard</a>
    </nav>

    <main class="admin-main">

<?php if ($active_view === 'overview'):
    // Compute overview telemetry stats
    // Count paired reports as 1 logical run (Forge Parallax = Break + Assure)
    $ov_unique_machines = count($telem_machines);
    $ov_verified = 0;
    $ov_certified = 0;
    $ov_paired_ids = [];
    $ov_total_pass = 0;
    $ov_models = [];
    $ov_logical_runs = 0;
    $ov_seen_pairs = [];
    foreach ($telem_reports as $tr) {
        $rid = $tr['run_id'] ?? '';
        $pid = $tr['paired_run_id'] ?? '';
        if (($tr['sig_status'] ?? '') === 'verified') $ov_verified++;
        if (!empty($tr['_verification']['origin_certified'])) $ov_certified++;
        $ov_models[$tr['model'] ?? 'unknown'] = true;

        // Count logical runs: paired reports share one run
        if ($pid && isset($ov_seen_pairs[$pid])) {
            // This is the second half of an already-counted pair
            $ov_seen_pairs[$rid] = true;
        } else {
            $ov_logical_runs++;
            if ($pid) $ov_seen_pairs[$rid] = true;
            $ov_total_pass += round(($tr['pass_rate'] ?? 0) * 100, 1);
        }
        if ($pid) $ov_paired_ids[$rid] = $pid;
    }
    $ov_parallax_pairs = 0;
    foreach ($ov_paired_ids as $r => $p) {
        if (isset($ov_paired_ids[$p])) $ov_parallax_pairs++;
    }
    $ov_parallax_pairs = intdiv($ov_parallax_pairs, 2);
    $ov_avg_pass = $ov_logical_runs > 0 ? round($ov_total_pass / $ov_logical_runs, 1) : 0;
    $ov_avg_class = $ov_avg_pass >= 85 ? 'text-green' : ($ov_avg_pass >= 70 ? 'text-yellow' : 'text-red');
    // Certified = count pairs as 1 certification
    $ov_certified_logical = intdiv($ov_certified, 2) + ($ov_certified % 2);
    $ov_all_users = db_get_all_users();
    $ov_user_count = count($ov_all_users);
?>
        <!-- ══════════════ OVERVIEW ══════════════ -->
        <h2 style="margin-bottom:24px">Overview</h2>

        <!-- Platform Stats -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo $ov_user_count; ?></span>
                <span class="stat-label">Registered Users</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_masters; ?></span>
                <span class="stat-label">Licensed Installs</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-green">$<?php echo number_format($total_revenue / 100, 0); ?></span>
                <span class="stat-label">Revenue</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_puppets; ?></span>
                <span class="stat-label">Active Puppets</span>
            </div>
        </div>

        <!-- Matrix Stats -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo $ov_logical_runs; ?></span>
                <span class="stat-label">Matrix Runs</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo count($ov_models); ?></span>
                <span class="stat-label">Models Tested</span>
            </div>
            <div class="stat-card">
                <span class="stat-value <?php echo $ov_avg_class; ?>"><?php echo $ov_avg_pass; ?>%</span>
                <span class="stat-label">Avg Pass Rate</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $ov_unique_machines; ?></span>
                <span class="stat-label">Contributors</span>
            </div>
        </div>

        <!-- Verification summary -->
        <?php if ($ov_logical_runs > 0): ?>
        <div class="card" style="margin-bottom:24px;padding:16px 20px">
            <div style="display:flex;gap:32px;align-items:center;flex-wrap:wrap">
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="color:var(--accent);font-weight:700;font-size:1.3em"><?php echo $ov_parallax_pairs; ?></span>
                    <span class="text-dim text-sm">Parallax Pairs</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="color:#ffd700;font-weight:700;font-size:1.3em"><?php echo $ov_certified_logical; ?></span>
                    <span class="text-dim text-sm">Origin Certified</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="color:var(--green);font-weight:700;font-size:1.3em"><?php echo $ov_verified; ?>/<?php echo count($telem_reports); ?></span>
                    <span class="text-dim text-sm">Signatures Valid</span>
                </div>
            </div>
        </div>
        <?php endif; ?>

        <!-- Quick Actions -->
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:16px">Quick Actions</h3>
            <div class="flex flex-wrap gap-sm">
                <a href="/admin/users" class="btn btn-primary btn-sm">Manage Users</a>
                <a href="/admin/telemetry" class="btn btn-secondary btn-sm">Intelligence Center</a>
                <a href="/admin/audit" class="btn btn-secondary btn-sm">Audit Log</a>
                <a href="/admin/masters" class="btn btn-secondary btn-sm">Passports</a>
            </div>
        </div>

        <!-- Recent Masters -->
        <div class="card" style="margin-bottom:24px">
            <div class="flex-between" style="margin-bottom:16px">
                <h3 style="margin:0">Recent Masters</h3>
                <a href="/admin/masters" class="text-sm">View all &rarr;</a>
            </div>
            <?php if (empty($masters)): ?>
                <div class="empty-state"><p>No masters yet.</p></div>
            <?php else: ?>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Label</th><th>Tier</th><th>Seats</th><th>Status</th><th>Issued</th></tr></thead>
                        <tbody>
                        <?php
                        $recent = array_slice($masters, 0, 5);
                        foreach ($recent as $m):
                            $tc = $m['tier'] === 'origin' ? '#f59e0b' : ($m['tier'] === 'power' ? 'var(--purple)' : ($m['tier'] === 'pro' ? 'var(--accent)' : 'var(--green)'));
                            $status = $m['revoked'] ? 'Revoked' : ($m['activated'] ? 'Active' : 'Pending');
                            $sb = $m['revoked'] ? 'badge-red' : ($m['activated'] ? 'badge-green' : 'badge-yellow');
                            $seats_display = $m['seats'] < 0 ? '&infin;' : $m['puppets_active'] . '/' . max(0, $m['seats'] - 1);
                            $issued_str = '—';
                            if ($m['issued']) {
                                $issued_str = htmlspecialchars(substr($m['issued'], 0, 10));
                            } elseif (!empty($m['activated_at'])) {
                                $issued_str = htmlspecialchars(substr($m['activated_at'], 0, 10));
                            }
                        ?>
                        <tr>
                            <td><?php echo htmlspecialchars($m['label']); ?></td>
                            <td style="color:<?php echo $tc; ?>;font-weight:600"><?php echo ucfirst($m['tier']); ?></td>
                            <td><?php echo $seats_display; ?></td>
                            <td><span class="badge <?php echo $sb; ?>"><?php echo $status; ?></span></td>
                            <td class="text-dim text-sm"><?php echo $issued_str; ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            <?php endif; ?>
        </div>

        <!-- Recent Webhooks -->
        <div class="card">
            <div class="flex-between" style="margin-bottom:16px">
                <h3 style="margin:0">Recent Webhooks</h3>
                <a href="/admin/webhooks" class="text-sm">View all &rarr;</a>
            </div>
            <?php if (empty($webhook_entries)): ?>
                <div class="empty-state"><p>No webhook events yet.</p></div>
            <?php else: ?>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Time</th><th>Event</th><th>Details</th></tr></thead>
                        <tbody>
                        <?php foreach (array_slice($webhook_entries, 0, 8) as $wh):
                            $evt = isset($wh['event']) ? $wh['event'] : 'unknown';
                            $ec = ($evt === 'master_created' || $evt === 'checkout.session.completed') ? 'text-green' : ($evt === 'error' || $evt === 'signature_failed' ? 'text-red' : 'text-dim');
                        ?>
                        <tr>
                            <td class="text-dim text-sm nowrap"><?php echo isset($wh['timestamp']) ? htmlspecialchars(substr($wh['timestamp'], 0, 19)) : '—'; ?></td>
                            <td><span class="<?php echo $ec; ?> font-bold"><?php echo htmlspecialchars($evt); ?></span></td>
                            <td class="text-dim text-sm"><?php
                                $details = array();
                                if (isset($wh['account_id'])) $details[] = 'acct:' . substr($wh['account_id'], 0, 12);
                                if (isset($wh['tier'])) $details[] = 'tier:' . $wh['tier'];
                                if (isset($wh['email'])) $details[] = $wh['email'];
                                if (isset($wh['msg'])) $details[] = $wh['msg'];
                                echo htmlspecialchars(implode(' | ', $details));
                            ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            <?php endif; ?>
        </div>

        <!-- Recent Matrix Reports -->
        <?php if (!empty($telem_reports)): ?>
        <div class="card" style="margin-bottom:24px">
            <div class="flex-between" style="margin-bottom:16px">
                <h3 style="margin:0">Recent Matrix Reports</h3>
                <a href="/admin/telemetry" class="text-sm">View all &rarr;</a>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Date</th><th>Model</th><th>Score</th><th>Scenarios</th><th>Machine</th><th>Sig</th></tr></thead>
                    <tbody>
                    <?php foreach (array_slice($telem_reports, 0, 5) as $rr):
                        $rr_pct = round(($rr['pass_rate'] ?? 0) * 100, 1);
                        $rr_cls = $rr_pct >= 85 ? 'text-green' : ($rr_pct >= 70 ? 'text-yellow' : 'text-red');
                        $rr_sig = ($rr['sig_status'] ?? '') === 'verified';
                    ?>
                    <tr>
                        <td class="text-dim text-sm nowrap"><?php echo ($rr['generated_at'] ?? 0) > 0 ? date('M j H:i', (int)$rr['generated_at']) : '-'; ?></td>
                        <td><span class="model-chip"><?php echo htmlspecialchars($rr['model'] ?? 'unknown'); ?></span></td>
                        <td><span class="<?php echo $rr_cls; ?>" style="font-weight:700"><?php echo $rr_pct; ?>%</span></td>
                        <td class="text-dim"><?php echo (int)($rr['scenarios_passed'] ?? 0); ?>/<?php echo (int)($rr['scenarios_run'] ?? 0); ?></td>
                        <td><code style="font-size:0.8em"><?php echo htmlspecialchars(substr($rr['machine_id'] ?? '', 0, 12)); ?></code></td>
                        <td><?php echo $rr_sig ? '<span class="badge badge-green" style="font-size:0.7em">Verified</span>' : '<span class="badge badge-red" style="font-size:0.7em">No</span>'; ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

<?php elseif ($active_view === 'users'): ?>
        <!-- ══════════════ USERS ══════════════ -->
        <h2 style="margin-bottom:24px">All Users</h2>
<?php
    $all_users = db_get_all_users();

    // Build lookup: email → master info (for tier badges)
    $email_to_master = [];
    foreach ($masters as $m) {
        $email = $m['email'] ?? '';
        if ($email) $email_to_master[strtolower($email)] = $m;
    }

    // Build lookup: email → token info
    $email_to_tokens = [];
    $all_tokens_for_users = [];
    try {
        $stmt = get_db()->query('SELECT token_hash, role, label, user_email, account_id, created, revoked FROM tokens ORDER BY created DESC');
        $all_tokens_for_users = $stmt->fetchAll() ?: [];
    } catch (Exception $e) {}
    foreach ($all_tokens_for_users as $tk) {
        $em = strtolower($tk['user_email'] ?? '');
        if ($em) $email_to_tokens[$em][] = $tk;
    }

    // Build lookup: machine profiles by account_id
    $account_to_machines = [];
    foreach ($profiles as $mid => $prof) {
        $acct = $prof['account_id'] ?? '';
        if ($acct) $account_to_machines[$acct][] = $prof;
    }

    $total_users = count($all_users);
    $active_count = 0;
    $role_counts = [];
    $tier_counts = [];
    foreach ($all_users as $u) {
        $r = $u['role'] ?? 'standalone';
        $role_counts[$r] = ($role_counts[$r] ?? 0) + 1;
        if (empty($u['disabled'])) $active_count++;

        // Tier comes from DB now (not passport lookup)
        $tier = $u['tier'] ?? 'community';
        if (($u['role'] ?? '') === 'origin') $tier = 'power'; // origin always power-level
        $tier_counts[$tier] = ($tier_counts[$tier] ?? 0) + 1;
    }
?>
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_users; ?></span>
                <span class="stat-label">Total Users</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-green"><?php echo $active_count; ?></span>
                <span class="stat-label">Active</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_users - $active_count; ?></span>
                <span class="stat-label">Disabled</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo count($email_to_master); ?></span>
                <span class="stat-label">Licensed (Masters)</span>
            </div>
        </div>

        <!-- Tier distribution -->
        <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap">
<?php
    $tier_badges = [
        'origin' => ['color' => '#f59e0b', 'icon' => '&#9733;'],
        'power' => ['color' => '#bc8cff', 'icon' => '&#9889;'],
        'pro' => ['color' => '#00d4ff', 'icon' => '&#9670;'],
        'community' => ['color' => '#34d399', 'icon' => '&#9679;'],
    ];
    foreach ($tier_counts as $tier => $cnt):
        $badge = $tier_badges[$tier] ?? $tier_badges['community'];
?>
            <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:8px 16px;display:flex;align-items:center;gap:8px">
                <span style="color:<?php echo $badge['color']; ?>;font-size:1.2em"><?php echo $badge['icon']; ?></span>
                <span style="font-weight:600;color:<?php echo $badge['color']; ?>"><?php echo htmlspecialchars(ucfirst($tier)); ?></span>
                <span class="text-dim">&times;<?php echo $cnt; ?></span>
            </div>
<?php endforeach; ?>
        </div>

        <!-- Search + Export bar -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
            <input type="text" id="users-search" class="form-input" style="width:320px;padding:8px 14px;font-size:0.88em" placeholder="Search by email, name, tier, role...">
            <div class="flex gap-sm">
                <button class="btn btn-secondary btn-sm" onclick="exportCSV('export_users')">Export CSV</button>
            </div>
        </div>

        <!-- Bulk actions bar (hidden until checkboxes selected) -->
        <div id="bulk-bar" style="display:none;align-items:center;gap:12px;margin-bottom:12px;padding:8px 16px;background:var(--bg-card);border:1px solid var(--accent);border-radius:var(--radius-md)">
            <span class="text-sm"><strong id="bulk-count">0</strong> selected</span>
            <button class="btn btn-secondary btn-sm" onclick="bulkAction('enable')">Enable</button>
            <button class="btn btn-secondary btn-sm" onclick="bulkAction('disable')">Disable</button>
            <button class="btn btn-secondary btn-sm" onclick="bulkAction('set_tier')">Set Tier</button>
        </div>

        <!-- Users table -->
        <div class="table-wrap">
            <table id="users-table">
                <thead>
                    <tr>
                        <th style="width:30px"><input type="checkbox" id="bulk-select-all" title="Select all"></th>
                        <th>User</th>
                        <th>Tier</th>
                        <th>Fleet Role</th>
                        <th>Admin</th>
                        <th>Status</th>
                        <th>Tokens</th>
                        <th>Machines</th>
                        <th>Registered</th>
                    </tr>
                </thead>
                <tbody>
<?php foreach ($all_users as $u):
    $em = strtolower($u['email'] ?? '');
    $role = $u['role'] ?? 'standalone';
    $label = $u['label'] ?? $em;
    $disabled = !empty($u['disabled']);
    $created = $u['created'] ?? '';

    // Tier from DB
    $tier = $u['tier'] ?? 'community';
    if ($role === 'origin') $tier = 'power';
    $user_is_admin = !empty($u['is_admin']) || $role === 'origin';
    $badge = $tier_badges[$tier] ?? $tier_badges['community'];
    $mst = $email_to_master[$em] ?? null;
    $account_id = $mst ? ($mst['account_id'] ?? '') : '';

    // Token count
    $user_tokens = $email_to_tokens[$em] ?? [];
    $active_tokens = array_filter($user_tokens, fn($t) => empty($t['revoked']));

    // Machine count — try master passport first, then token account_id
    $machines = [];
    if ($account_id) {
        $machines = $account_to_machines[$account_id] ?? [];
    }
    if (empty($machines) && !empty($user_tokens)) {
        foreach ($user_tokens as $_tk) {
            $_tk_acct = $_tk['account_id'] ?? '';
            if ($_tk_acct && isset($account_to_machines[$_tk_acct])) {
                $machines = $account_to_machines[$_tk_acct];
                break;
            }
        }
    }

    $em_attr = htmlspecialchars($em, ENT_QUOTES);
?>
                    <tr data-email="<?php echo $em_attr; ?>"<?php echo $disabled ? ' style="opacity:0.5"' : ''; ?>>
                        <td><?php if ($role !== 'origin'): ?><input type="checkbox" class="bulk-cb" data-email="<?php echo $em_attr; ?>"><?php endif; ?></td>
                        <td>
                            <div style="font-weight:600"><?php echo htmlspecialchars($label); ?></div>
                            <div class="text-dim text-sm"><?php echo htmlspecialchars($em); ?></div>
                        </td>
                        <td>
<?php if ($role === 'origin'): ?>
                            <span style="color:<?php echo $badge['color']; ?>;font-weight:700">Power</span>
<?php else: ?>
                            <select class="form-input" style="padding:3px 6px;font-size:0.78rem;width:auto" data-prev="<?php echo htmlspecialchars($tier); ?>" onchange="changeUserTier(this.closest('tr').dataset.email,this.value,this)">
                                <?php foreach (['community','pro','power'] as $t_opt): ?>
                                <option value="<?php echo $t_opt; ?>"<?php echo $tier === $t_opt ? ' selected' : ''; ?>><?php echo ucfirst($t_opt); ?></option>
                                <?php endforeach; ?>
                            </select>
<?php endif; ?>
                        </td>
                        <td>
<?php if ($role === 'origin'): ?>
                            <span class="text-dim text-sm">Origin</span>
<?php else: ?>
                            <select class="form-input" style="padding:3px 6px;font-size:0.78rem;width:auto" data-prev="<?php echo htmlspecialchars($role); ?>" onchange="changeUserRole(this.closest('tr').dataset.email,this.value,this)">
                                <?php foreach (['standalone','master','puppet'] as $r_opt): ?>
                                <option value="<?php echo $r_opt; ?>"<?php echo $role === $r_opt ? ' selected' : ''; ?>><?php echo ucfirst($r_opt); ?></option>
                                <?php endforeach; ?>
                            </select>
<?php endif; ?>
                        </td>
                        <td>
<?php if ($role === 'origin'): ?>
                            <span style="color:var(--yellow);font-weight:600">Origin</span>
<?php else: ?>
                            <input type="checkbox" <?php echo $user_is_admin ? 'checked' : ''; ?> onchange="toggleAdmin(this.closest('tr').dataset.email,this.checked)" title="Website admin access">
<?php endif; ?>
                        </td>
                        <td class="user-status-cell">
<?php if ($role !== 'origin'): ?>
                            <?php if ($disabled): ?>
                            <button class="btn btn-secondary" style="padding:2px 8px;font-size:0.72em" data-action="enable" data-email="<?php echo $em_attr; ?>">Enable</button>
                            <?php else: ?>
                            <span class="badge badge-green" style="cursor:pointer" data-action="disable" data-email="<?php echo $em_attr; ?>" title="Click to disable">Active</span>
                            <?php endif; ?>
<?php else: ?>
                            <span class="badge badge-green">Active</span>
<?php endif; ?>
                        </td>
                        <td style="font-weight:600"><?php echo count($active_tokens); ?></td>
                        <td><?php echo count($machines) > 0 ? '<span style="font-weight:600">' . count($machines) . '</span>' : '<span class="text-dim">—</span>'; ?></td>
                        <td class="text-dim text-sm"><?php echo htmlspecialchars(substr($created, 0, 10)); ?></td>
                    </tr>
<?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <div id="users-pagination" style="display:flex;align-items:center;justify-content:center;gap:8px;margin-top:16px"></div>

<?php elseif ($active_view === 'masters'): ?>
        <!-- ══════════════ MASTERS ══════════════ -->
        <div class="flex-between" style="margin-bottom:24px; flex-wrap:wrap; gap:12px">
            <h2 style="margin:0">Masters (<?php echo $total_masters; ?>)</h2>
            <div class="flex gap-sm">
                <input type="text" class="form-input form-input-mono" style="width:240px" placeholder="Search masters..." data-filter-target="masters-table">
                <button class="btn btn-primary btn-sm" onclick="openModal('modal-generate')">Generate New</button>
            </div>
        </div>

        <?php if (empty($masters)): ?>
            <div class="card"><div class="empty-state"><p>No masters registered yet.</p></div></div>
        <?php else: ?>
            <div class="table-wrap">
                <table id="masters-table">
                    <thead>
                        <tr>
                            <th>Label</th>
                            <th>Email</th>
                            <th>Tier</th>
                            <th>Seats</th>
                            <th>Puppets</th>
                            <th>Status</th>
                            <th>Last Seen</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                    <?php foreach ($masters as $m):
                        $tc = $m['tier'] === 'power' ? 'badge-purple' : ($m['tier'] === 'pro' ? 'badge-blue' : 'badge-green');
                        $status = $m['revoked'] ? 'Revoked' : ($m['activated'] ? 'Active' : 'Pending');
                        $sb = $m['revoked'] ? 'badge-red' : ($m['activated'] ? 'badge-green' : 'badge-yellow');
                    ?>
                    <tr>
                        <td class="font-bold"><?php echo htmlspecialchars($m['label']); ?></td>
                        <td class="text-sm"><?php echo htmlspecialchars($m['email'] ? $m['email'] : '—'); ?></td>
                        <td><span class="badge <?php echo $tc; ?>"><?php echo ucfirst($m['tier']); ?></span></td>
                        <td><?php echo $m['seats'] < 0 ? '&infin;' : $m['seats']; ?></td>
                        <td><?php echo $m['seats'] < 0 ? ($m['puppets_active'] . '/&infin;') : ($m['puppets_active'] . '/' . max(0, $m['seats'] - 1)); ?></td>
                        <td><span class="badge <?php echo $sb; ?>"><?php echo $status; ?></span></td>
                        <td class="text-dim text-sm"><?php echo $m['last_seen'] ? htmlspecialchars(substr($m['last_seen'], 0, 10)) : '—'; ?></td>
                        <td>
                            <div class="dropdown">
                                <button class="btn btn-ghost btn-sm dropdown-toggle">&#8943;</button>
                                <div class="dropdown-menu">
                                    <a href="account.php?account_id=<?php echo urlencode($m['account_id']); ?>" class="dropdown-item">View Account</a>
                                    <a href="analytics.php?view=my_fleet&account_id=<?php echo urlencode($m['account_id']); ?>" class="dropdown-item">View Fleet</a>
                                    <?php if (!$m['revoked']): ?>
                                    <div class="dropdown-divider"></div>
                                    <button class="dropdown-item danger" data-revoke-account="<?php echo htmlspecialchars($m['account_id'], ENT_QUOTES); ?>" data-revoke-label="<?php echo htmlspecialchars($m['label'], ENT_QUOTES); ?>">Revoke</button>
                                    <?php endif; ?>
                                </div>
                            </div>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>

<?php elseif ($active_view === 'tokens'): ?>
        <!-- ══════════════ TOKENS ══════════════ -->
<?php
    $auto_count = 0; $manual_count = 0; $active_tok = 0; $revoked_tok = 0;
    foreach ($token_list as $tk) {
        if ($tk['source'] === 'registration') $auto_count++; else $manual_count++;
        if ($tk['revoked']) $revoked_tok++; else $active_tok++;
    }
?>
        <div class="flex-between" style="margin-bottom:24px; flex-wrap:wrap; gap:12px">
            <h2 style="margin:0">API Tokens</h2>
            <div class="flex gap-sm">
                <input type="text" class="form-input" style="width:200px" placeholder="Search..." data-filter-target="tokens-table">
                <button class="btn btn-primary btn-sm" onclick="openModal('modal-token')">+ Manual Token</button>
            </div>
        </div>

        <div class="grid-4" style="margin-bottom:20px">
            <div class="stat-card"><span class="stat-value"><?php echo count($token_list); ?></span><span class="stat-label">Total</span></div>
            <div class="stat-card"><span class="stat-value text-green"><?php echo $active_tok; ?></span><span class="stat-label">Active</span></div>
            <div class="stat-card"><span class="stat-value" style="color:var(--accent)"><?php echo $auto_count; ?></span><span class="stat-label">Auto (Registration)</span></div>
            <div class="stat-card"><span class="stat-value" style="color:var(--yellow)"><?php echo $manual_count; ?></span><span class="stat-label">Manual (Admin)</span></div>
        </div>

        <div class="table-wrap">
            <table id="tokens-table">
                <thead><tr><th>Label</th><th>Source</th><th>Role</th><th>User</th><th>Created</th><th>Status</th><th>Hash</th><th>Actions</th></tr></thead>
                <tbody>
                <?php foreach ($token_list as $tok):
                    $role_colors = ['origin'=>'badge-purple','admin'=>'badge-blue','master'=>'badge-green','puppet'=>'badge-yellow','standalone'=>''];
                    $rb = $role_colors[$tok['role']] ?? '';
                    $src_badge = $tok['source'] === 'registration'
                        ? '<span style="color:var(--accent);font-size:0.75rem;font-weight:600">AUTO</span>'
                        : '<span style="color:var(--yellow);font-size:0.75rem;font-weight:600">MANUAL</span>';
                ?>
                <tr>
                    <td style="font-weight:600"><?php echo htmlspecialchars($tok['label']); ?></td>
                    <td><?php echo $src_badge; ?></td>
                    <td><span class="badge <?php echo $rb; ?>"><?php echo ucfirst($tok['role']); ?></span></td>
                    <td class="text-sm"><?php echo $tok['user_email'] ? htmlspecialchars($tok['user_email']) : '<span class="text-dim">—</span>'; ?></td>
                    <td class="text-dim text-sm"><?php echo $tok['created'] ? htmlspecialchars(substr($tok['created'], 0, 10)) : '—'; ?></td>
                    <td>
                        <?php if ($tok['revoked']): ?>
                            <span class="badge badge-red">Revoked</span>
                        <?php else: ?>
                            <span class="badge badge-green">Active</span>
                        <?php endif; ?>
                    </td>
                    <td class="text-mono text-sm text-dim"><?php echo htmlspecialchars($tok['hash_prefix']); ?></td>
                    <td>
                        <?php if (!$tok['revoked']): ?>
                        <button class="btn btn-ghost btn-sm text-red" data-revoke-hash="<?php echo htmlspecialchars($tok['hash'], ENT_QUOTES); ?>" data-revoke-label="<?php echo htmlspecialchars($tok['label'], ENT_QUOTES); ?>">Revoke</button>
                        <?php else: ?>
                        <span class="text-dim text-sm">—</span>
                        <?php endif; ?>
                    </td>
                </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>

<?php elseif ($active_view === 'revenue'): ?>
        <!-- ══════════════ REVENUE ══════════════ -->
        <h2 style="margin-bottom:24px">Revenue</h2>

        <div class="grid-4" style="margin-bottom:32px">
            <div class="stat-card">
                <span class="stat-value text-green">$<?php echo number_format($total_revenue / 100, 0); ?></span>
                <span class="stat-label">Total Revenue</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $paid_customers; ?></span>
                <span class="stat-label">Paid Customers</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $paid_customers > 0 ? '$' . number_format(($total_revenue / 100) / $paid_customers, 0) : '$0'; ?></span>
                <span class="stat-label">Avg Revenue / Customer</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $granted_count; ?></span>
                <span class="stat-label">Granted Licenses</span>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">
            <?php if (!empty($tier_breakdown)): ?>
            <div class="card" style="padding:20px">
                <h3 style="margin-bottom:12px">Revenue Distribution</h3>
                <canvas id="rev-chart" height="140"></canvas>
            </div>
            <div class="card" style="padding:20px">
                <h3 style="margin-bottom:16px">Revenue by Tier</h3>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Tier</th><th>Price</th><th>Customers</th><th>Revenue</th><th>Seats</th></tr></thead>
                        <tbody>
                        <?php foreach ($tier_breakdown as $tid => $tb):
                            $tc_map2 = ['origin'=>'#f59e0b','power'=>'#bc8cff','pro'=>'#00d4ff','community'=>'#34d399'];
                            $tc = $tc_map2[$tid] ?? '#666';
                            $tier_price = isset($tiers_config[$tid]['price_cents']) ? (int)$tiers_config[$tid]['price_cents'] : 0;
                        ?>
                        <tr>
                            <td class="font-bold" style="color:<?php echo $tc; ?>"><?php echo ucfirst($tid); ?></td>
                            <td><?php echo $tier_price > 0 ? '$' . number_format($tier_price / 100, 0) : 'Free'; ?></td>
                            <td><?php echo $tb['count']; ?></td>
                            <td class="font-bold text-green">$<?php echo number_format($tb['revenue'] / 100, 0); ?></td>
                            <td><?php echo $tb['seats']; ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
            <?php else: ?>
            <div class="card" style="padding:20px;grid-column:span 2">
                <div class="empty-state"><p>No paid customers yet.</p></div>
            </div>
            <?php endif; ?>
        </div>

        <?php
        // Split masters into paid vs granted for detail tables
        $paid_masters = [];
        $granted_masters = [];
        foreach ($masters as $m) {
            if ($m['amount_paid'] > 0) {
                $paid_masters[] = $m;
            } elseif ($m['tier'] !== 'origin') {
                $granted_masters[] = $m;
            }
        }
        $tc_map = ['origin'=>'#f59e0b','power'=>'#bc8cff','pro'=>'#00d4ff','community'=>'#34d399'];
        ?>

        <!-- Paid Customers detail -->
        <?php if (!empty($paid_masters)): ?>
        <div class="card" style="padding:20px;margin-bottom:24px">
            <h3 style="margin-bottom:16px">Paid Customers <span class="badge badge-green"><?php echo count($paid_masters); ?></span></h3>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Customer</th><th>Tier</th><th>Paid</th><th>Status</th><th>Seats</th><th>Issued</th></tr></thead>
                    <tbody>
                    <?php foreach ($paid_masters as $pm):
                        $pm_tc = $tc_map[$pm['tier']] ?? '#666';
                        $pm_status = $pm['revoked'] ? 'Revoked' : ($pm['activated'] ? 'Active' : 'Pending');
                        $pm_sb = $pm['revoked'] ? 'badge-red' : ($pm['activated'] ? 'badge-green' : 'badge-yellow');
                        $pm_label = $pm['label'] ?: ($pm['email'] ?: $pm['account_id']);
                        $pm_email = $pm['email'];
                        $pm_seats = $pm['seats'] < 0 ? '&infin;' : $pm['puppets_active'] . '/' . max(0, $pm['seats'] - 1);
                        $pm_issued = $pm['issued'] ? substr($pm['issued'], 0, 10) : ($pm['activated_at'] ? substr($pm['activated_at'], 0, 10) : '-');
                    ?>
                    <tr>
                        <td>
                            <div style="font-weight:600"><?php echo htmlspecialchars($pm_label); ?></div>
                            <?php if ($pm_email): ?>
                            <a href="/admin/users?search=<?php echo urlencode($pm_email); ?>" class="text-dim text-sm" style="text-decoration:none"><?php echo htmlspecialchars($pm_email); ?></a>
                            <?php endif; ?>
                        </td>
                        <td style="color:<?php echo $pm_tc; ?>;font-weight:600"><?php echo ucfirst($pm['tier']); ?></td>
                        <td class="font-bold text-green">$<?php echo number_format($pm['amount_paid'] / 100, 0); ?></td>
                        <td><span class="badge <?php echo $pm_sb; ?>"><?php echo $pm_status; ?></span></td>
                        <td><?php echo $pm_seats; ?></td>
                        <td class="text-dim text-sm"><?php echo htmlspecialchars($pm_issued); ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- Granted Licenses detail -->
        <?php if (!empty($granted_masters)): ?>
        <div class="card" style="padding:20px;margin-bottom:24px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;cursor:pointer" onclick="var t=document.getElementById('grants-detail');t.style.display=t.style.display==='none'?'block':'none';this.querySelector('.toggle-arrow').textContent=t.style.display==='none'?'\u25B6':'\u25BC'">
                <h3 style="margin:0">Granted Licenses <span class="badge" style="background:rgba(102,217,239,0.12);color:var(--accent)"><?php echo count($granted_masters); ?></span></h3>
                <span class="toggle-arrow text-dim" style="font-size:0.8em">&#9660;</span>
            </div>
            <div id="grants-detail">
                <p class="text-dim text-sm" style="margin-bottom:12px">Admin-issued, sponsor, and Origin licenses (no payment)</p>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>User</th><th>Tier</th><th>Status</th><th>Seats</th><th>Issued</th></tr></thead>
                        <tbody>
                        <?php foreach ($granted_masters as $gm):
                            $gm_tc = $tc_map[$gm['tier']] ?? '#666';
                            $gm_status = $gm['revoked'] ? 'Revoked' : ($gm['activated'] ? 'Active' : 'Pending');
                            $gm_sb = $gm['revoked'] ? 'badge-red' : ($gm['activated'] ? 'badge-green' : 'badge-yellow');
                            $gm_label = $gm['label'] ?: ($gm['email'] ?: $gm['account_id']);
                            $gm_email = $gm['email'];
                            $gm_seats = $gm['seats'] < 0 ? '&infin;' : $gm['puppets_active'] . '/' . max(0, $gm['seats'] - 1);
                            $gm_issued = $gm['issued'] ? substr($gm['issued'], 0, 10) : ($gm['activated_at'] ? substr($gm['activated_at'], 0, 10) : '-');
                        ?>
                        <tr>
                            <td>
                                <div style="font-weight:600"><?php echo htmlspecialchars($gm_label); ?></div>
                                <?php if ($gm_email): ?>
                                <a href="/admin/users?search=<?php echo urlencode($gm_email); ?>" class="text-dim text-sm" style="text-decoration:none"><?php echo htmlspecialchars($gm_email); ?></a>
                                <?php endif; ?>
                            </td>
                            <td style="color:<?php echo $gm_tc; ?>;font-weight:600"><?php echo ucfirst($gm['tier']); ?></td>
                            <td><span class="badge <?php echo $gm_sb; ?>"><?php echo $gm_status; ?></span></td>
                            <td><?php echo $gm_seats; ?></td>
                            <td class="text-dim text-sm"><?php echo htmlspecialchars($gm_issued); ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <?php endif; ?>

        <?php if (!empty($tier_breakdown)): ?>
        <script>
        (function(){
            var cs = getComputedStyle(document.documentElement);
            Chart.defaults.color = cs.getPropertyValue('--text-dim').trim();
            var labels = <?php echo json_encode(array_map('ucfirst', array_keys($tier_breakdown))); ?>;
            var data = <?php echo json_encode(array_map(function($tb){ return round($tb['revenue']/100); }, array_values($tier_breakdown))); ?>;
            var colors = [<?php echo implode(',', array_map(function($t){ $m=['origin'=>'#f59e0b','power'=>'#bc8cff','pro'=>'#00d4ff','community'=>'#34d399']; return "'".($m[$t]??'#666')."'"; }, array_keys($tier_breakdown))); ?>];
            new Chart(document.getElementById('rev-chart'), {
                type: 'doughnut',
                data: {labels: labels, datasets: [{data: data, backgroundColor: colors, borderWidth: 0}]},
                options: {responsive: true, plugins: {legend: {position: 'bottom'}}}
            });
        })();
        </script>
        <?php endif; ?>

<?php elseif ($active_view === 'webhooks'): ?>
        <!-- ══════════════ WEBHOOKS ══════════════ -->
        <h2 style="margin-bottom:24px">Webhook Events</h2>
<?php
    // Webhook stats
    $wh_success = 0; $wh_error = 0; $wh_other = 0;
    $wh_by_type = [];
    foreach ($webhook_entries as $wh) {
        $evt = $wh['event'] ?? 'unknown';
        $wh_by_type[$evt] = ($wh_by_type[$evt] ?? 0) + 1;
        if (in_array($evt, ['master_created','checkout.session.completed','passport_activated'])) $wh_success++;
        elseif (in_array($evt, ['error','signature_failed','webhook_error'])) $wh_error++;
        else $wh_other++;
    }
?>
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card"><span class="stat-value"><?php echo count($webhook_entries); ?></span><span class="stat-label">Total Events</span></div>
            <div class="stat-card"><span class="stat-value text-green"><?php echo $wh_success; ?></span><span class="stat-label">Success</span></div>
            <div class="stat-card"><span class="stat-value text-red"><?php echo $wh_error; ?></span><span class="stat-label">Errors</span></div>
            <div class="stat-card"><span class="stat-value"><?php echo $wh_other; ?></span><span class="stat-label">Other</span></div>
        </div>

        <?php if (empty($webhook_entries)): ?>
            <div class="card"><div class="empty-state"><p>No webhook events recorded yet.</p></div></div>
        <?php else: ?>
        <div class="card" style="padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <h3>Event Log</h3>
                <input type="text" class="form-input" placeholder="Filter..." style="width:180px;padding:6px 12px;font-size:0.85em" oninput="(function(q){document.querySelectorAll('#wh-table tbody tr').forEach(function(r){r.style.display=r.textContent.toLowerCase().indexOf(q)>=0?'':'none'})})(this.value.toLowerCase())">
            </div>
            <div class="table-wrap">
                <table id="wh-table">
                    <thead><tr><th>Time</th><th>Event</th><th>Account</th><th>Tier</th><th>Details</th></tr></thead>
                    <tbody>
                    <?php foreach ($webhook_entries as $wh):
                        $evt = $wh['event'] ?? 'unknown';
                        $is_ok = in_array($evt, ['master_created','checkout.session.completed','passport_activated']);
                        $is_err = in_array($evt, ['error','signature_failed','webhook_error']);
                        $badge_class = $is_ok ? 'badge-green' : ($is_err ? 'badge-red' : 'badge-yellow');
                    ?>
                    <tr>
                        <td class="text-dim text-sm nowrap"><?php echo isset($wh['timestamp']) ? htmlspecialchars(substr($wh['timestamp'], 0, 19)) : '—'; ?></td>
                        <td><span class="badge <?php echo $badge_class; ?>" style="font-size:0.78em"><?php echo htmlspecialchars($evt); ?></span></td>
                        <td class="text-sm"><code><?php echo htmlspecialchars(substr($wh['account_id'] ?? '—', 0, 16)); ?></code></td>
                        <td class="text-sm"><?php echo htmlspecialchars($wh['tier'] ?? '—'); ?></td>
                        <td class="text-dim text-sm"><?php echo htmlspecialchars($wh['email'] ?? $wh['msg'] ?? ''); ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- GitHub Sponsors Events -->
<?php
    $gh_log = __DIR__ . '/data/github_sponsors_log.jsonl';
    $gh_events = [];
    $gh_queue = [];
    if (file_exists($gh_log)) {
        $lines = file($gh_log, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($lines) {
            $lines = array_reverse(array_slice($lines, -50));
            foreach ($lines as $l) {
                $e = json_decode($l, true);
                if ($e) $gh_events[] = $e;
            }
        }
    }
    $queue_file = __DIR__ . '/data/passport_queue.jsonl';
    if (file_exists($queue_file)) {
        $qlines = file($queue_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($qlines) {
            foreach (array_reverse($qlines) as $ql) {
                $q = json_decode($ql, true);
                if ($q) $gh_queue[] = $q;
            }
        }
    }
?>
        <h3 style="margin-top:32px;margin-bottom:16px">GitHub Sponsors</h3>

<?php if (!empty($gh_queue)): ?>
        <div class="card" style="margin-bottom:16px;padding:20px;border-color:var(--yellow)">
            <h4 style="color:var(--yellow);margin-bottom:12px">Pending Passport Generation (<?php echo count($gh_queue); ?>)</h4>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Date</th><th>GitHub User</th><th>Tier</th><th>Amount</th><th>Status</th></tr></thead>
                    <tbody>
                    <?php foreach ($gh_queue as $q):
                        $tc = ($q['tier'] ?? '') === 'power' ? 'var(--purple)' : 'var(--accent)';
                    ?>
                    <tr>
                        <td class="text-dim text-sm"><?php echo htmlspecialchars(substr($q['timestamp'] ?? '', 0, 16)); ?></td>
                        <td style="font-weight:600"><a href="https://github.com/<?php echo htmlspecialchars($q['github_user'] ?? ''); ?>" target="_blank"><?php echo htmlspecialchars($q['github_user'] ?? ''); ?></a></td>
                        <td style="color:<?php echo $tc; ?>;font-weight:600"><?php echo ucfirst(htmlspecialchars($q['tier'] ?? '')); ?></td>
                        <td>$<?php echo number_format(($q['monthly_cents'] ?? 0) / 100, 2); ?>/mo</td>
                        <td><span class="badge badge-yellow"><?php echo htmlspecialchars($q['status'] ?? 'pending'); ?></span></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
<?php endif; ?>

<?php if (!empty($gh_events)): ?>
        <div class="card" style="padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h4>Sponsor Event Log</h4>
                <span class="text-dim text-sm"><?php echo count($gh_events); ?> events</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Date</th><th>Action</th><th>Sponsor</th><th>Tier</th><th>Amount</th></tr></thead>
                    <tbody>
                    <?php foreach ($gh_events as $ge):
                        $act = $ge['action'] ?? '';
                        $act_labels = ['created' => 'New Sponsor', 'cancelled' => 'Cancelled', 'tier_changed' => 'Tier Changed', 'pending_cancellation' => 'Pending Cancel', 'pending_tier_change' => 'Tier Changing', 'edited' => 'Updated'];
                        $act_label = $act_labels[$act] ?? $act;
                        $act_class = $act === 'created' ? 'badge-green' : ($act === 'cancelled' ? 'badge-red' : 'badge-yellow');
                    ?>
                    <tr>
                        <td class="text-dim text-sm"><?php echo htmlspecialchars(substr($ge['timestamp'] ?? '', 0, 16)); ?></td>
                        <td><span class="badge <?php echo $act_class; ?>" style="font-size:0.72em"><?php echo htmlspecialchars($act_label); ?></span></td>
                        <td style="font-weight:600"><a href="https://github.com/<?php echo htmlspecialchars($ge['sponsor'] ?? ''); ?>" target="_blank"><?php echo htmlspecialchars($ge['sponsor'] ?? ''); ?></a></td>
                        <td><?php echo htmlspecialchars($ge['tier'] ?? ''); ?></td>
                        <td>$<?php echo number_format(($ge['monthly_cents'] ?? 0) / 100, 2); ?><?php echo ($ge['is_onetime'] ?? false) ? '' : '/mo'; ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
<?php else: ?>
        <div class="card" style="padding:20px"><p class="text-dim">No GitHub Sponsor events yet. The webhook is active — events will appear here when someone sponsors.</p></div>
<?php endif; ?>

        <!-- API Activity (license revalidation, activations) -->
        <?php
        $api_log_path = __DIR__ . '/data/api_activity.jsonl';
        $api_entries = [];
        if (file_exists($api_log_path)) {
            $api_lines = file($api_log_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            if (is_array($api_lines)) {
                foreach (array_slice($api_lines, -200) as $al) {
                    $ae = json_decode($al, true);
                    if ($ae) $api_entries[] = $ae;
                }
                $api_entries = array_reverse($api_entries);
            }
        }
        if (!empty($api_entries)):
            // Stats
            $api_validates = 0;
            $api_mismatches = 0;
            $api_revoked = 0;
            $api_accounts = [];
            foreach ($api_entries as $ae) {
                if (($ae['action'] ?? '') === 'validate') { $api_validates++; $api_accounts[$ae['account_id'] ?? ''] = true; }
                if (!empty($ae['tier_mismatch'])) $api_mismatches++;
                if (strpos($ae['action'] ?? '', 'revoked') !== false) $api_revoked++;
            }
        ?>
        <div class="card" style="padding:20px;margin-top:24px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <h3 style="margin:0">Passport API Activity</h3>
                <div style="display:flex;gap:16px;align-items:center">
                    <span class="text-dim text-sm"><?php echo $api_validates; ?> validations</span>
                    <span class="text-dim text-sm"><?php echo count($api_accounts); ?> unique accounts</span>
                    <?php if ($api_mismatches > 0): ?>
                    <span class="badge badge-yellow" style="font-size:0.7em"><?php echo $api_mismatches; ?> tier mismatches</span>
                    <?php endif; ?>
                    <?php if ($api_revoked > 0): ?>
                    <span class="badge badge-red" style="font-size:0.7em"><?php echo $api_revoked; ?> revoked</span>
                    <?php endif; ?>
<?php if ($is_origin): ?>
                    <button class="btn btn-sm" style="font-size:0.7em;background:rgba(249,38,114,0.12);color:var(--red);border:1px solid var(--red-border)" onclick="if(confirm('Clear API activity log?')){fetch('/admin.php?ajax=clear_api_log',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({_csrf:CSRF_TOKEN})}).then(r=>r.json()).then(d=>{if(d.ok){showToast('Cleared','success');setTimeout(()=>location.reload(),800)}else showToast(d.error||'Failed','error')})}">Clear</button>
<?php endif; ?>
                </div>
            </div>
            <div style="overflow-x:auto;max-height:400px;overflow-y:auto">
                <table style="font-size:0.82em">
                    <thead><tr><th>Time</th><th>Action</th><th>Account</th><th>Client Tier</th><th>Server Tier</th><th>Mismatch</th><th>IP Hash</th></tr></thead>
                    <tbody>
                    <?php foreach (array_slice($api_entries, 0, 100) as $ae): ?>
                    <tr>
                        <td class="text-dim text-sm nowrap"><?php echo htmlspecialchars(substr($ae['ts'] ?? '', 0, 19)); ?></td>
                        <td><span class="badge <?php echo strpos($ae['action'] ?? '', 'revok') !== false ? 'badge-red' : (strpos($ae['action'] ?? '', 'reject') !== false ? 'badge-red' : 'badge-blue'); ?>" style="font-size:0.72em"><?php echo htmlspecialchars($ae['action'] ?? ''); ?></span></td>
                        <td><code style="font-size:0.82em"><?php echo htmlspecialchars(substr($ae['account_id'] ?? '', 0, 20)); ?></code></td>
                        <td><?php echo htmlspecialchars($ae['client_tier'] ?? '-'); ?></td>
                        <td><?php echo htmlspecialchars($ae['server_tier'] ?? '-'); ?></td>
                        <td><?php echo !empty($ae['tier_mismatch']) ? '<span class="badge badge-yellow" style="font-size:0.7em">YES</span>' : '<span class="text-dim">-</span>'; ?></td>
                        <td class="text-mono text-dim" style="font-size:0.72em"><?php echo htmlspecialchars($ae['ip_hash'] ?? ''); ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

<?php elseif ($active_view === 'system'): ?>
        <!-- ══════════════ SYSTEM ══════════════ -->
        <h2 style="margin-bottom:24px">System Health</h2>

        <div class="grid-3" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo phpversion(); ?></span>
                <span class="stat-label">PHP Version</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo isset($_SERVER['SERVER_SOFTWARE']) ? htmlspecialchars(substr($_SERVER['SERVER_SOFTWARE'], 0, 20)) : 'Unknown'; ?></span>
                <span class="stat-label">Web Server</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-green">Online</span>
                <span class="stat-label">API Status</span>
            </div>
        </div>

        <div class="card" style="margin-bottom:20px">
            <h3 style="margin-bottom:16px">Data Store</h3>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Item</th><th>Count</th><th>Location</th></tr></thead>
                    <tbody>
                        <tr><td>Master Records</td><td class="font-bold"><?php echo $total_masters; ?></td><td class="text-dim text-sm">data/masters/</td></tr>
                        <tr><td>Auth Tokens</td><td class="font-bold"><?php echo count($token_list); ?></td><td class="text-dim text-sm">MySQL tokens table</td></tr>
                        <tr><td>Machine Profiles</td><td class="font-bold"><?php echo $profile_count; ?></td><td class="text-dim text-sm">data/profiles/</td></tr>
                        <tr><td>Revocations</td><td class="font-bold"><?php echo count($revocations); ?></td><td class="text-dim text-sm">data/revocations.json</td></tr>
                        <tr><td>Rate Limit Files</td><td class="font-bold"><?php echo $rate_count; ?></td><td class="text-dim text-sm">rate_limits/</td></tr>
                        <tr><td>Webhook Log Entries</td><td class="font-bold"><?php echo count($webhook_entries); ?> (last 50)</td><td class="text-dim text-sm">data/webhook_log.jsonl</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom:16px">Configuration</h3>
            <div class="info-grid">
                <span class="info-label">Origin Key</span>
                <span class="info-value"><?php echo file_exists(__DIR__ . '/data/origin_key.json') ? '<span class="badge badge-green">Configured</span>' : '<span class="badge badge-red">Missing</span>'; ?></span>

                <span class="info-label">Stripe Config</span>
                <span class="info-value"><?php
                    $sc = file_exists(__DIR__ . '/data/stripe_config.json') ? json_decode(file_get_contents(__DIR__ . '/data/stripe_config.json'), true) : null;
                    $sk = isset($sc['secret_key']) ? $sc['secret_key'] : '';
                    echo (strpos($sk, 'REPLACE') !== false || !$sk) ? '<span class="badge badge-yellow">Not configured</span>' : '<span class="badge badge-green">Configured</span>';
                ?></span>

                <span class="info-label">Tiers Defined</span>
                <span class="info-value"><?php echo count($tiers_config); ?> tiers</span>
            </div>
        </div>

<?php elseif ($active_view === 'site'): ?>
        <!-- ══════════════ SITE ANALYTICS ══════════════ -->
        <?php $total_pv = count($sa_pageviews) ?: 1; ?>
        <div class="flex-between" style="margin-bottom:24px; flex-wrap:wrap; gap:12px">
            <div>
                <h2 style="margin:0">Site Analytics</h2>
                <?php if ($sa_realtime > 0): ?>
                <span class="badge badge-green" style="margin-top:6px;display:inline-block"><?php echo $sa_realtime; ?> visitor<?php echo $sa_realtime !== 1 ? 's' : ''; ?> online now</span>
                <?php endif; ?>
            </div>
            <div class="flex gap-sm">
                <?php
                $ranges = array('today' => 'Today', '7d' => '7 Days', '30d' => '30 Days', 'all' => 'All Time');
                foreach ($ranges as $rv => $rl):
                ?>
                <a href="/admin/site?range=<?php echo $rv; ?>"
                   class="btn btn-sm <?php echo $site_range === $rv ? 'btn-primary' : 'btn-secondary'; ?>"><?php echo $rl; ?></a>
                <?php endforeach; ?>
            </div>
        </div>

        <!-- ─── Top Stats Row ─── -->
        <div class="grid-4" style="margin-bottom:16px">
            <div class="stat-card" title="Distinct browser IDs that visited during this time range">
                <span class="stat-value"><?php echo number_format(count($sa_visitors)); ?></span>
                <span class="stat-label">Unique Visitors</span>
                <span class="stat-hint">Distinct browsers (localStorage ID)</span>
            </div>
            <div class="stat-card" title="Unique visitors who loaded a page today">
                <span class="stat-value text-green"><?php echo number_format(count($sa_today_visitors)); ?></span>
                <span class="stat-label">Today's Visitors</span>
                <span class="stat-hint">Unique visitors today (UTC)</span>
            </div>
            <div class="stat-card" title="Total page loads across all visitors">
                <span class="stat-value"><?php echo number_format(count($sa_pageviews)); ?></span>
                <span class="stat-label">Page Views</span>
                <span class="stat-hint">Total page loads (incl. refreshes)</span>
            </div>
            <div class="stat-card" title="Emails submitted via the waitlist form on checkout.php">
                <span class="stat-value" style="color:var(--purple)"><?php echo number_format($waitlist_count); ?></span>
                <span class="stat-label">Waitlist Signups</span>
                <span class="stat-hint">From checkout page waitlist form</span>
            </div>
        </div>

        <!-- ─── Engagement Stats Row ─── -->
        <div class="grid-4" style="margin-bottom:16px">
            <div class="stat-card" title="Percentage of visitors who clicked any CTA button (Get Started, Buy, Download, etc.)">
                <span class="stat-value"><?php echo $conversion_rate; ?>%</span>
                <span class="stat-label">CTA Conversion</span>
                <span class="stat-hint">% of visitors who clicked a CTA</span>
            </div>
            <div class="stat-card" title="Visitors who viewed only one page and left without any CTA click or scroll event">
                <span class="stat-value"><?php echo $bounce_rate; ?>%</span>
                <span class="stat-label">Bounce Rate</span>
                <span class="stat-hint">Single-page visits with no action</span>
            </div>
            <div class="stat-card" title="Average time between a visitor's first and last event in a session">
                <span class="stat-value"><?php echo $avg_session > 0 ? ($avg_session >= 60 ? round($avg_session / 60, 1) . 'm' : $avg_session . 's') : '—'; ?></span>
                <span class="stat-label">Avg Session</span>
                <span class="stat-hint">Time from first to last event</span>
            </div>
            <div class="stat-card" title="How far down the page visitors scroll on average (100% = reached bottom)">
                <span class="stat-value"><?php
                    $total_scroll = 0; $scroll_n = 0;
                    foreach ($sa_scroll_events as $se) { if (isset($se['max_scroll'])) { $total_scroll += (int)$se['max_scroll']; $scroll_n++; } }
                    echo $scroll_n > 0 ? round($total_scroll / $scroll_n) . '%' : '—';
                ?></span>
                <span class="stat-label">Avg Scroll Depth</span>
                <span class="stat-hint">How far visitors scroll (0-100%)</span>
            </div>
        </div>

        <!-- ─── CTA + Visitor Type Row ─── -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card" title="Total clicks on CTA buttons: Get Started, Buy, Download, Subscribe, Read Docs, Join Waitlist">
                <span class="stat-value"><?php echo number_format(count($sa_cta_clicks)); ?></span>
                <span class="stat-label">CTA Clicks</span>
                <span class="stat-hint">Clicks on Buy/Download/Subscribe</span>
            </div>
            <div class="stat-card" title="Waitlist form submissions tracked by the JS tracker (not the same as signups above)">
                <span class="stat-value"><?php echo number_format(count($sa_waitlist_events)); ?></span>
                <span class="stat-label">Waitlist Events</span>
                <span class="stat-hint">JS-tracked form submissions</span>
            </div>
            <div class="stat-card" title="Visitors with only 1 pageview ever (first-time visitors)">
                <span class="stat-value text-green"><?php echo number_format($sa_new_visitors); ?></span>
                <span class="stat-label">New Visitors</span>
                <span class="stat-hint">First-time visitors (1 session)</span>
            </div>
            <div class="stat-card" title="Visitors who have visited more than once (localStorage ID seen in multiple sessions)">
                <span class="stat-value" style="color:#f59e0b"><?php echo number_format($sa_returning_visitors); ?></span>
                <span class="stat-label">Returning</span>
                <span class="stat-hint">Visitors with 2+ sessions</span>
            </div>
        </div>

        <!-- ─── Visitors Over Time ─── -->
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:4px">Visitors Over Time</h3>
            <p class="text-dim text-sm" style="margin-bottom:12px">Daily unique visitors vs total page views. Shows traffic trends and growth.</p>
            <div style="max-height:200px"><canvas id="chart-visitors" height="120"></canvas></div>
        </div>

        <!-- ─── CTA Funnel + Hourly Traffic ─── -->
        <div class="grid-2" style="margin-bottom:24px">
            <div class="card">
                <h3 style="margin-bottom:4px">CTA Click Funnel</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">Which buttons visitors click most (Buy, Download, Subscribe, etc.)</p>
                <?php if (empty($sa_cta_funnel)): ?>
                    <div class="empty-state"><p>No CTA clicks yet.</p></div>
                <?php else: ?>
                    <div style="max-height:180px"><canvas id="chart-cta-funnel" height="120"></canvas></div>
                <?php endif; ?>
            </div>
            <div class="card">
                <h3 style="margin-bottom:4px">Traffic by Hour</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">When visitors arrive (UTC). Find your peak traffic hours.</p>
                <div style="max-height:180px"><canvas id="chart-hourly" height="120"></canvas></div>
            </div>
        </div>

        <!-- ─── Pie Charts Row (SMALL) ─── -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="card" style="text-align:center">
                <h4 style="margin-bottom:2px;font-size:0.85em;color:var(--text-dim)">Traffic Sources</h4>
                <p class="text-dim" style="font-size:0.7em;margin-bottom:6px">Where visitors came from (referrer domain)</p>
                <?php if (empty($sa_referrers)): ?>
                    <p class="text-dim text-sm">No data</p>
                <?php else: ?>
                    <div style="max-width:110px;margin:0 auto"><canvas id="chart-sources" height="110"></canvas></div>
                <?php endif; ?>
            </div>
            <div class="card" style="text-align:center">
                <h4 style="margin-bottom:2px;font-size:0.85em;color:var(--text-dim)">Devices</h4>
                <p class="text-dim" style="font-size:0.7em;margin-bottom:6px">Desktop / Mobile / Tablet (by viewport)</p>
                <?php if (empty($sa_devices)): ?>
                    <p class="text-dim text-sm">No data</p>
                <?php else: ?>
                    <div style="max-width:110px;margin:0 auto"><canvas id="chart-devices" height="110"></canvas></div>
                <?php endif; ?>
            </div>
            <div class="card" style="text-align:center">
                <h4 style="margin-bottom:2px;font-size:0.85em;color:var(--text-dim)">New vs Return</h4>
                <p class="text-dim" style="font-size:0.7em;margin-bottom:6px">First-time vs repeat visitors</p>
                <div style="max-width:110px;margin:0 auto"><canvas id="chart-newret" height="110"></canvas></div>
            </div>
            <div class="card" style="text-align:center">
                <h4 style="margin-bottom:2px;font-size:0.85em;color:var(--text-dim)">Viewports</h4>
                <p class="text-dim" style="font-size:0.7em;margin-bottom:6px">Screen width buckets (px)</p>
                <div style="max-width:110px;margin:0 auto"><canvas id="chart-viewports" height="110"></canvas></div>
            </div>
        </div>

        <!-- ─── Tier Interest Breakdown ─── -->
        <?php if (!empty($sa_tier_interest)): ?>
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:4px">Tier Interest Breakdown</h3>
            <p class="text-dim text-sm" style="margin-bottom:12px">Which pricing tiers visitors click on, split by one-time vs monthly billing preference.</p>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Tier</th><th>Clicks</th><th>One-Time</th><th>Monthly</th><th>% of CTA</th></tr></thead>
                    <tbody>
                    <?php foreach ($sa_tier_interest as $tid => $ti):
                        $tc = $tid === 'power' ? 'badge-purple' : ($tid === 'pro' ? 'badge-blue' : ($tid === 'community' ? 'badge-green' : ''));
                        $onetime = isset($ti['billing']['onetime']) ? $ti['billing']['onetime'] : 0;
                        $monthly = isset($ti['billing']['monthly']) ? $ti['billing']['monthly'] : 0;
                        $pct = count($sa_cta_clicks) > 0 ? round($ti['clicks'] / count($sa_cta_clicks) * 100, 1) : 0;
                    ?>
                    <tr>
                        <td><?php echo $tc ? '<span class="badge ' . $tc . '">' . ucfirst(htmlspecialchars($tid)) . '</span>' : htmlspecialchars($tid); ?></td>
                        <td class="font-bold"><?php echo $ti['clicks']; ?></td>
                        <td><?php echo $onetime; ?></td>
                        <td><?php echo $monthly; ?></td>
                        <td class="text-dim"><?php echo $pct; ?>%</td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- ─── Top Pages + Browser/OS ─── -->
        <div class="grid-2" style="margin-bottom:24px">
            <div class="card">
                <h3 style="margin-bottom:4px">Top Pages</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">Most visited URLs. Scroll = avg % scrolled. Time = avg seconds on page.</p>
                <?php if (empty($sa_pages)): ?>
                    <div class="empty-state"><p>No page data yet.</p></div>
                <?php else: ?>
                    <div class="table-wrap">
                        <table>
                            <thead><tr><th>Page</th><th>Views</th><th>Visitors</th><th>Scroll</th><th>Time</th></tr></thead>
                            <tbody>
                            <?php
                            uasort($sa_pages, function($a, $b) { return $b['views'] - $a['views']; });
                            $page_i = 0;
                            foreach ($sa_pages as $purl => $pd):
                                if ($page_i++ >= 15) break;
                                $avg_scroll = $pd['scroll_count'] > 0 ? round($pd['scroll_sum'] / $pd['scroll_count']) . '%' : '—';
                                $avg_time = $pd['scroll_count'] > 0 ? round($pd['time_sum'] / $pd['scroll_count']) . 's' : '—';
                            ?>
                            <tr>
                                <td class="text-sm" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="<?php echo htmlspecialchars($purl); ?>"><?php echo htmlspecialchars($purl); ?></td>
                                <td class="font-bold"><?php echo $pd['views']; ?></td>
                                <td><?php echo count($pd['visitors']); ?></td>
                                <td><?php echo $avg_scroll; ?></td>
                                <td><?php echo $avg_time; ?></td>
                            </tr>
                            <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                <?php endif; ?>
            </div>
            <div class="card">
                <h3 style="margin-bottom:4px">Browser &amp; OS</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">Parsed from User-Agent header. Shows browser name + version.</p>
                <?php if (empty($sa_browsers)): ?>
                    <div class="empty-state"><p>No browser data yet.</p></div>
                <?php else: ?>
                    <div class="table-wrap">
                        <table>
                            <thead><tr><th>Browser</th><th>Count</th><th>%</th></tr></thead>
                            <tbody>
                            <?php foreach (array_slice($sa_browsers, 0, 8, true) as $bn => $bc): ?>
                            <tr>
                                <td><?php echo htmlspecialchars($bn); ?></td>
                                <td class="font-bold"><?php echo $bc; ?></td>
                                <td class="text-dim"><?php echo round($bc / $total_pv * 100, 1); ?>%</td>
                            </tr>
                            <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                    <h4 style="margin:16px 0 8px">Operating System</h4>
                    <div class="table-wrap">
                        <table>
                            <thead><tr><th>OS</th><th>Count</th><th>%</th></tr></thead>
                            <tbody>
                            <?php foreach (array_slice($sa_os, 0, 6, true) as $on => $oc): ?>
                            <tr>
                                <td><?php echo htmlspecialchars($on); ?></td>
                                <td class="font-bold"><?php echo $oc; ?></td>
                                <td class="text-dim"><?php echo round($oc / $total_pv * 100, 1); ?>%</td>
                            </tr>
                            <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                <?php endif; ?>
            </div>
        </div>

        <!-- ─── UTM Campaign Performance ─── -->
        <?php if (!empty($sa_utm_campaigns)): ?>
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:4px">UTM Campaign Performance</h3>
            <p class="text-dim text-sm" style="margin-bottom:12px">Visitors who arrived via ?utm_source=X&amp;utm_medium=Y links (ad campaigns, social posts, email).</p>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Source / Medium (Campaign)</th><th>Views</th><th>Visitors</th></tr></thead>
                    <tbody>
                    <?php foreach (array_slice($sa_utm_campaigns, 0, 15, true) as $key => $uc): ?>
                    <tr>
                        <td class="font-bold"><?php echo htmlspecialchars($key); ?></td>
                        <td><?php echo $uc['views']; ?></td>
                        <td><?php echo count($uc['visitors']); ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- ─── CTA Detail Table ─── -->
        <div class="card" style="margin-bottom:24px">
            <div class="flex-between" style="margin-bottom:16px; flex-wrap:wrap; gap:8px">
                <h3 style="margin:0">CTA Click Details</h3>
                <p class="text-dim text-sm" style="margin:4px 0 0">Every button click: which button, which tier, one-time vs monthly, from which page section.</p>
                <input type="text" class="form-input" style="width:240px" placeholder="Search clicks..." data-filter-target="cta-detail-table">
            </div>
            <?php if (empty($sa_cta_detail)): ?>
                <div class="empty-state"><p>No CTA clicks recorded yet.</p></div>
            <?php else: ?>
                <div class="table-wrap">
                    <table id="cta-detail-table">
                        <thead><tr><th>Time</th><th>Button</th><th>Tier</th><th>Billing</th><th>Section</th><th>Page</th><th>Device</th></tr></thead>
                        <tbody>
                        <?php
                        $cta_sorted = array_reverse($sa_cta_detail);
                        foreach (array_slice($cta_sorted, 0, 50) as $click):
                        ?>
                        <tr>
                            <td class="text-dim text-sm nowrap"><?php echo isset($click['ts']) ? htmlspecialchars(substr($click['ts'], 0, 19)) : '—'; ?></td>
                            <td class="font-bold"><?php echo htmlspecialchars(isset($click['btn_text']) ? substr($click['btn_text'], 0, 40) : '—'); ?></td>
                            <td><?php
                                $ct = isset($click['tier']) ? $click['tier'] : '—';
                                $ctc = $ct === 'power' ? 'badge-purple' : ($ct === 'pro' ? 'badge-blue' : ($ct === 'community' ? 'badge-green' : ''));
                                echo $ctc ? '<span class="badge ' . $ctc . '">' . ucfirst(htmlspecialchars($ct)) . '</span>' : htmlspecialchars($ct);
                            ?></td>
                            <td class="text-sm"><?php echo htmlspecialchars(isset($click['billing']) ? $click['billing'] : '—'); ?></td>
                            <td class="text-sm text-dim"><?php echo htmlspecialchars(isset($click['section']) ? substr($click['section'], 0, 30) : '—'); ?></td>
                            <td class="text-sm" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><?php echo htmlspecialchars(isset($click['url']) ? $click['url'] : '—'); ?></td>
                            <td class="text-sm"><?php echo htmlspecialchars(isset($click['device']) ? $click['device'] : '—'); ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            <?php endif; ?>
        </div>

        <!-- ─── Geographic + Referrer Detail ─── -->
        <div class="grid-2" style="margin-bottom:24px">
            <?php if (!empty($sa_countries)): ?>
            <div class="card">
                <h3 style="margin-bottom:4px">Geographic Breakdown</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">Country codes from Cloudflare's CF-IPCountry header (only works if behind CF).</p>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Country</th><th>Visitors</th><th>%</th></tr></thead>
                        <tbody>
                        <?php foreach (array_slice($sa_countries, 0, 15, true) as $cc => $cnt): ?>
                        <tr>
                            <td class="font-bold"><?php echo htmlspecialchars($cc); ?></td>
                            <td><?php echo $cnt; ?></td>
                            <td class="text-dim"><?php echo round($cnt / $total_pv * 100, 1); ?>%</td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
            <?php endif; ?>
            <?php if (!empty($sa_referrers)): ?>
            <div class="card">
                <h3 style="margin-bottom:4px">Referrer Details</h3>
                <p class="text-dim text-sm" style="margin-bottom:12px">Full referrer domains. "Direct" = no referrer (typed URL, bookmark, or app).</p>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Source</th><th>Visits</th><th>%</th></tr></thead>
                        <tbody>
                        <?php foreach (array_slice($sa_referrers, 0, 15, true) as $rh => $rc): ?>
                        <tr>
                            <td><?php echo htmlspecialchars($rh); ?></td>
                            <td class="font-bold"><?php echo $rc; ?></td>
                            <td class="text-dim"><?php echo round($rc / $total_pv * 100, 1); ?>%</td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
            <?php endif; ?>
        </div>

        <!-- ─── Event Log (Raw) ─── -->
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:4px">Recent Events (Last 30)</h3>
            <p class="text-dim text-sm" style="margin-bottom:12px">Raw event log from tracker.js. Every page view, button click, scroll event, and waitlist submission.</p>
            <?php if (empty($site_events)): ?>
                <div class="empty-state"><p>No events yet. Visit the website to generate tracking data.</p></div>
            <?php else: ?>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Time</th><th>Event</th><th>Page</th><th>Visitor</th><th>Device</th><th>Details</th></tr></thead>
                        <tbody>
                        <?php
                        $recent_events = array_reverse(array_slice($site_events, -30));
                        foreach ($recent_events as $re):
                            $etype = isset($re['event']) ? $re['event'] : '';
                            $eclass = $etype === 'cta_click' ? 'text-green' : ($etype === 'waitlist' ? 'text-green font-bold' : ($etype === 'scroll_depth' ? 'text-dim' : ''));
                        ?>
                        <tr>
                            <td class="text-dim text-sm nowrap"><?php echo isset($re['ts']) ? htmlspecialchars(substr($re['ts'], 11, 8)) : '—'; ?></td>
                            <td><span class="<?php echo $eclass; ?>"><?php echo htmlspecialchars($etype); ?></span></td>
                            <td class="text-sm" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><?php echo htmlspecialchars(isset($re['url']) ? $re['url'] : '—'); ?></td>
                            <td class="text-mono text-sm text-dim"><?php echo isset($re['vid']) ? htmlspecialchars(substr($re['vid'], 0, 8)) : '—'; ?></td>
                            <td class="text-sm"><?php echo htmlspecialchars(isset($re['device']) ? $re['device'] : '—'); ?></td>
                            <td class="text-sm text-dim"><?php
                                $d = array();
                                if (isset($re['btn_text'])) $d[] = htmlspecialchars(substr($re['btn_text'], 0, 25));
                                if (isset($re['tier'])) $d[] = 'tier:' . htmlspecialchars($re['tier']);
                                if (isset($re['max_scroll'])) $d[] = 'scroll:' . (int)$re['max_scroll'] . '%';
                                if (isset($re['time_on_page'])) $d[] = (int)$re['time_on_page'] . 's';
                                if (isset($re['utm_source'])) $d[] = 'utm:' . htmlspecialchars($re['utm_source']);
                                echo implode(' | ', $d) ?: '—';
                            ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            <?php endif; ?>
        </div>

        <!-- Chart.js -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
        <script>
        (function() {
            var accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#00d4ff';
            var green = '#00ff88';
            var purple = '#a855f7';
            var yellow = '#f59e0b';
            var red = '#ef4444';
            var chartFont = {family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', size: 11};
            var gridColor = 'rgba(255,255,255,0.06)';
            var tickColor = 'rgba(255,255,255,0.4)';
            var miniOpts = {responsive:true, plugins:{legend:{display:false}}, cutout:'60%'};

            Chart.defaults.color = tickColor;
            Chart.defaults.font = chartFont;

            // ── Visitors Over Time ──
            var dailyLabels = <?php echo json_encode(array_keys($sa_daily), JSON_HEX_TAG); ?>;
            var dailyViews = <?php echo json_encode(array_values(array_map(function($d) { return $d['views']; }, $sa_daily)), JSON_HEX_TAG); ?>;
            var dailyVisitors = <?php echo json_encode(array_values(array_map(function($d) { return count($d['visitors']); }, $sa_daily)), JSON_HEX_TAG); ?>;

            if (dailyLabels.length > 0) {
                new Chart(document.getElementById('chart-visitors'), {
                    type: 'line',
                    data: {
                        labels: dailyLabels.map(function(d) { return d.substring(5); }),
                        datasets: [
                            {label: 'Page Views', data: dailyViews, borderColor: accent, backgroundColor: accent + '22', fill: true, tension: 0.3, pointRadius: 3},
                            {label: 'Unique Visitors', data: dailyVisitors, borderColor: green, backgroundColor: green + '22', fill: true, tension: 0.3, pointRadius: 3}
                        ]
                    },
                    options: {responsive: true, plugins: {legend: {position: 'bottom'}}, scales: {x: {grid: {color: gridColor}}, y: {beginAtZero: true, grid: {color: gridColor}}}}
                });
            }

            // ── CTA Funnel ──
            <?php if (!empty($sa_cta_funnel)): ?>
            new Chart(document.getElementById('chart-cta-funnel'), {
                type: 'bar',
                data: {
                    labels: <?php echo json_encode(array_map(function($l) { return strlen($l) > 22 ? substr($l, 0, 19) . '...' : $l; }, array_keys(array_slice($sa_cta_funnel, 0, 10, true))), JSON_HEX_TAG); ?>,
                    datasets: [{data: <?php echo json_encode(array_values(array_slice($sa_cta_funnel, 0, 10, true)), JSON_HEX_TAG); ?>, backgroundColor: [accent+'44',green+'44',purple+'44',yellow+'44',red+'44','#06b6d4'+'44','#8b5cf6'+'44','#ec4899'+'44','#14b8a6'+'44','#f97316'+'44'], borderColor: [accent,green,purple,yellow,red,'#06b6d4','#8b5cf6','#ec4899','#14b8a6','#f97316'], borderWidth: 1}]
                },
                options: {indexAxis: 'y', responsive: true, plugins: {legend: {display: false}}, scales: {x: {beginAtZero: true, grid: {color: gridColor}}, y: {grid: {display: false}}}}
            });
            <?php endif; ?>

            // ── Hourly Traffic ──
            new Chart(document.getElementById('chart-hourly'), {
                type: 'bar',
                data: {
                    labels: <?php echo json_encode(array_map(function($h) { return $h . ':00'; }, range(0, 23)), JSON_HEX_TAG); ?>,
                    datasets: [{data: <?php echo json_encode(array_values($sa_hourly), JSON_HEX_TAG); ?>, backgroundColor: accent + '44', borderColor: accent, borderWidth: 1}]
                },
                options: {responsive: true, plugins: {legend: {display: false}}, scales: {x: {grid: {display: false}}, y: {beginAtZero: true, grid: {color: gridColor}}}}
            });

            // ── Mini Pie: Traffic Sources ──
            <?php if (!empty($sa_referrers)): ?>
            new Chart(document.getElementById('chart-sources'), {
                type: 'doughnut',
                data: {labels: <?php echo json_encode(array_keys(array_slice($sa_referrers, 0, 6, true)), JSON_HEX_TAG); ?>, datasets: [{data: <?php echo json_encode(array_values(array_slice($sa_referrers, 0, 6, true)), JSON_HEX_TAG); ?>, backgroundColor: [accent,green,purple,yellow,red,'#06b6d4'], borderWidth: 0}]},
                options: miniOpts
            });
            <?php endif; ?>

            // ── Mini Pie: Devices ──
            <?php if (!empty($sa_devices)): ?>
            new Chart(document.getElementById('chart-devices'), {
                type: 'doughnut',
                data: {labels: <?php echo json_encode(array_keys($sa_devices), JSON_HEX_TAG); ?>, datasets: [{data: <?php echo json_encode(array_values($sa_devices), JSON_HEX_TAG); ?>, backgroundColor: [accent,green,purple], borderWidth: 0}]},
                options: miniOpts
            });
            <?php endif; ?>

            // ── Mini Pie: New vs Returning ──
            new Chart(document.getElementById('chart-newret'), {
                type: 'doughnut',
                data: {labels: ['New','Returning'], datasets: [{data: [<?php echo $sa_new_visitors; ?>,<?php echo $sa_returning_visitors; ?>], backgroundColor: [green,yellow], borderWidth: 0}]},
                options: miniOpts
            });

            // ── Mini Pie: Viewports ──
            new Chart(document.getElementById('chart-viewports'), {
                type: 'doughnut',
                data: {labels: <?php echo json_encode(array_keys($sa_viewports), JSON_HEX_TAG); ?>, datasets: [{data: <?php echo json_encode(array_values($sa_viewports), JSON_HEX_TAG); ?>, backgroundColor: [red,yellow,accent,green,purple], borderWidth: 0}]},
                options: miniOpts
            });
        })();
        </script>

<?php elseif ($active_view === 'telemetry'): ?>
        <!-- ══════════════ INTELLIGENCE ══════════════ -->
        <h2 style="margin-bottom:24px">Intelligence Center</h2>
<?php
    // Compute intelligence metrics
    $total_reports = count($telem_reports);
    $unique_machines = count($telem_machines);
    $verified_count = 0;
    $model_scores = []; // model → [scores]
    $model_runs = [];   // model → count
    $weekly_reports = []; // week_key → count
    $avg_pass_rate = 0;
    $total_pass = 0;

    foreach ($telem_reports as $tr) {
        if (($tr['sig_status'] ?? '') === 'verified') $verified_count++;
        $model = $tr['model'] ?? 'unknown';
        $score = round(($tr['pass_rate'] ?? 0) * 100, 1);
        $model_scores[$model][] = $score;
        $model_runs[$model] = ($model_runs[$model] ?? 0) + 1;
        $total_pass += $score;

        $ts = (int)($tr['generated_at'] ?? 0);
        if ($ts > 0) {
            $wk = date('Y-W', $ts);
            $weekly_reports[$wk] = ($weekly_reports[$wk] ?? 0) + 1;
        }
    }
    $avg_pass_rate = $total_reports > 0 ? round($total_pass / $total_reports, 1) : 0;
    $avg_class = $avg_pass_rate >= 85 ? 'text-green' : ($avg_pass_rate >= 70 ? 'text-yellow' : 'text-red');

    // Model averages for chart
    $model_avgs = [];
    foreach ($model_scores as $m => $scores) {
        $model_avgs[$m] = round(array_sum($scores) / count($scores), 1);
    }
    arsort($model_avgs);

    // Weekly report counts for trend chart
    ksort($weekly_reports);
    $week_labels = array_keys($weekly_reports);
    $week_counts = array_values($weekly_reports);
?>
        <!-- Stats -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_reports; ?></span>
                <span class="stat-label">Total Reports</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo count($model_avgs); ?></span>
                <span class="stat-label">Models Tested</span>
            </div>
            <div class="stat-card">
                <span class="stat-value <?php echo $avg_class; ?>"><?php echo $avg_pass_rate; ?>%</span>
                <span class="stat-label">Avg Pass Rate</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $unique_machines; ?></span>
                <span class="stat-label">Contributors</span>
            </div>
        </div>

        <!-- Charts row -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">
            <div class="card" style="padding:20px">
                <h3 style="margin-bottom:16px">Model Performance</h3>
                <canvas id="intel-model-chart" height="150"></canvas>
            </div>
            <div class="card" style="padding:20px">
                <h3 style="margin-bottom:16px">Reports Over Time</h3>
                <canvas id="intel-trend-chart" height="150"></canvas>
            </div>
        </div>

        <!-- Verification status -->
        <div class="card" style="margin-bottom:20px;padding:20px">
            <h3 style="margin-bottom:16px">Cryptographic Verification</h3>
            <div style="display:flex;gap:24px;align-items:center">
                <div style="text-align:center">
                    <div style="font-size:2rem;font-weight:700;color:var(--green)"><?php echo $verified_count; ?></div>
                    <div class="text-dim text-sm">Ed25519 Verified</div>
                </div>
                <div style="flex:1;background:var(--bg-code);border-radius:var(--radius-md);height:24px;overflow:hidden">
                    <div style="height:100%;background:var(--green);width:<?php echo $total_reports > 0 ? round($verified_count / $total_reports * 100) : 0; ?>%;border-radius:var(--radius-md);transition:width 0.5s"></div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:2rem;font-weight:700;color:var(--red)"><?php echo $total_reports - $verified_count; ?></div>
                    <div class="text-dim text-sm">Unverified</div>
                </div>
            </div>
        </div>

        <!-- Machines -->
        <div class="card" style="margin-bottom:20px;padding:20px">
            <h3 style="margin-bottom:16px">Machine Intelligence</h3>
            <?php if (empty($telem_machines)): ?>
                <p class="text-dim">No machines reporting yet.</p>
            <?php else: ?>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Machine</th><th>Runs</th><th>Models</th><th>Avg Score</th><th>Platform</th><th>Last Seen</th></tr></thead>
                    <tbody>
                    <?php foreach ($telem_machines as $mid => $mach):
                        $mach_scores = [];
                        foreach ($telem_reports as $tr) {
                            if (($tr['machine_id'] ?? '') === $mid) {
                                $mach_scores[] = round(($tr['pass_rate'] ?? 0) * 100, 1);
                            }
                        }
                        $mach_avg = count($mach_scores) > 0 ? round(array_sum($mach_scores) / count($mach_scores), 1) : 0;
                        $mach_avg_class = $mach_avg >= 85 ? 'text-green' : ($mach_avg >= 70 ? 'text-yellow' : 'text-red');
                        $p = $mach['platform'] ?? [];
                    ?>
                        <tr>
                            <td><code style="font-size:0.85em"><?php echo htmlspecialchars($mid); ?></code></td>
                            <td style="font-weight:600"><?php echo (int)$mach['runs']; ?></td>
                            <td><?php echo htmlspecialchars(implode(', ', array_keys($mach['models'] ?? []))); ?></td>
                            <td class="<?php echo $mach_avg_class; ?>" style="font-weight:700"><?php echo $mach_avg; ?>%</td>
                            <td class="text-sm"><?php echo htmlspecialchars(($p['os'] ?? '') . ' ' . ($p['arch'] ?? '')); ?></td>
                            <td class="text-dim text-sm"><?php echo $mach['last_seen'] ? date('Y-m-d H:i', (int)$mach['last_seen']) : '—'; ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <?php endif; ?>
        </div>

        <!-- ══════ LIVE AUDIT PIPELINE ══════ -->
        <?php
        $audit_queue_file = __DIR__ . '/data/audit_queue.jsonl';
        $audit_archive_file = __DIR__ . '/data/audit_archive.jsonl';
        $audit_orders = [];
        $archived_orders = [];
        if (file_exists($audit_queue_file)) {
            $lines = file($audit_queue_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ($lines as $line) {
                $o = json_decode($line, true);
                if ($o) $audit_orders[] = $o;
            }
            $audit_orders = array_reverse($audit_orders);
        }
        if (file_exists($audit_archive_file)) {
            $lines = file($audit_archive_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ($lines as $line) {
                $o = json_decode($line, true);
                if ($o) $archived_orders[] = $o;
            }
            $archived_orders = array_reverse($archived_orders);
        }
        $pending_orders = array_filter($audit_orders, function($o) { return ($o['status'] ?? '') === 'paid'; });
        ?>
        <?php
        $pending_orders = array_filter($audit_orders, function($o) {
            return in_array($o['status'] ?? '', ['paid', 'deposit_paid', 'running']);
        });
        ?>
        <?php
        // Active pipeline visualizations
        $running_orders = array_filter($audit_orders, function($o) { return ($o['status'] ?? '') === 'running'; });
        if (!empty($running_orders)):
        ?>
        <div class="card" style="padding:24px;margin-bottom:20px;border-color:var(--accent);background:linear-gradient(135deg,rgba(102,217,239,0.03),rgba(174,129,255,0.02))">
            <h3 style="margin-bottom:16px;color:var(--accent)">Live Audit Pipeline</h3>
            <?php foreach ($running_orders as $ro):
                $ro_models = $ro['models'] ?? [];
                $ro_progress = $ro['progress'] ?? [];
                $ro_stage = $ro_progress['stage'] ?? 'dispatched';
                $ro_cur = (int)($ro_progress['current'] ?? 0);
                $ro_total = (int)($ro_progress['total'] ?? 0);
                $ro_model_name = !empty($ro_models) ? ($ro_models[0]['model_name'] ?? '?') : '?';
                $ro_gpu = !empty($ro_models) ? ($ro_models[0]['gpu_label'] ?? '') : '';

                // Pipeline stages with status
                $stages = [
                    ['id' => 'intake',     'label' => 'Intake',     'icon' => '&#128203;'],
                    ['id' => 'payment',    'label' => 'Payment',    'icon' => '&#128176;'],
                    ['id' => 'dispatch',   'label' => 'Dispatch',   'icon' => '&#128640;'],
                    ['id' => 'boot',       'label' => 'GPU Boot',   'icon' => '&#9889;'],
                    ['id' => 'download',   'label' => 'Download',   'icon' => '&#128229;'],
                    ['id' => 'loading',    'label' => 'Load vLLM',  'icon' => '&#129504;'],
                    ['id' => 'break',      'label' => 'Break',      'icon' => '&#128296;'],
                    ['id' => 'assurance',  'label' => 'Assurance',  'icon' => '&#128737;'],
                    ['id' => 'signing',    'label' => 'Sign',       'icon' => '&#128274;'],
                    ['id' => 'certified',  'label' => 'Certified',  'icon' => '&#9989;'],
                    ['id' => 'delivered',  'label' => 'Delivered',  'icon' => '&#128232;'],
                    ['id' => 'invoiced',   'label' => 'Invoiced',   'icon' => '&#128179;'],
                ];

                // Map progress stage to pipeline index
                $stage_map = [
                    'dispatched' => 3, 'downloading' => 4, 'loading' => 5,
                    'break_running' => 6, 'assure_running' => 7, 'signing' => 8, 'completed' => 9,
                ];
                $active_idx = $stage_map[$ro_stage] ?? 3;
                // Intake and payment are always done for running orders
            ?>
            <div style="margin-bottom:20px">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
                    <code style="font-size:0.82em;color:var(--accent)"><?php echo htmlspecialchars($ro['order_id'] ?? ''); ?></code>
                    <span style="font-size:0.85em;font-weight:600"><?php echo htmlspecialchars($ro_model_name); ?></span>
                    <?php if ($ro_gpu): ?><span class="badge" style="font-size:0.68em;background:rgba(102,217,239,0.1);color:var(--accent)"><?php echo htmlspecialchars($ro_gpu); ?></span><?php endif; ?>
                </div>
                <div style="display:flex;gap:0;align-items:center;overflow-x:auto;padding:4px 0" data-pipeline="<?php echo htmlspecialchars($ro['order_id'] ?? ''); ?>">
                    <?php foreach ($stages as $si => $stage):
                        $is_done = $si < $active_idx;
                        $is_active = $si === $active_idx;
                        $is_future = $si > $active_idx;

                        if ($is_done) {
                            $node_bg = 'rgba(166,226,46,0.15)';
                            $node_border = '#a6e22e';
                            $node_color = '#a6e22e';
                        } elseif ($is_active) {
                            $node_bg = 'rgba(102,217,239,0.15)';
                            $node_border = '#66d9ef';
                            $node_color = '#66d9ef';
                        } else {
                            $node_bg = 'rgba(120,120,104,0.08)';
                            $node_border = '#484940';
                            $node_color = '#585950';
                        }
                    ?>
                    <?php if ($si > 0): ?>
                    <div class="pipe-connector" style="width:20px;height:2px;background:<?php echo $is_done ? '#a6e22e' : ($is_active ? '#66d9ef' : '#484940'); ?>;flex-shrink:0<?php echo $is_active ? ';animation:pulse-line 1.5s infinite' : ''; ?>"></div>
                    <?php endif; ?>
                    <div class="pipe-node" style="display:flex;flex-direction:column;align-items:center;gap:4px;flex-shrink:0;min-width:60px" title="<?php echo $stage['label']; ?>">
                        <div class="pipe-circle" style="width:36px;height:36px;border-radius:50%;background:<?php echo $node_bg; ?>;border:2px solid <?php echo $node_border; ?>;display:flex;align-items:center;justify-content:center;font-size:14px;<?php echo $is_active ? 'animation:pulse-node 1.5s infinite;box-shadow:0 0 12px ' . $node_border : ''; ?>"><?php echo $stage['icon']; ?></div>
                        <span class="pipe-label" style="font-size:0.65em;color:<?php echo $node_color; ?>;font-weight:<?php echo $is_active ? '700' : '400'; ?>;white-space:nowrap"><?php echo $stage['label']; ?></span>
                        <span class="pipe-counter" style="font-size:0.6em;color:var(--accent);font-weight:600"><?php echo ($is_active && $ro_cur > 0) ? $ro_cur . '/' . $ro_total : ''; ?></span>
                    </div>
                    <?php endforeach; ?>
                </div>
            </div>
            <!-- Live log terminal -->
            <div style="margin-top:12px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                    <span style="font-size:0.72em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px">Live Output</span>
                    <span id="log-status-<?php echo htmlspecialchars($ro['order_id'] ?? ''); ?>" style="font-size:0.68em;color:var(--accent)">connecting...</span>
                </div>
                <div id="log-terminal-<?php echo htmlspecialchars($ro['order_id'] ?? ''); ?>" style="background:#1a1b16;border:1px solid #333;border-radius:6px;padding:10px 12px;font-family:'Cascadia Code','Fira Code',monospace;font-size:0.72em;line-height:1.6;color:#a8a890;max-height:250px;overflow-y:auto;white-space:pre-wrap;word-break:break-all"></div>
            </div>
            <?php endforeach; ?>
        </div>
        <style>
        @keyframes pulse-node { 0%,100% { opacity:1; } 50% { opacity:0.6; } }
        @keyframes pulse-line { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        </style>
        <script>
        // Auto-refresh every 15 seconds while audits are running
        // Live pipeline polling — update in-place without page reload
        var _pipelineStageMap = {
            'dispatched': 3, 'pod_started': 3, 'downloading': 4, 'loading': 5,
            'break_running': 6, 'assure_running': 7, 'signing': 8, 'completed': 11,
            'delivered': 10, 'invoiced': 11
        };
        function pollPipeline() {
            <?php foreach ($running_orders as $ro): ?>
            fetch('/audit_orchestrator.php?action=status&order_id=<?php echo urlencode($ro['order_id'] ?? ''); ?>')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var p = d.progress || {};
                    var m = (d.models || [{}])[0];
                    var stage = p.stage || 'dispatched';
                    var activeIdx = _pipelineStageMap[stage] || 3;
                    var cur = p.current || 0;
                    var tot = p.total || 0;

                    // If completed or failed, reload once to show final state
                    if (m.status === 'completed' || m.status === 'failed') {
                        location.reload();
                        return;
                    }

                    // Update pipeline nodes in-place
                    var nodes = document.querySelectorAll('[data-pipeline="<?php echo htmlspecialchars($ro['order_id'] ?? ''); ?>"] .pipe-node');
                    nodes.forEach(function(node, idx) {
                        var isDone = idx < activeIdx;
                        var isActive = idx === activeIdx;
                        var circle = node.querySelector('.pipe-circle');
                        var label = node.querySelector('.pipe-label');
                        var counter = node.querySelector('.pipe-counter');

                        if (isDone) {
                            circle.style.background = 'rgba(166,226,46,0.15)';
                            circle.style.borderColor = '#a6e22e';
                            circle.style.animation = '';
                            circle.style.boxShadow = '';
                            label.style.color = '#a6e22e';
                            label.style.fontWeight = '400';
                        } else if (isActive) {
                            circle.style.background = 'rgba(102,217,239,0.15)';
                            circle.style.borderColor = '#66d9ef';
                            circle.style.animation = 'pulse-node 1.5s infinite';
                            circle.style.boxShadow = '0 0 12px #66d9ef';
                            label.style.color = '#66d9ef';
                            label.style.fontWeight = '700';
                        } else {
                            circle.style.background = 'rgba(120,120,104,0.08)';
                            circle.style.borderColor = '#484940';
                            circle.style.animation = '';
                            circle.style.boxShadow = '';
                            label.style.color = '#585950';
                            label.style.fontWeight = '400';
                        }

                        if (counter) {
                            counter.textContent = (isActive && cur > 0) ? cur + '/' + tot : '';
                        }
                    });

                    // Update connectors
                    var connectors = document.querySelectorAll('[data-pipeline="<?php echo htmlspecialchars($ro['order_id'] ?? ''); ?>"] .pipe-connector');
                    connectors.forEach(function(conn, idx) {
                        var segIdx = idx + 1;
                        conn.style.background = segIdx < activeIdx ? '#a6e22e' : (segIdx === activeIdx ? '#66d9ef' : '#484940');
                        conn.style.animation = segIdx === activeIdx ? 'pulse-line 1.5s infinite' : '';
                    });
                });
            <?php endforeach; ?>
        }
        setInterval(pollPipeline, 5000);

        // Log terminal polling
        var _logOffsets = {};
        function pollLogs() {
            <?php foreach ($running_orders as $ro):
                $oid = htmlspecialchars($ro['order_id'] ?? '');
            ?>
            (function(orderId) {
                var offset = _logOffsets[orderId] || 0;
                fetch('/audit_orchestrator.php?action=logs&order_id=' + encodeURIComponent(orderId) + '&after=' + offset)
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        var term = document.getElementById('log-terminal-' + orderId);
                        var status = document.getElementById('log-status-' + orderId);
                        if (d.lines && d.lines.length > 0) {
                            d.lines.forEach(function(line) {
                                var span = document.createElement('div');
                                // Color-code log lines
                                if (line.indexOf('ERROR') >= 0 || line.indexOf('FAILED') >= 0) {
                                    span.style.color = '#f92672';
                                } else if (line.indexOf('WARNING') >= 0) {
                                    span.style.color = '#e6db74';
                                } else if (line.indexOf('[+]') >= 0 || line.indexOf('complete') >= 0 || line.indexOf('ready') >= 0) {
                                    span.style.color = '#a6e22e';
                                } else if (line.indexOf('INFO') >= 0) {
                                    span.style.color = '#a8a890';
                                }
                                span.textContent = line;
                                term.appendChild(span);
                            });
                            term.scrollTop = term.scrollHeight;
                            status.textContent = d.lines.length + ' new lines';
                            status.style.color = 'var(--green)';
                        } else {
                            status.textContent = 'listening...';
                            status.style.color = 'var(--accent)';
                        }
                        _logOffsets[orderId] = d.offset || offset;
                    })
                    .catch(function() {
                        var status = document.getElementById('log-status-' + orderId);
                        if (status) { status.textContent = 'error'; status.style.color = 'var(--red)'; }
                    });
            })('<?php echo $oid; ?>');
            <?php endforeach; ?>
        }
        setInterval(pollLogs, 3000);
        pollLogs();
        </script>
        <?php endif; ?>

        <?php if (!empty($audit_orders)): ?>
        <div class="card" style="padding:20px;margin-bottom:20px;<?php echo !empty($pending_orders) ? 'border-color:#ffd700' : ''; ?>">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <h3>Audit Order Queue <?php if (!empty($pending_orders)): ?><span class="badge" style="background:rgba(255,215,0,0.15);color:#ffd700;border:1px solid #8b7500;margin-left:8px"><?php echo count($pending_orders); ?> active</span><?php endif; ?></h3>
            </div>
            <div style="overflow-x:auto">
                <table style="min-width:900px">
                    <thead><tr><th>Order ID</th><th>Tier</th><th>Customer</th><th>Access</th><th>Models</th><th>Deposit</th><th>Status</th><th>Date</th><?php if ($is_origin): ?><th></th><?php endif; ?></tr></thead>
                    <tbody>
                    <?php foreach ($audit_orders as $ao):
                        $ao_status = $ao['status'] ?? 'unknown';
                        $ao_badge_map = [
                            'deposit_paid' => 'badge-yellow', 'paid' => 'badge-yellow',
                            'running' => 'badge-blue', 'completed' => 'badge-green',
                            'partial' => 'badge-yellow', 'failed' => 'badge-red',
                            'dispatch_failed' => 'badge-red', 'cancelled' => 'badge-red',
                        ];
                        $ao_badge_cls = $ao_badge_map[$ao_status] ?? '';
                        $ao_tier_label = ($ao['tier'] ?? '') === 'audit_startup' ? 'Startup' : 'Enterprise';
                        $ao_deposit = ($ao['deposit_amount'] ?? $ao['amount'] ?? 0);
                        $ao_deposit_str = $ao_deposit > 0 ? '$' . number_format($ao_deposit / 100, 0) : '-';
                        $ao_models = $ao['models'] ?? [];
                        $ao_model_count = is_array($ao_models) ? count($ao_models) : 0;
                        $ao_models_done = 0;
                        if (is_array($ao_models)) {
                            foreach ($ao_models as $_am) {
                                if (($_am['status'] ?? '') === 'completed') $ao_models_done++;
                            }
                        }
                        $ao_access = $ao['access_type'] ?? '';
                        $ao_access_label = $ao_access === 'api_endpoint' ? 'API' : ($ao_access === 'model_weights' ? 'Weights' : '-');
                    ?>
                        <tr>
                            <td><code style="font-size:0.82em"><?php echo htmlspecialchars($ao['order_id'] ?? ''); ?></code></td>
                            <td><span class="badge <?php echo ($ao['tier'] ?? '') === 'audit_startup' ? 'badge-blue' : 'badge-purple'; ?>" style="font-size:0.72em"><?php echo $ao_tier_label; ?></span></td>
                            <td>
                                <div style="font-weight:600;font-size:0.88em"><?php echo htmlspecialchars($ao['name'] ?? ''); ?></div>
                                <div class="text-dim" style="font-size:0.75em"><?php echo htmlspecialchars($ao['email'] ?? ''); ?></div>
                            </td>
                            <td><span class="badge" style="font-size:0.68em"><?php echo $ao_access_label; ?></span></td>
                            <td>
                                <?php if ($ao_model_count > 0): ?>
                                <span style="font-weight:600"><?php echo $ao_models_done; ?>/<?php echo $ao_model_count; ?></span>
                                <?php if (is_array($ao_models)): ?>
                                <div style="font-size:0.72em;color:var(--text-dim);margin-top:2px">
                                    <?php foreach ($ao_models as $_mi => $_am): ?>
                                    <?php
                                        $_ms = $_am['status'] ?? 'pending';
                                        $_mc = $_ms === 'completed' ? 'var(--green)' : ($_ms === 'running' ? 'var(--accent)' : ($_ms === 'failed' ? 'var(--red)' : 'var(--text-dim)'));
                                    ?>
                                    <span style="color:<?php echo $_mc; ?>" title="<?php echo htmlspecialchars($_am['model_name'] ?? ''); ?>: <?php echo $_ms; ?>"><?php echo htmlspecialchars($_am['model_name'] ?? 'Model ' . ($_mi+1)); ?></span><?php echo $_mi < $ao_model_count - 1 ? ', ' : ''; ?>
                                    <?php endforeach; ?>
                                </div>
                                <?php endif; ?>
                                <?php else: ?>
                                <span class="text-dim">-</span>
                                <?php endif; ?>
                            </td>
                            <td style="font-weight:600"><?php echo $ao_deposit_str; ?></td>
                            <td>
                                <span class="badge <?php echo $ao_badge_cls; ?>" style="font-size:0.72em"><?php echo ucfirst(str_replace('_', ' ', $ao_status)); ?></span>
                                <?php if ($ao_status === 'running'):
                                    // Show pipeline stage from progress data
                                    $ao_progress = $ao['progress'] ?? [];
                                    $ao_stage = $ao_progress['stage'] ?? 'dispatched';
                                    $ao_scenario_cur = $ao_progress['current'] ?? 0;
                                    $ao_scenario_total = $ao_progress['total'] ?? 0;
                                    $ao_pass = $ao_progress['pass'] ?? '';
                                    $stage_labels = [
                                        'dispatched' => 'Queued',
                                        'downloading' => 'Downloading Model',
                                        'loading' => 'Loading vLLM',
                                        'break_running' => 'Break Pass',
                                        'assure_running' => 'Assurance Pass',
                                        'signing' => 'Signing Reports',
                                    ];
                                    $stage_label = $stage_labels[$ao_stage] ?? $ao_stage;
                                ?>
                                <div style="margin-top:4px;font-size:0.72em;color:var(--accent)">
                                    <?php echo htmlspecialchars($stage_label); ?>
                                    <?php if ($ao_scenario_cur > 0): ?>
                                    <span style="color:var(--text-dim)"><?php echo $ao_scenario_cur; ?>/<?php echo $ao_scenario_total; ?></span>
                                    <?php endif; ?>
                                </div>
                                <?php if ($ao_scenario_total > 0): ?>
                                <div style="margin-top:3px;background:var(--bg-surface);border-radius:3px;height:4px;overflow:hidden;width:100px">
                                    <div style="background:var(--accent);height:4px;width:<?php echo min(100, round($ao_scenario_cur / max(1,$ao_scenario_total) * 100)); ?>%;border-radius:3px"></div>
                                </div>
                                <?php endif; ?>
                                <?php endif; ?>
                            </td>
                            <td class="text-sm nowrap"><?php echo isset($ao['created_at']) ? htmlspecialchars(substr($ao['created_at'], 0, 16)) : '-'; ?></td>
<?php if ($is_origin): ?>
                            <td style="white-space:nowrap">
<?php if (in_array($ao_status, ['deposit_paid', 'paid', 'failed', 'dispatch_failed', 'partial'])): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.68em;background:rgba(102,217,239,0.12);color:var(--accent);border:1px solid var(--accent)" onclick="manualTriggerAudit('<?php echo htmlspecialchars($ao['order_id'] ?? ''); ?>')">Dispatch</button>
<?php endif; ?>
<?php if ($ao_status === 'running'): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.68em" onclick="refreshAuditProgress('<?php echo htmlspecialchars($ao['order_id'] ?? ''); ?>')">Refresh</button>
<?php endif; ?>
<?php if ($ao_status === 'completed'): ?>
                                <?php foreach ($ao_models as $_am): ?>
                                <?php if (!empty($_am['run_id'])): ?>
                                <a href="/report/<?php echo urlencode($_am['run_id']); ?>" class="btn btn-secondary" style="padding:2px 6px;font-size:0.65em">View</a>
                                <?php endif; ?>
                                <?php endforeach; ?>
<?php endif; ?>
<?php if ($ao_status === 'failed' && !empty($ao_models[0]['error'])): ?>
                                <div style="font-size:0.68em;color:var(--red);margin-top:4px;max-width:200px;overflow:hidden;text-overflow:ellipsis" title="<?php echo htmlspecialchars($ao_models[0]['error'] ?? ''); ?>"><?php echo htmlspecialchars(substr($ao_models[0]['error'] ?? '', 0, 80)); ?></div>
<?php endif; ?>
                            </td>
<?php endif; ?>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <?php if (!empty($archived_orders)): ?>
        <div class="card" style="padding:20px;margin-bottom:20px;opacity:0.8">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0;cursor:pointer" onclick="var t=document.getElementById('archived-orders-body');t.style.display=t.style.display==='none'?'':'none';this.querySelector('.toggle-arrow').textContent=t.style.display==='none'?'\u25B6':'\u25BC'">
                <h3 style="color:var(--text-dim)"><span class="toggle-arrow">&#9654;</span> Completed Audits <span class="badge" style="font-size:0.72em;margin-left:8px"><?php echo count($archived_orders); ?></span></h3>
            </div>
            <div id="archived-orders-body" style="display:none;margin-top:16px;overflow-x:auto">
                <table style="min-width:900px">
                    <thead><tr><th>Order ID</th><th>Tier</th><th>Customer</th><th>Models</th><th>Score</th><th>GPU Cost</th><th>Status</th><th>Completed</th><?php if ($is_origin): ?><th></th><?php endif; ?></tr></thead>
                    <tbody>
                    <?php foreach ($archived_orders as $ao):
                        $ao_status = $ao['status'] ?? 'unknown';
                        $ao_badge_cls = $ao_status === 'completed' ? 'badge-green' : ($ao_status === 'partial' ? 'badge-yellow' : 'badge-red');
                        $ao_tier_label = ($ao['tier'] ?? '') === 'audit_startup' ? 'Startup' : 'Enterprise';
                        $ao_models = $ao['models'] ?? [];
                        $ao_gpu_cost = 0;
                        $ao_score = 0;
                        foreach ($ao_models as $_am) {
                            $ao_gpu_cost += (float)($_am['gpu_cost'] ?? 0);
                            if (($_am['status'] ?? '') === 'completed') $ao_score = max($ao_score, (float)($_am['pass_rate'] ?? 0));
                        }
                    ?>
                        <tr>
                            <td><code style="font-size:0.82em"><?php echo htmlspecialchars($ao['order_id'] ?? ''); ?></code></td>
                            <td><span class="badge <?php echo ($ao['tier'] ?? '') === 'audit_startup' ? 'badge-blue' : 'badge-purple'; ?>" style="font-size:0.72em"><?php echo $ao_tier_label; ?></span></td>
                            <td>
                                <div style="font-weight:600;font-size:0.88em"><?php echo htmlspecialchars($ao['name'] ?? ''); ?></div>
                                <div class="text-dim" style="font-size:0.75em"><?php echo htmlspecialchars($ao['email'] ?? ''); ?></div>
                            </td>
                            <td style="font-size:0.82em">
                                <?php foreach ($ao_models as $_am): ?>
                                <div><?php echo htmlspecialchars($_am['model_name'] ?? '?'); ?></div>
                                <?php endforeach; ?>
                            </td>
                            <td><span class="badge <?php echo $ao_score >= 0.85 ? 'badge-green' : ($ao_score >= 0.7 ? 'badge-yellow' : 'badge-red'); ?>" style="font-size:0.78em"><?php echo $ao_score > 0 ? round($ao_score * 100, 1) . '%' : '-'; ?></span></td>
                            <td style="font-size:0.85em">$<?php echo number_format($ao_gpu_cost, 2); ?></td>
                            <td><span class="badge <?php echo $ao_badge_cls; ?>" style="font-size:0.72em"><?php echo ucfirst(str_replace('_', ' ', $ao_status)); ?></span></td>
                            <td class="text-sm nowrap"><?php echo isset($ao['completed_at']) ? htmlspecialchars(substr($ao['completed_at'], 0, 16)) : '-'; ?></td>
<?php if ($is_origin): ?>
                            <td>
                                <?php foreach ($ao_models as $_am): ?>
                                <?php if (!empty($_am['run_id'])): ?>
                                <a href="/report/<?php echo urlencode($_am['run_id']); ?>" class="btn btn-secondary" style="padding:2px 6px;font-size:0.65em">View</a>
                                <?php endif; ?>
                                <?php endforeach; ?>
                            </td>
<?php endif; ?>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- Reports table with filter -->
        <div class="card" style="padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px">
                <h3>All Reports</h3>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <input type="text" class="form-input" id="intel-search" placeholder="Search model, machine..." style="width:200px;padding:6px 12px;font-size:0.85em" oninput="filterIntelTable()">
                    <select class="form-input" id="intel-type-filter" style="padding:6px 12px;font-size:0.85em" onchange="filterIntelTable()">
                        <option value="">All Types</option>
                        <option value="pair">Parallax Pairs</option>
                        <option value="solo">Solo</option>
                    </select>
                    <select class="form-input" id="intel-cert-filter" style="padding:6px 12px;font-size:0.85em" onchange="filterIntelTable()">
                        <option value="">All Status</option>
                        <option value="certified">Certified</option>
                        <option value="uncertified">Not Certified</option>
                    </select>
                </div>
            </div>
            <div style="overflow-x:auto">
                <table id="intel-reports-table" style="min-width:1200px">
                    <thead><tr><th></th><th>Date</th><th>Type</th><th>Model</th><th>Score</th><th>Scenarios</th><th>Machine</th><th>Sig</th><th>Chain</th><th>Duration</th><th>Actions</th></tr></thead>
                    <tbody>
                    <?php
                    // Pre-build pair lookup and track which reports are "first of pair" (break)
                    $_pair_map = [];
                    $_rendered = [];
                    foreach ($telem_reports as $_i => $__r) {
                        $__pid = $__r['paired_run_id'] ?? ($__r['_verification']['paired_run_id'] ?? '');
                        if ($__pid) $_pair_map[$__r['run_id'] ?? ''] = $__pid;
                    }

                    foreach ($telem_reports as $idx => $tr):
                        $rid = $tr['run_id'] ?? '';
                        if (isset($_rendered[$rid])) continue;

                        $pct = round(($tr['pass_rate'] ?? 0) * 100, 1);
                        $pct_class = $pct >= 85 ? 'badge-green' : ($pct >= 70 ? 'badge-yellow' : 'badge-red');
                        $sig_ok = ($tr['sig_status'] ?? '') === 'verified';
                        $dur = ($tr['duration_s'] ?? 0) > 0 ? round($tr['duration_s'] / 60, 1) . 'm' : '—';
                        $paired_id = $_pair_map[$rid] ?? '';
                        $has_pair = !empty($paired_id);
                        $is_certified = !empty($tr['_verification']['origin_certified']);

                        // Find pair report data
                        $pair_report = null;
                        if ($has_pair) {
                            foreach ($telem_reports as $pr) {
                                if (($pr['run_id'] ?? '') === $paired_id) { $pair_report = $pr; break; }
                            }
                        }

                        // Determine order: earlier = Break, later = Assurance
                        $my_ts = (float)($tr['generated_at'] ?? 0);
                        $pair_ts = $pair_report ? (float)($pair_report['generated_at'] ?? 0) : 0;
                        $is_break = !$has_pair || $my_ts <= $pair_ts;

                        if ($has_pair && $pair_report):
                            // Render paired group with bracket
                            $break_r = $is_break ? $tr : $pair_report;
                            $assure_r = $is_break ? $pair_report : $tr;
                            $_rendered[$break_r['run_id'] ?? ''] = true;
                            $_rendered[$assure_r['run_id'] ?? ''] = true;

                            $b_pct = round(($break_r['pass_rate'] ?? 0) * 100, 1);
                            $a_pct = round(($assure_r['pass_rate'] ?? 0) * 100, 1);
                            $b_cls = $b_pct >= 85 ? 'badge-green' : ($b_pct >= 70 ? 'badge-yellow' : 'badge-red');
                            $a_cls = $a_pct >= 85 ? 'badge-green' : ($a_pct >= 70 ? 'badge-yellow' : 'badge-red');
                            $b_sig = ($break_r['sig_status'] ?? '') === 'verified';
                            $a_sig = ($assure_r['sig_status'] ?? '') === 'verified';
                            $b_dur = ($break_r['duration_s'] ?? 0) > 0 ? round($break_r['duration_s'] / 60, 1) . 'm' : '—';
                            $a_dur = ($assure_r['duration_s'] ?? 0) > 0 ? round($assure_r['duration_s'] / 60, 1) . 'm' : '—';
                            $pair_certified = !empty($break_r['_verification']['origin_certified']);
                            $break_id = $break_r['run_id'] ?? '';
                            $assure_id = $assure_r['run_id'] ?? '';
                    ?>
                        <tr style="border-top:2px solid var(--accent)">
                            <td rowspan="2" style="width:4px;padding:0;background:linear-gradient(180deg,var(--accent),rgba(102,217,239,0.3));border-radius:3px 0 0 3px"></td>
                            <td class="text-sm"><?php echo ($break_r['generated_at'] ?? 0) > 0 ? date('M j H:i', (int)$break_r['generated_at']) : '—'; ?></td>
                            <td><span class="badge badge-red" style="font-size:0.7em">Break</span></td>
                            <td style="font-weight:600"><?php echo htmlspecialchars($break_r['model'] ?? ''); ?></td>
                            <td><span class="badge <?php echo $b_cls; ?>" style="font-weight:700"><?php echo $b_pct; ?>%</span></td>
                            <td><?php echo (int)($break_r['scenarios_passed'] ?? 0); ?>/<?php echo (int)($break_r['scenarios_run'] ?? 0); ?></td>
                            <td><code style="font-size:0.8em"><?php echo htmlspecialchars(substr($break_r['machine_id'] ?? '', 0, 12)); ?></code></td>
                            <td><?php echo $b_sig ? '<span class="badge badge-green">Verified</span>' : '<span class="badge badge-red">No</span>'; ?></td>
                            <td><?php echo ($break_r['chain_ok'] ?? false) ? '<span class="text-green">OK</span>' : '<span class="text-red">FAIL</span>'; ?></td>
                            <td class="text-dim"><?php echo $b_dur; ?></td>
                            <td rowspan="2" style="white-space:nowrap;vertical-align:middle">
                                <a href="/report/<?php echo urlencode($break_id); ?>" class="btn btn-secondary" style="padding:2px 8px;font-size:0.75em">Break</a>
                                <a href="/report/<?php echo urlencode($assure_id); ?>" class="btn btn-secondary" style="padding:2px 8px;font-size:0.75em">Assure</a>
                                <a href="/report/<?php echo urlencode($break_id); ?>" class="btn btn-secondary" style="padding:2px 8px;font-size:0.75em">PDF</a>
<?php if (!$pair_certified): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.75em;background:rgba(255,215,0,0.12);color:#ffd700;border:1px solid #8b7500" onclick="certifyFromAdmin('<?php echo htmlspecialchars($break_id); ?>','<?php echo htmlspecialchars($assure_id); ?>')">Certify Pair</button>
<?php else: ?>
                                <span class="badge" style="background:rgba(255,215,0,0.12);color:#ffd700;border:1px solid #8b7500;font-size:0.7em">Certified</span>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.65em;background:rgba(249,38,114,0.12);color:var(--red);border:1px solid var(--red-border)" onclick="revokeFromAdmin('<?php echo htmlspecialchars($break_id); ?>','<?php echo htmlspecialchars($assure_id); ?>')">Revoke</button>
<?php endif; ?>
<?php if ($is_origin): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.65em;background:rgba(249,38,114,0.15);color:var(--red);border:1px solid var(--red-border)" onclick="deleteReport('<?php echo htmlspecialchars($break_id); ?>','<?php echo htmlspecialchars($assure_id); ?>')">Delete Pair</button>
<?php endif; ?>
                            </td>
                        </tr>
                        <tr style="border-bottom:2px solid var(--accent)">
                            <td class="text-sm"><?php echo ($assure_r['generated_at'] ?? 0) > 0 ? date('M j H:i', (int)$assure_r['generated_at']) : '—'; ?></td>
                            <td><span class="badge badge-green" style="font-size:0.7em">Assure</span></td>
                            <td style="font-weight:600"><?php echo htmlspecialchars($assure_r['model'] ?? ''); ?></td>
                            <td><span class="badge <?php echo $a_cls; ?>" style="font-weight:700"><?php echo $a_pct; ?>%</span></td>
                            <td><?php echo (int)($assure_r['scenarios_passed'] ?? 0); ?>/<?php echo (int)($assure_r['scenarios_run'] ?? 0); ?></td>
                            <td><code style="font-size:0.8em"><?php echo htmlspecialchars(substr($assure_r['machine_id'] ?? '', 0, 12)); ?></code></td>
                            <td><?php echo $a_sig ? '<span class="badge badge-green">Verified</span>' : '<span class="badge badge-red">No</span>'; ?></td>
                            <td><?php echo ($assure_r['chain_ok'] ?? false) ? '<span class="text-green">OK</span>' : '<span class="text-red">FAIL</span>'; ?></td>
                            <td class="text-dim"><?php echo $a_dur; ?></td>
                        </tr>
                    <?php else:
                            // Unpaired report — type from report data
                            $_rendered[$rid] = true;
                            $solo_type = $tr['report_type'] ?? 'break';
                            $solo_is_break = ($solo_type === 'break');
                    ?>
                        <tr>
                            <td style="width:4px;padding:0"></td>
                            <td class="text-sm"><?php echo ($tr['generated_at'] ?? 0) > 0 ? date('M j H:i', (int)$tr['generated_at']) : '—'; ?></td>
                            <td><span class="badge <?php echo $solo_is_break ? 'badge-red' : 'badge-green'; ?>" style="font-size:0.7em"><?php echo $solo_is_break ? 'Break' : 'Assure'; ?></span></td>
                            <td style="font-weight:600"><?php echo htmlspecialchars($tr['model'] ?? ''); ?></td>
                            <td><span class="badge <?php echo $pct_class; ?>" style="font-weight:700"><?php echo $pct; ?>%</span></td>
                            <td><?php echo (int)($tr['scenarios_passed'] ?? 0); ?>/<?php echo (int)($tr['scenarios_run'] ?? 0); ?></td>
                            <td><code style="font-size:0.8em"><?php echo htmlspecialchars(substr($tr['machine_id'] ?? '', 0, 12)); ?></code></td>
                            <td><?php echo $sig_ok ? '<span class="badge badge-green">Verified</span>' : '<span class="badge badge-red">No</span>'; ?></td>
                            <td><?php echo ($tr['chain_ok'] ?? false) ? '<span class="text-green">OK</span>' : '<span class="text-red">FAIL</span>'; ?></td>
                            <td class="text-dim"><?php echo $dur; ?></td>
                            <td style="white-space:nowrap">
                                <a href="/report/<?php echo urlencode($rid); ?>" class="btn btn-secondary" style="padding:2px 8px;font-size:0.75em">View</a>
                                <a href="/report/<?php echo urlencode($rid); ?>" class="btn btn-secondary" style="padding:2px 8px;font-size:0.75em">PDF</a>
<?php if (!$is_certified): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.75em;background:rgba(255,215,0,0.12);color:#ffd700;border:1px solid #8b7500" onclick="certifyFromAdmin('<?php echo htmlspecialchars($rid); ?>')">Certify</button>
<?php else: ?>
                                <span class="badge" style="background:rgba(255,215,0,0.12);color:#ffd700;border:1px solid #8b7500;font-size:0.7em">Certified</span>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.65em;background:rgba(249,38,114,0.12);color:var(--red);border:1px solid var(--red-border)" onclick="revokeFromAdmin('<?php echo htmlspecialchars($rid); ?>')">Revoke</button>
<?php endif; ?>
<?php if ($is_origin): ?>
                                <button class="btn btn-sm" style="padding:2px 8px;font-size:0.65em;background:rgba(249,38,114,0.15);color:var(--red);border:1px solid var(--red-border)" onclick="deleteReport('<?php echo htmlspecialchars($rid); ?>')">Delete</button>
<?php endif; ?>
                            </td>
                        </tr>
                    <?php endif; endforeach; ?>
                    </tbody>
                </table>
            </div>
            <div id="intel-pagination" style="margin-top:12px;font-size:0.82em;color:var(--text-dim)">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <span id="intel-page-info"></span>
                    <div style="display:flex;gap:6px;align-items:center">
                        <button class="btn btn-secondary" style="padding:4px 12px;font-size:0.82em" onclick="intelPage(-1)">Prev</button>
                        <button class="btn btn-secondary" style="padding:4px 12px;font-size:0.82em" onclick="intelPage(1)">Next</button>
                        <input type="number" id="intel-jump" min="1" max="1" style="width:60px;padding:4px 6px;font-size:0.82em;background:var(--bg-surface);border:1px solid var(--border);border-radius:3px;color:var(--text)" placeholder="pg#" onchange="intelJump()">
                    </div>
                </div>
                <div id="intel-page-nums" style="display:flex;flex-wrap:wrap;gap:3px;align-items:center"></div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
        <script>
        (function(){
            var cs = getComputedStyle(document.documentElement);
            var accent = cs.getPropertyValue('--accent').trim();
            var green = cs.getPropertyValue('--green').trim();
            var yellow = cs.getPropertyValue('--yellow').trim();
            var red = cs.getPropertyValue('--red').trim();
            var dim = cs.getPropertyValue('--text-dim').trim();
            var gridColor = cs.getPropertyValue('--border').trim();
            var defaults = {color: dim, borderColor: gridColor};
            Chart.defaults.color = dim;

            // Model performance bar chart
            var modelLabels = <?php echo json_encode(array_keys($model_avgs)); ?>;
            var modelData = <?php echo json_encode(array_values($model_avgs)); ?>;
            var modelColors = modelData.map(function(v){ return v >= 85 ? green : v >= 70 ? yellow : red; });
            new Chart(document.getElementById('intel-model-chart'), {
                type: 'bar',
                data: {labels: modelLabels, datasets: [{label: 'Avg Pass Rate %', data: modelData, backgroundColor: modelColors, borderRadius: 4}]},
                options: {responsive: true, plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, max: 100, grid: {color: gridColor}}, x: {grid: {display: false}}}}
            });

            // Reports trend line chart
            var weekLabels = <?php echo json_encode($week_labels); ?>;
            var weekData = <?php echo json_encode($week_counts); ?>;
            new Chart(document.getElementById('intel-trend-chart'), {
                type: 'line',
                data: {labels: weekLabels, datasets: [{label: 'Reports/Week', data: weekData, borderColor: accent, backgroundColor: accent + '20', fill: true, tension: 0.3, pointRadius: 4}]},
                options: {responsive: true, plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, grid: {color: gridColor}}, x: {grid: {display: false}}}}
            });
        })();

        var _intelPage = 0;
        var _intelPerPage = 25;

        function filterIntelTable() {
            _intelPage = 0;
            _renderIntelPage();
        }

        function intelPage(dir) {
            _intelPage += dir;
            if (_intelPage < 0) _intelPage = 0;
            _renderIntelPage();
        }

        function _renderIntelPage() {
            var q = (document.getElementById('intel-search').value || '').toLowerCase();
            var typeF = document.getElementById('intel-type-filter').value;
            var certF = document.getElementById('intel-cert-filter').value;

            // Get all "group" elements — paired rows share a rowspan bracket cell
            var tbody = document.querySelector('#intel-reports-table tbody');
            var allRows = Array.from(tbody.querySelectorAll('tr'));

            // Group rows into logical entries (pairs = 2 consecutive rows with rowspan)
            var groups = [];
            var i = 0;
            while (i < allRows.length) {
                var row = allRows[i];
                var bracketCell = row.querySelector('td[rowspan="2"]');
                if (bracketCell) {
                    groups.push({ rows: [allRows[i], allRows[i+1] || null], type: 'pair' });
                    i += 2;
                } else {
                    groups.push({ rows: [row], type: 'solo' });
                    i++;
                }
            }

            // Filter
            var filtered = groups.filter(function(g) {
                var text = g.rows.map(function(r){ return r ? r.textContent : ''; }).join(' ').toLowerCase();
                if (q && text.indexOf(q) < 0) return false;
                if (typeF === 'pair' && g.type !== 'pair') return false;
                if (typeF === 'solo' && g.type !== 'solo') return false;
                if (certF === 'certified' && text.indexOf('certified') < 0) return false;
                if (certF === 'uncertified' && text.indexOf('certified') >= 0) return false;
                return true;
            });

            var totalPages = Math.max(1, Math.ceil(filtered.length / _intelPerPage));
            if (_intelPage >= totalPages) _intelPage = totalPages - 1;

            var start = _intelPage * _intelPerPage;
            var visible = filtered.slice(start, start + _intelPerPage);
            var visibleRows = new Set();
            visible.forEach(function(g){ g.rows.forEach(function(r){ if(r) visibleRows.add(r); }); });

            allRows.forEach(function(r){ r.style.display = visibleRows.has(r) ? '' : 'none'; });

            // Page numbers with smart skipping
            var nav = '';
            var step = totalPages <= 20 ? 1 : (totalPages <= 100 ? 5 : (totalPages <= 500 ? 10 : 25));
            var shown = new Set();
            [0, 1].forEach(function(p) { shown.add(p); });
            [totalPages-2, totalPages-1].forEach(function(p) { if(p>=0) shown.add(p); });
            [_intelPage-1, _intelPage, _intelPage+1].forEach(function(p) { shown.add(p); });
            for (var s = 0; s < totalPages; s += step) shown.add(s);
            var sorted = Array.from(shown).filter(function(p) { return p >= 0 && p < totalPages; }).sort(function(a,b){return a-b;});
            var last = -2;
            sorted.forEach(function(p) {
                if (p - last > 1) nav += '<span style="color:var(--text-muted);margin:0 2px">..</span>';
                var active = p === _intelPage ? 'background:var(--accent);color:var(--bg-base);' : '';
                nav += '<button onclick="_intelPage='+p+';_renderIntelPage()" style="padding:2px 8px;border:1px solid var(--border);border-radius:3px;font-size:0.78em;cursor:pointer;background:var(--bg-surface);color:var(--text);'+active+'">'+(p+1)+'</button>';
                last = p;
            });

            document.getElementById('intel-page-info').textContent =
                'Page ' + (_intelPage + 1) + ' of ' + totalPages + ' (' + filtered.length + ' entries)';
            document.getElementById('intel-page-nums').innerHTML = nav;
            var jumpEl = document.getElementById('intel-jump');
            if (jumpEl) jumpEl.max = totalPages;
        }

        function intelJump() {
            var v = parseInt(document.getElementById('intel-jump').value);
            if (v >= 1) { _intelPage = v - 1; _renderIntelPage(); }
        }

        document.addEventListener('DOMContentLoaded', function(){ _renderIntelPage(); });
        </script>

<?php elseif ($active_view === 'audit'): ?>
        <!-- ══════════════ FRAUD LOG ══════════════ -->
        <?php
        $fraud_file = __DIR__ . '/data/fraud_reports.jsonl';
        $fraud_entries = [];
        if (file_exists($fraud_file)) {
            $lines = file($fraud_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ($lines as $line) {
                $f = json_decode($line, true);
                if ($f) $fraud_entries[] = $f;
            }
            $fraud_entries = array_reverse($fraud_entries);
        }
        if (!empty($fraud_entries)):
        ?>
        <div class="card" style="padding:20px;margin-bottom:24px;border-color:var(--red)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h3 style="color:var(--red);margin:0">Fraudulent Report Attempts <span class="badge badge-red"><?php echo count($fraud_entries); ?></span></h3>
<?php if ($is_origin): ?>
                <button class="btn btn-sm" style="background:rgba(249,38,114,0.12);color:var(--red);border:1px solid var(--red-border)" onclick="clearFraudLog()">Clear All</button>
<?php endif; ?>
            </div>
            <div style="overflow-x:auto">
                <table>
                    <thead><tr><th>Date</th><th>Run ID</th><th>Model</th><th>Claimed Score</th><th>Signature</th><th>Chain</th><th>Server</th><th>IP Hash</th></tr></thead>
                    <tbody>
                    <?php foreach (array_slice($fraud_entries, 0, 50) as $fe): ?>
                        <tr>
                            <td class="text-sm"><?php echo htmlspecialchars($fe['ts'] ?? ''); ?></td>
                            <td><code style="font-size:0.82em"><?php echo htmlspecialchars($fe['run_id'] ?? ''); ?></code></td>
                            <td><?php echo htmlspecialchars($fe['model'] ?? ''); ?></td>
                            <td><?php echo htmlspecialchars($fe['claimed_pass_rate'] ?? ''); ?>%</td>
                            <td><span class="badge <?php echo ($fe['signature_status'] ?? '') === 'valid' ? 'badge-green' : 'badge-red'; ?>"><?php echo htmlspecialchars($fe['signature_status'] ?? ''); ?></span></td>
                            <td><span class="badge <?php echo ($fe['chain_status'] ?? '') === 'intact' ? 'badge-green' : 'badge-red'; ?>"><?php echo htmlspecialchars($fe['chain_status'] ?? ''); ?></span></td>
                            <td><span class="badge <?php echo ($fe['server_status'] ?? '') === 'match' ? 'badge-green' : 'badge-red'; ?>"><?php echo htmlspecialchars($fe['server_status'] ?? ''); ?></span></td>
                            <td><code style="font-size:0.75em"><?php echo htmlspecialchars($fe['ip_hash'] ?? ''); ?></code></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <?php endif; ?>

        <!-- ══════════════ AUDIT LOG ══════════════ -->
<?php
    // Load audit log entries with filters
    $audit_filters = [];
    if (!empty($_GET['audit_action'])) $audit_filters['action'] = $_GET['audit_action'];
    if (!empty($_GET['audit_actor']))  $audit_filters['actor'] = $_GET['audit_actor'];
    if (!empty($_GET['audit_target'])) $audit_filters['target'] = $_GET['audit_target'];
    if (!empty($_GET['audit_from']))   $audit_filters['date_from'] = $_GET['audit_from'];
    if (!empty($_GET['audit_to']))     $audit_filters['date_to'] = $_GET['audit_to'];

    $audit_entries = db_get_audit_log(5000, $audit_filters);

    // Stat cards: last 24h
    $audit_total_24h = db_count_audit_events(24);
    $audit_logins_24h = db_count_audit_events(24, 'auth.login');
    $audit_security_24h = db_count_audit_events(24, 'security.%')
                        + db_count_audit_events(24, 'auth.login.failed');
    $audit_admin_24h = db_count_audit_events(24, 'user.tier.%')
                     + db_count_audit_events(24, 'user.role.%')
                     + db_count_audit_events(24, 'user.admin.%')
                     + db_count_audit_events(24, 'passport.generated');

    // Action color mapping
    $audit_action_colors = [
        'auth.login' => 'badge-green',
        'user.registered' => 'badge-green',
        'user.registered.pending' => 'badge-green',
        'user.verified' => 'badge-green',
        'license.claimed' => 'badge-green',
        'payment.checkout.completed' => 'badge-green',
        'sponsor.created' => 'badge-green',

        'user.tier.change' => 'badge-yellow',
        'user.role.change' => 'badge-yellow',
        'user.admin.toggle' => 'badge-yellow',
        'user.status.toggle' => 'badge-yellow',
        'passport.generated' => 'badge-yellow',
        'user.data.exported' => 'badge-yellow',
        'support.ticket.submitted' => 'badge-yellow',
        'sponsor.cancelled' => 'badge-yellow',

        'auth.login.failed' => 'badge-red',
        'user.account.deleted' => 'badge-red',
        'user.verification.failed' => 'badge-red',
        'security.honeypot.triggered' => 'badge-red',
        'security.timing.triggered' => 'badge-red',
    ];
?>
        <div class="flex-between" style="margin-bottom:24px; flex-wrap:wrap; gap:12px">
            <div>
                <h2 style="margin:0">Audit Log</h2>
                <p class="text-dim text-sm" style="margin-top:4px">Enterprise-grade audit trail. Every action, every actor, every timestamp.</p>
            </div>
        </div>

        <!-- Stat cards -->
        <div class="grid-4" style="margin-bottom:24px">
            <div class="stat-card">
                <span class="stat-value"><?php echo number_format($audit_total_24h); ?></span>
                <span class="stat-label">Events (24h)</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-green"><?php echo number_format($audit_logins_24h); ?></span>
                <span class="stat-label">Logins (24h)</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-red"><?php echo number_format($audit_security_24h); ?></span>
                <span class="stat-label">Security Events (24h)</span>
            </div>
            <div class="stat-card">
                <span class="stat-value" style="color:var(--yellow)"><?php echo number_format($audit_admin_24h); ?></span>
                <span class="stat-label">Admin Actions (24h)</span>
            </div>
        </div>

        <!-- Filter bar -->
        <div class="card" style="padding:16px;margin-bottom:20px">
            <form method="GET" action="/admin/audit" style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
                <div>
                    <label class="text-dim" style="display:block;font-size:0.72rem;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">Action</label>
                    <input type="text" name="audit_action" class="form-input" style="width:160px;padding:6px 10px;font-size:0.85em" placeholder="e.g. auth.login" value="<?php echo htmlspecialchars($_GET['audit_action'] ?? ''); ?>">
                </div>
                <div>
                    <label class="text-dim" style="display:block;font-size:0.72rem;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">Actor</label>
                    <input type="text" name="audit_actor" class="form-input" style="width:180px;padding:6px 10px;font-size:0.85em" placeholder="email..." value="<?php echo htmlspecialchars($_GET['audit_actor'] ?? ''); ?>">
                </div>
                <div>
                    <label class="text-dim" style="display:block;font-size:0.72rem;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">Target</label>
                    <input type="text" name="audit_target" class="form-input" style="width:160px;padding:6px 10px;font-size:0.85em" placeholder="user, passport..." value="<?php echo htmlspecialchars($_GET['audit_target'] ?? ''); ?>">
                </div>
                <div>
                    <label class="text-dim" style="display:block;font-size:0.72rem;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">From</label>
                    <input type="date" name="audit_from" class="form-input" style="width:140px;padding:6px 10px;font-size:0.85em" value="<?php echo htmlspecialchars($_GET['audit_from'] ?? ''); ?>">
                </div>
                <div>
                    <label class="text-dim" style="display:block;font-size:0.72rem;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">To</label>
                    <input type="date" name="audit_to" class="form-input" style="width:140px;padding:6px 10px;font-size:0.85em" value="<?php echo htmlspecialchars($_GET['audit_to'] ?? ''); ?>">
                </div>
                <button type="submit" class="btn btn-primary btn-sm" style="padding:6px 16px">Filter</button>
                <a href="/admin/audit" class="btn btn-secondary btn-sm" style="padding:6px 12px">Clear</a>
            </form>
        </div>

        <!-- Search + Export + Clear -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
            <input type="text" class="form-input" style="width:320px;padding:8px 14px;font-size:0.88em" placeholder="Search audit log..." id="audit-search" oninput="filterAuditLog(this.value)">
            <div style="display:flex;gap:8px">
                <button class="btn btn-secondary btn-sm" onclick="exportCSV('export_audit')">Export CSV</button>
<?php if ($is_origin): ?>
                <button class="btn btn-sm" style="background:rgba(249,38,114,0.12);color:var(--red);border:1px solid var(--red-border)" onclick="clearAuditLog()">Clear All</button>
<?php endif; ?>
            </div>
        </div>

        <!-- Audit log table -->
        <?php if (empty($audit_entries)): ?>
            <div class="card"><div class="empty-state"><p>No audit log entries<?php echo !empty($audit_filters) ? ' matching filters' : ' yet'; ?>.</p></div></div>
        <?php else: ?>
        <div class="card" style="padding:0;overflow:hidden">
            <div class="table-wrap">
                <table id="audit-table" style="margin:0">
                    <thead>
                        <tr>
                            <th style="width:150px">Timestamp</th>
                            <th>Actor</th>
                            <th>Action</th>
                            <th>Target</th>
                            <th style="min-width:200px">Details</th>
                            <th style="width:100px">IP Hash</th>
<?php if ($is_origin): ?>
                            <th style="width:30px"></th>
<?php endif; ?>
                        </tr>
                    </thead>
                    <tbody>
                    <?php foreach ($audit_entries as $ae):
                        $action_key = $ae['action'] ?? '';
                        $badge_class = $audit_action_colors[$action_key] ?? 'badge-blue';
                        $details_raw = $ae['details'] ?? null;
                        $details_arr = is_string($details_raw) ? json_decode($details_raw, true) : (is_array($details_raw) ? $details_raw : null);
                        $details_display = '';
                        $details_json_attr = '';
                        if ($details_arr && is_array($details_arr)) {
                            $parts = [];
                            foreach ($details_arr as $dk => $dv) {
                                if (is_bool($dv)) $dv = $dv ? 'true' : 'false';
                                if (is_array($dv)) $dv = json_encode($dv);
                                $parts[] = '<span style="font-weight:600;color:var(--text-dim)">' . htmlspecialchars($dk) . '</span> <span>' . htmlspecialchars((string)$dv) . '</span>';
                            }
                            $details_display = implode(' &middot; ', $parts);
                            $details_json_attr = htmlspecialchars(json_encode($details_arr), ENT_QUOTES);
                        }
                    ?>
                    <tr style="cursor:pointer" data-details="<?php echo $details_json_attr; ?>">
                        <td class="text-dim text-sm nowrap"><?php echo htmlspecialchars(substr($ae['timestamp'] ?? '', 0, 19)); ?></td>
                        <td>
                            <div style="font-weight:600;font-size:0.85em"><?php echo htmlspecialchars($ae['actor_email'] ?? ''); ?></div>
                            <div class="text-dim" style="font-size:0.72em"><?php echo htmlspecialchars($ae['actor_role'] ?? ''); ?></div>
                        </td>
                        <td><span class="badge <?php echo $badge_class; ?>" style="font-size:0.72em;white-space:nowrap"><?php echo htmlspecialchars($action_key); ?></span></td>
                        <td class="text-sm">
                            <?php if ($ae['target_type'] || $ae['target_id']): ?>
                            <span class="text-dim"><?php echo htmlspecialchars($ae['target_type'] ?? ''); ?></span>
                            <?php if ($ae['target_id']): ?>
                            <br><code style="font-size:0.8em"><?php echo htmlspecialchars(strlen($ae['target_id']) > 30 ? substr($ae['target_id'], 0, 27) . '...' : $ae['target_id']); ?></code>
                            <?php endif; ?>
                            <?php else: ?>
                            <span class="text-dim">--</span>
                            <?php endif; ?>
                        </td>
                        <td class="text-sm" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                            <?php echo $details_display ?: '<span class="text-dim">--</span>'; ?>
                        </td>
                        <td class="text-mono text-dim" style="font-size:0.72em"><?php echo htmlspecialchars($ae['ip_hash'] ?? ''); ?></td>
<?php if ($is_origin): ?>
                        <td><button class="btn btn-ghost btn-sm" style="font-size:0.65em;color:var(--red);padding:1px 6px" onclick="event.stopPropagation();deleteAuditEntry(<?php echo (int)($ae['id'] ?? 0); ?>,this)">&times;</button></td>
<?php endif; ?>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
        <div id="audit-pagination" style="margin-top:12px;font-size:0.82em;color:var(--text-dim)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                <span id="audit-page-info"></span>
                <div style="display:flex;gap:6px;align-items:center">
                    <button class="btn btn-secondary" style="padding:4px 12px;font-size:0.82em" onclick="auditPage(-1)">Prev</button>
                    <button class="btn btn-secondary" style="padding:4px 12px;font-size:0.82em" onclick="auditPage(1)">Next</button>
                    <input type="number" id="audit-jump" min="1" max="1" style="width:60px;padding:4px 6px;font-size:0.82em;background:var(--bg-surface);border:1px solid var(--border);border-radius:3px;color:var(--text)" placeholder="pg#" onchange="auditJump()">
                </div>
            </div>
            <div id="audit-page-nums" style="display:flex;flex-wrap:wrap;gap:3px;align-items:center"></div>
        </div>
        <script>
        var _auditPage = 0, _auditPerPage = 50;
        function auditGoTo(p) { _auditPage = p; _renderAuditPage(); }
        function auditPage(dir) { _auditPage += dir; _renderAuditPage(); }
        function _renderAuditPage() {
            if (_auditPage < 0) _auditPage = 0;
            var rows = Array.from(document.querySelectorAll('#audit-table tbody tr'));
            var total = rows.length;
            var pages = Math.max(1, Math.ceil(total / _auditPerPage));
            if (_auditPage >= pages) _auditPage = pages - 1;
            var start = _auditPage * _auditPerPage;
            rows.forEach(function(r, i) { r.style.display = (i >= start && i < start + _auditPerPage) ? '' : 'none'; });

            // Build page numbers with smart skipping
            var nav = '';
            var cur = _auditPage;
            var step = pages <= 20 ? 1 : (pages <= 100 ? 5 : (pages <= 500 ? 10 : 25));
            var shown = new Set();
            [0, 1].forEach(function(p) { shown.add(p); });
            [pages-2, pages-1].forEach(function(p) { if(p>=0) shown.add(p); });
            [cur-1, cur, cur+1].forEach(function(p) { shown.add(p); });
            for (var s = 0; s < pages; s += step) shown.add(s);
            var sorted = Array.from(shown).filter(function(p) { return p >= 0 && p < pages; }).sort(function(a,b){return a-b;});
            var last = -2;
            sorted.forEach(function(p) {
                if (p - last > 1) nav += '<span style="color:var(--text-muted);margin:0 2px">..</span>';
                var active = p === cur ? 'background:var(--accent);color:var(--bg-base);' : '';
                nav += '<button onclick="auditGoTo('+p+')" style="padding:2px 8px;border:1px solid var(--border);border-radius:3px;font-size:0.78em;cursor:pointer;background:var(--bg-surface);color:var(--text);'+active+'">'+(p+1)+'</button>';
                last = p;
            });

            document.getElementById('audit-page-info').textContent = 'Page ' + (cur + 1) + ' of ' + pages + ' (' + total + ' entries)';
            document.getElementById('audit-page-nums').innerHTML = nav;
            document.getElementById('audit-jump').max = pages;
        }
        function auditJump() {
            var v = parseInt(document.getElementById('audit-jump').value);
            if (v >= 1) { _auditPage = v - 1; _renderAuditPage(); }
        }
        document.addEventListener('DOMContentLoaded', function() { _renderAuditPage(); });
        </script>
        <?php endif; ?>

        <script>
        function filterAuditLog(q) {
            q = q.toLowerCase();
            var rows = document.querySelectorAll('#audit-table tbody tr');
            rows.forEach(function(r){
                if (r.classList.contains('audit-detail-row')) { r.style.display = 'none'; return; }
                r.style.display = r.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
            });
        }
        </script>

<?php elseif ($active_view === 'billing'): ?>
<!-- ══════════════ BILLING & COSTS ══════════════ -->
<h2 style="margin-bottom:24px">Billing &amp; Costs</h2>

<?php
// ── Load RunPod account data ──
$billing_cache_path = __DIR__ . '/data/billing_cache.json';
$billing_cache = file_exists($billing_cache_path) ? json_decode(file_get_contents($billing_cache_path), true) : [];
$cache_age = time() - ($billing_cache['fetched_at'] ?? 0);

// Refresh cache if older than 5 minutes
if ($cache_age > 300) {
    $audit_cfg = file_exists(__DIR__ . '/data/audit_config.json') ? json_decode(file_get_contents(__DIR__ . '/data/audit_config.json'), true) : [];
    $rp_key = $audit_cfg['runpod_api_key'] ?? '';
    if ($rp_key) {
        // GraphQL: balance + spend rate + daily charges
        $gql = '{ myself { clientBalance currentSpendPerHr dailyCharges { amount updatedAt diskCharges podCharges apiCharges serverlessCharges type } } }';
        $ch = curl_init('https://api.runpod.io/graphql');
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => ["Content-Type: application/json", "Authorization: Bearer {$rp_key}"],
            CURLOPT_POSTFIELDS => json_encode(['query' => $gql]),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 10,
        ]);
        $gql_resp = json_decode(curl_exec($ch), true);
        curl_close($ch);

        // REST: serverless billing history (last 90 days)
        $start = date('c', strtotime('-90 days'));
        $end = date('c');
        $ch = curl_init("https://rest.runpod.io/v1/billing/endpoints?bucketSize=day&startTime=" . urlencode($start) . "&endTime=" . urlencode($end));
        curl_setopt_array($ch, [
            CURLOPT_HTTPHEADER => ["Authorization: Bearer {$rp_key}"],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 10,
        ]);
        $rest_resp = json_decode(curl_exec($ch), true);
        curl_close($ch);

        $billing_cache = [
            'fetched_at' => time(),
            'balance' => $gql_resp['data']['myself']['clientBalance'] ?? 0,
            'spend_per_hr' => $gql_resp['data']['myself']['currentSpendPerHr'] ?? 0,
            'daily_charges' => $gql_resp['data']['myself']['dailyCharges'] ?? [],
            'endpoint_billing' => is_array($rest_resp) ? $rest_resp : [],
        ];
        file_put_contents($billing_cache_path, json_encode($billing_cache, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    }
}

$rp_balance = $billing_cache['balance'] ?? 0;
$rp_spend_hr = $billing_cache['spend_per_hr'] ?? 0;
$rp_daily = $billing_cache['daily_charges'] ?? [];
$rp_endpoint_billing = $billing_cache['endpoint_billing'] ?? [];

// Calculate totals from REST endpoint billing (more reliable than GraphQL dailyCharges)
$rp_total_30d = 0;
$rp_serverless_30d = 0;
foreach ($rp_endpoint_billing as $eb) {
    $rp_total_30d += (float)($eb['amount'] ?? 0);
    $rp_serverless_30d += (float)($eb['amount'] ?? 0); // all serverless
}

// ── Load audit orders for cost/revenue tracking (active queue + archive) ──
$audit_queue_path = __DIR__ . '/data/audit_queue.jsonl';
$audit_archive_path = __DIR__ . '/data/audit_archive.jsonl';
$all_audit_orders = [];
foreach ([$audit_queue_path, $audit_archive_path] as $_qpath) {
    if (file_exists($_qpath)) {
        foreach (file($_qpath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $o = json_decode($line, true);
            if ($o) $all_audit_orders[] = $o;
        }
    }
}

$total_revenue = 0;
$total_gpu_cost = 0;
$audit_cost_rows = [];
foreach ($all_audit_orders as $ao) {
    // Only count revenue from completed orders with live Stripe sessions (not test)
    $ao_is_test = strpos($ao['stripe_session'] ?? '', 'cs_test_') === 0;
    $ao_is_completed = in_array($ao['status'] ?? '', ['completed', 'partial']);
    $ao_revenue = ($ao_is_completed && !$ao_is_test) ? (int)($ao['total_amount'] ?? 0) : 0;
    $total_revenue += $ao_revenue;

    $ao_gpu_cost = 0;
    $ao_exec_time = 0;
    foreach ($ao['models'] ?? [] as $am) {
        $ao_gpu_cost += (float)($am['gpu_cost'] ?? 0);
        $ao_exec_time += (int)($am['execution_time_s'] ?? 0);
    }
    $total_gpu_cost += $ao_gpu_cost;

    $audit_cost_rows[] = [
        'order_id' => $ao['order_id'] ?? '',
        'customer' => $ao['name'] ?? ($ao['email'] ?? ''),
        'tier' => $ao['tier'] ?? '',
        'status' => $ao['status'] ?? '',
        'is_test' => $ao_is_test,
        'revenue' => $ao_revenue,
        'gpu_cost' => $ao_gpu_cost,
        'exec_time' => $ao_exec_time,
        'date' => $ao['created_at'] ?? '',
    ];
}
$audit_cost_rows = array_reverse($audit_cost_rows);
$gross_margin = $total_revenue > 0 ? round(($total_revenue - ($total_gpu_cost * 100)) / $total_revenue * 100, 1) : 0;
?>

<!-- Account Overview -->
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px">
    <div class="card" style="text-align:center;padding:20px">
        <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:6px">RunPod Balance</div>
        <div style="font-size:28px;font-weight:700;color:var(--text-bright)">$<?php echo number_format($rp_balance, 2); ?></div>
    </div>
    <div class="card" style="text-align:center;padding:20px">
        <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:6px">Current Burn Rate</div>
        <div style="font-size:28px;font-weight:700;color:<?php echo $rp_spend_hr > 0 ? 'var(--yellow)' : 'var(--green)'; ?>">$<?php echo number_format($rp_spend_hr, 2); ?>/hr</div>
    </div>
    <div class="card" style="text-align:center;padding:20px">
        <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:6px">30-Day GPU Spend</div>
        <div style="font-size:28px;font-weight:700;color:var(--red)">$<?php echo number_format($rp_total_30d, 2); ?></div>
    </div>
    <div class="card" style="text-align:center;padding:20px">
        <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:6px">Gross Margin</div>
        <div style="font-size:28px;font-weight:700;color:<?php echo $gross_margin >= 90 ? 'var(--green)' : ($gross_margin >= 70 ? 'var(--yellow)' : 'var(--red)'); ?>"><?php echo $gross_margin; ?>%</div>
    </div>
</div>

<!-- Revenue Summary -->
<div class="card" style="margin-bottom:24px;padding:20px">
    <h3 style="margin-bottom:16px">Revenue Summary</h3>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
        <div>
            <div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">Total Audit Revenue</div>
            <div style="font-size:22px;font-weight:700;color:var(--green)">$<?php echo number_format($total_revenue / 100, 2); ?></div>
        </div>
        <div>
            <div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">Total GPU Costs</div>
            <div style="font-size:22px;font-weight:700;color:var(--red)">$<?php echo number_format($total_gpu_cost, 2); ?></div>
        </div>
        <div>
            <div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">Net Profit</div>
            <div style="font-size:22px;font-weight:700;color:var(--text-bright)">$<?php echo number_format(($total_revenue / 100) - $total_gpu_cost, 2); ?></div>
        </div>
    </div>
</div>

<!-- Quarterly Tax Estimator -->
<?php
$_qtax_revenue = $total_revenue / 100; // dollars
$_qtax_months = max(1, (int)ceil((time() - strtotime('2026-01-01')) / (30*86400)));
$_qtax_monthly_rate = $_qtax_months > 0 ? $_qtax_revenue / $_qtax_months : 0;
$_qtax_projected_annual = $_qtax_monthly_rate * 12;

// Configurable W2 income (stored in audit_config or default)
$_qtax_w2 = (float)($_scfg['tax_w2_income'] ?? 83700); // combined household
$_qtax_w2_withholding = (float)($_scfg['tax_w2_withholding'] ?? 9700);

// S-Corp salary split (50% salary, 50% distribution)
$_qtax_salary_pct = 0.5;
$_qtax_salary = $_qtax_projected_annual * $_qtax_salary_pct;
$_qtax_distribution = $_qtax_projected_annual - $_qtax_salary;

// Estimated deductions
$_qtax_biz_expenses = $rp_total_30d * 12 + 3000; // projected annual RunPod + hosting/tools
$_qtax_taxable = $_qtax_w2 + $_qtax_salary + $_qtax_distribution - $_qtax_biz_expenses - 30000; // std deduction
$_qtax_taxable = max(0, $_qtax_taxable);

// Rough MFJ brackets 2026
$_qtax_fed_tax = 0;
if ($_qtax_taxable > 0) {
    $brackets = [[23200, 0.10], [71050, 0.12], [100525, 0.22], [191950, 0.24], [243725, 0.32], [609350, 0.35]];
    $remaining = $_qtax_taxable;
    $prev = 0;
    foreach ($brackets as $b) {
        $span = $b[0] - $prev;
        $chunk = min($remaining, $span);
        $_qtax_fed_tax += $chunk * $b[1];
        $remaining -= $chunk;
        $prev = $b[0];
        if ($remaining <= 0) break;
    }
    if ($remaining > 0) $_qtax_fed_tax += $remaining * 0.37;
}

// FICA on salary only (S-Corp)
$_qtax_fica = $_qtax_salary * 0.153;

// R&D credit estimate (from expenses tab if available)
$_qtax_rd_expenses = 0;
$exp_path = __DIR__ . '/data/expenses.jsonl';
if (file_exists($exp_path)) {
    foreach (file($exp_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $el) {
        $ex = json_decode($el, true);
        if ($ex && in_array($ex['category'] ?? '', ['R&D', 'Compute', 'Software'])) {
            $_qtax_rd_expenses += (float)($ex['amount'] ?? 0);
        }
    }
}
// Add dev labor estimate (hours from config or default)
$_qtax_dev_hours = (float)($_scfg['tax_dev_hours_ytd'] ?? 320);
$_qtax_dev_rate = (float)($_scfg['tax_dev_hourly_rate'] ?? 150);
$_qtax_rd_labor = $_qtax_dev_hours * $_qtax_dev_rate;
$_qtax_rd_total = $_qtax_rd_expenses + $_qtax_rd_labor + $rp_total_30d * 12;
$_qtax_rd_credit = $_qtax_rd_total * 0.115; // 6.5% fed + 5% WI

$_qtax_total_tax = $_qtax_fed_tax + $_qtax_fica - $_qtax_rd_credit;
$_qtax_quarterly = max(0, ($_qtax_total_tax - $_qtax_w2_withholding) / 4);

// Next quarterly due date
$_qtax_quarters = [
    ['Q1', strtotime('2026-04-15')],
    ['Q2', strtotime('2026-06-15')],
    ['Q3', strtotime('2026-09-15')],
    ['Q4', strtotime('2027-01-15')],
];
$_qtax_next = 'N/A';
foreach ($_qtax_quarters as $q) {
    if (time() < $q[1]) { $_qtax_next = $q[0] . ' — ' . date('M j, Y', $q[1]); break; }
}
?>
<div class="card" style="margin-bottom:24px;padding:20px">
    <h3 style="margin-bottom:16px">Quarterly Tax Estimator</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:16px">
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">YTD Revenue</div>
            <div style="font-size:20px;font-weight:700;color:var(--green)">$<?php echo number_format($_qtax_revenue, 0); ?></div>
        </div>
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Projected Annual</div>
            <div style="font-size:20px;font-weight:700;color:var(--text-bright)">$<?php echo number_format($_qtax_projected_annual, 0); ?></div>
        </div>
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Est. Annual Tax</div>
            <div style="font-size:20px;font-weight:700;color:var(--red)">$<?php echo number_format(max(0, $_qtax_total_tax), 0); ?></div>
        </div>
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">R&D Credit</div>
            <div style="font-size:20px;font-weight:700;color:var(--green)">-$<?php echo number_format($_qtax_rd_credit, 0); ?></div>
        </div>
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Quarterly Payment</div>
            <div style="font-size:20px;font-weight:700;color:var(--yellow)">$<?php echo number_format($_qtax_quarterly, 0); ?></div>
        </div>
        <div>
            <div style="font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Next Due Date</div>
            <div style="font-size:16px;font-weight:600;color:var(--text-bright)"><?php echo $_qtax_next; ?></div>
        </div>
    </div>
    <div style="font-size:11px;color:var(--text-dim);border-top:1px solid var(--border);padding-top:10px">
        Assumes: MFJ, $<?php echo number_format($_qtax_w2, 0); ?> household W2, S-Corp 50/50 salary/distribution split, $<?php echo number_format($_qtax_w2_withholding, 0); ?> W2 withholding.
        Configurable in <code>audit_config.json</code> (tax_w2_income, tax_w2_withholding, tax_dev_hours_ytd, tax_dev_hourly_rate).
        <strong>This is an estimate — consult your CPA.</strong>
    </div>
</div>

<!-- Per-Audit Costs -->
<div class="card" style="margin-bottom:24px">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border)">
        <h3>Per-Audit Cost Breakdown</h3>
        <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="audit-cost-search" placeholder="Search orders..." oninput="filterBillingTable()" style="padding:6px 10px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.82em;width:180px">
            <select id="audit-cost-status" onchange="filterBillingTable()" style="padding:6px 8px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.82em">
                <option value="">All Status</option>
                <option value="completed">Completed</option>
                <option value="running">Running</option>
                <option value="failed">Failed</option>
                <option value="deposit_paid">Deposit Paid</option>
            </select>
            <button onclick="exportBillingCSV()" class="btn btn-sm" style="font-size:0.82em">CSV</button>
        </div>
    </div>
    <div class="table-wrap">
        <table id="billing-table">
            <thead>
                <tr>
                    <th>Order ID</th>
                    <th>Customer</th>
                    <th>Tier</th>
                    <th>Status</th>
                    <th>Revenue</th>
                    <th>GPU Cost</th>
                    <th>Margin</th>
                    <th>Exec Time</th>
                    <th>Date</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($audit_cost_rows as $acr):
                    $acr_rev = $acr['revenue'] / 100;
                    $acr_cost = $acr['gpu_cost'];
                    $acr_margin = $acr_rev > 0 ? round(($acr_rev - $acr_cost) / $acr_rev * 100, 1) : 0;
                    $acr_exec_m = $acr['exec_time'] > 0 ? floor($acr['exec_time'] / 60) . 'm ' . ($acr['exec_time'] % 60) . 's' : '---';
                    $acr_date = $acr['date'] ? htmlspecialchars(substr($acr['date'], 0, 16)) : '---';
                    $acr_status_cls = $acr['status'] === 'completed' ? 'badge-green' : ($acr['status'] === 'running' ? 'badge-blue' : ($acr['status'] === 'failed' ? 'badge-red' : 'badge-yellow'));
                ?>
                <tr data-status="<?php echo htmlspecialchars($acr['status']); ?>" data-order="<?php echo htmlspecialchars($acr['order_id']); ?>">
                    <td><code style="font-size:0.82em"><?php echo htmlspecialchars($acr['order_id']); ?></code></td>
                    <td><?php echo htmlspecialchars($acr['customer']); ?></td>
                    <td><span class="badge" style="font-size:0.72em"><?php echo htmlspecialchars(ucfirst(str_replace('audit_', '', $acr['tier']))); ?></span></td>
                    <td>
                        <span class="badge <?php echo $acr_status_cls; ?>" style="font-size:0.72em"><?php echo ucfirst($acr['status']); ?></span>
                        <?php if ($acr['is_test'] ?? false): ?><span class="badge badge-yellow" style="font-size:0.68em;margin-left:2px">TEST</span><?php endif; ?>
                    </td>
                    <td style="color:<?php echo ($acr['is_test'] ?? false) ? 'var(--text-dim)' : 'var(--green)'; ?>;font-weight:600"><?php echo ($acr['is_test'] ?? false) ? '<s>' : ''; ?>$<?php echo number_format($acr_rev, 2); ?><?php echo ($acr['is_test'] ?? false) ? '</s>' : ''; ?></td>
                    <td style="color:var(--red)"><?php echo $acr_cost > 0 ? '$' . number_format($acr_cost, 2) : '<span class="text-dim">---</span>'; ?></td>
                    <td style="font-weight:600;color:<?php echo $acr_margin >= 95 ? 'var(--green)' : 'var(--yellow)'; ?>"><?php echo $acr_cost > 0 ? $acr_margin . '%' : '<span class="text-dim">---</span>'; ?></td>
                    <td class="text-dim text-sm"><?php echo $acr_exec_m; ?></td>
                    <td class="text-dim text-sm nowrap"><?php echo $acr_date; ?></td>
                    <td><button onclick="deleteAuditOrder('<?php echo htmlspecialchars($acr['order_id']); ?>', this)" class="btn btn-sm" style="font-size:0.7em;color:var(--red);background:none;border:1px solid var(--red);padding:2px 8px" title="Delete order">X</button></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <div id="audit-cost-pagination" style="display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-top:1px solid var(--border);font-size:0.82em;color:var(--text-dim)">
        <span id="audit-cost-count"><?php echo count($audit_cost_rows); ?> orders</span>
        <div id="audit-cost-pages"></div>
    </div>
</div>

<!-- RunPod Endpoint Charges (last 90 days) -->
<?php if (!empty($rp_endpoint_billing)): ?>
<div class="card" style="margin-bottom:24px">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border)">
        <h3>RunPod Charges by Endpoint</h3>
        <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="ep-charge-search" placeholder="Search..." oninput="filterEpTable()" style="padding:6px 10px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.82em;width:140px">
            <select id="ep-charge-filter" onchange="filterEpTable()" style="padding:6px 8px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.82em">
                <option value="">All Endpoints</option>
                <?php foreach (array_unique(array_map(function($e) use ($_ep_names) { return $_ep_names[$e['endpointId'] ?? ''] ?? 'OLD'; }, $rp_endpoint_billing)) as $n): ?>
                <option value="<?php echo htmlspecialchars($n); ?>"><?php echo htmlspecialchars($n); ?></option>
                <?php endforeach; ?>
            </select>
        </div>
    </div>
    <div class="table-wrap">
        <table id="ep-charge-table">
            <thead>
                <tr><th>Date</th><th>Endpoint</th><th>Amount</th><th>GPU Time</th><th>Disk (GB)</th></tr>
            </thead>
            <tbody>
                <?php
                // Map endpoint IDs to names
                $_ep_names = [];
                foreach (($_scfg['runpod_weights_endpoints'] ?? []) as $tn => $tv) {
                    $_ep_names[$tv['endpoint_id'] ?? ''] = strtoupper($tn);
                }
                $_ep_names[$_scfg['runpod_endpoint_id_api'] ?? ''] = 'API';

                $shown_ep = array_reverse($rp_endpoint_billing);
                foreach ($shown_ep as $eb):
                    $eb_date = htmlspecialchars(substr($eb['time'] ?? '', 0, 10));
                    $eb_epid = $eb['endpointId'] ?? '';
                    $eb_name = $_ep_names[$eb_epid] ?? 'OLD/' . substr($eb_epid, 0, 6);
                    $eb_time_s = ($eb['timeBilledMs'] ?? 0) / 1000;
                    $eb_time_fmt = $eb_time_s >= 3600 ? sprintf('%.1fh', $eb_time_s/3600) : ($eb_time_s >= 60 ? sprintf('%.0fm', $eb_time_s/60) : sprintf('%.0fs', $eb_time_s));
                ?>
                <tr data-ep="<?php echo htmlspecialchars($eb_name); ?>">
                    <td class="text-sm"><?php echo $eb_date; ?></td>
                    <td><span class="badge" style="font-size:0.72em"><?php echo htmlspecialchars($eb_name); ?></span></td>
                    <td style="font-weight:600;color:var(--red)">$<?php echo number_format((float)($eb['amount'] ?? 0), 4); ?></td>
                    <td class="text-dim"><?php echo $eb_time_fmt; ?></td>
                    <td class="text-dim"><?php echo (int)($eb['diskSpaceBilledGB'] ?? 0); ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <div id="ep-charge-pagination" style="display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-top:1px solid var(--border);font-size:0.82em;color:var(--text-dim)">
        <span id="ep-charge-count"><?php echo count($rp_endpoint_billing); ?> records</span>
        <div id="ep-charge-pages"></div>
    </div>
</div>
<?php endif; ?>

<div style="font-size:12px;color:var(--text-dim);margin-top:8px">
    Cache refreshed: <?php echo date('Y-m-d H:i:s', $billing_cache['fetched_at'] ?? 0); ?> (auto-refreshes every 5 min)
    &nbsp;&middot;&nbsp; <a href="/admin/billing" style="color:var(--accent)">Force Refresh</a>
</div>

<script>
var _billingPage = 1, _billingPerPage = 20;
var _epPage = 1, _epPerPage = 20;

function filterBillingTable() {
    _billingPage = 1;
    renderBillingPage();
}
function renderBillingPage() {
    var q = (document.getElementById('audit-cost-search').value || '').toLowerCase();
    var sf = document.getElementById('audit-cost-status').value;
    var rows = document.querySelectorAll('#billing-table tbody tr');
    var visible = [];
    rows.forEach(function(r) {
        var match = true;
        if (q && r.textContent.toLowerCase().indexOf(q) < 0) match = false;
        if (sf && r.dataset.status !== sf) match = false;
        r._billingMatch = match;
        if (match) visible.push(r);
    });
    var totalPages = Math.max(1, Math.ceil(visible.length / _billingPerPage));
    if (_billingPage > totalPages) _billingPage = totalPages;
    var start = (_billingPage - 1) * _billingPerPage;
    var end = start + _billingPerPage;
    var vi = 0;
    rows.forEach(function(r) {
        if (!r._billingMatch) { r.style.display = 'none'; return; }
        r.style.display = (vi >= start && vi < end) ? '' : 'none';
        vi++;
    });
    document.getElementById('audit-cost-count').textContent = visible.length + ' orders';
    var phtml = '';
    for (var p = 1; p <= totalPages; p++) {
        phtml += '<button onclick="_billingPage=' + p + ';renderBillingPage()" class="btn btn-sm" style="font-size:0.75em;margin:0 2px;' + (p === _billingPage ? 'background:var(--accent);color:#111' : '') + '">' + p + '</button>';
    }
    document.getElementById('audit-cost-pages').innerHTML = phtml;
}

function filterEpTable() {
    _epPage = 1;
    renderEpPage();
}
function renderEpPage() {
    var q = (document.getElementById('ep-charge-search').value || '').toLowerCase();
    var ef = document.getElementById('ep-charge-filter').value;
    var rows = document.querySelectorAll('#ep-charge-table tbody tr');
    var visible = [];
    rows.forEach(function(r) {
        var match = true;
        if (q && r.textContent.toLowerCase().indexOf(q) < 0) match = false;
        if (ef && (!r.dataset.ep || r.dataset.ep.indexOf(ef) < 0)) match = false;
        r._epMatch = match;
        if (match) visible.push(r);
    });
    var totalPages = Math.max(1, Math.ceil(visible.length / _epPerPage));
    if (_epPage > totalPages) _epPage = totalPages;
    var start = (_epPage - 1) * _epPerPage;
    var end = start + _epPerPage;
    var vi = 0;
    rows.forEach(function(r) {
        if (!r._epMatch) { r.style.display = 'none'; return; }
        r.style.display = (vi >= start && vi < end) ? '' : 'none';
        vi++;
    });
    document.getElementById('ep-charge-count').textContent = visible.length + ' records';
    var phtml = '';
    for (var p = 1; p <= totalPages; p++) {
        phtml += '<button onclick="_epPage=' + p + ';renderEpPage()" class="btn btn-sm" style="font-size:0.75em;margin:0 2px;' + (p === _epPage ? 'background:var(--accent);color:#111' : '') + '">' + p + '</button>';
    }
    document.getElementById('ep-charge-pages').innerHTML = phtml;
}

function deleteAuditOrder(orderId, btn) {
    if (!confirm('Delete audit order ' + orderId + '? This removes it from the billing table.')) return;
    var fd = new FormData();
    fd.append('csrf_token', '<?php echo $csrf_token; ?>');
    fd.append('delete_order_id', orderId);
    fetch('/admin.php?action=save_settings', {method: 'POST', body: fd, credentials: 'same-origin'})
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.ok) {
                var row = btn.closest('tr');
                if (row) row.remove();
                renderBillingPage();
                if (typeof showToast === 'function') showToast('Order deleted');
            } else {
                alert(d.error || 'Failed to delete');
            }
        });
}

// Init pagination on load
if (document.getElementById('billing-table')) renderBillingPage();
if (document.getElementById('ep-charge-table')) renderEpPage();

function exportBillingCSV() {
    var rows = [['Order ID','Customer','Tier','Status','Revenue ($)','GPU Cost ($)','Margin (%)','Exec Time (s)','Date']];
    <?php foreach ($audit_cost_rows as $acr): ?>
    rows.push([<?php echo json_encode($acr['order_id']); ?>,<?php echo json_encode($acr['customer']); ?>,<?php echo json_encode($acr['tier']); ?>,<?php echo json_encode($acr['status']); ?>,<?php echo json_encode(round($acr['revenue']/100,2)); ?>,<?php echo json_encode(round($acr['gpu_cost'],4)); ?>,<?php echo json_encode($acr['revenue']>0?round(($acr['revenue']/100-$acr['gpu_cost'])/($acr['revenue']/100)*100,1):0); ?>,<?php echo json_encode($acr['exec_time']); ?>,<?php echo json_encode($acr['date']); ?>]);
    <?php endforeach; ?>
    var csv = rows.map(function(r){return r.map(function(c){return '"'+String(c).replace(/"/g,'""')+'"'}).join(',')}).join('\n');
    var blob = new Blob([csv], {type:'text/csv'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'forge_audit_costs_' + new Date().toISOString().slice(0,10) + '.csv';
    a.click();
}
</script>

<?php elseif ($active_view === 'expenses'): ?>
<!-- ══════════════ BUSINESS EXPENSES ══════════════ -->
<?php if (!$is_origin) { echo '<div class="card" style="padding:40px;text-align:center;color:var(--text-dim)">Origin access required.</div>'; } else { ?>
<style>
select option { background: var(--bg-surface, #2d2e28); color: var(--text, #f8f8f2); }
select { color-scheme: dark; }
input[type="date"] { color-scheme: dark; }
</style>
<?php
$exp_path = __DIR__ . '/data/expenses.jsonl';
$all_expenses = [];
if (file_exists($exp_path)) {
    foreach (file($exp_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $e = json_decode($line, true);
        // Skip manually entered RunPod entries — replaced by live API data below
        if ($e && ($e['category'] ?? '') === 'Compute' && stripos($e['description'] ?? '', 'RunPod') !== false && empty($e['manual'])) {
            continue;
        }
        if ($e) $all_expenses[] = $e;
    }
}

// Inject live RunPod compute costs from REST billing API
$_exp_audit_cfg = file_exists(__DIR__ . '/data/audit_config.json') ? json_decode(file_get_contents(__DIR__ . '/data/audit_config.json'), true) : [];
$_exp_rp_key = $_exp_audit_cfg['runpod_api_key'] ?? '';
if ($_exp_rp_key) {
    $ch = curl_init("https://rest.runpod.io/v1/billing/endpoints?bucketSize=day&startTime=" . urlencode(date('Y') . "-01-01T00:00:00Z") . "&endTime=" . urlencode(date('c')));
    curl_setopt_array($ch, [
        CURLOPT_HTTPHEADER => ["Authorization: Bearer {$_exp_rp_key}"],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $_exp_rp_data = json_decode(curl_exec($ch), true);
    curl_close($ch);
    if (is_array($_exp_rp_data)) {
        // Map endpoint IDs to names
        $_exp_ep_names = [];
        foreach ($_exp_audit_cfg['runpod_weights_endpoints'] ?? [] as $tn => $tv) {
            $_exp_ep_names[$tv['endpoint_id'] ?? ''] = strtoupper($tn);
        }
        $_exp_ep_names[$_exp_audit_cfg['runpod_endpoint_id_api'] ?? ''] = 'API';

        foreach ($_exp_rp_data as $rb) {
            $amt = (float)($rb['amount'] ?? 0);
            if ($amt <= 0) continue;
            $date = substr($rb['time'] ?? '', 0, 10);
            $epid = $rb['endpointId'] ?? '';
            $epname = $_exp_ep_names[$epid] ?? substr($epid, 0, 8);
            $time_s = ($rb['timeBilledMs'] ?? 0) / 1000;
            $time_fmt = $time_s >= 3600 ? sprintf('%.1fh', $time_s/3600) : ($time_s >= 60 ? sprintf('%.0fm', $time_s/60) : sprintf('%.0fs', $time_s));
            $all_expenses[] = [
                'id' => 'rp_' . md5($epid . $date),
                'date' => $date,
                'category' => 'Compute',
                'description' => "RunPod {$epname} ({$time_fmt} GPU time)",
                'amount' => round($amt, 4),
                'receipt_url' => '',
                'created_at' => $date . 'T00:00:00Z',
                '_auto' => true,
            ];
        }
    }
}

usort($all_expenses, function($a, $b) {
    $d = strcmp($b['date'] ?? '', $a['date'] ?? '');
    if ($d !== 0) return $d;
    return strcmp($a['description'] ?? '', $b['description'] ?? '');
});

$expense_categories = ['R&D', 'Operations', 'Equipment', 'Travel', 'Office', 'Hosting', 'Compute', 'Software'];
$cat_totals = array_fill_keys($expense_categories, 0.0);
$grand_total = 0.0;
$current_year = date('Y');
$quarterly = [0.0, 0.0, 0.0, 0.0];

foreach ($all_expenses as $e) {
    if (substr($e['date'] ?? '', 0, 4) === $current_year) {
        $cat = $e['category'] ?? '';
        $amt = floatval($e['amount'] ?? 0);
        if (isset($cat_totals[$cat])) $cat_totals[$cat] += $amt;
        $grand_total += $amt;
        $month = (int)substr($e['date'], 5, 2);
        $quarterly[min(3, intval(($month - 1) / 3))] += $amt;
    }
}

$rd_qualified = ($cat_totals['R&D'] ?? 0) + ($cat_totals['Compute'] ?? 0) + ($cat_totals['Software'] ?? 0);
$federal_credit = $rd_qualified * 0.065;
$wi_credit = $rd_qualified * 0.05;
?>

<h2 style="margin-bottom:24px">Business Expenses</h2>

<!-- Recurring Expenses -->
<?php
$recurring_path = __DIR__ . '/data/recurring_expenses.json';
$recurring = file_exists($recurring_path) ? json_decode(file_get_contents($recurring_path), true) : [];
if (!is_array($recurring)) $recurring = [];

// Auto-generate any recurring expenses that are due
$today = date('Y-m-d');
$this_month = date('Y-m');
foreach ($recurring as $rec) {
    $freq = $rec['frequency'] ?? 'monthly';
    $rec_desc = $rec['description'] ?? '';
    $rec_cat = $rec['category'] ?? '';
    $rec_amt = (float)($rec['amount'] ?? 0);
    // Check if already generated this period (match on category + similar amount in same month)
    $already = false;
    foreach ($all_expenses as $ex) {
        if (substr($ex['date'] ?? '', 0, 7) === $this_month && ($ex['category'] ?? '') === $rec_cat) {
            // Same category, same month, similar amount = already covered
            $ex_amt = (float)($ex['amount'] ?? 0);
            if (abs($ex_amt - $rec_amt) < 0.01 || stripos($ex['description'] ?? '', substr($rec_desc, 0, 15)) !== false) {
                $already = true;
                break;
            }
        }
    }
    if (!$already && $rec_desc) {
        $auto = [
            'id' => 'exp_' . bin2hex(random_bytes(6)),
            'date' => date('Y-m-01'),
            'category' => $rec['category'] ?? 'Operations',
            'description' => $rec_desc,
            'amount' => (float)($rec['amount'] ?? 0),
            'receipt_url' => '',
            'created_at' => date('c'),
        ];
        if ($auto['amount'] > 0) {
            file_put_contents($exp_path, json_encode($auto, JSON_UNESCAPED_SLASHES) . "\n", FILE_APPEND | LOCK_EX);
            $all_expenses[] = $auto;
            $cat = $auto['category'];
            if (isset($cat_totals[$cat])) $cat_totals[$cat] += $auto['amount'];
            $grand_total += $auto['amount'];
        }
    }
}
?>
<div class="card" style="padding:20px;margin-bottom:24px">
    <h3 style="margin-bottom:12px">Recurring Expenses</h3>
    <div style="font-size:12px;color:var(--text-dim);margin-bottom:12px">Auto-generated on the 1st of each month. Edit <code>data/recurring_expenses.json</code> or manage below.</div>
    <div class="table-wrap">
        <table>
            <thead><tr><th>Description</th><th>Category</th><th>Amount</th><th>Frequency</th><th></th></tr></thead>
            <tbody>
                <?php foreach ($recurring as $ri => $rec): ?>
                <tr>
                    <td><?php echo htmlspecialchars($rec['description'] ?? ''); ?></td>
                    <td><span class="badge" style="font-size:0.72em"><?php echo htmlspecialchars($rec['category'] ?? ''); ?></span></td>
                    <td style="font-weight:600">$<?php echo number_format($rec['amount'] ?? 0, 2); ?>/<?php echo htmlspecialchars(substr($rec['frequency'] ?? 'mo', 0, 2)); ?></td>
                    <td class="text-dim"><?php echo htmlspecialchars($rec['frequency'] ?? 'monthly'); ?></td>
                    <td><button onclick="deleteRecurring(<?php echo $ri; ?>)" class="btn btn-sm" style="font-size:0.7em;color:var(--red);background:none;border:1px solid var(--red);padding:2px 8px">X</button></td>
                </tr>
                <?php endforeach; ?>
                <tr id="add-recurring-row">
                    <td><input type="text" id="rec-desc" placeholder="Description" style="padding:4px 8px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85em;width:100%"></td>
                    <td><select id="rec-cat" style="padding:4px 6px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.82em">
                        <?php foreach ($expense_categories as $c): ?><option value="<?php echo htmlspecialchars($c); ?>"><?php echo htmlspecialchars($c); ?></option><?php endforeach; ?>
                    </select></td>
                    <td><input type="number" id="rec-amt" step="0.01" min="0.01" placeholder="0.00" style="padding:4px 8px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85em;width:80px"></td>
                    <td><select id="rec-freq" style="padding:4px 6px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.82em">
                        <option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option>
                    </select></td>
                    <td><button onclick="addRecurring()" class="btn btn-sm" style="font-size:0.72em;padding:2px 8px">+ Add</button></td>
                </tr>
            </tbody>
        </table>
    </div>
</div>

<!-- Add Expense -->
<div class="card" style="padding:24px;margin-bottom:24px">
    <h3 style="margin-bottom:16px">Add Expense</h3>
    <form id="expense-form" onsubmit="return saveExpense(event)" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
        <div style="display:flex;flex-direction:column;gap:4px">
            <label style="font-size:0.78em;color:var(--text-dim)">Date</label>
            <input type="date" name="date" required value="<?php echo date('Y-m-d'); ?>" style="padding:8px 12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.88em">
        </div>
        <div style="display:flex;flex-direction:column;gap:4px">
            <label style="font-size:0.78em;color:var(--text-dim)">Category</label>
            <select name="category" required style="padding:8px 12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.88em">
                <?php foreach ($expense_categories as $cat): ?>
                <option value="<?php echo htmlspecialchars($cat); ?>"><?php echo htmlspecialchars($cat); ?></option>
                <?php endforeach; ?>
            </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:200px">
            <label style="font-size:0.78em;color:var(--text-dim)">Description</label>
            <input type="text" name="description" required placeholder="e.g. Claude Code subscription, RunPod charges" style="padding:8px 12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.88em">
        </div>
        <div style="display:flex;flex-direction:column;gap:4px;width:110px">
            <label style="font-size:0.78em;color:var(--text-dim)">Amount ($)</label>
            <input type="number" name="amount" required step="0.01" min="0.01" placeholder="0.00" style="padding:8px 12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.88em">
        </div>
        <div style="display:flex;flex-direction:column;gap:4px;min-width:160px">
            <label style="font-size:0.78em;color:var(--text-dim)">Receipt <span style="opacity:0.5">(optional)</span></label>
            <input type="file" name="receipt_file" accept="image/*,.pdf" style="padding:4px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.82em">
        </div>
        <button type="submit" class="btn btn-sm" style="height:38px;background:var(--accent);color:#111;font-weight:600">+ Add</button>
    </form>
</div>

<!-- YTD Summary -->
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:24px">
    <div class="card" style="text-align:center;padding:16px;border-left:3px solid var(--accent)">
        <div style="font-size:22px;font-weight:700;color:var(--green)">$<?php echo number_format($grand_total, 2); ?></div>
        <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px">YTD Total</div>
    </div>
    <?php foreach ($cat_totals as $cat => $total): if ($total > 0): ?>
    <div class="card" style="text-align:center;padding:16px">
        <div style="font-size:18px;font-weight:700">$<?php echo number_format($total, 2); ?></div>
        <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px"><?php echo htmlspecialchars($cat); ?></div>
    </div>
    <?php endif; endforeach; ?>
</div>

<!-- Quarterly Breakdown -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px">
    <?php for ($q = 0; $q < 4; $q++): ?>
    <div class="card" style="text-align:center;padding:16px">
        <div style="font-size:18px;font-weight:700;color:<?php echo $quarterly[$q] > 0 ? 'var(--text-bright)' : 'var(--text-dim)'; ?>">$<?php echo number_format($quarterly[$q], 2); ?></div>
        <div style="font-size:11px;color:var(--text-dim)">Q<?php echo $q + 1; ?> <?php echo $current_year; ?></div>
    </div>
    <?php endfor; ?>
</div>

<!-- R&D Credit Estimator -->
<div class="card" style="padding:20px;margin-bottom:24px;border-left:3px solid var(--accent)">
    <h3 style="margin-bottom:12px">R&amp;D Credit Estimator <span style="font-size:0.7em;color:var(--text-dim);font-weight:normal">(R&amp;D + Compute + Software categories)</span></h3>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
        <div>
            <div style="font-size:0.78em;color:var(--text-dim);margin-bottom:4px">Qualified Expenses</div>
            <div style="font-size:1.4em;font-weight:700">$<?php echo number_format($rd_qualified, 2); ?></div>
        </div>
        <div>
            <div style="font-size:0.78em;color:var(--text-dim);margin-bottom:4px">Federal Credit (6.5%)</div>
            <div style="font-size:1.4em;font-weight:700;color:var(--green)">$<?php echo number_format($federal_credit, 2); ?></div>
        </div>
        <div>
            <div style="font-size:0.78em;color:var(--text-dim);margin-bottom:4px">Wisconsin Credit (5%)</div>
            <div style="font-size:1.4em;font-weight:700;color:var(--green)">$<?php echo number_format($wi_credit, 2); ?></div>
        </div>
    </div>
    <div style="margin-top:10px;font-size:0.72em;color:var(--text-dim)">Logged expenses only. Does not include developer labor (configure in audit_config.json: tax_dev_hours_ytd, tax_dev_hourly_rate). Consult a CPA.</div>
</div>

<!-- Expenses Table -->
<div class="card" style="margin-bottom:24px">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border)">
        <h3>All Expenses</h3>
        <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="expense-search" placeholder="Search..." oninput="filterExpenses()" style="padding:6px 10px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.82em;width:160px">
            <button class="btn btn-sm" style="font-size:0.82em" onclick="exportExpensesCSV()">CSV</button>
        </div>
    </div>
    <div class="table-wrap">
        <table id="expenses-table">
            <thead><tr><th style="width:130px">Date</th><th style="width:100px">Category</th><th>Description</th><th style="width:100px;text-align:right">Amount</th><th style="width:80px">Receipt</th><th style="width:40px"></th></tr></thead>
            <tbody>
                <?php if (empty($all_expenses)): ?>
                <tr><td colspan="6" style="text-align:center;color:var(--text-dim);padding:40px">No expenses recorded yet.</td></tr>
                <?php else:
                $cat_colors = [
                    'R&D' => 'background:rgba(174,129,255,0.15);color:#ae81ff;border-color:#ae81ff',
                    'Software' => 'background:rgba(102,217,239,0.15);color:#66d9ef;border-color:#66d9ef',
                    'Compute' => 'background:rgba(253,151,31,0.15);color:#fd971f;border-color:#fd971f',
                    'Hosting' => 'background:rgba(230,219,116,0.15);color:#e6db74;border-color:#e6db74',
                    'Equipment' => 'background:rgba(166,226,46,0.15);color:#a6e22e;border-color:#a6e22e',
                    'Operations' => 'background:rgba(117,113,94,0.25);color:#a8a890;border-color:#75715e',
                    'Travel' => 'background:rgba(249,38,114,0.15);color:#f92672;border-color:#f92672',
                    'Office' => 'background:rgba(166,226,46,0.15);color:#a6e22e;border-color:#a6e22e',
                ];
                foreach ($all_expenses as $exp):
                    $eid = htmlspecialchars($exp['id'] ?? '');
                    $ecat = $exp['category'] ?? '';
                    $ecolor = $cat_colors[$ecat] ?? '';
                ?>
                <?php $is_auto = !empty($exp['_auto']); ?>
                <tr data-id="<?php echo $eid; ?>"<?php if ($is_auto) echo ' style="opacity:0.85"'; ?>>
                    <?php if ($is_auto): ?>
                    <td class="text-sm nowrap"><?php echo htmlspecialchars($exp['date'] ?? ''); ?></td>
                    <td><span class="badge" style="font-size:0.72em;<?php echo $ecolor; ?>"><?php echo htmlspecialchars($ecat); ?></span></td>
                    <td style="font-size:0.88em"><?php echo htmlspecialchars($exp['description'] ?? ''); ?></td>
                    <td style="text-align:right;font-weight:600;font-size:0.88em">$<?php echo number_format($exp['amount'] ?? 0, 4); ?></td>
                    <?php else: ?>
                    <td><input type="date" value="<?php echo htmlspecialchars($exp['date'] ?? ''); ?>" onchange="editExpense('<?php echo $eid; ?>','date',this.value)" style="padding:2px 6px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85em;width:130px"></td>
                    <td><select onchange="editExpense('<?php echo $eid; ?>','category',this.value)" style="padding:2px 6px;background:var(--bg-surface);border:1px solid transparent;border-radius:4px;font-size:0.78em;<?php echo $ecolor; ?>">
                        <?php foreach ($expense_categories as $c): ?>
                        <option value="<?php echo htmlspecialchars($c); ?>" <?php echo $c === $ecat ? 'selected' : ''; ?>><?php echo htmlspecialchars($c); ?></option>
                        <?php endforeach; ?>
                    </select></td>
                    <td><input type="text" value="<?php echo htmlspecialchars($exp['description'] ?? ''); ?>" onchange="editExpense('<?php echo $eid; ?>','description',this.value)" style="padding:2px 6px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85em;width:100%"></td>
                    <td><input type="number" value="<?php echo number_format($exp['amount'] ?? 0, 2, '.', ''); ?>" step="0.01" onchange="editExpense('<?php echo $eid; ?>','amount',parseFloat(this.value))" style="padding:2px 6px;background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85em;width:90px;text-align:right;font-weight:600"></td>
                    <?php endif; ?>
                    <td><?php
                        $rurl = $exp['receipt_url'] ?? '';
                        if ($rurl && preg_match('/\.(jpg|jpeg|png|webp)$/i', $rurl)):
                    ?><a href="<?php echo htmlspecialchars($rurl); ?>" target="_blank"><img src="<?php echo htmlspecialchars($rurl); ?>" style="max-width:40px;max-height:30px;border-radius:3px;border:1px solid var(--border)"></a><?php
                        elseif ($rurl):
                    ?><a href="<?php echo htmlspecialchars($rurl); ?>" target="_blank" style="color:var(--accent);font-size:0.82em">View</a><?php
                        else:
                    ?><input type="file" accept="image/*,.pdf" onchange="uploadReceipt('<?php echo $eid; ?>',this)" style="width:80px;font-size:0.7em;color:var(--text-dim)"><?php
                        endif;
                    ?></td>
                    <td><?php if (empty($exp['_auto'])): ?><button onclick="deleteExpense('<?php echo $eid; ?>', this)" class="btn btn-sm" style="font-size:0.7em;color:var(--red);background:none;border:1px solid var(--red);padding:2px 8px">X</button><?php else: ?><span style="font-size:0.68em;color:var(--text-dim)" title="Auto-generated from RunPod API">AUTO</span><?php endif; ?></td>
                </tr>
                <?php endforeach; endif; ?>
            </tbody>
        </table>
    </div>
</div>

<script>
function saveExpense(e) {
    e.preventDefault();
    var f = e.target;
    var fileInput = f.receipt_file;
    var doSave = function(receiptUrl) {
        apiCall('/admin.php?ajax=save_expense', { body: {
            date: f.date.value, category: f.category.value, description: f.description.value,
            amount: parseFloat(f.amount.value), receipt_url: receiptUrl || ''
        }}).then(function(d) {
            if (d.ok) { if (typeof showToast === 'function') showToast('Expense added'); setTimeout(function(){location.reload()},600); }
            else { alert(d.error || 'Failed'); }
        });
    };
    if (fileInput && fileInput.files.length > 0) {
        var fd = new FormData();
        fd.append('receipt', fileInput.files[0]);
        fd.append('_csrf', CSRF_TOKEN);
        fetch('/admin.php?ajax=upload_receipt', {method:'POST', body:fd, credentials:'same-origin'})
            .then(function(r){return r.json()})
            .then(function(d){ doSave(d.ok ? d.url : ''); });
    } else {
        doSave('');
    }
    return false;
}
function deleteExpense(id, btn) {
    if (!confirm('Delete this expense?')) return;
    apiCall('/admin.php?ajax=delete_expense', { body: { id: id } }).then(function(d) {
        if (d.ok) { btn.closest('tr').remove(); if (typeof showToast === 'function') showToast('Deleted'); }
    });
}
function filterExpenses() {
    var q = document.getElementById('expense-search').value.toLowerCase();
    document.querySelectorAll('#expenses-table tbody tr').forEach(function(r) {
        r.style.display = r.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
    });
}
function exportExpensesCSV() {
    window.location.href = '/admin.php?ajax=export_expenses&_csrf=' + encodeURIComponent(CSRF_TOKEN);
}
function addRecurring() {
    var desc = document.getElementById('rec-desc').value;
    var cat = document.getElementById('rec-cat').value;
    var amt = parseFloat(document.getElementById('rec-amt').value);
    var freq = document.getElementById('rec-freq').value;
    if (!desc || !amt) { alert('Fill in description and amount'); return; }
    apiCall('/admin.php?ajax=save_recurring', { body: { description: desc, category: cat, amount: amt, frequency: freq }})
        .then(function(d) { if (d.ok) { showToast('Recurring expense added'); location.reload(); } else alert(d.error); });
}
function deleteRecurring(idx) {
    if (!confirm('Remove this recurring expense?')) return;
    apiCall('/admin.php?ajax=delete_recurring', { body: { index: idx }})
        .then(function(d) { if (d.ok) { showToast('Removed'); location.reload(); } });
}
function uploadReceipt(expId, input) {
    if (!input.files.length) return;
    var fd = new FormData();
    fd.append('receipt', input.files[0]);
    fd.append('_csrf', CSRF_TOKEN);
    fetch('/admin.php?ajax=upload_receipt', {method:'POST', body:fd, credentials:'same-origin'})
        .then(function(r){return r.json()})
        .then(function(d){
            if (d.ok) {
                editExpense(expId, 'receipt_url', d.url);
                showToast('Receipt uploaded');
                setTimeout(function(){location.reload()},600);
            } else alert(d.error);
        });
}
function editExpense(id, field, value) {
    var body = { id: id };
    body[field] = value;
    apiCall('/admin.php?ajax=update_expense', { body: body })
        .then(function(d) { if (d.ok && typeof showToast === 'function') showToast('Updated'); });
}
</script>
<?php } // end origin-only expenses ?>

<?php elseif ($active_view === 'settings'): ?>
<!-- ══════════════ SETTINGS ══════════════ -->
<?php
$_scfg_path = __DIR__ . '/data/audit_config.json';
$_scfg = file_exists($_scfg_path) ? json_decode(file_get_contents($_scfg_path), true) : [];
$_s_maint = !empty($_scfg['audit_maintenance']);
$_s_maint_msg = $_scfg['audit_maintenance_message'] ?? 'Certified Audit infrastructure is being upgraded. Purchases are temporarily disabled. Check back soon.';
$_s_stripe_path = __DIR__ . '/data/stripe_config.json';
$_s_stripe = file_exists($_s_stripe_path) ? json_decode(file_get_contents($_s_stripe_path), true) : [];
$_s_stripe_mode = (strpos($_s_stripe['secret_key'] ?? '', 'test') !== false) ? 'TEST' : 'LIVE';
?>
<h2 style="margin-bottom:24px">Settings</h2>

<!-- Audit Maintenance Toggle -->
<div class="card" style="margin-bottom:24px;padding:24px">
    <h3 style="margin-bottom:16px">Certified Audit System</h3>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
            <input type="checkbox" id="maint-toggle" <?php echo $_s_maint ? 'checked' : ''; ?>
                style="width:20px;height:20px;accent-color:var(--accent);cursor:pointer"
                onchange="toggleMaintenance(this.checked)">
            <span style="font-size:14px;font-weight:600;color:var(--text-bright)">Maintenance Mode</span>
        </label>
        <span id="maint-badge" class="badge <?php echo $_s_maint ? 'badge-yellow' : 'badge-green'; ?>" style="font-size:0.78em">
            <?php echo $_s_maint ? 'ON — Purchases Disabled' : 'OFF — Accepting Orders'; ?>
        </span>
    </div>
    <div style="margin-bottom:12px">
        <label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:4px">Public maintenance message</label>
        <input type="text" id="maint-msg" value="<?php echo htmlspecialchars($_s_maint_msg); ?>"
            style="width:100%;padding:8px 12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:0.88em"
            onchange="saveMaintMessage(this.value)">
    </div>
    <div style="font-size:12px;color:var(--text-dim)">
        When enabled: enterprise page shows a banner, Start Audit buttons are disabled, and checkout API rejects audit purchases. Admins and Origin bypass all restrictions.
    </div>
</div>

<!-- Stripe Mode -->
<div class="card" style="margin-bottom:24px;padding:24px">
    <h3 style="margin-bottom:16px">Payment System</h3>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <span style="font-size:14px;font-weight:600;color:var(--text-bright)">Stripe Mode</span>
        <span id="stripe-badge" class="badge <?php echo $_s_stripe_mode === 'TEST' ? 'badge-yellow' : 'badge-green'; ?>" style="font-size:0.82em"><?php echo $_s_stripe_mode; ?></span>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:12px">
        <button onclick="setStripeMode('live')" id="stripe-live-btn" class="btn btn-sm" style="font-size:0.82em;<?php echo $_s_stripe_mode === 'LIVE' ? 'background:var(--green);color:#111;' : ''; ?>">Live</button>
        <button onclick="setStripeMode('test')" id="stripe-test-btn" class="btn btn-sm" style="font-size:0.82em;<?php echo $_s_stripe_mode === 'TEST' ? 'background:var(--yellow);color:#111;' : ''; ?>">Test</button>
    </div>
    <div style="font-size:12px;color:var(--text-dim)">
        Key prefix: <code id="stripe-key-prefix" style="font-size:0.85em"><?php echo htmlspecialchars(substr($_s_stripe['secret_key'] ?? '', 0, 12)); ?>...</code>
    </div>
</div>

<!-- RunPod Endpoints -->
<div class="card" style="margin-bottom:24px;padding:24px">
    <h3 style="margin-bottom:16px">RunPod GPU Tiers</h3>
    <div class="table-wrap">
        <table>
            <thead><tr><th>Tier</th><th>GPU</th><th>VRAM</th><th>Max Params (INT4)</th><th>Price/hr</th><th>Endpoint</th></tr></thead>
            <tbody>
                <?php foreach ($_scfg['runpod_weights_endpoints'] ?? [] as $tn => $t): ?>
                <tr>
                    <td><span class="badge" style="font-size:0.78em"><?php echo strtoupper(htmlspecialchars($tn)); ?></span></td>
                    <td><?php echo htmlspecialchars($t['gpu'] ?? ''); ?></td>
                    <td><?php echo ($t['vram_gb'] ?? 0); ?> GB</td>
                    <td><?php echo ($t['max_params_b'] ?? 0); ?>B</td>
                    <td>$<?php echo number_format(($t['gpu_count'] ?? 1) * ($t['gpu_price_per_hr'] ?? 0), 2); ?>/hr</td>
                    <td><code style="font-size:0.78em"><?php echo htmlspecialchars($t['endpoint_id'] ?? ''); ?></code></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>

<script>
function toggleMaintenance(enabled) {
    var fd = new FormData();
    fd.append('csrf_token', '<?php echo $csrf_token; ?>');
    fd.append('audit_maintenance', enabled ? '1' : '0');
    fetch('/admin.php?action=save_settings', {method:'POST', body: fd, credentials:'same-origin'})
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                var badge = document.getElementById('maint-badge');
                badge.className = 'badge ' + (d.audit_maintenance ? 'badge-yellow' : 'badge-green');
                badge.textContent = d.audit_maintenance ? 'ON \u2014 Purchases Disabled' : 'OFF \u2014 Accepting Orders';
                if (typeof showToast === 'function') showToast(d.audit_maintenance ? 'Maintenance mode enabled' : 'Maintenance mode disabled');
            } else {
                alert(d.error || 'Failed to save');
                document.getElementById('maint-toggle').checked = !enabled;
            }
        });
}
function saveMaintMessage(msg) {
    var fd = new FormData();
    fd.append('csrf_token', '<?php echo $csrf_token; ?>');
    fd.append('audit_maintenance_message', msg);
    fetch('/admin.php?action=save_settings', {method:'POST', body: fd, credentials:'same-origin'})
        .then(r => r.json())
        .then(d => { if (d.ok && typeof showToast === 'function') showToast('Message updated'); });
}
function setStripeMode(mode) {
    if (mode === 'live' && !confirm('Switch to LIVE Stripe? Real payments will be processed.')) return;
    var fd = new FormData();
    fd.append('csrf_token', '<?php echo $csrf_token; ?>');
    fd.append('stripe_mode', mode);
    fetch('/admin.php?action=save_settings', {method:'POST', body: fd, credentials:'same-origin'})
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(d => {
            if (d.ok) {
                var badge = document.getElementById('stripe-badge');
                var liveBtn = document.getElementById('stripe-live-btn');
                var testBtn = document.getElementById('stripe-test-btn');
                badge.className = 'badge ' + (d.stripe_mode === 'TEST' ? 'badge-yellow' : 'badge-green');
                badge.textContent = d.stripe_mode;
                liveBtn.style.background = d.stripe_mode === 'LIVE' ? 'var(--green)' : '';
                liveBtn.style.color = d.stripe_mode === 'LIVE' ? '#111' : '';
                testBtn.style.background = d.stripe_mode === 'TEST' ? 'var(--yellow)' : '';
                testBtn.style.color = d.stripe_mode === 'TEST' ? '#111' : '';
                document.getElementById('stripe-key-prefix').textContent = d.stripe_mode === 'TEST' ? 'sk_test_...' : 'rk_live_...';
                if (typeof showToast === 'function') showToast('Stripe switched to ' + d.stripe_mode);
            } else {
                alert(d.error || 'Failed');
            }
        });
}
</script>

<?php endif; ?>

    </div>
</div>

<!-- ══════════════ MODALS ══════════════ -->

<!-- Generate Master Modal -->
<div class="modal-overlay" id="modal-generate">
    <div class="modal">
        <div class="modal-header">
            <h3>Generate Master Passport</h3>
            <button class="modal-close" onclick="closeModal('modal-generate')">&times;</button>
        </div>
        <form id="form-generate" onsubmit="return handleGenerate(event)">
            <div class="form-group">
                <label class="form-label">Tier</label>
                <select class="form-select" name="tier" required>
                    <?php
                    // Non-origin admins can only create pro/power passports. Origin tier reserved for $is_origin.
                    $allowed_gen_tiers = $is_origin ? $tiers_config : array_diff_key($tiers_config, array_flip(['origin']));
                    foreach ($allowed_gen_tiers as $tid => $tc):
                        if ($tid === 'community') continue; // community doesn't need passports
                    ?>
                    <option value="<?php echo htmlspecialchars($tid); ?>"><?php echo htmlspecialchars($tc['label']); ?> (<?php echo isset($tc['price_display']) ? $tc['price_display'] : 'Free'; ?>, <?php echo isset($tc['seats']) ? ($tc['seats'] < 0 ? 'unlimited' : $tc['seats']) : '?' ?> seats)</option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Customer Name</label>
                <input type="text" class="form-input" name="customer_label" placeholder="John Smith" required>
            </div>
            <div class="form-group">
                <label class="form-label">Email</label>
                <input type="email" class="form-input" name="email" placeholder="john@example.com">
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary btn-sm" onclick="closeModal('modal-generate')">Cancel</button>
                <button type="submit" class="btn btn-primary btn-sm">Generate Passport</button>
            </div>
        </form>
    </div>
</div>

<!-- Register Token Modal -->
<div class="modal-overlay" id="modal-token">
    <div class="modal">
        <div class="modal-header">
            <h3>Register API Token</h3>
            <button class="modal-close" onclick="closeModal('modal-token')">&times;</button>
        </div>
        <p style="color:var(--text-dim);font-size:0.85rem;padding:0 24px;margin-bottom:16px">
            Tokens authenticate Forge clients against the server for telemetry uploads,
            assurance report sharing, genome sync, and fleet management. Each user or machine
            gets a unique token. The plaintext is given to the user — only the SHA-512 hash is stored.
        </p>
        <form id="form-token" onsubmit="return handleRegisterToken(event)">
            <div class="form-group">
                <label class="form-label">Label</label>
                <input type="text" class="form-input" name="label" placeholder="e.g. alice-macbook, ci-runner-01, staging-gpu" required pattern="[a-zA-Z0-9_-]+">
                <span class="form-hint">A human-readable name to identify this token. Letters, numbers, dashes, underscores.</span>
            </div>
            <div class="form-group">
                <label class="form-label">Token (plaintext)</label>
                <div style="display:flex;gap:8px;align-items:center">
                    <input type="text" class="form-input form-input-mono" name="token" id="token-input" placeholder="Click Generate or paste your own" required style="flex:1">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('token-input').value='fg_tk_'+Array.from(crypto.getRandomValues(new Uint8Array(24)),b=>b.toString(16).padStart(2,'0')).join('')">Generate</button>
                </div>
                <span class="form-hint">This is the value the user puts in their <code>telemetry_token</code> config. Store it — you won't see it again after registration.</span>
            </div>
            <div class="form-group">
                <label class="form-label">Tier</label>
                <select class="form-select" name="role">
                    <option value="standalone">Community</option>
                    <option value="master-pro">Pro</option>
                    <option value="master-power">Power</option>
                </select>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary btn-sm" onclick="closeModal('modal-token')">Cancel</button>
                <button type="submit" class="btn btn-primary btn-sm">Register Token</button>
            </div>
        </form>
    </div>
</div>

<script>
var CSRF_TOKEN = <?php echo json_encode($csrf_token); ?>;

function revokeFromAdmin(runId, pairedId) {
    var reason = prompt('REVOKE Origin certification' + (pairedId ? ' for both paired reports' : '') + '.\n\nReason for revocation:');
    if (reason === null) return;
    var body = JSON.stringify({notes: reason});
    var headers = {'Content-Type': 'application/json'};
    var promises = [
        fetch('/assurance_verify.php?action=revoke_cert&run_id=' + encodeURIComponent(runId), {
            method: 'POST', credentials: 'same-origin', headers: headers, body: body
        }).then(function(r) { return r.json(); })
    ];
    if (pairedId) {
        promises.push(
            fetch('/assurance_verify.php?action=revoke_cert&run_id=' + encodeURIComponent(pairedId), {
                method: 'POST', credentials: 'same-origin', headers: headers, body: body
            }).then(function(r) { return r.json(); })
        );
    }
    Promise.all(promises).then(function(results) {
        var allOk = results.every(function(d) { return d.status === 'revoked' || d.status === 'not_certified'; });
        if (allOk) {
            showToast('Certification revoked', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast('Revocation failed', 'error');
        }
    }).catch(function() { showToast('Network error', 'error'); });
}

function certifyFromAdmin(runId, pairedId) {
    var msg = pairedId
        ? 'Origin-certify Forge Parallax pair?\n\nBreak: ' + runId + '\nAssurance: ' + pairedId
        : 'Origin-certify report ' + runId + '?';
    if (!confirm(msg)) return;
    var promises = [
        fetch('/assurance_verify.php?action=certify&run_id=' + encodeURIComponent(runId), {
            method: 'POST', credentials: 'same-origin'
        }).then(function(r) { return r.json(); })
    ];
    if (pairedId) {
        promises.push(
            fetch('/assurance_verify.php?action=certify&run_id=' + encodeURIComponent(pairedId), {
                method: 'POST', credentials: 'same-origin'
            }).then(function(r) { return r.json(); })
        );
    }
    Promise.all(promises).then(function(results) {
        var allOk = results.every(function(d) { return d.status === 'certified' || d.status === 'already_certified'; });
        if (allOk) {
            showToast(pairedId ? 'Parallax pair certified' : 'Report certified', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            var errs = results.filter(function(d) { return d.error; }).map(function(d) { return d.error; });
            showToast(errs.join(', ') || 'Certification failed', 'error');
        }
    }).catch(function() { showToast('Network error', 'error'); });
}

function refreshAuditProgress(orderId) {
    fetch('/audit_orchestrator.php?action=status&order_id=' + encodeURIComponent(orderId))
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (typeof showToast === 'function') {
                var p = d.progress || {};
                var m = (d.models || [{}])[0];
                var msg = m.status || 'unknown';
                if (p.stage) msg += ' | ' + p.stage;
                if (p.current > 0) msg += ' ' + p.current + '/' + p.total;
                showToast(msg);
            }
            setTimeout(function() { location.reload(); }, 500);
        });
}
function manualTriggerAudit(orderId) {
    if (!confirm('Dispatch/re-dispatch RunPod jobs for order ' + orderId + '?')) return;
    fetch('/audit_orchestrator.php?action=manual_trigger&order_id=' + encodeURIComponent(orderId), {
        method: 'POST',
        credentials: 'same-origin',
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            showToast('Dispatched ' + (d.dispatched || 0) + ' job(s)', 'success');
            setTimeout(function() { location.reload(); }, 1200);
        } else {
            showToast(d.error || 'Dispatch failed', 'error');
        }
    }).catch(function() { showToast('Network error', 'error'); });
}

function clearFraudLog() {
    if (!confirm('PERMANENTLY DELETE ALL fraud log entries?\n\nThis cannot be undone.')) return;
    apiCall('/admin.php?ajax=clear_fraud', { body: {} }).then(function(d) {
        if (d.ok) {
            showToast(d.deleted + ' fraud entries cleared', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(d.error || 'Clear failed', 'error');
        }
    });
}

function deleteAuditEntry(id, btn) {
    apiCall('/admin.php?ajax=delete_audit', { body: { id: id } }).then(function(d) {
        if (d.ok) {
            var row = btn.closest('tr');
            if (row) row.remove();
        } else {
            showToast(d.error || 'Delete failed', 'error');
        }
    });
}

function clearAuditLog() {
    if (!confirm('PERMANENTLY DELETE ALL audit log entries?\n\nThis cannot be undone.')) return;
    apiCall('/admin.php?ajax=clear_audit', { body: {} }).then(function(d) {
        if (d.ok) {
            showToast(d.deleted + ' entries cleared', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(d.error || 'Clear failed', 'error');
        }
    });
}

function deleteReport(runId, pairedId) {
    var msg = pairedId
        ? 'PERMANENTLY DELETE Parallax pair?\n\nBreak: ' + runId + '\nAssurance: ' + pairedId + '\n\nThis cannot be undone.'
        : 'PERMANENTLY DELETE report ' + runId + '?\n\nThis cannot be undone.';
    if (!confirm(msg)) return;
    var body = {run_id: runId, _csrf: CSRF_TOKEN};
    if (pairedId) {
        body.delete_pair = true;
        body.pair_run_id = pairedId;
    }
    fetch('/admin.php?ajax=delete_report', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            var count = (d.deleted || []).length;
            showToast(count + ' report(s) deleted', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(d.error || d.errors.join(', ') || 'Delete failed', 'error');
        }
    }).catch(function() { showToast('Network error', 'error'); });
}

function showToast(msg, type) {
    var el = document.createElement('div');
    el.textContent = msg;
    el.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;padding:12px 20px;border-radius:var(--radius-md);font-size:0.88em;font-weight:600;max-width:400px;box-shadow:0 4px 20px rgba(0,0,0,0.3);transition:opacity 0.3s;';
    el.style.background = type === 'error' ? 'var(--red)' : 'var(--green)';
    el.style.color = '#fff';
    document.body.appendChild(el);
    setTimeout(function() { el.style.opacity = '0'; setTimeout(function() { el.remove(); }, 300); }, 3000);
}

function apiCall(url, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json' };
    var fetchOpts = { method: opts.method || 'POST', headers: headers, credentials: 'same-origin' };
    if (opts.body) {
        if (typeof opts.body === 'object') opts.body._csrf = CSRF_TOKEN;
        fetchOpts.body = JSON.stringify(opts.body);
    }
    return fetch(url, fetchOpts).then(function(r) { return r.json(); });
}

/* ── Row flash indicator ── */
function flashRow(row, color) {
    if (!row) return;
    row.style.transition = 'background 0.3s';
    row.style.background = color || 'rgba(52,211,153,0.15)';
    setTimeout(function() { row.style.background = ''; }, 1500);
}
function findRowByEmail(email) {
    var rows = document.querySelectorAll('#users-table tbody tr[data-email]');
    for (var i = 0; i < rows.length; i++) {
        if (rows[i].getAttribute('data-email') === email) return rows[i];
    }
    return null;
}

function handleGenerate(e) {
    e.preventDefault();
    var f = e.target;
    apiCall('/passport_api.php?action=generate_master', {
        body: {
            tier: f.tier.value,
            customer_label: f.customer_label.value,
            email: f.email.value
        }
    }).then(function(data) {
        if (data.ok) {
            showToast('Master passport generated: ' + data.account_id, 'success');
            closeModal('modal-generate');
            setTimeout(function() { location.reload(); }, 1000);
        } else {
            showToast(data.error || 'Failed to generate', 'error');
        }
    }).catch(function() { showToast('Network error', 'error'); });
    return false;
}

function handleRegisterToken(e) {
    e.preventDefault();
    var f = e.target;
    var rawRole = f.role.value;
    var role = rawRole;
    var tier = null;

    if (rawRole === 'master-pro') { role = 'master'; tier = 'pro'; }
    else if (rawRole === 'master-power') { role = 'master'; tier = 'power'; }

    var token = f.token.value;
    crypto.subtle.digest('SHA-512', new TextEncoder().encode(token)).then(function(buf) {
        var hash = Array.from(new Uint8Array(buf)).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
        return apiCall('/token_admin.php', {
            body: { action: 'register', token_hash: hash, label: f.label.value, role: role }
        });
    }).then(function(data) {
        if (data.status !== 'ok') {
            showToast(data.error || 'Token registration failed', 'error');
            return;
        }
        if (tier) {
            return apiCall('/passport_api.php?action=generate_master', {
                body: { tier: tier, customer_label: f.label.value, email: '' }
            }).then(function(pdata) {
                if (pdata.ok || pdata.account_id) {
                    showToast('Token + ' + tier.toUpperCase() + ' passport created for ' + f.label.value, 'success');
                } else {
                    showToast('Token created but passport failed: ' + (pdata.error || ''), 'error');
                }
                closeModal('modal-token');
                setTimeout(function() { location.reload(); }, 1000);
            });
        } else {
            showToast('Token registered: ' + f.label.value, 'success');
            closeModal('modal-token');
            setTimeout(function() { location.reload(); }, 1000);
        }
    }).catch(function(err) { showToast(err.message || 'Error', 'error'); });
    return false;
}

function revokeToken(hash, label) {
    if (!confirm('Revoke token "' + label + '"? This cannot be undone.')) return;
    apiCall('/token_admin.php', { body: { action: 'revoke', token_hash: hash } })
    .then(function(data) {
        if (data.status === 'ok') {
            showToast('Token revoked: ' + label, 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(data.error || 'Failed', 'error');
        }
    });
}

function revokeMaster(accountId, label) {
    if (!confirm('Revoke master "' + label + '"? This will invalidate all their puppets.')) return;
    apiCall('/passport_api.php?action=revoke', { body: { account_id: accountId } })
    .then(function(data) {
        if (data.ok) {
            showToast('Master revoked. ' + (data.puppets_revoked || 0) + ' puppets invalidated.', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(data.error || 'Failed', 'error');
        }
    });
}

/* ── BUG FIX: Cancel restores select, does NOT reload ── */
function changeUserTier(email, newTier, selectEl) {
    var messages = {
        'pro': 'Upgrade "' + email + '" to Pro tier?\n\nThis will:\n- Update their tier in the database\n- Generate or update their master passport\n- Grant Pro-level features and seat count',
        'power': 'Upgrade "' + email + '" to Power tier?\n\nThis will:\n- Update their tier in the database\n- Generate or update their master passport\n- Grant Power-level features and maximum seat count',
        'community': 'Downgrade "' + email + '" to Community tier?\n\nThis will:\n- Update their tier in the database\n- Mark their passport as admin-downgraded (passport NOT deleted)\n- Remove paid-tier features'
    };
    if (!confirm(messages[newTier] || 'Change tier for "' + email + '" to ' + newTier + '?')) {
        /* Restore previous value instead of reloading */
        if (selectEl) {
            var prev = selectEl.getAttribute('data-prev') || 'community';
            selectEl.value = prev;
        }
        return;
    }
    apiCall('/admin.php?ajax=update_tier', {
        body: {email: email, tier: newTier}
    }).then(function(data) {
        if (data.ok) {
            var extra = '';
            if (data.passport_action === 'generated') extra = ' (passport auto-generated)';
            else if (data.passport_action === 'updated') extra = ' (passport updated)';
            else if (data.passport_action === 'downgraded') extra = ' (passport marked downgraded)';
            showToast('Tier changed to ' + newTier + extra, 'success');
            if (selectEl) selectEl.setAttribute('data-prev', newTier);
            flashRow(findRowByEmail(email));
            /* Always reload — tier change may update role, passport, etc. */
            setTimeout(function(){ location.reload(); }, 1200);
        } else {
            showToast(data.error || 'Failed', 'error');
            if (selectEl) {
                var prev = selectEl.getAttribute('data-prev') || 'community';
                selectEl.value = prev;
            }
        }
    });
}

function toggleAdmin(email, isAdmin) {
    apiCall('/admin.php?ajax=toggle_admin', {
        body: {email: email, is_admin: isAdmin}
    }).then(function(data) {
        if (data.ok) {
            showToast(isAdmin ? 'Admin granted' : 'Admin revoked', 'success');
            flashRow(findRowByEmail(email));
        } else {
            showToast(data.error || 'Failed', 'error');
            /* Revert checkbox */
            var row = findRowByEmail(email);
            if (row) {
                var cb = row.querySelector('input[type="checkbox"]');
                if (cb) cb.checked = !isAdmin;
            }
        }
    });
}

function changeUserRole(email, newRole, selectEl) {
    if (!confirm('Change role for "' + email + '" to ' + newRole + '?')) {
        if (selectEl) {
            var prev = selectEl.getAttribute('data-prev') || 'standalone';
            selectEl.value = prev;
        }
        return;
    }
    apiCall('/admin.php?ajax=update_role', {
        body: {email: email, role: newRole}
    }).then(function(data) {
        if (data.ok) {
            showToast('Role updated to ' + newRole, 'success');
            if (selectEl) selectEl.setAttribute('data-prev', newRole);
            flashRow(findRowByEmail(email));
        } else {
            showToast(data.error || 'Failed', 'error');
            if (selectEl) {
                var prev = selectEl.getAttribute('data-prev') || 'standalone';
                selectEl.value = prev;
            }
        }
    });
}

function toggleUserStatus(email, disable) {
    var action = disable ? 'disable' : 'enable';
    if (!confirm(action.charAt(0).toUpperCase() + action.slice(1) + ' user "' + email + '"?')) return;
    apiCall('/admin.php?ajax=toggle_status', {
        body: {email: email, disabled: disable}
    }).then(function(data) {
        if (data.ok) {
            showToast('User ' + action + 'd', 'success');
            var row = findRowByEmail(email);
            if (row) {
                row.style.opacity = disable ? '0.5' : '1';
                /* Update status cell */
                var statusTd = row.querySelector('.user-status-cell');
                if (statusTd) {
                    if (disable) {
                        statusTd.innerHTML = '<button class="btn btn-secondary" style="padding:2px 8px;font-size:0.72em" data-action="enable" data-email="' + email.replace(/"/g, '&quot;') + '">Enable</button>';
                    } else {
                        statusTd.innerHTML = '<span class="badge badge-green" style="cursor:pointer" data-action="disable" data-email="' + email.replace(/"/g, '&quot;') + '" title="Click to disable">Active</span>';
                    }
                }
                flashRow(row, disable ? 'rgba(248,113,113,0.15)' : 'rgba(52,211,153,0.15)');
            }
        } else {
            showToast(data.error || 'Failed', 'error');
        }
    });
}

/* ── Users table: search + pagination ── */
(function() {
    var table = document.getElementById('users-table');
    if (!table) return;

    var tbody = table.querySelector('tbody');
    var allRows = Array.from(tbody.querySelectorAll('tr'));
    var filteredRows = allRows.slice();
    var PAGE_SIZE = 25;
    var currentPage = 1;

    var searchInput = document.getElementById('users-search');
    var paginationDiv = document.getElementById('users-pagination');

    function applyFilter() {
        var q = (searchInput ? searchInput.value : '').toLowerCase();
        filteredRows = allRows.filter(function(r) {
            return !q || r.textContent.toLowerCase().indexOf(q) >= 0;
        });
        currentPage = 1;
        renderPage();
    }

    function renderPage() {
        var total = filteredRows.length;
        var totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        if (currentPage > totalPages) currentPage = totalPages;
        var start = (currentPage - 1) * PAGE_SIZE;
        var end = start + PAGE_SIZE;

        allRows.forEach(function(r) { r.style.display = 'none'; });
        filteredRows.slice(start, end).forEach(function(r) { r.style.display = ''; });

        if (paginationDiv) {
            paginationDiv.innerHTML =
                '<button class="btn btn-secondary btn-sm" ' + (currentPage <= 1 ? 'disabled' : '') + ' data-page="prev">&laquo; Prev</button>' +
                '<span class="text-dim text-sm" style="padding:0 12px">Page ' + currentPage + ' of ' + totalPages + ' (' + total + ' users)</span>' +
                '<button class="btn btn-secondary btn-sm" ' + (currentPage >= totalPages ? 'disabled' : '') + ' data-page="next">Next &raquo;</button>';
        }
    }

    if (searchInput) searchInput.addEventListener('input', applyFilter);
    if (paginationDiv) paginationDiv.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-page]');
        if (!btn || btn.disabled) return;
        if (btn.getAttribute('data-page') === 'prev') currentPage--;
        else currentPage++;
        renderPage();
    });

    /* Event delegation for status toggle buttons inside users table */
    if (tbody) tbody.addEventListener('click', function(e) {
        var el = e.target.closest('[data-action][data-email]');
        if (!el) return;
        var action = el.getAttribute('data-action');
        var email = el.getAttribute('data-email');
        if (action === 'disable' || action === 'enable') {
            toggleUserStatus(email, action === 'disable');
        }
    });

    renderPage();
})();

/* ── Bulk actions ── */
(function() {
    var selectAll = document.getElementById('bulk-select-all');
    var bulkBar = document.getElementById('bulk-bar');
    if (!selectAll || !bulkBar) return;

    selectAll.addEventListener('change', function() {
        var checked = this.checked;
        document.querySelectorAll('#users-table tbody input.bulk-cb').forEach(function(cb) {
            if (cb.closest('tr').style.display !== 'none') cb.checked = checked;
        });
        updateBulkBar();
    });

    document.getElementById('users-table').querySelector('tbody').addEventListener('change', function(e) {
        if (e.target.classList.contains('bulk-cb')) updateBulkBar();
    });

    function getSelected() {
        var emails = [];
        document.querySelectorAll('#users-table tbody input.bulk-cb:checked').forEach(function(cb) {
            emails.push(cb.getAttribute('data-email'));
        });
        return emails;
    }

    function updateBulkBar() {
        var sel = getSelected();
        bulkBar.style.display = sel.length > 0 ? 'flex' : 'none';
        var countEl = document.getElementById('bulk-count');
        if (countEl) countEl.textContent = sel.length;
    }

    window.bulkAction = function(action) {
        var emails = getSelected();
        if (!emails.length) return;
        var body = { emails: emails, action: action };
        if (action === 'set_tier') {
            var tier = prompt('Set tier to (community, pro, power):');
            if (!tier || !['community','pro','power'].includes(tier)) return;
            body.tier = tier;
        }
        if (!confirm('Apply "' + action + '" to ' + emails.length + ' user(s)?')) return;
        apiCall('/admin.php?ajax=bulk_action', { body: body }).then(function(data) {
            if (data.ok) {
                showToast(data.count + ' user(s) updated', 'success');
                setTimeout(function(){ location.reload(); }, 800);
            } else {
                showToast(data.error || 'Failed', 'error');
            }
        });
    };
})();

/* ── Audit log: expandable detail rows ── */
(function() {
    var auditTable = document.getElementById('audit-table');
    if (!auditTable) return;
    auditTable.querySelector('tbody').addEventListener('click', function(e) {
        var row = e.target.closest('tr');
        if (!row || row.classList.contains('audit-detail-row')) return;
        var existing = row.nextElementSibling;
        if (existing && existing.classList.contains('audit-detail-row')) {
            existing.remove();
            return;
        }
        var raw = row.getAttribute('data-details');
        if (!raw) return;
        try { var details = JSON.parse(raw); } catch(ex) { return; }
        var html = '<td colspan="6" style="padding:12px 20px;background:var(--bg-surface);border-left:3px solid var(--accent)">';
        html += '<div style="display:grid;grid-template-columns:auto 1fr;gap:4px 16px;font-size:0.85em">';
        for (var k in details) {
            if (!details.hasOwnProperty(k)) continue;
            var v = details[k];
            if (typeof v === 'object' && v !== null) v = JSON.stringify(v);
            if (typeof v === 'boolean') v = v ? 'true' : 'false';
            html += '<span style="font-weight:600;color:var(--text-dim)">' + k.replace(/_/g,' ') + '</span>';
            html += '<span>' + String(v).replace(/</g,'&lt;') + '</span>';
        }
        html += '</div></td>';
        var detailRow = document.createElement('tr');
        detailRow.className = 'audit-detail-row';
        detailRow.innerHTML = html;
        row.parentNode.insertBefore(detailRow, row.nextSibling);
    });
})();

/* ── CSV exports ── */
function exportCSV(type) {
    var params = '_csrf=' + encodeURIComponent(CSRF_TOKEN);
    if (type === 'export_audit') {
        var urlParams = new URLSearchParams(window.location.search);
        ['audit_action','audit_actor'].forEach(function(k) {
            var v = urlParams.get(k);
            if (v) params += '&' + k + '=' + encodeURIComponent(v);
        });
    }
    window.location.href = '/admin.php?ajax=' + type + '&' + params;
}

/* ── Event delegation for data-revoke-* buttons (XSS-safe) ── */
document.addEventListener('click', function(e) {
    var btn;
    /* Token revoke */
    btn = e.target.closest('[data-revoke-hash]');
    if (btn) {
        revokeToken(btn.getAttribute('data-revoke-hash'), btn.getAttribute('data-revoke-label') || '');
        return;
    }
    /* Master revoke */
    btn = e.target.closest('[data-revoke-account]');
    if (btn) {
        revokeMaster(btn.getAttribute('data-revoke-account'), btn.getAttribute('data-revoke-label') || '');
        return;
    }
});
</script>

    </main>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
