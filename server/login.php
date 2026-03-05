<?php
/**
 * Forge — Login Page
 *
 * Dedicated authentication page. Validates token and redirects
 * to admin.php (owner) or account.php (master/other).
 */
require_once __DIR__ . '/includes/auth_guard.php';

// If already authenticated, redirect
if ($is_authed) {
    $key_param = isset($_GET['key']) ? '?key=' . urlencode($_GET['key']) : '';
    if ($is_owner) {
        header('Location: admin.php' . $key_param);
    } else {
        header('Location: account.php' . $key_param);
    }
    exit;
}

// Check for login error
$login_error = '';
$attempted_key = isset($_GET['key']) && $_GET['key'] !== '';
if ($attempted_key) {
    $login_error = isset($auth['error']) ? $auth['error'] : 'Invalid token';
}

$page_title = 'Forge — Sign In';
$page_id = 'login';
require_once __DIR__ . '/includes/header.php';
?>

<div class="page-content">
    <div class="container" style="max-width:500px">

        <div class="login-box" style="margin-top:40px">
            <h2>Sign In</h2>
            <p class="subtitle">Enter your Forge token to access your account.</p>

            <?php if ($login_error): ?>
            <div class="alert alert-error" style="margin-bottom:20px">
                <?php echo htmlspecialchars($login_error); ?>
            </div>
            <?php endif; ?>

            <form method="get" action="login.php" id="login-form">
                <div class="form-group">
                    <input type="text" name="key" id="login-key" class="form-input form-input-mono" placeholder="fg_tok_... or fg_cap_..." autocomplete="off" autofocus>
                </div>
                <div class="form-group" style="margin-top:12px">
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:0.9em;color:var(--text-dim)">
                        <input type="checkbox" id="remember-me" checked>
                        Remember me on this browser
                    </label>
                </div>
                <button type="submit" class="btn btn-primary btn-block">Sign In</button>
            </form>

            <script>
            (function() {
                var saved = localStorage.getItem('forge_auth_token');
                var input = document.getElementById('login-key');
                var checkbox = document.getElementById('remember-me');

                // Auto-fill saved token
                if (saved && !input.value) {
                    input.value = saved;
                    // Auto-submit if no error on this page
                    <?php if (!$attempted_key): ?>
                    document.getElementById('login-form').submit();
                    <?php endif; ?>
                }

                // Save token on submit if "remember me" is checked
                document.getElementById('login-form').addEventListener('submit', function() {
                    if (checkbox.checked && input.value) {
                        localStorage.setItem('forge_auth_token', input.value);
                    } else {
                        localStorage.removeItem('forge_auth_token');
                    }
                });
            })();
            </script>
        </div>

        <div class="card" style="margin-top:24px">
            <h3 style="margin-bottom:12px">Where to find your token</h3>
            <div style="color:var(--text-dim); font-size:0.92em">
                <p style="margin-bottom:12px">Your token is generated when you activate your Master passport in Forge.</p>
                <p style="margin-bottom:8px"><strong style="color:var(--text-bright)">After activation:</strong></p>
                <p style="margin-bottom:12px">Check your Forge config file:</p>
                <div class="code-block">
                    <button class="copy-btn">Copy</button>
<pre><code># Windows
C:\Users\YOU\.forge\config.yaml

# Linux/Mac
~/.forge/config.yaml</code></pre>
                </div>
                <p>Look for the <code>telemetry_token</code> field. That's your login token.</p>
            </div>
        </div>

        <div style="text-align:center; margin-top:32px">
            <p class="text-dim">Don't have a license yet?</p>
            <a href="/Forge/#pricing" class="text-accent" style="font-weight:600">Get Forge</a>
        </div>

    </div>
</div>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
