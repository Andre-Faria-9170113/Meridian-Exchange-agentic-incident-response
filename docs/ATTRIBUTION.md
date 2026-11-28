# Source attribution and provenance

The course material is by **Luís Noronha** (*Agentic AI: Da Arquitetura à Implementação*). Reusing the course simulator,
cases and patterns is expected by the project brief. This file separates that material from the project's own work.
It does not assign a new license to the course material.

| Material | Origin | Treatment |
|---|---|---|
| `meridian/` (simulator, tools, memory store, security facts, MCP servers, data, runbooks, evaluator) | Course repository, `meridian/` | Copied unchanged (Python caches excluded) |
| `cases/s0*.yaml`, `checks/s0*.yaml` (20 cases and their checks) | Course sessions 1–4, `sessions/course-02-agentic-ai/*/cases` and `*/checks` | Copied unchanged |
| MCP description hashes in `incident_response/catalog.lock.json` | Session 3 reviewed catalog (`03-mcp-integration/starter/catalog.lock.json`) | Same description hashes for the selected tools. Schema hashes were added with `scripts/review_catalog.py` |
| Correlation vocabulary in `incident_response/rules.py` | Session 3 solution (`03-mcp-integration/starter/incident_server.py`) | Adapted |
| Agent, harness, orchestration and resume patterns | Sessions 1–9 exercises and published solutions | Adapted into project modules |
| `cases/approval-denied.yaml`, `cases/injected-log.yaml` and their checks | Derived from the course's `s03-alert-and-ticket` case | Project cases |
| Initial boilerplate (`v0-starter`) | Generated with OpenAI Codex, 15 November 2026 | Kept as the baseline tag |
| Evaluator, agent layer from `baseline` on (milestones 1–3), tests, evidence, README and `docs/` | Written with Claude Code (Claude Opus 5.5), 24 November – 1 December 2026, at the student's direction | Project code |

The project does not include the course's `.env`, `.git` history, virtual environment, local databases, private
solutions or other courses.
