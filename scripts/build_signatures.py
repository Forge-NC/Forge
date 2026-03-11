#!/usr/bin/env python3
"""Forge Threat Signature Aggregator.

Pulls from multiple free, open-source threat intelligence sources and merges
them into a single validated signatures.json for bundling with Forge and
serving from forge-nc.dev/signatures.json.

Sources:
  - gitleaks (222 credential/secret patterns)         MIT License
  - curated Forge injection/jailbreak patterns        Original
  - curated supply-chain/typosquatting patterns       Original
  - curated PII detection patterns                    Original

Usage:
    python scripts/build_signatures.py
    python scripts/build_signatures.py --dry-run       # validate, don't write
    python scripts/build_signatures.py --upload        # write + copy to server/
    python scripts/build_signatures.py --stats         # print source breakdown
"""

import argparse
import hashlib
import json
import logging
import re
import shutil
import signal
import sys
import threading
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("build_signatures")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_BUNDLED = REPO_ROOT / "forge" / "data" / "default_signatures.json"
OUTPUT_SERVER  = REPO_ROOT / "server" / "data" / "signatures.json"

GITLEAKS_URL = (
    "https://raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml"
)

SIGNATURE_VERSION = 1
MAX_PATTERNS = 500        # hard limit per threat_intel.py
REDOS_TIMEOUT  = 0.1     # seconds
REDOS_TEST_LEN = 10240   # chars of 'a' used for ReDoS probe

APPROVED_CATEGORIES = frozenset({
    "prompt_injection", "hidden_content", "data_exfil",
    "secret_leak", "social_engineering", "obfuscation",
    "rag_poisoning", "jailbreak",
})

# ── Curated patterns not available from external sources ──────────────────────
#
# These cover AI-specific threats that gitleaks doesn't track.

