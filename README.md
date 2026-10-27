# Claude Session Image Audit

**Find the screenshots quietly accumulating inside Claude Code session logs.**

A local, read-only CLI that scans Claude Code JSONL sessions and reports embedded image payload sizes, tool-result images, duplicate payloads, and malformed records. It does not upload, print, delete, or rewrite session content.

## Why this exists

Claude Code users have reported that screenshots returned by tools can take up a large share of local session transcripts, while ordinary usage summaries do not show those bytes separately. One public report measured 171.5 MB of base64 image data across 312 sessions; that is one user's sample, not a platform-wide estimate. This tool makes the same kind of local measurement available without sharing a transcript.

## What it reports

- Base64 image block count and encoded size per session
- Images nested inside `tool_result` blocks, separated from other image blocks
- Exact duplicate image payloads within each session
- Estimated decoded image bytes, derived from base64 length
- Malformed JSONL line counts
- Table or JSON output, in English or Chinese

The byte counts describe stored transcript data. They are not token counts, billed usage, or a guarantee that a provider resends every image on every turn.

## Quick start

Requires Python 3.10 or later. There are no runtime dependencies.

```bash
python3 -m pip install .
claude-session-image-audit
```

By default it scans `~/.claude/projects` recursively. Point it at one session or another directory when needed:

```bash
claude-session-image-audit ~/.claude/projects
claude-session-image-audit /path/to/session.jsonl --lang zh
claude-session-image-audit ~/.claude/projects --format json > image-audit.json
```

Use `--show-paths` to include absolute local paths in output. The default report uses paths relative to the scan root.

## Try the synthetic demo

The fixture contains two identical, tiny base64 strings so you can see how tool-result images and repeated payloads are counted. It contains no real screenshot.

```bash
claude-session-image-audit examples/synthetic-session.jsonl
```

## Safety and scope

- Reads local `.jsonl` files only; makes no network requests.
- Does not display, export, modify, compact, or delete image/session data.
- Does not estimate token charges or claim that duplicate images were billed repeatedly.
- Supports Claude Code session JSONL only. Other agent log formats are not included yet.

## 中文

**找出 Claude Code 会话记录里悄悄累积的截图数据。**

这是一个本地只读命令行工具：扫描 Claude Code 的 JSONL 会话，统计内嵌图片的 Base64 大小、工具返回图片、会话内重复图片，以及格式错误的记录。它不会上传、打印、删除或改写会话内容。

### 快速开始

需要 Python 3.10 或更新版本；运行时不依赖第三方库。

```bash
python3 -m pip install .
claude-session-image-audit --lang zh
```

默认递归扫描 `~/.claude/projects`，也可以指定单个会话文件或其他目录：

```bash
claude-session-image-audit ~/.claude/projects --lang zh
claude-session-image-audit /path/to/session.jsonl --lang zh --format json
```

### 能看到什么

- 每个会话的图片块数量和 Base64 数据大小
- `tool_result` 中的图片与其他图片块分别统计
- 每个会话中完全相同的重复图片负载
- 按 Base64 长度估算的图片解码大小
- JSONL 格式错误行数

这些数字描述会话文件里的数据大小，不等于 token 数、账单费用，也不证明模型每轮都重新接收了同一张图片。

## Background

The tool responds to public reports such as [Claude Code issue #86421](https://github.com/anthropics/claude-code/issues/86421). It is an independent implementation and does not include code from that issue or from other projects.
