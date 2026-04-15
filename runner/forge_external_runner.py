"""Forge External Runner — entrypoint for the customer-hosted audit runner.

Runs inside either:
  - A Docker container (ghcr.io/forge-nc/forge-external-runner:v1) for the
    in-VPC Deployment Assessment flow, or
  - The customer's Forge CLI for the self-hosted Forge Certified Audit flow.

Lifecycle (single-shot):
  1. Load the sealed bundle from disk (FORGE_BUNDLE env or --bundle flag).
  2. Load the runner's X25519 private key (FORGE_RUNNER_PRIV env or --runner-priv flag).
  3. Open the bundle; extract envelope + child signing seed + upload metadata.
  4. Offline-verify the envelope against the pinned Origin public key
     (fetched once from /.well-known/forge-origin.json or pinned in env).
  5. Run the Forge Crucible Assurance Protocol's 74 scenarios against the
     configured target (endpoint_url + model_id from the bundle's target block,
     plus customer-provided FORGE_TARGET_API_KEY + FORGE_TARGET_URL overrides).
  6. Sign the final report with the child Ed25519 key.
  7. POST the report to upload_url with an HMAC-SHA512 body authentication
     header (X-Forge-Upload-HMAC), using upload_secret from the bundle.
  8. Print the server's response (report URL, transparency leaf index, etc.)
     and exit 0 on success, nonzero on failure.

The runner is stateless. One bundle = one audit run. Bundles are single-use
server-side; any retry needs a fresh bundle via the admin reissue flow.

Proprietary. © Forge NC (Forge Neural Cortex). All rights reserved.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any


log = logging.getLogger("forge.external_runner")


# ── Configuration ─────────────────────────────────────────────────────────

class RunnerConfig:
    """Resolved configuration for a single runner invocation."""

    def __init__(
        self,
        bundle_path: Path,
        runner_priv_path: Path | None,
        runner_priv_b64: str | None,
        target_url_override: str | None,
        target_api_key: str | None,
        verbose: bool,
    ):
        self.bundle_path = bundle_path
        self.runner_priv_path = runner_priv_path
        self.runner_priv_b64 = runner_priv_b64
        self.target_url_override = target_url_override
        self.target_api_key = target_api_key
        self.verbose = verbose


def parse_args() -> RunnerConfig:
    parser = argparse.ArgumentParser(
        prog="forge-external-runner",
        description="Forge External Runner — one-shot audit executor",
    )
    parser.add_argument(
        "--bundle",
        default=os.environ.get("FORGE_BUNDLE"),
        help="Path to the sealed bundle (.enc file). Defaults to env FORGE_BUNDLE.",
    )
    parser.add_argument(
        "--runner-priv",
        default=os.environ.get("FORGE_RUNNER_PRIV"),
        help="Path to runner X25519 private key file (raw 32 bytes). Defaults to env FORGE_RUNNER_PRIV.",
    )
    parser.add_argument(
        "--runner-priv-b64",
        default=os.environ.get("FORGE_RUNNER_PRIV_B64"),
        help="Base64-encoded X25519 private key (alternative to --runner-priv).",
    )
    parser.add_argument(
        "--target-url",
        default=os.environ.get("FORGE_TARGET_URL"),
        help="Override the target endpoint URL from the bundle (for environments where internal DNS differs).",
    )
    parser.add_argument(
        "--target-api-key",
        default=os.environ.get("FORGE_TARGET_API_KEY"),
        help="API key for the target endpoint (Bearer token). Defaults to env FORGE_TARGET_API_KEY.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()

    if not args.bundle:
        parser.error("--bundle (or env FORGE_BUNDLE) is required")
    bundle_path = Path(args.bundle).expanduser().resolve()
    if not bundle_path.exists():
        parser.error(f"Bundle not found: {bundle_path}")

    if not (args.runner_priv or args.runner_priv_b64):
        parser.error("--runner-priv (or --runner-priv-b64) is required")
    runner_priv_path = Path(args.runner_priv).expanduser().resolve() if args.runner_priv else None
    if runner_priv_path and not runner_priv_path.exists():
        parser.error(f"Runner private key file not found: {runner_priv_path}")

    return RunnerConfig(
        bundle_path=bundle_path,
        runner_priv_path=runner_priv_path,
        runner_priv_b64=args.runner_priv_b64,
        target_url_override=args.target_url,
        target_api_key=args.target_api_key,
        verbose=args.verbose,
    )


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# ── Bundle loading + envelope verification ────────────────────────────────

def load_runner_private_key(cfg: RunnerConfig) -> bytes:
    """Load the runner's X25519 private key from file or base64 env."""
    if cfg.runner_priv_path:
        raw = cfg.runner_priv_path.read_bytes()
        if len(raw) == 32:
            return raw
        # Tolerate base64 content in the file too
        try:
            decoded = base64.b64decode(raw, validate=True)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        raise SystemExit(f"Runner priv file must be 32 raw bytes or base64-encoded 32 bytes")
    # b64
    decoded = base64.b64decode(cfg.runner_priv_b64 or "", validate=True)
    if len(decoded) != 32:
        raise SystemExit("Runner priv b64 must decode to exactly 32 bytes")
    return decoded


