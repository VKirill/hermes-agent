---
name: aif-dockerize
description: >-
  Analyze a project and generate a complete Docker configuration: multi-stage Dockerfile
  (dev/prod), compose.yml, compose.override.yml (dev), compose.production.yml (hardened),
  .dockerignore, and deploy scripts — plus a production security audit. Use when a dev task
  says "dockerize", "add docker", "docker compose", "containerize", or "setup docker".
  Port of lee-to AI Factory /aif-dockerize, adapted to Hermes.
tags:
  - aif
  - docker
  - infrastructure
  - deployment
  - dev-factory
---

# aif-dockerize — Docker Configuration Generator

Analyze a project and generate a complete, production-grade Docker setup: multi-stage Dockerfile, Docker Compose for development and production, `.dockerignore`, and a security audit of the result.

**Three modes based on what exists:**

| What exists | Mode | Action |
|-------------|------|--------|
| Nothing | `generate` | Create everything from scratch |
| Only local Docker (no production files) | `enhance` | Audit & improve local, then create production config |
| Full Docker setup (local + prod) | `audit` | Audit everything against checklist, fix gaps |

## Hermes context

- You run **as a kanban worker** on the `departments` board (usually under `aif_implementer` or the DevOps role). Native Hermes kanban is the handoff layer — **no `HANDOFF_MODE`, no MCP handoff, no `.ai-factory/config.yaml`**; paths are fixed. Department-wide pipeline and laws: skill `aif-methodology`.
- Skill artifacts (`references/`, `templates/`) live in `~/.hermes/skills/aif-dockerize/`; project artifacts in the app workspace (`~/Work/apps/<slug>/`).
- **Autonomous:** no interactive questions in kanban mode. Infrastructure choices come from code detection (Step 2.5) and the task body — not from asking. If a genuinely required choice cannot be inferred, **block the kanban task with the exact missing input**. Interactive (topic/CLI) sessions may ask the user.
- **Safety (block-not-ask):** writing Docker/deploy configuration *into the project* is always in scope. But actions that touch real production are not: running `deploy/scripts/*.sh` against a production host, `docker compose up` on a prod server, pushing images to a live registry, pointing DNS/SSL at new infra → `kanban_block` with the exact pending action. Local `docker build` / `docker compose config` validation is fine where the sandbox permits.

---

## Step 0: Load Project Context

Read the project description if available:

```
Read DESCRIPTION.md            # project root; tech stack, conventions
Read ARCHITECTURE.md           # project root; if present
Read .hermes-dev/rules/*       # hard project rules, if present
```

Store project context for later steps. If absent, Step 2 detects everything.

**Read `.hermes-dev/skill-context/aif-dockerize/SKILL.md`** — MANDATORY if the file exists.

This file contains project-specific rules accumulated by `aif-evolve` from patches, codebase conventions, and tech-stack analysis. How to apply them:

- Treat them as **project-level overrides** for this skill's general instructions.
- On conflict, **the skill-context rule wins** (more specific context takes priority — same principle as nested agent-notes files).
- When there is no conflict, apply both: general rules from this SKILL.md + project rules from skill-context.
- Do NOT ignore skill-context rules even if they contradict this skill's defaults — they exist because the project's experience proved the default insufficient.
- **CRITICAL:** skill-context rules apply to ALL outputs of this skill — including Dockerfile, compose files, .dockerignore, and deploy scripts. Templates in this skill are **base structures**. If a skill-context rule says "Dockerfile MUST include X" or "compose MUST have service Y" — augment the templates accordingly. Generating Docker config that violates skill-context rules is a bug.

**Enforcement:** After generating any output artifact, verify it against all skill-context rules. If any rule is violated — fix the output before finishing.

Also read the kanban task body + parent handoffs (`hermes kanban --board departments show <id>`): they may request `--audit` or name infrastructure choices (DB, proxy, cache).

---

## Step 1: Detect Existing Docker Files & Determine Mode

### 1.1 Scan for Existing Files

```
Glob: Dockerfile, Dockerfile.*, docker-compose.yml, docker-compose.yaml, compose.yml, compose.yaml, compose.override.yml, compose.production.yml, .dockerignore, deploy/scripts/*.sh
```

