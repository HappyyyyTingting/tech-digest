# 配置指南

本仓库由三段组成：

1. **Grok Automation** 每天搜索 X 上的科技动态，把中文日报写入 `digests/YYYY-MM-DD.md`。
2. **GitHub Actions** 在日报更新后，把 Markdown 完整渲染成 HTML 邮件和纯文本邮件并发送。
3. **GitHub Actions（可选）** 同一份日报合成中文语音，上传到 Cloudflare R2，并发布到 GitHub Pages 的播放页和播客 feed。

本文档说明首次配置、邮件服务切换、语音版配置和排错。日常使用和本地命令见 [README](../README.md)。

## 整体流程

```text
Grok Automation（每天）
  → digests/YYYY-MM-DD.md
  → GitHub Actions（push 触发，或手动触发）
  → scripts/make_audio.py  → MP3 → Cloudflare R2
  → scripts/build_site.py  → 播放页 + feed.xml → GitHub Pages
  → scripts/send_email.py  → 响应式 HTML + 纯文本（含语音链接）
  → 邮箱
```

- 只有 `main` 分支上 `digests/*.md` 的改动会触发自动发送。
- `digests/_TEMPLATE.md` 是格式模板，不会被当成日报发送。
- 手动触发时可以指定日报文件，也可以只生成预览、不发送。

## 1. Grok Automation

### 1.1 连接 GitHub connector

1. 打开 <https://grok.com/connectors>。
2. 找到 **GitHub**，点击连接。
3. 在 GitHub 授权页选择 **Only select repositories**。
4. 只勾选 `HappyyyyTingting/tech-digest`。
5. 授予 **write** 权限，Grok 需要向仓库提交文件。

授权范围越小越好，不要选择 “All repositories”。如果以后换仓库，重新授权即可。

### 1.2 创建 Automation

打开 <https://grok.com/automations>，新建一个 automation：

- **Schedule**：每天一次。建议设在早上 07:30（Asia/Shanghai），给后续邮件任务留出时间。
- **Delivery**：app notification 或 none 都可以。邮件由 GitHub Actions 发送，不依赖 Grok 的邮件功能。
- **Prompt**：使用下面的完整提示词。

### 1.3 Prompt

