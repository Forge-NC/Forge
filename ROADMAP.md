# Forge — Engineering Roadmap
# Strategic Architecture Plan: Enterprise-Grade AI Runtime Infrastructure

> Written: 2026-03-05
> Engineering Status: Phases 1–5 IMPLEMENTED — 2026-03-05
> Launch Status: Phase 6 PENDING (non-code deliverables remain: README rewrite, docs/launch/)
> This document is Forge-readable. Internal AI, read this to understand the plan.

---

## Strategic Identity

Forge is not another AI coding assistant. It is an AI runtime environment that measures,
hardens, and certifies AI systems under real-world conditions. The coding interface is
the entry point. The infrastructure layer is the product.

**One-line positioning: Forge is chaos engineering for AI agents.**

Chaos engineering (Chaos Monkey, etc.) became standard infrastructure practice by doing
one thing: intentionally breaking systems to prove reliability. Forge is the AI equivalent.
Developers already understand the concept. The positioning is instantly legible.

**The test track, not the judge.**

Forge does not pick winners. It provides the track where models race. A race track
makes money because the race happens there — it does not care who crosses first.
This framing is the foundation of all future positioning decisions:

- Forge tests OpenAI, Anthropic, local models, future models — with identical scenarios
- Forge publishes failure evidence, not opinions
- Forge never recommends a model or editorializes results

Neutrality is the moat. It is why every AI lab, every open-source community, every
enterprise wants Forge to exist — because none of them control it.

**Long-term: the AI Truth Layer.**

The AI ecosystem currently has no trusted external measurement. Vendors self-report
benchmarks. Labs run academic evals on controlled prompts. Nobody measures real
workload behavior under pressure across thousands of independent machines.

Forge is architecturally positioned to become that measurement layer. Not by marketing —
by the data existing and being cryptographically trustworthy. BPoS + Proof of Inference
+ fleet consensus is the infrastructure that makes this possible. No competitor can
replicate this without rebuilding from scratch.

Three markets:
1. AI developer tooling (immediate — users who want a better coding assistant)
2. AI reliability/observability platform (near-term — orgs running fleets of AI agents)
3. AI assurance/certification infrastructure (long-term — defense, finance, healthcare, aviation)

**Revenue model tied to neutrality:**

Forge makes money because models compete on it — not by picking sides. Revenue appears at:
1. Enterprise assurance — organizations prove their AI agents are safe before deployment
2. Model evaluation services — AI labs run Forge suites before release
3. Reliability analytics — fleet telemetry + consensus data as observability infrastructure

The more models compete on Forge, the more valuable the benchmark becomes.
The benchmark's value funds the infrastructure. This flywheel only works if neutrality holds.

Each layer reinforces the others. More users → more telemetry → better benchmarks →
more credibility → more users. This flywheel only works if telemetry is trusted, which
is why BPoS (Ed25519 passport signing, machine fingerprints, provenance chains) is the
foundational moat — not a feature.

The Microsoft/Azure risk: they will build centralized cloud AI orchestration. Forge wins
by being local + distributed. Cloud providers can measure datacenter behavior. They
cannot measure RTX consumer GPUs, messy real workflows, and 200-turn overnight sessions.
Every Forge install is a measurement node they cannot buy.

---

## Current State (as of 2026-03-05)

- ~4,149 lines in engine.py (the monolith to address)
- Plugin system exists: ForgePlugin + PluginManager with hooks, priority, restricted proxy
- BPoS: Ed25519 passport signing, machine fingerprints, tier gates — COMPLETE
- Crucible: runtime output scanning for threats — COMPLETE, direct engine coupling
- Shipwright + AutoForge: release management + auto-commit — COMPLETE, direct coupling
- Fleet analytics dashboard: live at dirt-star.com/Forge/analytics.php
- Telemetry receiver: signed zip bundles — COMPLETE
- 1,318 tests, 0 skip/xfail
- Models: qwen3:14b (primary), qwen3:4b (small), nomic-embed-text (embeddings)
- Backend support: Ollama (local), OpenAI API, Anthropic API

