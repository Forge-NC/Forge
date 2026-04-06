"""One-time server setup — creates roles, categories, and channels.

Run as a slash command: /setup-server
Or standalone: python server_setup.py (uses bot token from .env)
"""

import discord
from discord import app_commands
from discord.ext import commands

import config


class ServerSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setup-server",
        description="Create all Forge NC roles, categories, and channels",
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_server(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Must be used in a server.")
            return

        await interaction.response.defer(thinking=True)
        log_lines: list[str] = []

        # ── 1. Create roles (bottom-up so hierarchy is correct) ──────

        existing_roles = {r.name: r for r in guild.roles}
        created_roles: dict[str, discord.Role] = {}

        # Reverse so highest role is created last (ends up on top)
        for role_name in reversed(list(config.ROLES.keys())):
            props = config.ROLES[role_name]
            if role_name in existing_roles:
                created_roles[role_name] = existing_roles[role_name]
                log_lines.append(f"Role `{role_name}` already exists, skipped")
            else:
                role = await guild.create_role(
                    name=role_name,
                    color=discord.Color(props["color"]),
                    hoist=props["hoist"],
                    mentionable=True,
                )
                created_roles[role_name] = role
                log_lines.append(f"Created role `{role_name}`")

        # ── 2. Create categories + channels ──────────────────────────

        existing_categories = {c.name: c for c in guild.categories}
        existing_channels = {c.name: c for c in guild.text_channels}

        # Default overwrites for read-only channels
        def _read_only_overwrites() -> dict:
            return {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False, add_reactions=True, read_messages=True
                ),
                guild.me: discord.PermissionOverwrite(
                    send_messages=True, manage_messages=True
                ),
            }

        for cat_name, channels in config.CATEGORIES.items():
            # Create or get category
            if cat_name in existing_categories:
                category = existing_categories[cat_name]
                log_lines.append(f"Category `{cat_name}` already exists")
            else:
                category = await guild.create_category(cat_name)
                log_lines.append(f"Created category `{cat_name}`")

            # Create channels in category
            for ch_name in channels:
                if ch_name in existing_channels:
                    log_lines.append(f"  Channel `#{ch_name}` already exists")
                    continue

                overwrites = (
                    _read_only_overwrites()
                    if ch_name in config.READ_ONLY_CHANNELS
                    else {}
                )

                # Topic descriptions
                topics = {
                    "rules": "Server rules and role selection",
                    "introductions": "Introduce yourself to the community",
                    "announcements": "Official Forge NC announcements",
                    "general": "General discussion about Forge and AI safety",
                    "feature-requests": "Request new Forge features",
                    "bug-reports": "Report bugs with reproduction steps",
                    "showcase": "Show off your audit results and integrations",
                    "audit-discussion": "Discuss audit methodology and results",
                    "audit-results": "Automated feed of completed certified audits",
                    "enterprise-inquiries": "Enterprise audit and licensing questions",
                    "self-hosted-support": "Help with self-hosted Forge deployments",
                    "api-integration": "Forge API and SDK integration help",
                    "model-compatibility": "Model compatibility and testing discussion",
                    "off-topic": "Anything goes (within reason)",
                    "ai-news": "AI industry news and papers",
                    "memes": "AI and dev memes",
                }

                channel = await guild.create_text_channel(
                    ch_name,
                    category=category,
                    topic=topics.get(ch_name, ""),
                    overwrites=overwrites,
                )
                log_lines.append(f"  Created `#{ch_name}`")

        # ── 3. Summary ───────────────────────────────────────────────

        embed = discord.Embed(
            title="Server Setup Complete",
            description="\n".join(log_lines),
            color=config.GREEN,
        )
        embed.add_field(
            name="Next Steps",
            value=(
                "1. Go to `#rules` and run `/post-rules` to post rules + role selector\n"
                "2. Drag roles into the correct hierarchy order in Server Settings\n"
                "3. Set the server icon and banner to Forge branding\n"
                "4. Configure the webhook on your Forge server (see README)"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerSetup(bot))
