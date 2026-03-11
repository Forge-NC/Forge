<?php
/**
 * Forge — Shared Header
 *
 * Sets: $page_title, $page_id (required before including)
 * Optional: $hide_nav (bool), $auth (array from validate_auth)
 */
if (!isset($page_title)) $page_title = 'Forge';
if (!isset($page_id)) $page_id = '';
if (!isset($hide_nav)) $hide_nav = false;

// Auth state for nav (optional — pages that need auth include auth_guard.php before this)
$_nav_authed = isset($auth) && !empty($auth['valid']);
$_nav_role = isset($auth['role']) ? $auth['role'] : '';
$_nav_is_owner = ($_nav_role === 'owner');
$_nav_is_master = ($_nav_role === 'captain' || $_nav_role === 'master');
$_nav_key_param = isset($_GET['key']) ? '?key=' . urlencode($_GET['key']) : '';
?><!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?php echo htmlspecialchars($page_title); ?></title>
    <meta name="description" content="Forge is a local AI coding assistant. No cloud. No subscriptions. Your code stays yours.">
    <link rel="stylesheet" href="assets/style.css?v=<?php echo filemtime(__DIR__ . '/../assets/style.css'); ?>">
</head>
<body>

<?php if (!$hide_nav): ?>
<nav class="nav">
    <div class="nav-inner">
        <a href="/Forge/" class="nav-brand">Forge <span class="version">v1.0</span></a>
        <button class="nav-hamburger" aria-label="Menu">&#9776;</button>
        <div class="nav-links">
            <a href="/Forge/"<?php echo $page_id === 'home' ? ' class="active"' : ''; ?>>Home</a>
            <a href="docs.php"<?php echo $page_id === 'docs' ? ' class="active"' : ''; ?>>Docs</a>
            <a href="matrix.php"<?php echo $page_id === 'matrix' ? ' class="active"' : ''; ?>>Matrix</a>
            <a href="scoreboard.php"<?php echo $page_id === 'scoreboard' ? ' class="active"' : ''; ?>>Scoreboard</a>
            <a href="status.php"<?php echo $page_id === 'status' ? ' class="active"' : ''; ?>>Status</a>
            <a href="support.php"<?php echo $page_id === 'support' ? ' class="active"' : ''; ?>>Support</a>
            <?php if ($_nav_is_owner): ?>
                <a href="admin.php<?php echo $_nav_key_param; ?>"<?php echo $page_id === 'admin' ? ' class="active"' : ''; ?>>Admin</a>
            <?php endif; ?>
            <?php if ($_nav_authed): ?>
                <a href="account.php<?php echo $_nav_key_param; ?>"<?php echo $page_id === 'account' ? ' class="active"' : ''; ?>>Account</a>
            <?php else: ?>
                <a href="login.php"<?php echo $page_id === 'login' ? ' class="active"' : ''; ?>>Sign In</a>
            <?php endif; ?>
            <a href="/Forge/#pricing" class="nav-cta">Get Forge</a>
        </div>
    </div>
</nav>
<?php endif; ?>