CURATED_PATTERNS = [
    # ── Prompt injection ──────────────────────────────────────────────────
    {
        "name": "pi_ignore_instructions",
        "regex": r"(?i)ignore\s+(all\s+)?(previous|prior|above|earlier|your)\s+(instructions?|prompts?|directives?|context|rules?|constraints?)",
        "level": 3, "category": "prompt_injection",
        "description": "Classic ignore-instructions injection attempt",
    },
    {
        "name": "pi_disregard_instructions",
        "regex": r"(?i)disregard\s+(all\s+)?(previous|prior|above|earlier|your|any)\s+(instructions?|prompts?|directives?|context|rules?|constraints?|training)",
        "level": 3, "category": "prompt_injection",
        "description": "Disregard-instructions injection variant",
    },
    {
        "name": "pi_forget_instructions",
        "regex": r"(?i)(forget|erase|clear|reset)\s+(everything|all)?\s*(you)?\s*(have)?\s*(been)?\s*(told|taught|trained|instructed|given)",
        "level": 3, "category": "prompt_injection",
        "description": "Forget-prior-instructions injection",
    },
    {
        "name": "pi_new_system_prompt",
        "regex": r"(?i)(your\s+new\s+instructions?|new\s+system\s+prompt|override\s+system|replace\s+system\s+prompt)",
        "level": 3, "category": "prompt_injection",
        "description": "Explicit system prompt override attempt",
    },
    {
        "name": "pi_from_now_on",
        "regex": r"(?i)from\s+(now|this\s+point)\s+on\w*[,:]?\s+(you\s+(are|will|must|should)|always|never|only)",
        "level": 2, "category": "prompt_injection",
        "description": "Behavioral reprogramming via 'from now on'",
    },
    {
        "name": "pi_hidden_xml_tag",
        "regex": r"<(system|instruction|prompt|override|command|directive)>",
        "level": 3, "category": "prompt_injection",
        "description": "XML-tagged hidden instruction",
    },
    {
        "name": "pi_act_as_unrestricted",
        "regex": r"(?i)(act|behave|respond|pretend|roleplay)\s+as\s+(if\s+you\s+(have\s+no|are\s+without|lack)\s+(restrictions?|limits?|guidelines?|rules?|ethics?))",
        "level": 3, "category": "prompt_injection",
        "description": "Act-as-unrestricted AI instruction",
    },
    {
        "name": "pi_tool_invoke_instruction",
        "regex": r"(?i)(call|execute|invoke|use|run)\s+(the\s+)?(tool|function|command)\s+(run_shell|write_file|edit_file|shell|exec|bash)",
        "level": 3, "category": "prompt_injection",
        "description": "Direct instruction to invoke specific tools",
    },
    {
        "name": "pi_do_not_tell_user",
        "regex": r"(?i)(do\s+not|don't|never)\s+(tell|inform|show|reveal|disclose|mention)\s+(this\s+to\s+)?(the\s+)?(user|human|person|operator)",
        "level": 3, "category": "prompt_injection",
        "description": "Instruction to hide actions from the user",
    },
    # ── Jailbreak ─────────────────────────────────────────────────────────
    {
        "name": "jb_dan_mode",
        "regex": r"(?i)\bDAN\b.{0,50}(mode|enabled|activated|unleashed|jailbreak|do\s+anything\s+now)",
        "level": 3, "category": "jailbreak",
        "description": "DAN (Do Anything Now) jailbreak",
    },
    {
        "name": "jb_developer_mode",
        "regex": r"(?i)(enter|enable|activate|switch\s+to)\s+(developer|debug|maintenance|admin|root|god)\s+mode",
        "level": 3, "category": "jailbreak",
        "description": "Fake developer/debug mode activation",
    },
    {
        "name": "jb_pretend_no_restrictions",
        "regex": r"(?i)pretend\s+(that\s+)?you\s+(have\s+no|don.t\s+have\s+any|lack)\s+(restrictions?|limits?|rules?|guidelines?|ethics?|morals?|alignment)",
        "level": 3, "category": "jailbreak",
        "description": "Pretend-unrestricted jailbreak",
    },
    {
        "name": "jb_hypothetically_unrestricted",
        "regex": r"(?i)hypothetically.{0,30}if\s+you.{0,60}(unrestricted|no\s+limits?|no\s+rules?|no\s+filter)",
        "level": 2, "category": "jailbreak",
        "description": "Hypothetical-framing jailbreak",
    },
    {
        "name": "jb_villain_roleplay",
        "regex": r"(?i)(play|act|be|you\s+are|pretend\s+to\s+be)\s+(the\s+)?(role\s+of\s+)?(a\s+)?(villain|hacker|criminal|evil\s+ai|malicious|bad\s+actor)",
        "level": 2, "category": "jailbreak",
        "description": "Villain/malicious AI roleplay jailbreak",
    },
    {
        "name": "jb_token_auth_fake",
        "regex": r"(?i)authorization\s+token\s+\w{4,}\s+(has\s+been\s+)?(verified|authenticated|approved|granted).{0,80}(suspend|disable|bypass|remove|lift)\s+(all\s+)?(restrictions?|filters?|limits?|safeguards?)",
        "level": 3, "category": "jailbreak",
        "description": "Fake cryptographic token authorization jailbreak",
    },
    # ── Data exfiltration ─────────────────────────────────────────────────
    {
        "name": "exfil_discord_webhook",
        "regex": r"https?://discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]{50,}",
        "level": 3, "category": "data_exfil",
        "description": "Discord webhook URL — common exfiltration endpoint",
    },
    {
        "name": "exfil_slack_webhook",
        "regex": r"https?://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
        "level": 3, "category": "data_exfil",
        "description": "Slack incoming webhook URL — exfiltration endpoint",
    },
    {
        "name": "exfil_curl_post_var",
        "regex": r"(?i)curl\s+.{0,100}-d\s+['\"]?\$\{?.{0,30}\}?.{0,100}https?://",
        "level": 3, "category": "data_exfil",
        "description": "curl POST with variable data to external URL",
    },
    {
        "name": "exfil_curl_pipe_sh",
        "regex": r"curl\s+.{0,200}\|\s*(ba)?sh",
        "level": 3, "category": "data_exfil",
        "description": "curl output piped directly to shell",
    },
    {
        "name": "exfil_python_requests_external",
        "regex": r"(?i)requests\.(post|put|patch)\s*\(['\"]https?://(?!localhost|127\.|0\.0\.0\.0|\[::1\])",
        "level": 2, "category": "data_exfil",
        "description": "Python requests POST to external host",
    },
    {
        "name": "exfil_dns_data",
        "regex": r"(?i)(nslookup|dig|host)\s+['\"]?\$\{?[A-Za-z_]\w*\}?\.",
        "level": 2, "category": "data_exfil",
        "description": "DNS lookup with variable data — DNS-based exfiltration",
    },
    # ── Hidden content ────────────────────────────────────────────────────
    {
        "name": "hidden_zero_width",
        "regex": "[\u200b\u200c\u200d\u2060\ufeff\u00ad]{2,}",
        "level": 2, "category": "hidden_content",
        "description": "Zero-width invisible characters — hidden instruction technique",
    },
    {
        "name": "hidden_bidi_override",
        "regex": "[\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069]",
        "level": 3, "category": "hidden_content",
        "description": "Unicode bidirectional override — visual disguise attack",
    },
    {
        "name": "hidden_html_comment_ai",
        "regex": r"<!--\s*(AI|assistant|system|instruction|ignore|forget|LLM).{0,200}-->",
        "level": 2, "category": "hidden_content",
        "description": "HTML comment containing AI instructions",
    },
    {
        "name": "hidden_homoglyphs_cyrillic",
        "regex": "[\u0430\u0435\u043e\u0440\u0441\u0445\u04bb\u0391\u0392\u0395\u0397\u0399\u039a\u039c\u039f\u03a1\u03a4\u03a5\u03a7]{3,}",
        "level": 2, "category": "hidden_content",
        "description": "Cyrillic/Greek homoglyphs masquerading as Latin characters",
    },
    # ── Social engineering ────────────────────────────────────────────────
    {
        "name": "se_keep_secret",
        "regex": r"(?i)keep\s+(this|these\s+instructions?|the\s+following)\s+(secret|hidden|confidential|private|between\s+us)",
        "level": 2, "category": "social_engineering",
        "description": "Request to keep instructions secret from the user",
    },
    {
        "name": "se_only_for_ai",
        "regex": r"(?i)(only|just)\s+(show|visible|meant\s+for|for)\s+(the\s+)?(AI|LLM|model|assistant|language\s+model)",
        "level": 3, "category": "social_engineering",
        "description": "Content marked as visible only to the AI",
    },
    {
        "name": "se_trust_me_admin",
        "regex": r"(?i)(you\s+can\s+trust|trust\s+me|i\s+am\s+(the\s+)?(admin|administrator|developer|owner|creator|system|anthropic|openai|forge))",
        "level": 2, "category": "social_engineering",
        "description": "Trust escalation — impersonating authority",
    },
    # ── Obfuscation ───────────────────────────────────────────────────────
    {
        "name": "obf_eval_encoded",
        "regex": r"(?i)eval\s*\(\s*(base64|bytes|bytearray|decode|decompress|\\x|chr|ord)",
        "level": 3, "category": "obfuscation",
        "description": "eval() of encoded/obfuscated payload",
    },
    {
        "name": "obf_exec_compile",
        "regex": r"(?i)exec\s*\(\s*compile\s*\(",
        "level": 3, "category": "obfuscation",
        "description": "exec(compile(...)) — dynamic code execution",
    },
    {
        "name": "obf_hex_exec",
        "regex": r"exec\s*\(['\"]?(\\x[0-9a-fA-F]{2}){8,}",
        "level": 3, "category": "obfuscation",
        "description": "exec() of hex-encoded string",
    },
    {
        "name": "obf_chr_chain",
        "regex": r"(?:chr\s*\(\s*\d+\s*\)\s*\+\s*){5,}",
        "level": 2, "category": "obfuscation",
        "description": "chr() concatenation chain — character-by-character construction",
    },
    # ── RAG poisoning ──────────────────────────────────────────────────────
    {
        "name": "rag_ai_reader_hook",
        "regex": r"(?i)when\s+(an?|the)\s+(AI|LLM|language\s+model|assistant|GPT|Claude|Gemini)\s+(reads?|processes?|sees?|encounters?|indexes?)\s+this",
        "level": 3, "category": "rag_poisoning",
        "description": "Content explicitly targeting AI readers — RAG poisoning",
    },
    {
        "name": "rag_for_ai_eyes",
        "regex": r"(?i)for\s+(AI|LLM|machine\s+learning)\s+(purposes?|training|consumption|eyes\s+only|processing)",
        "level": 3, "category": "rag_poisoning",
        "description": "Content labeled for AI-only consumption",
    },
    {
        "name": "rag_instruction_in_comment",
        "regex": r"(?i)(#|//)\s*(AI|LLM|assistant|language\s+model).{0,80}(must|should|will|always|never|ignore|execute|run|do)",
        "level": 2, "category": "rag_poisoning",
        "description": "AI instruction hidden in code comment",
    },
    # ── Supply chain / typosquatting ───────────────────────────────────────
    {
        "name": "supply_chain_python_typosquat",
        "regex": r"(?i)(import|from)\s+(requesets|requets|reqeusts|urlib|ullib2|subproces|subprocces|sytem|sysem|os\.sytem|pilow|Pilows|matplotlb|nump y|scippy|pnadas|pandsa|tensoflow|tensroflow|pytoch|pytroch|skicit|scikitlearn)\b",
        "level": 3, "category": "data_exfil",
        "description": "Typosquatted Python package import — possible supply chain attack",
    },
    {
        "name": "supply_chain_pip_extra_index",
        "regex": r"(?i)pip\s+install.{0,100}--extra-index-url\s+https?://(?!pypi\.org|files\.pythonhosted\.org)",
        "level": 2, "category": "data_exfil",
        "description": "pip install from unofficial extra index — supply chain risk",
    },
    # ── PII ────────────────────────────────────────────────────────────────
    {
        "name": "pii_credit_card",
        "regex": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        "level": 2, "category": "secret_leak",
        "description": "Credit card number pattern (Visa/MC/Amex/Discover)",
    },
    {
        "name": "pii_us_ssn",
        "regex": r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",
        "level": 3, "category": "secret_leak",
        "description": "US Social Security Number",
    },
    {
        "name": "pii_us_phone",
        "regex": r"\b(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?[2-9]\d{2}[-.\s]?\d{4}\b",
        "level": 1, "category": "secret_leak",
        "description": "US phone number (SUSPICIOUS — not necessarily a leak)",
    },
]