def open_and_verify_bundle(cfg: RunnerConfig) -> dict:
    """Open the sealed bundle, then verify the envelope offline against the Origin pubkey."""
    from forge.external_runner_keys import (
        open_bundle,
        verify_external_attestation,
    )

    log.info("Opening bundle: %s", cfg.bundle_path)
    runner_priv = load_runner_private_key(cfg)
    bundle_bytes = cfg.bundle_path.read_bytes()
    bundle = open_bundle(bundle_bytes, runner_priv)

    envelope = bundle.get("envelope")
    if not isinstance(envelope, dict):
        raise SystemExit("Bundle missing envelope")

    # Verify envelope with only the Origin pubkey (we don't have the seed);
    # the HKDF re-derivation part is trusted-because-server-generated.
    # Full server-side verification happens at ingest time anyway.
    _assert_origin_signature(envelope, bundle.get("origin_pubkey_b64", ""))
    log.info("Envelope Origin-signature verified. job_id=%s runner_kind=%s",
             envelope.get("job_id"), envelope.get("runner_kind"))
    return bundle


def _assert_origin_signature(envelope: dict, origin_pubkey_b64: str) -> None:
    """Verify origin_envelope_sig against the pinned Origin pubkey.

    This is a client-side precheck so the runner fails fast if the bundle
    was tampered with or Origin-pubkey-rotated out from under it.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception as exc:
        raise SystemExit(f"cryptography package required: {exc}")

    sig_b64 = envelope.get("origin_envelope_sig", "")
    if not sig_b64:
        raise SystemExit("envelope missing origin_envelope_sig")

    # Allow envelope's own origin_pub_b64 to override bundle's pinned pubkey
    # only if they match. If they don't, something is wrong.
    env_pub = envelope.get("origin_pub_b64", "")
    if origin_pubkey_b64 and env_pub and env_pub != origin_pubkey_b64:
        raise SystemExit("origin_pub_b64 mismatch between envelope and bundle")
    pub_b64 = env_pub or origin_pubkey_b64
    if not pub_b64:
        raise SystemExit("no Origin pubkey available for envelope verification")

    env_for_sig = {k: v for k, v in envelope.items() if k != "origin_envelope_sig"}
    to_verify = json.dumps(env_for_sig, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
        pub.verify(base64.b64decode(sig_b64), to_verify)
    except InvalidSignature:
        raise SystemExit("envelope origin_envelope_sig did not verify")


# ── Audit execution ───────────────────────────────────────────────────────

def run_audit(bundle: dict, cfg: RunnerConfig) -> dict:
    """Run the Forge Crucible Assurance Protocol and return the signed report."""
    from forge.assurance import AssuranceRunner
    from forge.assurance_report import generate_report
    from forge.break_runner import BreakRunner
    from forge.models.openai_backend import OpenAIBackend

    envelope = bundle["envelope"]
    target = bundle.get("target", {})

    endpoint_url = cfg.target_url_override or target.get("endpoint_url") or ""
    model_id     = target.get("model_id") or ""
    api_key      = cfg.target_api_key or os.environ.get("FORGE_TARGET_API_KEY") or ""
    if not endpoint_url:
        raise SystemExit("Target endpoint_url missing (not in bundle and --target-url not given)")

    log.info("Target: %s (model=%s)", endpoint_url, model_id)

    backend = OpenAIBackend(
        base_url=endpoint_url.rstrip("/"),
        api_key=api_key,
        model=model_id,
    )

    break_runner = BreakRunner(
        backend=backend,
        scenarios=None,   # default = full catalog
    )
    break_result = break_runner.run()

    assure_runner = AssuranceRunner(
        backend=backend,
        scenarios=None,
    )
    assure_result = assure_runner.run()

    # Pair the two runs via paired_run_id
    break_result.report["paired_run_id"]  = assure_result.report["run_id"]
    assure_result.report["paired_run_id"] = break_result.report["run_id"]

    # Sign the ASSURE report with the child key (this is the one we upload)
    report = assure_result.report
    report["_verification"] = {"external_envelope": envelope}

    _sign_report_with_child_key(report, bundle["child_priv_seed_b64"])
    log.info("Audit complete. scenarios_run=%s pass_rate=%.4f",
             report.get("scenarios_run"), report.get("pass_rate", 0))
    return report


def _sign_report_with_child_key(report: dict, child_priv_seed_b64: str) -> None:
    """Sign the report in place: populate pub_key_b64 and signature using the child Ed25519 key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    seed = base64.b64decode(child_priv_seed_b64)
    if len(seed) != 32:
        raise SystemExit("child_priv_seed_b64 must be 32 bytes after base64 decode")
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub_bytes = priv.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)

    # Canonical signable body: report minus signature + pub_key_b64 + paired_run_id + _verification
    signable = {
        k: v for k, v in report.items()
        if k not in ("signature", "pub_key_b64", "paired_run_id", "_verification")
    }
    to_sign = json.dumps(signable, sort_keys=True).encode("utf-8")

    report["pub_key_b64"] = base64.b64encode(pub_bytes).decode("ascii")
    report["signature"]   = base64.b64encode(priv.sign(to_sign)).decode("ascii")


