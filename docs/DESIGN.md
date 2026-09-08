# Design

Architecture and design-pattern decisions for the Category Insights Agent,
recorded as they're made — this file grows sprint by sprint, it isn't
written after the fact.

## Sprint 0 — bootstrap

- Repository initialized with a `main` branch; each subsequent layer is
  built on a `sprint/0N-<name>` feature branch and merged with
  `git merge --no-ff` after review, so sprint history stays visible.
- CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`,
  and `pytest` on every push to `main` or a `sprint/*` branch.
- Architecture is hexagonal (ports & adapters): `domain/` defines
  `Protocol` contracts and Pydantic models with zero I/O; `db/`, `rag/`,
  and `mcp_server/` are adapters implementing those contracts; `agent/` is
  the orchestration/logic layer; `ui/` is presentation. See the plan file
  for the full layer map and rationale for each design pattern used
  (Chain of Responsibility, Command, Provider, Factory, dependency
  injection) — summarized here as each layer lands.
