"""Tests verifying SHA-512 upgrade across Forge subsystems."""

import hashlib
import pytest


class TestAuditSHA512:
    def test_manifest_uses_sha512(self):
        """Verify audit.py uses sha512 for file hashes."""
        from forge.audit import AuditExporter
        import inspect
        source = inspect.getsource(AuditExporter.export)
        assert "sha512" in source
        assert "sha256" not in source

    def test_hash_prefix_format(self):
        """Verify hash format is sha512:{hex}."""
        from forge.audit import AuditExporter
        import inspect
        source = inspect.getsource(AuditExporter.export)
        assert 'sha512:' in source


class TestBugReporterSHA512:
    def test_fingerprint_uses_sha512(self):
        """Verify CrashFingerprint uses sha512."""
        from forge.bug_reporter import CrashFingerprint
        fp = CrashFingerprint(
            exc_type="KeyError",
            forge_frame="engine.py",
            function="test_func",
            normalized_msg="test message",
        )
        # Compute expected hash
        data = "KeyError|engine.py|test_func|test message"
        expected = hashlib.sha512(data.encode()).hexdigest()[:16]
        assert fp.hash == expected


class TestProvenanceSHA512:
    def test_provenance_hmac_uses_sha512(self):
        """Verify provenance chain uses HMAC-SHA512."""
        from forge.crucible import Crucible
        c = Crucible(enabled=True)
        c.record_provenance("read_file", {"path": "test.py"})
        entry = c._provenance[0]
        # SHA-512 hex digest is 128 chars
        assert len(entry["hmac"]) == 128

    def test_provenance_chain_hash_length(self):
        """Verify chain hash is 64 bytes (SHA-512)."""
        from forge.crucible import Crucible
        c = Crucible(enabled=True)
        c.record_provenance("read_file", {"path": "test.py"})
        # Internal chain hash should be 64 bytes
        assert len(c._provenance_chain_hash) == 64
