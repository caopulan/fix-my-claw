# OpenClaw Recovery Runbook (expanded)

## Objective

Restore OpenClaw health. This stage allows broader changes, including code/installation updates, but only as a last resort.

## Non-negotiable constraints

- Non-interactive: do not ask questions and do not require confirmation.
- Keep changes minimal and reversible where possible.
- Still prefer official OpenClaw recovery commands and configuration/workspace fixes first.

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

- Evidence is available under `$attempt_dir`.

## Procedure

1) Review evidence and attempt the least invasive fix first.
2) If needed, re-run official recovery steps (non-interactive).
3) Only then consider code/installation changes.
4) Verify with `$health_cmd` and `$status_cmd` until both succeed.

## Deliverable

Write a concise report to `$attempt_dir/report.md`:

- Root cause hypothesis (with evidence)
- Exact changes (files + commands)
- Verification outputs (health/status)