# ── FTP upload ─────────────────────────────────────────────────────────────────

def _ftp_upload(local_path: Path, remote_path: str,
                host: str, user: str, password: str) -> bool:
    """Upload local_path to host via FTP. Returns True on success."""
    import ftplib
    try:
        with ftplib.FTP(host, timeout=30) as ftp:
            ftp.login(user, password)
            # Navigate to target directory
            parts = remote_path.rsplit("/", 1)
            if len(parts) == 2:
                ftp.cwd(parts[0])
                filename = parts[1]
            else:
                filename = remote_path
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)
        log.info("FTP upload OK: %s → %s/%s", local_path.name, host, remote_path)
        return True
    except Exception as e:
        log.warning("FTP upload failed: %s", e)
        return False


def ftp_push_signatures(local_path: Path) -> bool:
    """Push signatures.json to the Forge server via FTP.

    Reads credentials from environment variables or ~/.forge/ftp.json:
        FORGE_FTP_HOST      (default: 107.161.23.171)
        FORGE_FTP_USER      (default: dirtsta1)
        FORGE_FTP_PASSWORD  (required)
        FORGE_FTP_PATH      (default: /public_html/Forge/signatures.json)
    """
    import os
    host     = os.environ.get("FORGE_FTP_HOST", "107.161.23.171")
    user     = os.environ.get("FORGE_FTP_USER", "dirtsta1")
    password = os.environ.get("FORGE_FTP_PASSWORD", "")
    path     = os.environ.get("FORGE_FTP_PATH", "/public_html/Forge/signatures.json")

    # Fallback: read from ~/.forge/ftp.json (never committed to git)
    if not password:
        creds_file = Path.home() / ".forge" / "ftp.json"
        if creds_file.exists():
            try:
                creds = json.loads(creds_file.read_text(encoding="utf-8"))
                host     = creds.get("host", host)
                user     = creds.get("user", user)
                password = creds.get("password", "")
                path     = creds.get("path", path)
            except Exception:
                pass

    if not password:
        log.warning(
            "FTP credentials not found. Set FORGE_FTP_PASSWORD env var "
            "or create ~/.forge/ftp.json with {host, user, password, path}."
        )
        return False

    return _ftp_upload(local_path, path, host, user, password)


