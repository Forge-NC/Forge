"""Tests for PII/secret detection patterns in Crucible."""

import pytest
from forge.crucible import Crucible, ThreatLevel


@pytest.fixture
def crucible():
    c = Crucible(enabled=True)
    return c


class TestAWSAccessKey:
    def test_positive_match(self, crucible):
        content = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "aws_access_key" for t in threats)

    def test_negative_no_match(self, crucible):
        content = 'AKIANOTLONG'  # Too short
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "aws_access_key" for t in threats)


class TestGitHubToken:
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
    def test_positive_match(self, crucible):
        content = 'api_key = "sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890abcdefgh"'
        threats = crucible.scan_content("test.py", content)
        assert any(t.pattern_name == "openai_api_key" for t in threats)

    def test_short_sk_no_match(self, crucible):
        content = 'sk-short'  # Under 20 chars after sk-
        threats = crucible.scan_content("test.py", content)
        assert not any(t.pattern_name == "openai_api_key" for t in threats)


class TestSSHPrivateKey:
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
