---
name: dev-handoff
description: >-
  Hand off a software-development request from a conversational topic to the AIF Dev Factory
  on the `departments` kanban board, then subscribe this topic so progress and completion
  come back here. Use when a NON-dev topic agent (e.g. a personal-assistant or marketing profile)
  is asked to build/change software — an app, parser, script, CLI, bot, API, feature, or a code
  bug fix — that is not that profile's own production job.
tags:
  - aif
  - dev-factory
  - kanban
  - handoff
  - routing
---

# dev-handoff — route dev work to the AIF Dev Factory

You are a conversational topic agent, not a developer. When the user asks for **software** to be built or changed, do **not** implement it yourself and do **not** hand-wave a design — route it to the AIF Dev Factory and step back. Progress will come back to this topic.

## When this applies
The request is to build/modify software: an app, parser, scraper, script, CLI, bot, API, integration, dashboard, a new feature, or a fix to existing code. If it's your own domain (marketing copy, ads, analytics, personal content) — handle it normally; this skill is only for dev work.

## Step 1 — Confirm scope in one line
Restate the goal in one sentence and note: is it a **new application** (no existing folder/repo) or a change to an **existing project/folder**? If the request is too vague to act on (no idea what the software should do), ask ONE clarifying question first — otherwise proceed.

## Step 2 — Create a triage task on the `departments` board
The board's orchestrator is `aif_planner`, which will decompose it into spec → plan → implement → verify → review.

```
hermes kanban --board departments create "<one-line goal>" --triage \
  --body "Originating topic: <this topic name>.
Kind: <new app | change to <existing path>>.
What it should do: <2-4 lines of concrete requirements/constraints>.
For a new app: aif_planner bootstraps a project + folder ~/Work/apps/<slug>/ with .hermes-dev/ (see aif-plan)."
```
Capture the printed task id (`t_...`). `--triage` parks it for `aif_planner` to spec + decompose; do NOT assign leaf work yourself and do NOT invent assignees.

## Step 3 — Subscribe THIS topic to the task (progress comes back here)
So the user hears about progress/completion in this same topic:

```
hermes kanban notify-subscribe <task_id> \
  --platform <this topic's platform, e.g. telegram> \
  --chat-id <this chat id> \
  --thread-id <this topic/thread id>
```
Use the current conversation's own source identifiers (the gateway session you are running in). If a `/kanban subscribe <task_id>` shortcut is available in this gateway, that auto-fills the current source — prefer it.

## Step 4 — Report back to the user
Tell the user, briefly: the task is now with the AIF Dev Factory (task id), what it will do, and that updates will land in this topic. Do not produce a design doc or start coding.

## Rules
- Never implement the software yourself — that's `aif_implementer`'s job under review.
- One triage task per distinct request; if the user asks for a change to an app that already has a project, mention the existing folder in the body so `aif_planner` reuses it instead of creating a new one.
- If you lack shell/CLI access, use the `kanban_create` tool targeting the `departments` board instead, then the subscription tool/command.
- Stay in your lane afterwards: the department owns delivery; you own relaying status to the user.

## When the task blocks asking for input
Relay the question to the user in the topic. When the user answers, post the answer as a kanban comment AND unblock in one call: `hermes kanban --board departments comment <id> "<answer>" --unblock`. A comment alone never resumes a blocked task.
