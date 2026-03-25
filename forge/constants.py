"""Forge — Global constants.

Single source of truth for server URLs and other values
that must be consistent across the codebase.
"""

# ── Forge NC Server ──────────────────────────────────────────────────────────
# Base URL for all Forge NC services. Every endpoint derives from this.
FORGE_SERVER = "https://forge-nc.dev"

# API endpoints (derived from base)
TELEMETRY_URL       = f"{FORGE_SERVER}/telemetry_receiver.php"
ASSURANCE_URL       = f"{FORGE_SERVER}/assurance_verify.php"
CHALLENGE_URL       = f"{FORGE_SERVER}/challenge_server.php"
PASSPORT_API_URL    = f"{FORGE_SERVER}/passport_api.php"
TOKEN_ADMIN_URL     = f"{FORGE_SERVER}/token_admin.php"
SIGNATURES_URL      = f"{FORGE_SERVER}/signatures.json"
