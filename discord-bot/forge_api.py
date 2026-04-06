"""Async client for the Forge NC API."""

import aiohttp
from config import FORGE_API_URL, FORGE_API_TOKEN


class ForgeAPI:
    """Thin async wrapper around forge-nc.dev endpoints."""

    def __init__(self):
        self._session = None  # type: aiohttp.ClientSession

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Forge-Token": FORGE_API_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # --- Public endpoints ---

    async def get_leaderboard(self) -> dict:
        """Fetch model reliability leaderboard."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/assurance_verify.php",
            params={"action": "leaderboard"},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def get_report(self, run_id: str) -> dict:
        """Fetch a specific assurance report as JSON."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/report_view.php",
            params={"id": run_id, "fmt": "json"},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def get_report_list(self) -> dict:
        """Fetch recent public reports."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/report_view.php",
            params={"action": "list", "fmt": "json"},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def get_audit_status(self, run_id: str) -> dict:
        """Check verification status of a submitted report."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/assurance_verify.php",
            params={"action": "status", "run_id": run_id},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def get_order_status(self, order_id: str) -> dict:
        """Check status of an audit order (enterprise)."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/audit_orchestrator.php",
            params={"action": "status", "order_id": order_id},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def get_scoreboard(self, model=None) -> dict:
        """Fetch scoreboard, optionally filtered to a model."""
        s = await self._get_session()
        params: dict = {"fmt": "json"}
        if model:
            params["model"] = model
        async with s.get(
            f"{FORGE_API_URL}/scoreboard.php", params=params
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def validate_passport(self, passport_json: dict) -> dict:
        """Validate a BPoS passport."""
        s = await self._get_session()
        async with s.post(
            f"{FORGE_API_URL}/passport_api.php",
            params={"action": "validate"},
            json={"passport_json": passport_json},
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def validate_account(self, account_id: str) -> dict:
        """Look up an account by ID and return tier + fleet info.

        Uses the my_fleet endpoint with the bot's admin token to look up
        any account. Returns dict with ok, tier, seats_total, seats_used,
        has_certified_audits, etc.
        """
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/passport_api.php",
            params={"action": "my_fleet", "account_id": account_id},
        ) as r:
            r.raise_for_status()
            data = await r.json()

        # Check if this account has any certified audit reports
        has_certified = False
        try:
            reports = await self.get_report_list()
            # Look through recent reports for any from this account
            for report in reports.get("recent", []):
                if report.get("account_id") == account_id:
                    has_certified = True
                    break
        except Exception:
            pass

        data["has_certified_audits"] = has_certified
        return data

    async def get_linked_account(self, discord_id: str) -> dict:
        """Look up a Forge account by linked Discord ID."""
        s = await self._get_session()
        async with s.get(
            f"{FORGE_API_URL}/discord_api.php",
            params={"action": "lookup", "discord_id": discord_id},
        ) as r:
            if r.status == 404:
                return {"ok": False}
            r.raise_for_status()
            return await r.json()

    async def get_service_status(self) -> bool:
        """Ping the status page. Returns True if healthy."""
        s = await self._get_session()
        try:
            async with s.get(f"{FORGE_API_URL}/status.php") as r:
                return r.status == 200
        except Exception:
            return False
