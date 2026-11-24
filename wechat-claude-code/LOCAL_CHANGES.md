# 本地改动说明（相对上游）

- 上游：<https://github.com/Wechat-ggGitHub/wechat-claude-code>（MIT，`Copyright (c) 2026 Wechat-ggGitHub`）
- 许可证：同目录 `LICENSE`，为上游原文件，未改；本地改动属于衍生作品，版权仍归上游 + 本地修改者
- 本地不是干净快照，而是**分支式改写**（`git diff` 约 +968 / −6206 行）

## 新增（上游没有）

| 文件 | 作用 |
|---|---|
| `src/permission.ts` | 权限审批通道：把 Claude Code 的权限请求转发到微信，由人在微信里批准/拒绝 |
| `start.bat` | Windows 启动脚本（内含本机路径 `E:\CodeProject\ClaudeRoom\wechat-claude-code-main\...` 与 `E:\Git\bin\bash.exe`，换机器要改） |
| `README_zh.md` | 中文说明（上游是 `README_en.md` + 英文 `README.md`） |
| `agents/openai.yaml` | 供 Codex / OpenAI 侧识别的 skill 元数据 |

## 删除（上游有、本地没有）

`docs/`（含 2026-06-20 消息批处理文档等）、`src/tools/visualize-logs.ts`、`src/tests/*`、
`src/claude/tool-noise-filter.ts`、`src/claude/turn-router.ts`、`src/constants.ts`、
`src/pending-queue.ts`、`src/wechat/upload.ts`、`tool-noise/`、`README_en.md`。
即：本地把测试、日志可视化、工具噪音过滤、上传通道等裁掉了，只留主链路 + 权限审批。

## 修改

`SKILL.md`、`src/main.ts`、`src/claude/provider.ts`、`src/commands/{handlers,router}.ts`、
`src/wechat/*`（api / media / send / login / types 等）、`package.json`、`scripts/daemon.sh`。

## 注意

- 删掉的测试与 `tool-noise`/`turn-router` 是上游后续修 bug 的依据；升级时按 `../../SYNC.md`
  把这些**新文件单独拿回来**再合，别整目录覆盖。
- 上游 README 描述 macOS（launchd）；本目录的 `start.bat` / `daemon.sh` 已按 Windows 改过，
  两者不要互相覆盖。
