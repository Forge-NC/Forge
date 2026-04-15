"""Origin-derived Ed25519 keys for external (customer-hosted) runners.

An external runner is a Python process that a customer runs inside their
own infrastructure to perform a Forge Certified Audit or Deployment
Assessment against an endpoint that forge-nc.dev cannot reach from the
public internet. The runner needs to produce signed reports that are
traceable to Origin but uses a scoped, time-limited, revocable child key —
never Origin itself.

Key derivation: HKDF-SHA512 from the Origin Ed25519 seed, with a
deterministic info string containing the job ID and issuance timestamp.

  - Deterministic: Origin can re-derive the same child key from just the
    job_id and issued_at timestamp, enabling verification without storing
    child keys anywhere.

  - Verifiable: the child public key, when regenerated from the same seed,
    must match the signature's public key. A forged child key (derived
    from a different seed) will not validate because the derivation inputs
    are embedded in the signed attestation envelope.

  - Scoped: the info string is
    "forge-external-runner-v1|{job_id}|{issued_at}". Each job gets a
    unique key; a leaked key compromises only one assessment.

  - Time-limited: the issuance_ts is part of the info string. The
    orchestrator verifies the current time is within VALIDITY_SECONDS of
    issued_at before accepting a signature. Default validity: 10 days.

  - Revocable: a server-side revocation list of job_ids rejects
    signatures from keys whose jobs were cancelled, even within the
    validity window.

  - Origin-signed envelope: the attestation envelope itself carries an
    Origin signature over its canonical serialization. This prevents any
    party that knows the HKDF scheme from forging arbitrary envelopes
    without access to the Origin seed.

Naming convention for human-readable identifiers: "Origin-External-{job_id}"
(e.g., "Origin-External-205205025" where the number is a job sequence ID).

Proprietary. © Forge NC (Forge Neural Cortex). All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional, Tuple


VALIDITY_SECONDS = 10 * 24 * 60 * 60   # child keys valid for 10 days
EXTERNAL_INFO_PREFIX = b"forge-external-runner-v1"
SCHEME = "forge-external-runner-v1"
KDF_SALT = b"forge-external-runner-salt-v1"

# Valid runner_kind values
RUNNER_KIND_SELF_HOSTED_FCA = "self-hosted-fca"
RUNNER_KIND_DEPLOYMENT_VPC = "deployment-assessment-vpc"
_VALID_RUNNER_KINDS = {RUNNER_KIND_SELF_HOSTED_FCA, RUNNER_KIND_DEPLOYMENT_VPC}


# ── HKDF-SHA512 (RFC 5869) ────────────────────────────────────────────────
# Matches PHP's hash_hkdf('sha512', $ikm, $length, $info, $salt)
# byte-for-byte. See tests/test_external_runner_interop.py for golden
# vectors that are verified in both languages.

def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract step: PRK = HMAC-SHA512(salt, IKM)."""
    if not salt:
        salt = b"\x00" * hashlib.sha512().digest_size
    return hmac.new(salt, ikm, hashlib.sha512).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand step: OKM = T(1) | T(2) | ..."""
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha512).digest()
        okm += t
        counter += 1
    return okm[:length]


def _hkdf_sha512(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """Full HKDF-SHA512: extract then expand to `length` bytes."""
    return _hkdf_expand(_hkdf_extract(salt, ikm), info, length)


# ── Canonical JSON (matches server/includes/assurance_verify.php python_json_encode) ──

def _canonical_json(obj) -> bytes:
    """Deterministic JSON serialization for signing.

    Rules (forge-cjson-v1):
      - Object keys sorted lexicographically
      - UTF-8 bytes
      - Compact separators (',' and ':') — no whitespace
      - ensure_ascii=False so UTF-8 strings stay compact

    This matches the PHP implementation in
    server/includes/forge_crypto_v2.php forge_canonical_json().
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# ── Child key derivation ──────────────────────────────────────────────────

def _build_info(job_id: str, issued_at: int) -> bytes:
    """Construct the canonical info string for HKDF.

    Format: "forge-external-runner-v1|{job_id}|{issued_at}"
    """
    return (
        EXTERNAL_INFO_PREFIX
        + b"|" + job_id.encode("utf-8")
        + b"|" + str(issued_at).encode("ascii")
    )


