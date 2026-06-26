# Hooks · v2.6

## 文件清单

| 文件 | 用途 |
|---|---|
| `hooks.json` | Claude Code 的 SessionStart hook 配置（直接调 session-start，不走 polyglot） |
| `session-start` | bash 脚本 · 在 SessionStart 时打印 skill 列表 + 工作流提醒，输出到 Claude additionalContext |
| `hooks-cursor.json` | Cursor IDE 用的 hook 配置 · 经 `run-hook.cmd` polyglot 调度（Windows 兼容，见下「Cursor Windows 兼容修复」） |
| `run-hook.cmd` | polyglot bash/batch 调度器 · Windows 上由 cmd 执行后调 bash 跑 `session-start`；Unix 上由 bash 直接跑 · `hooks-cursor.json` 入口 |

## 安装

`session-start` 需要可执行权限。`setup.sh` 自动做了：

```bash
chmod +x hooks/session-start hooks/run-hook.cmd
```

如果手动 clone：

```bash
chmod +x hooks/session-start
```

## v2.6 论坛 bug 修复说明

论坛反馈 "Claude plugin 执行不了"，原因是旧版 `hooks.json` 调用
`run-hook.cmd` 中转脚本，而 `.cmd` 在 macOS Claude Code 安全策略下：
1. 权限检查未通过（Claude Code 可能拒绝执行 `.cmd` 后缀脚本）
2. polyglot bash/batch 用 `: <<'BATCH_SCRIPT'` heredoc 体操，对解释器有要求

v2.6 修复：`hooks.json` 改为**直接调** `session-start`（标准 sh 脚本，已有 shebang），
跳过 `run-hook.cmd` 中间层。Windows 用户若依赖该中转，仍可手动调用。

## Cursor Windows 兼容修复

论坛反馈（同 `obra/superpowers#1449`）：Windows 版 Cursor 在 SessionStart 时会把
`hooks-cursor.json` 里无后缀的 `./hooks/session-start` 当成文件「打开」，弹出
「选择打开方式」对话框，而非用 bash 执行。

修复：`hooks-cursor.json` 的 `command` 改为经 `run-hook.cmd` polyglot 中转：

```diff
- "command": "./hooks/session-start"
+ "command": "./hooks/run-hook.cmd session-start"
```

- Windows：cmd 直接执行 `.cmd`，再调 `bash hooks/session-start`，输出合法 JSON，退出 0
- macOS/Linux：bash 执行 `run-hook.cmd`（shebang + 可执行位），内部 `exec` 到 `session-start`

注意：Windows 端依赖 `bash` 在 PATH 中（Git for Windows / WSL 自带）。`hooks.json`
（Claude Code）保持直接调 `session-start` 不变，避免 v2.6 已修复的 `.cmd` 在 macOS
Claude Code 安全策略下被拒问题。

## 调试

若 SessionStart 没有触发：

1. 确认 `session-start` 有 `+x` 权限：`ls -l hooks/session-start`
2. 手动测试输出：`./hooks/session-start | head -5`（应看到 JSON 含 `additionalContext`）
3. 检查 Claude Code 日志（`Cmd+Shift+P → Developer: Open Logs`）
4. 若 Claude Code 报路径错误，确认 `${CLAUDE_PLUGIN_ROOT}` 正确解析
