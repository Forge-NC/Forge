<?php
/**
 * Forge — Landing Page
 *
 * Public product page with Neural Cortex hero, feature showcase, terminal demo,
 * 9-layer security breakdown, interactive brain demo, pricing, FAQ, and CTA.
 */

$tiers_file = __DIR__ . '/data/tiers_config.json';
$tiers = file_exists($tiers_file) ? json_decode(file_get_contents($tiers_file), true) : array();

$tier_order = array('community', 'pro', 'power');
$tier_icons = array('community' => '&#9881;', 'pro' => '&#9889;', 'power' => '&#9733;');
$tier_colors = array('community' => '#3fb950', 'pro' => '#00d4ff', 'power' => '#bc8cff');
$tier_descriptions = array(
    'community' => 'For developers who want to explore local AI on their own terms.',
    'pro'       => 'For professionals and power users who demand the full arsenal.',
    'power'     => 'For teams and organizations that need fleet control and enterprise compliance.'
);

$page_title = 'Forge — Local AI Coding Assistant';
$page_id = 'home';
require_once __DIR__ . '/includes/header.php';
?>

<!-- ── Hero with Neural Cortex ── -->
<section class="hero">
    <div class="container" style="position:relative; z-index:1">
        <div class="cortex-hero">
            <div class="hero-text">
                <span class="badge-label">100% Local AI</span>
                <h1>Your Code. <span class="text-gradient">Your AI.</span><br>Your Machine.</h1>
                <p class="tagline">
                    Forge is a local AI coding assistant that runs entirely on your hardware.
                    No cloud APIs. No subscriptions required. No data leaves your machine.<sup style="font-size:0.6em;opacity:0.6">*</sup>
                </p>
                <div class="hero-buttons">
                    <a href="#pricing" class="btn btn-primary btn-lg">Get Started</a>
                    <a href="docs.php" class="btn btn-secondary btn-lg">Read the Docs</a>
                </div>

                <div class="hero-stats stagger">
                    <div class="hero-stat">
                        <span class="num" data-count="54207" data-suffix="+">0</span>
                        <span class="label">Lines of Source</span>
                    </div>
                    <div class="hero-stat">
                        <span class="num" data-count="1318">0</span>
                        <span class="label">Tests Passing</span>
                    </div>
                    <div class="hero-stat">
                        <span class="num" data-count="59">0</span>
                        <span class="label">Commands</span>
                    </div>
                    <div class="hero-stat">
                        <span class="num" data-count="14">0</span>
                        <span class="label">Themes</span>
                    </div>
                </div>
            </div>
            <div class="cortex-wrap">
                <div class="cortex-canvas-wrap">
                    <canvas id="hero-cortex" style="border-radius:50%"></canvas>
                </div>
                <span class="cortex-state-label" id="hero-state-label">booting</span>
            </div>
        </div>
    </div>
</section>

<!-- ── Why Local? Manifesto ── -->
<section class="section" style="padding-bottom:24px">
    <div class="container">
        <div class="manifesto animate-on-scroll">
            <div class="manifesto-col">
                <div class="manifesto-q">Who sees your code?</div>
                <p class="manifesto-a">With cloud AI, every line you write passes through someone else's servers. Their logs. Their retention policies. Their breach surface. With Forge: <strong style="color:var(--accent)">nobody</strong>. Your code never leaves your machine.</p>
            </div>
            <div class="manifesto-col">
                <div class="manifesto-q">What happens when the API goes down?</div>
                <p class="manifesto-a">Cloud tools stop working. Your entire workflow halts. Rate limits hit at 2 AM. With Forge: <strong style="color:var(--accent)">nothing changes</strong>. It runs on your GPU. No internet required. No outages.</p>
            </div>
            <div class="manifesto-col">
                <div class="manifesto-q">How much will it cost next year?</div>
                <p class="manifesto-a">Cloud subscriptions increase. Always. Per-seat, per-token, per-feature. Forge offers a <strong style="color:var(--accent)">one-time purchase</strong>. Every token after that is free. The math only gets better over time.</p>
            </div>
        </div>
        <p class="manifesto-tagline">These aren't hypotheticals. They're why Forge exists.</p>
        <p style="font-size:0.72rem;opacity:0.45;margin-top:8px;text-align:center"><sup>*</sup> With local AI via Ollama (default). Optional integrations with OpenAI or Anthropic use your own API key and are subject to their privacy policies.</p>
    </div>
</section>

<!-- ── Terminal Demo ── -->
<section class="section">
    <div class="container-narrow">
        <div class="effects-container" data-effects="particles edge-glow" style="border-radius:var(--radius-xl)">
            <div class="terminal" style="max-width:720px; margin:0 auto">
                <div class="terminal-bar">
                    <div class="terminal-dot terminal-dot-r"></div>
                    <div class="terminal-dot terminal-dot-y"></div>
                    <div class="terminal-dot terminal-dot-g"></div>
                    <span class="terminal-title">forge terminal</span>
                </div>
                <div class="terminal-body" data-demo='[
                    "<span class=\"prompt\">forge&gt;<\/span> <span class=\"cmd\">Add input validation to the signup form<\/span>\n<span class=\"dim\">[routing] qwen2.5-coder:14b \u2022 quality-aware \u2022 38.2 tok/s<\/span>\n<span class=\"dim\">[crucible] scan clean \u2022 9 security layers passed<\/span>\n<span class=\"dim\">[plan] 3 files identified \u2022 verified against spec<\/span>\n<span class=\"out\">Created validators in auth/validate.py<\/span>\n<span class=\"out\">Updated signup_form.py with field validation<\/span>\n<span class=\"out\">Added 12 test cases to test_signup.py<\/span>\n<span class=\"dim\">[continuity: A] [reliability: 94.2] [billing: $0.00]<\/span>",
                    "<span class=\"prompt\">forge&gt;<\/span> <span class=\"cmd\">/puppet generate DevBox<\/span>\n<span class=\"out\">Puppet passport created: forge_puppet_DevBox.json<\/span>\n<span class=\"out\">Seats: 2/3 used. 1 remaining.<\/span>\n\n<span class=\"prompt\">forge&gt;<\/span> <span class=\"cmd\">/puppet status<\/span>\n<span class=\"out\">Role: Master \u2022 Tier: Pro \u2022 Seats: 2/3<\/span>\n<span class=\"out\">Puppets: DevBox (active), WorkLaptop (active)<\/span>\n<span class=\"dim\">[fleet sync: OK] [genome: 847 patterns]<\/span>",
                    "<span class=\"prompt\">forge&gt;<\/span> <span class=\"cmd\">Fix the race condition in the connection pool<\/span>\n<span class=\"dim\">[routing] qwen2.5-coder:14b \u2022 complexity: high \u2022 AMI tier 1<\/span>\n<span class=\"dim\">[context] 4 files pinned \u2022 2,847 tokens<\/span>\n<span class=\"dim\">[plan] Lock ordering issue in pool.py:142<\/span>\n<span class=\"out\">Replaced threading.Lock with RLock in ConnectionPool<\/span>\n<span class=\"out\">Added acquire timeout (30s default)<\/span>\n<span class=\"out\">Tests: 8 passed, 0 failed<\/span>\n<span class=\"dim\">[continuity: A] [reliability: 96.1] [billing: $0.00]<\/span>"
                ]'>
                    <span class="dim">Loading demo...</span>
                </div>
            </div>
        </div>
    </div>
</section>

<!-- ── What Is Forge? (Plain English) ── -->
<section class="section" id="features">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">What Is Forge?</span>
            <h2>An AI That Lives On Your Machine</h2>
            <p>Forge is a coding assistant that runs AI models directly on your GPU. It reads your code, writes changes, runs tests, and tracks everything &mdash; without ever connecting to the cloud.</p>
        </div>

        <div class="grid-3 animate-on-scroll">
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128274;</span>
                <h3>100% Local Execution</h3>
                <p class="explain-what">Runs on your GPU using <a href="https://ollama.com" style="color:var(--accent)">Ollama</a>. Your source code never touches a server.</p>
                <p class="explain-why">Why it matters: No API keys, no rate limits, no monthly bills for tokens. Your code stays yours.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128737;</span>
                <h3>9-Layer Security Pipeline</h3>
                <p class="explain-what">Every AI response passes through 9 security layers &mdash; shell gating, path sandboxing, pattern scanning, semantic anomaly detection, behavioral tripwires, canary traps, output fencing, rate limiting, and SSRF protection &mdash; before it can touch your code.</p>
                <p class="explain-why">Why it matters: AI models can be tricked into running malicious code. Forge catches it automatically.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#9889;</span>
                <h3>Self-Healing AI</h3>
                <p class="explain-what">When the AI gets confused, freezes, or refuses to use its tools, Forge detects it and fixes it in real-time with 3 escalation levels.</p>
                <p class="explain-why">Why it matters: Other AI tools just fail. Forge recovers automatically so you don't lose your flow.</p>
            </div>
        </div>

        <div class="grid-3 animate-on-scroll" style="margin-top:20px">
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128202;</span>
                <h3>Multi-Machine Licensing</h3>
                <p class="explain-what">Buy once, run on multiple machines. You're the Master on your main machine, your other machines are Puppets. Revoke any machine instantly.</p>
                <p class="explain-why">Why it matters: One purchase covers your desktop, laptop, and workstation. No per-device fees.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128200;</span>
                <h3>Session Health Monitor</h3>
                <p class="explain-what">Long coding sessions degrade AI quality. Forge tracks 6 health signals &mdash; objective alignment, file coverage, decision retention, swap freshness, recall quality, and working memory depth &mdash; and gives you a letter grade (A through F). Drops below C? Auto-recovery kicks in.</p>
                <p class="explain-why">Why it matters: You'll know before the AI starts giving bad answers, and Forge fixes it without you asking.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128736;</span>
                <h3>59 Built-in Commands</h3>
                <p class="explain-what">From /model to switch AI models, to /scan to analyze your codebase, to /export for compliance-ready audit bundles. Full toolbox out of the box.</p>
                <p class="explain-why">Why it matters: Everything you need is already built in. No plugins required to get started.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128171;</span>
                <h3>Learning Memory</h3>
                <p class="explain-what">Forge remembers what works across sessions. Patterns, preferences, and solutions persist in a "genome" so it gets smarter over time.</p>
                <p class="explain-why">Why it matters: Monday's lessons improve Tuesday's code. Your AI doesn't start from scratch every time.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#128269;</span>
                <h3>Automatic Code Verification</h3>
                <p class="explain-what">After the AI makes changes, Forge can automatically run your tests, linter, and type checker. If something breaks, it rolls back or repairs.</p>
                <p class="explain-why">Why it matters: No more blindly trusting AI output. Forge proves the code works before you see it.</p>
            </div>
            <div class="feature-card card-hover explain-card">
                <span class="feature-icon">&#127912;</span>
                <h3>97 Configuration Options</h3>
                <p class="explain-what">Safety levels, model routing, context management, voice settings, plan verification, enterprise mode, telemetry &mdash; every aspect of Forge is configurable via a single YAML file.</p>
                <p class="explain-why">Why it matters: Your AI, your rules. Tune every knob or leave the defaults. Both work.</p>
            </div>
        </div>
    </div>
