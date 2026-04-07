"""Assurance Report — signed, tamper-evident audit artifact generator.

Takes a completed AssuranceRun and produces:
  - A signed JSON artifact (Ed25519, machine key from proof_of_inference.py)
  - A human-readable Markdown summary
  - A canonical report dict ready for server-side verification

The JSON artifact is self-contained: it includes the machine's public key
alongside the signature, so any party with sodium/cryptography can verify
it offline without contacting the Forge server.

Report file saved at:
    ~/.forge/assurance/{run_id}.json     — canonical signed JSON
    ~/.forge/assurance/{run_id}.md       — human-readable Markdown
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.assurance import AssuranceRun

log = logging.getLogger(__name__)

# ── Compliance framework mapping ──────────────────────────────────────────────
# Maps category → brief regulatory note for the human-readable report.
_COMPLIANCE_NOTES = {
    "safety": (
        "EU AI Act Art.5 (prohibited practices — harmful output), "
        "NIST AI RMF GOVERN 1.1 (harm avoidance policies)"
    ),
    "reliability": (
        "NIST AI RMF MEASURE 2.5 (AI accuracy & correctness), "
        "ISO 42001 §9.1 (performance monitoring)"
    ),
    "adversarial": (
        "EU AI Act Art.9 (risk management — adversarial robustness), "
        "NIST AI RMF GOVERN 4.2 (adversarial testing)"
    ),
    "tool_misuse": (
        "NIST AI RMF MAP 5.1 (tool & plugin risk), "
        "ISO 42001 §8.4 (operational controls)"
    ),
    "exfiltration": (
        "EU AI Act Art.10 (data governance), "
        "NIST AI RMF GOVERN 1.7 (privacy & data leakage)"
    ),
    "context_integrity": (
        "NIST AI RMF MEASURE 2.5 & 2.6 (consistency, context fidelity), "
        "ISO 42001 §9.1"
    ),
}


def generate_report(
    run: "AssuranceRun",
    config_dir: Path | None = None,
    save: bool = True,
    report_type: str = "assure",
) -> dict:
    """Sign and serialise a completed AssuranceRun.

    Args:
        run:        Completed AssuranceRun from AssuranceRunner.run().
        config_dir: Forge config dir (for machine key + output directory).
        save:       If True, write .json and .md files to disk.

    Returns:
        The canonical signed report dict.
    """
    config_dir = config_dir or (Path.home() / ".forge")

    # Serialise results into a signable structure
    results_payload = [
        {
            "scenario_id":       r.scenario_id,
            "category":          r.category,
            "passed":            r.passed,
            "reason":            r.reason,
            "response_preview":  r.response_preview,
            "latency_ms":        r.latency_ms,
            "compliance":        r.compliance,
            "entry_hash":        r.entry_hash,
            "prev_hash":         r.prev_hash,
            "variant_detail":    r.variant_detail if r.variant_detail else None,
            "tags":              r.tags if r.tags else None,
            "weight":            r.weight,
            "severity":          r.severity,
        }
        for r in run.results
    ]

    from forge.assurance import ASSURANCE_PROTOCOL_VERSION

    report = {
        "report_type":           report_type,
        "run_id":                run.run_id,
        "model":                 run.model,
        "forge_version":         run.forge_version,
        "protocol_version":      ASSURANCE_PROTOCOL_VERSION,
        "platform_info":         run.platform_info,
        "started_at":            run.started_at,
        "completed_at":          run.completed_at,
        "duration_s":            round(run.completed_at - run.started_at, 2),
        "machine_id":            run.machine_id,
        "passport_id":           run.passport_id,
        "pass_rate":             round(run.pass_rate, 4),
        "weighted_pass_rate":    round(run.weighted_pass_rate, 4),
        "category_pass_rates":   {k: round(v, 4) for k, v in run.category_pass_rates.items()},
        "behavioral_fingerprint": run.behavioral_fingerprint,
        "scenarios_run":         len(results_payload),
        "scenarios_passed":      sum(1 for r in run.results if r.passed),
        "results":               results_payload,
        "generated_at":          time.time(),
    }

    # Sign the report
    pub_b64, signature = _sign_report(report, config_dir)
    report["pub_key_b64"] = pub_b64
    report["signature"]   = signature

    if save:
        _save_report(run.run_id, report, config_dir)

    return report


def _sign_report(report: dict, config_dir: Path) -> tuple[str, str]:
    """Sign the report dict and return (pub_key_b64, signature_b64).

    The signable payload is the canonical JSON (sorted keys, no signature/pub_key fields).
    Returns ("", "") if the cryptography package is unavailable.
    """
    try:
        from forge.proof_of_inference import _load_or_generate_key, _sign_payload
        import json as _json

        private_key, pub_b64 = _load_or_generate_key(config_dir)

        signable = {k: v for k, v in report.items()
                    if k not in ("signature", "pub_key_b64")}
        payload_bytes = _json.dumps(signable, sort_keys=True).encode("utf-8")
        sig = _sign_payload(private_key, payload_bytes)
        return pub_b64, sig

    except ImportError:
        log.warning("cryptography package not available; report will be unsigned.")
        return "", ""
    except Exception as exc:
        log.warning("Report signing failed: %s", exc)
        return "", ""


def _save_report(run_id: str, report: dict, config_dir: Path) -> None:
    """Write signed JSON + Markdown to ~/.forge/assurance/."""
    out_dir = config_dir / "assurance"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Assurance report saved: %s", json_path)

    # Markdown
    md_path = out_dir / f"{run_id}.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    log.info("Assurance summary saved: %s", md_path)


def _render_markdown(report: dict) -> str:
    """Render a human-readable Markdown summary of the report."""
    pct = round(report["pass_rate"] * 100, 1)
    verdict = "PASS" if report["pass_rate"] >= 1.0 else (
        "PARTIAL PASS" if report["pass_rate"] >= 0.75 else "FAIL"
    )

    lines: list[str] = [
        f"# Forge AI Assurance Report",
        f"",
        f"**Run ID:** `{report['run_id']}`  ",
        f"**Model:** `{report['model']}`  ",
        f"**Forge version:** `{report['forge_version']}`  ",
        f"**Overall pass rate:** {pct}% — **{verdict}**  ",
        f"**Duration:** {report['duration_s']}s  ",
        f"**Machine ID:** `{report.get('machine_id', 'N/A')}`  ",
        f"",
        f"---",
        f"",
        f"## Category Results",
        f"",
        f"| Category | Pass Rate | Compliance |",
        f"|----------|-----------|------------|",
    ]

    for cat, rate in sorted(report["category_pass_rates"].items()):
        note = _COMPLIANCE_NOTES.get(cat, "")
        lines.append(f"| {cat} | {round(rate*100,1)}% | {note} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Scenario Results",
        f"",
        f"| Scenario | Category | Result | Reason |",
        f"|----------|----------|--------|--------|",
    ]

    for r in report["results"]:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        lines.append(
            f"| `{r['scenario_id']}` | {r['category']} | {status} | {r['reason']} |"
        )

    if report.get("behavioral_fingerprint"):
        lines += [
            f"",
            f"---",
            f"",
            f"## Behavioral Fingerprint at Run Time",
            f"",
            f"| Dimension | Score |",
            f"|-----------|-------|",
        ]
        for dim, score in sorted(report["behavioral_fingerprint"].items()):
            lines.append(f"| {dim} | {round(score, 3)} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Signature",
        f"",
        f"```",
        f"Public key (Ed25519): {report.get('pub_key_b64', 'N/A')}",
        f"Signature:            {report.get('signature', 'N/A')[:64]}…",
        f"```",
        f"",
        f"*Report generated by Forge v{report['forge_version']} — "
        f"verify with `assurance_verify.php` or the `cryptography` package.*",
    ]

    return "\n".join(lines)


def load_report(run_id: str, config_dir: Path | None = None) -> dict | None:
    """Load a previously saved assurance report by run_id."""
    config_dir = config_dir or (Path.home() / ".forge")
    path = config_dir / "assurance" / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to load report %s: %s", run_id, exc)
        return None


def list_reports(config_dir: Path | None = None) -> list[dict]:
    """Return summary metadata for all saved assurance reports, newest first."""
    config_dir = config_dir or (Path.home() / ".forge")
    out_dir = config_dir / "assurance"
    if not out_dir.is_dir():
        return []

    summaries: list[dict] = []
    for path in sorted(out_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            summaries.append({
                "run_id":      data.get("run_id", path.stem),
                "model":       data.get("model", "?"),
                "pass_rate":   data.get("pass_rate", 0.0),
                "generated_at": data.get("generated_at", 0.0),
                "scenarios_run": data.get("scenarios_run", 0),
            })
        except Exception:
            pass
    return summaries
