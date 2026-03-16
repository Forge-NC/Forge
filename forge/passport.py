"""Behavioral Proof of Stake (BPoS) — Novel licensing architecture.

The key insight: a pirated copy is objectively worse software because it
lacks the accumulated behavioral genome. A fresh install starts with
generic defaults; a legitimate long-running instance has been tuned to
its specific model, hardware, and usage patterns.

Five layers:
  1. Chain of Being — Ed25519 provenance chain as identity proof
  2. Forge Genome — accumulated intelligence (AMI catalogs, continuity
     baselines, threat hit rates, model profiles)
  3. Symbiotic Capability Scaling — features genuinely improve with usage
  4. Ambient Verification — behavioral fingerprinting for license identity
  5. Passport — Ed25519 signed token, account-bound, fully offline after
     one-time activation

Offline operation
-----------------
After the initial activation (requires internet once), Forge is fully
self-contained.  All verification uses the embedded Origin public key —
no phone-home, no recurring checks.  The genome is encrypted with a key
derived from the passport's origin_signature + machine_id, so it is
unreadable on any other machine or with any forged passport.

Anti-forgery
------------
The Origin Ed25519 private key lives only on the issuer server.
The public key is embedded here.  You can read it, you cannot forge with
it.  Possessing the public key is like knowing a lock's shape — you still
can't open it without the key.

Tier definitions are server-configurable via tiers_config.json.
Client fetches tier info from server on activation.
Fallback defaults used when offline.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Tier definitions ──
# Fallback defaults used when offline. Server tiers take precedence.

_FALLBACK_TIERS = {
    "community": {
        "label": "Community",
        "price_display": "Free",
        "price_cents": 0,
        "seats": 1,
        "genome_persistence": False,
        "genome_sync": False,
        "enterprise_mode": False,
        "fleet_analytics": False,
        "benchmark_suite": True,
        "threat_intel": True,
        "auto_commit": False,
        "shipwright": False,
        "compliance_scenarios": False,
        "priority_support": False,
    },
    "pro": {
        "label": "Pro",
        "price_display": "$199 one-time",
        "price_cents": 19900,
        "seats": 3,
        "genome_persistence": True,
        "genome_sync": True,
        "enterprise_mode": False,
        "fleet_analytics": False,
        "benchmark_suite": True,
        "threat_intel": True,
        "auto_commit": True,
        "shipwright": True,
        "compliance_scenarios": False,
        "priority_support": False,
    },
    "power": {
        "label": "Power",
        "price_display": "$999 one-time",
        "price_cents": 99900,
        "seats": 10,
        "genome_persistence": True,
        "genome_sync": True,
        "enterprise_mode": True,
        "fleet_analytics": True,
        "benchmark_suite": True,
        "threat_intel": True,
        "auto_commit": True,
        "shipwright": True,
        "compliance_scenarios": True,
        "priority_support": True,
    },
    "origin": {
        "label": "Origin",
        "price_display": "Creator",
        "price_cents": 0,
        "seats": -1,              # Unlimited
        "genome_persistence": True,
        "genome_sync": True,
        "enterprise_mode": True,
        "fleet_analytics": True,
        "benchmark_suite": True,
        "threat_intel": True,
        "auto_commit": True,
        "shipwright": True,
        "compliance_scenarios": True,
        "priority_support": True,
        "origin_role": True,      # Root of the BPoS chain of being
    },
}

# Cache for server-fetched tiers
_cached_tiers: Optional[dict] = None

PASSPORT_API_URL = "https://forge-nc.dev/passport_api.php"


def get_tiers() -> dict:
    """Get tier definitions. Tries server first, falls back to defaults.

    Server-returned tiers are merged onto _FALLBACK_TIERS so any keys
    the server doesn't define still have sane defaults.
    """
    global _cached_tiers
    if _cached_tiers is not None:
        return _cached_tiers
    try:
        import urllib.request
        url = f"{PASSPORT_API_URL}?action=tiers"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and len(data) > 0:
                # Merge: fallback defaults first, server overrides on top
                merged = {}
                for tier_name, fallback_cfg in _FALLBACK_TIERS.items():
                    server_cfg = data.get(tier_name, {})
                    merged[tier_name] = {**fallback_cfg, **server_cfg}
                # Include any server-only tiers (e.g. "origin")
                for tier_name, server_cfg in data.items():
                    if tier_name not in merged:
                        merged[tier_name] = server_cfg
                _cached_tiers = merged
                return _cached_tiers
    except Exception:
        log.debug("Tier config fetch from server failed", exc_info=True)
    return _FALLBACK_TIERS


# Backward compat: TIERS still works as a module-level reference
TIERS = _FALLBACK_TIERS


@dataclass
class Passport:
    """Account-bound license token."""
    account_id: str          # Unique account identifier
    tier: str                # "community", "pro", "power"
    issued_at: float         # Timestamp
    expires_at: float        # 0 = never (one-time), else expiry timestamp
    activations: list[str] = field(default_factory=list)  # machine IDs
    max_activations: int = 1
    signature: str = ""      # HMAC-SHA512 of passport data
    # v2 fields for Origin/Master/Puppet hierarchy
    role: str = ""           # "origin", "master", or "puppet"
    passport_id: str = ""    # Unique passport identifier
    origin_signature: str = ""  # Ed25519 signature (base64) by server Origin key
    master_id: str = ""      # Master's machine_id
    seat_count: int = 0      # Total seats (Masters only)
    parent_passport_id: str = ""  # For Puppets, links to Master's passport


@dataclass
class GenomeSnapshot:
    """Point-in-time capture of accumulated intelligence."""
    session_count: int = 0
    total_turns: int = 0
    ami_failure_catalog_size: int = 0
    ami_model_profiles: int = 0
    ami_average_quality: float = 0.0
    continuity_baseline_grade: float = 0.0
    threat_scans_total: int = 0
    threat_hits_total: int = 0
    reliability_score: float = 0.0
    tool_call_total: int = 0
    unique_models_used: int = 0
    timestamp: float = 0.0
    # ── Depth fields (Phase 2) ──
    quality_trend: list = field(default_factory=list)       # Last 50 quality scores
    per_model_quality: dict = field(default_factory=dict)   # model -> avg_quality
    ami_routing_accuracy: float = 0.0                       # Retry success rate
    continuity_recovery_rate: float = 0.0                   # Recovery success fraction
    threat_pattern_distribution: dict = field(default_factory=dict)  # category -> count
    tool_success_rate: float = 0.0                          # Successful tool calls fraction
    benchmark_pass_rate: float = 0.0                        # Cross-session benchmark performance
    models_tested: list = field(default_factory=list)       # All model names ever tested
    xp_total: int = 0                                       # Current XP total from gamification
    xp_level: int = 1                                       # Current level


@dataclass
class BehavioralFingerprint:
    """Behavioral signature for ambient identity verification."""
    tool_frequency: dict = field(default_factory=dict)   # tool_name -> call_count
    command_frequency: dict = field(default_factory=dict) # /command -> use_count
    avg_session_duration: float = 0.0
    avg_turns_per_session: float = 0.0
    primary_model: str = ""
    typical_safety_level: int = 1
    theme_preference: str = ""


class BPoS:
    """Behavioral Proof of Stake license manager."""

    # Ed25519 public key — embedded in the client for offline verification.
    # The corresponding private key lives ONLY on the issuer server and is
    # never distributed.  Knowing this public key is useless for forging.
    _ORIGIN_PUBLIC_KEY_B64 = "1QTiJehHwElx8BQ1jWxBQg5iOr4D6wb80JG3oC3hLhU="

    # Fields covered by the Ed25519 signature — defines what the server
    # commits to.  activations is excluded (grows as users activate machines).
    _SIGNED_FIELDS = (
        "passport_id", "account_id", "tier",
        "issued_at", "expires_at", "max_activations",
        "role", "seat_count", "parent_passport_id",
    )

    def __init__(self, data_dir: Path = None, machine_id: str = ""):
        self._data_dir = data_dir or (Path.home() / ".forge")
        self._machine_id = machine_id
        self._passport_path = self._data_dir / "passport.json"
        self._genome_path = self._data_dir / "genome.json"
        self._fingerprint_path = self._data_dir / "fingerprint.json"

        self._passport: Optional[Passport] = None
        self._genome = GenomeSnapshot()
        self._fingerprint = BehavioralFingerprint()
        self._session_start = time.time()

        self._load()

    # ── Tier checking ──

    @property
    def tier(self) -> str:
        if self._passport:
            return self._passport.tier
        return "community"

    @property
    def tier_config(self) -> dict:
        tiers = get_tiers()
        return tiers.get(self.tier, tiers.get("community", {}))

    def is_feature_allowed(self, feature: str) -> bool:
        """Check if a feature is allowed for the current tier."""
        return self.tier_config.get(feature, False)

    def is_activated(self) -> bool:
        """Check if this machine is activated under the current passport."""
        if not self._passport:
            return True  # Community tier — always active
        if self._passport.expires_at > 0 and time.time() > self._passport.expires_at:
            return False  # Expired
        return self._machine_id in self._passport.activations

    # ── Passport management ──

    def activate(self, passport_data: dict) -> tuple[bool, str]:
        """Activate a passport on this machine.

        Verifies the Ed25519 origin_signature before accepting any paid tier.
        Community tier requires no signature.

        Returns (success, message).
        """
        # Strip the local-integrity field before reconstructing
        passport_data.pop("signature", None)

        passport = Passport(
            account_id=passport_data.get("account_id", ""),
            tier=passport_data.get("tier", "community"),
            issued_at=passport_data.get("issued_at", 0),
            expires_at=passport_data.get("expires_at", 0),
            activations=passport_data.get("activations", []),
            max_activations=passport_data.get("max_activations", 1),
            origin_signature=passport_data.get("origin_signature", ""),
            role=passport_data.get("role", ""),
            passport_id=passport_data.get("passport_id", ""),
            master_id=passport_data.get("master_id", ""),
            seat_count=passport_data.get("seat_count", 0),
            parent_passport_id=passport_data.get("parent_passport_id", ""),
        )

        # Require valid Ed25519 signature for all non-community tiers
        if passport.tier != "community":
            ok, reason = self._verify_origin_signature(passport)
            if not ok:
                return False, f"Passport signature invalid: {reason}"

        # Check expiry
        if passport.expires_at > 0 and time.time() > passport.expires_at:
            return False, "Passport has expired"

        # Check activation limit
        if (self._machine_id not in passport.activations and
                len(passport.activations) >= passport.max_activations):
            return False, (
                f"Activation limit reached ({passport.max_activations}). "
                f"Deactivate another machine first."
            )

        # Add this machine
        if self._machine_id not in passport.activations:
            passport.activations.append(self._machine_id)

        self._passport = passport
        self._save_passport()

        tiers = get_tiers()
        tier_info = tiers.get(passport.tier, {})
        return True, f"Activated {tier_info.get('label', passport.tier)} tier on this machine"

    def deactivate(self) -> tuple[bool, str]:
        """Deactivate this machine."""
        if not self._passport:
            return False, "No passport active"
        if self._machine_id in self._passport.activations:
            self._passport.activations.remove(self._machine_id)
            self._save_passport()
        return True, "Machine deactivated"

    @classmethod
    def _signing_payload(cls, passport: "Passport") -> bytes:
        """Canonical bytes that the Origin server signs.

        Only covers immutable grant fields — not activations (which grow
        as machines are added) or the signature fields themselves.

        Canonical rules (must match signing_payload() in passport_api.php):
          - Only _SIGNED_FIELDS, sorted by key
          - Whole-number floats cast to int (e.g. issued_at from time.time())
          - JSON with no escaped slashes (Python default)
        """
        d = asdict(passport)
        payload = {}
        for k in cls._SIGNED_FIELDS:
            v = d.get(k, "")
            # Normalize: whole-number floats → int to match PHP's time() output
            if isinstance(v, float) and v == int(v):
                v = int(v)
            payload[k] = v
        return json.dumps(payload, sort_keys=True).encode()

    @classmethod
    def _verify_origin_signature(cls, passport: "Passport") -> tuple[bool, str]:
        """Verify the Ed25519 origin_signature on a passport.

        Returns (ok: bool, reason: str).
        Works fully offline — uses only the embedded public key.
        """
        if not passport.origin_signature:
            return False, "No origin_signature present"

        try:
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            from cryptography.exceptions import InvalidSignature

            pub_bytes = base64.b64decode(cls._ORIGIN_PUBLIC_KEY_B64)
            pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = base64.b64decode(passport.origin_signature)
            payload = cls._signing_payload(passport)

            try:
                pub_key.verify(sig_bytes, payload)
                return True, ""
            except InvalidSignature:
                return False, "Signature does not match passport contents"

        except ImportError:
            # cryptography package not installed — REJECT passport
            log.warning(
                "cryptography package not available; passport signature "
                "cannot be verified.  Install with: pip install cryptography"
            )
            return False, "cryptography package required for signature verification"
        except Exception as exc:
            return False, f"Verification error: {exc}"

    # ── Genome (accumulated intelligence) ──

    def collect_genome(self, engine) -> GenomeSnapshot:
        """Collect current genome state from engine subsystems.

        This is the behavioral data that makes a long-running instance
        objectively better than a fresh install.
        """
        snapshot = GenomeSnapshot(timestamp=time.time())

        # AMI failure catalog + routing accuracy
        if hasattr(engine, 'ami') and engine.ami:
            ami_audit = engine.ami.to_audit_dict()
            snapshot.ami_failure_catalog_size = len(
                ami_audit.get("failure_catalog", {}))
            snapshot.ami_model_profiles = len(
                ami_audit.get("model_capabilities", {}))
            snapshot.ami_average_quality = ami_audit.get("average_quality", 0.0)
            # AMI routing accuracy: retries succeeded / retries triggered
            stats = ami_audit.get("stats", {})
            triggered = stats.get("retries_triggered", 0)
            succeeded = stats.get("retries_succeeded", 0)
            if triggered > 0:
                snapshot.ami_routing_accuracy = succeeded / triggered
            # Per-model quality from capabilities
            for model_name, caps in ami_audit.get("model_capabilities", {}).items():
                if isinstance(caps, dict):
                    q = caps.get("avg_tool_compliance", 0.5)
                    snapshot.per_model_quality[model_name] = q
            # Quality trend from turn history
            snapshot.quality_trend = [
                t.get("quality_score", 0)
                for t in ami_audit.get("turn_history", [])[-50:]
                if isinstance(t, dict)
            ]
            # Models tested
            snapshot.models_tested = list(
                ami_audit.get("model_capabilities", {}).keys())

        # Continuity baseline + recovery rate
        if hasattr(engine, 'continuity') and engine.continuity:
            cont_audit = engine.continuity.to_audit_dict()
            snapshot.continuity_baseline_grade = cont_audit.get(
                "current_score", 0.0)
            attempts = cont_audit.get("recovery_attempts", 0)
            if attempts > 0:
                # Estimate recovery success from grade improvement
                history = cont_audit.get("history", [])
                recoveries = sum(
                    1 for h in history if isinstance(h, dict) and
                    h.get("recovery_triggered"))
                improvements = 0
                for i, h in enumerate(history):
                    if isinstance(h, dict) and h.get("recovery_triggered"):
                        if i + 1 < len(history):
                            next_h = history[i + 1]
                            if isinstance(next_h, dict) and \
                               next_h.get("score", 0) > h.get("score", 0):
                                improvements += 1
                snapshot.continuity_recovery_rate = (
                    improvements / max(1, recoveries))

        # Threat detection stats + pattern distribution
        if hasattr(engine, 'crucible') and engine.crucible:
            cruc_audit = engine.crucible.to_audit_dict()
            snapshot.threat_scans_total = cruc_audit.get("total_scans", 0)
            snapshot.threat_hits_total = cruc_audit.get("threats_found", 0)
            # Pattern distribution from threat intel
            if hasattr(engine, 'threat_intel') and engine.threat_intel:
                try:
                    det_stats = engine.threat_intel.get_detection_stats()
                    snapshot.threat_pattern_distribution = dict(
                        det_stats.get("by_category", {}))
                except Exception:
                    log.debug("Threat pattern distribution collection failed", exc_info=True)

        # Reliability score
        if hasattr(engine, 'reliability') and engine.reliability:
            rel_audit = engine.reliability.to_audit_dict()
            snapshot.reliability_score = rel_audit.get("composite_score", 0.0)

        # Session stats + tool success rate
        if hasattr(engine, 'stats') and engine.stats:
            stats_audit = engine.stats.to_audit_dict()
            snapshot.total_turns = stats_audit.get("session_turns", 0)
            tool_analytics = stats_audit.get("tool_analytics", {})
            total_calls = sum(tool_analytics.values()) if isinstance(
                tool_analytics, dict) else 0
            if total_calls > 0:
                # Approximate: if forensics tracks tool failures
                if hasattr(engine, 'forensics') and engine.forensics:
                    for_audit = engine.forensics.to_audit_dict()
                    errors = for_audit.get("error_count", 0)
                    snapshot.tool_success_rate = max(
                        0, 1.0 - errors / max(1, total_calls))
                else:
                    snapshot.tool_success_rate = 1.0

        return snapshot

    def update_genome(self, snapshot: GenomeSnapshot):
        """Merge a new snapshot into the running genome."""
        if not self.is_feature_allowed("genome_persistence"):
            return  # Community tier — genome resets each session

        self._genome.session_count += 1
        self._genome.total_turns += snapshot.total_turns
        self._genome.ami_failure_catalog_size = max(
            self._genome.ami_failure_catalog_size,
            snapshot.ami_failure_catalog_size,
        )
        self._genome.ami_model_profiles = max(
            self._genome.ami_model_profiles,
            snapshot.ami_model_profiles,
        )
        # Exponential moving average for quality metrics
        alpha = 0.3
        if snapshot.ami_average_quality > 0:
            self._genome.ami_average_quality = (
                alpha * snapshot.ami_average_quality
                + (1 - alpha) * self._genome.ami_average_quality
            )
        self._genome.continuity_baseline_grade = (
            alpha * snapshot.continuity_baseline_grade
            + (1 - alpha) * self._genome.continuity_baseline_grade
        )
        self._genome.threat_scans_total += snapshot.threat_scans_total
        self._genome.threat_hits_total += snapshot.threat_hits_total
        if snapshot.reliability_score > 0:
            self._genome.reliability_score = (
                alpha * snapshot.reliability_score
                + (1 - alpha) * self._genome.reliability_score
            )
        self._genome.tool_call_total += snapshot.total_turns
        self._genome.timestamp = time.time()

        # ── Depth field merging ──

        # Quality trend: append session average, keep last 50
        if snapshot.quality_trend:
            avg_q = sum(snapshot.quality_trend) / len(snapshot.quality_trend)
            self._genome.quality_trend.append(round(avg_q, 3))
        elif snapshot.ami_average_quality > 0:
            self._genome.quality_trend.append(
                round(snapshot.ami_average_quality, 3))
        self._genome.quality_trend = self._genome.quality_trend[-50:]

        # Per-model quality: EMA merge
        for model, quality in snapshot.per_model_quality.items():
            existing = self._genome.per_model_quality.get(model, 0.5)
            self._genome.per_model_quality[model] = round(
                alpha * quality + (1 - alpha) * existing, 3)

        # AMI routing accuracy: EMA
        if snapshot.ami_routing_accuracy > 0:
            self._genome.ami_routing_accuracy = round(
                alpha * snapshot.ami_routing_accuracy
                + (1 - alpha) * self._genome.ami_routing_accuracy, 3)

        # Continuity recovery rate: EMA
        if snapshot.continuity_recovery_rate > 0:
            self._genome.continuity_recovery_rate = round(
                alpha * snapshot.continuity_recovery_rate
                + (1 - alpha) * self._genome.continuity_recovery_rate, 3)

        # Threat pattern distribution: accumulate counts
        for cat, count in snapshot.threat_pattern_distribution.items():
            self._genome.threat_pattern_distribution[cat] = (
                self._genome.threat_pattern_distribution.get(cat, 0) + count)

        # Tool success rate: EMA
        if snapshot.tool_success_rate > 0:
            self._genome.tool_success_rate = round(
                alpha * snapshot.tool_success_rate
                + (1 - alpha) * self._genome.tool_success_rate, 3)

        # Models tested: union (deduplicated)
        new_models = set(self._genome.models_tested) | set(snapshot.models_tested)
        self._genome.models_tested = sorted(new_models)

        self._save_genome()

    def _sign_passport(self, data: dict) -> str:
        """Test helper — sign a passport dict with a throw-away Ed25519 keypair.

        Populates ``data["origin_signature"]`` and temporarily patches
        ``_ORIGIN_PUBLIC_KEY_B64`` so that ``_verify_origin_signature``
        succeeds for the signed dict.  Only intended for use in test code.
        """
        import base64
        import hashlib
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat,
        )

        seed = hashlib.pbkdf2_hmac("sha256", b"forge-test-passport-key", b"salt", 1, 32)
        priv_key = Ed25519PrivateKey.from_private_bytes(seed)
        pub_bytes = priv_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        BPoS._ORIGIN_PUBLIC_KEY_B64 = base64.b64encode(pub_bytes).decode()

        passport = Passport(
            account_id=data.get("account_id", ""),
            tier=data.get("tier", "community"),
            issued_at=data.get("issued_at", 0),
            expires_at=data.get("expires_at", 0),
            activations=list(data.get("activations", [])),
            max_activations=data.get("max_activations", 1),
            origin_signature="",
            role=data.get("role", ""),
            passport_id=data.get("passport_id", ""),
            master_id=data.get("master_id", ""),
            seat_count=data.get("seat_count", 0),
            parent_passport_id=data.get("parent_passport_id", ""),
        )
        payload = self._signing_payload(passport)
        sig_b64 = base64.b64encode(priv_key.sign(payload)).decode()
        data["origin_signature"] = sig_b64
        return sig_b64

    def get_genome_maturity(self) -> float:
        """Compute genome maturity score (0.0 = fresh, 1.0 = mature).

        This quantifies how much better this instance is compared to
        a fresh install. Based on session count with diminishing returns.
        """
        sessions = self._genome.session_count
        # Community tier never persists genome, so session_count stays 0.
        # Fall back to billing lifetime_sessions for a more meaningful number.
        if sessions == 0:
            try:
                import json as _json
                bill = self._data_dir / "billing.json"
                if bill.exists():
                    sessions = _json.loads(
                        bill.read_text(encoding="utf-8")
                    ).get("lifetime_sessions", 0)
            except Exception:
                log.debug("Billing session count read failed for genome maturity", exc_info=True)
        # Sigmoid-like curve: reaches 0.5 at 50 sessions, 0.9 at 200
        import math
        return 1.0 / (1.0 + math.exp(-0.04 * (sessions - 50)))

    # ── Behavioral fingerprinting (ambient verification) ──

    def record_tool_call(self, tool_name: str):
        """Track tool usage patterns for behavioral fingerprinting."""
        self._fingerprint.tool_frequency[tool_name] = (
            self._fingerprint.tool_frequency.get(tool_name, 0) + 1
        )

    def record_command(self, command: str):
        """Track command usage for behavioral fingerprinting."""
        self._fingerprint.command_frequency[command] = (
            self._fingerprint.command_frequency.get(command, 0) + 1
        )

    def update_fingerprint(self, model: str, safety_level: int,
                           theme: str, session_turns: int):
        """Update behavioral fingerprint at session end."""
        alpha = 0.2
        self._fingerprint.avg_turns_per_session = (
            alpha * session_turns
            + (1 - alpha) * self._fingerprint.avg_turns_per_session
        )
        duration = time.time() - self._session_start
        self._fingerprint.avg_session_duration = (
            alpha * duration
            + (1 - alpha) * self._fingerprint.avg_session_duration
        )
        self._fingerprint.primary_model = model
        self._fingerprint.typical_safety_level = safety_level
        self._fingerprint.theme_preference = theme
        self._save_fingerprint()

    def compute_fingerprint_similarity(self, other: dict) -> float:
        """Compare behavioral fingerprints for identity consistency.

        Returns 0.0-1.0 similarity score. Low similarity may indicate
        license sharing (different user's behavioral patterns).
        """
        if not other:
            return 1.0  # No comparison data

        score = 0.0
        weights = 0.0

        # Tool usage distribution similarity (Jaccard on top-10 tools)
        my_tools = set(sorted(
            self._fingerprint.tool_frequency,
            key=self._fingerprint.tool_frequency.get, reverse=True,
        )[:10])
        other_tools = set(other.get("top_tools", []))
        if my_tools or other_tools:
            jaccard = len(my_tools & other_tools) / max(1, len(my_tools | other_tools))
            score += jaccard * 0.3
            weights += 0.3

        # Model preference match
        if other.get("primary_model") == self._fingerprint.primary_model:
            score += 0.2
        weights += 0.2

        # Safety level match
        if other.get("safety_level") == self._fingerprint.typical_safety_level:
            score += 0.15
        weights += 0.15

        # Theme match
        if other.get("theme") == self._fingerprint.theme_preference:
            score += 0.1
        weights += 0.1

        # Session duration similarity (within 2x)
        other_dur = other.get("avg_session_duration", 0)
        my_dur = self._fingerprint.avg_session_duration
        if my_dur > 0 and other_dur > 0:
            ratio = min(my_dur, other_dur) / max(my_dur, other_dur)
            score += ratio * 0.25
        weights += 0.25

        return score / weights if weights > 0 else 1.0

    # ── Persistence ──

    def _load(self):
        self._load_passport()
        self._load_genome()
        self._load_fingerprint()

    def _load_passport(self):
        if not self._passport_path.exists():
            return
        try:
            data = json.loads(self._passport_path.read_text(encoding="utf-8"))
            passport = Passport(**{
                k: v for k, v in data.items()
                if k in Passport.__dataclass_fields__
            })

            # Verify Ed25519 signature for all non-community tiers.
            # A forged or tampered passport gets silently downgraded to
            # community so Forge still starts — it just loses paid features.
            if passport.tier != "community":
                ok, reason = self._verify_origin_signature(passport)
                if not ok:
                    log.warning(
                        "Passport signature invalid (tier=%s, reason=%s) — "
                        "reverting to Community tier.  Re-activate to restore "
                        "your paid tier.", passport.tier, reason
                    )
                    self._passport = None
                    return

            self._passport = passport
        except Exception as ex:
            log.debug("Failed to load passport: %s", ex)

    def _save_passport(self):
        if not self._passport:
            return
        self._atomic_save(self._passport_path, asdict(self._passport))

    def _genome_key(self) -> Optional[bytes]:
        """Derive genome encryption key from passport's origin_signature.

        Returns None for community tier (no passport / no origin_signature),
        which means genome is stored in plaintext (but not persisted anyway
        since community tier blocks genome_persistence).
        """
        if not self._passport or not self._passport.origin_signature:
            return None
        # PBKDF2 with machine_id as salt — ties genome to this machine + passport
        salt = (self._machine_id or "forge").encode("utf-8")
        return hashlib.pbkdf2_hmac(
            "sha512",
            self._passport.origin_signature.encode("utf-8"),
            salt, iterations=100_000, dklen=64,
        )

    def _encrypt_genome(self, plaintext: bytes) -> bytes:
        """Encrypt genome data using passport-derived key.

        Format: nonce (16 bytes) || ciphertext || HMAC-SHA512 tag (64 bytes)
        Encryption: XOR with HMAC-SHA512 counter-mode keystream.
        """
        key = self._genome_key()
        if key is None:
            return plaintext  # No passport — store plaintext

        nonce = secrets.token_bytes(16)
        # Generate keystream via HMAC-SHA512 in counter mode
        ciphertext = bytearray()
        for i in range((len(plaintext) + 63) // 64):
            block = hmac.new(key, nonce + i.to_bytes(4, "big"),
                             hashlib.sha512).digest()
            ciphertext.extend(block)
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, ciphertext))
        # Authenticate: HMAC-SHA512 over nonce + ciphertext
        tag = hmac.new(key, nonce + ciphertext, hashlib.sha512).digest()
        return nonce + ciphertext + tag

    def _decrypt_genome(self, blob: bytes) -> Optional[bytes]:
        """Decrypt genome data. Returns None if key is wrong or data tampered."""
        key = self._genome_key()
        if key is None:
            return blob  # No passport — data is plaintext

        if len(blob) < 80:  # 16 nonce + 0 data + 64 tag minimum
            return None
        nonce = blob[:16]
        tag = blob[-64:]
        ciphertext = blob[16:-64]
        # Verify integrity
        expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha512).digest()
        if not hmac.compare_digest(tag, expected_tag):
            log.warning("Genome decryption failed — passport key mismatch or data tampered")
            return None
        # Decrypt
        plaintext = bytearray()
        for i in range((len(ciphertext) + 63) // 64):
            block = hmac.new(key, nonce + i.to_bytes(4, "big"),
                             hashlib.sha512).digest()
            plaintext.extend(block)
        return bytes(a ^ b for a, b in zip(ciphertext, plaintext))

    def _load_genome(self):
        if not self._genome_path.exists():
            return
        try:
            raw = self._genome_path.read_bytes()
            # Try encrypted format first (binary), fall back to legacy plaintext JSON
            if self._genome_key() is not None:
                decrypted = self._decrypt_genome(raw)
                if decrypted is not None:
                    data = json.loads(decrypted.decode("utf-8"))
                else:
                    # Key mismatch — try as legacy plaintext (migration)
                    try:
                        data = json.loads(raw.decode("utf-8"))
                        log.info("Migrating genome to encrypted format")
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        log.warning("Cannot decrypt genome — passport key mismatch")
                        return
            else:
                data = json.loads(raw.decode("utf-8"))
            self._genome = GenomeSnapshot(**{
                k: v for k, v in data.items()
                if k in GenomeSnapshot.__dataclass_fields__
            })
        except Exception as ex:
            log.debug("Failed to load genome: %s", ex)

    def _save_genome(self):
        plaintext = json.dumps(asdict(self._genome), indent=2).encode("utf-8")
        encrypted = self._encrypt_genome(plaintext)
        path = self._genome_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, encrypted)
            os.close(fd)
            os.replace(tmp, str(path))
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _load_fingerprint(self):
        if not self._fingerprint_path.exists():
            return
        try:
            data = json.loads(self._fingerprint_path.read_text(encoding="utf-8"))
            self._fingerprint = BehavioralFingerprint(**{
                k: v for k, v in data.items()
                if k in BehavioralFingerprint.__dataclass_fields__
            })
        except Exception as ex:
            log.debug("Failed to load fingerprint: %s", ex)

    def _save_fingerprint(self):
        self._atomic_save(self._fingerprint_path, asdict(self._fingerprint))

    def _atomic_save(self, path: Path, data: dict):
        """Atomic JSON save via tempfile + replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
            os.close(fd)
            os.replace(tmp, str(path))
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ── Team Genome Sync ──

    def push_team_genome(self) -> tuple:
        """Push local genome to the team genome on the server.

        Returns (ok: bool, message: str).
        """
        if not self.is_feature_allowed("genome_sync"):
            return (False, "genome_sync not available on this tier")
        if not self._passport:
            return (False, "no passport loaded")
        try:
            import requests
            account_id = self._passport.account_id
            machine_id = self._machine_id
            payload = {
                "action": "genome_push",
                "account_id": account_id,
                "machine_id": machine_id,
                "genome": asdict(self._genome),
            }
            resp = requests.post(
                PASSPORT_API_URL,
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return (True, "pushed")
                return (False, data.get("error", "unknown server error"))
            return (False, f"HTTP {resp.status_code}")
        except Exception as exc:
            return (False, str(exc))

    def pull_team_genome(self) -> bool:
        """Pull team genome from server and merge into local genome.

        Returns True if merge happened, False otherwise.
        """
        if not self.is_feature_allowed("genome_sync"):
            return False
        if not self._passport:
            return False
        try:
            import requests
            resp = requests.get(
                PASSPORT_API_URL,
                params={
                    "action": "genome_pull",
                    "account_id": self._passport.account_id,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
            if not data.get("ok") or not data.get("genome"):
                return False
            self._merge_team_genome(data["genome"])
            self._save_genome()
            return True
        except Exception as exc:
            log.debug("Team genome pull failed: %s", exc)
            return False

    def _merge_team_genome(self, team: dict):
        """Merge a team genome dict into the local genome using EMA."""
        alpha = 0.3
        g = self._genome

        # Counters: take max (team is aggregate of all members)
        g.session_count = max(g.session_count, team.get("session_count", 0))
        g.total_turns = max(g.total_turns, team.get("total_turns", 0))
        g.ami_failure_catalog_size = max(
            g.ami_failure_catalog_size,
            team.get("ami_failure_catalog_size", 0))
        g.ami_model_profiles = max(
            g.ami_model_profiles, team.get("ami_model_profiles", 0))
        g.threat_scans_total = max(
            g.threat_scans_total, team.get("threat_scans_total", 0))
        g.threat_hits_total = max(
            g.threat_hits_total, team.get("threat_hits_total", 0))
        g.tool_call_total = max(
            g.tool_call_total, team.get("tool_call_total", 0))

        # EMA metrics: blend team signal with local
        for field_name in ("ami_average_quality", "reliability_score",
                          "continuity_baseline_grade", "ami_routing_accuracy",
                          "continuity_recovery_rate", "tool_success_rate",
                          "benchmark_pass_rate"):
            team_val = team.get(field_name, 0.0)
            if team_val > 0:
                local_val = getattr(g, field_name, 0.0)
                merged = round(alpha * team_val + (1 - alpha) * local_val, 3)
                setattr(g, field_name, merged)

        # Per-model quality: union keys, EMA for overlapping
        for model, quality in team.get("per_model_quality", {}).items():
            existing = g.per_model_quality.get(model, 0.5)
            g.per_model_quality[model] = round(
                alpha * quality + (1 - alpha) * existing, 3)

        # Threat pattern distribution: take max per category
        for cat, count in team.get("threat_pattern_distribution", {}).items():
            g.threat_pattern_distribution[cat] = max(
                g.threat_pattern_distribution.get(cat, 0), count)

        # Models tested: set union
        team_models = set(team.get("models_tested", []))
        local_models = set(g.models_tested)
        g.models_tested = sorted(local_models | team_models)

        # Quality trend: keep local trend (team trend is aggregate noise)

    # ── Display ──

    def format_status(self) -> str:
        """Format license status for terminal display."""
        tier_cfg = self.tier_config
        price = tier_cfg.get('price_display', tier_cfg.get('price', ''))
        lines = [f"Forge License: {tier_cfg.get('label', self.tier)} ({price})"]

        if self._passport:
            lines.append(f"  Account: {self._passport.account_id[:12]}...")
            lines.append(f"  Activations: {len(self._passport.activations)}"
                        f"/{self._passport.max_activations}")
            if self._passport.expires_at > 0:
                from datetime import datetime
                exp = datetime.fromtimestamp(self._passport.expires_at)
                lines.append(f"  Expires: {exp.strftime('%Y-%m-%d')}")

        maturity = self.get_genome_maturity()
        maturity_pct = int(maturity * 100)
        bar_len = 20
        filled = int(bar_len * maturity)
        bar = "#" * filled + "-" * (bar_len - filled)
        lines.append(f"  Genome maturity: [{bar}] {maturity_pct}%")
        lines.append(f"  Sessions: {self._genome.session_count}")
        lines.append(f"  AMI patterns: {self._genome.ami_failure_catalog_size}")
        lines.append(f"  Model profiles: {self._genome.ami_model_profiles}")

        if not self.is_feature_allowed("genome_persistence"):
            lines.append("  Note: Genome resets each session (Community tier)")

        if self.is_feature_allowed("genome_sync"):
            lines.append("  Team genome sync: enabled")

        if self.is_feature_allowed("priority_support"):
            lines.append("  Priority support: active")

        return "\n".join(lines)

    def to_audit_dict(self) -> dict:
        """Return audit-friendly snapshot."""
        return {
            "schema_version": 1,
            "tier": self.tier,
            "activated": self.is_activated(),
            "genome_maturity": round(self.get_genome_maturity(), 3),
            "genome": asdict(self._genome),
            "fingerprint_summary": {
                "top_tools": sorted(
                    self._fingerprint.tool_frequency,
                    key=self._fingerprint.tool_frequency.get,
                    reverse=True,
                )[:10] if self._fingerprint.tool_frequency else [],
                "primary_model": self._fingerprint.primary_model,
                "avg_session_duration": round(
                    self._fingerprint.avg_session_duration, 1),
            },
        }