</section>

<!-- ── Competitive Comparison ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">How We Compare</span>
            <h2>Forge vs. The Cloud</h2>
            <p>Every other AI coding assistant sends your code to their servers. We don't.</p>
        </div>
        <div class="compare-wrap animate-on-scroll">
            <table class="compare-table">
                <thead>
                    <tr>
                        <th>Feature</th>
                        <th class="col-forge">Forge</th>
                        <th>GitHub Copilot</th>
                        <th>Cursor</th>
                        <th>Windsurf</th>
                        <th>Tabnine</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Data stays on your machine</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-partial">Partial</td>
                    </tr>
                    <tr>
                        <td>Monthly cost (individual)</td>
                        <td class="col-forge">Free &ndash; $19</td>
                        <td>$10 &ndash; $39</td>
                        <td>$20</td>
                        <td>$15</td>
                        <td>$12</td>
                    </tr>
                    <tr>
                        <td>One-time purchase option</td>
                        <td class="col-forge check-yes">&#10003; $199</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                    <tr>
                        <td>Unlimited tokens</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">Rate limited</td>
                        <td class="check-no">Capped</td>
                        <td class="check-no">Capped</td>
                        <td class="check-no">Rate limited</td>
                    </tr>
                    <tr>
                        <td>Self-healing AI (AMI)</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                    <tr>
                        <td>Security layers</td>
                        <td class="col-forge check-yes">9</td>
                        <td class="check-no">0</td>
                        <td class="check-no">0</td>
                        <td class="check-no">0</td>
                        <td class="check-partial">1</td>
                    </tr>
                    <tr>
                        <td>Works fully offline</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                    <tr>
                        <td>Forensic audit trail</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                    <tr>
                        <td>Voice I/O</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                    <tr>
                        <td>Learning memory (Genome)</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-partial">Limited</td>
                    </tr>
                    <tr>
                        <td>Choose any LLM model</td>
                        <td class="col-forge check-yes">&#10003;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                        <td class="check-no">&#10007;</td>
                    </tr>
                </tbody>
            </table>
        </div>
        <p class="compare-note">Data as of March 2026. Prices based on published plans.</p>
    </div>
</section>

<!-- ── ROI Calculator ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Save Money</span>
            <h2>ROI Calculator</h2>
            <p>See how much you'll save switching from cloud AI to local execution. Real math, no marketing.</p>
        </div>
        <div class="roi-calculator animate-on-scroll">
            <div class="roi-inputs">
                <div class="roi-input-group">
                    <label>Team Size (developers)</label>
                    <input type="number" id="roi-devs" value="3" min="1" max="100">
                </div>
                <div class="roi-input-group">
                    <label>Current Monthly Cost / Seat</label>
                    <select id="roi-cloud">
                        <option value="10">GitHub Copilot ($10/mo)</option>
                        <option value="20" selected>Cursor Pro ($20/mo)</option>
                        <option value="39">Copilot Business ($39/mo)</option>
                        <option value="15">Windsurf ($15/mo)</option>
                        <option value="12">Tabnine ($12/mo)</option>
                    </select>
                </div>
                <div class="roi-input-group">
                    <label>Time Horizon</label>
                    <select id="roi-months">
                        <option value="12">1 Year</option>
                        <option value="24" selected>2 Years</option>
                        <option value="36">3 Years</option>
                        <option value="60">5 Years</option>
                    </select>
                </div>
            </div>
            <div class="roi-results" id="roi-results">
                <div class="roi-result">
                    <span class="roi-num cost" id="roi-cloud-total">$1,440</span>
                    <span class="roi-label">Cloud Total</span>
                </div>
                <div class="roi-result">
                    <span class="roi-num neutral" id="roi-forge-total">$199</span>
                    <span class="roi-label">Forge Total (one-time)</span>
                </div>
                <div class="roi-result">
                    <span class="roi-num savings" id="roi-savings">$1,241</span>
                    <span class="roi-label">Total Savings</span>
                </div>
                <div class="roi-result">
                    <span class="roi-num savings" id="roi-pct">86%</span>
                    <span class="roi-label">Cost Reduction</span>
                </div>
            </div>
            <div class="roi-verdict" id="roi-verdict">
                Forge pays for itself in month 1. Every month after that is free.
            </div>
        </div>
    </div>
</section>

<!-- ── 9-Layer Security Breakdown ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Security</span>
            <h2>9 Layers Between AI and Your Code</h2>
            <p>Every response the AI generates passes through all 9 layers. If any layer flags a threat, the action is blocked before it can execute.</p>
        </div>

        <div class="security-layers animate-on-scroll">
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Pattern Scanner</h4>
                    <p>Checks every response against 21 compiled regex patterns across 5 categories &mdash; prompt injection, data exfiltration, obfuscated payloads, hidden content, and credential leaks. Catches the obvious stuff instantly.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Semantic Anomaly Detector</h4>
                    <p>Uses AI embeddings to spot content that doesn't belong. If a database file suddenly contains instructions about "executing shell commands," this layer catches the mismatch.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Behavioral Tripwire</h4>
                    <p>Monitors what the AI does after reading your files. If it reads a file then immediately tries to send data to the internet, the action is blocked &mdash; that's exfiltration behavior.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Canary Trap</h4>
                    <p>A hidden marker is placed in every AI conversation. If the AI has been hijacked by prompt injection, it will leak the marker &mdash; and Forge will catch it and kill the session.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Threat Intelligence</h4>
                    <p>An upgradeable signature database that auto-updates with new attack patterns. Every signature is validated against catastrophic backtracking and hash-verified before loading.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Command Guard</h4>
                    <p>49 regex patterns block dangerous shell commands &mdash; reverse shells, crypto miners, registry edits, privilege escalation, LOLBins, PowerShell cradles. 4 safety levels from "unleashed" to "locked down."</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Path Sandbox</h4>
                    <p>File operations are restricted to your project directory. Symlink escape attempts are caught. The AI can't read your SSH keys, system files, or anything outside the sandbox.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Plan Verifier</h4>
                    <p>After the AI changes your code, Forge automatically runs your tests, linter, and type checker. In strict mode, failures trigger automatic rollback. No broken code gets committed.</p>
                </div>
            </div>
            <div class="security-layer">
                <div class="security-layer-num"></div>
                <div>
                    <h4>Forensic Auditor</h4>
                    <p>Every action is logged with timestamps, risk levels, and a cryptographic provenance chain (HMAC-SHA512). If anyone tampers with the log, the chain breaks and you know exactly where.</p>
                </div>
            </div>
        </div>
    </div>
</section>

<!-- ── Enterprise Compliance ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Enterprise</span>
            <h2>Built for Compliance</h2>
            <p>Forge meets the strictest security and compliance requirements out of the box. No add-ons, no enterprise tiers for basic security.</p>
        </div>
        <div class="compliance-grid animate-on-scroll">
            <div class="compliance-card">
                <div class="compliance-icon">&#128274;</div>
                <h4>Zero Data Egress</h4>
                <p>All AI processing happens on local hardware. No API calls, no cloud endpoints, no data transmission. Your source code, prompts, and AI responses never leave the machine. Period.</p>
                <span class="compliance-badge built-in">Built-in</span>
            </div>
            <div class="compliance-card">
                <div class="compliance-icon">&#128203;</div>
                <h4>Forensic Audit Trail</h4>
                <p>Every action logged with timestamps, risk levels, and HMAC-SHA512 cryptographic chains. Export compliance-ready audit bundles with a single command. Tamper detection built in.</p>
                <span class="compliance-badge built-in">Built-in</span>
            </div>
            <div class="compliance-card">
                <div class="compliance-icon">&#127760;</div>
                <h4>Air-Gapped Operation</h4>
                <p>Designed from day one for networks with zero internet access. License validation, model loading, genome persistence, and all 59 commands work fully offline.</p>
                <span class="compliance-badge ready">Air-Gap Ready</span>
            </div>
            <div class="compliance-card">
                <div class="compliance-icon">&#128737;</div>
                <h4>SOC 2 Alignment</h4>
                <p>Access controls (role-based licensing), change management (provenance chain), risk assessment (9-layer threat scanning), monitoring (session health + fleet analytics). Audit export maps to SOC 2 trust principles.</p>
                <span class="compliance-badge ready">Aligned</span>
            </div>
            <div class="compliance-card">
                <div class="compliance-icon">&#128272;</div>
                <h4>HIPAA-Compatible</h4>
                <p>Protected health information never leaves the local machine. No BAA needed because there's no cloud vendor to sign one with. Local processing = no third-party data handling.</p>
                <span class="compliance-badge ready">Compatible</span>
            </div>
            <div class="compliance-card">
                <div class="compliance-icon">&#127919;</div>
                <h4>ITAR / Export Control</h4>
                <p>Defense contractors can use AI coding assistance without export control concerns. No data crosses international boundaries. No foreign-hosted servers process controlled technical data.</p>
                <span class="compliance-badge ready">Compatible</span>
            </div>
        </div>
    </div>
