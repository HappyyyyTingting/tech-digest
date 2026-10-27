#!/usr/bin/env python3
"""Turn a digest Markdown file into a spoken MP3 with edge-tts.

Examples:
    python scripts/make_audio.py --latest --dry-run
    python scripts/make_audio.py --file digests/2026-10-27.md
    python scripts/make_audio.py --latest --upload

Uploading is configured through environment variables (Cloudflare R2):

    R2_ACCOUNT_ID
    R2_BUCKET
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    AUDIO_BASE_URL        Public base URL of the bucket, e.g. https://audio.example.com

TTS settings:

    TTS_VOICE             Defaults to zh-CN-XiaoxiaoNeural
    TTS_RATE              Defaults to +0%

The script writes audio/<date>.mp3 and audio/<date>.json. The JSON records the
duration, byte size and public URL so the site builder and email step can use
it without another network call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from send_email import (
    ROOT,
    digest_date,
    extract_title,
    read_markdown,
    resolve_digest_path,
)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
DEFAULT_OUT_DIR = "audio"
BYTES_PER_SECOND_48KBPS = 6000

_EMOJI_RE = re.compile(
    r"[\U0001F000-\U0001FAFF☀-➿️‍]+"
)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_SEPARATOR_RE = re.compile(r"^:?-{2,}:?$")
_TERMINAL_PUNCT = "。！？；…!?;"


def _inline_to_speech(text: str) -> str:
    """Strip inline Markdown and anything that should not be read aloud."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"[（(]\s*如\s*[）)]", "", text)
    text = re.sub(r"[（(]\s*[）)]", "", text)
    text = re.sub(r"(\d{4})-(\d{1,2})-(\d{1,2})", r"\1年\2月\3日", text)
    text = re.sub(r"[*_`~]+", "", text)
    text = text.replace("\\", "")
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _sentence(text: str) -> str:
    """Close a spoken line with punctuation, unless it is a lead-in."""
    text = text.strip()
    if not text:
        return ""
    if text.endswith(("：", ":", "，", ",")):
        return text
    if text[-1] not in _TERMINAL_PUNCT:
        text += "。"
    return text


def _table_row_to_speech(line: str) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if cells and all(not cell or _TABLE_SEPARATOR_RE.match(cell) for cell in cells):
        return ""
    spoken = [_inline_to_speech(cell) for cell in cells]
    spoken = [cell for cell in spoken if cell and cell not in {"...", "…", "—"}]
    if not spoken:
        return ""
    return _sentence("，".join(spoken))


def markdown_to_speech(markdown_text: str) -> str:
    """Convert digest Markdown into a script that sounds natural when read."""
    lines: list[str] = []
    in_fence = False

    for raw_line in markdown_text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue

        if line.startswith("|"):
            spoken = _table_row_to_speech(line)
            if spoken:
                lines.append(spoken)
            continue

        if re.fullmatch(r"[-*_]{3,}", line):
            continue

        if re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", line):
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            spoken = _inline_to_speech(heading.group(2))
            if spoken:
                lines.append(_sentence(spoken))
            continue

        line = re.sub(r"^>\s?", "", line)
        ordered = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if ordered:
            line = f"{ordered.group(1)}、{ordered.group(2)}"
        else:
            line = re.sub(r"^[-*+]\s+", "", line)

        spoken = _inline_to_speech(line)
        if spoken:
            lines.append(_sentence(spoken))

    return "\n".join(lines).strip()


def compose_speech(title: str, body_markdown: str) -> str:
    """Title first, then the cleaned body, as one readable script."""
    spoken_title = _sentence(_inline_to_speech(title))
    spoken_body = markdown_to_speech(body_markdown)
    return f"{spoken_title}\n{spoken_body}".strip()


def probe_duration(path: Path) -> float:
    """Read the MP3 duration; fall back to size at edge-tts' 48 kbps."""
    try:
        from mutagen.mp3 import MP3

        return float(MP3(str(path)).info.length)
    except Exception:  # noqa: BLE001 - duration is metadata only
        return path.stat().st_size / BYTES_PER_SECOND_48KBPS


