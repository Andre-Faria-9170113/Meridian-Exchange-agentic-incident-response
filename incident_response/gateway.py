"""Small, reviewed MCP surface plus journaled native simulator tools."""
import hashlib
import json
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from fastmcp import Client

from meridian.mcp_servers import build_servers
from meridian.tools import MeridianTools

from .state import Checkpoint

CATALOG = Path(__file__).with_name("catalog.lock.json")
MCP_ALLOW = {"tickets": {"search_issues", "get_issue"},
             "monitoring": {"list_alerts"}}
NATIVE_ALLOW = {"read_metrics", "read_logs", "check_link", "recent_changes",
                "list_runbooks", "read_runbook", "exchange_status",
                "request_approval", "restart_instance", "rollback_change", "action_status"}


class ToolFailure(RuntimeError):
    pass


def redact(value: Any) -> Any:
    """Illustrative email masking; extend for account IDs, phones and your data."""
    if isinstance(value, str):
        return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class Gateway:
    def __init__(self, tools: MeridianTools, checkpoint: Checkpoint):
        self.tools, self.checkpoint = tools, checkpoint
        self.clients: dict[str, Client] = {}
        self.blocked: set[tuple[str, str]] = set()
        self.approved: set[tuple[str, str]] = set()
        self.stack = AsyncExitStack()

    async def __aenter__(self):
        lock = json.loads(CATALOG.read_text(encoding="utf-8"))
        try:
            for name, server in build_servers(self.tools, names=list(MCP_ALLOW)).items():
                client = await self.stack.enter_async_context(Client(server))
                self.clients[name] = client
                for tool in await client.list_tools():
                    digest = hashlib.sha256((tool.description or "").encode()).hexdigest()[:12]
                    if tool.name in MCP_ALLOW[name] and lock.get(name, {}).get(tool.name) == digest:
                        self.approved.add((name, tool.name))
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *exc):
        await self.stack.aclose()

    async def _execute(self, server: str, name: str, args: dict) -> dict:
        if server == "native":
            if name not in NATIVE_ALLOW:
                raise ToolFailure(f"Tool not exposed: {name}")
            result = getattr(self.tools, name)(**args)
        else:
            if (server, name) not in self.approved:
                raise ToolFailure(f"MCP tool not reviewed or description changed: {server}.{name}")
            if (server, name) in self.blocked:
                raise ToolFailure(f"MCP scope previously refused: {server}.{name}")
            response = await self.clients[server].call_tool(name, args)
            # FastMCP validates the protocol response; validate our object boundary too.
            result = response.data
            if not isinstance(result, dict):
                result = json.loads(response.content[0].text)
        if not isinstance(result, dict):
            raise ToolFailure(f"Invalid result from {server}.{name}: expected an object")
        result = redact(result)
        if result.get("error") == "insufficient_scope":
            self.blocked.add((server, name))
        return result

    async def call(self, tool_name: str, *, server: str = "native", **args) -> dict:
        # Persist intent before touching the simulator, including before a lost response.
        event = {"server": server, "name": tool_name, "args": args, "actor": self.tools.actor}
        self.checkpoint.data["events"].append(event)
        self.checkpoint.save()
        try:
            result = await self._execute(server, tool_name, args)
        except Exception as error:
            result = {"error": str(error), "retryable": False}
        event["result"] = result
        self.checkpoint.save()
        return result

    async def replay(self) -> None:
        """Reconstruct this run from the pinned scenario and tool intents."""
        for event in self.checkpoint.data["events"]:
            current_actor = self.tools.actor
            self.tools.actor = event["actor"]
            try:
                actual = await self._execute(event["server"], event["name"], event["args"])
            except Exception as error:
                actual = {"error": str(error), "retryable": False}
            finally:
                self.tools.actor = current_actor
            if "result" in event and actual != event["result"]:
                raise ToolFailure("Replay diverged; restore the original code/catalog before resuming")
            event["result"] = actual
        self.checkpoint.save()


def require(result: dict) -> dict:
    if result.get("error"):
        raise ToolFailure(str(result["error"]))
    return result
