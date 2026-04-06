"""Forge NC Discord bot — entry point.

Usage:
    pip install -r requirements.txt
    cp .env.example .env   # fill in your tokens
    python bot.py
"""

import asyncio
import logging

import discord
from discord.ext import commands

import config
from cogs.welcome import RoleSelectView

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("forge.bot")

COGS = [
    "cogs.welcome",
    "cogs.audits",
    "cogs.moderation",
]


class ForgeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="AI model audits | forge-nc.dev",
            ),
        )

    async def setup_hook(self):
        # Load cogs
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("Loaded %s", cog)
            except Exception as e:
                log.error("Failed to load %s: %s", cog, e)

        # Register persistent views (survives restarts)
        self.add_view(RoleSelectView())

        # Sync slash commands to the guild for instant availability
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to guild %d", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Synced commands globally (may take up to 1 hour)")

    async def on_ready(self):
        log.info("Logged in as %s (ID: %d)", self.user, self.user.id)
        log.info("Guilds: %d | Latency: %.0fms", len(self.guilds), self.latency * 1000)


def main():
    if not config.DISCORD_TOKEN:
        print("ERROR: Set DISCORD_TOKEN in .env file")
        print("  cp .env.example .env")
        print("  Then edit .env with your bot token from discord.com/developers")
        return

    bot = ForgeBot()
    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
