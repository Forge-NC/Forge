<?php
/**
 * Forge — Auth Guard
 *
 * Include this in pages that need authentication context.
 * Sets: $auth, $is_authed, $is_owner, $is_master, $auth_role, $token_hash
 * Does NOT block unauthenticated users — pages decide that themselves.
 *
 * If no ?key= in URL, emits a small JS snippet that checks localStorage
 * for a saved token and redirects with it appended.
 */
require_once __DIR__ . '/../auth.php';

$auth = validate_auth();
$is_authed = !empty($auth['valid']);
$auth_role = isset($auth['role']) ? $auth['role'] : 'tester';
$is_owner = ($auth_role === 'owner');
$is_master = ($auth_role === 'captain' || $auth_role === 'master');
$token_hash = isset($auth['token_hash']) ? $auth['token_hash'] : '';

// If not authenticated and no ?key= param, emit JS to try localStorage auto-login.
// This runs before any HTML output from the including page.
if (!$is_authed && !isset($_GET['key'])) {
    echo '<script>'
       . 'var t=localStorage.getItem("forge_auth_token");'
       . 'if(t){var u=new URL(window.location.href);u.searchParams.set("key",t);window.location.replace(u.toString());}'
       . '</script>';
}