</section>

<!-- ── Neural Cortex Interactive Demo ── -->
<section class="section" id="cortex">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Neural Cortex</span>
            <h2>Watch It Think</h2>
            <p>The Neural Cortex is Forge's real-time brain visualization. It responds to what the AI is actually doing &mdash; thinking, writing code, scanning for threats, or recovering from errors. Click a state to see it in action.</p>
        </div>

        <div class="cortex-demo animate-on-scroll">
            <div class="cortex-wrap">
                <div class="cortex-canvas-wrap">
                    <canvas id="demo-cortex" style="border-radius:50%"></canvas>
                </div>
                <span class="cortex-state-label" id="demo-state-label">idle</span>
            </div>
            <div class="cortex-panel">
                <div class="cortex-controls" id="cortex-buttons">
                    <button class="cortex-btn" data-state="boot"><span class="cortex-dot" style="background:#0088ff"></span>Boot</button>
                    <button class="cortex-btn active" data-state="idle"><span class="cortex-dot" style="background:#00aacc"></span>Idle</button>
                    <button class="cortex-btn" data-state="thinking"><span class="cortex-dot" style="background:#ff6600"></span>Thinking</button>
                    <button class="cortex-btn" data-state="tool_exec"><span class="cortex-dot" style="background:#00cc88"></span>Executing</button>
                    <button class="cortex-btn" data-state="indexing"><span class="cortex-dot" style="background:#cc88ff"></span>Indexing</button>
                    <button class="cortex-btn" data-state="swapping"><span class="cortex-dot" style="background:#ffffff"></span>Swapping</button>
                    <button class="cortex-btn" data-state="error"><span class="cortex-dot" style="background:#ff4444"></span>Error</button>
                    <button class="cortex-btn" data-state="threat"><span class="cortex-dot" style="background:#ff0000"></span>Threat</button>
                    <button class="cortex-btn" data-state="pass"><span class="cortex-dot" style="background:#34d399"></span>Pass</button>
                </div>
                <div class="cortex-desc" id="cortex-desc">
                    <strong>Idle</strong> &mdash; Waiting for your input. Low power, minimal glow. The brain is listening but not processing.
                </div>
            </div>
        </div>
    </div>
</section>

<!-- ── How It Works ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Getting Started</span>
            <h2>Up and Running in Minutes</h2>
            <p>No complex setup. No API keys to manage. Just install and go.</p>
        </div>

        <div class="steps-row animate-on-scroll">
            <div class="step-card">
                <h3>Install Ollama</h3>
                <p>Download <a href="https://ollama.com" style="color:var(--accent)">Ollama</a> (free) and pull a coding model. One command: <code>ollama pull qwen2.5-coder:14b</code></p>
            </div>
            <div class="step-card">
                <h3>Launch Forge</h3>
                <p>Run <code>python -m forge</code> in any project directory. It auto-detects your environment, models, and GPU.</p>
            </div>
            <div class="step-card">
                <h3>Start Coding</h3>
                <p>Describe what you want in plain English. Forge reads your code, plans changes, edits files, runs tests, and tracks everything.</p>
            </div>
            <div class="step-card">
                <h3>Scale Your Fleet</h3>
                <p>Activate your license to run on multiple machines with Master/Puppet architecture. One purchase, all your devices.</p>
            </div>
        </div>
    </div>
</section>

<!-- ── Performance Benchmarks ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Performance</span>
            <h2>Real-World Benchmarks</h2>
            <p>Measured on an RTX 5070 Ti (16GB VRAM) with qwen2.5-coder:14b. These aren't theoretical maximums &mdash; they're what you get in daily coding.</p>
        </div>
        <div class="benchmark-grid animate-on-scroll">
            <div class="bench-card">
                <span class="bench-value">38.2 <span class="bench-unit">tok/s</span></span>
                <span class="bench-label">Token Generation</span>
                <span class="bench-detail">qwen2.5-coder:14b on RTX 5070 Ti with KV Q8</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:76%"></div></div>
            </div>
            <div class="bench-card">
                <span class="bench-value">&lt;200 <span class="bench-unit">ms</span></span>
                <span class="bench-label">First Token Latency</span>
                <span class="bench-detail">Time from prompt to first response token</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:90%"></div></div>
            </div>
            <div class="bench-card">
                <span class="bench-value">128K <span class="bench-unit">ctx</span></span>
                <span class="bench-label">Context Window</span>
                <span class="bench-detail">Full context with Continuity Engine recovery</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:85%"></div></div>
            </div>
            <div class="bench-card">
                <span class="bench-value">A&ndash;F</span>
                <span class="bench-label">Continuity Grade</span>
                <span class="bench-detail">6-signal context health tracking with auto-recovery</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:94%"></div></div>
            </div>
            <div class="bench-card">
                <span class="bench-value">1,318</span>
                <span class="bench-label">Automated Tests</span>
                <span class="bench-detail">226 security + 373 AI + 198 licensing + 63 integration + 458 infra</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:100%"></div></div>
            </div>
            <div class="bench-card">
                <span class="bench-value">$0<span class="bench-unit">/token</span></span>
                <span class="bench-label">Ongoing Cost</span>
                <span class="bench-detail">Unlimited tokens after one-time purchase</span>
                <div class="bench-bar-wrap"><div class="bench-bar" style="width:100%"></div></div>
            </div>
        </div>
        <p style="text-align:center; color:var(--text-dim); font-size:0.85em; margin-top:20px">
            Performance scales with GPU. RTX 3060 (12GB): ~22 tok/s. RTX 4090 (24GB): ~55 tok/s. CPU-only mode: ~3 tok/s. All models loaded via Ollama with automatic KV cache quantization.
        </p>
    </div>
</section>

<!-- ── BPoS Architecture ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Architecture</span>
            <h2>Behavioral Proof of Stake</h2>
            <p>Five cryptographic and behavioral layers that make Forge tamper-proof. Not DRM &mdash; something better.</p>
        </div>

        <div class="bpos-layers animate-on-scroll">
            <div class="bpos-layer">
                <div class="bpos-num">1</div>
                <div class="bpos-content">
                    <h4>Chain of Being</h4>
                    <p class="bpos-plain">Every license is cryptographically signed and chained back to Origin. Forge knows if a passport was tampered with, cloned, or forged.</p>
                    <p class="bpos-tech">HMAC-SHA512 provenance chain with monotonic timestamps</p>
                </div>
            </div>
            <div class="bpos-layer">
                <div class="bpos-num">2</div>
                <div class="bpos-content">
                    <h4>Forge Genome</h4>
                    <p class="bpos-plain">Forge accumulates intelligence over time &mdash; model failure patterns, quality trends, tool usage patterns, reliability scores. This genome is unique to your instance.</p>
                    <p class="bpos-tech">Persistent behavioral fingerprint across sessions</p>
                </div>
            </div>
            <div class="bpos-layer">
                <div class="bpos-num">3</div>
                <div class="bpos-content">
                    <h4>Symbiotic Capability Scaling</h4>
                    <p class="bpos-plain">Features genuinely improve the more you use them. AMI learns which models fail on which tasks. The Continuity Engine gets more accurate. The Router optimizes for your workflow. You can't copy this.</p>
                    <p class="bpos-tech">Adaptive learning across AMI, Continuity, Router subsystems</p>
                </div>
            </div>
            <div class="bpos-layer">
                <div class="bpos-num">4</div>
                <div class="bpos-content">
                    <h4>Ambient Verification</h4>
                    <p class="bpos-plain">Forge knows its own behavioral fingerprint &mdash; tool frequency, command patterns, session cadence. A legitimate instance and a pirated copy produce measurably different signatures.</p>
                    <p class="bpos-tech">Statistical behavioral analysis with drift detection</p>
                </div>
            </div>
            <div class="bpos-layer">
                <div class="bpos-num">5</div>
                <div class="bpos-content">
                    <h4>Passport Token</h4>
                    <p class="bpos-plain">Your license is an HMAC-signed passport containing your tier, role (Master or Puppet), activation count, and expiry. Server-validated on activation, locally cached for offline use.</p>
                    <p class="bpos-tech">HMAC-SHA512, account-bound, role-encoded (v2 protocol)</p>
                </div>
            </div>
        </div>

        <div class="bpos-verdict animate-on-scroll">
            A pirated copy of Forge is a <strong>lobotomized</strong> copy. It runs, but it can't learn, can't heal, can't prove it's real, and starts from zero every time. The legitimate version gets smarter with every session.
        </div>
    </div>
