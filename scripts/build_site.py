#!/usr/bin/env python3
"""Build the static audio library and podcast feed for the digest.

Examples:
    python scripts/build_site.py --site-dir site
    python scripts/build_site.py --audio-base-url https://audio.example.com \
        --site-url https://example.github.io/tech-digest/ --no-head

The script scans digests/*.md, joins each digest with its audio metadata in
audio/<date>.json, and writes site/index.html plus site/feed.xml. Episodes whose
audio does not exist yet are skipped when --no-head is not set.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from send_email import extract_preheader, extract_title, read_markdown

DIGEST_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES_NS)

DEFAULT_TITLE = "科技股市入门日报"
DEFAULT_DESCRIPTION = "每天一份科技股市入门日报，通勤路上直接听。"
TZ_SHANGHAI = timezone(timedelta(hours=8))
HEAD_WORKERS = 8


@dataclass
class Episode:
    date: str
    title: str
    summary: str
    audio_url: str
    source_url: str
    bytes: int = 0
    duration: int = 0


def _itunes(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _read_metadata(audio_dir: Path, date_text: str) -> dict:
    path = audio_dir / f"{date_text}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def head_size(url: str, timeout: float = 8.0) -> int | None:
    """Return the file size, or None when the object does not exist."""
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length", "")
            return int(length) if length.isdigit() else 0
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404}:
            return None
        return 0
    except Exception:  # noqa: BLE001 - network failure should not drop episodes
        return 0


def _derive_repo() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repository:
        return repository
    try:
        raw = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", raw)
    return match.group(1) if match else ""


def default_site_url() -> str:
    repository = _derive_repo()
    if not repository:
        return ""
    owner, name = repository.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def default_repo_url() -> str:
    repository = _derive_repo()
    return f"https://github.com/{repository}" if repository else ""


def load_episodes(
    digests_dir: Path,
    audio_dir: Path,
    audio_base_url: str,
    *,
    head: bool = True,
    limit: int = 0,
    repo_url: str = "",
) -> list[Episode]:
    base = audio_base_url.rstrip("/")
    episodes: list[Episode] = []
    uploaded: set[str] = set()

    for path in sorted(digests_dir.glob("*.md")):
        date_text = path.stem
        if path.name.startswith("_") or not DIGEST_DATE_RE.fullmatch(date_text):
            continue

        markdown_text = read_markdown(path)
        title, _ = extract_title(markdown_text)
        summary = extract_preheader(markdown_text)
        audio_url = f"{base}/{date_text}.mp3"
        source_url = f"{repo_url}/blob/main/digests/{path.name}" if repo_url else ""

        metadata = _read_metadata(audio_dir, date_text)
        size = int(metadata.get("bytes") or 0)
        duration = int(float(metadata.get("duration") or 0))
        if metadata.get("url"):
            audio_url = str(metadata["url"])
            uploaded.add(date_text)

        local_mp3 = audio_dir / f"{date_text}.mp3"
        if local_mp3.is_file():
            size = size or local_mp3.stat().st_size
            if not duration:
                duration = _probe_local_duration(local_mp3)

        episodes.append(
            Episode(
                date=date_text,
                title=title or f"科技股市入门日报 {date_text}",
                summary=summary,
                audio_url=audio_url,
                source_url=source_url,
                bytes=size,
                duration=duration,
            )
        )

    if head:
        # Only trust an object as present when this run uploaded it, or when
        # HEAD succeeds. This keeps a failed upload out of the feed instead of
        # publishing a dead link just because a local MP3 exists.
        checked = [episode for episode in episodes if episode.date not in uploaded]
        if checked:
            with ThreadPoolExecutor(max_workers=HEAD_WORKERS) as pool:
                sizes = list(pool.map(lambda item: head_size(item.audio_url), checked))
            missing = set()
            for episode, size in zip(checked, sizes):
                if size is None:
                    missing.add(episode.date)
                else:
                    episode.bytes = episode.bytes or size
            episodes = [episode for episode in episodes if episode.date not in missing]

    episodes.sort(key=lambda item: item.date, reverse=True)
    if limit > 0:
        episodes = episodes[:limit]
    return episodes


def _probe_local_duration(path: Path) -> int:
    try:
        from mutagen.mp3 import MP3

        return int(MP3(str(path)).info.length)
    except Exception:  # noqa: BLE001 - duration is optional
        return int(path.stat().st_size / 6000)


def _pub_datetime(date_text: str) -> datetime:
    day = date_cls.fromisoformat(date_text)
    return datetime.combine(day, time_cls(hour=8), tzinfo=TZ_SHANGHAI)


def build_feed_xml(
    episodes: list[Episode],
    *,
    site_url: str,
    title: str,
    description: str,
    cover_url: str = "",
) -> str:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "zh-cn"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    ET.SubElement(channel, "generator").text = "tech-digest"
    ET.SubElement(channel, _itunes("author")).text = title
    ET.SubElement(channel, _itunes("explicit")).text = "false"
    ET.SubElement(channel, _itunes("category"), {"text": "Technology"})

    if cover_url:
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = cover_url
        ET.SubElement(image, "title").text = title
        ET.SubElement(image, "link").text = site_url
        ET.SubElement(channel, _itunes("image"), {"href": cover_url})

    total = len(episodes)
    for index, episode in enumerate(episodes):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = episode.title
        if episode.source_url:
            ET.SubElement(item, "link").text = episode.source_url
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = (
            f"tech-digest-{episode.date}"
        )
        ET.SubElement(item, "pubDate").text = format_datetime(_pub_datetime(episode.date))
        ET.SubElement(item, "description").text = episode.summary
        ET.SubElement(
            item,
            "enclosure",
            {
                "url": episode.audio_url,
                "length": str(episode.bytes),
                "type": "audio/mpeg",
            },
        )
        if episode.duration:
            ET.SubElement(item, _itunes("duration")).text = str(episode.duration)
        ET.SubElement(item, _itunes("episode")).text = str(total - index)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    return ET.tostring(rss, encoding="unicode", xml_declaration=True)


def format_duration_cn(seconds: int) -> str:
    if seconds <= 0:
        return ""
    minutes = max(1, (seconds + 30) // 60)
    return f"约 {minutes} 分钟"


def format_date_cn(date_text: str) -> str:
    try:
        day = date_cls.fromisoformat(date_text)
    except ValueError:
        return date_text
    return f"{day.year}年{day.month}月{day.day}日"


def render_index(
    episodes: list[Episode],
    *,
    feed_url: str,
    title: str,
    description: str,
) -> str:
    cards: list[str] = []
    for index, episode in enumerate(episodes):
        featured = " featured" if index == 0 else ""
        duration = format_duration_cn(episode.duration)
        meta_parts = [f'<time datetime="{html.escape(episode.date)}">{format_date_cn(episode.date)}</time>']
        if duration:
            meta_parts.append(f"<span>{html.escape(duration)}</span>")
        source = (
            f'<a class="source" href="{html.escape(episode.source_url, quote=True)}">阅读文字版 →</a>'
            if episode.source_url
            else ""
        )
        cards.append(
            f"""
      <article class="episode{featured}">
        <div class="meta">{' · '.join(meta_parts)}</div>
        <h2>{html.escape(episode.title)}</h2>
        <p class="summary">{html.escape(episode.summary)}</p>
        <audio controls preload="none" src="{html.escape(episode.audio_url, quote=True)}"></audio>
        {source}
      </article>"""
        )

    latest = (
        f"{len(episodes)} 期节目" if len(episodes) != 1 else "第 1 期节目"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{html.escape(title)}</title>
<link rel="alternate" type="application/rss+xml" title="{html.escape(title)}" href="{html.escape(feed_url, quote=True)}">
<style>
  :root {{
    --bg: #f5f7fa; --card: #ffffff; --ink: #1f2328; --muted: #667085;
    --line: #e4e8ec; --accent: #0b6bcb; --accent-ink: #ffffff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f1419; --card: #171d24; --ink: #e6edf3; --muted: #9aa7b4;
      --line: #27303a; --accent: #3b9eff; --accent-ink: #06121f;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.65;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 40px 16px 64px; }}
  header {{ margin-bottom: 28px; }}
  .eyebrow {{
    margin: 0 0 8px; font-size: 12px; letter-spacing: 2px;
    text-transform: uppercase; color: var(--muted);
  }}
  h1 {{ margin: 0 0 10px; font-size: 32px; line-height: 1.25; }}
  .lede {{ margin: 0 0 16px; color: var(--muted); }}
  .subscribe {{
    display: inline-block; padding: 8px 16px; border-radius: 999px;
    background: var(--accent); color: var(--accent-ink);
    text-decoration: none; font-size: 14px; font-weight: 600;
  }}
  .episode {{
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 20px 22px; margin: 0 0 14px;
  }}
  .episode.featured {{ border-color: var(--accent); }}
  .meta {{ font-size: 13px; color: var(--muted); margin-bottom: 6px; }}
  .episode h2 {{ margin: 0 0 8px; font-size: 19px; line-height: 1.4; }}
  .summary {{ margin: 0 0 12px; color: var(--muted); font-size: 15px; }}
  audio {{ width: 100%; height: 40px; }}
  .source {{
    display: inline-block; margin-top: 10px; font-size: 14px;
    color: var(--accent); text-decoration: none;
  }}
  footer {{ margin-top: 32px; font-size: 12px; color: var(--muted); }}
  footer a {{ color: inherit; }}
  @media (max-width: 520px) {{
    .wrap {{ padding-top: 28px; }}
    h1 {{ font-size: 26px; }}
    .episode {{ padding: 16px; }}
  }}
</style>
</head>
<body>
  <main class="wrap">
    <header>
      <p class="eyebrow">Tech Digest · 语音版</p>
      <h1>{html.escape(title)}</h1>
      <p class="lede">{html.escape(description)}</p>
      <a class="subscribe" href="{html.escape(feed_url, quote=True)}">订阅播客 RSS</a>
      <p class="meta" style="margin-top:10px;">{latest}，点击播放器即可收听。</p>
    </header>
    {''.join(cards) if cards else '<p class="summary">还没有生成语音，稍后再来看看。</p>'}
    <footer>
      由 GitHub Actions 自动生成 · <a href="{html.escape(feed_url, quote=True)}">RSS</a>
    </footer>
  </main>
</body>
</html>
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成语音日报的播客 feed 和静态页面。")
    parser.add_argument("--digests-dir", default="digests", help="日报目录（默认 digests）")
    parser.add_argument("--audio-dir", default="audio", help="音频元数据目录（默认 audio）")
    parser.add_argument("--site-dir", default="site", help="输出目录（默认 site）")
    parser.add_argument(
        "--audio-base-url",
        default=os.getenv("AUDIO_BASE_URL", "").strip(),
        help="音频的公开访问前缀，例如 https://audio.example.com",
    )
    parser.add_argument(
        "--site-url",
        default=os.getenv("SITE_URL", "").strip(),
        help="站点地址；默认根据 GitHub 仓库推导",
    )
    parser.add_argument(
        "--repo-url",
        default=os.getenv("REPO_URL", "").strip(),
        help="仓库地址；默认根据 GitHub 仓库推导",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="节目名称")
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION, help="节目简介")
    parser.add_argument("--limit", type=int, default=0, help="最多保留多少期（0 表示全部）")
    parser.add_argument(
        "--no-head",
        action="store_true",
        help="不检查远程音频是否存在（离线构建/测试用）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        audio_base_url = args.audio_base_url
        if not audio_base_url:
            raise ValueError("缺少 AUDIO_BASE_URL（R2 的公开访问地址）")

        site_url = args.site_url or default_site_url()
        if not site_url:
            raise ValueError("无法推导站点地址，请设置 SITE_URL")
        if not site_url.endswith("/"):
            site_url += "/"
        feed_url = f"{site_url}feed.xml"
        repo_url = (args.repo_url or default_repo_url()).rstrip("/")

        digests_dir = Path(args.digests_dir).expanduser()
        audio_dir = Path(args.audio_dir).expanduser()
        site_dir = Path(args.site_dir).expanduser()
        if not digests_dir.is_absolute():
            digests_dir = Path.cwd() / digests_dir
        if not audio_dir.is_absolute():
            audio_dir = Path.cwd() / audio_dir
        if not site_dir.is_absolute():
            site_dir = Path.cwd() / site_dir

        episodes = load_episodes(
            digests_dir,
            audio_dir,
            audio_base_url,
            head=not args.no_head,
            limit=args.limit,
            repo_url=repo_url,
        )
        if not episodes:
            raise ValueError("没有找到可发布的语音节目（检查 digests/ 和音频是否已上传）")

        cover_url = ""
        for name in ("cover.jpg", "cover.png", "cover.jpeg"):
            if (site_dir / name).is_file():
                cover_url = f"{site_url}{name}"
                break

        site_dir.mkdir(parents=True, exist_ok=True)
        index_path = site_dir / "index.html"
        feed_path = site_dir / "feed.xml"
        index_path.write_text(
            render_index(
                episodes,
                feed_url=feed_url,
                title=args.title,
                description=args.description,
            ),
            encoding="utf-8",
        )
        feed_path.write_text(
            build_feed_xml(
                episodes,
                site_url=site_url,
                title=args.title,
                description=args.description,
                cover_url=cover_url,
            )
            + "\n",
            encoding="utf-8",
        )

        print(f"节目数：{len(episodes)}")
        print(f"页面：{_display_path(index_path)}")
        print(f"Feed：{_display_path(feed_path)}")
        print(f"订阅地址：{feed_url}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