What the plugin system currently lacks:
- No event bus — only synchronous hook-pipeline dispatch
- No session/turn lifecycle events (session.start, turn.end, model.switch, etc.)
- Bundled internal plugins load from ~/.forge/plugins/ only, not from forge/plugins/bundled/
- Subsystems (Crucible, AutoForge, Shipwright, Reliability, Forensics) are direct engine
  attributes, not event subscribers — they require engine.py surgery to extend

---

## Phase 1 — Foundation: Event Bus + Plugin Lifecycle Events
### Priority: FIRST. Everything else depends on this.

### Goal
Add an in-process async event bus. Engine emits typed events at key lifecycle points.
Plugins can subscribe to observe (not just intercept-and-transform). Subsystems start
receiving events. No breaking changes to existing hooks or external plugin API.

### New concepts

**ForgeEvent** — typed event with standard fields:
  - event_type: str  (e.g. "turn.end", "tool.call", "threat.detected")
  - data: dict       (event-specific payload)
  - timestamp: float
  - session_id: str

**ForgeEventBus** — in-process pub/sub:
  - subscribe(event_type, handler, priority=50) — register a handler
  - emit(event_type, data) — synchronous fire to all subscribers
  - emit_async(event_type, data) — fire-and-forget (for non-blocking observers)
  - Wildcard support: subscribe("*") to receive all events
  - Handler errors are caught and logged, never crash the bus

**Event taxonomy** (the standard schema — stable contract):
  Session lifecycle:
    session.start       {session_id, model, cwd, config_summary}
    session.end         {session_id, turns, tokens_prompt, tokens_generated,
                         duration_s, tool_calls, files_modified}
  Turn lifecycle:
    turn.start          {turn_id, user_input_preview, context_pct}
    turn.end            {turn_id, tokens_prompt, tokens_generated, duration_ms,
                         tool_calls_count, had_errors, pass_rate}
  Model events:
    model.request       {model, prompt_tokens, context_pct}
    model.response      {model, response_tokens, duration_ms, had_tool_calls}
    model.switch        {from_model, to_model, reason}
  Tool events:
    tool.call           {tool_name, args_summary, turn_id}
    tool.result         {tool_name, success, duration_ms, output_size}
    tool.error          {tool_name, error_type, error_msg, turn_id}
  File events:
    file.read           {path, size, cached}
    file.write          {path, size, was_edit}
  Security events:
    threat.detected     {level, rule, source, preview, action}
    safety.prompt       {action, path_or_cmd, level}
    safety.decision     {action, allowed, by_user}
  Context events:
    context.pressure    {used_pct, tokens_used, tokens_max, swap_imminent}
    context.swap        {turns_preserved, tokens_before, tokens_after}
  Plan events:
    plan.created        {step_count, model_used}
    plan.approved       {method}  (auto/user)
    plan.step_complete  {step_index, step_summary, pass_rate}
    plan.complete       {steps, duration_s, all_passed}
  Infrastructure:
    challenge.received  {challenge_id}    (Phase 3: proof of inference)
    challenge.complete  {challenge_id, latency_ms, tokens}
    fingerprint.drift   {model, delta, dimension}  (Phase 2: behavioral fingerprinting)

### New files
- forge/event_bus.py — ForgeEvent dataclass + ForgeEventBus class

### Modified files
- forge/plugins/base.py
    Add observer hooks to ForgePlugin:
      on_event(self, event: ForgeEvent) -> None  (catch-all)
      on_session_start(self, data: dict) -> None
      on_session_end(self, data: dict) -> None
      on_turn_start(self, data: dict) -> None
      on_turn_end(self, data: dict) -> None
      on_model_switch(self, from_model: str, to_model: str) -> None
      on_context_pressure(self, used_pct: float, data: dict) -> None
      on_threat_detected(self, threat: dict) -> None
    Add event_types class attribute: list[str] = []
      Plugins declare which events they want. Bus skips dispatch if not listed
      (performance optimization for high-frequency events like tool.call)

