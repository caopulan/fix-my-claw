# Contributing

Thanks for taking the time to contribute!

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Local smoke checks

```bash
python -m compileall -q src
fix-my-claw --help
```

## Pull requests

- Keep changes focused and easy to review.
- Prefer minimal, reversible recovery actions (especially around `ai.*`).
- Update documentation when behavior/config changes.

## Reporting issues

When reporting a bug, please include:

- Your OS + Python version
- Your OpenClaw version
- The relevant `fix-my-claw` config (redacted)
- Recent logs from `~/.fix-my-claw/fix-my-claw.log`
- The latest attempt directory under `~/.fix-my-claw/attempts/`

