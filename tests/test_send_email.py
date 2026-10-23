import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_email  # noqa: E402

DIGEST = ROOT / "digests" / "2026-10-23.md"


class RenderingTests(unittest.TestCase):
    def test_extract_title_removes_first_h1(self):
        title, body = send_email.extract_title(
            "# 科技股市入门日报 2026-10-23\n\n## 今日要闻\n\n正文"
        )
        self.assertEqual(title, "科技股市入门日报 2026-10-23")
        self.assertTrue(body.startswith("## 今日要闻"))
        self.assertNotIn("# 科技股市入门日报", body)

    def test_extract_title_when_missing(self):
        title, body = send_email.extract_title("## 今日要闻\n\n正文")
        self.assertEqual(title, "")
        self.assertEqual(body, "## 今日要闻\n\n正文")

    def test_markdown_escapes_raw_html_and_dangerous_links(self):
        rendered = send_email.markdown_to_html(
            "<script>alert(1)</script>\n\n"
            "[click](javascript:alert(1))\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |"
        )
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("<table>", rendered)

    def test_render_digest_keeps_all_sections_and_links(self):
        rendered = send_email.render_digest(DIGEST)

        self.assertEqual(rendered.subject, "科技股市入门日报 2026-10-23")
        self.assertEqual(rendered.date, "2026-10-23")
        for heading in (
            "一、今日重要新闻",
            "二、新闻解读（小白版）",
            "三、关键数据速览",
            "四、今日入门小课堂",
            "五、给初学者的小建议",
        ):
            self.assertIn(heading, rendered.html)
            self.assertIn(heading, rendered.text)

        self.assertIn("https://www.reuters.com", rendered.html)
        self.assertIn("以上内容仅供学习参考，不构成投资建议", rendered.html)
        self.assertIn("以上内容仅供学习参考，不构成投资建议", rendered.text)
        # H1 is used as the header, so it should not be rendered a second time.
        self.assertNotIn("<h1>科技股市入门日报", rendered.html)

    def test_html_is_responsive_and_has_plain_text_alternative(self):
        rendered = send_email.render_digest(DIGEST)
        self.assertIn('name="viewport"', rendered.html)
        self.assertIn("@media (max-width: 620px)", rendered.html)
        self.assertIn("max-width:640px", rendered.html)

        message = send_email.build_message(
            rendered,
            "Tech Digest <digest@example.com>",
            ["reader@example.com"],
            "reply@example.com",
        )
        self.assertEqual(message["Subject"], rendered.subject)
        self.assertEqual(message["Reply-To"], "reply@example.com")
        self.assertEqual(message.get_content_type(), "multipart/alternative")

        plain_part = message.get_body(preferencelist=("plain",))
        html_part = message.get_body(preferencelist=("html",))
        self.assertIsNotNone(plain_part)
        self.assertIsNotNone(html_part)
        self.assertIn("今日重要新闻", plain_part.get_content())
        self.assertIn("Tech Digest", html_part.get_content())
        self.assertIn("Tech Digest · 每日科技股市简报", html_part.get_content())

    def test_plain_text_keeps_links_readable(self):
        rendered = send_email.render_digest(DIGEST)
        self.assertIn("Reuters (https://www.reuters.com", rendered.text)
        self.assertNotIn("**", rendered.text)
        self.assertNotIn("###", rendered.text)

    def test_latest_digest_ignores_template(self):
        original_dir = send_email.DIGEST_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "2026-10-22.md").write_text("# old\n", encoding="utf-8")
                (directory / "2026-10-23.md").write_text("# new\n", encoding="utf-8")
                (directory / "_TEMPLATE.md").write_text("# template\n", encoding="utf-8")
                send_email.DIGEST_DIR = directory
                self.assertEqual(send_email.find_latest_digest().name, "2026-10-23.md")
        finally:
            send_email.DIGEST_DIR = original_dir

    def test_preview_files_are_written(self):
        rendered = send_email.render_digest(DIGEST)
        with tempfile.TemporaryDirectory() as tmp:
            html_path, text_path = send_email.write_preview(rendered, Path(tmp))
            self.assertTrue(html_path.is_file())
            self.assertTrue(text_path.is_file())
            self.assertIn("今日重要新闻", html_path.read_text(encoding="utf-8"))
            self.assertIn("今日重要新闻", text_path.read_text(encoding="utf-8"))

    def test_resolve_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            send_email.resolve_digest_path("digests/not-found.md")


class SendingTests(unittest.TestCase):
    def setUp(self):
        self.rendered = send_email.render_digest(DIGEST)

    def test_smtp_send(self):
        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "digest@example.com",
            "SMTP_PASSWORD": "auth-code",
            "SMTP_SECURITY": "ssl",
        }
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "send_email.smtplib.SMTP_SSL"
        ) as smtp_ssl:
            server = smtp_ssl.return_value
            result = send_email._send_via_smtp(
                self.rendered,
                "Tech Digest <digest@example.com>",
                ["reader@example.com"],
                "",
            )

        self.assertEqual(result, "smtp")
        smtp_ssl.assert_called_once()
        server.login.assert_called_once_with("digest@example.com", "auth-code")
        server.send_message.assert_called_once()
        server.quit.assert_called_once()

    def test_resend_send(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"id":"email_123"}'

        with mock.patch.dict(os.environ, {"RESEND_API_KEY": "re_test"}, clear=False):
            with mock.patch(
                "send_email.urllib.request.urlopen", return_value=FakeResponse()
            ) as urlopen:
                result = send_email._send_via_resend(
                    self.rendered,
                    "Tech Digest <digest@example.com>",
                    ["reader@example.com"],
                    "reply@example.com",
                )

        self.assertEqual(result, "email_123")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["subject"], self.rendered.subject)
        self.assertEqual(payload["to"], ["reader@example.com"])
        self.assertEqual(payload["reply_to"], "reply@example.com")
        self.assertIn("今日重要新闻", payload["html"])
        self.assertIn("今日重要新闻", payload["text"])

    def test_provider_inference_prefers_resend(self):
        env = {"RESEND_API_KEY": "re_test"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("EMAIL_PROVIDER", None)
            with mock.patch(
                "send_email._send_via_resend", return_value="resend-id"
            ) as resend:
                result = send_email.send_email(
                    self.rendered, "reader@example.com", "digest@example.com", ""
                )
        self.assertEqual(result, "resend-id")
        resend.assert_called_once()


if __name__ == "__main__":
    unittest.main()
