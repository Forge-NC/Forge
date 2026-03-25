# Forge Neural Cortex — Launch Roadmap
# From Engineering to Revenue

> Written: 2026-03-24
> Updated: 2026-03-25 — LAUNCHED (repo public, PyPI live)
> Status: v0.9.0 PUBLIC — Phase 1 nearly complete
> Previous roadmap (Phases 1-5 engineering) fully implemented and archived
> This document is Forge-readable. Internal AI, read this to understand the plan.

---

## Where We Are (2026-03-25)

Forge v0.9.0 is live and publicly available:
- **GitHub:** https://github.com/Forge-NC/Forge (public, 2026-03-25)
- **PyPI:** `pip install forge-nc` (published 2026-03-25)
- **Website:** https://forge-nc.dev (live with docs, dashboard, admin, Matrix)
- **VS Code extension:** Built and packaged, marketplace publishing pending

80,000+ lines of Python, 18,000+ lines of PHP server, a VS Code extension,
1,318 passing tests, 60 slash commands, 28 AI tools, 38 assurance scenarios,
30-probe behavioral fingerprinting, Ed25519-signed reports, 14 themes,
XP/achievement system, fleet management, and the Forge Matrix™ 3D visualization.

**Patent clock started 2026-03-25. Filing deadline: 2027-03-25.**
Three provisional patent applications in preparation (semantic anomaly, behavioral tripwire, continuity grading).

---

## Phase 1: Ship It (Weeks 1-2)

**Goal:** Anyone can install Forge in under 5 minutes.

### Deliverables
- [x] Fix all CRITICAL bugs from pre-release audit — DONE 2026-03-24
- [x] Fix all HIGH bugs — DONE 2026-03-24
- [x] Make GitHub repo public — DONE 2026-03-25
- [x] Publish to PyPI (`pip install forge-nc`) — DONE 2026-03-25
- [ ] Publish VS Code extension to marketplace (needs Azure DevOps PAT)
- [x] Update pyproject.toml classifier from Alpha to Beta — DONE 2026-03-24
- [x] Commit and push all accumulated fixes — DONE 2026-03-25
- [x] Auth system refactored: tier/role/admin separated — DONE 2026-03-25
- [x] Account ID system: opaque IDs (FORGE-0001, fg_xxxx) — DONE 2026-03-25
- [x] Dashboard: settings tab, fleet merge, XP opt-in — DONE 2026-03-25

### Success Criteria
- [x] `pip install forge-nc && forge` works — VERIFIED
- [ ] VS Code extension installable from marketplace search — PENDING
- [x] GitHub repo has a clean README with install instructions that work — VERIFIED

---

## Phase 2: First 100 Users (Weeks 3-6)

**Goal:** Get developers using Forge and contributing to the Matrix.

### Deliverables
- [ ] Write launch blog post: "Break Your AI Before It Breaks Your Code"
- [ ] Record 2-minute demo video showing `/break --full` on a real model
- [ ] Run `/break --full` against 6+ models, publish comparison results
- [ ] Post to: Hacker News, r/LocalLLaMA, r/programming, dev.to, Twitter/X
- [ ] Identify and contact 10 developer content creators for early access
- [ ] Populate the Matrix with real data (minimum 6 models, 50+ reports)
- [ ] Set up Discord server for community

### Success Criteria
- 100+ GitHub stars
- 50+ unique installs (tracked via telemetry opt-in)
- 10+ unique contributors to the Matrix
- 1 external blog post or video about Forge

---

## Phase 3: First Revenue (Months 2-3)

**Goal:** Validate that someone will pay for this.

### Deliverables
- [ ] Form LLC (Wisconsin, ~$130)
- [ ] Enable Stripe payments (checkout.php is built, needs real keys)
- [ ] Trademark search + filing for "Forge Neural Cortex" and "Forge Crucible"
- [ ] Create compliance report template: "AI Coding Tool Assurance Report"
- [ ] Cold-email 50 CTOs at FinTech/HealthTech companies with the pitch: "Your developers use AI. Can you prove it's safe?"
- [ ] Offer free assurance audits to 5 companies in exchange for case studies
- [ ] Build air-gap installation docs (no internet after initial setup)
- [ ] Add Enterprise tier to pricing ($25,000/year, 50 seats, SSO stub, custom SLA)

### Success Criteria
- LLC formed
- Stripe live, at least 1 test transaction
- 3 enterprise conversations started
- 1 paying customer (any tier)

---

## Phase 4: Product-Market Fit (Months 3-6)

**Goal:** Find the repeatable sales motion.

