import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_audio  # noqa: E402

DIGEST = ROOT / "digests" / "2026-10-27.md"


class SpeechTextTests(unittest.TestCase):
    def test_links_urls_and_markdown_are_removed(self):
        text = make_audio.markdown_to_speech(
            "# 标题\n\n"
            "- **要点**：内容 [来源](https://example.com/a)，见 https://example.com/b。\n"
        )
        self.assertIn("要点", text)
        self.assertIn("来源", text)
        self.assertNotIn("http", text)
        self.assertNotIn("**", text)
        self.assertNotIn("](", text)
        self.assertNotIn("#", text)

    def test_table_rows_become_sentences(self):
        text = make_audio.markdown_to_speech(
            "| 公司 | 数值 |\n|---|---|\n| 英伟达 | +3% |\n"
        )
        self.assertIn("公司，数值。", text)
        self.assertIn("英伟达，+3%。", text)
        self.assertNotIn("|", text)
        self.assertNotIn("---", text)

    def test_headings_lists_and_dates_are_speakable(self):
        text = make_audio.markdown_to_speech(
            "### 一、今日新闻\n\n2026-10-27\n\n1. 第一条\n2. 第二条\n"
        )
        self.assertIn("一、今日新闻。", text)
        self.assertIn("2026年10月27日。", text)
        self.assertIn("1、第一条。", text)

    def test_handles_and_emoji_are_removed(self):
        text = make_audio.markdown_to_speech("消息来自 @DeItaone 🚀（如@someone）")
        self.assertNotIn("@", text)
        self.assertNotIn("🚀", text)
        self.assertNotIn("（如）", text)

    def test_lead_in_keeps_its_colon(self):
        self.assertEqual(make_audio._sentence("覆盖方向："), "覆盖方向：")
        self.assertEqual(make_audio._sentence("普通句子"), "普通句子。")

    def test_compose_speech_normalizes_title_date(self):
        text = make_audio.compose_speech(
            "科技股市入门日报 2026-10-27", "### 一、新闻\n\n正文"
        )
        self.assertTrue(text.startswith("科技股市入门日报 2026年10月27日。"))
        self.assertIn("一、新闻。", text)

    def test_real_digest_is_clean(self):
        markdown_text = make_audio.read_markdown(DIGEST)
        title, body = make_audio.extract_title(markdown_text)
        text = make_audio.markdown_to_speech(body)

        self.assertGreater(len(text), 800)
        self.assertIn("今日重要新闻", text)
        self.assertNotIn("http", text)
        self.assertNotIn("|", text)
        self.assertNotIn("#", text)
        self.assertNotIn("**", text)


if __name__ == "__main__":
    unittest.main()
