<?php
/**
 * Forge — Admin Dashboard (Owner Only)
 *
 * Master management, token management, revenue overview,
 * webhook log viewer, and system health.
 */
require_once __DIR__ . '/includes/auth_guard.php';

// Owner only
if (!$is_authed || !$is_owner) {
    header('Location: login.php');
    exit;
}

$key_param = isset($_GET['key']) ? '?key=' . urlencode($_GET['key']) : '';
$raw_key = isset($_GET['key']) ? $_GET['key'] : '';

// ── Load all data server-side ──
$MASTERS_DIR  = __DIR__ . '/data/masters';
$PUPPET_REG    = __DIR__ . '/data/puppet_registry.json';
$TIERS_FILE    = __DIR__ . '/data/tiers_config.json';
$REVOC_FILE    = __DIR__ . '/data/revocations.json';
$TOKENS_FILE   = __DIR__ . '/data/tokens.json';
$WEBHOOK_LOG   = __DIR__ . '/data/webhook_log.jsonl';

$tiers_config = file_exists($TIERS_FILE) ? json_decode(file_get_contents($TIERS_FILE), true) : array();
$puppet_registry = file_exists($PUPPET_REG) ? json_decode(file_get_contents($PUPPET_REG), true) : array();
$revocations = file_exists($REVOC_FILE) ? json_decode(file_get_contents($REVOC_FILE), true) : array();
$tokens_data = file_exists($TOKENS_FILE) ? json_decode(file_get_contents($TOKENS_FILE), true) : array();

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
$tier_breakdown = array();
foreach ($masters as $m) {
    if ($m['activated'] && !$m['revoked']) $active_masters++;
    $total_seats += $m['seats'];
    $total_puppets += $m['puppets_active'];
    $t = $m['tier'];
    if (!isset($tier_breakdown[$t])) {
        $tier_breakdown[$t] = array('count' => 0, 'revenue' => 0, 'seats' => 0);
    }
    $tier_breakdown[$t]['count']++;
    $tier_breakdown[$t]['seats'] += $m['seats'];
    $price = isset($tiers_config[$t]['price_cents']) ? (int)$tiers_config[$t]['price_cents'] : 0;
    $tier_breakdown[$t]['revenue'] += $price;
    $total_revenue += $price;
}

