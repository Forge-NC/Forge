<?php
/**
 * Forge — Account / Master Dashboard
 *
 * Master self-service: view fleet, see seat usage, manage puppets.
 */
require_once __DIR__ . '/includes/auth_guard.php';

// Redirect unauthenticated to login
if (!$is_authed) {
    header('Location: login.php');
    exit;
}

// Load fleet data
$master_info = null;
$master_puppets = array();
$fleet_account = null;
$tiers = array();

$MASTERS_DIR = __DIR__ . '/data/masters';
$PUPPET_REG   = __DIR__ . '/data/puppet_registry.json';
$TIERS_FILE   = __DIR__ . '/data/tiers_config.json';

$tiers = file_exists($TIERS_FILE) ? json_decode(file_get_contents($TIERS_FILE), true) : array();
$puppet_registry = file_exists($PUPPET_REG) ? json_decode(file_get_contents($PUPPET_REG), true) : array();

// Find master account by token or owner override
if ($is_owner && isset($_GET['account_id'])) {
    $fleet_account = preg_replace('/[^a-zA-Z0-9_]/', '', $_GET['account_id']);
} elseif ($token_hash) {
    $tokens_data = file_exists(__DIR__ . '/data/tokens.json')
        ? json_decode(file_get_contents(__DIR__ . '/data/tokens.json'), true) : array();
    $tok_entry = isset($tokens_data[$token_hash]) ? $tokens_data[$token_hash] : array();
    $fleet_account = isset($tok_entry['account_id']) ? $tok_entry['account_id'] : null;
}

if ($fleet_account && is_dir($MASTERS_DIR)) {
    $mst_file = $MASTERS_DIR . '/' . $fleet_account . '.json';
    if (file_exists($mst_file)) {
        $master_info = json_decode(file_get_contents($mst_file), true);
        $master_puppets = isset($puppet_registry[$fleet_account]) ? $puppet_registry[$fleet_account] : array();
    }
}

$key_param = isset($_GET['key']) ? '?key=' . urlencode($_GET['key']) : '';

$page_title = 'Forge — Account';
$page_id = 'account';
require_once __DIR__ . '/includes/header.php';
?>

<div class="page-content">
    <div class="container-narrow">

<?php if ($is_owner && isset($_GET['account_id'])): ?>
    <div class="alert alert-info" style="margin-bottom:20px">
        Viewing master account as admin. <a href="admin.php<?php echo $key_param; ?>">Back to Admin</a>
    </div>
<?php endif; ?>

<?php if (!$master_info): ?>
    <!-- ── No Master Data ── -->
    <h1>Account</h1>
    <p class="text-dim" style="margin-bottom:32px">Signed in as <strong class="text-bright"><?php echo htmlspecialchars(isset($auth['label']) ? $auth['label'] : 'Unknown'); ?></strong> (<?php echo $auth_role; ?>)</p>

    <div class="card">
        <div class="empty-state">
            <?php if ($is_owner): ?>
                <p>You're the Origin owner. Use the <a href="admin.php<?php echo $key_param; ?>">Admin Dashboard</a> to manage masters and tokens.</p>
            <?php else: ?>
                <p style="font-size:1.1em; margin-bottom:16px">No Master license found for this token.</p>
                <p>If you've purchased a license, make sure your token is linked to your account.</p>
                <p style="margin-top:8px">Run <code>/puppet activate passport.json</code> in Forge to link your token.</p>
                <div style="margin-top:24px">
                    <a href="/Forge/#pricing" class="btn btn-primary">Purchase a License</a>
                </div>
            <?php endif; ?>
        </div>
    </div>

