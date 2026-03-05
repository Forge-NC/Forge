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
        <a href="#commands">Commands (55)</a>
        <a href="#tools">Tool System (27)</a>
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
        <a href="#config">Configuration (70+)</a>
        <a href="#enterprise">Enterprise Mode</a>
        <a href="#benchmark">Benchmark Suite</a>
        <a href="#shipwright">Shipwright</a>
        <a href="#autoforge">AutoForge</a>
        <a href="#telemetry">Telemetry</a>
    </div>
    <div class="sidebar-offset"></div>

    <div class="sidebar-content">

        <h1 style="border-bottom:1px solid var(--border); padding-bottom:16px; margin-bottom:8px">Forge Documentation</h1>
        <p style="margin-bottom:32px">Forge is a local AI coding assistant that runs entirely on your hardware. 55 commands, 27 AI tools, 14 themes, 9-layer security, voice I/O, plugin system, and multi-model intelligence &mdash; all offline, all yours.</p>

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
        <p><strong>What:</strong> 55 slash commands for controlling every aspect of Forge.</p>
        <p><strong>How:</strong> Type any command at the <code>forge&gt;</code> prompt. Use <code>/help</code> to see them all.</p>

        <input type="text" placeholder="Filter commands..." data-filter-target="cmd-table" style="width:100%; padding:10px 14px; background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius-md); color:var(--text); font-size:0.92em; margin-bottom:16px">

        <div class="table-wrap" style="margin:16px 0" id="cmd-table">
            <table>
                <thead><tr><th style="width:210px">Command</th><th>Description</th><th style="width:160px">Example</th></tr></thead>
                <tbody>
                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SYSTEM</td></tr>
                    <tr><td><code>/help</code></td><td>Show all available commands with descriptions</td><td><code>/help</code></td></tr>
                    <tr><td><code>/docs</code></td><td>Open documentation window (F1 shortcut)</td><td><code>/docs</code></td></tr>
                    <tr><td><code>/quit</code> / <code>/exit</code></td><td>Exit Forge with auto-save</td><td><code>/quit</code></td></tr>
                    <tr><td><code>/dashboard</code></td><td>Open the Neural Cortex HUD dashboard</td><td><code>/dashboard</code></td></tr>
                    <tr><td><code>/voice</code></td><td>Toggle voice input/output (requires audio deps)</td><td><code>/voice</code></td></tr>
                    <tr><td><code>/theme &lt;name&gt;</code></td><td>Switch UI theme (14 built-in themes)</td><td><code>/theme cyberpunk</code></td></tr>
                    <tr><td><code>/update</code></td><td>Check for Forge updates</td><td><code>/update</code></td></tr>
                    <tr><td><code>/cd &lt;dir&gt;</code></td><td>Change working directory</td><td><code>/cd ../other-project</code></td></tr>
                    <tr><td><code>/plugins</code></td><td>List/reload custom plugins</td><td><code>/plugins reload</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">MODEL &amp; TOOLS</td></tr>
                    <tr><td><code>/model &lt;name&gt;</code></td><td>Switch the active AI model</td><td><code>/model qwen2.5-coder:7b</code></td></tr>
                    <tr><td><code>/models</code></td><td>Open Model Manager GUI (pull/delete/browse)</td><td><code>/models</code></td></tr>
                    <tr><td><code>/tools</code></td><td>List all 27 registered AI tools with call stats</td><td><code>/tools</code></td></tr>
                    <tr><td><code>/router</code></td><td>Show multi-model routing decisions and stats</td><td><code>/router</code></td></tr>
                    <tr><td><code>/compare</code></td><td>Compare model outputs side-by-side on same prompt</td><td><code>/compare</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">CONTEXT &amp; MEMORY</td></tr>
                    <tr><td><code>/context</code></td><td>Show context window usage with token breakdown by partition</td><td><code>/context</code></td></tr>
                    <tr><td><code>/pin &lt;idx&gt;</code></td><td>Pin a context entry so it survives eviction</td><td><code>/pin 3</code></td></tr>
                    <tr><td><code>/unpin &lt;idx&gt;</code></td><td>Remove pin from context entry</td><td><code>/unpin 3</code></td></tr>
                    <tr><td><code>/drop &lt;idx&gt;</code></td><td>Manually evict a context entry to free tokens</td><td><code>/drop 5</code></td></tr>
                    <tr><td><code>/clear</code></td><td>Clear all non-pinned context entries</td><td><code>/clear</code></td></tr>
                    <tr><td><code>/save &lt;name&gt;</code></td><td>Save entire session to file (full fidelity)</td><td><code>/save my-session</code></td></tr>
                    <tr><td><code>/load &lt;name&gt;</code></td><td>Restore a previously saved session</td><td><code>/load my-session</code></td></tr>
                    <tr><td><code>/reset</code></td><td>Hard reset &mdash; clear everything and start fresh</td><td><code>/reset</code></td></tr>
                    <tr><td><code>/memory</code></td><td>View Forge Genome (accumulated intelligence)</td><td><code>/memory</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SEARCH &amp; INDEXING</td></tr>
                    <tr><td><code>/scan &lt;dir&gt;</code></td><td>Scan directory for indexable files</td><td><code>/scan src/</code></td></tr>
                    <tr><td><code>/index</code></td><td>Build/rebuild semantic embedding index</td><td><code>/index</code></td></tr>
                    <tr><td><code>/search &lt;query&gt;</code></td><td>Full-text search across codebase</td><td><code>/search "handleAuth"</code></td></tr>
                    <tr><td><code>/journal &lt;query&gt;</code></td><td>Semantic search via embeddings (conceptual matches)</td><td><code>/journal authentication</code></td></tr>
                    <tr><td><code>/recall &lt;query&gt;</code></td><td>Recall relevant context from long-term memory</td><td><code>/recall database schema</code></td></tr>
                    <tr><td><code>/digest</code></td><td>Show structured codebase summary</td><td><code>/digest</code></td></tr>
                    <tr><td><code>/synapse</code></td><td>Analyze file dependencies and import graph</td><td><code>/synapse</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">SAFETY &amp; SECURITY</td></tr>
                    <tr><td><code>/safety &lt;0-3&gt;</code></td><td>Set safety level (0=off, 1=smart, 2=confirm, 3=locked)</td><td><code>/safety 2</code></td></tr>
                    <tr><td><code>/crucible</code></td><td>Threat scanner status and toggle</td><td><code>/crucible</code></td></tr>
                    <tr><td><code>/forensics</code></td><td>View forensic audit trail for current session</td><td><code>/forensics</code></td></tr>
                    <tr><td><code>/threats</code></td><td>View threat intelligence signatures and hit counts</td><td><code>/threats</code></td></tr>
                    <tr><td><code>/provenance</code></td><td>View cryptographic provenance chain history</td><td><code>/provenance</code></td></tr>
                    <tr><td><code>/plan</code></td><td>View or create execution plans for complex tasks</td><td><code>/plan</code></td></tr>
                    <tr><td><code>/dedup</code></td><td>Tool call deduplication status and threshold</td><td><code>/dedup</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">AI INTELLIGENCE</td></tr>
                    <tr><td><code>/ami</code></td><td>Self-healing AI status: recovery rates, failure catalog</td><td><code>/ami</code></td></tr>
                    <tr><td><code>/continuity</code></td><td>Session health grade (A-F) with 6 signal breakdown</td><td><code>/continuity</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">DIAGNOSTICS &amp; REPORTING</td></tr>
                    <tr><td><code>/stats</code></td><td>Session statistics (turns, tokens, tool calls, timing)</td><td><code>/stats</code></td></tr>
                    <tr><td><code>/billing</code></td><td>Token usage and virtual cost tracking</td><td><code>/billing</code></td></tr>
                    <tr><td><code>/tasks</code></td><td>View current task list and subtasks</td><td><code>/tasks</code></td></tr>
                    <tr><td><code>/report</code></td><td>Generate formatted session report</td><td><code>/report</code></td></tr>
                    <tr><td><code>/export</code></td><td>Export session artifacts (markdown, JSON, ZIP)</td><td><code>/export</code></td></tr>
                    <tr><td><code>/benchmark</code></td><td>Run reproducible coding benchmarks</td><td><code>/benchmark</code></td></tr>
                    <tr><td><code>/hardware</code></td><td>Show GPU, CPU, VRAM, and model recommendations</td><td><code>/hardware</code></td></tr>
                    <tr><td><code>/cache</code></td><td>File read cache statistics and management</td><td><code>/cache clear</code></td></tr>
                    <tr><td><code>/config</code></td><td>View or edit ~/.forge/config.yaml</td><td><code>/config safety_level</code></td></tr>
                    <tr><td><code>/topup</code></td><td>Top up virtual token budget</td><td><code>/topup</code></td></tr>

                    <tr><td colspan="3" style="background:var(--bg-card); color:var(--accent); font-weight:600; font-size:0.88em; letter-spacing:1px">FLEET &amp; LICENSING</td></tr>
                    <tr><td><code>/license status</code></td><td>Show current tier, genome maturity, and features</td><td><code>/license status</code></td></tr>
                    <tr><td><code>/license activate</code></td><td>Activate a purchased license passport</td><td><code>/license activate passport.json</code></td></tr>
                    <tr><td><code>/license genome</code></td><td>View accumulated Forge Genome intelligence</td><td><code>/license genome</code></td></tr>
                    <tr><td><code>/license tiers</code></td><td>Show available tiers and features</td><td><code>/license tiers</code></td></tr>
                    <tr><td><code>/puppet status</code></td><td>Fleet role, tier, and seat allocation</td><td><code>/puppet status</code></td></tr>
                    <tr><td><code>/puppet generate</code></td><td>Generate Puppet passport from seat pool</td><td><code>/puppet generate DevBox</code></td></tr>
                    <tr><td><code>/puppet join</code></td><td>Join a fleet as Puppet</td><td><code>/puppet join puppet.json</code></td></tr>
                    <tr><td><code>/puppet list</code></td><td>List all fleet members with status</td><td><code>/puppet list</code></td></tr>
                    <tr><td><code>/puppet revoke</code></td><td>Revoke a Puppet's seat</td><td><code>/puppet revoke machine-id</code></td></tr>
                    <tr><td><code>/puppet sync</code></td><td>Force genome sync to master</td><td><code>/puppet sync</code></td></tr>
                    <tr><td><code>/puppet seats</code></td><td>Show seat allocation details</td><td><code>/puppet seats</code></td></tr>
                    <tr><td><code>/ship</code></td><td>Shipwright release management</td><td><code>/ship status</code></td></tr>
                    <tr><td><code>/autocommit</code></td><td>Smart auto-commit toggle</td><td><code>/autocommit on</code></td></tr>
                    <tr><td><code>/admin</code></td><td>Server administration (owner only)</td><td><code>/admin</code></td></tr>
                </tbody>
            </table>
        </div>

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
                    <tr><td>All 55 commands</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                    <tr><td>All 27 tools</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
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
        <p><strong>What:</strong> All 70+ configuration parameters in <code>~/.forge/config.yaml</code>.</p>
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

<?php require_once __DIR__ . '/includes/footer.php'; ?>
