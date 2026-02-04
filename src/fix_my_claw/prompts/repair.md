# OpenClaw Recovery Runbook (restricted)

## Objective

Restore OpenClaw to a healthy state by making the smallest safe change.

## Non-negotiable constraints

- Non-interactive: do not ask questions and do not require confirmation.
- Prefer official OpenClaw recovery commands first. Only then adjust configuration/workspace.
- Do not modify OpenClaw source code or install new tools in this stage.
- Keep changes reversible: before editing a file, write a backup copy next to it.

## Working directories

- OpenClaw workspace: `$workspace_dir`
- OpenClaw state/config dir: `$openclaw_state_dir`
- fix-my-claw state dir: `$monitor_state_dir`
- Current attempt dir: `$attempt_dir`

## Probes (verification)

- Health: `$health_cmd`
- Status: `$status_cmd`
- Logs: `$logs_cmd`

## Context

- OpenClaw is unhealthy.
- Official repair steps have already been executed, but OpenClaw is still unhealthy.
- Evidence is available under `$attempt_dir` (health/status/logs + official step outputs).

## Procedure

1) Review evidence under `$attempt_dir`.
2) Form a hypothesis (common causes: bad config, workspace corruption, missing files, stuck process, environment changes).
3) Apply the safest fix, in this order:
   - Configuration/state under `$openclaw_state_dir`
   - Workspace under `$workspace_dir`
4) Re-run `$health_cmd` and `$status_cmd` until both succeed.

## Deliverable

Write a concise report to `$attempt_dir/report.md`:

- Root cause hypothesis (with evidence)
- Exact changes (files + commands)
- Verification outputs (health/status)