<?php else: ?>
    <!-- ── Master Dashboard ── -->
    <?php
        $pp = isset($master_info['passport']) ? $master_info['passport'] : array();
        $tier = isset($pp['tier']) ? $pp['tier'] : 'community';
        $tier_label = isset($tiers[$tier]['label']) ? $tiers[$tier]['label'] : ucfirst($tier);
        $tier_color = $tier === 'power' ? '#bc8cff' : ($tier === 'pro' ? '#00d4ff' : '#3fb950');
        $seats = isset($pp['seat_count']) ? (int)$pp['seat_count'] : 1;
        $puppet_limit = max(0, $seats - 1);
        $active_pups = 0;
        foreach ($master_puppets as $p) {
            if (isset($p['status']) && $p['status'] === 'active') $active_pups++;
        }
        $seat_pct = $puppet_limit > 0 ? round(($active_pups / $puppet_limit) * 100) : 0;
        $seat_color = $seat_pct >= 90 ? 'var(--yellow)' : ($seat_pct >= 70 ? 'var(--blue)' : 'var(--green)');
        $activated = !empty($master_info['activated']);
        $activated_at = isset($master_info['activated_at']) ? $master_info['activated_at'] : '';
    ?>

    <div class="flex-between" style="margin-bottom:32px; flex-wrap:wrap; gap:12px">
        <div>
            <h1 style="margin-bottom:4px">Master Dashboard</h1>
            <p class="text-dim">
                <?php echo htmlspecialchars(isset($pp['customer_label']) ? $pp['customer_label'] : 'Master'); ?>
                &mdash;
                <span style="color:<?php echo $tier_color; ?>; font-weight:600"><?php echo htmlspecialchars($tier_label); ?></span> tier
            </p>
        </div>
        <div class="flex gap-sm">
            <a href="analytics.php<?php echo $key_param; ?>" class="btn btn-secondary btn-sm">Analytics</a>
            <?php if ($fleet_account): ?>
            <a href="passport_download.php?id=<?php echo urlencode($fleet_account); ?>&key=<?php echo urlencode(isset($_GET['key']) ? $_GET['key'] : ''); ?>" class="btn btn-secondary btn-sm">Download Passport</a>
            <?php endif; ?>
        </div>
    </div>

    <!-- Status Cards -->
    <div class="grid-4" style="margin-bottom:24px">
        <div class="stat-card">
            <span class="stat-icon">&#128273;</span>
            <span class="stat-value" style="font-size:1em; color:<?php echo $activated ? 'var(--green)' : 'var(--yellow)'; ?>">
                <?php echo $activated ? 'Active' : 'Pending'; ?>
            </span>
            <span class="stat-label">License Status</span>
        </div>
        <div class="stat-card">
            <span class="stat-icon" style="color:<?php echo $tier_color; ?>">&#9733;</span>
            <span class="stat-value" style="font-size:1em; color:<?php echo $tier_color; ?>"><?php echo htmlspecialchars($tier_label); ?></span>
            <span class="stat-label">Tier</span>
        </div>
        <div class="stat-card">
            <span class="stat-icon">&#128187;</span>
            <span class="stat-value" style="font-size:1em"><?php echo $active_pups; ?> / <?php echo $puppet_limit; ?></span>
            <span class="stat-label">Puppet Seats</span>
        </div>
        <div class="stat-card">
            <span class="stat-icon">&#128202;</span>
            <span class="stat-value" style="font-size:1em"><?php echo $seats; ?></span>
            <span class="stat-label">Total Seats</span>
        </div>
    </div>

    <!-- Seat Utilization -->
    <div class="card" style="margin-bottom:20px">
        <div class="flex-between" style="margin-bottom:12px">
            <h3 style="margin:0">Seat Utilization</h3>
            <span style="color:<?php echo $seat_color; ?>; font-weight:700"><?php echo $seat_pct; ?>%</span>
        </div>
        <div class="flex-between text-sm text-dim" style="margin-bottom:6px">
            <span><?php echo $active_pups; ?> of <?php echo $puppet_limit; ?> puppet seats used</span>
            <span><?php echo max(0, $puppet_limit - $active_pups); ?> available</span>
        </div>
        <div class="progress-bg">
            <div class="progress-fill" style="width:<?php echo min(100, $seat_pct); ?>%; background:<?php echo $seat_color; ?>"></div>
        </div>
    </div>

    <!-- License Details -->
    <div class="card" style="margin-bottom:20px">
        <h3 style="margin-bottom:16px">License Details</h3>
        <div class="info-grid">
            <span class="info-label">Account ID</span>
            <span class="info-value text-mono text-sm"><?php echo htmlspecialchars(isset($pp['account_id']) ? $pp['account_id'] : ''); ?></span>

            <span class="info-label">Passport ID</span>
            <span class="info-value text-mono text-sm"><?php echo htmlspecialchars(isset($pp['passport_id']) ? substr($pp['passport_id'], 0, 20) . '...' : ''); ?></span>

            <span class="info-label">Email</span>
            <span class="info-value"><?php echo htmlspecialchars(isset($pp['email']) ? $pp['email'] : 'Not set'); ?></span>

            <?php if ($activated_at): ?>
            <span class="info-label">Activated</span>
            <span class="info-value"><?php echo htmlspecialchars($activated_at); ?></span>
            <?php endif; ?>

            <span class="info-label">Issued</span>
            <span class="info-value"><?php echo htmlspecialchars(isset($pp['issued_date']) ? $pp['issued_date'] : 'Unknown'); ?></span>
        </div>
    </div>

    <!-- Puppets Table -->
    <div class="card" style="margin-bottom:20px">
        <div class="flex-between" style="margin-bottom:16px">
            <h3 style="margin:0">Fleet &mdash; Puppets</h3>
            <span class="badge badge-blue"><?php echo count($master_puppets); ?> registered</span>
        </div>

        <?php if (empty($master_puppets)): ?>
            <div class="empty-state">
                <p style="margin-bottom:8px">No puppets registered yet.</p>
                <p class="text-sm">In Forge, run <code>/puppet generate MyDevice</code> to create a puppet passport.</p>
            </div>
        <?php else: ?>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Machine ID</th>
                            <th>Seat</th>
                            <th>Status</th>
                            <th>Last Seen</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($master_puppets as $pup):
                            $ps = isset($pup['status']) ? $pup['status'] : 'unknown';
                            $pb = $ps === 'active' ? 'badge-green' : ($ps === 'revoked' ? 'badge-red' : 'badge-yellow');
                        ?>
                        <tr>
                            <td><?php echo htmlspecialchars(isset($pup['name']) ? $pup['name'] : (isset($pup['puppet_name']) ? $pup['puppet_name'] : '—')); ?></td>
                            <td class="mono text-sm"><?php echo htmlspecialchars(isset($pup['puppet_mid']) ? substr($pup['puppet_mid'], 0, 12) . '...' : '—'); ?></td>
                            <td><?php echo htmlspecialchars(isset($pup['seat_id']) ? $pup['seat_id'] : '—'); ?></td>
                            <td><span class="badge <?php echo $pb; ?>"><?php echo ucfirst($ps); ?></span></td>
                            <td class="text-dim"><?php echo isset($pup['last_seen']) ? htmlspecialchars($pup['last_seen']) : '—'; ?></td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>

    <!-- Quick Links -->
    <div class="card">
        <h3 style="margin-bottom:16px">Quick Links</h3>
        <div class="flex flex-wrap gap-sm">
            <a href="analytics.php<?php echo $key_param; ?>" class="btn btn-secondary btn-sm">Analytics Dashboard</a>
            <a href="docs.php#puppets" class="btn btn-secondary btn-sm">Fleet Docs</a>
            <a href="docs.php#config" class="btn btn-secondary btn-sm">Configuration</a>
            <a href="docs.php#commands" class="btn btn-secondary btn-sm">Commands Reference</a>
        </div>
    </div>

<?php endif; ?>

    </div>
</div>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
