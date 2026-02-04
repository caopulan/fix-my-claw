# fix-my-claw

[中文](README_ZH.md)

`fix-my-claw` is a 24/7 watchdog + self-healing tool for OpenClaw:

1. **Probe periodically**: runs `openclaw gateway health --json` and `openclaw gateway status --json` on an interval.
2. **Official repair first**: if unhealthy, runs OpenClaw official repair steps (default: `openclaw doctor --repair` then `openclaw gateway restart`).
3. **AI fallback (optional)**: if official steps still fail, runs **Codex CLI** or **Claude Code** in fully non-interactive mode.
   - By default it is restricted to only modify **OpenClaw config/state dir** and **workspace dir**.
   - Only if you explicitly set `ai.allow_code_changes=true`, it will enter a second stage that may modify broader files/code.

> Warning: AI-assisted repair is equivalent to unattended “run commands + edit files”. Run it in a controlled environment and keep backups.

## Quick start

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

### 2) One-command start (recommended)

```bash
fix-my-claw up
```

This creates a default config at `~/.fix-my-claw/config.toml` (if missing) and starts the monitor loop.

### 3) Configure (optional)

```bash
mkdir -p ~/.fix-my-claw
cp examples/fix-my-claw.toml ~/.fix-my-claw/config.toml
```

### 4) Run

```bash
fix-my-claw check
fix-my-claw repair
fix-my-claw monitor
```

## systemd

Copy files from `deploy/systemd/`:

- Option A (recommended): `fix-my-claw.service` runs a long-lived monitor loop.
- Option B: `fix-my-claw-oneshot.service` + `fix-my-claw.timer` runs `fix-my-claw repair` periodically (cron-style).

## Non-interactive AI fallback

### Codex CLI

The default config uses `codex exec` with `approval_policy="never"` so it never prompts for confirmation.

Stage 1 uses `-s workspace-write` and `--add-dir` to restrict write access to:

- `openclaw.workspace_dir`
- `openclaw.state_dir`
- `monitor.state_dir`

### Claude Code

Claude Code’s non-interactive flags vary by version, so this project treats it as a configurable command (`ai.command` + `ai.args`).

## License

MIT, see `LICENSE`.
