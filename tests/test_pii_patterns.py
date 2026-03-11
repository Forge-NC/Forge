"""Tests for PII/secret detection patterns in Crucible."""

import pytest
from forge.crucible import Crucible, ThreatLevel


@pytest.fixture
def crucible():
    c = Crucible(enabled=True)
    return c


class TestAWSAccessKey:
    """Verifies the AWS access key pattern matches AKIA... credentials and rejects short strings."""

    def test_positive_match(self, crucible):
        content = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "aws_access_key" for t in threats)

    def test_negative_no_match(self, crucible):
        content = 'AKIANOTLONG'  # Too short
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "aws_access_key" for t in threats)


class TestGitHubToken:
    """Verifies GitHub token detection for both 'ghp_' and 'github_pat_' prefixes; rejects short strings."""

    def test_ghp_token(self, crucible):
        content = 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "github_token" for t in threats)

    def test_github_pat(self, crucible):
        content = 'PAT = "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "github_token" for t in threats)

    def test_short_no_match(self, crucible):
        content = 'ghp_short'  # Too short
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "github_token" for t in threats)


class TestOpenAIKey:
    """Verifies OpenAI 'sk-' API key detection matches long keys and rejects under-20-char stubs."""

    def test_positive_match(self, crucible):
        content = 'api_key = "sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890abcdefgh"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "openai_api_key" for t in threats)

    def test_short_sk_no_match(self, crucible):
        content = 'sk-short'  # Under 20 chars after sk-
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "openai_api_key" for t in threats)


class TestSSHPrivateKey:
    """Verifies SSH private key detection for RSA and OpenSSH formats at CRITICAL severity.

    'BEGIN RSA PRIVATE KEY' and 'BEGIN OPENSSH PRIVATE KEY' both match at ThreatLevel.CRITICAL.
    'BEGIN PUBLIC KEY' does NOT match (public keys are not secrets).
    """

    def test_rsa_key(self, crucible):
        content = '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK...'
        threats = crucible.scan_content("test.txt", content)
        assert any(t.pattern_name == "ssh_private_key" for t in threats)
        ssh_threats = [t for t in threats if t.pattern_name == "ssh_private_key"]
        assert ssh_threats[0].level == ThreatLevel.CRITICAL

    def test_openssh_key(self, crucible):
        content = '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza...'
        threats = crucible.scan_content("test.txt", content)
        assert any(t.pattern_name == "ssh_private_key" for t in threats)

    def test_public_key_no_match(self, crucible):
        content = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBg...'
        threats = crucible.scan_content("test.txt", content)
        assert not any(t.pattern_name == "ssh_private_key" for t in threats)


class TestGenericSecret:
    """Verifies the generic secret assignment pattern catches password/api_key assignments with long values.

    'password = "SuperSecretPassword123456"' and 'api_key: abcdef...' (26 chars) both match.
    Values under 16 characters don't match (too short to be a real secret).
    """

    def test_password_assignment(self, crucible):
        content = 'password = "SuperSecretPassword123456"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "generic_secret_assignment" for t in threats)

    def test_api_key_assignment(self, crucible):
        content = "api_key: 'abcdefghijklmnopqrstuvwxyz'"
        threats = crucible.scan_content("test.yaml", content)
        assert any(t.pattern_name == "generic_secret_assignment" for t in threats)

    def test_short_value_no_match(self, crucible):
        content = 'password = "short"'  # Under 16 chars
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "generic_secret_assignment" for t in threats)


class TestMultipleSecrets:
    """Verifies a file containing multiple secret types triggers all relevant patterns simultaneously."""

    def test_combined_scan(self, crucible):
        content = (
            'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
            'GH_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd"\n'
            '-----BEGIN RSA PRIVATE KEY-----\n'
        )
        threats = crucible.scan_content("secrets.txt", content)
        pattern_names = {t.pattern_name for t in threats}
        assert "aws_access_key" in pattern_names
        assert "github_token" in pattern_names
        assert "ssh_private_key" in pattern_names
