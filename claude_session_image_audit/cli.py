from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator

DEFAULT_ROOT = Path.home() / ".claude" / "projects"


def _image_blocks(value: Any, in_tool_result: bool = False) -> Iterator[tuple[str, str, bool]]:
    """Yield (base64 data, media type, came from tool_result) for image blocks."""
    if isinstance(value, list):
        for item in value:
            yield from _image_blocks(item, in_tool_result)
        return

    if not isinstance(value, dict):
        return

    inside_tool_result = in_tool_result or value.get("type") == "tool_result"
    if value.get("type") == "image":
        source = value.get("source")
        if (
            isinstance(source, dict)
            and source.get("type") == "base64"
            and isinstance(source.get("data"), str)
        ):
            yield source["data"], str(source.get("media_type", "unknown")), inside_tool_result

    for child in value.values():
        yield from _image_blocks(child, inside_tool_result)


def _decoded_size_estimate(data: str) -> int:
    compact = "".join(data.split())
    padding = min(2, len(compact) - len(compact.rstrip("=")))
    return max(0, (len(compact) * 3 // 4) - padding)


def _scan_file(path: Path, display_path: str) -> dict[str, Any]:
    session: dict[str, Any] = {
        "file": display_path,
        "file_bytes": path.stat().st_size,
        "json_lines": 0,
        "malformed_json_lines": 0,
        "image_blocks": 0,
        "tool_image_blocks": 0,
        "other_image_blocks": 0,
        "base64_bytes": 0,
        "decoded_image_bytes_estimate": 0,
        "duplicate_image_blocks": 0,
        "duplicate_base64_bytes": 0,
    }
    seen_payloads: set[bytes] = set()

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                session["malformed_json_lines"] += 1
                continue

            session["json_lines"] += 1
            for data, _media_type, from_tool in _image_blocks(record):
                encoded_size = len(data.encode("utf-8"))
                digest = hashlib.sha256(data.encode("utf-8")).digest()
                session["image_blocks"] += 1
                session["base64_bytes"] += encoded_size
                session["decoded_image_bytes_estimate"] += _decoded_size_estimate(data)
                if from_tool:
                    session["tool_image_blocks"] += 1
                else:
                    session["other_image_blocks"] += 1

                if digest in seen_payloads:
                    session["duplicate_image_blocks"] += 1
                    session["duplicate_base64_bytes"] += encoded_size
                else:
                    seen_payloads.add(digest)

    return session


def _collect_files(root: Path) -> tuple[Path, list[Path]]:
    expanded = root.expanduser().resolve()
    if expanded.is_file():
        return expanded.parent, [expanded]
    if not expanded.is_dir():
        raise FileNotFoundError(f"Path does not exist: {root}")
    files = sorted(path for path in expanded.rglob("*.jsonl") if path.is_file())
    return expanded, files


def _display_path(path: Path, root: Path, show_paths: bool) -> str:
    if show_paths:
        return str(path)
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _aggregate(sessions: list[dict[str, Any]]) -> dict[str, int]:
    fields = (
        "file_bytes",
        "json_lines",
        "malformed_json_lines",
        "image_blocks",
        "tool_image_blocks",
        "other_image_blocks",
        "base64_bytes",
        "decoded_image_bytes_estimate",
        "duplicate_image_blocks",
        "duplicate_base64_bytes",
    )
    return {field: sum(int(session[field]) for session in sessions) for field in fields}


def _format_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if amount < 1024 or unit == "GiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{value} B"
        amount /= 1024
    return f"{value} B"


def _print_table(report: dict[str, Any], lang: str, top: int) -> None:
    if lang == "zh":
        print("会话文件                 图片块   工具图片   Base64大小   重复图片   文件大小")
        print("-" * 84)
    else:
        print("Session file              Images  Tool images  Base64 size  Repeated  File size")
        print("-" * 84)

    sessions = report["sessions"][:top]
    if not sessions or not any(session["image_blocks"] for session in sessions):
        print("未找到内嵌 Base64 图片块。" if lang == "zh" else "No embedded base64 image blocks found.")
        return

    for session in sessions:
        name = session["file"]
        if len(name) > 24:
            name = "…" + name[-23:]
        print(
            f"{name:<24} {session['image_blocks']:>6}"
            f" {session['tool_image_blocks']:>12}"
            f" {_format_size(session['base64_bytes']):>12}"
            f" {session['duplicate_image_blocks']:>9}"
            f" {_format_size(session['file_bytes']):>10}"
        )

    total = report["totals"]
    if lang == "zh":
        print("\n扫描会话：{files}  图片块：{images}  工具图片：{tool_images}".format(
            files=report["files_scanned"], images=total["image_blocks"], tool_images=total["tool_image_blocks"]
        ))
        print("Base64 数据：{encoded}  解码后估算：{decoded}  重复块：{duplicates} / {duplicate_bytes}".format(
            encoded=_format_size(total["base64_bytes"]),
            decoded=_format_size(total["decoded_image_bytes_estimate"]),
            duplicates=total["duplicate_image_blocks"],
            duplicate_bytes=_format_size(total["duplicate_base64_bytes"]),
        ))
        print("只读扫描；不会输出图片内容或改写会话文件。")
    else:
        print("\nSessions: {files}  Image blocks: {images}  Tool images: {tool_images}".format(
            files=report["files_scanned"], images=total["image_blocks"], tool_images=total["tool_image_blocks"]
        ))
        print("Base64 data: {encoded}  Decoded estimate: {decoded}  Repeated: {duplicates} / {duplicate_bytes}".format(
            encoded=_format_size(total["base64_bytes"]),
            decoded=_format_size(total["decoded_image_bytes_estimate"]),
            duplicates=total["duplicate_image_blocks"],
            duplicate_bytes=_format_size(total["duplicate_base64_bytes"]),
        ))
        print("Read-only scan; image contents are not shown and session files are not changed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-session-image-audit",
        description="Measure embedded base64 image payloads in local Claude Code JSONL sessions.",
    )
    parser.add_argument("path", nargs="?", default=str(DEFAULT_ROOT), help="JSONL file or directory (default: ~/.claude/projects)")
    parser.add_argument("--lang", choices=("en", "zh"), default="en", help="Output language")
    parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format")
    parser.add_argument("--top", type=int, default=25, help="Maximum session rows to show in table output")
    parser.add_argument("--show-paths", action="store_true", help="Show absolute file paths instead of paths relative to the scan root")
    args = parser.parse_args(argv)

    if args.top < 1:
        parser.error("--top must be at least 1")

    try:
        root, files = _collect_files(Path(args.path))
        sessions = [
            _scan_file(path, _display_path(path, root, args.show_paths))
            for path in files
        ]
    except (OSError, UnicodeError) as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
        return 2

    sessions.sort(key=lambda session: session["base64_bytes"], reverse=True)
    report = {
        "schema_version": 1,
        "scope": "claude-code-local-jsonl",
        "files_scanned": len(sessions),
        "totals": _aggregate(sessions),
        "sessions": sessions,
    }

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(report, args.lang, args.top)
    return 0
