# Source attribution and provenance

This folder was assembled from the user's local Generative AI course workspace on 15 November 2026.

| Material | Original location in the course workspace | Treatment |
|---|---|---|
| Meridian simulator, tools, memory, security facts, MCP servers, data and tests | `meridian/` | Copied as supplied; excludes Python bytecode/cache files |
| Four scenario files | Sessions 1, 2 and 3 under `sessions/course-02-agentic-ai/*/cases/` | Copied unchanged |
| Four public expectation files | Corresponding session `checks/` folders | Copied unchanged; not supplied to model context |
| MCP description hashes | Session 3 `starter/catalog.lock.json` | Only the starter's selected read tools retained |
| Agent/harness patterns | Sessions 1–7, especially tools/context, MCP, memory, security and multi-agent exercises | Adapted into new project-owned modules |
| Requirements interpretation | Root `Projeto Agentic AI.pdf`, pages 2–10 | Paraphrased in `docs/PROJECT_BRIEF.md`; PDF not duplicated here |
| Student-facing boilerplate and documentation | `incident_response/`, `scripts/`, `tests/`, `docs/`, project configuration | Generated with Codex assistance for this starter |
| Additional synthetic cases | `cases/approval-denied.yaml`, `cases/injected-log.yaml` | Derived from the supplied multi-source incident |

The course brief identifies the trainer as **Luís Noronha**. Retain this source attribution and existing notices in the public project repository. This starter does not assign a new license to the copied course material.

The starter intentionally does not copy the course `.env`, `.git`, virtual environment, local databases, unrelated courses or private solution directories.
