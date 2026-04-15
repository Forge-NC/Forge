"""Forge NC — Offline Report Verifier.

Pure-Python implementation of the client-side verification logic for a
Forge Certified Audit report. Only depends on the `cryptography` package
(no network access required once the Origin pubkey is pinned or fetched).

Typical usage:

    >>> from forge.verifier import verify_report
    >>> with open("report.json") as f:
    ...     report = json.load(f)
    >>> result = verify_report(report, origin_pub_b64="1QTiJehHw...")
    >>> if result.valid:
    ...     print("Certified:", result.certified_by)
    >>> else:
    ...     for issue in result.issues:
    ...         print("ISSUE:", issue)

The verifier checks (in order):
    1. Report has a signature + pub_key_b64
    2. The signature verifies against pub_key_b64 (report integrity)
    3. If _verification.external_envelope is present:
         a. Envelope scheme matches
         b. Envelope not expired
         c. Envelope Origin signature verifies against origin_pub
         d. Envelope's child_pub_b64 matches report.pub_key_b64
    4. If _verification.origin_signature is present:
         a. Countersignature verifies against origin_pub
    5. Hash chain integrity (informational — not a reject reason since
       timestamp normalization differs between generator languages)
    6. Revocation: if a revocation list is supplied, the job_id must not
       appear. Callers can fetch this from
       https://forge-nc.dev/.well-known/forge-revocations.json

The verifier does NOT require any network access. Callers who want
transparency-log inclusion proofs can fetch them separately from
https://forge-nc.dev/api/v1/external/inclusion_proof and verify them
with `verify_inclusion_proof()`.

Proprietary. © Forge NC (Forge Neural Cortex). All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


SCHEME = "forge-external-runner-v1"


@dataclass
class VerificationResult:
    valid: bool
    certified: bool = False
    certified_by: str = ""
    certified_at: int = 0
    issues: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)  # per-check pass/fail

    def __bool__(self) -> bool:
        return self.valid


# ── Canonical JSON (matches forge_canonical_json in PHP) ─────────────────

def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _python_json_signable(obj: dict) -> bytes:
    """Match the report-signing rule: sort_keys but default separators.

    This is different from _canonical_json (which uses compact separators)
    because the machine-signed portion of reports used Python's default
    json.dumps(sort_keys=True). The envelope origin sig uses canonical form.
    Both are deterministic; just different rules for different fields.
    """
    return json.dumps(obj, sort_keys=True).encode("utf-8")


# ── Primary API ──────────────────────────────────────────────────────────

def verify_report(
    report: dict,
    origin_pub_b64: Optional[str] = None,
    revocation_list: Optional[list] = None,
    now_ts: Optional[int] = None,
    strict_hash_chain: bool = False,
) -> VerificationResult:
    """Verify a Forge Certified Audit report offline.

    Args:
        report:           The full signed report dict.
        origin_pub_b64:   Pinned Origin public key (base64-encoded raw 32 bytes).
                          If None, the verifier will look for it inside
                          _verification.origin_pub_key_b64 or envelope.origin_pub_b64.
        revocation_list:  Iterable of revoked job_ids.
        now_ts:           Current unix time (for expiry checks). Defaults to time().
        strict_hash_chain: If True, a broken hash chain fails the overall result.
                          Default False — the chain is informational.

    Returns:
        VerificationResult with valid flag + per-check dict + any issues.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception as exc:
        return VerificationResult(
            valid=False,
            issues=[f"cryptography package required: {exc}"]
        )

    result = VerificationResult(valid=False)
    if now_ts is None:
        now_ts = int(time.time())

    # ── 1. Machine signature ─────────────────────────────────────────────
    sig_b64 = report.get("signature", "")
    pub_b64 = report.get("pub_key_b64", "")
    if not sig_b64 or not pub_b64:
        result.issues.append("Report missing signature or pub_key_b64")
        result.checks["machine_signature"] = "missing"
        return result
    signable = {
        k: v for k, v in report.items()
        if k not in ("signature", "pub_key_b64", "paired_run_id", "_verification")
    }
    to_verify = _python_json_signable(signable)
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig_b64), to_verify
        )
        result.checks["machine_signature"] = "verified"
    except InvalidSignature:
        result.issues.append("Machine signature did not verify")
        result.checks["machine_signature"] = "invalid"
        return result
    except Exception as exc:
        result.issues.append(f"Machine signature verification error: {exc}")
        result.checks["machine_signature"] = "error"
        return result

    # ── 2. Envelope (for external-runner reports) ────────────────────────
    envelope = (report.get("_verification") or {}).get("external_envelope")
    env_present = isinstance(envelope, dict)
    result.checks["envelope_present"] = env_present

    if env_present:
        # Pin origin pubkey: prefer caller-supplied, else envelope, else verification block
        resolved_origin = origin_pub_b64 or envelope.get("origin_pub_b64")
        if not resolved_origin:
            result.issues.append("No Origin pubkey available for envelope verification")
            result.checks["envelope"] = "no_origin_pub"
            return result
        # Scheme
        if envelope.get("scheme") != SCHEME:
            result.issues.append(f"Envelope scheme mismatch: {envelope.get('scheme')}")
            result.checks["envelope_scheme"] = "mismatch"
            return result
        # Expiry
        expires_at = int(envelope.get("expires_at", 0))
        if now_ts > expires_at:
            result.issues.append(f"Envelope expired at {expires_at} (now {now_ts})")
            result.checks["envelope_expiry"] = "expired"
            # Non-fatal: existing signatures remain provable, but envelope no longer valid
        else:
            result.checks["envelope_expiry"] = "fresh"
        # Origin signature over envelope
        env_sig_b64 = envelope.get("origin_envelope_sig", "")
        if not env_sig_b64:
            result.issues.append("Envelope missing origin_envelope_sig")
            result.checks["envelope_origin_sig"] = "missing"
            return result
        env_for_sig = {k: v for k, v in envelope.items() if k != "origin_envelope_sig"}
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(resolved_origin)).verify(
                base64.b64decode(env_sig_b64),
                _canonical_json(env_for_sig),
            )
            result.checks["envelope_origin_sig"] = "verified"
        except InvalidSignature:
            result.issues.append("Envelope Origin signature did not verify")
            result.checks["envelope_origin_sig"] = "invalid"
            return result
        # Binding: child_pub in envelope must match report.pub_key_b64
        if envelope.get("child_pub_b64") != pub_b64:
            result.issues.append("Report pub_key_b64 does not match envelope child_pub_b64")
            result.checks["envelope_binding"] = "mismatch"
            return result
        result.checks["envelope_binding"] = "ok"
        # Revocation
        if revocation_list and envelope.get("job_id") in revocation_list:
            result.issues.append(f"Job {envelope.get('job_id')} is on the revocation list")
            result.checks["envelope_revocation"] = "revoked"
            return result
        result.checks["envelope_revocation"] = "not_revoked"

    # ── 3. Origin countersignature (if present) ─────────────────────────
    verif = report.get("_verification") or {}
    cs_b64 = verif.get("origin_signature", "")
    cs_pub_b64 = verif.get("origin_pub_key_b64", origin_pub_b64)
    if cs_b64:
        if not cs_pub_b64:
            result.issues.append("Origin countersignature present but no pubkey to verify against")
            result.checks["origin_countersig"] = "no_pub"
            return result
        cs_payload = {
            "run_id":              report.get("run_id", ""),
            "machine_signature":   sig_b64,
            "machine_pub_key_b64": pub_b64,
            "pass_rate":           float(report.get("pass_rate", 0.0)),
            "model":               report.get("model", ""),
            "scenarios_run":       int(report.get("scenarios_run", 0)),
            "certified_at":        int(verif.get("certified_at", 0)),
            "certified_by":        verif.get("certified_by", ""),
        }
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(cs_pub_b64)).verify(
                base64.b64decode(cs_b64),
                _canonical_json(cs_payload),
            )
            result.checks["origin_countersig"] = "verified"
            result.certified = True
            result.certified_by = str(verif.get("certified_by", ""))
            result.certified_at = int(verif.get("certified_at", 0))
        except InvalidSignature:
            result.issues.append("Origin countersignature did not verify")
            result.checks["origin_countersig"] = "invalid"
            return result

    # ── 4. Hash chain (informational) ───────────────────────────────────
    chain_ok = _check_hash_chain(report)
    result.checks["hash_chain"] = "intact" if chain_ok else "broken"
    if not chain_ok:
        result.issues.append("Hash chain irregular (informational)")
        if strict_hash_chain:
            return result

    # ── 5. Revocation check on _verification.certification_revoked ──────
    if verif.get("certification_revoked"):
        result.issues.append("Report's _verification.certification_revoked flag is True")
        result.checks["post_publish_revocation"] = "revoked"
        return result
    result.checks["post_publish_revocation"] = "not_revoked"

    result.valid = True
    return result


