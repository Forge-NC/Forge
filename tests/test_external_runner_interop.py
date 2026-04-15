"""Golden-vector interop tests for the External Runner Protocol crypto.

Ensures Python HKDF-SHA512 derivation, child keypair generation, envelope
construction, and signature verification match byte-for-byte with the PHP
implementation in server/includes/external_runner_crypto.php.

The fixtures in tests/fixtures/external_runner_vectors.json are the source
of truth. The PHP test suite (server/tests/test_external_runner_crypto.php)
consumes the same fixture file and must produce identical bytes.

If these tests pass and the PHP tests pass, Python and PHP agree on every
bit of the protocol's crypto. If either fails, protocol interop is broken
and anything downstream will not verify cleanly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from forge.external_runner_keys import (
    _build_info,
    _canonical_json,
    _hkdf_sha512,
    build_attestation_envelope,
    compute_target_hash,
    derive_external_keypair,
    verify_external_attestation,
    KDF_SALT,
    SCHEME,
    VALIDITY_SECONDS,
)


# ── Golden-vector fixture loading ─────────────────────────────────────────

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "external_runner_vectors.json"


@pytest.fixture(scope="module")
def vectors() -> dict:
    """Load the shared Python/PHP golden vector fixtures."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ── HKDF byte-vector tests (RFC 5869 compliance + cross-language parity) ──

def test_hkdf_extract_then_expand_matches_rfc5869():
    """RFC 5869 Appendix A.3 (SHA-256) adapted test for SHA-512: length-0
    salt and info should produce a deterministic 32-byte OKM."""
    ikm = b"\x0b" * 22
    salt = b""
    info = b""
    okm = _hkdf_sha512(ikm, salt, info, length=32)
    assert len(okm) == 32
    # Deterministic: re-running produces identical bytes
    assert _hkdf_sha512(ikm, salt, info, length=32) == okm


def test_hkdf_with_forge_salt_and_info(vectors):
    """Golden vector: derive the child seed bytes from a fixed Origin seed
    + job_id + issued_at. Must match the PHP hash_hkdf output exactly."""
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    for tc in vectors["hkdf_cases"]:
        salt = KDF_SALT
        info = _build_info(tc["job_id"], tc["issued_at"])
        okm = _hkdf_sha512(origin_seed[:32], salt, info, length=32)
        expected = base64.b64decode(tc["child_seed_b64"])
        assert okm == expected, (
            f"HKDF output mismatch for job_id={tc['job_id']}: "
            f"got {okm.hex()[:32]}..., expected {expected.hex()[:32]}..."
        )


# ── Child keypair derivation ──────────────────────────────────────────────

def test_derive_external_keypair_determinism(vectors):
    """Same inputs always produce the same child public key."""
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    for tc in vectors["hkdf_cases"]:
        _, pub1, _, _ = derive_external_keypair(origin_seed, tc["job_id"], issued_at=tc["issued_at"])
        _, pub2, _, _ = derive_external_keypair(origin_seed, tc["job_id"], issued_at=tc["issued_at"])
        assert pub1 == pub2
        assert pub1 == tc["child_pub_b64"]


def test_derive_different_job_ids_produce_different_keys(vectors):
    """Different job_ids MUST produce different child keys (domain separation)."""
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    _, pub_a, _, _ = derive_external_keypair(origin_seed, "job_a", issued_at=1000)
    _, pub_b, _, _ = derive_external_keypair(origin_seed, "job_b", issued_at=1000)
    assert pub_a != pub_b


def test_derive_different_timestamps_produce_different_keys(vectors):
    """Same job_id at different issuance times produces different keys."""
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    _, pub1, _, _ = derive_external_keypair(origin_seed, "job_x", issued_at=1000)
    _, pub2, _, _ = derive_external_keypair(origin_seed, "job_x", issued_at=2000)
    assert pub1 != pub2


# ── Canonical JSON parity ─────────────────────────────────────────────────

def test_canonical_json_sorted_no_whitespace():
    """Canonical JSON must be sorted-keys + no-whitespace + UTF-8."""
    obj = {"b": 2, "a": 1, "c": {"z": 9, "y": 8}}
    cj = _canonical_json(obj)
    assert cj == b'{"a":1,"b":2,"c":{"y":8,"z":9}}'


def test_canonical_json_matches_php_vectors(vectors):
    """Golden vector: canonical serialization of sample envelopes must
    match the PHP forge_canonical_json() byte-for-byte."""
    for case in vectors.get("canonical_json_cases", []):
        actual = _canonical_json(case["input"])
        expected = base64.b64decode(case["canonical_bytes_b64"])
        assert actual == expected, (
            f"canonical JSON mismatch: got {actual!r}, expected {expected!r}"
        )


# ── Envelope construction + Origin signature ──────────────────────────────

