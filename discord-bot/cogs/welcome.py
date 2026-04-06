"""Welcome system — greeting DMs, role selection, license verification."""

import discord
from discord import app_commands
from discord.ext import commands

import config
from forge_api import ForgeAPI


class RoleSelectView(discord.ui.View):
    """Persistent dropdown for self-assigning Community role (unverified users)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        cls=discord.ui.Select,
        custom_id="forge_role_select",
        placeholder="Select your tier...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Community",
                description="Free tier — open source, local-only",
                emoji="\u2699\ufe0f",
                value="Community",
            ),
            discord.SelectOption(
                label="Pro",
                description="Pro license holder — use /verify to confirm",
                emoji="\u26a1",
                value="Pro",
            ),
            discord.SelectOption(
                label="Power",
                description="Power license holder — use /verify to confirm",
                emoji="\U0001f525",
                value="Power",
            ),
        ],
    )
    async def on_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        chosen = select.values[0]
        guild = interaction.guild
        if guild is None:
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Pro and Power require verification
        if chosen in ("Pro", "Power"):
            await interaction.response.send_message(
                f"**{chosen}** requires license verification.\n"
                f"Run `/verify` with your Forge passport to get the role automatically.",
                ephemeral=True,
            )
            return

        # Community is free — anyone can self-assign
        tier_roles = {"Community", "Pro", "Power"}
        to_remove = [r for r in member.roles if r.name in tier_roles]
        if to_remove:
            await member.remove_roles(*to_remove)

        role = discord.utils.get(guild.roles, name="Community")
        if role:
            await member.add_roles(role)
            await interaction.response.send_message(
                f"You now have the **Community** role. "
                f"If you have a Pro or Power license, use `/verify` to upgrade.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Role not found. Contact a Forge Team member.", ephemeral=True
            )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = ForgeAPI()

    async def cog_unload(self):
        await self.api.close()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """DM new members with a welcome message and point them to #rules."""
        embed = discord.Embed(
            title="Welcome to Forge Neural Cortex",
            description=(
                f"Hey {member.mention} — welcome to the **Forge NC** community.\n\n"
                "Forge is a local-first AI coding assistant and auditing platform "
                "that stress-tests language models and generates cryptographically "
                "signed reliability reports.\n\n"
                "**Get started:**\n"
                "1. Read the rules in **#rules**\n"
                "2. Link your Forge account at [Dashboard > Settings](https://forge-nc.dev/dashboard/settings) to get your tier role automatically\n"
                "3. Introduce yourself in **#introductions**"
            ),
            color=config.CYAN,
        )
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else "")
        embed.set_footer(text="forge-nc.dev | AI you can verify, not just trust.")

        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        channel = discord.utils.get(member.guild.text_channels, name="introductions")
        if channel:
            await channel.send(
                f"Welcome {member.mention}! Tell us what you're working on "
                f"and what models you're running."
            )

    # ── /verify — license-based role assignment ──────────────────────

    @app_commands.command(
        name="verify",
        description="Verify your Forge license and get your tier role automatically",
    )
    @app_commands.describe(
        account_id="Your Forge account ID (fg_...) from your passport file",
    )
    async def verify(self, interaction: discord.Interaction, account_id: str):
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild = interaction.guild
        if not isinstance(member, discord.Member) or guild is None:
            return

        # Validate the account via passport API
        try:
            # Check fleet info which returns tier
            data = await self.api.validate_account(account_id)
        except Exception as e:
            await interaction.followup.send(
                f"Could not verify account `{account_id}`. "
                f"Make sure you're using your Forge account ID (starts with `fg_`).\n"
                f"Error: {e}",
                ephemeral=True,
            )
            return

        if not data.get("ok"):
            await interaction.followup.send(
                f"Verification failed: {data.get('error', 'Unknown error')}",
                ephemeral=True,
            )
            return

        tier = data.get("tier", "community").capitalize()
        if tier not in ("Community", "Pro", "Power"):
            tier = "Community"

        # Remove existing tier roles
        tier_roles = {"Community", "Pro", "Power"}
        to_remove = [r for r in member.roles if r.name in tier_roles]
        if to_remove:
            await member.remove_roles(*to_remove)

        # Assign verified tier
        role = discord.utils.get(guild.roles, name=tier)
        if role:
            await member.add_roles(role)

        # Also check if they have certified audits
        certified_role = discord.utils.get(guild.roles, name="Certified")
        if data.get("has_certified_audits") and certified_role:
            if certified_role not in member.roles:
                await member.add_roles(certified_role)

        embed = discord.Embed(
            title="Verification Complete",
            description=(
                f"**Account:** `{account_id}`\n"
                f"**Tier:** {tier}\n"
                f"**Seats:** {data.get('seats_used', 0)}/{data.get('seats_total', 1)}"
            ),
            color=config.GREEN,
        )
        if data.get("has_certified_audits"):
            embed.add_field(
                name="Certified",
                value="You also received the **Certified** role.",
                inline=False,
            )
        embed.set_footer(text="forge-nc.dev | Verified")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /grant-role — admin manual role assignment ───────────────────

    @app_commands.command(
        name="grant-role",
        description="Manually assign a role to a member (admin only)",
    )
    @app_commands.describe(
        member="The member to assign the role to",
        role="The role to assign",
    )
    @app_commands.default_permissions(administrator=True)
    async def grant_role(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ):
        try:
            await member.add_roles(role)
            await interaction.response.send_message(
                f"Assigned **{role.name}** to {member.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"Can't assign **{role.name}** — check role hierarchy.", ephemeral=True
            )



async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
