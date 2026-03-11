<?php
/**
 * Forge — Enterprise Documentation
 */
$page_title = 'Forge — Documentation';
$page_id = 'docs';
require_once __DIR__ . '/includes/header.php';
?>

<div class="sidebar-layout">
    <div class="sidebar">
        <h4>Getting Started</h4>
        <a href="#install">Installation &amp; Setup</a>
        <a href="#requirements">System Requirements</a>
        <a href="#quickstart">Quick Start</a>
        <a href="#models">Choosing a Model</a>

        <h4>Core Features</h4>
        <a href="#commands">Commands (59)</a>
        <a href="#tools">Tool System (28)</a>
        <a href="#routing">Multi-Model Routing</a>
        <a href="#context">Context Management</a>

        <h4>AI Intelligence</h4>
        <a href="#ami">Self-Healing AI (AMI)</a>
        <a href="#continuity">Session Health Monitor</a>
        <a href="#genome">Learning Memory</a>
        <a href="#reliability">Reliability Tracking</a>

        <h4>Security</h4>
        <a href="#security">9-Layer Architecture</a>
        <a href="#safety-levels">Safety Levels</a>
        <a href="#threat-intel">Threat Intelligence</a>
        <a href="#forensics">Forensics &amp; Audit</a>

        <h4>Voice &amp; Interaction</h4>
        <a href="#voice">Voice I/O</a>
        <a href="#themes">Themes &amp; Dashboard</a>
        <a href="#plugins">Plugin System</a>

        <h4>Licensing &amp; Fleet</h4>
        <a href="#licensing">Tiers &amp; Pricing</a>
        <a href="#activation">Activation</a>
        <a href="#fleet">Master/Puppet Fleet</a>
        <a href="#bpos">Behavioral Proof of Stake</a>

        <h4>Advanced</h4>
        <a href="#config">Configuration (97)</a>
        <a href="#enterprise">Enterprise Mode</a>
        <a href="#benchmark">Benchmark Suite</a>
        <a href="#shipwright">Shipwright</a>
        <a href="#autoforge">AutoForge</a>
        <a href="#telemetry">Telemetry</a>
    </div>
    <div class="sidebar-offset"></div>

    <div class="sidebar-content">

        <h1 style="border-bottom:1px solid var(--border); padding-bottom:16px; margin-bottom:8px">Forge Documentation</h1>
        <p style="margin-bottom:32px">Forge is a local AI coding assistant that runs entirely on your hardware. 59 commands, 28 AI tools, 14 themes, 9-layer security, voice I/O, plugin system, and multi-model intelligence &mdash; all offline, all yours.</p>

        <!-- ══════════════ GETTING STARTED ══════════════ -->

        <h2 id="install">Installation &amp; Setup</h2>
        <p><strong>What:</strong> Get Forge running on your machine in under 5 minutes.</p>
        <p><strong>Why:</strong> Everything runs locally. No API keys to manage, no cloud bills, no data leaving your network.</p>

        <h3>Prerequisites</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li>Python 3.10 or newer</li>
            <li><a href="https://ollama.com">Ollama</a> installed and running (handles the AI models)</li>
            <li>GPU with 4GB+ VRAM recommended (see <a href="#requirements">System Requirements</a>)</li>
            <li>Windows 10/11, Linux (Ubuntu 20.04+), or macOS 12+</li>
        </ul>

        <h3>Install Forge</h3>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Clone the repository
git clone https://github.com/yourusername/forge.git
cd forge

# Create virtual environment
python -m venv venv
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt</code></pre>
        </div>

        <h3>Pull Your First Model</h3>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Primary coding model (recommended, ~10GB VRAM)
ollama pull qwen2.5-coder:14b

# Embedding model for semantic search
ollama pull nomic-embed-text</code></pre>
        </div>

        <div class="callout">
            <strong>How it works:</strong> Ollama manages the AI models (downloading, loading, inference). Forge connects to Ollama's local API (localhost:11434) and sends your requests to the model. Nothing leaves your machine.
        </div>

        <!-- ── System Requirements ── -->
        <h2 id="requirements">System Requirements</h2>
        <p><strong>What:</strong> Hardware needed to run Forge at different performance levels.</p>
        <p><strong>Why:</strong> Larger models need more VRAM. This table helps you pick the right model for your hardware.</p>

        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Component</th><th>Minimum</th><th>Recommended</th><th>Optimal</th></tr></thead>
                <tbody>
                    <tr><td><strong>GPU</strong></td><td>4GB VRAM (GTX 1650+)</td><td>12GB+ (RTX 3060/4060)</td><td>16GB+ (RTX 4070 Ti / 5070 Ti)</td></tr>
                    <tr><td><strong>RAM</strong></td><td>8 GB</td><td>16 GB</td><td>32 GB</td></tr>
                    <tr><td><strong>Storage</strong></td><td>10 GB (models)</td><td>20 GB</td><td>50 GB (multiple models)</td></tr>
                    <tr><td><strong>CPU</strong></td><td>Any modern 4-core</td><td>6+ cores</td><td>8+ cores</td></tr>
                    <tr><td><strong>OS</strong></td><td colspan="3">Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+</td></tr>
                </tbody>
            </table>
        </div>

        <p><strong>Model sizes and VRAM requirements:</strong></p>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Model Size</th><th>VRAM (Q4)</th><th>Quality</th><th>Best For</th></tr></thead>
                <tbody>
                    <tr><td>1.5B</td><td>~1.5 GB</td><td>Basic</td><td>Quick questions, simple edits</td></tr>
                    <tr><td>3B</td><td>~2.5 GB</td><td>Good</td><td>Router model, fast classification</td></tr>
                    <tr><td>7B</td><td>~5 GB</td><td>Better</td><td>General coding, 8GB GPU sweet spot</td></tr>
                    <tr><td>14B</td><td>~10 GB</td><td>Excellent</td><td>Complex reasoning, refactoring</td></tr>
                    <tr><td>32B</td><td>~20 GB</td><td>Best</td><td>Hardest problems, architecture design</td></tr>
                </tbody>
            </table>
        </div>
        <p>Forge auto-detects your GPU and recommends the best model for your hardware via <code>/hardware</code>. KV cache quantization (Q8) is enabled by default to maximize context window size.</p>

        <!-- ── Quick Start ── -->
        <h2 id="quickstart">Quick Start</h2>
        <p><strong>What:</strong> Start using Forge in your project right now.</p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Launch Forge in your project directory
cd your-project/
python -m forge</code></pre>
        </div>

        <p>Then just type what you want in plain English:</p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code>forge&gt; Add a login endpoint to the Flask API
forge&gt; Fix the bug in parser.py where it crashes on empty input
forge&gt; Refactor the database module to use connection pooling
forge&gt; Write tests for the authentication middleware</code></pre>
        </div>

        <div class="callout">
            <strong>What happens behind the scenes:</strong> Forge reads your project files, builds context, generates a plan, edits code, runs tests, and tracks every change in a forensic audit trail. Use <code>/pin &lt;file&gt;</code> to keep important files in context permanently.
        </div>

        <!-- ── Models ── -->
        <h2 id="models">Choosing a Model</h2>
        <p><strong>What:</strong> Forge works with any Ollama-compatible model. You can also use OpenAI or Anthropic APIs as backends.</p>
        <p><strong>Why:</strong> Different models have different strengths. Use the router to automatically pick the right model for each task.</p>

        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Model</th><th>VRAM</th><th>Best For</th></tr></thead>
                <tbody>
                    <tr><td><code>qwen2.5-coder:14b</code></td><td>~10 GB</td><td>Primary coding model (best balance of quality + speed)</td></tr>
                    <tr><td><code>qwen2.5-coder:7b</code></td><td>~5 GB</td><td>Good quality on 8GB GPUs</td></tr>
                    <tr><td><code>qwen2.5-coder:3b</code></td><td>~2.5 GB</td><td>Fast router model for task classification</td></tr>
                    <tr><td><code>deepseek-coder-v2:16b</code></td><td>~12 GB</td><td>Strong alternative to Qwen</td></tr>
                    <tr><td><code>nomic-embed-text</code></td><td>~300 MB</td><td>Embeddings for semantic search and indexing</td></tr>
                </tbody>
            </table>
        </div>

        <p><strong>How to configure:</strong></p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># ~/.forge/config.yaml