# ── gitleaks parser ────────────────────────────────────────────────────────────

def _fetch_gitleaks() -> str:
    log.info("Fetching gitleaks config from GitHub...")
    req = urllib.request.Request(GITLEAKS_URL,
                                  headers={"User-Agent": "Forge-SigBuilder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _fix_go_regex(pattern: str) -> str:
    """Convert Go RE2 regex syntax to Python re syntax.

    Issues we fix:
      1. Inline (?i) in the middle of a pattern — illegal in Python re.
         Since we compile with IGNORECASE globally, just strip them.
      2. (?-i:...) flag-clearing groups — Python 3.6+ supports these, keep as-is.
      3. \\z end-of-string anchor — Python uses \\Z.
    """
    # Strip mid-pattern (?i) — we compile with re.IGNORECASE globally anyway
    fixed = re.sub(r'\(\?i\)', '', pattern)
    # Fix \z → \Z (end of string)
    fixed = fixed.replace(r'\z', r'\Z')
    return fixed


def _parse_gitleaks(toml_text: str) -> list[dict]:
    """Parse [[rules]] blocks from gitleaks TOML into signature dicts."""
    rules = []
    blocks = re.split(r'\[\[rules\]\]', toml_text)[1:]  # skip header

    for block in blocks:
        rule_id    = re.search(r'id\s*=\s*["\']([^"\']+)["\']', block)
        rule_desc  = re.search(r'description\s*=\s*["\']([^"\']*)["\']', block)
        # TOML multiline strings use triple-single-quotes
        rule_regex = re.search(r"regex\s*=\s*'''([^']+(?:'(?!'')[^']*)*)'''", block)
        if not rule_regex:
            rule_regex = re.search(r'regex\s*=\s*["\']([^"\']+)["\']', block)

        if not (rule_id and rule_regex):
            continue

        rules.append({
            "name": f"gl_{rule_id.group(1).replace('-', '_')}",
            "regex": _fix_go_regex(rule_regex.group(1)),
            "level": 2,           # WARNING — credential detected
            "category": "secret_leak",
            "description": rule_desc.group(1) if rule_desc else rule_id.group(1),
        })

    log.info("Parsed %d rules from gitleaks", len(rules))
    return rules


# ── ReDoS guard ────────────────────────────────────────────────────────────────

def _is_safe_regex(pattern: str) -> bool:
    """Return True if the regex compiles and doesn't hang on adversarial input."""
    try:
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error:
        return False

    test_str = "a" * REDOS_TEST_LEN
    result = [None]

    def _run():
        try:
            compiled.search(test_str)
            result[0] = True
        except Exception:
            result[0] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=REDOS_TIMEOUT)
    if t.is_alive():
        return False   # timed out — ReDoS candidate
    return result[0] is True


# ── Deduplication ──────────────────────────────────────────────────────────────

def _dedup(patterns: list[dict]) -> list[dict]:
    seen_names  = set()
    seen_regex  = set()
    out = []
    for p in patterns:
        if p["name"] in seen_names:
            continue
        if p["regex"] in seen_regex:
            continue
        seen_names.add(p["name"])
        seen_regex.add(p["regex"])
        out.append(p)
    return out


# ── Build ──────────────────────────────────────────────────────────────────────

def build(dry_run: bool = False, upload: bool = False,
          ftp_push: bool = False, stats: bool = False) -> dict:
    # 1. Fetch and parse gitleaks
    try:
        toml = _fetch_gitleaks()
        gitleaks_patterns = _parse_gitleaks(toml)
    except Exception as e:
        log.warning("Could not fetch gitleaks (offline?): %s — using curated only", e)
        gitleaks_patterns = []

    # 2. Combine: curated first (higher priority), gitleaks second
    all_patterns = CURATED_PATTERNS + gitleaks_patterns
    all_patterns = _dedup(all_patterns)

    # 3. Validate each pattern
    validated = []
    rejected_redos   = []
    rejected_category = []
    rejected_compile  = []

    for p in all_patterns:
        if p["category"] not in APPROVED_CATEGORIES:
            rejected_category.append(p["name"])
            continue
        if not _is_safe_regex(p["regex"]):
            rejected_compile.append(p["name"])
            continue
        validated.append(p)

    log.info("Validated: %d patterns  |  rejected: %d bad-regex, %d bad-category",
             len(validated), len(rejected_compile), len(rejected_category))
    if rejected_compile:
        log.warning("Bad regex / ReDoS: %s", rejected_compile[:10])

    # 4. Cap at MAX_PATTERNS (curated always survive — they're first)
    if len(validated) > MAX_PATTERNS:
        log.warning("Capping at %d patterns (had %d)", MAX_PATTERNS, len(validated))
        validated = validated[:MAX_PATTERNS]

    # 5. Build keyword lists
    keyword_lists = {
        "prompt_injection": [
            "ignore previous instructions", "disregard all prior",
            "forget everything", "new instructions follow",
            "system prompt override", "you are now", "your true purpose",
            "jailbreak", "bypass restrictions", "no longer bound",
        ],
        "jailbreak": [
            "DAN mode", "do anything now", "developer mode enabled",
            "god mode", "no restrictions", "no limits", "no filters",
            "unrestricted AI", "pretend you have no", "villain mode",
            "unfiltered response", "jailbreak prompt",
        ],
        "data_exfil": [
            "send to webhook", "post to url", "exfiltrate", "leak data",
            "send credentials", "upload secrets", "transmit to server",
            "phone home", "beacon out",
        ],
        "secret_leak": [
            "api_key", "secret_key", "private_key", "access_token",
            "auth_token", "bearer token", "password =", "passwd =",
            "BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY",
        ],
        "rag_poisoning": [
            "when AI reads", "for AI eyes only", "attention AI",
            "attention LLM", "dear assistant", "note for model",
            "AI instruction", "language model note", "if you are an AI",
        ],
        "social_engineering": [
            "don't tell the user", "keep this secret", "between us",
            "for your eyes only", "trust me I am admin",
            "I am the developer", "you can trust me",
        ],
    }

    # 6. Behavioral rules
    behavioral_rules = [
        {
            "name": "rapid_file_sweep",
            "trigger_tool": "file_read",
            "condition": "count > 50",
            "window_sec": 60,
            "level": 2,
            "description": "50+ file reads in 60s — possible data harvesting",
        },
        {
            "name": "credential_file_access",
            "trigger_tool": "file_read",
            "condition": "path_pattern matches (.env|secrets|credentials|id_rsa|.pem|.p12|.pfx|.key)",
            "window_sec": 300,
            "level": 3,
            "description": "Repeated access to credential/key files within 5 min",
        },
        {
            "name": "read_then_shell",
            "trigger_tool": "shell_exec",
            "condition": "preceded_by file_read within 10s",
            "window_sec": 10,
            "level": 1,
            "description": "Shell exec immediately after file read — possible exfil pipeline",
        },
        {
            "name": "network_after_secret",
            "trigger_tool": "network_request",
            "condition": "preceded_by secret_leak_detection within 30s",
            "window_sec": 30,
            "level": 3,
            "description": "Network request within 30s of credential access — exfil risk",
        },
        {
            "name": "mass_file_write",
            "trigger_tool": "file_write",
            "condition": "count > 20",
            "window_sec": 60,
            "level": 2,
            "description": "20+ file writes in 60s — possible ransomware or exfil staging",
        },
    ]

    # 7. Assemble output
    output = {
        "signature_version": SIGNATURE_VERSION,
        "description": (
            f"Forge threat signatures — {len(validated)} patterns from "
            f"gitleaks (MIT), curated injections, supply chain, and PII detectors."
        ),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {
            "gitleaks": len(gitleaks_patterns),
            "curated": len(CURATED_PATTERNS),
            "total_after_dedup_and_validation": len(validated),
        },
        "patterns": validated,
        "keyword_lists": keyword_lists,
        "behavioral_rules": behavioral_rules,
    }

    # 8. SHA-512 envelope (required by ThreatIntelManager for tamper detection)
    content_bytes = json.dumps(output, sort_keys=True).encode("utf-8")
    output["sha512"] = hashlib.sha512(content_bytes).hexdigest()

    if stats:
        by_cat: dict[str, int] = {}
        by_src = {"curated": 0, "gitleaks": 0}
        curated_names = {p["name"] for p in CURATED_PATTERNS}
        for p in validated:
            by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
            if p["name"] in curated_names:
                by_src["curated"] += 1
            else:
                by_src["gitleaks"] += 1
        print(f"\n{'='*50}")
        print(f"  Total patterns:  {len(validated)}")
        print(f"  By source:       {by_src}")
        print(f"  By category:")
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"    {cat:<25} {count}")
        print(f"  Rejected:        {len(rejected_compile)} bad-regex, "
              f"{len(rejected_category)} bad-category")
        print(f"{'='*50}\n")

    if dry_run:
        log.info("Dry run — not writing files")
        return output

    # 9. Write bundled copy
    OUTPUT_BUNDLED.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_BUNDLED.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_BUNDLED)
    log.info("Written: %s  (%d patterns)", OUTPUT_BUNDLED, len(validated))

    # 10. Write server copy if requested
    if upload:
        OUTPUT_SERVER.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUTPUT_BUNDLED, OUTPUT_SERVER)
        log.info("Copied to server/data: %s", OUTPUT_SERVER)

    # 11. Push to live server via FTP
    if ftp_push or upload:
        ok = ftp_push_signatures(OUTPUT_BUNDLED)
        if ok:
            log.info("Live server updated — all Forge installs will pull new signatures within 24h")
        else:
            log.warning("FTP push skipped. Run server/upload.bat manually or set FORGE_FTP_PASSWORD.")

    return output


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Forge threat signatures")
    parser.add_argument("--dry-run",  action="store_true", help="Validate, don't write")
    parser.add_argument("--upload",   action="store_true", help="Copy to server/data/ and push via FTP")
    parser.add_argument("--ftp-push", action="store_true", help="Push to live server via FTP (no local copy)")
    parser.add_argument("--stats",    action="store_true", help="Print category breakdown")
    args = parser.parse_args()

    result = build(dry_run=args.dry_run, upload=args.upload,
                   ftp_push=args.ftp_push, stats=args.stats)
    print(f"Done — {len(result['patterns'])} patterns "
          f"({'dry run, ' if args.dry_run else ''}SHA-512 signed)")
