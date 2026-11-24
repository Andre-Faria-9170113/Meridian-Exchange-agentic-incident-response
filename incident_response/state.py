"""Atomic checkpoints and a write-ahead journal for the local simulator.

Replay rebuilds this *simulated* world. Do not reuse this adapter for external
services: those require durable server-side action status and idempotency.
"""
import json
import os
from pathlib import Path
from typing import Any


class Checkpoint:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "checkpoint.json"
        self.data: dict[str, Any] = {}

    def load(self) -> None:
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)

    def set(self, **values: Any) -> None:
        self.data.update(values)
        self.save()
