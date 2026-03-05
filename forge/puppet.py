"""Puppet Manager -- Origin/Master/Puppet fleet management for Forge.

Three-tier licensing hierarchy:
  Origin  — The creator (you). Can see all Masters, revoke access, god view.
  Master  — Paying customer. Buys a tier, gets N seats, manages own Puppets.
  Puppet  — Terminal user under a Master. Cannot distribute further.

Standalone — default for unactivated installs. Full local features,
no fleet participation.

Activation flow:
  1. Customer buys a tier on the website (Stripe checkout)
  2. Server generates a Master passport (signed with Origin key)
  3. Customer downloads passport, runs /puppet activate passport.json
  4. Forge validates passport with server, activates as Master
  5. Master generates Puppet sub-passports from their seat pool
  6. Puppet activates locally with Master's passport (server validates chain)

Sync protocol (v2): file-based via a local shared directory (optional).
  <sync_dir>/puppets/<mid>/status.json -- puppet health heartbeat
  <sync_dir>/puppets/<mid>/genome.json -- puppet genome snapshot
"""

import enum
import hashlib
import hmac
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Puppet considered stale after 24 hours without heartbeat
STALE_THRESHOLD_S = 86400

# Server endpoint for passport operations
DEFAULT_PASSPORT_API = "https://dirt-star.com/Forge/passport_api.php"


class PuppetRole(enum.Enum):
    MASTER = "master"          # Paying customer (also Origin backward compat)
    PUPPET = "puppet"          # Terminal user under a Master
    STANDALONE = "standalone"  # Default, no fleet


@dataclass
class PuppetInfo:
    """Information about a registered puppet."""
    machine_id: str
    name: str
    passport_tier: str = "community"
    registered_at: float = 0.0
    last_seen: float = 0.0
    status: str = "active"       # active, stale, revoked
    genome_maturity_pct: int = 0
    session_count: int = 0
    seat_id: str = ""
    parent_id: str = ""          # Master's account_id (for Puppets)
    last_genome: Optional[dict] = field(default=None, repr=False)