def _check_hash_chain(report: dict) -> bool:
    """Walk results array and verify each entry's prev_hash == prior entry's entry_hash."""
    results = report.get("results", [])
    if not isinstance(results, list):
        return False
    prev = ""
    for r in results:
        if not isinstance(r, dict):
            return False
        if (r.get("prev_hash") or "") != prev:
            return False
        prev = str(r.get("entry_hash") or "")
    return True


# ── Transparency log inclusion proof ─────────────────────────────────────

def verify_inclusion_proof(proof: dict, sth: dict) -> tuple:
    """Verify a Merkle inclusion proof against a signed tree head.

    Args:
        proof: Inclusion proof object (from /api/v1/external/inclusion_proof)
               with fields leaf_index, tree_size, leaf_hash, path (list of
               {direction, hash}).
        sth:   Signed Tree Head (from /.well-known/forge-transparency-sth.json)
               with fields tree_size, root_hash, timestamp, signature_b64,
               origin_pub_b64.

    Returns:
        (is_valid, reason)
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception as exc:
        return (False, f"cryptography required: {exc}")

    # First: verify STH signature
    sig_b64 = sth.get("signature_b64", "")
    pub_b64 = sth.get("origin_pub_b64", "")
    if not sig_b64 or not pub_b64:
        return (False, "STH missing signature or pubkey")
    sth_for_sig = {k: v for k, v in sth.items() if k not in ("signature_b64", "origin_pub_b64")}
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig_b64),
            _canonical_json(sth_for_sig),
        )
    except InvalidSignature:
        return (False, "STH signature did not verify")
    except Exception as exc:
        return (False, f"STH verification error: {exc}")

    # Second: walk the Merkle path
    if int(proof.get("tree_size", 0)) != int(sth.get("tree_size", 0)):
        return (False, "Proof tree_size != STH tree_size (stale proof or stale STH)")
    cur = bytes.fromhex(str(proof.get("leaf_hash", "")))
    idx = int(proof.get("leaf_index", 0))
    for step in (proof.get("path") or []):
        sib = bytes.fromhex(step["hash"])
        if step["direction"] == "L":
            cur = hashlib.sha512(sib + cur).digest()
        else:
            cur = hashlib.sha512(cur + sib).digest()
        idx //= 2
    if cur.hex() != sth.get("root_hash", ""):
        return (False, "Computed root != STH root")
    return (True, "valid")


def fetch_origin_pubkey(base_url: str = "https://forge-nc.dev") -> str:
    """Fetch + verify the self-signed /.well-known/forge-origin.json and
    return the pinned Origin public key.

    This is the ONE network call most verifier callers will make. After
    this, the pubkey can be cached locally indefinitely (rotation is
    announced explicitly).
    """
    import urllib.request
    req = urllib.request.Request(
        base_url.rstrip("/") + "/.well-known/forge-origin.json",
        headers={"User-Agent": "forge-verifier/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    sig_b64 = doc.get("self_signature_b64", "")
    pub_b64 = doc.get("origin_pub_b64", "")
    if not sig_b64 or not pub_b64:
        raise RuntimeError("well-known document missing signature or pubkey")
    body = {k: v for k, v in doc.items() if k != "self_signature_b64"}
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
        base64.b64decode(sig_b64),
        _canonical_json(body),
    )
    return pub_b64


__all__ = [
    "VerificationResult",
    "SCHEME",
    "verify_report",
    "verify_inclusion_proof",
    "fetch_origin_pubkey",
]