</section>

<!-- ── Architecture Deep Dive ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Under the Hood</span>
            <h2>System Architecture</h2>
            <p>Seven layers from user input to code output. Every request passes through the entire stack.</p>
        </div>
        <div class="arch-diagram animate-on-scroll">
            <div class="arch-layer">
                <span class="arch-label">Input</span>
                <div class="arch-blocks">
                    <span class="arch-block input">Terminal UI</span>
                    <span class="arch-block input">Voice (Whisper)</span>
                    <span class="arch-block input">Slash Commands</span>
                    <span class="arch-block input">Plugin Hooks</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">Router</span>
                <div class="arch-blocks">
                    <span class="arch-block core">Complexity Analyzer</span>
                    <span class="arch-block core">Model Selector</span>
                    <span class="arch-block core">Context Manager</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">Security</span>
                <div class="arch-blocks">
                    <span class="arch-block security">Pattern Scanner</span>
                    <span class="arch-block security">Semantic Anomaly</span>
                    <span class="arch-block security">Behavioral Tripwire</span>
                    <span class="arch-block security">Canary Trap</span>
                    <span class="arch-block security">Command Guard</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">AI Engine</span>
                <div class="arch-blocks">
                    <span class="arch-block core">Ollama Backend</span>
                    <span class="arch-block core">OpenAI Backend</span>
                    <span class="arch-block core">Anthropic Backend</span>
                    <span class="arch-block core">Streaming Parser</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">Intelligence</span>
                <div class="arch-blocks">
                    <span class="arch-block intel">AMI (Self-Healing)</span>
                    <span class="arch-block intel">Continuity Engine</span>
                    <span class="arch-block intel">Genome (Memory)</span>
                    <span class="arch-block intel">Neural Cortex</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">Tools</span>
                <div class="arch-blocks">
                    <span class="arch-block output">File Editor</span>
                    <span class="arch-block output">Shell Executor</span>
                    <span class="arch-block output">Code Search</span>
                    <span class="arch-block output">Web Fetch</span>
                    <span class="arch-block output">Tree-sitter AST</span>
                </div>
            </div>
            <div class="arch-connector">&#8595;</div>
            <div class="arch-layer">
                <span class="arch-label">Infra</span>
                <div class="arch-blocks">
                    <span class="arch-block infra">BPoS Licensing</span>
                    <span class="arch-block infra">Forensic Auditor</span>
                    <span class="arch-block infra">Fleet Telemetry</span>
                    <span class="arch-block infra">Shipwright CI</span>
                    <span class="arch-block infra">AutoForge</span>
                </div>
            </div>
        </div>
    </div>
</section>

<!-- ── Beyond Coding ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">More Than Code</span>
            <h2>Beyond Coding</h2>
            <p>Forge isn't just a coding assistant. It's a full development environment with voice, web, plugins, and multi-model intelligence.</p>
        </div>
        <div class="beyond-grid animate-on-scroll">
            <div class="beyond-card">
                <h4>Voice I/O</h4>
                <p>Talk to your AI with push-to-talk or hands-free voice activation. Whisper-powered speech recognition runs locally on your GPU. Responses read back via text-to-speech.</p>
                <p class="beyond-tech">faster-whisper STT + edge-tts TTS, PTT + VOX modes</p>
            </div>
            <div class="beyond-card">
                <h4>Multi-Model Support</h4>
                <p>Works with Ollama, OpenAI, and Anthropic backends. Pull any model from the built-in Model Manager. Smart routing sends simple tasks to small models and hard tasks to large ones.</p>
                <p class="beyond-tech">3 backends, built-in model manager, complexity-based routing</p>
            </div>
            <div class="beyond-card">
                <h4>Plugin System</h4>
                <p>Build custom plugins that hook into 17 lifecycle events including user input, AI response, tool calls, commands, file reads, session lifecycle, model switches, threats, and context pressure. Priority dispatch with glob-pattern event filtering.</p>
                <p class="beyond-tech">ForgePlugin base class, ~/.forge/plugins/, 6 hook points</p>
            </div>
            <div class="beyond-card">
                <h4>Web Search &amp; Fetching</h4>
                <p>Forge can search the web via DuckDuckGo and fetch any public URL. No API keys needed. Private IPs and loopback addresses are blocked for safety.</p>
                <p class="beyond-tech">DuckDuckGo search, URL fetch with SSRF protection</p>
            </div>
            <div class="beyond-card">
                <h4>Code Intelligence</h4>
                <p>Tree-sitter AST parsing for definition finding, reference search, call graphs, and symbol tables. Semantic search via embeddings finds conceptually related code, not just text matches.</p>
                <p class="beyond-tech">tree-sitter + nomic-embed-text, cosine similarity RAG</p>
            </div>
            <div class="beyond-card">
                <h4>Benchmark Suite</h4>
                <p>Reproducible coding benchmarks in isolated temp directories. Test any model against deterministic scenarios. Compare results across runs with full metrics.</p>
                <p class="beyond-tech">YAML scenarios, validation patterns, cross-run comparison</p>
            </div>
        </div>
    </div>
</section>

<!-- ── Integration Ecosystem ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Integrations</span>
            <h2>Works With Your Stack</h2>
            <p>Forge doesn't care what language, framework, or editor you use. It reads code, understands structure, and works everywhere.</p>
        </div>
        <div class="ecosystem-grid animate-on-scroll">
            <div class="eco-category">
                <h4>Languages</h4>
                <ul class="eco-items">
                    <li>Python</li>
                    <li>JavaScript / TypeScript</li>
                    <li>C / C++ / C#</li>
                    <li>Rust</li>
                    <li>Go</li>
                    <li>Java / Kotlin</li>
                    <li>PHP / Ruby</li>
                    <li>Any text-based language</li>
                </ul>
            </div>
            <div class="eco-category">
                <h4>AI Models</h4>
                <ul class="eco-items">
                    <li>Qwen2.5-Coder (3B/7B/14B/32B)</li>
                    <li>Llama 3.3 (8B/70B)</li>
                    <li>DeepSeek-Coder V3</li>
                    <li>CodeGemma / Gemma 2</li>
                    <li>Mistral / Mixtral</li>
                    <li>Phi-4</li>
                    <li>Any Ollama model</li>
                    <li>OpenAI / Anthropic APIs</li>
                </ul>
            </div>
            <div class="eco-category">
                <h4>Tools</h4>
                <ul class="eco-items">
                    <li>Git (diff, commit, branch)</li>
                    <li>pytest / unittest / jest</li>
                    <li>ESLint / pylint / mypy</li>
                    <li>Docker</li>
                    <li>Shell (bash, PowerShell)</li>
                    <li>Tree-sitter (30+ parsers)</li>
                    <li>DuckDuckGo search</li>
                    <li>Custom plugins</li>
                </ul>
            </div>
            <div class="eco-category">
                <h4>Platforms</h4>
                <ul class="eco-items">
                    <li>Windows 10/11</li>
                    <li>Linux (Ubuntu, Fedora, Arch)</li>
                    <li>macOS 12+</li>
                    <li>WSL / WSL2</li>
                    <li>NVIDIA GPUs (CUDA)</li>
                    <li>AMD GPUs (ROCm)</li>
                    <li>Apple Silicon (Metal)</li>
                    <li>CPU-only fallback</li>
                </ul>
            </div>
        </div>
    </div>
</section>

<!-- ── Command Showcase ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Commands</span>
            <h2>59 Commands, Zero Plugins Required</h2>
            <p>Every command ships with Forge. No extensions to install, no marketplace to browse. Full toolbox from the first launch.</p>
        </div>
        <div class="cmd-showcase animate-on-scroll">
            <div class="cmd-group">
                <h4>Core AI</h4>
                <ul class="cmd-list">
                    <li><code>/plan</code> <span class="cmd-desc">Generate and verify an implementation plan</span></li>
                    <li><code>/model</code> <span class="cmd-desc">Switch AI models on the fly</span></li>
                    <li><code>/router</code> <span class="cmd-desc">Multi-model routing (simple/complex)</span></li>
                    <li><code>/context</code> <span class="cmd-desc">Manage conversation context window</span></li>
                    <li><code>/voice</code> <span class="cmd-desc">Toggle voice input/output modes</span></li>
                    <li><code>/ami</code> <span class="cmd-desc">AI model intelligence and quality scoring</span></li>
                </ul>
            </div>
            <div class="cmd-group">
                <h4>Code Intelligence</h4>
                <ul class="cmd-list">
                    <li><code>/scan</code> <span class="cmd-desc">Deep-scan codebase for patterns and issues</span></li>
                    <li><code>/search</code> <span class="cmd-desc">Semantic code search via embeddings</span></li>
                    <li><code>/index</code> <span class="cmd-desc">Build or refresh the code search index</span></li>
                    <li><code>/digest</code> <span class="cmd-desc">AST analysis and code structure breakdown</span></li>
                    <li><code>/recall</code> <span class="cmd-desc">Semantic memory search with previews</span></li>
                    <li><code>/dedup</code> <span class="cmd-desc">Detect and suppress duplicate responses</span></li>
                </ul>
            </div>
            <div class="cmd-group">
                <h4>Security &amp; Compliance</h4>
                <ul class="cmd-list">
                    <li><code>/crucible</code> <span class="cmd-desc">4-layer threat scanner status and controls</span></li>
                    <li><code>/export</code> <span class="cmd-desc">Generate compliance audit bundle with SHA-256</span></li>
                    <li><code>/threats</code> <span class="cmd-desc">View threat intelligence patterns and rules</span></li>
                    <li><code>/provenance</code> <span class="cmd-desc">Verify forensic tool-call chain integrity</span></li>
                    <li><code>/safety</code> <span class="cmd-desc">Set safety level (unleashed to locked down)</span></li>
                    <li><code>/forensics</code> <span class="cmd-desc">Session forensics summary and export</span></li>
                </ul>
            </div>
            <div class="cmd-group">
                <h4>Reliability &amp; Fleet</h4>
                <ul class="cmd-list">
                    <li><code>/break</code> <span class="cmd-desc">Run reliability suite with signed reports</span></li>
                    <li><code>/assure</code> <span class="cmd-desc">AI assurance suite (31 scenarios, 6 categories)</span></li>
                    <li><code>/ship</code> <span class="cmd-desc">Shipwright release management</span></li>
                    <li><code>/autocommit</code> <span class="cmd-desc">Smart auto-commit with AI messages</span></li>
                    <li><code>/license</code> <span class="cmd-desc">View license status and tier</span></li>
                    <li><code>/puppet</code> <span class="cmd-desc">Fleet puppet passport management</span></li>
                </ul>
            </div>
        </div>
        <p style="text-align:center; color:var(--text-dim); font-size:0.88em; margin-top:16px">
            Plus 35 more commands for themes, plugins, config, billing, benchmarks, and session management. <a href="docs.php#commands" style="color:var(--accent)">See the full list &rarr;</a>
        </p>
    </div>
