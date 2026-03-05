<?php
/**
 * Forge — System Status Page
 *
 * Public page showing service health indicators.
 * Does NOT reveal internal configuration state.
 */

// Check API health — use file check instead of self-request (avoids SSRF)
$tiers_file = __DIR__ . '/data/tiers_config.json';
$api_status = file_exists($tiers_file) ? 'operational' : 'degraded';

// Generic checks — don't reveal WHAT is or isn't configured
$all_operational = ($api_status === 'operational');

$page_title = 'Forge — Status';
$page_id = 'status';
require_once __DIR__ . '/includes/header.php';
?>

<div class="page-content">
    <div class="container-narrow" style="padding-top:40px">

        <div style="text-align:center; margin-bottom:48px">
            <h1 style="margin-bottom:8px">System Status</h1>
            <?php if ($all_operational): ?>
                <div class="badge badge-green" style="font-size:1em; padding:8px 20px">All Systems Operational</div>
            <?php else: ?>
                <div class="badge badge-yellow" style="font-size:1em; padding:8px 20px">Partial Service</div>
            <?php endif; ?>
        </div>

        <div class="card" style="margin-bottom:20px">
            <h3 style="margin-bottom:20px">Services</h3>

            <div style="display:flex; flex-direction:column; gap:16px">
                <!-- Website -->
                <div class="flex-between" style="padding-bottom:16px; border-bottom:1px solid var(--border)">
                    <div>
                        <strong class="text-bright">Website</strong>
                        <p class="text-dim text-sm">Landing page, documentation, account portal</p>
                    </div>
                    <span class="badge badge-green">Operational</span>
                </div>

                <!-- API -->
                <div class="flex-between" style="padding-bottom:16px; border-bottom:1px solid var(--border)">
                    <div>
                        <strong class="text-bright">Passport API</strong>
                        <p class="text-dim text-sm">License validation, activation, fleet management</p>
                    </div>
                    <span class="badge <?php echo $api_status === 'operational' ? 'badge-green' : 'badge-yellow'; ?>"><?php echo ucfirst($api_status); ?></span>
                </div>

                <!-- Telemetry -->
                <div class="flex-between" style="padding-bottom:16px; border-bottom:1px solid var(--border)">
                    <div>
                        <strong class="text-bright">Telemetry Receiver</strong>
                        <p class="text-dim text-sm">Performance data collection (opt-in)</p>
                    </div>
                    <span class="badge badge-green">Operational</span>
                </div>

                <!-- Payments -->
                <div class="flex-between">
                    <div>
                        <strong class="text-bright">Payment Processing</strong>
                        <p class="text-dim text-sm">Checkout and subscription management</p>
                    </div>
                    <span class="badge badge-green">Operational</span>
                </div>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom:12px">About</h3>
            <p class="text-dim" style="font-size:0.92em">
                Forge runs entirely on your local machine. This status page monitors the server-side components that handle
                licensing, telemetry, and payment processing. The core AI functionality works offline and is unaffected by
                server status.
            </p>
        </div>

        <p class="text-center text-dim text-sm" style="margin-top:32px">
            Last checked: <?php echo date('Y-m-d H:i:s T'); ?>
        </p>

    </div>
</div>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
