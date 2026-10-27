#!/usr/bin/env python3
"""Render a digest Markdown file as a responsive email and send it.

Examples:
    python scripts/send_email.py --file digests/2026-10-23.md --dry-run
    python scripts/send_email.py --latest --dry-run
    python scripts/send_email.py --file digests/2026-10-23.md

Sending is configured entirely through environment variables:

    MAIL_TO              Recipient(s), comma separated
    MAIL_FROM            Sender, e.g. "Tech Digest <digest@example.com>"
    MAIL_REPLY_TO        Optional Reply-To address

    AUDIO_URL            Optional MP3 URL shown as a listen button
    AUDIO_DURATION       Optional audio length in seconds
    PODCAST_FEED_URL     Optional podcast feed URL

    # Resend (recommended for GitHub Actions)
    RESEND_API_KEY
    EMAIL_PROVIDER=resend

    # Or SMTP
    SMTP_HOST
    SMTP_PORT            Defaults to 465 for SSL, 587 otherwise
    SMTP_USER
    SMTP_PASSWORD
    SMTP_SECURITY        ssl | starttls | none
    EMAIL_PROVIDER=smtp

If EMAIL_PROVIDER is omitted, Resend is used when RESEND_API_KEY is set,
otherwise SMTP is used.

The rendered email is intentionally a single column, with inline styles and
a plain-text alternative. The first Markdown H1 becomes the subject and the
email header; the rest of the digest is rendered in full. Nothing is truncated.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import mistune

ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = ROOT / "digests"
PREVIEW_HTML = "email_preview.html"
PREVIEW_TEXT = "email_preview.txt"

# Resend is the only HTTP API provider for now. SMTP is the fallback.
RESEND_ENDPOINT = "https://api.resend.com/emails"
MAX_SUBJECT_CHARS = 180
WARN_HTML_BYTES = 90_000

_markdown = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "table", "url"],
)

_DANGEROUS_URL_RE = re.compile(
    r"""(?ix)
    \s+(href|src)\s*=\s*(["'])\s*
    (?:javascript|vbscript|data):
    [^"']*
    \2
    """
)


@dataclass(frozen=True)
class RenderedEmail:
    digest_path: Path
    title: str
    date: str
    date_cn: str
    subject: str
    preheader: str
    html: str
    text: str
    audio_url: str = ""
    audio_duration: str = ""
    podcast_url: str = ""


class NonRetryableSendError(RuntimeError):
    """A configuration/permission error that should not be retried."""


def find_latest_digest() -> Path:
    """Return the newest digest file, ignoring templates and hidden files."""
    files = [
        path
        for path in DIGEST_DIR.glob("*.md")
        if path.is_file() and not path.name.startswith("_")
    ]
    if not files:
        raise FileNotFoundError(f"没有找到日报文件：{DIGEST_DIR}/*.md")
    return max(files, key=lambda path: path.name)


def resolve_digest_path(file_arg: str | None) -> Path:
    if not file_arg:
        return find_latest_digest()

    candidate = Path(file_arg).expanduser()
    if not candidate.is_absolute():
        cwd_candidate = Path.cwd() / candidate
        root_candidate = ROOT / candidate
        candidate = cwd_candidate if cwd_candidate.exists() else root_candidate

    candidate = candidate.resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"日报文件不存在：{candidate}")
    if candidate.suffix.lower() != ".md":
        raise ValueError(f"日报文件必须是 .md：{candidate}")
    return candidate


def read_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    if not text:
        raise ValueError(f"日报文件为空：{path}")
    return text


def _plain_inline(text: str) -> str:
    """Turn inline Markdown into a short plain-text string."""
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`~]+", "", text)
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def extract_title(markdown_text: str) -> tuple[str, str]:
    """Return (title, body_without_first_h1)."""
    lines = markdown_text.splitlines()
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^#\s+\S", line):
            title = _plain_inline(re.sub(r"^#\s+", "", line))
            body = "\n".join(lines[:index] + lines[index + 1 :]).strip()
            return title, body
    return "", markdown_text.strip()


def extract_preheader(markdown_text: str) -> str:
    """Use the first blockquote as a short hidden preview line."""
    in_fence = False
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):
            text = _plain_inline(stripped.lstrip(">").strip())
            if text:
                return _truncate(text, 120)
    return "今日科技股市要点"


def digest_date(path: Path, title: str = "") -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name) or re.search(
        r"(\d{4}-\d{2}-\d{2})", title
    )
    return match.group(1) if match else ""


def format_date_cn(date_text: str) -> str:
    try:
        day = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return date_text
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{day.year}年{day.month}月{day.day}日 {weekdays[day.weekday()]}"


def format_duration(seconds: object) -> str:
    """Turn a duration in seconds into a short label such as 约 8 分钟."""
    try:
        value = int(float(str(seconds)))
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    minutes = max(1, (value + 30) // 60)
    return f"约 {minutes} 分钟"


def _audio_cta_html(audio_url: str, duration_label: str, podcast_url: str) -> str:
    """A listen button shown above the digest body."""
    if not audio_url and not podcast_url:
        return ""

    buttons: list[str] = []
    if audio_url:
        label = "🎧 听本期日报"
        if duration_label:
            label += f" · {duration_label}"
        buttons.append(
            f'<a href="{html_lib.escape(audio_url, quote=True)}" '
            'style="display:inline-block;background:#0b6bcb;color:#ffffff;'
            "text-decoration:none;font-size:15px;font-weight:600;"
            'padding:10px 18px;border-radius:999px;">'
            f"{label}</a>"
        )
    if podcast_url:
        buttons.append(
            f'<a href="{html_lib.escape(podcast_url, quote=True)}" '
            'style="display:inline-block;background:#ffffff;color:#0b5cad;'
            "border:1px solid #b9cde4;text-decoration:none;font-size:15px;"
            "font-weight:600;padding:10px 18px;border-radius:999px;"
            'margin-left:8px;">订阅播客</a>'
        )

    return (
        '<div style="margin:0 0 22px;padding:16px 18px;background:#f4f8fd;'
        'border:1px solid #d8e4f2;border-radius:12px;">'
        '<div style="font-size:13px;color:#5b6b7f;margin-bottom:10px;">'
        "通勤路上，直接听这一期</div>"
        f'{"".join(buttons)}</div>'
    )


def _audio_cta_text(audio_url: str, duration_label: str, podcast_url: str) -> str:
    lines: list[str] = []
    if audio_url:
        suffix = f"（{duration_label}）" if duration_label else ""
        lines.append(f"🎧 听本期日报{suffix}：{audio_url}")
    if podcast_url:
        lines.append(f"订阅播客：{podcast_url}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n\n——————————"


def sanitize_html_links(html_text: str) -> str:
    return _DANGEROUS_URL_RE.sub("", html_text)


def markdown_to_html(markdown_text: str) -> str:
    return sanitize_html_links(_markdown(markdown_text))


def markdown_to_text(markdown_text: str) -> str:
    """A readable plain-text alternative that keeps links and list markers."""
    text = markdown_text.replace("\r\n", "\n")
    text = re.sub(r"```[^\n]*\n?", "", text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "————————", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _email_css() -> str:
    return """
    :root { color-scheme: light; }
    body { margin: 0; padding: 0; background: #eef2f6; }
    .email-body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      font-size: 16px;
      line-height: 1.75;
      color: #1f2328;
      overflow-wrap: anywhere;
    }
    .email-body h1 { font-size: 24px; line-height: 1.35; margin: 0 0 16px; color: #111827; }
    .email-body h2 {
      font-size: 19px; line-height: 1.45; margin: 30px 0 12px;
      padding-bottom: 8px; border-bottom: 1px solid #e4e8ec; color: #111827;
    }
    .email-body h3 {
      font-size: 17px; line-height: 1.5; margin: 26px 0 10px;
      padding-left: 10px; border-left: 3px solid #0b6bcb; color: #0b4f91;
    }
    .email-body h4 { font-size: 16px; margin: 20px 0 8px; color: #111827; }
    .email-body p { margin: 0 0 14px; }
    .email-body ul, .email-body ol { margin: 0 0 16px; padding-left: 24px; }
    .email-body li { margin: 0 0 8px; }
    .email-body li > p { margin: 0 0 6px; }
    .email-body blockquote {
      margin: 0 0 18px; padding: 12px 16px; background: #f4f8fd;
      border-left: 4px solid #0b6bcb; border-radius: 0 8px 8px 0; color: #44505f;
    }
    .email-body a { color: #0969da; text-decoration: none; overflow-wrap: anywhere; }
    .email-body strong { color: #111827; }
    .email-body table {
      width: 100%; border-collapse: collapse; margin: 8px 0 18px;
      font-size: 14px; line-height: 1.55;
    }
    .email-body th, .email-body td {
      border: 1px solid #d8dee4; padding: 8px 10px;
      text-align: left; vertical-align: top;
    }
    .email-body th { background: #f6f8fa; color: #111827; }
    .email-body hr { border: 0; border-top: 1px solid #e4e8ec; margin: 24px 0; }
    .email-body code {
      background: #f6f8fa; padding: 2px 5px; border-radius: 4px;
      font-size: 14px;
    }
    .email-body pre {
      background: #f6f8fa; padding: 12px; border-radius: 6px;
      overflow-x: auto; font-size: 14px;
    }
    .email-body img { max-width: 100%; height: auto; }
    @media (max-width: 620px) {
      .email-outer { padding: 12px 8px !important; }
      .email-card { border-radius: 12px !important; }
      .email-header { padding: 24px 20px !important; }
      .email-title { font-size: 22px !important; }
      .email-body { padding: 22px 18px !important; }
      .email-body h2 { font-size: 18px !important; }
      .email-body h3 { font-size: 16px !important; }
      .email-body table { font-size: 13px !important; }
      .email-body th, .email-body td { padding: 6px 7px !important; }
      .email-footer { padding: 18px 20px 24px !important; }
    }
    """


def wrap_email_html(title: str, date_cn: str, preheader: str, body_html: str) -> str:
    safe_title = html_lib.escape(title, quote=True)
    safe_date = html_lib.escape(date_cn, quote=True)
    safe_preheader = html_lib.escape(preheader, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="x-apple-disable-message-reformatting">
<title>{safe_title}</title>
<style>{_email_css()}</style>
</head>
<body style="margin:0;padding:0;background:#eef2f6;">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">
{safe_preheader}
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#eef2f6;">
  <tr>
    <td class="email-outer" align="center" style="padding:28px 12px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             class="email-card"
             style="max-width:640px;background:#ffffff;border:1px solid #e1e7ed;border-radius:16px;overflow:hidden;">
        <tr>
          <td class="email-header"
              style="background-color:#0b5cad;background-image:linear-gradient(135deg,#0b5cad 0%,#0a7ea4 100%);padding:30px 32px;color:#ffffff;">
            <div style="font-size:12px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.82;margin-bottom:8px;">
              Tech Digest · 每日科技股市简报
            </div>
            <div class="email-title" style="font-size:26px;line-height:1.35;font-weight:700;color:#ffffff;">
              {safe_title}
            </div>
            <div style="font-size:14px;line-height:1.5;opacity:0.86;margin-top:10px;">
              {safe_date} · 完整版
            </div>
          </td>
        </tr>
        <tr>
          <td class="email-body" style="padding:28px 32px 10px;">
            {body_html}
          </td>
        </tr>
        <tr>
          <td class="email-footer"
              style="padding:20px 32px 28px;color:#7a8493;font-size:12px;line-height:1.7;border-top:1px solid #eef1f4;">
            由 Grok + GitHub Actions 自动生成并发送。<br>
            内容仅供学习参考，不构成投资建议。
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


def render_digest(
    path: Path,
    subject_override: str = "",
    audio_url: str = "",
    audio_duration: str = "",
    podcast_url: str = "",
) -> RenderedEmail:
    markdown_text = read_markdown(path)
    raw_title, body_markdown = extract_title(markdown_text)
    date_text = digest_date(path, raw_title) or date_cls.today().isoformat()
    title = raw_title or f"科技股市入门日报 {date_text}"

    if not body_markdown.strip():
        body_markdown = "（今日日报暂无正文，请检查 Grok 的输出。）"

    duration_label = format_duration(audio_duration)
    cta_html = _audio_cta_html(audio_url, duration_label, podcast_url)
    body_html = markdown_to_html(body_markdown)
    if cta_html:
        body_html = cta_html + body_html

    date_cn = format_date_cn(date_text)
    preheader = extract_preheader(markdown_text)
    subject = _truncate(subject_override or title, MAX_SUBJECT_CHARS)
    html_doc = wrap_email_html(title, date_cn, preheader, body_html)

    text_body = markdown_to_text(markdown_text)
    cta_text = _audio_cta_text(audio_url, duration_label, podcast_url)
    if cta_text:
        text_body = cta_text + "\n\n" + text_body

    return RenderedEmail(
        digest_path=path,
        title=title,
        date=date_text,
        date_cn=date_cn,
        subject=subject,
        preheader=preheader,
        html=html_doc,
        text=text_body,
        audio_url=audio_url,
        audio_duration=duration_label,
        podcast_url=podcast_url,
    )


def _split_addresses(value: str) -> list[str]:
    addresses = [part.strip() for part in re.split(r"[,;]", value or "") if part.strip()]
    if not addresses:
        raise ValueError("MAIL_TO 为空")
    for address in addresses:
        if "@" not in address:
            raise ValueError(f"邮箱地址格式不正确：{address}")
    return addresses


def _extract_email_address(value: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+", value or "")
    return match.group(0) if match else value


def build_message(
    rendered: RenderedEmail,
    from_addr: str,
    to_addrs: list[str],
    reply_to: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = rendered.subject
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    if reply_to:
        message["Reply-To"] = reply_to
    message["Date"] = formatdate(localtime=True)
    domain = _extract_email_address(from_addr).split("@")[-1] or "localhost"
    message["Message-ID"] = make_msgid(domain=domain)
    message.set_content(rendered.text)
    message.add_alternative(rendered.html, subtype="html")
    return message


def _retry(operation, attempts: int = 3, base_delay: float = 2.0):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except NonRetryableSendError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry boundary
            last_error = exc
            if attempt >= attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            print(
                f"发送失败（第 {attempt}/{attempts} 次）：{exc}；{delay:g}s 后重试",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(f"发送失败（已重试 {attempts} 次）：{last_error}") from last_error


def _send_via_smtp(
    rendered: RenderedEmail,
    from_addr: str,
    to_addrs: list[str],
    reply_to: str,
) -> str:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    port_raw = os.getenv("SMTP_PORT", "").strip()

    missing = [name for name, value in (("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASSWORD", password)) if not value]
    if missing:
        raise ValueError("缺少 SMTP 配置：" + ", ".join(missing))

    if not security:
        security = "ssl" if (not port_raw or port_raw == "465") else "starttls"
    if security not in {"ssl", "starttls", "none"}:
        raise ValueError("SMTP_SECURITY 只能是 ssl、starttls 或 none")

    port = int(port_raw) if port_raw else (465 if security == "ssl" else 587)
    message = build_message(rendered, from_addr, to_addrs, reply_to)

    def attempt() -> str:
        context = ssl.create_default_context()
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if security == "starttls":
                server.starttls(context=context)
                server.ehlo()

        try:
            try:
                server.login(user, password)
            except smtplib.SMTPAuthenticationError as exc:
                raise NonRetryableSendError(
                    "SMTP 登录失败，请确认 SMTP_USER 和 SMTP_PASSWORD（QQ/Foxmail 使用的是授权码，不是登录密码）"
                ) from exc
            try:
                server.send_message(message)
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
                raise NonRetryableSendError(f"SMTP 拒绝收件人或发件人：{exc}") from exc
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        return "smtp"

    return _retry(attempt)


def _send_via_resend(
    rendered: RenderedEmail,
    from_addr: str,
    to_addrs: list[str],
    reply_to: str,
) -> str:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise ValueError("缺少 RESEND_API_KEY")

    payload: dict[str, object] = {
        "from": from_addr,
        "to": to_addrs,
        "subject": rendered.subject,
        "html": rendered.html,
        "text": rendered.text,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    def attempt() -> str:
        request = urllib.request.Request(
            RESEND_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "tech-digest/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            message = f"Resend HTTP {exc.code}：{detail}"
            if exc.code == 429 or exc.code >= 500:
                raise RuntimeError(message) from exc
            raise NonRetryableSendError(message) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Resend 网络错误：{exc.reason}") from exc

        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return str(data.get("id") or "resend")

    return _retry(attempt)


def send_email(rendered: RenderedEmail, to_value: str, from_addr: str, reply_to: str) -> str:
    to_addrs = _split_addresses(to_value)
    if not from_addr.strip():
        raise ValueError("缺少 MAIL_FROM")

    provider = os.getenv("EMAIL_PROVIDER", "").strip().lower()
    if not provider:
        provider = "resend" if os.getenv("RESEND_API_KEY", "").strip() else "smtp"
    if provider not in {"resend", "smtp"}:
        raise ValueError("EMAIL_PROVIDER 只能是 resend 或 smtp")

    if provider == "resend":
        return _send_via_resend(rendered, from_addr, to_addrs, reply_to)
    return _send_via_smtp(rendered, from_addr, to_addrs, reply_to)


def write_preview(rendered: RenderedEmail, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / PREVIEW_HTML
    text_path = out_dir / PREVIEW_TEXT
    html_path.write_text(rendered.html, encoding="utf-8")
    text_path.write_text(rendered.text + "\n", encoding="utf-8")
    return html_path, text_path


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 digests/*.md 渲染成完整邮件并发送（或只生成预览）。"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", "-f", help="日报文件路径；不传则使用最新一份")
    group.add_argument("--latest", action="store_true", help="使用最新一份日报（默认行为）")
    parser.add_argument("--dry-run", action="store_true", help="只生成预览，不发送")
    parser.add_argument(
        "--out-dir",
        default="",
        help=f"预览输出目录（默认仓库根目录，写入 {PREVIEW_HTML} / {PREVIEW_TEXT}）",
    )
    parser.add_argument("--to", help="覆盖 MAIL_TO（仅建议本地测试使用）")
    parser.add_argument("--from", dest="from_addr", help="覆盖 MAIL_FROM（仅建议本地测试使用）")
    parser.add_argument("--subject", help="覆盖邮件主题（默认取日报第一个 H1）")
    parser.add_argument(
        "--audio-url",
        help="本期语音链接，邮件顶部会显示播放按钮（默认读取 AUDIO_URL）",
    )
    parser.add_argument(
        "--audio-duration",
        help="本期音频秒数，用于显示『约 N 分钟』（默认读取 AUDIO_DURATION）",
    )
    parser.add_argument(
        "--podcast-url",
        help="播客订阅地址（默认读取 PODCAST_FEED_URL）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        digest_path = resolve_digest_path(args.file)
        audio_url = (args.audio_url or os.getenv("AUDIO_URL", "")).strip()
        audio_duration = (args.audio_duration or os.getenv("AUDIO_DURATION", "")).strip()
        podcast_url = (args.podcast_url or os.getenv("PODCAST_FEED_URL", "")).strip()
        rendered = render_digest(
            digest_path,
            args.subject or "",
            audio_url=audio_url,
            audio_duration=audio_duration,
            podcast_url=podcast_url,
        )

        html_bytes = len(rendered.html.encode("utf-8"))
        if html_bytes > WARN_HTML_BYTES:
            print(
                f"警告：HTML 邮件约 {html_bytes / 1024:.1f} KB，超过 "
                f"{WARN_HTML_BYTES / 1000:.0f} KB，Gmail 可能折叠正文；内容仍然完整发送。",
                file=sys.stderr,
            )

        print(f"日报文件：{_display_path(digest_path)}")
        print(f"邮件主题：{rendered.subject}")
        print(f"HTML 大小：{html_bytes / 1024:.1f} KB")
        if rendered.audio_url:
            print(f"语音链接：{rendered.audio_url}")

        if args.dry_run:
            out_dir = Path(args.out_dir).expanduser() if args.out_dir else ROOT
            if not out_dir.is_absolute():
                out_dir = Path.cwd() / out_dir
            html_path, text_path = write_preview(rendered, out_dir)
            print(f"HTML 预览：{html_path}")
            print(f"纯文本预览：{text_path}")
            print("dry-run：未发送邮件。")
            return 0

        to_value = args.to or os.getenv("MAIL_TO", "")
        from_addr = args.from_addr or os.getenv("MAIL_FROM", "")
        reply_to = os.getenv("MAIL_REPLY_TO", "").strip()
        message_id = send_email(rendered, to_value, from_addr, reply_to)
        provider = os.getenv("EMAIL_PROVIDER", "").strip().lower() or (
            "resend" if os.getenv("RESEND_API_KEY", "").strip() else "smtp"
        )
        print(f"发送成功：provider={provider} id={message_id}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