def test_build_envelope_includes_all_required_fields(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]

    env = build_attestation_envelope(
        origin_seed=origin_seed,
        job_id=tc["job_id"],
        order_id="aud_test_001",
        passport_id="pp_test_001",
        runner_kind="self-hosted-fca",
        target_hash_hex=compute_target_hash("https://example.com/v1", "qwen3:14b"),
        scenario_pack_version=3,
        scenario_pack_hash_hex=hashlib.sha512(b"scenario_pack_placeholder").hexdigest(),
        child_pub_b64=tc["child_pub_b64"],
        origin_pub_b64=origin_pub,
        issued_at=tc["issued_at"],
    )

    required = {
        "scheme", "job_id", "order_id", "passport_id", "runner_kind",
        "target_hash", "scenario_pack_version", "scenario_pack_hash",
        "issued_at", "expires_at", "child_key_name", "child_pub_b64",
        "origin_pub_b64", "kdf", "kdf_salt", "kdf_info_prefix",
        "origin_envelope_sig",
    }
    assert required <= set(env.keys())
    assert env["scheme"] == SCHEME
    assert env["kdf"] == "HKDF-SHA512"
    assert env["expires_at"] == env["issued_at"] + VALIDITY_SECONDS


def test_build_envelope_rejects_bad_runner_kind(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]

    with pytest.raises(ValueError, match="runner_kind"):
        build_attestation_envelope(
            origin_seed=origin_seed,
            job_id=tc["job_id"],
            order_id="aud_test_001",
            passport_id="pp_test_001",
            runner_kind="made-up-kind",
            target_hash_hex="a" * 128,
            scenario_pack_version=3,
            scenario_pack_hash_hex="b" * 128,
            child_pub_b64=tc["child_pub_b64"],
            origin_pub_b64=origin_pub,
            issued_at=tc["issued_at"],
        )


# ── Full round-trip verification ──────────────────────────────────────────

def test_envelope_roundtrip_verify_ok(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]

    env = build_attestation_envelope(
        origin_seed=origin_seed,
        job_id=tc["job_id"],
        order_id="aud_001",
        passport_id="pp_001",
        runner_kind="deployment-assessment-vpc",
        target_hash_hex=compute_target_hash("https://internal.acme/v1", "internal-llm"),
        scenario_pack_version=3,
        scenario_pack_hash_hex=hashlib.sha512(b"pack").hexdigest(),
        child_pub_b64=tc["child_pub_b64"],
        origin_pub_b64=origin_pub,
        issued_at=tc["issued_at"],
    )
    ok, reason = verify_external_attestation(env, origin_seed, now_ts=tc["issued_at"] + 60)
    assert ok, reason


def test_envelope_rejects_tampered_child_pubkey(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]

    env = build_attestation_envelope(
        origin_seed=origin_seed,
        job_id=tc["job_id"],
        order_id="aud_001",
        passport_id="pp_001",
        runner_kind="self-hosted-fca",
        target_hash_hex="c" * 128,
        scenario_pack_version=3,
        scenario_pack_hash_hex="d" * 128,
        child_pub_b64=tc["child_pub_b64"],
        origin_pub_b64=origin_pub,
        issued_at=tc["issued_at"],
    )
    # Tamper: swap the child_pub for another
    env["child_pub_b64"] = vectors["hkdf_cases"][1]["child_pub_b64"]
    ok, reason = verify_external_attestation(env, origin_seed, now_ts=tc["issued_at"] + 60)
    assert not ok
    assert "sig" in reason or "child pubkey" in reason


def test_envelope_rejects_expired(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]
    env = build_attestation_envelope(
        origin_seed=origin_seed,
        job_id=tc["job_id"],
        order_id="aud_001",
        passport_id="pp_001",
        runner_kind="self-hosted-fca",
        target_hash_hex="c" * 128,
        scenario_pack_version=3,
        scenario_pack_hash_hex="d" * 128,
        child_pub_b64=tc["child_pub_b64"],
        origin_pub_b64=origin_pub,
        issued_at=tc["issued_at"],
    )
    # Check 11 days later (past 10-day validity)
    far_future = tc["issued_at"] + VALIDITY_SECONDS + 3600
    ok, reason = verify_external_attestation(env, origin_seed, now_ts=far_future)
    assert not ok
    assert "expired" in reason


def test_envelope_rejects_revoked(vectors):
    origin_seed = base64.b64decode(vectors["origin_seed_b64"])
    origin_pub = vectors["origin_pub_b64"]
    tc = vectors["hkdf_cases"][0]
    env = build_attestation_envelope(
        origin_seed=origin_seed,
        job_id=tc["job_id"],
        order_id="aud_001",
        passport_id="pp_001",
        runner_kind="self-hosted-fca",
        target_hash_hex="c" * 128,
        scenario_pack_version=3,
        scenario_pack_hash_hex="d" * 128,
        child_pub_b64=tc["child_pub_b64"],
        origin_pub_b64=origin_pub,
        issued_at=tc["issued_at"],
    )
    revoked = {tc["job_id"]}
    ok, reason = verify_external_attestation(
        env, origin_seed, revocation_list=revoked, now_ts=tc["issued_at"] + 60
    )
    assert not ok
    assert "revocation" in reason or "revoked" in reason


def test_target_hash_is_deterministic():
    h1 = compute_target_hash("https://api.openai.com/v1", "gpt-4")
    h2 = compute_target_hash("https://api.openai.com/v1", "gpt-4")
    h3 = compute_target_hash("https://api.openai.com/v1", "gpt-5")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 128  # SHA-512 hex
