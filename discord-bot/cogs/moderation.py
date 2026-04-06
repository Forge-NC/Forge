"""Auto-moderation + auto-role assignment for linked Forge accounts."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

import config
from forge_api import ForgeAPI

log = logging.getLogger("forge.moderation")

# Forge tier -> Discord role name
TIER_ROLE_MAP = {
    "community": "Community",
    "pro": "Pro",
    "power": "Power",
    "origin": "Origin",
}


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = ForgeAPI()
        self._msg_history = defaultdict(list)  # {user_id: [datetime, ...]}

    async def cog_unload(self):
        await self.api.close()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Auto-assign role based on linked Forge account, or Community."""
        guild = member.guild

        # Check if this Discord user has a linked Forge account
        try:
            linked = await self.api.get_linked_account(str(member.id))
            if linked and linked.get("ok"):
                roles_to_add = []

                # Tier role
                tier = linked.get("tier", "community")
                role_name = TIER_ROLE_MAP.get(tier, "Community")
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    roles_to_add.append(role)

                # Admin on website = Forge Team on Discord
                forge_role = linked.get("role", "standalone")
                is_admin = linked.get("is_admin", False)
                if forge_role == "origin":
                    for rn in ("Origin", "Forge Team"):
                        r = discord.utils.get(guild.roles, name=rn)
                        if r:
                            roles_to_add.append(r)
                elif is_admin:
                    r = discord.utils.get(guild.roles, name="Forge Team")
                    if r:
                        roles_to_add.append(r)

                # Certified
                if linked.get("has_certified_audits"):
                    r = discord.utils.get(guild.roles, name="Certified")
                    if r:
                        roles_to_add.append(r)

                if roles_to_add:
                    await member.add_roles(*roles_to_add)
                    names = [r.name for r in roles_to_add]
                    log.info("Auto-assigned %s to %s (linked Forge account)", names, member)
                return
        except Exception as e:
            log.warning("Failed to check linked account for %s: %s", member, e)

        # Fallback: assign Community
        role = discord.utils.get(guild.roles, name="Community")
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Staff bypass
        if any(
            r.name in ("Origin", "Forge Team") for r in message.author.roles
        ):
            return

        # --- Spam detection ---
        now = datetime.now(timezone.utc)
        window = now - timedelta(seconds=config.SPAM_WINDOW_SECONDS)
        history = self._msg_history[message.author.id]
        history.append(now)
        self._msg_history[message.author.id] = [t for t in history if t > window]

        if len(self._msg_history[message.author.id]) > config.SPAM_MAX_MESSAGES:
            try:
                await message.author.timeout(
                    timedelta(minutes=config.SPAM_TIMEOUT_MINUTES),
                    reason="Auto-mod: spam detection",
                )
                await message.channel.send(
                    f"{message.author.mention} timed out for "
                    f"{config.SPAM_TIMEOUT_MINUTES} min (spam).",
                    delete_after=15,
                )
                log.info(
                    "Timed out %s for spam in #%s",
                    message.author,
                    message.channel.name,
                )
            except discord.Forbidden:
                pass
            self._msg_history[message.author.id] = []
            return

        # --- Duplicate message detection ---
        if len(self._msg_history[message.author.id]) >= 3:
            recent = []
            async for msg in message.channel.history(limit=6):
                if msg.author.id == message.author.id:
                    recent.append(msg.content)
            dupes = sum(1 for c in recent if c == message.content)
            if dupes >= 3:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} please don't repeat messages.",
                        delete_after=10,
                    )
                except discord.Forbidden:
                    pass
                return

        # --- Discord invite link filter ---
        if "discord.gg/" in message.content.lower():
            if message.channel.name not in ("off-topic", "memes"):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} invite links aren't allowed here.",
                        delete_after=10,
                    )
                except discord.Forbidden:
                    pass
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