Classify found files into categories:
- `HAS_DOCKERFILE`: Dockerfile exists
- `HAS_LOCAL_COMPOSE`: compose.yml or docker-compose.yml exists
- `HAS_DEV_OVERRIDE`: compose.override.yml exists
- `HAS_PROD_COMPOSE`: compose.production.yml exists
- `HAS_DOCKERIGNORE`: .dockerignore exists
- `HAS_DEPLOY_SCRIPTS`: deploy/scripts/ exists

### 1.2 Determine Mode

**If the task body contains `--audit`** → set `MODE = "audit"` regardless.

**Path A: Nothing exists** (`!HAS_DOCKERFILE && !HAS_LOCAL_COMPOSE`):
- Set `MODE = "generate"`
- Proceed to **Step 1.3: Infrastructure Choices**

**Path B: Only local Docker** (`HAS_LOCAL_COMPOSE && !HAS_PROD_COMPOSE`):
- Set `MODE = "enhance"`
- Read all existing Docker files → store as `EXISTING_CONTENT`
- Log: "Found local Docker setup. Will audit, improve, and create production configuration."

**Path C: Full setup exists** (`HAS_LOCAL_COMPOSE && HAS_PROD_COMPOSE`):
- Set `MODE = "audit"`
- Read all existing Docker files → store as `EXISTING_CONTENT`
- Log: "Found complete Docker setup. Will audit against security checklist and fix gaps."

### 1.3 Infrastructure Choices (Generate Mode Only)

In kanban mode do **not** ask — fill `USER_INFRA_CHOICES` on evidence, in this order: (1) explicit choices in the task body / parent handoffs, (2) code detection from Step 2.5, (3) defaults below. Interactive sessions may ask the user the same questions instead.