</section>

<!-- ── Who It's For (Persona Tabs) ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Who It's For</span>
            <h2>Built For How You Work</h2>
            <p>From side projects to classified networks. Find your use case.</p>
        </div>

        <div class="persona-tabs" id="persona-tabs">
            <div class="persona-tab active" data-persona="solo">Solo Developer</div>
            <div class="persona-tab" data-persona="team">Team Lead</div>
            <div class="persona-tab" data-persona="security">Security Engineer</div>
            <div class="persona-tab" data-persona="gov">Air-Gapped / Gov / Military</div>
            <div class="persona-tab" data-persona="nontechnical">Non-Technical User</div>
        </div>

        <div class="persona-panel active" data-persona-panel="solo">
            <div class="persona-content">
                <ul class="persona-features">
                    <li><span class="pf-icon">&#10003;</span> All 59 commands and 28 AI tools included free</li>
                    <li><span class="pf-icon">&#10003;</span> 14 themes with live visual effects</li>
                    <li><span class="pf-icon">&#10003;</span> Voice input and output &mdash; code hands-free</li>
                    <li><span class="pf-icon">&#10003;</span> $0 per token. Run as much as your GPU allows</li>
                    <li><span class="pf-icon">&#10003;</span> Works with any Ollama model from 3B to 70B+</li>
                </ul>
                <div class="persona-scenario">
                    <strong>Saturday, 11 PM.</strong> You're deep in a side project. The API for your cloud coding assistant is rate-limiting you. Again. You switch to Forge. It runs on your RTX card. No limits. No waiting. No monthly bill. You finish the feature before midnight.
                </div>
            </div>
            <div class="persona-cta"><a href="docs.php#install" class="btn btn-primary">Download Free</a></div>
        </div>

        <div class="persona-panel" data-persona-panel="team">
            <div class="persona-content">
                <ul class="persona-features">
                    <li><span class="pf-icon">&#10003;</span> Master/Puppet fleet &mdash; one license, multiple machines</li>
                    <li><span class="pf-icon">&#10003;</span> Genome learning persists across sessions and devices</li>
                    <li><span class="pf-icon">&#10003;</span> Shipwright release management with AI-generated changelogs</li>
                    <li><span class="pf-icon">&#10003;</span> AutoForge smart auto-commit detects meaningful changes</li>
                    <li><span class="pf-icon">&#10003;</span> $199 one-time for 3 seats &mdash; less than 1 year of Copilot</li>
                </ul>
                <div class="persona-scenario">
                    <strong>Your team of three just shipped a release.</strong> Shipwright auto-generated the changelog from commit history. AutoForge caught and committed a hotfix your junior missed. Genome learned from yesterday's debugging session and suggested the fix before you asked. Total cloud bill: $0.
                </div>
            </div>
            <div class="persona-cta"><a href="#pricing" class="btn btn-primary">Get Pro &mdash; $199</a></div>
        </div>

        <div class="persona-panel" data-persona-panel="security">
            <div class="persona-content">
                <ul class="persona-features">
                    <li><span class="pf-icon">&#10003;</span> 9-layer Crucible scans every AI response in real-time</li>
                    <li><span class="pf-icon">&#10003;</span> Forensic Auditor logs every action with HMAC-SHA512 chains</li>
                    <li><span class="pf-icon">&#10003;</span> Canary traps detect prompt injection and context poisoning</li>
                    <li><span class="pf-icon">&#10003;</span> Auto-updating threat intelligence with signature database</li>
                    <li><span class="pf-icon">&#10003;</span> Export compliance bundles with /export command</li>
                </ul>
                <div class="persona-scenario">
                    <strong>The AI's response looks clean.</strong> But Layer 4 catches it &mdash; a canary token was echoed back, meaning the AI was prompt-injected. Session quarantined. Forensic Auditor logs the incident with tamper-proof hashes. Neural Cortex flashes red. Total data exfiltrated: zero bytes.
                </div>
            </div>
            <div class="persona-cta"><a href="docs.php#security" class="btn btn-primary">Read Security Docs</a></div>
        </div>

        <div class="persona-panel" data-persona-panel="gov">
            <div class="persona-content">
                <ul class="persona-features">
                    <li><span class="pf-icon">&#10003;</span> 100% offline operation &mdash; zero network dependencies</li>
                    <li><span class="pf-icon">&#10003;</span> Enterprise audit export for compliance frameworks</li>
                    <li><span class="pf-icon">&#10003;</span> Zero data egress &mdash; everything stays on your hardware</li>
                    <li><span class="pf-icon">&#10003;</span> Fleet management for up to 10 machines per license</li>
                    <li><span class="pf-icon">&#10003;</span> Tamper-proof provenance chain (BPoS)</li>
                </ul>
                <div class="persona-scenario">
                    <strong>Your network has no internet. Zero.</strong> Forge doesn't care. It runs entirely on local hardware with local models. Passport validation works offline. Audit logs are cryptographically chained. When the inspector asks how your AI handles classified code, you hand them the forensic export. Everything checks out.
                </div>
            </div>
            <div class="persona-cta"><a href="#pricing" class="btn btn-primary">Get Power &mdash; $999</a></div>
        </div>

        <div class="persona-panel" data-persona-panel="nontechnical">
            <div class="persona-content">
                <ul class="persona-features">
                    <li><span class="pf-icon">&#10003;</span> Describe what you want in plain English</li>
                    <li><span class="pf-icon">&#10003;</span> Voice input &mdash; talk to your AI instead of typing</li>
                    <li><span class="pf-icon">&#10003;</span> Auto-verification runs tests so you don't have to</li>
                    <li><span class="pf-icon">&#10003;</span> Neural Cortex gives visual feedback on what the AI is doing</li>
                    <li><span class="pf-icon">&#10003;</span> Self-healing means it recovers from mistakes automatically</li>
                </ul>
                <div class="persona-scenario">
                    <strong>You don't write code.</strong> You describe what you need: "Build me a contact form that emails submissions." Forge reads your project, writes the code, tests it, and tells you when it's done. The Neural Cortex brain pulses as it works. When it finishes, it glows green. You check the result. It works.
                </div>
            </div>
            <div class="persona-cta"><a href="docs.php#quickstart" class="btn btn-primary">See How It Works</a></div>
        </div>
    </div>
</section>

<!-- ── System Requirements ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Hardware</span>
            <h2>System Requirements</h2>
            <p>Forge scales from entry-level GPUs to multi-GPU workstations. The model catalog spans 3B to 70B+ parameters &mdash; pick the tier that matches your hardware.</p>
        </div>
        <table class="spec-table animate-on-scroll">
            <thead>
                <tr>
                    <th class="spec-label">Component</th>
                    <th>Entry</th>
                    <th class="spec-rec">Recommended</th>
                    <th>High-End</th>
                    <th>Workstation</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="spec-label">GPU</td>
                    <td>4&ndash;8 GB VRAM (GTX 1650 / RTX 3050)</td>
                    <td class="spec-rec">12&ndash;16 GB VRAM (RTX 3060 / 4060 / 5070 Ti)</td>
                    <td>24 GB VRAM (RTX 3090 / 4090 / 5090)</td>
                    <td>48 GB+ VRAM (RTX A6000 / dual GPU)</td>
                </tr>
                <tr>
                    <td class="spec-label">RAM</td>
                    <td>8 GB</td>
                    <td class="spec-rec">16 GB</td>
                    <td>32 GB</td>
                    <td>64 GB+</td>
                </tr>
                <tr>
                    <td class="spec-label">Storage</td>
                    <td>10 GB (one small model)</td>
                    <td class="spec-rec">20 GB (14B model + embeddings)</td>
                    <td>50 GB (multiple models)</td>
                    <td>100 GB+ (full model library)</td>
                </tr>
                <tr>
                    <td class="spec-label">OS</td>
                    <td colspan="4">Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+</td>
                </tr>
                <tr>
                    <td class="spec-label">Models</td>
                    <td>1.5B &ndash; 7B params</td>
                    <td class="spec-rec">14B params (qwen2.5-coder:14b)</td>
                    <td>32B &ndash; 34B params</td>
                    <td>70B+ params (Llama 3.3:70b, Qwen2.5-Coder:32b)</td>
                </tr>
                <tr>
                    <td class="spec-label">Use Case</td>
                    <td>Code completion, quick edits</td>
                    <td class="spec-rec">Full coding assistant, refactoring, tests</td>
                    <td>Complex multi-file reasoning, large codebases</td>
                    <td>Enterprise-scale analysis, maximum context</td>
                </tr>
            </tbody>
        </table>
        <p style="text-align:center; color:var(--text-dim); font-size:0.88em; margin-top:12px">
            Works with any Ollama-compatible model. CPU-only mode supported but slow. KV cache quantization (Q8) enabled by default for optimal VRAM usage.
        </p>
    </div>