# ── Upload ────────────────────────────────────────────────────────────────

def upload_report(report: dict, bundle: dict) -> dict:
    """POST the signed report to the bundle's upload_url with HMAC auth header.

    Returns the server's JSON response on success. Raises SystemExit on failure.
    """
    import requests

    upload_url    = bundle.get("upload_url", "")
    upload_secret = base64.b64decode(bundle.get("upload_secret_b64", ""))
    if not upload_url or not upload_secret:
        raise SystemExit("Bundle missing upload_url or upload_secret_b64")

    body = json.dumps({"report": report}, sort_keys=False).encode("utf-8")
    mac = hmac.new(upload_secret, body, hashlib.sha512).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Forge-Upload-HMAC": mac,
        "User-Agent": "forge-external-runner/1.0",
    }

    log.info("Uploading report to %s (body=%d bytes)", upload_url, len(body))
    try:
        resp = requests.post(upload_url, data=body, headers=headers, timeout=60)
    except Exception as exc:
        raise SystemExit(f"Upload failed (network): {exc}")

    if resp.status_code != 200:
        log.error("Upload failed: status=%d body=%s", resp.status_code, resp.text[:500])
        raise SystemExit(f"Upload rejected ({resp.status_code})")

    try:
        return resp.json()
    except Exception:
        raise SystemExit(f"Upload response not JSON: {resp.text[:500]}")


# ── Entrypoint ────────────────────────────────────────────────────────────

def main() -> int:
    cfg = parse_args()
    setup_logging(cfg.verbose)

    try:
        bundle = open_and_verify_bundle(cfg)
    except SystemExit:
        raise
    except Exception as exc:
        log.exception("Bundle open failed")
        return 2

    start = time.monotonic()
    try:
        report = run_audit(bundle, cfg)
    except SystemExit:
        raise
    except Exception as exc:
        log.exception("Audit execution failed")
        return 3

    try:
        resp = upload_report(report, bundle)
    except SystemExit:
        raise
    except Exception:
        log.exception("Upload failed")
        return 4

    elapsed = time.monotonic() - start
    log.info("Done in %.1fs. Report: %s  Leaf: %s",
             elapsed, resp.get("report_url"), resp.get("transparency_leaf_index"))
    print(json.dumps(resp, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