```text
你是一个面向股市新手的科技情报编辑。请生成一份「科技股市入门日报」，
用中文 Markdown 输出，语言通俗易懂。

## 数据来源与写入方式

1. 搜索过去 24 小时 X 上关于科技巨头和半导体/AI 产业链的重要动态。
   优先使用高互动、可信的 X 帖子，其次使用可靠媒体、公司公告或财报。
2. 使用 GitHub connector，把完整日报写入仓库 HappyyyyTingting/tech-digest 的
   digests/<当天日期，格式 YYYY-MM-DD>.md，直接 commit 到 main 分支。
3. 写入前先尝试读取仓库 digests/ 目录下最近几天的文件，确认「今日入门小课堂」
   昨天讲过什么，今天讲下一个概念，避免重复。如果读不到历史文件，就按常见
   入门顺序选一个，并在小课堂开头注明。
4. 不要修改仓库里的其他文件；不要创建 PR；如果当天文件已存在，覆盖它。
5. commit message 使用 "digest: YYYY-MM-DD"。
6. 写入成功后只回复一句「已写入 digests/YYYY-MM-DD.md」，不要把全文再贴一遍。
   如果写入失败，说明失败原因，不要假装成功。

## 日报结构

# 科技股市入门日报 YYYY-MM-DD

> 一句话总结今天科技股和产业链最重要的变化。

### 一、今日重要新闻

列出过去 24 小时内最重要的 4–7 条新闻，覆盖科技巨头和关键细分行业。

覆盖方向：
- 科技巨头：Apple、Microsoft、Google、NVIDIA、Meta、Amazon、Tesla 等
- 关键细分行业：芯片/半导体、存储（DRAM/NAND）、AI 大模型、先进封装、
  半导体设备、AI 算力相关等

每条包含：
- 简要标题
- 核心内容总结（2–3 句，把关键信息写清楚，不要只给链接）
- 来源（优先 X 上的高互动帖子或可靠信息，附链接）

### 二、新闻解读（小白版）

用最简单的语言解释这些新闻可能对相关公司和行业意味着什么：
- 这件事偏利好还是偏利空？为什么？
- 对短期和中期可能有什么影响？
- 普通人需要注意什么信号？

要求：
- 用「可能」「偏利好/偏利空」这样的表述，不要给出确定性预测
- 解释清楚逻辑，避免专业术语堆砌

### 三、关键数据速览

简要列出主要公司和行业相关的核心数据：
- 股价变动、市值、近期涨跌幅
- 行业景气指标（如存储价格、AI 算力需求、半导体设备出货等）

要求：
- 优先使用过去 24 小时内可核实的数据，注明数据时间和来源
- 如果拿不到可靠数据，就写「数据暂缺」，不要编造
- 用通俗的方式说明这些数字代表什么

### 四、今日入门小课堂

每天只讲 1 个基础知识点，从入门开始，循序渐进。

可讲的主题例如：
- 什么是市盈率（PE）？
- 什么是市值？
- 什么是财报？
- 美联储加息/降息对科技股有什么影响？
- 芯片行业常见术语：先进制程、HBM、CoWoS 等

要求：
- 先看仓库里最近几天的日报，避免重复昨天讲过的概念
- 用生活化的例子解释，控制在 300 字以内

### 五、给初学者的小建议

针对今天的新闻和数据，给出 1–2 条适合股市新手的观察建议或学习方向。

要求：
- 只给观察和学习建议，不要给具体买卖建议
- 语言简单、可执行

---

文末加一句：以上内容仅供学习参考，不构成投资建议。

## 总体要求

- 全文控制在 3000 字以内，适合手机阅读
- 不要写「继续阅读 / Continue Reading」，不要要求点开链接才能看到正文
- 忽略明显广告、营销号和低质内容
- 所有新闻和数字都要有来源；不确定的信息要明确标注
- 输出完整内容，不要省略任何一节
```

### 1.4 验证 Grok 写入

在 automation 页面点 **Run now**，然后检查：

1. 打开 <https://github.com/HappyyyyTingting/tech-digest/commits/main>。
2. 应该出现一条 `digest: YYYY-MM-DD` 的提交。
3. 点开 `digests/YYYY-MM-DD.md`，确认五个小节、来源链接和免责声明都在。
4. 回到 Grok 的 run history，确认运行没有报错。

之后 Grok 每个计划时间写入的新日报都会触发邮件 workflow。

## 2. 邮件服务

`scripts/send_email.py` 支持两种发送方式：

- **SMTP**：使用任意支持 SMTP 的邮箱，配置简单。
- **Resend**：通过 HTTPS API 发信，适合不想处理 SMTP 风控的场景。

两者只能选一个。`EMAIL_PROVIDER` 不设置时，如果存在 `RESEND_API_KEY` 则优先使用 Resend，否则使用 SMTP。建议显式设置 `EMAIL_PROVIDER`，避免误判。

### 2.1 SMTP

#### 通用配置

| Secret | 必需 | 说明 |
|---|---|---|
| `EMAIL_PROVIDER` | 建议 | `smtp` |
| `SMTP_HOST` | 是 | SMTP 服务器地址 |
| `SMTP_PORT` | 否 | 默认 `465`（SSL）或 `587`（STARTTLS） |
| `SMTP_SECURITY` | 建议 | `ssl` / `starttls` / `none` |
| `SMTP_USER` | 是 | 完整邮箱地址 |
| `SMTP_PASSWORD` | 是 | SMTP 授权码或应用专用密码，不是网页登录密码 |
| `MAIL_FROM` | 是 | 发件地址，可写成 `显示名 <邮箱>` |
| `MAIL_TO` | 是 | 收件地址，多个用英文逗号分隔 |
| `MAIL_REPLY_TO` | 否 | 回复地址 |