def derive_external_keypair(
    origin_seed: bytes,
    job_id: str,
    issued_at: Optional[int] = None,
) -> Tuple[object, str, int, str]:
    """Derive a child Ed25519 keypair from the Origin seed.

    Args:
        origin_seed: Raw 32-byte Ed25519 seed of the Origin key.
        job_id:      Assessment job ID.
        issued_at:   Unix timestamp of issuance. Defaults to now.

    Returns:
        (private_key, public_key_b64, issued_at, key_name)
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception as exc:
        raise RuntimeError("cryptography package required for Ed25519") from exc

    if len(origin_seed) < 32:
        raise ValueError("Origin seed must be at least 32 bytes")
    if issued_at is None:
        issued_at = int(time.time())

    salt = KDF_SALT
    info = _build_info(job_id, issued_at)

    child_seed = _hkdf_sha512(origin_seed[:32], salt, info, length=32)
    child_priv = Ed25519PrivateKey.from_private_bytes(child_seed)

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    pub_bytes = child_priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")

    key_name = f"Origin-External-{job_id}"
    return child_priv, pub_b64, issued_at, key_name


# ── Attestation envelope ──────────────────────────────────────────────────

def build_attestation_envelope(
    origin_seed: bytes,
    job_id: str,
    order_id: str,
    passport_id: str,
    runner_kind: str,
    target_hash_hex: str,
    scenario_pack_version: int,
    scenario_pack_hash_hex: str,
    child_pub_b64: str,
    origin_pub_b64: str,
    issued_at: int,
    validity_seconds: int = VALIDITY_SECONDS,
) -> dict:
    """Build and Origin-sign the attestation envelope for an external runner job.

    The envelope proves:
      - Origin authorized this specific job (origin_envelope_sig)
      - Which job the child key was derived for (job_id, issued_at)
      - What target the key is scoped to (target_hash, runner_kind)
      - What customer order it belongs to (order_id, passport_id)
      - What scenario pack will run (scenario_pack_version, scenario_pack_hash)
      - Validity window (expires_at)
      - The public keys (child + origin) needed to verify downstream signatures

    Verifiers re-derive the expected child pubkey from origin_pub + job_id
    + issued_at; if it matches the envelope's child_pub_b64 AND the
    origin_envelope_sig verifies AND the report signature verifies against
    the child pubkey, the chain of trust is intact.
    """
    if runner_kind not in _VALID_RUNNER_KINDS:
        raise ValueError(
            f"runner_kind must be one of {sorted(_VALID_RUNNER_KINDS)}, got {runner_kind!r}"
        )

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception as exc:
        raise RuntimeError("cryptography package required for Ed25519") from exc

    envelope = {
        "scheme": SCHEME,
        "job_id": job_id,
        "order_id": order_id,
        "passport_id": passport_id,
        "runner_kind": runner_kind,
        "target_hash": target_hash_hex,
        "scenario_pack_version": scenario_pack_version,
        "scenario_pack_hash": scenario_pack_hash_hex,
        "issued_at": issued_at,
        "expires_at": issued_at + validity_seconds,
        "child_key_name": f"Origin-External-{job_id}",
        "child_pub_b64": child_pub_b64,
        "origin_pub_b64": origin_pub_b64,
        "kdf": "HKDF-SHA512",
        "kdf_salt": KDF_SALT.decode("ascii"),
        "kdf_info_prefix": SCHEME,
    }

    # Sign the canonical JSON of the envelope (excluding the signature field)
    origin_priv = Ed25519PrivateKey.from_private_bytes(origin_seed[:32])
    to_sign = _canonical_json(envelope)
    sig = origin_priv.sign(to_sign)
    envelope["origin_envelope_sig"] = base64.b64encode(sig).decode("ascii")

    return envelope


# ── Verification (run on the server when external report lands) ──────────

def verify_external_attestation(
    envelope: dict,
    origin_seed: bytes,
    revocation_list: Optional[set] = None,
    now_ts: Optional[int] = None,
) -> Tuple[bool, str]:
    """Verify an external runner attestation envelope.

    Checks (ALL must pass):
      1. Scheme matches.
      2. Not expired, not issued in the future (60s clock skew tolerance).
      3. Job ID not revoked.
      4. Origin envelope signature verifies against origin_pub_b64.
      5. Re-derived child pubkey from (origin_seed, job_id, issued_at) matches
         the envelope's declared child_pub_b64.

    Returns (is_valid, reason).
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey, Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
    except Exception as exc:
        return (False, f"cryptography package required: {exc}")

    if not isinstance(envelope, dict):
        return (False, "envelope is not a dict")
    if envelope.get("scheme") != SCHEME:
        return (False, f"unsupported scheme: {envelope.get('scheme')}")

    job_id = envelope.get("job_id", "")
    try:
        issued_at = int(envelope.get("issued_at", 0))
        expires_at = int(envelope.get("expires_at", 0))
    except (TypeError, ValueError):
        return (False, "envelope issued_at/expires_at are not integers")

    claimed_child_pub = envelope.get("child_pub_b64", "")
    origin_pub_b64 = envelope.get("origin_pub_b64", "")
    origin_sig_b64 = envelope.get("origin_envelope_sig", "")

    if not job_id or not issued_at or not claimed_child_pub or not origin_pub_b64:
        return (False, "envelope missing required fields")

    if revocation_list and job_id in revocation_list:
        return (False, f"job {job_id} is on the revocation list")

    if now_ts is None:
        now_ts = int(time.time())
    if now_ts > expires_at:
        return (False, f"envelope expired at {expires_at} (now {now_ts})")
    if now_ts < issued_at - 60:
        return (False, f"envelope issued in the future ({issued_at} vs {now_ts})")

    # 4. Verify Origin signature over the envelope (excluding the sig field)
    if not origin_sig_b64:
        return (False, "envelope missing origin_envelope_sig")
    try:
        env_for_sig = {k: v for k, v in envelope.items() if k != "origin_envelope_sig"}
        to_verify = _canonical_json(env_for_sig)
        origin_pub_bytes = base64.b64decode(origin_pub_b64)
        origin_pub = Ed25519PublicKey.from_public_bytes(origin_pub_bytes)
        origin_pub.verify(base64.b64decode(origin_sig_b64), to_verify)
    except InvalidSignature:
        return (False, "origin_envelope_sig is invalid")
    except Exception as exc:
        return (False, f"origin signature verification error: {exc}")

    # 5. Re-derive the child pubkey from the Origin seed and compare
    try:
        _, derived_pub_b64, _, _ = derive_external_keypair(
            origin_seed, job_id, issued_at=issued_at
        )
    except Exception as exc:
        return (False, f"key re-derivation failed: {exc}")

    if derived_pub_b64 != claimed_child_pub:
        return (False, "derived child pubkey does not match envelope")

    return (True, "valid")