- `database`: postgres | mysql | mongodb | sqlite | none — from detected drivers/ORM config; if the app clearly needs a relational DB but the engine is not determinable from code or task, prefer **PostgreSQL** (the original's recommended default) and state the assumption in the handoff.
- `reverse_proxy`: angie | nginx | traefik | none — needed for SSL termination / multi-service routing; PHP (Laravel, Symfony) projects always need one. Prefer **Angie**.
- `cache`: redis | memcached | none — only if code uses it.
- `queue`: rabbitmq | none — only if code uses it.

> **Note:** Prefer **Angie** over Nginx. Angie is a drop-in Nginx replacement with better module support, dynamic configuration, and active development. See: https://en.angie.software/angie/docs/configuration/

Do not add infrastructure the code doesn't use (see over-engineering checks in Step 4).

### 1.4 Read Existing Files (Enhance / Audit Modes)

Read all existing Docker files and store as `EXISTING_CONTENT`:
- Dockerfile(s)
- All compose files (local + override + production)
- .dockerignore
- deploy/scripts/*.sh (if any)

---

## Step 2: Deep Project Analysis

Scan the project thoroughly — every decision in the generated files depends on this profile.

### 2.1 Language & Runtime

| File | Language | Base Image |
|------|----------|------------|
| `go.mod` | Go | `golang:<version>-alpine` / `distroless/static` |
| `package.json` | Node.js | `node:<version>-alpine` |
| `pyproject.toml` / `setup.py` | Python | `python:<version>-slim` |
| `composer.json` | PHP | `php:<version>-fpm-alpine` |
| `Cargo.toml` | Rust | `rust:<version>-slim` / `distroless` |

**`<version>` = read from project files** (see Step 4.1). Never hardcode — always match what the project requires.

### 2.2 Framework & Dev Server

Read dependency files to detect the framework:

**Node.js** (`package.json` dependencies):
- `next` → Next.js (port 3000, `next dev` / `next start`)
- `nuxt` → Nuxt (port 3000, `nuxt dev` / `nuxt start`)
- `express` → Express (port 3000, `nodemon` / `node`)
- `fastify` → Fastify (port 3000)
- `@nestjs/core` → NestJS (port 3000, `nest start --watch` / `node dist/main`)
- `hono` → Hono (port 3000)

**Python** (`pyproject.toml` / requirements):
- `fastapi` → FastAPI (port 8000, `uvicorn --reload` / `uvicorn`)
- `django` → Django (port 8000, `manage.py runserver` / `gunicorn`)
- `flask` → Flask (port 5000, `flask run --debug` / `gunicorn`)

**PHP** (`composer.json` require):
- `laravel/framework` → Laravel (port 8000, `artisan serve` / `php-fpm`)
- `symfony/framework-bundle` → Symfony (port 8000, `symfony serve` / `php-fpm`)

**Go** (`go.mod` require):
- `gin-gonic/gin`, `labstack/echo`, `gofiber/fiber`, `go-chi/chi` → (port 8080, `air` / compiled binary)

### 2.3 Package Manager & Lock File

Same detection as `aif-build-automation` Step 2.2 (or the lock-file table in `aif-ci` Step 2.3).

Store: `PACKAGE_MANAGER`, `LOCK_FILE`.

### 2.4 Entry Point Detection

Find the application entry point:

```
# Go
Glob: cmd/*/main.go, main.go

# Node.js
Read package.json → "main" or "scripts.start"
Glob: src/index.ts, src/index.js, src/main.ts, src/main.js, index.ts, index.js, server.ts, server.js

# Python
Glob: main.py, app.py, src/main.py, src/app.py
Read pyproject.toml → [project.scripts] or [tool.uvicorn]

# PHP
Glob: public/index.php, artisan, bin/console
```

### 2.5 Infrastructure Dependencies

Detect what services the app needs:

```
# Database
Grep: postgres|postgresql|pg_|mysql|mariadb|mongo|mongodb|sqlite
Glob: prisma/schema.prisma, drizzle.config.*, alembic/, migrations/

# Cache
Grep: redis|memcached|ioredis

# Queue
Grep: rabbitmq|amqp|bullmq|celery|sidekiq

# Reverse Proxy / Web Server
Grep: nginx|angie|proxy_pass|upstream
Glob: nginx.conf, nginx/, angie.conf, angie/
# PHP projects (Laravel, Symfony) always need a reverse proxy → default to Angie

# Search
Grep: elasticsearch|opensearch|meilisearch|typesense|algolia

# Object Storage
Grep: minio|s3|aws-sdk.*S3|boto3.*s3

# Email
Grep: nodemailer|sendgrid|mailgun|postmark|smtp|MAIL_HOST
```

For each detected dependency, record:
- Service type (postgres, redis, rabbitmq, etc.)
- Specific variant (MySQL vs PostgreSQL, Redis vs Memcached)
- Connection string pattern found in code

**Merge with `USER_INFRA_CHOICES`** (from Step 1.3 in Generate mode):
- Explicit task-body choices override auto-detection for database and reverse proxy
- Auto-detected services are added unless the task explicitly chose "None"

**Reverse proxy preference:** When a reverse proxy is needed, prefer **Angie** over Nginx. Angie is a fully compatible Nginx fork with active development, dynamic upstream management, and built-in Prometheus metrics. Reference: https://en.angie.software/angie/docs/configuration/

### 2.6 Exposed Ports

Check existing configs:

```
Grep: PORT|port|listen|EXPOSE
Read package.json → scripts.dev, scripts.start (look for --port)
```

### 2.7 Build Output

```
# Node.js
Read package.json → scripts.build, check for dist/, build/, .next/, out/
Read tsconfig.json → outDir

# Go
Glob: cmd/*/main.go → binary name from directory

# Python
Check for pyproject.toml [build-system]

# PHP
Check for public/ directory (web root)
```

### 2.8 Existing .env Structure

```
Glob: .env.example, .env.sample, .env.template
```

If found, read it to understand required environment variables. This drives `env_file`, `environment:` (computed values), and `.env.example` generation.

### Summary

Build `PROJECT_PROFILE`:
- `language`, `language_version`
- `framework`, `dev_command`, `prod_command`
- `package_manager`, `lock_file`
- `entry_point`, `build_output_dir`
- `port` (primary app port)
- `debug_port` (language-specific debug port)
- `services`: list of infrastructure deps (`postgres`, `redis`, `rabbitmq`, etc.)
- `has_build_step`: boolean
- `env_vars`: list from .env.example

---

## Step 3: Read Best Practices & Templates

```
Read references/BEST-PRACTICES.md         # in this skill's folder (~/.hermes/skills/aif-dockerize/)
Read references/SECURITY-CHECKLIST.md
```

Additional focused references are available for production reverse-proxy and Compose permission edge cases:

- `references/ANGIE-ACME.md` — read when generating or auditing Angie HTTPS/ACME configuration. Use it for built-in ACME setup, persistent certificate volumes, `acme_client_path`, resolver requirements, and avoiding unnecessary Certbot containers.
- `references/COMPOSE-LIFECYCLE-HOOKS.md` — read when a production Compose service runs non-root but needs named-volume ownership fixes or best-effort stop hooks. Use it for `post_start`/`pre_stop` syntax, Docker Compose 2.30.0+ requirements, and hook timing caveats.

Select the Dockerfile template matching the language:

| Language | Template |
|----------|----------|
| Go | `templates/dockerfile-go` |
| Node.js | `templates/dockerfile-node` |
| Python | `templates/dockerfile-python` |
| PHP | `templates/dockerfile-php` |

Read selected template and the compose templates:

```
Read templates/dockerfile-<language>
Read templates/compose-base.yml
Read templates/compose-override-dev.yml
Read templates/compose-production.yml
Read templates/dockerignore
```

---

## Step 4: Generate Files (Generate Mode)

Generate files customized from the project profile and templates.

### 4.1 Generate Dockerfile

Using the language-specific template as a base:

**Customize:**
- Base image version **from the project**, not from template defaults:
  - Go: read `go` directive in `go.mod` → e.g. `go 1.24` → `golang:1.24-alpine`
  - Node.js: read `engines.node` in `package.json`, `.nvmrc`, or `.node-version` → e.g. `node:22-alpine`
  - Python: read `requires-python` in `pyproject.toml` or `.python-version` → e.g. `python:3.13-slim`
  - PHP: read `require.php` in `composer.json` → e.g. `php:8.4-fpm-alpine`
  - Rust: read `rust-version` in `Cargo.toml` or `rust-toolchain.toml` → e.g. `rust:1.82-slim`
- Entry point to match `entry_point`
- Build command to match project's actual build script
- Dev command with hot reload (framework-specific)
- Production command (framework-specific)
- Exposed ports (app port + debug port in dev stage)
- Package manager commands (npm ci vs pnpm install vs yarn install vs bun install)
- Lock file name in COPY

**Stages:**
1. `deps` — install production dependencies only
2. `builder` — install all dependencies + build
3. `development` — full dev environment with hot reload, debug port
4. `production` — minimal image, non-root user, only runtime artifacts

**Verify infrastructure image versions online:**

For infrastructure images (PostgreSQL, Redis, Angie, Nginx, etc.) — the version is NOT in project files. Before generating compose.yml, use `WebSearch` to check the current stable version of each infrastructure image:
- Search for `<service> docker official image latest version` (e.g. `angie docker image latest version`)
- Use the latest stable `major.minor` tag, never `:latest`
- Example: `docker.angie.software/angie:1.11-alpine`, `postgres:17-alpine`, `redis:7-alpine`

This prevents generating non-existent image tags that would break `docker compose pull`. If web access is unavailable, fall back to the pinned versions in this skill's templates and flag the tags as "verify before deploy" in the handoff.

### 4.2 Generate compose.yml (Base)

The shared configuration:

- Top-level `name: ${COMPOSE_PROJECT_NAME}` — project name from `.env`, NOT from folder name
- `app` service with `build.target: production`, healthcheck, depends_on with `service_healthy`
- Infrastructure services based on `PROJECT_PROFILE.services` + `USER_INFRA_CHOICES`:
  - PostgreSQL / MySQL / MongoDB → with healthcheck, named volume
  - Redis / Memcached → with healthcheck, maxmemory config, named volume
  - RabbitMQ → with healthcheck, management UI port in dev
  - Angie / Nginx / Traefik → as reverse proxy with SSL termination config
  - Elasticsearch → with healthcheck, JVM memory, ulimits
  - MinIO → with healthcheck

**Reverse proxy (Angie/Nginx):** Use `docker.angie.software/angie:<version>-alpine` (Angie) or `nginx:<version>-alpine` (Nginx) — verify current version online. Mount config from `docker/angie/`. Sits on `frontend` network, proxies to `app` on `backend` network. In production: read_only, cap_add NET_BIND_SERVICE.

**Environment variable strategy and service configuration patterns** — read `references/COMPOSE-PATTERNS.md`

**Service inclusion is conditional** — only add services that were detected in Step 2.5.

### 4.3 Generate compose.override.yml (Development)

Development overrides: `build.target: development`, bind mount source code (`.:/app`), expose all ports, dev env vars, dev command override, `mailpit` service (profile: `dev`) if email detected. **No database admin UIs** — use native GUI clients via exposed DB port.

**Hot-reload:** If dev stage uses air (Go) or nodemon (Node.js), verify its config file exists and points to the correct entry point. Generate config if missing and entry point is non-standard.

### 4.4 Generate compose.production.yml (Hardened)

Production hardening overlay:

- Use pre-built image from registry (not `build:`)
- `read_only: true` on all services
- `security_opt: [no-new-privileges:true]`
- `cap_drop: [ALL]` with selective `cap_add` per service
- `user: "1001:1001"`
- `tmpfs` for `/tmp` with `noexec,nosuid,size=100m`
- Resource limits (CPU, memory, PIDs) — use reference recommendations
- Log rotation on every service (`max-size: 20m, max-file: 5`)
- `restart: unless-stopped`
- `backend` network with `internal: true`
- Sensitive values via `.env` file (gitignored) — NOT hardcoded in compose
- YAML anchors (`x-logging`, `x-security`) to reduce duplication
- **NO `ports:` on infrastructure services** (DB, Redis, RabbitMQ) — they communicate via Docker network only
- Only the reverse proxy (or app if no proxy) exposes ports `80`/`443` to the host
- If a port MUST be exposed, bind to localhost only: `127.0.0.1:5432:5432`
- NO debug ports (9229, 5005, etc.)
- NO dev tools

### 4.5 Generate .dockerignore

Use the template as base, add language-specific exclusions:

- Go: `bin/`, `*.exe`
- Node.js: `node_modules/`, `.next/`, `out/`
- Python: `__pycache__/`, `.venv/`, `*.pyc`, `.mypy_cache/`
- PHP: `vendor/`, `storage/`, `bootstrap/cache/`

### Quality Checks (Before Writing)

Verify generated content before passing to Step 6:

**Correctness:**
- [ ] Dockerfile has all 4 stages (deps, builder, development, production)
- [ ] Production stage uses non-root user
- [ ] Production stage uses minimal base image
- [ ] BuildKit cache mounts present for dependency installation
- [ ] compose.yml has healthchecks on every service
- [ ] compose.yml uses `depends_on` with `condition: service_healthy`
- [ ] compose.production.yml has security hardening on every service
- [ ] compose.production.yml has resource limits on every service
- [ ] compose.production.yml has log rotation on every service
- [ ] .dockerignore excludes `.git`, dependencies, `.env*`, Docker files

**Over-engineering check** (read `references/SECURITY-CHECKLIST.md` → "Over-Engineering Checklist"):
- [ ] No services added that the code doesn't import/use
- [ ] No reverse proxy for single-service apps with no SSL needs
- [ ] No deploy scripts if project deploys via CI/CD
- [ ] No backup scripts if using managed DB (RDS, Cloud SQL)
- [ ] No separate frontend/backend networks if there's only app + DB
- [ ] Complexity matches project size (solo → minimal, team → standard, production → full)

**Remove anything that fails the over-engineering check before writing.**

---

## Step 5: Audit & Enhance Existing Files (Enhance / Audit Modes)

When `MODE = "enhance"` or `MODE = "audit"`, analyze `EXISTING_CONTENT` against the security checklist and best practices.

**Enhance mode** (`MODE = "enhance"`): Local Docker exists but no production config. After auditing local files, create production configuration. Fill missing infrastructure choices the same way as Step 1.3 (task body → detection → defaults; interactive sessions may ask) before generating production files.

For detailed audit procedures, report format, fix flow, and enhance mode steps → read `references/AUDIT-GUIDE.md`

**What to audit:**
- **Dockerfile**: image pinning, minimal base, multi-stage, non-root user, no secrets in ENV/ARG, .dockerignore, BuildKit features, HEALTHCHECK
- **Compose per-service**: read_only, no-new-privileges, cap_drop ALL, user, tmpfs, resource limits, healthcheck, log rotation, restart policy
- **Network**: internal backend, no host networking, no Docker socket
- **Secrets**: values in .env not hardcoded, .env in .gitignore, .env.example exists
- **Gaps**: services detected in code but missing from compose

Present results as tables with ✅/❌/⚠️. Fix flow: in kanban mode apply all CRITICAL and HIGH fixes (plus safe MEDIUM/LOW), record applied vs deferred in the handoff; interactive sessions may ask (fix all / critical only / details / export report).

---

## Step 6: Write Files

For detailed file organization (directory layout, file tables per mode, .env.example template, volume mount examples) → read `references/FILE-ORGANIZATION.md`

### 6.0 Overview

- **Root**: `Dockerfile`, `compose.yml`, `compose.override.yml`, `compose.production.yml`, `.dockerignore`
- **`docker/`**: service configs (angie, postgres, php, redis) — only create what's needed
- **`deploy/scripts/`**: production ops scripts (Step 8)

### 6.1 Generate Mode — write all root files + conditional docker/ dirs + deploy/scripts/

### 6.2 Audit / Enhance Mode — only write changed/new files, respect existing layout

### 6.3 Create .env.example if missing — single file with sections, production vars commented out. Ensure `.env` in `.gitignore`.

---

## Step 7: Security Checklist (Always Runs)

Regardless of mode, run the production security checklist on the final compose.production.yml.

Read `references/SECURITY-CHECKLIST.md` and verify every item. Check categories: Container Isolation (read_only, no-new-privileges, cap_drop, non-root, tmpfs), Network & Ports (internal backend, no host networking, no Docker socket, no infra ports exposed), Resources (memory/CPU/PID limits), Secrets (.env not hardcoded, .gitignore, .env.example), Health & Logging (healthcheck, log rotation, restart policy), Images (version-pinned, minimal base).

Display as compact checklist with `[x]`/`[ ]` per item and a score. If any checks fail → fix them immediately before finishing (kanban mode); interactive sessions may offer the fix.

---

## Step 8: Generate Deploy Scripts (Production)

Generate production deployment scripts in `deploy/scripts/` from templates.

Read `references/DEPLOY-SCRIPTS.md` for script customization points and generation rules.

Templates: `templates/deploy.sh`, `templates/update.sh`, `templates/logs.sh`, `templates/health-check.sh`, `templates/rollback.sh`, `templates/backup.sh`

**Safety:** generating these scripts into the repo is in scope. **Executing** them against a production host is not — that requires explicit human approval (`kanban_block` if the task demands it).

---

## Step 9: Summary & Hand Off

Display a summary of all created/updated files using the format from `references/SUMMARY-FORMAT.md`.

Return a structured handoff (mode, files written, services table, security checklist score, assumptions/deferred items) and **complete on evidence** via `kanban_complete`. Suggest follow-ups in the handoff: load skill `aif-build-automation` for Docker targets, load skill `aif-docs` for documentation.

## Artifact Ownership and Config Policy

- Primary ownership: Docker artifacts (`Dockerfile`, `compose*.yml`, `.dockerignore`, `docker/*`, `deploy/scripts/*`, and related `.env.example` scaffolding when created by this skill).
- Allowed companion updates: none outside Docker and deployment artifacts by default.
- Config policy: config-agnostic by design. This skill uses repository detection, explicit task-body infrastructure choices, and fixed Hermes context files (`DESCRIPTION.md`, `.hermes-dev/skill-context/`) — Hermes has no `config.yaml`; paths are fixed.