class PuppetManager:
    """Fleet management for Origin/Master/Puppet topology."""

    def __init__(self, data_dir: Path = None, bpos=None,
                 machine_id: str = ""):
        self._data_dir = Path(data_dir or (Path.home() / ".forge" / "puppets"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._data_dir / "registry.json"
        self._bpos = bpos
        self._machine_id = machine_id
        self._role = PuppetRole.STANDALONE
        self._puppets: dict[str, PuppetInfo] = {}
        self._sync_dir: Optional[Path] = None
        self._master_id: str = ""
        # Master-specific fields
        self._account_id: str = ""
        self._passport_id: str = ""
        self._master_tier: str = "community"
        self._seats_total: int = 1
        self._seats_used: int = 0
        self._telemetry_token: str = ""
        self._passport_api: str = DEFAULT_PASSPORT_API
        # Puppet-specific fields
        self._parent_account_id: str = ""
        self._seat_id: str = ""
        self._load()

    # ── Properties ──

    @property
    def role(self) -> PuppetRole:
        return self._role

    @property
    def sync_dir(self) -> Optional[Path]:
        return self._sync_dir

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def seats_total(self) -> int:
        return self._seats_total

    @property
    def seats_used(self) -> int:
        return self._seats_used

    @property
    def master_tier(self) -> str:
        return self._master_tier

    # ── Master activation (online) ──

    def activate_master(self, passport_path: str) -> tuple[bool, str]:
        """Activate as Master using a passport file downloaded from website.

        1. Reads passport JSON
        2. Validates with server (signature check)
        3. Registers machine_id as Master
        4. Receives telemetry token
        """
        pp = Path(passport_path)
        if not pp.exists():
            return False, f"Passport file not found: {passport_path}"

        try:
            passport_data = json.loads(pp.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Invalid passport file: {e}"

        # Validate with server
        ok, result = self._server_request("validate", {
            "passport_json": passport_data,
        })
        if not ok:
            return False, f"Server validation failed: {result}"
        if not result.get("valid"):
            reason = result.get("reason", "Unknown")
            return False, f"Passport invalid: {reason}"

        # Activate with server
        ok, result = self._server_request("activate", {
            "passport_json": passport_data,
            "machine_id": self._machine_id,
        })
        if not ok:
            return False, f"Server activation failed: {result}"
        if not result.get("ok"):
            return False, result.get("error", "Activation failed")

        # Success — update local state
        self._role = PuppetRole.MASTER
        self._account_id = result.get("account_id", passport_data.get("account_id", ""))
        self._passport_id = passport_data.get("passport_id", "")
        self._master_tier = result.get("tier", passport_data.get("tier", "community"))
        self._seats_total = result.get("seat_count", passport_data.get("seat_count", 1))
        self._telemetry_token = result.get("telemetry_token", "")
        self._master_id = self._machine_id

        # Also activate in BPoS for local tier features
        if self._bpos:
            tier_config = result.get("tier_config", {})
            bpos_data = {
                "account_id": self._account_id,
                "tier": self._master_tier,
                "issued_at": passport_data.get("issued_at", time.time()),
                "expires_at": passport_data.get("expires_at", 0),
                "activations": [self._machine_id],
                "max_activations": self._seats_total,
            }
            bpos_data["signature"] = self._bpos._sign_passport(bpos_data)
            self._bpos.activate(bpos_data)

        self._save()

        tier_label = self._master_tier.title()
        puppet_seats = max(0, self._seats_total - 1)
        return True, (
            f"Activated as Master — {tier_label} tier, "
            f"{self._seats_total} seats ({puppet_seats} available for puppets)"
        )

    # ── Master: generate puppet passport ──

    def generate_puppet_passport(self, puppet_name: str,
                                  output_dir: str = None) -> Optional[Path]:
        """Generate a puppet passport from Master's seat pool.

        Creates a passport file that a Puppet machine can use to join.
        Registers the puppet with the server.
        """
        if self._role != PuppetRole.MASTER:
            log.warning("Only masters can generate puppet passports")
            return None

        puppet_seats = max(0, self._seats_total - 1)
        if self._seats_used >= puppet_seats:
            log.warning("All puppet seats used (%d/%d)",
                        self._seats_used, puppet_seats)
            return None

        seat_id = f"seat_{self._seats_used + 1}"

        # Create puppet passport (signed by Master locally)
        puppet_passport = {
            "passport_id": f"pp_puppet_{int(time.time())}_{os.urandom(4).hex()}",
            "account_id": self._account_id,
            "role": "puppet",
            "tier": self._master_tier,
            "puppet_name": puppet_name,
            "master_id": self._machine_id,
            "parent_passport_id": self._passport_id,
            "seat_id": seat_id,
            "seat_count": 0,  # Puppets cannot distribute
            "issued_at": time.time(),
            "issued_date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "expires_at": 0,
        }

        # Sign with Master's local key (chain of trust)
        if self._bpos:
            puppet_passport["master_signature"] = self._bpos._sign_passport(
                puppet_passport)

        # Register puppet with server
        ok, result = self._server_request("register_puppet", {
            "master_id": self._account_id,
            "puppet_mid": f"pending_{puppet_name}",
            "puppet_name": puppet_name,
            "seat_id": seat_id,
        })
        if ok and result.get("ok"):
            self._seats_used = result.get("seats_used", self._seats_used + 1)
        else:
            # Server registration failed — still generate locally
            err = result if isinstance(result, str) else result.get("error", "")
            log.warning("Server puppet registration failed: %s (generating locally)", err)
            self._seats_used += 1

        # Write passport file
        out = Path(output_dir) if output_dir else self._data_dir / "passports"
        out.mkdir(parents=True, exist_ok=True)
        safe_name = puppet_name.replace(" ", "_").lower()
        path = out / f"puppet_{safe_name}.json"
        self._atomic_write(path, puppet_passport)

        self._save()
        log.info("Generated puppet passport: %s -> %s", puppet_name, path)
        return path

    # ── Puppet: join fleet ──

    def init_as_puppet(self, passport_path: str,
                       sync_dir: str = None) -> tuple[bool, str]:
        """Register this machine as a Puppet under a Master.

        Validates the Master's passport chain with the server.
        Optional sync_dir for local genome sync (backward compat).
        """
        pp = Path(passport_path)
        if not pp.exists():
            return False, f"Passport file not found: {passport_path}"

        try:
            passport_data = json.loads(pp.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Invalid passport file: {e}"

        # Verify this is a puppet passport
        if passport_data.get("role") != "puppet":
            return False, "This is not a puppet passport"

        # Validate Master's passport chain with server
        ok, result = self._server_request("validate", {
            "passport_json": passport_data,
        })
        if ok and result.get("valid") is False:
            reason = result.get("reason", "Unknown")
            return False, f"Master's license invalid: {reason}"

        # Activate locally via BPoS
        if self._bpos:
            bpos_data = {
                "account_id": passport_data.get("account_id", ""),
                "tier": passport_data.get("tier", "community"),
                "issued_at": passport_data.get("issued_at", time.time()),
                "expires_at": passport_data.get("expires_at", 0),
                "activations": [self._machine_id],
                "max_activations": 1,
            }
            bpos_data["signature"] = self._bpos._sign_passport(bpos_data)
            self._bpos.activate(bpos_data)

        self._role = PuppetRole.PUPPET
        self._parent_account_id = passport_data.get("account_id", "")
        self._master_id = passport_data.get("master_id",
                                           passport_data.get("captain_id", ""))
        self._seat_id = passport_data.get("seat_id", "")
        self._master_tier = passport_data.get("tier", "community")
        self._passport_id = passport_data.get("passport_id", "")

        # Optional local sync directory
        if sync_dir:
            sd = Path(sync_dir)
            if sd.exists():
                self._sync_dir = sd
                puppet_dir = sd / "puppets" / self._machine_id
                puppet_dir.mkdir(parents=True, exist_ok=True)
                self._write_puppet_status(puppet_dir)

        self._save()
        tier_label = self._master_tier.title()
        return True, f"Joined fleet as Puppet — {tier_label} tier, seat {self._seat_id}"

    # ── Backward compat: init_as_master (local fleet) ──

    def init_as_master(self, sync_dir: str) -> bool:
        """Initialize as fleet master (local mode, backward compat).

        For users who want local fleet management without server
        activation. Maps to MASTER role internally.
        """
        sd = Path(sync_dir)
        if not sd.exists():
            try:
                sd.mkdir(parents=True)
            except OSError as e:
                log.error("Cannot create sync dir: %s", e)
                return False

        self._role = PuppetRole.MASTER
        self._sync_dir = sd
        self._master_id = self._machine_id

        # Write master manifest
        master_dir = sd / "master"
        master_dir.mkdir(exist_ok=True)
        (master_dir / "passports").mkdir(exist_ok=True)
        manifest = {
            "master_id": self._machine_id,
            "timestamp": time.time(),
            "version": 2,
        }
        self._atomic_write(master_dir / "manifest.json", manifest)
        (sd / "puppets").mkdir(exist_ok=True)

        self._save()
        return True

    # ── Common fleet API ──

    def list_puppets(self) -> list[PuppetInfo]:
        """List all registered puppets with latest status."""
        return list(self._puppets.values())

    def revoke_puppet(self, machine_id: str) -> bool:
        """Revoke a puppet's access."""
        if machine_id in self._puppets:
            self._puppets[machine_id].status = "revoked"
            self._save()
            return True
        return False

    def get_puppet_genome(self, machine_id: str) -> Optional[dict]:
        """Read a puppet's genome snapshot from sync dir."""
        if not self._sync_dir:
            return None
        genome_path = (self._sync_dir / "puppets" / machine_id
                       / "genome.json")
        if genome_path.exists():
            try:
                return json.loads(genome_path.read_text())
            except Exception as e:
                log.debug("Failed to read puppet genome: %s", e)
        return None

    def refresh_puppet_status(self) -> list[PuppetInfo]:
        """Scan sync directory for puppet status updates."""
        if not self._sync_dir:
            return list(self._puppets.values())

        puppets_dir = self._sync_dir / "puppets"
        if not puppets_dir.exists():
            return list(self._puppets.values())

        now = time.time()
        for puppet_dir in puppets_dir.iterdir():
            if not puppet_dir.is_dir():
                continue
            mid = puppet_dir.name
            status_file = puppet_dir / "status.json"
            if not status_file.exists():
                continue

            try:
                status_data = json.loads(status_file.read_text())
            except Exception:
                continue

            last_seen = status_data.get("timestamp", 0)
            is_stale = (now - last_seen) > STALE_THRESHOLD_S

            genome = None
            genome_file = puppet_dir / "genome.json"
            if genome_file.exists():
                try:
                    genome = json.loads(genome_file.read_text())
                except Exception:
                    pass

            if mid in self._puppets:
                p = self._puppets[mid]
                p.last_seen = last_seen
                if p.status != "revoked":
                    p.status = "stale" if is_stale else "active"
                p.genome_maturity_pct = status_data.get(
                    "genome_maturity_pct", 0)
                p.session_count = status_data.get("session_count", 0)
                p.last_genome = genome
            else:
                self._puppets[mid] = PuppetInfo(
                    machine_id=mid,
                    name=status_data.get("name", mid[:8]),
                    passport_tier=status_data.get("tier", "community"),
                    registered_at=status_data.get("registered_at",
                                                  last_seen),
                    last_seen=last_seen,
                    status="stale" if is_stale else "active",
                    genome_maturity_pct=status_data.get(
                        "genome_maturity_pct", 0),
                    session_count=status_data.get("session_count", 0),
                    last_genome=genome,
                )

        self._save()
        return list(self._puppets.values())

    def sync_to_master(self, genome_snapshot: dict) -> bool:
        """Write genome snapshot + status to sync directory."""
        if self._role != PuppetRole.PUPPET or not self._sync_dir:
            return False

        puppet_dir = self._sync_dir / "puppets" / self._machine_id
        puppet_dir.mkdir(parents=True, exist_ok=True)
        self._write_puppet_status(puppet_dir)
        self._atomic_write(puppet_dir / "genome.json", genome_snapshot)
        log.debug("Puppet genome synced to master")
        return True

    def check_master_alive(self) -> bool:
        """Check if master's manifest is recent (< 24h)."""
        if not self._sync_dir:
            return False
        manifest = self._sync_dir / "master" / "manifest.json"
        if not manifest.exists():
            return False
        try:
            data = json.loads(manifest.read_text())
            ts = data.get("timestamp", 0)
            return (time.time() - ts) < STALE_THRESHOLD_S
        except Exception:
            return False

    def get_seat_summary(self) -> dict:
        """Return seat allocation summary for Masters."""
        puppet_limit = max(0, self._seats_total - 1)
        active_puppets = sum(
            1 for p in self._puppets.values() if p.status == "active")
        return {
            "seats_total": self._seats_total,
            "puppet_limit": puppet_limit,
            "seats_used": self._seats_used,
            "active_puppets": active_puppets,
            "seats_available": max(0, puppet_limit - self._seats_used),
        }

    # ── Server communication ──

    def _server_request(self, action: str, data: dict) -> tuple[bool, dict]:
        """Make a request to the passport API server.

        Returns (success, response_dict).
        Uses the telemetry token for auth if available.
        """
        import urllib.request
        import urllib.error

        url = f"{self._passport_api}?action={action}"
        payload = json.dumps(data).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._telemetry_token:
            headers["X-Forge-Token"] = self._telemetry_token

        req = urllib.request.Request(url, data=payload, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return True, body
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
                return False, body.get("error", str(e))
            except Exception:
                return False, str(e)
        except Exception as e:
            log.debug("Server request failed: %s", e)
            return False, str(e)

    # ── Status helpers ──

    def _write_puppet_status(self, puppet_dir: Path):
        """Write status heartbeat to sync directory."""
        maturity = 0
        session_count = 0
        tier = "community"
        name = self._machine_id[:8]

        if self._bpos:
            maturity = int(self._bpos.get_genome_maturity() * 100)
            session_count = self._bpos._genome.session_count
            tier = self._bpos.tier
            try:
                from forge.machine_id import get_machine_label
                label = get_machine_label()
                if label:
                    name = label
            except Exception:
                pass

        status_data = {
            "machine_id": self._machine_id,
            "name": name,
            "tier": tier,
            "timestamp": time.time(),
            "genome_maturity_pct": maturity,
            "session_count": session_count,
            "registered_at": getattr(self, "_registered_at", time.time()),
        }
        self._atomic_write(puppet_dir / "status.json", status_data)

    # ── Display ──

    def format_status(self) -> str:
        """Format fleet status for terminal display."""
        role_labels = {
            PuppetRole.MASTER: "Master",
            PuppetRole.PUPPET: "Puppet",
            PuppetRole.STANDALONE: "Standalone",
        }
        lines = [f"Fleet Role: {role_labels.get(self._role, self._role.value)}"]

        if self._role == PuppetRole.MASTER and self._account_id:
            lines.append(f"  Tier: {self._master_tier.title()}")
            summary = self.get_seat_summary()
            lines.append(
                f"  Seats: {summary['seats_used']}/{summary['puppet_limit']} "
                f"puppet seats used ({summary['seats_available']} available)")
            lines.append(f"  Account: {self._account_id}")
            if self._puppets:
                lines.append(f"  Puppets: {len(self._puppets)}")
                for p in self._puppets.values():
                    icon = {"active": "+", "stale": "?",
                            "revoked": "x"}.get(p.status, "?")
                    lines.append(
                        f"    [{icon}] {p.name} ({p.passport_tier}) "
                        f"genome: {p.genome_maturity_pct}% "
                        f"sessions: {p.session_count}")

        elif self._role == PuppetRole.MASTER:
            if self._sync_dir:
                lines.append(f"  Sync Dir: {self._sync_dir}")
            lines.append(f"  Puppets: {len(self._puppets)}")
            for p in self._puppets.values():
                icon = {"active": "+", "stale": "?",
                        "revoked": "x"}.get(p.status, "?")
                lines.append(
                    f"    [{icon}] {p.name} ({p.passport_tier}) "
                    f"genome: {p.genome_maturity_pct}% "
                    f"sessions: {p.session_count}")

        elif self._role == PuppetRole.PUPPET:
            lines.append(f"  Tier: {self._master_tier.title()}")
            lines.append(f"  Seat: {self._seat_id}")
            lines.append(f"  Master: {self._master_id}")
            if self._sync_dir:
                alive = self.check_master_alive()
                lines.append(
                    f"  Sync: {'connected' if alive else 'offline/stale'}")

        else:
            lines.append("  Not part of a fleet.")
            lines.append("  Use /puppet activate <file> to activate a "
                         "Master passport.")

        return "\n".join(lines)

    def to_audit_dict(self) -> dict:
        """Return audit-friendly snapshot."""
        return {
            "schema_version": 2,
            "role": self._role.value,
            "machine_id": self._machine_id,
            "account_id": self._account_id,
            "master_tier": self._master_tier,
            "seats_total": self._seats_total,
            "seats_used": self._seats_used,
            "sync_dir": str(self._sync_dir) if self._sync_dir else None,
            "puppet_count": len(self._puppets),
            "puppets": {
                mid: {
                    "name": p.name,
                    "tier": p.passport_tier,
                    "status": p.status,
                    "maturity_pct": p.genome_maturity_pct,
                    "session_count": p.session_count,
                    "seat_id": p.seat_id,
                }
                for mid, p in self._puppets.items()
            },
        }

    # ── Persistence ──

    def _load(self):
        """Load registry from disk."""
        if not self._registry_path.exists():
            return
        try:
            data = json.loads(self._registry_path.read_text())
            role_str = data.get("role", "standalone")
            # Backward compat: old "captain" role maps to MASTER
            if role_str == "captain":
                role_str = "master"
            try:
                self._role = PuppetRole(role_str)
            except ValueError:
                self._role = PuppetRole.STANDALONE
            self._sync_dir = (Path(data["sync_dir"])
                              if data.get("sync_dir") else None)
            self._master_id = data.get("master_id", "")
            self._account_id = data.get("account_id", "")
            self._passport_id = data.get("passport_id", "")
            # Backward compat: read old "captain_tier" key too
            self._master_tier = data.get("master_tier",
                                         data.get("captain_tier", "community"))
            self._seats_total = data.get("seats_total", 1)
            self._seats_used = data.get("seats_used", 0)
            self._telemetry_token = data.get("telemetry_token", "")
            self._parent_account_id = data.get("parent_account_id", "")
            self._seat_id = data.get("seat_id", "")
            for mid, pdata in data.get("puppets", {}).items():
                self._puppets[mid] = PuppetInfo(
                    machine_id=mid,
                    name=pdata.get("name", mid[:8]),
                    passport_tier=pdata.get("passport_tier", "community"),
                    registered_at=pdata.get("registered_at", 0),
                    last_seen=pdata.get("last_seen", 0),
                    status=pdata.get("status", "active"),
                    genome_maturity_pct=pdata.get("genome_maturity_pct", 0),
                    session_count=pdata.get("session_count", 0),
                    seat_id=pdata.get("seat_id", ""),
                    parent_id=pdata.get("parent_id", ""),
                )
        except Exception as e:
            log.debug("Failed to load puppet registry: %s", e)

    def _save(self):
        """Save registry to disk."""
        data = {
            "version": 2,
            "role": self._role.value,
            "machine_id": self._machine_id,
            "sync_dir": str(self._sync_dir) if self._sync_dir else None,
            "master_id": self._master_id,
            "account_id": self._account_id,
            "passport_id": self._passport_id,
            "master_tier": self._master_tier,
            "seats_total": self._seats_total,
            "seats_used": self._seats_used,
            "telemetry_token": self._telemetry_token,
            "parent_account_id": self._parent_account_id,
            "seat_id": self._seat_id,
            "puppets": {
                mid: {
                    "name": p.name,
                    "passport_tier": p.passport_tier,
                    "registered_at": p.registered_at,
                    "last_seen": p.last_seen,
                    "status": p.status,
                    "genome_maturity_pct": p.genome_maturity_pct,
                    "session_count": p.session_count,
                    "seat_id": p.seat_id,
                    "parent_id": p.parent_id,
                }
                for mid, p in self._puppets.items()
            },
        }
        self._atomic_write(self._registry_path, data)

    @staticmethod
    def _atomic_write(path: Path, data: dict):
        """Atomic JSON write via tempfile + os.replace."""
        content = json.dumps(data, indent=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix="puppet_")
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp, str(path))
        except Exception:
            if not closed:
                os.close(fd)
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass
            raise
