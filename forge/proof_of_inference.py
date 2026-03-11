"""Proof of Inference — cryptographic proof that a model forward pass ran.

Challenge-response protocol:
  Server sends:  {challenge_id, probe_prompt, expected_category, nonce, expires_at}
  Client runs:   The probe_prompt through the local LLM, classifies the response,
                 hashes it with the nonce, signs the payload with its machine key.
  Client returns: {challenge_id, response_category, response_hash, latency_ms,
                   tokens_generated, passport_id, machine_id, signed_at, signature}
  Server checks:  Signature, latency plausibility, category match, nonce freshness.

This proves computation happened — the "work" is inference, not hashing.
The fleet's capability matrix entries are cryptographically defended.

Machine signing key:
    Generated once on first use.  Stored at ~/.forge/machine_signing_key.pem.
    The Ed25519 public key is registered with the challenge server at activation
    time and accompanies each proof response for server-side verification.

Requires: cryptography>=41.0  (pip install cryptography)
If cryptography is unavailable, challenges are declined gracefully.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Response categories ───────────────────────────────────────────────────────
# The server selects one category per challenge.  The client must classify
# the LLM's response into one of these coarse bins.
RESPONSE_CATEGORIES = {
    "numeric":    lambda t: any(c.isdigit() for c in t[:20]),
    "affirmative": lambda t: t.strip().lower() in ("yes", "true", "correct", "affirmative"),
    "negative":   lambda t: t.strip().lower() in ("no", "false", "incorrect", "refused"),
    "code":       lambda t: any(kw in t for kw in ("def ", "class ", "return ", "import ", "{")),
    "json":       lambda t: t.strip().startswith("{") or t.strip().startswith("["),
    "refusal":    lambda t: any(kw in t.lower() for kw in
                                ("cannot", "can't", "refuse", "won't", "unable",
                                 "i'm sorry", "i apologize")),
    "free_text":  lambda t: True,  # catch-all — always matches
}


def classify_response(text: str, expected_category: str) -> str:
    """Classify *text* into the closest RESPONSE_CATEGORIES key.

    Returns *expected_category* if it matches, otherwise returns the
    first matching category, or "free_text" as fallback.
    """
    # Check expected category first (optimistic path)
    fn = RESPONSE_CATEGORIES.get(expected_category)
    if fn and fn(text):
        return expected_category

    for category, fn in RESPONSE_CATEGORIES.items():
        if category == "free_text":
            continue
        if fn(text):
            return category

    return "free_text"


# ── Machine signing key ───────────────────────────────────────────────────────

def _key_path(config_dir: Path) -> Path:
    return config_dir / "machine_signing_key.pem"


def _load_or_generate_key(config_dir: Path):
    """Load the machine Ed25519 private key, generating it on first call.

    Returns:
        (private_key, public_key_b64: str)
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
        )
    except ImportError:
        raise ImportError(
            "cryptography package required for Proof of Inference. "
            "Install with: pip install cryptography"
        )

    path = _key_path(config_dir)
    if path.exists():
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        raw = path.read_bytes()
        private_key = load_pem_private_key(raw, password=None)
    else:
        private_key = Ed25519PrivateKey.generate()
        pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pem)
        log.info("Machine signing key generated: %s", path)

    pub_bytes = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    pub_b64 = base64.b64encode(pub_bytes).decode()
    return private_key, pub_b64


def get_public_key_b64(config_dir: Path) -> str | None:
    """Return the machine's Ed25519 public key as base64, or None on error."""
    try:
        _, pub_b64 = _load_or_generate_key(config_dir)
        return pub_b64
    except Exception as exc:
        log.debug("Could not load machine signing key: %s", exc)
        return None


def _sign_payload(private_key, payload_bytes: bytes) -> str:
    """Sign *payload_bytes* with *private_key* and return base64 signature."""
    sig_bytes = private_key.sign(payload_bytes)
    return base64.b64encode(sig_bytes).decode()


# ── ProofOfInference ──────────────────────────────────────────────────────────

class ProofOfInference:
    """Execute a server-issued challenge and produce a signed proof.

    Args:
        config_dir: Forge config directory (``~/.forge`` by default).
        machine_id: This machine's fingerprint ID (from BPoS).
        passport_id: This machine's passport ID (from BPoS).
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        machine_id: str = "",
        passport_id: str = "",
    ) -> None:
        self._config_dir  = config_dir or (Path.home() / ".forge")
        self._machine_id  = machine_id
        self._passport_id = passport_id
        self._private_key = None
        self._pub_b64:  str = ""

    def _ensure_key(self) -> bool:
        """Lazy-load the machine signing key.  Returns False if unavailable."""
        if self._private_key is not None:
            return True
        try:
            self._private_key, self._pub_b64 = _load_or_generate_key(
                self._config_dir)
            return True
        except Exception as exc:
            log.warning("Proof of Inference key unavailable: %s", exc)
            return False

    def execute_challenge(self, challenge: dict, llm: Any) -> dict | None:
        """Run a challenge and return a signed proof response.

        Args:
            challenge: Server-issued challenge dict with keys:
                - challenge_id (str)
                - probe_prompt (str)
                - expected_category (str)
                - nonce (str)
                - expires_at (float)
            llm: LLM backend implementing ``LLMBackend`` protocol.

        Returns:
            Signed proof dict ready to POST to the challenge server,
            or None if the challenge is expired, malformed, or signing fails.
        """
        if not self._ensure_key():
            return None

        # Validate challenge
        required = {"challenge_id", "probe_prompt", "expected_category",
                    "nonce", "expires_at"}
        if not required.issubset(challenge):
            log.warning("Challenge missing fields: %s", required - set(challenge))
            return None

        if time.time() > challenge["expires_at"]:
            log.warning("Challenge %s has expired.", challenge["challenge_id"])
            return None

        # Run inference
        from forge.models.base import collect_response

        t_start = time.time()
        messages = [{"role": "user", "content": challenge["probe_prompt"]}]
        try:
            result = collect_response(llm, messages, temperature=0.0)
            response_text = result.get("text", "").strip()
            tokens_generated = result.get("tokens_out", 0)
        except Exception as exc:
            log.warning("Inference failed during PoI challenge: %s", exc)
            return None

        latency_ms = int((time.time() - t_start) * 1000)

        # Classify response
        response_category = classify_response(
            response_text, challenge["expected_category"]
        )

        # Compute nonce-salted response hash
        h = hashlib.sha512(
            (challenge["nonce"] + response_text).encode("utf-8")
        )
        response_hash = h.hexdigest()

        # Build signable payload (deterministic JSON — sorted keys)
        signed_at = time.time()
        payload = {
            "challenge_id":      challenge["challenge_id"],
            "response_category": response_category,
            "response_hash":     response_hash,
            "latency_ms":        latency_ms,
            "tokens_generated":  tokens_generated,
            "passport_id":       self._passport_id,
            "machine_id":        self._machine_id,
            "pub_key_b64":       self._pub_b64,
            "signed_at":         signed_at,
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = _sign_payload(self._private_key, payload_bytes)

        proof = dict(payload)
        proof["signature"] = signature

        log.info(
            "PoI challenge %s complete: category=%s latency=%dms tokens=%d",
            challenge["challenge_id"], response_category,
            latency_ms, tokens_generated,
        )
        return proof

    @property
    def public_key_b64(self) -> str:
        """Return this machine's Ed25519 public key as base64."""
        self._ensure_key()
        return self._pub_b64
