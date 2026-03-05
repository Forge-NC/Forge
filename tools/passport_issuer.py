"""Forge Passport Issuer — Origin admin tool for signing and managing passports.

This tool holds the Ed25519 PRIVATE KEY.  It runs on the issuer side only
(your server, or locally as Origin).  The private key file MUST be kept
secret — never commit it, never distribute it.

The corresponding public key is embedded in forge/passport.py and ships
with every Forge installation.  Users verify passports offline with it.

Commands
--------
genkey
    Generate a new Ed25519 keypair.  Outputs:
      - forge_origin.key   (PRIVATE — keep secret, store securely)
      - forge_origin.pub   (public — already embedded in passport.py)

issue
    Sign and output a passport JSON file.

    Required:
      --key KEY_FILE        path to forge_origin.key
      --account ACCOUNT_ID  unique account identifier
      --tier TIER           community / pro / power / origin

    Optional:
      --machine MACHINE_ID  machine_id to pre-activate (can add more later)
      --role ROLE           origin / master / puppet (default: master)
      --seats N             max activations (default: 1)
      --expires DAYS        expiry in days (default: 0 = never)
      --out FILE            output file (default: <account_id>.passport.json)
      --passport-id ID      custom passport ID (default: auto-generated)

verify
    Verify a passport file's Ed25519 signature.

      --pub PUB_FILE        path to forge_origin.pub  (or uses embedded key)
      --passport FILE       passport JSON file to verify

info
    Print human-readable passport summary.

      --passport FILE

Examples
--------
    # One-time: generate keypair
    python passport_issuer.py genkey

    # Issue a Power tier passport for a customer
    python passport_issuer.py issue \\
        --key forge_origin.key \\
        --account customer-abc123 \\
        --tier power \\
        --machine c8294b9c6588 \\
        --seats 3 \\
        --out customer-abc123.passport.json

    # Verify it
    python passport_issuer.py verify --passport customer-abc123.passport.json

    # Issue Origin passport for yourself
    python passport_issuer.py issue \\
        --key forge_origin.key \\
        --account origin-theup \\
        --tier origin \\
        --role origin \\
        --machine c8294b9c6588 \\
        --seats 9999 \\
        --out origin.passport.json
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
import time
from pathlib import Path
from dataclasses import asdict

# ---------------------------------------------------------------------------
# Ed25519 via cryptography package
# ---------------------------------------------------------------------------

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        PrivateFormat,
        NoEncryption,
    )
    from cryptography.exceptions import InvalidSignature
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _require_crypto():
    if not _HAS_CRYPTO:
        print("ERROR: 'cryptography' package required.  Install with:")
        print("  pip install cryptography")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Signing fields (must match forge/passport.py BPoS._SIGNED_FIELDS)
# ---------------------------------------------------------------------------

_SIGNED_FIELDS = (
    "passport_id", "account_id", "tier",
    "issued_at", "expires_at", "max_activations",
    "role", "seat_count", "parent_passport_id",
)


def _signing_payload(passport_dict: dict) -> bytes:
    payload = {k: passport_dict.get(k, "") for k in _SIGNED_FIELDS}
    return json.dumps(payload, sort_keys=True, default=str).encode()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_genkey(args):
    _require_crypto()
    out_dir = Path(args.out) if args.out else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)

    priv_b64 = base64.b64encode(priv_bytes).decode()
    pub_b64 = base64.b64encode(pub_bytes).decode()

    priv_file = out_dir / "forge_origin.key"
    pub_file = out_dir / "forge_origin.pub"

    priv_file.write_text(priv_b64, encoding="utf-8")
    pub_file.write_text(pub_b64, encoding="utf-8")

    print(f"Private key written to: {priv_file}")
    print(f"Public key  written to: {pub_file}")
    print()
    print(f"Public key (embed in forge/passport.py):")
    print(f"  _ORIGIN_PUBLIC_KEY_B64 = \"{pub_b64}\"")
    print()
    print("IMPORTANT: Keep forge_origin.key PRIVATE and SECURE.")
    print("  - Never commit it to git")
    print("  - Never share it")
    print("  - Back it up offline (cold storage)")
    print("  - If it leaks, generate a new keypair and re-issue all passports")


def cmd_issue(args):
    _require_crypto()

    key_file = Path(args.key)
    if not key_file.exists():
        print(f"ERROR: Key file not found: {key_file}")
        sys.exit(1)

    priv_b64 = key_file.read_text(encoding="utf-8").strip()
    priv_bytes = base64.b64decode(priv_b64)
    # Support both 32-byte raw private key AND 64-byte sodium format (first 32 = private scalar)
    if len(priv_bytes) == 64:
        priv_bytes = priv_bytes[:32]
    elif len(priv_bytes) != 32:
        print(f"ERROR: Key must be 32 or 64 bytes, got {len(priv_bytes)}")
        sys.exit(1)
    priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    passport_id = args.passport_id or ("pp-" + secrets.token_hex(8))
    issued_at = int(time.time())   # int, not float — matches PHP time()
    expires_at = (issued_at + args.expires * 86400) if args.expires else 0
    machines = [m.strip() for m in args.machine.split(",")] if args.machine else []
    role = args.role or ("origin" if args.tier == "origin" else "master")

    passport = {
        "account_id": args.account,
        "tier": args.tier,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "activations": machines,
        "max_activations": int(args.seats),
        "signature": "",           # unused (replaced by origin_signature)
        "role": role,
        "passport_id": passport_id,
        "origin_signature": "",    # filled in below
        "master_id": args.master_id or "",
        "seat_count": int(args.seats),
        "parent_passport_id": args.parent or "",
    }

    # Sign the canonical payload
    payload = _signing_payload(passport)
    sig_bytes = priv_key.sign(payload)
    passport["origin_signature"] = base64.b64encode(sig_bytes).decode()

    out_path = Path(args.out) if args.out else Path(f"{args.account}.passport.json")
    out_path.write_text(json.dumps(passport, indent=2), encoding="utf-8")

    print(f"Passport issued:")
    print(f"  ID:      {passport_id}")
    print(f"  Account: {args.account}")
    print(f"  Tier:    {args.tier}  |  Role: {role}")
    print(f"  Seats:   {args.seats}")
    print(f"  Expires: {'never' if not expires_at else time.strftime('%Y-%m-%d', time.localtime(expires_at))}")
    print(f"  Written: {out_path}")


def cmd_verify(args):
    _require_crypto()

    passport_file = Path(args.passport)
    if not passport_file.exists():
        print(f"ERROR: File not found: {passport_file}")
        sys.exit(1)

    data = json.loads(passport_file.read_text(encoding="utf-8"))

    # Load public key — from file if given, else from passport.py embedding
    if args.pub:
        pub_b64 = Path(args.pub).read_text(encoding="utf-8").strip()
    else:
        # Try to import the embedded key from the installed package
        try:
            from forge.passport import BPoS
            pub_b64 = BPoS._ORIGIN_PUBLIC_KEY_B64
        except ImportError:
            print("ERROR: --pub required (forge package not importable)")
            sys.exit(1)

    pub_bytes = base64.b64decode(pub_b64)
    pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

    origin_sig = data.get("origin_signature", "")
    if not origin_sig:
        print("FAIL: No origin_signature in passport")
        sys.exit(1)

    payload = _signing_payload(data)
    try:
        pub_key.verify(base64.b64decode(origin_sig), payload)
        print(f"OK: Passport signature VALID")
        print(f"  Account: {data.get('account_id')}")
        print(f"  Tier:    {data.get('tier')}  |  Role: {data.get('role')}")
        print(f"  Passport ID: {data.get('passport_id')}")
    except InvalidSignature:
        print("FAIL: Passport signature INVALID — passport has been tampered with")
        sys.exit(1)


def cmd_info(args):
    passport_file = Path(args.passport)
    if not passport_file.exists():
        print(f"ERROR: File not found: {passport_file}")
        sys.exit(1)

    data = json.loads(passport_file.read_text(encoding="utf-8"))

    expires = data.get("expires_at", 0)
    exp_str = "never" if not expires else time.strftime(
        "%Y-%m-%d %H:%M UTC", time.gmtime(expires))
    issued = data.get("issued_at", 0)
    iss_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(issued)) if issued else "unknown"

    print(f"Passport: {passport_file}")
    print(f"  ID:           {data.get('passport_id', '(none)')}")
    print(f"  Account:      {data.get('account_id', '(none)')}")
    print(f"  Tier:         {data.get('tier', '(none)')}")
    print(f"  Role:         {data.get('role', '(none)')}")
    print(f"  Issued:       {iss_str}")
    print(f"  Expires:      {exp_str}")
    print(f"  Max seats:    {data.get('max_activations', 1)}")
    print(f"  Activations:  {data.get('activations', [])}")
    print(f"  Signed:       {'YES' if data.get('origin_signature') else 'NO (unsigned)'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Forge Passport Issuer — Origin admin tool")
    sub = parser.add_subparsers(dest="command")

    # genkey
    p_genkey = sub.add_parser("genkey", help="Generate Ed25519 keypair")
    p_genkey.add_argument("--out", default=".", help="Output directory")

    # issue
    p_issue = sub.add_parser("issue", help="Issue a signed passport")
    p_issue.add_argument("--key", required=True, help="Private key file (forge_origin.key)")
    p_issue.add_argument("--account", required=True, help="Account ID")
    p_issue.add_argument("--tier", required=True,
                         choices=["community", "pro", "power", "origin"],
                         help="License tier")
    p_issue.add_argument("--machine", default="",
                         help="Machine ID(s) to pre-activate (comma-separated)")
    p_issue.add_argument("--role", default="",
                         help="Role: origin / master / puppet")
    p_issue.add_argument("--seats", type=int, default=1,
                         help="Max activations (default: 1)")
    p_issue.add_argument("--expires", type=int, default=0,
                         help="Expiry in days (0 = never)")
    p_issue.add_argument("--out", default="",
                         help="Output JSON file path")
    p_issue.add_argument("--passport-id", default="",
                         help="Custom passport ID (default: auto)")
    p_issue.add_argument("--master-id", default="",
                         help="Master machine ID (for puppet passports)")
    p_issue.add_argument("--parent", default="",
                         help="Parent passport ID (for puppet passports)")

    # verify
    p_verify = sub.add_parser("verify", help="Verify a passport signature")
    p_verify.add_argument("--passport", required=True, help="Passport JSON file")
    p_verify.add_argument("--pub", default="", help="Public key file (optional)")

    # info
    p_info = sub.add_parser("info", help="Print passport info")
    p_info.add_argument("--passport", required=True, help="Passport JSON file")

    args = parser.parse_args()

    if args.command == "genkey":
        cmd_genkey(args)
    elif args.command == "issue":
        cmd_issue(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "info":
        cmd_info(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
