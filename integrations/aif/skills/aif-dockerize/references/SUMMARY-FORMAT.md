# Summary Display Format

## Summary Template

```
## Docker Setup Complete

### Files Created/Updated
- Dockerfile (multi-stage: development + production)
- compose.yml (app + postgres + redis, COMPOSE_PROJECT_NAME from .env)
- compose.override.yml (dev: hot reload, debug ports, mailpit)
- compose.production.yml (hardened: read-only, non-root, resource limits, no infra ports)
- .dockerignore (38 exclusion rules)
- .env.example (with COMPOSE_PROJECT_NAME, DB credentials, app config)
- docker/angie/ (reverse proxy config, if needed)
- deploy/scripts/ (deploy, update, logs, health-check, rollback, backup)

### Quick Start
  # Development
  docker compose up

  # Development with email testing
  docker compose --profile dev up

  # Production (locally)
  docker compose -f compose.yml -f compose.production.yml up -d

  # Build production image
  docker build --target production -t myapp:latest .

### Services
| Service | Port (dev) | Port (prod) | Image |
|---------|------------|-------------|-------|
| app | 3000, 9229 | — | built locally |
| postgres | 5432 | — | postgres:17-alpine |
| redis | 6379 | — | redis:7-alpine |
| mailpit | 8025, 1025 | — | axllent/mailpit |
```

## Follow-Up Suggestions

**Kanban (autonomous) mode:** do not ask. Include the follow-up suggestions in the completion handoff so `aif_planner` (or the originating topic) can decide:

- Build automation — load skill `aif-build-automation` to add Docker targets to Makefile/Taskfile
- Docs — load skill `aif-docs` to document the Docker setup
- If both are wanted → build-automation first, then docs

**Interactive (topic/CLI) sessions** may offer the user the same choice directly (build automation / docs / both / done).

> Reminder (Hermes safety rule): the "Quick Start" production commands are for the operator. In kanban mode never run them against a production host — that is an explicit-approval action (block, don't ask).
