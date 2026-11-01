# Claude Session Image Audit

**Find the screenshots quietly accumulating inside Claude Code session logs.**

A local, read-only CLI that scans Claude Code JSONL sessions and reports embedded image payload sizes, tool-result images, duplicate payloads, and malformed records. It does not upload, print, delete, or rewrite session content.

**[Download v0.1.0 preview wheel](https://github.com/LydiaTools/claude-session-image-audit/releases/download/v0.1.0/claude_session_image_audit-0.1.0-py3-none-any.whl)** · [Release notes and checksum](https://github.com/LydiaTools/claude-session-image-audit/releases/tag/v0.1.0)

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

## Check image block structure

If a session reports an image-related error, add `--check-images` to count
base64 image blocks with missing data, invalid base64, missing or unsupported
media types, or a signature that does not match the declared PNG, JPEG, GIF or
WebP type. Findings are counted per session and in the total; the data itself
is never printed. Checks decode in bounded chunks and do not modify the file.

```bash
claude-session-image-audit /path/to/session.jsonl --check-images
claude-session-image-audit /path/to/session.jsonl --check-images --format json
```

This is a basic structural check, not a full image decode or an API request.
A clean result does not prove an image is complete or that a provider will
accept it. The check covers `image` blocks with a `base64` source, not raw
strings or other image formats. It cannot determine the cause of an API error
or repair a session. The synthetic demo's tiny strings are not actual image
files, so their signatures are expected to be flagged.

## Quick start

Requires Python 3.10 or later. There are no runtime dependencies. Install the preview directly from GitHub, then check the available options without scanning any files:

```bash
python3 -m pip install https://github.com/LydiaTools/claude-session-image-audit/releases/download/v0.1.0/claude_session_image_audit-0.1.0-py3-none-any.whl
python3 -m claude_session_image_audit --help
```

To run from a cloned source checkout instead, use `python3 -m pip install .` inside that checkout. The commands below use the installed `claude-session-image-audit` entry point; if it is not on your PATH, replace it with `python3 -m claude_session_image_audit`.

By default it scans `~/.claude/projects` recursively. Point it at one session or another directory when needed:

```bash
claude-session-image-audit ~/.claude/projects
claude-session-image-audit /path/to/session.jsonl --lang zh
claude-session-image-audit ~/.claude/projects --format json > image-audit.json
```

Use `--show-paths` to include absolute local paths in output. The default report uses paths relative to the scan root.

## Try the synthetic demo

The source fixture contains two identical, tiny base64 strings so you can see how tool-result images and repeated payloads are counted. It contains no real screenshot. The wheel does not include this fixture; to try it, clone the matching release and run:

```bash
git clone --branch v0.1.0 https://github.com/LydiaTools/claude-session-image-audit.git
cd claude-session-image-audit
python3 -m claude_session_image_audit examples/synthetic-session.jsonl --check-images
```

## Safety and scope

- Reads local `.jsonl` files only; makes no network requests.
- Does not display, export, modify, compact, or delete image/session data.
- Does not estimate token charges or claim that duplicate images were billed repeatedly.
- Supports Claude Code session JSONL only. Other agent log formats are not included yet.

## 中文

**找出 Claude Code 会话记录里悄悄累积的截图数据。**

这是一个本地只读命令行工具：扫描 Claude Code 的 JSONL 会话，统计内嵌图片的 Base64 大小、工具返回图片、会话内重复图片，以及格式错误的记录。它不会上传、打印、删除或改写会话内容。

**[下载 v0.1.0 预览安装包](https://github.com/LydiaTools/claude-session-image-audit/releases/download/v0.1.0/claude_session_image_audit-0.1.0-py3-none-any.whl)** · [更新说明与校验值](https://github.com/LydiaTools/claude-session-image-audit/releases/tag/v0.1.0)

### 快速开始

需要 Python 3.10 或更新版本；运行时不依赖第三方库。可以直接安装 GitHub 预览包，再查看参数；查看帮助不会扫描文件：

```bash
python3 -m pip install https://github.com/LydiaTools/claude-session-image-audit/releases/download/v0.1.0/claude_session_image_audit-0.1.0-py3-none-any.whl
python3 -m claude_session_image_audit --help
```

如果使用克隆的源码，请进入源码目录后运行 `python3 -m pip install .`。下面的命令使用安装后的 `claude-session-image-audit`；若该命令不在 PATH 中，可换成 `python3 -m claude_session_image_audit`。

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

### 检查图片块结构

如果会话出现图片相关错误，可添加 `--check-images`：

```bash
claude-session-image-audit /path/to/session.jsonl --lang zh --check-images
```

它会统计缺少数据、Base64 格式异常、媒体类型缺失或不支持，以及文件标识与 PNG、JPEG、GIF、WebP 声明不一致的图片块。检查按分块处理，不显示图片内容，也不修改文件。

这只是基础结构检查，不会完整解码图片、发送 API 请求或修复会话；没有发现异常也不代表图片完整或一定能被服务商接受。检查范围是来源类型为 `base64` 的 `image` 块，不覆盖普通字符串或其他图片格式。自带示例是虚构短字符串，并非真实图片，文件标识出现提示属于预期。

## Background

The tool responds to public reports such as [Claude Code issue #86421](https://github.com/anthropics/claude-code/issues/86421). It is an independent implementation and does not include code from that issue or from other projects.
