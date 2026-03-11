"""Tests for passport API server integration (mocked HTTP)."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from forge.puppet import PuppetManager, PuppetRole


class TestServerRequests:
    """Verifies PuppetManager._server_request handles success, timeout, and HTTP errors.

    Mocked urllib: valid JSON response → ok=True, result dict. Exception (timeout) → ok=False.
    HTTPError 403 → ok=False.
    """

    def test_server_request_success(self, tmp_path):
        pm = PuppetManager(data_dir=tmp_path, machine_id="test1")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"valid": True, "tier": "pro"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, result = pm._server_request("validate", {"test": True})
            assert ok is True
            assert result["valid"] is True

    def test_server_request_timeout(self, tmp_path):
        pm = PuppetManager(data_dir=tmp_path, machine_id="test1")

        import urllib.error
        with patch("urllib.request.urlopen",
                   side_effect=Exception("timeout")):
            ok, result = pm._server_request("validate", {})
            assert ok is False

    def test_server_request_http_error(self, tmp_path):
        pm = PuppetManager(data_dir=tmp_path, machine_id="test1")

        import urllib.error
        err = urllib.error.HTTPError(
            "http://test", 403, "Forbidden", {},
            MagicMock(read=lambda: json.dumps(
                {"error": "Insufficient permissions"}).encode()))

        with patch("urllib.request.urlopen", side_effect=err):
            ok, result = pm._server_request("validate", {})
            assert ok is False


class TestMasterActivationFlow:
    """Verifies full master activation flow: validate then activate, with persistence.

    mock_server called with 'validate' then 'activate' (each exactly once) → ok=True,
    role=MASTER, account_id='fg_flow_123', seats_total=10. Activation persists:
    reloading PuppetManager from same data_dir restores role, account_id, master_tier, seats_total.
    """

    def test_full_activation_flow(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="my_machine")
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "local_sig"
        pm._bpos.activate.return_value = (True, "OK")

        # Write passport
        passport = {
            "passport_id": "pp_flow_test",
            "account_id": "fg_flow_123",
            "role": "master",
            "tier": "power",
            "seat_count": 10,
            "issued_at": time.time(),
            "expires_at": 0,
            "origin_signature": "origin_sig",
        }
        pp_file = tmp_path / "passport.json"
        pp_file.write_text(json.dumps(passport))

        call_count = {"validate": 0, "activate": 0}

        def mock_server(action, data):
            call_count[action] = call_count.get(action, 0) + 1
            if action == "validate":
                return True, {"valid": True}
            if action == "activate":
                return True, {
                    "ok": True,
                    "account_id": "fg_flow_123",
                    "master_id": "my_machine",
                    "tier": "power",
                    "seat_count": 10,
                    "telemetry_token": "fg_master_token",
                    "tier_config": {"seats": 10},
                }
            return False, "unknown"

        pm._server_request = mock_server

        ok, msg = pm.activate_master(str(pp_file))
        assert ok is True
        assert pm.role == PuppetRole.MASTER
        assert pm.account_id == "fg_flow_123"
        assert pm.seats_total == 10
        assert call_count["validate"] == 1
        assert call_count["activate"] == 1

    def test_activation_persists(self, tmp_path):
        """After activation, reloading PuppetManager preserves state."""
        pm1 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm1._role = PuppetRole.MASTER
        pm1._account_id = "fg_persist"
        pm1._master_tier = "pro"
        pm1._seats_total = 3
        pm1._telemetry_token = "tok"
        pm1._save()

        pm2 = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        assert pm2.role == PuppetRole.MASTER
        assert pm2.account_id == "fg_persist"
        assert pm2.master_tier == "pro"
        assert pm2.seats_total == 3


class TestPuppetGenerationFlow:
    """Verifies generate_puppet_passport() creates passport files with correct fields and seat tracking.

    Generated passport has role='puppet', puppet_name, master_id, account_id, seat_count=0
    (puppets cannot sub-distribute). Each generation increments _seats_used. With seats_total=3
    (1 master + 2 puppet), third generation returns None. Passport includes parent_passport_id,
    master_id, master_signature for chain-of-trust verification.
    """

    def test_generate_creates_file(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._account_id = "fg_gen_test"
        pm._master_tier = "pro"
        pm._seats_total = 3
        pm._seats_used = 0
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "master_sig"

        # Mock server (registration may fail offline — still works)
        pm._server_request = lambda a, d: (False, "offline")

        path = pm.generate_puppet_passport("DevBox")
        assert path is not None
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["role"] == "puppet"
        assert data["puppet_name"] == "DevBox"
        assert data["master_id"] == "cap1"
        assert data["account_id"] == "fg_gen_test"
        assert data["seat_count"] == 0  # Puppets cannot distribute

    def test_generate_increments_seats(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._account_id = "fg_seats"
        pm._master_tier = "pro"
        pm._seats_total = 3  # 1 master + 2 puppet seats
        pm._seats_used = 0
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "sig"
        pm._server_request = lambda a, d: (False, "offline")

        pm.generate_puppet_passport("Box1")
        assert pm._seats_used == 1

        pm.generate_puppet_passport("Box2")
        assert pm._seats_used == 2

        # Third should fail (only 2 puppet seats)
        path = pm.generate_puppet_passport("Box3")
        assert path is None

    def test_puppet_passport_has_master_chain(self, tmp_path):
        pm = PuppetManager(
            data_dir=tmp_path / "data", machine_id="cap1")
        pm._role = PuppetRole.MASTER
        pm._account_id = "fg_chain"
        pm._passport_id = "pp_master_xyz"
        pm._master_tier = "power"
        pm._seats_total = 10
        pm._seats_used = 0
        pm._bpos = MagicMock()
        pm._bpos._sign_passport.return_value = "chain_sig"
        pm._server_request = lambda a, d: (False, "offline")

        path = pm.generate_puppet_passport("ChainTest")
        data = json.loads(path.read_text())
        assert data["parent_passport_id"] == "pp_master_xyz"
        assert data["master_id"] == "cap1"
        assert data["master_signature"] == "chain_sig"


class TestTierFetching:
    """Verifies tier config fallback when license server is unavailable.

    _FALLBACK_TIERS has community/pro/power with seats 1/3/10. TIERS module variable
    works for backward compat. get_tiers() returns a dict with >=3 tiers (uses fallback
    when server is not running).
    """

    def test_fallback_tiers_available(self):
        from forge.passport import _FALLBACK_TIERS
        assert "community" in _FALLBACK_TIERS
        assert "pro" in _FALLBACK_TIERS
        assert "power" in _FALLBACK_TIERS

    def test_fallback_tiers_have_seats(self):
        from forge.passport import _FALLBACK_TIERS
        assert _FALLBACK_TIERS["community"]["seats"] == 1
        assert _FALLBACK_TIERS["pro"]["seats"] == 3
        assert _FALLBACK_TIERS["power"]["seats"] == 10

    def test_tiers_backward_compat(self):
        """TIERS module-level variable still works."""
        from forge.passport import TIERS
        assert isinstance(TIERS, dict)
        assert "community" in TIERS

    def test_get_tiers_returns_dict(self):
        from forge.passport import get_tiers, _FALLBACK_TIERS
        # Will use fallback since server is not running
        import forge.passport as pp
        pp._cached_tiers = None  # Reset cache
        tiers = get_tiers()
        assert isinstance(tiers, dict)
        assert len(tiers) >= 3
        pp._cached_tiers = None  # Clean up


class TestPassportV2Fields:
    """Verifies Passport dataclass v2 fields and backward compatibility defaults.

    v2 Passport with role, passport_id, origin_signature, seat_count → all accessible.
    Old-style Passport (no v2 fields) → role='', passport_id='', max_activations=1.
    """

    def test_passport_has_v2_fields(self):
        from forge.passport import Passport
        p = Passport(
            account_id="fg_test",
            tier="pro",
            issued_at=time.time(),
            expires_at=0,
            role="master",
            passport_id="pp_test",
            origin_signature="sig",
            seat_count=3,
        )
        assert p.role == "master"
        assert p.passport_id == "pp_test"
        assert p.origin_signature == "sig"
        assert p.seat_count == 3

    def test_passport_backward_compat(self):
        """Old-style passport still works."""
        from forge.passport import Passport
        p = Passport(
            account_id="old_acct",
            tier="community",
            issued_at=time.time(),
            expires_at=0,
        )
        assert p.role == ""
        assert p.passport_id == ""
        assert p.max_activations == 1
