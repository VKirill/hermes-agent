# Core commits on this branch

The Hermes-core changes that this integration package rides on, oldest first
(`git log origin/main..HEAD --oneline`). The runtime assets in this directory
(skills / agents / profiles / installer) assume all of them are merged.

| Commit | Change |
|---|---|
| `4bb60ddec` | fix(kanban): explicit `workspace_kind='scratch'` no longer rewritten to a project worktree — an explicitly requested scratch workspace stays scratch even when a resolvable project is linked. |
| `c09e82b08` | feat(kanban): per-board `orchestrator_profile` / `default_assignee` override in `board.json`, resolved board → global config → active default — lets dev boards be led by `aif_planner` while other boards keep their own orchestrator. |
| `98207ca84` | feat(dashboard): board-aware Orchestration panel — reads/writes the per-board override with `?board=<slug>` and labels whether the value comes from the board or the global config. |
| `f83a95a1e` | feat(kanban): machine-readable `gate_result` contract for gate workers — stdlib validator, fail-closed wiring in `kanban_complete` (blocking verdicts rejected and routed to `kanban_block`), gate guidance for workers. |
| `d1ecf7878` | feat(kanban): AIF workflow stage machine + convergence-aware review gate (port of lee-to aif-handoff) — one card walks spec→…→verified, stage in `current_step_key`, assignee rewritten per stage, human gates, rework/manual_review_required decision tree, `kanban.max_review_iterations` / `auto_review_strategy` / `use_subagents` / `run_plan_improve` / `run_post_verify` config keys. |
| `b202d1768` | feat(dashboard): AIF workflow UI — stage chip and convergence badges on cards, workflow MetaRow and human-gate buttons (Approve / Request changes / Start implementation / Replan) in the drawer, `POST /tasks/{id}/workflow-action`. |
| `e1a479f75` | fix(kanban): exempt workflow stage transitions from the `recent_success` / `active_pr` respawn guards — a completed run is exactly how a stage hands off, so the guards must not stall the next stage's spawn. |
| `da3e22bfa` | fix(gateway): deliver profile-owned kanban notifications in single-adapter mode — the notifier no longer skips subscriptions whose owning profile has no dedicated adapter. |
| `4a495f028` | fix(gateway): kanban notifier honors `SendResult` soft-failures — a failed delivery now retries instead of being logged as delivered and silently dropped. |
| `7136809e6` | fix(telegram): anchor-less opt-in for DM-topic system notifications — kanban notifications (which have no inbound message to anchor to) can route into private-chat topic lanes via an explicit metadata opt-in. |
| `4341a5927` | feat(kanban): `--model` flag on `create` — per-task model override at creation time, e.g. pin review gates to a different model than the profile default. |
| `ec85ee32e` | feat(kanban): `comment --unblock` / `kanban_comment(unblock=true)` — answer a blocked task's question and resume it in one call (a comment alone never resumes a blocked task). |
