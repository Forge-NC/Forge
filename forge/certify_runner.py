"""Forge CLI — Self-Hosted Certified Audit flow.

Triggered by `/certify-audit <order_id>` from the Forge CLI. Walks a
paying customer through:

    1. Generate a one-time X25519 keypair (stays on the user's machine).
    2. POST the public X25519 key + order_id + runner_kind to the Forge NC
       enrollment endpoint; receive a single-use download URL.
    3. Download the sealed bundle, open it with the private X25519 key.
    4. Verify the envelope's Origin signature offline.
    5. Run the Forge Crucible Assurance Protocol against the audit target
       (pulled from the bundle's `target` block).
    6. Sign the final report with the bundle's child Ed25519 seed.
    7. POST the signed report to the ingest endpoint with an HMAC upload
       header. Receive the certified report URL + transparency leaf index.

Proprietary. © Forge NC (Forge Neural Cortex). All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("forge.certify_runner")


FORGE_NC_BASE = "https://forge-nc.dev"
ENROLL_URL    = FORGE_NC_BASE + "/api/v1/external/enroll"


class CertifyError(RuntimeError):
    """Raised when any phase of the self-hosted certification flow fails."""


def certify_audit(
    *,
    order_id: str,
    auth_token: str,
    target_endpoint_url: Optional[str] = None,
    target_api_key: Optional[str] = None,
    runner_kind: str = "self-hosted-fca",
    session_dir: Optional[Path] = None,
) -> dict:
    """Execute the self-hosted FCA flow end-to-end.

    Args:
        order_id:             Forge NC order ID (starts with 'aud_').
        auth_token:           Forge passport / API token used to authenticate
                              the enrollment request (Authorization header).
        target_endpoint_url:  Override the bundle's target.endpoint_url.
                              Useful if the bundle was created with a
                              placeholder endpoint and the real URL is only
                              known locally.
        target_api_key:       API key for the target endpoint.
        runner_kind:          "self-hosted-fca" or "deployment-assessment-vpc".
        session_dir:          Where to stash the ephemeral bundle + keypair
                              during this run. Defaults to a per-run temp dir
                              under ~/.forge/certify/.

    Returns:
        The ingest response dict (includes report_url and
        transparency_leaf_index).
    """
    try:
        import requests  # noqa: F401
    except Exception as exc:
        raise CertifyError("requests package required") from exc

    from forge.external_runner_keys import (
        generate_runner_keypair,
        open_bundle,
        verify_external_attestation,
    )

    if session_dir is None:
        home = Path.home() / ".forge" / "certify" / order_id
    else:
        home = Path(session_dir).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    # ── 1. Generate runner X25519 keypair ────────────────────────────────
    runner_priv, runner_pub = generate_runner_keypair()
    priv_path = home / "runner.key"
    priv_path.write_bytes(runner_priv)
    os.chmod(priv_path, 0o600)

    # ── 2. Enroll with forge-nc.dev ──────────────────────────────────────
    log.info("Enrolling order_id=%s (runner_kind=%s) …", order_id, runner_kind)
    enroll_resp = _post_json(
        ENROLL_URL,
        headers={"Authorization": f"Bearer {auth_token}"},
        body={
            "order_id":              order_id,
            "runner_pub_x25519_b64": base64.b64encode(runner_pub).decode("ascii"),
            "runner_kind":           runner_kind,
        },
    )
    if not enroll_resp.get("ok"):
        raise CertifyError(f"Enrollment failed: {enroll_resp!r}")

    job_id       = enroll_resp["job_id"]
    download_url = enroll_resp["download_url"]
    log.info("Enrolled. job_id=%s; downloading sealed bundle …", job_id)

    # ── 3. Download the sealed bundle ────────────────────────────────────
    bundle_path = home / f"bundle_{job_id}.enc"
    _download_to_file(download_url, bundle_path, auth_token=auth_token)
    log.info("Bundle downloaded: %s (%d bytes)", bundle_path, bundle_path.stat().st_size)

    # ── 4. Open + verify envelope ────────────────────────────────────────
    bundle_bytes = bundle_path.read_bytes()
    bundle = open_bundle(bundle_bytes, runner_priv)
    envelope = bundle["envelope"]

    # Offline pubkey pinning: fetch /.well-known/forge-origin.json once
    origin_pub_b64 = _fetch_origin_pubkey()
    if envelope.get("origin_pub_b64") != origin_pub_b64:
        raise CertifyError(
            "envelope origin_pub_b64 does not match forge-nc.dev .well-known; "
            "bundle may be forged or Origin key rotated mid-flight."
        )

    # Full verification of signature + expiry (skip HKDF re-derivation
    # since we don't have the Origin seed client-side).
    _verify_origin_signature(envelope)

    # ── 5. Run the audit ─────────────────────────────────────────────────
    log.info("Running Crucible Assurance Protocol …")
    report = _run_audit(bundle, target_endpoint_url, target_api_key)

    # ── 6. Sign the report with the bundle's child Ed25519 seed ──────────
    _sign_report(report, bundle["child_priv_seed_b64"])

    # ── 7. Upload ────────────────────────────────────────────────────────
    log.info("Uploading signed report …")
    ingest_resp = _upload_report(report, bundle)
    log.info("Certified. %s", ingest_resp.get("report_url", ""))

    # Cleanup ephemeral keypair + bundle (child priv is single-use anyway)
    try:
        priv_path.unlink()
        bundle_path.unlink()
    except Exception:
        pass

    return ingest_resp


# ── Helpers ───────────────────────────────────────────────────────────────

def _post_json(url: str, headers: dict, body: dict) -> dict:
    import requests
    headers.setdefault("Content-Type", "application/json")
    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        try:
            err = resp.json()
        except Exception:
            err = {"error": resp.text[:500]}
        raise CertifyError(f"{url} -> HTTP {resp.status_code}: {err}")
    return resp.json()


def _download_to_file(url: str, path: Path, auth_token: str = "") -> None:
    import requests
    headers = {"User-Agent": "forge-cli/self-hosted"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    with requests.get(url, headers=headers, timeout=60, stream=True) as r:
        if r.status_code != 200:
            raise CertifyError(f"Bundle download failed: HTTP {r.status_code}")
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
    os.chmod(path, 0o600)


def _fetch_origin_pubkey() -> str:
    """Pull the Origin pubkey from the canonical well-known endpoint.

    Returns the base64 pubkey string. Caches once per process.
    """
    global _cached_origin_pub
    try:
        return _cached_origin_pub  # type: ignore[name-defined]
    except NameError:
        pass
    import requests
    r = requests.get(FORGE_NC_BASE + "/.well-known/forge-origin.json", timeout=15)
    r.raise_for_status()
    doc = r.json()
    # Verify self-signature
    sig_b64 = doc.get("self_signature_b64")
    pub_b64 = doc.get("origin_pub_b64")
    if not sig_b64 or not pub_b64:
        raise CertifyError("well-known forge-origin.json missing required fields")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        body = {k: v for k, v in doc.items() if k != "self_signature_b64"}
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig_b64), payload
        )
    except Exception as exc:
        raise CertifyError(f"well-known forge-origin.json signature failed: {exc}")
    _cached_origin_pub = pub_b64  # type: ignore[misc]
    return pub_b64


def _verify_origin_signature(envelope: dict) -> None:
    """Offline-check the Origin signature over an attestation envelope."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    sig_b64 = envelope.get("origin_envelope_sig", "")
    pub_b64 = envelope.get("origin_pub_b64", "")
    if not sig_b64 or not pub_b64:
        raise CertifyError("envelope missing Origin signature fields")
    env_for_sig = {k: v for k, v in envelope.items() if k != "origin_envelope_sig"}
    to_verify = json.dumps(env_for_sig, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig_b64), to_verify
        )
    except InvalidSignature:
        raise CertifyError("envelope Origin signature did not verify")