### Deliverables
- [ ] SSO/SAML integration (enterprise requirement)
- [ ] RBAC for team deployments
- [ ] Centralized admin console for fleet management
- [ ] SOC2 Type I self-assessment
- [ ] Custom scenario library system (enterprise can add their own assurance scenarios)
- [ ] File the 3 provisional patents (semantic anomaly, behavioral tripwire, continuity grading)
- [ ] Publish academic paper on behavioral fingerprinting methodology (target: NeurIPS Datasets & Benchmarks)
- [ ] VS Code extension: workspace context, apply-diff, diagnostic integration
- [ ] macOS/Apple Silicon support documentation

### Success Criteria
- $10K ARR (any combination of tiers)
- 500+ weekly active users
- 1,000+ Matrix contributors
- 1 enterprise pilot ($5K+)
- Academic paper submitted

---

## Phase 5: Scale (Months 6-12)

**Goal:** Build the data moat and enterprise pipeline.

### Deliverables
- [ ] Matrix data API for model providers (paid access to aggregated behavioral data)
- [ ] Model provider partnerships (pitch: "neutral third-party evaluation for your model releases")
- [ ] Government/defense partnership via systems integrator
- [ ] Automated compliance report generation (PDF export for auditors)
- [ ] Real-time fleet health dashboard with alerting
- [ ] CI/CD integration guide (`/stress --ci` in GitHub Actions)
- [ ] JetBrains plugin
- [ ] Seed fundraise ($2-5M at $10-15M valuation)
- [ ] Hire employee #1 (reduce key-person risk)

### Success Criteria
- $100K ARR
- 5,000+ weekly active users
- 10,000+ Matrix contributors
- 3+ enterprise customers ($25K+/year each)
- 1 model provider data partnership
- Seed round closed or term sheet signed

---

## Phase 6: $1M ARR (Year 2)

**Goal:** Prove the business model scales.

### Revenue Targets
| Source | Target | Avg Deal | Deals Needed |
|--------|--------|----------|-------------|
| Enterprise tier ($25K+/yr) | $500K | $50K | 10 |
| Power tier ($79/mo) | $200K | $948/yr | 211 |
| Pro tier ($19/mo) | $100K | $228/yr | 439 |
| Model provider data | $200K | $100K | 2 |
| **Total** | **$1M** | | |

### Key Initiatives
- [ ] Enterprise sales team (1 AE + 1 SE)
- [ ] SOC2 Type II certification
- [ ] FedRAMP authorization package (for government vertical)
- [ ] Series A fundraise ($10-20M)
- [ ] Expand to 5-10 employees

---

## The Moat

The Forge Matrix™ is the moat. Every user who runs `/break --full --share` contributes
cryptographically signed, proof-of-inference-validated behavioral data to a decentralized
model leaderboard that no competitor can replicate without rebuilding the entire
local-first, Ed25519-signed infrastructure.

The coding assistant is the distribution channel.
The Matrix is the data asset.
Enterprise assurance is the revenue engine.

Unlike traditional benchmarks (MMLU, HumanEval), the Matrix measures real-world
reliability under adversarial pressure from real developers on real hardware.
It can't be gamed because results are signed and consensus-validated.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Nobody installs (local model quality perceived as inferior) | Medium | High | Prominently support OpenAI/Anthropic backends |
| Matrix never reaches critical mass | Medium | High | Gamification (XP), influencer seeding, run own models |
| Incumbent ships similar auditing feature | Low | High | Move fast, build data moat, publish paper, file patents |
| Single-founder risk | High | High | Hire #1 before fundraising, document everything |
| Trademark challenge on "Forge" | Medium | Medium | Use "Forge Neural Cortex" / "Forge NC" as primary brand |
| Enterprise sales cycle too long for solo founder | High | Medium | Start with compliance-angle outreach, not full enterprise sales |

---

## Completed (Archived)

### Previous Roadmap (2026-03-05)
All 5 engineering phases completed:
- Phase 1: Event Bus + Plugin Lifecycle
- Phase 2: Behavioral Fingerprinting + Adaptive Pressure
- Phase 3: Proof of Inference + Fleet Consensus
- Phase 4: AI Assurance Platform
- Phase 5: Public Surface (break, autopsy, stress)

### Pre-Release Audit (2026-03-24)
Full codebase audit completed. 7 critical, 8 high, 10 medium issues identified and fixed.
Website restructured with two-story split (Code with Forge / Break Your AI).
Theme system unified across all pages. Navigation simplified. Dashboard built.
XP sync endpoint deployed. Analytics merged into dashboard. All stats verified against codebase.
Publications synced. Constants centralized. Telemetry dual-upload + pending recovery added.

### Public Launch (2026-03-25)
- GitHub repo made public (forking disabled — proprietary license)
- Published to PyPI: `pip install forge-nc`
- Auth system refactored: tier, role, and admin are now independent concepts
- Account IDs migrated to opaque format (FORGE-0001 for origin, fg_xxxx for users)
- Patent clock started — 3 provisional applications in preparation
- Docs updated with pip install as primary install method
