"""The single path from agents and harness to the systems: an MCP and tool gateway.

Every call, by a specialist or by harness code, goes through `Gateway.call`, which:

- checks the caller may use that tool (least privilege per specialist; mutations are harness-only);
- for MCP tools, allows only reviewed servers and tools whose description and input schema
  match the reviewed lock (catalog.lock.json); unreviewed servers are never connected;
- clamps list sizes so one result cannot flood the model context;
- journals the call in the checkpoint before running it (write-ahead) and its result after;
- retries once when a tool says the failure is retryable;
- blocks a tool for the rest of the run after an `insufficient_scope` refusal;
- masks personal data in results before any model or file sees them;
- gives each result a reference (T01, T02, ...) that specialists must cite as evidence.

As session 9's MCP gateway: identity is the run's actor and the caller (who may call what); allowed tools are
CALLER_TOOLS plus the reviewed catalog lock; credentials never reach a model (keys stay in .env and the
servers run in-process); the journal is the audit; masking covers what is logged and what a model sees.
Admission is enforced around it: read budgets per specialist answer and request and token limits per run
(agents.py). There is no response cache on purpose: incident readings change every minute, and a cache is only
right for the same answer while it is still true.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable

from fastmcp import Client
from fastmcp.exceptions import ToolError

from meridian.mcp_servers import build_servers
from meridian.tools import MeridianTools

from .state import Checkpoint

LOCK = Path(__file__).with_name("catalog.lock.json")

READS = {"read_metrics", "read_logs", "check_link", "recent_changes", "list_runbooks", "read_runbook", "exchange_status"}
MUTATIONS = {"request_approval", "restart_instance", "rollback_change"}
HARNESS_MCP = {"tickets.add_comment", "tickets.link_issues", "tickets.create_issue"}

# Least privilege: what each caller may use. Specialists only read; only harness code changes anything.
CALLER_TOOLS: dict[str, set[str]] = {
    "triage": {"monitoring.list_alerts", "tickets.search_issues", "tickets.get_issue"},
    "investigator": {"read_metrics", "read_logs", "recent_changes", "list_runbooks", "read_runbook", "memory.recall"},
    "reviewer": {"read_metrics", "check_link", "recent_changes", "exchange_status", "list_runbooks", "read_runbook"},
    "harness": READS | MUTATIONS | {"action_status", "monitoring.list_alerts", "tickets.search_issues",
                                    "tickets.get_issue"} | HARNESS_MCP,
}
# Context limits: the most items one call may return.
CLAMPS = {"read_metrics": ("window_ticks", 10), "read_logs": ("limit", 30), "recent_changes": ("limit", 10),
          "monitoring.list_alerts": ("size", 20), "tickets.search_issues": ("max_results", 10)}

PERSONAL_DATA = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r"\bACC-\d{6}\b"), "[account]"),
    (re.compile(r"\+\d{1,3}(?: ?\d{2,4}){2,4}\b"), "[phone]"),
]


class ToolFailure(RuntimeError):
    """A tool needed by harness code failed: the run stops in a controlled way."""


def redact(value: Any) -> Any:
    """Mask personal data (session 5 patterns) while keeping technical evidence intact."""
    if isinstance(value, str):
        for pattern, label in PERSONAL_DATA:
            value = pattern.sub(label, value)
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def tool_hashes(description: str | None, schema: dict[str, Any] | None) -> dict[str, str]:
    return {"description_sha256": hashlib.sha256((description or "").encode()).hexdigest()[:12],
            "schema_sha256": hashlib.sha256(json.dumps(schema or {}, sort_keys=True).encode()).hexdigest()[:12]}


class Gateway:
    def __init__(self, tools: MeridianTools, checkpoint: Checkpoint, local_tools: dict[str, Callable[..., dict]] | None = None):
        self.tools, self.checkpoint = tools, checkpoint
        self.local_tools = local_tools or {}
        self.clients: dict[str, Client] = {}
        self.mcp_tools: dict[str, Any] = {}  # qualified name -> reviewed MCP tool definition
        self.blocked: set[str] = set()
        self.catalog: dict[str, list] = {"approved": [], "refused": [], "ignored_servers": [], "warnings": []}
        self.stack = AsyncExitStack()
        self.checkpoint.data.setdefault("events", [])

    # Catalog review -------------------------------------------------------------------------------------

    async def __aenter__(self) -> Gateway:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        wanted = {name for names in CALLER_TOOLS.values() for name in names if "." in name and not name.startswith("memory.")}
        try:
            for server_name, server in build_servers(self.tools).items():
                reviewed = lock.get(server_name)
                if reviewed is None:
                    self.catalog["ignored_servers"].append(f"{server_name}: not reviewed for this project; never connected")
                    continue
                client = await self.stack.enter_async_context(Client(server))
                self.clients[server_name] = client
                version = getattr(client.server_info, "version", None)
                if version and version != reviewed["version"]:
                    self.catalog["warnings"].append(f"{server_name} reports version {version}, reviewed {reviewed['version']}")
                for tool in await client.list_tools():
                    qualified = f"{server_name}.{tool.name}"
                    if qualified not in wanted:
                        continue  # least privilege: other tools of the server are never offered
                    if reviewed["tools"].get(tool.name) == tool_hashes(tool.description, tool.input_schema):
                        self.mcp_tools[qualified] = tool
                        self.catalog["approved"].append(qualified)
                    else:
                        self.catalog["refused"].append(f"{qualified}: description or input schema differs from the reviewed lock")
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *exc) -> None:
        await self.stack.aclose()

    # Calls ----------------------------------------------------------------------------------------------

    async def _execute(self, name: str, args: dict[str, Any]) -> Any:
        if name in self.local_tools:
            return self.tools.record_call(name, args, lambda: self.local_tools[name](**args))
        if "." not in name:
            return getattr(self.tools, name)(**args)
        if name not in self.mcp_tools:
            return {"error": f"{name} is not in the reviewed catalog (unreviewed, changed or not selected)"}
        if name in self.blocked:
            return {"error": f"{name} was refused for lack of scope earlier in this run; not retried"}
        server, tool = name.split(".", 1)
        try:
            response = await self.clients[server].call_tool(tool, args)
        except ToolError as error:
            return {"error": str(error)}
        if isinstance(response.data, dict):
            return response.data
        return json.loads(response.content[0].text) if response.content else {"error": "empty MCP response"}

    async def call(self, tool: str, /, *, caller: str = "harness", **args: Any) -> dict[str, Any]:
        name = tool
        if name not in CALLER_TOOLS.get(caller, set()):
            return {"error": f"{caller} may not use {name}"}
        if name in CLAMPS:
            key, limit = CLAMPS[name]
            if key in args and isinstance(args[key], int):
                args[key] = max(1, min(args[key], limit))
            elif key not in args and "." in name:  # an MCP server's own default can be large (list_alerts: 50)
                args[key] = limit
        for attempt in (1, 2):
            events = self.checkpoint.data["events"]
            ref = f"T{len(events) + 1:02d}"
            event = {"ref": ref, "caller": caller, "tool": name, "args": args, "actor": self.tools.actor, "attempt": attempt}
            events.append(event)
            self.checkpoint.save()  # write-ahead: the intent is durable before the systems are touched
            try:
                result = await self._execute(name, dict(args))
            except (TypeError, ValueError) as error:  # bad arguments from a model: tell it, do not crash
                result = {"error": f"invalid arguments for {name}: {error}"}
            if not isinstance(result, dict):
                result = {"error": f"{name} returned {type(result).__name__}, expected an object"}
            result = redact(result)
            if result.get("error") == "insufficient_scope":
                self.blocked.add(name)
            event["result"] = result
            self.checkpoint.save()
            if not result.get("retryable") or attempt == 2:
                return {"ref": ref, **result}
        raise AssertionError("unreachable")

    # Evidence -------------------------------------------------------------------------------------------

    def refs(self, caller: str | None = None) -> set[str]:
        return {event["ref"] for event in self.checkpoint.data["events"]
                if "result" in event and not event["result"].get("error") and (caller is None or event["caller"] == caller)}

    def result(self, ref: str) -> dict[str, Any] | None:
        return next((event.get("result") for event in self.checkpoint.data["events"] if event["ref"] == ref), None)


def require(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("error"):
        raise ToolFailure(f"{result.get('ref', '')} {result['error']}".strip())
    return result
