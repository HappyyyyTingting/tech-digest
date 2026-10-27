import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


def write_digest(directory: Path, date_text: str, title: str = "测试日报", summary: str = "摘要") -> None:
    (directory / f"{date_text}.md").write_text(
        f"# {title} {date_text}\n\n> {summary}\n\n### 一、新闻\n\n正文。\n",
        encoding="utf-8",
    )


class BuildSiteTests(unittest.TestCase):
    def test_load_episodes_prefers_metadata_and_sorts_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digests = root / "digests"
            audio = root / "audio"
            digests.mkdir()
            audio.mkdir()
            write_digest(digests, "2026-10-26")
            write_digest(digests, "2026-10-27", summary="今日摘要")
            (audio / "2026-10-27.json").write_text(
                json.dumps(
                    {
                        "bytes": 12345,
                        "duration": 495.4,
                        "url": "https://audio.example.com/2026-10-27.mp3",
                    }
                ),
                encoding="utf-8",
            )

            episodes = build_site.load_episodes(
                digests,
                audio,
                "https://audio.example.com",
                head=False,
                repo_url="https://github.com/example/repo",
            )

            self.assertEqual([episode.date for episode in episodes], ["2026-10-27", "2026-10-26"])
            self.assertEqual(episodes[0].bytes, 12345)
            self.assertEqual(episodes[0].duration, 495)
            self.assertEqual(episodes[0].summary, "今日摘要")
            self.assertEqual(
                episodes[0].source_url,
                "https://github.com/example/repo/blob/main/digests/2026-10-27.md",
            )
            self.assertEqual(
                episodes[1].audio_url, "https://audio.example.com/2026-10-26.mp3"
            )

    def test_head_check_excludes_episodes_without_a_remote_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digests = root / "digests"
            audio = root / "audio"
            digests.mkdir()
            audio.mkdir()
            write_digest(digests, "2026-10-26")
            write_digest(digests, "2026-10-27")
            (audio / "2026-10-26.json").write_text(
                json.dumps(
                    {
                        "bytes": 100,
                        "duration": 60,
                        "url": "https://audio.example.com/2026-10-26.mp3",
                    }
                ),
                encoding="utf-8",
            )
            # A local MP3 alone must not publish a dead remote link.
            (audio / "2026-10-27.mp3").write_bytes(b"x" * 100)

            with mock.patch("build_site.head_size", return_value=None) as head:
                episodes = build_site.load_episodes(
                    digests, audio, "https://audio.example.com", head=True
                )

            self.assertEqual([episode.date for episode in episodes], ["2026-10-26"])
            self.assertEqual(head.call_count, 1)

    def test_limit_keeps_latest_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digests = root / "digests"
            audio = root / "audio"
            digests.mkdir()
            audio.mkdir()
            for day in ("2026-10-25", "2026-10-26", "2026-10-27"):
                write_digest(digests, day)

            episodes = build_site.load_episodes(
                digests, audio, "https://audio.example.com", head=False, limit=2
            )

            self.assertEqual([episode.date for episode in episodes], ["2026-10-27", "2026-10-26"])

    def test_feed_contains_enclosures_and_itunes_metadata(self):
        episodes = [
            build_site.Episode(
                date="2026-10-27",
                title="测试日报 2026-10-27",
                summary="摘要 & 说明",
                audio_url="https://audio.example.com/2026-10-27.mp3",
                source_url="https://github.com/example/repo/blob/main/digests/2026-10-27.md",
                bytes=12345,
                duration=495,
            )
        ]

        xml = build_site.build_feed_xml(
            episodes,
            site_url="https://example.github.io/tech-digest/",
            title="科技股市入门日报",
            description="每天一份",
            cover_url="https://example.github.io/tech-digest/cover.jpg",
        )
        root = ET.fromstring(xml)
        channel = root.find("channel")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.findtext("title"), "科技股市入门日报")
        self.assertEqual(
            channel.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}image").get("href"),
            "https://example.github.io/tech-digest/cover.jpg",
        )

        items = channel.findall("item")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.findtext("title"), "测试日报 2026-10-27")
        self.assertEqual(item.findtext("description"), "摘要 & 说明")
        enclosure = item.find("enclosure")
        self.assertEqual(enclosure.get("url"), "https://audio.example.com/2026-10-27.mp3")
        self.assertEqual(enclosure.get("length"), "12345")
        self.assertEqual(enclosure.get("type"), "audio/mpeg")
        self.assertEqual(
            item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration"), "495"
        )

    def test_index_has_players_and_escapes_text(self):
        episodes = [
            build_site.Episode(
                date="2026-10-27",
                title='<script>alert("x")</script>',
                summary="摘要 & 说明",
                audio_url="https://audio.example.com/2026-10-27.mp3",
                source_url="",
                bytes=1,
                duration=495,
            )
        ]

        page = build_site.render_index(
            episodes,
            feed_url="https://example.github.io/tech-digest/feed.xml",
            title="科技股市入门日报",
            description="每天一份",
        )

        self.assertIn('<audio controls preload="none"', page)
        self.assertIn("https://audio.example.com/2026-10-27.mp3", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)
        self.assertIn("约 8 分钟", page)

    def test_empty_index_shows_placeholder(self):
        page = build_site.render_index(
            [],
            feed_url="https://example.github.io/tech-digest/feed.xml",
            title="科技股市入门日报",
            description="每天一份",
        )
        self.assertIn("还没有生成语音", page)
        self.assertNotIn("<audio", page)


if __name__ == "__main__":
    unittest.main()