</section>

<!-- ── Themes ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Themes</span>
            <h2>14 Built-in Themes</h2>
            <p>From dark minimalist to full cyberpunk. Three themes include live particle effects and animated edge glow.</p>
        </div>
        <div class="theme-grid animate-on-scroll">
            <?php
            $themes = [
                ['midnight',  '#0a0e17', false], ['obsidian',  '#1a1a1a', false],
                ['dracula',   '#282a36', false], ['solarized', '#002b36', false],
                ['nord',      '#2e3440', false], ['monokai',   '#272822', false],
                ['cyberpunk', '#050508', true],  ['matrix',    '#0a0f0a', true],
                ['amber',     '#1a1000', false], ['phosphor',  '#0a120a', false],
                ['arctic',    '#f0f2f5', false], ['sunset',    '#1a0f0a', false],
                ['od_green',  '#111408', false], ['plasma',    '#070010', true],
            ];
            foreach ($themes as $t) {
                $slug = $t[0]; $bg = $t[1]; $fx = $t[2];
                $label = ucwords(str_replace('_', ' ', $slug));
                echo '<div class="theme-badge" data-theme="' . $slug . '">';
                echo '<span class="theme-swatch" style="background:' . $bg . '"></span>';
                echo '<span class="theme-name">' . htmlspecialchars($label) . '</span>';
                if ($fx) echo '<span class="fx-dot" title="Has visual effects"></span>';
                echo '</div>';
            }
            ?>
        </div>
        <p class="theme-hint">Click any theme to preview it on this page</p>
    </div>
</section>

<!-- ── Open Source Transparency ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Transparency</span>
            <h2>The Numbers Don't Lie</h2>
            <p>Forge ships its source code with every install. Every claim on this page is verifiable in the codebase.</p>
        </div>
        <div class="code-stats-grid animate-on-scroll">
            <div class="code-stat">
                <span class="cs-num" data-count="54207" data-suffix="+">0</span>
                <span class="cs-label">Lines of Source</span>
            </div>
            <div class="code-stat">
                <span class="cs-num" data-count="95">0</span>
                <span class="cs-label">Source Files</span>
            </div>
            <div class="code-stat">
                <span class="cs-num" data-count="1318">0</span>
                <span class="cs-label">Tests Passing</span>
            </div>
            <div class="code-stat">
                <span class="cs-num" data-count="28">0</span>
                <span class="cs-label">AI Tools</span>
            </div>
            <div class="code-stat">
                <span class="cs-num" data-count="59">0</span>
                <span class="cs-label">Commands</span>
            </div>
            <div class="code-stat">
                <span class="cs-num" data-count="9">0</span>
                <span class="cs-label">Core Subsystems</span>
            </div>
        </div>
        <div class="methodology-list animate-on-scroll">
            <div class="methodology-item">
                <span class="mi-num">1</span>
                <div><strong>Adaptive Model Intelligence (AMI)</strong> &mdash; Self-healing AI with 3 escalation levels. Detects frozen models, tool refusal, and context rot. Auto-recovers without user intervention.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">2</span>
                <div><strong>Behavioral Proof of Stake (BPoS)</strong> &mdash; Five cryptographic and behavioral layers that make legitimate copies genuinely better than pirated ones. Not DRM &mdash; earned capability.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">3</span>
                <div><strong>Crucible Security Engine</strong> &mdash; 9-layer defense-in-depth pipeline with pattern scanning, semantic anomaly detection, canary traps, and cryptographic audit trails.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">4</span>
                <div><strong>Continuity Engine</strong> &mdash; Tracks 6 signals to measure AI context health (A-F grade). Auto-recovery re-reads critical files when quality degrades. Prevents hallucination drift in long sessions.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">5</span>
                <div><strong>Forge Genome</strong> &mdash; Persistent behavioral fingerprint that accumulates intelligence across sessions. Model failure patterns, quality trends, tool usage, and reliability scores. Unique to your instance.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">6</span>
                <div><strong>Symbiotic Capability Scaling</strong> &mdash; Features improve with usage. AMI learns failure modes, Router optimizes model selection, Genome stores patterns. You can copy the code but not the learned intelligence.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">7</span>
                <div><strong>Ambient Verification</strong> &mdash; Statistical behavioral analysis that distinguishes legitimate instances from pirated copies based on tool frequency, command patterns, and session cadence.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">8</span>
                <div><strong>Neural Cortex</strong> &mdash; Real-time brain visualization using depth-aware Gaussian wave physics. 9 distinct states with characteristic animation patterns. Visual state feedback, not decoration.</div>
            </div>
            <div class="methodology-item">
                <span class="mi-num">9</span>
                <div><strong>Shipwright</strong> &mdash; AI-powered release management. Automated preflight checks, semantic versioning, AI-generated changelogs from commit history, and release artifact generation.</div>
            </div>
        </div>
    </div>
</section>

<!-- ── Trust & Credibility ── -->
<section class="section" style="padding-top:0; padding-bottom:40px">
    <div class="container">
        <div class="trust-pills animate-on-scroll">
            <span class="trust-pill"><span class="tp-icon">&#128187;</span> 54,207 Lines of Source</span>
            <span class="trust-pill"><span class="tp-icon">&#10003;</span> 1,318 Tests Passing</span>
            <span class="trust-pill"><span class="tp-icon">&#128274;</span> HMAC-SHA512 Audit Chain</span>
            <span class="trust-pill"><span class="tp-icon">&#127760;</span> 100% Offline Capable</span>
            <span class="trust-pill"><span class="tp-icon">&#128737;</span> Zero Data Egress</span>
        </div>
        <div class="credibility-grid animate-on-scroll">
            <div class="credibility-card">
                <h4>1,318 Automated Tests</h4>
                <p>226 security tests (red-team attacks, prompt injection, PII scanning, threat intel, rate limiting, output fencing). 373 AI intelligence tests (self-healing, quality scoring, continuity, reliability, benchmarks, plan verification, dedup). 198 licensing &amp; release tests (passport crypto, fleet management, auto-commit, semantic versioning). 63 integration/stress tests (crash recovery, network chaos, context storms, policy drift). 458 infrastructure tests (context window, billing, forensics, event bus, plugins, config). 77 test files. Zero skip, zero xfail. Every test passes on every commit.</p>
            </div>
            <div class="credibility-card">
                <h4>Security Depth</h4>
                <p>9 security layers across 3 tiers. 21 content-scanning regex patterns. 49 shell command blocklist patterns. Canary traps for prompt injection. HMAC-SHA512 forensic provenance chain. Built by someone who assumes the AI is hostile.</p>
            </div>
            <div class="credibility-card">
                <h4>Novel Research</h4>
                <p>10 published method papers plus a comprehensive systems paper. Behavioral Proof of Stake. Adaptive Model Intelligence. Continuity Grading. Semantic Anomaly Detection. These aren't buzzwords &mdash; they're implemented, tested systems with full source code.</p>
            </div>
        </div>
        <div class="transparency-callout animate-on-scroll">
            Forge ships its source code with every install. You can read every line, audit every security layer, and verify every claim on this page. <a href="docs.php">Read the docs &rarr;</a>
        </div>
    </div>
</section>