def synthesize(text: str, voice: str, rate: str, out_path: Path, attempts: int = 3) -> None:
    """Render text to an MP3, retrying transient edge-tts failures."""

    async def _run() -> None:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        await communicate.save(str(out_path))

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if out_path.exists():
                out_path.unlink()
            asyncio.run(_run())
            if out_path.is_file() and out_path.stat().st_size > 0:
                return
            raise RuntimeError("edge-tts 生成了空文件")
        except Exception as exc:  # noqa: BLE001 - retry boundary
            last_error = exc
            if attempt >= attempts:
                break
            delay = 2.0 * (2 ** (attempt - 1))
            print(f"语音合成失败（第 {attempt}/{attempts} 次）：{exc}；{delay:g}s 后重试", file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError(f"语音合成失败（已重试 {attempts} 次）：{last_error}") from last_error


def upload_to_r2(local_path: Path, key: str) -> str:
    """Upload to Cloudflare R2 and return the public URL."""
    import boto3

    required = {
        "R2_ACCOUNT_ID": os.getenv("R2_ACCOUNT_ID", "").strip(),
        "R2_BUCKET": os.getenv("R2_BUCKET", "").strip(),
        "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        "AUDIO_BASE_URL": os.getenv("AUDIO_BASE_URL", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError("缺少 R2 配置：" + ", ".join(missing))

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{required['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=required["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=required["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    client.upload_file(
        str(local_path),
        required["R2_BUCKET"],
        key,
        ExtraArgs={
            "ContentType": "audio/mpeg",
            "CacheControl": "public, max-age=86400",
        },
    )
    return f"{required['AUDIO_BASE_URL'].rstrip('/')}/{key}"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把日报转换成语音 MP3。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", "-f", help="日报文件路径；不传则使用最新一份")
    group.add_argument("--latest", action="store_true", help="使用最新一份日报（默认行为）")
    parser.add_argument(
        "--voice",
        default=os.getenv("TTS_VOICE") or DEFAULT_VOICE,
        help=f"edge-tts 音色（默认 {DEFAULT_VOICE}）",
    )
    parser.add_argument(
        "--rate",
        default=os.getenv("TTS_RATE") or DEFAULT_RATE,
        help="语速，例如 +10%% 或 -5%%（默认 +0%%）",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help=f"输出目录（默认 {DEFAULT_OUT_DIR}/）",
    )
    parser.add_argument("--upload", action="store_true", help="生成后上传到 Cloudflare R2")
    parser.add_argument("--dry-run", action="store_true", help="只输出口语稿统计，不合成")
    parser.add_argument("--text-out", default="", help="可选：把口语稿写入指定文件，便于检查")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        digest_path = resolve_digest_path(args.file)
        markdown_text = read_markdown(digest_path)
        title, body = extract_title(markdown_text)
        if not body.strip():
            body = markdown_text

        date_text = digest_date(digest_path, title)
        if not date_text:
            raise ValueError(f"无法从文件名或标题中识别日期：{digest_path}")

        spoken_text = compose_speech(title, body)
        if not spoken_text:
            raise ValueError(f"日报没有可朗读的内容：{digest_path}")

        char_count = len(re.sub(r"\s+", "", spoken_text))
        estimate_seconds = char_count / 4.8
        print(f"日报文件：{_display_path(digest_path)}")
        print(f"朗读稿：{char_count} 字，预计约 {estimate_seconds / 60:.1f} 分钟")
        print(f"音色 / 语速：{args.voice} / {args.rate}")

        if args.text_out:
            text_path = Path(args.text_out).expanduser()
            if not text_path.is_absolute():
                text_path = Path.cwd() / text_path
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(spoken_text + "\n", encoding="utf-8")
            print(f"口语稿：{text_path}")

        if args.dry_run:
            print("dry-run：未生成音频。")
            return 0

        out_dir = Path(args.out_dir).expanduser()
        if not out_dir.is_absolute():
            out_dir = Path.cwd() / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        mp3_path = out_dir / f"{date_text}.mp3"

        synthesize(spoken_text, args.voice, args.rate, mp3_path)
        duration = probe_duration(mp3_path)
        size = mp3_path.stat().st_size

        url = ""
        if args.upload:
            try:
                url = upload_to_r2(mp3_path, mp3_path.name)
            except Exception as exc:  # noqa: BLE001 - report a clean CLI error
                raise RuntimeError(f"上传 R2 失败：{exc}") from exc
            print(f"已上传：{url}")

        metadata = {
            "date": date_text,
            "title": title,
            "file": mp3_path.name,
            "bytes": size,
            "duration": round(duration, 1),
            "voice": args.voice,
            "rate": args.rate,
            "url": url,
        }
        meta_path = out_dir / f"{date_text}.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        print(f"音频：{mp3_path}（{size / 1024:.0f} KB，{duration / 60:.1f} 分钟）")
        print(f"元数据：{meta_path}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
