from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator

DEFAULT_ROOT = Path.home() / ".claude" / "projects"


def _image_blocks(value: Any, in_tool_result: bool = False) -> Iterator[tuple[Any, Any, bool]]:
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
        ):
            yield source.get("data"), source.get("media_type"), inside_tool_result

    for child in value.values():
        yield from _image_blocks(child, inside_tool_result)


def _decoded_size_estimate(data: str) -> int:
    compact = "".join(data.split())
    padding = min(2, len(compact) - len(compact.rstrip("=")))
    return max(0, (len(compact) * 3 // 4) - padding)


def _inspect_image(data: Any, media_type: Any) -> set[str]:
    """Check basic block structure without retaining or printing image contents.

    This is not an image decoder or a provider request validator.
    """
    problems: set[str] = set()
    supported = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    if not isinstance(media_type, str) or media_type not in supported:
        problems.add("media_type")
    if not isinstance(data, str) or not data:
        problems.add("missing_data")
        return problems

    # Decode bounded chunks: avoid allocating a second full-size image buffer.
    prefix = bytearray()
    try:
        for start in range(0, len(data), 65536):
            chunk = data[start:start + 65536]
            if start + len(chunk) < len(data) and "=" in chunk:
                raise ValueError("padding before end")
            decoded = base64.b64decode(chunk, validate=True)
            if len(prefix) < 12:
                prefix.extend(decoded[:12 - len(prefix)])
    except (ValueError, binascii.Error):
        problems.add("invalid_base64")
        return problems

    signatures = {
        "image/png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": prefix.startswith(b"\xff\xd8\xff"),
        "image/gif": prefix.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP",
    }
    if isinstance(media_type, str) and media_type in supported and not signatures[media_type]:
        problems.add("signature_mismatch")
    return problems


def _scan_file(path: Path, display_path: str, check_images: bool = False) -> dict[str, Any]:
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
    if check_images:
        session["image_checks"] = {key: 0 for key in (
            "blocks_checked", "blocks_with_findings", "missing_data",
            "invalid_base64", "media_type", "signature_mismatch",
        )}
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
            for data, media_type, from_tool in _image_blocks(record):
                if check_images:
                    findings = _inspect_image(data, media_type)
                    checks = session["image_checks"]
                    checks["blocks_checked"] += 1
                    checks["blocks_with_findings"] += bool(findings)
                    for finding in findings:
                        checks[finding] += 1
                if not isinstance(data, str):
                    continue
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


def _print_image_checks(report: dict[str, Any], lang: str, top: int) -> None:
    if "image_checks" not in report:
        return
    checks = report["image_checks"]
    if lang == "zh":
        print("图片结构检查：{blocks_checked} 块，{blocks_with_findings} 块需检查；缺少数据 {missing_data}，Base64 异常 {invalid_base64}，媒体类型异常 {media_type}，文件标识不符 {signature_mismatch}。".format(**checks))
    else:
        print("Image checks: {blocks_checked} blocks, {blocks_with_findings} with findings; missing data {missing_data}, invalid base64 {invalid_base64}, media type {media_type}, signature mismatch {signature_mismatch}.".format(**checks))
    affected = [session for session in report["sessions"] if session["image_checks"]["blocks_with_findings"]]
    if affected:
        print("需检查的会话：" if lang == "zh" else "Sessions with findings:")
        for session in affected[:top]:
            values = session["image_checks"]
            print("  {file}: missing_data={missing_data}, invalid_base64={invalid_base64}, media_type={media_type}, signature_mismatch={signature_mismatch}".format(file=session["file"], **values))
        if len(affected) > top:
            print(f"  +{len(affected) - top} " + ("个会话未显示；可增大 --top 或使用 JSON。" if lang == "zh" else "more sessions; increase --top or use JSON."))


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
        _print_image_checks(report, lang, top)
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
    _print_image_checks(report, lang, top)


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
    parser.add_argument("--check-images", action="store_true", help="Check base64, media type and image signatures without printing image content")
    args = parser.parse_args(argv)

    if args.top < 1:
        parser.error("--top must be at least 1")

    try:
        root, files = _collect_files(Path(args.path))
        sessions = [
            _scan_file(path, _display_path(path, root, args.show_paths), args.check_images)
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
    if args.check_images:
        keys = ("blocks_checked", "blocks_with_findings", "missing_data", "invalid_base64", "media_type", "signature_mismatch")
        report["image_checks"] = {key: sum(session["image_checks"][key] for session in sessions) for key in keys}

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(report, args.lang, args.top)
    return 0