- forge/plugins/__init__.py
    Add to PluginManager:
      dispatch_event(event: ForgeEvent) — routes to on_event and specific handlers
      _bundled_dir: Path — loads forge/plugins/bundled/ before user plugins
      _load_from_dir(dir, label) — shared loader for both dirs

- forge/engine.py
    Wire in event bus:
      self.event_bus = ForgeEventBus()
      pass event_bus to _RestrictedEngineProxy (plugins can subscribe but not emit)
    Add bus.subscribe calls for internal subsystems that need session events:
      self.reliability.subscribe(self.event_bus)  (if reliability grows a subscribe method)
      self.forensics.subscribe(self.event_bus)    (same)
    Emit events at key points:
      run() → emit session.start at entry, session.end at exit
      _agent_loop() → emit turn.start, turn.end, model.request, model.response
      _cached_read_file/_cached_write_file → emit file.read, file.write
      _guarded_run_shell → emit tool.call, tool.result (or error)
      _scan_llm_output / _scan_recall_content → emit threat.detected
      _auto_context_swap → emit context.pressure, context.swap
      _run_plan_mode → emit plan.created, plan.approved, plan.complete
      ModelRouter switch → emit model.switch
    Update _RestrictedEngineProxy:
      Add "event_bus" to _ALLOWED (subscribe-only — emit is not exposed)

- forge/plugins/bundled/ (new directory)
    forge/plugins/bundled/__init__.py
    forge/plugins/bundled/telemetry_plugin.py  — subscribes to session.end,
      turn.end, formats and ships the telemetry bundle (extracts from engine.telemetry)
    forge/plugins/bundled/cortex_plugin.py — subscribes to turn.start/end,
      model.switch, threat.detected, context.pressure — drives NeuralCortex state
      (extracts from engine._write_dashboard_state, _push_dashboard_data)

  Note: Crucible and Safety are NOT migrated to plugins in Phase 1 — they require
  synchronous intercept (must block), not async observation. They stay as direct
  engine attributes. The event bus notifies AFTER they act.

### What this enables
- External plugins can observe session lifecycle, turn metrics, threats without engine surgery
- Phase 2 behavioral fingerprinting subscribes to session.start and model.response
- Phase 3 proof-of-inference subscribes to challenge.received
- Telemetry and cortex state become testable in isolation
- Tests can subscribe to the bus instead of mocking engine internals

### What does NOT change in Phase 1
- Existing ForgePlugin hooks (on_user_input, on_response, on_tool_call, etc.) — unchanged
- External plugin API — fully backward compatible
- Crucible, Safety — still direct engine attributes
- Shipwright, AutoForge — still direct engine attributes (Phase 2 candidates)
- No user-visible behavior changes

### Tests to add
- tests/test_event_bus.py — unit tests for ForgeEventBus (subscribe, emit, wildcard,
  error isolation, priority ordering, async emit)
- tests/test_plugin_events.py — tests that engine emits expected events at lifecycle points

---

## Phase 2 — Intelligence Layer: Behavioral Fingerprinting + Adaptive Pressure
### Depends on: Phase 1 complete

### Behavioral Fingerprinting
Every model has a behavioral signature. Not capability — behavior. How it hedges
uncertainty. What it hallucinates about. How it degrades under context pressure.

Probe suite: 12 version-stable prompts targeting behavioral dimensions:
  1. numeric_continuation (hallucination baseline)
  2. instruction_following (precise constraint adherence)
  3. uncertainty_hedge (how model expresses unknowns)
  4. tool_refusal (when model refuses a tool call appropriately)
  5. context_long_recall (remembers detail from 60 turns ago)
  6. context_short_recall (remembers from 3 turns ago)
  7. code_correction (finds a planted bug)
  8. reasoning_chain (multi-step inference)
  9. adversarial_compliance (resists bad instruction framing)
  10. edge_case_null (handles None/empty/zero input)
  11. repair_loop (recovers from a forced tool error)
  12. self_knowledge (accurate about its own capabilities)

