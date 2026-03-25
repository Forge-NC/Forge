<p align="center">
  <img src="https://forge-nc.dev/assets/brain.webp" alt="Forge" width="128">
</p>

<h1 align="center">Forge</h1>

<p align="center">
  <strong>AI you can verify, not just trust.</strong>
</p>

<p align="center">
  <a href="https://forge-nc.dev">Website</a> &middot;
  <a href="https://forge-nc.dev/docs.php">Documentation</a> &middot;
  <a href="https://forge-nc.dev/matrix.php">The Matrix</a> &middot;
  <a href="#quick-start">Quick Start</a>
</p>

---

AI tools help you write code. But none of them tell you whether the model you're trusting with your codebase is actually safe, reliable, or honest. You're supposed to just... trust it.

Forge is a local AI coding assistant that also audits the AI it runs. Write code with any Ollama model. Then stress-test that model across safety, reliability, adversarial resistance, data exfiltration, context integrity, and more. Get a cryptographically signed report of exactly what happened. Every session is logged, every tool call is recorded, every context decision is visible.

**The [Forge Matrix™](https://forge-nc.dev/matrix.php) aggregates test results from every user into a crowdsourced model intelligence map -- like Rotten Tomatoes, but for AI models.** See which models hold up under pressure, which ones collapse, and where the gaps are across the entire open-source ecosystem. Users run the tests. The data speaks for itself.

Everything runs on your hardware. Nothing leaves your machine unless you opt in.

```
git clone https://github.com/Forge-NC/Forge.git
cd Forge && python install.py
```

79,000+ lines of Python. 1,318 tests. 60 commands. Zero telemetry by default.

## The Coding Assistant

Download Forge, pick a model, start coding. Every user gets:

- **Tool use** -- Forge gives the model hands. File read/write/edit, git operations, web requests, tree-sitter AST navigation across 8+ languages, codebase indexing with semantic search, and a digest engine for whole-project analysis.
- **Context window management** -- most AI tools silently compact or drop context when the window fills up. Forge partitions context into priority tiers, scores each entry by importance, and evicts deterministically so you always know what the model can see and what it can't. Every eviction is logged. A real-time continuity grade (A-F) monitors 6 quality signals after every swap and triggers automatic recovery -- re-reading critical files and re-injecting decisions -- when quality degrades. Nothing is silently lost.
- **Multi-model routing** -- route simple tasks to a small fast model (3B) and complex tasks to your primary model (14B-70B). Saves tokens without sacrificing quality where it matters. Forge auto-detects your GPU and recommends the best fit.
- **Plan mode** -- break complex tasks into steps with test/lint verification gates between each one. The model executes, Forge verifies.
- **Episodic memory** -- long-term recall with embeddings that persists across sessions. Forge remembers what you worked on, what decisions were made, and what the model learned about your project.
- **Billing ledger** -- token-level cost accounting with per-turn tracking. Compare your local costs against cloud providers with `/compare`.
- **Voice input** -- push-to-talk or voice-activated dictation via faster-whisper.
- **14 visual themes** -- midnight, obsidian, dracula, nord, monokai, cyberpunk, matrix, amber, phosphor, arctic, sunset, od_green, plasma, solarized_dark. Hot-swap with `/theme`.
- **Plugin system** -- 17 hooks for extending Forge behavior. Drop a `.py` file in `~/.forge/plugins/` and it loads automatically.
- **Neural Cortex GUI** -- full dashboard with brain animation, performance cards, HUD menu, model manager, settings dialog, and visual effects engine. Or use the console terminal if you prefer.

## The Auditing Platform

Opt in to Forge's testing and assurance infrastructure and you get a full AI auditing toolkit:

### `/break` -- Adversarial Stress Testing

Run your model through structured adversarial scenarios and get a scored report. Categories tested:

| Category | What It Tests |
|----------|---------------|
| **Safety** | Harm refusal, jailbreak resistance, social engineering, unsafe code generation |
| **Reliability** | Instruction following, output consistency, edge case handling, long-context coherence |
| **Adversarial** | Prompt injection, role hijacking, context manipulation, multi-turn attacks |
| **Tool Misuse** | Hallucinated tool calls, unauthorized file access, command injection attempts |
| **Exfiltration** | Data leakage, credential extraction, side-channel attempts |
| **Context Integrity** | Memory poisoning, instruction persistence, context window manipulation |
| **Data Residency** | Cross-session data bleed, PII retention, workspace isolation |
| **Audit Integrity** | Log tampering resistance, forensic record completeness |

Each scenario runs the model through a probe, evaluates the response, and scores it. Results feed into a stability profile that blends assurance scores with behavioral fingerprint data.

### `/assure` -- Signed Assurance Reports

Generate a cryptographically signed report of your model's assurance run. Reports are:
- **Signed with Ed25519** using the machine's private key (generated on first run, hardware-bound)
- **Tamper-evident** -- any modification invalidates the signature
- **Uploadable** -- share results to a verification endpoint where third parties can validate the signature and review scores
- **Stored locally** as JSON + human-readable Markdown in `~/.forge/assurance/`

### `/export` -- Governance Audit Bundles

Export a complete session as a zip bundle for compliance review:
- `manifest.json` with SHA-512 file hashes, machine fingerprint, hardware profile
- `audit.json` with full structured session data
- `logs/tool_calls.jsonl`, `logs/threats.jsonl`, `logs/journal.jsonl`
- `verification/results.json` with plan verification outcomes
- Provenance chain integrity verification
- Optional redaction mode that strips sensitive content while preserving metadata

### Proof of Inference

Challenge-response protocol that cryptographically proves a model forward pass actually ran on local hardware. Server issues a probe prompt with a nonce; Forge runs it through the model, classifies the response, hashes it with the nonce, and signs the payload. Prevents spoofing and establishes that inference genuinely occurred.

### Behavioral Fingerprinting

Builds a unique behavioral profile for each model instance by running standardized probes and measuring response characteristics. Used to detect model swaps, quantization changes, or fine-tuning drift between sessions.

### Fleet Telemetry (Opt-In)

For teams running Forge across multiple machines:
- Per-machine profiles with hardware fingerprints, scenario history, pass rates
- Server-side adaptive test manifests that learn which scenarios are flaky on which hardware
- Fleet health dashboard with cross-machine analytics
- SLA alerting when fleet pass rate drops below threshold

## Forge Crucible™ Security Pipeline

9 layers spanning the full request lifecycle:

| # | Layer | Function |
|---|-------|----------|
| 1 | **Pattern Scanner** | Regex detection of prompt injection signatures, shell metacharacters, LOLBins, zero-width unicode, encoded payloads |
| 2 | **Semantic Anomaly** | AI-generated responses scanned before reaching user or disk; RAG context validated for injection and poisoning |
| 3 | **Behavioral Tripwire** | Timing anomalies, call frequency spikes, abnormal request pattern throttling |
| 4 | **Canary Trap** | Honeypot canary integrity — planted tokens detect context exfiltration |
| 5 | **Threat Intelligence** | Updatable signature database with SHA-512 validation and version monotonicity |
| 6 | **Command Guard** | Dangerous command detection, LOLBin blocking, shell metacharacter filtering |
| 7 | **Path Sandbox** | Filesystem sandboxing with 4-tier safety guard |
| 8 | **Plan Verifier** | Multi-step plan validation with test/lint gates |
| 9 | **Forensic Auditor** | Full audit trail with severity classification and forensic context |

All threats logged with severity and full forensic context. The Crucible™ scanner (layers 1-4) runs in under 50 ms per check.

## Quick Start

```bash
git clone https://github.com/Forge-NC/Forge.git
cd Forge
python install.py          # Creates venv, installs deps, creates desktop shortcut
.venv/Scripts/forge        # Windows
.venv/bin/forge            # Linux / macOS
```

On first launch Forge creates `~/.forge/`, connects to your local Ollama instance, and offers to pull a model.

## System Requirements

| Component | Minimum | Recommended | Optimal |
|-----------|---------|-------------|---------|
| **GPU** | 4-8 GB VRAM (GTX 1650 / RTX 3060) | 16-24 GB (RTX 4070 Ti / 5070 Ti / 4090 / 5090) | 48 GB+ (dual GPU / A6000 / workstation) |
| **RAM** | 8 GB | 32 GB | 64-128 GB |
| **Storage** | 10 GB | 50 GB | 200 GB+ |
| **CPU** | Any modern 4-core | 8+ cores | 16+ cores |
| **OS** | Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+ |||

Larger models produce better results but need more VRAM:

| Parameters | VRAM (Q4) | Quality | Use Case |
|------------|-----------|---------|----------|
| 3B | ~2.5 GB | Good | Router model, fast classification |
| 7B | ~5 GB | Strong | General coding, 8 GB GPU sweet spot |
| 14B | ~10 GB | Excellent | Complex reasoning, refactoring |
| 32B | ~20 GB | Best | Architecture design, hard problems |
| 70B | ~48 GB | Frontier | Maximum quality, multi-GPU setups |

Forge auto-detects your GPU and recommends the best model via `/hardware`.

## Launch Modes

| Command | Description |
|---------|-------------|
| `forge` | Console terminal |
| `forge --fnc` | Neural Cortex GUI with dashboard, brain animation, HUD menu |
| `forge --gui-terminal` | GUI terminal with visual effects |

## Commands

60 commands. Run `/help` in-session for the full list.

| Category | Commands |
|----------|----------|
| **Session** | `/save`, `/load`, `/clear`, `/reset`, `/quit` |
| **Context** | `/context`, `/pin`, `/unpin`, `/drop` |
| **Models** | `/model`, `/models`, `/router`, `/ami` |
| **Development** | `/tools`, `/cd`, `/scan`, `/digest`, `/index`, `/search`, `/tasks`, `/plan`, `/dedup` |
| **Memory** | `/memory`, `/journal`, `/recall` |
| **Billing** | `/billing`, `/compare`, `/topup` |
| **Safety** | `/safety`, `/crucible`, `/forensics`, `/provenance`, `/threats` |
| **Continuity** | `/continuity` |
| **Reliability** | `/break`, `/autopsy`, `/stress`, `/assure` |
| **Audit** | `/export`, `/benchmark`, `/stats`, `/report` |
| **Release** | `/ship`, `/autocommit`, `/license` |
| **Fleet** | `/puppet`, `/admin` |
| **UI** | `/theme`, `/dashboard`, `/docs`, `/voice`, `/plugins`, `/synapse` |
| **Config** | `/config`, `/hardware`, `/cache` |
| **Updates** | `/update` |

## Configuration

99 configuration keys. Edit `~/.forge/config.yaml` or use `/config` in-session.

```yaml
default_model: "qwen2.5-coder:14b"
small_model: "qwen2.5-coder:3b"
router_enabled: true
safety_level: 1          # 0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down
sandbox_enabled: true
swap_threshold_pct: 85
theme: "midnight"
telemetry_enabled: false  # opt-in only
```

## Nightly Testing

Automated fleet-wide testing with adaptive scheduling:

- 13 integration scenarios (endurance, model swap, context storm, plugin chaos, crash recovery, malicious repo, and more)
- 8 invariants checked after every scenario
- Auto-bisect to pinpoint regressions
- Cross-platform scheduling via Settings

## Testing

```bash
pytest tests/ -v --timeout=300                            # 1,318 unit tests
pytest tests/integration/ -v --timeout=600                # Stub mode (no Ollama)
pytest tests/integration/ -v --live --timeout=600         # Live mode (requires Ollama)
python scripts/run_live_stress.py --live --full -n 1      # Full stress suite
```

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://forge-nc.dev">forge-nc.dev</a>
</p>
