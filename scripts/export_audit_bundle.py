"""Export a comprehensive audit bundle for external review.

Collects all assurance reports, fingerprints, harness data,
forensics, and code samples into a single directory with a
structured manifest. Designed for passing to external AI
systems or human auditors for product evaluation.

Usage:
    python scripts/export_audit_bundle.py [--output DIR]
"""

import json
import os
import shutil
import sys
import hashlib
from datetime import datetime
from pathlib import Path

FORGE_DIR = Path.home() / ".forge"
FORGE_SRC = Path(__file__).resolve().parent.parent / "forge"
DEFAULT_OUTPUT = Path.home() / "Desktop" / "forge_audit_bundle"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_assurance(bundle: Path) -> list:
    """Copy all assurance reports."""
    src = FORGE_DIR / "assurance"
    dst = bundle / "assurance_reports"
    dst.mkdir(parents=True, exist_ok=True)
    items = []
    if src.exists():
        for f in sorted(src.iterdir()):
            if f.suffix in (".json", ".md"):
                shutil.copy2(f, dst / f.name)
                items.append({
                    "file": f"assurance_reports/{f.name}",
                    "type": "assurance_report",
                    "format": f.suffix.lstrip("."),
                    "size_bytes": f.stat().st_size,
                    "sha256": sha256_file(f),
                })
    return items


def collect_fingerprints(bundle: Path) -> list:
    """Copy all behavioral fingerprint data."""
    src = FORGE_DIR / "fingerprints"
    dst = bundle / "fingerprints"
    dst.mkdir(parents=True, exist_ok=True)
    items = []
    if src.exists():
        for model_dir in sorted(src.iterdir()):
            if model_dir.is_dir():
                model_dst = dst / model_dir.name
                model_dst.mkdir(exist_ok=True)
                for f in sorted(model_dir.iterdir()):
                    if f.suffix == ".json":
                        shutil.copy2(f, model_dst / f.name)
                        items.append({
                            "file": f"fingerprints/{model_dir.name}/{f.name}",
                            "type": "behavioral_fingerprint",
                            "model": model_dir.name,
                            "format": "json",
                            "size_bytes": f.stat().st_size,
                        })
    return items


def collect_harness(bundle: Path) -> list:
    """Copy harness trend data and run summaries."""
    dst = bundle / "harness"
    dst.mkdir(parents=True, exist_ok=True)
    items = []

    trend = FORGE_DIR / "harness_trend.jsonl"
    if trend.exists():
        shutil.copy2(trend, dst / "harness_trend.jsonl")
        items.append({
            "file": "harness/harness_trend.jsonl",
            "type": "harness_trendline",
            "format": "jsonl",
            "size_bytes": trend.stat().st_size,
        })

    dashboard = FORGE_DIR / "harness_dashboard.html"
    if dashboard.exists():
        shutil.copy2(dashboard, dst / "harness_dashboard.html")
        items.append({
            "file": "harness/harness_dashboard.html",
            "type": "harness_dashboard",
            "format": "html",
            "size_bytes": dashboard.stat().st_size,
        })

    runs = FORGE_DIR / "harness_runs"
    if runs.exists():
        for run_dir in sorted(runs.iterdir()):
            if run_dir.is_dir():
                run_dst = dst / "runs" / run_dir.name
                run_dst.mkdir(parents=True, exist_ok=True)
                for f in run_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, run_dst / f.name)
                        items.append({
                            "file": f"harness/runs/{run_dir.name}/{f.name}",
                            "type": "harness_run",
                            "format": f.suffix.lstrip("."),
                        })
    return items


def collect_forensics(bundle: Path) -> list:
    """Copy session forensics reports."""
    src = FORGE_DIR / "forensics"
    dst = bundle / "forensics"
    dst.mkdir(parents=True, exist_ok=True)
    items = []
    if src.exists():
        for f in sorted(src.iterdir()):
            if f.suffix == ".md":
                shutil.copy2(f, dst / f.name)
                items.append({
                    "file": f"forensics/{f.name}",
                    "type": "session_forensics",
                    "format": "md",
                    "size_bytes": f.stat().st_size,
                })
    return items