// Load tokens
$token_list = array();
foreach ($tokens_data as $hash => $entry) {
    $role = isset($entry['role']) ? $entry['role'] : 'tester';
    if ($role === 'tester' && isset($entry['label']) && strpos($entry['label'], 'admin') !== false) {
        $role = 'admin';
    }
    $token_list[] = array(
        'hash' => $hash,
        'hash_prefix' => substr($hash, 0, 12) . '...',
        'label' => isset($entry['label']) ? $entry['label'] : 'unknown',
        'role' => $role,
        'created' => isset($entry['created']) ? $entry['created'] : '',
        'revoked' => !empty($entry['revoked']),
        'account_id' => isset($entry['account_id']) ? $entry['account_id'] : '',
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
if (is_dir($profile_dir)) {
    $pg = glob($profile_dir . '/*.json');
    $profile_count = is_array($pg) ? count($pg) : 0;
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
$valid_views = array('overview', 'masters', 'tokens', 'revenue', 'webhooks', 'system', 'site');
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

$page_title = 'Forge — Admin';
$page_id = 'admin';
require_once __DIR__ . '/includes/header.php';
?>

<div class="sidebar-layout">
    <div class="sidebar admin-sidebar">
        <h4>Admin</h4>
        <a href="admin.php<?php echo $key_param; ?>&view=overview"<?php echo $active_view === 'overview' ? ' class="active"' : ''; ?>>&#9632; Overview</a>
        <a href="admin.php<?php echo $key_param; ?>&view=masters"<?php echo $active_view === 'masters' ? ' class="active"' : ''; ?>>&#9733; Masters</a>
        <a href="admin.php<?php echo $key_param; ?>&view=tokens"<?php echo $active_view === 'tokens' ? ' class="active"' : ''; ?>>&#128273; Tokens</a>
        <a href="admin.php<?php echo $key_param; ?>&view=revenue"<?php echo $active_view === 'revenue' ? ' class="active"' : ''; ?>>&#128176; Revenue</a>
        <a href="admin.php<?php echo $key_param; ?>&view=webhooks"<?php echo $active_view === 'webhooks' ? ' class="active"' : ''; ?>>&#128232; Webhooks</a>
        <a href="admin.php<?php echo $key_param; ?>&view=system"<?php echo $active_view === 'system' ? ' class="active"' : ''; ?>>&#9881; System</a>
        <a href="admin.php<?php echo $key_param; ?>&view=site"<?php echo $active_view === 'site' ? ' class="active"' : ''; ?>>&#128202; Site Analytics</a>

        <h4>Quick Links</h4>
        <a href="analytics.php<?php echo $key_param; ?>">Analytics Dashboard</a>
        <a href="/Forge/">View Website</a>
    </div>
    <div class="sidebar-offset" style="width:220px"></div>

    <div class="sidebar-content" style="max-width:none; padding:32px">

<?php if ($active_view === 'overview'): ?>
        <!-- ══════════════ OVERVIEW ══════════════ -->
        <h2 style="margin-bottom:24px">Overview</h2>

        <div class="grid-4" style="margin-bottom:32px">
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_masters; ?></span>
                <span class="stat-label">Total Masters</span>
            </div>
            <div class="stat-card">
                <span class="stat-value text-green">$<?php echo number_format($total_revenue / 100, 0); ?></span>
                <span class="stat-label">Total Revenue</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_seats; ?></span>
                <span class="stat-label">Total Seats Sold</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_puppets; ?></span>
                <span class="stat-label">Active Puppets</span>
            </div>
        </div>

        <!-- Quick Actions -->
        <div class="card" style="margin-bottom:24px">
            <h3 style="margin-bottom:16px">Quick Actions</h3>
            <div class="flex flex-wrap gap-sm">
                <button class="btn btn-primary btn-sm" onclick="openModal('modal-generate')">Generate Master Passport</button>
                <a href="admin.php<?php echo $key_param; ?>&view=tokens" class="btn btn-secondary btn-sm">Manage Tokens</a>
                <a href="analytics.php<?php echo $key_param; ?>&view=fleet_admin" class="btn btn-secondary btn-sm">Fleet Analytics</a>
            </div>
        </div>

        <!-- Recent Masters -->
        <div class="card" style="margin-bottom:24px">
            <div class="flex-between" style="margin-bottom:16px">
                <h3 style="margin:0">Recent Masters</h3>
                <a href="admin.php<?php echo $key_param; ?>&view=masters" class="text-sm">View all &rarr;</a>
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
                            $tc = $m['tier'] === 'power' ? 'var(--purple)' : ($m['tier'] === 'pro' ? 'var(--accent)' : 'var(--green)');
                            $status = $m['revoked'] ? 'Revoked' : ($m['activated'] ? 'Active' : 'Pending');
                            $sb = $m['revoked'] ? 'badge-red' : ($m['activated'] ? 'badge-green' : 'badge-yellow');
                        ?>
                        <tr>
                            <td><?php echo htmlspecialchars($m['label']); ?></td>
                            <td style="color:<?php echo $tc; ?>"><?php echo ucfirst($m['tier']); ?></td>
                            <td><?php echo $m['puppets_active']; ?>/<?php echo max(0, $m['seats'] - 1); ?></td>
                            <td><span class="badge <?php echo $sb; ?>"><?php echo $status; ?></span></td>
                            <td class="text-dim text-sm"><?php echo $m['issued'] ? htmlspecialchars(substr($m['issued'], 0, 10)) : '—'; ?></td>
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
                <a href="admin.php<?php echo $key_param; ?>&view=webhooks" class="text-sm">View all &rarr;</a>
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
                        <td><?php echo $m['seats']; ?></td>
                        <td><?php echo $m['puppets_active']; ?>/<?php echo max(0, $m['seats'] - 1); ?></td>
                        <td><span class="badge <?php echo $sb; ?>"><?php echo $status; ?></span></td>
                        <td class="text-dim text-sm"><?php echo $m['last_seen'] ? htmlspecialchars(substr($m['last_seen'], 0, 10)) : '—'; ?></td>
                        <td>
                            <div class="dropdown">
                                <button class="btn btn-ghost btn-sm dropdown-toggle">&#8943;</button>
                                <div class="dropdown-menu">
                                    <a href="account.php<?php echo $key_param; ?>&account_id=<?php echo urlencode($m['account_id']); ?>" class="dropdown-item">View Account</a>
                                    <a href="analytics.php<?php echo $key_param; ?>&view=my_fleet&account_id=<?php echo urlencode($m['account_id']); ?>" class="dropdown-item">View Fleet</a>
                                    <?php if (!$m['revoked']): ?>
                                    <div class="dropdown-divider"></div>
                                    <button class="dropdown-item danger" onclick="revokeMaster('<?php echo htmlspecialchars($m['account_id']); ?>', '<?php echo htmlspecialchars(addslashes($m['label'])); ?>')">Revoke</button>
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
        <div class="flex-between" style="margin-bottom:24px; flex-wrap:wrap; gap:12px">
            <h2 style="margin:0">Tokens (<?php echo count($token_list); ?>)</h2>
            <div class="flex gap-sm">
                <input type="text" class="form-input" style="width:200px" placeholder="Search tokens..." data-filter-target="tokens-table">
                <button class="btn btn-primary btn-sm" onclick="openModal('modal-token')">Register Token</button>
            </div>
        </div>

        <div class="table-wrap">
            <table id="tokens-table">
                <thead><tr><th>Label</th><th>Role</th><th>Created</th><th>Status</th><th>Hash</th><th>Actions</th></tr></thead>
                <tbody>
                <?php foreach ($token_list as $tok):
                    $rb = $tok['role'] === 'owner' ? 'badge-purple' : ($tok['role'] === 'admin' ? 'badge-blue' : (in_array($tok['role'], ['captain','master']) ? 'badge-green' : 'badge-yellow'));
                ?>
                <tr>
                    <td class="font-bold"><?php echo htmlspecialchars($tok['label']); ?></td>
                    <td><span class="badge <?php echo $rb; ?>"><?php echo ucfirst($tok['role']); ?></span></td>
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
                        <button class="btn btn-ghost btn-sm text-red" onclick="revokeToken('<?php echo htmlspecialchars($tok['hash']); ?>', '<?php echo htmlspecialchars(addslashes($tok['label'])); ?>')">Revoke</button>
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

        <div class="grid-3" style="margin-bottom:32px">
            <div class="stat-card">
                <span class="stat-value text-green">$<?php echo number_format($total_revenue / 100, 0); ?></span>
                <span class="stat-label">Total Revenue</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_masters; ?></span>
                <span class="stat-label">Total Customers</span>
            </div>
            <div class="stat-card">
                <span class="stat-value"><?php echo $total_masters > 0 ? '$' . number_format(($total_revenue / 100) / $total_masters, 0) : '$0'; ?></span>
                <span class="stat-label">Avg Revenue / Customer</span>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom:16px">Revenue by Tier</h3>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Tier</th><th>Price</th><th>Customers</th><th>Revenue</th><th>Seats Sold</th></tr></thead>
                    <tbody>
                    <?php foreach ($tier_breakdown as $tid => $tb):
                        $tc = $tid === 'power' ? 'var(--purple)' : ($tid === 'pro' ? 'var(--accent)' : 'var(--green)');
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

<?php elseif ($active_view === 'webhooks'): ?>
        <!-- ══════════════ WEBHOOKS ══════════════ -->
        <h2 style="margin-bottom:24px">Webhook Log (Last 50)</h2>

        <?php if (empty($webhook_entries)): ?>
            <div class="card"><div class="empty-state"><p>No webhook events recorded yet.</p></div></div>
        <?php else: ?>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Timestamp</th><th>Event</th><th>Details</th></tr></thead>
                    <tbody>
                    <?php foreach ($webhook_entries as $wh):
                        $evt = isset($wh['event']) ? $wh['event'] : 'unknown';
                        $ec = ($evt === 'master_created' || $evt === 'checkout.session.completed') ? 'text-green'
                            : ($evt === 'error' || $evt === 'signature_failed' ? 'text-red' : '');
                    ?>
                    <tr>
                        <td class="text-dim text-sm nowrap"><?php echo isset($wh['timestamp']) ? htmlspecialchars($wh['timestamp']) : '—'; ?></td>
                        <td><span class="font-bold <?php echo $ec; ?>"><?php echo htmlspecialchars($evt); ?></span></td>
                        <td class="text-sm text-dim"><?php
                            $d = $wh;
                            unset($d['timestamp'], $d['event']);
                            echo htmlspecialchars(json_encode($d, JSON_UNESCAPED_SLASHES));
                        ?></td>
                    </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
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
                        <tr><td>Auth Tokens</td><td class="font-bold"><?php echo count($token_list); ?></td><td class="text-dim text-sm">data/tokens.json</td></tr>
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
                <a href="admin.php<?php echo $key_param; ?>&view=site&range=<?php echo $rv; ?>"
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
                    <?php foreach ($tiers_config as $tid => $tc): ?>
                    <option value="<?php echo htmlspecialchars($tid); ?>"><?php echo htmlspecialchars($tc['label']); ?> (<?php echo isset($tc['price_display']) ? $tc['price_display'] : 'Free'; ?>, <?php echo $tc['seats']; ?> seats)</option>
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
            <h3>Register New Token</h3>
            <button class="modal-close" onclick="closeModal('modal-token')">&times;</button>
        </div>
        <form id="form-token" onsubmit="return handleRegisterToken(event)">
            <div class="form-group">
                <label class="form-label">Label</label>
                <input type="text" class="form-input" name="label" placeholder="tester-alice" required pattern="[a-zA-Z0-9_-]+">
                <span class="form-hint">Alphanumeric, dashes, underscores only</span>
            </div>
            <div class="form-group">
                <label class="form-label">Token (plaintext)</label>
                <input type="text" class="form-input form-input-mono" name="token" placeholder="Will be SHA-512 hashed" required>
                <span class="form-hint">This will be hashed before storage. Give the plaintext to the user.</span>
            </div>
            <div class="form-group">
                <label class="form-label">Role</label>
                <select class="form-select" name="role">
                    <option value="tester">Tester</option>
                    <option value="admin">Admin</option>
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
var AUTH_KEY = <?php echo json_encode($raw_key); ?>;
var KEY_PARAM = <?php echo json_encode($key_param); ?>;

function apiCall(url, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json' };
    if (AUTH_KEY) headers['X-Forge-Token'] = AUTH_KEY;
    var fetchOpts = { method: opts.method || 'POST', headers: headers };
    if (opts.body) fetchOpts.body = JSON.stringify(opts.body);
    return fetch(url, fetchOpts).then(function(r) { return r.json(); });
}

function handleGenerate(e) {
    e.preventDefault();
    var f = e.target;
    apiCall('passport_api.php?action=generate_master', {
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
    // Hash the token client-side with SHA-512
    var token = f.token.value;
    crypto.subtle.digest('SHA-512', new TextEncoder().encode(token)).then(function(buf) {
        var hash = Array.from(new Uint8Array(buf)).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
        return apiCall('token_admin.php', {
            body: { action: 'register', token_hash: hash, label: f.label.value, role: f.role.value }
        });
    }).then(function(data) {
        if (data.status === 'ok') {
            showToast('Token registered: ' + data.label, 'success');
            closeModal('modal-token');
            setTimeout(function() { location.reload(); }, 1000);
        } else {
            showToast(data.error || 'Failed', 'error');
        }
    }).catch(function(err) { showToast(err.message || 'Error', 'error'); });
    return false;
}

function revokeToken(hash, label) {
    if (!confirm('Revoke token "' + label + '"? This cannot be undone.')) return;
    apiCall('token_admin.php', { body: { action: 'revoke', token_hash: hash } })
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
    apiCall('passport_api.php?action=revoke', { body: { account_id: accountId } })
    .then(function(data) {
        if (data.ok) {
            showToast('Master revoked. ' + (data.puppets_revoked || 0) + ' puppets invalidated.', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(data.error || 'Failed', 'error');
        }
    });
}
</script>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