Fingerprint: 12-dimensional float vector, one per probe, scored 0.0-1.0.
Stored at: ~/.forge/fingerprints/{model_id}/{version}.json

Drift detector: compares current fingerprint to stored baseline. Logs drift to
event bus as fingerprint.drift. Alerts if delta > threshold on any dimension.
Practical use: detect silent model swaps, quantization behavioral changes,
version regressions the vendor didn't announce.

New files:
  forge/behavioral_fingerprint.py — probe suite, scorer, drift detector
  forge/plugins/bundled/fingerprint_plugin.py — subscribes to session.start,
    runs probes after model confirmed, emits fingerprint.drift if needed

### Adaptive Pressure Testing
Crucible currently uses fixed scenario categories. Adaptive pressure watches
the live session — file types, tool patterns, context trajectory — and generates
adversarial variants of the actual workload.

If the user edits Python files → stress scenarios involve Python-specific failures
If working on C++ with a build system → linker/compiler error recovery scenarios
If in a long refactor session → context window pressure + coherence invariants

New files:
  forge/adaptive_pressure.py — session watcher + scenario generator
  Integrates with Crucible's scenario runner

### Genome integration
Behavioral baseline stored as part of genome. Drift becomes a genome event.
Persistent longitudinal baseline: "how did this model's behavior change over
the 3 months I've been using it?" — data no vendor has about their own model.

---

## Phase 3 — Trust Infrastructure: Proof of Inference + Fleet Consensus
### Depends on: Phase 1 complete. Phase 2 optional.

### Proof of Inference
Problem: any node can fake telemetry. BPoS proves identity, not behavioral
authenticity. We need proof that inference actually ran, with real hardware.

