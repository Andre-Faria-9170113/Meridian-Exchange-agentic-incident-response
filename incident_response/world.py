"""The simulated systems, kept apart from the agent process.

In production the exchange, the executor and the ticket system live outside the agents:
when the agent process dies, they keep their state, including every action they applied.
This module imitates that for the in-process simulator. After every tool call the whole
simulated world (state, executor history, approvals, tickets, trace) is written to
`world.pkl`, atomically. The agent's own progress lives elsewhere (checkpoint.json).

So after an interruption there are two records, as in session 8:
- the agent's checkpoint, which can be behind (it may not know an action ran);
- the systems' history (executor audit, approvals), which is the truth.

`world.pkl` is a trusted local file written by this program. Never load one from elsewhere.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meridian.simulator import Simulator
from meridian.tools import MeridianTools


@dataclass
class DurableTools(MeridianTools):
    """MeridianTools whose world is persisted after every call, like an external system would be."""

    world_path: Path | None = None

    def _run(self, tool: str, args: dict[str, Any], fn) -> Any:
        result = super()._run(tool, args, fn)
        self.persist()
        return result

    def persist(self) -> None:
        if self.world_path is None:
            return
        temporary = self.world_path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            pickle.dump(self, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.world_path)

    def pass_time(self, minutes: int) -> None:
        """Nobody works for `minutes` (a crash, a shift change). The systems keep running."""
        if minutes > 0:
            self.sim.advance(minutes)
            self.persist()


def create_world(scenario: Path, path: Path | None, actor: str) -> DurableTools:
    tools = DurableTools(Simulator(scenario), actor=actor, world_path=path)
    tools.persist()
    return tools


def load_world(path: Path, actor: str) -> DurableTools:
    with path.open("rb") as stream:
        tools = pickle.load(stream)  # noqa: S301 - trusted file written by this program
    if not isinstance(tools, DurableTools):
        raise ValueError(f"{path} does not hold a Meridian world")
    tools.world_path, tools.actor = path, actor
    return tools