`SMTP_SECURITY` 不填时，脚本按端口推断：465 用 SSL，其他端口用 STARTTLS。`SMTP_SECURITY=none` 只建议在受控的内网测试环境使用，公网 25 端口通常被拦截。

#### QQ / Foxmail 示例

1. 登录 QQ 邮箱网页版 → 设置 → 账号 → 开启 **SMTP 服务**。
2. 按提示生成 **授权码**。`SMTP_PASSWORD` 填授权码，不是 QQ 登录密码。
3. 服务器填 `smtp.qq.com`，端口 `465`，加密方式 `ssl`。
4. `SMTP_USER` 和 `MAIL_FROM` 都填完整邮箱地址。

> GitHub Actions 的 runner 在海外，QQ / Foxmail 可能因为异地登录触发风控。如果出现登录失败、连接超时或 `550 From header invalid`，可以改用 Resend，或换其他 SMTP 服务。

#### 其他邮箱

在邮箱服务商帮助中心找到 SMTP 主机、端口和加密方式，填入对应 Secret 即可。常见组合：

- `465` + `ssl`
- `587` + `starttls`

如果服务商要求“应用专用密码”，用它代替登录密码。

### 2.2 Resend

1. 打开 <https://resend.com> 注册。
2. 在 **API Keys** 页面创建 key，权限选 `Sending access`。
3. 测试阶段可以使用 `onboarding@resend.dev` 作为发件人；它只能发送到 Resend 账号注册邮箱。
4. 长期使用或发送到其他地址时，在 Resend 验证自己的域名，然后把 `MAIL_FROM` 改成该域名下的地址。

| Secret | 必需 | 说明 |
|---|---|---|
| `EMAIL_PROVIDER` | 建议 | `resend` |
| `RESEND_API_KEY` | 是 | `re_...` |
| `MAIL_FROM` | 是 | `onboarding@resend.dev` 或已验证域名下的地址 |
| `MAIL_TO` | 是 | 收件地址，多个用英文逗号分隔 |
| `MAIL_REPLY_TO` | 否 | 回复地址 |

Resend 返回 `403` 时，先检查发件域名和收件地址是否符合上面的限制。

### 2.3 发件人显示名称

邮件里显示的发送人名称由 `MAIL_FROM` 控制，格式是：

```text
科技股市日报 <digest@example.com>
```

注意：

- 尖括号里的地址必须是 SMTP 服务允许的发件地址，通常要和 `SMTP_USER` 一致；Resend 则必须是已验证域名下的地址。
- 普通中文名称不需要引号；如果名称包含英文逗号、引号等特殊字符，用双引号包起来。
- 修改 Secret 后重新运行 workflow 即可，不需要改代码。
- 如果 SMTP 报 `550 From header invalid`，先把 `MAIL_FROM` 改回纯邮箱地址排查。

## 3. GitHub Actions Secrets

打开仓库：

`Settings → Secrets and variables → Actions → New repository secret`

把需要的名字和值逐个添加。Secret 名称要和 workflow 里引用的名称逐字一致。

workflow 会读取以下 Secrets：

```text
MAIL_TO
MAIL_FROM
MAIL_REPLY_TO
EMAIL_PROVIDER
RESEND_API_KEY
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_SECURITY
```

`MAIL_TO` 和 `MAIL_FROM` 是必填；其他变量按所选邮件服务填写。

### Secret 的可见性

- Secret 值不会出现在仓库文件里，也不能通过 GitHub 网页或 API 读回明文。
- 未登录访客打开 Actions 日志会看到 `Sign in to view logs`，看不到内容。
- 登录用户如果有仓库访问权限，可以看到公开仓库的 Actions 日志，但 GitHub 会对 secret 值自动打码。
- 有 write 权限的协作者可以修改 workflow 来读取 secret，所以只给信任的人写权限。
- 当前脚本只打印日报路径、邮件主题、HTML 大小和 provider，不打印邮箱、授权码或 API key。
- 不要把授权码、API key 写进 README、Markdown 或代码；建议使用专用发件邮箱和可撤销的凭据。

