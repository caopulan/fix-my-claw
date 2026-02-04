# fix-my-claw

[English](README.md)

一个 7×24 无人值守的 OpenClaw 守护/自愈工具：

1. **定时探测**：周期性执行 `openclaw gateway health --json` 与 `openclaw gateway status --json`（可配置）。
2. **官方修复优先**：失败时先跑 OpenClaw 官方修复手段（默认：`openclaw doctor --repair` + `openclaw gateway restart`，可配置）。
3. **AI 兜底（可选）**：官方手段仍失败，再调用 **Codex CLI** 或 **Claude Code** 自动修复。
   - 默认严格限制：只允许改 **OpenClaw 配置目录** + **workspace 目录**（符合“优先修复配置和 workspace 文件”的要求）。
   - 若你显式开启 `ai.allow_code_changes=true`，才会进入更高权限的第二阶段（可能改动更多文件）。

> 免责声明：AI 自动修复功能本质上等同于“自动执行 shell + 改文件”。请务必在隔离环境/受控账号下运行，并设置合理的目录权限与备份策略。

## 快速开始

### 1) 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

### 2) 一键启动（推荐）

```bash
fix-my-claw up
```

会在 `~/.fix-my-claw/config.toml` 不存在时自动生成默认配置，然后启动常驻监控循环。

### 3) 配置（可选）

复制示例配置并按需修改：

```bash
mkdir -p ~/.fix-my-claw
cp examples/fix-my-claw.toml ~/.fix-my-claw/config.toml
```

### 4) 单次检查 / 修复 / 监控

```bash
fix-my-claw check
fix-my-claw repair
fix-my-claw monitor
```

## systemd（推荐）

将 `deploy/systemd/*` 拷贝到你的服务器：

- 方式 A：`fix-my-claw.service`（长驻进程）：每隔 `interval_seconds` 探测并自愈
- 方式 B：`fix-my-claw-oneshot.service` + `fix-my-claw.timer`（cron 风格）：定时跑一次 `fix-my-claw repair`

## AI 兜底的非交互模式

### Codex CLI

默认配置使用 `codex exec`，并通过 `-c approval_policy="never"` 来确保无确认提示。

同时在第一阶段使用 `-s workspace-write`，配合 `--add-dir` 仅允许写：

- `openclaw.workspace_dir`
- `openclaw.state_dir`
- `monitor.state_dir`

### Claude Code

Claude Code 的参数与非交互模式因版本而异，本项目将其作为“可配置命令”处理；你需要在配置里把 `ai.command/ai.args` 配好。

## 目录结构（默认）

- `~/.fix-my-claw/`：本工具的 state、日志、修复尝试产物
- `~/.openclaw/`：OpenClaw 的配置与数据目录（可配置）
- `~/.openclaw/workspace/`：OpenClaw workspace（可配置）

## 开源协议

MIT License，见 `LICENSE`。