<!-- ── Pricing ── -->
<section class="section" id="pricing">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Pricing</span>
            <h2>Choose Your Plan</h2>
            <p>One-time purchase or monthly &mdash; your choice. No per-token fees either way.</p>
        </div>

        <div class="pricing-toggle">
            <span class="active" id="label-onetime">One-Time</span>
            <button class="toggle-switch" id="pricing-switch" onclick="togglePricing()"></button>
            <span id="label-monthly">Monthly</span>
        </div>

        <div class="grid-3 animate-on-scroll">
            <?php foreach ($tier_order as $tid):
                $t = isset($tiers[$tid]) ? $tiers[$tid] : null;
                if (!$t) continue;
                $color = isset($tier_colors[$tid]) ? $tier_colors[$tid] : '#8b949e';
                $icon = isset($tier_icons[$tid]) ? $tier_icons[$tid] : '';
                $desc = isset($tier_descriptions[$tid]) ? $tier_descriptions[$tid] : '';
                $is_featured = ($tid === 'pro');
                $price_cents = isset($t['price_cents']) ? (int)$t['price_cents'] : 0;
                $monthly_cents = isset($t['price_monthly_cents']) ? (int)$t['price_monthly_cents'] : 0;
                $seats = isset($t['seats']) ? (int)$t['seats'] : 1;
                $puppet_seats = max(0, $seats - 1);
            ?>
            <div class="price-card<?php echo $is_featured ? ' featured' : ''; ?>">
                <div class="price-tier" style="color:<?php echo $color; ?>"><?php echo $icon; ?> <?php echo htmlspecialchars($t['label']); ?></div>
                <div class="price-desc"><?php echo htmlspecialchars($desc); ?></div>
                <div class="price-amount">
                    <span class="price-onetime">
                        <?php if ($price_cents === 0): ?>Free<?php else: ?>$<?php echo number_format($price_cents / 100, 0); ?><span class="period">one-time</span><?php endif; ?>
                    </span>
                    <span class="price-monthly" style="display:none">
                        <?php if ($monthly_cents === 0): ?>Free<?php else: ?>$<?php echo number_format($monthly_cents / 100, 0); ?><span class="period">/month</span><?php endif; ?>
                    </span>
                </div>
                <div class="price-note">
                    <span class="price-onetime"><?php echo $seats; ?> seat<?php echo $seats > 1 ? 's' : ''; ?> (1 master<?php echo $puppet_seats > 0 ? " + {$puppet_seats} puppet" . ($puppet_seats > 1 ? 's' : '') : ''; ?>)</span>
                    <span class="price-monthly" style="display:none"><?php echo $monthly_cents > 0 ? 'Cancel anytime. Same features.' : 'Free forever.'; ?></span>
                </div>
                <ul class="price-features">
                    <li><span class="check">&#10003;</span> Full local AI assistant</li>
                    <li><span class="check">&#10003;</span> All 59 commands</li>
                    <li><span class="check">&#10003;</span> 9-layer security shield</li>
                    <li><span class="check">&#10003;</span> 14 themes + HUD dashboard</li>
                    <li>
                        <?php if (!empty($t['genome_persistence'])): ?>
                            <span class="check">&#10003;</span> Learning memory (genome)
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Learning memory</span>
                        <?php endif; ?>
                    </li>
                    <li>
                        <?php if (!empty($t['fleet_analytics'])): ?>
                            <span class="check">&#10003;</span> Fleet analytics dashboard
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Fleet analytics</span>
                        <?php endif; ?>
                    </li>
                    <li>
                        <?php if (!empty($t['enterprise_mode'])): ?>
                            <span class="check">&#10003;</span> Enterprise mode + audit export
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Enterprise mode</span>
                        <?php endif; ?>
                    </li>
                    <li>
                        <?php if (!empty($t['genome_sync'])): ?>
                            <span class="check">&#10003;</span> Shared team genome sync
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Team genome sync</span>
                        <?php endif; ?>
                    </li>
                    <li>
                        <?php if (!empty($t['compliance_scenarios'])): ?>
                            <span class="check">&#10003;</span> HIPAA/SOC2 compliance scenarios
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Compliance scenarios</span>
                        <?php endif; ?>
                    </li>
                    <li>
                        <?php if (!empty($t['priority_support'])): ?>
                            <span class="check">&#10003;</span> Priority support SLA
                        <?php else: ?>
                            <span class="x">&#10007;</span> <span class="disabled">Priority support</span>
                        <?php endif; ?>
                    </li>
                </ul>
                <?php if ($price_cents === 0): ?>
                    <a href="docs.php#install" class="btn btn-secondary btn-block">Download Free</a>
                <?php else: ?>
                    <a href="checkout.php?tier=<?php echo $tid; ?>" class="btn btn-primary btn-block price-onetime">Buy <?php echo htmlspecialchars($t['label']); ?></a>
                    <a href="checkout.php?tier=<?php echo $tid; ?>&billing=monthly" class="btn btn-primary btn-block price-monthly" style="display:none">Subscribe <?php echo htmlspecialchars($t['label']); ?></a>
                <?php endif; ?>
            </div>
            <?php endforeach; ?>
        </div>
    </div>
</section>

<!-- ── Roadmap ── -->
<section class="section">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">Roadmap</span>
            <h2>What's Coming</h2>
            <p>Forge is actively developed. Here's what's shipped and what's next.</p>
        </div>
        <div class="roadmap-timeline animate-on-scroll">
            <div class="roadmap-item done">
                <div class="roadmap-phase">Shipped &mdash; v0.5</div>
                <h4>Core AI Engine</h4>
                <p>Local AI execution via Ollama, 28 tools, context management, streaming responses, file editing, shell execution, code search.</p>
            </div>
            <div class="roadmap-item done">
                <div class="roadmap-phase">Shipped &mdash; v0.7</div>
                <h4>Security &amp; Intelligence</h4>
                <p>9-layer Crucible engine, AMI self-healing, Continuity Engine, Forge Genome, forensic audit trail with HMAC-SHA512 provenance chains.</p>
            </div>
            <div class="roadmap-item done">
                <div class="roadmap-phase">Shipped &mdash; v0.8</div>
                <h4>Voice, Themes &amp; Polish</h4>
                <p>Voice I/O (Whisper STT + edge-tts), 14 themes with live effects, Neural Cortex visualization, plugin system, web search, benchmark suite.</p>
            </div>
            <div class="roadmap-item current">
                <div class="roadmap-phase">Current &mdash; v0.9</div>
                <h4>Fleet &amp; Enterprise</h4>
                <p>BPoS licensing (3 tiers), Master/Puppet fleet management, Shipwright release management, AutoForge smart auto-commit, fleet analytics, enterprise audit export.</p>
            </div>
            <div class="roadmap-item future">
                <div class="roadmap-phase">Next &mdash; v1.0</div>
                <h4>Production Release</h4>
                <p>Stripe checkout integration, expanded model catalog, performance optimizations, documentation site, installer packages (Windows/Mac/Linux), stability hardening.</p>
            </div>
            <div class="roadmap-item future">
                <div class="roadmap-phase">Planned &mdash; v1.1+</div>
                <h4>Advanced Intelligence</h4>
                <p>Multi-agent orchestration, project-level memory, cross-session learning improvements, IDE integrations (VS Code, JetBrains), team genome sharing, custom model fine-tuning pipeline.</p>
            </div>
        </div>
    </div>
</section>

<!-- ── FAQ ── -->
<section class="section" id="faq">
    <div class="container">
        <div class="section-header">
            <span class="badge-label">FAQ</span>
            <h2>Common Questions</h2>
        </div>

        <div class="faq-list">
            <div class="faq-item">
                <button class="faq-q">What models does Forge support?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Forge works with any model available through Ollama &mdash; that includes hundreds of open-source AI models ranging from lightweight 3B models to massive 70B+ parameter models. We recommend qwen2.5-coder:14b for most users (needs ~10GB of GPU memory), but the full catalog spans from Qwen2.5-coder:3b on a 4GB card all the way up to Llama 3.3:70b and Qwen2.5-Coder:32b on workstation-class 48GB+ GPUs. Forge automatically profiles your hardware and picks the best model for each task.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Does my code ever leave my machine?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Never. All AI processing runs locally through Ollama on your GPU. The only optional network call is telemetry (disabled by default) which sends anonymized performance stats &mdash; never your source code, prompts, or AI responses. You can audit exactly what's sent with the /export command.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What hardware do I need?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Forge scales across the full GPU range. Entry-level 4&ndash;8GB cards (GTX 1650, RTX 3050) run 3B&ndash;7B models for code completion and quick edits. Mid-range 12&ndash;16GB cards (RTX 3060, 4060, 5070 Ti) handle 14B models &mdash; the sweet spot for most coding tasks. High-end 24GB cards (RTX 4090, 5090) unlock 32B&ndash;34B models for complex reasoning across large codebases. Workstation GPUs with 48GB+ VRAM (RTX A6000, dual GPUs) can run 70B+ parameter models for maximum capability. CPU-only mode is also supported &mdash; slower, but functional. Forge profiles your hardware and optimizes model selection automatically.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What's the difference between Master and Puppet?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">A Master is the license holder &mdash; you. A Puppet is another machine that uses one of your seats. Example: Buy a Pro license (3 seats), and you're the Master on your main desktop. Generate Puppet passports for your laptop and work PC &mdash; they share your license. Revoke any machine anytime.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What is the Neural Cortex?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">The Neural Cortex is Forge's real-time brain visualization. It uses depth-aware Gaussian wave physics to animate a neural pathway image that responds to what the AI is actually doing &mdash; thinking (rainbow chaos), writing code (directional sweep), scanning for threats (red alert), idle (gentle pulse). It's not just eye candy &mdash; it gives you instant visual feedback on the AI's state.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What does the Continuity Grade mean?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">During long sessions, the AI's context window fills up and old information gets swapped out. The Continuity Grade (A-F) tracks 6 signals to measure how much "memory" the AI still has. A = pristine, C = getting fuzzy, F = critical. When it drops, auto-recovery re-reads important files to bring the grade back up.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Is this a subscription?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">It can be, but it doesn't have to be. Every paid tier offers both a one-time purchase (own it forever) and a monthly subscription (cancel anytime). The Community tier is always free. Since the AI runs on your hardware, there are no ongoing server costs for us to pass on.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Can I switch between monthly and one-time?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Yes. If you start with monthly, you can buy the one-time license later and cancel the subscription. If you buy one-time, it's yours forever. Both options get the exact same features for the same tier.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What happens if my monthly subscription lapses?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Forge doesn't stop working. It drops back to Community tier features &mdash; you keep all 59 commands, the full security shield, and local AI execution. What you lose is Pro/Power-tier features: Genome persistence (learning memory resets each session), AutoForge, Shipwright, fleet analytics, and enterprise mode. Your data, projects, and local models are untouched. Resubscribe anytime to restore your tier instantly &mdash; your Genome picks up right where it left off.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">How does the 9-layer security system work?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Every AI response passes through 9 checks: pattern matching (known attacks), semantic analysis (AI detects anomalies), behavioral monitoring (catches exfiltration), canary traps (detects hijacked AI), threat intelligence (auto-updating signatures), command blocklist (49 dangerous patterns), path sandbox (filesystem jail), plan verification (runs your tests), and forensic logging (tamper-proof audit trail). All 9 run locally, in real-time.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Can I use Forge for commercial projects?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Absolutely. Forge generates code locally &mdash; it's no different from writing code yourself. The Community tier works for any project. Pro and Power tiers add fleet management and enterprise features for teams that need compliance and audit trails.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Is Forge suitable for HIPAA / SOC 2 / ITAR environments?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Yes. Since all AI processing happens locally, no data ever touches a third-party server. There's no BAA to sign, no vendor data processing agreement needed, and no export control concerns. The forensic audit trail (HMAC-SHA512) provides tamper-proof logging for compliance audits. The /export command generates ready-to-submit compliance bundles.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">What's included in the free Community tier?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Everything except fleet management and persistence features. You get: full local AI execution, all 59 commands, all 28 registered AI tools, the complete 9-layer security shield, 14 themes with effects, voice I/O, the Neural Cortex visualization, web search, plugin system, benchmarks, and unlimited tokens. Community tier has no time limit, no trial period, and no feature gating on core functionality.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">How does Forge compare in speed to cloud AI tools?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">On a mid-range GPU (RTX 3060 or better), Forge generates tokens at 20&ndash;55 tok/s with sub-200ms latency to first token. No network round-trips means responses start faster than cloud APIs. You'll never hit rate limits, capacity errors, or degraded performance during peak hours. The tradeoff: model size is limited by your GPU VRAM, but 14B models (our recommended default) handle the vast majority of coding tasks.</div>
            </div>
            <div class="faq-item">
                <button class="faq-q">Can I run Forge on a remote server or VM?<span class="faq-arrow">&#9660;</span></button>
                <div class="faq-a">Yes. Forge runs anywhere Python runs. GPU VM instances on AWS, GCP, or Azure work great &mdash; you get cloud GPU power with local-style privacy since Forge doesn't send data to any AI provider. Popular configs: SSH into a GPU VM and run Forge in tmux. The key benefit: your code stays on infrastructure you control, not a third-party AI vendor.</div>
            </div>
        </div>
    </div>
