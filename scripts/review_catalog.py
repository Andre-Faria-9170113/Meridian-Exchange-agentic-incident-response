"""Compare the MCP tools the gateway would use with the reviewed lock.

    python scripts/review_catalog.py                      # show differences, change nothing
    python scripts/review_catalog.py --scenario cases/s03-description-change.yaml
    python scripts/review_catalog.py --write              # after a person reviewed the diff

The lock pins, per selected tool, the SHA-256 (first 12 hex digits) of its description and of its
input schema, plus each server's reviewed version and publisher. The gateway refuses a selected
tool whose description or schema changed. Never run --write automatically at startup.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastmcp import Client  # noqa: E402

from incident_response.gateway import CALLER_TOOLS, LOCK, tool_hashes  # noqa: E402
from meridian.mcp_servers import build_servers  # noqa: E402
from meridian.mcp_servers.__main__ import DEFAULTS  # noqa: E402
from meridian.simulator import Simulator  # noqa: E402
from meridian.tools import MeridianTools  # noqa: E402

SELECTED = sorted({name for names in CALLER_TOOLS.values() for name in names if "." in name and not name.startswith("memory.")})


async def current(scenario: Path) -> dict:
    tools = MeridianTools(Simulator(scenario))
    wanted_servers = {name.split(".")[0] for name in SELECTED}
    catalog = {}
    for server_name, server in build_servers(tools, names=sorted(wanted_servers)).items():
        async with Client(server) as client:
            listed = {tool.name: tool for tool in await client.list_tools()}
            version = client.server_info.version
        catalog[server_name] = {"version": version, "publisher": DEFAULTS[server_name]["publisher"], "tools": {
            name.split(".", 1)[1]: tool_hashes(listed[name.split(".", 1)[1]].description, listed[name.split(".", 1)[1]].input_schema)
            for name in SELECTED if name.startswith(server_name + ".")}}
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, default=ROOT / "cases/s03-alert-and-ticket.yaml")
    parser.add_argument("--write", action="store_true", help="Write the lock (only after reviewing the differences)")
    args = parser.parse_args()
    catalog = asyncio.run(current(args.scenario))
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {}
    differences = []
    for server, entry in catalog.items():
        reviewed = lock.get(server, {})
        if entry["version"] != reviewed.get("version"):
            differences.append(f"{server}: version {reviewed.get('version')} -> {entry['version']}")
        for name, hashes in entry["tools"].items():
            if reviewed.get("tools", {}).get(name) != hashes:
                differences.append(f"{server}.{name}: {reviewed.get('tools', {}).get(name)} -> {hashes}")
    print("\n".join(differences) if differences else "The selected tools match the reviewed lock.")
    if args.write:
        LOCK.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {LOCK.relative_to(ROOT)}")
    return 1 if differences and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