# ── Revocation list persistence ───────────────────────────────────────────

def load_revocation_list(config_dir: Path) -> set:
    """Load the set of revoked job IDs from disk. Missing file → empty set."""
    path = config_dir / "external_revocations.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("revoked_jobs", []))
    except Exception:
        return set()


def revoke_external_job(
    config_dir: Path,
    job_id: str,
    reason: str = "",
    approved_by: str = "",
) -> None:
    """Add a job ID to the revocation list.

    Signatures from its child key will be rejected immediately even if the
    validity window hasn't expired. Requires Origin-role approval in the
    server-side UI flow (the two-person approval pattern); the
    `approved_by` field records who clicked Approve.
    """
    path = config_dir / "external_revocations.json"
    data = {"revoked_jobs": [], "entries": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if job_id not in data.get("revoked_jobs", []):
        data.setdefault("revoked_jobs", []).append(job_id)
        data.setdefault("entries", []).append({
            "job_id": job_id,
            "revoked_at": int(time.time()),
            "reason": reason,
            "approved_by": approved_by,
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )


# ── Helpers for runners/orchestrators ────────────────────────────────────

def compute_target_hash(endpoint_url: str, model_id: str) -> str:
    """Compute the target_hash field used in the envelope.

    Binds the child key to a specific audit target so a leaked bundle can't
    be pointed at a different model or endpoint.
    """
    h = hashlib.sha512()
    h.update(endpoint_url.encode("utf-8"))
    h.update(b":")
    h.update(model_id.encode("utf-8"))
    return h.hexdigest()


__all__ = [
    "VALIDITY_SECONDS",
    "SCHEME",
    "KDF_SALT",
    "RUNNER_KIND_SELF_HOSTED_FCA",
    "RUNNER_KIND_DEPLOYMENT_VPC",
    "derive_external_keypair",
    "build_attestation_envelope",
    "verify_external_attestation",
    "load_revocation_list",
    "revoke_external_job",
    "compute_target_hash",
]