</section>

<!-- ── CTA ── -->
<section class="cta-banner">
    <div class="container" style="position:relative; z-index:1">
        <h2>Ready to take control of your AI?</h2>
        <p>Join developers who run their AI locally. No cloud. No limits. Full control.</p>
        <div class="hero-buttons">
            <a href="#pricing" class="btn btn-primary btn-lg">Get Forge</a>
            <a href="docs.php" class="btn btn-secondary btn-lg">Read the Docs</a>
        </div>
    </div>
</section>

<?php require_once __DIR__ . '/includes/footer.php'; ?>

<script src="assets/cortex.js?v=<?php echo filemtime(__DIR__ . '/assets/cortex.js'); ?>"></script>
<script src="assets/effects.js?v=<?php echo filemtime(__DIR__ . '/assets/effects.js'); ?>"></script>
<script>
// ── Neural Cortex: Hero (auto-cycle) ──
var heroCortex = new NeuralCortex(document.getElementById('hero-cortex'), {
    autoMode: true,
    size: 220,
    scale: 2,
    onStateChange: function(s) {
        var label = document.getElementById('hero-state-label');
        if (label) label.textContent = s.replace('_', ' ');
    }
});

// ── Neural Cortex: Interactive Demo ──
var STATE_DESCS = {
    boot: '<strong>Boot</strong> &mdash; Forge is starting up. Neural pathways initializing with a slow spiral sweep. The brain is loading models, scanning your project, and building context.',
    idle: '<strong>Idle</strong> &mdash; Waiting for your input. Low power, minimal glow. The brain is listening but not processing.',
    thinking: '<strong>Thinking</strong> &mdash; The AI is generating code. Multiple neural pathways firing simultaneously with rainbow hue shifts. This is the highest cognitive load state.',
    tool_exec: '<strong>Executing</strong> &mdash; Writing files or running shell commands. A directional sweep moves across the brain, showing focused activity.',
    indexing: '<strong>Indexing</strong> &mdash; Building a search index of your codebase. Fast radial pulses as the AI processes every file and creates embeddings.',
    swapping: '<strong>Swapping</strong> &mdash; Context window is full. A bright flash signals memory being swapped out and recovered. The Continuity Engine monitors quality during this transition.',
    error: '<strong>Error</strong> &mdash; Something went wrong. A red pulse radiates outward, then decays. Forge logs the error and attempts recovery.',
    threat: '<strong>Threat Detected</strong> &mdash; The security system found something dangerous. Maximum alert: 5 rapid red waves at 20 FPS. The action is blocked instantly.',
    pass: '<strong>Tests Passed</strong> &mdash; All verification checks completed successfully. A calm green radial wave confirms everything is working.'
};

var demoCortex;
var demoObserver = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting && !demoCortex) {
        demoCortex = new NeuralCortex(document.getElementById('demo-cortex'), {
            autoMode: false,
            size: 280,
            scale: 2,
            onStateChange: function(s) {
                document.getElementById('demo-state-label').textContent = s.replace('_', ' ');
                document.getElementById('cortex-desc').innerHTML = STATE_DESCS[s] || '';
                var btns = document.querySelectorAll('.cortex-btn');
                for (var i = 0; i < btns.length; i++) {
                    btns[i].classList.toggle('active', btns[i].getAttribute('data-state') === s);
                }
            }
        });
    }
}, { threshold: 0.2 });
demoObserver.observe(document.getElementById('cortex'));

document.getElementById('cortex-buttons').addEventListener('click', function(e) {
    var btn = e.target.closest('.cortex-btn');
    if (!btn || !demoCortex) return;
    demoCortex.setAutoMode(false);
    demoCortex.setState(btn.getAttribute('data-state'));
});

// ── Persona Tabs ──
var personaTabs = document.getElementById('persona-tabs');
if (personaTabs) {
    personaTabs.addEventListener('click', function(e) {
        var tab = e.target.closest('.persona-tab');
        if (!tab) return;
        var target = tab.getAttribute('data-persona');
        personaTabs.querySelectorAll('.persona-tab').forEach(function(t) { t.classList.remove('active'); });
        tab.classList.add('active');
        document.querySelectorAll('.persona-panel').forEach(function(p) { p.classList.remove('active'); });
        var panel = document.querySelector('[data-persona-panel="' + target + '"]');
        if (panel) panel.classList.add('active');
    });
}

// ── Pricing Toggle ──
function togglePricing() {
    var sw = document.getElementById('pricing-switch');
    var isMonthly = sw.classList.toggle('on');
    document.getElementById('label-onetime').classList.toggle('active', !isMonthly);
    document.getElementById('label-monthly').classList.toggle('active', isMonthly);
    var oneEls = document.querySelectorAll('.price-onetime');
    var moEls = document.querySelectorAll('.price-monthly');
    for (var i = 0; i < oneEls.length; i++) oneEls[i].style.display = isMonthly ? 'none' : '';
    for (var i = 0; i < moEls.length; i++) moEls[i].style.display = isMonthly ? '' : 'none';
}

// ── ROI Calculator ──
function calcROI() {
    var devs = parseInt(document.getElementById('roi-devs').value) || 1;
    var perSeat = parseInt(document.getElementById('roi-cloud').value) || 20;
    var months = parseInt(document.getElementById('roi-months').value) || 24;
    var cloudTotal = devs * perSeat * months;
    var forgeTier = devs <= 1 ? 0 : (devs <= 3 ? 199 : Math.ceil(devs / 10) * 999);
    var savings = cloudTotal - forgeTier;
    var pct = cloudTotal > 0 ? Math.round((savings / cloudTotal) * 100) : 0;
    document.getElementById('roi-cloud-total').textContent = '$' + cloudTotal.toLocaleString();
    document.getElementById('roi-forge-total').textContent = forgeTier === 0 ? 'Free' : '$' + forgeTier.toLocaleString();
    document.getElementById('roi-savings').textContent = '$' + savings.toLocaleString();
    document.getElementById('roi-pct').textContent = pct + '%';
    var breakeven = perSeat > 0 ? Math.ceil(forgeTier / (devs * perSeat)) : 0;
    var verdict = forgeTier === 0 ? 'Forge Community is free. You save $' + cloudTotal.toLocaleString() + ' over ' + months + ' months.'
        : 'Forge pays for itself in ' + (breakeven <= 1 ? 'month 1' : breakeven + ' months') + '. Save $' + savings.toLocaleString() + ' over ' + (months/12) + ' year' + (months > 12 ? 's' : '') + '.';
    document.getElementById('roi-verdict').textContent = verdict;
}
document.getElementById('roi-devs').addEventListener('input', calcROI);
document.getElementById('roi-cloud').addEventListener('change', calcROI);
document.getElementById('roi-months').addEventListener('change', calcROI);
calcROI();

// ── Animated counters for code stats ──
var csObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
        if (!entry.isIntersecting) return;
        var nums = entry.target.querySelectorAll('[data-count]');
        nums.forEach(function(el) {
            if (el.dataset.counted) return;
            el.dataset.counted = '1';
            var target = parseInt(el.dataset.count);
            var suffix = el.dataset.suffix || '';
            var duration = 1200;
            var start = performance.now();
            function tick(now) {
                var t = Math.min((now - start) / duration, 1);
                t = 1 - Math.pow(1 - t, 3);
                el.textContent = Math.round(target * t).toLocaleString() + suffix;
                if (t < 1) requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
    });
}, { threshold: 0.3 });
document.querySelectorAll('.code-stats-grid').forEach(function(g) { csObserver.observe(g); });
</script>