语音版还会读取 `R2_ACCOUNT_ID`、`R2_BUCKET`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY` 和 `AUDIO_BASE_URL` 等 Secrets，见下一节。

## 语音版（可选：Cloudflare R2 + GitHub Pages）

语音功能是可选的。没有配置 R2 时，workflow 的音频步骤会失败，但不会影响邮件；邮件顶部只是不会出现播放按钮。

### 原理

```text
digests/YYYY-MM-DD.md
  → scripts/make_audio.py   清洗成口语稿（去掉链接、表格符号）→ edge-tts → MP3
  → Cloudflare R2           https://<公开域名>/YYYY-MM-DD.mp3
  → scripts/build_site.py   扫描 digests/ + audio/*.json → index.html + feed.xml
  → GitHub Pages            https://<owner>.github.io/<repo>/
```

### 1. 创建 R2 bucket

1. 登录 <https://dash.cloudflare.com>，进入 **R2**，创建 bucket，例如 `tech-digest-audio`。
2. 打开 bucket 的 **Settings → Public access**：
   - 临时使用可以启用 **R2.dev subdomain**，得到 `https://pub-xxxx.r2.dev`。
   - 长期使用建议绑定自定义域名（例如 `audio.example.com`），播客客户端拉流更稳定。
3. 在 **Manage R2 API Tokens** 创建 token，权限选 **Object Read & Write**，范围只选这个 bucket。记下 Access Key ID 和 Secret Access Key。

### 2. 配置 Secrets 和 Variables

Secrets（`Settings → Secrets and variables → Actions → Secrets`）：

| 名称 | 值 |
|---|---|
| `R2_ACCOUNT_ID` | Cloudflare 账户 ID（R2 概览页右侧可见） |
| `R2_BUCKET` | bucket 名称，例如 `tech-digest-audio` |
| `R2_ACCESS_KEY_ID` | API token 的 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | API token 的 Secret Access Key |
| `AUDIO_BASE_URL` | 公开访问前缀，例如 `https://audio.example.com` 或 `https://pub-xxxx.r2.dev`；只填域名，不要带路径 |

> `AUDIO_BASE_URL` 是公开地址，会出现在邮件按钮、播放页和 feed 里；放在 Secrets 只是为了在 Actions 日志中自动打码。

Variables（同一页面的 **Variables** 标签）：

| 名称 | 必需 | 值 |
|---|---|---|
| `SITE_URL` | 否 | Pages 地址；默认 `https://<owner>.github.io/<repo>/` |
| `PODCAST_FEED_URL` | 否 | 邮件里的订阅链接；默认 `SITE_URL + feed.xml` |
| `TTS_VOICE` | 否 | 音色，默认 `zh-CN-XiaoxiaoNeural` |
| `TTS_RATE` | 否 | 语速，默认 `+0%`，可设为 `+10%` |

> MP3 从不进入 git：Actions 每次都是全新 checkout，音频只存在 R2，仓库不会逐年膨胀。

### 3. 开启 GitHub Pages

`Settings → Pages → Build and deployment → Source` 选择 **GitHub Actions**。workflow 会用 `upload-pages-artifact` + `deploy-pages` 发布 `site/` 目录。

发布后：

- 播放页：`https://<owner>.github.io/<repo>/`
- 播客 feed：`https://<owner>.github.io/<repo>/feed.xml`

可选：把一张 1400×1400 的封面图放到 `site/cover.jpg` 并提交，feed 会自动引用。

首次配置完成后，在 Actions 页面手动运行一次 workflow，并勾选 **`audio_only`**，生成第一期的音频和站点（不会重复发邮件）。

### 4. 订阅播客

在小宇宙、Apple Podcasts、Overcast、Pocket Casts 里选择「通过 URL 添加节目 / Add a Show by URL」，粘贴上面的 feed 地址。之后每天的新音频会自动出现在节目列表里，支持倍速、断点续播、锁屏和离线下载。

> feed 和播放页是公开的，即使仓库本身是私有的，GitHub Pages 站点默认也对所有人可见。如果日报不打算公开，可以把 `SITE_URL` 换成不可猜的路径，或改用带访问控制的托管方式（RSS 客户端不会跟随登录跳转）。

### 5. 本地生成与检查

```bash
# 只看口语稿（不联网、不出音频）
.venv/bin/python scripts/make_audio.py --latest --dry-run --text-out /tmp/spoken.txt

# 生成 MP3
.venv/bin/python scripts/make_audio.py --latest

# 上传（需要先 export R2_* 和 AUDIO_BASE_URL）
.venv/bin/python scripts/make_audio.py --latest --upload

# 本地生成播放页（--no-head 不检查远端文件）
.venv/bin/python scripts/build_site.py \
  --audio-base-url https://audio.example.com \
  --site-url https://example.github.io/tech-digest/ \
  --site-dir /tmp/tech-digest-site \
  --no-head
open /tmp/tech-digest-site/index.html
```

### 6. 语音相关排错

- **音频步骤失败，邮件仍正常**：这是设计。看日志里的 `语音合成失败` 或 `缺少 R2 配置`。
- **音频生成了但链接 404**：确认 R2 bucket 已开启公共访问，且 `AUDIO_BASE_URL` 和公开域名完全一致。
- **edge-tts 偶尔失败**：脚本会自动重试 3 次；仍失败可以重跑 workflow。
- **想换音色**：设置 `TTS_VOICE`，例如 `zh-CN-YunxiNeural`（男声）、`zh-CN-XiaoyiNeural`。可用音色见 `edge-tts --list-voices`。
- **补历史音频**：手动触发时把 `file` 填成某一天的路径，并勾选 `audio_only`，只生成音频和站点、不重复发邮件。一次处理一天，多跑几次即可。
- **想调整朗读速度**：设置 `TTS_RATE`，例如 `+10%`。

## 4. 触发方式

### 自动触发

Grok 把 `digests/YYYY-MM-DD.md` 提交到 `main` 后，workflow 会被 push 事件触发。它只处理本次新增或修改的 `digests/*.md`：

- `digests/_TEMPLATE.md` 会被忽略。
- 同一次 push 修改多个日报时，会逐个发送。
- `concurrency` 会让同一组任务排队，避免两封邮件同时发出。

### 手动触发

打开 `Actions → Send digest email → Run workflow`：

- `file` 留空：使用最新一份日报。
- `file` 填 `digests/2026-10-23.md`：发送指定日报。
- `dry_run` 勾选：只渲染，不发送，运行结束后下载 `email-preview` artifact。
- `audio_only` 勾选：只生成语音和 Pages 站点，不发送邮件；补历史音频时用。

`dry_run` 的预览文件是：

```text
email_preview.html
email_preview.txt
```

artifact 默认保留 7 天。

## 5. 本地调试

```bash
cd /path/to/tech-digest
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 只生成预览
.venv/bin/python scripts/send_email.py --file digests/2026-10-23.md --dry-run
open email_preview.html

# 本地真实发送（以 SMTP 为例）
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

.venv/bin/python scripts/send_email.py --latest
unset SMTP_PASSWORD
```

使用 Resend 时，把 SMTP 变量换成：

```bash
export EMAIL_PROVIDER='resend'
export RESEND_API_KEY='re_...'
```

运行测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 6. 邮件渲染规则

- **主题**：日报第一个 `# ` 标题；没有标题时使用「科技股市入门日报 + 日期」。
- **正文**：完整 Markdown 转 HTML，保留标题、列表、表格、引用和来源链接。
- **纯文本**：同时生成 `text/plain` 版本，链接显示为 `文字 (URL)`。
- **样式**：单栏、最大宽度 640px、16px 字号、1.75 行高、移动端媒体查询。
- **安全**：Markdown 原始 HTML 会被转义；`javascript:`、`vbscript:`、`data:` 等危险链接会被拦截。
- **大小**：超过约 90KB 会在日志里警告，但不会截断。正常 3000 字日报约 10KB。

## 7. 排错

### Grok 说没有权限或无法写入

- 回到 <https://grok.com/connectors> 重新授权 GitHub。
- 确认选择的是 **Only select repositories**，并且勾选了 `tech-digest`。
- 确认授予了 write 权限。
- 如果仓库开了分支保护，允许 connector 直接提交，或改成提交到新分支并在 workflow 里调整触发分支。

### Grok 提交到 `master` 而不是 `main`

在 GitHub 仓库 `Settings → Branches` 把默认分支改成 `main`，或者把 prompt 里的分支名改成实际分支，并同步修改 workflow 的 `branches`。

### Grok 写到了根目录或路径不对

Grok 必须写到 `digests/YYYY-MM-DD.md`。检查 prompt 是否完整复制；路径不对时 workflow 的 `paths: digests/*.md` 不会触发。

### 推送后 workflow 没有运行

- 确认改动的是 `main` 分支上的 `digests/*.md`，不是根目录或其他路径。
- 打开仓库的 `Actions` 页面，看 `Send digest email` 是否有运行记录。
- 检查 `Settings → Actions → General` 是否允许 Actions 运行。
- 本 workflow 由 push 触发，不受 GitHub 定时任务 60 天无活动限制。
- 如果 Grok 通过 GitHub App 提交后确实没有触发，使用 `workflow_dispatch` 手动补发。

### 日志提示缺少配置

脚本会明确列出缺少的变量，例如：

```text
错误：缺少 SMTP 配置：SMTP_HOST, SMTP_USER, SMTP_PASSWORD
```

回到 `Settings → Secrets and variables → Actions` 补齐即可。注意 Secret 名称必须完全一致。

### SMTP 登录失败

- QQ / Foxmail / 163 的 SMTP 密码是 **授权码**，不是网页登录密码。
- 确认邮箱设置里已经开启 SMTP 服务。
- 465 端口配 `SMTP_SECURITY=ssl`；587 端口配 `starttls`。
- 海外 GitHub runner 可能触发邮箱风控，换 Resend 通常最省事。

### SMTP 报 `550 From header invalid`

- 把 `MAIL_FROM` 先改回纯邮箱地址，不要带显示名称。
- 确认 `MAIL_FROM` 的地址与 `SMTP_USER` 一致，或属于服务商允许的发件地址。
- 确认服务商没有强制要求发件地址与登录账号完全一致。

### Resend 返回 403

- `onboarding@resend.dev` 只能发送到 Resend 账号注册邮箱。
- 如果要发给其他地址，先在 Resend 验证自己的域名，再用该域名下的发件地址。
- 确认 API key 有 `Sending access` 权限。

### 邮件进了垃圾箱

- 把发件人加入联系人。
- 使用 Resend 并验证自己的域名，配置 SPF / DKIM，送达率会明显更好。
- 测试阶段用 `onboarding@resend.dev` 时，部分邮箱会把它当陌生发件人。

### 收到了旧日报或重复邮件

- push 触发只发送本次改动或新增的 `digests/*.md`。
- 手动 `workflow_dispatch` 留空 `file` 时会发送最新一份，不判断是否已经发过。
- 如果同一天 Grok 覆盖了日报，会再发一次更新版，这是预期行为。
- 想避免重复，可以在手动触发时指定具体文件，或之后增加“已发送”状态文件。

### 想调整邮件样式

编辑 `scripts/send_email.py` 里的 `_email_css()` 和 `wrap_email_html()`，运行本地预览确认后再 push。下一次日报会使用新样式。

## 8. 公开仓库注意事项

- 日报内容来自公开的 X 帖子和媒体，公开没有问题。
- 不要把 API key、邮箱密码、个人隐私写进 Markdown。
- 真实收件地址、发件地址和授权码只放在 GitHub Actions Secrets，不要写进 README 或提交历史。
- 如果曾经把凭据写进文件，立即在邮件服务商处撤销并重新生成，然后清理 Git 历史。
