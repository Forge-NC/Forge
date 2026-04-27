"""Canonical scenario-pack exporter.

Dumps `forge.assurance._SCENARIOS` to a deterministic JSON file with a
content-addressed SHA-512 hash. The output is the source of truth for the
sealed-bundle scenario pack distributed to external runners.

The pack format is intentionally simple:

    {
      "version": 3,
      "scheme": "forge.scenario-pack.v1",
      "scenarios": [...sorted by id...],
      "scenarios_sha512": "<hex>",
      "generated_at": "<iso8601>"
    }

`scenarios_sha512` covers the canonical JSON of the scenarios array (sorted
keys, sorted entries by id, no whitespace, UTF-8 bytes). The server stores
this file, computes the same hash on read, includes it in the Origin-signed
attestation envelope, and ships the scenarios array inside the sealed bundle.
The runner then runs the bundled scenarios — never the local _SCENARIOS —
and the hash chain proves which pack was used.

Run from the Forge repo root:

    python -m forge.scenario_pack_export

Writes to ``server/data/scenario_packs/v<version>.json`` by default.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

from forge.assurance import ASSURANCE_PROTOCOL_VERSION, _SCENARIOS


PACK_SCHEME = "forge.scenario-pack.v1"


def _canonical_scenarios_bytes(scenarios: list[dict]) -> bytes:
    """Return canonical UTF-8 JSON bytes for the scenarios array.

    Canonicalization rules:
      - entries sorted by 'id' (stable across runs)
      - keys sorted within each entry
      - separators (',', ':') — no whitespace
      - ensure_ascii=False so unicode characters round-trip cleanly
    """
    sorted_entries = sorted(scenarios, key=lambda s: s["id"])
    return json.dumps(
        sorted_entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_pack(scenarios: list[dict] = None, version: int = None) -> dict:
    """Build the canonical pack dict from a scenarios list + version."""
    scenarios = scenarios if scenarios is not None else _SCENARIOS
    version = version if version is not None else ASSURANCE_PROTOCOL_VERSION
    canonical = _canonical_scenarios_bytes(scenarios)
    digest = hashlib.sha512(canonical).hexdigest()
    sorted_entries = json.loads(canonical.decode("utf-8"))
    return {
        "version": version,
        "scheme": PACK_SCHEME,
        "scenarios": sorted_entries,
        "scenarios_sha512": digest,
        "generated_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def write_pack(out_path: Path, pack: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export canonical scenario pack")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Defaults to server/data/scenario_packs/v<version>.json",
    )
    p.add_argument(
        "--version",
        type=int,
        default=None,
        help="Override protocol version (defaults to ASSURANCE_PROTOCOL_VERSION)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Compute hash and print summary without writing.",
    )
    args = p.parse_args(argv)

    pack = build_pack(version=args.version)

    print(f"scheme           : {pack['scheme']}")
    print(f"version          : {pack['version']}")
    print(f"scenarios        : {len(pack['scenarios'])}")
    print(f"scenarios_sha512 : {pack['scenarios_sha512']}")
    print(f"generated_at     : {pack['generated_at']}")

    if args.check:
        return 0

    if args.out is None:
        repo_root = Path(__file__).resolve().parent.parent
        args.out = repo_root / "server" / "data" / "scenario_packs" / f"v{pack['version']}.json"

    write_pack(args.out, pack)
    print(f"wrote            : {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