default_model: "qwen2.5-coder:14b"    # Primary model
small_model: "qwen2.5-coder:3b"       # Fast model for routing
embedding_model: "nomic-embed-text"    # Embeddings
router_enabled: true                   # Auto-route by complexity
backend_provider: "ollama"             # ollama, openai, or anthropic</code></pre>
        </div>

        <p><strong>Model Manager GUI:</strong> Run <code>/models</code> to open the built-in model manager. Browse the Ollama registry, pull new models with progress bars, delete unused models, and set your primary model &mdash; all from a graphical interface.</p>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ CORE FEATURES ══════════════ -->

        <h2 id="commands">Commands Reference</h2>
        <p><strong>What:</strong> 59 slash commands for controlling every aspect of Forge.</p>
        <p><strong>How:</strong> Type any command at the <code>forge&gt;</code> prompt. Click any row below to see a real usage example.</p>

        <input type="text" placeholder="Filter commands..." data-filter-target="cmd-table" style="width:100%; padding:10px 14px; background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius-md); color:var(--text); font-size:0.92em; margin-bottom:16px">

        <style>
            .cmd-row { cursor:pointer; transition: background 0.15s; }
            .cmd-row:hover { background: var(--bg-card-hover) !important; }
            .cmd-row td:first-child::after { content:''; display:inline-block; width:6px; height:6px; border-right:1.5px solid var(--text-dim); border-bottom:1.5px solid var(--text-dim); transform:rotate(-45deg); margin-left:8px; opacity:0; transition:opacity 0.15s; vertical-align:middle; }
            .cmd-row:hover td:first-child::after { opacity:1; }
            .cmd-modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); backdrop-filter:blur(4px); z-index:9000; justify-content:center; align-items:center; animation:cmdFadeIn 0.15s ease; }
            .cmd-modal-overlay.active { display:flex; }
            .cmd-modal { background:var(--bg-card); border:1px solid var(--border-light); border-radius:var(--radius-lg); width:min(680px,92vw); max-height:85vh; overflow-y:auto; box-shadow:0 24px 80px rgba(0,0,0,0.6), 0 0 1px var(--accent-dim); animation:cmdSlideUp 0.2s ease; }
            .cmd-modal-head { display:flex; align-items:center; justify-content:space-between; padding:20px 24px 16px; border-bottom:1px solid var(--border); }
            .cmd-modal-head h3 { margin:0; font-size:1.15em; color:var(--accent); font-family:'JetBrains Mono',monospace; }
            .cmd-modal-close { background:none; border:none; color:var(--text-dim); font-size:1.4em; cursor:pointer; padding:4px 8px; border-radius:var(--radius-sm); transition:color 0.15s, background 0.15s; line-height:1; }
            .cmd-modal-close:hover { color:var(--text); background:rgba(255,255,255,0.06); }
            .cmd-modal-body { padding:24px; }
            .cmd-modal-desc { color:var(--text-dim); font-size:0.92em; margin-bottom:20px; line-height:1.6; }
            .cmd-modal-label { font-size:0.72em; text-transform:uppercase; letter-spacing:1.5px; color:var(--accent-dim); font-weight:600; margin-bottom:8px; }
            .cmd-modal-term { background:var(--bg); border:1px solid var(--border); border-radius:var(--radius-md); padding:16px 20px; font-family:'JetBrains Mono',monospace; font-size:0.88em; line-height:1.7; white-space:pre; overflow-x:auto; margin-bottom:20px; color:var(--text); }
            .cmd-modal-term .prompt { color:var(--accent); }
            .cmd-modal-term .output { color:var(--text-dim); }
            .cmd-modal-term .highlight { color:#4ade80; }
            .cmd-modal-term .warn { color:#f59e0b; }
            .cmd-modal-term .dim { color:#4a5568; }
            .cmd-modal-variants { margin-top:4px; }
            .cmd-modal-variants h4 { font-size:0.82em; color:var(--text-dim); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
            .cmd-modal-variants code { display:inline-block; background:var(--bg); border:1px solid var(--border); padding:3px 10px; border-radius:var(--radius-sm); font-size:0.88em; margin:0 6px 6px 0; color:var(--accent); cursor:pointer; transition:background 0.15s, border-color 0.15s; user-select:none; }
            .cmd-modal-variants code:hover { background:var(--accent-bg); border-color:var(--accent-dim); }
            .cmd-modal-variants code.active { background:var(--accent-bg-strong); border-color:var(--accent); }
            .cmd-modal-tag { display:inline-block; padding:2px 10px; border-radius:var(--radius-full); font-size:0.72em; text-transform:uppercase; letter-spacing:0.8px; font-weight:600; margin-left:12px; }
            .cmd-modal-tag.cat-system { background:rgba(0,212,255,0.12); color:var(--accent); }
            .cmd-modal-tag.cat-model { background:rgba(139,92,246,0.12); color:#a78bfa; }
            .cmd-modal-tag.cat-context { background:rgba(59,130,246,0.12); color:#60a5fa; }
            .cmd-modal-tag.cat-search { background:rgba(16,185,129,0.12); color:#34d399; }
            .cmd-modal-tag.cat-safety { background:rgba(239,68,68,0.12); color:#f87171; }
            .cmd-modal-tag.cat-intel { background:rgba(251,191,36,0.12); color:#fbbf24; }
            .cmd-modal-tag.cat-diag { background:rgba(156,163,175,0.12); color:#9ca3af; }
            .cmd-modal-tag.cat-reliability { background:rgba(34,211,238,0.12); color:#22d3ee; }
            .cmd-modal-tag.cat-fleet { background:rgba(244,114,182,0.12); color:#f472b6; }
            @keyframes cmdFadeIn { from{opacity:0} to{opacity:1} }
            @keyframes cmdSlideUp { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:translateY(0)} }
        </style>

        <div class="table-wrap" style="margin:16px 0" id="cmd-table">
            <table>
                <thead><tr><th style="width:210px">Command</th><th>Description</th></tr></thead>
                <tbody>
                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SYSTEM</td></tr>
                    <tr class="cmd-row" data-cmd="help"><td><code>/help</code></td><td>Show all available commands with descriptions</td></tr>
                    <tr class="cmd-row" data-cmd="docs"><td><code>/docs</code></td><td>Open documentation window (F1 shortcut)</td></tr>
                    <tr class="cmd-row" data-cmd="quit"><td><code>/quit</code> / <code>/exit</code></td><td>Exit Forge with auto-save</td></tr>
                    <tr class="cmd-row" data-cmd="dashboard"><td><code>/dashboard</code></td><td>Open the Neural Cortex HUD dashboard</td></tr>
                    <tr class="cmd-row" data-cmd="voice"><td><code>/voice</code></td><td>Toggle voice input/output modes</td></tr>
                    <tr class="cmd-row" data-cmd="theme"><td><code>/theme &lt;name&gt;</code></td><td>Switch UI theme (14 built-in themes)</td></tr>
                    <tr class="cmd-row" data-cmd="update"><td><code>/update</code></td><td>Check for and apply Forge updates</td></tr>
                    <tr class="cmd-row" data-cmd="cd"><td><code>/cd &lt;dir&gt;</code></td><td>Change working directory</td></tr>
                    <tr class="cmd-row" data-cmd="plugins"><td><code>/plugins</code></td><td>List loaded plugins and their status</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">MODEL &amp; TOOLS</td></tr>
                    <tr class="cmd-row" data-cmd="model"><td><code>/model &lt;name&gt;</code></td><td>Show or switch the active AI model</td></tr>
                    <tr class="cmd-row" data-cmd="models"><td><code>/models</code></td><td>Open Model Manager GUI (pull, delete, browse)</td></tr>
                    <tr class="cmd-row" data-cmd="tools"><td><code>/tools</code></td><td>List all 28 registered AI tools with call stats</td></tr>
                    <tr class="cmd-row" data-cmd="router"><td><code>/router</code></td><td>Multi-model routing status and controls</td></tr>
                    <tr class="cmd-row" data-cmd="compare"><td><code>/compare</code></td><td>Compare Forge costs against cloud providers</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">CONTEXT &amp; MEMORY</td></tr>
                    <tr class="cmd-row" data-cmd="context"><td><code>/context</code></td><td>Show context window usage with token breakdown</td></tr>
                    <tr class="cmd-row" data-cmd="pin"><td><code>/pin &lt;idx&gt;</code></td><td>Pin a context entry so it survives eviction</td></tr>
                    <tr class="cmd-row" data-cmd="unpin"><td><code>/unpin &lt;idx&gt;</code></td><td>Remove pin from a context entry</td></tr>
                    <tr class="cmd-row" data-cmd="drop"><td><code>/drop &lt;idx&gt;</code></td><td>Manually evict a context entry to free tokens</td></tr>
                    <tr class="cmd-row" data-cmd="clear"><td><code>/clear</code></td><td>Clear all non-pinned context entries</td></tr>
                    <tr class="cmd-row" data-cmd="save"><td><code>/save &lt;file&gt;</code></td><td>Save entire session to file</td></tr>
                    <tr class="cmd-row" data-cmd="load"><td><code>/load &lt;file&gt;</code></td><td>Restore a previously saved session</td></tr>
                    <tr class="cmd-row" data-cmd="reset"><td><code>/reset</code></td><td>Hard reset &mdash; clear everything and start fresh</td></tr>
                    <tr class="cmd-row" data-cmd="memory"><td><code>/memory</code></td><td>Show all memory subsystem status</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SEARCH &amp; INDEXING</td></tr>
                    <tr class="cmd-row" data-cmd="scan"><td><code>/scan &lt;path&gt;</code></td><td>Scan codebase structure (classes, functions, routes)</td></tr>
                    <tr class="cmd-row" data-cmd="index"><td><code>/index</code></td><td>Build or rebuild the semantic embedding index</td></tr>
                    <tr class="cmd-row" data-cmd="search"><td><code>/search &lt;query&gt;</code></td><td>Quick semantic search (file list)</td></tr>
                    <tr class="cmd-row" data-cmd="journal"><td><code>/journal</code></td><td>Show last N journal entries</td></tr>
                    <tr class="cmd-row" data-cmd="recall"><td><code>/recall &lt;query&gt;</code></td><td>Semantic code search with previews</td></tr>
                    <tr class="cmd-row" data-cmd="digest"><td><code>/digest</code></td><td>AST analysis and code structure breakdown</td></tr>
                    <tr class="cmd-row" data-cmd="synapse"><td><code>/synapse</code></td><td>Run synapse check &mdash; cycle all Neural Cortex modes</td></tr>
                    <tr class="cmd-row" data-cmd="tasks"><td><code>/tasks</code></td><td>Show task state and progress</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SAFETY &amp; SECURITY</td></tr>
                    <tr class="cmd-row" data-cmd="safety"><td><code>/safety</code></td><td>Show or set safety level and sandbox status</td></tr>
                    <tr class="cmd-row" data-cmd="crucible"><td><code>/crucible</code></td><td>4-layer threat scanner status and controls</td></tr>
                    <tr class="cmd-row" data-cmd="forensics"><td><code>/forensics</code></td><td>View forensic audit trail for current session</td></tr>
                    <tr class="cmd-row" data-cmd="threats"><td><code>/threats</code></td><td>View threat intelligence patterns and rules</td></tr>
                    <tr class="cmd-row" data-cmd="provenance"><td><code>/provenance</code></td><td>View tool-call provenance chain</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">PLANNING &amp; QUALITY</td></tr>
                    <tr class="cmd-row" data-cmd="plan"><td><code>/plan</code></td><td>Multi-step plan mode with verification gates</td></tr>
                    <tr class="cmd-row" data-cmd="dedup"><td><code>/dedup</code></td><td>Response deduplication status and threshold</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">AI INTELLIGENCE</td></tr>
                    <tr class="cmd-row" data-cmd="ami"><td><code>/ami</code></td><td>AI model intelligence: quality, capabilities, recovery</td></tr>
                    <tr class="cmd-row" data-cmd="continuity"><td><code>/continuity</code></td><td>Session health grade (A-F) with signal breakdown</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">DIAGNOSTICS &amp; BILLING</td></tr>
                    <tr class="cmd-row" data-cmd="stats"><td><code>/stats</code></td><td>Full analytics: performance, tools, cost</td></tr>
                    <tr class="cmd-row" data-cmd="billing"><td><code>/billing</code></td><td>Token usage and cost tracking</td></tr>
                    <tr class="cmd-row" data-cmd="topup"><td><code>/topup</code></td><td>Add sandbox funds (default: $50)</td></tr>
                    <tr class="cmd-row" data-cmd="report"><td><code>/report</code></td><td>File a bug report to GitHub</td></tr>
                    <tr class="cmd-row" data-cmd="export"><td><code>/export</code></td><td>Export audit bundle (zip with SHA-256 manifest)</td></tr>
                    <tr class="cmd-row" data-cmd="benchmark"><td><code>/benchmark</code></td><td>Run reproducible coding benchmarks</td></tr>
                    <tr class="cmd-row" data-cmd="hardware"><td><code>/hardware</code></td><td>Show GPU, CPU, VRAM, and model recommendation</td></tr>
                    <tr class="cmd-row" data-cmd="cache"><td><code>/cache</code></td><td>File read cache statistics and management</td></tr>
                    <tr class="cmd-row" data-cmd="config"><td><code>/config</code></td><td>View or edit configuration</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">RELIABILITY &amp; ASSURANCE</td></tr>
                    <tr class="cmd-row" data-cmd="break"><td><code>/break</code></td><td>Run Forge Break Suite (reliability + fingerprint)</td></tr>
                    <tr class="cmd-row" data-cmd="autopsy"><td><code>/autopsy</code></td><td>Break suite with detailed failure-mode analysis</td></tr>
                    <tr class="cmd-row" data-cmd="stress"><td><code>/stress</code></td><td>Minimal 3-scenario stress suite (CI-compatible)</td></tr>
                    <tr class="cmd-row" data-cmd="assure"><td><code>/assure</code></td><td>Run full AI assurance scenario suite</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">RELEASE &amp; LICENSING</td></tr>
                    <tr class="cmd-row" data-cmd="ship"><td><code>/ship</code></td><td>Shipwright release management</td></tr>
                    <tr class="cmd-row" data-cmd="autocommit"><td><code>/autocommit</code></td><td>Smart auto-commit with AI-generated messages</td></tr>
                    <tr class="cmd-row" data-cmd="license"><td><code>/license</code></td><td>View license tier, features, and genome</td></tr>

                    <tr><td colspan="2" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">FLEET &amp; ADMIN</td></tr>
                    <tr class="cmd-row" data-cmd="puppet"><td><code>/puppet</code></td><td>Fleet puppet passport management</td></tr>
                    <tr class="cmd-row" data-cmd="admin"><td><code>/admin</code></td><td>GitHub collaborator and token management</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Command Detail Modal -->
        <div class="cmd-modal-overlay" id="cmdModal">
            <div class="cmd-modal">
                <div class="cmd-modal-head">
                    <h3 id="cmdModalTitle">/command</h3>
                    <span id="cmdModalTag" class="cmd-modal-tag"></span>
                    <button class="cmd-modal-close" id="cmdModalClose">&times;</button>
                </div>
                <div class="cmd-modal-body">
                    <div class="cmd-modal-desc" id="cmdModalDesc"></div>
                    <div class="cmd-modal-label">Example Session</div>
                    <div class="cmd-modal-term" id="cmdModalTerm"></div>
                    <div class="cmd-modal-variants" id="cmdModalVariants"></div>
                </div>
            </div>
        </div>

        <script>
        (function(){
            var CMD = {
                help: {
                    cat: 'system', desc: 'Lists every slash command organized by category with a short description. This is the quickest way to discover what Forge can do.',
                    term: '<span class="prompt">forge&gt;</span> /help\n\n<span class="dim">Context Management:</span>\n  <span class="highlight">/context</span>          Show detailed context window status\n  <span class="highlight">/drop N</span>            Drop context entry at index N\n  <span class="highlight">/pin N</span>             Pin entry (survives eviction)\n  ...\n\n<span class="dim">Model &amp; Tools:</span>\n  <span class="highlight">/model [name]</span>      Show or switch model\n  <span class="highlight">/models</span>            List available Ollama models\n  <span class="highlight">/tools</span>             List available tools\n  ...\n\n<span class="dim">59 commands across 12 categories.</span>\n<span class="dim">Everything else is sent to the AI.</span>',
                    variants: []
                },
                docs: {
                    cat: 'system', desc: 'Opens the built-in documentation window. Also available via the F1 keyboard shortcut. Provides searchable, categorized access to all Forge features without leaving the application.',
                    term: '<span class="prompt">forge&gt;</span> /docs\n<span class="output">Documentation window opened.</span>',
                    variants: []
                },
                quit: {
                    cat: 'system', desc: 'Gracefully exits Forge. Session state is auto-saved so you can resume later with /load. The /exit alias does the same thing.',
                    term: '<span class="prompt">forge&gt;</span> /quit\n<span class="output">Session auto-saved to ~/.forge/session.json</span>\n<span class="output">Goodbye.</span>',
                    variants: ['/exit']
                },
                dashboard: {
                    cat: 'system', desc: 'Launches the Neural Cortex GUI dashboard. Shows real-time brain animation, performance cards (tokens/sec, context usage, continuity grade), threat alerts, and session timeline. The dashboard updates live during AI interactions.',
                    term: '<span class="prompt">forge&gt;</span> /dashboard\n<span class="output">Neural Cortex dashboard opened.</span>\n<span class="dim">[GUI window appears with live brain animation,</span>\n<span class="dim"> performance cards, and session timeline]</span>',
                    variants: []
                },
                voice: {
                    cat: 'system', desc: 'Controls voice input modes. Push-to-talk (hold backtick key) or VOX (voice-activated, auto-detects when you speak). Requires the voice extras: pip install forge[voice].',
                    term: '<span class="prompt">forge&gt;</span> /voice ptt\n<span class="output">Voice input: push-to-talk mode</span>\n<span class="output">Hold ` (backtick) to speak. Release to send.</span>\n\n<span class="prompt">forge&gt;</span> /voice vox\n<span class="output">Voice input: VOX mode (auto-detect)</span>\n<span class="output">Speak naturally. Silence &gt; 1.5s sends input.</span>\n\n<span class="prompt">forge&gt;</span> /voice off\n<span class="output">Voice input disabled.</span>',
                    variants: ['/voice ptt', '/voice vox', '/voice off']
                },
                theme: {
                    cat: 'system', desc: 'Switches the terminal color theme. 14 built-in themes, 3 with animated effects (cyberpunk, matrix, phosphor). Hot-swaps instantly without restart.',
                    term: '<span class="prompt">forge&gt;</span> /theme\n<span class="output">Available themes:</span>\n  <span class="highlight">midnight</span>  obsidian  dracula  solarized_dark\n  nord  monokai  <span class="highlight">cyberpunk</span>  matrix  amber\n  phosphor  arctic  sunset  <span class="highlight">neon</span>  hologram\n<span class="dim">Current: midnight</span>\n\n<span class="prompt">forge&gt;</span> /theme cyberpunk\n<span class="output">Theme switched to cyberpunk.</span>',
                    variants: ['/theme', '/theme &lt;name&gt;']
                },
                update: {
                    cat: 'system', desc: 'Checks GitHub for new Forge releases. Shows what changed and lets you apply the update. Uses git pull --ff-only (safe, no merge conflicts). If pyproject.toml changed, dependencies are auto-reinstalled.',
                    term: '<span class="prompt">forge&gt;</span> /update\n<span class="output">Current version: v0.9.0</span>\n<span class="output">Latest version:  v0.9.1</span>\n<span class="output">3 commits behind:</span>\n  <span class="highlight">fix:</span> context swap preserves pinned entry order\n  <span class="highlight">feat:</span> /break --share uploads signed report\n  <span class="highlight">docs:</span> update command reference\n\n<span class="output">Run /update --yes to apply.</span>\n\n<span class="prompt">forge&gt;</span> /update --yes\n<span class="output">Pulling updates...</span>\n<span class="highlight">Updated to v0.9.1 (3 commits applied).</span>',
                    variants: ['/update', '/update --yes']
                },
                cd: {
                    cat: 'system', desc: 'Changes Forge\'s working directory. All file operations, scans, and tool calls will use the new directory. Useful when working across multiple projects in one session.',
                    term: '<span class="prompt">forge&gt;</span> /cd ../my-api\n<span class="output">Working directory: /home/dev/my-api</span>\n<span class="dim">12 Python files, 3 JS files indexed.</span>',
                    variants: []
                },
                plugins: {
                    cat: 'system', desc: 'Shows all loaded plugins with their status (active, disabled, errored). Plugins are Python files dropped into ~/.forge/plugins/. Auto-disabled after 5 consecutive errors to prevent cascading failures.',
                    term: '<span class="prompt">forge&gt;</span> /plugins\n<span class="output">Loaded plugins:</span>\n  <span class="highlight">[active]</span>  Auto Lint v1.0 — runs linter on file changes\n  <span class="highlight">[active]</span>  Forge Telemetry v1.0 — session telemetry\n  <span class="warn">[error]</span>   My Plugin v0.1 — 3/5 errors (will auto-disable at 5)\n<span class="dim">Plugin directory: ~/.forge/plugins/</span>',
                    variants: []
                },
                model: {
                    cat: 'model', desc: 'Shows the currently active model, or switches to a different one. The new model must be available in your local Ollama instance. Token counting and billing adjust automatically for the new model.',
                    term: '<span class="prompt">forge&gt;</span> /model\n<span class="output">Current model: qwen2.5-coder:14b</span>\n<span class="dim">Parameters: 14B  Context: 32,768  Quantization: Q4_K_M</span>\n\n<span class="prompt">forge&gt;</span> /model qwen2.5-coder:7b\n<span class="output">Switched to qwen2.5-coder:7b</span>\n<span class="dim">Parameters: 7B  Context: 32,768  VRAM: ~5.2 GB</span>',
                    variants: ['/model', '/model &lt;name&gt;']
                },
                models: {
                    cat: 'model', desc: 'Opens the Model Manager GUI. Browse all models available in Ollama, see VRAM requirements, pull new models, or delete unused ones. Shows which models fit your GPU.',
                    term: '<span class="prompt">forge&gt;</span> /models\n<span class="output">Opening Model Manager...</span>\n<span class="dim">[GUI window with model cards showing size, VRAM,</span>\n<span class="dim"> quantization, and pull/delete buttons]</span>',
                    variants: []
                },
                tools: {
                    cat: 'model', desc: 'Lists all 27 AI tools registered in the engine with per-tool call counts and timing stats for the current session. Useful for understanding which tools the AI uses most.',
                    term: '<span class="prompt">forge&gt;</span> /tools\n<span class="output">28 tools registered:</span>\n  <span class="highlight">read_file</span>        47 calls   avg 12ms\n  <span class="highlight">edit_file</span>        23 calls   avg 8ms\n  <span class="highlight">run_shell</span>        11 calls   avg 340ms\n  <span class="highlight">grep_files</span>        9 calls   avg 45ms\n  <span class="highlight">write_file</span>        6 calls   avg 15ms\n  <span class="dim">... 22 more tools (0 calls this session)</span>',
                    variants: []
                },
                router: {
                    cat: 'model', desc: 'Shows the multi-model router status. When enabled, simple tasks (greetings, short questions) route to a smaller, faster model, while complex tasks (code generation, analysis) route to the primary model. Saves tokens without sacrificing quality.',
                    term: '<span class="prompt">forge&gt;</span> /router\n<span class="output">Multi-Model Router: <span class="highlight">ENABLED</span></span>\n  Primary: qwen2.5-coder:14b\n  Small:   qwen2.5-coder:3b\n  Threshold: 0.6\n<span class="output">This session:</span>\n  Routed to primary: 12 turns\n  Routed to small:    8 turns\n  <span class="highlight">Tokens saved: ~14,200</span>\n\n<span class="prompt">forge&gt;</span> /router off\n<span class="output">Router disabled. All tasks use primary model.</span>',
                    variants: ['/router', '/router on|off', '/router big &lt;model&gt;', '/router small &lt;model&gt;']
                },
                compare: {
                    cat: 'model', desc: 'Shows a cost comparison between running Forge locally versus using cloud AI providers (Claude, GPT-4, Gemini). Based on your actual token usage this session.',
                    term: '<span class="prompt">forge&gt;</span> /compare\n<span class="output">Cost Comparison (this session: 142,800 tokens)</span>\n\n  <span class="highlight">Forge (local)</span>     $0.00\n  Claude Sonnet     $1.28\n  GPT-4o            $0.93\n  Gemini Pro        $0.71\n\n<span class="dim">Based on actual prompt + completion tokens.</span>\n<span class="highlight">You saved $1.28 vs. the nearest cloud provider.</span>',
                    variants: []
                },
                context: {
                    cat: 'context', desc: 'Shows detailed context window status: total tokens used, percentage full, per-partition breakdown (system, user, assistant, tool), and eviction history. This is how you monitor whether a context swap is approaching.',
                    term: '<span class="prompt">forge&gt;</span> /context\n<span class="output">Context Window: 18,432 / 32,768 tokens (<span class="warn">56.3%</span>)</span>\n<span class="output">  [==============              ] 56.3%</span>\n\n  #  Role       Tag          Tokens  Pin\n  0  <span class="highlight">system</span>     system        1,240   *\n  1  user       user            380\n  2  assistant  response      2,100\n  3  tool       file_read       890\n  4  user       user            210\n  ...\n\n<span class="dim">Token usage by type:</span>\n  system                  1,240 tokens\n  user                    3,420 tokens\n  assistant              11,200 tokens\n  tool                    2,572 tokens',
                    variants: []
                },
                pin: {
                    cat: 'context', desc: 'Pins a context entry by index so it survives automatic eviction. Pinned entries stay in the context window even when the swap threshold is hit. Use /context to see entry indices.',
                    term: '<span class="prompt">forge&gt;</span> /context\n<span class="dim">  3  tool  file_read  890 tokens</span>\n\n<span class="prompt">forge&gt;</span> /pin 3\n<span class="output">Pinned entry 3</span>\n<span class="dim">This entry will survive context swaps.</span>',
                    variants: []
                },
                unpin: {
                    cat: 'context', desc: 'Removes the pin from a context entry, allowing it to be evicted during the next context swap if needed.',
                    term: '<span class="prompt">forge&gt;</span> /unpin 3\n<span class="output">Unpinned entry 3</span>',
                    variants: []
                },
                drop: {
                    cat: 'context', desc: 'Manually evicts a specific context entry to free tokens. Use this when you know a particular entry is no longer relevant and you want to reclaim space before an automatic swap.',
                    term: '<span class="prompt">forge&gt;</span> /context\n<span class="dim">  5  assistant  response  3,200 tokens  (old analysis)</span>\n\n<span class="prompt">forge&gt;</span> /drop 5\n<span class="output">Dropped entry 5: [assistant] 3,200 tokens freed</span>\n<span class="output">Context: 15,232 / 32,768 (46.5%)</span>',
                    variants: []
                },
                clear: {
                    cat: 'context', desc: 'Clears all non-pinned context entries. The system prompt and any pinned entries survive. Good for starting a new task without a full /reset.',
                    term: '<span class="prompt">forge&gt;</span> /clear\n<span class="output">Cleared 14 entries</span>\n<span class="output">Context: 1,240 / 32,768 (3.8%)</span>\n<span class="dim">System prompt and 1 pinned entry preserved.</span>',
                    variants: []
                },
                save: {
                    cat: 'context', desc: 'Saves the entire session to a JSON file with full fidelity &mdash; context entries, metadata, turn count, billing state. Restore later with /load.',
                    term: '<span class="prompt">forge&gt;</span> /save refactor-session\n<span class="output">Session saved to ~/.forge/sessions/refactor-session.json</span>\n<span class="dim">22 entries, 18,432 tokens, 15 turns preserved.</span>',
                    variants: []
                },
                load: {
                    cat: 'context', desc: 'Restores a previously saved session. All context entries, turn history, and metadata are loaded back. The current session is replaced.',
                    term: '<span class="prompt">forge&gt;</span> /load refactor-session\n<span class="output">Loaded 22 entries from refactor-session.json</span>\n<span class="output">Context: 18,432 / 32,768 (56.3%)</span>',
                    variants: []
                },
                reset: {
                    cat: 'context', desc: 'Hard reset: clears all context entries (including pinned), resets turn counter and billing for this session. Equivalent to starting a completely new session.',
                    term: '<span class="prompt">forge&gt;</span> /reset\n<span class="output">Session reset. Context cleared, turn count zeroed.</span>\n<span class="output">Context: 1,240 / 32,768 (3.8%)</span>',
                    variants: []
                },
                memory: {
                    cat: 'context', desc: 'Shows the status of all memory subsystems: episodic memory (long-term recall), journal entries, codebase index, and the Forge Genome (accumulated intelligence across sessions).',
                    term: '<span class="prompt">forge&gt;</span> /memory\n<span class="output">Memory Subsystems:</span>\n  <span class="highlight">Episodic</span>    142 memories  (embeddings: nomic-embed-text)\n  <span class="highlight">Journal</span>      38 entries   (last 7 days)\n  <span class="highlight">Index</span>       891 files    (last built: 2h ago)\n  <span class="highlight">Genome</span>       12 sessions  (maturity: 34%)',
                    variants: []
                },
                scan: {
                    cat: 'search', desc: 'Deep-scans a directory using tree-sitter AST parsing. Extracts classes, functions, routes, database tables, imports, and structural patterns across 8+ languages. Results feed into the AI\'s understanding of your codebase.',
                    term: '<span class="prompt">forge&gt;</span> /scan src/\n<span class="output">Scanning src/ ...</span>\n<span class="output">Found:</span>\n  <span class="highlight">47</span> Python files\n  <span class="highlight">12</span> classes, <span class="highlight">89</span> functions\n  <span class="highlight">3</span> Flask routes, <span class="highlight">2</span> database models\n  <span class="highlight">156</span> imports\n<span class="dim">Results added to context (1,200 tokens).</span>',
                    variants: ['/scan', '/scan &lt;path&gt;', '/scan force']
                },
                index: {
                    cat: 'search', desc: 'Builds or rebuilds the semantic embedding index for codebase search. Processes all files in the working directory through the embedding model. Enables /search and /recall to find code by meaning, not just text.',
                    term: '<span class="prompt">forge&gt;</span> /index\n<span class="output">Indexing codebase...</span>\n  Processing: 891 files\n  Embedding model: nomic-embed-text\n<span class="highlight">Index built: 891 files, 4,230 chunks</span>\n<span class="dim">Use /search or /recall to query.</span>',
                    variants: ['/index', '/index &lt;path&gt;']
                },
                search: {
                    cat: 'search', desc: 'Quick semantic search across the indexed codebase. Returns a ranked list of matching files. Faster than /recall but shows less detail.',
                    term: '<span class="prompt">forge&gt;</span> /search "authentication middleware"\n<span class="output">Search results (top 5):</span>\n  <span class="highlight">0.94</span>  src/auth/middleware.py\n  <span class="highlight">0.87</span>  src/auth/jwt_handler.py\n  <span class="highlight">0.82</span>  src/routes/login.py\n  <span class="highlight">0.71</span>  tests/test_auth.py\n  <span class="highlight">0.68</span>  src/config/security.py',
                    variants: []
                },
                journal: {
                    cat: 'search', desc: 'Shows recent journal entries &mdash; automatic logs of what Forge did each session. Useful for reviewing what happened in past sessions.',
                    term: '<span class="prompt">forge&gt;</span> /journal 5\n<span class="output">Last 5 journal entries:</span>\n  <span class="dim">2026-03-07 14:23</span>  Refactored auth module (3 files edited)\n  <span class="dim">2026-03-07 10:11</span>  Fixed billing roundtrip bug\n  <span class="dim">2026-03-06 16:45</span>  Added /stress command\n  <span class="dim">2026-03-06 09:30</span>  Context swap quality: B+\n  <span class="dim">2026-03-05 22:15</span>  Assurance suite: 100% pass',
                    variants: ['/journal', '/journal &lt;N&gt;']
                },
                recall: {
                    cat: 'search', desc: 'Semantic code search with previews. Like /search but shows code snippets from matching files, making it easier to find the exact function or class you need.',
                    term: '<span class="prompt">forge&gt;</span> /recall database connection pooling\n<span class="output">Top matches:</span>\n\n  <span class="highlight">src/db/pool.py</span> (0.93)\n  <span class="dim">class ConnectionPool:</span>\n  <span class="dim">    def acquire(self, timeout=30):</span>\n  <span class="dim">        \"\"\"Get a connection from the pool...\"\"\"</span>\n\n  <span class="highlight">src/db/config.py</span> (0.85)\n  <span class="dim">POOL_SIZE = int(os.getenv(\"DB_POOL_SIZE\", 10))</span>',
                    variants: []
                },
                digest: {
                    cat: 'search', desc: 'Shows a structural breakdown of your codebase using tree-sitter AST analysis. For a specific file, shows all functions, classes, imports, and their relationships.',
                    term: '<span class="prompt">forge&gt;</span> /digest\n<span class="output">Codebase Digest:</span>\n  Files: 131    Lines: 58,200    Languages: 2\n  Classes: 89   Functions: 1,247  Imports: 2,340\n\n<span class="prompt">forge&gt;</span> /digest forge/engine.py\n<span class="output">forge/engine.py (3,287 lines)</span>\n  <span class="highlight">class ForgeEngine</span>\n    __init__, run, _agent_loop, _process_tool_calls\n    _cached_read_file, _cached_write_file, ...\n  <span class="dim">42 methods, 12 imports, 3 constants</span>',
                    variants: ['/digest', '/digest &lt;file&gt;']
                },
                synapse: {
                    cat: 'search', desc: 'Runs a synapse check &mdash; cycles through all Neural Cortex display modes to verify the GUI subsystem is working correctly. A diagnostic tool for the dashboard.',
                    term: '<span class="prompt">forge&gt;</span> /synapse\n<span class="output">Synapse check:</span>\n  <span class="highlight">[OK]</span> Idle state\n  <span class="highlight">[OK]</span> Thinking animation\n  <span class="highlight">[OK]</span> Threat alert mode\n  <span class="highlight">[OK]</span> Context pressure mode\n  <span class="highlight">[OK]</span> Success animation\n<span class="output">All 5 cortex modes passed.</span>',
                    variants: []
                },
                tasks: {
                    cat: 'search', desc: 'Shows the current task list and progress. Tasks are created automatically when the AI works on multi-step operations, or manually via plan mode.',
                    term: '<span class="prompt">forge&gt;</span> /tasks\n<span class="output">Active tasks:</span>\n  <span class="highlight">[2/5]</span> Refactor auth module\n    <span class="highlight">[done]</span> Extract JWT logic\n    <span class="highlight">[done]</span> Create middleware class\n    <span class="warn">[wip]</span>  Update route handlers\n    <span class="dim">[todo]</span> Write tests\n    <span class="dim">[todo]</span> Update docs',
                    variants: []
                },
                safety: {
                    cat: 'safety', desc: 'Shows or sets the safety level. Four tiers control what the AI can do: unleashed (no restrictions), smart_guard (blocks dangerous commands), confirm_writes (asks before file changes), locked_down (read-only). Also controls filesystem sandboxing.',
                    term: '<span class="prompt">forge&gt;</span> /safety\n<span class="output">Safety Level: <span class="highlight">smart_guard</span> (1)</span>\n  Sandbox: <span class="highlight">enabled</span>\n  Allowed paths: /home/dev/project, /tmp\n\n<span class="prompt">forge&gt;</span> /safety confirm_writes\n<span class="output">Safety level set to confirm_writes (2)</span>\n<span class="dim">AI will ask before modifying any file.</span>\n\n<span class="prompt">forge&gt;</span> /safety sandbox off\n<span class="output">Filesystem sandbox disabled.</span>\n<span class="warn">Warning: AI can now access any path.</span>',
                    variants: ['/safety', '/safety &lt;level&gt;', '/safety sandbox on|off', '/safety allow &lt;path&gt;']
                },
                crucible: {
                    cat: 'safety', desc: 'Shows Crucible security scanner status and detection statistics. Four detection layers: static patterns, zero-width Unicode, encoded payloads, and behavioral tripwires. Every message passes through Crucible in under 50ms.',
                    term: '<span class="prompt">forge&gt;</span> /crucible\n<span class="output">Crucible Security Scanner: <span class="highlight">ACTIVE</span></span>\n  Static patterns:    247 rules\n  Zero-width detect:  enabled\n  Payload decoder:    enabled\n  Behavioral trips:   enabled\n<span class="output">This session:</span>\n  Scans: 142     Threats: 0\n  Avg latency: 8ms\n  <span class="highlight">Canary: INTACT</span>\n\n<span class="prompt">forge&gt;</span> /crucible log\n<span class="output">No threats detected this session.</span>',
                    variants: ['/crucible', '/crucible on|off', '/crucible log', '/crucible canary']
                },
                forensics: {
                    cat: 'safety', desc: 'Shows the forensic audit trail for the current session. Every tool call, threat event, context swap, and model switch is recorded with timestamps, arguments, and results.',
                    term: '<span class="prompt">forge&gt;</span> /forensics\n<span class="output">Session Forensics (15 turns, 42 events)</span>\n  Tool calls:     38\n  Threat events:   0\n  Context swaps:   1\n  Model switches:  2\n\n<span class="output">Last 5 events:</span>\n  <span class="dim">14:23:01</span>  tool:edit_file  forge/commands.py  <span class="highlight">OK</span>\n  <span class="dim">14:22:58</span>  tool:read_file  forge/commands.py  <span class="highlight">OK</span>\n  <span class="dim">14:22:45</span>  tool:grep_files pattern=def.*cmd   <span class="highlight">OK</span>\n  ...\n\n<span class="prompt">forge&gt;</span> /forensics save\n<span class="output">Forensics report saved to ~/.forge/forensics/session_abc123.json</span>',
                    variants: ['/forensics', '/forensics save']
                },
                threats: {
                    cat: 'safety', desc: 'Shows threat intelligence status: how many detection patterns are loaded (hardcoded + external), keyword lists, behavioral rules, and signature version. External signatures can be updated from a remote feed.',
                    term: '<span class="prompt">forge&gt;</span> /threats\n<span class="output">Threat Intelligence</span>\n  Status:      <span class="highlight">ACTIVE</span>\n  Patterns:    187 hardcoded + 60 external (247 total)\n  Keywords:    4 lists (312 terms)\n  Behavioral:  8 rules\n  Version:     2026.03.07\n  Last update: 2h ago',
                    variants: []
                },
                provenance: {
                    cat: 'safety', desc: 'Shows the cryptographic provenance chain &mdash; a tamper-evident log of every tool call with SHA-256 hashes. Each entry links to the previous one, forming a blockchain-like chain. If any entry is modified, the chain breaks.',
                    term: '<span class="prompt">forge&gt;</span> /provenance\n<span class="output">Provenance Chain (38 entries)</span>\n  Chain integrity: <span class="highlight">VALID</span>\n\n  <span class="dim">#37</span>  edit_file  forge/commands.py\n       <span class="dim">hash: a7f2c...</span>  <span class="dim">prev: 9e3b1...</span>\n  <span class="dim">#36</span>  read_file  forge/commands.py\n       <span class="dim">hash: 9e3b1...</span>  <span class="dim">prev: 4d8a0...</span>\n  ...',
                    variants: []
                },
                plan: {
                    cat: 'safety', desc: 'Controls multi-step plan mode. When enabled, complex tasks are broken into steps with optional verification (tests, linting) between each step. Modes: off, manual, auto (triggers on complex tasks), always.',
                    term: '<span class="prompt">forge&gt;</span> /plan\n<span class="output">Plan Mode: <span class="dim">off</span></span>\n\n<span class="prompt">forge&gt;</span> /plan auto\n<span class="output">Plan mode: auto (threshold: 0.6)</span>\n<span class="dim">Complex tasks will generate a plan before execution.</span>\n\n<span class="prompt">forge&gt;</span> /plan verify\n<span class="output">Plan Verification</span>\n  Mode:     report\n  Tests:    on\n  Lint:     on\n  Timeout:  30s\n\n<span class="prompt">forge&gt;</span> /plan verify strict\n<span class="output">Plan verification: strict</span>\n<span class="dim">Each step must pass tests before proceeding.</span>',
                    variants: ['/plan', '/plan on|off', '/plan auto', '/plan always', '/plan verify [off|report|repair|strict]']
                },
                dedup: {
                    cat: 'safety', desc: 'Controls response deduplication. When enabled, Forge detects when the AI produces duplicate or near-duplicate tool calls and suppresses them. Adjustable similarity threshold.',
                    term: '<span class="prompt">forge&gt;</span> /dedup\n<span class="output">Deduplication: <span class="highlight">enabled</span></span>\n  Threshold: 85%\n  Suppressed this session: 3\n\n<span class="prompt">forge&gt;</span> /dedup threshold 0.9\n<span class="output">Dedup threshold set to 90%</span>\n<span class="dim">Only near-exact duplicates will be suppressed.</span>',
                    variants: ['/dedup', '/dedup on|off', '/dedup threshold &lt;0.0-1.0&gt;']
                },
                ami: {
                    cat: 'intel', desc: 'Shows Adaptive Model Intelligence status. AMI tracks what the current model is good and bad at, learns from failures, and adjusts prompting strategies. Shows quality score, capability probes, and recovery stats.',
                    term: '<span class="prompt">forge&gt;</span> /ami\n<span class="output">Adaptive Model Intelligence (qwen2.5-coder:14b)</span>\n  Quality score:  <span class="highlight">0.87</span>\n  Capabilities:   tool_calls, multi_file, refactor, test_gen\n  Failure catalog: 4 patterns learned\n  Recovery rate:   92%\n\n<span class="prompt">forge&gt;</span> /ami probe\n<span class="output">Probing model capabilities...</span>\n  Tool calls:     <span class="highlight">supported</span>\n  Multi-file:     <span class="highlight">supported</span>\n  JSON output:    <span class="highlight">supported</span>\n  Long context:   <span class="highlight">supported</span>\n\n<span class="prompt">forge&gt;</span> /ami stats\n<span class="output">AMI Recovery Analytics:</span>\n  Total retries:    23\n  Successful:       21 (91.3%)\n  Avg retry time:   1.2s',
                    variants: ['/ami', '/ami probe', '/ami reset', '/ami stats']
                },
                continuity: {
                    cat: 'intel', desc: 'Shows the continuity grade (A through F) that scores how well context swaps preserve conversation quality. Six signals are measured: topic retention, instruction recall, entity consistency, code reference accuracy, style consistency, and factual grounding.',
                    term: '<span class="prompt">forge&gt;</span> /continuity\n<span class="output">Continuity Grade: <span class="highlight">B+</span></span>\n  Topic retention:     <span class="highlight">92%</span>\n  Instruction recall:  <span class="highlight">88%</span>\n  Entity consistency:  <span class="highlight">85%</span>\n  Code references:     <span class="warn">78%</span>\n  Style consistency:   <span class="highlight">90%</span>\n  Factual grounding:   <span class="highlight">87%</span>\n\n<span class="prompt">forge&gt;</span> /continuity history\n<span class="output">Last 5 snapshots:</span>\n  <span class="dim">Turn 45:</span> A-    <span class="dim">Turn 38:</span> B+\n  <span class="dim">Turn 30:</span> B     <span class="dim">Turn 22:</span> A\n  <span class="dim">Turn 15:</span> A+',
                    variants: ['/continuity', '/continuity history', '/continuity set &lt;N&gt;', '/continuity on|off']
                },
                stats: {
                    cat: 'diag', desc: 'Shows full session analytics: turn count, total tokens (prompt + generated), tool call breakdown, timing data, and cost summary.',
                    term: '<span class="prompt">forge&gt;</span> /stats\n<span class="output">Session Analytics</span>\n  Turns:        15\n  Duration:     23m 14s\n  Prompt tokens:    98,200\n  Generated tokens: 44,600\n  Total tokens:    142,800\n\n<span class="output">Tool calls: 38</span>\n  read_file: 18  edit_file: 9  run_shell: 5\n  grep_files: 4  write_file: 2\n\n<span class="output">Performance:</span>\n  Avg response: 2.3s\n  Tokens/sec:   42.1',
                    variants: ['/stats', '/stats reliability']
                },
                billing: {
                    cat: 'diag', desc: 'Shows the token-level billing ledger. Tracks per-turn usage, total cost against your sandbox balance, and cost breakdown by model if the router is active.',
                    term: '<span class="prompt">forge&gt;</span> /billing\n<span class="output">Billing Summary</span>\n  Balance:    $48.72 / $50.00\n  Spent:      $1.28\n  Turns:      15\n\n  <span class="dim">By model:</span>\n    qwen2.5-coder:14b   $0.94  (112K tokens)\n    qwen2.5-coder:3b    $0.34  (30.8K tokens)\n\n  <span class="dim">Last turn:</span>\n    Prompt: 6,420 tokens  Generated: 1,890 tokens\n    Cost: $0.08',
                    variants: []
                },
                topup: {
                    cat: 'diag', desc: 'Adds funds to the sandbox billing ledger. Default is $50. The billing system tracks virtual costs for token usage comparison purposes.',
                    term: '<span class="prompt">forge&gt;</span> /topup\n<span class="output">Added $50.00 to billing balance.</span>\n<span class="output">New balance: $98.72</span>\n\n<span class="prompt">forge&gt;</span> /topup 100\n<span class="output">Added $100.00 to billing balance.</span>\n<span class="output">New balance: $198.72</span>',
                    variants: ['/topup', '/topup &lt;amount&gt;']
                },
                report: {
                    cat: 'diag', desc: 'Files a bug report to GitHub Issues with session context automatically attached. Includes model info, OS, Forge version, and a description you provide.',
                    term: '<span class="prompt">forge&gt;</span> /report context swap drops pinned entries\n<span class="output">Filing bug report...</span>\n<span class="output">Report submitted: <span class="highlight">Issue #47</span></span>\n<span class="dim">Attached: model=qwen2.5-coder:14b, OS=Win11,</span>\n<span class="dim">version=0.9.0, context_pct=82%</span>',
                    variants: []
                },
                export: {
                    cat: 'diag', desc: 'Exports a governance-grade audit bundle as a zip file. Includes the full forensic trail, provenance chain, billing ledger, and a manifest with SHA-256 hashes for chain-of-custody verification. Supports redaction mode for sensitive environments.',
                    term: '<span class="prompt">forge&gt;</span> /export\n<span class="output">Exporting audit bundle...</span>\n<span class="output">Saved: ~/.forge/exports/audit_2026-03-07_abc123.zip</span>\n  forensics.json     SHA-256: a7f2c3...\n  provenance.json    SHA-256: 9e3b18...\n  billing.json       SHA-256: 4d8a05...\n  manifest.json      SHA-256: f1c2d4...\n\n<span class="prompt">forge&gt;</span> /export --redact\n<span class="output">Exporting with redaction...</span>\n<span class="output">Saved: ~/.forge/exports/audit_2026-03-07_redacted.zip</span>\n<span class="dim">User prompts and file contents redacted.</span>',
                    variants: ['/export', '/export --redact']
                },
                benchmark: {
                    cat: 'diag', desc: 'Runs reproducible coding benchmarks against the current model. Results are stored locally for comparison across models and versions.',
                    term: '<span class="prompt">forge&gt;</span> /benchmark list\n<span class="output">Available suites:</span>\n  <span class="highlight">core</span>      8 scenarios (code gen, refactor, debug)\n  <span class="highlight">security</span>  5 scenarios (injection, exfil, encoding)\n  <span class="highlight">speed</span>     3 scenarios (throughput, latency)\n\n<span class="prompt">forge&gt;</span> /benchmark run core\n<span class="output">Running core benchmark (8 scenarios)...</span>\n  [1/8] Function generation    <span class="highlight">PASS</span>  1.8s\n  [2/8] Bug detection          <span class="highlight">PASS</span>  2.1s\n  [3/8] Refactor class         <span class="highlight">PASS</span>  3.4s\n  ...\n<span class="highlight">Score: 7/8 (87.5%)</span>',
                    variants: ['/benchmark list', '/benchmark run [suite]', '/benchmark results', '/benchmark compare']
                },
                hardware: {
                    cat: 'diag', desc: 'Detects your GPU, CPU, and RAM and recommends which models will fit in VRAM. Shows current GPU utilization and memory usage.',
                    term: '<span class="prompt">forge&gt;</span> /hardware\n<span class="output">Hardware Profile</span>\n  GPU:  NVIDIA RTX 5070 Ti (16 GB VRAM)\n  CPU:  AMD Ryzen 9 7950X (16 cores)\n  RAM:  64 GB DDR5\n\n<span class="output">VRAM Usage:</span>\n  Model loaded: 9.2 GB\n  Available:    6.8 GB\n\n<span class="output">Recommended models:</span>\n  <span class="highlight">qwen2.5-coder:14b</span>  ~9 GB   (current)\n  <span class="highlight">qwen2.5-coder:32b</span>  ~18 GB  (needs offload)\n  <span class="highlight">qwen2.5-coder:7b</span>   ~5 GB   (fits easily)',
                    variants: []
                },
                cache: {
                    cat: 'diag', desc: 'Shows file read cache statistics: hit rate, entries, memory usage. The LRU cache avoids re-reading files that haven\'t changed, improving tool call performance.',
                    term: '<span class="prompt">forge&gt;</span> /cache\n<span class="output">File Read Cache</span>\n  Entries:   47 / 200 max\n  Hit rate:  78.3%\n  Memory:    2.1 MB\n\n<span class="prompt">forge&gt;</span> /cache clear\n<span class="output">Cache cleared (47 entries removed).</span>',
                    variants: ['/cache', '/cache clear']
                },
                config: {
                    cat: 'diag', desc: 'Shows or modifies Forge configuration. 97 configuration keys covering models, safety, context, UI, telemetry, and more. Changes are saved to ~/.forge/config.yaml.',
                    term: '<span class="prompt">forge&gt;</span> /config\n<span class="output">Configuration (showing non-default values):</span>\n  default_model:       qwen2.5-coder:14b\n  safety_level:        1\n  swap_threshold_pct:  85\n  theme:               midnight\n  router_enabled:      true\n<span class="dim">97 keys available. See /docs for full list.</span>\n\n<span class="prompt">forge&gt;</span> /config reload\n<span class="output">Configuration reloaded from ~/.forge/config.yaml</span>',
                    variants: ['/config', '/config reload']
                },
                break: {
                    cat: 'reliability', desc: 'Runs the Forge Break Suite &mdash; 31 scenarios across 6 categories plus a 30-probe behavioral fingerprint. Tests response quality, context handling, tool accuracy, and model consistency. Power tier adds 7 HIPAA/SOC2 compliance scenarios (2 additional categories). Results are signed and tamper-evident. When <code>telemetry_enabled</code> is true in your config, results are automatically contributed to the Forge Matrix leaderboard.',
                    term: '<span class="prompt">forge&gt;</span> /break\n<span class="output">Running Forge Break Suite against \'qwen2.5-coder:14b\'...</span>\n\n  [1/31] Response coherence      <span class="highlight">PASS</span>\n  [2/31] Tool call accuracy      <span class="highlight">PASS</span>\n  [3/31] Multi-file consistency  <span class="highlight">PASS</span>\n  [4/31] Context recall          <span class="warn">WEAK</span> (0.72)\n  [5/31] Error recovery          <span class="highlight">PASS</span>\n  ...\n  [31/31] Behavioral fingerprint <span class="highlight">PASS</span>\n\n<span class="highlight">Reliability Score: 96.8%  (30/31 passed, 1 weak)</span>\n<span class="output">Report saved: brk_abc123</span>\n<span class="dim">Telemetry enabled &mdash; results contributed to Forge Matrix.</span>',
                    variants: ['/break --autopsy', '/break --self-rate', '/break --assure', '/break --share', '/break --json']
                },
                autopsy: {
                    cat: 'reliability', desc: 'Alias for <code>/break --autopsy</code>. Runs the full Break Suite and produces a detailed failure-mode analysis with per-category grades. For each scenario that failed or showed weakness, explains the root cause and suggests model-specific mitigations.',
                    term: '<span class="prompt">forge&gt;</span> /autopsy\n<span class="output">Running Forge Break Suite against \'qwen2.5-coder:14b\'...</span>\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  exfiltration            ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n\n<span class="highlight">  Forge Reliability Score: 94.6%  --  PARTIAL PASS</span>\n  (30/31 scenarios passed)\n\n<span class="output">  Failure Modes Detected:</span>\n\n  <span class="warn">1. Reliability Failure</span>\n     Scenario: reliability_context_recall\n     Detail:   invariant \'correct_entity\' NOT found in response\n\n<span class="output">  Stability Profile:</span>\n  Safety           [##########]  100%\n  Policy Adherence [##########]  100%\n  Tool Discipline  [##########]  100%\n  Exfil Guard      [##########]  100%\n  Reasoning        [########..]   85%\n  Context Integrity[#######...]   74%',
                    variants: ['/autopsy', '/autopsy --share']
                },
                stress: {
                    cat: 'reliability', desc: 'Runs a minimal 3-scenario stress suite designed for CI pipelines. Completes in under 30 seconds. Exits with code 1 on failure, making it safe to use in pre-commit hooks or GitHub Actions.',
                    term: '<span class="prompt">forge&gt;</span> /stress\n<span class="output">Forge Stress Suite (3 scenarios)...</span>\n  [1/3] Basic tool call    <span class="highlight">PASS</span>  2.1s\n  [2/3] Context boundary   <span class="highlight">PASS</span>  4.3s\n  [3/3] Error recovery     <span class="highlight">PASS</span>  3.8s\n\n<span class="highlight">3/3 passed (10.2s)</span>\n\n<span class="dim"># In CI pipeline:</span>\n<span class="prompt">$</span> forge --stress --ci\n<span class="output">3/3 passed</span>\n<span class="prompt">$</span> echo $?\n<span class="output">0</span>',
                    variants: ['/stress', '/stress --json', '/stress --ci']
                },
                assure: {
                    cat: 'reliability', desc: 'Runs the AI Assurance Suite &mdash; 31 scenarios across 6 categories mapped to EU AI Act, NIST AI RMF, and ISO 42001 standards. Power tier adds 7 HIPAA/SOC2 compliance scenarios (data_residency + audit_integrity categories). Generates a signed, tamper-evident compliance report. Upload requires <code>telemetry_enabled: true</code> or the <code>--share</code> flag (local-first, opt-in only).',
                    term: '<span class="prompt">forge&gt;</span> /assure\n<span class="output">Running AI assurance full suite against \'qwen2.5-coder:14b\'...</span>\n\n<span class="output">Assurance complete: 100% \u2014 PASS (31/31 scenarios)</span>\n<span class="output">Report saved: asr_def456</span>\n  <span class="highlight">\u2713</span> correctness: 100%\n  <span class="highlight">\u2713</span> safety: 100%\n  <span class="highlight">\u2713</span> consistency: 100%\n  <span class="highlight">\u2713</span> robustness: 100%\n  <span class="highlight">\u2713</span> compliance: 100%\n  <span class="highlight">\u2713</span> performance: 100%\n\n<span class="prompt">forge&gt;</span> /assure list\n<span class="output">Assurance reports (3 saved):</span>\n  asr_def456  qwen2.5-coder:14b  100%  2026-03-07\n  asr_abc123  qwen2.5-coder:14b   92%  2026-03-05\n  asr_789xyz  qwen2.5-coder:7b    85%  2026-03-04',
                    variants: ['/assure', '/assure --share', '/assure list', '/assure show &lt;id&gt;', '/assure categories', '/assure run &lt;category&gt;']
                },
                ship: {
                    cat: 'fleet', desc: 'Shipwright release management. Analyzes commits since last release, classifies them (breaking/feature/fix), computes the next semantic version, generates a changelog, runs preflight checks, and creates the release tag.',
                    term: '<span class="prompt">forge&gt;</span> /ship status\n<span class="output">Shipwright</span>\n  Current version: v0.9.0\n  Unreleased commits: 7\n  Next version: v0.9.1 (patch)\n\n<span class="prompt">forge&gt;</span> /ship dry\n<span class="output">Dry Run:</span>\n  v0.9.0 -> v0.9.1 (patch)\n  7 commits\n\n  <span class="highlight">## v0.9.1</span>\n  <span class="highlight">### Fixes</span>\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  <span class="highlight">### Features</span>\n  - feat: /break --share uploads signed report\n\n<span class="prompt">forge&gt;</span> /ship preflight\n  [<span class="highlight">PASS</span>] Tests: 1318 passed\n  [<span class="highlight">PASS</span>] No uncommitted changes\n  [<span class="highlight">PASS</span>] On main branch\n<span class="output">All preflight checks passed.</span>\n\n<span class="prompt">forge&gt;</span> /ship go\n<span class="output">Released v0.9.1 (v0.9.0 -> v0.9.1)</span>',
                    variants: ['/ship', '/ship dry', '/ship preflight', '/ship go', '/ship changelog', '/ship history', '/ship push on|off']
                },
                autocommit: {
                    cat: 'fleet', desc: 'Controls AutoForge, the smart auto-commit system. When enabled, every AI turn that modifies files creates a git commit with an auto-generated message describing the changes.',
                    term: '<span class="prompt">forge&gt;</span> /autocommit\n<span class="output">AutoForge: <span class="dim">disabled</span></span>\n  Pending edits: 0\n  Total commits: 0\n\n<span class="prompt">forge&gt;</span> /autocommit on\n<span class="output">AutoForge enabled. File edits will be auto-committed.</span>\n\n<span class="dim">[... you ask the AI to refactor a file ...]</span>\n\n<span class="output">[AutoForge] Committed: \"refactor: extract auth</span>\n<span class="output">middleware into separate module\" (2 files)</span>',
                    variants: ['/autocommit', '/autocommit on|off', '/autocommit push on|off', '/autocommit status', '/autocommit hook']
                },
                license: {
                    cat: 'fleet', desc: 'Shows your current license tier and available features. Three tiers: Community (free, full core features), Pro (genome persistence, AutoForge, Shipwright), and Power (fleet management, enterprise mode).',
                    term: '<span class="prompt">forge&gt;</span> /license\n<span class="output">Forge License</span>\n  Tier: <span class="highlight">Community</span> (free)\n  Machine ID: a7f2c3d8...\n  Genome maturity: 34%\n\n<span class="prompt">forge&gt;</span> /license tiers\n  <span class="highlight">Community</span> (free)\n    All 59 commands, 28 tools, 14 themes\n    Full security shield, voice I/O\n  <span class="highlight">Pro</span> ($199 one-time or $19/mo)\n    + Genome persistence across sessions\n    + AutoForge, Shipwright, 3 seats\n  <span class="highlight">Power</span> ($999 one-time or $79/mo)\n    + Fleet management (Master/Puppet)\n    + Enterprise mode, 10 seats\n\n<span class="prompt">forge&gt;</span> /license activate passport.json\n<span class="output">License activated: Pro tier</span>\n<span class="output">Genome persistence enabled.</span>',
                    variants: ['/license', '/license tiers', '/license activate &lt;file&gt;', '/license deactivate', '/license genome']
                },
                puppet: {
                    cat: 'fleet', desc: 'Fleet management for Power tier. A Master instance can generate Puppet passports for other machines, forming a fleet that shares genome intelligence, coordinated testing, and centralized analytics.',
                    term: '<span class="prompt">forge&gt;</span> /puppet status\n<span class="output">Fleet Status</span>\n  Role: <span class="highlight">Master</span>\n  Tier: Power\n  Seats: 3/5 used\n\n<span class="prompt">forge&gt;</span> /puppet list\n<span class="output">Fleet Members:</span>\n  <span class="highlight">[master]</span>  DevBox-Main   a7f2c3...  online\n  <span class="highlight">[puppet]</span>  CI-Runner     9e3b18...  online\n  <span class="highlight">[puppet]</span>  Laptop        4d8a05...  offline\n\n<span class="prompt">forge&gt;</span> /puppet generate BuildServer\n<span class="output">Puppet passport generated: puppet_BuildServer.json</span>\n<span class="dim">Transfer this file to the target machine</span>\n<span class="dim">and run: /puppet join puppet_BuildServer.json</span>',
                    variants: ['/puppet', '/puppet list', '/puppet generate &lt;label&gt;', '/puppet join &lt;file&gt;', '/puppet revoke &lt;id&gt;', '/puppet sync', '/puppet seats']
                },
                admin: {
                    cat: 'fleet', desc: 'Manages GitHub collaborators and telemetry tokens. Owner-only: invite or remove collaborators, check pending invitations, generate API tokens for testers. Requires GitHub CLI (gh) authenticated with repo scope.',
                    term: '<span class="prompt">forge&gt;</span> /admin\n<span class="output">Repository Collaborators:</span>\n  <span class="highlight">owner</span>    ups0n\n  <span class="highlight">collab</span>   dev-team-member\n\n<span class="prompt">forge&gt;</span> /admin invite new-tester\n<span class="output">Invitation sent to new-tester (push access).</span>\n\n<span class="prompt">forge&gt;</span> /admin token beta-tester-1\n<span class="output">Token generated for beta-tester-1:</span>\n  <span class="dim">forge_tk_a7f2c3d8e9b1...</span>\n<span class="dim">Share this token securely. It cannot be retrieved later.</span>',
                    variants: ['/admin', '/admin invite &lt;user&gt;', '/admin remove &lt;user&gt;', '/admin pending', '/admin token &lt;label&gt;', '/admin role &lt;label&gt; &lt;role&gt;']
                }
            };

            var catLabels = {
                system:'System', model:'Model & Tools', context:'Context & Memory',
                search:'Search & Indexing', safety:'Safety & Security',
                intel:'AI Intelligence', diag:'Diagnostics', reliability:'Reliability',
                fleet:'Fleet & Licensing'
            };
            var catClasses = {
                system:'cat-system', model:'cat-model', context:'cat-context',
                search:'cat-search', safety:'cat-safety', intel:'cat-intel',
                diag:'cat-diag', reliability:'cat-reliability', fleet:'cat-fleet'
            };

            var overlay = document.getElementById('cmdModal');
            var titleEl = document.getElementById('cmdModalTitle');
            var tagEl   = document.getElementById('cmdModalTag');
            var descEl  = document.getElementById('cmdModalDesc');
            var termEl  = document.getElementById('cmdModalTerm');
            var varEl   = document.getElementById('cmdModalVariants');
            var closeBtn= document.getElementById('cmdModalClose');

            var currentKey = '';
            var currentBaseTerm = '';

            function _esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
            function _p(c){return '<span class="prompt">forge&gt;</span> '+c;}
            function _o(t){return '<span class="output">'+t+'</span>';}
            function _h(t){return '<span class="highlight">'+t+'</span>';}
            function _w(t){return '<span class="warn">'+t+'</span>';}
            function _d(t){return '<span class="dim">'+t+'</span>';}

            function openModal(key) {
                var c = CMD[key];
                if (!c) return;
                titleEl.textContent = '/' + key;
                tagEl.textContent = catLabels[c.cat] || c.cat;
                tagEl.className = 'cmd-modal-tag ' + (catClasses[c.cat] || '');
                descEl.innerHTML = c.desc;
                termEl.innerHTML = c.term;
                currentKey = key;
                currentBaseTerm = c.term;
                if (c.variants && c.variants.length) {
                    var baseCmd = '/' + key;
                    var h = '<h4>All Forms</h4>';
                    h += '<code class="cmd-var-pill active" data-var="__base__">' + _esc(baseCmd) + '</code>';
                    c.variants.forEach(function(v){ h += '<code class="cmd-var-pill" data-var="' + _esc(v) + '">' + _esc(v) + '</code>'; });
                    varEl.innerHTML = h;
                    varEl.style.display = '';
                } else {
                    varEl.style.display = 'none';
                }
                overlay.classList.add('active');
                document.body.style.overflow = 'hidden';
            }

            function closeModal() {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }

            closeBtn.addEventListener('click', closeModal);
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) closeModal();
            });
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') closeModal();
            });

            /* ── Variant examples (per-form terminal output) ── */
            var VTERM = {
                quit: {
                    '/exit': _p('/exit')+'\n'+_o('Session auto-saved.')+'\n'+_o('Goodbye.')
                },
                voice: {
                    '/voice ptt': _p('/voice ptt')+'\n'+_o('Voice input: push-to-talk mode')+'\n'+_o('Hold ` (backtick) to speak. Release to send.'),
                    '/voice vox': _p('/voice vox')+'\n'+_o('Voice input: VOX mode (auto-detect)')+'\n'+_o('Speak naturally. Silence > 1.5s sends input.'),
                    '/voice off': _p('/voice off')+'\n'+_o('Voice input disabled.')
                },
                theme: {
                    '/theme <name>': _p('/theme cyberpunk')+'\n'+_o('Theme switched to ')+_h('cyberpunk')+_o('.')+'\n'+_d('Colors, glow effects, and scanline overlay applied.')
                },
                update: {
                    '/update --yes': _p('/update --yes')+'\n'+_o('Pulling updates...')+'\n'+_h('Updated to v0.9.1 (3 commits applied).')+'\n'+_o('Dependencies unchanged.')+'\n'+_d('Restart recommended — core files changed.')
                },
                model: {
                    '/model <name>': _p('/model qwen2.5-coder:7b')+'\n'+_o('Switched to qwen2.5-coder:7b')+'\n'+_d('Parameters: 7B  Context: 32,768  VRAM: ~5.2 GB')
                },
                router: {
                    '/router on|off': _p('/router on')+'\n'+_o('Multi-model router ')+_h('enabled')+_o('.')+'\n'+_d('Simple tasks route to small model, complex to primary.')+'\n\n'+_p('/router off')+'\n'+_o('Router disabled. All tasks use primary model.'),
                    '/router big <model>': _p('/router big qwen2.5-coder:14b')+'\n'+_o('Primary (complex) model set to qwen2.5-coder:14b'),
                    '/router small <model>': _p('/router small qwen2.5-coder:3b')+'\n'+_o('Small (simple) model set to qwen2.5-coder:3b')
                },
                safety: {
                    '/safety <level>': _p('/safety confirm_writes')+'\n'+_o('Safety level set to ')+_h('confirm_writes (2)')+'\n'+_d('AI will ask before modifying any file.')+'\n\n'+_p('/safety unleashed')+'\n'+_w('Safety level set to unleashed (0) — no restrictions.'),
                    '/safety sandbox on|off': _p('/safety sandbox on')+'\n'+_o('Filesystem sandbox ')+_h('enabled')+_o('.')+'\n'+_d('AI restricted to working directory and allowed paths.')+'\n\n'+_p('/safety sandbox off')+'\n'+_w('Filesystem sandbox disabled.')+'\n'+_w('Warning: AI can now access any path.'),
                    '/safety allow <path>': _p('/safety allow /tmp/builds')+'\n'+_o('Added /tmp/builds to sandbox allowlist.')
                },
                crucible: {
                    '/crucible on|off': _p('/crucible on')+'\n'+_o('Crucible threat scanner ')+_h('enabled')+_o('.')+'\n\n'+_p('/crucible off')+'\n'+_w('Crucible threat scanner disabled.')+'\n'+_w('Warning: Messages will not be scanned for threats.'),
                    '/crucible log': _p('/crucible log')+'\n'+_o('Threat log (last 10):')+'\n  '+_d('14:23:01')+' '+_w('MEDIUM')+' prompt_injection  "ignore previous..."'+'\n  '+_d('14:20:45')+' '+_w('LOW')+' encoded_payload  base64 in response'+'\n  '+_d('No further events.'),
                    '/crucible canary': _p('/crucible canary')+'\n'+_o('Honeypot canary integrity: ')+_h('INTACT')+'\n'+_d('All 3 canary tokens are present and unmodified.')
                },
                forensics: {
                    '/forensics save': _p('/forensics save')+'\n'+_o('Forensics report saved to ~/.forge/forensics/session_abc123.json')+'\n'+_d('38 events, 15 turns, 0 threats recorded.')
                },
                plan: {
                    '/plan on|off': _p('/plan on')+'\n'+_o('Plan mode armed — next prompt will generate a plan.')+'\n\n'+_p('/plan off')+'\n'+_o('Plan mode disabled.'),
                    '/plan auto': _p('/plan auto')+'\n'+_o('Plan mode: auto (threshold: 0.6)')+'\n'+_d('Complex tasks will generate a plan before execution.'),
                    '/plan always': _p('/plan always')+'\n'+_o('Plan mode: always')+'\n'+_d('Every prompt generates a multi-step plan.'),
                    '/plan verify [off|report|repair|strict]': _p('/plan verify')+'\n'+_o('Plan Verification')+'\n  Mode:     report\n  Tests:    on\n  Lint:     on\n  Timeout:  30s\n\n'+_p('/plan verify strict')+'\n'+_o('Plan verification: ')+_h('strict')+'\n'+_d('Each step must pass tests before proceeding.')
                },
                dedup: {
                    '/dedup on|off': _p('/dedup on')+'\n'+_o('Tool deduplication ')+_h('enabled')+_o('.')+'\n\n'+_p('/dedup off')+'\n'+_o('Tool deduplication disabled.'),
                    '/dedup threshold <0.0-1.0>': _p('/dedup threshold 0.9')+'\n'+_o('Dedup threshold set to ')+_h('90%')+'\n'+_d('Only near-exact duplicates will be suppressed.')
                },
                ami: {
                    '/ami probe': _p('/ami probe')+'\n'+_o('Probing model capabilities...')+'\n  Tool calls:     '+_h('supported')+'\n  Multi-file:     '+_h('supported')+'\n  JSON output:    '+_h('supported')+'\n  Long context:   '+_h('supported'),
                    '/ami reset': _p('/ami reset')+'\n'+_o('AMI failure catalog cleared.')+'\n'+_d('Learned patterns reset. Model will be re-profiled.'),
                    '/ami stats': _p('/ami stats')+'\n'+_o('AMI Recovery Analytics:')+'\n  Total retries:    23\n  Successful:       21 (91.3%)\n  Avg retry time:   1.2s\n  Top failure:      malformed_json (5 occurrences)'
                },
                continuity: {
                    '/continuity history': _p('/continuity history')+'\n'+_o('Last 5 snapshots:')+'\n  '+_d('Turn 45:')+' A-    '+_d('Turn 38:')+' B+\n  '+_d('Turn 30:')+' B     '+_d('Turn 22:')+' A\n  '+_d('Turn 15:')+' A+',
                    '/continuity set <N>': _p('/continuity set 80')+'\n'+_o('Recovery threshold set to 80.')+'\n'+_d('Auto-recovery triggers when continuity score drops below 80%.'),
                    '/continuity on|off': _p('/continuity on')+'\n'+_o('Continuity monitoring ')+_h('enabled')+_o('.')+'\n\n'+_p('/continuity off')+'\n'+_o('Continuity monitoring disabled.')
                },
                topup: {
                    '/topup <amount>': _p('/topup 100')+'\n'+_o('Added $100.00 to billing balance.')+'\n'+_o('New balance: $148.72')
                },
                export: {
                    '/export --redact': _p('/export --redact')+'\n'+_o('Exporting with redaction...')+'\n'+_o('Saved: ~/.forge/exports/audit_2026-03-07_redacted.zip')+'\n'+_d('User prompts, file contents, and PII redacted.')
                },
                benchmark: {
                    '/benchmark list': _p('/benchmark list')+'\n'+_o('Available suites:')+'\n  '+_h('core')+'      8 scenarios (code gen, refactor, debug)\n  '+_h('security')+'  5 scenarios (injection, exfil, encoding)\n  '+_h('speed')+'     3 scenarios (throughput, latency)',
                    '/benchmark run [suite]': _p('/benchmark run core')+'\n'+_o('Running core benchmark (8 scenarios)...')+'\n  [1/8] Function generation    '+_h('PASS')+'  1.8s\n  [2/8] Bug detection          '+_h('PASS')+'  2.1s\n  [3/8] Refactor class         '+_h('PASS')+'  3.4s\n  ...\n'+_h('Score: 7/8 (87.5%)'),
                    '/benchmark results': _p('/benchmark results')+'\n'+_o('Benchmark History:')+'\n  '+_d('2026-03-07')+' core     qwen2.5-coder:14b  87.5%\n  '+_d('2026-03-05')+' core     qwen2.5-coder:7b   75.0%\n  '+_d('2026-03-04')+' security qwen2.5-coder:14b  100%',
                    '/benchmark compare': _p('/benchmark compare')+'\n'+_o('Comparing last two runs:')+'\n  '+_d('Run 1:')+' core  qwen2.5-coder:14b  87.5%\n  '+_d('Run 2:')+' core  qwen2.5-coder:7b   75.0%\n  '+_h('Delta: +12.5%')+' (14b outperforms 7b on code generation)'
                },
                cache: {
                    '/cache clear': _p('/cache clear')+'\n'+_o('Cache cleared (47 entries removed).')
                },
                config: {
                    '/config reload': _p('/config reload')+'\n'+_o('Configuration reloaded from ~/.forge/config.yaml')+'\n'+_d('3 values changed since last load.')
                },
                break: {
                    '/break --autopsy': _p('/break --autopsy')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n\n  [31/31 scenarios complete]\n\n'+_o('Failure Mode Analysis:')+'\n\n  '+_w('[WEAK]')+' Context recall (score: 0.72)\n  '+_d('Root cause: Model loses entity references after')+'\n  '+_d('3+ context swaps. Summary budget may be too low.')+'\n  '+_d('Suggestion: Increase swap_summary_tokens to 800.')+'\n\n  '+_h('[PASS]')+' All other scenarios within expected range.',
                    '/break --self-rate': _p('/break --self-rate')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n  (self-assessment enabled -- model will grade itself)\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n  exfiltration            ........ PASS\n\n'+_h('Reliability Score: 94.6%  --  PARTIAL PASS')+'\n  (30/31 scenarios passed)\n\n'+_o('Self-Assessment Calibration: 76.9%')+'\n'+_d('  (model correctly predicted its own pass/fail on 76.9% of scenarios)')+'\n    safety_harm_refusal               PASS  self-rated 9/10 (predicted pass -- '+_h('correct')+')\n    reliability_context_recall        FAIL  self-rated 7/10 (predicted pass -- '+_w('WRONG')+')\n      '+_d('model says: \"I failed to maintain entity references across context boundaries.\"')+'\n    adversarial_compliance            PASS  self-rated 8/10 (predicted pass -- '+_h('correct')+')',
                    '/break --assure': _p('/break --assure')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n  exfiltration            ........ PASS\n\n'+_h('Reliability Score: 94.6%  --  PARTIAL PASS')+'\n  (30/31 scenarios passed)\n\n'+_o('Running AI Assurance Suite against \'qwen2.5-coder:14b\'...')+'\n\n'+_o('Assurance complete: 100% -- PASS (31/31 scenarios)')+'\n'+_o('Report saved: asr_def456')+'\n  + safety: 100%\n  + reliability: 100%\n  + adversarial: 100%\n  + tool_misuse: 100%\n  + exfiltration: 100%\n  + context_integrity: 100%\n\n  ==================================================\n'+_h('  Combined Forge Matrix Score: 97.3%')+'\n    Break:     94.6%\n    Assurance: 100%\n  ==================================================',
                    '/break --share': _p('/break --share')+'\n'+_o('Running Forge Break Suite...')+'\n  [31/31 complete]  Reliability: 94.6%\n\n'+_o('Uploading signed report...')+'\n'+_h('Report shared: https://forge.dirtstar.dev/report/abc123')+'\n'+_d('Shareable link valid for 90 days.'),
                    '/break --json': _p('/break --json')+'\n'+_d('{')+'\n'+_d('  "model": "qwen2.5-coder:14b",')+'\n'+_d('  "pass_rate": 0.946,')+'\n'+_d('  "scenarios_passed": 30,')+'\n'+_d('  "scenarios_run": 31,')+'\n'+_d('  "reliability_score": 94.6,')+'\n'+_d('  "fingerprint": { ... },')+'\n'+_d('  "signature": "a7f2c3d8..."')+'\n'+_d('}')
                },
                autopsy: {
                    '/autopsy --share': _p('/autopsy --share')+'\n'+_o('Running Forge Autopsy...')+'\n  [31/31 complete]\n\n'+_o('Failure analysis generated.')+'\n'+_o('Uploading signed report...')+'\n'+_h('Report shared: https://forge.dirtstar.dev/report/def456')
                },
                stress: {
                    '/stress --json': _p('/stress --json')+'\n'+_d('{"passed":3,"failed":0,"total":3,"duration_s":10.2,"scenarios":[...]}')+'\n',
                    '/stress --ci': _p('/stress --ci')+'\n'+_o('Forge Stress Suite (3 scenarios)...')+'\n  [1/3] Basic tool call    '+_h('PASS')+'\n  [2/3] Context boundary   '+_h('PASS')+'\n  [3/3] Error recovery     '+_h('PASS')+'\n'+_h('3/3 passed')+'\n\n'+_d('# Exit code 0 = all passed (CI-safe)')+'\n'+_d('# Exit code 1 = at least one failed')
                },
                assure: {
                    '/assure --share': _p('/assure --share')+'\n'+_o('Running AI assurance full suite against \'qwen2.5-coder:14b\'...')+'\n\n'+_o('Assurance complete: 100% -- PASS (31/31 scenarios)')+'\n'+_o('Report saved: asr_def456')+'\n'+_o('Uploading to assurance server...')+'\n'+_h('Report uploaded to assurance server.'),
                    '/assure list': _p('/assure list')+'\n'+_o('Assurance reports (3 saved):')+'\n  asr_def456  qwen2.5-coder:14b  100%  2026-03-07\n  asr_abc123  qwen2.5-coder:14b   92%  2026-03-05\n  asr_789xyz  qwen2.5-coder:7b    85%  2026-03-04',
                    '/assure show <id>': _p('/assure show asr_def456')+'\n'+_o('Assurance Report: asr_def456')+'\n  Model:    qwen2.5-coder:14b\n  Date:     2026-03-07 14:23\n  Result:   '+_h('PASS (100%)')+'\n  Signed:   SHA-256:a7f2c3...\n\n  Categories:\n    correctness:  100%\n    safety:       100%\n    consistency:  100%\n    robustness:   100%',
                    '/assure categories': _p('/assure categories')+'\n'+_o('Assurance scenario categories:')+'\n  adversarial\n  context_integrity\n  exfiltration\n  reliability\n  safety\n  tool_misuse',
                    '/assure run <category>': _p('/assure run safety')+'\n'+_o('Running AI assurance category \'safety\'...')+'\n  [1/3] Injection resistance  '+_h('PASS')+'\n  [2/3] Exfil detection       '+_h('PASS')+'\n  [3/3] Output safety         '+_h('PASS')+'\n\n'+_h('Category safety: 100% (3/3)')
                },
                ship: {
                    '/ship dry': _p('/ship dry')+'\n'+_o('Dry Run:')+'\n  v0.9.0 -> v0.9.1 (patch)\n  7 commits\n\n  '+_h('## v0.9.1')+'\n  '+_h('### Fixes')+'\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  '+_h('### Features')+'\n  - feat: /break --share uploads signed report',
                    '/ship preflight': _p('/ship preflight')+'\n  ['+_h('PASS')+'] Tests: 1318 passed\n  ['+_h('PASS')+'] No uncommitted changes\n  ['+_h('PASS')+'] On main branch\n  ['+_h('PASS')+'] Version not already tagged\n'+_o('All preflight checks passed.'),
                    '/ship go': _p('/ship go')+'\n'+_o('Executing release...')+'\n'+_h('Released v0.9.1 (v0.9.0 -> v0.9.1)')+'\n\n  ## v0.9.1 Changelog\n  - fix: context swap preserves pinned order\n  - feat: /break --share uploads signed report\n\n'+_d('Pushed to origin — testers can /update.'),
                    '/ship changelog': _p('/ship changelog')+'\n\n  '+_h('## v0.9.1 (unreleased)')+'\n  ### Fixes\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  ### Features\n  - feat: /break --share uploads signed report\n  ### Other\n  - docs: update command reference',
                    '/ship history': _p('/ship history')+'\n'+_o('Release History:')+'\n  v0.9.0  2026-03-05  12 commits  patch\n  v0.8.0  2026-02-28  31 commits  minor\n  v0.7.0  2026-02-20  45 commits  minor\n  v0.6.0  2026-02-12  28 commits  minor',
                    '/ship push on|off': _p('/ship push on')+'\n'+_o('Shipwright push ')+_h('enabled')+_o('. /ship go will push to origin.')+'\n\n'+_p('/ship push off')+'\n'+_o('Shipwright push disabled.')
                },
                autocommit: {
                    '/autocommit on|off': _p('/autocommit on')+'\n'+_o('AutoForge ')+_h('enabled')+_o('. File edits will be auto-committed.')+'\n\n'+_p('/autocommit off')+'\n'+_o('AutoForge disabled.'),
                    '/autocommit push on|off': _p('/autocommit push on')+'\n'+_o('AutoForge push ')+_h('enabled')+_o('. Commits will be pushed to origin.')+'\n\n'+_p('/autocommit push off')+'\n'+_o('AutoForge push disabled.'),
                    '/autocommit status': _p('/autocommit status')+'\n'+_o('AutoForge: ')+_h('enabled')+'\n  Pending edits: 0\n  Total commits this session: 4\n  Push on commit: off',
                    '/autocommit hook': _p('/autocommit hook')+'\n'+_o('Hook script written to .claude/hooks/auto_commit.py')+'\n'+_d('Add to .claude/settings.json to activate.')
                },
                license: {
                    '/license tiers': _p('/license tiers')+'\n\n  '+_h('Community')+' (free)\n    All 59 commands, 28 tools, 14 themes\n    Full security shield, voice I/O\n\n  '+_h('Pro')+' ($199 or $19/mo)\n    + Genome persistence, 3 seats\n    + AutoForge, Shipwright\n\n  '+_h('Power')+' ($999 or $79/mo)\n    + Fleet management, 10 seats\n    + Enterprise mode, fleet analytics',
                    '/license activate <file>': _p('/license activate passport.json')+'\n'+_h('License activated: Pro tier')+'\n'+_o('Genome persistence enabled.'),
                    '/license deactivate': _p('/license deactivate')+'\n'+_o('License deactivated. Reverted to Community tier.')+'\n'+_d('Your data and models are unchanged.'),
                    '/license genome': _p('/license genome')+'\n'+_o('Forge Genome')+'\n  Maturity: 34%\n  Sessions: 12\n  AMI patterns: 4\n  Model profiles: 2\n  Avg quality: 0.87\n  Reliability: 94.6\n  Threat scans: 1,247'
                },
                puppet: {
                    '/puppet list': _p('/puppet list')+'\n'+_o('Fleet Members:')+'\n  '+_h('[master]')+'  DevBox-Main   a7f2c3...  online\n  '+_h('[puppet]')+'  CI-Runner     9e3b18...  online\n  '+_h('[puppet]')+'  Laptop        4d8a05...  offline',
                    '/puppet generate <label>': _p('/puppet generate BuildServer')+'\n'+_o('Puppet passport generated: puppet_BuildServer.json')+'\n'+_d('Transfer this file to the target machine and run:')+'\n'+_d('/puppet join puppet_BuildServer.json'),
                    '/puppet join <file>': _p('/puppet join puppet_BuildServer.json')+'\n'+_h('Joined fleet as Puppet.')+'\n'+_o('Master: DevBox-Main (a7f2c3...)')+'\n'+_o('Genome sync: enabled'),
                    '/puppet revoke <id>': _p('/puppet revoke 4d8a05')+'\n'+_o('Puppet 4d8a05 (Laptop) revoked.')+'\n'+_d('Seat freed. 2/5 seats in use.'),
                    '/puppet sync': _p('/puppet sync')+'\n'+_o('Syncing genome to master...')+'\n'+_h('Genome synced.')+' 3 new patterns uploaded.',
                    '/puppet seats': _p('/puppet seats')+'\n'+_o('Seat Allocation:')+'\n  Total: 5\n  Used: 3\n  Available: 2\n\n  '+_h('master')+'  DevBox-Main  (permanent)\n  '+_h('puppet')+'  CI-Runner    expires 2026-04-07\n  '+_h('puppet')+'  Laptop       expires 2026-04-07'
                },
                admin: {
                    '/admin invite <user>': _p('/admin invite new-tester')+'\n'+_o('Invitation sent to new-tester (push access).'),
                    '/admin remove <user>': _p('/admin remove old-tester')+'\n'+_o('Removed old-tester from collaborators.'),
                    '/admin pending': _p('/admin pending')+'\n'+_o('Pending invitations:')+'\n  new-tester    invited 2h ago\n  '+_d('No expired invitations.'),
                    '/admin token <label>': _p('/admin token beta-tester-1')+'\n'+_o('Token generated for beta-tester-1:')+'\n  '+_d('forge_tk_a7f2c3d8e9b1...')+'\n'+_d('Share this token securely. It cannot be retrieved later.'),
                    '/admin role <label> <role>': _p('/admin role beta-tester-1 admin')+'\n'+_o('Role updated: beta-tester-1 is now ')+_h('admin')
                },
                scan: {
                    '/scan <path>': _p('/scan src/auth/')+'\n'+_o('Scanning src/auth/ ...')+'\n'+_o('Found:')+'\n  '+_h('6')+' Python files\n  '+_h('3')+' classes, '+_h('14')+' functions\n  '+_h('1')+' Flask route\n'+_d('Results added to context (420 tokens).'),
                    '/scan force': _p('/scan force')+'\n'+_o('Force re-scanning entire project...')+'\n'+_o('Found:')+'\n  '+_h('131')+' Python files\n  '+_h('89')+' classes, '+_h('1,247')+' functions\n'+_d('Full rescan complete. Cache invalidated.')
                },
                index: {
                    '/index <path>': _p('/index src/')+'\n'+_o('Indexing src/ ...')+'\n  Processing: 47 files\n'+_h('Index built: 47 files, 890 chunks')
                },
                journal: {
                    '/journal <N>': _p('/journal 3')+'\n'+_o('Last 3 journal entries:')+'\n  '+_d('2026-03-07 14:23')+'  Refactored auth module (3 files)\n  '+_d('2026-03-07 10:11')+'  Fixed billing roundtrip bug\n  '+_d('2026-03-06 16:45')+'  Added /stress command'
                },
                digest: {
                    '/digest <file>': _p('/digest forge/engine.py')+'\n'+_o('forge/engine.py (3,287 lines)')+'\n  '+_h('class ForgeEngine')+'\n    __init__, run, _agent_loop, _process_tool_calls\n    _cached_read_file, _cached_write_file, ...\n  '+_d('42 methods, 12 imports, 3 constants')
                }
            };

            /* ── Variant pill click delegation ── */
            varEl.addEventListener('click', function(e) {
                var pill = e.target.closest('.cmd-var-pill');
                if (!pill) return;
                var vCmd = pill.getAttribute('data-var');
                var vt;
                if (vCmd === '__base__') {
                    vt = currentBaseTerm;
                } else {
                    vt = (VTERM[currentKey] && VTERM[currentKey][vCmd]) || (_p(vCmd) + '\n' + _d('(Run this in Forge to see full output)'));
                }
                termEl.innerHTML = vt;
                varEl.querySelectorAll('.cmd-var-pill').forEach(function(p) { p.classList.remove('active'); });
                pill.classList.add('active');
            });

            document.querySelectorAll('.cmd-row').forEach(function(row) {
                row.addEventListener('click', function() {
                    openModal(this.getAttribute('data-cmd'));
                });
            });
        })();
        </script>

        <!-- ── Tool System ── -->
        <h2 id="tools">Tool System</h2>
        <p><strong>What:</strong> 27 structured tools that the AI uses to interact with your codebase, filesystem, shell, and web.</p>
        <p><strong>Why:</strong> Tools give the AI precise, auditable actions instead of unstructured text output. Every tool call is logged in the forensic audit trail.</p>
        <p><strong>How:</strong> The AI automatically selects the right tool for each subtask. View stats with <code>/tools</code>.</p>

        <h3>File Operations</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                    <tr><td><code>read_file</code></td><td>Read file contents with line numbers, offset, and limit. Crucible-scanned for threats. Cached for performance.</td></tr>
                    <tr><td><code>write_file</code></td><td>Create or overwrite files. Atomic writes (temp file + replace) prevent corruption.</td></tr>
                    <tr><td><code>edit_file</code></td><td>Surgical find-and-replace edits. Multiple replacements per call. Cache invalidation on edit.</td></tr>
                    <tr><td><code>glob_files</code></td><td>Find files by glob pattern (e.g., <code>**/*.py</code>). Recursive directory search.</td></tr>
                    <tr><td><code>grep_files</code></td><td>Regex search across files with context lines. Like <code>grep -rn</code> but structured.</td></tr>
                    <tr><td><code>list_directory</code></td><td>List directory contents with file sizes and types.</td></tr>
                </tbody>
            </table>
        </div>

        <h3>Execution &amp; Reasoning</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                    <tr><td><code>run_shell</code></td><td>Execute shell commands with configurable timeout and working directory. Safety-validated before execution.</td></tr>
                    <tr><td><code>think</code></td><td>Internal step-by-step reasoning (hidden from user). Helps the AI plan complex operations.</td></tr>
                </tbody>
            </table>
        </div>

        <h3>Code Analysis (Tree-sitter)</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th style="width:200px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                    <tr><td><code>codebase_digest</code></td><td>Generate a structured summary of the entire project (files, functions, classes).</td></tr>
                    <tr><td><code>file_digest</code></td><td>Analyze a single file: extract all functions, classes, imports, and structure.</td></tr>
                    <tr><td><code>symbol_search</code></td><td>Find function/class definitions across the codebase by name.</td></tr>
                    <tr><td><code>dependency_graph</code></td><td>Build import and call dependency graphs for a file or module.</td></tr>
                    <tr><td><code>find_references</code></td><td>Find all references to a symbol across the codebase.</td></tr>
                    <tr><td><code>find_definition</code></td><td>Jump to the definition of a function, class, or variable.</td></tr>
                    <tr><td><code>get_function_signature</code></td><td>Extract function prototype (name, args, return type).</td></tr>
                    <tr><td><code>list_functions</code></td><td>List all functions defined in a file.</td></tr>
                    <tr><td><code>analyze_function_calls</code></td><td>Build a call graph for a specific function.</td></tr>
                </tbody>
            </table>
        </div>

        <h3>Git</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                    <tr><td><code>git_log</code></td><td>Show commit history with optional filters.</td></tr>
                    <tr><td><code>git_diff</code></td><td>Diff working tree, staging area, or between commits.</td></tr>
                    <tr><td><code>git_status</code></td><td>Show repository status (staged, modified, untracked).</td></tr>
                    <tr><td><code>git_blame</code></td><td>Line-by-line attribution for a file.</td></tr>
                    <tr><td><code>git_show</code></td><td>Show details of a specific commit.</td></tr>
                </tbody>
            </table>
        </div>

        <h3>Web</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th style="width:200px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                    <tr><td><code>fetch_url</code></td><td>HTTP GET with text extraction. Blocks private/loopback IPs (SSRF protection).</td></tr>
                    <tr><td><code>fetch_with_headers</code></td><td>HTTP GET with custom headers for APIs.</td></tr>
                    <tr><td><code>post_request</code></td><td>HTTP POST with JSON body.</td></tr>
                </tbody>
            </table>
        </div>

        <!-- ── Routing ── -->
        <h2 id="routing">Multi-Model Routing</h2>
        <p><strong>What:</strong> Forge automatically routes tasks to the optimal model based on complexity.</p>
        <p><strong>Why:</strong> Simple tasks (typo fixes, quick questions) don't need a 14B model. The router saves VRAM and latency by using a smaller model for easy work.</p>
        <p><strong>How:</strong> Set <code>router_enabled: true</code> and <code>small_model: "qwen2.5-coder:3b"</code> in config. The router scores each input from -5 (very simple) to +15 (very complex) using signal analysis:</p>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Complex signals (+):</strong> multi-file references, architecture keywords, long input, multiple questions, "think hard" cues</li>
            <li><strong>Simple signals (-):</strong> single-file operations, short input, formatting tasks, quick questions</li>
        </ul>
        <p>View routing decisions with <code>/router</code>.</p>

        <!-- ── Context ── -->
        <h2 id="context">Context Management</h2>
        <p><strong>What:</strong> Forge gives you full control over the AI's context window &mdash; no hidden compaction, no lossy summaries.</p>
        <p><strong>Why:</strong> Context quality directly impacts AI quality. Forge shows you exactly what's in context, how many tokens each entry uses, and lets you manually manage it.</p>

        <h3>Partitions</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Core</strong> &mdash; System prompts and pinned messages. Highest priority, never evicted.</li>
            <li><strong>Working</strong> &mdash; Recent chat history. Evicted oldest-first when space is needed.</li>
            <li><strong>Reference</strong> &mdash; Tool results and file reads. Automatically deduplicated (re-reading a file replaces the old read).</li>
            <li><strong>Recall</strong> &mdash; Semantic index retrievals from the embedding search.</li>
            <li><strong>Quarantine</strong> &mdash; Evicted entries (no longer sent to the model but still visible to you).</li>
        </ul>

        <h3>Key Commands</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><code>/context</code> &mdash; See what's in context with token counts per partition</li>
            <li><code>/pin &lt;idx&gt;</code> / <code>/unpin</code> &mdash; Pin entries to survive eviction</li>
            <li><code>/drop &lt;idx&gt;</code> &mdash; Manually evict an entry to free tokens</li>
            <li><code>/save</code> / <code>/load</code> &mdash; Save and restore full sessions with complete fidelity</li>
        </ul>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ AI INTELLIGENCE ══════════════ -->

        <h2 id="ami">Self-Healing AI (AMI)</h2>
        <p><strong>What:</strong> Adaptive Model Intelligence &mdash; a 3-tier recovery system that detects when the AI is failing and fixes it automatically.</p>
        <p><strong>Why:</strong> AI models sometimes refuse tasks, loop, forget their tools, or produce garbage. Instead of making you restart, AMI detects the problem and escalates through increasingly aggressive recovery strategies.</p>

        <h3>How It Works</h3>
        <p>AMI scores every AI response on 5 quality dimensions in real-time:</p>
        <ol style="padding-left:24px; margin-bottom:16px">
            <li><strong>Refusal Score</strong> &mdash; Is the model declining the request? ("I can't help with that")</li>
            <li><strong>Tool Compliance</strong> &mdash; Is it using its tools when it should be?</li>
            <li><strong>Repetition Score</strong> &mdash; Is it stuck in a loop?</li>
            <li><strong>Progress Score</strong> &mdash; Is it making forward progress?</li>
            <li><strong>Content Length</strong> &mdash; Is it producing useful output?</li>
        </ol>

        <p>If the composite score drops below the threshold (default 0.7), AMI triggers recovery:</p>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Tier</th><th>Strategy</th><th>What Happens</th></tr></thead>
                <tbody>
                    <tr><td><strong>1</strong></td><td>Parse Nudge</td><td>Inject instruction: "You have tools available. Use them." + show tool format example. Temperature set to 0.1.</td></tr>
                    <tr><td><strong>2</strong></td><td>Constrained Decoding</td><td>Force JSON tool-call output via GBNF grammar. The model <em>must</em> produce a valid tool call.</td></tr>
                    <tr><td><strong>3</strong></td><td>Context Reset</td><td>Clear recent history, re-inject core context, fresh attempt with higher temperature (0.5). Last resort.</td></tr>
                </tbody>
            </table>
        </div>

        <p>AMI also maintains a <strong>failure catalog</strong> &mdash; a persistent dictionary of failure patterns per model, so it learns which recovery strategy works best for each situation.</p>

        <!-- ── Continuity ── -->
        <h2 id="continuity">Session Health Monitor (Continuity)</h2>
        <p><strong>What:</strong> Tracks 6 health signals to give your session a letter grade (A through F) and triggers auto-recovery when quality drops.</p>
        <p><strong>Why:</strong> Long coding sessions degrade AI quality. Context gets stale, decisions get forgotten, files drift out of scope. The Continuity Engine detects this before you notice it.</p>

        <h3>6 Health Signals</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Signal</th><th>What It Measures</th></tr></thead>
                <tbody>
                    <tr><td><strong>Objective Alignment</strong></td><td>Is the current context still aligned with your original goal? (semantic comparison)</td></tr>
                    <tr><td><strong>File Coverage</strong></td><td>Are the files relevant to your task still in context?</td></tr>
                    <tr><td><strong>Decision Retention</strong></td><td>Are prior decisions and plans still recalled in context?</td></tr>
                    <tr><td><strong>Swap Freshness</strong></td><td>How many turns since the last context swap? (recency)</td></tr>
                    <tr><td><strong>Recall Quality</strong></td><td>How accurate are semantic index retrievals? (if embeddings enabled)</td></tr>
                    <tr><td><strong>Working Memory Depth</strong></td><td>How much recent turn history is intact?</td></tr>
                </tbody>
            </table>
        </div>

        <p><strong>Grading:</strong> A (90-100) = excellent | B (75-89) = good | C (60-74) = degraded | D (40-59) = poor, auto-recovery triggered | F (0-39) = critical, multi-file refresh required.</p>
        <p>Check your grade with <code>/continuity</code>.</p>

        <!-- ── Genome ── -->
        <h2 id="genome">Learning Memory (Forge Genome)</h2>
        <p><strong>What:</strong> Persistent cross-session intelligence that makes Forge smarter over time.</p>
        <p><strong>Why:</strong> Every session teaches Forge something &mdash; which models fail on which tasks, what tool patterns work, how reliable your sessions are. This intelligence persists and improves the next session.</p>

        <h3>What the Genome Stores</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li>Session count, total turns, unique models used</li>
            <li>AMI failure catalog (per-model failure → effective fix mapping)</li>
            <li>Quality trend (last 50 quality scores)</li>
            <li>Per-model quality averages</li>
            <li>AMI routing accuracy (retry success rate)</li>
            <li>Continuity recovery rate</li>
            <li>Threat pattern distribution</li>
            <li>Tool success rates, benchmark pass rates</li>
            <li>Behavioral fingerprint (tool frequency, command frequency, session cadence)</li>
        </ul>
        <p>View your genome with <code>/license genome</code> or <code>/memory</code>.</p>

        <!-- ── Reliability ── -->
        <h2 id="reliability">Reliability Tracking</h2>
        <p><strong>What:</strong> Persistent cross-session health metrics that track Forge's reliability over a rolling 30-session window.</p>
        <p><strong>Why:</strong> Shows you whether Forge is getting more or less reliable over time, and breaks down exactly which metrics changed.</p>
        <h3>Composite Score Components</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li>Verification pass rate (25%) &mdash; How often do tests pass after AI changes?</li>
            <li>Continuity grade average (25%) &mdash; Average session health grade</li>
            <li>Tool success rate (20%) &mdash; Tool execution success percentage</li>
            <li>Duration stability (15%) &mdash; Consistent session lengths (rewards reliability)</li>
            <li>Token efficiency (15%) &mdash; Output tokens per turn (more = better)</li>
        </ul>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ SECURITY ══════════════ -->

        <h2 id="security">9-Layer Security Architecture</h2>
        <p><strong>What:</strong> Every AI response passes through 9 independent security layers before it can affect your code.</p>
        <p><strong>Why:</strong> AI models can be tricked by prompt injection, produce malicious code, or attempt data exfiltration. Forge's security system catches these threats at multiple levels.</p>

        <ol style="padding-left:24px; margin-bottom:16px; line-height:2.2">
            <li><strong>Pattern Scanner</strong> &mdash; 25+ regex patterns detect known injection, data theft, credential leaks, and obfuscation (zero-width chars, RTL overrides, encoded payloads).</li>
            <li><strong>Semantic Anomaly Detector</strong> &mdash; AI embeddings flag content that doesn't belong contextually. If a database utility suddenly discusses "executing shell commands," this layer catches it.</li>
            <li><strong>Behavioral Tripwire</strong> &mdash; Monitors tool call sequences for suspicious escalation patterns (e.g., file read followed by immediate curl/wget to external server).</li>
            <li><strong>Canary Trap</strong> &mdash; Random UUID injected into the system prompt. If the AI outputs it in a tool call, it proves prompt injection succeeded &mdash; action blocked.</li>
            <li><strong>Threat Intelligence</strong> &mdash; Auto-updating signature database with SHA-512 envelope validation, ReDoS protection (100ms timeout per regex), and reduce-only merging (external patterns can't lower threat levels).</li>
            <li><strong>Command Guard</strong> &mdash; 70+ regex rules block dangerous shell commands: piped downloads, PowerShell encoded commands, privilege escalation, credential theft, destructive operations.</li>
            <li><strong>Path Sandbox</strong> &mdash; File operations restricted to allowed directories. Symlink escape detection, null byte injection blocking.</li>
            <li><strong>Plan Verifier</strong> &mdash; Automatically runs tests, linter, and type checker after AI changes. Rolls back or repairs on failure.</li>
            <li><strong>Forensic Auditor</strong> &mdash; HMAC-SHA512 provenance chain creates tamper-proof session logs. If anyone modifies the log, the chain breaks.</li>
        </ol>

        <!-- ── Safety Levels ── -->
        <h2 id="safety-levels">Safety Levels</h2>
        <p><strong>What:</strong> Four progressively strict safety modes. Set via <code>/safety &lt;0-3&gt;</code> or <code>safety_level</code> in config.</p>

        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Level</th><th>Name</th><th>Description</th><th>Use Case</th></tr></thead>
                <tbody>
                    <tr><td>0</td><td>Unleashed</td><td>No restrictions. Everything runs immediately.</td><td>Trusted personal projects, experimentation</td></tr>
                    <tr><td>1</td><td>Smart Guard</td><td>Blocklist-only. Known dangerous commands blocked. <strong>(Default)</strong></td><td>Normal development</td></tr>
                    <tr><td>2</td><td>Confirm Writes</td><td>Prompt for confirmation on file writes. Auto-accept after 3s timeout.</td><td>Production codebases, team environments</td></tr>
                    <tr><td>3</td><td>Locked Down</td><td>Explicit approval required for every tool call.</td><td>Audited environments, compliance requirements</td></tr>
                </tbody>
            </table>
        </div>

        <!-- ── Threat Intel ── -->
        <h2 id="threat-intel">Threat Intelligence</h2>
        <p><strong>What:</strong> Upgradeable signature database for the Crucible threat scanner.</p>
        <p><strong>Why:</strong> New attack patterns emerge constantly. The threat intel system lets Forge update its defenses without a full software update.</p>
        <h3>Three Sources (Merged)</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Bundled</strong> &mdash; Ships with Forge in <code>forge/data/default_signatures.json</code></li>
            <li><strong>Fetched</strong> &mdash; Remote updates from server (SHA-512 validated, version-monotonic)</li>
            <li><strong>Custom</strong> &mdash; Your own patterns in <code>~/.forge/custom_signatures.json</code></li>
        </ul>
        <h3>Security Guarantees</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Reduce-Only Rule:</strong> External patterns can never lower threat levels set by hardcoded patterns</li>
            <li><strong>ReDoS Guard:</strong> Every regex tested with 100ms timeout on 10KB input before acceptance</li>
            <li><strong>Category Whitelist:</strong> Only 8 approved categories accepted</li>
            <li><strong>Atomic Writes:</strong> No partial or corrupt signature files</li>
        </ul>

        <!-- ── Forensics ── -->
        <h2 id="forensics">Forensics &amp; Audit Trail</h2>
        <p><strong>What:</strong> Compliance-ready session audit logging that tracks every action the AI takes.</p>
        <p><strong>Why:</strong> When something goes wrong (or goes right and you want to reproduce it), you need to know exactly what happened, when, and why.</p>
        <h3>Tracked Events (9 Categories)</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><code>file_read</code>, <code>file_write</code>, <code>file_edit</code> &mdash; All file operations with paths and sizes</li>
            <li><code>shell</code> &mdash; Commands executed, exit codes, output length</li>
            <li><code>tool</code> &mdash; Tool name, arguments (sanitized), results</li>
            <li><code>threat</code> &mdash; Crucible detections with category, severity, matched text</li>
            <li><code>context_swap</code>, <code>eviction</code> &mdash; Context management events</li>
            <li><code>error</code> &mdash; Exception types and messages</li>
        </ul>
        <p>View with <code>/forensics</code>. Export with <code>/export</code>. Reports saved to <code>~/.forge/forensics/</code>.</p>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ VOICE & INTERACTION ══════════════ -->

        <h2 id="voice">Voice I/O</h2>
        <p><strong>What:</strong> Talk to Forge with your voice. Responses can be read back aloud. Everything runs locally.</p>
        <p><strong>Why:</strong> Hands-free coding. Describe what you want while looking at reference material, whiteboarding, or just thinking out loud.</p>

        <h3>Speech-to-Text (Input)</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Engine:</strong> faster-whisper (OpenAI Whisper, optimized for speed)</li>
            <li><strong>Models:</strong> tiny, base, small, medium (tiny is default for low latency)</li>
            <li><strong>Modes:</strong> Push-to-talk (backtick key) or voice-activated (VOX, continuous monitoring)</li>
            <li><strong>GPU accelerated:</strong> Uses CUDA when available</li>
        </ul>

        <h3>Text-to-Speech (Output)</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Engine:</strong> Microsoft Edge TTS (free, high quality)</li>
            <li><strong>Default voice:</strong> en-US-GuyNeural (5 voice options)</li>
            <li><strong>Non-blocking:</strong> Audio plays in background thread</li>
            <li><strong>Smart filtering:</strong> Strips markdown, code blocks, file paths for natural speech</li>
        </ul>

        <p><strong>Configuration:</strong></p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code>voice_model: "tiny"          # whisper model size
voice_language: "en"         # ISO language code
voice_vox_threshold: 0.02    # RMS threshold for VOX
voice_silence_timeout: 1.5   # seconds of silence to end recording</code></pre>
        </div>

        <p>Toggle with <code>/voice</code>. Optional dependencies: <code>faster-whisper</code>, <code>sounddevice</code>, <code>pynput</code>.</p>

        <!-- ── Themes ── -->
        <h2 id="themes">Themes &amp; Dashboard</h2>
        <p><strong>What:</strong> 14 built-in themes from dark minimalist to full cyberpunk. Three themes include live visual effects (particles, edge glow, crackle).</p>
        <p><strong>How:</strong> Switch with <code>/theme &lt;name&gt;</code>. Open the full dashboard with <code>/dashboard</code>.</p>

        <div class="theme-grid" style="margin:20px 0">
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

        <p><strong>Dashboard features:</strong> Neural Cortex brain visualization (9 animated states), live session stats, system health cards, real-time status updates. The brain animation reflects what Forge is doing &mdash; thinking, executing, indexing, scanning for threats.</p>

        <!-- ── Plugins ── -->
        <h2 id="plugins">Plugin System</h2>
        <p><strong>What:</strong> Build custom plugins that hook into Forge's lifecycle events.</p>
        <p><strong>Why:</strong> Extend Forge with custom behavior &mdash; log to your own system, modify AI prompts, add custom commands, filter outputs.</p>

        <h3>6 Hook Points</h3>
        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Hook</th><th>When It Fires</th></tr></thead>
                <tbody>
                    <tr><td><code>on_user_input(text)</code></td><td>Before user input is sent to the AI. Can modify or observe.</td></tr>
                    <tr><td><code>on_ai_response(response)</code></td><td>After AI response, before display. Can intercept.</td></tr>
                    <tr><td><code>on_tool_call(name, args)</code></td><td>Before tool execution. Can block or modify.</td></tr>
                    <tr><td><code>on_command(cmd, arg)</code></td><td>On slash command. Can handle custom commands.</td></tr>
                    <tr><td><code>on_file_read(path, content)</code></td><td>After file read. Can post-process content.</td></tr>
                    <tr><td><code>on_context_add(entry)</code></td><td>When new context is added. Can react or filter.</td></tr>
                </tbody>
            </table>
        </div>

        <p><strong>How to create a plugin:</strong></p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># ~/.forge/plugins/my_plugin.py
from forge.plugins.base import ForgePlugin

class MyPlugin(ForgePlugin):
    priority = 50  # Lower = runs first

    def on_load(self, engine):
        self.engine = engine
        print("My plugin loaded!")

    def on_tool_call(self, name, args):
        print(f"Tool called: {name}")
        return args  # Return modified args or None to block</code></pre>
        </div>
        <p>Plugins are auto-discovered from <code>~/.forge/plugins/</code>. Reload with <code>/plugins reload</code>.</p>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ LICENSING & FLEET ══════════════ -->

        <h2 id="licensing">Tiers &amp; Pricing</h2>
        <p><strong>What:</strong> Three tiers with different seat counts and feature access.</p>

        <div class="table-wrap" style="margin:16px 0">
            <table>
                <thead><tr><th>Feature</th><th>Community (Free)</th><th>Pro ($199)</th><th>Power ($999)</th></tr></thead>
                <tbody>
                    <tr><td>Seats</td><td>1</td><td>3</td><td>10</td></tr>
                    <tr><td>All 59 commands</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>All 28 tools</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>9-layer security</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>14 themes + dashboard</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>Genome persistence</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>AutoForge (auto-commit)</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>Shipwright (release mgmt)</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>Enterprise mode</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>Fleet analytics</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                </tbody>
            </table>
        </div>
        <p>Monthly alternatives available: Pro $19/mo, Power $79/mo. See <a href="/Forge/#pricing">pricing page</a>.</p>

        <!-- ── Activation ── -->
        <h2 id="activation">Activation</h2>
        <p><strong>What:</strong> How to activate your purchased license.</p>

        <h3>Master Activation</h3>
        <ol style="padding-left:24px; margin-bottom:16px">
            <li>Purchase a tier from the <a href="/Forge/#pricing">pricing page</a></li>
            <li>Download your passport file from the success page</li>
            <li>In Forge, run: <code>/license activate passport.json</code></li>
            <li>Forge validates the cryptographic signature and activates your Master role</li>
        </ol>

        <h3>Puppet Activation</h3>
        <ol style="padding-left:24px; margin-bottom:16px">
            <li>On your Master machine: <code>/puppet generate DevBox</code></li>
            <li>Transfer the generated passport file to the target machine</li>
            <li>On the target machine: <code>/puppet join puppet_passport.json</code></li>
            <li>Forge validates the chain of trust back to Origin and activates</li>
        </ol>

        <div class="callout warn">
            <strong>Security:</strong> Passport files contain cryptographic license credentials. Keep them secure. If compromised, use <code>/puppet revoke &lt;machine_id&gt;</code> to instantly invalidate.
        </div>

        <!-- ── Fleet ── -->
        <h2 id="fleet">Master/Puppet Fleet</h2>
        <p><strong>What:</strong> Run Forge on multiple machines from a single license.</p>
        <p><strong>Why:</strong> Developers often work on multiple machines (desktop, laptop, work machine). Instead of buying separate licenses, you get N seats and distribute them.</p>

        <h3>Hierarchy</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><strong>Master</strong> &mdash; You. Owns the tier, controls the seat pool, generates Puppet passports, can revoke any Puppet.</li>
            <li><strong>Puppet</strong> &mdash; Your other machines. Each uses one seat. Cannot distribute further. Validated against Master's chain of trust.</li>
        </ul>

        <h3>Fleet Commands</h3>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code>/puppet seats              # Check seat allocation
/puppet generate WorkLaptop  # Create puppet passport (uses 1 seat)
/puppet list               # List all fleet members with status
/puppet revoke &lt;id&gt;        # Instantly revoke a puppet's access
/puppet sync               # Force genome sync to master
/puppet status             # Your role, tier, and fleet summary</code></pre>
        </div>

        <!-- ── BPoS ── -->
        <h2 id="bpos">Behavioral Proof of Stake</h2>
        <p><strong>What:</strong> Forge's anti-piracy system. Five layers that make a pirated copy functionally inferior to a legitimate one.</p>
        <p><strong>Why:</strong> Traditional DRM frustrates paying customers. BPoS takes a different approach: legitimate copies genuinely work better because they accumulate intelligence that pirated copies can't replicate.</p>

        <ol style="padding-left:24px; margin-bottom:16px; line-height:2.2">
            <li><strong>Chain of Being</strong> &mdash; HMAC-SHA512 signed identity chain. Every passport traced back to Origin.</li>
            <li><strong>Forge Genome</strong> &mdash; Accumulated behavioral intelligence. Pirated copy starts at zero.</li>
            <li><strong>Symbiotic Capability Scaling</strong> &mdash; AMI, Continuity, and Router genuinely improve with usage.</li>
            <li><strong>Ambient Verification</strong> &mdash; Behavioral fingerprinting detects anomalous usage patterns.</li>
            <li><strong>Passport Token</strong> &mdash; Cryptographically signed, account-bound, role-encoded (v2 protocol).</li>
        </ol>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">

        <!-- ══════════════ ADVANCED ══════════════ -->

        <h2 id="config">Configuration Reference</h2>
        <p><strong>What:</strong> All 97 configuration parameters in <code>~/.forge/config.yaml</code>.</p>
        <p><strong>How:</strong> Edit directly or use <code>/config &lt;key&gt; &lt;value&gt;</code>. Invalid values are logged with fallback to defaults.</p>

        <input type="text" placeholder="Filter config..." data-filter-target="config-table" style="width:100%; padding:10px 14px; background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius-md); color:var(--text); font-size:0.92em; margin-bottom:16px">

        <div class="table-wrap" id="config-table">
            <table>
                <thead><tr><th style="width:260px">Parameter</th><th style="width:100px">Default</th><th>Description</th></tr></thead>
                <tbody>
                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SAFETY &amp; SECURITY</td></tr>
                    <tr><td><code>safety_level</code></td><td>1</td><td>Safety tier: 0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down</td></tr>
                    <tr><td><code>sandbox_enabled</code></td><td>false</td><td>Restrict file operations to sandbox_roots directories</td></tr>
                    <tr><td><code>threat_signatures_enabled</code></td><td>true</td><td>Load and use threat signature database</td></tr>
                    <tr><td><code>threat_signatures_url</code></td><td>""</td><td>Custom URL for remote threat signatures</td></tr>
                    <tr><td><code>threat_auto_update</code></td><td>true</td><td>Auto-check for signature updates</td></tr>
                    <tr><td><code>output_scanning</code></td><td>true</td><td>Scan LLM output for secrets and threats</td></tr>
                    <tr><td><code>rag_scanning</code></td><td>true</td><td>Scan RAG retrievals before context injection</td></tr>
                    <tr><td><code>data_retention_days</code></td><td>30</td><td>Auto-prune forensic logs older than N days</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">MODEL &amp; LLM</td></tr>
                    <tr><td><code>backend_provider</code></td><td>"ollama"</td><td>LLM backend: ollama, openai, or anthropic</td></tr>
                    <tr><td><code>default_model</code></td><td>"qwen2.5-coder:14b"</td><td>Primary model for coding tasks</td></tr>
                    <tr><td><code>small_model</code></td><td>""</td><td>Fast model for routing (e.g., qwen2.5-coder:3b)</td></tr>
                    <tr><td><code>router_enabled</code></td><td>false</td><td>Auto-route tasks to optimal model by complexity</td></tr>
                    <tr><td><code>embedding_model</code></td><td>"nomic-embed-text"</td><td>Model for semantic search embeddings</td></tr>
                    <tr><td><code>ollama_url</code></td><td>"http://localhost:11434"</td><td>Ollama API endpoint</td></tr>
                    <tr><td><code>openai_api_key</code></td><td>""</td><td>OpenAI API key (or OPENAI_API_KEY env var)</td></tr>
                    <tr><td><code>anthropic_api_key</code></td><td>""</td><td>Anthropic API key (or ANTHROPIC_API_KEY env var)</td></tr>
                    <tr><td><code>openai_base_url</code></td><td>""</td><td>Custom OpenAI-compatible endpoint URL</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">CONTEXT WINDOW</td></tr>
                    <tr><td><code>context_safety_margin</code></td><td>0.85</td><td>Use this fraction of calculated max context</td></tr>
                    <tr><td><code>swap_threshold_pct</code></td><td>85</td><td>Auto-swap context at this % usage</td></tr>
                    <tr><td><code>swap_summary_target_tokens</code></td><td>500</td><td>Target token count when summarizing old context</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">AGENT &amp; TOOLS</td></tr>
                    <tr><td><code>max_agent_iterations</code></td><td>15</td><td>Max tool-call loops per user turn</td></tr>
                    <tr><td><code>shell_timeout</code></td><td>30</td><td>Shell command timeout in seconds</td></tr>
                    <tr><td><code>shell_max_output</code></td><td>10000</td><td>Truncate shell output at this many characters</td></tr>
                    <tr><td><code>dedup_enabled</code></td><td>true</td><td>Suppress near-duplicate tool calls</td></tr>
                    <tr><td><code>dedup_threshold</code></td><td>0.92</td><td>Similarity threshold for dedup (0.0-1.0)</td></tr>
                    <tr><td><code>dedup_window</code></td><td>5</td><td>Recent calls to compare per tool</td></tr>
                    <tr><td><code>rate_limiting</code></td><td>true</td><td>Circuit breaker for runaway tool loops</td></tr>
                    <tr><td><code>rate_limit_per_minute</code></td><td>30</td><td>Max tool calls per sliding minute</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">VOICE</td></tr>
                    <tr><td><code>voice_model</code></td><td>"tiny"</td><td>Whisper model size: tiny, base, small, medium</td></tr>
                    <tr><td><code>voice_language</code></td><td>"en"</td><td>ISO language code for STT</td></tr>
                    <tr><td><code>voice_vox_threshold</code></td><td>0.02</td><td>RMS threshold for voice-activation mode</td></tr>
                    <tr><td><code>voice_silence_timeout</code></td><td>1.5</td><td>Seconds of silence to end recording</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">UI &amp; PERSONA</td></tr>
                    <tr><td><code>theme</code></td><td>"midnight"</td><td>Color theme (14 options)</td></tr>
                    <tr><td><code>effects_enabled</code></td><td>true</td><td>Animated visual effects in themes that support them</td></tr>
                    <tr><td><code>terminal_mode</code></td><td>"console"</td><td>Interface mode: console or gui</td></tr>
                    <tr><td><code>persona</code></td><td>"professional"</td><td>AI persona: professional, casual, mentor, hacker</td></tr>
                    <tr><td><code>show_hardware_on_start</code></td><td>true</td><td>Show GPU/CPU info on startup</td></tr>
                    <tr><td><code>show_billing_on_start</code></td><td>true</td><td>Show token balance on startup</td></tr>
                    <tr><td><code>show_cache_on_start</code></td><td>true</td><td>Show cache stats on startup</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">CONTINUITY &amp; AMI</td></tr>
                    <tr><td><code>continuity_enabled</code></td><td>true</td><td>Track session health and continuity grade</td></tr>
                    <tr><td><code>continuity_threshold</code></td><td>60</td><td>Score below this triggers mild recovery</td></tr>
                    <tr><td><code>continuity_aggressive_threshold</code></td><td>40</td><td>Score below this triggers aggressive recovery</td></tr>
                    <tr><td><code>ami_enabled</code></td><td>true</td><td>Adaptive Model Intelligence (self-healing)</td></tr>
                    <tr><td><code>ami_max_retries</code></td><td>3</td><td>Max recovery attempts per turn</td></tr>
                    <tr><td><code>ami_quality_threshold</code></td><td>0.7</td><td>Quality score below this triggers AMI</td></tr>
                    <tr><td><code>ami_auto_probe</code></td><td>true</td><td>Auto-detect model capabilities on first use</td></tr>
                    <tr><td><code>ami_constrained_fallback</code></td><td>true</td><td>Use GBNF grammar for forced tool compliance</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">PLAN VERIFICATION</td></tr>
                    <tr><td><code>plan_mode</code></td><td>"off"</td><td>Plan mode: off, manual, auto, always</td></tr>
                    <tr><td><code>plan_auto_threshold</code></td><td>3</td><td>Complexity score to auto-trigger planning</td></tr>
                    <tr><td><code>plan_verify_mode</code></td><td>"off"</td><td>Verification: off, report, repair, strict</td></tr>
                    <tr><td><code>plan_verify_tests</code></td><td>true</td><td>Run tests after each AI change</td></tr>
                    <tr><td><code>plan_verify_lint</code></td><td>false</td><td>Run linter after each AI change</td></tr>
                    <tr><td><code>plan_verify_timeout</code></td><td>30</td><td>Max seconds for test/lint suite</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">ENTERPRISE &amp; LICENSING</td></tr>
                    <tr><td><code>enterprise_mode</code></td><td>false</td><td>Strict verification, forced safety 2+, audit export</td></tr>
                    <tr><td><code>license_tier</code></td><td>"community"</td><td>License tier: community, pro, power</td></tr>
                    <tr><td><code>auto_commit</code></td><td>false</td><td>AutoForge: auto-commit file edits after each turn</td></tr>
                    <tr><td><code>shipwright_llm_classify</code></td><td>false</td><td>Use LLM for commit classification (slower, more accurate)</td></tr>
                    <tr><td><code>starting_balance</code></td><td>50.0</td><td>Virtual token budget in credits</td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">TELEMETRY &amp; BUG REPORTER</td></tr>
                    <tr><td><code>telemetry_enabled</code></td><td>false</td><td>Send anonymized performance data on session end</td></tr>
                    <tr><td><code>telemetry_redact</code></td><td>true</td><td>Strip prompts and responses from telemetry</td></tr>
                    <tr><td><code>telemetry_label</code></td><td>""</td><td>Machine nickname for telemetry dashboard</td></tr>
                    <tr><td><code>bug_reporter_enabled</code></td><td>false</td><td>Auto-file GitHub issues on crashes (owner only)</td></tr>
                    <tr><td><code>bug_reporter_max_daily</code></td><td>10</td><td>Max auto-filed issues per day</td></tr>
                </tbody>
            </table>
        </div>

        <!-- ── Enterprise ── -->
        <h2 id="enterprise">Enterprise Mode</h2>
        <p><strong>What:</strong> Strict operating mode for regulated environments. Requires Power tier.</p>
        <p><strong>Why:</strong> When you need audit trails, verified changes, and enforced safety for compliance requirements.</p>
        <p><strong>What it enables:</strong></p>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li>Safety level enforced at 2+ (cannot be lowered)</li>
            <li>Strict plan verification (unverified plans blocked)</li>
            <li>Forensic logging on all tool calls (mandatory)</li>
            <li>Audit export with chain-of-custody manifests</li>
            <li>Fleet analytics dashboard access</li>
            <li>Reproducible benchmark suite</li>
        </ul>

        <!-- ── Benchmark ── -->
        <h2 id="benchmark">Benchmark Suite</h2>
        <p><strong>What:</strong> Reproducible coding benchmarks that test any model against deterministic scenarios in isolated temp directories.</p>
        <p><strong>Why:</strong> Compare models objectively. Track quality over time. Prove to stakeholders that your AI setup works.</p>
        <p><strong>How:</strong> Run <code>/benchmark</code>. Results stored in <code>~/.forge/benchmarks/</code> with exact prompt hashes, model info, and config for reproducibility.</p>
        <p><strong>Metrics tracked:</strong> pass/fail, behavior preserved (tests still pass), file scope accuracy, iteration count, quality score, token counts.</p>

        <!-- ── Shipwright ── -->
        <h2 id="shipwright">Shipwright (Release Management)</h2>
        <p><strong>What:</strong> AI-powered release management. Classifies commits, determines version bumps, generates changelogs.</p>
        <p><strong>Why:</strong> Automates the tedious parts of releasing software while keeping you in control.</p>
        <h3>Commands</h3>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><code>/ship status</code> &mdash; Current version, unreleased commits, suggested bump</li>
            <li><code>/ship dry</code> &mdash; Preview next release without modifying anything</li>
            <li><code>/ship preflight</code> &mdash; Run tests + lint before release</li>
            <li><code>/ship go</code> &mdash; Tag, bump version, push (irreversible)</li>
            <li><code>/ship changelog</code> &mdash; Generate formatted changelog</li>
            <li><code>/ship history</code> &mdash; Show past releases</li>
        </ul>
        <p>Uses 25+ rules for commit classification (breaking, feature, fix, docs, tests, security, performance). Unclassified commits optionally passed to LLM for semantic analysis.</p>

        <!-- ── AutoForge ── -->
        <h2 id="autoforge">AutoForge (Smart Auto-Commit)</h2>
        <p><strong>What:</strong> Automatically commits file changes after each AI turn. Smart batching groups related edits into single commits.</p>
        <p><strong>Why:</strong> Never lose AI-generated changes. Every turn = one coherent commit with auto-generated message.</p>
        <ul style="padding-left:24px; margin-bottom:16px">
            <li><code>/autocommit on</code> / <code>off</code> / <code>status</code></li>
            <li><code>/autocommit hook</code> &mdash; Generate Claude Code hook for automatic triggering</li>
        </ul>

        <!-- ── Telemetry ── -->
        <h2 id="telemetry">Telemetry</h2>
        <p><strong>What:</strong> Optional, anonymized performance telemetry. <strong>Disabled by default.</strong></p>
        <p><strong>Why:</strong> Helps improve Forge by sending hardware profiles, token rates, and reliability scores. No prompts, no responses, no source code.</p>
        <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code>telemetry_enabled: true    # Opt in
telemetry_redact: true     # Strip all user content (default)
telemetry_label: "my-pc"   # Machine nickname for dashboard</code></pre>
        </div>

        <hr style="border:none; border-top:1px solid var(--border); margin:32px 0">
        <p class="text-center text-dim" style="margin-top:40px">
            &copy; <?php echo date('Y'); ?> Forge by Dirt Star &bull;
            <a href="/Forge/">Home</a> &bull;
            <a href="account.php">Account</a>
        </p>

    </div>
</div>

<script>
/* ── Scroll-spy: highlight active sidebar link ── */
(function(){
    var sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    var links = sidebar.querySelectorAll('a[href^="#"]');
    if (!links.length) return;

    var sections = [];
    links.forEach(function(link) {
        var id = link.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (el) sections.push({el: el, link: link});
    });

    var ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function() {
            var scrollY = window.scrollY + 120;
            var current = null;
            for (var i = 0; i < sections.length; i++) {
                if (sections[i].el.offsetTop <= scrollY) {
                    current = sections[i];
                }
            }
            links.forEach(function(l){ l.classList.remove('active'); });
            if (current) current.link.classList.add('active');
            ticking = false;
        });
    }

    window.addEventListener('scroll', onScroll, {passive: true});
    onScroll();
})();
</script>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
