"""Tests for PuppetManager — Origin/Master/Puppet fleet management."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from forge.puppet import PuppetManager, PuppetRole, PuppetInfo


@pytest.fixture
def pm(tmp_path):
    return PuppetManager(data_dir=tmp_path, machine_id="master123abc")


class TestStandalone:
    """Verifies PuppetManager defaults for a fresh standalone instance.

    A new PuppetManager with no init call has role==STANDALONE, sync_dir==None,
    list_puppets()==[], format_status() contains 'Standalone', audit dict has
    role=='standalone' and puppet_count==0, and seat_summary reports
    seats_total=1 / puppet_limit=0 / seats_available=0 (one seat = the local machine).
    """

    def test_default_role_is_standalone(self, pm):
        assert pm.role == PuppetRole.STANDALONE

    def test_no_sync_dir(self, pm):
        assert pm.sync_dir is None

    def test_list_puppets_empty(self, pm):
        assert pm.list_puppets() == []

    def test_format_status_standalone(self, pm):
        status = pm.format_status()
        assert "Standalone" in status or "standalone" in status

    def test_to_audit_dict(self, pm):
        audit = pm.to_audit_dict()
        assert audit["role"] == "standalone"
        assert audit["puppet_count"] == 0

    def test_seat_summary_defaults(self, pm):
        summary = pm.get_seat_summary()
        assert summary["seats_total"] == 1
        assert summary["puppet_limit"] == 0
        assert summary["seats_available"] == 0


class TestMaster:
    """Verifies PuppetManager master-mode initialization and passport generation.

    init_as_master(sync_dir) sets role=MASTER, stores the sync_dir, creates master/
    and puppets/ subdirectories, and writes a manifest.json containing master_id.
    generate_puppet_passport() returns None if not yet master; succeeds when master,
    writing a passport JSON with tier, puppet_name, role='puppet', and master_signature.
    Seat limit enforcement: with _seats_total=2 and _seats_used=1, the one puppet slot
    is full and generate_puppet_passport() returns None.
    """

    def test_init_as_master(self, pm, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        assert pm.init_as_master(str(sync))
        assert pm.role == PuppetRole.MASTER
        assert pm.sync_dir == sync

    def test_master_creates_manifest(self, pm, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        pm.init_as_master(str(sync))
        manifest = sync / "master" / "manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert data["master_id"] == "master123abc"

    def test_master_creates_dirs(self, pm, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        pm.init_as_master(str(sync))
        assert (sync / "master" / "passports").is_dir()
        assert (sync / "puppets").is_dir()

    def test_generate_passport_requires_master(self, pm):
        pm._bpos = MagicMock()
        path = pm.generate_puppet_passport("test")
        assert path is None  # Not master yet

    def test_generate_passport(self, pm, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        pm.init_as_master(str(sync))
        pm._account_id = "fg_test123"
        pm._master_tier = "pro"
        pm._seats_total = 3
        pm._seats_used = 0
        bpos_mock = MagicMock()
        bpos_mock._sign_passport.return_value = "sig123"
        pm._bpos = bpos_mock
        path = pm.generate_puppet_passport("DevBox")
        assert path is not None
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["tier"] == "pro"
        assert data["puppet_name"] == "DevBox"
        assert data["role"] == "puppet"
        assert data["master_signature"] == "sig123"

    def test_generate_passport_respects_seat_limit(self, pm, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        pm.init_as_master(str(sync))
        pm._account_id = "fg_test"
        pm._master_tier = "pro"
        pm._seats_total = 2  # 1 master + 1 puppet
        pm._seats_used = 1   # Already used the 1 puppet seat
        pm._bpos = MagicMock()
        path = pm.generate_puppet_passport("TooMany")
        assert path is None


class TestPuppet:
    """Verifies puppet-mode join, sync, status reading, and passport validation.

    Full join flow: master generates a passport, puppet calls init_as_puppet(passport_path)
    → ok=True, role=PUPPET. sync_to_master(genome) writes genome.json and status.json
    under sync/puppets/{machine_id}/. Master's refresh_puppet_status() reads those files
    back into PuppetInfo objects with the correct name and genome_maturity_pct. Joining
    with a non-existent passport path → ok=False. Joining with a master-role passport
    (not puppet) → ok=False with 'not a puppet passport' in the message.
    """

    def test_join_as_puppet(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()

        # Master setup
        master = PuppetManager(
            data_dir=tmp_path / "m", machine_id="master1")
        master._bpos = MagicMock()
        master._bpos._sign_passport.return_value = "sig"
        master.init_as_master(str(sync))
        master._account_id = "fg_test"
        master._master_tier = "pro"
        master._seats_total = 3
        master._seats_used = 0
        passport_path = master.generate_puppet_passport("P1")

        # Puppet setup
        puppet = PuppetManager(
            data_dir=tmp_path / "p", machine_id="puppet1")
        puppet._bpos = MagicMock()
        puppet._bpos.activate.return_value = (True, "OK")
        puppet._bpos.tier = "pro"
        puppet._bpos.get_genome_maturity.return_value = 0.0
        puppet._bpos._genome.session_count = 0
        puppet._bpos._sign_passport.return_value = "sig"
        ok, msg = puppet.init_as_puppet(
            str(passport_path), sync_dir=str(sync))
        assert ok is True
        assert puppet.role == PuppetRole.PUPPET

    def test_puppet_sync(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        (sync / "puppets").mkdir()

        puppet = PuppetManager(
            data_dir=tmp_path / "p", machine_id="puppet1")
        puppet._role = PuppetRole.PUPPET
        puppet._sync_dir = sync
        puppet._bpos = MagicMock()
        puppet._bpos.get_genome_maturity.return_value = 0.5
        puppet._bpos._genome.session_count = 10
        puppet._bpos.tier = "pro"

        genome = {"session_count": 10, "ami_failure_catalog_size": 5}
        assert puppet.sync_to_master(genome)

        genome_file = sync / "puppets" / "puppet1" / "genome.json"
        assert genome_file.exists()
        status_file = sync / "puppets" / "puppet1" / "status.json"
        assert status_file.exists()

    def test_master_reads_puppet_status(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()

        # Master
        master = PuppetManager(
            data_dir=tmp_path / "m", machine_id="master1")
        master.init_as_master(str(sync))

        # Simulate puppet writing status
        p_dir = sync / "puppets" / "puppet1"
        p_dir.mkdir(parents=True)
        status = {
            "machine_id": "puppet1",
            "name": "DevBox",
            "tier": "pro",
            "timestamp": time.time(),
            "genome_maturity_pct": 45,
            "session_count": 20,
        }
        (p_dir / "status.json").write_text(json.dumps(status))

        puppets = master.refresh_puppet_status()
        assert len(puppets) == 1
        assert puppets[0].name == "DevBox"
        assert puppets[0].genome_maturity_pct == 45

    def test_puppet_not_found(self, pm):
        ok, msg = pm.init_as_puppet("/nonexistent.json")
        assert ok is False

    def test_puppet_rejects_non_puppet_passport(self, tmp_path):
        """Puppet join should reject passport without role=puppet."""
        puppet = PuppetManager(
            data_dir=tmp_path / "p", machine_id="p1")
        # Write a master passport (not puppet)
        pp_file = tmp_path / "master.json"
        pp_file.write_text(json.dumps({
            "role": "master", "tier": "pro",
            "account_id": "fg_test"}))
        ok, msg = puppet.init_as_puppet(str(pp_file))
        assert ok is False
        assert "not a puppet passport" in msg


class TestRevoke:
    """Verifies revoke_puppet() sets status='revoked' and handles missing puppet IDs.

    revoke_puppet(machine_id) on a known puppet → returns True and sets
    _puppets[machine_id].status == 'revoked'. revoke_puppet on an unknown ID → returns False.
    """

    def test_revoke_puppet(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        master = PuppetManager(
            data_dir=tmp_path / "m", machine_id="master1")
        master.init_as_master(str(sync))
        master._puppets["puppet1"] = PuppetInfo(
            machine_id="puppet1", name="P1", status="active")
        assert master.revoke_puppet("puppet1")
        assert master._puppets["puppet1"].status == "revoked"

    def test_revoke_nonexistent(self, pm):
        assert pm.revoke_puppet("nonexistent") is False


class TestStaleDetection:
    """Verifies staleness detection for puppets that haven't synced recently.

    A puppet whose status.json timestamp is >24h ago is marked status='stale' when
    the master calls refresh_puppet_status(). check_master_alive() returns False when
    no manifest exists in the sync dir, and True when manifest.json contains a fresh
    (current) timestamp.
    """

    def test_stale_puppet(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()
        master = PuppetManager(
            data_dir=tmp_path / "m", machine_id="master1")
        master.init_as_master(str(sync))

        # Write old status
        p_dir = sync / "puppets" / "stale1"
        p_dir.mkdir(parents=True)
        status = {
            "machine_id": "stale1",
            "name": "OldBox",
            "tier": "pro",
            "timestamp": time.time() - 100000,  # >24h ago
            "genome_maturity_pct": 10,
            "session_count": 2,
        }
        (p_dir / "status.json").write_text(json.dumps(status))

        puppets = master.refresh_puppet_status()
        assert len(puppets) == 1
        assert puppets[0].status == "stale"

    def test_check_master_alive(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()

        puppet = PuppetManager(
            data_dir=tmp_path / "p", machine_id="p1")
        puppet._sync_dir = sync
        assert puppet.check_master_alive() is False

        # Write fresh manifest
        m_dir = sync / "master"
        m_dir.mkdir(parents=True)
        (m_dir / "manifest.json").write_text(json.dumps({
            "master_id": "m1", "timestamp": time.time()}))
        assert puppet.check_master_alive() is True


class TestPersistence:
    """Verifies PuppetManager state is fully saved and restored across restarts.

    Master roundtrip: after init_as_master + adding a puppet entry, _save() then
    loading a new PuppetManager from the same data_dir restores role=MASTER,
    the puppet dict, and genome_maturity_pct. Master-specific fields roundtrip:
    account_id, passport_id, master_tier, seats_total, seats_used, telemetry_token.
    Puppet-specific fields roundtrip: role=PUPPET, parent_account_id, seat_id.
    """

    def test_save_load_roundtrip(self, tmp_path):
        sync = tmp_path / "sync"
        sync.mkdir()

        pm1 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="master1")
        pm1.init_as_master(str(sync))
        pm1._puppets["p1"] = PuppetInfo(
            machine_id="p1", name="Box1",
            passport_tier="pro", status="active",
            genome_maturity_pct=42, session_count=10)
        pm1._save()

        pm2 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="master1")
        assert pm2.role == PuppetRole.MASTER
        assert "p1" in pm2._puppets
        assert pm2._puppets["p1"].name == "Box1"
        assert pm2._puppets["p1"].genome_maturity_pct == 42

    def test_save_load_master_roundtrip(self, tmp_path):
        """Master-specific fields persist across restart."""
        pm1 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm1._role = PuppetRole.MASTER
        pm1._account_id = "fg_abc123"
        pm1._passport_id = "pp_xyz"
        pm1._master_tier = "power"
        pm1._seats_total = 10
        pm1._seats_used = 3
        pm1._telemetry_token = "fg_master_token"
        pm1._save()

        pm2 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        assert pm2.role == PuppetRole.MASTER
        assert pm2.account_id == "fg_abc123"
        assert pm2.master_tier == "power"
        assert pm2.seats_total == 10
        assert pm2.seats_used == 3

    def test_save_load_puppet_roundtrip(self, tmp_path):
        """Puppet-specific fields persist across restart."""
        pm1 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="pup1")
        pm1._role = PuppetRole.PUPPET
        pm1._parent_account_id = "fg_master"
        pm1._seat_id = "seat_2"
        pm1._master_tier = "pro"
        pm1._save()

        pm2 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="pup1")
        assert pm2.role == PuppetRole.PUPPET
        assert pm2._parent_account_id == "fg_master"
        assert pm2._seat_id == "seat_2"


class TestMasterActivation:
    """Verifies master online activation against a mocked license server.

    activate_master() with a missing file → ok=False, 'not found' in message.
    Successful activation: mock server returns valid=True then activation payload
    (account_id, tier, seat_count, telemetry_token) → ok=True, role=MASTER,
    account_id and seats_total set from server response, 'Master' in success message.
    Server rejects passport (valid=False) → ok=False, 'invalid' in message.
    """

    def test_activate_master_file_not_found(self, pm):
        ok, msg = pm.activate_master("/no/such/file.json")
        assert ok is False
        assert "not found" in msg

    def test_activate_master_success(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap_machine")
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "local_sig"
        pm._bpos.activate.return_value = (True, "OK")

        # Write a passport file
        passport = {
            "passport_id": "pp_test",
            "account_id": "fg_test_master",
            "role": "master",
            "tier": "pro",
            "seat_count": 3,
            "issued_at": time.time(),
            "expires_at": 0,
            "origin_signature": "server_sig",
        }
        pp_file = tmp_path / "passport.json"
        pp_file.write_text(json.dumps(passport))

        # Mock server responses
        def mock_request(action, data):
            if action == "validate":
                return True, {"valid": True}
            if action == "activate":
                return True, {
                    "ok": True,
                    "account_id": "fg_test_master",
                    "master_id": "cap_machine",
                    "tier": "pro",
                    "seat_count": 3,
                    "telemetry_token": "fg_master_tok123",
                    "tier_config": {},
                }
            return False, "unknown"

        pm._server_request = mock_request

        ok, msg = pm.activate_master(str(pp_file))
        assert ok is True
        assert pm.role == PuppetRole.MASTER
        assert pm.account_id == "fg_test_master"
        assert pm.seats_total == 3
        assert "Master" in msg

    def test_activate_master_server_rejects(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap2")

        passport = {
            "passport_id": "pp_bad",
            "account_id": "fg_bad",
            "role": "master",
            "tier": "pro",
            "origin_signature": "wrong",
        }
        pp_file = tmp_path / "passport.json"
        pp_file.write_text(json.dumps(passport))

        pm._server_request = lambda a, d: (
            True, {"valid": False, "reason": "Invalid origin signature"})

        ok, msg = pm.activate_master(str(pp_file))
        assert ok is False
        assert "invalid" in msg.lower()


class TestSeatEnforcement:
    """Verifies seat accounting: puppet_limit = seats_total - 1 (master occupies one seat).

    seats_total=3 → puppet_limit=2, seats_available=2. Community tier with seats_total=1
    → puppet_limit=0 → generate_puppet_passport() returns None even when _seats_used=0.
    """

    def test_seats_include_master(self, tmp_path):
        """seat_count=3 means 1 master + 2 puppet seats."""
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._seats_total = 3
        pm._seats_used = 0
        summary = pm.get_seat_summary()
        assert summary["puppet_limit"] == 2
        assert summary["seats_available"] == 2

    def test_cant_exceed_puppet_limit(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._account_id = "fg_test"
        pm._master_tier = "community"
        pm._seats_total = 1  # Only master seat, no puppet seats
        pm._seats_used = 0
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "sig"

        path = pm.generate_puppet_passport("ShouldFail")
        assert path is None  # 0 puppet seats available


class TestRoleEnum:
    """Verifies PuppetRole enum values and PuppetInfo dataclass seat fields.

    PuppetRole.MASTER.value == 'master'. The full set of role values is exactly
    {'master', 'puppet', 'standalone'}. PuppetInfo accepts seat_id and parent_id
    keyword args and exposes them as attributes.
    """

    def test_master_role_exists(self):
        assert PuppetRole.MASTER.value == "master"

    def test_all_roles(self):
        roles = {r.value for r in PuppetRole}
        assert roles == {"master", "puppet", "standalone"}

    def test_puppet_info_has_seat_fields(self):
        p = PuppetInfo(machine_id="m1", name="test",
                       seat_id="seat_1", parent_id="fg_cap")
        assert p.seat_id == "seat_1"
        assert p.parent_id == "fg_cap"


class TestAuditDict:
    """Verifies to_audit_dict() produces schema_version=2 with all required fields.

    A standalone manager's audit dict has schema_version=2 and includes account_id,
    master_tier, seats_total, seats_used keys. A master manager's audit dict has
    role='master', master_tier='power', and a 'puppets' sub-dict where each entry
    contains its seat_id.
    """

    def test_v2_audit_fields(self, pm):
        audit = pm.to_audit_dict()
        assert audit["schema_version"] == 2
        assert "account_id" in audit
        assert "master_tier" in audit
        assert "seats_total" in audit
        assert "seats_used" in audit

    def test_master_audit(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._account_id = "fg_master"
        pm._master_tier = "power"
        pm._seats_total = 10
        pm._seats_used = 3
        pm._puppets["p1"] = PuppetInfo(
            machine_id="p1", name="Box1", seat_id="seat_1")

        audit = pm.to_audit_dict()
        assert audit["role"] == "master"
        assert audit["master_tier"] == "power"
        assert audit["puppets"]["p1"]["seat_id"] == "seat_1"
