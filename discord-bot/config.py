"""Forge NC Discord bot configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
FORGE_API_URL = os.getenv("FORGE_API_URL", "https://forge-nc.dev")
FORGE_API_TOKEN = os.getenv("FORGE_API_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))

# Brand colors (Monokai theme)
CYAN = 0x66D9EF
GREEN = 0xA6E22E
DARK_BG = 0x272822
ORANGE = 0xFD971F
RED = 0xF92672
YELLOW = 0xE6DB74

# Server structure
CATEGORIES = {
    "WELCOME": ["rules", "introductions", "announcements"],
    "PRODUCT": ["general", "feature-requests", "bug-reports", "showcase"],
    "CERTIFIED AUDITS": ["audit-discussion", "audit-results", "enterprise-inquiries"],
    "TECHNICAL": ["self-hosted-support", "api-integration", "model-compatibility"],
    "COMMUNITY": ["off-topic", "ai-news", "memes"],
}

# Read-only channels (only bot + admins can post)
READ_ONLY_CHANNELS = {"rules", "announcements", "audit-results"}

# Roles in hierarchy order (top = highest)
ROLES = {
    "Origin": {"color": 0xE74C3C, "hoist": True},
    "Forge Team": {"color": 0xFD971F, "hoist": True},
    "Testee": {"color": 0x4E96B9, "hoist": True},
    "Certified": {"color": 0xA6E22E, "hoist": True},
    "Power": {"color": 0x66D9EF, "hoist": True},
    "Pro": {"color": 0xAE81FF, "hoist": True},
    "Community": {"color": 0x75715E, "hoist": False},
}

# Anti-spam: max messages per user per window
SPAM_MAX_MESSAGES = 5
SPAM_WINDOW_SECONDS = 10
SPAM_TIMEOUT_MINUTES = 5