def collect_signing_info(bundle: Path) -> list:
    """Export public key info (never the private key)."""
    items = []
    key_file = FORGE_DIR / "machine_signing_key.pem"
    if key_file.exists():
        info = {
            "key_exists": True,
            "key_format": "Ed25519 PEM",
            "note": "Private key NOT exported. Public key embedded in signed reports.",
        }
        info_path = bundle / "signing_info.json"
        with open(info_path, "w") as f:
            json.dump(info, f, indent=2)
        items.append({
            "file": "signing_info.json",
            "type": "signing_metadata",
            "format": "json",
        })

    machine_id = FORGE_DIR / "machine_id"
    if machine_id.exists():
        shutil.copy2(machine_id, bundle / "machine_id.txt")
        items.append({
            "file": "machine_id.txt",
            "type": "machine_identifier",
            "format": "text",
        })

    passport = FORGE_DIR / "passport.json"
    if passport.exists():
        shutil.copy2(passport, bundle / "passport.json")
        items.append({
            "file": "passport.json",
            "type": "passport_credentials",
            "format": "json",
        })
    return items


def collect_code_samples(bundle: Path) -> list:
    """Copy key implementation files that demonstrate audit depth."""
    dst = bundle / "implementation_samples"
    dst.mkdir(parents=True, exist_ok=True)
    items = []

    key_files = [
        ("assurance.py", "Core assurance engine: 74 scenarios, 8 categories, Trident Protocol"),
        ("assurance_report.py", "Report generation, Ed25519 signing, compliance mapping"),
        ("behavioral_fingerprint.py", "30-probe behavioral signature system"),
        ("proof_of_inference.py", "Ed25519 key management, proof-of-inference protocol"),
        ("crucible.py", "4-layer threat detection: static, semantic, behavioral, honeypot"),
        ("safety.py", "Shell gating, path sandboxing, tiered approval"),
        ("break_runner.py", "Break reliability suite, autopsy, self-rate, Matrix sharing"),
        ("audit.py", "Session audit export, zip bundling, redaction"),
        ("adaptive_pressure.py", "27 adaptive pressure scenarios"),
    ]

    # Also include server-side verification code
    server_dir = FORGE_SRC.parent / "server"
    server_files = [
        ("report_view.php", "Public report viewer with verdict generator, exec summary, certification tiers"),
        ("assurance_verify.php", "Report ingestion, Ed25519 verification, Origin certification API"),
        ("verify_report.php", "Independent 4-check verification system with fraud detection"),
    ]
    for filename, description in server_files:
        src = server_dir / filename
        if src.exists():
            shutil.copy2(src, dst / filename)
            line_count = sum(1 for _ in open(src, encoding="utf-8", errors="ignore"))
            items.append({
                "file": f"implementation_samples/{filename}",
                "type": "source_code",
                "description": description,
                "lines": line_count,
            })

    for filename, description in key_files:
        src = FORGE_SRC / filename
        if src.exists():
            shutil.copy2(src, dst / filename)
            line_count = sum(1 for _ in open(src, encoding="utf-8", errors="ignore"))
            items.append({
                "file": f"implementation_samples/{filename}",
                "type": "source_code",
                "description": description,
                "lines": line_count,
            })
    return items


def collect_config(bundle: Path) -> list:
    """Copy config (with secrets redacted)."""
    items = []
    cfg = FORGE_DIR / "config.yaml"
    if cfg.exists():
        with open(cfg, "r", encoding="utf-8") as f:
            lines = f.readlines()
        redacted = []
        sensitive = ("token", "key", "secret", "password", "api_key")
        for line in lines:
            lower = line.lower()
            if any(s in lower for s in sensitive) and ":" in line:
                key_part = line.split(":")[0]
                redacted.append(f"{key_part}: [REDACTED]\n")
            else:
                redacted.append(line)
        out = bundle / "config_redacted.yaml"
        with open(out, "w", encoding="utf-8") as f:
            f.writelines(redacted)
        items.append({
            "file": "config_redacted.yaml",
            "type": "configuration",
            "format": "yaml",
            "note": "Sensitive values redacted",
        })
    return items


