# tech-digest

每天自动生成并发送**科技股市入门日报**。

Grok Automation 搜索过去 24 小时 X 上的科技巨头、半导体和 AI 产业链动态，写成中文 Markdown 日报并提交到本仓库；GitHub Actions 在收到新日报后，把完整内容渲染成响应式 HTML 邮件（同时生成纯文本版本）发送到邮箱。

每份日报还会用 edge-tts 合成中文语音，上传到 Cloudflare R2，并在 GitHub Pages 上生成播放页和播客 feed——通勤路上可以直接听。

[![Send digest email](https://github.com/HappyyyyTingting/tech-digest/actions/workflows/send-email.yml/badge.svg)](https://github.com/HappyyyyTingting/tech-digest/actions/workflows/send-email.yml)

> 日报内容仅供学习参考，不构成投资建议。

## 特性

- **每日自动更新**：Grok 按计划生成日报，Git 保存历史版本。
- **语音版日报**：edge-tts 合成 MP3（约 8 分钟），邮件顶部一键收听；同一份音频自动发布为播客 feed，可在小宇宙、Apple Podcasts、Overcast 等客户端订阅。
- **完整邮件正文**：不截断，不含「Continue Reading」。
- **手机友好**：单栏布局，最大宽度 640px，16px 字号，1.75 行高。
- **SMTP / Resend 双支持**：凭据保存在 GitHub Actions Secrets，不写进仓库。
- **可手动补发**：支持 `workflow_dispatch`，可指定日报文件或只生成预览。
- **安全渲染**：Markdown 原始 HTML 转义，危险链接拦截，附带纯文本 alternative。
- **测试覆盖**：渲染、口语稿清洗、播客 feed、SMTP / Resend 发送逻辑。

## 工作流

```text
Grok Automation（每天）
  → digests/YYYY-MM-DD.md
  → GitHub Actions（push 触发）
  → scripts/make_audio.py   Markdown → 口语稿 → MP3 → Cloudflare R2
  → scripts/build_site.py   播放页 + 播客 feed → GitHub Pages
  → scripts/send_email.py   响应式 HTML + 纯文本（含语音链接）
  → 邮箱
```

- push 到 `main` 且改动 `digests/*.md` 时自动发送。
- `digests/_TEMPLATE.md` 不会被发送。
- 也可以在 Actions 页面手动触发；`dry_run` 只生成预览 artifact。
- 语音和 Pages 部署都是可选的：任一步失败不会阻止邮件发送。

## 快速开始

### 本地预览

```bash
git clone https://github.com/HappyyyyTingting/tech-digest.git
cd tech-digest
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/send_email.py --latest --dry-run
open email_preview.html

# 语音版：先看口语稿，再合成 MP3（需要联网）
.venv/bin/python scripts/make_audio.py --latest --dry-run --text-out /tmp/spoken.txt
.venv/bin/python scripts/make_audio.py --latest

# 生成播放页和播客 feed（本地用示例地址预览）
.venv/bin/python scripts/build_site.py \
  --audio-base-url https://audio.example.com \
  --site-url https://example.github.io/tech-digest/ \
  --site-dir /tmp/tech-digest-site \
  --no-head
open /tmp/tech-digest-site/index.html
```

### 本地发送

以 SMTP 为例：

```bash
export MAIL_TO='you@example.com'
export MAIL_FROM='科技股市日报 <digest@example.com>'
export EMAIL_PROVIDER='smtp'
export SMTP_HOST='smtp.example.com'
export SMTP_PORT='465'
export SMTP_SECURITY='ssl'
export SMTP_USER='digest@example.com'

printf 'SMTP 授权码: '
read -rs SMTP_PASSWORD
echo
export SMTP_PASSWORD

# 发送最新一份
.venv/bin/python scripts/send_email.py --latest

# 或发送指定文件
.venv/bin/python scripts/send_email.py --file digests/2026-10-23.md

unset SMTP_PASSWORD
```

本地发送同样支持 Resend：设置 `EMAIL_PROVIDER=resend` 和 `RESEND_API_KEY`，不需要 `SMTP_*` 变量。

## 配置

在仓库 `Settings → Secrets and variables → Actions` 添加 **Repository secrets**。

### SMTP（当前使用）

| Secret | 说明 |
|---|---|
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | `465`（SSL）或 `587`（STARTTLS） |
| `SMTP_SECURITY` | `ssl` / `starttls` / `none` |
| `SMTP_USER` | 完整邮箱地址 |
| `SMTP_PASSWORD` | SMTP 授权码或应用专用密码 |
| `MAIL_FROM` | 发件地址；支持 `显示名 <邮箱>` 格式 |
| `MAIL_TO` | 收件地址，多个用英文逗号分隔 |
| `MAIL_REPLY_TO` | 可选 |

### Resend（备选）

| Secret | 说明 |
|---|---|
| `EMAIL_PROVIDER` | `resend` |
| `RESEND_API_KEY` | Resend API key |
| `MAIL_FROM` | `onboarding@resend.dev` 或已验证域名下的地址 |
| `MAIL_TO` | 收件地址，多个用英文逗号分隔 |

### 语音版与 GitHub Pages（可选）

音频存放在 **Cloudflare R2**（10GB 免费额度，按每天约 3MB 可用十年以上），播放页和播客 feed 由 **GitHub Pages** 托管。

Secrets：

| Secret | 说明 |
|---|---|
| `R2_ACCOUNT_ID` | Cloudflare 账户 ID |
| `R2_BUCKET` | 存放 MP3 的 bucket 名称 |
| `R2_ACCESS_KEY_ID` | R2 API token 的 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | R2 API token 的 Secret Access Key |
| `AUDIO_BASE_URL` | bucket 的公开访问前缀，例如 `https://audio.example.com`（必填，只填域名、不要带路径） |

`AUDIO_BASE_URL` 本来就是公开地址（会出现在邮件按钮、播放页和 feed 里），放进 Secret 只是为了让 Actions 日志自动打码。

Variables（`Settings → Secrets and variables → Actions → Variables`）：

| Variable | 说明 |
|---|---|
| `SITE_URL` | 自定义站点地址；默认按 `https://<owner>.github.io/<repo>/` 推导 |
| `PODCAST_FEED_URL` | 邮件里的订阅链接；默认由 `SITE_URL` 推导 |
| `TTS_VOICE` | 音色，默认 `zh-CN-XiaoxiaoNeural` |
| `TTS_RATE` | 语速，默认 `+0%` |

另外需要在 `Settings → Pages` 把 **Source** 设为 **GitHub Actions**。完整步骤（R2 公共访问、API token、播客订阅）见 [docs/setup.md](docs/setup.md)。

### 发件人显示名称

邮件里显示的发送人名称由 `MAIL_FROM` 控制：

```text
科技股市日报 <digest@example.com>
```

尖括号里的地址必须是 SMTP 服务允许的发件地址（通常与 `SMTP_USER` 一致），或 Resend 已验证域名下的地址。修改 secret 后重新运行 workflow 即可，不需要改代码。

### Secret 安全

- Secret 值不会出现在仓库里，也不能通过 GitHub 网页/API 读回明文。
- 未登录访客看不到 Actions 日志；登录用户能看日志，但 GitHub 会自动打码 secret 值。
- 当前脚本只打印日报路径、主题、HTML 大小和 provider，不打印邮箱、授权码或 API key。
- 有 write 权限的协作者可以修改 workflow 读取 secret，所以只给信任的人写权限。
- 建议使用专用发件邮箱和可撤销的授权码/API key。

## 邮件格式

- 主题取日报第一个 `#` 标题。
- 正文完整渲染，保留标题、列表、表格、引用和来源链接。
- 同时生成 `text/plain` 版本。
- HTML 超过约 90KB 时日志会警告，但不会截断。
- Markdown 原始 HTML 会被转义，`javascript:` / `data:` 等危险链接会被拦截。

## 项目结构

```text
.github/workflows/send-email.yml   # push / workflow_dispatch 触发；音频、Pages、邮件
digests/                            # 每日日报与格式模板
scripts/make_audio.py               # Markdown → 口语稿 → MP3 → R2
scripts/build_site.py               # 播放页 index.html + 播客 feed.xml
scripts/send_email.py               # 渲染与发送（含语音链接）
tests/                              # 单元测试
requirements.txt                    # mistune、edge-tts、boto3、mutagen
docs/setup.md                       # Grok、SMTP、Resend、R2、Pages 详细配置与排查
```

## 开发

```bash
# 运行全部测试
.venv/bin/python -m unittest discover -s tests -v

# 只生成预览，不发送
.venv/bin/python scripts/send_email.py --file digests/2026-10-23.md --dry-run
```

脚本参数：

- `--file <path>`：指定日报文件。
- `--latest`：使用最新一份日报（默认行为）。
- `--dry-run`：只写 `email_preview.html` / `email_preview.txt`，不发送。
- `--to` / `--from` / `--subject`：本地测试时覆盖环境变量。
- `--audio-url` / `--audio-duration` / `--podcast-url`：邮件顶部的语音链接、秒数和订阅地址；也可用 `AUDIO_URL` / `AUDIO_DURATION` / `PODCAST_FEED_URL` 环境变量。

`make_audio.py`：

- `--voice` / `--rate`：音色和语速（默认 `zh-CN-XiaoxiaoNeural` / `+0%`）。
- `--dry-run`：只输出字数和预计时长，不合成。
- `--text-out <path>`：把清洗后的口语稿写出来，便于检查。
- `--upload`：生成后上传到 R2（需要 `R2_*` 和 `AUDIO_BASE_URL`）。

`build_site.py`：

- `--audio-base-url`：MP3 的公开前缀（也读 `AUDIO_BASE_URL`）。
- `--site-url` / `--repo-url`：站点和仓库地址，默认按 GitHub 仓库推导。
- `--no-head`：不检查远程音频是否存在，离线预览用。
- `--limit`：只保留最近 N 期。

## 文档

详细的 Grok Automation、邮件服务和排错说明见 [docs/setup.md](docs/setup.md)。
