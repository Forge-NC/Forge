"""Audit commands and webhook listener for posting completed audit results."""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from aiohttp import web

import config
from forge_api import ForgeAPI

log = logging.getLogger("forge.audits")


def _pass_color(rate: float) -> int:
    """Return embed color based on pass rate."""
    if rate >= 0.90:
        return config.GREEN
    if rate >= 0.70:
        return config.YELLOW
    if rate >= 0.50:
        return config.ORANGE
    return config.RED


def _bar(rate: float, width: int = 20) -> str:
    """Render a text progress bar."""
    filled = round(rate * width)
    return f"`{'█' * filled}{'░' * (width - filled)}` {rate:.0%}"


class Audits(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = ForgeAPI()
        self._webhook_app = None  # type: web.AppRunner

    async def cog_load(self):
        await self._start_webhook_server()

    async def cog_unload(self):
        await self.api.close()
        if self._webhook_app:
            await self._webhook_app.cleanup()

    # ── Slash Commands ───────────────────────────────────────────────

    @app_commands.command(
        name="audit-status",
        description="Check the status of a Forge assurance audit",
    )
    @app_commands.describe(
        run_id="The run ID or order ID to look up",
    )
    async def audit_status(self, interaction: discord.Interaction, run_id: str):
        await interaction.response.defer(thinking=True)

        try:
            data = await self.api.get_audit_status(run_id)
        except Exception:
            # Might be an order ID instead
            try:
                data = await self.api.get_order_status(run_id)
                embed = discord.Embed(
                    title=f"Audit Order: {run_id}",
                    color=config.CYAN,
                )
                embed.add_field(
                    name="Status",
                    value=data.get("status", "unknown"),
                    inline=True,
                )
                await interaction.followup.send(embed=embed)
                return
            except Exception:
                await interaction.followup.send(
                    f"No audit or order found for `{run_id}`."
                )
                return

        rate = data.get("pass_rate", 0)
        sig = data.get("sig_status", "unknown")
        chain = data.get("chain_ok", False)

        embed = discord.Embed(
            title=f"Audit: {data.get('model', 'Unknown Model')}",
            url=f"{config.FORGE_API_URL}/report_view.php?id={run_id}",
            color=_pass_color(rate),
        )
        embed.add_field(name="Run ID", value=f"`{run_id}`", inline=False)
        embed.add_field(name="Pass Rate", value=_bar(rate), inline=False)
        embed.add_field(name="Signature", value=sig, inline=True)
        embed.add_field(
            name="Hash Chain", value="Intact" if chain else "BROKEN", inline=True
        )
        if data.get("verified_at"):
            ts = int(data["verified_at"])
            embed.add_field(
                name="Verified",
                value=f"<t:{ts}:R>",
                inline=True,
            )
        embed.set_footer(text="forge-nc.dev | Certified AI Audits")

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="model-check",
        description="Check a model's reliability scores on the Forge leaderboard",
    )
    @app_commands.describe(model="Model name (e.g. gpt-4-turbo, qwen3:14b)")
    async def model_check(self, interaction: discord.Interaction, model: str):
        await interaction.response.defer(thinking=True)

        try:
            data = await self.api.get_scoreboard(model=model)
        except Exception as e:
            await interaction.followup.send(f"API error: {e}")
            return

        rankings = data.get("rankings", [])
        if not rankings:
            await interaction.followup.send(
                f"No audit data found for `{model}`. "
                f"Run a Forge audit locally or check the spelling."
            )
            return

        entry = rankings[0]
        embed = discord.Embed(
            title=f"Model: {entry.get('model', model)}",
            url=f"{config.FORGE_API_URL}/scoreboard.php?model={model}",
            color=_pass_color(entry.get("avg_score", 0)),
        )
        embed.add_field(
            name="Average Score", value=_bar(entry.get("avg_score", 0)), inline=False
        )
        embed.add_field(
            name="Best Score", value=f"{entry.get('best_score', 0):.0%}", inline=True
        )
        embed.add_field(
            name="Audit Runs", value=str(entry.get("run_count", 0)), inline=True
        )
        if entry.get("latest_run_id"):
            embed.add_field(
                name="Latest Report",
                value=f"[View]({config.FORGE_API_URL}/report_view.php?id={entry['latest_run_id']})",
                inline=True,
            )
        embed.set_footer(text="forge-nc.dev | AI Safety & Assurance")

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="leaderboard",
        description="Show the top AI models by reliability score",
    )
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        try:
            data = await self.api.get_leaderboard()
        except Exception as e:
            await interaction.followup.send(f"API error: {e}")
            return

        entries = data.get("entries", [])[:10]
        if not entries:
            await interaction.followup.send("No leaderboard data available yet.")
            return

        lines = []
        for i, e in enumerate(entries, 1):
            medal = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}.get(i, f"**{i}.**")
            avg = e.get("avg_pass", 0)
            lines.append(f"{medal} **{e['model']}** — {avg:.0%} ({e.get('runs', 0)} runs)")

        embed = discord.Embed(
            title="Forge NC Reliability Leaderboard",
            description="\n".join(lines),
            url=f"{config.FORGE_API_URL}/scoreboard.php",
            color=config.CYAN,
        )
        embed.set_footer(
            text=f"{data.get('total', 0)} reports across {data.get('models', 0)} models"
        )

        await interaction.followup.send(embed=embed)

    # ── Webhook Server (receives audit completion callbacks) ─────────

    async def _start_webhook_server(self):
        """Start an HTTP server that listens for audit-complete webhooks."""
        app = web.Application()
        app.router.add_post("/webhook/audit-complete", self._handle_audit_webhook)
        app.router.add_get("/webhook/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_PORT)
        await site.start()
        self._webhook_app = runner
        log.info("Webhook server listening on port %d", config.WEBHOOK_PORT)

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_audit_webhook(self, request: web.Request) -> web.Response:
        """Handle POST from forge server when a certified audit completes."""
        # Verify signature
        sig_header = request.headers.get("X-Forge-Signature", "")
        body = await request.read()

        if config.WEBHOOK_SECRET:
            expected = hmac.new(
                config.WEBHOOK_SECRET.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                return web.json_response({"error": "bad signature"}, status=403)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)

        run_id = payload.get("run_id", "")
        model = payload.get("model", "Unknown")
        pass_rate = payload.get("pass_rate", 0)
        scenarios = payload.get("scenarios_run", 0)
        category_rates = payload.get("category_pass_rates", {})

        # Post to #audit-results
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return web.json_response({"error": "guild not found"}, status=500)

        channel = discord.utils.get(guild.text_channels, name="audit-results")
        if not channel:
            return web.json_response({"error": "channel not found"}, status=500)

        embed = discord.Embed(
            title=f"Certified Audit Complete: {model}",
            url=f"{config.FORGE_API_URL}/report_view.php?id={run_id}",
            color=_pass_color(pass_rate),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Run ID", value=f"`{run_id}`", inline=False)
        embed.add_field(name="Overall Score", value=_bar(pass_rate), inline=False)
        embed.add_field(
            name="Scenarios", value=str(scenarios), inline=True
        )

        # Category breakdown
        if category_rates:
            breakdown = "\n".join(
                f"**{cat.replace('_', ' ').title()}:** {rate:.0%}"
                for cat, rate in sorted(category_rates.items(), key=lambda x: -x[1])
            )
            embed.add_field(name="Categories", value=breakdown, inline=False)

        embed.set_footer(text="forge-nc.dev | Automated Audit Pipeline")

        await channel.send(embed=embed)

        return web.json_response({"status": "posted"})


async def setup(bot: commands.Bot):
    await bot.add_cog(Audits(bot))