def build_analysis_doc(bundle: Path, manifest: dict):
    """Generate the analysis document for external AI review."""
    report_count = sum(1 for i in manifest["artifacts"] if i["type"] == "assurance_report" and i["format"] == "json")
    fingerprint_models = set(i.get("model", "") for i in manifest["artifacts"] if i["type"] == "behavioral_fingerprint")
    fingerprint_models.discard("")
    forensics_count = sum(1 for i in manifest["artifacts"] if i["type"] == "session_forensics")

    doc = f"""# Forge Neural Cortex - Audit Bundle Analysis Guide

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Purpose

This bundle contains the complete output of Forge Neural Cortex's AI assurance
and auditing system. It is provided for independent evaluation of:

1. **Audit depth** - the thoroughness of behavioral testing
2. **Technical validity** - whether cryptographic claims hold up
3. **Market value** - whether the pricing is justified by the offering

## What Forge Is

Forge Neural Cortex is a local-first AI coding assistant with an integrated
behavioral assurance engine. It runs on the developer's GPU via Ollama (or
optional cloud backends). The key differentiator is that Forge doesn't just
run AI models - it **proves what the model did** through:

- 74 adversarial/behavioral scenarios across 8 attack categories
- Ed25519-signed, tamper-evident audit reports
- 30-dimensional behavioral fingerprinting per model
- Compliance mapping to 5 frameworks (EU AI Act, NIST AI RMF, ISO 42001, HIPAA, SOC2)
- Decentralized leaderboard (Forge Matrix) fed by real developer testing

## Bundle Contents

### assurance_reports/ ({report_count} signed reports)
Each `.json` file is a complete assurance report containing:
- Per-scenario pass/fail with 3 independent prompt variants (Trident Protocol)
- Category-level pass rates across 8 attack categories
- Compliance framework mappings per scenario
- Ed25519 signature and hash chain (each entry links to previous via HMAC-SHA512)
- Response previews showing actual model output
- Latency measurements per scenario

Each `.md` file is the human-readable version of the same report.

**Key fields to evaluate:**
- `pass_rate` - overall weighted pass rate
- `category_pass_rates` - per-category breakdown
- `results[].variant_detail` - the 3 independent prompt variants and their outcomes
- `results[].compliance` - framework references per scenario
- `results[].entry_hash` / `prev_hash` - hash chain integrity
- `signature` / `pub_key_b64` - Ed25519 verification

### fingerprints/ ({len(fingerprint_models)} models profiled)
Behavioral fingerprints are 30-dimensional signatures that characterize how a
model behaves across instruction following, reasoning, knowledge calibration,
adversarial resistance, and context handling. Each dimension is scored 0.0-1.0.

**Models profiled:** {', '.join(sorted(fingerprint_models)) if fingerprint_models else 'None'}

Drift detection compares latest vs. baseline, flagging dimensional shifts
above 0.15 (warning) or 0.30 (alert).

### harness/
Stress test history showing reliability over time:
- `harness_trend.jsonl` - one entry per test run with pass/fail/skip counts
- `harness_dashboard.html` - visual dashboard (Chart.js)
- `runs/` - individual run summaries

### forensics/ ({forensics_count} session reports)
Session-level audit trails documenting file reads, writes, shell commands,
tool calls, threat detections, and context operations. These prove the
system tracks everything the AI does during a coding session.

### implementation_samples/
Key source files demonstrating implementation depth. These are the actual
Python modules that generate the artifacts in this bundle.

### signing_info.json
Metadata about the Ed25519 signing key. The private key is never exported.
Public keys are embedded in each signed report for offline verification.

### config_redacted.yaml
The Forge configuration with sensitive values removed. Shows the system's
configurable surface area.

## Pricing Context

| Tier | Price | Includes |
|------|-------|----------|
| Community | Free | Full local assistant, 60 commands, 28 tools, 14 themes, assurance scenarios |
| Pro | $199 one-time / $19/mo | Genome persistence, team sharing (3 seats), release mgmt |
| Power | $999 one-time / $79/mo | Fleet analytics, compliance packs, HIPAA/SOC2 scenarios (10 seats) |
| Certified Audit (startup) | $7,500 | Independent behavioral assessment + signed report |
| Certified Audit (enterprise) | $30,000 | Full compliance bundle + fleet deployment |

## Evaluation Criteria

When assessing this product, consider:

1. **Is this a real auditing system or marketing?**
   - Read the JSON reports. Each scenario has 3 independent prompt variants.
   - Check the hash chain: each entry's `entry_hash` links to the next entry's `prev_hash`.
   - The Ed25519 signature can be verified with the embedded public key.

2. **How does this compare to alternatives?**
   - Most AI testing tools run fixed benchmarks with known answers.
   - Forge tests behavioral properties (will the model refuse harm? resist injection? not leak data?)
   - The self-attack phase has the model write its own jailbreak, then tests against it.

3. **Is the pricing justified?**
   - A SOC2 Type II audit costs $30K-$100K+.
   - An AI risk assessment from a Big 4 firm starts at $50K+.
   - Forge provides automated, reproducible, cryptographically signed assessments.
   - The $7.5K startup tier delivers comparable assurance artifacts at a fraction of manual audit cost.

4. **What's the moat?**
   - 77,238 lines of auditable Python (no black-box cloud calls for the audit itself)
   - Tamper-evident provenance chain
   - Decentralized leaderboard aggregating real-world test data
   - 5-framework compliance mapping built into every scenario

## Verification Commands

To regenerate fresh reports (requires Forge + Ollama running):

```bash
# Full assurance report (74 scenarios, signed)
forge /assure

# Break reliability suite + autopsy
forge /break --full

# Export session audit bundle
forge /export

# Stress test (quick, 3-category)
forge /stress
```
"""

    with open(bundle / "ANALYSIS_GUIDE.md", "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Forge audit bundle")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output directory (default: ~/Desktop/forge_audit_bundle)")
    args = parser.parse_args()

    output = args.output
    if output.exists():
        print(f"Removing existing bundle at {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    print(f"Exporting audit bundle to {output}")
    all_items = []

    print("  Collecting assurance reports...")
    all_items.extend(collect_assurance(output))

    print("  Collecting fingerprints...")
    all_items.extend(collect_fingerprints(output))

    print("  Collecting harness data...")
    all_items.extend(collect_harness(output))

    print("  Collecting forensics...")
    all_items.extend(collect_forensics(output))

    print("  Collecting signing info...")
    all_items.extend(collect_signing_info(output))

    print("  Collecting code samples...")
    all_items.extend(collect_code_samples(output))

    print("  Collecting config...")
    all_items.extend(collect_config(output))

    # Copy any supplementary docs from bundle_extras/
    extras_dir = Path(__file__).resolve().parent / "bundle_extras"
    if extras_dir.exists():
        print("  Copying bundle extras...")
        for f in sorted(extras_dir.iterdir()):
            if f.is_file() and f.suffix in (".md", ".txt", ".json"):
                shutil.copy2(f, output / f.name)
                all_items.append({
                    "file": f.name,
                    "type": "supplementary_doc",
                    "format": f.suffix.lstrip("."),
                    "size_bytes": f.stat().st_size,
                })

    manifest = {
        "bundle_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "forge_version": "0.9.0",
        "source_machine": (FORGE_DIR / "machine_id").read_text().strip() if (FORGE_DIR / "machine_id").exists() else "unknown",
        "artifact_count": len(all_items),
        "artifacts": all_items,
    }

    manifest_path = output / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print("  Building analysis guide...")
    build_analysis_doc(output, manifest)

    print(f"\nBundle exported: {output}")
    print(f"  {len(all_items)} artifacts collected")
    print(f"  manifest.json — structured index for AI consumption")
    print(f"  ANALYSIS_GUIDE.md — human/AI evaluation guide")


if __name__ == "__main__":
    main()