def _validate_bundled_scenarios(pack: dict) -> list[dict]:
    """Verify the bundle's scenario pack against its declared content hash.

    The runner is the trust boundary for self-hosted FCA. Even though the
    bundle is sealed and Origin-signed, a malicious operator could in
    principle manipulate the scenario list before signing the resulting
    report — UNLESS we re-derive the hash from the bundled scenarios and
    require it to equal what the bundle declares. The hash is also pinned
    by the Origin envelope, so the chain is: Origin → envelope.scenario_pack_hash
    → bundle.scenario_pack.hash → recomputed(bundle.scenario_pack.scenarios).
    """
    if not isinstance(pack, dict):
        raise CertifyError("Bundle is missing scenario_pack block")
    scenarios = pack.get("scenarios")
    declared = pack.get("hash") or ""
    scheme = pack.get("scheme") or ""
    if not isinstance(scenarios, list) or not scenarios:
        raise CertifyError("Bundle scenario_pack has no scenarios array")
    if scheme != "forge.scenario-pack.v1":
        raise CertifyError(f"Unknown scenario_pack scheme: {scheme!r}")
    if not declared:
        raise CertifyError("Bundle scenario_pack is missing 'hash'")

    # Re-derive the canonical hash. MUST match forge.scenario_pack_export
    # exactly (sort by id, sort_keys, no whitespace, ensure_ascii=False).
    sorted_entries = sorted(scenarios, key=lambda s: s["id"])
    canonical = json.dumps(
        sorted_entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    computed = hashlib.sha512(canonical).hexdigest()
    if not hmac.compare_digest(computed, declared):
        raise CertifyError(
            "Scenario pack hash mismatch — bundle was tampered with or "
            "produced by a divergent exporter. Refusing to run."
        )
    return sorted_entries


def _run_audit(bundle: dict, target_url_override: Optional[str], target_api_key: Optional[str]) -> dict:
    """Run break + assurance and return the assurance report with envelope attached."""
    from forge.assurance import AssuranceRunner
    from forge.assurance_report import generate_report
    from forge.break_runner import BreakRunner
    from forge.models.openai_backend import OpenAIBackend

    envelope = bundle["envelope"]
    target = bundle.get("target", {})
    endpoint_url = target_url_override or target.get("endpoint_url") or ""
    model_id     = target.get("model_id") or ""
    if not endpoint_url:
        raise CertifyError("No target endpoint_url (bundle and override both empty)")

    # Validate and use ONLY the scenarios bundled in the sealed payload.
    # The runner's local _SCENARIOS is intentionally NOT consulted for FCA
    # — local Forge code may be modified by the operator; the bundle is the
    # Origin-signed source of truth.
    bundled_scenarios = _validate_bundled_scenarios(bundle.get("scenario_pack") or {})

    backend = OpenAIBackend(
        base_url=endpoint_url.rstrip("/"),
        api_key=target_api_key or os.environ.get("FORGE_TARGET_API_KEY", ""),
        model=model_id,
    )

    # BreakRunner runs the assurance suite + behavioral fingerprint and
    # produces the break-side report; AssuranceRunner produces the
    # paired assurance-side report. Both consume the SAME bundled scenarios.
    break_runner = BreakRunner()
    break_result = break_runner.run(
        llm=backend,
        model=model_id,
        mode="full",
        report_type="certify",
        scenarios=bundled_scenarios,
    )

    assure_runner = AssuranceRunner()
    assure_run = assure_runner.run(
        llm=backend,
        model=model_id,
        scenarios=bundled_scenarios,
    )
    assure_result_report = generate_report(assure_run, report_type="certify")

    break_result.report["paired_run_id"]    = assure_result_report["run_id"]
    assure_result_report["paired_run_id"]   = break_result.report["run_id"]

    report = assure_result_report
    report["_verification"] = {"external_envelope": envelope}
    return report


def _sign_report(report: dict, child_priv_seed_b64: str) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    seed = base64.b64decode(child_priv_seed_b64)
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub_bytes = priv.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)

    signable = {
        k: v for k, v in report.items()
        if k not in ("signature", "pub_key_b64", "paired_run_id", "_verification")
    }
    to_sign = json.dumps(signable, sort_keys=True).encode("utf-8")

    report["pub_key_b64"] = base64.b64encode(pub_bytes).decode("ascii")
    report["signature"]   = base64.b64encode(priv.sign(to_sign)).decode("ascii")


def _upload_report(report: dict, bundle: dict) -> dict:
    import requests

    upload_url    = bundle["upload_url"]
    upload_secret = base64.b64decode(bundle["upload_secret_b64"])
    body = json.dumps({"report": report}, sort_keys=False).encode("utf-8")
    mac  = hmac.new(upload_secret, body, hashlib.sha512).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Forge-Upload-HMAC": mac,
        "User-Agent": "forge-cli/self-hosted",
    }
    resp = requests.post(upload_url, data=body, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise CertifyError(f"Upload failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()