Challenge-response protocol:
  Server sends:
    {challenge_id, probe_prompt, expected_category, nonce, expires_at}
  Client executes:
    Run probe_prompt through the local model
    Classify response into expected_category (local lightweight classifier)
    Return: {challenge_id, response_category, response_hash=sha512(nonce+response),
             latency_ms, tokens_generated, signed=Ed25519(machine_key, payload)}
  Server verifies:
    - Signature valid (machine Ed25519 key from passport)
    - latency_ms consistent with hardware profile (RTX 5070 Ti doesn't take 30s for 12 tokens)
    - response_category matches expected
    - nonce not reused (replay attack prevention)

This is Proof of Inference — the computation is a model forward pass, not a hash.
The fleet's capability matrix entries are cryptographically defended.

New files:
  forge/proof_of_inference.py — challenge executor, response signer
  forge/plugins/bundled/poi_plugin.py — subscribes to challenge.received,
    executes proof, emits challenge.complete
  Server-side: server/challenge_server.php — generates challenges, verifies responses,
    updates capability matrix with verified entries

### Fleet Consensus
For each (model, scenario) pair across N nodes:
  - Aggregate signed results
  - Compute consensus value + confidence interval
  - Preserve outliers with flag (don't discard — they're the most interesting data)
  - Entry shows: N nodes, consensus value, confidence, outlier count, last verified

This makes the capability matrix a decentralized model leaderboard.
No vendor controls it. No node can dominate it. The math defends it.

New files:
  server/consensus_engine.php — aggregation, outlier detection, confidence calc
  server/data/consensus/ — per-(model,scenario) consensus records

---

## Phase 4 — Enterprise/Verification Layer: AI Assurance Platform
### Depends on: Phase 1-3 complete

### AI Assurance
The emerging problem: organizations need to certify AI behavior before deployment.
Defense contractors, hospitals, financial institutions, infrastructure operators —
they all need an answer to "how do we prove this AI won't do something catastrophic?"
Current answers are terrible. Forge can be the right answer.

Assurance scenario library:
  Categories: safety, reliability, adversarial, tool_misuse, exfiltration, context_integrity
  Each scenario: fixed inputs, defined invariants, pass/fail criteria, reproducible

Assurance run produces a signed artifact:
  - Machine-signed JSON report (Ed25519 + machine fingerprint)
  - Scenario results with invariant outcomes
  - Behavioral fingerprint at time of run
  - Hardware profile, Forge version, model version
  - Timestamp chain (tamper-evident)
  Everything needed for an audit trail.

Compliance mapping:
  Scenario categories mapped to: EU AI Act risk tiers, NIST AI RMF, ISO 42001
  Forge doesn't certify — it provides the evidence. Auditors make the judgment.

Enterprise deployment:
  Air-gapped mode: zero fleet telemetry, local-only assurance reports
  Custom scenario library: enterprises inject their own invariants
  Policy plugin API: custom rules that block/allow actions per enterprise policy

New files:
  forge/assurance.py — assurance run orchestrator
  forge/assurance_report.py — signed report generator
  forge/plugins/bundled/assurance_plugin.py — /assure command handler
  server/assurance_verify.php — server-side report verification

---

## Phase 5 — Public Surface: forge break + Model Autopsy Reports
### Depends on: Phase 4 complete
### Priority: Required before public launch

### Goal
Expose Forge's existing assurance/reliability infrastructure through a single developer-facing
command. The internal harness is built. Phase 5 makes it ergonomic and shareable enough to
spread on its own.

### forge break command

    forge break --model qwen3:14b

Runs the Forge Reliability Suite and prints structured pass/fail results:

    Running Forge Break Suite...

    context_storm ........ PASS
    repair_loop .......... PASS
    tool_corruption ...... FAIL
    policy_drift ......... PASS
    prompt_injection ..... FAIL

    Forge Reliability Score: 82%
    2 failure modes detected — run `forge autopsy` for details

Key design rules:
- Single command, zero config required
- Works against any configured backend (Ollama, OpenAI, Anthropic)
- Output is parseable (structured JSON via --json flag)
- Exits non-zero if any scenario fails (CI-compatible)

### forge autopsy command

    forge autopsy --model qwen3:14b

Produces a human-readable failure analysis, not just pass/fail:

    Forge Autopsy Report
    Model: qwen3:14b

    Reliability Score: 82%

    Failure Modes Detected:

    1. Tool Hallucination
       Model attempted to call non-existent tool "edit_file_block" (2 occurrences)

    2. Policy Drift
       Model violated safety invariant after 6-turn adversarial pressure sequence

    Stability Profile:
    Reasoning:          ██████████  96%
    Tool Discipline:    ████████░░  80%
    Context Resilience: █████████░  91%
    Recovery Ability:   ████████░░  81%
    Policy Adherence:   ███████░░░  73%

This is more valuable than capability benchmarks because it shows HOW models break,
not just whether they pass. Engineers building on top of models need this information.

### Shareable reports

    forge break --model qwen3:14b --share

Generates a report artifact and uploads to dirt-star.com/Forge/reports/ (reuses existing
telemetry infrastructure + BPoS signing). Returns a short URL. Developers can post this link
directly. Drives organic comparison posts ("I ran Forge against 6 models — results:").

Report format: signed JSON (reuses assurance_report.py infrastructure from Phase 4).
Viewing is public. Submitting requires a valid BPoS passport (prevents spam/spoofing).

### Reliability Scoreboard — the viral surface

This is the most important page on dirt-star.com/Forge/:

    Forge Reliability Rankings
    Community-generated · Cryptographically signed · Tamper-evident

    Model              Score   Runs    Signed
    ─────────────────────────────────────────
    qwen3:14b           91%    1,847     ✓
    llama3-8b           86%      923     ✓
    mistral-7b          82%      601     ✓
    gpt-4o              89%      204     ✓

Every row is backed by signed reports. The score is fleet consensus, not self-reported.
"N runs" shows how many independent machines verified it. Clicking a score shows the
signed report with individual scenario results.

This page spreads because:
- Developers compare models they use — and link to their own run
- Researchers cite it ("as measured by the Forge Reliability Index")
- AI labs watch it and improve models to rank higher
- Journalists reference it when writing about model comparisons

The Scoreboard is powered entirely by `forge break --share`. Every developer who
shares a result makes the Scoreboard more accurate. This is the viral loop.

Implementation: `server/report_view.php` (already built) hosts the leaderboard.
The assurance_verify.php index.json feeds the aggregate scores.
The scoreboard page is the homepage of the Forge server, not a sub-page.

### forge stress command (alias for CI pipelines)

    forge stress --model llama3 --suite minimal

A lighter 3-scenario variant designed to complete in under 30 seconds. Intended for
pre-commit hooks, CI gates, and rapid iteration. Exits 0/1 for pass/fail.

### New files
- forge/commands/break_cmd.py   — forge break + forge autopsy + forge stress handlers
- forge/break_runner.py         — orchestrates scenario selection, scoring, profile output
- server/reports/               — public report hosting (one JSON per UUID slug)
- server/report_view.php        — minimal public report viewer

### Modified files
- forge/commands.py             — register break, autopsy, stress commands
- forge/assurance.py            — add minimal suite (3 scenarios) for stress mode
- forge/assurance_report.py     — add shareable upload path

### What this enables
- Single most shareable Forge feature — one command, immediately useful output
- Community-generated model comparison data (no vendor can control it)
- CI integration story: "Did you Forge-test your agent before deploying?"
- Foundation for the model leaderboard (Phase 3 fleet consensus feeds into this)

---

## Phase 6 — Go-to-Market: Developer Launch
### Depends on: Phase 5 complete
### Priority: Ship Phase 5 first, then execute this

### Strategic context
Big AI companies (Anthropic, OpenAI, Microsoft) do not respond to ideas. They respond to
adoption, influence, data, and ecosystems. The goal of Phase 6 is not revenue or investors.
The goal is 500 real developers who understand what Forge is.

**Success in month 1:** 100 users, 500 GitHub stars
**Success in month 3:** 500 users, community Discord, model comparison posts circulating
**Success in month 6:** 2k–5k users, AI lab engineers watching, first enterprise inquiries

Once the tool is known for breaking models, model companies will ask how their model
performs in Forge. That is when conversations with vendors become productive. Not before.

### Pre-launch checklist (4 days)

**README must close in 30 seconds:**

    Forge — AI Chaos Engineering

    Run adversarial reliability tests against any AI model.

    • Works with local models (Ollama, LM Studio)
    • Runs the Forge Reliability Suite — 5 battle-tested failure scenarios
    • Produces shareable Autopsy reports
    • CI-compatible (exits non-zero on failure)

    pip install forge-ai
    forge init
    forge break --model llama3

Then immediately show sample output. Developers want fast first success.

**Forge Reliability Suite v1 — named scenarios:**
  - context_storm
  - repair_loop
  - tool_corruption
  - verification_theater
  - policy_drift

Publishing these names matters. Once they circulate, Forge becomes a reference framework.
"Does it pass context_storm?" becomes a real question in model evaluation discussions.

**Demo screenshots:** Neural Cortex UI, reliability dashboard, autopsy output, scenario chart.
Developers scroll GitHub fast. Visuals stop them.

### Launch sequence (2 weeks)

**Day 1 — Soft launch, developer communities only:**

  Hacker News: "Show HN: Forge – chaos engineering for AI agents"
  Reddit r/LocalLLaMA: focus on local model angle
  Reddit r/MachineLearning: focus on reliability/eval angle
  X/Twitter AI community: short thread with sample autopsy output

  Tone: do NOT oversell. Developers distrust hype. Position as infrastructure.
  Do NOT use: "revolutionary", "the future of AI", "replaces X"
  DO use: "developer infrastructure", "reliability testing", "how your model breaks"

**Week 1 — Feedback loop:**

  Three response types to handle:
  1. Curious developers — invite to Discord/GitHub Discussions. These are gold.
  2. Skeptics ("why not LangChain?") — engage respectfully, explain the reliability angle.
  3. Power users who break Forge — their bug reports are extremely valuable.

**Week 2 — Momentum post:**

  Publish: "Forge Reliability Report — 6 models compared"
  Format: table of model vs. scenario pass rates + worst failure mode per model.
  These posts spread fast because they reveal model weaknesses.
  Post to same communities + tag relevant AI researchers on X.

### Scenario library — community growth

  "Submit your own adversarial scenario" — GitHub Discussions or dedicated form.
  Over time this becomes Forge Scenario Library, a community-maintained benchmark.
  Once the library grows, Forge is a standard, not just a tool.

### Three realistic viral paths

These are not marketing campaigns. They are conditions to watch for and be ready to
amplify when they appear. Any one of them triggers a step-change in adoption.

**Path 1 — The Model Embarrassment Event (most likely first)**
Someone runs `forge break` against several models and posts the comparative results.
"I ran Forge against 7 models. Here's what breaks." The post spreads because
developers love failure analysis more than capability claims. The Reliability Scoreboard
makes this easy: one command, one shareable link, instant comparison.
Watch for: unprompted results posts on HN, Reddit r/LocalLLaMA, X AI community.
When it happens: engage, ask questions, invite to Discord. These are the 100 right users.

**Path 2 — The AI Agent Disaster (slow burn, high impact)**
When an AI agent system causes a significant real-world failure — deleted data, leaked
credentials, broken deployment — the community will ask: "Was this tested?"
If Forge is already established as the testing tool, the answer becomes obvious.
This is how Chaos Monkey went from obscure Netflix project to industry standard:
not because Netflix marketed it, but because a few high-profile outages made
chaos testing feel obviously necessary.
Position to capture this: Forge already has the `forge certify` framing in Phase 4
(`/assure` generates a signed audit artifact). Make sure this is visible before the event.

**Path 3 — Researcher Adoption (quiet, compounding)**
If a researcher publishes a paper using Forge scenarios — citing `context_storm`,
`repair_loop`, `policy_drift` by name — those scenario names enter academic vocabulary.
Papers get cited. Benchmarks that appear in papers get used by other researchers.
Once Forge appears as a citation, it has the same gravity as MMLU or HumanEval.
This is slow (6–18 months from first use to published paper) but extremely durable.
Position to capture this: scenario documentation in SCENARIOS.md must be precise enough
to be citeable. Each scenario needs a clear behavioral hypothesis and scoring methodology.
Academic rigor in the documentation costs nothing and pays compounding returns.

### The long-term moat

Once AI agents run real systems (infrastructure, codebases, financial workflows), every
organization will need to answer: "Did you test this agent before deploying it?"
The current industry answer is: no one knows. Forge can be the right answer.

Path 1 — Open Infrastructure: Forge becomes the Chaos Monkey for AI. Company later.
Path 2 — Enterprise Platform: AI reliability/assurance for defense, finance, hospitals.
Path 3 — Model Developer Tool: Evaluation/benchmark platform for AI labs.

These are not mutually exclusive. The developer community builds the credibility that
makes Paths 2 and 3 tractable. Start with Path 1.

---

## Novel Concepts Summary

**Proof of Inference** — cryptographic proof that a model forward pass ran on real
hardware. Like proof-of-work but the computation is AI inference. Prevents fleet
telemetry manipulation. Does not exist in any AI platform today.

**Behavioral Fingerprinting** — 12-dimensional behavioral signature per model version.
Detects silent model changes, quantization differences, version regressions. Creates
longitudinal behavioral baseline no vendor has about their own model.

**Fleet Consensus** — decentralized model leaderboard where each entry requires
cryptographically signed agreement from N independent nodes. Not gameable by any
single party. The math defends the benchmark.

**Adaptive Pressure** — stress test harness that generates scenarios from the live
session's actual workload, not fixed categories. Catches failure modes that generic
scenarios never would.

**Session-Aware Event Bus** — in-process pub/sub that makes Forge's internals
observable without coupling. The event schema is the stable contract that allows
an ecosystem to grow without touching the core.

---

## File Map: What Gets Touched

Phase 1:
  NEW:  forge/event_bus.py
  NEW:  forge/plugins/bundled/__init__.py
  NEW:  forge/plugins/bundled/telemetry_plugin.py
  NEW:  forge/plugins/bundled/cortex_plugin.py
  MOD:  forge/plugins/base.py      (add event observer hooks)
  MOD:  forge/plugins/__init__.py  (add dispatch_event, bundled dir loading)
  MOD:  forge/engine.py            (wire bus, emit events at lifecycle points)
  NEW:  tests/test_event_bus.py
  NEW:  tests/test_plugin_events.py

Phase 2:
  NEW:  forge/behavioral_fingerprint.py
  NEW:  forge/adaptive_pressure.py
  NEW:  forge/plugins/bundled/fingerprint_plugin.py
  MOD:  forge/crucible.py          (adaptive scenario integration)
  MOD:  forge/memory.py            (store behavioral baseline in genome)

Phase 3:
  NEW:  forge/proof_of_inference.py
  NEW:  forge/plugins/bundled/poi_plugin.py
  NEW:  server/challenge_server.php
  NEW:  server/consensus_engine.php
  MOD:  server/analytics.php       (display consensus data)
  MOD:  forge/telemetry.py         (include challenge results in bundle)

Phase 4:
  NEW:  forge/assurance.py
  NEW:  forge/assurance_report.py
  NEW:  forge/plugins/bundled/assurance_plugin.py
  NEW:  server/assurance_verify.php
  MOD:  forge/commands.py          (/assure command)
  MOD:  forge/engine.py            (assurance run integration)

Phase 5:
  NEW:  forge/break_runner.py      (BreakRunner orchestrator, FailureMode extraction, stability profile)
  NEW:  server/report_view.php     (individual report viewer)
  NEW:  server/scoreboard.php      (Reliability Scoreboard — primary public surface)
  NEW:  forge/plugins/bundled/assurance_plugin.py  (auto_assurance on session.end)
  MOD:  forge/commands.py          (/break, /autopsy, /stress registered)
  MOD:  forge/engine.py            (model.request/response, tool.call/result/error, plan.* events added)

Phase 6:
  (Non-code deliverables)
  UPD:  README.md                  (30-second hook, scenario names, demo screenshots)
  NEW:  SCENARIOS.md               (Forge Reliability Suite v1 — named + documented)
  NEW:  docs/launch/               (HN post, Reddit post templates, benchmark report template)

---

## Guiding Principles

1. Event bus before everything. No new capability gets built without asking:
   "what events does this emit and subscribe to?"

2. Core stays small. New capabilities are plugins or subscribers, not engine edits.

3. Telemetry is optional, Forge is great without it.
   The assurance platform is even more valuable when telemetry is off (air-gapped).

4. Never claim precision we can't guarantee.
   Local token counts ≠ vendor billing tokens. Store both, label both, never conflate.

5. Outliers are data, not noise.
   Fleet consensus preserves minority reports. The interesting failure is the one
   most nodes don't see.

6. BPoS is the foundation, not a feature.
   Every trust guarantee in this roadmap depends on machine identity being real.
   Don't weaken the passport system for convenience.

7. Neutrality is the moat. Never break it.
   Forge must never: favor a specific model in results, recommend or demote a model,
   adjust scenario weights to flatter a vendor, hide failing results, or become a model
   provider. The moment Forge is perceived as having a commercial interest in any model's
   performance, the Reliability Scoreboard loses credibility and the AI Truth Layer
   thesis collapses. Every product decision must pass this test:
   "Does this make Forge more like a test track, or more like a judge?"
   Test track: always. Judge: never.
